-- =============================================================================
-- wiki-index — SQLite schema (DRAFT v0.1, SINGLE-VAULT — SUPERSEDED)
-- =============================================================================
-- ⚠️ STATUS: SUPERSEDED by SCHEMA-v2.sql (multi-vault, 2026-05-26).
-- ⚠️ This file is kept for reference during transition; do NOT use for new work.
-- ⚠️ For current schema see: docs/SCHEMA-v2.sql
-- ⚠️ Architectural decisions: docs/adr/ADR-001 (Wrap+Index), docs/adr/ADR-002 (Multi-vault)
--
-- Original purpose: индексирующий слой для Karpathy-style LLM Wiki + cybos-style
-- multi-source (markdown source-of-truth, SQLite — derivative cache).
--
-- Why superseded: single-vault assumption violates ADR-002 D1 (one DB serving
-- multiple Obsidian vaults). All tables in v2 add `vault_id` partition column;
-- PKs become composite. New `vaults` registry + `log_events` structured mirror.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 0. Pragmas (выполнять при создании БД, не часть DDL)
-- ---------------------------------------------------------------------------
-- PRAGMA journal_mode = WAL;
-- PRAGMA synchronous = NORMAL;          -- WAL + NORMAL = безопасно + быстро
-- PRAGMA foreign_keys = ON;
-- PRAGMA temp_store = MEMORY;
-- PRAGMA mmap_size = 268435456;         -- 256MB memory-mapped IO

-- ---------------------------------------------------------------------------
-- 1. entities — каноничные сущности (concept, person, company, product, group)
-- ---------------------------------------------------------------------------
-- В терминах wiki — это «concept page» по Karpathy. В cybos то же самое для
-- people/companies. Унифицированы: одна таблица для всего, type различает.
--
-- Postgres equivalent: identical, плюс GIN на jsonb-полях для быстрых path-queries.

CREATE TABLE IF NOT EXISTS entities (
    slug              TEXT PRIMARY KEY,         -- kebab-case, vault-wide unique
    type              TEXT NOT NULL CHECK (type IN (
                          'concept', 'person', 'company', 'product', 'group',
                          'event', 'work', 'external'
                      )),
    name              TEXT NOT NULL,            -- canonical display name
    definition        TEXT,                     -- 1-3 sentences, canonical
    project           TEXT,                     -- project slug or NULL = vault-wide
    is_candidate      INTEGER NOT NULL DEFAULT 0 CHECK (is_candidate IN (0, 1)),
    is_external       INTEGER NOT NULL DEFAULT 0 CHECK (is_external IN (0, 1)),
    is_private        INTEGER NOT NULL DEFAULT 0 CHECK (is_private IN (0, 1)),
    -- Identity matchers (cybos pattern, multi-stage resolution)
    primary_email     TEXT,                     -- person/company exact-match key
    telegram_handle   TEXT,                     -- person exact-match key (e.g. @nick)
    canonical_url     TEXT,                     -- product/external — primary URL
    -- Provenance
    first_seen        TEXT NOT NULL,            -- ISO-8601 timestamp
    last_updated      TEXT NOT NULL,            -- ISO-8601 timestamp
    canonicalized_by  TEXT,                     -- 'human' | 'llm:claude-opus-4-7@2026-04-28'
    -- File-system mirror
    file_path         TEXT UNIQUE,              -- relative to vault_root, e.g. 'Concepts/shadow-ai.md'
    -- Auxiliary
    mentions_count    INTEGER NOT NULL DEFAULT 0,
    metadata_json     TEXT                      -- JSON, schema-less extension
);

CREATE INDEX IF NOT EXISTS idx_entities_type           ON entities(type);
CREATE INDEX IF NOT EXISTS idx_entities_project        ON entities(project);
CREATE INDEX IF NOT EXISTS idx_entities_email          ON entities(primary_email)    WHERE primary_email IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_entities_tg             ON entities(telegram_handle)  WHERE telegram_handle IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_entities_candidate      ON entities(is_candidate)     WHERE is_candidate = 1;
CREATE INDEX IF NOT EXISTS idx_entities_last_updated   ON entities(last_updated);

