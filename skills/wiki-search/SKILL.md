---
name: wiki-search
description: >-
  FTS5 full-text search across one or more registered vaults. Returns ranked
  hits with BM25 score + snippet. Use when looking up domain facts, prior
  decisions, concept/entity definitions before grep+Read.
  Triggers: "search wiki", "find in vault", "wiki-search".
tier: 2
version: 1.0
---

# wiki-search

Read-only FTS5 query against the multi-vault SQLite index. Single-vault,
multi-vault, or cross-vault (`_global_` sentinel).

## When to use

- Agent / operator looking up a concept slug, entity name, or fragment in
  the knowledge base before doing anything else.
- Phase 3a knowledge-lookup default — see `CLAUDE.md` "Knowledge lookup
  priority".
- Before creating a concept/entity page, search to avoid duplicates.

## When NOT to use

- Need full file contents → `Read` after `wiki-search` returns the path.
- Search disk for files not yet indexed → `Glob` or `find`.

## Invocation

```bash
python -m scripts.wiki_skills.wiki_search "<query>" \
    [--vaults "<id1,id2>" | --vaults all] \
    [--types summary,concept,entity] \
    [--project _vault_] [--limit 20] \
    [--format json|markdown] \
    [--db-path <override>]
```

Or `/wiki-search "<query>" [...]`.

## Contract

- `<query>` is an FTS5 MATCH expression — supports `AND`, `OR`, `NOT`,
  phrase quoting, prefix `*`. Invalid syntax → `sqlite3.OperationalError`.
- `--vaults` omitted OR `all` → searches every registered vault.
- Default output: JSON envelope with `hits[]` (each hit has `vault_id`,
  `slug`, `project`, `type`, `title`, `bm25_score`, `snippet`).

## Exit codes

| Code | Envelope |
|---|---|
| 0 | `{"action": "searched", "query": ..., "hits": [...], "count": N}` |
