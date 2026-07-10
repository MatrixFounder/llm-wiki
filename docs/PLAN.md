# PLAN — TASK 056: SQLite DAL modularization (`sqlite_repository.py` → domain-package)

Stub-First here means **the suite is green after every bead**: bead 1 converts the module to a
package *verbatim* (structure first, zero logic movement — the mechanical proof that the import
surface froze), then each bead peels one domain cluster into its mixin module and re-runs the
full gates. No bead leaves the tree in a state where `pytest tests/` or `mypy --strict scripts/`
is red. Every RTM ID from `docs/TASK.md` maps to bead(s) below. **Zero test-file edits across
the refactor beads (056-01+)** — the single sanctioned test change is the 056-00 prep commit
(TASK Problem §6); any later bead that "needs" a test change is a defect in that bead.

## Per-bead gate (applies to every bead)

`pytest tests/` green + `mypy --strict scripts/` clean + `git diff --stat tests/` empty
(against the post-056-00 baseline). On failure: fix within the bead; never carry red forward.

## Beads (atomic, ordered)

- [ ] **[R1]** 056-00 — PREP commit (the only test edit; lands BEFORE the refactor).
  - Generalize the M-4 grep guard `tests/test_pages_upsert.py::
    test_unit_01_no_insert_or_replace_in_source` (today it reads
    `scripts/wiki_index/sqlite_repository.py` from disk by literal path — FileNotFoundError once
    the module becomes a package): `base = Path(__file__).parent.parent / "scripts" /
    "wiki_index" / "sqlite_repository"`; scan `[base.with_suffix(".py")]` if it exists else
    `sorted(base.glob("*.py"))`; report offenders as `<file>:L<n>`.
  - Guard holds for BOTH layouts (green before and after 056-01) and extends M-4 coverage to
    every future mixin module. Own commit → the refactor diff stays test-clean.

- [ ] **[R1]** 056-01 — package conversion, byte-verbatim.
  - `git mv scripts/wiki_index/sqlite_repository.py scripts/wiki_index/sqlite_repository/__init__.py`
    (content untouched; history preserved via rename detection).
  - Verify: per-bead gate + `python -c "from scripts.wiki_index.sqlite_repository import
    SQLiteRepository, AliasCollisionError, VaultRegistrationError"` + grep-verify zero edits in
    the 8 importer script files.
  - This bead alone proves R1's frozen-surface claim before any splitting risk is taken.

- [ ] **[R2]** 056-02 — extract `_base.py`.
  - Move to `_base.py`: `VaultRegistrationError`, `AliasCollisionError`, `_SCHEMA_PATH`
    (`_stub` is NOT moved — zero call sites verified; it is deleted at 056-07a), and a new
    `class SQLiteRepositoryBase(IndexRepository)` carrying
    `__init__(db_path)`, `_connect()` + PRAGMA block (verbatim), `close()`,
    `__enter__`/`__exit__`, `apply_schema()`, and the hoisted `@staticmethod _in_clause`.
  - `__init__.py`: `SQLiteRepository` now inherits `SQLiteRepositoryBase`; the moved members are
    deleted from it; exceptions **and `_SCHEMA_PATH` (defensive, per TASK R1)** re-exported from
    `_base` (import path unchanged for consumers).
  - `search_pages`/`query_log_events` call sites of `_in_clause` need **no edit** (`self.`-resolution).

- [ ] **[R3]** 056-03 — peel leaf domains: `_vaults.py`, `_events.py`, `_state.py`.
  - `_VaultsMixin` (register/get/list/rename/get_by_root_path + `_row_to_vault`);
    `_EventsMixin` (append/update-offset/query log events + `_row_to_log_event`, begin/finish/last
    batch runs); `_StateMixin` (check/record query state, check/record verify state, get/set
    source state, `find_pages_citing_source`, `all_cited_sources`).
  - Bodies verbatim; `SQLiteRepository` base tuple gains the three mixins.

- [ ] **[R3]** 056-04 — peel `_pages.py` + `_refs_graph.py`.
  - `_PagesMixin` (`_upsert_page_in_txn`, upsert/get/delete page, `_row_to_page`);
    `_RefsGraphMixin` (upsert_refs, `_replace_refs_in_txn`, replace_refs, `_ref_from_row`,
    get_backlinks, concept_pages, mentioning_source_pages, refs_from, neighbors, edge_chain).

