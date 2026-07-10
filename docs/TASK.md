# TASK 056 — Modularize the SQLite DAL: split `sqlite_repository.py` into a domain-package (Postgres-ready shape)

## 0. Meta Information
- **Task ID**: 056
- **Slug**: sqlite-repository-module-split
- **Roadmap**: P3 "Operational polish → Postgres backend" enabler (`docs/ROADMAP.md` §P3: *"Postgres
  backend — `IndexRepository` ABC was designed for this"*); `docs/SQLITE-VS-POSTGRES.md` §4 (DAL
  pattern, two executors over one interface).
- **Type**: Structural refactor (behaviour-preserving; zero-DDL; zero feature change)
- **Effort**: M (mechanical method moves + one targeted method decomposition + docs; the test
  suite is the primary gate)
- **Context**: `scripts/wiki_index/sqlite_repository.py` has grown to **2227 lines / ~75 methods
  in one class** accreted over TASKs 001→054. Ten unrelated domains (vault registry, pages,
  refs/graph, FTS search, health/lint, log events, batch runs, entities/aliases, workflow state,
  entity merge) live in one file; `search_pages` alone is ~310 lines. Every new feature (R-15
  health rules, R-19 ontology, R-16/17 policy filters) lands in the same file → review diffs are
  noisy, merge conflicts likely, navigation costly. The file must be split into cohesive modules
  **without changing behaviour or public surface**, and the resulting shape must be the template
  a future `PostgresRepository` package can mirror.
- **Architecture**: module-level restructuring only. Class A/B/C layering, Decision-17,
  `user_version 7`, factory-as-sole-entry (`make_repo`), and the `IndexRepository` ABC contract
  are all untouched. See ARCHITECTURE.md §2.x update (this task).

## 1. Problem / Motivation (verified against source)

1. **Single 2227-line module.** `wc -l` confirms `sqlite_repository.py` is the largest file in
   the tree (next: `layout_config.py` 1339). One class, ~75 public/private methods.
2. **Ten near-disjoint domains in one class.** Method inventory clusters cleanly by table family:
   vaults (l.150–243), pages (244–368), refs+graph (369–598), search (599–919), health/lint
   (920–1494), log events (1495–1567), batch runs (1568–1608), entities+aliases (1609–1859),
   query/verify/source state + citations (1860–2041), alias collisions + merge (2042–2227).
   **Cross-cluster helper inventory** (traced; the complete list — these four are the only
   couplings besides `self._connect()`):
   - `search_pages` (search) → `_row_to_page` (pages, private static, L901)
   - `merge_entities` (merge) → `_recompute_mentions` (entities, private, L2203)
   - `query_log_events` (events) → `_in_clause` (search cluster today, stateless, L1546)
   - `check_drift` (health) → `get_vault` (vaults, **public — declared on the ABC**, L1344)
3. **`search_pages` is a ~310-line monolith** (FTS5 MATCH + alias expansion + metadata filters +
   `--as-of` graph CTE + membership narrowing in one body).
4. **Postgres is a declared future** (ROADMAP P3; SQLITE-VS-POSTGRES.md §4.3 sketches
   `PostgresRepository`). Today there is no per-domain seam a second backend could mirror, and
   no map of which SQL is dialect-portable vs SQLite-only (FTS5, `json_extract`, PRAGMAs).
5. **Import surface is load-bearing**: `scripts.wiki_index.sqlite_repository` is imported from
   11 import sites across 8 script files and ≈105 sites across 95 test files
   (`SQLiteRepository`, `AliasCollisionError`, `VaultRegistrationError`). Any path break is a
   mass-churn hazard.
6. **One non-import consumer coupling** (found by the plan-gate consumer audit): the M-4 grep
   guard `tests/test_pages_upsert.py::test_unit_01_no_insert_or_replace_in_source`
   (L136–137) reads `scripts/wiki_index/sqlite_repository.py` **from disk by literal path**, not
   via import — the frozen import surface does not cover it, and it would FileNotFoundError
   after the package conversion. Handled by the sanctioned 056-00 prep commit (see R1/R5
   carve-out): the guard is generalized to scan the module *or* every `sqlite_repository/*.py`,
   which also extends M-4 coverage to all future mixin modules.

## Requirements Traceability Matrix

