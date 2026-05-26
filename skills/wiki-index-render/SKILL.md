---
name: wiki-index-render
description: >-
  Render index.md (read-only projection of the SQLite index) for a vault.
  Preserves operator-authored custom sections marked with
  <!-- BEGIN-CUSTOM:name --> / <!-- END-CUSTOM:name -->.
  Triggers: "render index", "rebuild index.md".
tier: 2
version: 1.0
---

# wiki-index-render

Generate `index.md` for a vault from the `index_meta` SQL view.

## When to use

- After significant ingest activity to refresh the human-readable index.
- After `wiki-reindex --full` to materialize the projection.
- Periodic maintenance (cron).

## Custom sections

Operator-authored blocks like:

```markdown
<!-- BEGIN-CUSTOM:notes -->
Hand-written commentary the generator must preserve.
<!-- END-CUSTOM:notes -->
```

…are extracted from the existing `index.md` (if any) and re-injected
verbatim after the auto-generated sections. The `name` field
(`[a-z0-9-]+`) must be unique within the file.

## Invocation

```bash
python -m scripts.wiki_skills.wiki_index_render \
    --vault <vault_id> \
    [--output <abs-path.md> | default: <vault_root>/index.md] \
    [--db-path <override>]
```

Or `/wiki-index-render --vault <vid>`.

## Contract

- `--output` defaults to `<vault_root>/index.md`; absolute path overrides.
- Atomic write via `tempfile` + `os.rename` (no partial file on crash).
- Appends a `reindex` event row to `log_events` after success.

## Exit codes

| Code | Envelope |
|---|---|
| 0 | `{"action": "rendered", "vault_id": ..., "output_path": ..., "page_count": N}` |
| 6 | `{"error": "VAULT_NOT_REGISTERED", "vault_id": ...}` |

## Related

- KNOWN_ISSUES D-2 (R-26 enforcement on `--output` paths — pending)
- ADR-002 §D8 (index.md is Class B — fully regenerable from DB)
