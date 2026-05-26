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
