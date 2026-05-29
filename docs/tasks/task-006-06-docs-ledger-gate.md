# Task 006-06: docs (L-1/6/7) + ledger close + regression gate

## Ledger ids: L-1, L-6, L-7 + acceptance gate for all of TASK 006

## Goal
Land the doc-only clarifications, mark the closed ledger items fixed, and run the
final regression gate.

## Changes
### Docs (L-1/L-6/L-7)
- **L-1**: inline comment in `sql/wiki-index-v2.sql` + `docs/SCHEMA-v2.sql` on the
  `entities.file_path` UNIQUE-per-(vault_id) invariant (alias-target collision note).
- **L-6**: header comment on the `known_concepts` view documenting the
  `json_group_array` correlated-subquery cold-call cost.
- **L-7**: add the "Verified consistent with `page_entity_refs` design, 2026-05-29"
  note to the ADR-002 §D8 anti-pattern row.
### Ledger
- `docs/KNOWN_ISSUES.md`: mark **P-5, L-5, L-2, L-8, F12c, P-10, F12b, L-1, L-6, L-7**
  `[STATUS: fixed 2026-05-29]` with one-line resolutions. Leave all deferred items
  (scale-perf, threat-security, L-3, DF-2) + their triggers intact.
### Other docs
- `docs/ROADMAP.md`: note TASK 006 hygiene sweep done.
- `.AGENTS.md` (scripts/wiki_index, scripts/wiki_skills, tests): note v4 + helper + lint-from-DB.

## Test cases (acceptance gate)
1. `pytest tests/ -q` → all green (baseline 539 + new 006 tests), 0 failed.
2. `mypy --strict scripts/` → clean.
3. `PRAGMA user_version == 4`; `idx_pages_vault_tags` absent; `type='log'` rejected; `event_date` generated.
4. Lint frontmatter scan: no `frontmatter.load` in the path; dogfood findings unchanged.

## Acceptance
- [ ] L-1/L-6/L-7 doc notes present.
- [ ] All 10 closed ledger items marked fixed; deferred items + triggers intact.
- [ ] Full `pytest` green; `mypy --strict` clean; DoD (PLAN §5) checked.

## Notes
Verify/docs bead — no stub phase. Depends on all prior beads. A post-ship `/vdd-multi` adversarial sweep + dogfood of the v4 migration follow this gate.
