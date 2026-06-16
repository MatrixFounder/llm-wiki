-- =============================================================================
-- wiki-index — SQLite schema v2.0 (Multi-Vault)
-- =============================================================================
-- Single global DB serving MULTIPLE Obsidian vaults, partitioned by vault_id.
--
-- Architectural foundations:
--   ADR-001 — Wrap+Index (wiki-ingest = file-layer; this DB = derivative cache)
--   ADR-002 — Multi-vault partitioning + bottleneck corrections (this file)
--   ADR-002 §D8 — Data Layering Contract:
--                   Class A = vault-only (semantic canonical)
--                   Class B = vault-canonical + DB-mirrored (cache, rebuildable)
--                   Class C = DB-only operational (minimal: only `vaults.registered_at`)
--
-- Core invariant: vault (markdown) = source of truth; DB = 100% rebuildable
-- cache. `wiki-reindex --full` restores DB from files without semantic loss.
--
-- Compatibility: generic ANSI SQL except FTS5 (SQLite-only). Postgres equivalents
-- documented inline. See docs/SQLITE-VS-POSTGRES.md.
--
-- Status: DRAFT v2.0 (2026-05-26) — pending architecture review before Phase 3a
-- implementation. Supersedes SCHEMA-DRAFT.sql (v1, single-vault).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 0. Pragmas (apply at connection setup, not part of DDL)
-- ---------------------------------------------------------------------------
-- PRAGMA journal_mode = WAL;
-- PRAGMA synchronous = NORMAL;
-- PRAGMA foreign_keys = ON;
-- PRAGMA temp_store = MEMORY;
-- PRAGMA mmap_size = 268435456;       -- 256MB memory-mapped IO

-- ---------------------------------------------------------------------------
-- 1. vaults — registry of all Obsidian vaults sharing this DB
-- ---------------------------------------------------------------------------
-- ADR-002 D1: single global DB serves multiple vaults via vault_id partitioning.
-- ADR-002 D1.1: vault_id is REQUIRED explicit in <vault>/WIKI_SCHEMA.md.
--               No hash fallback. Format: ^[a-z][a-z0-9-]{2,31}$
--
-- Class breakdown:
--   vault_id, name, root_path, schema_version, config_json — Class B (mirror of
--     WIKI_SCHEMA.md and filesystem state; rebuildable from files)
--   registered_at — Class C (strict DB-only; approximated from earliest
--     log_events.event_ts on reindex)
--   ingest_count, last_ingest_at — VIEWS over log_events (not stored)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS vaults (
    vault_id          TEXT PRIMARY KEY
                        CHECK (
                          vault_id = '_global_'                  -- M-7 sentinel for cross-vault batch_runs
                          OR (
                            vault_id GLOB '[a-z][a-z0-9-]*[a-z0-9]'  -- M-1: tighten — letter-start, no trailing hyphen
                            AND vault_id NOT GLOB '*--*'             -- M-1: no double hyphens
                            AND length(vault_id) BETWEEN 3 AND 32
                          )
                        ),
    name              TEXT NOT NULL,
    root_path         TEXT NOT NULL UNIQUE,           -- absolute path; for '_global_' = '/dev/null' sentinel
    schema_version    TEXT NOT NULL,                  -- WIKI_SCHEMA.md::schema_version (e.g. '2.0'); for '_global_' = '2.0'
    registered_at     TEXT NOT NULL,                  -- ISO-8601; Class C
    config_json       TEXT,                           -- per-vault wiki.* config snapshot (Class B; from CLAUDE.md or .wiki.yaml)
    notes             TEXT
);

CREATE INDEX IF NOT EXISTS idx_vaults_root_path ON vaults(root_path);

