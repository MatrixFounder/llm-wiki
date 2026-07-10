# PLAN 058 — wiki-config: per-folder config interface

Spec: `docs/TASK.md` (TASK 058). Full ratified design: `~/.claude/plans/drifting-snacking-wolf.md`.
Branch: `task-058-wiki-config-interface`. Each phase is independently shippable and ends
with `pytest tests/` + `mypy --strict scripts/` green + a commit.

## Phase 1 — read core (show/tree + provenance engine)
- [ ] `config/sync-config.schema.yaml`: additive `x-wiki-scope` (root-only|cascading) on
      SyncConfig top-level keys; `x-wiki-format: regex` on group_key/key.*_regex fields
      (instance validation byte-identical — unknown keywords are annotations).
- [ ] `scripts/wiki_index/sync_config.py`: additive `SyncConfigError.reason` machine field
      (SYMLINK|OUTSIDE_VAULT|SIZE_CAP|ALIAS|ANCHOR|PARSE|NOT_MAPPING|SCHEMA|UNSAFE_SUBDIR)
      set at existing raise sites; zero behavior change; existing tests untouched.
- [ ] New package `scripts/wiki_skills/wiki_config/`: `_uimodel.py` (schema → UI-model
      projection keyed by JSON pointer: type/enum/default/description/scope/format),
      `_provenance.py` (mirror-the-merge fold over `_ancestor_dirs` + `_load_validated_raw`
      + real `deep_merge`; origins, shadows, ignored-non-cascading; identity + layout
      systems via their loaders), `__init__.py` (argparse: `show`, `tree`; `emit` envelopes;
      `--report` md sidecar).
- [ ] `bin/wiki-config` wrapper (clone `bin/wiki-query` no-cd pattern).
- [ ] Tests: `test_wiki_config_provenance.py` (equivalence release-gate vs
      `resolve_policy`/`resolve_summarize`; origin-consistency; Cyrillic/space fixtures),
      `test_wiki_config_cli.py` (show/tree envelopes, exit codes, evolution test R-058-10).

## Phase 2 — validate
- [ ] `_findings.py`: `ConfigFinding` + taxonomy registry (33 codes → severity, tier,
      value-free message template) + renderers (histogram / md report / json sidecar).
- [ ] `_lint.py`: pass 0 discovery walk; pass 1 hard gates via loaders (catch + enumerate
      schema errors via `iter_errors`); pass 2 per-file advisory; pass 3 cross-level.
      All three config systems.
- [ ] CLI `validate [<folder>] [--strict] [--json-sidecar <p>] [--report <p>]`; exit 6 on
      error-severity, `--strict` promotes warnings.
- [ ] Tests: `test_wiki_config_validate.py` — one fixture per code; golden run over samples/;
      loader↔linter reason lockstep; CWE-209 grep-asserts.

## Phase 3 — write core (doctor/fix/restore/set)
- [ ] `requirements.txt` + `ruamel.yaml>=0.18`; mypy wiring confined to `_edit.py`.
- [ ] `_edit.py`: the sandwich — hardened gate BEFORE (our `_NoAliasSafeLoader` + schema +
      size cap on input text) → ruamel round-trip edit → hardened gate AFTER + semantic
      equality + untouched-lines byte-identity → downgrade-to-MANUAL on any failure.
- [ ] `_backups.py`: backup/list/prune(10)/restore; `atomic_write_text` (+ optional
      `suffix` param in `_common.py`).
- [ ] `_doctor.py`: FixPlan; finding→fix mapping (tiers per taxonomy); TOCTOU sha256
      pinning; PARSE_ERROR recovery (restore-from-backup | archive-`.broken`+scaffold).
- [ ] CLI `doctor`, `fix [--from-plan] [--yes] [--dry-run] [--no-backup]`,
      `restore [--list|--to] [--yes]`, `set`/`unset <folder> <pointer> [<value>]`
      (root-only-in-subfolder → exit 2 with explanation).
