# TASK 025 — adoption-currency-hardening

## 0. Meta

- **Task ID:** 025
- **Slug:** `task-025-adoption-currency-hardening`
- **Mode:** VDD (full) — task/arch/plan reviews + `/vdd-multi` + code-review
- **Context:** The 2026-06-09 **adoption-currency audit** (a 4-agent workflow run
  after the first real-vault dogfood of an obsidian-personal PARA iCloud vault).
  The audit verified the framework is substantially current (schema↔code: **no
  drift**; `wiki-init` TASK 022 behaviour verified live) and surfaced a set of
  **adequacy + documentation** gaps — none block adoption, but each was directly
  provoked by the real vault. This task closes them. Findings recorded in the
  auto-memory `personal-vault-adoption` and the runbook's "Related framework
  follow-ups" footer.
- **Constraints (inherited, non-negotiable):** zero DDL (`user_version` stays 5);
  no new deps; **no `import anthropic`**; `mypy --strict scripts/` is the contract;
  byte-identity for the Karpathy golden anchor (no behaviour change to Karpathy
  vaults); the obsidian-personal built-in changes must stay **back-compatible**
  (additive type_mapping / ignore only — never re-classify an already-indexed page
  type, never change a slug/project of an existing Karpathy/dev page).

## 1. Problem

After the real-vault dogfood, three classes of gap remain between the framework's
*shipped* state and the *validated reality*:

1. **Installer footgun (data-on-disk):** an absolute `--index-db` without
   `WIKI_ALLOW_ABSOLUTE_INDEX_DB=1` is written into `WIKI_SCHEMA.md` (a Class-A
   file) and the command *then* fails — leaving a half-applied mutation. The
   `INVALID_INDEX_DB` error is also emitted with two different contracts (exit 2 /
   `field: index-db` in `wiki_init.py`, vs exit 6 / `field: index_db` in the
   centralized `_common.build_repo_config`).
2. **Built-in obsidian-personal adequacy:** the PARA layout silently drops notes
   carrying a custom summary subtype not in its `type_mapping` (the dogfood hit
   `tutorial-summary`), and has no `ignore` for the `_raw`/`.staging` scratch trees
   that its companion `wiki-sync` config already prunes — so raw scratch markdown
   lands in the search index.