- [ ] **[R3]** 056-05 — peel `_entities.py` + `_merge.py` (first dependency edge).
  - `_EntitiesMixin` (upsert/resolve entity, `_row_to_entity`, candidates, `_recompute_mentions`
    + recompute/auto-promote/preview, add/remove/list aliases, expand_query_aliases);
    `_MergeMixin(_EntitiesMixin)` (find_alias_collisions, merge_entities, get_entity_file_path,
    find_entity_by_name).
  - Composite tuple rule: `_MergeMixin` joins the tuple; `_EntitiesMixin` is **omitted**
    (transitive) — C3 check via import + mypy.

- [ ] **[R3]** 056-06 — peel `_health_rules.py` + `_health_scan.py`.
  - `_HealthRulesMixin` (find_lifecycle_drift, find_coverage_gaps, find_ontology_violations);
    `_HealthScanMixin` (find_orphan_links, find_classification_leaks,
    find_invalid_classifications, find_verified_slugs, find_pages_missing_in_index, check_drift,
    `_is_intentional_mapping`, `_extract_frontmatter_type`, find_cross_vault_concept_duplicates).
  - `check_drift → self.get_vault` resolves via the ABC on the base — no edit.

- [ ] **[R3]** 056-07a — peel `_search.py` verbatim (second dependency edge).
  - `_SearchMixin(_PagesMixin)` with `search_pages` moved verbatim; `_PagesMixin` drops out of
    the composite tuple (transitive). `__init__.py` is now assembly-only: mixin imports, the
    `SQLiteRepository(<mixins>, IndexRepository)` class, re-exports + `__all__`.
  - Rewrite the stale 2024 stub-phase docstrings (module header "every method raises
    NotImplementedError…" + the class docstring "Stub phase…") to describe the package/assembly
    role; drop the dead `_stub` helper (zero call sites, verified) instead of relocating it.
- [ ] **[R4]** 056-07b — decompose `search_pages` in place.
  - Extract module-private helpers (filter-clause builder incl. `--where`/status/severity/tag,
    alias-expansion + FTS MATCH assembly, `--as-of` CTE builder, membership narrowing, row→
    `PageHit` mapping); public method becomes the orchestrator. No new public surface.
  - Cap check: `wc -l _search.py` ≤ 500 post-decomposition (overflow remedy: named carve-out
    `_search_asof.py`, per TASK R4).

- [ ] **[R5]** 056-08 — full gate sweep + cap audit.
  - `pytest tests/` (zero test edits), `mypy --strict scripts/` (zero `type: ignore` added),
    `wc -l scripts/wiki_index/sqlite_repository/*.py` all ≤ 500, e2e reindex-full tests green
    (rebuildability), `grep -rn "sqlite_repository" scripts/ | grep -v sqlite_repository/` shows
    only unchanged import lines.

- [ ] **[R6]** 056-09 — Postgres-readiness dialect map (docs only).
  - Add a `dialect:` tag line to every domain-module docstring (generic vs SQLite-only: FTS5 in
    `_search`, `json_extract`/`json_each` in `_health_*`/`_search`/`_state`, PRAGMA +
    `user_version` in `_base`).
  - `docs/SQLITE-VS-POSTGRES.md` §4: replace illustrative `sqlite_repo.py`/`postgres_repo.py`
    with the real package layout + the `postgres_repository/` mirror convention + consolidated
    dialect table, **plus the explicit non-goal sentence — no `PostgresRepository` code in this
    task (TASK R6c)** — mirrored in the ARCHITECTURE.md §3 summary if absent.

- [ ] **[R7]** 056-10 — ledger/docs closeout.
  - `scripts/wiki_index/.AGENTS.md`: new package inventory (one line per module).
  - Verify `docs/ARCHITECTURE.md` + `docs/architectures/{system-architecture,project-anatomy,
    open-questions}.md` (updated in the Architecture phase) still match the as-built result;
    README repo-layout touch if it names `sqlite_repository.py`;
    `grep -rn "sqlite_repository\.py" docs/ARCHITECTURE.md README.md` → 0 stale hits.

## Verification checkpoints
1. After every bead: the per-bead gate (suite + mypy + tests-untouched).
2. After 056-08: full acceptance sweep = TASK §4 criteria 1–5.
3. Adversarial review (`/vdd-adversarial`, Phase 4): logic/perf/security critics over the final
   diff — special attention to MRO order, `_search` decomposition SQL equivalence, and any
   accidental behaviour drift in relocated SQL strings.
4. Docs closeout (TASK §4 criterion 6) + task archive.
