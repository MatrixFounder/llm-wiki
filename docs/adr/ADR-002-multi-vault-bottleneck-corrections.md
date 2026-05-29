# ADR-002: Multi-Vault Single-DB + Log/Index Bottleneck Corrections

- **Status**: Accepted (2026-05-26)
- **Decider**: innokentiy.georgievskiy@mdcloud.tech
- **Supersedes**: nothing (extends [ADR-001](./ADR-001-wiki-ingest-integration.md))
- **Empirical basis**: `trade-agents/Lessons/ZeroOne Systems/` — real-world ingest of 13 lessons producing 35 concepts + 58 entities + 13 sources; 22,743 lines / ~1.2 MB markdown; log.md = 23 events / 195 lines.
- **Related**: [trade-agents/docs/wiki-ingest-promotion-spec.md](../../trade-agents/docs/wiki-ingest-promotion-spec.md) — two-tier vault model (course-local + vault-root).

## Context

После реального использования `wiki-ingest` v1.0 на `trade-agents/` обнаружены конкретные bottleneck'и, которые в спецификации MVP не были адресованы:

### Empirical bottlenecks (root cause analysis)

| # | Bottleneck | Root cause | Сейчас | При 1000 concepts |
|---|---|---|---|---|
| B1 | Read-amplification на ingest | O(N) filesystem scan + YAML parse каждого concept page в Phase 1 | ~500ms (93 файла) | ~5s |
| B2 | Known-concepts token cost | Wiki-ingest передаёт full concept-list в `summarizing-meetings` context | ~4K tokens | ~60-200K tokens/ingest |
| B3 | log.md grep linear scan | Append-only Markdown, no structured query | OK (195 lines) | OK для grep, плохо для "events for concept X" / period queries |
| B4 | index.md hot-path read | Human-readable Markdown с definitions; LLM читает на каждом ingest | ~4K tokens | ~30K tokens |
| B5 | Lint O(N²) | Orphan detection: every wiki-link × every page | ~100ms (10K ops) | ~10s (1M ops) |
| B6 | Multi-vault visibility | wiki-ingest single-vault; cross-vault overlap detection отсутствует | N/A | Critical при 3+ vaults |

### Multi-vault constraint (new)

Пользователь работает с несколькими Obsidian vaults параллельно (`trade-agents/`, `obsidian-llm-wiki/`, future `personal-research/`). Требование:

- **Один SQLite-файл серверит все vaults** (не per-vault DB)
- **Partition by `vault_id`** на уровне schema
- **Cross-vault queries возможны** через `WHERE vault_id IN (...)`
- **Per-vault изоляция данных** через composite PK

## Decision

### D1. Single global DB с `vault_id` partitioning

Один файл: `~/Library/Application Support/wiki-index/global.db` (платформенный default). Все data-таблицы получают `vault_id TEXT NOT NULL`. Composite PKs:
- `pages`: `(vault_id, slug, project)`
- `entities`: `(vault_id, slug)`
- `page_entity_refs`: `(vault_id, page_slug, page_project, entity_slug, ref_type)`
- `source_state`: `(vault_id, source_kind, scope, key)`

Новая таблица `vaults` — registry: `vault_id`, `name`, `root_path` (UNIQUE), `schema_version`, `last_ingest_at`, `ingest_count`, `config_json`. `wiki-init` создаёт row.

`vault_id` derivation: **REQUIRED explicit** field в root `WIKI_SCHEMA.md`. **No hash fallback** (см. D1.1 ниже — fail-fast принят как UX-decision 2026-05-26).

### D1.1. `vault_id` REQUIRED explicit (fail-fast, no fallback)

**Decision (2026-05-26)**: `WIKI_SCHEMA.md` v2.0+ ОБЯЗАН содержать `vault_id` в frontmatter. Hash-derivation fallback **отвергнут** — приводит к silent drift при переименовании vault folder.

**Schema constraint**:

```yaml
---
name: WIKI_SCHEMA (root)
schema_version: 2.0
vault_id: trade-agents              # REQUIRED — stable identity across folder renames
description: ...
---
```