| ID | Requirement | Acceptance criteria | Location |
|----|-------------|---------------------|----------|
| R1 | **Package conversion, import-surface frozen.** Replace the module `sqlite_repository.py` with a package `sqlite_repository/` whose `__init__.py` re-exports the identical public surface: `SQLiteRepository`, `AliasCollisionError`, `VaultRegistrationError` (plus the module-private names tests may touch, e.g. `_SCHEMA_PATH`, re-exported defensively). Sub-features: (a) `__init__.py` assembly, (b) `__all__` declared, (c) grep-verified zero edits in `scripts/wiki_skills/*`, `scripts/wiki_index/{factory,lint,reindex,rendering}.py`, `scripts/benchmark.py`. | `from scripts.wiki_index.sqlite_repository import SQLiteRepository, AliasCollisionError, VaultRegistrationError` works byte-identically; **no importer file outside the new package is edited**; full pytest suite passes with zero test-file changes **in the refactor diff** (sole sanctioned test change = the 056-00 M-4 guard prep commit, landed BEFORE the package conversion — Problem §6). | `scripts/wiki_index/sqlite_repository/__init__.py` |
| R2 | **Connection/base module.** Extract connection lifecycle into `_base.py`: `db_path`, lazy `_connect()` + PRAGMA block, `close()`, `__enter__/__exit__`, `apply_schema()`, `_SCHEMA_PATH`, the genuinely cross-domain stateless helper `_in_clause` (used by search L644/648 **and** `query_log_events` L1546), and the two exception classes. Sub-features: (a) `SQLiteRepositoryBase(IndexRepository)` — an **abstract** base (inherits the ABC so public cross-mixin calls like `check_drift → get_vault` type-check; never instantiated directly) owning `db_path`/`_conn`/lifecycle, (b) PRAGMA block moved verbatim (WAL/synchronous/foreign_keys/temp_store/mmap), (c) exceptions defined here, re-exported at package root. | PRAGMA sequence byte-identical (guarded by existing perf/WAL tests); `close()` idempotence preserved; exceptions importable from the old path. | `scripts/wiki_index/sqlite_repository/_base.py` |
| R3 | **Domain mixin modules (one per table-family).** Move method clusters verbatim into cohesive mixin modules, each inheriting `SQLiteRepositoryBase`: `_vaults.py` (register/get/list/rename/by-root-path + `_row_to_vault`), `_pages.py` (upsert/get/delete + txn helpers + `_row_to_page`), `_refs_graph.py` (upsert/replace refs, backlinks, concept_pages, mentioning_source_pages, refs_from, neighbors, edge_chain), `_search.py` (search_pages + helpers), `_health_rules.py` (config-driven R-15/R-19 rule analyses: find_lifecycle_drift / find_coverage_gaps / find_ontology_violations — ≈250 body lines), `_health_scan.py` (structural integrity scans: find_orphan_links / classification_leaks / invalid_classifications / verified_slugs / pages_missing_in_index / check_drift + `_is_intentional_mapping` + `_extract_frontmatter_type` / cross_vault_duplicates — ≈330 body lines), `_events.py` (log events + batch runs), `_entities.py` (entity CRUD, candidates, mentions, aliases, expand_query_aliases), `_merge.py` (find_alias_collisions, merge_entities, get_entity_file_path, find_entity_by_name), `_state.py` (query/verify/source state, find_pages_citing_source, all_cited_sources). `SQLiteRepository` becomes `class SQLiteRepository(<mixins>, IndexRepository)` with an empty-ish body. **Cross-cluster private calls resolve via two declared mechanisms** (per the Problem §2 inventory — no other cross-mixin calls exist): the stateless `_in_clause` hoists to `_base.py` (R2); the two domain-owned private helpers stay home and the caller declares an explicit mixin-dependency edge — `class _SearchMixin(_PagesMixin)` (for `_row_to_page`) and `class _MergeMixin(_EntitiesMixin)` (for `_recompute_mentions`) — visible in the class statement, MRO-linearized, mypy-strict-clean. Sub-features: (a) method bodies moved **verbatim** (no logic edits beyond imports), (b) no NEW cross-mixin calls introduced beyond the two declared dependency edges; **base-tuple ordering constraint**: in the composite `SQLiteRepository` base tuple a mixin carrying a dependency edge MUST precede its dependency (dependent-before-dependency) for C3 linearization — equivalently (preferred), **omit the super-mixin from the tuple entirely** since `_SearchMixin`/`_MergeMixin` bring `_PagesMixin`/`_EntitiesMixin` transitively, (c) every module ≤ 500 lines. | The full pytest suite (95 files importing the class) passes unchanged; `python -c "import scripts.wiki_index.sqlite_repository"` round-trips; per-module `wc -l` ≤ 500. | `scripts/wiki_index/sqlite_repository/_*.py` |
| R4 | **`search_pages` decomposition.** Inside `_search.py`, split the ~311-line method into private, individually-testable helpers (e.g. filter-clause builder, alias/FTS MATCH assembly, `--as-of` CTE builder, row→`PageHit` mapping) with the public method as the orchestrating body. Decomposition **adds** lines (signatures/docstrings): the ≤500 cap is measured **post-decomposition** (starting body is 310 lines — `search_pages` alone; `_in_clause` departs to `_base.py` per R2 → est. ≤430 after; if it still overflows, a named carve-out split such as `_search_asof.py` is the sanctioned remedy, never cap-waiving). Sub-features: (a) SQL produced for every existing test scenario is behaviour-identical, (b) helpers are module-private (`_`-prefixed), (c) no new public surface. | All `test_search_pages*.py`, `test_wiki_search_*.py`, `test_graph_rag.py`, as-of/membership/metadata-filter suites pass unchanged. | `scripts/wiki_index/sqlite_repository/_search.py` |
| R5 | **Type-safety + regression gate.** The refactor is complete only when: (a) `mypy --strict scripts/` is clean, no `type: ignore` added — **typing approach pinned**: `SQLiteRepositoryBase` inherits `IndexRepository` (public cross-mixin calls resolve against the ABC), shared private helpers live on the base (R2), domain-private cross-calls resolve via the two declared mixin-dependency edges (R3); (b) the **full** `pytest tests/` suite is green with **zero test-file edits in the refactor diff** (the one sanctioned prep-commit exception: 056-00 generalizes the path-coupled M-4 grep guard, Problem §6, and lands as its own commit before any refactor bead), (c) `wiki-reindex --full` rebuildability smoke (existing e2e tests) stays green. | CI-equivalent local run: `mypy --strict scripts/` exit 0; `pytest tests/` exit 0; refactor-diff shows no `tests/**` changes (post-056-00 baseline). | repo-wide |
| R6 | **Postgres-readiness map (docs, no code).** Document the backend-mirroring convention: a future `postgres_repository/` package mirrors the same per-domain module layout over `psycopg`; annotate each module with its dialect exposure (generic SQL vs SQLite-only: FTS5 MATCH/bm25/snippet, `json_extract`/`json_each`, PRAGMA block, `user_version`) in module docstrings + one consolidated table in SQLITE-VS-POSTGRES.md §4 and ARCHITECTURE.md. Sub-features: (a) per-module docstring dialect note (`dialect:` tag), (b) SQLITE-VS-POSTGRES.md §4 updated to the *actual* package layout — its illustrative `sqlite_repo.py`/`postgres_repo.py` filenames reconciled to the real `sqlite_repository/` package + future `postgres_repository/` mirror, (c) explicit non-goal statement — no `PostgresRepository` code in this task. | Docs updated; grep for `dialect:` docstring tag hits every domain module. | `docs/SQLITE-VS-POSTGRES.md`, `docs/ARCHITECTURE.md`, module docstrings |
| R7 | **Docs/ledger sync.** Update `scripts/wiki_index/.AGENTS.md` (single-writer: Developer) to the new package inventory; ARCHITECTURE.md DAL section reflects the package + mixin composition and the Q-0XX rationale entry (mixin-over-composition decision); README repo-layout touch if it names the file. | `.AGENTS.md` lists every new module with one-line purpose; ARCHITECTURE.md section merged; no stale reference to a monolithic `sqlite_repository.py` remains in living docs (`grep -rn "sqlite_repository.py" docs/ARCHITECTURE.md README.md` → 0 stale hits). | `scripts/wiki_index/.AGENTS.md`, `docs/ARCHITECTURE.md`, `README.md` |

