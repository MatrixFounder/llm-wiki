# Development Plan: TASK 006 — consolidation / hardening sweep

> **Status**: DRAFT (2026-05-29) — awaiting plan-reviewer sign-off.
> **Task ID**: 006 / Slug: `consolidation-hardening`
> **Source**: [docs/TASK.md](./TASK.md) (RTM by ledger-id) + gates
> [task-006-review.md](./reviews/task-006-review.md), [architecture-006-review.md](./reviews/architecture-006-review.md) (both APPROVED).
> **Methodology**: Stub-First / green-throughout. Schema first (code + tests depend on the v4 DDL), then code, then docs/ledger.
> **Out of scope** (TASK §1, deferred with triggers): scale-perf (P-1/2/3/4/6/7/8/9/11, H-PERF-3), threat-security (D-1/D-2/H-5/H-6/Q17/TOCTOU), L-3 (Epic 6), DF-2 (by-design).

---

## 1. Task Execution Sequence

### Phase 1 — Schema v3→v4 (foundation; blocks the rest)

- [MIG, P-5, L-5, L-2-schema] **006-01** — Schema v3→v4 in `sql/wiki-index-v2.sql` + `docs/SCHEMA-v2.sql`: drop `idx_pages_vault_tags` (P-5); drop `'log'` from `pages.type` CHECK (L-5); `log_events.event_date TEXT GENERATED ALWAYS AS (substr(event_ts,1,10)) STORED` (L-2); bump `PRAGMA user_version 3→4` + `schema_meta`; ADR-002 §D8 v3→v4 amendment. Update `tests/test_schema_smoke.py` (`user_version==4`).
  - File: [docs/tasks/task-006-01-schema-v4.md](./tasks/task-006-01-schema-v4.md) · Priority: Critical · Deps: none
  - Tests: fresh apply → `user_version==4`; `idx_pages_vault_tags` absent; `type='log'` insert rejected by CHECK; `event_date` auto-equals `substr(event_ts,1,10)` on insert without supplying it.

### Phase 2 — Code (depends on v4 DDL)

- [L-2-code] **006-02** — `append_log_event` stops setting `event_date` (drop the column + value from the INSERT; it is now generated).
  - File: [docs/tasks/task-006-02-log-event-generated.md](./tasks/task-006-02-log-event-generated.md) · Priority: High · Deps: 006-01
  - Tests: `append_log_event` round-trip → row `event_date == event_ts[:10]`; `query_log_events` date-slice unchanged.

- [L-8] **006-03** — `reindex_full` entity-name fallback `title → name → slug`.
  - File: [docs/tasks/task-006-03-reindex-name-fallback.md](./tasks/task-006-03-reindex-name-fallback.md) · Priority: High · Deps: none
  - Tests: `_concepts/<slug>.md` with `name:` and no `title:` → `entities.name == name` (was slug).

- [F12c] **006-04** — extract `_recompute_mentions(conn, vault_id, slug=None)`; all 4 sites (reindex Step 3, `recompute_mentions`, `auto_promote_candidates`, `merge_entities`) call it.
  - File: [docs/tasks/task-006-04-mentions-helper.md](./tasks/task-006-04-mentions-helper.md) · Priority: Medium · Deps: none
  - Tests: existing mentions/auto-promote/merge tests stay green (behavior byte-identical).

- [P-10, F12b] **006-05** — `wiki-lint` frontmatter-alias collision scan reads `pages.frontmatter_json` (SQL `json_extract`/`json_each '$.aliases'`) instead of `frontmatter.load()` per file; surface unparseable rows rather than silently `continue`.
  - File: [docs/tasks/task-006-05-lint-scan-from-db.md](./tasks/task-006-05-lint-scan-from-db.md) · Priority: Medium · Deps: 006-01 (gate on dogfood collision fixtures for equivalence)
  - Tests: the cross_slug/cross_name/frontmatter dogfood findings are identical; no `frontmatter.load` in the scan; malformed frontmatter is reported.