3. **Operator documentation:** the `basename` provenance match mode (the *correct*
   choice for the dogfood vault — it basenames BOTH sides) is undocumented
   everywhere (manual/README/workflow/schema; ARCHITECTURE calls it an "orphaned
   knob"); the `paths`/`ref_extraction` = REPLACE-on-override sharp edge is only in
   internal architecture, not the operator-facing schema/manual; and nothing tells
   an adopter that a custom `type:` needs a per-vault `type_mapping` override. The
   default-Karpathy `CLAUDE.md` template is written verbatim into PARA/dev vaults,
   incl. a hardcoded `rm "$HOME/Library/Application Support/wiki-index/global.db"`
   that is wrong for a local-`index_db` vault.

## 2. Requirements & RTM

| ID | Requirement | Class | Sev | Verification |
|----|-------------|-------|-----|--------------|
| **R-025-1** | `wiki-init` (scaffold-new + register-existing) validates the candidate `index_db` (absolute→`WIKI_ALLOW_ABSOLUTE_INDEX_DB` gate; symlink/escape; NUL) **BEFORE** `_ensure_index_db` writes it → a failed command leaves WIKI_SCHEMA.md **unmutated**. Validation logic shared with `config_loader.resolve_index_db_path` (single source of truth). | code | MED | `tests/test_cli_local_db_resolution.py`: absolute `--index-db` without env → exit 6, schema **unchanged** (new); with env → written. Existing relative/symlink/escape cases stay green. |
| **R-025-2** | `INVALID_INDEX_DB` is emitted with **one** contract everywhere: exit **6**, `field: "index_db"`. `INDEX_DB_ALREADY_DECLARED` aligned to `field: "index_db"` (keep its exit). Module docstring exit-code legend enumerates exit 2 (INVALID_VENDOR, INDEX_DB_ALREADY_DECLARED) + the TASK 022 errors. | code | LOW | grep: no `field: "index-db"` remains; tests assert exit 6/index_db for the malformed + ungated-absolute cases. |
| **R-025-3** | obsidian-personal built-in `type_mapping` pre-maps the common summary family: add `tutorial-summary`, `article-summary`, `book-summary`, `video-summary`, `podcast-summary`, `course-summary` → `db_type: summary` (+ a distinguishing tag). | code | MED | `tests/test_layouts_end_to_end.py`: a note `type: tutorial-summary` indexes as `db_type=summary` (no UnmappedTypeError). |
| **R-025-4** | obsidian-personal built-in `ignore` excludes raw/staging scratch markdown from the search index via `**/_raw/**` + `**/.staging/**` (ANY depth). INTENTIONALLY BROADER than wiki-sync's own walk (which prunes only `_raw/.staging\|.locks\|failed` and INGESTS top-level `_raw/`) — the search index excludes all raw markdown, the sync walk distils it; they deliberately disagree on `_raw`. `_raw`/`.staging` become reserved scratch names. (Does NOT add `_transcripts` — distilled `.txt`, already non-`.md`.) | code | MED | layout test: a `_raw/foo.md` under a numbered folder is NOT indexed; `.staging/**` likewise. Karpathy byte-identity unaffected. |
| **R-025-5** | Layout-aware `CLAUDE.md`: (a) remove the hardcoded `rm …/global.db` from the Karpathy template — `wiki-reindex --full` rebuilds from Class-A without it; (b) add a non-Karpathy `CLAUDE.*.md.tmpl` for `dev-project`/`obsidian-personal` (layout-aware flow: reindex/upsert in place, `.wiki/{layout,sync}.yaml` tuning, no `_sources`/promote), selected per `--layout` in `_write_agent_files`. | code/tmpl | MED | `wiki-init --scaffold-new --layout obsidian-personal` writes the PARA template (no `_sources`/`global.db rm`); Karpathy still writes the (fixed) Karpathy template. Test asserts template selection per layout. |
| **R-025-6** | Document the `basename` provenance match mode + the choose-which rule: `config/sync-config.schema.yaml` `ProvenanceRef.match` gains a `description`; `docs/manuals/…` + `workflows/wiki-sync.md` + ARCHITECTURE Q-019 note that `basename` basenames both sides and is preferred for globally-unique source basenames / pre-existing basename-cited corpora. | docs | HIGH | grep: `basename` documented in manual + workflow + schema; "orphaned knob" phrasing softened. |
| **R-025-7** | Document the `paths`/`ref_extraction` = REPLACE merge asymmetry (vs `ignore` UNION, `type_mapping` MERGE) in `config/layout-config.schema.yaml` top description + the manual override section. | docs | LOW | grep: REPLACE semantics in schema + manual. |
| **R-025-8** | Document that a custom `type:` not in the built-in `type_mapping` must be added via a per-vault `.wiki/layout.yaml` `type_mapping` override (else UnmappedTypeError-skip). | docs | LOW | grep: present in manual (runbook already covers it). |

## 3. Non-goals / explicitly deferred

- **Do NOT change the resummarize default `match`** (`vault-rel-path`). Changing a
  back-compat gate default risks MERGING distinct same-basename raws on other
  vaults. Document the tradeoff (R-025-6) and let the operator opt into `basename`.
- No `register-existing` fail-fast layout validation (audit INFO) — downstream
  resolution already catches a typo cleanly; defer.
- No advisory `default:` annotations in sync-config schema (audit INFO) — cosmetic;
  defer.
- No DDL, no new CLI, no new deps.

## 4. Acceptance

- All 8 RTM rows verified; full `pytest` green + `mypy --strict scripts/` clean.
- Karpathy golden-anchor byte-identity preserved (a Karpathy reindex is unchanged).
- `/vdd-multi` (logic/security/performance) converged; code-review APPROVED.
- Runbook footer "Related framework follow-ups" updated to "closed in TASK 025".