## 3. Use Cases

### UC-1 (primary): developer lands a new health rule
**Today**: edits a 2227-line file, scrolls past search/entities/merge, diff reviewed against
unrelated domains. **After**: edits `_health_rules.py` (~290 lines with headers), diff scoped to
the declared-rules health domain; `__init__.py` untouched.

### UC-2: future Postgres backend (out of scope to implement)
A contributor creates `scripts/wiki_index/postgres_repository/` mirroring the domain modules,
implements them over `psycopg` per the dialect map (R6), adds a `backend:` branch in
`factory.make_repo`. Nothing in skills/CLIs changes — they already speak `IndexRepository` only.

### UC-3: consumer code (skills/CLIs/tests) — must be a no-op
`wiki_alias.py` keeps `from scripts.wiki_index.sqlite_repository import AliasCollisionError`;
all ≈107 test-site imports across 95 files keep working. Alternative scenario (import breaks) =
R1 acceptance failure.

## 4. Acceptance Criteria (task-level, pass/fail)
1. `pytest tests/` — green, **zero test-file modifications in the refactor diff** (`git diff
   --stat tests/` empty measured against the post-056-00 baseline; the 056-00 M-4 guard
   generalization is the single sanctioned prep-commit test edit, Problem §6).
2. `mypy --strict scripts/` — exit 0, no new `type: ignore`.
3. Public import surface: the three load-bearing names importable from the unchanged path.
4. No module in the new package exceeds 500 lines (`wc -l` check).
5. Behaviour freeze: no SQL string intentionally altered except mechanical relocation; `search_pages`
   decomposition covered by the existing search/as-of/membership suites.
