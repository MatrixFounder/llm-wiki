---
description: LLM-driven concept extraction from an indexed source page; emits a wiki-ingest v1.1 manifest and optionally dispatches in-process to the indexer
---

Run via Bash:

```bash
wiki-extract-concepts $ARGUMENTS
```

The wrapper at `bin/wiki-extract-concepts` cd's into the repo and activates
its venv, so this works from any CWD as long as the repo's `bin/` is on
`PATH` (see `bin/install-globally.sh`). See
`skills/wiki-extract-concepts/SKILL.md` for invocation modes (inspection
vs `--ingest` auto-dispatch), exit codes, and the underlying manifest
contract.
