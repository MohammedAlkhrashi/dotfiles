---
name: interactive-notebook
description: Collaborate on Cursor or VS Code # %% interactive notebooks via the live ipykernel. Shared kernel state for running cells, inspecting variables, adding cells, fixing errors, and exploratory analysis. Use when the user works in interactive Python cells, mentions notebook collaboration, asks to run/fix/add cells, inspect kernel variables, or debug # %% output in any project.
---

# Interactive Notebook Collaboration

Work **with** the user in their live Cursor session — same kernel, same variables, same data in memory.

**Bridge:** `~/.cursor/skills/interactive-notebook/scripts/kernel_bridge.py` (never in repos)

## One-time machine setup

```bash
pip install jupyter_client          # in the Python env Cursor uses as kernel
python ~/.cursor/skills/interactive-notebook/scripts/kernel_bridge.py check
```

In Cursor: select the **same interpreter** as your kernel (bottom-right Python version). Run one `# %%` cell to start the kernel.

## Collaboration loop

1. **Connect** — `check` or `list`; user has run ≥1 cell
2. **Orient** — `cells <file>` and/or `variables`
3. **Act** — run cells, edit file, add `# %%` blocks, `exec` snippets
4. **Report** — what you ran, what you saw, what changed

### User request → action

| User says | You do |
|-----------|--------|
| "fix the last cell" | `cells` → edit → `run --last 1` |
| "run the last 3 cells" | `run <file> --last 3` |
| "run everything" | `run <file> --all` |
| "rerun from cell 2" | `run <file> --range 2:-1` |
| "add a cell to …" | edit file → `run` new cell |
| "what do we have?" / "what's loaded?" | `variables` |
| "what does df look like?" | `exec "print(df.info()); print(df.head())"` |
| "cell N errored" | `run <file> N` → fix → rerun |
| "kernel restarted" | `run <file> <n> --from-start` |

### Multiple kernels

Use context when obvious; **ask which file** when ambiguous.

### Shared state

- Default: run only needed cells (prior state stays in memory)
- `--from-start`: rebuild after kernel restart or `NameError`
- Never use `python -c` for interactive state — use the bridge

## Commands

```bash
BRIDGE=~/.cursor/skills/interactive-notebook/scripts/kernel_bridge.py

python "$BRIDGE" check
python "$BRIDGE" cells <file>
python "$BRIDGE" variables
python "$BRIDGE" run <file> <index>
python "$BRIDGE" run <file> --last 3
python "$BRIDGE" run <file> --range 2:-1
python "$BRIDGE" run <file> --all
python "$BRIDGE" exec "print(df.shape)"
python "$BRIDGE" list
```

## Seeing output without rerunning

**Short answer:** `print()` output from cells you already ran is **not** stored in the kernel — Cursor shows it in the UI only. The agent cannot read that UI buffer today.

| What | Without rerun? |
|------|----------------|
| `print()` / stdout | No — rerun cell, or use session log (below) |
| Last expression result (`df.head()` as last line) | Yes — `history` |
| Past cell source code | Yes — `history` |
| Variables in memory | Yes — `variables` or `exec` |

```bash
python "$BRIDGE" history --last 5   # recent inputs + return values
python "$BRIDGE" enable-log        # once per session, before analysis cells
python "$BRIDGE" logs --last 50    # read captured stdout/stderr after that
```

Run `enable-log` early in a session (or as first cell) so later cells' prints land in `/tmp/cursor-nb-session.log`. Logging is not retroactive.

Manual fallback: paste output into chat, or **Jupyter: Export Interactive Window as Jupyter Notebook** and point the agent at the `.ipynb`.

## Plots and rich output

The bridge captures **text only** — not inline charts. For visual collaboration:

```python
# In a cell or exec — save so the agent can read the image
import matplotlib.pyplot as plt
plt.savefig("/tmp/nb-plot.png", bbox_inches="tight", dpi=120)
plt.close()
```

Then read `/tmp/nb-plot.png`. Prefer `/tmp/nb-*.png` to avoid cluttering the project.

## Adding cells

- Append or insert `# %%` blocks; optional title after marker: `# %% Load EOD data`
- Match existing imports and style; keep cells small
- Run via bridge after edits

## Rules

- Do **not** add bridge scripts to the user's project
- Do **not** start Jupyter Notebook/Lab unless asked
- Avoid bridge calls while user is mid-execution on the same kernel

## What helps the user (tell them if missing)

- **Same Python env** for kernel and bridge (`check` verifies connectivity)
- **Say "kernel restarted"** when they hit Restart — agent should `--from-start`
- **Name the file** when multiple notebooks are open
- **Move skill to personal** (`~/.cursor/skills/interactive-notebook/SKILL.md`) when ready for all projects; delete per-repo copy

## Optional: personal Cursor user rule

Add in Cursor Settings → Rules (user-level):

> When I work in `# %%` interactive Python files, use the interactive-notebook skill and kernel bridge for execution — not fresh subprocesses.

## Further reading

Setup checklist and limitations: [reference.md](reference.md)