### Phase 3 — Docs + ledger + gate

- [L-1, L-6, L-7, all] **006-06** — doc clarifications (L-1 file_path UNIQUE invariant comment; L-6 known_concepts cold-call note; L-7 ADR §D8 anti-pattern "verified" note) + mark P-5/L-5/L-2/L-8/F12c/P-10/F12b/L-1/L-6/L-7 `[STATUS: fixed]` in KNOWN_ISSUES + update `.AGENTS.md`/ROADMAP + full `pytest` + `mypy --strict`. Acceptance gate.
  - File: [docs/tasks/task-006-06-docs-ledger-gate.md](./tasks/task-006-06-docs-ledger-gate.md) · Priority: Critical · Deps: all prior

---

## 2. Dependency DAG

```text
006-01 schema-v4 ──┬─► 006-02 log-event-generated
                   └─► 006-05 lint-from-DB
006-03 reindex-name-fallback   (independent)
006-04 mentions-helper         (independent)
ALL ─► 006-06 docs + ledger + regression gate
```
**Critical path:** 006-01 → 006-05 → 006-06. **Parallel-safe:** {006-03, 006-04} any time.

## 3. Stub-First / green-throughout

| Bead | Code surface | RED test (first) | Then |
|---|---|---|---|
| 006-01 | DDL | fresh apply asserts user_version==4 + idx absent + log-type rejected + event_date generated | edit both DDL files + ADR + smoke test |
| 006-02 | sqlite_repository | round-trip asserts event_date generated w/o inserter | drop column+value from INSERT |
| 006-03 | reindex | RED: name-only concept → entities.name==name | title→name→slug fallback |
| 006-04 | sqlite_repository + reindex | n/a (refactor; existing tests are the guard) | extract helper, 4 call-sites |
| 006-05 | lint | RED: dogfood fixtures equal + no frontmatter.load | SQL json scan |
| 006-06 | docs/verify | n/a | doc edits + ledger + full suite |

## 4. RTM Coverage

| Ledger id | Bead | Phase |
|---|---|---|
| P-5 | 006-01 | 1 |
| L-5 | 006-01 | 1 |
| L-2 | 006-01 (schema) + 006-02 (inserter) | 1,2 |
| MIG (v3→v4) | 006-01 | 1 |
| L-8 | 006-03 | 2 |
| F12c | 006-04 | 2 |
| P-10 + F12b | 006-05 | 2 |
| L-1, L-6, L-7 | 006-06 | 3 |

## 5. Definition of Done (006-06 gate)

- [ ] 6 beads complete; `pytest tests/` all green; `mypy --strict scripts/` clean.
- [ ] `PRAGMA user_version == 4`; `idx_pages_vault_tags` absent; `type='log'` rejected; `event_date` generated (no inserter).
- [ ] Name-only concept reindexes to its display name; 4 mentions-UPDATE sites use one helper.
- [ ] Lint frontmatter scan does no `frontmatter.load`; dogfood collision findings unchanged.
- [ ] KNOWN_ISSUES: P-5/L-5/L-2/L-8/F12c/P-10/F12b/L-1/L-6/L-7 marked fixed; deferred items + triggers intact.
- [ ] ADR-002 §D8 v3→v4 amendment present.

## 6. Risk Register

| # | Risk | Mit |
|---|---|---|
| R-1 | GENERATED column breaks an insert/trigger path | Verified in arch m-1 (no trigger on log_events; only `append_log_event` writes event_date → drop it). 006-02 test guards. |
| R-2 | P-10 assumes `aliases` in `pages.frontmatter_json` | 006-05 verifies the key exists before deleting the file-scan; dogfood fixtures are the equivalence gate. Fallback: keep file-scan if absent (flag). |
| R-3 | F12c refactor changes mentions semantics | Pure extraction; existing mentions/auto-promote/merge/durability tests are the guard (must stay green). |
| R-4 | v4 migration breaks existing test fixtures on v3 | DB is rebuilt per-test (apply_schema); smoke test updated to ==4. |
