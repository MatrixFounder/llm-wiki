---
name: wiki-append-log
description: >-
  Append a structured event to the vault's monthly log.md AND mirror it to
  the log_events table (bi-directional sync, M-2 contract). Atomic via
  flock + fsync. Triggers: "log event", "append to wiki log".
tier: 2
version: 1.0
---

# wiki-append-log

Bi-directional sync between human-readable `log.md` (one per month, under
`<vault>/00-Vault-Index/log/YYYY-MM.md`) and the `log_events` table.

## When to use

- After a manual ingest / cleanup / promotion action that's not already
  logged by another wiki-* CLI.
- Audit trail entries.
- Sub-step inside `wiki-import` (the `log_event` block from the
  concept manifest is mirrored via this path).

## Invocation

```bash
wiki-append-log \
    --vault <vault_id> \
    --event-type <type> \
    [--subject "<one-line>"] \
    [--details-json '{"k":"v"}' | --details-json <path-to-json-file>] \
    [--db-path <override>]
```

Or `/wiki-append-log [...]`.

## Contract

- `event_type` must match the CHECK enum in `log_events`
  (`ingest`/`lint`/`reindex`/`reclassify`/`promote`/`demote`/`render`).
- Monthly rotation: file path resolved via `rotate_log_path(vault_root,
  datetime.now())` → `<vault>/00-Vault-Index/log/<YYYY-MM>.md`.
- Atomic: `fcntl.flock(LOCK_EX)` held for the whole write; partial-write
  loop on `os.write`; `os.fsync` before lock release.
- DB-first → log.md second → backfill `log_md_byte_offset`. On write
  failure, log_events row is rolled back and `LOG_APPEND_FAILED` envelope
  emitted (exit 6).

## Exit codes

| Code | Envelope |
|---|---|
| 0 | `{"action": "logged", "event_id": N, "log_md_path": ..., "byte_offset": N}` |
| 6 | `{"error": "VAULT_NOT_REGISTERED" / "LOG_APPEND_FAILED", ...}` |

## Related

- `scripts/wiki_index/logfile.py` — `rotate_log_path`, `append_atomic`,
  `parse_log_md`
- M-2 contract: `log_md_byte_offset` enables reverse-parse for
  `wiki-reindex --full`
