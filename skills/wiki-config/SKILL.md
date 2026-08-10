---
name: wiki-config
description: >-
  Inspect, validate, repair, and EDIT the per-folder vault config
  (`.wiki/sync.yaml` cascade) — effective values with per-key inheritance
  provenance (default / root / inherited-from / defined-here / ignored),
  whole-tree validation across all three config systems, tiered doctor/fix
  with backups+restore, template-based folder setup, a self-contained HTML
  inheritance report, and a local token-authenticated web editor (schema-driven
  form with hints + raw-YAML tab).
  Triggers: "which settings does this folder inherit", "why is this key
  ignored", "validate the sync config", "fix my sync.yaml", "set up this
  folder from a template", "config report", "wiki-config".
tier: 2
version: 1.1
---

# wiki-config

Per-folder configuration interface for a vault's **`.wiki/sync.yaml`** tree
(TASK 058). NOT the vault *identity* config — `WIKI_SCHEMA.md` is validated
here (`validate`) but owned by `wiki-init`; the similarly-named
`config/wiki-config.schema.yaml` is that identity schema, while this CLI's
schema is `config/sync-config.schema.yaml`.

Key facts the tool encodes so you don't have to remember them:

- Only **`resummarize:` and `summarize:`** cascade per folder (deepest-wins
  RAW deep-merge; partial overrides inherit the parent's other keys; LISTS
  REPLACE, never extend). `zones` / `exclude` / `tag_namespace` /
  `extensions` / `transcript_dedup` are **root-only** — in a subfolder file
  they are silently ignored (surfaced as `NON_CASCADING_KEY_IN_SUBFOLDER`).
- The scope split lives in the schema itself (`x-wiki-scope` annotations), and
  every interface surface (form, report, provenance, typo suggestions) is
  generated from the schema at runtime — a NEW config field needs zero
  interface-code changes.
- No DB access at all: works with a broken or absent index (recovery path).

## Subcommands

| Command | Purpose | Exit |
|---|---|---|
| `show [<folder>]` | effective config + per-key provenance (`origin`, `shadows`, root-only scope). Folder optional: defaults to the **active Obsidian note's** folder → CWD (inside vault) → vault root; envelope `folder_source` names the signal | 0 / 2 / 6 broken ancestor |
| `tree` | vault-wide override map (defines / overridden_by / ignored; never aborts) | 0 |
| `validate [<folder>] [--strict] [--json-sidecar J] [--report M]` | ALL findings (40-code taxonomy), 3 config systems | 6 on error-severity; `--strict` promotes warnings |
| `doctor [--report M]` | validate + tiered repair PLAN (read-only; diffs in the report) | 0 |
| `fix [--from-plan J] [--yes] [--dry-run] [--no-backup]` | apply plans: SAFE always, CONFIRM with `--yes` | 7 confirm pending · 5 partial fail · 2 CONFIG_DRIFTED |
| `set <folder> <pointer> <value>` / `unset …` | one-key edit, comment-preserving, schema-gated; refuses a root-only key in a subfolder | 0 / 2 / 6 |
| `init <folder> --template <n> [--var k=v] [--merge\|--force]` | template setup (level-enforced; regex vars ReDoS-gated; re-init byte-identical) | 0 / 1 / 2 / 6 / 7 exists |
| `templates` | list builtin + `<vault>/.wiki/templates/*` (builtin wins collisions) | 0 |
| `restore <folder> [--list\|--to TS] [--yes]` | reversible restore from `.wiki/backups/` (retention 10) | 0 / 2 / 7 |
| `report [--open] [--out P] [--all-folders] [--md P]` | ONE self-contained HTML file: hierarchical tree (configured spine + ancestors) + badges default/ROOT/HERE/↑ancestor/⛔IGNORED + copy-paste fix commands | 0 |
| `serve [--port N] [--open]` | local web editor: schema-driven form (hints, enum dropdowns, inherited placeholders, override/reset, regex tester) + YAML tab. Full vault tree (unconfigured folders dimmed; Override here / Delete config), collapsible + expand/collapse-all (state persisted), per-folder **pending edits** kept across switches (red tree dots + *Save all N*), template Quick setup / re-init in the panel header, **restore-from-backup** picker (amber banner when a folder HAD a config) | runs until Ctrl-C |

## Invocation

```bash
wiki-config show --vault-root ~/Vault   # no folder → the active Obsidian note's folder
wiki-config show "06 - Business Development/Встречи" --vault-root ~/Vault
wiki-config validate --strict --json-sidecar /tmp/plan.json
wiki-config fix --from-plan /tmp/plan.json --yes
wiki-config init Lessons --template lessons-mirror --var 'group_key=^(\d{8})'
wiki-config report --open
wiki-config serve --open
```

Or `/wiki-config …` from any harness.

## Contract

- One JSON envelope on stdout per **completed subcommand invocation**; human output via
  `--report` sidecars. ⚠️ **Two stated exceptions** (DF-072-3): an argparse refusal writes usage
  to **stderr**, exits **2** and prints **nothing** to stdout; and **`serve`** prints its tokened
  URL banner to **stderr** and returns 0 with **no stdout envelope at all**
  (`wiki_config/_server.py:564-572` — deliberate: it keeps the token out of the machine-readable
  stdout envelope). ⚠️ **stderr is not a confidentiality boundary** — `capture_output=True`,
  `2>&1`, CI logs and most agent harnesses capture it, and many surface it to a model. The real
  protections are that the token lives in the URL **fragment** (never sent to the server, never
  logged by it), the 127.0.0.1 bind, the Host-header allowlist and `hmac.compare_digest`.
- Every mutation of an existing file: hardened-gate sandwich (the write is
  verified semantically + comment-survival before it happens; an unverifiable
  fix downgrades to MANUAL and writes NOTHING) + `.wiki/backups/` copy +
  TOCTOU hash re-check. Envelopes never echo operator values (CWE-209).
- serve binds 127.0.0.1 only; the token travels in the URL fragment and the
  `X-Wiki-Config-Token` header; zero cookies; whitelist-id dispatch.

## Related

- `scripts/wiki_skills/wiki_config/` — implementation package.
- `config/sync-config.schema.yaml` (+ committed `.json` projection for the
  yaml-language-server modeline that `init` injects).
- `templates/sync-profiles/*.yaml` — the builtin profiles.
- `skills/wiki-sync/SKILL.md` — the consumer of everything this tool edits.