- [ ] Tests: `test_wiki_config_doctor.py` — fix round-trip per code, idempotency,
      adversarial downgrade, TOCTOU exit 2, backup retention/restore reversibility.

## Phase 4 — templates
- [ ] `templates/sync-profiles/{meeting-zone,lessons-mirror,connector-zone,article-zone,
      root-baseline}.yaml` with strict comment headers (name/semver/level/vars/purpose);
      migrate `templates/connector-zone.sync.yaml` (update manual references).
- [ ] `_templates.py`: registry (builtin + `<vault>/.wiki/templates/`, builtin wins on
      collision), header parse, `string.Template` vars (regex vars ReDoS-gated, control-char
      ban), full gate on rendered text pre-write; `--merge` (template=base, existing wins,
      append-only comment-preserving) / `--force` (backup + replace).
- [ ] CLI `init`, `templates`; `TEMPLATE_DRIFT` finding into `_lint.py`.
- [ ] `config/sync-config.schema.json` projection + identity test; `# yaml-language-server:`
      modeline injected by init; `SCHEMA_MODELINE_MISSING/STALE` findings.
- [ ] Tests: `test_wiki_config_init.py` per TASK acceptance (level mismatch exit 2,
      byte-identical re-init, ReDoS var exit 6 without echo, all builtins pass gates).

## Phase 5 — HTML report
- [ ] `_report.py`: pure `render_html(model) -> str` (string.Template + html.escape all;
      NFC display normalization; casefold sort; anchors slug+hash; configured-spine tree
      with `<details>` collapse; badges default/ROOT/↑inherited/HERE/⛔IGNORED; findings
      with shlex-quoted copy commands; CSP meta; prefers-color-scheme; ~150 lines vanilla
      JS: filter/expand/copy). Optional `render_md` (AUTO-block markers).
- [ ] CLI `report [--out] [--open] [--all-folders] [--md <path>]`; default out
      `<vault>/.wiki/config-report.html`; `webbrowser.open`.
- [ ] Tests: `test_wiki_config_report.py` — snapshot fixtures (Cyrillic/space/emoji names,
      ignored-root-key, invalid-file, icloud-placeholder, 3-level cascade), determinism.

## Phase 6 — serve (web editor)
- [ ] `_server.py`: stdlib `http.server`, single-threaded; 127.0.0.1:ephemeral; token
      fragment + `X-Wiki-Config-Token` (hmac.compare_digest); Host check; JSON-only POST;
      `validate_inside_vault`; whitelist dispatch. Endpoints: `/` (inline app),
      `GET /api/tree|/api/folder|/api/schema`, `POST /api/validate|/api/write|/api/fix|
      /api/template|/api/test-regex` (guarded_search deadline).
- [ ] Inline app (ONE html string module): schema-driven form renderer (enum dropdown,
      bool toggle, regex field + tester, array editor, inherited placeholders +
      override/reset, disabled root-only fields with root link) + YAML tab (debounced
      validate) + diff preview on save; shadcn-like CSS custom props, dark/light.
- [ ] Tests: `test_wiki_config_serve.py` — API contract via http.client against an
      in-process server: auth 403s, Host reject, traversal reject, write-through-sandwich
      (comments preserved, backup created), fix whitelist, test-regex bounded.

## Phase 7 — delivery
- [ ] `skills/wiki-config/SKILL.md` (disambiguation vs `config/wiki-config.schema.yaml`),
      `commands/wiki-config.md`; re-run `bin/install-globally.sh`.
- [ ] `docs/manuals/obsidian-llm-wiki_manual.md` section (+ exit-code table row,
      connector-zone path fix); `README.md` (18 CLIs); `docs/ARCHITECTURE.md` +
      `docs/architectures/` section; `docs/ROADMAP.md` entry.
- [ ] Dogfood: report+serve on `samples/Demand-generation` and
      `samples/personal-vault-dogfood` per TASK §6 acceptance; fix any findings.
- [ ] Final gates: full pytest, mypy --strict, golden samples run; merge to main.
