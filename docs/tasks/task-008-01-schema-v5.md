# Task 008-01: schema v4→v5 — admit `verification` type, `verifies` ref, `verify` event

## Use Case Connection
- UC-26: Durability round-trip (the §D8 gate depends on a `type=verification` page being insertable + rediscoverable).

## Task Goal
Bump the schema from v4 to **v5** so the verdict page and its graph edges are storable. This is **R-8.9** and the single biggest structural cost of TASK 008 — unlike R-6 (`wiki-query`), the verdict-page type / verify relationship / verify event are **not** pre-provisioned. The DB is a Class B rebuildable cache.

> **Migration (corrected per adversarial-plan finding DUR-2/DEC-4 — the prior "just `wiki-reindex --full`" wording was wrong for a POPULATED v4 DB):** SQLite cannot ALTER-relax a CHECK constraint, and the DDL uses `CREATE TABLE IF NOT EXISTS` — so on an **existing** v4 DB, `apply_schema_if_missing` no-ops (the file exists) and `reindex_full` only DELETEs+re-INSERTs rows; **neither recreates the table, so the old v4 CHECK persists and a `type='verification'` INSERT raises `IntegrityError`.** The actual v4→v5 migration is: **delete the `.db`/`-wal`/`-shm` files, then `wiki-init --register-existing <vault>` + `wiki-reindex --full`** — the deletion makes the next `make_repo` apply the fresh v5 schema, the re-register restores the `vaults` row (wiped with the DB), and the reindex repopulates from Class A markdown. There is **no** `user_version`-gated in-place reseed in the codebase (do NOT claim one).

## Changes Description

### Changes in Existing Files

#### File: `sql/wiki-index-v2.sql` (the live runtime DDL)
- `pages.type` CHECK (line ~162-164): add `'verification'` → `('summary','concept','query','brief','research','index','verification')`.
- `page_entity_refs.ref_type` CHECK (line ~194-196): add `'verifies'` → `('mentioned','defined-here','related','cited','verifies')`.
- `log_events.event_type` CHECK (line ~225-230): add `'verify'`.
- `index_meta` view (line ~393-402): `WHERE type IN ('summary','concept','query','verification')` (catalog/render parity with `query`).
- `PRAGMA user_version = 5;` (line ~452).
- **No `pages_fts_*` trigger change** — they index every row regardless of `type`, so a `verification` page is FTS-searchable the moment the CHECK admits it (verified §1.1).
- Add the `schema_meta`/`user_version` v4→v5 comment block mirroring the v3→v4 note.

#### File: `docs/SCHEMA-v2.sql` (the documentation mirror)
- Apply the identical four edits + `user_version = 5` + a header comment for v5.

#### File: `scripts/wiki_index/models.py` (added during the 008-01 Roast — schema↔model sync)
- `PageType = Literal[...]` mirrors the `pages.type` CHECK; add `"verification"` so a `Page(type="verification")` (built by 008-07) type-checks under `mypy --strict`. Update the `PageRef.ref_type` (`+ 'verifies'`) and `LogEvent.event_type` (`+ 'verify'`) prose docstrings for accuracy (both are `str`-typed, not Literals — no type-break, but stale enumerations are slop). **Why here:** the schema-v5 bead defines "verification is a valid page type"; leaving the Python `PageType` Literal stale is the exact "schema admits it but the model doesn't" divergence the adversarial reviews flag.

### Changes in Test Files

#### File: `tests/test_schema_v5.py` (NEW)
- Assert a fresh DB (apply the schema) has `PRAGMA user_version == 5`.
- Assert each new enum value is accepted: `INSERT` a `pages` row `type='verification'`, a `page_entity_refs` row `ref_type='verifies'`, a `log_events` row `event_type='verify'` — all succeed; a bogus value still raises `IntegrityError`.
- Assert the `index_meta` view returns a `type='verification'` page (catalog parity).

#### Existing schema-version pin tests — **ALL THREE** (adversarial-plan finding DEC-3/DUR-3)
A grep for `PRAGMA user_version` shows **three** test files hard-assert `== 4`, all reading the live DDL via `executescript` — all must move to `== 5` (or be superseded) **in this bead** so the suite stays green-throughout (the version bump + every assertion change are one atomic unit):
- `tests/test_schema_v4.py:27` (`test_user_version_is_4`) → `== 5`.
- `tests/test_schema_smoke.py:67` (the e2e pragma assertion) **and the `:51` docstring** (`user_version=4`) → `5`.
- `tests/test_schema_v3.py:31` (`test_user_version_is_current`, asserts `== 4` despite the filename) → `== 5`.
- (Precedent: the TASK 006 v3→v4 bump touched these same three locations.)

### Component Integration
The CHECK relaxations make the verdict page (008-07 `upsert_page`), the `verifies` ref (008-03/007), and the `verify` log event (008-07) all writable. No other table changes. A **fresh** vault (`wiki-init --scaffold-new`) gets v5 directly. An **existing populated v4 DB** migrates via the delete-then-reregister-then-reindex sequence in the §Task-Goal migration note above (NOT an in-place reseed — there is no such code).

## Test Cases

### Unit / schema Tests
1. **TC-SCHEMA-01:** fresh DB → `user_version == 5`.
2. **TC-SCHEMA-02:** `INSERT pages(type='verification')` succeeds; `type='bogus'` raises.
3. **TC-SCHEMA-03:** `INSERT page_entity_refs(ref_type='verifies')` succeeds; bogus raises.
4. **TC-SCHEMA-04:** `INSERT log_events(event_type='verify')` succeeds; bogus raises.
5. **TC-SCHEMA-05:** `index_meta` includes a `type='verification'` row.

### Regression Tests
- All existing schema tests pass with the new enums (additive — no existing value removed); `pages_fts` search over a verification page returns it (triggers unchanged).
- `tests/test_schema_v4.py` version assertion updated to 5 (or superseded) — suite green.

## Acceptance Criteria
- [ ] `pages.type`, `page_entity_refs.ref_type`, `log_events.event_type` admit the three new values; `index_meta` view includes `verification`.
- [ ] `PRAGMA user_version == 5` in both `sql/wiki-index-v2.sql` and `docs/SCHEMA-v2.sql`.
- [ ] `test_schema_v5.py` green; **all three** prior `== 4` version-pins updated (`test_schema_v4.py:27`, `test_schema_smoke.py:67`+`:51` docstring, `test_schema_v3.py:31`) — `grep -rn "user_version" tests/` shows **no remaining `== 4` assertion** (suite green-throughout).
- [ ] No `pages_fts_*` trigger change; no in-place ALTER. Migration runbook = **delete `.db`/`-wal`/`-shm` → `wiki-init --register-existing` → `wiki-reindex --full`** (NOT bare `wiki-reindex --full`, which can't relax a CHECK on a populated DB).
- [ ] `mypy --strict scripts/` clean (no code change, but run the gate).

## Notes
This is the prerequisite for every other bead that writes a verification row. Additive enum relaxation only — no removal — so existing data/tests are unaffected besides the version pin. ADR-002 §D8 already carries the v4→v5 amendment (added in the Architecture phase).