**Format constraints**:
- Pattern: `^[a-z][a-z0-9-]{2,31}$` (letter-start, kebab-case, length 3-32, no leading digit/hyphen)
- DB-unique across `vaults.vault_id` (PK enforces)
- Идиоматично: derived from vault folder name (manual slug — `trade-agents/` → `vault_id: trade-agents`), но **explicit, не auto-computed**

**Fail-fast scenarios** (wiki-ingest и MVP должны прервать execution с понятным error):

| Scenario | Error | Suggested fix |
|---|---|---|
| `WIKI_SCHEMA.md` отсутствует | `MISSING_WIKI_SCHEMA` | `wiki-ingest init <vault>` |
| `WIKI_SCHEMA.md` есть, но без `vault_id` | `MISSING_VAULT_ID` + `suggested_vault_id: <slug-from-folder>` | Add `vault_id: <slug>` в frontmatter (one-line edit) |
| `vault_id` не соответствует pattern | `INVALID_VAULT_ID` + spec | Rename to kebab-case |
| `vault_id` exists в `vaults` table с другим `root_path` | `VAULT_ID_COLLISION` + existing path | Pick different slug ИЛИ migrate existing vault |
| `vault_id` changed между ingests (existing row points to different vault_id для этого root_path) | `VAULT_RENAMED` warning + reconciliation prompt | Operator confirms rename → UPDATE registry row |

**Migration for existing vaults** (e.g., `trade-agents/`):
1. **Operator** adds `vault_id: <slug>` в `WIKI_SCHEMA.md` frontmatter (one-line edit, не touched by tooling — manual chose-name step).
2. **First post-edit ingest** или `wiki-init --register-existing` — registers `(vault_id, root_path, schema_version, ingest_count из existing log.md)` в `vaults` table.
3. **Backfill** sweep — все historic `_sources/`/`_concepts/`/`_entities/` indexed в SQLite с этим `vault_id`.

**Recommended slug rule** (для UX consistency, не enforce'ится tooling'ом): operator пишет slug = `kebab(folder_basename)`. Если folder будет переименован, `vault_id` остаётся прежним — это intentional.

All existing indexes prefix'аются `vault_id` для partition pruning. FTS5 contentless tables содержат `vault_id` как UNINDEXED column для `WHERE vault_id = ?` фильтрации.

### D2. `log_events` table — structured mirror of log.md

Каждый event в log.md имеет parallel row в SQLite:

```sql
CREATE TABLE log_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  vault_id TEXT NOT NULL REFERENCES vaults(vault_id),
  event_ts TEXT NOT NULL,
  event_type TEXT NOT NULL CHECK (event_type IN (
    'ingest','query','lint','reindex','promote','demote',
    'backfill','reclassify','resolve-contradiction','fix-dangling','fix-orphan'
  )),
  subject TEXT,
  pages_created_json TEXT,
  pages_touched_json TEXT,
  contradictions_count INTEGER DEFAULT 0,
  details_json TEXT,
  log_md_byte_offset INTEGER
);
CREATE INDEX idx_log_vault_ts ON log_events(vault_id, event_ts DESC);
CREATE INDEX idx_log_event_type ON log_events(vault_id, event_type, event_ts DESC);
```

**log.md остаётся** (Karpathy canon, Obsidian-friendly, git-friendly). Записываются **оба** атомарно через wiki-ingest manifest emission + MVP indexer.

Решает B3. Новые queries < 10ms: "events для concept X", "contradictions per vault", "ingests in last 7 days across all vaults".

### D3. `index_meta` view + `entities`/`pages` queries replace index.md scan

LLM известно-concepts list ВСЕГДА получается через SQL:

```sql
SELECT slug, name FROM entities WHERE vault_id = ?;        -- < 5ms
SELECT slug, title FROM pages WHERE vault_id = ? AND kind IN ('concept','entity');
```

**index.md остаётся** rebuildable view (R-08 wiki-index-render); Obsidian Graph и человек читают markdown, LLM hot-path стучит в SQLite.

