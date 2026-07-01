---
name: wiki-index-upsert
description: >-
  Index a single markdown file into the SQLite index. Parses frontmatter,
  normalizes body for FTS, upserts pages + page_entity_refs. Idempotent
  (file_hash match → unchanged). Triggers: "upsert page", "index this file".
tier: 2
version: 1.0
---

# wiki-index-upsert

Lowest-level index operation: one markdown file → one DB row (with refs).

## When to use

- Operator manually edited a file and wants it indexed without a full
  reindex (cheaper).
- Sub-step inside `wiki-import` (called once per `written[].path`).
- `wiki-lint --fix` (future) for resolving missing-in-db drift.

## When NOT to use

- Bulk reindex → use `/wiki-reindex --delta` or `--full`.
- File is NOT yet on disk → use `/wiki-import` (which fetches + authors
  the note first, then produces the file).

## Invocation

```bash
wiki-index-upsert \
    --vault <vault_id> \
    --source <abs-path-to-md-file> \
    [--vault-root <abs-path>] \
    [--db-path <override>]
```

Or `/wiki-index-upsert [...]`.

## Contract

- `--vault-root` defaults to walking up from `--source` looking for
  `WIKI_SCHEMA.md`. Provide explicitly if walk-up fails.
- Source path must resolve inside vault_root (R-26 / `validate_inside_vault`).
- Idempotent: same file_hash → `action: unchanged`, no DB mutation.
- Type-mapping per R-07.4 (`lesson-summary` → `summary` + `tag: lesson`).
- Body normalization per R-07.5 (mermaid blocks stripped; SECTION anchors
  excised before FTS write).

## Exit codes

| Code | Envelope |
|---|---|
| 0 | `{"action": "inserted" / "updated" / "unchanged", "slug": ..., "file_hash": ...}` |
| 6 | `{"error": "VAULT_ROOT_NOT_FOUND" / "UnmappedTypeError" / "BodyNormalizationError" / "PathTraversalError", "source": ...}` |

## Related

- `scripts/wiki_index/normalization.py` (type-mapping + body normalization)
- `scripts/wiki_source/manual.py` (frontmatter + ref extraction)
