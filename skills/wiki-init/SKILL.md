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
wiki-init <mode-flag> --vault <abs-path> \
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

⚠️ **Exit `1` here carries a normal ERROR envelope** (`MISSING_VAULT_ARG`), which diverges from
the family convention that `1` = an unhandled exception with **no** envelope. Read the envelope,
not `$?` (DF-072-3).

## `vault_id` validity — the two rules the `pattern` cannot express

`INVALID_VAULT_ID` envelopes carry `{field, reason, source, pattern, constraints}` and **never**
the offending value (DF-072-5, CWE-117). `pattern` is `^[a-z][a-z0-9-]{1,30}[a-z0-9]$`; two rules
sit outside it and are emitted in `constraints`:

- **No `--` sequence.** `a--b` matches the regex and is still refused.
- **`_global_` is ACCEPTED** — deliberately, and it is not an oversight (DF-074-3). It is
  `layout.GLOBAL_VAULT_SENTINEL`: the vault_id `wiki-search --log-access` attributes a
  **multi-vault** read to (charging it to one named vault would be wrong), and the one
  `repository.list_vaults` excludes from "all registered vaults". `wiki-init` is the only surface
  that calls `register_vault`, so refusing it would make that row unseedable and multi-vault
  read-audit permanently unattributable. The leading underscore — which the pattern forbids — is
  what keeps it out of the namespace an operator can mint by accident. Pinned by
  `tests/test_wiki_init_flows.py::test_global_sentinel_is_an_accepted_vault_id_on_purpose`.

`source` names where the id came from (`--vault-id` vs *derived from the vault directory name*),
so a refusal of a **derived** id doesn't send the operator hunting for a flag they never passed.

## Related

- `scripts/wiki_skills/wiki_init.py`
- ADR-002 §D1.1 (vault_id REQUIRED no fallback)
- `templates/WIKI_SCHEMA.md.tmpl`, `templates/CLAUDE.md.tmpl`
