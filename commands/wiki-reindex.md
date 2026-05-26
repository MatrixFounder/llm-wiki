---
description: Rebuild the SQLite index from markdown files (--full or --delta)
---

Run via Bash:

```bash
wiki-reindex $ARGUMENTS
```

Wrapper at `bin/wiki-reindex` handles cd + venv activation; works from any
CWD when the repo's `bin/` is on `PATH`. See `skills/wiki-reindex/SKILL.md`
for mode semantics, output schema. ADR-002 §D8 — this is THE rebuildability
gate.
