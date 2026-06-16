# PLAN 034 — Temporal core + agent-memory edges & classes

Stub-First, green-throughout. Each bead: RED (failing test) → GREEN (minimal code) → mypy
`--strict`. Order chosen so Delta 2's `invalidated-by` edge exists before Delta 1's `valid_to`
walk reads it. Maps to `docs/TASK.md` RTM.

## Bead 034-00 — Delta 2: typed edges + schema v6→v7  (R-2, R-2a)
- **RED:** `tests/test_event_graph_new_edges.py` — author `invalidated_by`/`activated_by`/
  `uses`/`owns` (and the reverse-direction keys) on fixture pages → assert forward rows +
  auto-derived inverses (`invalidates`/`activates`/`used-by`/`owned-by`), idempotency,
  orphan-target skip; assert the 3 code maps ⊇ the SQL CHECK enum (drift guard).
- **GREEN:**
  - [reindex.py:202](../scripts/wiki_index/reindex.py#L202) `_EDGE_KEY_TO_REF_TYPE` += 8 keys.
  - [reindex.py:281](../scripts/wiki_index/reindex.py#L281) `_INVERSE_REF_TYPE` += 8 directions.
  - [wiki-index-v2.sql:195](../sql/wiki-index-v2.sql#L195) CHECK enum += 8 values;
    `PRAGMA user_version = 7` ([:470](../sql/wiki-index-v2.sql#L470)) + `-- v7 (TASK 034)` note.
  - [models.py:199](../scripts/wiki_index/models.py#L199) `PageRef.ref_type` docstring.
- **Verify:** new + existing `test_event_graph*` green; `wiki-graph --kind invalidates` traverses.

## Bead 034-01 — Delta 1 DAL: `search_pages(as_of=…)`  (R-1, R-1b, R-1c)
- **RED:** `tests/test_wiki_search_as_of.py` — build a fixture vault with decision-16
  (`date 2026-03-01`) ⟵ decision-17 (`date 2026-05-01`, `supersedes`); assert `as_of`
  2026-04-15 → 16 active not 17; 2026-06-01 → 17; multi-step chain; `invalidated_by` an
  incident; no-date page excluded; override `valid_from`/`valid_to`; equality back-compat
  unchanged (no `as_of` → identical rows).
- **GREEN:** add `as_of: str | None = None` to the ABC
  ([repository.py:151](../scripts/wiki_index/repository.py#L151)) + impl
  ([sqlite_repository.py:548](../scripts/wiki_index/sqlite_repository.py#L548)); append the
  §4 predicate when set (3 binds). No `as_of` → zero SQL delta (R-1c/R-4).

## Bead 034-02 — Delta 1 CLI: `wiki-search --as-of`  (R-1, R-1a)
- **RED:** CLI tests in `test_wiki_search_as_of.py` — `--as-of 2026-04-15` end-to-end;
  `--as-of bad` → `INVALID_FILTER` exit 2 no echo; `--as-of` alone (no query/where) valid.
- **GREEN:** [wiki_search.py](../scripts/wiki_skills/wiki_search.py) — add `--as-of`, ISO
  validate (`datetime.date.fromisoformat`, reject → emit no-echo), relax the empty-search
  guard ([:132](../scripts/wiki_skills/wiki_search.py#L132)), thread to both `search_pages`
  call sites.

## Bead 034-03 — Delta 3: agent-memory classes (config only)  (R-3, R-4)
- **RED:** `tests/test_layout_agent_memory.py` — a `cybos` fixture vault with
  `agents/x.md` (`type: agent`) etc. → `iter_pages`/derive classifies to the mapped
  `db_type` + tag; no `UnmappedTypeError`; Karpathy unaffected.
- **GREEN:** [cybos.yaml](../scripts/wiki_index/layouts/cybos.yaml) `type_mapping` += 6 types,
  `paths` += globs; `templates/page-types/{agent,tool,workflow,capability,execution,pattern}.md`;
  fix the stale "deferred Phase-2" header comment.

## Bead 034-04 — Docs lockstep + dogfood + gates  (R-5)
- `skills/wiki-search/SKILL.md` (+`--as-of` eval), manuals EN/RU, `cli-quick-ref`,
  `docs/layouts/cybos.md`, `docs/ARCHITECTURE.md` §4, CLAUDE.md narrative, ROADMAP.
- **Dogfood:** `samples/` cybos vault — as-of flip, `wiki-graph chain --kind supersedes`,
  `wiki-graph backlinks <capability> --kind implements`, `--kind invalidates`.
- **Gates:** full `pytest` + `mypy --strict` green; `/vdd-multi` (logic/security/performance)
  converge.