6. Docs synced per R6/R7.

## 5. Non-goals / constraints
- **No `PostgresRepository` implementation** — readiness shape + docs only (YAGNI; ROADMAP trigger
  is corpus >100K or multi-writer).
- **No `IndexRepository` ABC split** — the 779-line contract file stays one module (it *is* the
  single interface both backends share; splitting it would churn every importer for no cohesion
  gain). Revisit only if a Postgres task needs interface segregation.
- **No ORM** (SQLITE-VS-POSTGRES.md §8 anti-pattern: raw SQL + N repository packages).
- **Zero-DDL / `user_version 7`**; no PRAGMA changes; no perf-path changes (P-030 residuals stay as-is).
- **No behavior/feature changes** — deferred perf issues (P-9, P-11, R-X3-MF-SCAN) are explicitly NOT
  fixed in passing; they move verbatim.
- `factory.py` unchanged (still the sole public entry; still SQLite-only branch).

## 6. Implementation deltas (as-built, 2026-07-10)

The relocation shipped verbatim except these sanctioned deltas (each forced by the move itself
or by a gate; AST audit vs HEAD confirms 72/75 method bodies byte-identical, only the three
below changed):

1. **`_SCHEMA_PATH` depth** — `+1 .parent` (module → package adds one path level; caught by the
   056-01 gate: 519 test failures until fixed).
2. **`_extract_frontmatter_type`** — class self-reference `SQLiteRepository._FM_TYPE_RE` →
   `_HealthScanMixin._FM_TYPE_RE` (the attribute's new owner).
3. **`__enter__` → `-> Self`** (was `-> "SQLiteRepository"`; base can't name the composite;
   `Self` preserves the concrete type for subclass users).
4. **`__all__` landed at 056-02**, not 056-07a — mypy `--strict` `no-implicit-reexport` makes the
   package-root re-exports invisible without it (gate would go red mid-plan otherwise).
5. **`_PagesMixin` class docstring reworded** — the original phrase contained the literal M-4
   banned string, and the generalized guard (rightly) flagged it; the ban rationale moved into a
   `#`-comment (guard-exempt by design).
6. **`_stub` deleted** (zero call sites — the 056-02 conditional resolved to "not referenced").
7. **Post-adversarial slop sweep** — dead imports the split stranded (`json` ×2, `sqlite3`,
   `DriftHit`, `Page`) removed from `_health_rules`/`_health_scan`/`_merge`/`_refs_graph`
   (found by critic-logic; confirmed by AST sweep; mypy does not flag unused imports).

Out-of-scope observation (adversarial docs-critic, MINOR): the working tree carries an
**unrelated** modification to `templates/vault.claude-settings.json` (adds `sleep`/`ps`/
`ffprobe`/`mw` to the vault Bash allowlist — belongs to the separate video-folder-inference
work). It is NOT part of TASK 056: exclude it from the 056 commit / commit it separately.

## 7. Open Questions
- none blocking. Decision "mixin composition over delegating facade" is recorded as the Q-0XX
  rationale entry in `docs/architectures/open-questions.md` (R7): the ABC already forces a single
  concrete class surface; a delegating facade would add ~75 hand-written forwarding methods
  (churn + drift risk) for no cohesion gain, while mixins move bodies verbatim onto an
  MRO-linearized hierarchy rooted at `SQLiteRepositoryBase(IndexRepository)`, with exactly two
  declared mixin-dependency edges (`_SearchMixin(_PagesMixin)`, `_MergeMixin(_EntitiesMixin)`)
  covering the real cross-domain private calls. C3-linearization is guaranteed by the R3
  base-tuple rule: the super-mixins `_PagesMixin`/`_EntitiesMixin` are omitted from the composite
  tuple (inherited transitively via their dependents).
