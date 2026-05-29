# Architecture Review — TASK 006 (consolidation-hardening)

- **Date:** 2026-05-29
- **Reviewer:** Architecture Reviewer (self-correction loop, VDD `/vdd-start-feature`)
- **Status:** ✅ **APPROVED** (0 critical, 0 major; m-1 resolved in this pass)
- **Checklist:** `architecture-review-checklist` v1.1
- **Scope:** `docs/ARCHITECTURE.md` status + `docs/architectures/data-model.md` (§4.2 indexes, §4.4 v3→v4 migration).

## General Assessment

The only architectural surface is the **Data Model (v3→v4)** — three Class-B DDL
hygiene changes that reuse the proven v2→v3 "Class-B rebuildable, migrate via
`wiki-reindex --full`, no in-place ALTER" contract. All three are *subtractive
or guarantee-strengthening* (drop a dead index, drop a dead enum value, convert a
hand-set column to a STORED generated one) — they reduce surface and remove drift
risk rather than adding complexity. YAGNI-clean. The task-review's MAJOR-adjacent
m-1 (generated-column / FTS-trigger safety) was the only real risk and is now
verified clear.

## Comments

### 🔴 CRITICAL — None.
### 🟡 MAJOR — None.

### 🟢 m-1 (RESOLVED in this pass — generated-column safety)
Verified against the live schema + runtime: (a) SQLite runtime **3.51.0** (STORED
generated columns supported since 3.31); (b) the only `CREATE TRIGGER`s are
`pages_fts_{ai,ad,au}` on **`pages`** — none on `log_events`, so nothing treats
`event_date` as a settable column; (c) `idx_log_vault_date (vault_id, event_date)`
indexes a STORED generated column, which is valid; (d) `append_log_event` is the
sole writer of `event_date` and simply drops it from the INSERT (the `LogEvent`
dataclass never carried it). No blocker.

### 🟢 MINOR (→ Planning/Dev)
- **am-1:** P-10 (lint scan from `pages.frontmatter_json`) is a Skill/Lint-Layer
  change, not a data-model one — no schema impact; Dev must confirm `aliases`
  actually lands in `pages.frontmatter_json` for `_concepts`/`_entities` rows
  before deleting the file-scan (carried from task-review m-2; gate on the dogfood
  collision fixtures).
- **am-2:** the v3→v4 bump is the 2nd schema rev in two tasks. Still "bump
  user_version + reindex" (Q-A3 default holds; no migration framework needed yet).
  If a 3rd lands soon, reconsider a `scripts/migrations/` runner — note only.

## Checklist Result

| Group | Item | Verdict |
|---|---|---|
| 1 TASK Compliance | RTM (P-5/L-5/L-2/L-8/F12c/P-10/MIG/docs) mapped; NFR addressed | ✅ |
| 2 Data Model (CRITICAL) | v3→v4 types/migration; GENERATED column safe (m-1); index drop | ✅ |
| 3 System Design | subtractive hygiene, no new components; index 193-ish lines; no drift | ✅ |
| 4 Security | none introduced (subtractive); threat-gated items stay deferred | ✅ |
| 5 Scalability | P-10 removes an O(pages) sweep; rest scale-neutral | ✅ |

## Final Recommendation

**PROCEED to Planning (`/vdd-plan`).** Suggested bead order (schema first, since
code + tests depend on the v4 DDL): (1) MIG+P-5+L-5+L-2 schema v3→v4 + smoke-test
update, (2) L-2 `append_log_event` inserter change, (3) L-8 reindex name fallback,
(4) F12c `_recompute_mentions` helper, (5) P-10 lint-from-DB rewrite, (6) L-1/6/7
docs + ledger close + regression gate.

```json
{ "review_file": "docs/reviews/architecture-006-review.md", "has_critical_issues": false }
```
