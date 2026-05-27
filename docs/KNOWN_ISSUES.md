# Known Issues

Tracking ledger for low-priority cleanups and post-discovery bugs.

## Entry format

```markdown
## [YYYY-MM-DD] <short-title> [STATUS: open|fixed|wontfix]

- **Symptom**: <what user sees / what's wrong>
- **Root cause**: <one sentence>
- **Affected components**: <files/skills>
- **Fix plan**: <task/PR reference, or "deferred to Epic X">
- **Prevention**: <guard added>
```

---

## Low-severity items from architecture-review-pre-phase3a-2026-05-26

To be batched into a single cleanup PR before Phase 3a Exit. Tracked here per Plan Reviewer feedback I-4 to ensure they don't get dropped.

## [2026-05-26] L-1 entities.file_path UNIQUE invariant not explicit [STATUS: open]

- **Symptom**: Architecture review noted `entities.file_path UNIQUE per (vault_id, file_path)` (SCHEMA-v2.sql line 116) but `entity_aliases` has no FK back to a unique key on entities other than `(vault_id, slug)`. Invariant that file_path may not collide with another entity's alias-target path is implicit.
- **Root cause**: Documentation gap, not behavior bug.
- **Affected components**: `docs/SCHEMA-v2.sql` (header comment), `sql/wiki-index-v2.sql` (when created via task-001-01).
- **Fix plan**: Add inline comment in SCHEMA-v2.sql + sql/wiki-index-v2.sql clarifying the invariant.

## [2026-05-26] L-2 log_events.event_date should be GENERATED ALWAYS column [STATUS: open]

- **Symptom**: `log_events.event_date` is currently a regular TEXT column populated by inserter logic. Drift risk if inserter forgets to set it to `substr(event_ts, 1, 10)`.
- **Root cause**: Schema design — Class B (denorm) column without storage discipline.
- **Affected components**: `docs/SCHEMA-v2.sql` log_events DDL (line ~232), `sql/wiki-index-v2.sql`, task-001-19 log_events-CRUD impl.
- **Fix plan**: Convert to `event_date TEXT GENERATED ALWAYS AS (substr(event_ts, 1, 10)) STORED`. Schema-level guarantee.

## [2026-05-26] L-3 interactions.id is three identifiers in one [STATUS: open]

- **Symptom**: `interactions` has `id TEXT` (composite-style `'{kind}:{source_id}'`) AND PK `(vault_id, id)` AND separate UNIQUE `(vault_id, source_kind, source_id)`. Three identifiers for one row.
- **Root cause**: Carry-over from cybos pattern; redundant.
- **Affected components**: SCHEMA-v2.sql §7 interactions table.
- **Fix plan**: Drop synthetic `id` column; PK becomes `(vault_id, source_kind, source_id)`. Out-of-MVP (Epic 6) — defer fix until Epic 6 activates this table.

## [2026-05-26] L-4 entity_aliases PK includes entity_slug (wrong) [STATUS: open]

- **Symptom**: `entity_aliases` PK `(vault_id, alias, entity_slug)` allows the same alias to point at two different entity_slugs in one vault. Probably wrong — `"Sharpe ratio"` should resolve to a single entity.
- **Root cause**: Schema design error.
- **Affected components**: SCHEMA-v2.sql §3 entity_aliases.
- **Fix plan**: PK → `(vault_id, alias)` with `entity_slug` as regular column. Run uniqueness check first on existing data (none yet in MVP).

## [2026-05-26] L-5 pages.type='log' is dead enum value [STATUS: open]

- **Symptom**: `pages.type` enum includes `'log'` (SCHEMA-v2.sql line 167) but log content lives in `log.md` (Class A file rendered by wiki-ingest), not as a page row.
- **Root cause**: Leftover from v1 design; unused.
- **Affected components**: SCHEMA-v2.sql pages.type CHECK, task-001-26 (wiki-index-render).
- **Fix plan**: Remove `'log'` from enum. Verify task-001-26 doesn't create log-type pages.

## [2026-05-26] L-6 known_concepts view has cold-call cost [STATUS: open]

- **Symptom**: `known_concepts` view (SCHEMA-v2.sql line 470) uses `json_group_array(alias)` correlated subquery. Performant for read but unindexed.
- **Root cause**: Trade-off — correlated subquery is concise but uncached.
- **Affected components**: SCHEMA-v2.sql `known_concepts` view; task-001-17 search-pages impl (if it uses known_concepts).
- **Fix plan**: Document cold-call cost in view header comment. If wiki-ingest v1.1 known-concepts injection causes latency issue, materialise as a table populated by trigger.

