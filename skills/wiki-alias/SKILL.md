---
name: wiki-alias
description: >-
  Register / remove / list alias surface-strings for an entity ("Hermes" →
  hermes-agent). Aliases are Class A frontmatter + SQLite mirror, expand
  wiki-search, and are hard-unique per vault (one alias → one entity).
  Triggers: "add alias", "register alias", "wiki-alias".
tier: 2
version: 1.0
---

# wiki-alias

Two-tier alias table (Epic 7, TASK 005 / R-5). An alias is a surface string
that resolves to one canonical entity in a vault. Aliases are **Class A
canonical** (entity-page `aliases:` frontmatter) + **Class B mirror**
(`entity_aliases`); `wiki-search` expands queries through them by default and
`wiki-lint` flags collisions. The `(vault_id, alias)` primary key enforces
one-alias-→-one-entity (closes KNOWN_ISSUES L-4).

## When to use

- The LLM/operator referred to one thing by several names; register the
  variants so search and resolution unify them.

## Usage

```bash
wiki-alias <slug> --add "Hermes" --vault <id>                 # register
wiki-alias <slug> --add "HMS" --type acronym --vault <id>     # typed
wiki-alias <slug> --remove "Hermes" --vault <id>              # drop
wiki-alias <slug> --list --vault <id>                          # list
```

- `<slug>` may be a canonical slug or an existing alias.
- `--type` ∈ spelling_variant (default) | translation | nickname | acronym |
  former_name | product_codename. The flat Obsidian `aliases:` list carries no
  type, so the type is Class B only and normalises to `spelling_variant` on a
  full reindex (documented limitation).

## Exit codes

| Exit | Code | Meaning |
|---|---|---|
| 0 | — | success (incl. idempotent `unchanged`) |
| 2 | `INVALID_ARG` | empty / too-long / control-char surface |
| 3 | `ENTITY_NOT_FOUND` | slug not in the vault |
| 4 | `ENTITY_FILE_MISSING` | entity file missing → run `wiki-reindex --delta` |
| 5 | `ALIAS_COLLISION` | surface already resolves to a different entity |
