---
description: Bootstrap or register a wiki vault (scaffold-new / register-existing / reconcile)
---

Run via Bash:

```bash
wiki-init $ARGUMENTS
```

Wrapper at `bin/wiki-init` handles cd + venv activation; works from any
CWD when the repo's `bin/` is on `PATH`. See `skills/wiki-init/SKILL.md`
for modes, flags, exit codes. Operator must pass `--vault <abs-path>`
explicitly (no cwd default).
