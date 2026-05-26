# Architecture Review — Pre-Phase 3a Gate (2026-05-26)

**Reviewer**: Architecture Reviewer (subagent, fresh context)
**Subject**: `obsidian-llm-wiki` Phase 3a foundation (SCHEMA-v2.sql + ADR-001 + ADR-002 + PLAN.md)
**Empirical anchor**: `trade-agents/Lessons/ZeroOne Systems/` — 13 sources / 35 concepts / 58 entities / 22,743 lines

## 1. Verdict

**APPROVED WITH COMMENTS** (confidence: high).

Architecture is fundamentally sound: Class A/B/C contract is rigorous, multi-vault partitioning is correctly designed-in (not retrofitted), composite PKs and CASCADE chains hold up under the rename scenario, and SCHEMA-v2.sql cleanly implements ADR-002's commitments. There are **3 blocking issues** that must be fixed before I-1.2 (apply schema) lands, plus several MED issues that should land inside Phase 3a. None require redesign.

## 2. Critical issues (HIGH — block Phase 3a kickoff)

### H-1. `pages_fts` contentless DELETE-by-column is fragile

Contentless FTS5 tables (no `content=`) support `DELETE FROM pages_fts WHERE <cols>` only when the column filter is satisfiable from the FTS index. `vault_id`, `slug`, `project` are all UNINDEXED — SQLite accepts the syntax but DELETE performs a full table scan on every page UPDATE/DELETE, and on contentless FTS5 some SQLite versions reject DELETE on UNINDEXED columns entirely.

Worse: the AFTER UPDATE trigger's DELETE arm uses `WHERE vault_id=? AND slug=? AND project=?` from `old.*`, but contentless FTS5 requires the original *indexed* token values via the 'delete' command. Stale tokens accumulate on every page update.

**Fix**: add `id INTEGER PRIMARY KEY AUTOINCREMENT` to `pages` (separate from composite PK kept as UNIQUE). FTS5 rowid = pages.id. Triggers use 'delete' command with original indexed values + new pages.id:

```sql
CREATE TRIGGER pages_fts_ad AFTER DELETE ON pages BEGIN
    INSERT INTO pages_fts(pages_fts, rowid, vault_id, slug, project, title, tldr, body_excerpt, tags)
    VALUES('delete', old.id, old.vault_id, old.slug, old.project, old.title, old.tldr, old.body_excerpt,
           json_extract(old.frontmatter_json, '$.tags'));
END;
```

Combine with M-4 fix (mandate `ON CONFLICT(vault_id, slug, project) DO UPDATE SET …` so pages.id preserved across upserts).

### H-2. `index_meta` view excludes entity rows

ADR-002 §D3 query: `SELECT slug, title FROM pages WHERE kind IN ('concept','entity')`. But entities live in `entities` table, not `pages`. `pages.type` enum has no `'entity'` value.

**Fix**: rewrite as UNION ALL:

```sql
CREATE VIEW index_meta AS
  SELECT vault_id, slug, project, type AS kind, title, tldr, last_modified
    FROM pages WHERE type IN ('summary', 'concept', 'query')
  UNION ALL
  SELECT vault_id, slug, NULL AS project, 'entity' AS kind, name AS title, definition AS tldr, last_updated AS last_modified
    FROM entities WHERE is_candidate = 0;
```

### H-3. `v_concept_cooccurrence` overcounts via ref_type cartesian

`page_entity_refs` PK includes `ref_type`. Same two entities with `ref_type='mentioned'` AND `ref_type='cited'` on the same page produce **two pair rows**, so `COUNT(*)` inflates.

**Fix**: `COUNT(DISTINCT page_slug || '|' || page_project)`.

## 3. Important issues (MED — fix before Phase 3a finishes)

- **M-1**: `vault_id GLOB '[a-z][a-z0-9-]*'` admits trailing/double hyphens. Tighten: `GLOB '[a-z][a-z0-9-]*[a-z0-9]'` + `NOT GLOB '*--*'`.
- **M-2**: FTS5 `vault_id UNINDEXED` does not accelerate `WHERE vault_id IN (?,?)`. For cross-vault at scale, MATCH+post-filter. Flag for benchmark E6.3 — if 10×5K regresses, this is the cause.
- **M-3**: `idx_pages_vault_tags` functional index requires byte-exact match in WHERE. Document the exact query form in I-3.3; EXPLAIN QUERY PLAN test in E6.
- **M-4**: `INSERT OR REPLACE` triggers CASCADE DELETE on `page_entity_refs` (nukes refs every upsert). Mandate `ON CONFLICT … DO UPDATE` for pages/entities; reserve `INSERT OR REPLACE` only for M:N rewrite tables. Document in PLAN.md I-2.2/I-3.3.
- **M-5**: Use `PRAGMA user_version = 2` for migration gating; keep `schema_meta` for human metadata only.
- **M-6**: `interactions`/`extracted_items` are dead weight для MVP. Keep tables but **drop indexes** until Epic 6 activation.
- **M-7**: `batch_runs.vault_id NULL` inconsistent с `'_vault_'` sentinel. Reserve `('_global_', 'Cross-vault operations', '/dev/null', '2.0', …)` row; make batch_runs.vault_id NOT NULL.