Решает B2 + B4. Token cost снижается с ~4K (full markdown) до ~500 tokens (slug + title only). Read latency < 5ms.

### D4. Pre-computed lint queries

Все 9 lint checks (R-11) переписываются на SQL. Orphan detection = LEFT JOIN на `page_entity_refs` × `pages` — O(N) с индексом.

Решает B5.

### D5. Cross-vault search

`wiki-search` принимает `--vaults <slug1,slug2,...>` (default = all vaults). FTS5 query:

```sql
SELECT vault_id, slug, title, bm25(pages_fts) AS score, snippet(...)
FROM pages_fts
JOIN pages USING (vault_id, slug, project)
WHERE pages_fts MATCH ?
  AND (? IS NULL OR vault_id IN (?))   -- vault filter
ORDER BY score LIMIT ?;
```

Также: cross-vault concept-overlap detection (suggest promotion candidate когда concept появляется в ≥ 2 vaults):

```sql
SELECT slug, COUNT(DISTINCT vault_id) AS vault_count
FROM entities GROUP BY slug HAVING vault_count >= 2;
```

Решает B6.

### D6. Three-tier scoping (multi-vault + promotion-spec)

Promotion-spec вводит two-tier (course-local + vault-root). Multi-vault добавляет третий уровень:

| Tier | Scope | Schema representation |
|---|---|---|
| 3 — Cross-vault | Across multiple vaults (search-only union; no auto-promotion) | Different `vault_id` rows |
| 2 — Vault-root (shared) | Concepts shared across courses within one vault | `(vault_id=X, project='_vault_')` |
| 1 — Course-local | Concepts specific to one course | `(vault_id=X, project='<course>')` |

`promote` operation = `UPDATE pages SET project='_vault_' WHERE vault_id=? AND slug=?` + file move (атомарно в transaction).

### D7. SQLite остаётся default; Postgres opt-in через DAL

Re-evaluation matrix (см. [SQLITE-VS-POSTGRES.md](../SQLITE-VS-POSTGRES.md)) при multi-vault personal-use scale:

- 5 vaults × 1K concepts = 5K total → SQLite trivially handles
- 10 vaults × 5K concepts = 50K → SQLite < 30ms search
- 20 vaults × 10K concepts = 200K → SQLite < 100ms, Postgres < 30ms (с HNSW)

Postgres становится правильным выбором, если **любое** из:
1. Personal-use перешагнул 100K concepts (5+ лет работы при текущем темпе)
2. Multi-device shared DB critical (Tailscale + Mac mini / NAS)
3. Team setup (несколько ingestors одновременно)
4. Heavy vector workload (cross-vault semantic search at scale)

Single-user personal scale (5-10 vaults × 1K concepts текущие 12-18 месяцев) — SQLite remains.

### D8. Data Layering Contract (Vault canonical, DB rebuildable cache)

**Core invariant**: vault (markdown) = canonical source of truth; DB = 100% rebuildable cache. Алгоритм `wiki-reindex --full` восстанавливает всю функциональность БД из файлов без потери семантики. Единственное исключение — `vaults.registered_at` (approximated from earliest `log_events.event_ts`).

