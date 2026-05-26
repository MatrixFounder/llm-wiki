---
description: SQL-level health-check across one wiki vault or all registered vaults
---

Run via Bash:

```bash
wiki-lint $ARGUMENTS
```

Wrapper at `bin/wiki-lint` handles cd + venv activation; works from any
CWD when the repo's `bin/` is on `PATH`. See `skills/wiki-lint/SKILL.md`
for issue categories, flags, exit semantics.
