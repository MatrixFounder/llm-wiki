---
description: Format-aware, tag-routed ingest dispatcher — scan a zone → plan → convert/ingest/upsert/skip
---

`/wiki-sync` is a **two-phase** skill (Decision-17). `scan` is deterministic
Python: it walks a zone, classifies every file (by extension + `#wiki/*` tags +
generated-view detection + a layout-general type check), and emits a strict
**plan JSON** — NO LLM, network, or mutation. The orchestrator then executes the
plan (delegate each distil source whole to `wiki-import` — which owns
fetch+convert, H-6 fencing, REASON, and concept filing — or `wiki-index-upsert`
a ready note), recording a per-file `source_state` commit-marker so a re-run is a
no-op.

**Workflow location (works from any CWD, incl. a vault):** the workflow file lives in the
obsidian-llm-wiki REPO, not in the current directory — resolve it through this command's own
symlink:

1. Run (plain command — pre-allowed, no shell constructs, so no permission prompt):

   ```bash
   readlink -f ~/.claude/commands/wiki-sync.md
   ```

2. The output is `<repo>/commands/wiki-sync.md`. Derive the workflow path YOURSELF (no shell):
   replace `commands/wiki-sync.md` with `workflows/wiki-sync.md`.
3. Open that file with the **Read tool** (not cat) and follow its steps.

Follow the workflow's steps. (Symlink absent → ask the user for the repo path and use
`<repo>/workflows/wiki-sync.md` — do NOT improvise the procedure from memory.)
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

## The typed-knowledge dispatch flag (TASK 063)

A `scan` entry's `delegate` block may carry `"extract_decisions": true`, resolved from
the per-folder `.wiki/sync.yaml` cascade.

When it is true, after `wiki-import` has filed the note, **run the extraction rail on
that note** (`wiki-extract-decisions prepare` → REASON → `apply`). `wiki-sync` does not
run it — it plans the work; the orchestrator does it.

The flag is absent when the rail is not enabled for that folder.