-- ---------------------------------------------------------------------------
-- 2. entity_aliases — alias-имена для дедупликации
-- ---------------------------------------------------------------------------
-- Cybos pattern: «Workслоп» и «AI слоп» — один концепт workslop с двумя aliases.
--
-- Postgres equivalent: identical.

CREATE TABLE IF NOT EXISTS entity_aliases (
    alias             TEXT NOT NULL,
    entity_slug       TEXT NOT NULL REFERENCES entities(slug) ON DELETE CASCADE,
    alias_type        TEXT NOT NULL CHECK (alias_type IN (
                          'name', 'email', 'telegram', 'translit', 'abbreviation', 'former'
                      )),
    confidence        REAL NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
    added_by          TEXT NOT NULL,            -- 'human' | 'llm:...' | 'auto-translit'
    added_at          TEXT NOT NULL,            -- ISO-8601
    PRIMARY KEY (alias, entity_slug)
);

CREATE INDEX IF NOT EXISTS idx_aliases_entity ON entity_aliases(entity_slug);
CREATE INDEX IF NOT EXISTS idx_aliases_type   ON entity_aliases(alias_type);

-- ---------------------------------------------------------------------------
-- 3. pages — индекс всех markdown-страниц vault'а (Summaries/Concepts/Queries/...)
-- ---------------------------------------------------------------------------
-- Один rebuilds-источник. Pages == «summary pages» + «concept pages» + «query pages» +
-- «brief pages» + «research notes». type различает.
-- Все полнотекстовые поиски идут через pages_fts (см. §6).
--
-- Postgres equivalent: identical, плюс tsvector colmun + GIN(tsvector) для FTS.

-- IMPORTANT: project is NOT NULL with sentinel '_vault_' для vault-wide pages.
-- Это предотвращает SQLite NULL-PK semantics (NULL ≠ NULL → дубликаты).
-- См. TASK §6.1.

