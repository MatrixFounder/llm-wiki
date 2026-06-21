# TASK 042 — fix dogfood-session errors: concept-quote rescue, loud drops, app-data index_db carve-out

## 0. Meta
- **Task ID:** 042 · **Slug:** `task-042-import-quote-rescue-and-appdata-carveout`
- **ADR:** none new — amends Q-022-4/HIGH-S2 (the absolute-`index_db` gate) in
  `docs/architectures/open-questions.md`.
- **Mode:** framework **self-improvement** (skill behavior + DAL config validation; no schema /
  `user_version` change — zero-DDL). Reviewers: `code-reviewer` + `security-auditor` (the carve-out
  relaxes a security gate). Both ran; security-audit **PASS** (no critical/high), code-review fed back
  two should-fix items, both applied.
- **Touches:** `scripts/wiki_skills/wiki_import_article/` (`_authoring.py`, `__init__.py`),
  `scripts/wiki_index/` (`factory.py`, `config_loader.py`), `scripts/wiki_skills/_common.py`,
  `scripts/wiki_skills/wiki_init.py`; tests (5 modules); docs/installers (`skills/wiki-import/
  references/reason-contract.md`, `skills/wiki-search/SKILL.md`, `CLAUDE.md`, `README.md`,
  `templates/{WIKI_SCHEMA.md.tmpl,CLAUDE.layout.md.tmpl}`, `docs/manuals/{cli-quick-reference,
  obsidian-llm-wiki_manual}{,.ru}.md`, `docs/runbooks/personal-vault-adoption.md`,
  `scripts/wiki_index/.AGENTS.md`, `scripts/wiki_skills/.AGENTS.md`, open-questions Q-022-4).

## 1. Problem (origin: a real Claude-CLI session inside an iCloud Obsidian vault)
A user-facing session comparing two Elliott-wave sources and importing one via `/wiki-import` hit a
chain of avoidable failures. Root causes, by layer:

1. **`INVALID_INDEX_DB` on the first `wiki-search`.** The vault's `index_db` is an absolute path
   (correctly outside iCloud — the framework forces the DB out of iCloud). Absolute paths were gated
   behind `WIKI_ALLOW_ABSOLUTE_INDEX_DB=1`, and the error named the env var only parenthetically —
   never "set it". Every later command then carried the env prefix, which made each Bash string unique
   and defeated permission allow-listing (the "too many prompts" complaint).
2. **Two concept pages silently dropped (`no-verbatim-quote`).** Entities named `"Зигзаг (волновой
   анализ)"` / `"Плоскость (волновой анализ)"` were dropped because (a) the orchestrator copied quotes
   from the raw source, not the authored body, and (b) the name-mention fallback probed only `name` /
   `name[:14]` — both still carry the `(волновой…` suffix the body never prints. The drop landed in
   `skipped[]` while `action:"imported"` / exit 0 made it look like a clean success.
3. **Agent-discipline errors** (not framework bugs): a hand-written `SELECT source_path …` (real column
   is `file_path`) and a `find | xargs grep` over an iCloud path (lazy `.icloud` placeholders + Cyrillic
   names → matched nothing).

## 2. Fixes
- **A — disambiguator-aware quote fallback.** `_authoring.verbatim_quote` strips a trailing
  `(disambiguator)` (`_DISAMBIG_SUFFIX_RE`) and probes the BASE name. Probe order `(name, name[:14],
  base)` keeps `base` last → strictly additive (only rescues a previously-dropped candidate; never
  changes an existing quote — locked by `test_verbatim_quote_prefix_probe_precedes_base_probe`).
- **B — loud drops.** `apply()` emits an always-present `warnings[]`; one `CONCEPTS_DROPPED` entry PER
  recoverable reason (`_LOSSY_SKIP_REASONS` = `no-verbatim-quote` + `max-candidates`), each with a
  reason-specific `hint`. Exit code unchanged (the note + other concepts still imported). Benign
  dedup/collision/layout skips stay quiet.
- **C — app-data carve-out + actionable error.** `factory.appdata_root()` (single source of truth,
  shared with `_resolve_db_path`); `config_loader.validate_index_db_value` trusts an absolute path that
  `resolve()`-s under it WITHOUT the env var (symlink-resolved first; fails closed if the root can't be
  computed). `INVALID_INDEX_DB` envelopes (`_common.py`, ×2 in `wiki_init.py`) gained an actionable,
  value-free `hint`. See open-questions Q-022-4 (TASK 042 amendment).
- **D — guidance.** reason-contract pre-apply self-check + `warnings[]` note; wiki-search SKILL + CLAUDE.md:
  prefer `wiki-search`/`file_path` over raw SQL or `find`/`grep` (esp. in iCloud vaults).

Settings layer (Error 5) was scoped as a snippet only (env var + read-only wiki-* allow-list in
`~/.claude/settings.json` or the vault's `.claude/settings.json`) — NOT applied; it belongs in the
vault/global Claude config, not this repo.

## 3. Verification
- Targeted (6 modules) + full suite: **1668 passed, 5 skipped**; `mypy --strict scripts/` clean.
- Real CLI E2E (karpathy scratch vault, absolute app-data `index_db`, NO env var): `wiki-init` scaffold
  + `wiki-search` + `wiki-import apply` all succeed; the two disambiguated concepts are filed
  (`_concepts/zigzag-wave-analysis.md`, `flat-wave-analysis.md`), and a genuinely unsupported entity
  drops with a loud `warnings[CONCEPTS_DROPPED]`. Negative control (absolute path outside app-data)
  returns the actionable `hint`.
