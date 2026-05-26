---
description: FTS5 full-text search across one or more registered wiki vaults
---

Run via Bash:

```bash
wiki-search $ARGUMENTS
```

The wrapper at `bin/wiki-search` cd's into the repo and activates its venv,
so this works from any CWD as long as the repo's `bin/` is on `PATH`
(see `bin/install-globally.sh`). See `skills/wiki-search/SKILL.md` for
query syntax, flags, output schema.
