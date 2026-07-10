# TASK 058 — wiki-config: per-folder config interface (CLI + HTML report + local web editor)

## 0. Meta Information
- **Task ID**: 058
- **Slug**: wiki-config-interface
- **Origin**: operator request 2026-07-10 — "plan a web and/or CLI interface for configuring
  each folder in the tree: show which parameters are inherited vs defined at this level;
  syntax validation; repair/recovery; quick template-based folder setup; **editing with
  hints is a key capability**; the interface must NOT need rework when new config fields
  appear." Approved design: `~/.claude/plans/drifting-snacking-wolf.md` (plan-mode session,
  three-perspective design synthesis).
- **Type**: Feature (new 18th `wiki-*` CLI + web layer; additive; zero-DDL; no index/DB use)
- **Effort**: L (7 phases, each independently shippable)
- **Architecture**: no layering change. Class A/B/C untouched (`.wiki/sync.yaml` is Class A
  operator source; the HTML report is a derived, regenerable artifact — Class-B spirit).
  Decision-17 holds (no `import anthropic`; one JSON envelope + stable exit code per
  subcommand). H-6: config values are data, never echoed into error surfaces (CWE-209/117).
  One NEW dependency: `ruamel.yaml>=0.18` (write-path only, never a security gate).

## 1. Problem

Per-folder vault configuration (`.wiki/sync.yaml`) is hand-authored YAML with no tooling:

1. **Inheritance is invisible.** The Option-A cascade (deepest-wins RAW deep-merge,
   `scripts/wiki_skills/_resummarize.py:93-171`) applies ONLY to `resummarize:`/`summarize:`;
   `zones`/`exclude`/`tag_namespace`/`extensions`/`transcript_dedup` are consumed from the
   vault root only (`load_sync_config`, `scripts/wiki_index/sync_config.py:222`). An operator
   cannot see, for a given folder, which effective value comes from where — and a root-only
   key placed in a subfolder file is **silently ignored** (the #1 real-world trap, documented
   in the BD-workspace memory).
2. **Validation exists but only as a runtime fail-fast gate** (`_load_validated_raw`,
   exit 6). There is no whole-tree lint, no advisory findings (typo suggestions, dead mirror
   regexes, redundant overrides), no `--fix`, no doctor, no backup/restore anywhere in the
   repo.
3. **No guided setup.** `templates/connector-zone.sync.yaml` is the single copy-me file;
   real recurring shapes (meeting zone, lessons mirror with a `group_key` var) are re-derived
   by hand each time. Regex fields (`group_key`, `key.*_regex`, `match:` mode) are the
   documented pain points.
4. **No editing surface with hints.** The operator edits raw YAML blind; enum values,
   key scopes, and inherited context live only in code/docs.

## 2. Requirements (RTM)

| ID | Requirement | Verified by |
|----|-------------|-------------|
| R-058-1 | `wiki-config show <folder>`: effective config + per-key provenance (`default` / `root` / `<ancestor>` / defined-HERE, `shadows`, root-only scope), computed WITHOUT modifying the real resolver, provably equivalent to it | equivalence test suite (release gate) |
| R-058-2 | `wiki-config tree`: whole-vault override map incl. `overridden_by` and ignored keys; never aborts on one broken file | CLI tests |
| R-058-3 | `wiki-config validate`: whole-tree, all-findings (not fail-fast), across ALL THREE config systems (sync.yaml full; layout.yaml + WIKI_SCHEMA.md/.wiki.yaml via their loaders); taxonomy of stable finding codes with severity × fix-tier; wiki-lint-style outputs (histogram stdout, `--json-sidecar`, `--report`, `--strict`); exit 6 on error-severity | per-code fixture tests + golden run over `samples/` |
| R-058-4 | `wiki-config doctor`/`fix`: repair plan + tiered application (SAFE / CONFIRM→exit 7 / MANUAL); comment preservation as a **checked invariant** (ruamel sandwich: hardened-gate before AND after, semantic equality, untouched-lines byte-identity, downgrade-to-MANUAL on any verify failure); TOCTOU hash pinning (`CONFIG_DRIFTED` exit 2) | fix round-trip + idempotency + adversarial downgrade tests |
| R-058-5 | Backups: `.wiki/backups/<name>.<utc-ts>.bak` before every mutation of an existing file, retention 10, `wiki-config restore <folder> [--list\|--to <ts>]`; restore itself reversible | backup/restore tests |
| R-058-6 | `wiki-config init <folder> --template <name> [--var k=v] [--merge\|--force]` + `templates` list; 5 shipped profiles (meeting-zone, lessons-mirror, connector-zone, article-zone, root-baseline); level enforcement (root-template in subfolder → exit 2); regex vars ReDoS-gated; rendered output passes the full gate BEFORE write; deterministic (re-init byte-identical) | template tests |
| R-058-7 | `wiki-config report [--open]`: ONE self-contained HTML file (inline CSS/JS, CSP `default-src 'none'`, no CDN) with folder tree + per-key inheritance badges (default/ROOT/↑inherited/HERE/⛔IGNORED) + findings with copy-paste fix commands; `html.escape` + NFC on ALL interpolations (Cyrillic/space/RTL names); snapshot-tested | renderer snapshot tests + manual E2E |
| R-058-8 | `wiki-config serve`: local web editor — **schema-driven form** (enum→dropdown, bool→toggle, regex field with live tester, inherited values as placeholders with override/reset controls, hints from schema `description`) + raw-YAML tab with validation; writes go through the R-058-4 sandwich + R-058-5 backups | serve API tests + manual E2E |
| R-058-9 | serve security: bind 127.0.0.1 ephemeral port; token in URL fragment + `X-Wiki-Config-Token` header (`hmac.compare_digest`); zero cookies (CSRF-immune); Host-header check; JSON-only POST; `validate_inside_vault` on every path; whitelist-id dispatch (server never executes client strings) | security-focused API tests |
| R-058-10 | **Evolution invariant**: adding a new field to `config/sync-config.schema.yaml` (with `description`/enum/`x-wiki-*`) surfaces it in the UI model, form, HTML report, validate, and typo-suggestions with ZERO interface-code changes | dedicated test: inject a synthetic field into the schema → assert it appears in `_uimodel` projection + report model |
| R-058-11 | Existing behavior untouched: `_resummarize.py` and resolver semantics byte-identical; `sync_config.py` change limited to an additive `SyncConfigError.reason` field; all pre-existing tests pass unmodified | full pytest run |
| R-058-12 | `mypy --strict scripts/` stays green (ruamel confined to `_edit.py`, typed wrappers) | mypy gate |
| R-058-13 | Vendor-agnostic: every capability incl. report reachable from plain shell + any LLM harness as `/wiki-config`; serve optional, one command | SKILL.md/commands + install-script wiring |

