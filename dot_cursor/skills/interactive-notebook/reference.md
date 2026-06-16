# Interactive Notebook — Reference

## Setup checklist

- [ ] `pip install jupyter_client` in kernel Python env
- [ ] Cursor kernel picker matches that env
- [ ] `python ~/.cursor/skills/interactive-notebook/scripts/kernel_bridge.py check` → `status: ready`
- [ ] Skill at `~/.cursor/skills/interactive-notebook/SKILL.md` (personal) or `.cursor/skills/...` (per project)
- [ ] Optional: user-level Cursor rule pointing agents to this skill

## What works well

- Shared in-memory state (DataFrames, models, imports)
- Fast iteration: run one cell, inspect, fix, rerun
- Adding cells collaboratively
- Text output, errors, `df.head()`, `variables`

## Limitations

| Gap | Workaround |
|-----|------------|
| **Past `print()` output** | Not in kernel; use `enable-log` going forward, rerun, paste, or export IW to `.ipynb` |
| Past expression results | `history` (no rerun) |
| Inline matplotlib in Cursor UI | `savefig` to `/tmp/nb-*.png`; agent reads file |
| Widgets / `%matplotlib widget` | Not supported via bridge |
| Multiple kernels | Agent asks which file, or user names it |
| Very long-running cells | Increase `--timeout` on bridge commands |
| Kernel dies | User restarts in Cursor; agent uses `--from-start` |

### Why print output disappears

When a cell runs, stdout streams to Cursor's Interactive Window over ZMQ. IPython does not keep that text in memory — only return values land in `Out[n]`. Cursor does not expose the IW text buffer to agents (workspace storage has URIs/metadata only).

## Habits that speed collaboration

1. Run imports + data-load cells once; then iterate on analysis cells
2. Say **which file** if you have several `.py` notebooks open
3. Say **"kernel restarted"** after Restart — don't assume state exists
4. Keep notebook `.py` files in git; keep large data out of git (`.gitignore`)

## New machine

```bash
pip install jupyter_client
# copy ~/.cursor/skills/interactive-notebook/ from dotfiles or recreate from repo skill
python ~/.cursor/skills/interactive-notebook/scripts/kernel_bridge.py check
```
