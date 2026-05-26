# TASK Review — Iteration 2

**Reviewed file:** `docs/TASK.md`
**Date:** 2026-04-28
**Reviewer:** Task Reviewer Agent
**Iteration:** 2 (post-fixes)
**Reference:** Iteration 1 found 5 CRITICAL + 10 MAJOR (see [task-001-review.md](./task-001-review.md) — pending iteration 1 archive).

---

## Status: APPROVED WITH MINOR COMMENTS

One MAJOR-class regression found (UC-06 type field contradicts SCHEMA CHECK constraint), but it is narrowly scoped, fix is mechanical, and does not block downstream Architecture phase. Recommended fix before Planning.

---

## Verification of Iteration 1 findings

### CRITICAL (5/5 CLOSED)

| ID | Subject | Status |
|---|---|---|
| C-1 | transcript MVP scope | CLOSED |
| C-2 | SQLite NULL-PK | CLOSED |
| C-3 | target directory | CLOSED |
| C-4 | NFR vs UC AC drift | CLOSED |
| C-5 | LLM budget claim | CLOSED |

### MAJOR (10/10 CLOSED)

All M-1 through M-10 closed. Specifics validated against current TASK.md content.

---

## NEW Comments (Iteration 2)

### 🟡 MAJOR — 1 finding

**N-MAJOR-1**: UC-06 `type: summary-light` contradicts `pages.type` CHECK constraint.

UC-06 §4.6 step 6 prescribes frontmatter `type: summary-light`. SCHEMA-DRAFT.sql defines `pages.type CHECK (type IN ('summary', 'concept', 'query', 'brief', 'research', 'index', 'log'))`. `summary-light` is NOT in the allowed set → `wiki-index-upsert` will fail with CHECK constraint violation.

UC-06 Postconditions imply remap (`type='summary'` + tag `summary-light`), but this is not explicit in steps or AC.

**Fix**: Document remap in UC-06 step 6 and add binary AC: `SELECT type FROM pages WHERE slug = '<date>-<slug>'` returns `'summary'` AND `tags` JSON contains `'summary-light'`.

### 🟢 MINOR — 9 findings

- **N-MINOR-1**: Schema views still contain dead `IS NULL` branches (cosmetic — both columns are NOT NULL now).
- **N-MINOR-2**: §5.1 numbers still duplicated in UC-03/UC-04 AC text (drift risk).
- **N-MINOR-3**: UC-06 slug ambiguity — bare vs date-prefixed.
- **N-MINOR-4**: R-25 has no UC AC verifying `vault_metadata` is seeded.
- **N-MINOR-5**: R-13.1 RTM sub-feature does not mirror `--dry-run`.
- **N-MINOR-6**: UC-01 step 9 / SCHEMA seed redundancy.
- **N-MINOR-7**: §6.2 transcript description understates pyramid stages.
- **N-MINOR-8**: §1.3 step 4 phrasing «(новый workflow)».
- **N-MINOR-9**: Typo «iCloud-coruption».

---

## Coverage Matrix Verification

All MVP R-XX have RTM + Issue + at least one UC AC, except **R-25** missing direct AC verification (N-MINOR-4).

---

## Final Recommendation

**APPROVED WITH MINOR COMMENTS.**

Recommended path:
1. Apply **N-MAJOR-1** fix (UC-06 type-field remap clarification + AC) before Planning phase.
2. Apply **N-MINOR-4** (R-25 AC), **N-MINOR-5** (RTM mirror), **N-MINOR-1** (dead view branches) opportunistically with N-MAJOR-1.
3. Other MINORs deferred to final polish pass.

No critical issues remain. **Architecture phase may proceed.** Planning phase должен дождаться N-MAJOR-1 fix (или explicit risk-acceptance).

---

```json
{"review_file": "docs/reviews/task-001-review-iter2.md", "has_critical_issues": false, "iteration": 2}
```
