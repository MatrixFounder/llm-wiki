---
description: Append a structured event to log.md AND mirror it to log_events (bi-directional sync)
---

Run via Bash:

```bash
wiki-append-log $ARGUMENTS
```

Wrapper at `bin/wiki-append-log` handles cd + venv activation; works from
any CWD when the repo's `bin/` is on `PATH`. See
`skills/wiki-append-log/SKILL.md` for event-type enum, atomicity guarantees.
