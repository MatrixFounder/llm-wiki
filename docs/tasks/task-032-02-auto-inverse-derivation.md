# 032-02 — auto-inverse derivation (global full pass + delta scoped)  ·  `tdd-strict`

**Owns:** AC-3.1/3.2/3.3/3.4. **Dep:** 032-01. **Detail:** PLAN.md §2 / ADR-004 D3/D4 / Q-032-2/3.

## Scope
Materialize inverse edges. The inverse row lives on the TARGET page → it CANNOT ride the source's per-page `replace_refs` (task-review C-1). Forward edges unchanged (M-1).

## Files
- `scripts/wiki_index/reindex.py`:
  - **`reindex_full`** — NEW global pass **between AM-3 (`:879`) and Step-3 `_recompute_mentions` (`:884`)** (arch M2): for each forward-edge row, **JOIN `entity_slug`→`pages.slug`**, **skip orphan targets** (arch M1 — enforced FK), use the **target's `page_project`**, `INSERT OR IGNORE` the inverse `(page_slug=target, …, entity_slug=source, ref_type=<inverse>)`; skip self-loops; `related` symmetric. Edge rows count toward `mentions_count` (documented).
  - **`reindex_delta`** — scoped reconciliation per changed source A: upsert A's current inverses (same skip/target-project); delete stale inverses `WHERE entity_slug=A AND ref_type ∈ inverse-set`; the delete is **load-bearing on A's orphan-delete path** (FK CASCADE drops only A's own rows). Rename residual → `--full` (A5).

## Stub-First (RED → GREEN)
AC-3.1 (one direction → both rows; ordering proven via a `mentions_count` assertion); AC-3.2 (2nd full no-op; author-both → one row each, PK dedup); **AC-3.3 orphan-target** (orphan edge → forward kept, inverse NOT derived, reindex doesn't crash); AC-3.4 delta (edit → target inverse refreshed; source-delete → back-pointers gone; rename residual documented).

## Verify
Full + delta idempotency/symmetry to the stated contract; `mypy --strict`; anchor green.
