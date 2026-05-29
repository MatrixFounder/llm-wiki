---
name: wiki-merge
description: >-
  Fold a duplicate entity into the canonical one (hermes-framework →
  hermes-agent): re-point references, absorb + register redirect aliases,
  delete the duplicate page. The alias table IS the durable redirect — no
  wikilink rewriting. Triggers: "merge entities", "dedupe entity", "wiki-merge".
tier: 2
version: 1.0
---

# wiki-merge

Resolves the "Hermes / Hermes Agent / Hermes Framework" duplication the LLM
creates (Epic 7, TASK 005 / R-4.7). Folds a duplicate `from` entity into the
canonical `into`:

1. **Class A first**: appends `from`'s slug + name + aliases to `into`'s
   frontmatter `aliases:` (the durable redirect), then **deletes** the `from`
   entity page (so a full reindex cannot re-materialise it).
2. **Class B mirror** (one transaction): re-points `page_entity_refs`
   (de-duplicating on the PK, keeping the higher trust_level), re-points/absorbs
   aliases, registers the redirect aliases (`former_name`), deletes the `from`
   row, and recomputes `into`'s mention count.

The **alias table is the redirect** — `[[from-slug]]` links keep resolving to
`into` via alias-aware resolution + reindex ref-canonicalization (AM-3). No
`[[...]]` wikilink rewriting (lower blast radius).

## Usage

```bash
wiki-merge <from-slug> <into-slug> --vault <id>            # fold
wiki-merge <from-slug> <into-slug> --vault <id> --dry-run  # report only
```

## Exit codes

| Exit | Code | Meaning |
|---|---|---|
| 0 | — | success (incl. `--dry-run`) |
| 2 | `INVALID_ARG` | bad slug |
| 3 | `ENTITY_NOT_FOUND` | `from` or `into` not in the vault (names which side) |
| 4 | `ENTITY_FILE_MISSING` | an entity file missing → run `wiki-reindex --delta` |
| 5 | `INVALID_MERGE` | self-merge (`from == into`) |
| 6 | `MERGE_MIRROR_FAILED` | Class A applied, DB mirror failed → `wiki-reindex --delta` to reconcile |

Output: `{from, into, action:"merged", refs_repointed, aliases_absorbed, aliases_skipped}`.
