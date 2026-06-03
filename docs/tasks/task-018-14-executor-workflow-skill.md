# task-018-14 — Executor workflow + SKILL + surface symlinks

**Parent:** TASK 018. **Depends on:** 018-13 (plan contract), 018-02 (`set_source_state`). **RTM:** E3.2, Q-018-5, SEC-A1/SEC-N4, AC-7. **Method:** `skill-tdd-strict` for the H-6 fence (security). **Design:** functional-architecture.md *Execution workflow* + security §7.5.

## Goal
Author the Decision-17 orchestrator recipe that executes a `scan` plan, plus the skill contract.

## Steps
1. New `workflows/wiki-sync.md` — per-entry executor (skip already-`is_unchanged`):
   - **per-vault advisory `flock`** on `<vault>/.wiki/sync.lock` (`LOCK_EX|LOCK_NB` → if held,
     emit `SYNC_IN_PROGRESS` exit 2); held for the run, fd-scoped auto-release.
   - `convert+ingest` → run the harness `docx`/`pdf`/`pptx`/`xlsx` skill → write
     `_raw/.staging/<slug(stem)>-<ext>.md` (collision-safe; refuse-overwrite-different-content;
     **empty-slug fallback** `sync-<sha8(rel-path)>-<ext>.md`, SEC-N1); converter `needs-ocr`
     → flag in report, skip rest of this file, continue.
   - `ingest` → `[.vtt/.srt]` de-timestamp via transcript-fetcher `scripts/sources/_vtt_to_text.py`
     → **H-6 fence the raw/converted body** (SEC-A1 — `summarizing-meetings` has no built-in
     banner) → `summarizing-meetings` → `wiki-enrich --source <summary>` → `wiki-extract-concepts`
     prepare/apply.
   - `upsert` → `wiki-index-upsert`.
   - on **full** per-file success → `set_source_state(vault_id,'sync',rel,'source_hash',hash)`
     (commit marker; partial failure leaves no row → resumes). Per-file isolation; final report =
     plan `summary{}` + per-entry `result`.
   - `## Fallback` section for non-Claude-Code vendors (inline the convert/summarise skills).
2. New `skills/wiki-sync/SKILL.md` — contract: triggers, the `scan` CLI surface, the plan JSON
   schema, exit codes, the executor recipe pointer, the H-6 banner. Symlink into `.claude/skills/`,
   `.agent/skills/`; the workflow into `.agent/workflows/` (via `bin/link-*.sh`).

## Verification
- `wiki-sync` appears in the skills list; `bash bin/install-project-symlinks.sh` reconnects it;
  manual dogfood (one `.vtt` + one ready `.md`) on a `samples/` copy → compounding pages + re-run
  no-op. (Full e2e asserted in 15.)