## 4. Minor (LOW)

- **L-1**: Document `entities.file_path` UNIQUE invariant.
- **L-2**: `log_events.event_date` should be `GENERATED ALWAYS AS (substr(event_ts, 1, 10)) STORED`.
- **L-3**: `interactions.id` is three identifiers in one — drop synthetic `id`, use `(vault_id, source_kind, source_id)` PK.
- **L-4**: `entity_aliases` PK should be `(vault_id, alias)` (alias unique within vault); `entity_slug` is column, not PK part.
- **L-5**: `pages.type='log'` — why? log.md is Class A file. Remove from enum unless I-3.4 uses it.
- **L-6**: `known_concepts` view's correlated subquery — document cold-call cost.
- **L-7**: ADR-002 §D8 anti-pattern table correct; schema doesn't violate.

## 5. Class A/B/C audit

| Table.column | Class | Rebuildable? | Notes |
|---|---|---|---|
| `vaults.vault_id` | B | yes (WIKI_SCHEMA.md) | ✓ |
| `vaults.name` | B | yes | ✓ |
| `vaults.root_path` | B | yes (filesystem) | ✓ |
| `vaults.schema_version` | B | yes | ✓ |
| `vaults.registered_at` | **C-strict** | no (approximated MIN(log_events.event_ts)) | ✓ per §D8 |
| `vaults.config_json` | B | yes (CLAUDE.md/.wiki.yaml) | ✓ |
| `vaults.notes` | **C-loose** | no | **flag**: not in §D8 audit; drop or reclassify |
| `entities.*` | B | yes | ✓ |
| `entities.mentions_count` | B (computed) | yes via `COUNT(*)` over refs | **should be view, not stored** (drift) |
| `entity_aliases.*` | B | yes | ✓ |
| `pages.*` | B | yes | ✓ |
| `pages.is_frozen` | B | yes (frontmatter) | document frontmatter key |
| `page_entity_refs.*` | B | yes (body parse) | ✓ |
| `log_events.*` | B | yes (log.md parse) | ✓ |
| `log_events.event_date` | B (denorm) | yes (substr) | → GENERATED column (L-2) |
| `interactions.*` | B | yes | out-of-MVP (M-6) |
| `extracted_items.*` | B | yes (LLM re-extract — expensive) | acceptable per §D8 |
| `batch_runs.*` | **C-loose** | partial | flag — status/errors not rebuildable; acknowledge as forensic-only |
| `source_state.*` | **C-cache** | recomputable but expensive | ✓ per §D8 |
| `schema_meta.*` | **C-strict** | no | ✓ |

Rebuildability gaps to declare in PLAN.md I-5.1: `vaults.registered_at` (approximated), `batch_runs.status/errors_json/finished_at` (lost), `source_state.value` (recomputed at cost). Invariant holds ✓.

## 6. Hallucination check

All cited paths verified to exist:
- `SCHEMA-v2.sql` ✓
- `adr/ADR-001-wiki-ingest-integration.md` ✓
- `adr/ADR-002-multi-vault-bottleneck-corrections.md` ✓ (§D1, D1.1, D2, D3, D4, D5, D6, D7, D8 все present)
- `PLAN.md` ✓
- `TASK.md` §0 status `PHASE-3A-READY` ✓
- `WIKI-INGEST-V1.1-CONTRACT.md` §1, §5 ✓
- ADR-002 §D8 event_type enum (11 types) matches SCHEMA-v2.sql lines 236-241 ✓

No hallucinations detected.

## 7. Convergence signal

**APPROVED WITH COMMENTS — PASS-with-fixlist**.

All 3 HIGH issues are fixable in < 50 lines of schema diff. ADR-001 / ADR-002 sound. Class A/B/C contract enforceable. Multi-vault partitioning correctly designed-in.

**Recommended sequencing**:
1. Patch SCHEMA-v2.sql for H-1, H-2, H-3 + M-4 + M-7 (bundle: pages.id PK, ON CONFLICT DO UPDATE pattern, index_meta UNION, COUNT DISTINCT, `_global_` sentinel row).
2. Re-verify triggers and views.
3. Land I-1.2 (apply schema).
4. M-1, M-2, M-3, M-5, M-6 tracked as issues during E1-E6 implementation, gated by benchmarks (E6.2/E6.3).
5. LOW items batched into single cleanup PR before Phase 3a exit.