## 3. Non-goals / out of scope
- No Obsidian plugin, no Electron/Tauri, no Node.js toolchain (frontend = one
  self-contained vanilla-JS HTML page — explicit user decision after weighing React+shadcn).
- No FastAPI/uvicorn/textual/rich/click — backend is stdlib `http.server`.
- No form editing for layout.yaml / WIKI_SCHEMA.md in v1 (raw-YAML tab + validate only;
  the generic renderer makes this a cheap follow-up).
- No editing of the SQLite index or any DB interaction at all (tool must work with a
  broken/absent DB — recovery scenario).
- No mutation deep-links from the static HTML report (copy-paste commands only).

## 4. Key design decisions (user-ratified)
1. CLI + HTML report + local web editor; **editing with hints is a key capability**.
2. Form-per-key + raw-YAML tab.
3. `ruamel.yaml` for comment-preserving writes — wrapped in the hardened sandwich; the
   existing `_NoAliasSafeLoader`/schema/size gates remain the ONLY security authority.
4. Scope: all three config systems (sync.yaml = full CRUD + form; other two = show/validate
   + raw-YAML editing).
5. Backups under `.wiki/backups/` + `restore` (vaults are typically not git repos).
6. **Schema-driven everything** (evolution without interface rework) — see R-058-10.
7. Frontend: vanilla JS single file, shadcn-like aesthetic, zero build/deps.

## 5. Evolution contract (answers "what happens when new fields appear")

Adding a field = one edit in `config/sync-config.schema.yaml`. Automatically picked up by:
form (runtime `/api/schema`), HTML report, validate (strict schema), difflib typo
suggestions, provenance (generic dict fold). Manual by design: (a) the consumer code that
USES the field (that is the feature itself); (b) `sync-config.schema.json` regeneration —
enforced by an identity test that fails until regenerated; (c) a NEW top-level cascading
block additionally needs a small resolver (à la `resolve_summarize`) — new fields INSIDE
`resummarize`/`summarize` cascade with zero code; (d) optional template refresh, surfaced
to operators via the `TEMPLATE_DRIFT` finding. Planned follow-ups (post-v1): form mode for
layout/identity configs, web restore/undo UI, finer `extract_concepts` granularity,
CI rail (`validate --strict`), localized descriptions.

## 6. Acceptance
- All RTM rows verified by the named tests; `pytest tests/` + `mypy --strict scripts/` green.
- Golden run: the 4 real `samples/**/sync.yaml` produce no unexpected findings.
- Manual E2E on `samples/Demand-generation`: report shows the Lessons cascade
  (`group_key` HERE, `source_state` ↑inherited); serve edits `profile` via the form →
  comments preserved, backup created, `wiki-sync scan --dry-run` sees the new value;
  hand-broken sync.yaml → doctor offers restore.
