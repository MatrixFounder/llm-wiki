---
name: wiki-confirm
description: >-
  Promote an LLM-extracted candidate entity to confirmed (or demote with
  --undo), or bulk auto-promote by mention threshold. Confirm-state is Class A
  (entity-page frontmatter `is_candidate`) mirrored to the SQLite index.
  Triggers: "confirm entity", "promote candidate", "wiki-confirm".
tier: 2
version: 1.0
---

# wiki-confirm

Two-tier entity resolution (Epic 7, TASK 005 / R-4). `wiki-extract-concepts`
emits **candidate** entities (`is_candidate=1`); this promotes them to
**confirmed** (`is_candidate=0`). Confirm-state is Class A canonical — the
frontmatter is written first, then mirrored to the DB via an explicit setter
that **bypasses** the re-extraction `MIN()` downgrade-guard (operator intent is
authoritative). Durable: survives `wiki-reindex --full`.

## When to use

- An operator reviewed a candidate concept page and wants it in the canonical
  catalog (search/index surface confirmed entities).
- Bulk-confirm everything that has crossed a mention threshold (`--auto`).

## Usage

```bash
wiki-confirm <slug> --vault <id>            # promote candidate → confirmed
wiki-confirm <slug> --vault <id> --undo     # demote confirmed → candidate
wiki-confirm --auto --threshold 3 --vault <id>            # bulk by mentions ≥ N
wiki-confirm --auto --threshold 3 --vault <id> --dry-run  # report only, no writes
```

- `<slug>` may be a canonical slug **or** a registered alias (it is resolved).
- `--threshold` default **3**. `--dry-run` mutates neither frontmatter nor DB.
- `--auto` flips the Class A frontmatter of every promoted entity too (so a
  full reindex does not revert it).

## Exit codes

| Exit | Code | Meaning |
|---|---|---|
| 0 | — | success (incl. idempotent `changed:false` and `--dry-run`) |
| 2 | `INVALID_ARG` | a slug is required unless `--auto` |
| 3 | `ENTITY_NOT_FOUND` | slug not in the vault |
| 4 | `ENTITY_FILE_MISSING` | entity file missing on disk → run `wiki-reindex --delta` |

Output is a one-line JSON envelope (`{slug, status, changed}` or
`{action:"auto-promote", promoted:[...]}`).