-- Computed views (NOT stored — recomputed on every read; Class B materialization):
CREATE VIEW IF NOT EXISTS v_vault_stats AS
SELECT
    v.vault_id,
    v.name,
    v.root_path,
    (SELECT COUNT(*) FROM log_events le WHERE le.vault_id = v.vault_id AND le.event_type = 'ingest') AS ingest_count,
    (SELECT MAX(event_ts) FROM log_events le WHERE le.vault_id = v.vault_id) AS last_event_at,
    (SELECT MAX(event_ts) FROM log_events le WHERE le.vault_id = v.vault_id AND le.event_type = 'ingest') AS last_ingest_at,
    (SELECT COUNT(*) FROM pages p WHERE p.vault_id = v.vault_id) AS page_count,
    (SELECT COUNT(*) FROM entities e WHERE e.vault_id = v.vault_id) AS entity_count
FROM vaults v;

-- ---------------------------------------------------------------------------
-- 2. entities — canonical entities (concept, person, company, product, etc.)
-- ---------------------------------------------------------------------------
-- Karpathy "concept page" semantic. Cybos "people/companies" semantic.
-- Unified: one table, type discriminates.
--
-- Class B: mirror of <vault>/_concepts/<slug>.md and <vault>/_entities/<slug>.md
-- frontmatter + body excerpts. Rebuildable via wiki-reindex.
--
-- Postgres equivalent: identical + GIN on jsonb fields.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS entities (
    vault_id          TEXT NOT NULL REFERENCES vaults(vault_id) ON UPDATE CASCADE ON DELETE CASCADE,
    slug              TEXT NOT NULL,                   -- canonical filename (e.g. 'hermes-agent')
    type              TEXT NOT NULL CHECK (type IN (
                          'concept', 'person', 'company', 'product', 'group',
                          'event', 'work', 'external'
                      )),
    name              TEXT NOT NULL,                   -- canonical display name
    definition        TEXT,                            -- 1-3 sentences (Class B cache of body's first section)
    project           TEXT,                            -- '_vault_' = vault-root (promotion-spec tier 2);
                                                       -- <course-slug> = course-local (tier 1)
    is_candidate      INTEGER NOT NULL DEFAULT 0 CHECK (is_candidate IN (0, 1)),
    is_external       INTEGER NOT NULL DEFAULT 0 CHECK (is_external IN (0, 1)),
    is_private        INTEGER NOT NULL DEFAULT 0 CHECK (is_private IN (0, 1)),
    -- Identity matchers (cybos two-tier resolution)
    primary_email     TEXT,
    telegram_handle   TEXT,
    canonical_url     TEXT,
    -- Provenance
    first_seen        TEXT NOT NULL,                   -- ISO-8601
    last_updated      TEXT NOT NULL,                   -- ISO-8601
    canonicalized_by  TEXT,                            -- 'human' | 'llm:claude-opus-4-7@2026-05-26'
    -- File-system mirror
    file_path         TEXT NOT NULL,                   -- relative to vault root, e.g. '_concepts/hermes-agent.md'
    file_hash         TEXT,                            -- sha256 of body for change detection
    -- Auxiliary
    mentions_count    INTEGER NOT NULL DEFAULT 0,
    metadata_json     TEXT,                            -- frontmatter snapshot (Class B cache)
    PRIMARY KEY (vault_id, slug),
    -- L-1 (TASK 006): file_path UNIQUE per (vault_id) — two entities can't share
    -- a file. entity_aliases FKs only to (vault_id, slug); an alias-target's
    -- file_path is governed transitively via that FK, not duplicated here.
    UNIQUE (vault_id, file_path)
);

CREATE INDEX IF NOT EXISTS idx_entities_vault_type        ON entities(vault_id, type);
CREATE INDEX IF NOT EXISTS idx_entities_vault_project     ON entities(vault_id, project);
CREATE INDEX IF NOT EXISTS idx_entities_email             ON entities(vault_id, primary_email)    WHERE primary_email IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_entities_telegram          ON entities(vault_id, telegram_handle)  WHERE telegram_handle IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_entities_candidate         ON entities(vault_id, is_candidate)     WHERE is_candidate = 1;
CREATE INDEX IF NOT EXISTS idx_entities_updated           ON entities(vault_id, last_updated DESC);

-- ---------------------------------------------------------------------------
-- 3. entity_aliases — multiple display names for one entity
-- ---------------------------------------------------------------------------
-- "Workслоп" and "AI слоп" → entity `workslop` with two aliases.
-- Class B: derived from frontmatter `aliases:` field in entity pages.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS entity_aliases (
    vault_id          TEXT NOT NULL,
    alias             TEXT NOT NULL,
    entity_slug       TEXT NOT NULL,
    alias_type        TEXT NOT NULL CHECK (alias_type IN (
                          'spelling_variant', 'translation', 'nickname',
                          'acronym', 'former_name', 'product_codename'
                      )),
    -- TASK 005 / R-5.4 (schema v3): PK is (vault_id, alias) — one alias
    -- resolves to EXACTLY ONE entity per vault. Closes KNOWN_ISSUES L-4.
    -- entity_slug is now a regular column.
    PRIMARY KEY (vault_id, alias),
    FOREIGN KEY (vault_id, entity_slug) REFERENCES entities(vault_id, slug) ON UPDATE CASCADE ON DELETE CASCADE
);

-- TASK 005 / R-5.4: idx_aliases_lookup dropped (duplicate of the v3 PK index);
-- idx_aliases_entity added — reverse lookup for list_aliases (R-5.2),
-- search-expansion sibling gathering (R-5.5), merge re-pointing (R-4.7).
CREATE INDEX IF NOT EXISTS idx_aliases_entity ON entity_aliases(vault_id, entity_slug);

-- ---------------------------------------------------------------------------
-- 4. pages — wiki pages (sources, concept pages, queries, etc.)
-- ---------------------------------------------------------------------------
-- All markdown files in vault that have YAML frontmatter and participate in
-- wiki semantics. Sources = _sources/*.md; concepts = _concepts/*.md.
--
-- Note: entity-pages live in `entities` table (kind unification by promotion-
-- spec convention), NOT in `pages`. `pages.type` reflects source/concept/query
-- pages produced by ingest workflows.
--
-- Class B: full mirror of file frontmatter + body excerpt. Body excerpt is
-- normalized via R-07.5 (strip mermaid + SECTION anchors before FTS5 indexing).
--
-- DESIGN: `id INTEGER PRIMARY KEY AUTOINCREMENT` exists alongside the composite
-- (vault_id, slug, project) UNIQUE. Required for FTS5 contentless 'delete'
-- command pattern (H-1 fix from architecture-review-pre-phase3a-2026-05-26).
-- Upsert contract: MUST use `INSERT … ON CONFLICT(vault_id, slug, project)
-- DO UPDATE SET …` (preserves pages.id → FTS5 rowid stays stable → triggers
-- correctly un-index old tokens). NEVER use `INSERT OR REPLACE` on pages —
-- that creates new rowid and CASCADE-deletes page_entity_refs (M-4 fix).
--
-- project column semantics:
--   '_vault_'        = vault-root shared layer (promotion-spec tier 2)
--   '<course-slug>'  = course-local (promotion-spec tier 1)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS pages (
    id                INTEGER PRIMARY KEY AUTOINCREMENT, -- stable rowid for FTS5 (H-1 fix)
    vault_id          TEXT NOT NULL REFERENCES vaults(vault_id) ON UPDATE CASCADE ON DELETE CASCADE,
    slug              TEXT NOT NULL,
    project           TEXT NOT NULL DEFAULT '_vault_', -- '_vault_' sentinel for vault-wide
    type              TEXT NOT NULL CHECK (type IN (
                          'summary', 'concept', 'query', 'brief', 'research', 'index',
                          'verification'   -- TASK 008 / R-8.9 (schema v5): wiki-verify-multi verdict page
                      )),
    title             TEXT NOT NULL,
    file_path         TEXT NOT NULL,                   -- relative to vault_root
    tldr              TEXT,                            -- one-line for index render
    date              TEXT,                            -- ISO-8601 (YYYY-MM-DD); nullable — sources may be undated or carry unparseable placeholders
    last_modified     TEXT NOT NULL,                   -- file mtime, ISO-8601
    file_hash         TEXT NOT NULL,                   -- sha256 of body
    frontmatter_json  TEXT NOT NULL,                   -- full frontmatter as JSON
    body_excerpt      TEXT,                            -- first 500 chars, normalized (mermaid + anchors stripped)
    is_frozen         INTEGER NOT NULL DEFAULT 0,
    UNIQUE (vault_id, slug, project),                  -- semantic PK
    UNIQUE (vault_id, file_path)
);

CREATE INDEX IF NOT EXISTS idx_pages_vault_type         ON pages(vault_id, type);
CREATE INDEX IF NOT EXISTS idx_pages_vault_project_date ON pages(vault_id, project, date DESC);
CREATE INDEX IF NOT EXISTS idx_pages_vault_date         ON pages(vault_id, date DESC);
-- TASK 006 / P-5 (schema v4): idx_pages_vault_tags DROPPED (dead JSON-array
-- functional index, no query used it; tags route through pages_fts.tags).

-- ---------------------------------------------------------------------------
-- 5. page_entity_refs — M:N page ↔ entity references (with provenance v1.1)
-- ---------------------------------------------------------------------------
-- Karpathy "cross-references as valuable as documents". Replaces `appears_in:`
-- frontmatter list with normalized M:N.
--
-- Class B: derived from parsing body wiki-links + footnote definitions.
-- provenance fields (source_quote, line_start, line_end, trust_level) come from
-- the actual file text around each reference.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS page_entity_refs (
    vault_id          TEXT NOT NULL,
    page_slug         TEXT NOT NULL,
    page_project      TEXT NOT NULL DEFAULT '_vault_',
    entity_slug       TEXT NOT NULL,
    ref_type          TEXT NOT NULL CHECK (ref_type IN (
                          'mentioned', 'defined-here', 'related', 'cited',
                          'verifies',  -- TASK 008 / R-8.9 (schema v5): verdict-page → audited-query-page edge
                          -- TASK 032 / R-032-1 (schema v6): event-graph typed edges (ADR-004 D1), inverse-closed
                          'implements', 'implemented-by',
                          'supersedes', 'superseded-by',
                          'causes', 'caused-by',
                          -- TASK 034 / R-2 (schema v7): temporal + agent-memory edges
                          'invalidated-by', 'invalidates',
                          'activated-by', 'activates',
                          'uses', 'used-by',
                          'owns', 'owned-by'
                      )),
    -- Provenance v1.1
    line_start        INTEGER,
    line_end          INTEGER,
    source_quote      TEXT,                            -- 10-50 word verbatim
    trust_level       TEXT NOT NULL DEFAULT 'medium' CHECK (trust_level IN ('high', 'medium', 'low')),
    PRIMARY KEY (vault_id, page_slug, page_project, entity_slug, ref_type),
    FOREIGN KEY (vault_id, page_slug, page_project) REFERENCES pages(vault_id, slug, project) ON UPDATE CASCADE ON DELETE CASCADE
    -- NOTE: No FK on entity_slug — refs may target unresolved wiki-link slugs
    -- (orphan links). `find_orphan_links` (R-11) LEFT JOINs entities to detect
    -- these. Discovered during task-001-25 Phase 3a impl.
);

CREATE INDEX IF NOT EXISTS idx_refs_entity   ON page_entity_refs(vault_id, entity_slug);
CREATE INDEX IF NOT EXISTS idx_refs_page     ON page_entity_refs(vault_id, page_slug, page_project);
CREATE INDEX IF NOT EXISTS idx_refs_type     ON page_entity_refs(vault_id, ref_type);

-- ---------------------------------------------------------------------------
-- 6. log_events — structured mirror of <vault>/log.md (ADR-002 D2)
-- ---------------------------------------------------------------------------
-- Each event in log.md has a parallel row here. Resolves bottleneck B3 from
-- ADR-002 (linear log.md scan for "events per concept / period / type").
--
-- Class B: log.md remains canonical for human + git. log_events is rebuildable
-- via `wiki-reindex` parsing of '## [YYYY-MM-DD] event | subject' blocks.
-- log_md_byte_offset enables round-trip between Markdown row and DB row.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS log_events (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    vault_id          TEXT NOT NULL REFERENCES vaults(vault_id) ON UPDATE CASCADE ON DELETE CASCADE,
    event_ts          TEXT NOT NULL,                   -- ISO-8601 with timezone
    -- TASK 006 / L-2 (schema v4): STORED generated column — no inserter discipline.
    event_date        TEXT GENERATED ALWAYS AS (substr(event_ts, 1, 10)) STORED,
    event_type        TEXT NOT NULL CHECK (event_type IN (
                          'ingest', 'query', 'lint', 'reindex',
                          'promote', 'demote',
                          'backfill', 'reclassify',
                          'resolve-contradiction', 'fix-dangling', 'fix-orphan',
                          'verify'   -- TASK 008 / R-8.9 (schema v5): wiki-verify-multi audit event
                      )),
    subject           TEXT,                            -- source title / concept name / etc.
    project           TEXT,                            -- course this event happened in; '_vault_' for vault-wide
    pages_created_json   TEXT,                         -- JSON array of (slug, project) pairs
    pages_touched_json   TEXT,
    contradictions_count INTEGER NOT NULL DEFAULT 0,
    details_json      TEXT,                            -- full event payload (extensible)
    log_md_byte_offset INTEGER                         -- pointer into log.md tail for round-trip
);

CREATE INDEX IF NOT EXISTS idx_log_vault_ts       ON log_events(vault_id, event_ts DESC);
CREATE INDEX IF NOT EXISTS idx_log_vault_type     ON log_events(vault_id, event_type, event_ts DESC);
CREATE INDEX IF NOT EXISTS idx_log_vault_date     ON log_events(vault_id, event_date);
CREATE INDEX IF NOT EXISTS idx_log_subject        ON log_events(vault_id, subject)  WHERE subject IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 7. interactions — raw sources: emails, telegram messages, calls, web fetches
-- ---------------------------------------------------------------------------
-- Cybos-style. One email = one row. One transcript = one row (long body).
-- Future Epic 6 (multi-source); kept here for forward-compat in MVP.
--
-- Class B: derived from raw source files in <vault>/_raw/.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS interactions (
    vault_id          TEXT NOT NULL REFERENCES vaults(vault_id) ON UPDATE CASCADE ON DELETE CASCADE,
    id                TEXT NOT NULL,                   -- '{source_kind}:{source_id}' e.g. 'email:gmail/abc123'
    source_kind       TEXT NOT NULL CHECK (source_kind IN (
                          'email', 'telegram', 'call', 'web', 'transcript', 'manual', 'light'
                      )),
    source_id         TEXT NOT NULL,                   -- backend-specific ID
    body              TEXT NOT NULL,                   -- raw content
    body_hash         TEXT NOT NULL,                   -- sha256 for change detection
    occurred_at       TEXT NOT NULL,                   -- when in source system
    ingested_at       TEXT NOT NULL,                   -- when MVP saw it
    subject           TEXT,
    participants_json TEXT,
    raw_metadata_json TEXT,
    PRIMARY KEY (vault_id, id),
    UNIQUE (vault_id, source_kind, source_id)
);

CREATE INDEX IF NOT EXISTS idx_interactions_kind_date ON interactions(vault_id, source_kind, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_interactions_hash      ON interactions(vault_id, body_hash);

-- ---------------------------------------------------------------------------
-- 8. extracted_items — atomic LLM-extracted claims (future Epic 7)
-- ---------------------------------------------------------------------------
-- Cybos pattern. Each item = atomic claim with v1.1 provenance.
-- Out of MVP scope, kept for forward-compat.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS extracted_items (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    vault_id          TEXT NOT NULL,
    interaction_id    TEXT NOT NULL,
    type              TEXT NOT NULL CHECK (type IN (
                          'promise', 'action_item', 'decision', 'question',
                          'metric', 'claim', 'definition', 'entity_context'
                      )),
    content           TEXT NOT NULL,
    owner_entity      TEXT,                            -- entity slug; FK below
    target_entity     TEXT,
    related_entities_json TEXT,
    source_quote      TEXT NOT NULL,
    source_span       TEXT NOT NULL,                   -- 'L120-L138' or 'mm:ss-mm:ss'
    trust_level       TEXT NOT NULL CHECK (trust_level IN ('high', 'medium', 'low')),
    status            TEXT NOT NULL DEFAULT 'open' CHECK (status IN (
                          'open', 'resolved', 'cancelled', 'superseded'
                      )),
    resolved_at       TEXT,
    extracted_by      TEXT NOT NULL,
    extracted_at      TEXT NOT NULL,
    FOREIGN KEY (vault_id, interaction_id) REFERENCES interactions(vault_id, id) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (vault_id, owner_entity)   REFERENCES entities(vault_id, slug)   ON UPDATE CASCADE ON DELETE SET NULL,
    FOREIGN KEY (vault_id, target_entity)  REFERENCES entities(vault_id, slug)   ON UPDATE CASCADE ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_items_vault_interaction ON extracted_items(vault_id, interaction_id);
CREATE INDEX IF NOT EXISTS idx_items_vault_type        ON extracted_items(vault_id, type);
CREATE INDEX IF NOT EXISTS idx_items_vault_owner       ON extracted_items(vault_id, owner_entity, status);
CREATE INDEX IF NOT EXISTS idx_items_vault_status      ON extracted_items(vault_id, status, type);

-- ---------------------------------------------------------------------------
-- 9. batch_runs — log of reindex operations per vault
-- ---------------------------------------------------------------------------
-- Used by freshness check ("DB stale > 24h, run /wiki-reindex" warning).
-- Class B: implicit operational log; can be reconstructed from filesystem mtimes.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS batch_runs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    vault_id          TEXT NOT NULL REFERENCES vaults(vault_id) ON UPDATE CASCADE ON DELETE CASCADE,
                        -- M-7 fix: NOT NULL + use '_global_' sentinel vault row for cross-vault ops
                        -- (consistent with pages.project='_vault_' sentinel pattern)
    started_at        TEXT NOT NULL,
    finished_at       TEXT,
    status            TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed', 'partial')),
    mode              TEXT NOT NULL CHECK (mode IN ('full', 'delta', 'extract-only')),
    pages_indexed     INTEGER NOT NULL DEFAULT 0,
    interactions_indexed INTEGER NOT NULL DEFAULT 0,
    items_extracted   INTEGER NOT NULL DEFAULT 0,
    errors_json       TEXT,
    notes             TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_vault_started ON batch_runs(vault_id, started_at DESC);

-- ---------------------------------------------------------------------------
-- 10. source_state — per-source dedup state (cybos .state.json equivalent)
-- ---------------------------------------------------------------------------
-- Class C cache: source_hash for idempotency. Recomputable from source file
-- but costly (esp. cloud transcripts) — kept as cache.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS source_state (
    vault_id          TEXT NOT NULL REFERENCES vaults(vault_id) ON UPDATE CASCADE ON DELETE CASCADE,
    source_kind       TEXT NOT NULL,
    scope             TEXT NOT NULL,                   -- e.g. abs(source path) or 'gmail/me@example.com'
    key               TEXT NOT NULL,                   -- e.g. 'source_hash' or 'last_message_id'
    value             TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    PRIMARY KEY (vault_id, source_kind, scope, key)
);

-- =============================================================================
-- 11. FTS5 — full-text search (SQLite-only)
-- =============================================================================
-- CONTENTLESS mode (no `content='...'`) because we index computed values
-- (frontmatter tags via json_extract, normalized body excerpt). vault_id is
-- UNINDEXED — used for `WHERE vault_id IN (?, ?)` partition pruning.
--
-- Postgres equivalent: replace with `tsvector` column + `GIN(to_tsvector(...))`.
-- =============================================================================

CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
    vault_id UNINDEXED,
    slug UNINDEXED,
    project UNINDEXED,
    title,
    tldr,
    body_excerpt,
    tags,
    tokenize='unicode61 remove_diacritics 2'
);
-- DESIGN: internal-content FTS5 (no content= argument). FTS5 stores indexed
-- values internally; supports DELETE/UPDATE via standard SQL.

-- Triggers: keep pages_fts in sync with pages (Class B cache discipline)
--
-- DESIGN (H-1 fix):
--   1. FTS5 rowid = pages.id (INTEGER PRIMARY KEY AUTOINCREMENT). Stable across
--      ON CONFLICT DO UPDATE upserts (M-4 contract — see pages table comment).
--   2. DELETE-by-rowid is O(log N) via FTS5's internal rowid index — much faster
--      than the original `WHERE vault_id=? AND slug=? AND project=?` filter on
--      UNINDEXED columns (which scanned all FTS rows per H-1 review).
--   3. UPDATE = DELETE-by-rowid + INSERT pattern — eliminates stale tokens.
--
-- CRITICAL upsert contract for callers: MUST use `ON CONFLICT(vault_id, slug,
-- project) DO UPDATE SET …`. `INSERT OR REPLACE` would DELETE+INSERT pages,
-- generating new pages.id, breaking page_entity_refs CASCADE chain (M-4).

CREATE TRIGGER IF NOT EXISTS pages_fts_ai AFTER INSERT ON pages BEGIN
    INSERT INTO pages_fts(rowid, vault_id, slug, project, title, tldr, body_excerpt, tags)
    VALUES (new.id, new.vault_id, new.slug, new.project, new.title, new.tldr, new.body_excerpt,
            json_extract(new.frontmatter_json, '$.tags'));
END;

CREATE TRIGGER IF NOT EXISTS pages_fts_ad AFTER DELETE ON pages BEGIN
    DELETE FROM pages_fts WHERE rowid = old.id;
END;

CREATE TRIGGER IF NOT EXISTS pages_fts_au AFTER UPDATE ON pages BEGIN
    DELETE FROM pages_fts WHERE rowid = old.id;
    INSERT INTO pages_fts(rowid, vault_id, slug, project, title, tldr, body_excerpt, tags)
    VALUES (new.id, new.vault_id, new.slug, new.project, new.title, new.tldr, new.body_excerpt,
            json_extract(new.frontmatter_json, '$.tags'));
END;

-- =============================================================================
-- 12. Views — convenience layer
-- =============================================================================

-- index_meta — consolidated catalog (replaces index.md scan for LLM hot-path).
-- Reduces token cost: ~500 tokens vs ~4-30K tokens for full markdown.
--
-- H-2 fix: includes both pages (sources/concepts/queries) AND entities (the
-- canonical concept catalog). Entities live in `entities` table per the
-- promotion-spec layout (_concepts/*.md, _entities/*.md), NOT in pages.
-- Confirmed (is_candidate=0) entities only — candidate entities are noisy
-- LLM-extracted candidates, not part of the catalog.
CREATE VIEW IF NOT EXISTS index_meta AS
    SELECT vault_id, slug, project, type AS kind,
           title, tldr, last_modified
      FROM pages
     WHERE type IN ('summary', 'concept', 'query', 'verification')
  UNION ALL
    SELECT vault_id, slug, project, type AS kind,
           name AS title, definition AS tldr, last_updated AS last_modified
      FROM entities
     WHERE is_candidate = 0;

-- known_concepts — for wiki-ingest's --known-concepts-stdin injection (resolves B2).
CREATE VIEW IF NOT EXISTS known_concepts AS
    SELECT vault_id, slug, name, definition,
           (SELECT json_group_array(alias)
            FROM entity_aliases a
            WHERE a.vault_id = e.vault_id AND a.entity_slug = e.slug) AS aliases_json
    FROM entities e;

-- v_concept_cooccurrence — concepts that appear together on the same page (Epic 7-friendly).
--
-- H-3 fix: page_entity_refs PK includes ref_type, so the same entity-pair can
-- appear multiple times for one page (different ref_types: 'mentioned',
-- 'cited', 'defined-here', 'related'). COUNT(*) overcounts. Use COUNT(DISTINCT
-- page_slug || '|' || page_project) to count unique pages.
CREATE VIEW IF NOT EXISTS v_concept_cooccurrence AS
    SELECT
        r1.vault_id,
        r1.entity_slug AS slug_a,
        r2.entity_slug AS slug_b,
        COUNT(DISTINCT r1.page_slug || '|' || r1.page_project) AS pages_in_common
    FROM page_entity_refs r1
    JOIN page_entity_refs r2
      ON r1.vault_id = r2.vault_id
     AND r1.page_slug = r2.page_slug
     AND r1.page_project = r2.page_project
     AND r1.entity_slug < r2.entity_slug
    GROUP BY r1.vault_id, r1.entity_slug, r2.entity_slug;

-- =============================================================================
-- 13. Bootstrap data (run after table/view DDL on first init)
-- =============================================================================

-- 13.1 schema_meta — db-wide markers for migrations (Class C strict)
-- (Also use PRAGMA user_version = 2 for cheap migration gating; this table is
-- for human-readable metadata.)

CREATE TABLE IF NOT EXISTS schema_meta (
    key               TEXT PRIMARY KEY,
    value             TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

-- Seeded on first init by wiki-init:
--   INSERT INTO schema_meta(key, value, updated_at) VALUES ('schema_version', '5.0', <ISO-8601>);
--   INSERT INTO schema_meta(key, value, updated_at) VALUES ('created_at',     <ISO-8601>, <ISO-8601>);
--   PRAGMA user_version = 5;   -- v5 (TASK 008 / R-8.9): admit pages.type='verification', ref_type='verifies', event_type='verify' + index_meta parity (wiki-verify-multi).
--   PRAGMA user_version = 6;   -- v6 (TASK 032 / R-032-1, ADR-004): event-graph typed edges (implements/supersedes/causes + inverses).
--   PRAGMA user_version = 7;   -- v7 (TASK 034 / R-2): temporal + agent-memory edges (invalidated-by/activated-by/uses/owns + inverses).
--                              -- v4 (TASK 006): drop dead idx_pages_vault_tags (P-5) + event_date GENERATED (L-2).
--                              -- Migration on a populated DB: delete .db/-wal/-shm → wiki-init --register-existing → wiki-reindex --full (bare reindex can't relax a CHECK).
--
-- 13.2 '_global_' sentinel vault — M-7 fix
-- Pre-create so batch_runs.vault_id can be NOT NULL while still supporting
-- cross-vault operations. Pattern matches pages.project='_vault_' sentinel.
-- wiki-init MUST execute these inserts before any application code runs.
--
--   INSERT OR IGNORE INTO vaults(vault_id, name, root_path, schema_version, registered_at, notes)
--   VALUES (
--     '_global_',
--     'Cross-vault operations sentinel',
--     '/dev/null',
--     '2.0',
--     <ISO-8601>,
--     'Auto-created. Used by batch_runs for global reindex / cross-vault ops. Do not delete.'
--   );

-- =============================================================================
-- End of schema v2.0
-- =============================================================================
