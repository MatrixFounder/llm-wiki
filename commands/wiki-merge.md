---
description: Fold a duplicate entity into the canonical one (re-point refs + redirect aliases)
---

Run via Bash:

```bash
wiki-merge $ARGUMENTS
```

Wrapper at `bin/wiki-merge` handles cd + venv activation; works from any
CWD when the repo's `bin/` is on `PATH`. See `skills/wiki-merge/SKILL.md`
for the Class-A-first write order, the alias-redirect mechanism, and exit
semantics.
