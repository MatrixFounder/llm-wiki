# Task 012-03: PW-C/E — config-driven type inference + type_mapping

## Use Case Connection
- UC-29: byte-identical Karpathy (the 15-entry TYPE_MAPPING stays bit-identical).
- UC-31: dev-project `task`→`brief`+tag `task`, `adr`→`research`+tag `adr` (tag-route, zero DDL).

## Task Goal
Externalise the hardcoded `TYPE_MAPPING` + `_PATH_TYPE_FALLBACK` so type inference is
config-driven (PW-C/E), while keeping the module-level constants in `normalization.py`
as the **karpathy default** (so 012-01's invariant test + back-compat callers hold).

## Changes Description

### Changes in Existing Files

#### File: `scripts/wiki_index/normalization.py`
- `normalize_frontmatter(fm, *, source_path=None, type_mapping=None, path_type_fallback=None)`:
  new optional params; when `None`, fall back to the module-level `TYPE_MAPPING` /
  `_PATH_TYPE_FALLBACK` (today's behaviour — back-compat for any caller that doesn't pass a
  config). When a `LayoutConfig` is in play, the reindex layer passes
  `config.type_mapping` + `config.path_type_fallback`.
- `_infer_type_from_path(source_path, path_type_fallback=None)`: consume the passed map
  (default = module constant). Keep the `for part in source_path.parts` scan semantics
  (byte-identical inference order).
- **Do NOT delete** the module-level `TYPE_MAPPING` / `_PATH_TYPE_FALLBACK` — they are the
  karpathy default + the projection target the 012-01 invariant pins.

#### File: `scripts/wiki_index/reindex.py`
- In `reindex_full` / `reindex_delta`, load the vault's `LayoutConfig` (already available
  via the 012-02 `discover_pages` config-load; thread it through or re-resolve cached) and
  pass `config.type_mapping` + `config.path_type_fallback` to `normalize_frontmatter`.

### Changes in Test Files

#### File: `tests/test_normalization.py` (extend) + `tests/test_config_type_mapping.py` (NEW)
- All existing normalization tests pass unchanged (the `None`-default path == today).
- `normalize_frontmatter` with a dev-project `type_mapping`: `type: task` → `db_type=brief`,
  tag `task`; `type: adr` → `db_type=research`, tag `adr`.
- `UnmappedTypeError` still raised when `raw_type` ∉ the supplied map.
- Path fallback honours a config-supplied `path_type_fallback` (e.g. `docs/issues`→`known-issue`).

## Acceptance Criteria
- ✅ 012-00 golden snapshot green (karpathy 15-entry mapping + tag-injection byte-identical).
- ✅ dev `task`/`adr` map through the tag-route; `UnmappedTypeError` preserved.
- ✅ `mypy --strict` clean; full suite green.

## Stub-First
Phase 1: add the optional params defaulting to the module constants (behaviour unchanged) →
existing tests green. Phase 2: wire reindex to pass config maps + add the dev-mapping tests
(RED against the karpathy-only stub).
