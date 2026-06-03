# task-018-03 — [STUB] sync-config schema + loader surface

**Parent:** TASK 018. **Depends on:** 018-00. **RTM:** E4.1, Q-018-4, META-4. **Design:** ARCHITECTURE.md Q-018-4 + interfaces §5.4 + security §7.5.

## Goal
Author the strict `.wiki/sync.yaml` schema and the loader's Stub-First surface.

## Steps
1. New `config/sync-config.schema.yaml` (JSON-Schema 2020-12, `additionalProperties:false`):
   `zones: [glob]`, `exclude: [glob]`, `tag_namespace: str (default "wiki")`,
   `extensions: {convert,text,skip:[...]}` (optional overrides). Mirror `layout-config.schema.yaml`
   style (strict, library-of-`$defs`).
2. New `scripts/wiki_index/sync_config.py`: a frozen `SyncConfig` dataclass + `load_sync_config(
   vault_root: Path) -> SyncConfig` **stub** returning defaults; a `_NoAliasSafeLoader(SafeLoader)`
   **stub** (class only) + module constant `WIKI_SYNC_CONFIG_MAX_BYTES = 256 * 1024`.
3. RED tests in `tests/test_wiki_sync.py`: `test_sync_config_rejects_misspelled_key`,
   `test_sync_config_rejects_yaml_anchor`, `test_sync_config_size_cap` (all fail on the stub).

## Verification
- `pytest -q -k sync_config` → the 3 new RED; all else GREEN; `mypy --strict` clean.
