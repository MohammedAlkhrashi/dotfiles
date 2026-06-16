#!/usr/bin/env python3
"""Bridge to the live Cursor/VS Code ipykernel for collaborative cell execution."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from jupyter_client import BlockingKernelClient

CELL_MARKER = re.compile(r"^#\s*%%\s*(.*)$")
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
SESSION_LOG = Path("/tmp/cursor-nb-session.log")


def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE.sub("", text)


def runtime_dirs() -> list[Path]:
    dirs: list[Path] = []
    try:
        from jupyter_core.paths import jupyter_runtime_dir

        dirs.append(Path(jupyter_runtime_dir()))
    except Exception:
        pass

    xdg = os.environ.get("XDG_RUNTIME_DIR")
    if xdg:
        dirs.append(Path(xdg) / "jupyter" / "runtime")

    try:
        dirs.append(Path(f"/run/user/{os.getuid()}/jupyter/runtime"))
    except Exception:
        pass

    seen: set[Path] = set()
    unique: list[Path] = []
    for path in dirs:
        if path in seen or not path.is_dir():
            continue
        seen.add(path)
        unique.append(path)
    return unique


def find_kernels() -> list[Path]:
    kernels: list[Path] = []
    for runtime_dir in runtime_dirs():
        kernels.extend(runtime_dir.glob("kernel-*.json"))
    return sorted(kernels, key=os.path.getmtime, reverse=True)


def connect_kernel(connection_file: Path | None = None) -> BlockingKernelClient:
    candidates = [connection_file] if connection_file else find_kernels()
    if not candidates or candidates == [None]:
        raise SystemExit(
            "No active ipykernel found. Run at least one # %% cell in Cursor first."
        )

    errors: list[str] = []
    for candidate in candidates:
        if candidate is None:
            continue
        client = BlockingKernelClient()
        client.load_connection_file(str(candidate))
        client.start_channels()
        try:
            client.wait_for_ready(timeout=15)
            return client
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")
            client.stop_channels()

    raise SystemExit(
        "No responding ipykernel found. Run a cell in Cursor first.\n"
        + "\n".join(errors)
    )


def parse_cells(source: str) -> list[tuple[str, str]]:
    lines = source.splitlines(keepends=True)
    cells: list[tuple[str, str]] = []
    title = ""
    start = 0

    for index, line in enumerate(lines):
        match = CELL_MARKER.match(line.rstrip("\n"))
        if not match:
            continue
        if index > start or cells:
            code = "".join(lines[start:index]).strip("\n")
            if code.strip():
                cells.append((title, code))
        title = match.group(1).strip()
        start = index + 1

    tail = "".join(lines[start:]).strip("\n")
    if tail.strip():
        cells.append((title, tail))
    return cells


def cell_preview(code: str, max_len: int = 60) -> str:
    for line in code.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            text = stripped.replace("\t", " ")
            return text[: max_len - 3] + "..." if len(text) > max_len else text
    return "(empty)"


VARIABLES_CODE = """
import types

_ipy_skip = {
    "In", "Out", "get_ipython", "exit", "quit", "open", "license",
    "copyright", "credits", "help", "dir", "vars", "exec", "eval",
}
_ns = get_ipython().user_ns if get_ipython() else globals()
_rows = []
for name in sorted(_ns):
    if name.startswith("_") or name in _ipy_skip:
        continue
    val = _ns[name]
    if isinstance(val, types.ModuleType):
        continue
    kind = type(val).__name__
    if hasattr(val, "shape"):
        detail = f"shape={tuple(val.shape)}"
    elif hasattr(val, "__len__"):
        try:
            detail = f"len={len(val)}"
        except TypeError:
            detail = ""
    else:
        detail = repr(val)[:80]
    _rows.append(f"{name}: {kind}" + (f" ({detail})" if detail else ""))
print("\\n".join(_rows) if _rows else "(no user variables)")
""".strip()

ENABLE_LOG_CODE = f"""
import sys
from pathlib import Path

_LOG = Path({SESSION_LOG!r})

