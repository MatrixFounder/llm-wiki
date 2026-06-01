# task-016-06 — Extract `_db.py` (with the lock carve-out)

**Parent:** TASK 016. **Depends on:** 016-05. **RTM:** R-016-4c, R-016-2 (carve-out).

## Goal
Move the DB/entity/manifest leaf — the ONLY leaf that holds monkeypatched names. Two of its
residents (`load_known_entities`, `update_idempotency_state`) are in the 8-symbol lock
surface, so the facade must **re-import them and call them as facade globals** (the carve-out).
The other `_db` residents are NOT patched → plain leaf functions.

## Context
Move (verbatim) from `__init__.py`:
- **Patched (carve-out)**: `load_known_entities`, `update_idempotency_state`.
- **Not patched**: `_lookup_entity_row`, `upsert_extracted_entity`, `upsert_entity_refs`,
  `check_idempotency`, `build_manifest`.
- `_db` depends on `_validation` (`upsert_entity_refs` → `_parse_source_span`) + `_errors`.

> **CARVE-OUT (the make-or-break detail)**: the facade callers must resolve the patched
> names as `__init__` globals:
> - `load_known_entities` is called from `_load_known_and_drift`, `_apply_write`, `apply`
>   (all in `__init__`) → `__init__` does `from ._db import load_known_entities` so
>   `patch.object(wec, "load_known_entities")` / `patch("…wiki_extract_concepts.load_known_entities")`
>   rebinds the facade global the callers see.
> - `update_idempotency_state` is called ONLY from `_try_update_idempotency_state` (in
>   `__init__`) → `__init__` does `from ._db import update_idempotency_state`; the facade
>   caller references it as a bare global. Tests patch it at the facade
>   (`test_wiki_extract_concepts.py:1868`/`:2581`).
> Do NOT have the facade callers import these names locally or call `_db.load_known_entities`
> qualified — that would break the patch.

## Steps
1. Create `_db.py` with `from ._validation import _parse_source_span` + `from ._errors import …` + the moved 7 symbols (verbatim). Imports: `datetime`, `scripts.wiki_index.factory`? NO — `make_repo` stays in the facade (it is a lock symbol used by the command layer); `_db` functions take an already-open `repo` arg.
2. In `__init__.py`, delete the moved defs and add `from ._db import (load_known_entities, update_idempotency_state, _lookup_entity_row, upsert_extracted_entity, upsert_entity_refs, check_idempotency, build_manifest)`. Confirm the facade callers (`_load_known_and_drift`, `_apply_write`, `apply`, `_try_update_idempotency_state`) reference `load_known_entities` / `update_idempotency_state` as **bare facade globals**.
3. Per-bead gate, with EXPLICIT runs of:
   - `tests/test_perf_hardening.py` (patches `load_known_entities`, `_try_update_idempotency_state`, etc. — the load-once + isolation tests).
   - `tests/test_wiki_extract_concepts.py::` the two `update_idempotency_state` patch tests (C-1 partial-failure @1868, H-3 DB-lock @2581) — they MUST still intercept the call.

## Acceptance
- ✅ `_db.py` imports only `_validation`/`_errors`/stdlib (no facade import; no `make_repo`).
- ✅ `patch(wec.load_known_entities)` AND `patch(wec.update_idempotency_state)` are observed by the in-facade callers (proven by the perf + the two H-3/C-1 tests passing **unmodified**).
- ✅ Full suite green; mypy strict clean.

## Files
- `scripts/wiki_skills/wiki_extract_concepts/_db.py` (new)
- `scripts/wiki_skills/wiki_extract_concepts/__init__.py` (delete defs + carve-out import)
