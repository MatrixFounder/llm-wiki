---
description: Format-aware, tag-routed ingest dispatcher — scan a zone → plan → convert/ingest/upsert/skip
---

`/wiki-sync` is a **two-phase** skill (Decision-17). `scan` is deterministic
Python: it walks a zone, classifies every file (by extension + `#wiki/*` tags +
generated-view detection + a layout-general type check), and emits a strict
**plan JSON** — NO LLM, network, or mutation. The orchestrator then executes the
plan (convert office/PDF → staged `_raw/.staging/`, de-timestamp `.vtt`/`.srt`,
H-6-fence the raw body, summarise → `wiki-enrich` → `wiki-extract-concepts`,
or `wiki-index-upsert` a ready note), recording a per-file `source_state`
commit-marker so a re-run is a no-op.

Execute the workflow at [`workflows/wiki-sync.md`](../workflows/wiki-sync.md).
Do **not** hand-run the convert/summarise steps — follow the recipe (per-vault
`flock`, per-file isolation, idempotency).

Quick reference (wrapper at `bin/wiki-sync` handles cd + venv):

```bash
# deterministic plan (no mutation)
wiki-sync scan <zone> --vault <id> [--vault-root <path>]
# preview every action + skip-reason, write nothing
wiki-sync scan <zone> --vault <id> --dry-run
```

Exit codes: `0` ok · `2` precondition (zone missing / outside vault / no vault
root) · `6` config-invalid (`.wiki/sync.yaml`). See `skills/wiki-sync/SKILL.md`
for the plan-JSON schema + the full flag/exit reference.
