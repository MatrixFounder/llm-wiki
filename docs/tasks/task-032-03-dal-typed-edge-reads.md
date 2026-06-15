# 032-03 — DAL typed-edge reads

**Owns:** AC-4.1. **Dep:** 032-00. **Detail:** PLAN.md §2 / ADR-004 D-DAL / Q-032-6.

## Scope
Read primitives for the graph (inbound/outbound by kind + bounded traversal).

## Files
- `scripts/wiki_index/repository.py` (ABC) **+** `scripts/wiki_index/sqlite_repository.py` (impl), in **lockstep** (mypy strict):
  - `get_backlinks(vault_id, entity_slug, ref_type=None)` — additive kw, default = today's all-kinds (existing callers unaffected).
  - NEW `refs_from(vault_id, page_slug, project, ref_type=None)` — outbound.
  - NEW `neighbors(...)` / `chain(...)` — depth-capped, visited-set cycle-safe; reuse `idx_refs_type/entity/page`; bound params, no per-node round-trip blowup (batch per depth level).

## Stub-First (RED → GREEN)
**DECISION (plan-review 🟡-2): ONE shared fixture-graph builder** — create a reusable `(decision→task→incident [+ a cycle, + an orphan-target])` graph builder here (e.g. `tests/_graph_fixtures.py` or a `conftest.py` fixture) and **reuse it across 032-02/03/04/05** so the inverse-derivation, DAL, CLI, and RAG tests assert against ONE consistent topology. Then: inbound/outbound filtered by kind; `chain` resolves the 3-hop path; a cycle terminates at the depth cap; ABC + impl signatures agree.

## Verify
`mypy --strict`; existing `get_backlinks` callers (wiki-merge/lint) still pass (default all-kinds).