CREATE TABLE IF NOT EXISTS pages (
    slug              TEXT NOT NULL,
    project           TEXT NOT NULL DEFAULT '_vault_',  -- '_vault_' = vault-wide (NULL заменён sentinel'ом)
    type              TEXT NOT NULL CHECK (type IN (
                          'summary', 'concept', 'query', 'brief', 'research', 'index', 'log'
                      )),
    title             TEXT NOT NULL,
    file_path         TEXT NOT NULL UNIQUE,     -- relative to vault_root
    tldr              TEXT,                     -- one-line summary for index render
    date              TEXT NOT NULL,            -- ISO-8601 (YYYY-MM-DD)
    last_modified     TEXT NOT NULL,            -- file mtime, ISO-8601
    file_hash         TEXT NOT NULL,            -- sha256 of body, for change detection
    frontmatter_json  TEXT NOT NULL,            -- full frontmatter as JSON
    body_excerpt      TEXT,                     -- first 500 chars of body, for FTS preview
    is_frozen         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (slug, project)
);

CREATE INDEX IF NOT EXISTS idx_pages_type         ON pages(type);
CREATE INDEX IF NOT EXISTS idx_pages_project_date ON pages(project, date DESC);
CREATE INDEX IF NOT EXISTS idx_pages_date         ON pages(date DESC);
CREATE INDEX IF NOT EXISTS idx_pages_frontmatter  ON pages(json_extract(frontmatter_json, '$.tags'));

-- ---------------------------------------------------------------------------
-- 4. page_entity_refs — М:М связь страница ↔ entity (concept упомянут на странице)
-- ---------------------------------------------------------------------------
-- Заменяет «appears_in:» frontmatter list на normalized М:М.
-- Backlinks-запрос: SELECT page FROM page_entity_refs WHERE entity_slug = 'shadow-ai'.
-- Karpathy «cross-references as valuable as documents themselves».
--
-- Postgres equivalent: identical.

CREATE TABLE IF NOT EXISTS page_entity_refs (
    page_slug         TEXT NOT NULL,
    page_project      TEXT NOT NULL DEFAULT '_vault_',  -- aligned с pages.project sentinel
    entity_slug       TEXT NOT NULL REFERENCES entities(slug) ON DELETE CASCADE,
    ref_type          TEXT NOT NULL CHECK (ref_type IN (
                          'mentioned', 'defined-here', 'related', 'cited'
                      )),
    -- Provenance: где именно
    line_start        INTEGER,
    line_end          INTEGER,
    source_quote      TEXT,                     -- 10-50 word verbatim
    trust_level       TEXT NOT NULL DEFAULT 'medium' CHECK (trust_level IN ('high', 'medium', 'low')),
    PRIMARY KEY (page_slug, page_project, entity_slug, ref_type),
    FOREIGN KEY (page_slug, page_project) REFERENCES pages(slug, project) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_refs_entity      ON page_entity_refs(entity_slug);
CREATE INDEX IF NOT EXISTS idx_refs_page        ON page_entity_refs(page_slug, page_project);
CREATE INDEX IF NOT EXISTS idx_refs_ref_type    ON page_entity_refs(ref_type);

-- ---------------------------------------------------------------------------
-- 5. interactions — сырые источники: emails, telegram messages, calls, web fetches
-- ---------------------------------------------------------------------------
-- Cybos-style. Один email = одна interaction. Один Telegram message = одна.
-- Один transcript = одна (с длинным body). Один web-fetch = одна.
-- Из interactions LLM extract'ит extracted_items.
--
-- Postgres equivalent: identical, plus jsonb instead of TEXT for *_json.

CREATE TABLE IF NOT EXISTS interactions (
    id                TEXT PRIMARY KEY,         -- '{source_kind}:{source_id}' e.g. 'email:gmail/abc123'
    source_kind       TEXT NOT NULL CHECK (source_kind IN (
                          'email', 'telegram', 'call', 'transcript', 'web', 'manual'
                      )),
    source_id         TEXT NOT NULL,            -- gmail messageId, telegram msg_id, granola call_id, etc.
    project           TEXT,
    date              TEXT NOT NULL,            -- ISO-8601 timestamp
    -- Participants
    sender_entity     TEXT REFERENCES entities(slug) ON DELETE SET NULL,
    recipient_entities_json TEXT,               -- JSON array of slugs
    -- Content
    subject           TEXT,
    body              TEXT NOT NULL,
    body_hash         TEXT NOT NULL,            -- sha256 for dedup
    -- File mirror (если есть)
    file_path         TEXT UNIQUE,              -- relative to vault, e.g. 'Sources/email/2026-04-28-..../body.md'
    -- Source-specific metadata
    metadata_json     TEXT,                     -- gmail labels, telegram chat_id, granola attendees, ...
    -- Indexing state
    indexed_at        TEXT NOT NULL,            -- when this row was inserted
    extracted_at      TEXT,                     -- when LLM extraction last ran (NULL = pending)
    UNIQUE (source_kind, source_id)
);

CREATE INDEX IF NOT EXISTS idx_inter_kind_date     ON interactions(source_kind, date DESC);
CREATE INDEX IF NOT EXISTS idx_inter_sender        ON interactions(sender_entity);
CREATE INDEX IF NOT EXISTS idx_inter_project_date  ON interactions(project, date DESC);
CREATE INDEX IF NOT EXISTS idx_inter_pending       ON interactions(extracted_at) WHERE extracted_at IS NULL;

-- ---------------------------------------------------------------------------
-- 6. extracted_items — LLM-extracted структурированные facts из interactions
-- ---------------------------------------------------------------------------
-- Cybos pattern. Каждый item — atomic claim.
-- Provenance v1.1: source_quote / source_span / trust_level всегда обязательны.
--
-- Postgres equivalent: identical.

CREATE TABLE IF NOT EXISTS extracted_items (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    interaction_id    TEXT NOT NULL REFERENCES interactions(id) ON DELETE CASCADE,
    type              TEXT NOT NULL CHECK (type IN (
                          'promise',         -- «I'll send you the deck»
                          'action_item',     -- «Follow up on pricing»
                          'decision',        -- «We agreed to proceed»
                          'question',        -- «Need to confirm timeline»
                          'metric',          -- «500K ARR, 10 employees»
                          'claim',           -- factual statement, для wiki-knowledge use case
                          'definition',      -- определение концепта, candidate для concept page
                          'entity_context'   -- «X is working on Y»
                      )),
    content           TEXT NOT NULL,            -- normalized statement (LLM-paraphrased)
    -- Subjects (всегда entity-references, никогда free-form)
    owner_entity      TEXT REFERENCES entities(slug) ON DELETE SET NULL,
    target_entity     TEXT REFERENCES entities(slug) ON DELETE SET NULL,
    related_entities_json TEXT,                 -- JSON array of slugs
    -- Provenance v1.1 (обязательно!)
    source_quote      TEXT NOT NULL,            -- verbatim 10-50 words
    source_span       TEXT NOT NULL,            -- 'L120-L138' или 'mm:ss-mm:ss' для timeline
    trust_level       TEXT NOT NULL CHECK (trust_level IN ('high', 'medium', 'low')),
    -- Lifecycle
    status            TEXT NOT NULL DEFAULT 'open' CHECK (status IN (
                          'open', 'resolved', 'cancelled', 'superseded'
                      )),
    resolved_at       TEXT,                     -- when status changed to resolved
    -- Extraction metadata
    extracted_by      TEXT NOT NULL,            -- 'llm:claude-haiku-4-5@2026-04-28'
    extracted_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_items_interaction  ON extracted_items(interaction_id);
CREATE INDEX IF NOT EXISTS idx_items_type         ON extracted_items(type);
CREATE INDEX IF NOT EXISTS idx_items_owner        ON extracted_items(owner_entity, status);
CREATE INDEX IF NOT EXISTS idx_items_status       ON extracted_items(status, type);

-- ---------------------------------------------------------------------------
-- 7. batch_runs — лог reindex-операций (для freshness check)
-- ---------------------------------------------------------------------------
-- Cybos pattern. SessionStart hook или CLI читает последнюю запись для warning'а
-- «БД устарела > 24h, run /wiki-reindex».
--
-- Postgres equivalent: identical.

CREATE TABLE IF NOT EXISTS batch_runs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at        TEXT NOT NULL,
    finished_at       TEXT,
    status            TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed', 'partial')),
    mode              TEXT NOT NULL CHECK (mode IN ('full', 'delta', 'extract-only')),
    pages_indexed     INTEGER NOT NULL DEFAULT 0,
    interactions_indexed INTEGER NOT NULL DEFAULT 0,
    items_extracted   INTEGER NOT NULL DEFAULT 0,
    errors_json       TEXT,                     -- JSON array of {file, error} pairs
    notes             TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_started ON batch_runs(started_at DESC);

-- ---------------------------------------------------------------------------
-- 7.bis vault_metadata — vault identity и schema versioning (key-value)
-- ---------------------------------------------------------------------------
-- Хранит vault_hash, schema_version, created_at и другие vault-wide singletons.
-- Используется wiki-init §A2 для проверки «matching vault_hash» при re-init.
--
-- Postgres equivalent: identical.

CREATE TABLE IF NOT EXISTS vault_metadata (
    key               TEXT PRIMARY KEY,
    value             TEXT NOT NULL,
    updated_at        TEXT NOT NULL              -- ISO-8601
);

-- Seeded keys (заполняются wiki-init):
--   'vault_hash'      — sha256(abs_vault_root)[:12]
--   'vault_root_path' — absolute path для аудита
--   'schema_version'  — '1' изначально, инкрементируется wiki-migrate
--   'created_at'      — ISO-8601 timestamp первой инициализации
--   'language'        — 'ru' | 'en' | 'mixed' (cached из CLAUDE.md)
--   'layout'          — 'per-project' | 'flat'

-- ---------------------------------------------------------------------------
-- 8. source_state — per-source dedup state (cybos .state.json эквивалент)
-- ---------------------------------------------------------------------------
-- Удобнее в БД, чем в JSON-файле: транзакционно, не теряется при crash'е.
-- Один rec на (source_kind, scope) — например, 'email' + 'gmail-account-1' + 'last-message-id'.

CREATE TABLE IF NOT EXISTS source_state (
    source_kind       TEXT NOT NULL,
    scope             TEXT NOT NULL,            -- e.g. 'gmail/me@example.com', 'tg/+1234567890'
    key               TEXT NOT NULL,            -- e.g. 'last_message_id', 'last_pull_timestamp'
    value             TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    PRIMARY KEY (source_kind, scope, key)
);

-- =============================================================================
-- 9. FTS5 — полнотекстовый поиск (SQLite-only)
-- =============================================================================
-- ВАЖНО: используется CONTENTLESS mode (без `content='...'`), потому что мы
-- индексируем computed values (frontmatter tags via json_extract) — что не
-- 1-to-1 columns базовой таблицы. Triggers пишут explicit values напрямую.
--
-- Postgres equivalent: replace with `tsvector` column + `GIN(to_tsvector(...))`.
-- См. docs/SQLITE-VS-POSTGRES.md §3.2.

-- Pages full-text (поиск по title + tldr + body_excerpt + frontmatter tags)
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
    slug UNINDEXED,
    project UNINDEXED,
    title,
    tldr,
    body_excerpt,
    tags,
    tokenize = 'unicode61 remove_diacritics 2'   -- кириллица + латиница
    -- contentless: triggers populate values explicitly
);

-- Triggers держат pages_fts в sync с pages.
-- ВАЖНО: contentless FTS5 НЕ поддерживает обычный `DELETE FROM <fts>`. Корректный
-- idiom — `INSERT INTO <fts>(<fts>, rowid, ...) VALUES('delete', rowid, ...)` со
-- ВСЕМИ values из old.* для backout-of-index. См. https://sqlite.org/fts5.html §4.4.3.
CREATE TRIGGER IF NOT EXISTS pages_fts_insert AFTER INSERT ON pages BEGIN
    INSERT INTO pages_fts(rowid, slug, project, title, tldr, body_excerpt, tags)
    VALUES (
        new.rowid,
        new.slug,
        new.project,
        new.title,
        COALESCE(new.tldr, ''),
        COALESCE(new.body_excerpt, ''),
        COALESCE(json_extract(new.frontmatter_json, '$.tags'), '')
    );
END;

CREATE TRIGGER IF NOT EXISTS pages_fts_delete AFTER DELETE ON pages BEGIN
    INSERT INTO pages_fts(pages_fts, rowid, slug, project, title, tldr, body_excerpt, tags)
    VALUES (
        'delete',
        old.rowid,
        old.slug,
        old.project,
        old.title,
        COALESCE(old.tldr, ''),
        COALESCE(old.body_excerpt, ''),
        COALESCE(json_extract(old.frontmatter_json, '$.tags'), '')
    );
END;

CREATE TRIGGER IF NOT EXISTS pages_fts_update AFTER UPDATE ON pages BEGIN
    INSERT INTO pages_fts(pages_fts, rowid, slug, project, title, tldr, body_excerpt, tags)
    VALUES (
        'delete',
        old.rowid,
        old.slug,
        old.project,
        old.title,
        COALESCE(old.tldr, ''),
        COALESCE(old.body_excerpt, ''),
        COALESCE(json_extract(old.frontmatter_json, '$.tags'), '')
    );
    INSERT INTO pages_fts(rowid, slug, project, title, tldr, body_excerpt, tags)
    VALUES (
        new.rowid,
        new.slug,
        new.project,
        new.title,
        COALESCE(new.tldr, ''),
        COALESCE(new.body_excerpt, ''),
        COALESCE(json_extract(new.frontmatter_json, '$.tags'), '')
    );
END;

-- Interactions full-text (для future Epic 6 — emails / telegram body).
-- Также contentless mode + 'delete'-command pattern.
CREATE VIRTUAL TABLE IF NOT EXISTS interactions_fts USING fts5(
    id UNINDEXED,
    subject,
    body,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS interactions_fts_insert AFTER INSERT ON interactions BEGIN
    INSERT INTO interactions_fts(rowid, id, subject, body) VALUES (new.rowid, new.id, COALESCE(new.subject, ''), new.body);
END;
CREATE TRIGGER IF NOT EXISTS interactions_fts_delete AFTER DELETE ON interactions BEGIN
    INSERT INTO interactions_fts(interactions_fts, rowid, id, subject, body)
    VALUES ('delete', old.rowid, old.id, COALESCE(old.subject, ''), old.body);
END;
CREATE TRIGGER IF NOT EXISTS interactions_fts_update AFTER UPDATE ON interactions BEGIN
    INSERT INTO interactions_fts(interactions_fts, rowid, id, subject, body)
    VALUES ('delete', old.rowid, old.id, COALESCE(old.subject, ''), old.body);
    INSERT INTO interactions_fts(rowid, id, subject, body)
    VALUES (new.rowid, new.id, COALESCE(new.subject, ''), new.body);
END;

-- entities_fts — DEFERRED to Epic 7 migration (entity-resolver).
-- В v1 schema не создаётся: orphaned FTS index без triggers — антипаттерн.
-- Re-introduce когда будут aliases-aggregation triggers + использование в скиллах.

-- =============================================================================
-- 10. Vector search (опц., sqlite-vec extension)
-- =============================================================================
-- Включается только если wiki.index.vector.enabled = true.
-- См. https://github.com/asg017/sqlite-vec
--
-- Postgres equivalent: `pgvector` + HNSW index. См. docs/SQLITE-VS-POSTGRES.md §3.3.

-- ATTACH 'sqlite-vec.dylib';   -- при загрузке

-- CREATE VIRTUAL TABLE IF NOT EXISTS page_embeddings USING vec0(
--     page_rowid INTEGER PRIMARY KEY,
--     embedding FLOAT[384]                       -- miniLM dim; или 1536 для OpenAI ada
-- );

-- Sample query (cosine similarity):
-- SELECT p.slug, p.title, vec_distance_cosine(pe.embedding, ?) AS distance
-- FROM page_embeddings pe JOIN pages p ON p.rowid = pe.page_rowid
-- ORDER BY distance LIMIT 10;

-- =============================================================================
-- 11. Materialized views (через SQLite views; в Postgres — MATERIALIZED VIEW)
-- =============================================================================

-- Backlinks: для concept-page «куда я вписан».
-- (project / page_project NOT NULL DEFAULT '_vault_' — поэтому NULL-handling не нужен.)
CREATE VIEW IF NOT EXISTS v_entity_backlinks AS
    SELECT
        per.entity_slug,
        per.page_slug,
        per.page_project,
        p.title    AS page_title,
        p.date     AS page_date,
        per.ref_type,
        per.source_quote
    FROM page_entity_refs per
    JOIN pages p ON p.slug = per.page_slug
                AND p.project = per.page_project;

-- Co-occurrence: концепты, которые встречаются вместе на одной странице.
-- Используется в wiki-search для «Co-occurring concepts (≥ N mentions)».
CREATE VIEW IF NOT EXISTS v_concept_cooccurrence AS
    SELECT
        a.entity_slug AS concept_a,
        b.entity_slug AS concept_b,
        COUNT(*)      AS shared_pages
    FROM page_entity_refs a
    JOIN page_entity_refs b
        ON a.page_slug = b.page_slug
       AND a.page_project = b.page_project
       AND a.entity_slug < b.entity_slug
    GROUP BY a.entity_slug, b.entity_slug;

-- Pending items per owner (для daily brief).
CREATE VIEW IF NOT EXISTS v_pending_items AS
    SELECT
        ei.id,
        ei.type,
        ei.content,
        ei.owner_entity,
        ei.source_quote,
        i.date AS interaction_date,
        i.source_kind,
        ei.trust_level
    FROM extracted_items ei
    JOIN interactions i ON i.id = ei.interaction_id
    WHERE ei.status = 'open'
      AND ei.type IN ('promise', 'action_item', 'question');

-- =============================================================================
-- 12. Initial seed
-- =============================================================================

INSERT OR IGNORE INTO batch_runs (started_at, finished_at, status, mode, notes)
    VALUES (datetime('now'), datetime('now'), 'success', 'full', 'schema initialized');

-- vault_metadata seeded by wiki-init (placeholders here, реальные значения
-- инжектятся скриптом, см. UC-01 step 9):
INSERT OR IGNORE INTO vault_metadata(key, value, updated_at) VALUES
    ('schema_version', '1',                                datetime('now')),
    ('created_at',     datetime('now'),                    datetime('now'));
-- vault_hash, vault_root_path, language, layout — set by wiki-init

-- =============================================================================
-- END OF SCHEMA
-- =============================================================================
