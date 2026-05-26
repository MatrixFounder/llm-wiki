---
description: Render index.md projection from the SQLite index (preserves BEGIN-CUSTOM blocks)
---

Run via Bash:

```bash
wiki-index-render $ARGUMENTS
```

Wrapper at `bin/wiki-index-render` handles cd + venv activation; works from
any CWD when the repo's `bin/` is on `PATH`. See
`skills/wiki-index-render/SKILL.md` for custom-section behavior.