## [2026-05-26] L-7 ADR-002 §D8 anti-pattern table correctness re-verify [STATUS: open]

- **Symptom**: Architecture review §4 L-7 noted ADR-002 §D8 anti-pattern row "Wiki-links только в БД через JOIN" — schema correctly mirrors to `page_entity_refs` (Class B), not anti-pattern. No fix needed; just confirming.
- **Root cause**: Documentation accuracy check.
- **Affected components**: ADR-002 §D8 anti-pattern table.
- **Fix plan**: Add reviewer confirmation note inline ("Verified consistent with `page_entity_refs` design, 2026-05-26").

---

## Performance items deferred from `/vdd-multi` iteration 1 (2026-05-26)

All flagged as SEV-1 by `critic-performance` but defer-justified: pass at N=100 in benchmark; 1k/10k SLO enforcement is not Phase 3a gate.

## [2026-05-26] P-1 reindex_full per-page transactions [STATUS: open]

- **Symptom**: `reindex_full` calls `repo.upsert_page` + `repo.replace_refs` once per page; each opens its own `BEGIN IMMEDIATE`/`COMMIT`. At 10k pages → ~20k commits + FTS5 trigger work per commit. Projected ~60–120 s; tight against the 3-min SLO.
- **Root cause**: `upsert_page` invariant that it owns its own transaction (M-4 contract) prevents trivial wrapping in an outer BEGIN.
- **Affected components**: `scripts/wiki_index/reindex.py:reindex_full`, `scripts/wiki_index/sqlite_repository.py:upsert_page`.
- **Fix plan**: Introduce `repo.bulk_upsert_pages(iter[Page])` with executemany inside one tx; defer FTS5 maintenance (drop+rebuild triggers + bulk INSERT into pages_fts at end). Acceptable only when `enforce_slos` testing at N=10k is wired into CI.

## [2026-05-26] P-2 reindex_delta no-op walk cost [STATUS: open]

- **Symptom**: `reindex_delta` calls `discover_pages` (rglob over `_sources/_concepts/_entities` × root + course tier) + `path.stat()` on every page + `SELECT slug, project FROM pages` + set membership. No-op delta at 10k pages risks blowing the 2 s SLO.
- **Root cause**: `Path.rglob` allocates Path objects per entry; `stat()` invoked on every discovered file even if unmodified.
- **Affected components**: `scripts/wiki_index/reindex.py:reindex_delta`, `discover_pages`.
- **Fix plan**: Replace `Path.rglob` with `os.scandir`; persist mtime/size to avoid re-stat; pull `last_modified` from `pages` table for comparison. Profile after.

## [2026-05-26] P-3 check_drift re-hashes every file [STATUS: open]

- **Symptom**: `SQLiteRepository.check_drift` reads + sha256-hashes every page on disk, plus `yaml.safe_load` on each frontmatter for type-mismatch detection. At 10k pages → wiki-lint 30 s SLO at risk.
- **Root cause**: No mtime/size short-circuit; PyYAML safe_load is slow.
- **Affected components**: `scripts/wiki_index/sqlite_repository.py:check_drift`.
- **Fix plan**: Compare `os.stat().st_mtime + st_size` against stored `last_modified` first; only re-hash on mismatch. Replace PyYAML with regex fast-path for `^type:\s*(\S+)`. Stream hashing via `hashlib.file_digest`.

## [2026-05-26] P-4 benchmark suite default n=100 only [STATUS: open]

- **Symptom**: `pytest tests/test_benchmark.py` and CLI default `--n 100` exercise only the smallest SLO bucket. The 1k/10k SLOs in `SLOS` dict are never automatically validated.
- **Root cause**: Benchmark designed for fast smoke; no CI scale gate.
- **Affected components**: `scripts/benchmark.py`, CI workflow (not yet created).
- **Fix plan**: Add `--scale all` mode (loops 100/1000/10000 + `--enforce-slos`); wire `--n 1000 --enforce-slos` into CI; mark `--n 10000` as nightly/manual. Document expected runtime per bucket.

## [2026-05-26] P-5 idx_pages_vault_tags is dead-weight functional index [STATUS: open]

- **Symptom**: `idx_pages_vault_tags ON pages(vault_id, json_extract(frontmatter_json, '$.tags'))` is maintained on every upsert but indexes a JSON array (compared as string), which provides no useful query path. Tag queries should route through `pages_fts.tags`.
- **Root cause**: Speculative index added during schema design; never used by any query.
- **Affected components**: `sql/wiki-index-v2.sql`, `docs/SCHEMA-v2.sql`.
- **Fix plan**: Drop the index. If tag selectivity becomes a real need, build a `pages_tags(vault_id, slug, tag)` join table populated by trigger.

