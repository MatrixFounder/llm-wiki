# 032-00 — schema v5→v6 (inverse-closed ref_type)  ·  `tdd-strict`

**Owns:** AC-1.1/1.2/1.3. **Dep:** none (foundation, FIRST). **Detail:** PLAN.md §2.

## Scope
Additive `ref_type` CHECK migration + `user_version` 5→6. Class-B rebuild (TASK 008 shape).

## Files
- `sql/wiki-index-v2.sql` — `page_entity_refs.ref_type` CHECK (`:195-198`) += `implements`,`implemented-by`,`supersedes`,`superseded-by`,`causes`,`caused-by` (comment `TASK 032 / R-032-1 (schema v6)`); **reuse `related`** for relates_to (NO `relates-to`). `PRAGMA user_version = 6` (`:461`).
- `scripts/wiki_index/models.py` — `PageRef.ref_type` docstring → v6 set.
- version-pin bumps in `tests/test_schema_v3.py`/`v4`/`v5`/`test_schema_smoke.py` (→ 6).

## Stub-First (RED → GREEN)
NEW `tests/test_schema_v6.py` (mirror `test_schema_v5.py`): `user_version==6`; each of the 6 new ref_types INSERTs (`PRAGMA foreign_keys=OFF`); bogus → `IntegrityError`. **AC-1.3:** an INLINE table with the OLD 5-value CHECK, populated, rejects `INSERT … 'implements'` (`IntegrityError`) — proves the Class-B rebuild is mandatory.

## Verify
Full suite green (pins updated); `mypy --strict`; Karpathy anchor green; no table/PK change.
