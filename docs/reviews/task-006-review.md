# Task Review — TASK 006 (consolidation-hardening)

- **Date:** 2026-05-29
- **Reviewer:** Task Reviewer (self-correction loop, VDD `/vdd-start-feature`)
- **Status:** ✅ **APPROVED WITH COMMENTS** (0 critical; 3 minor → Architecture/Dev)
- **Checklist:** `task-review-checklist` v1.0

## General Assessment

A well-fenced cleanup TASK. The standout discipline is the **explicit
NOT-in-scope fence** (§1): scale-gated perf and threat-gated security stay
deferred *with their ledger triggers intact*, and the spec cites
`developer-guidelines` §1.6 (no speculative work) as the rationale — exactly
right for a hardening sweep that could otherwise balloon. RTM is keyed by
**ledger id** (P-5/L-5/L-2/L-8/F12c/P-10/MIG/docs), avoiding a confusing clash
with ROADMAP R-numbers (D-006-3) — good call. Every requirement is grounded in a
verified repo fact (§1.1: dead index unreferenced, no `type='log'` emitter,
`event_date` inserter located, 4 mentions-UPDATE sites, concept frontmatter in
`pages.frontmatter_json`). The v3→v4 migration reuses the proven v2→v3
Class-B-rebuild contract. No invention.

## Comments

### 🔴 CRITICAL — None.
### 🟡 MAJOR — None.

### 🟢 MINOR (→ Architecture / Dev)
- **m-1 (L-2 / C-4, verify in Arch):** STORED generated columns can't be added by
  `ALTER` to a populated table — fine via the rebuild path, but Architecture must
  confirm (a) the FTS5 triggers + any `log_events` insert/select don't treat
  `event_date` as a settable column, and (b) the bundled SQLite (Python 3.14.4)
  supports `GENERATED ALWAYS … STORED` (it does, ≥3.31). Pin in the data-model chunk.
- **m-2 (P-10, verify in Dev):** the rewrite assumes `aliases` is present in
  `pages.frontmatter_json` for `_concepts`/`_entities` pages. §1.1 establishes
  `upsert_page` stores `frontmatter_json`; Dev must assert the `aliases` key
  actually survives (reindex passes `updated_fm`) before deleting the file-scan —
  keep the dogfood collision fixtures as the equivalence gate (UC-17 AC).
- **m-3 (UC thinness):** UC-16..19 are terser than a feature task's (System-only
  invariants, no rich actor flows). Acceptable — this is internal hardening; the
  binding part is the per-UC Acceptance Criteria, which are concrete + verifiable.

## Checklist Result

| Group | Item | Verdict |
|---|---|---|
| 1 Compliance | Requirements / Scope / Goal | ✅ (operator-selected subset; fence explicit) |
| 2 Use Cases | Structure / AC | ✅ (m-3 minor) |
| 3 Compatibility | Terminology / Architecture / Migration | ✅ (v2→v3 precedent; m-1 to verify) |
| 4 Consistency | Internal / Naming | ✅ (ledger-id RTM, D-006-3) |
| 5 Non-Functional | Perf / Regression / No-speculative | ✅ (NFR-1..5) |

## Final Recommendation

**PROCEED to Architecture.** Update `docs/architectures/data-model.md` for the
v3→v4 changes (drop `idx_pages_vault_tags`, drop `'log'` enum, `event_date`
GENERATED) + the lint-scan source change, and resolve m-1 (FTS-trigger /
generated-column verification). No blocking issues.

```json
{ "review_file": "docs/reviews/task-006-review.md", "has_critical_issues": false }
```
