---
description: Index a single markdown file into the SQLite index (idempotent)
---

Run via Bash:

```bash
wiki-index-upsert $ARGUMENTS
```

Wrapper at `bin/wiki-index-upsert` handles cd + venv activation; works from
any CWD when the repo's `bin/` is on `PATH`. See
`skills/wiki-index-upsert/SKILL.md` for normalization rules, exit codes.
