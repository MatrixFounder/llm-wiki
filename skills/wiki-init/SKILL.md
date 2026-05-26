---
name: wiki-init
description: >-
  Scaffold a new wiki vault OR register an existing one in the SQLite index.
  Modes: --scaffold-new (fresh vault layout), --register-existing (register
  pre-existing vault), --reconcile (rename a registered vault).
  Triggers: "create wiki vault", "register existing vault", "wiki-init".
tier: 2
version: 1.0
---

# wiki-init

Bootstrap or register a vault in the multi-vault SQLite index.

## When to use

- First time setting up a new vault on disk → `--scaffold-new --vault /path`.
- Existing vault (already has `WIKI_SCHEMA.md` with `vault_id`) needs to
  enter the index → `--register-existing --vault /path`.
- Operator renamed a vault folder or changed its `vault_id` →
  `--reconcile --vault /path --confirm`.

## Invocation

```bash
python -m scripts.wiki_skills.wiki_init <mode-flag> --vault <abs-path> \
    [--vault-id <slug>] [--db-path <override>] [--confirm]
```

Or `/wiki-init <args>`.

## Contract

- `--vault` is **required** for all modes (no silent cwd default).
- `vault_id` must match `^[a-z][a-z0-9-]{1,30}[a-z0-9]$` (ADR-002 §D1.1)
  OR be `_global_` sentinel.
- `--scaffold-new --force` overwrites `WIKI_SCHEMA.md` / `CLAUDE.md` templates.
- `--reconcile` without `--confirm` returns warning exit 7 with the proposed
  rename; re-run with `--confirm` to apply CASCADE rename.

## Exit codes

| Code | Envelope keys |
|---|---|
| 0 | `action: scaffolded` / `registered` / `already-registered` / `renamed` / `no-change` |
| 1 | `error: MISSING_VAULT_ARG` |
| 6 | `error: INVALID_VAULT_ID` / `MISSING_WIKI_SCHEMA` / `MISSING_VAULT_ID` / `VAULT_NOT_FOUND` / `VAULT_ID_COLLISION` / `VAULT_NOT_REGISTERED` |
| 7 | `warning: VAULT_RENAMED` (reconcile needs --confirm) |

## Related

- `scripts/wiki_skills/wiki_init.py`
- ADR-002 §D1.1 (vault_id REQUIRED no fallback)
- `templates/WIKI_SCHEMA.md.tmpl`, `templates/CLAUDE.md.tmpl`