> **Amendment (TASK 005, schema v2→v3 — 2026-05-29).** Epic 7 R-4/R-5 add
> two Class-A facts to entity-page frontmatter and one DB-schema change:
> - **`is_candidate: true|false`** and **`aliases: [...]`** in `_concepts/`/`_entities/`
>   frontmatter are **Class A canonical**; the `entities.is_candidate` column and
>   the `entity_aliases` table are their **Class B mirrors** (rebuilt by
>   `wiki-reindex --full`, which now *reads* both — closing a prior round-trip gap
>   where reindex reset every candidate to confirmed and never mirrored aliases).
> - **`entity_aliases` PK `(vault_id, alias, entity_slug)` → `(vault_id, alias)`**
>   (closes KNOWN_ISSUES **L-4**; `idx_aliases_lookup` dropped, `idx_aliases_entity`
>   added; `PRAGMA user_version` 2→3). Because the DB is a Class B rebuildable cache,
>   the migration is a **`wiki-reindex --full`**, NOT an in-place `ALTER`
>   (`apply_schema`'s `CREATE TABLE IF NOT EXISTS` cannot mutate a live PK). On
>   rebuild, aliases reconstruct from Class A frontmatter under the new PK; any
>   surviving collision is surfaced (report-and-skip, never silent `INSERT OR IGNORE`).
> - **Merge** (`wiki-merge`, R-4.7) is expressed entirely in Class A — the duplicate
>   page is deleted and its surfaces become aliases of the survivor — so it needs no
>   merge-ledger table and survives a full rebuild. Reindex canonicalizes
>   `page_entity_refs.entity_slug` through the alias table at build time (AM-3) so
>   mention counts / backlinks stay correct across a rebuild.
>
> **Amendment (TASK 006, schema v3→v4 — 2026-05-29).** Three Class-B DDL hygiene
> changes, same rebuild contract (no in-place `ALTER`; migrate via
> `wiki-reindex --full`; bump `PRAGMA user_version` 3→4):
> - **Drop** the dead `idx_pages_vault_tags` functional index (P-5 — indexed a
>   JSON-array string nothing queried; tags route through `pages_fts.tags`).
> - **`log_events.event_date`** becomes a **STORED generated column**
>   (`GENERATED ALWAYS AS (substr(event_ts,1,10)) STORED`, L-2) — a schema-level
>   guarantee replacing inserter discipline. It is **Class B** (still rederived on
>   reindex from `event_ts`); `idx_log_vault_date` indexes the generated column.
>   A STORED generated column cannot be `ALTER`-added to a populated table, so the
>   rebuild path is mandatory (reinforces the no-ALTER rule). (L-5 — the dead
>   `pages.type='log'` enum value — was already absent from the current schema;
>   no change needed, ledger entry closed.)
>
> **Amendment (TASK 008, schema v4→v5 — 2026-05-29).** Epic 7 R-8
> (`wiki-verify-multi`) adds a first-class `_verifications/<slug>.md` **verdict
> page** — the first RAG-layer task that requires DDL (R-6's `query`/`cited`/
> `query`-event were pre-provisioned; the verdict-page type/ref/event are not).
> Four **CHECK-enum / view** edits, **same Class-B rebuild contract** (no in-place
> `ALTER`; bump `PRAGMA user_version` 4→5):
> - `pages.type` CHECK `+= 'verification'`; `page_entity_refs.ref_type` CHECK
>   `+= 'verifies'` (the verdict→query edge); `log_events.event_type` CHECK
>   `+= 'verify'`; `index_meta` view WHERE `+= 'verification'` (catalog parity).
> - **This is the first amendment that relaxes a CHECK enum** (vs the v2→v3 PK
>   change and v3→v4 generated-column/index changes). SQLite **cannot
>   `ALTER`-relax a CHECK constraint** on a populated table.
> - **Precise migration procedure for an EXISTING populated v4 DB** (corrected per
>   the TASK 008 adversarial-plan review, DUR-2 — the prior amendments' bare
>   "migrate via `wiki-reindex --full`" wording was imprecise): the schema DDL is
>   `CREATE TABLE IF NOT EXISTS`, and `wiki-reindex --full` only `DELETE`s+re-`INSERT`s
>   *rows* — **neither recreates the table**, so on a live DB the old v4 CHECK
>   persists and a `verification` insert raises `IntegrityError`. The migration is
>   therefore **delete the `.db`/`-wal`/`-shm` files first** (so the next
>   `make_repo`/`apply_schema_if_missing` applies the fresh v5 DDL), **then
>   `wiki-init --register-existing`** (the `vaults` row was wiped with the DB)
>   **+ `wiki-reindex --full`** (repopulate from Class A). This is legitimate
>   because the DB is **Class B rebuildable** — there is **no in-place auto-reseed**
>   keyed on `user_version` in the codebase. The verdict page's `pages` row + its
>   `verifies` (+ optional `cited`) refs reconstruct from the
>   `_verifications/<slug>.md` Class-A frontmatter via the R-8.5e reindex read-side
>   (the `verifies:`→`'verifies'` analog of R-6.5e's `cites:`→`'cited'`).
>   `source_state` (`source_kind='verification'`) verify-idempotency is Class C
>   (no DDL). *(The same delete-then-rebuild procedure applies to the v2→v3 and
>   v3→v4 amendments above, whose "wiki-reindex --full" shorthand carried the same
>   imprecision; recorded here for accuracy.)*

Все данные классифицируются по трём классам с чётким правилом расположения:

#### Class A — Vault-only (semantic canonical, никогда не дублируется в БД as semantic)

| Артефакт | Где живёт | Rationale |
|---|---|---|
| `WIKI_SCHEMA.md` content (incl. `vault_id`) | `<vault>/WIKI_SCHEMA.md` | Convention; читается на init / register |
| Concept-page body (facts, definitions, contradictions) | `<vault>/_concepts/<slug>.md` | Human-readable, git-versioned, Obsidian-rendered |
| Entity-page body | `<vault>/_entities/<slug>.md` | Same |
| Source-page body (summaries) | `<vault>/_sources/<slug>.md` | Same |
| `## Contradictions` blocks | в теле concept/entity pages | Human-resolved, git-trackable; operator видит в Obsidian |
| Footnote definitions `[^src-foo]: [[...]] — Title` | в теле concept/entity pages | Provenance line — Obsidian-renderable, manually citable |
| `index.md` rendered view | `<vault>/index.md` | Human catalog для Obsidian; LLM hot-path читает из БД, не отсюда |
| `log.md` rendered view | `<vault>/log.md` | Human + grep-friendly + git-diffable |

**Test**: если удалить DB и запустить `wiki-reindex --full`, все Class-A артефакты остаются нетронутыми. Если что-то требует DB-only данных для рендеринга — это нарушение Class A.

#### Class B — Vault-canonical + DB-mirrored (vault wins on conflict)

| Артефакт | Vault representation (canonical) | DB representation (cache) | Назначение DB |
|---|---|---|---|
| `vault_id` | `WIKI_SCHEMA.md::vault_id` | `vaults.vault_id` PK | Partition key |
| Page slug | filename `<slug>.md` | `pages.slug` / `entities.slug` | Lookups, FK targets |
| Frontmatter fields | YAML в файле | `pages.frontmatter_json` (cached parse) | Избежать re-parse на каждом query |
| Tags | `frontmatter.tags[]` | `json_extract(...)` индексирован | FTS5 фильтрация |
| Wiki-links `[[X]]` | parsed из body | `page_entity_refs` rows | Backlinks / orphan detection / O(N) lint |
| Footnote provenance | `[^src-foo]: ...` line | `page_entity_refs.source_quote/line_start/line_end` | Fast «кто цитирует X» |
| Log events | `log.md` block `## [date] event \| subject` | `log_events` row + `log_md_byte_offset` | Structured queries |
| File hash | computed from body | `pages.file_hash` (cached) | Idempotency без re-read |
| Body excerpt | first 500 chars body | `pages.body_excerpt` (cached) | FTS5 preview / snippet |

**Conflict resolution**: vault wins. `wiki-reindex --full` пересчитывает все Class-B строки из файлов. Manual DB edits затираются.

**Test для каждой колонки**: «Удалить колонку, перезапустить reindex, восстановится ли?» Да → Class B (cache). Нет → Class C.

#### Class C — DB-only operational metadata (минимальный набор, не семантика)

| Field | Назначение | Derivable? | Класс |
|---|---|---|---|
| `vaults.registered_at` | Когда MVP впервые увидел vault | Approximation из earliest `log_events.event_ts` | Class C strict (только этот!) |
| `vaults.ingest_count` | Сколько раз ingested | `SELECT COUNT(*) FROM log_events WHERE event_type='ingest'` | Class B (computed view, не stored) |
| `vaults.last_ingest_at` | Последний ingest | `SELECT MAX(event_ts)` | Class B (view) |
| `source_state.source_hash` | Idempotency для transcript adapter | Re-computable from source file (дорого для cloud transcripts) | Class C cache (recomputed on reindex) |
| FTS5 inverted index | BM25 search | Rebuilt from `pages_fts` trigger | Class B (cache) |

**Истинно Class C** после дисциплины — только `vaults.registered_at`. Всё остальное либо derive из markdown (Class B), либо computed view над Class B таблицами.

#### Anti-patterns (нарушают invariant — должны отвергаться в review)

| ❌ Anti-pattern | Почему плохо | Правильно |
|---|---|---|
| Хранить concept-page body только в DB | Markdown теряет source-of-truth статус; Obsidian → viewer-only | Body всегда в файле; DB хранит excerpt |
| Wiki-links только в БД через JOIN | Obsidian рендерит граф из файлов → пустой граф | `[[links]]` в body (canonical) + mirror в `page_entity_refs` (**L-7: verified consistent with the `page_entity_refs` Class-B design — not an anti-pattern violation, 2026-05-29**) |
| Contradictions только в DB | Operator не видит в Obsidian → не сможет resolve | `## Contradictions` блок в page body + flag в DB |
| Frontmatter только в DB | Файл перестаёт быть self-describing | YAML в файле + parsed JSON в DB cache |
| `wiki-ingest` write directly to DB без файла | Нарушение Karpathy canon | Always write file first → manifest emit → DB indexer следующим |

#### Reconciliation flow для rename (исходный edge case)

```
Old:    folder `trade-agents/`, vault_id `trade-agents`, registered в DB
Action: operator renames folder → `trading-research/`
Action: operator edits WIKI_SCHEMA.md::vault_id → `trading-research`

wiki-init --register-existing --vault /new/path:
  1. Read WIKI_SCHEMA.md::vault_id = 'trading-research'
  2. Detect: vaults table имеет row (vault_id='trade-agents', root_path='/old/path')
  3. Prompt operator:
     "Old vault 'trade-agents' at /old/path is missing.
      New vault 'trading-research' at /new/path detected.
      Options:
        (R)ename: UPDATE vaults SET vault_id='trading-research', root_path='/new/path' …
                  → preserves registered_at; all FK rows auto-update (CASCADE)
        (N)ew:    INSERT new row; old row stays (operator должен DELETE manually)
        (F)ork:   keep both"
  4. На (R) → atomic UPDATE в transaction (CASCADE updates pages/entities/refs/log_events)
  5. Затем wiki-reindex --vault trading-research --full — пересчитывает FTS5, refs, log_events из файлов
```

**No file mutations** при rename — только metadata reconciliation в DB. `(R)ename` сохраняет `registered_at` (единственный strict Class-C field); `(N)ew` потеряет его approximation; `(F)ork` дублирует под разными vault_id.

#### Special cases: log.md and index.md (sync direction matters)

Two vault artefacts have unusual sync semantics — both touch DB *and* file but in opposite directions. Worth pinning down explicitly because I-3.4 and I-3.5 implementations differ on this point.

##### log.md — file canonical, DB mirror (bi-directional append)

```
log_event emitted by skill
            │
            ▼ atomic (in same transaction)
  ┌─────────────────────────────────┐
  │ APPEND block to log.md           │  ← canonical store
  │   "## [date] event | subject"    │
  │   - Pages created: [...]         │
  │   - Contradictions: 0            │
  └─────────────────────────────────┘
            │
            ▼
  ┌─────────────────────────────────┐
  │ INSERT row into log_events       │  ← derivative cache for queries
  │   with log_md_byte_offset = X    │     pointing back into log.md
  └─────────────────────────────────┘
```

- **Canonical**: `<vault>/log.md` (or monthly-rotated `log/{YYYY-MM}.md`). File is the truth.
- **DB mirror**: `log_events` table — every Markdown block has parallel row; `log_md_byte_offset` allows round-trip.
- **Write**: atomic bi-directional (R-28 contract). One transaction writes both.
- **Read**: chosen by use case. Human/grep → file. Structured query («events per concept / period / type») → `log_events` (< 10ms vs O(N) grep).
- **Rebuildability**: `wiki-reindex --full` parses log.md blocks → re-INSERTs into log_events. No semantic loss.
- **Class (§D8)**: log.md = Class A storage-form; log_events = Class B mirror.

##### index.md — hybrid: catalog sections DB-canonical, custom sections file-canonical

```
pages + entities tables (Class B, derived from files)
            │
            ▼
       index_meta VIEW (computed on read)
            │
            ▼ (wiki-index-render skill, I-3.4)
  ┌─────────────────────────────────────────┐
  │ Render to <vault>/index.md, sections:   │
  │   ## Sources       ← DB-canonical       │
  │   ## Concepts      ← DB-canonical       │
  │   ## Entities      ← DB-canonical       │
  │   ## Shared concepts referenced ← DB    │
  │                                          │
  │   ## Notes         ← FILE-canonical     │
  │   (any operator-added sections)         │  ← preserved by reindex
  └─────────────────────────────────────────┘
```

- **Catalog sections** (`## Sources` / `## Concepts` / `## Entities` / `## Shared concepts referenced`): **DB canonical**. `index_meta` view → file. Re-rendering затирает старые catalog rows. Operator edits to these sections are **lost** on next render — by design.
- **Custom sections** (`## Notes` or any operator-added): **File canonical**. `wiki-index-render` **preserves** them (R-08 contract; per wiki-ingest's `reindex --preserve-custom-sections`). DB has no representation of them.
- **LLM hot-path discipline**: LLM **never parses index.md** for known-concepts/known-pages list — queries `index_meta` view directly. index.md exists для Obsidian Graph rendering + human browsing (resolves bottleneck B2/B4: token cost ~500 vs ~4-30K).
- **Class (§D8)**: catalog sections = Class B canonical-on-DB (re-renderable from views); custom sections = Class A (file-only).

##### Why the asymmetry

- **log.md**: log events are first-class operations (they happened). The chronicle is fundamental — append-only by Karpathy canon, git-diffable, grep-friendly. File must be primary store; DB serves query performance.
- **index.md**: the catalog is a **projection** over already-existing pages/entities (each Class B mirror of its own file). The catalog itself adds no new canonical information — it's a view. File-rendering exists для Obsidian Graph, not для truth.
- **Common rule**: «canonical» follows the data origin: log events originate from operations → file is their natural home; catalog rows originate from existing pages → DB is their natural home (because pages are already там).

##### Implementation note для I-3.4 / I-3.5

- **I-3.5 `wiki-append-log`**: must perform `BEGIN IMMEDIATE` → `APPEND` to log.md → `INSERT` into log_events with `log_md_byte_offset = file.tell() before APPEND` → `COMMIT`. Failure on either side rolls back both. flock or `O_APPEND` for crash safety.
- **I-3.4 `wiki-index-render`**: must (a) read existing `<vault>/index.md` if present; (b) preserve any section NOT in the generated set ({Sources, Concepts, Entities, Shared concepts referenced, Shared entities referenced}); (c) regenerate catalog sections from `index_meta`; (d) atomic write via tempfile + rename. Operator's `## Notes` survives.

#### Implications для design reviews

При любом изменении schema или skill'а, reviewer должен ответить на:
1. **Is the new data Class A, B, or C?** (если ответ unclear — пересмотреть)
2. **If Class B (cache)**: «есть ли алгоритм reconstruction из vault файлов?» (если нет — это Class C, обоснуй)
3. **If Class C (DB-only)**: «можно ли derive из существующих Class-B таблиц через view?» (если да — заменить view'ом)
4. **If anti-pattern violation**: explicitly call out → block merge

## Consequences

### Positive

- **B1-B6 решены** на уровне schema (не runtime ad-hoc оптимизации)
- **Karpathy canon preserved** — log.md, index.md, _concepts/, _entities/ остаются как single source of truth
- **SQLite — derivative cache** для hot-path queries (< 50ms ВНЕ зависимости от vault size)
- **Multi-vault native** — один файл, partition-aware queries
- **Promotion-spec native** — `project='_vault_'` sentinel ровно ложится на vault-root tier
- **Token cost снижен** на ingest: 4K → 500 tokens на known-concepts; ~7-8% сокращение бюджета per-ingest

### Negative

- **Schema complexity** — composite PKs, vault_id везде. Migration v1 → v2 не trivial.
- **wiki-ingest v1.1 → v1.2 contract** — нужен `vault_id` в JSON manifest + `--vault-id` flag. Update WIKI-INGEST-V1.1-CONTRACT.md.
- **Multi-process write contention** — concurrent ingest из 2+ vault'ов serialized через SQLite single-writer. Acceptable для personal-use (рекомендация: один ingest за раз, BEGIN IMMEDIATE).

### Neutral

- **Existing TASK.md дополняется тремя R-27/R-28/R-29** (см. ниже). Не блокирует Phase 3 rework — встраивается в него.
- **Existing SCHEMA-DRAFT.sql require v2.0 update** — composite PK migration + `vaults`/`log_events` tables.

## Implementation Path

**Phase 2.5 (NEW — paralleled with wiki-ingest v1.1 work):**
- [x] ADR-002 (этот файл)
- [ ] Update `docs/WIKI-INGEST-V1.1-CONTRACT.md` — добавить `vault_id` в JSON manifest, `--vault-id` flag, `log_event` JSON schema
- [ ] Update `docs/SCHEMA-DRAFT.sql` → v2.0 с composite PKs, `vaults`, `log_events`, FTS5 vault_id column
- [ ] Update `docs/SQLITE-VS-POSTGRES.md` — multi-vault section, single-file rationale
- [ ] Stage R-27/R-28/R-29 в TASK.md (в `## 2. RTM` block; не реворкать другие R-*, они переедут в Phase 3)

**Phase 3 (после wiki-ingest v1.1 + 1.2 release):**
- Coordinated rework TASK.md под Option I + multi-vault (ADR-001 + ADR-002 вместе)
- Re-run /vdd-adversarial на updated TASK

## New requirements (для будущего TASK.md rework)

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **R-27** | Multi-vault partitioning | ✅ | (R-27.1) `vaults` registry table; (R-27.2) `vault_id` discriminator на pages/entities/refs/source_state; (R-27.3) composite PKs; (R-27.4) FTS5 содержит `vault_id` для partition pruning; (R-27.5) `wiki-init --vault-id <slug>` interactive prompt либо derivation из `WIKI_SCHEMA.md` |
| **R-28** | Structured `log_events` table | ✅ | (R-28.1) atomic bi-directional sync log.md ↔ log_events row; (R-28.2) `log_md_byte_offset` для round-trip; (R-28.3) event_type CHECK enum (11 types); (R-28.4) details_json для extensible payloads |
| **R-29** | Cross-vault search + overlap detection | ✅ | (R-29.1) `wiki-search --vaults <list>` flag; (R-29.2) `wiki-lint --cross-vault-duplicates` mode (suggests promotion candidates); (R-29.3) `index_meta` view для consolidated catalog |

## References

- [ADR-001](./ADR-001-wiki-ingest-integration.md) — Option I architecture pivot
- [WIKI-INGEST-V1.1-CONTRACT.md](../WIKI-INGEST-V1.1-CONTRACT.md) — to be updated with `vault_id` requirements
- [SCHEMA-DRAFT.sql](../SCHEMA-DRAFT.sql) — current schema (single-vault, will be v2.0'd)
- [SQLITE-VS-POSTGRES.md](../SQLITE-VS-POSTGRES.md) — DB decision (matrix re-validated for multi-vault)
- [trade-agents/docs/wiki-ingest-promotion-spec.md](../../trade-agents/docs/wiki-ingest-promotion-spec.md) — two-tier vault model
- `~/.claude/skills/wiki-ingest/SKILL.md` v1.0 — current global skill (4 modes)
- Empirical: `trade-agents/Lessons/ZeroOne Systems/` — 13 ingests, log.md + index.md + 106 wiki pages