class _Tee:
    def __init__(self, stream):
        self._stream = stream
    def write(self, data):
        if data:
            self._stream.write(data)
            with _LOG.open("a") as handle:
                handle.write(data)
    def flush(self):
        self._stream.flush()
    def __getattr__(self, name):
        return getattr(self._stream, name)

if not isinstance(sys.stdout, _Tee):
    _LOG.write_text("")
    sys.stdout = _Tee(sys.stdout)
    sys.stderr = _Tee(sys.stderr)
print("session logging -> " + str(_LOG))
""".strip()


def history_code(count: int) -> str:
    return f"""
n = {count}
start = max(1, len(In) - n + 1)
for i in range(start, len(In) + 1):
    print(f"=== execution {{i}} ===")
    print(In[i - 1])
    if i in Out:
        print("--- return value ---")
        value = Out[i]
        if hasattr(value, "_repr_pretty_"):
            from IPython.lib.pretty import pretty
            print(pretty(value, max_width=120))
        else:
            print(repr(value)[:2000])
    print()
""".strip()


def resolve_indices(
    cell_count: int,
    cell: int | None,
    *,
    from_start: bool = False,
    last: int | None = None,
    range_spec: str | None = None,
    run_all: bool = False,
) -> list[int]:
    if cell_count == 0:
        raise SystemExit("No cells in file.")

    modes = sum(
        1
        for x in (last, range_spec, run_all)
        if x is not None and x is not False
    )
    if cell is not None:
        modes += 1
    if from_start:
        modes += 1
    if modes > 1 and not (cell is not None and from_start and not last and not range_spec and not run_all):
        if sum(1 for x in (last, range_spec, run_all) if x) > 0 or (
            from_start and (last or range_spec or run_all)
        ):
            raise SystemExit("Use only one of: cell index, --from-start, --last, --range, --all")

    if run_all:
        return list(range(cell_count))

    if last is not None:
        if last <= 0 or last > cell_count:
            raise SystemExit(f"--last {last} out of range (1..{cell_count})")
        return list(range(cell_count - last, cell_count))

    if range_spec is not None:
        if ":" not in range_spec:
            raise SystemExit("--range must be START:END (END may be -1 for last cell)")
        start_text, end_text = range_spec.split(":", 1)
        start = int(start_text)
        end = cell_count - 1 if end_text == "-1" else int(end_text)
        if start < 0 or end >= cell_count or start > end:
            raise SystemExit(f"Range {range_spec} out of range (0..{cell_count - 1})")
        return list(range(start, end + 1))

    if cell is None:
        raise SystemExit("Provide a cell index, --last, or --range")

    if cell < 0 or cell >= cell_count:
        raise SystemExit(f"Cell index {cell} out of range (0..{cell_count - 1})")

    if from_start:
        return list(range(0, cell + 1))
    return [cell]


def execute_code(client: BlockingKernelClient, code: str, timeout: float = 120) -> dict:
    msg_id = client.execute(code)
    streams: dict[str, list[str]] = {"stdout": [], "stderr": []}
    results: list[dict] = []
    error: dict | None = None
    status = "unknown"

    while True:
        msg = client.get_iopub_msg(timeout=timeout)
        if msg["parent_header"].get("msg_id") != msg_id:
            continue

        msg_type = msg["msg_type"]
        content = msg["content"]

        if msg_type == "stream":
            streams[content["name"]].append(content["text"])
        elif msg_type in ("execute_result", "display_data"):
            results.append(content.get("data", {}))
        elif msg_type == "error":
            error = {
                "ename": content["ename"],
                "evalue": content["evalue"],
                "traceback": content["traceback"],
            }
        elif msg_type == "status" and content["execution_state"] == "idle":
            break

    reply = client.get_shell_msg(timeout=timeout)
    if reply["parent_header"].get("msg_id") == msg_id:
        status = reply["content"].get("status", status)

    return {
        "status": status,
        "stdout": "".join(streams["stdout"]),
        "stderr": "".join(streams["stderr"]),
        "results": results,
        "error": error,
    }


def format_output(cell_index: int, title: str, code: str, result: dict) -> str:
    parts = [f"=== cell {cell_index}" + (f" ({title})" if title else "") + " ==="]
    parts.append(code)
    parts.append("--- output ---")

    if result["stdout"]:
        parts.append(result["stdout"].rstrip())
    if result["stderr"]:
        parts.append(result["stderr"].rstrip())
    for item in result["results"]:
        if "text/plain" in item:
            parts.append(item["text/plain"])
    if result["error"]:
        traceback = "\n".join(strip_ansi(line) for line in result["error"]["traceback"])
        parts.append(traceback)
        parts.append(f"status: {result['status']}")
    elif result["status"] == "ok":
        parts.append("status: ok")
    else:
        parts.append(f"status: {result['status']}")

    return "\n".join(parts)


def run_cells(
    client: BlockingKernelClient,
    cells: list[tuple[str, str]],
    indices: list[int],
    timeout: float,
) -> int:
    exit_code = 0
    for index in indices:
        title, code = cells[index]
        result = execute_code(client, code, timeout=timeout)
        print(format_output(index, title, code, result))
        print()
        if result["error"]:
            exit_code = 1
            break
    return exit_code


def cmd_list(_: argparse.Namespace) -> int:
    kernels = find_kernels()
    if not kernels:
        print("No active kernels.")
        return 1
    for path in kernels:
        with path.open() as handle:
            info = json.load(handle)
        print(f"{path}\t{info.get('kernel_name', '?')}")
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    client = connect_kernel(args.connection)
    try:
        result = execute_code(client, history_code(args.last), timeout=args.timeout)
    finally:
        client.stop_channels()
    if result["error"]:
        print("\n".join(strip_ansi(line) for line in result["error"]["traceback"]))
        return 1
    print(result["stdout"].rstrip() or "(no history)")
    print(
        "\nNote: print() output is not stored in the kernel — only inputs and "
        "expression return values appear here."
    )
    return 0


def cmd_enable_log(args: argparse.Namespace) -> int:
    client = connect_kernel(args.connection)
    try:
        result = execute_code(client, ENABLE_LOG_CODE, timeout=args.timeout)
    finally:
        client.stop_channels()
    if result["error"]:
        print("\n".join(strip_ansi(line) for line in result["error"]["traceback"]))
        return 1
    print(result["stdout"].rstrip())
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    if not SESSION_LOG.is_file():
        raise SystemExit(
            f"No session log at {SESSION_LOG}. Run: python .../kernel_bridge.py enable-log"
        )
    lines = SESSION_LOG.read_text().splitlines()
    tail = lines[-args.last :] if args.last else lines
    print("\n".join(tail))
    return 0


def cmd_check(_: argparse.Namespace) -> int:
    try:
        import jupyter_client  # noqa: F401
    except ImportError:
        print("jupyter_client: NOT INSTALLED (pip install jupyter_client)")
        return 1
    print("jupyter_client: ok")

    kernels = find_kernels()
    print(f"kernels found: {len(kernels)}")
    if not kernels:
        print("status: no kernel — run a # %% cell in Cursor first")
        return 1

    client = connect_kernel(kernels[0])
    client.stop_channels()
    print(f"latest kernel: {kernels[0]}")
    print("status: ready")
    return 0


def cmd_variables(args: argparse.Namespace) -> int:
    client = connect_kernel(args.connection)
    try:
        result = execute_code(client, VARIABLES_CODE, timeout=args.timeout)
    finally:
        client.stop_channels()
    if result["error"]:
        print("\n".join(strip_ansi(line) for line in result["error"]["traceback"]))
        return 1
    print(result["stdout"].rstrip() or "(no output)")
    return 0


def cmd_cells(args: argparse.Namespace) -> int:
    path = Path(args.file)
    cells = parse_cells(path.read_text())
    if not cells:
        raise SystemExit(f"No # %% cells found in {path}")

    for index, (title, code) in enumerate(cells):
        label = f" [{title}]" if title else ""
        print(f"{index}:{label} {cell_preview(code)}")
    print(f"({len(cells)} cells, indices 0..{len(cells) - 1})")
    return 0


def cmd_exec(args: argparse.Namespace) -> int:
    client = connect_kernel(args.connection)
    try:
        result = execute_code(client, args.code, timeout=args.timeout)
    finally:
        client.stop_channels()
    print(format_output(-1, "", args.code, result))
    return 1 if result["error"] else 0


def cmd_run(args: argparse.Namespace) -> int:
    path = Path(args.file)
    cells = parse_cells(path.read_text())
    if not cells:
        raise SystemExit(f"No # %% cells found in {path}")

    indices = resolve_indices(
        len(cells),
        args.cell,
        from_start=args.from_start,
        last=args.last,
        range_spec=args.range,
        run_all=args.all,
    )

    client = connect_kernel(args.connection)
    try:
        exit_code = run_cells(client, cells, indices, args.timeout)
    finally:
        client.stop_channels()
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List active ipykernels")
    list_parser.set_defaults(func=cmd_list)

    check_parser = subparsers.add_parser("check", help="Verify bridge setup and kernel connectivity")
    check_parser.set_defaults(func=cmd_check)

    variables_parser = subparsers.add_parser("variables", help="List variables in the live kernel")
    variables_parser.add_argument("--connection", type=Path, default=None)
    variables_parser.add_argument("--timeout", type=float, default=30)
    variables_parser.set_defaults(func=cmd_variables)

    history_parser = subparsers.add_parser(
        "history",
        help="Show recent kernel inputs and return values (not print output)",
    )
    history_parser.add_argument(
        "--last",
        type=int,
        default=5,
        metavar="N",
        help="Number of recent executions to show (default: 5)",
    )
    history_parser.add_argument("--connection", type=Path, default=None)
    history_parser.add_argument("--timeout", type=float, default=30)
    history_parser.set_defaults(func=cmd_history)

    enable_log_parser = subparsers.add_parser(
        "enable-log",
        help="Tee stdout/stderr to /tmp/cursor-nb-session.log for this session",
    )
    enable_log_parser.add_argument("--connection", type=Path, default=None)
    enable_log_parser.add_argument("--timeout", type=float, default=30)
    enable_log_parser.set_defaults(func=cmd_enable_log)

    logs_parser = subparsers.add_parser(
        "logs",
        help="Read session log written by enable-log",
    )
    logs_parser.add_argument(
        "--last",
        type=int,
        default=100,
        metavar="N",
        help="Last N lines (default: 100)",
    )
    logs_parser.set_defaults(func=cmd_logs)

    cells_parser = subparsers.add_parser("cells", help="List cells in a # %% file")
    cells_parser.add_argument("file", help="Path to .py file with # %% cells")
    cells_parser.set_defaults(func=cmd_cells)

    exec_parser = subparsers.add_parser("exec", help="Execute code in the live kernel")
    exec_parser.add_argument("code", help="Python code to run")
    exec_parser.add_argument("--connection", type=Path, default=None)
    exec_parser.add_argument("--timeout", type=float, default=120)
    exec_parser.set_defaults(func=cmd_exec)

    run_parser = subparsers.add_parser("run", help="Run cells from a # %% notebook file")
    run_parser.add_argument("file", help="Path to .py file with # %% cells")
    run_parser.add_argument("cell", type=int, nargs="?", default=None, help="0-based cell index")
    run_parser.add_argument(
        "--from-start",
        action="store_true",
        help="With CELL: run cells 0 through CELL inclusive",
    )
    run_parser.add_argument(
        "--last",
        type=int,
        metavar="N",
        help="Run the last N cells (e.g. --last 3)",
    )
    run_parser.add_argument(
        "--range",
        metavar="START:END",
        help="Run inclusive range; END=-1 means last cell (e.g. 2:-1)",
    )
    run_parser.add_argument("--all", action="store_true", help="Run every cell in the file")
    run_parser.add_argument("--connection", type=Path, default=None)
    run_parser.add_argument("--timeout", type=float, default=120)
    run_parser.set_defaults(func=cmd_run)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
