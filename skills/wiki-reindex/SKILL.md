---
name: wiki-reindex
description: >-
  Rebuild the SQLite index from canonical markdown files. Modes: --full
  (wipe + rebuild, ADR-002 §D8 Class A→B gate), --delta (mtime-based
  incremental). Triggers: "reindex vault", "rebuild wiki db".
tier: 2
version: 1.0
---

# wiki-reindex

Reconstruct the index layer from the file layer. Critical for ADR-002 §D8
rebuildability invariant.

## When to use

- After bulk-editing markdown outside the wiki-* CLIs (manual edits, git
  pull, restore from backup).
- After deleting / corrupting the SQLite DB → `--full` rebuilds from scratch.
- Daily / hourly maintenance → `--delta` picks up changed files since the
  last log event.
- All registered vaults at once → `--all-vaults` (full mode only).

## Modes

- **`--full`** — wipes all rows for this vault, walks filesystem (root tier
  + `Lessons/*/` course tier), upserts every page, mirrors `log.md` →
  `log_events`, recomputes `entities.mentions_count`. Authoritative
  rebuild. Takes seconds for ~1k pages, minutes for ~10k.
- **`--delta`** — mtime cutoff = `MAX(log_events.event_ts)` or
  `vaults.registered_at`. Re-ingests files modified after cutoff; deletes
  DB rows for files removed from disk. Wrapped in BEGIN/COMMIT for the
  delete sweep.

## Invocation

```bash
python -m scripts.wiki_skills.wiki_reindex \
    (--full | --delta) \
    (--vault <vault_id> | --all-vaults) \
    [--db-path <override>]
```

Or `/wiki-reindex --full --vault <vid>`.

## Contract

- `--full` and `--delta` mutually exclusive. `--vault` and `--all-vaults`
  mutually exclusive. One of each required.
- `--all-vaults` is only supported with `--full`.
- Per-file errors are collected into `skipped[]` (never silently dropped
  per critic-logic fix).

## Output

| Mode | JSON envelope |
|---|---|
| `--full` | `{"action": "reindexed", "vault_id": ..., "pages": N, "entities": N, "log_events": N, "skipped": [...], "duration_seconds": ...}` |
| `--delta` | `{"action": "reindexed", "mode": "delta", "vault_id": ..., "touched": N, "deleted": N, "skipped": [...], "duration_seconds": ...}` |
| `--all-vaults --full` | `{"action": "reindexed", "scope": "all-vaults", "vaults_processed": N, "pages_indexed": N, "results": [...]}` |

## Related

- ADR-002 §D8 (Class A → Class B reconstruction invariant)
- KNOWN_ISSUES P-1 (per-page transactions — scaling concern)
- KNOWN_ISSUES P-2 (delta walk cost — scaling concern)
