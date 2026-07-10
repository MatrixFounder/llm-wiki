---
description: Inspect / validate / repair / edit the per-folder .wiki/sync.yaml config (provenance, doctor, templates, HTML report, web editor)
---

Run via Bash:

```bash
wiki-config $ARGUMENTS
```

Wrapper at `bin/wiki-config` handles venv activation; works from any CWD when
the repo's `bin/` is on `PATH`. See `skills/wiki-config/SKILL.md` for the
subcommand table, finding taxonomy, and exit semantics. When the human asks
"which settings does this folder inherit", render the `show` envelope's
`provenance` map as a table (pointer / value / origin / shadows).
