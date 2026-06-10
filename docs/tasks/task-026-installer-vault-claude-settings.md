# TASK 026 — installer ships the vault `.claude/settings.json`

## 0. Meta
- **Task ID:** 026 · **Slug:** `task-026-installer-vault-claude-settings`
- **Mode:** VDD (focused) — code-review + critic-security gate
- **Context:** TASK 025 added `templates/vault.claude-settings.json` (the Claude Code
  permissions template that stops the constant command prompts in a vault). The
  operator currently must copy it by hand. `wiki-init` already writes the per-vendor
  agent file (`CLAUDE.md`) where the `--vendor` is selected; it should ALSO drop the
  vendor's settings file there, so adopting a vault is one command.
- **Constraints:** zero DDL (`user_version` 5); no new deps; no `import anthropic`;
  `mypy --strict`; the Karpathy golden-anchor byte-identity unaffected; **NON-destructive**
  (must never clobber an operator's existing `.claude/settings.json` or their accumulated
  `settings.local.json`) — only write if absent or `--force`.

## 1. Requirements & RTM
| ID | Requirement | Class | Verification |
|----|-------------|-------|--------------|
| **R-026-1** | `templates/agent-files.yaml` `claude` vendor gains optional `settings_file: ".claude/settings.json"` + `settings_template: "vault.claude-settings.json"`. Config-driven (other vendors may declare their own later; absent ⇒ no settings written). | config | YAML parses; `gemini` declares none. |
| **R-026-2** | `wiki-init` (scaffold-new + register-existing) writes the selected vendor's settings file into `<vault>/<settings_file>` **when the vendor declares one** — copied **VERBATIM** (NOT `string.Template.substitute`; the JSON contains `$schema`), parent dir `mkdir -p`, NON-destructive (absent-or-`--force`), reported in the `agent_files` envelope (`{".claude/settings.json": "written"\|"exists"\|"error"}`). | code | new test: `--register-existing` with default (claude) vendor writes `.claude/settings.json` byte-identical to the template; re-run → `"exists"` (no clobber); `--vendor gemini` writes none. |
| **R-026-3** | A pre-existing `.claude/settings.json` is preserved (status `"exists"`); `--force` overwrites it. `settings.local.json` is never touched. | code | test: pre-create a sentinel `.claude/settings.json` → unchanged without `--force`, replaced with `--force`. |

## 2. Non-goals
- No Gemini settings template (Gemini settings format differs; `gemini` declares no
  `settings_file` → nothing written). No `--no-settings` flag (YAGNI; `--force` + manual
  edit suffice). No change to the `_resolve_vendors` selection grammar.

## 3. Acceptance
- RTM verified; full `pytest` green + `mypy --strict scripts/` clean; Karpathy byte-identity held.
- The settings file is verbatim-identical to `templates/vault.claude-settings.json` (valid JSON).
- code-review APPROVED + critic-security clean (non-destructive, no path escape, no clobber).
