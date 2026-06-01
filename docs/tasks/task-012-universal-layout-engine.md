# TASK 012 — Universalise the layout engine + dev-vault bootstrap (R-X1 + R-X2 A-B + R-X3)

> **VDD MODE** — high-integrity decomposition. Requirements structured as one
> Epic with an RTM, detailed Use Cases, and binary Acceptance Criteria.
> Approved implementation plan: `~/.claude/plans/docs-roadmap-md-ticklish-sunrise.md`.

### 0. Meta Information

- **Task ID:** 012
- **Slug:** `universal-layout-engine`
- **Mode:** VDD (`/vdd-start-feature` → `/vdd-plan` → `/vdd-develop-all`)
- **Roadmap source:** `docs/ROADMAP.md` → "P2 — Cross-project indexing" → **R-X1**
  (Universalise layout engine — PW-A..N + PW-Q) + **R-X2** Phases A-B (dev-vault +
  obsidian-personal bootstrap) + **R-X3** (KNOWN_ISSUES → per-file migration; pulled
  forward by operator decision #1 — see below).
- **Design proposal:** `docs/proposals/indexing-agentic-dev-artifacts.md` (2026-05-27,
  `/vdd-adversarial` PASS) — §11 (PW table, error policies, ReDoS guard), §§2,4,8
  (Phases A-C), §Phase D (KNOWN_ISSUES migration), §12 (dependency strategy).
- **Predecessors / seams already in place:**
  - TASK 007 (R-6) introduced the **R-X1-forward role split** in `layout.py`
    (`INGEST_SHARED_SUBDIRS` / `HOST_ONLY_SUBDIRS`) + the **type-aware reindex
    read-side** (`_cited_refs_from_frontmatter`, R-6.5e) this task generalises.
  - TASK 008 (R-8) added `_verifications` as the **second** `HOST_ONLY_SUBDIRS`
    member (proving the role-split generalises) and was built **layout-agnostic
    by construction** (reads via `pages.file_path` + DAL) as explicit
    R-X1/R-X2-forward preparation (C-8/NFR-7).
  - The existing per-vault config system (`config_loader.py` +
    `config/wiki-config.schema.yaml`, `load_config(cwd)`) — **kept as-is**; this
    task adds a **parallel** layout-grammar layer (operator decision #2).
- **Current HEAD:** `c8881fd` (TASK 011 shipped + just archived to
  `docs/tasks/task-011-wiki-verify-eval-v4.md`); schema `user_version = 5`.
- **Closes:** R-X1, R-X2 (Phases A-B), R-X3 in `docs/ROADMAP.md`. Migrates this
  repo's `docs/KNOWN_ISSUES.md` to per-file Class-A `docs/issues/*.md`.
- **Defers (operator decision #4, recorded in ROADMAP this task):** R-X2 **Phase C**
  (the `agentic-development/.agent/tools/archive_protocol.py` indexing hook) — split
  out as a separate follow-up entry; *stabilise the wiki first, then extend to the
  framework*. Also still deferred: R-X4, R-X5, PW-I (enum), PW-O (date), PW-P (MOC).

- **Scope decisions (operator-confirmed 2026-06-01, via plan-mode AskUserQuestion):**
  - **D-012-1 (PW-G/H/Q = INCLUDE NOW).** Build the full §11 engine *including* the
    KNOWN_ISSUES auto-render (PW-H), the one-shot splitter (PW-G), and the
    auto-generated lint guard (PW-Q), **and** dogfood the migration on this repo's
    `docs/KNOWN_ISSUES.md`. This pulls **R-X3 / Phase D** forward into this Epic.
    Requires an **ADR-002 §D8 amendment** (new Class-B sub-case "rebuildable
    markdown") landed **before** the renderer ships.
  - **D-012-2 (config = TWO SEPARATE SYSTEMS).** The existing per-vault config
    (identity/language/lint) is untouched. A **new parallel layer** carries the
    parsing grammar: `scripts/wiki_index/layout_config.py` +
    `config/layout-config.schema.yaml` + built-in
    `scripts/wiki_index/layouts/{karpathy,dev-project,obsidian-personal}.yaml`.
    `WIKI_SCHEMA.md` `layout:` just *names* the layout; the grammar ships once.
  - **D-012-3 (ReDoS = stdlib `re` + load-time budget gate).** No new runtime
    dependency (protects the PyPI/self-contained-publication goal). Validate every
    operator-supplied regex against a 100 KB adversarial payload at config-load;
    reject (exit 6) over-budget patterns. Built-in layouts are pre-vetted. The
    residual (a pattern slow only on specific file content) is documented; a stdlib
    watchdog is added later only if it actually bites (YAGNI).
  - **D-012-4 (archive hook = DEFER).** See "Defers" above.

---

### 1. General Description

`obsidian-llm-wiki` indexes a vault into SQLite/FTS5. Today the *layout grammar* —
which files exist, what page-`type` they are, how `project`/`slug` are derived, and
how wiki-links are extracted — is **hardcoded** across ~15 Python surfaces
(`layout.py` constants, `reindex.py::discover_pages`, `normalization.py`'s
`TYPE_MAPPING`/`_PATH_TYPE_FALLBACK`, `parsing.py`'s `_WIKILINK_RE`/`derive_slug`,
plus three more walks). Every new vault shape (a software project's `docs/`, a real
personal Obsidian vault with numbered folders + Cyrillic + system dirs + `.base`
files) requires **another Python patch**.

**Goal:** replace those hardcoded surfaces with a **YAML-config-driven engine**.
Three built-in layouts ship — `karpathy.yaml` (today's behaviour, **byte-identical**),
`dev-project.yaml`, `obsidian-personal.yaml`. New layouts become **config, not code**.
Then extend `wiki-init` with a `--layout` flag, bootstrap this repo (and one peer)
as dev-vaults, and migrate this repo's `KNOWN_ISSUES.md` to per-file Class-A pages
with an auto-rendered ledger — dogfooding the engine end-to-end. The payoff:
`wiki-search "ADR-002" --vaults all` returns ranked, snippetted, cross-project hits.

#### 1.1 Connection with existing system (grounded facts, file:line verified)

| Fact (verified in repo) | Consequence for this task |
|---|---|
| `layout.py` is the single source of truth for layout constants: `SOURCES_SUBDIR`/`_concepts`/`_entities`/`_queries`/`_verifications`, `INGEST_SHARED_SUBDIRS`, `HOST_ONLY_SUBDIRS`, `PAGE_SUBDIRS`, `COURSE_TIER_DIR="Lessons"`, `VAULT_TIER_PROJECT="_vault_"`, `SCAFFOLD_DIRS`, `SYSTEM_FILES`, `SCHEMA_FILE`, `VAULT_INDEX_DIR`, `GLOBAL_VAULT_SENTINEL` ([layout.py](../scripts/wiki_index/layout.py)). Imported by 20+ files. | **Constants are NOT deleted.** `karpathy.yaml` is a *validated projection* of them (R-X1.A invariant test). `wiki_init` scaffolding, `SYSTEM_FILES`, and the vendored `wiki_ingest.DEFAULT_SUBDIRS` drift guard keep depending on them. |
| `reindex.py::discover_pages(vault_root)` ([reindex.py:65-88](../scripts/wiki_index/reindex.py)) **unconditionally** walks root-tier `PAGE_SUBDIRS` (project=`"_vault_"`) **and** `Lessons/<Course>/PAGE_SUBDIRS` (project=`slugify(course)`). The `layout` field (flat/per-project) does **NOT** gate the walk. `slug = path.stem` (verbatim). | The Karpathy grammar = both tiers, always. `flat`/`per-project` collapse safely onto `karpathy.yaml` (R-X1.A alias map). The byte-identity anchor (Bead 0) snapshots THIS function. |
| The two-tier walk appears in **five physical sites** (architecture-review C1): `reindex.py::discover_pages` (canonical-to-be), `sqlite_repository.py::check_drift` (~577 — **already delegates** to `discover_pages`, no change), `sqlite_repository.py::find_pages_missing_in_index` (526-549 — **inlines its own walk + compares slug-ONLY, ignoring project**; a latent course-tier bug), `parsing.py::derive_slug` ([parsing.py:58-76](../scripts/wiki_source/parsing.py)), and `wiki_extract_concepts.py::_derive_source_project` (~1140-1165). | **Converge the three non-delegating walks onto `discover_pages`/`iter_pages`, comparing on `(slug, project)` not bare `f.stem`** — else the drift/orphan surface and the reindex surface disagree → false orphans + spurious `wiki-lint --fix` re-upserts under a drifted slug (`UNIQUE(vault_id, slug, project)` PK-drift). (R-X1.B + R-X1.L.) |
| `TYPE_MAPPING` (15 entries) + `_PATH_TYPE_FALLBACK` (4 subdir→type) + `_slugify_concept(regex_pattern=r"[^a-z0-9\-]")` ([normalization.py:75-123](../scripts/wiki_index/normalization.py)). `_slugify_concept` is the **strict** concept-tag slug — distinct from the **loose** course-project `slugify` and from the verbatim page `path.stem`. | **Three slug surfaces kept distinct.** Karpathy page slug = new `slug_strategy: identity` (no slugify). `_slugify_concept` is **left untouched**. PW-L strategies (`transliterate`…) all *call* slugify and are obsidian-personal-only. |
| `_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")`; `extract_wiki_links(body)→[(target,line,quote)]` ([parsing.py:15,43-55](../scripts/wiki_source/parsing.py)). | `karpathy.yaml` `ref_extraction[]` carries exactly this one pattern → byte-identical output. `extract_wiki_links` kept as a thin wrapper. (R-X1.D.) |
| `pages` PK = `UNIQUE(vault_id, slug, project)` + `UNIQUE(vault_id, file_path)`; `pages.type` CHECK = `{summary,concept,query,brief,research,index,verification}`; `user_version = 5` ([sql/wiki-index-v2.sql](../sql/wiki-index-v2.sql)). | **Zero DDL in R-X1/R-X2.** New doc types (task/adr/review/…) route through the **TYPE_MAPPING tag-route** to existing `db_type` enum values (proposal §3 / §7.1) — no `pages.type` CHECK change. `user_version` stays **5**. (PW-I enum extension stays deferred.) |
| EXISTING config: `config/wiki-config.schema.yaml` ($defs `WikiRootConfig`/`WikiProjectOverride`/`Layout` enum `[flat,per-project]`/`Paths` — **`Paths` is defined but NOT consumed** by the hardcoded engine) + `config_loader.py` `load_config(cwd)` (jsonschema Draft202012Validator, `deep_merge` REPLACES lists). | **Kept untouched** except the `Layout` enum gains `karpathy`/`dev-project`/`obsidian-personal`. The new grammar lives in the **parallel** `layout_config.py` layer (D-012-2) because `deep_merge`'s list-replace is wrong for layered layout grammar. |
| `WIKI_SCHEMA.md` frontmatter today: `vault_id`, `schema_version:"2.0"`, `language`, `layout`, `description` (template `templates/WIKI_SCHEMA.md.tmpl`). `wiki-init` argparse `--layout {flat,per-project}` ([wiki_init.py](../scripts/wiki_skills/wiki_init.py)); stores layout in `vaults.config_json`. | R-X2 expands `--layout` to 5 values + writes the chosen `layout:` into `WIKI_SCHEMA.md`; the engine resolves the built-in `layouts/<name>.yaml` (with `flat`/`per-project`→karpathy alias). |
| `wiki-index-render` ([rendering.py](../scripts/wiki_index/rendering.py) + `scripts/wiki_skills/wiki_index_render.py`) renders one `index.md` per vault, preserving `<!-- BEGIN-CUSTOM:name -->…<!-- END-CUSTOM:name -->` blocks via `_CUSTOM_BLOCK_RE`. | PW-H **extends** this: walk `config.auto_indexes[]`, render each output (e.g. `docs/KNOWN_ISSUES.md` grouped by category, sorted by severity), preserving custom blocks. Render-trigger also fires at end of any upsert that creates/deletes a `known-issue` row. |
| `wiki-lint` ([lint.py](../scripts/wiki_index/lint.py)) dispatches `find_orphan_links`/`check_drift`/`find_alias_collisions`/`find_cross_vault_concept_duplicates`. | PW-Q adds `check_auto_generated_unchanged` (re-render to a temp buffer, compare against `.wiki/state.json` sha256) — folded into existing `wiki-lint`, no new CLI. |
| **This repo's** `docs/KNOWN_ISSUES.md` (743 lines) uses a `## [YYYY-MM-DD] <title> [STATUS: open\|fixed\|wontfix]` header format with `- **Symptom / Root cause / Affected components / Fix plan / Prevention**` fields — **NOT** the Universal-skills `Status:`/`Severity:`/timer/do-not-block format the proposal §Phase D sketched. | **PW-G's splitter + acceptance fixture target THIS repo's actual format.** Build `tests/fixtures/known_issues_migration/` from the real file. The richer Universal-skills fields are optional/forward-compat, not the v1 acceptance bar. |
| Deps present: `pyyaml>=6.0`, `python-frontmatter`, `python-slugify>=8.0`, `jsonschema>=4.20`, `types-PyYAML`, `types-jsonschema`. **`regex` (PyPI) NOT present.** mypy `strict=True` (py3.14); `scripts.wiki_ingest.*` `ignore_errors`. pytest.ini `testpaths=tests`, marker `slow`. ~702 tests green at HEAD. | **No new runtime dependency** (D-012-3 ReDoS gate uses stdlib `re`). New code is mypy-strict; tests under `tests/`. |
| `tests/conftest.py` fixtures: `minimal_vault`, `multi_vault` (has `Lessons/Course-A/` course tier), `repo_factory`. Layout-invariant tests assert `PAGE_SUBDIRS`/`HOST_ONLY_SUBDIRS` membership + vendored `wiki_ingest.DEFAULT_SUBDIRS` drift; `test_verify_e2e.py` greps that no `PAGE_SUBDIRS` literal strings leak into skill code. | **All must pass unchanged** (R-X1 acceptance). Bead 0 snapshots `multi_vault`. New fixtures: `tests/fixtures/obsidian-personal-vault/`, `tests/fixtures/dev-project-vault/`, `tests/fixtures/known_issues_migration/`. |

> **Naming note:** the live DDL file is `sql/wiki-index-v2.sql`; the `-v2` is a
> legacy era name and currently encodes `PRAGMA user_version = 5`. This task adds
> **no DDL** — do not bump it.

---

### 2. Requirements Traceability Matrix (RTM)

#### Epic R-X1a — Config-driven layout engine (the universal parser)

| ID | Requirement (PW) | MVP? | Sub-features |
|---|---|---|---|
| **R-X1.A** | **PW-A** — Layout-config schema + loader; built-in `karpathy.yaml`; expand `Layout` enum. | ✅ | (a) `scripts/wiki_index/layout_config.py`: frozen `LayoutConfig` dataclass (`paths[]`, `type_mapping`, `path_type_fallback`, `ref_extraction[]`, `slug_strategy`, `ignore[]`, `file_extensions`, `frontmatter_synthesis`, `auto_indexes[]`) + `load_layout_config(vault_root, root_config)`; (b) `config/layout-config.schema.yaml` (Draft202012; **`additionalProperties:false` at PathEntry level** — stricter than the existing config so a misspelled key is exit-6, not a silent `_unmatched_` flood); (c) built-in `scripts/wiki_index/layouts/karpathy.yaml`; (d) resolution: `root_config["layout"]` → alias map (`flat`/`per-project`→`karpathy`) → `layouts/<name>.yaml` base, deep-merged with optional per-vault override (`WIKI_SCHEMA.md` `layout_config:` or `<vault>/.wiki/layout.yaml`), validated; (e) expand `config/wiki-config.schema.yaml` `$defs/Layout` enum to `[flat,per-project,karpathy,dev-project,obsidian-personal]`; (f) **invariant test** `test_karpathy_config_matches_layout_constants`: karpathy.yaml root-tier globs == `{sub}/**/*.md` ∀ `PAGE_SUBDIRS`; course prefix == `COURSE_TIER_DIR`; `_vault_`==`VAULT_TIER_PROJECT`; `type_mapping`==15-entry `TYPE_MAPPING` (proposal §11's "13 entries" is **stale** — pre-TASK-008; the live count is 15). |
| **R-X1.B** | **PW-B/J/K/M** — config-driven `discover_pages` + `iter_pages` engine. | ✅ | (a) `layout_config.iter_pages(vault_root, config)`: per `paths[]` entry resolve `Path(vault_root).glob(entry.glob)` (native `**`); **first-match-wins**, declared order; (b) **PW-K** `ignore[]` globs evaluated *before* `paths[]` (skip `.obsidian/**`, `.trash/**`, `_templates/**`, `**/*.base`, `**/.DS_Store`, …); (c) **PW-M** `file_extensions` allow-list (default `[.md]`); (d) **PW-J** `project` derivation via `project` literal OR `project_pattern`(regex)+`project_template`(`string.Template` `${name}` only); error policy: regex-compile-fail→exit6, glob-matches-but-pattern-doesn't→WARN+`project:"_unmatched_"`, template-missing-group→exit6; (e) **stable canonical sort by relative POSIX path** before emit (deterministic, ≥ today); (f) rewrite `reindex.py::discover_pages` to delegate (signature `discover_pages(vault_root)` unchanged — loads config internally, cached per-vault); (g) **route `sqlite_repository.find_pages_missing_in_index` (526-549) through `discover_pages`** and compare on `(slug, project)` not bare `f.stem` (architecture-review C1 — fixes the latent slug-only course-tier bug); `check_drift` already delegates. **PW-J/K/M are traced here but are independently RED-testable — the Planner SHOULD give each its own bead** (PW-K ignore-before-paths ordering; PW-M file-extension allow-list; PW-J project_pattern/template + error policy). |
| **R-X1.C/E** | **PW-C/E** — config-driven type inference + `type_mapping`. | ✅ | (a) `normalization.py`: externalise `TYPE_MAPPING` + `_PATH_TYPE_FALLBACK`; `normalize_frontmatter` takes `config`-sourced maps, defaulting to the karpathy built-in for back-compat callers; (b) 15 karpathy entries byte-identical; `UnmappedTypeError` preserved; (c) dev-project `task`→`(brief, tag=task)`, `adr`→`(research, tag=adr)`, etc. (tag-route, no DDL). |
| **R-X1.D** | **PW-D** — config-driven ref extraction + **stdlib-`re` ReDoS load-gate**. | ✅ | (a) `parsing.py::extract_refs(body, config)` iterating `config.ref_extraction[]` (`kind`, `regex`, `target_group`, optional `transform: stem`); keep `extract_wiki_links` as a karpathy-path wrapper (byte-identical); (b) dev-project adds markdown-link + id-ref (`ADR-\d+`,`R-\d+`,`task-\d+…`,`M-\d+`,`P-\d+`,`UC-\d+…`); (c) **D-012-3 load-time budget gate**: at config-load run every pattern against a ~100 KB adversarial payload; reject (exit 6) any over a fixed median budget; built-ins pre-vetted; (d) stdlib `re` only — no `regex` dependency; residual documented. |
| **R-X1.L/N** | **PW-L/N** — slug strategy + `default_tags`/`extra_tags`. | ✅ | (a) `slug_strategy` ∈ `{identity, preserve-unicode, transliterate, ascii-only}`; **`identity`** = `path.stem` verbatim (karpathy); preserve-unicode = `slugify(allow_unicode=True, regex_pattern=r"[^\w\-]")`; transliterate = current strict ASCII; ascii-only = lossy; (b) route page-slug + course-project through the strategy in `derive_slug`; **converge** `wiki_extract_concepts._derive_source_project` onto the same helper; (c) `_slugify_concept` (concept-tag) **untouched**; (d) **PW-N**: per-glob `default_tags`/`extra_tags` merged (dedup, order-preserving) with frontmatter `tags:`; (e) documented APFS-case + NFC/NFD known-limitation tests assert a *surfaced collision warning*, never silent overwrite. |
| **R-X1.F** | **PW-F** — frontmatter synthesis (title fallback chain). | ✅ | (a) `parsing.py::parse_frontmatter`: when no YAML block and `frontmatter_synthesis.enabled`, synthesise `{type: <path-inferred>, title: first_h1 ∥ filename_stem}`; (b) karpathy `enabled:false` → type-less file still raises `UnmappedTypeError` (byte-identical); (c) obsidian-personal `enabled:true` → notes with no frontmatter index. |
| **R-X1.layouts** | Ship `dev-project.yaml` + `obsidian-personal.yaml` built-ins, end-to-end. | ✅ | (a) `layouts/dev-project.yaml` (paths for `docs/tasks`,`docs/adr`,`docs/reviews`,`docs/audit`,`docs/architectures`,`docs/product`,`docs/issues`,`docs/proposals`,top-level `TASK/PLAN/ARCHITECTURE/ROADMAP.md`; tag-route type_mapping; wiki-link+markdown-link+id-ref extraction); (b) `layouts/obsidian-personal.yaml` (numbered folders, `_daily`/`_clippings`/`_inbox` system dirs, MOC glob `extra_tags:[moc]`, `slug_strategy: preserve-unicode`, project_pattern/template); (c) both validate + index their fixtures with correct `project`/`slug`/`tags`, no PK collision, no `.base` leak. |

#### Epic R-X1b — KNOWN_ISSUES bundle (PW-G/H/Q) + ADR amendment (= R-X3)

| ID | Requirement (PW) | MVP? | Sub-features |
|---|---|---|---|
| **R-X1.ADR** | ADR-002 §D8 amendment (Class-B "rebuildable markdown" sub-case). | ✅ | (a) amend `docs/adr/ADR-002-*.md` §D8 (or open `docs/adr/ADR-003-*.md`) to register a new Class-B sub-case: *auto-rendered markdown that is rebuildable from Class-A per-issue files* (today's Class B is the SQLite cache only); (b) define the rebuildability invariant for the ledger (byte-identical modulo a GENERATED-AT header); (c) **land before PW-H ships** (gating). |
| **R-X1.H** | **PW-H** — `auto_indexes[]` render engine. | ✅ | (a) `rendering.py` + `wiki_index_render` walk `config.auto_indexes[]`; render each `output` (e.g. `docs/KNOWN_ISSUES.md`) `group_by` + `sort_within_group` from a template; (b) preserve `BEGIN-CUSTOM` blocks; (c) emit `<!-- GENERATED-AT: <iso8601> by wiki-index-render --auto-indexes -->` header + store rendered-body sha256 in `<vault>/.wiki/state.json`; (d) **render-trigger contract**: also fire at end of any `wiki-index-upsert` batch that creates OR deletes a page **whose tag-route type is `known-issue`** (i.e. `db_type=research` + tag `known-issue` — the trigger predicate keys off the tag/frontmatter `type:` marker, **NOT** a `pages.type` column value, since `known-issue` has no distinct enum value — zero-DDL), plus on every `wiki-reindex --full/--delta`; (e) `--auto-indexes` CLI flag. |
| **R-X1.Q** | **PW-Q** — auto-generated lint guard. | ✅ | (a) `lint.py::check_auto_generated_unchanged`: for each `auto_indexes[].output`, re-render to a temp buffer at lint time and compare against the `.wiki/state.json` sha256; (b) mismatch → lint issue with remediation hint ("manual edit detected at `<path>`; run `wiki-index-render --auto-indexes`, or move your edit into the per-issue file"); (c) folded into `wiki-lint` (no new CLI); `--strict` advisory exit. |
| **R-X1.G** | **PW-G** — KNOWN_ISSUES splitter (one-shot) + partial-confidence report. | ✅ | (a) `scripts/migrate_known_issues_to_files.py` parses THIS repo's `## [YYYY-MM-DD] <title> [STATUS]` + field shape into `docs/issues/<id>-<slug>.md` per-issue frontmatter (`id`, `type: known-issue`, `status`, `opened_at`, `category`, `severity` where present, `affected_components`, `related_*`); (b) preserve full body verbatim; (c) emit `docs/issues/.migration-report.md` listing every issue the splitter wasn't fully confident about (ambiguous status/severity, malformed fields) — **flag, never silently drop**; (d) fixture `tests/fixtures/known_issues_migration/` is the acceptance bar: round-trip parity = "split→render == original modulo whitespace + GENERATED-AT". |
| **R-X3.dogfood** | Dogfood the migration on this repo. | ✅ | (a) run the splitter → `docs/issues/*.md` (Class A); (b) `wiki-index-render --auto-indexes` regenerates `docs/KNOWN_ISSUES.md` (now Class B); (c) operator reviews `.migration-report.md`, fixes flagged issues, re-renders; (d) `wiki-search "hash drift"` returns one specific issue, not the whole ledger; (e) delete + re-render is byte-identical (modulo GENERATED-AT). |

#### Epic R-X2 — Bootstrap (Phases A-B; Phase C deferred)

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **R-X2.1** | **wiki-init `--layout` flag** (single CLI surface, §10). | ✅ | (a) `wiki_init.py` `--layout` choices → `[flat,per-project,karpathy,dev-project,obsidian-personal]` (default `per-project`, back-compat); (b) write the chosen `layout:` into `WIKI_SCHEMA.md` (template passthrough); (c) register the vault; (d) idempotent; doesn't touch existing project files. |
| **R-X2.2** | **Phase A** — bootstrap obsidian-llm-wiki itself as the first dev-vault. | ✅ | (a) `wiki-init --layout dev-project --vault . --vault-id obsidian-llm-wiki` writes `docs/WIKI_SCHEMA.md` (or repo-root, per layout resolution); (b) `wiki-reindex --full`; (c) `wiki-search "ADR-002" --vaults obsidian-llm-wiki` returns ranked hits with snippets. |
| **R-X2.3** | **Phase B** — bootstrap one peer dev-vault + cross-project search. | ✅ | (a) bootstrap a peer repo (e.g. `Universal-skills` or `trade-agents`) as a dev-vault; (b) `wiki-search "M-4" --vaults all` returns hits spanning both vaults. |
| **R-X2.roadmap** | ROADMAP update + deferral record. | ✅ | (a) mark R-X1 + R-X2(A-B) + R-X3 DONE in `docs/ROADMAP.md`; (b) **split R-X2 Phase C (archive_protocol.py hook) out as a distinct deferred follow-up entry** with the §12 Option C sketch reference, so it isn't forgotten (D-012-4). |

---

### 3. Use Cases

#### 3.1 UC-29 — Re-index a Karpathy vault, byte-identically (the §D8 acceptance)
- **Actors:** operator / sub-agent; the indexer.
- **Preconditions:** an existing Karpathy vault (`multi_vault` fixture or `trade-agents`), `layout: per-project`.
- **Main scenario:** (1) `wiki-reindex --full`; (2) the config-driven engine resolves `flat`/`per-project`→`karpathy.yaml`; (3) walks both tiers via `iter_pages`; (4) emits pages; (5) rows written.
- **Postcondition:** every `(slug, project, type, tags, file_path)` row is **identical** to the pre-refactor engine (modulo `last_modified`); all current tests pass unchanged.
- **Acceptance:** ✅ Bead-0 golden snapshot green at every bead. ✅ `test_karpathy_config_matches_layout_constants` green. ✅ `pytest` fully green; `mypy --strict` clean.

#### 3.2 UC-30 — Index a real personal Obsidian vault (numbered folders, Cyrillic, system dirs)
- **Actors:** operator; the indexer.
- **Preconditions:** `tests/fixtures/obsidian-personal-vault/` with a Cyrillic note (`Квартиры.md`), 3 same-named files under different `<area>/<sub>/`, an `_inbox/` draft, an `.obsidian/` dir, an ignored `.base`.
- **Main scenario:** (1) reindex under `layout: obsidian-personal`; (2) `ignore[]` skips `.obsidian/` + `.base`; (3) `project_pattern`/`template` derives `Personal Home/Household` etc.; (4) `slug_strategy: preserve-unicode` keeps `Квартиры`; (5) `frontmatter_synthesis` fills `title` from H1∥stem; (6) `default_tags` injected.
- **Alternative:** **A1 (cross-platform / case-or-NFC collision)** → engine surfaces a collision **warning** (lint/report), never silently overwrites a PK row.
- **Postcondition:** all expected pages indexed with correct `project` values; **no PK collision**; no `.base` row leaked.
- **Acceptance:** ✅ 3 same-named files → 3 distinct `project`s. ✅ Cyrillic slug preserved. ✅ `.base`/`.obsidian` excluded. ✅ collision case warns.

#### 3.3 UC-31 — Index a dev-project's `docs/` and search it
- **Actors:** operator / sub-agent.
- **Preconditions:** a repo with `docs/` (TASKs, ADRs, proposals), `layout: dev-project`.
- **Main scenario:** (1) `wiki-init --layout dev-project …`; (2) `wiki-reindex --full`; (3) `paths[]` map `docs/adr/*.md`→`adr`(tag), etc.; (4) `ref_extraction[]` picks up `ADR-NNN`/`R-NN`/markdown-links; (5) `wiki-search "ADR-002" --types adr` returns the ADR.
- **Postcondition:** dev docs are FTS-searchable, type-tagged, cross-referenced.
- **Acceptance:** ✅ `wiki-search "ADR-002" --vaults obsidian-llm-wiki` returns ranked hits + snippets. ✅ `--vaults all` spans the peer vault (UC-33).

#### 3.4 UC-32 — Migrate KNOWN_ISSUES to per-file + auto-rendered ledger (dogfood)
- **Actors:** operator + agent.
- **Preconditions:** this repo's `docs/KNOWN_ISSUES.md` (743 lines); ADR amendment landed (R-X1.ADR).
- **Main scenario:** (1) `python scripts/migrate_known_issues_to_files.py` → `docs/issues/<id>-<slug>.md` + `.migration-report.md`; (2) operator reviews flagged issues, fixes; (3) `wiki-index-render --auto-indexes` regenerates `docs/KNOWN_ISSUES.md` (Class B, GENERATED-AT header); (4) operator commits.
- **Alternative:** **A1 (low-confidence parse)** → issue listed in `.migration-report.md`, surfaced for manual review, **not dropped**.
- **Postcondition:** `docs/issues/*.md` Class A; `docs/KNOWN_ISSUES.md` Class B rebuildable; manual edits to the ledger are lint-flagged (PW-Q).
- **Acceptance:** ✅ round-trip byte-identical (modulo GENERATED-AT). ✅ `wiki-search "hash drift"` returns one issue. ✅ `wiki-lint` flags a hand-edit of the generated ledger.

#### 3.5 UC-33 — Cross-project search across vaults
- **Actors:** operator / sub-agent.
- **Preconditions:** this repo + one peer bootstrapped as dev-vaults.
- **Main scenario:** `wiki-search "M-4" --vaults all` → ranked hits from both, each with vault_id + snippet.
- **Acceptance:** ✅ hits span ≥2 vaults; private-vault exclusion default honored (proposal §7.3 — out-of-scope to *build* here, but the default must not regress).

#### 3.6 UC-34 — Operator-supplied custom layout config (ReDoS + schema guard)
- **Actors:** advanced operator.
- **Preconditions:** a `<vault>/.wiki/layout.yaml` override.
- **Main scenario:** (1) load resolves base + override; (2) schema validates (`additionalProperties:false` at PathEntry); (3) the ReDoS budget gate runs each regex against the adversarial payload.
- **Alternative:** **A1 (pathological regex)** → config-load **exit 6** with a clear message, before any file is processed. **A2 (misspelled key)** → schema validation exit 6. **A3 (project_template references missing group)** → exit 6.
- **Acceptance:** ✅ pathological pattern rejected at load. ✅ built-in layouts pass. ✅ misspelled key rejected.

---

### 4. Non-functional Requirements

- **NFR-1 (byte-identity / §D8 rebuildability).** A Karpathy re-index produces rows identical to the pre-refactor engine modulo `last_modified`. Enforced by the Bead-0 golden snapshot kept green throughout + the karpathy-config-matches-constants invariant.
- **NFR-2 (no behavioural regression).** All ~702 existing tests pass **unchanged**; `mypy --strict scripts/` clean; the vendored `wiki_ingest.DEFAULT_SUBDIRS` drift guard + the `test_verify_e2e.py` "no literal PAGE_SUBDIRS string in skills" guard still hold.
- **NFR-3 (no new runtime dependency).** stdlib `re` for ReDoS; reuse `pyyaml`/`jsonschema`/`python-slugify`/`python-frontmatter` already present (protects the self-contained-publication goal).
- **NFR-4 (security: config is a new attack surface).** JSON-Schema validation (strict at PathEntry), ReDoS load-time budget gate, PW-J error policy (compile-fail/template-mismatch → exit 6). Egress sanitiser + `O_NOFOLLOW`/`validate_inside_vault` reused for any file the renderer/splitter writes.
- **NFR-5 (determinism).** `iter_pages` output stably sorted by relative POSIX path — independent of filesystem glob order.
- **NFR-6 (no silent data loss).** PW-G flags low-confidence parses in `.migration-report.md`; PW-J reports `_unmatched_`; malformed `verifies:`/`cites:` already skip-and-report.
- **NFR-7 (zero DDL).** `user_version` stays 5; new doc types via the TYPE_MAPPING tag-route.

---

### 5. Constraints and Assumptions

- **C-1.** `layout.py` constants are the source of truth; `karpathy.yaml` is a *validated projection*, not a replacement. Constants are not deleted.
- **C-2.** Three slug surfaces stay distinct (page=`identity`, course=loose slugify, concept-tag=`_slugify_concept` untouched).
- **C-3.** The new layout-grammar layer is **parallel** to the existing per-vault config (D-012-2). The existing `config_loader.py`/`wiki-config.schema.yaml` change only by the `Layout` enum expansion.
- **C-4.** The three non-delegating slug/project-producing walks (`find_pages_missing_in_index`, `derive_slug`, `_derive_source_project`) must converge on `discover_pages`/`iter_pages` and compare on `(slug, project)`, not bare `f.stem`, or the drift/orphan surface and the reindex surface disagree (PK-drift). `check_drift` already delegates. (architecture-review C1.)
- **C-5 (assumption).** No test asserts row insertion order (verified during planning); the new stable sort is strictly more deterministic and cannot break an existing assertion. *Pinned by a new `test_discover_pages_is_path_sorted`.*
- **C-6.** R-X2 Phase C (peer-repo archive hook) is **out of scope** (D-012-4); recorded as a deferred ROADMAP entry.
- **C-7.** PW-H requires the ADR amendment (R-X1.ADR) landed first.
- **C-8.** Per-vault override path is both `WIKI_SCHEMA.md` frontmatter `layout_config:` (explicit, precedence) and `<vault>/.wiki/layout.yaml` (conventional).
- **C-9 (assumption).** The peer dev-vault for UC-33 is `Universal-skills` unless the operator prefers `trade-agents`; either satisfies the cross-project acceptance.

---

### 6. Open Questions

- **Q-012-a (resolved → D-012-2).** Config home? → New parallel layer.
- **Q-012-b (resolved → D-012-3).** ReDoS guard? → stdlib `re` + load-time gate.
- **Q-012-c (resolved → D-012-1).** PW-G/H/Q scope? → include now + dogfood.
- **Q-012-d (resolved → D-012-4).** Archive hook? → defer + record in ROADMAP.
- **Q-012-e (Architecture to pin).** `auto_indexes[]` template mechanism: a `string.Template`/Jinja-free renderer in Python vs an external `assets/known-issues-ledger.md.tmpl` (proposal §11 implies a template file). Recommendation: a small Python renderer driven by `group_by`/`sort_within_group` config + an optional template asset — keep it dependency-free.
- **Q-012-f (Architecture to pin).** Per-vault override **merge policy** for `paths[]`/`ref_extraction[]` (replace vs append). Recommendation: **replace** if the operator provides the key (predictable), scalars overlay; pin in schema-validation tests.
- **Q-012-g (operator, low-stakes).** Peer dev-vault for UC-33: `Universal-skills` (default) or `trade-agents`?

---

#### Decision Log (analysis-time, operator-confirmed 2026-06-01)

- **D-012-1** PW-G/H/Q INCLUDE NOW (+ dogfood; ADR amendment gates PW-H).
- **D-012-2** Two separate config systems (new parallel `layout_config` layer).
- **D-012-3** ReDoS = stdlib `re` + load-time budget gate (no `regex` dep).
- **D-012-4** R-X2 Phase C archive hook DEFERRED; recorded in ROADMAP.
