# SQLite vs PostgreSQL — выбор индексирующего движка для wiki-index

> Этот документ — референс для решения «какой движок использовать под индексирующий слой LLM-Wiki». Главный архитектурный документ — [TASK-ref-v2.md](./archive/TASK-ref-v2.md). Здесь — детальное обоснование выбора и реализация **обоих** backend'ов через единый `IndexRepository` интерфейс.

---

## 1. TL;DR

- **SQLite — default** для personal Obsidian wiki, single user, multi-device, ≤ 100K документов, offline-capable.
- **Postgres — opt-in** для team-vault, > 100K документов, или когда нужны pgvector+HNSW / pg_trgm.
- **Объединяем** через DAL (`IndexRepository` interface) → одна и та же бизнес-логика поверх любого backend'а.
- **iCloud-критическое правило**: SQLite-файл **обязательно** хранится **вне** vault'а в iCloud (`~/.local/share/wiki-index/<hash>.db` или macOS-эквивалент `~/Library/Application Support/wiki-index/...`).

---

## 2. Decision matrix (детальный)

Контекст: один пользователь, vault в iCloud Obsidian, multi-device (Mac + iPhone + iPad), сотни–тысячи документов, multi-source (email/telegram/web), offline иногда обязателен, primary storage — markdown в iCloud.