---

## VDD-multi iteration 1 (2026-05-26) — accepted-and-noted lows

## [2026-05-26] D-1 assert_no_symlink_escape limited on Unix [STATUS: documented]

- **Symptom**: Function walks `Path.parent` lexically and checks `target.is_relative_to(p.anchor)`. On Unix `anchor = "/"` so the escape check can never trigger; loop detection unreachable (parent chain never revisits).
- **Root cause**: Defensive primitive whose strong form would need an FD-based, kernel-mediated walk.
- **Affected components**: `scripts/wiki_index/security.py`.
- **Fix plan**: Documented as a sanity rail (called from `reindex_delta`); primary R-26 protection is `validate_inside_vault` in `manual.fetch`. No code change beyond docstring honesty.

## [2026-05-26] D-2 R-26 not enforced on CLI output paths [STATUS: open]

- **Symptom**: `wiki-lint --report` / `--json-sidecar`, `wiki-index-render --output` accept arbitrary destination paths. An operator can write report files outside the vault root.
- **Root cause**: Outputs were considered operator-trusted; not gated by `validate_inside_vault`.
- **Affected components**: `scripts/wiki_skills/wiki_lint.py`, `scripts/wiki_skills/wiki_index_render.py`.
- **Fix plan**: Decide policy — either gate via `validate_inside_vault(arg, vault.root_path)` for R-26 compliance, or document explicit operator-trust scope in CLI `--help` text. Deferred pending Phase 3b threat-model review.

---

## VDD-multi iteration 2 (2026-05-28, TASK 003 v2) — deferred LOW findings

After the `/vdd-multi` adversarial sweep on TASK 003 v2 (`wiki-extract-concepts`), 6 must-fix items (1 CRITICAL + 3 HIGH + 2 MEDIUM) were patched inline and verified by `critic-logic` iteration-2 clean-pass. The 3 LOW findings below were explicitly deferred — recorded here so a future polish bead can sweep them.

## [2026-05-28] L-V3.1 datetime import inside update_idempotency_state [STATUS: fixed 2026-05-28]

- **Symptom**: `scripts/wiki_skills/wiki_extract_concepts.py::update_idempotency_state` did `from datetime import datetime as _dt, timezone as _tz` inside the function body instead of at module top.
- **Root cause**: Style inconsistency carried over from an earlier draft; worked correctly because Python caches modules in `sys.modules`.
- **Affected components**: `scripts/wiki_skills/wiki_extract_concepts.py`.
- **Resolution**: Hoisted to module top with the other stdlib imports. `update_idempotency_state` now uses `datetime.now(timezone.utc).isoformat()` directly. No behavior change. No new test (cosmetic).

## [2026-05-28] L-V3.2 check_idempotency missing defensive NULL check [STATUS: fixed 2026-05-28]

- **Symptom**: `check_idempotency` compared `row["value"] == current_hash`. If a corrupt row existed with `value=NULL`, comparison was `False` (the right behavior) but no documentation surfaced the implicit reliance on the DB CHECK constraint.
- **Root cause**: `source_state.value` is `TEXT NOT NULL` per schema, so this case shouldn't arise. Implicit reliance on DB constraint.
- **Affected components**: `scripts/wiki_skills/wiki_extract_concepts.py::check_idempotency`.
- **Resolution**: Added explicit `if row is None or row["value"] is None: return False` with docstring referencing L-V3.2. Regression test `test_check_idempotency_handles_null_row_value` mocks the cursor to simulate a NULL row and asserts the False return.

## [2026-05-28] L-V3.3 Anthropic SDK exception-chain may leak metadata [STATUS: fixed 2026-05-28]

- **Symptom**: `LLMUnavailableError(...) from e` preserved the SDK exception in `__cause__`. The operator-visible JSON envelope only emits `str(e)` of the wrapper (no leak today), but a future caller reaching for `__cause__.args` could surface `request_id` or partial headers from the SDK exception.
- **Root cause**: Python's default exception-chaining behavior; not specific to this code.
- **Affected components**: `scripts/wiki_skills/wiki_extract_concepts.py::extract_concepts_llm`.
- **Resolution**: Changed `from e` → `from None` to suppress the chain. The wrapper exception now has `__cause__ is None`; any future consumer attempting to walk `__cause__.args` finds nothing to leak. Regression test `test_extract_concepts_llm_suppresses_sdk_exception_chain` pins the behavior. CWE-209 closed.
