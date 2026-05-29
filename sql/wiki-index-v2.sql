-- =============================================================================
-- wiki-index — SQLite schema v2.0 (Multi-Vault) — RUNTIME COPY
-- =============================================================================
-- This file is the runtime source for `wiki-init`. The planning artefact is
-- `docs/SCHEMA-v2.sql`. Two deltas from the planning artefact (per task-001-01
-- acceptance criteria):
--   1. `PRAGMA user_version = 2;` appended after §13.1 (M-5 fix from
--      architecture-review-pre-phase3a-2026-05-26 — migration gating).
--   2. Indexes on `interactions` and `extracted_items` commented out with
--      `-- Epic 6 reactivation: uncomment ...` markers (M-6 fix — those tables
--      have no writers in Phase 3a, indexes are dead-weight on insert/maintain).
-- Schema-mutating changes must go through a Schema Change Request workflow that
-- updates docs/SCHEMA-v2.sql first, then this file. See sql/.AGENTS.md.
--
-- Architectural foundations:
--   ADR-001 — Wrap+Index (wiki-ingest = file-layer; this DB = derivative cache)
--   ADR-002 — Multi-vault partitioning + bottleneck corrections
--   ADR-002 §D8 — Data Layering Contract:
--                   Class A = vault-only (semantic canonical)
--                   Class B = vault-canonical + DB-mirrored (cache, rebuildable)
--                   Class C = DB-only operational (minimal: only `vaults.registered_at`)
--
-- Core invariant: vault (markdown) = source of truth; DB = 100% rebuildable
-- cache. `wiki-reindex --full` restores DB from files without semantic loss.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 0. Pragmas (apply at connection setup, not part of DDL — listed for reference)
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
    root_path         TEXT NOT NULL UNIQUE,
    schema_version    TEXT NOT NULL,
    registered_at     TEXT NOT NULL,                   -- ISO-8601; Class C
    config_json       TEXT,                            -- Class B; from CLAUDE.md or .wiki.yaml
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

