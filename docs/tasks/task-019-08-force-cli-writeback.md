# Task 019.08: [LOGIC] `--force` CLI + dry-run report + workflow `sources:` writeback

## Use Case Connection
- UC-3 · E1.1, E4.1 · AC-4, AC-13

## Task Goal
Expose `--force` on `wiki-sync scan`, thread it into the gate, surface the new skip reasons
in the dry-run report, and specify the executor's `sources:` writeback (D2a self-priming).

## Changes Description
#### File: `scripts/wiki_skills/wiki_sync.py`
- argparse `scan`: add `sp.add_argument("--force", action="store_true", help="re-summarize raw sources even if a summary exists")`.
- scan handler: pass `force=args.force` into `_build_entries(...)`.
- `_build_entries`: thread `force` into `apply_policy`; when `force` flips a would-be
  skip-by-policy, the entry keeps its actionable `action` with `reason="forced"`.
- `_emit_dry_run` / `_summarize`: count the new skip reasons
  (`summary-exists:*`, `resummarize-never`, `forced`) — no silent truncation (AC-13 report).

#### File: `workflows/wiki-sync.md`
- Thread `--force` through the orchestrator invocation.
- **`sources:` writeback (AC-13):** after generating a summary from N raw sources, the
  executor writes `sources: [<raw vault-rel paths>]` into the summary's frontmatter (so the
  next scan detects via the exact D2a signal). Document the contract + idempotency.

#### Files: `skills/wiki-sync/SKILL.md`, `config/sync-config.schema.yaml` (header doc)
- Document `--force`, the `resummarize:` block, and the new skip reasons.

## Test Cases
### Unit / E2E
1. **TC-08-1 (AC-4):** `--force` → a raw that D1/D2a/D2b would skip is planned actionable, `reason="forced"`.
2. **TC-08-2:** dry-run report lists every gated file + reason + counts; `--force` flips counts.
3. **TC-08-3 (AC-13 contract):** a fixture summary written with `sources:[raw]` → next scan skips that raw `summary-exists:provenance`.

## Acceptance Criteria
- [ ] `--force` zone-scoped; report complete; writeback contract documented + tested.
- [ ] `mypy --strict` clean; regression green.

## Notes
`--force` bypasses detectors + `mode`; persistent per-folder force = `mode: always` (bead 04).
