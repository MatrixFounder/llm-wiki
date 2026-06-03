# task-018-04 — [LOGIC] sync-config loader (size-cap + anchor-ban + strict schema)

**Parent:** TASK 018. **Depends on:** 018-03. **RTM:** E4.1, SEC-A5/SEC-N3, META-4. **Method:** `skill-tdd-strict` (security — the anchor-bomb test must show refusal; RED proves expansion without the guard).

## Goal
Implement a safe, strict `.wiki/sync.yaml` loader. Closes the SEC-N3 false-`safe_load` claim.

## Design (locked — SEC-N3)
`yaml.safe_load` does **NOT** stop an anchor-bomb (it expands aliases). Defense = (1) 256 KiB
`stat().st_size` cap before read; (2) a `SafeLoader` subclass that **raises on any anchor/alias
node** (the config is a flat glob-string dict — anchors have no legitimate use).

## Steps
1. `load_sync_config`: if no `.wiki/sync.yaml` → return defaults; else `stat().st_size` >
   `WIKI_SYNC_CONFIG_MAX_BYTES` → raise `SyncConfigError("INVALID_SYNC_CONFIG", "oversize")`.
2. Parse with `_NoAliasSafeLoader` (override `compose_node`/anchor handling to raise on
   anchor/alias). jsonschema-validate against `config/sync-config.schema.yaml` (strict).
3. Build `SyncConfig`; pin `exclude` × `#wiki/keep` precedence at the loader boundary (document).
4. GREEN: valid config parses; misspelled key → `INVALID_SYNC_CONFIG` (exit 6, value not echoed —
   CWE-209); a 232-byte anchor-bomb → refused; >256 KiB → refused.

## Verification
- `pytest -q -k sync_config` GREEN; `mypy --strict` clean.