CREATE TABLE IF NOT EXISTS entities (
    vault_id          TEXT NOT NULL REFERENCES vaults(vault_id) ON UPDATE CASCADE ON DELETE CASCADE,
    slug              TEXT NOT NULL,
    type              TEXT NOT NULL CHECK (type IN (
                          'concept', 'person', 'company', 'product', 'group',
                          'event', 'work', 'external'
                      )),
    name              TEXT NOT NULL,
    definition        TEXT,
    project           TEXT,
    is_candidate      INTEGER NOT NULL DEFAULT 0 CHECK (is_candidate IN (0, 1)),
    is_external       INTEGER NOT NULL DEFAULT 0 CHECK (is_external IN (0, 1)),
    is_private        INTEGER NOT NULL DEFAULT 0 CHECK (is_private IN (0, 1)),
    primary_email     TEXT,
    telegram_handle   TEXT,
    canonical_url     TEXT,
    first_seen        TEXT NOT NULL,
    last_updated      TEXT NOT NULL,
    canonicalized_by  TEXT,
    file_path         TEXT NOT NULL,
    file_hash         TEXT,
    mentions_count    INTEGER NOT NULL DEFAULT 0,
    metadata_json     TEXT,
    PRIMARY KEY (vault_id, slug),
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

CREATE TABLE IF NOT EXISTS entity_aliases (
    vault_id          TEXT NOT NULL,
    alias             TEXT NOT NULL,
    entity_slug       TEXT NOT NULL,
    alias_type        TEXT NOT NULL CHECK (alias_type IN (
                          'spelling_variant', 'translation', 'nickname',
                          'acronym', 'former_name', 'product_codename'
                      )),
    -- TASK 005 / R-5.4 (schema v3): PK is (vault_id, alias) — one alias
    -- resolves to EXACTLY ONE entity per vault. Closes KNOWN_ISSUES L-4
    -- (the old (vault_id, alias, entity_slug) PK let one alias point at
    -- multiple entities). entity_slug is now a regular column.
    PRIMARY KEY (vault_id, alias),
    FOREIGN KEY (vault_id, entity_slug) REFERENCES entities(vault_id, slug) ON UPDATE CASCADE ON DELETE CASCADE
);

-- TASK 005 / R-5.4: idx_aliases_lookup (vault_id, alias) was a duplicate of
-- the PK's implicit index under the v3 PK → dropped (dead-weight, cf. P-5).
-- idx_aliases_entity is the reverse lookup for list_aliases (R-5.2),
-- sibling-alias gathering during search expansion (R-5.5), and alias
-- re-pointing during merge (R-4.7) — the old composite PK put entity_slug
-- as the 3rd column (not a usable index prefix).
CREATE INDEX IF NOT EXISTS idx_aliases_entity ON entity_aliases(vault_id, entity_slug);

-- ---------------------------------------------------------------------------
-- 4. pages — wiki pages (sources, concept pages, queries, etc.)
-- ---------------------------------------------------------------------------
-- DESIGN: `id INTEGER PRIMARY KEY AUTOINCREMENT` exists alongside the composite
-- (vault_id, slug, project) UNIQUE. Required for FTS5 contentless 'delete'
-- command pattern (H-1 fix). Upsert contract: MUST use
-- `INSERT … ON CONFLICT(vault_id, slug, project) DO UPDATE SET …` (preserves
-- pages.id → FTS5 rowid stays stable). NEVER use `INSERT OR REPLACE` (M-4).
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS pages (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    vault_id          TEXT NOT NULL REFERENCES vaults(vault_id) ON UPDATE CASCADE ON DELETE CASCADE,
    slug              TEXT NOT NULL,
    project           TEXT NOT NULL DEFAULT '_vault_',
    type              TEXT NOT NULL CHECK (type IN (
                          'summary', 'concept', 'query', 'brief', 'research', 'index'
                      )),
    title             TEXT NOT NULL,
    file_path         TEXT NOT NULL,
    tldr              TEXT,
    date              TEXT,                              -- nullable: real-world sources may be undated or carry unparseable placeholders ('⚠️ UNKNOWN' etc)
    last_modified     TEXT NOT NULL,
    file_hash         TEXT NOT NULL,
    frontmatter_json  TEXT NOT NULL,
    body_excerpt      TEXT,
    is_frozen         INTEGER NOT NULL DEFAULT 0,
    UNIQUE (vault_id, slug, project),
    UNIQUE (vault_id, file_path)
);

CREATE INDEX IF NOT EXISTS idx_pages_vault_type         ON pages(vault_id, type);
CREATE INDEX IF NOT EXISTS idx_pages_vault_project_date ON pages(vault_id, project, date DESC);
CREATE INDEX IF NOT EXISTS idx_pages_vault_date         ON pages(vault_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_pages_vault_tags         ON pages(vault_id, json_extract(frontmatter_json, '$.tags'));

-- ---------------------------------------------------------------------------
-- 5. page_entity_refs — M:N page ↔ entity references (with provenance v1.1)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS page_entity_refs (
    vault_id          TEXT NOT NULL,
    page_slug         TEXT NOT NULL,
    page_project      TEXT NOT NULL DEFAULT '_vault_',
    entity_slug       TEXT NOT NULL,
    ref_type          TEXT NOT NULL CHECK (ref_type IN (
                          'mentioned', 'defined-here', 'related', 'cited'
                      )),
    line_start        INTEGER,
    line_end          INTEGER,
    source_quote      TEXT,
    trust_level       TEXT NOT NULL DEFAULT 'medium' CHECK (trust_level IN ('high', 'medium', 'low')),
    PRIMARY KEY (vault_id, page_slug, page_project, entity_slug, ref_type),
    FOREIGN KEY (vault_id, page_slug, page_project) REFERENCES pages(vault_id, slug, project) ON UPDATE CASCADE ON DELETE CASCADE
    -- NOTE: No FK on entity_slug — refs may target unresolved wiki-link slugs
    -- (orphan links). `find_orphan_links` (R-11) LEFT JOINs entities to detect
    -- these. Entity deletion does NOT auto-cascade refs; cleanup is operator-
    -- driven via wiki-lint --fix (Epic 7+).
);

CREATE INDEX IF NOT EXISTS idx_refs_entity   ON page_entity_refs(vault_id, entity_slug);
CREATE INDEX IF NOT EXISTS idx_refs_page     ON page_entity_refs(vault_id, page_slug, page_project);
CREATE INDEX IF NOT EXISTS idx_refs_type     ON page_entity_refs(vault_id, ref_type);

-- ---------------------------------------------------------------------------
-- 6. log_events — structured mirror of <vault>/log.md (ADR-002 D2)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS log_events (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    vault_id          TEXT NOT NULL REFERENCES vaults(vault_id) ON UPDATE CASCADE ON DELETE CASCADE,
    event_ts          TEXT NOT NULL,
    event_date        TEXT NOT NULL,
    event_type        TEXT NOT NULL CHECK (event_type IN (
                          'ingest', 'query', 'lint', 'reindex',
                          'promote', 'demote',
                          'backfill', 'reclassify',
                          'resolve-contradiction', 'fix-dangling', 'fix-orphan'
                      )),
    subject           TEXT,
    project           TEXT,
    pages_created_json   TEXT,
    pages_touched_json   TEXT,
    contradictions_count INTEGER NOT NULL DEFAULT 0,
    details_json      TEXT,
    log_md_byte_offset INTEGER
);

CREATE INDEX IF NOT EXISTS idx_log_vault_ts       ON log_events(vault_id, event_ts DESC);
CREATE INDEX IF NOT EXISTS idx_log_vault_type     ON log_events(vault_id, event_type, event_ts DESC);
CREATE INDEX IF NOT EXISTS idx_log_vault_date     ON log_events(vault_id, event_date);
CREATE INDEX IF NOT EXISTS idx_log_subject        ON log_events(vault_id, subject)  WHERE subject IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 7. interactions — raw sources (future Epic 6; tables kept, indexes deferred)
-- ---------------------------------------------------------------------------
-- M-6 fix: indexes on this table are commented out (no writers in Phase 3a).
-- Epic 6 reactivation: uncomment idx_interactions_* below when implementing
-- multi-source ingestion.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS interactions (
    vault_id          TEXT NOT NULL REFERENCES vaults(vault_id) ON UPDATE CASCADE ON DELETE CASCADE,
    id                TEXT NOT NULL,
    source_kind       TEXT NOT NULL CHECK (source_kind IN (
                          'email', 'telegram', 'call', 'web', 'transcript', 'manual', 'light'
                      )),
    source_id         TEXT NOT NULL,
    body              TEXT NOT NULL,
    body_hash         TEXT NOT NULL,
    occurred_at       TEXT NOT NULL,
    ingested_at       TEXT NOT NULL,
    subject           TEXT,
    participants_json TEXT,
    raw_metadata_json TEXT,
    PRIMARY KEY (vault_id, id),
    UNIQUE (vault_id, source_kind, source_id)
);

-- Epic 6 reactivation: uncomment when interactions table gets writers.
-- CREATE INDEX IF NOT EXISTS idx_interactions_kind_date ON interactions(vault_id, source_kind, occurred_at DESC);
-- Epic 6 reactivation: uncomment when interactions table gets writers.
-- CREATE INDEX IF NOT EXISTS idx_interactions_hash      ON interactions(vault_id, body_hash);

-- ---------------------------------------------------------------------------
-- 8. extracted_items — atomic LLM-extracted claims (future Epic 7)
-- ---------------------------------------------------------------------------
-- M-6 fix: indexes commented out (no writers in Phase 3a). See §7 above.
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
    owner_entity      TEXT,
    target_entity     TEXT,
    related_entities_json TEXT,
    source_quote      TEXT NOT NULL,
    source_span       TEXT NOT NULL,
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

-- Epic 7 reactivation: uncomment when extracted_items table gets writers.
-- CREATE INDEX IF NOT EXISTS idx_items_vault_interaction ON extracted_items(vault_id, interaction_id);
-- Epic 7 reactivation: uncomment when extracted_items table gets writers.
-- CREATE INDEX IF NOT EXISTS idx_items_vault_type        ON extracted_items(vault_id, type);
-- Epic 7 reactivation: uncomment when extracted_items table gets writers.
-- CREATE INDEX IF NOT EXISTS idx_items_vault_owner       ON extracted_items(vault_id, owner_entity, status);
-- Epic 7 reactivation: uncomment when extracted_items table gets writers.
-- CREATE INDEX IF NOT EXISTS idx_items_vault_status      ON extracted_items(vault_id, status, type);

-- ---------------------------------------------------------------------------
-- 9. batch_runs — log of reindex operations per vault
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS batch_runs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    vault_id          TEXT NOT NULL REFERENCES vaults(vault_id) ON UPDATE CASCADE ON DELETE CASCADE,
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
-- 10. source_state — per-source dedup state (Class C cache)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS source_state (
    vault_id          TEXT NOT NULL REFERENCES vaults(vault_id) ON UPDATE CASCADE ON DELETE CASCADE,
    source_kind       TEXT NOT NULL,
    scope             TEXT NOT NULL,
    key               TEXT NOT NULL,
    value             TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    PRIMARY KEY (vault_id, source_kind, scope, key)
);

-- =============================================================================
-- 11. FTS5 — full-text search (SQLite-only)
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
-- H-1 fix: rowid = pages.id; UPDATE = DELETE-by-rowid + INSERT.

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

-- index_meta — consolidated catalog (pages + entities UNION; H-2 fix).
CREATE VIEW IF NOT EXISTS index_meta AS
    SELECT vault_id, slug, project, type AS kind,
           title, tldr, last_modified
      FROM pages
     WHERE type IN ('summary', 'concept', 'query')
  UNION ALL
    SELECT vault_id, slug, project, type AS kind,
           name AS title, definition AS tldr, last_updated AS last_modified
      FROM entities
     WHERE is_candidate = 0;

-- known_concepts — for wiki-ingest --known-concepts-stdin injection (B2 resolver).
CREATE VIEW IF NOT EXISTS known_concepts AS
    SELECT vault_id, slug, name, definition,
           (SELECT json_group_array(alias)
            FROM entity_aliases a
            WHERE a.vault_id = e.vault_id AND a.entity_slug = e.slug) AS aliases_json
    FROM entities e;

-- v_concept_cooccurrence — concepts that appear together on the same page (H-3 fix).
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

CREATE TABLE IF NOT EXISTS schema_meta (
    key               TEXT PRIMARY KEY,
    value             TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

-- 13.2 PRAGMA user_version — migration gating marker (M-5 fix)
-- Set unconditionally on every apply; idempotent. wiki-init reads this to
-- decide whether to seed schema or run a migration step.
-- v3 (TASK 005 / R-5.4): entity_aliases PK (vault_id, alias) + idx swap.
-- The DB is a Class B rebuildable cache, so the v2→v3 migration is a
-- `wiki-reindex --full`, NOT an in-place ALTER (apply_schema's
-- CREATE TABLE IF NOT EXISTS cannot mutate a live PK). See ADR-002 §D8
-- amendment.
PRAGMA user_version = 3;

-- 13.3 '_global_' sentinel vault — M-7 fix
-- Pre-create so batch_runs.vault_id can be NOT NULL while still supporting
-- cross-vault operations. wiki-init MUST also re-execute this on register
-- flows (idempotent via INSERT OR IGNORE) so the row exists before any
-- application code runs. registered_at is left blank here — wiki-init fills
-- it on first run with the current ISO-8601 timestamp.
--
-- Commented out here so a raw `sqlite3 db < wiki-index-v2.sql` apply does not
-- require a timestamp literal. wiki-init Python code runs this with the real
-- value (see task-001-15 vaults-CRUD impl):
--
-- INSERT OR IGNORE INTO vaults(vault_id, name, root_path, schema_version, registered_at, notes)
-- VALUES (
--   '_global_',
--   'Cross-vault operations sentinel',
--   '/dev/null',
--   '2.0',
--   <ISO-8601-now>,
--   'Auto-created. Used by batch_runs for global reindex / cross-vault ops. Do not delete.'
-- );

-- =============================================================================
-- End of schema v2.0
-- =============================================================================