| # | Критерий | SQLite (FTS5+WAL+sqlite-vec) | PostgreSQL (pgvector+pg_trgm+tsvector) | Победитель |
|---|---|---|---|---|
| 1 | Setup-overhead | Zero — embedded, single file | Средний: `brew install postgresql`, `initdb`, `pg_hba.conf`, daemon | **SQLite** |
| 2 | Зависимости в скилле | stdlib (`sqlite3` python, `bun:sqlite`); опц. `sqlite-vec` (.dylib) | postgres server + libpq + extensions | **SQLite** |
| 3 | iOS / Obsidian Mobile | Нативно (Bun/Python/Swift все его поддерживают) | Невозможно (нужен сервер) | **SQLite** |
| 4 | FTS-поиск 100K rows | FTS5: < 10ms median, < 50ms p99 ([бенчмарки 2026](https://thelinuxcode.com/sqlite-full-text-search-fts5-in-practice/)) | tsvector+GIN: 5–20ms p99 | Ничья (оба отлично) |
| 5 | Vector search 100K × 384-dim | sqlite-vec brute-force: < 100ms | pgvector + HNSW: 5–15K QPS, < 5ms | **Postgres** |
| 6 | Vector search 1M × 1536-dim | sqlite-vec: секунды | pgvector + HNSW: 10–50ms | **Postgres** (decisive) |
| 7 | Fuzzy match (Levenshtein/trigram) | Levenshtein в TS/Python (cybos pattern) или `spellfix1` extension | `pg_trgm` + GIN: native, fast | **Postgres** |
| 8 | JSON-queries (frontmatter, metadata) | `json_extract()` + computed columns + index | `jsonb` + `->`/`->>` + GIN на любой path | **Postgres** |
| 9 | Concurrent writes | Один писатель (WAL разрешает читателей) | Multi-writer, MVCC | **Postgres** при > 1 ingester |
| 10 | Reads concurrency | Excellent с WAL | Excellent | Ничья |
| 11 | Backup | Файл copy + `.backup` команда | `pg_dump`, WAL archiving | **SQLite** проще |
| 12 | Дистрибуция в скилл (npm/pip) | Self-contained, ship without runtime deps | Пользователь должен установить Postgres | **SQLite** |
| 13 | iCloud-совместимость | DB-файл **не** в iCloud (workaround: путь вне vault'а) | Сервер не зависит от iCloud | **Postgres** elegant |
| 14 | Сборка из markdown (full reindex) | 1000 docs ≈ 2-5s | 1000 docs ≈ 30-60s (overhead per-tx) | **SQLite** |
| 15 | Проверенность под use-case | Cybos уже работает на этом (см. [Gerstep/cybos](https://github.com/Gerstep/cybos)) | Не использован в reference-проекте | **SQLite** |
| 16 | Scale ceiling | ≈ 100K документов / 100K векторов комфортно | 10M+ документов, миллионы векторов | **Postgres** при > 100K |
| 17 | Переход на другой backend | Возможен через DAL | Возможен через DAL | Ничья |
| 18 | RAM footprint | < 50 MB | 100+ MB постоянно (даже idle) | **SQLite** |
| 19 | Ремонт коррупции | `PRAGMA integrity_check` + restore из markdown | `pg_resetwal` + restore | Ничья |
| 20 | Ecosystem-стабильность | SQLite — самый широко используемый DB в мире | Postgres — самый используемый OSS RDBMS | Ничья |

**Сводный счёт**: 9–4 в пользу SQLite для текущего use-case. Postgres строго лучше, если корпус **> 100K документов** ИЛИ multi-user team setup.

---

## 3. Side-by-side эквивалентность DDL

Для каждого SQLite-only паттерна — Postgres-эквивалент. Это базис DAL: бизнес-логика остаётся одинаковой, меняется только executor.

### 3.1 Базовые таблицы (одинаковы, generic SQL)

Таблицы `entities`, `entity_aliases`, `pages`, `page_entity_refs`, `interactions`, `extracted_items`, `batch_runs`, `source_state` — определены в [SCHEMA-DRAFT.sql](./archive/SCHEMA-DRAFT.sql) одинаковым ANSI SQL. Различия:

- В SQLite: `TEXT` для timestamps + `metadata_json` (validation в коде).
- В Postgres: `TIMESTAMPTZ` + `JSONB` + check constraints.

**Адаптер DAL** при INSERT'е сериализует/десериализует timestamps; при SELECT'е возвращает уже стандартный `datetime`.

### 3.2 Полнотекстовый поиск

#### SQLite (FTS5)

```sql
CREATE VIRTUAL TABLE pages_fts USING fts5(
    slug UNINDEXED,
    title,
    tldr,
    body_excerpt,
    tags,
    content='pages',
    tokenize='unicode61 remove_diacritics 2'
);

-- Query
SELECT slug, snippet(pages_fts, 2, '<b>', '</b>', '...', 32)
FROM pages_fts
WHERE pages_fts MATCH 'shadow ai OR теневой'
ORDER BY rank LIMIT 20;
```

#### Postgres (tsvector + GIN)

```sql
ALTER TABLE pages ADD COLUMN tsv tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('simple', coalesce(title, '')),       'A') ||
        setweight(to_tsvector('simple', coalesce(tldr, '')),        'B') ||
        setweight(to_tsvector('simple', coalesce(body_excerpt,'')), 'C') ||
        setweight(to_tsvector('simple', coalesce(
            jsonb_path_query_array(frontmatter_json::jsonb, '$.tags[*]')::text, ''
        )), 'D')
    ) STORED;

CREATE INDEX idx_pages_tsv ON pages USING GIN(tsv);

-- Query
SELECT slug,
       ts_headline('simple', body_excerpt, q, 'StartSel=<b>, StopSel=</b>') AS snippet
FROM pages, plainto_tsquery('simple', 'shadow ai теневой') q
WHERE tsv @@ q
ORDER BY ts_rank(tsv, q) DESC
LIMIT 20;
```

**Семантическая эквивалентность**: оба варианта поддерживают AND/OR/NOT операторы, ranking, snippet/headline. Различия:

- FTS5 быстрее на embedded use-case (< 10ms median на 100K).
- Postgres мощнее на корпусах > 1M (GIN-индекс лучше масштабируется).

### 3.3 Vector search

#### SQLite (sqlite-vec)

```sql
CREATE VIRTUAL TABLE page_embeddings USING vec0(
    page_rowid INTEGER PRIMARY KEY,
    embedding FLOAT[384]
);

-- Insert (через адаптер; Python: vec_f32([0.1, 0.2, ...]))
INSERT INTO page_embeddings(page_rowid, embedding) VALUES (?, ?);

-- Query (cosine similarity, brute-force)
SELECT p.slug, p.title,
       vec_distance_cosine(pe.embedding, ?) AS distance
FROM page_embeddings pe
JOIN pages p ON p.rowid = pe.page_rowid
ORDER BY distance LIMIT 10;
```

**Performance**: 100K × 384-dim — < 100ms; 100K × 1536-dim — ~500ms; 1M+ — секунды.

#### Postgres (pgvector + HNSW)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE pages ADD COLUMN embedding vector(384);

CREATE INDEX idx_pages_embedding ON pages
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Query
SELECT slug, title, embedding <=> ?::vector AS distance
FROM pages
ORDER BY embedding <=> ?::vector
LIMIT 10;
```

**Performance**: HNSW даёт sub-linear scaling; на 1M × 1536-dim — 10–50ms, 5–15K QPS на single node.

**Когда переключаться на Postgres**: если корпус > 100K векторов **или** dimension > 768 **или** требуется > 100 QPS vector search.

### 3.4 Fuzzy match (для entity resolution)

#### SQLite (TypeScript Levenshtein, как в cybos)

```typescript
// Cybos pattern: scripts/db/entity-resolver.ts
function fuzzyMatchEntity(name: string, candidates: Entity[]): Entity | null {
    let best: { entity: Entity, score: number } | null = null;
    for (const cand of candidates) {
        const namesToCheck = [cand.name, ...cand.aliases.map(a => a.alias)];
        for (const n of namesToCheck) {
            const sim = levenshteinSimilarity(name.toLowerCase(), n.toLowerCase());
            if (sim > 0.7 && (!best || sim > best.score)) {
                best = { entity: cand, score: sim };
            }
        }
    }
    return best?.entity ?? null;
}
```

**Performance**: O(N) per resolve — для < 10K entities приемлемо. Кэшировать результаты в session.

#### Postgres (pg_trgm)

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_entities_name_trgm ON entities USING GIN(name gin_trgm_ops);
CREATE INDEX idx_aliases_alias_trgm ON entity_aliases USING GIN(alias gin_trgm_ops);

-- Query: найти entity по похожему имени
SELECT slug, name, similarity(name, ?) AS sim
FROM entities
WHERE name % ?                                    -- % = trigram match operator
ORDER BY sim DESC
LIMIT 5;
```

**Performance**: индексированно — < 5ms на 100K entities.

### 3.5 JSON queries

#### SQLite

```sql
-- Pages с тегом 'management'
SELECT slug, title FROM pages
WHERE EXISTS (
    SELECT 1 FROM json_each(json_extract(frontmatter_json, '$.tags'))
    WHERE value = 'management'
);

-- Без индекса = O(N). С computed column можно индексировать одно поле:
ALTER TABLE pages ADD COLUMN tags_json TEXT GENERATED ALWAYS AS (json_extract(frontmatter_json, '$.tags')) VIRTUAL;
CREATE INDEX idx_pages_tags ON pages(tags_json);
```

#### Postgres

```sql
-- Pages с тегом 'management' — c GIN-индексом O(log N)
CREATE INDEX idx_pages_fm_gin ON pages USING GIN((frontmatter_json::jsonb -> 'tags'));

SELECT slug, title FROM pages
WHERE frontmatter_json::jsonb -> 'tags' @> '["management"]'::jsonb;
```

---

## 4. DAL pattern: единый `IndexRepository` interface

Цель — переключение backend через config, без изменения бизнес-логики скиллов.

### 4.0 Фактическая раскладка (TASK 056) и mirror-конвенция для Postgres

Код ниже в §4.1–4.4 — исторические иллюстративные наброски (имена `sqlite_repo.py` /
`postgres_repo.py` устарели). **Фактическая** реализация: `IndexRepository` ABC в
`scripts/wiki_index/repository.py` и SQLite-backend как **доменный пакет**
`scripts/wiki_index/sqlite_repository/` (TASK 056) — per-table-family mixin-модули,
собранные в один класс; путь импорта заморожен
(`from scripts.wiki_index.sqlite_repository import SQLiteRepository`).

**Mirror-конвенция**: будущий Postgres-backend создаётся как пакет
`scripts/wiki_index/postgres_repository/`, зеркалящий ту же по-доменную раскладку поверх
`psycopg`, + ветка `backend:` в `factory.make_repo`. Каждый модуль SQLite-пакета несёт
`dialect:`-тег в docstring — карта того, что переносится как есть, а что переписывается:

| Модуль | Диалект | Postgres-замена |
|---|---|---|
| `_base.py` | SQLite-only: PRAGMA-блок (WAL/…), `user_version`-DDL | psycopg pool + session config |
| `_search.py` | SQLite-only ядро: FTS5 `MATCH`/`bm25()`/`snippet()`, `json_extract`/`json_each` | tsvector + `ts_rank`/`ts_headline` + `jsonb` (§3.2) |
| `_health_rules.py`, `_health_scan.py`, `_state.py` | смешанный: формы запросов портируемы, `json_extract`/`json_each`/`json_type` → `jsonb`-операторы | `->`/`->>`/`jsonb_typeof`/`jsonb_array_elements` |
| `_vaults.py`, `_pages.py`, `_refs_graph.py`, `_events.py`, `_entities.py`, `_merge.py` | generic SQL (ON CONFLICT DO UPDATE — общий синтаксис) | как есть (меняется только драйвер/placeholder) |

**Явный non-goal (TASK 056 R6c): код `PostgresRepository` в задаче 056 НЕ создаётся** —
только Postgres-ready форма пакета и эта карта диалектов. Триггеры перехода — §7.

### 4.1 Python (рекомендуется для wiki-* скиллов)

```python
# scripts/wiki_index/repository.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class PageHit:
    slug: str
    project: Optional[str]
    title: str
    score: float
    snippet: Optional[str] = None

@dataclass
class Entity:
    slug: str
    type: str
    name: str
    definition: Optional[str]
    aliases: list[str]
    primary_email: Optional[str]
    telegram_handle: Optional[str]
    is_candidate: bool
    mentions_count: int

class IndexRepository(ABC):
    """Generic interface, реализуется для SQLite и Postgres одинаково."""

    # ── Pages ────────────────────────────────────────────────────────────
    @abstractmethod
    def upsert_page(self, slug: str, project: Optional[str], **fields) -> None: ...

    @abstractmethod
    def get_page(self, slug: str, project: Optional[str]) -> Optional[dict]: ...

    @abstractmethod
    def search_pages(
        self, query: str, *,
        project: Optional[str] = None,
        types: Optional[list[str]] = None,
        limit: int = 20,
    ) -> list[PageHit]: ...

    @abstractmethod
    def search_pages_vector(
        self, embedding: list[float], *,
        project: Optional[str] = None,
        limit: int = 10,
    ) -> list[PageHit]: ...

    # ── Entities ─────────────────────────────────────────────────────────
    @abstractmethod
    def resolve_entity(
        self, *,
        name: Optional[str] = None,
        email: Optional[str] = None,
        telegram_handle: Optional[str] = None,
        type_hint: Optional[str] = None,
        fuzzy_threshold: float = 0.7,
    ) -> Optional[Entity]: ...

    @abstractmethod
    def upsert_entity(self, entity: Entity) -> None: ...

    @abstractmethod
    def find_duplicates(self, threshold: float = 0.85) -> list[tuple[Entity, Entity]]: ...

    # ── Lint ─────────────────────────────────────────────────────────────
    @abstractmethod
    def find_orphan_links(self) -> list[dict]: ...

    @abstractmethod
    def find_pages_missing_in_index(self, vault_root: str) -> list[str]: ...

    # ── Reindex ──────────────────────────────────────────────────────────
    @abstractmethod
    def begin_batch_run(self, mode: str) -> int: ...

    @abstractmethod
    def finish_batch_run(self, run_id: int, status: str, **stats) -> None: ...

    @abstractmethod
    def last_batch_run(self) -> Optional[dict]: ...
```

### 4.2 SQLite-реализация (default)

```python
# scripts/wiki_index/sqlite_repo.py
import sqlite3
from pathlib import Path

class SQLiteRepository(IndexRepository):
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.row_factory = sqlite3.Row
        # Опционально: load sqlite-vec extension
        try:
            self._conn.enable_load_extension(True)
            self._conn.load_extension("sqlite-vec")
            self._has_vec = True
        except sqlite3.OperationalError:
            self._has_vec = False

    def search_pages(self, query, *, project=None, types=None, limit=20):
        sql = """
            SELECT p.slug, p.project, p.title,
                   bm25(pages_fts) AS score,
                   snippet(pages_fts, 2, '<b>', '</b>', '...', 16) AS snippet
            FROM pages_fts
            JOIN pages p ON p.rowid = pages_fts.rowid
            WHERE pages_fts MATCH ?
        """
        params = [query]
        if project:
            sql += " AND p.project = ?"
            params.append(project)
        if types:
            placeholders = ",".join("?" * len(types))
            sql += f" AND p.type IN ({placeholders})"
            params.extend(types)
        sql += " ORDER BY score LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [PageHit(**dict(r)) for r in rows]

    def resolve_entity(self, *, name=None, email=None, telegram_handle=None,
                       type_hint=None, fuzzy_threshold=0.7):
        # Stage 2: email exact
        if email:
            row = self._conn.execute(
                "SELECT * FROM entities WHERE primary_email = ? LIMIT 1", (email,)
            ).fetchone()
            if row: return self._row_to_entity(row)
        # Stage 3: telegram exact
        if telegram_handle:
            row = self._conn.execute(
                "SELECT * FROM entities WHERE telegram_handle = ? LIMIT 1", (telegram_handle,)
            ).fetchone()
            if row: return self._row_to_entity(row)
        # Stage 4: fuzzy by name (in Python, since no pg_trgm in SQLite)
        if name:
            return self._fuzzy_match_python(name, type_hint, fuzzy_threshold)
        return None

    # ... (полная реализация ~400 строк)
```

### 4.3 Postgres-реализация (opt-in)

```python
# scripts/wiki_index/postgres_repo.py
import psycopg

class PostgresRepository(IndexRepository):
    def __init__(self, dsn: str):
        self.dsn = dsn
        self._conn = psycopg.connect(dsn, autocommit=False)

    def search_pages(self, query, *, project=None, types=None, limit=20):
        sql = """
            SELECT slug, project, title,
                   ts_rank(tsv, q) AS score,
                   ts_headline('simple', body_excerpt, q, 'StartSel=<b>,StopSel=</b>') AS snippet
            FROM pages, plainto_tsquery('simple', %s) q
            WHERE tsv @@ q
        """
        params = [query]
        if project is not None:
            sql += " AND project = %s"
            params.append(project)
        if types:
            sql += " AND type = ANY(%s)"
            params.append(types)
        sql += " ORDER BY score DESC LIMIT %s"
        params.append(limit)
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            return [PageHit(*r) for r in cur.fetchall()]

    def resolve_entity(self, *, name=None, email=None, telegram_handle=None,
                       type_hint=None, fuzzy_threshold=0.7):
        # Postgres pg_trgm path: одним запросом найти лучшего кандидата
        with self._conn.cursor() as cur:
            if email:
                cur.execute("SELECT * FROM entities WHERE primary_email = %s LIMIT 1", (email,))
                row = cur.fetchone()
                if row: return self._row_to_entity(row)
            if telegram_handle:
                cur.execute("SELECT * FROM entities WHERE telegram_handle = %s LIMIT 1", (telegram_handle,))
                row = cur.fetchone()
                if row: return self._row_to_entity(row)
            if name:
                cur.execute("""
                    SELECT *, similarity(name, %s) AS sim FROM entities
                    WHERE name %% %s
                    ORDER BY sim DESC LIMIT 1
                """, (name, name))
                row = cur.fetchone()
                if row and row[-1] >= fuzzy_threshold:
                    return self._row_to_entity(row)
        return None

    # ... (полная реализация ~400 строк)
```

### 4.4 Factory + config

```python
# scripts/wiki_index/factory.py
def make_repo(config: dict) -> IndexRepository:
    backend = config["wiki"]["index"]["backend"]
    if backend == "sqlite":
        path = Path(config["wiki"]["index"]["location"]["sqlite"]["path"]).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        return SQLiteRepository(path)
    elif backend == "postgres":
        dsn = config["wiki"]["index"]["location"]["postgres"]["url"]
        return PostgresRepository(dsn)
    raise ValueError(f"unknown index backend: {backend}")
```

Теперь все wiki-* скиллы:

```python
repo = make_repo(load_wiki_config())
hits = repo.search_pages("shadow ai", project="management-2026", limit=10)
```

— и всё одинаково работает на любом backend'е.

---

## 5. Critical workaround: SQLite + iCloud

### 5.1 Проблема

iCloud + SQLite = **гарантированная коррупция через 2-4 недели** на multi-device:

1. iCloud синкает бинарный файл побайтно. Если SQLite пишет в WAL/main одновременно с syncing — torn write.
2. WAL и shm файлы (`.db-wal`, `.db-shm`) расходятся между устройствами.
3. iCloud периодически evict'ает файлы (превращает в `.icloud` placeholder) — `sqlite3.connect()` блокируется на скачивание или падает.
4. Concurrent writes из разных устройств — last-writer-wins на CloudKit без слияния.

### 5.2 Решение

**SQLite-файл хранится вне iCloud**:

| Платформа | Default path |
|---|---|
| macOS | `~/Library/Application Support/wiki-index/<vault_hash>.db` |
| Linux | `~/.local/share/wiki-index/<vault_hash>.db` |
| Windows | `%LOCALAPPDATA%\wiki-index\<vault_hash>.db` |

Где `<vault_hash>` = `sha256(absolute_vault_root_path)[:12]`.

`wiki-init` детектирует iCloud-путь vault'а (любой путь, содержащий `Mobile Documents/iCloud~`), и **forces** DB-путь вне iCloud, warn-печатает пользователю.

### 5.3 Multi-device behavior

- **Mac** имеет свой DB локально, читает markdown из iCloud, периодически делает `wiki-reindex`.
- **iPad/iPhone** имеет свой DB локально (через Obsidian Mobile + iSH/Pythonista для скриптов, либо просто просматривает markdown).
- DB-расхождения между устройствами **нормальны** — DB пересобирается из markdown за секунды. Это `derivative cache`, не source-of-truth.

### 5.4 Postgres избегает этой проблемы целиком

Если пользователь хочет multi-device share — Postgres на домашнем сервере (Mac mini / NAS / Raspberry Pi) + Tailscale. Все устройства подключаются к одному DB. Это уже power-user setup.

---

## 6. Performance budget

| Операция | SQLite (default) | Postgres (opt-in) |
|---|---|---|
| `search_pages("term")` на 1K docs | < 5ms | < 10ms |
| `search_pages("term")` на 100K docs | < 50ms | < 20ms |
| `resolve_entity(email=)` на 10K | < 1ms | < 1ms |
| `resolve_entity(name=, fuzzy)` на 10K | < 50ms (Python Levenshtein) | < 5ms (pg_trgm) |
| `find_orphan_links()` на 1K pages | < 100ms | < 50ms |
| `find_orphan_links()` на 100K pages | < 5s | < 1s |
| `search_pages_vector` 100K × 384 | < 100ms | < 5ms (HNSW) |
| Full reindex 1K markdown files | < 5s | < 30s |
| Full reindex 100K markdown files | < 5min | < 5min |

**Verification**: бенчмарк-скрипт `scripts/wiki_index/benchmark.py` (см. TASK-ref-v2.md §28) генерирует synthetic vault по N-параметру и проверяет SLO.

---

## 7. Когда переключаться SQLite → Postgres

Triggers (любой сработавший):

1. **Корпус > 100K документов** — SQLite FTS5 продолжит работать, но vector-search и lint начинают тормозить.
2. **Vector dim > 768 + > 50K документов** — sqlite-vec brute-force становится узким местом, нужен HNSW.
3. **Multi-user team vault** — concurrent ingest writers требуют MVCC.
4. **Need network access из нескольких машин** — Postgres elegant solution.
5. **Heavy fuzzy match workload** — `pg_trgm` много быстрее Python Levenshtein.

Migration: `wiki-migrate sqlite-to-postgres --vault <name>`.

1. Создать пустую Postgres DB + расширения.
2. Прогнать `wiki-reindex --backend postgres --full` — markdown заново индексируется в Postgres.
3. (Никакие данные не теряются — markdown остаётся source-of-truth.)
4. Изменить `wiki.index.backend: postgres` в `CLAUDE.md`.
5. Удалить старый SQLite-файл.

---

## 8. Anti-patterns

| ❌ Не делать | Почему |
|---|---|
| Хранить SQLite-файл в iCloud-vault | Коррупция, see §5 |
| Вводить «единственный backend» в публичный API скиллов | Ломает opt-in Postgres |
| Использовать ORM (SQLAlchemy/Prisma) | Усложняет ничего; raw SQL + 2 repository классов проще |
| Дублировать схему между backend'ами | Держать generic SQL в одном месте, per-backend addons отдельно |
| Pgvector с default параметрами (m=8, ef=20) | На реальном корпусе recall падает; ставить m=16, ef_construction=64 минимум |
| Включать sqlite-vec по default'у | Extension нужен только для semantic search; YAGNI на старте |
| Делать индекс vault-shared между устройствами через Dropbox/iCloud | Та же проблема что iCloud — бинарный sync ломает SQLite |

---

## 9. References

- [SQLite FTS5 documentation](https://www.sqlite.org/fts5.html)
- [sqlite-vec on GitHub](https://github.com/asg017/sqlite-vec)
- [pgvector on GitHub](https://github.com/pgvector/pgvector)
- [Cybos architecture](https://github.com/Gerstep/cybos/blob/main/docs/ARCHITECTURE.md) — proven SQLite+FTS5 для multi-source personal AI
- [Vector DB benchmarks 2026](https://callsphere.ai/blog/vector-database-benchmarks-2026-pgvector-qdrant-weaviate-milvus-lancedb)
- [SQLite WAL mode](https://www.sqlite.org/wal.html)

---

## 10. Итог

- **Default = SQLite** для personal Obsidian wiki — простота, embedded, iOS, proven в cybos.
- **Postgres** как opt-in через DAL — для тех, кто перерос SQLite или нуждается в pgvector+HNSW / pg_trgm.
- **Объединение** через `IndexRepository` interface: одна бизнес-логика, два executors.
- **iCloud-критично**: SQLite-файл всегда вне iCloud, markdown остаётся в iCloud.
