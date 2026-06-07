# Task 019.01: [STUB] `$def Resummarize` schema + dataclass + loader stub

## Use Case Connection
- E3.1 · AC-9, AC-11

## Task Goal
Author the strict `$def Resummarize` config surface + a frozen `ResummarizeConfig`
dataclass + the loader-parse stub (absent → `None`). No detector logic yet.

## Changes Description
### Changes in Existing Files
#### File: `config/sync-config.schema.yaml`
- Add `$def Resummarize` (STRICT, `additionalProperties:false`):
  - `mode`: enum `[if-missing, always, never]` (default `if-missing`)
  - `detect`: object `{source_state: bool, provenance_ref: {enabled: bool, fields: [string], match: enum[vault-rel-path,basename]}, mirror: {enabled: bool, raw_dirs:[string], summary_dir: string, summary_ext: string, match: enum[stem-relpath,group-key], group_key: string, key: {raw_regex,summary_regex,template,flags:[string]}}}`
- Add `SyncConfig.properties.resummarize: {$ref: '#/$defs/Resummarize'}`.

#### File: `scripts/wiki_index/sync_config.py`
- Add frozen dataclasses `ResummarizeConfig`, `DetectConfig`, `ProvenanceConfig`,
  `MirrorConfig`, `MirrorKey` (typed; tuples for lists).
- `SyncConfig`: add field `resummarize: ResummarizeConfig | None = None`.
- `load_sync_config`: **stub** — leave `resummarize=None` for now (parse added in 02).

## Test Cases
### Unit (RED — partially green at stub)
1. **TC-01-1:** a valid `resummarize:` block passes `_validate` (schema accepts).
2. **TC-01-2 (RED):** an unknown key (`resummarize: {modee: always}`) → `SyncConfigError`
   `INVALID_SYNC_CONFIG` (value not echoed).
3. **TC-01-3:** `SyncConfig.resummarize` defaults to `None` when absent.

## Acceptance Criteria
- [ ] Schema strict; meta-validates; dataclasses typed + frozen.
- [ ] `mypy --strict` clean; bead-00 golden still green.

## Notes
Keep `MirrorKey.flags` a tuple of `{ignorecase, unicode}`-validated strings.
