---
description: Promote a candidate entity to confirmed (or --undo / --auto by mention threshold)
---

Run via Bash:

```bash
wiki-confirm $ARGUMENTS
```

Wrapper at `bin/wiki-confirm` handles cd + venv activation; works from any
CWD when the repo's `bin/` is on `PATH`. See `skills/wiki-confirm/SKILL.md`
for flags (`--undo`, `--auto`, `--threshold`, `--dry-run`) and exit semantics.
