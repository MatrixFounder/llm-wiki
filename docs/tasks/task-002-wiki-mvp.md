# TASK: LLM Wiki MVP — Karpathy + cybos hybrid с SQLite-первым индексом

### 0. Meta Information

- **Task ID:** 001
- **Slug:** `wiki-mvp`
- **Source spec:** [docs/TASK-ref-v2.md](./TASK-ref-v2.md) (полная спецификация на 1745 строк — этот TASK — её MVP-нарезка)
- **Related artifacts:**
  - [docs/SCHEMA-DRAFT.sql](./SCHEMA-DRAFT.sql) — SQLite DDL (готов)
  - [docs/SQLITE-VS-POSTGRES.md](./SQLITE-VS-POSTGRES.md) — backend сравнение (готов)
  - [docs/MIGRATION-v1-to-v2.md](./MIGRATION-v1-to-v2.md) — план миграции (готов)
  - [docs/KNOWN_ISSUES.md](./KNOWN_ISSUES.md) — stub-файл создан (no known issues at start of project; entry format задан внутри).
- **Mode:** Standard
- **Status:** `PHASE-3A-COMPLETE` (2026-05-26) — all 34 atomic tasks landed; 293 tests pass; mypy --strict clean; rebuildability E2E gate green; VDD multi-adversarial + adversarial reviews passed (no Critical/High open); dogfooded on trade-agents (5 production bugs caught + fixed).
  - **Decision-1 (2026-05-25)**: pivot к **Option I (Wrap + Index)** — `wiki-ingest` v1.1+ becomes canonical file-layer; MVP wraps + indexes. См. [ADR-001](./adr/ADR-001-wiki-ingest-integration.md).
  - **Decision-2 (2026-05-26)**: **Single global DB + `vault_id` partitioning** — один SQLite-файл серверит multiple Obsidian vaults; schema partition by `vault_id`. Resolves empirical bottlenecks B1-B6 measured on `trade-agents/`. См. [ADR-002](./adr/ADR-002-multi-vault-bottleneck-corrections.md).
  - **Decision-3 (2026-05-26)**: **`vault_id` REQUIRED explicit** в `WIKI_SCHEMA.md` — no hash fallback. См. ADR-002 §D1.1.
  - **Decision-4 (2026-05-26)**: **Data Layering Contract** — Class A (vault canonical) / B (cache, rebuildable) / C (DB-only operational, only `vaults.registered_at`). См. ADR-002 §D8.
  - **Decision-5 (2026-05-27)**: **UC-06 / UC-07 superseded by `/wiki-enrich`** — the bridge skill (built 2026-05-25) covers transcript ingest AND arbitrary-markdown ingest through the wiki-ingest v1.1 manifest pipeline. R-06.3 and R-24 marked SUPERSEDED in the RTM below; original Use Case bodies retained for historical rationale but each carries a SUPERSEDED banner. Reasoning + onward plan: [docs/ROADMAP.md](./ROADMAP.md) §R-1.
  - **Current schema**: [docs/SCHEMA-v2.sql](./SCHEMA-v2.sql). [SCHEMA-DRAFT.sql](./SCHEMA-DRAFT.sql) superseded.
  - **Three new requirements staged in Phase 3a**:
    - **R-27**: Multi-vault partitioning (vaults registry, vault_id discriminator, composite PKs, FTS5 vault_id column, vault_id format CHECK) ✅ DONE
    - **R-28**: Structured log_events table (bi-directional sync log.md ↔ log_events row, event_type CHECK enum, log_md_byte_offset round-trip) ✅ DONE
    - **R-29**: Cross-vault search + overlap detection (--vaults flag, cross-vault duplicates lint) ✅ DONE
  - **Phase 3a delivered**: foundation, DAL, core ingest, search/lint, reindex, benchmark — all green; `/wiki-enrich` bridge integrating with wiki-ingest v1.1 manifests is the end-to-end ingestion path. Roadmap for Phase 3b+ in [docs/ROADMAP.md](./ROADMAP.md).

---

### 1. General Description

#### 1.1 Цель

Построить **рабочий MVP персональной LLM Wiki** для Obsidian-vault'а пользователя, объединяющий:
- идею Karpathy (markdown-first, index/log/concepts/lint/query как операции),
- паттерн cybos (file + SQLite индекс, pluggable per-source adapters, provenance v1.1),
- двухслойную конфигурацию (vault `CLAUDE.md` + per-project `.wiki.yaml`).

MVP = **single-source wiki** на manual + transcript + light-summary ingestion с FTS5-поиском < 50ms на 1000+ документах. Multi-source (email/telegram/web), entity-resolver, vector search, Postgres backend — **out of MVP scope**, описаны как future Epics.

#### 1.2 Связь с существующей системой

- **Существует**: `tmp2/` (16 готовых summary-страниц от skill `summarizing-meetings`), полная спецификация v2.
- **Используется как-есть**: skill `summarizing-meetings` + **workflow `/generate-detailed-meeting-summary`** (educational overlay) из MatrixFounder/Universal-skills репо (decision: include в MVP — git-submodule или симлинк, см. §6.1 Constraints). Workflow генерирует frontmatter с `type: lesson-summary` + `content_type/course/module/speaker/concepts/prerequisites` extension fields; adapter нормализует к SCHEMA-allowed type через mapping в §6.1.
- **Vault пользователя**: `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/ObsidianNotes/` (iCloud) — будет dogfood-цель, но **тестируется на не-iCloud копии** (`/tmp/wiki-test-vault/`) для предотвращения коррупции SQLite.
- **Code location** (decision): этот репо `obsidian-llm-wiki/`. Структура добавляется: `skills/wiki-*/`, `scripts/wiki_index/` (Python DAL), `scripts/wiki_source/` (adapters), `scripts/wiki_telegram/` (TS GramJS, future Epic 6), `tests/`, `workflows/ingest-source.md`. Установка в `~/.claude/skills/` через симлинк или плагин (отдельная sub-task).

#### 1.3 Goal of development

После MVP пользователь сможет:
1. Запустить `/wiki-init` в Obsidian-vault'е → получить рабочую структуру + SQLite-индекс (вне iCloud).
2. Через `/ingest-source --kind manual --source <md-file>` индексировать существующий markdown в SQLite + log.
3. Через `/ingest-source --kind transcript --source <transcript-path>` запустить **`/generate-detailed-meeting-summary` workflow** (который extends базовый `summarizing-meetings` skill educational-overlay'ем: расширенный frontmatter с `content_type/course/module/speaker/concepts/prerequisites`, three-level pyramid, Mermaid-диаграммы, `<!-- SECTION:* -->` anchors, RAG `Chunk Boundaries`) → получить summary в `Summaries/<slug>/body.md` + индексировать.
4. Через `/wiki-enrich --source <path>` (bridge skill) выполнить end-to-end ingest произвольного markdown-источника — wiki-ingest синтезирует страницы → manifest → индексация в SQLite одним вызовом. Это покрывает и transcript-кейсы, и ad-hoc заметки. _(Прежние варианты UC-06 `wiki-light-summary` / UC-07 `wiki-source-transcript` superseded решением 2026-05-27.)_
5. Через `/wiki-search "term"` искать по корпусу < 50ms.
6. Через `/wiki-lint` получать health-report корпуса.
7. Мигрировать существующие 16 `tmp2/` файлов в новую структуру скриптом.

---

### 2. Requirements Traceability Matrix (RTM)

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **R-01** | Конфигурационный слой | ✅ | (R-01.1) JSON Schema для `wiki:` блока в CLAUDE.md и `.wiki.yaml`; (R-01.2) deep-merge root + project; (R-01.3) валидация при load с fail-fast |
| **R-02** | SQLite-индекс с FTS5 | ✅ | (R-02.1) DDL из [SCHEMA-DRAFT.sql](./SCHEMA-DRAFT.sql); (R-02.2) WAL mode + foreign_keys; (R-02.3) trigger-sync для FTS5 |
| **R-03** | iCloud-aware DB location | ✅ | (R-03.1) detect iCloud-путь vault'а; (R-03.2) force DB вне iCloud; (R-03.3) per-platform default path (macOS/Linux/Windows) |
| **R-04** | DAL: `IndexRepository` interface + SQLite implementation | ✅ | (R-04.1) abstract base; (R-04.2) SQLiteRepository ~400 строк; (R-04.3) factory + config-driven instantiation |
| **R-05** | `wiki-init` — bootstrap vault'а | ✅ | (R-05.1) детектит iCloud + interactive prompts; (R-05.2) создаёт SQLite + директории; (R-05.3) пишет initial CLAUDE.md из template |
| **R-06** | Source Adapter контракт | ✅ (partial) | (R-06.1) ✅ abstract `SourceAdapter` interface; (R-06.2) ✅ `manual` adapter (existing markdown); (R-06.3) **SUPERSEDED → `/wiki-enrich`** — transcript ingestion goes through the wiki-ingest v1.1 manifest pipeline (file synthesis owned by external skill, indexing owned by us). See [docs/WIKI-INGEST-V1.1-CONTRACT.md](./WIKI-INGEST-V1.1-CONTRACT.md) and [skills/wiki-enrich/SKILL.md](../skills/wiki-enrich/SKILL.md). Original spec body retained in I-3.3 / UC-07 for historical rationale. |
| **R-07** | `wiki-index-upsert` — DB upsert | ✅ | (R-07.1) parse frontmatter + body; (R-07.2) compute file_hash; (R-07.3) single-tx upsert + page_entity_refs; (R-07.4) **educational frontmatter handling**: `type: lesson-summary` нормализуется к `pages.type='summary'` + tag `lesson-summary` (см. §6.1 type-mapping rule); `concepts[]` копируются (a) в `pages.frontmatter_json.concepts[]` вербатим (preserves originals), (b) `slugify(c)` для каждого concept и merge в `tags` JSON-array через **`python-slugify`** library (`slugify(c, lowercase=True, separator='-', regex_pattern=r'[^a-z0-9\-]')`); duplicates dedup'аются; collision-cases (`"AI"` & `"a.i."` → `"ai"`) логируются как INFO в lint report (не error — Karpathy-vault допускает aliasing); entity-promotion ⇒ Epic 7; `prerequisites: [[wiki-link], ...]` остаются в `frontmatter_json` без промоушна в `page_entity_refs` (`ref_type='prerequisite'` отсутствует в CHECK constraint — расширение ⇒ Epic 7); Obsidian Graph View рендерит их сам из YAML; (R-07.5) **body normalization для FTS5/body_excerpt** — точные regex-патерны (compiled once, applied in order): (a) Mermaid: `re.compile(r"^```mermaid\s*\n.*?^```\s*$", re.DOTALL \| re.MULTILINE)` — strips fenced blocks; **sanity-check**: если файл содержит `^```mermaid` но НЕ matching closing fence — `raise BodyNormalizationError('unclosed mermaid fence')`, fail-fast (не tail-eat); (b) SECTION anchors: `re.compile(r"<!--\s*SECTION:[a-z0-9_-]+\s*-->")` — **whitelist** строго `SECTION:` prefix, generic `<!-- TODO -->` / `<!-- ... -->` НЕ трогаются; (c) оригинальный body на диске не модифицируется — stripping применяется только к in-memory copy для FTS5 + body_excerpt computation |
| **R-08** | `wiki-index-render` — read-only `index.md` projection | ✅ | (R-08.1) query SQLite group_by category; (R-08.2) atomic markdown write; (R-08.3) auto-shard если pages > 200 |
| **R-09** | `wiki-append-log` — chronological log с ротацией | ✅ | (R-09.1) monthly rotation `log/{YYYY-MM}.md`; (R-09.2) `log/index.md` router; (R-09.3) atomic append (`O_APPEND` или `flock`) |
| **R-10** | `wiki-search` — FTS5-backed поиск | ✅ | (R-10.1) BM25 ranking; (R-10.2) project/type filters; (R-10.3) snippet с highlighting |
| **R-11** | `wiki-lint` — SQL-based health-check (lean mode) | ✅ | (R-11.1) orphan links / missing backlinks / **index-drift с применением §6.1 type-mapping** (drift-check НЕ флажит case когда `file_frontmatter.type ∈ {lesson-summary, summary-light, meeting-summary}` AND `pages.type='summary'` AND `pages.tags` contains соответствующий marker — это intentional mapping, не drift); (R-11.2) markdown report + JSON sidecar; (R-11.3) `--fix` safe operations |
| **R-12** | `ingest-source` meta-workflow (single-source) | ✅ | (R-12.1) dispatch к `wiki-source-{kind}`; (R-12.2) chained: source → index-upsert → log; (R-12.3) failure handling с partial-recovery |
| **R-13** | Bulk-migration `tmp2/` → v2 layout | ✅ | (R-13.1) перенос flat файлов в subfolder pattern + `--dry-run` flag; (R-13.2) batch index-upsert (sequential, single-writer); (R-13.3) e2e check на 16 файлах |
| **R-14** | Benchmark suite + SLO checker | ✅ | (R-14.1) synthetic vault generator (100/1000/10000 docs); (R-14.2) latency measurement per operation; (R-14.3) сравнение с §28 v2 SLOs |
| **R-15** | Provenance model v1.1 | ✅ | (R-15.1) `source_quote / source_span / trust_level` поля в DDL; (R-15.2) обязательны для extracted_items; (R-15.3) `wiki-source-manual` ставит `trust_level='high'` (user-curated); transcript adapter — `trust_level='medium'` по default; configurable через frontmatter |
| **R-24** | `wiki-light-summary` workflow для произвольного markdown-куска | **SUPERSEDED → `/wiki-enrich`** | The bridge skill ingests any markdown source through the wiki-ingest v1.1 manifest pipeline. No separate "light" path needed — `wiki-ingest` handles arbitrary markdown the same way it handles transcripts. Original spec body retained in I-3.7 / UC-06 for historical rationale. |
| **R-25** | `vault_metadata` table + vault_hash storage | ✅ | (R-25.1) key-value таблица для vault identity и schema versioning; (R-25.2) seeded `wiki-init` (`vault_hash`, `vault_root_path`, `schema_version`, `created_at`, `language`, `layout`); (R-25.3) используется UC-01 §A2 для re-init detection |
| **R-26** | Path-traversal защита и schema PK fix | ✅ | (R-26.1) `pages.project NOT NULL DEFAULT '_vault_'` (sentinel вместо NULL для idempotency); (R-26.2) `wiki-source-manual` validates source path внутри vault_root; (R-26.3) AC-test для path-traversal attempt |
| **R-16** | Multi-source ingestion (email/telegram/web) | ❌ | future Epic 6 — отдельный TASK после MVP |
| **R-17** | Cross-source `wiki-brief` | ❌ | future Epic 6 |
| **R-18** | `wiki-extract-concepts` + entity-resolver | ❌ | future Epic 7 — opt-in, не в MVP |
| **R-19** | `wiki-query` (RAG) | ❌ | future Epic 7 |
| **R-20** | `wiki-research` (web enrichment) | ❌ | future Epic 7 |
| **R-21** | `wiki-verify-multi` (4-critic ensemble) | ❌ | future Epic 7, default off в v2 |
| **R-22** | Vector layer (sqlite-vec) | ❌ | future Epic 8 |
| **R-23** | Postgres backend (PostgresRepository) | ❌ | future Epic 8, opt-in через DAL |

**Покрытие MVP**: R-01 — R-15, R-24 — R-26 (18 требований). Остальные 8 — future Epics с явным MVP=No.

---

### 3. Epics & Issues (Chainlink Decomposition)

#### Epic E1: Foundation — конфиг, схема, init [MVP]
> Закладывает базис, на котором стоит всё остальное. Без этого ничего не работает.

- **I-1.1** Реализовать `wiki-config.schema.yaml` (JSON Schema 2020-12 формат). Покрывает оба слоя: `WikiRootConfig` для `CLAUDE.md::wiki:`, `WikiProjectOverride` для `.wiki.yaml`. → R-01.
- **I-1.2** Зафиксировать [docs/SCHEMA-DRAFT.sql](./SCHEMA-DRAFT.sql) как `sql/wiki-index.sql` в репо имплементации. Включает `vault_metadata` таблицу + `pages.project NOT NULL DEFAULT '_vault_'` sentinel (см. §6.1 C-2 fix). → R-02 + R-25.1 + R-26.1.
- **I-1.3** Реализовать `wiki-init` skill: detect iCloud, compute vault_hash, create SQLite (вместе с seed `vault_metadata` rows: vault_hash, vault_root_path, language, layout), mkdir directories, write CLAUDE.md template, interactive prompts (layout / auto_extract / automations / sources). → R-03 + R-05 + R-25.2.
- **I-1.4** Skill `wiki-init` self-check: SQLite connect OK, FTS5 trigger OK, все paths созданы, vault_metadata seeded.

#### Epic E2: Index Layer (DAL) [MVP]
> SQLite-абстракция, на которой строятся все search/lint/upsert операции.

- **I-2.1** `IndexRepository` abstract (Python `abc.ABC`). Methods для MVP: `upsert_page`, `get_page`, `delete_page`, `search_pages`, `upsert_refs`, `replace_refs` (delete + insert atomic), `get_backlinks`, `find_orphan_links`, `find_pages_missing_in_index`, `check_drift`, `begin_batch_run`, `finish_batch_run`, `last_batch_run`, `get_vault_metadata`, `set_vault_metadata`. **Заглушка**: `resolve_entity` возвращает `None` (raises `NotImplementedError` в strict-mode — entity-resolver приходит в Epic 7). → R-04.1.
- **I-2.2** `SQLiteRepository` concrete. WAL pragmas, FTS5 query через `bm25()`, JSON-extract для frontmatter, atomic transactions (`BEGIN IMMEDIATE`), parameterized queries (sql-injection защита). → R-04.2.
- **I-2.3** Factory `make_repo(config)` + path resolution (`vault_hash`, per-platform default). → R-04.3.
- **I-2.4** Unit tests: minimal vault fixture, все методы repo покрыты, idempotency check (UPSERT тот же row дважды → SELECT count = 1).

#### Epic E3: Core Ingest — single source [MVP]
> Связать manual / transcript / light ingestion со SQLite-индексом и файловыми артефактами.

- **I-3.1** `SourceAdapter` abstract base + dataclasses `SourceItem`, `SourceOutput`. → R-06.1.
- **I-3.2** `wiki-source-manual` — adapter для уже-существующих markdown файлов. Не модифицирует body, не перемещает файлы. Если требуется reshape (flat → subfolder), используется отдельный скрипт `wiki-migrate-flat-to-folders` (I-5.1) перед ingestion. Validates source path внутри vault_root (path-traversal защита). Sets `trust_level='high'` для refs (user-curated content). → R-06.2 + R-15.3 + R-26.2.
- **I-3.3** `wiki-source-transcript` — **SUPERSEDED → `/wiki-enrich`** (Decision-5, 2026-05-27). The bridge skill `wiki-enrich` (in `skills/wiki-enrich/`) runs `wiki-ingest ingest --output-format json`, validates the v1.1 manifest against R-26 path containment + vault_id check, then upserts every `manifest.written[].path` into the SQLite index and mirrors the `log_event` into `log_events`. No separate subprocess-to-`/generate-detailed-meeting-summary` path — wiki-ingest owns transcript synthesis internally per ADR-001. Spec body below retained as historical rationale.<br><br>_Original spec (historical — subprocess invocation contract before Option I):_
  - **(a) Discovery**: проверяет (i) `~/.claude/skills/summarizing-meetings/SKILL.md` существует, (ii) `~/.claude/commands/generate-detailed-meeting-summary.md` существует, (iii) `shutil.which('claude')` returns non-None ИЛИ env var `WIKI_GENSUMMARY_CMD` задан (escape-hatch для non-Claude-CLI окружений: Cursor, IDE plugins). Если любой fail — `{error: 'WORKFLOW_NOT_FOUND', missing: [...], expected_paths: [...]}`, exit ≠ 0.
  - **(b) Idempotency-check (A4 short-circuit)**: применяет UC-07 A4 logic — `source_state` query на `source_hash`. Если hit — skip к (e), no subprocess spawn.
  - **(c) Spawn**: `subprocess.run([claude_cmd, '-p', f'/generate-detailed-meeting-summary on transcript {abs(source)} output to {abs(output)}/summary.md'], timeout=600, capture_output=True, check=False, env={**os.environ, 'CLAUDE_NONINTERACTIVE': '1'})`. По default 10 min; configurable через `wiki.transcript.timeout_seconds`.
  - **(c.1) Timeout/crash handler**: при `subprocess.TimeoutExpired` → `proc.kill()` + wait; при non-zero exit_code — обрабатывать как failed. В обоих случаях: best-effort `unlink(<output>/summary.md)`, move partial output (если есть) в `<vault>/_raw/failed/<YYYY-MM-DD-HHMMSS>-<slug>.md`, write log entry, return `{error: 'WORKFLOW_TIMEOUT'|'WORKFLOW_FAILED', exit_code, stderr_tail: <last 1KB>}`.
  - **(d) Output validation** (anti-truncation): reads `<output>/summary.md`. Проверяет: (i) frontmatter parseable; (ii) presence `<!-- SECTION:agent-metadata -->` маркера; (iii) `Content Fingerprint` block с **rendered** значениями (НЕ `{{N}}` placeholders): `Total concepts extracted: N` где N — integer ≥ 1; `Source files:` line содержит non-empty filename. Если любой fail → `{error: 'WORKFLOW_INCOMPLETE', details}`.
  - **(e) Normalization & upsert**: Применяет **R-07.4** (frontmatter `type` mapping через §6.1 table — если `type ∉ mapping` → fail с `{error: 'UNMAPPED_TYPE'}`, см. UC-07 A3) и **R-07.5** (body normalization) перед записью в DB. Файл на диске не модифицируется.
  - **(f) Persist idempotency state**: `INSERT OR REPLACE INTO source_state(source_kind='transcript', scope=abs(source), key='source_hash', value=current_hash, updated_at=now())`.
  - **(g) Trust level**: Sets `trust_level='medium'` для всех `page_entity_refs` (LLM-generated).
  
  → R-06.3 + R-15.3 + R-07.4 + R-07.5.
- **I-3.4** `wiki-index-upsert` — single-tx UPSERT в pages + page_entity_refs. Idempotent на основе `(slug, project)` PK с sentinel `'_vault_'` для NULL-replacement (см. §6.1). **Применяет R-07.4 (educational frontmatter mapping) и R-07.5 (body normalization)**: при `frontmatter.type == 'lesson-summary'` — записывает `pages.type='summary'`, добавляет tag `lesson-summary` в JSON-array tags, копирует `frontmatter.concepts[]` в `pages.frontmatter_json` + merge в tags (slugified) для FTS5; `frontmatter.prerequisites[]` остаются в `frontmatter_json` (не промотируются в `page_entity_refs` в MVP — `ref_type='prerequisite'` отсутствует в CHECK; см. R-07.4). Перед FTS5-индексацией body стрипит ` ```mermaid…``` ` и `<!-- SECTION:* -->` (regex-based; оригинальный body на диске не модифицируется). → R-07 + R-26.1.
- **I-3.5** `wiki-index-render` — генерирует `index.md` projection из SQLite. Atomic write через tempfile. Auto-shard если > 200 pages. → R-08.
- **I-3.6** `wiki-append-log` — monthly-rotated log (`log/{YYYY-MM}.md`) + `log/index.md` router. Atomic append. → R-09.
- **I-3.7** `wiki-light-summary` workflow — **SUPERSEDED → `/wiki-enrich`** (Decision-5, 2026-05-27). The bridge skill ingests any markdown source through the wiki-ingest v1.1 manifest pipeline. No separate "light" path needed — wiki-ingest handles arbitrary markdown the same way it handles transcripts; output frontmatter type is decided per file inside wiki-ingest. Spec body below retained as historical rationale.<br><br>_Original spec (historical):_ Standalone skill+workflow for arbitrary markdown chunks. Accepted `--text "..."` inline or `--source <path>` to a markdown file. Generated a short summary via single LLM call (Claude Haiku/Sonnet) and emitted `Summaries/light/<date>-<slug>.md` with `type: summary-light`. → R-24.

#### Epic E4: Search & Health [MVP]
> Read-side операции — то, ради чего пользователь работает с wiki.

- **I-4.1** `wiki-search` skill — wraps `repo.search_pages(...)` + nice markdown output (BM25 score + snippet с `<b>...</b>` highlighters [пробрасываются явно в `snippet()` arguments] + co-occurrences для concept-type). → R-10.
- **I-4.2** `wiki-lint` skill (lean mode) — 9 чеков из [TASK-ref-v2.md §13](./TASK-ref-v2.md), все через SQL. Для `flat` layout (sentinel project='_vault_') — `required_frontmatter` исключает `project` (см. §6.1). Markdown report + JSON sidecar. `--fix` для safe operations. → R-11.
- **I-4.3** `ingest-source` meta-workflow (markdown в `workflows/`) — dispatcher на `wiki-source-{kind}` (manual / transcript / light), цепочка `source → upsert → log → lint quick-pass`. Failure handling с partial-recovery. → R-12.

#### Epic E5: Migration & Validation [MVP]
> Доказать, что всё работает на реальном корпусе + измерить performance.

- **I-5.1** `wiki-migrate-flat-to-folders` script — конвертит `tmp2/Summaries/{date}-{slug}.md` → `Summaries/{date}-{slug}/body.md` + sibling `metadata.json`. Idempotent (re-run no-op). Поддерживает `--dry-run` flag. → R-13.1.
- **I-5.2** Bulk-ingest скрипт для `tmp2/` (16 файлов) → SQLite через `wiki-source-manual`. Sequential (не параллельный — single-writer SQLite). → R-13.2 + R-13.3.
- **I-5.3** Benchmark suite (`scripts/benchmark.py`): synthetic vault generator (markdown с frontmatter + [[wiki-links]]) + per-operation latency measurement + сравнение с SLOs из §5.1 (NOT из UC AC — §5.1 — single source of truth для performance targets). CI-fail при > target. → R-14.

---

### 4. Use Cases (детально для MVP)

#### 4.1. UC-01: Initialize new vault (wiki-init)

**Actors:**
- User (developer / knowledge-worker)
- System (Claude Code CLI)
- Filesystem (markdown layer + SQLite layer)

**Preconditions:**
- Целевая директория существует и read-write.
- `~/.claude/skills/wiki-init/` установлен или плагин активен.
- Python 3.11+ доступен в PATH.

**Main Scenario:**
1. User: `cd ~/Obsidian/MyVault && claude`
2. User: `/wiki-init`
3. System: Detects iCloud-путь (`Mobile Documents/iCloud~`)? Если да — печатает warning + объясняет что DB будет вне iCloud.
4. System: Computes `vault_hash = sha256(abs_vault_root)[:12]`.
5. System: Determines DB path по платформе:
   - macOS: `~/Library/Application Support/wiki-index/<vault_hash>.db`
   - Linux: `~/.local/share/wiki-index/<vault_hash>.db`
6. System: Interactive prompts (или `--non-interactive` flag):
   - Layout: `per-project | flat`? (default = detect; иначе ask)
   - Auto-concept-extraction: `[y/N]` (default N — lean mode)
   - Daily automation cron: `[y/N]` (default N)
   - Sources to enable: multi-select (default `manual + transcript`)
7. System: Mkdir DB parent (`~/Library/Application Support/wiki-index/`).
8. System: Создаёт SQLite файл из [SCHEMA-DRAFT.sql](./SCHEMA-DRAFT.sql), применяет PRAGMAs (WAL, foreign_keys, etc.).
9. System: Inserts seed `batch_runs` row (mode=full, status=success, notes='schema initialized').
10. System: Mkdir vault-internal: `00-Vault-Index/`, `Summaries/`, `Sources/{email,telegram,web,manual}/`, `_raw/`, **`_raw/.locks/`** (used by UC-07 A8 concurrent-ingest flock), **`_raw/failed/`** (used by I-3.3 step c.1 partial-output cleanup).
11. System: Записывает `CLAUDE.md` (если отсутствует) с заполненным `vault_hash`, language, layout, ответами prompts'ов.
12. System: Записывает `00-Vault-Index/index.md`, `00-Vault-Index/log/2026-04.md` (текущий месяц), `00-Vault-Index/taxonomy.md` со скелетами.
13. System: Печатает banner: SQLite location, vault location, suggested next-steps (`wiki-search`, `ingest-source`, etc.).

**Alternative Scenarios:**

- **A1: `CLAUDE.md` уже существует**
  1. System: Detects existing `CLAUDE.md::wiki:` block.
  2. System: Print warning + suggest `wiki-init --force` для overwrite, или `wiki-init --skip-config` для оставить как есть и инициализировать только SQLite.
  3. System: Exit code 1, no changes.

- **A2: SQLite-файл уже существует по target path**
  1. System: Connects, queries `batch_runs` для existing vault info.
  2. If matching `vault_hash` — re-use, no overwrite.
  3. If mismatch — fail-fast: «Existing DB at <path> has different vault_hash. Use --force to overwrite».

- **A3: iCloud detected + user override**
  1. System: Print warning «iCloud detected → DB будет в `<path вне iCloud>`».
  2. User passes `--db-path <custom>`.
  3. System: validates `<custom>` is NOT in iCloud (check path content); if it IS — fail-fast.

- **A4: Insufficient permissions**
  1. System: Cannot mkdir DB parent (e.g. read-only home).
  2. System: Fail-fast с инструкцией где сделать chmod.

**Postconditions:**
- SQLite файл существует, schema применена, FTS5 trigger'ы установлены.
- vault директории созданы.
- `CLAUDE.md` валиден против JSON Schema.
- Idempotent: повторный run без `--force` — no-op (warns).

**Acceptance Criteria:**
- ✅ `sqlite3 <db_path> "SELECT count(*) FROM sqlite_master WHERE type='table'"` ≥ 8.
- ✅ `sqlite3 <db_path> "PRAGMA journal_mode"` returns `wal`.
- ✅ `sqlite3 <db_path> "SELECT count(*) FROM batch_runs"` ≥ 1.
- ✅ `<vault>/CLAUDE.md` парсится как valid YAML с `wiki:` блоком.
- ✅ `<vault>/00-Vault-Index/`, `<vault>/Summaries/`, `<vault>/Sources/` существуют.
- ✅ DB path **не** содержит `Mobile Documents/iCloud~` для iCloud-vault'ов.
- ✅ `wiki-init` re-run без `--force` exits с warn, не мутирует state.
- ✅ **vault_metadata seeded** (R-25.2): `SELECT count(*) FROM vault_metadata WHERE key IN ('vault_hash', 'vault_root_path', 'schema_version', 'created_at', 'language', 'layout')` = 6.
- ✅ `SELECT value FROM vault_metadata WHERE key='schema_version'` = `'1'`.
- ✅ `SELECT length(value) FROM vault_metadata WHERE key='vault_hash'` = 12 (sha256 truncate length).

---

#### 4.2. UC-02: Ingest existing markdown into index (manual adapter)

**Actors:**
- User
- System
- `wiki-source-manual` adapter
- SQLite

**Preconditions:**
- UC-01 успешно выполнен (vault инициализирован).
- Существует markdown-файл с валидным YAML frontmatter (как минимум `type`, `title`, `date`, `tags`).

**Main Scenario:**
1. User: `/ingest-source --kind manual --source Summaries/2026-04-27-savochka/body.md`
2. System: Resolves config (root + project) через `find_vault_root` + `find_project_root`. Если `project` не определён → используется sentinel `'_vault_'` (см. §6.1).
3. System: **Path-traversal validation** — abs(source) starts with abs(vault_root)? Если нет → fail-fast `{error: "PATH_OUTSIDE_VAULT"}`.
4. System: Opens `IndexRepository` via factory.
5. System (`wiki-source-manual`): Reads file, parses frontmatter, validates required fields per `wiki.lint.required_frontmatter` (для `layout: flat` исключает `project`).
6. System: Computes `file_hash = sha256(body)`, `last_modified = os.stat(...).st_mtime ISO`.
7. System (`wiki-index-upsert`): `repo.upsert_page(slug, project, type, title, tldr, date, last_modified, file_hash, frontmatter_json, body_excerpt)` в одной transaction (`BEGIN IMMEDIATE`).
8. System: Парсит [[wiki-links]] из body, извлекает `(target_slug, line_start, line_end, source_quote)` для каждой.
9. System: `repo.replace_refs(page_slug, page_project, [(entity_slug, ref_type, line_start, line_end, source_quote, trust_level='high'), ...])` — provenance v1.1, `trust_level='high'` для manual (user-curated). Атомарный delete + insert.
10. System: FTS5 trigger автоматически обновляет `pages_fts`.
11. System (`wiki-append-log`): Records `## [TIMESTAMP] ingest | <slug>` event в `00-Vault-Index/log/{YYYY-MM}.md` (текущий месяц вычисляется динамически).
12. System: Returns JSON `{action: "added"|"updated", slug, refs_added: N, refs_removed: K}`.

**Alternative Scenarios:**

- **A1: Frontmatter сломан**
  1. System: yaml.safe_load throws.
  2. System: Returns `{error: "INVALID_FRONTMATTER", file, details}` JSON envelope; non-zero exit.
  3. SQLite остаётся нетронутым.

- **A2: Required field отсутствует**
  1. System: `wiki.lint.required_frontmatter` example: `[type, title, date, tags, project]`. Проверка: одно из полей отсутствует.
  2. System: Returns `{error: "MISSING_REQUIRED_FIELD", field, file}`.

- **A3: Re-ingest же файла, body не изменилось**
  1. System: Computes new `file_hash`, сравнивает со stored.
  2. Если совпадает — no-op для pages-table; refs пере-resolve может найти новые ссылки → upsert refs.
  3. Returns `{action: "unchanged"}`.

- **A4: Body изменился**
  1. UPSERT обновляет `pages.last_modified`, `body_excerpt`, `file_hash`, `frontmatter_json`.
  2. FTS5 trigger пере-индексирует.
  3. Refs пере-resolve полностью (delete + insert).

- **A5: Concurrent ingest того же файла**
  1. `BEGIN IMMEDIATE` второго writer'а блокируется до commit'а первого.
  2. Второй upsert делает no-op (file_hash совпадает после первого commit'а).

**Postconditions:**
- Row в `pages` table consistent с диском.
- Rows в `page_entity_refs` корректны (для каждой [[link]] — ровно одна запись).
- FTS5 пере-индексирована.
- Запись в `log/{YYYY-MM}.md` добавлена.

**Acceptance Criteria:**
- ✅ После ingest: `repo.get_page(slug, project)` возвращает row с правильными полями.
- ✅ `SELECT count(*) FROM pages_fts WHERE pages_fts MATCH 'title-keyword'` ≥ 1.
- ✅ `SELECT count(*) FROM page_entity_refs WHERE page_slug = '<slug>'` = количество [[wiki-links]] в body.
- ✅ **Idempotency**: re-ingest the same file twice → `SELECT count(*) FROM pages WHERE slug = '<slug>' AND project = '_vault_'` = 1 (NOT 2 — sentinel-PK предотвращает duplicates).
- ✅ Sql injection невозможна (parameterized queries; test: ingest файла с frontmatter `title: "'; DROP TABLE pages--"` — table остаётся).
- ✅ **Path-traversal**: `ingest-source --source ../../../etc/passwd` returns `{error: "PATH_OUTSIDE_VAULT"}`, exit code ≠ 0, no SQLite write (`SELECT count(*) FROM pages` unchanged).
- ✅ Все refs имеют `trust_level='high'` (manual adapter).

---

#### 4.3. UC-03: Search across vault by text (wiki-search)

**Actors:** User, System, `IndexRepository` (FTS5).

**Preconditions:**
- ≥ 1 page в SQLite.

**Main Scenario:**
1. User: `/wiki-search "shadow ai"`
2. System: Loads config, opens repo.
3. System: `repo.search_pages("shadow ai", limit=20)` — FTS5 query с `MATCH` operator + `bm25()` ranking.
4. System: Для каждого hit — `snippet(pages_fts, ...)` для preview.
5. System (опц.): Если query похож на concept-name — собирает co-occurrences из `v_concept_cooccurrence` view.
6. System: Renders markdown:
   ```markdown
   ## "shadow ai" — 3 mentions
   - [[Summaries/.../body|Title]] (BM25=4.21) — "...quoted snippet..."
   ...
   Co-occurring concepts (≥ 2 mentions): X (3), Y (2)
   ```

**Alternative Scenarios:**

- **A1: 0 результатов** — System: «No matches. Try alternative terms or `/wiki-search --vector "..."` if vector layer enabled.»
- **A2: `--type summary|concept|query|brief` filter** — добавляет `WHERE p.type = ?` к query.
- **A3: `--project <name>` filter** — `WHERE p.project = ?`.
- **A4: SQLite locked (concurrent reindex)** — query через WAL читает consistent snapshot, не блокируется.

**Postconditions:**
- Read-only operation: SQLite и markdown не изменяются.

**Acceptance Criteria:**
- ✅ Query "shadow ai" на vault со страницей упоминающей "Shadow AI" → ≥ 1 hit.
- ✅ Latency targets per §5.1: < 30ms / 100 docs, < 50ms / 1000 docs, < 100ms / 10000 docs (verified by R-14 benchmark suite).
- ✅ Snippet возвращается с явно переданными markers `<b>` / `</b>` (FTS5 `snippet(pages_fts, <col>, '<b>', '</b>', '...', 16)` arguments проверяются explicitly в test).
- ✅ BM25 score возвращается, hits отсортированы по relevance ascending (lower = better в SQLite bm25).

---

#### 4.4. UC-04: Health-check corpus (wiki-lint)

**Actors:** User, System, `IndexRepository`.

**Preconditions:**
- Vault инициализирован, ≥ 0 pages.

**Main Scenario:**
1. User: `/wiki-lint --report 00-Vault-Index/lint-report.md`
2. System: Loads config + repo.
3. System: Прогоняет 9 чеков (см. v2 §13):
   1. Orphan links — `LEFT JOIN page_entity_refs ↔ entities`.
   2. Missing backlinks — для concept-pages с `appears_in:` проверить что source-страница реально содержит [[link]].
   3. Stale claims — `pages WHERE date < now() - 18 months AND tags LIKE '%current%'`.
   4. Required frontmatter — для каждой page проверить `wiki.lint.required_frontmatter`.
   5. Tag taxonomy violations — LEFT JOIN tags ↔ taxonomy.
   6. Index drift — walk filesystem, compare с pages-table. **Применяет §6.1 forward-mapping**: разница `file_frontmatter.type='lesson-summary'` vs `pages.type='summary'` НЕ считается drift'ом если `pages.tags` содержит marker `lesson-summary` (idem для `summary-light`, `meeting-summary`). Drift фиксируется только когда: (a) файл существует, но DB row отсутствует; (b) DB row есть, но файл отсутствует; (c) `file_hash` не совпадает; (d) `type` mismatch не покрыт §6.1 mapping.
   7. Log gaps — `interactions LEFT JOIN log_events`.
   8. Duplicate concepts (если `--strict`) — Levenshtein < 3 на entity names.
   9. External-only orphans (`is_external=1` без backlinks) — info-only.
4. System: Building markdown report:
   ```markdown
   # Wiki Lint Report — 2026-04-28 14:55
   ## Summary
   - 16 summaries, 0 concepts, 0 queries.
   - ❌ 4 issues found (4 orphan, 0 missing-backlinks, 0 stale).
   ## Orphan Links (4)
   - `Summaries/.../body.md` → `[[Школа менеджмента Стратоплан]]` — no such page.
   ...
   ```
5. System (опц.): JSON sidecar `00-Vault-Index/lint-report.json` для machine-consumption.

**Alternative Scenarios:**

- **A1: `--fix` mode** — applies safe fixes (missing backlinks INSERT, index-drift через `wiki-index-upsert`); orphan-target создание оставляет человеку.
- **A2: `--strict` mode** — все info → warning, все warning → error. Включает duplicate-concepts чек.
- **A3: 0 issues** — report содержит «✅ Healthy. No issues found.»
- **A4: Filesystem inconsistency mid-lint** — concurrent file delete/add. Lint берёт snapshot at start.

**Postconditions:**
- Report-файл создан (если `--report` указан).
- `--fix`: applied changes логируются в `log.md` event=lint.
- Без `--fix` — пользовательские файлы не мутируются.

**Acceptance Criteria:**
- ✅ На vault с orphan link `[[Школа менеджмента Стратоплан]]` → report содержит exact line `- \`<source-file>\` → \`[[Школа менеджмента Стратоплан]]\` — no such page.`
- ✅ На clean vault → report содержит exact phrase `✅ Healthy. No issues found.`
- ✅ **Type-mapping aware drift** (post-UC-07): После UC-07 (transcript ingest) на vault без других issues, `wiki-lint` reports `✅ Healthy. No issues found.` — НЕ флажит type-mapping divergence (file `type: lesson-summary` vs DB `type='summary'`) как drift. Verified: `SELECT count(*) FROM lint_issues WHERE category='index-drift' AND page_slug='<transcript-slug>'` = 0.
- ✅ Latency targets per §5.1: < 500ms / 100 docs, < 2s / 1000 docs, < 30s / 10000 docs (verified by R-14 benchmark suite).
- ✅ JSON sidecar parseable: `python -c "import json; json.load(open('lint-report.json'))"` exits 0.
- ✅ `--fix` идемпотентен: second run produces JSON sidecar с `applied_fixes: 0`.

---

#### 4.5. UC-05: Migrate existing tmp2/ corpus

**Actors:** Developer (выполняет migration), System, `wiki-migrate-flat-to-folders`, bulk-ingest.

**Preconditions:**
- `tmp2/` содержит 16 markdown файлов в flat layout `tmp2/<filename>.md`.
- v2 implementation готова (Epics E1-E4 завершены).

**Main Scenario:**
1. Developer: `cd tmp2 && claude`
2. Developer: `/wiki-init --layout flat --language ru` (для tmp2 как одного-проектного vault).
3. System: Создаёт SQLite, директории, CLAUDE.md.
4. Developer: `python scripts/wiki-migrate-flat-to-folders.py tmp2/` — конвертит каждый `tmp2/<file>.md` → `tmp2/Summaries/<file>/body.md` (subfolder pattern).
5. Developer: `for f in tmp2/Summaries/*/body.md; do /ingest-source --kind manual --source "$f"; done` (или batch скрипт).
6. System: Каждый файл → row в `pages`, refs резолвятся.
7. Developer: `/wiki-index-render` → генерирует `00-Vault-Index/index.md`.
8. Developer: `/wiki-lint --report 00-Vault-Index/lint.md` → ожидает orphan links на `[[Школа менеджмента Стратоплан]]` и т. п.
9. Developer: Решает per-orphan: создать stub `Concepts/<slug>.md` с `is_external: true` или добавить в `external_allowlist`.

**Alternative Scenarios:**

- **A1: Migration на iCloud-vault**
  1. `wiki-init` detects iCloud → DB вне vault'а.
  2. Markdown остаётся в iCloud — migration работает, но пользователь предупреждается о multi-device implications.

- **A2: Файл с битым frontmatter в tmp2**
  1. Bulk-ingest fail-fast на этом файле.
  2. Continue processing остальных (опция `--skip-errors` в bulk script).
  3. Failed files логируются.

**Postconditions:**
- Все 16 файлов в `tmp2/Summaries/<slug>/body.md`.
- SQLite содержит 16 rows в `pages`.
- `index.md` содержит 16 entries.
- Lint identifies все orphans.

**Acceptance Criteria:**
- ✅ `SELECT count(*) FROM pages WHERE type = 'summary'` = 16.
- ✅ `wiki-search "Shadow AI"` находит N hits, где N = `grep -l 'Shadow AI' tmp2/*.md | wc -l` (verify pre-migration). Threshold ≥ N - 1 (tolerance for stub edge cases).
- ✅ Rendered `index.md` валидный markdown с 16 ссылками на subfolder-paths.
- ✅ Lint report корректен (≥ 1 orphan ожидается на `[[Школа менеджмента Стратоплан]]`).
- ✅ Для flat-layout: `wiki.lint.required_frontmatter` excludes `project` (см. §6.1) → lint не флажит каждую страницу как missing project.

---

#### 4.6. UC-06: Light summary of arbitrary markdown chunk (NEW)

> **SUPERSEDED → `/wiki-enrich`** (Decision-5, 2026-05-27). The bridge skill
> ingests any markdown source through the wiki-ingest v1.1 manifest pipeline
> — no separate "light summary" path is needed. New operators should use
> `/wiki-enrich --vault <vid> --source <path>` instead.
> Original Use Case retained below for design rationale (token-budget math,
> input-size guard, single-LLM-call flow). See [docs/ROADMAP.md](./ROADMAP.md) §R-1.

**Actors:** User, System, `wiki-light-summary` workflow, LLM (Claude Haiku/Sonnet via API).

**Preconditions:**
- UC-01 успешно выполнен.
- LLM API доступен (Anthropic API key в env или MCP-config).

**Main Scenario:**
1. User: `/wiki-light-summary --text "длинный текст-кусок..."` (или `--source path/to/note.md` для file-based input).
2. System: Загружает text. Если > 10K chars — fail-fast с предложением использовать transcript flow (`wiki-source-transcript`) для длинных документов.
3. System: Вызывает LLM (single-call) с prompt: «Summarize the following text in 2-3 sentences as TL;DR. Extract 3-5 tags.»
4. System: Получает structured response: `{tldr: "...", tags: [...]}`.
5. System: Generates `base_slug = slugify(<first-non-empty-line of input>)` (truncated to 60 chars). Final composite slug: `<YYYY-MM-DD>-<base_slug>`.
6. System: Writes `<vault>/Summaries/light/<composite-slug>.md`:
   ```markdown
   ---
   type: summary
   slug: <composite-slug>
   date: <YYYY-MM-DD>
   tags: [summary-light, <from LLM>]
   tldr: "<TLDR>"
   source_excerpt: "<first 200 chars of input>"
   trust_level: medium
   project: '_vault_'
   ---

   # <Title — extracted from first H1 if present, else <base_slug>>

   <Original text — full, не сокращённый>

   ## TL;DR

   <TLDR>
   ```

   **Note**: frontmatter `type: summary` (NOT `summary-light`) — соответствует SCHEMA `pages.type` CHECK constraint (set: `summary, concept, query, brief, research, index, log`). Маркер «light» хранится как **tag** `summary-light` в `tags`, что позволяет фильтровать через FTS5 без расширения schema.
7. System: Calls `wiki-index-upsert` на этот файл — DB row будет иметь `type='summary'`, `tags JSON contains 'summary-light'`.
8. System: Calls `wiki-append-log --event ingest --entity <composite-slug>`.
9. System: Returns JSON `{action: "added", slug: "<composite-slug>", file_path, llm_tokens_used}`.

**Alternative Scenarios:**

- **A1: Text > 10K chars** — fail-fast с указанием использовать `--kind transcript` flow.
- **A2: LLM API недоступен** — fail-fast c понятным error, не пишет partial файл.
- **A3: Slug collision** — `<date>-<slug>` уже существует. Append `-2`, `-3` суффикс.
- **A4: Empty input** — fail-fast «Empty text provided».

**Postconditions:**
- 1 file в `Summaries/light/<date>-<slug>.md`.
- 1 row в `pages` (type='summary' с tag `summary-light` для filtering).
- 1 row в log.

**Acceptance Criteria:**
- ✅ Markdown файл валидный, frontmatter parseable.
- ✅ `tldr` ≤ 300 chars.
- ✅ `tags` — list of 3-5 strings, обязательно содержит `summary-light` как первый tag.
- ✅ **Schema-compatibility**: `SELECT type FROM pages WHERE slug = '<composite-slug>'` returns exactly `'summary'`. AND `SELECT 1 FROM pages, json_each(json_extract(frontmatter_json, '$.tags')) WHERE slug = '<composite-slug>' AND value = 'summary-light'` returns 1 row.
- ✅ `wiki-search "<keyword from input>"` находит созданный файл.
- ✅ Latency: < 5s на 1K-char input (LLM-bound).
- ✅ Idempotent на slug-collision: re-run с тем же input → second file gets `-2` suffix, без перезаписи первого.

---

#### 4.7. UC-07: Ingest transcript via `/generate-detailed-meeting-summary` workflow (NEW)

> **SUPERSEDED → `/wiki-enrich`** (Decision-5, 2026-05-27). Transcript
> ingestion now flows through the wiki-ingest v1.1 manifest pipeline:
> `/wiki-enrich` invokes `wiki-ingest ingest --output-format json`, validates
> the manifest, and indexes every written file into the SQLite DB plus mirrors
> the `log_event` row. wiki-ingest owns the LLM synthesis (which may itself
> call `summarizing-meetings` internally — that's wiki-ingest's concern, not
> ours). See ADR-001 + [skills/wiki-enrich/SKILL.md](../skills/wiki-enrich/SKILL.md).
> Original Use Case retained below for design rationale (idempotency on
> `source_hash`, anti-truncation validation, concurrent-ingest flock pattern).

**Actors:**
- User
- System (`/ingest-source` dispatcher → `wiki-source-transcript` adapter)
- `summarizing-meetings` skill + `/generate-detailed-meeting-summary` workflow (Universal-skills repo, git-submodule)
- LLM (Claude Sonnet via Anthropic API)
- SQLite

**Preconditions:**
- UC-01 успешно выполнен.
- `~/.claude/skills/summarizing-meetings/` существует (git-submodule или симлинк).
- `~/.claude/commands/generate-detailed-meeting-summary.md` (или эквивалентный workflow path) существует.
- LLM API доступен.
- Transcript-файл (`.txt`, `.md`, или `.srt` без timestamps) присутствует на диске.

**Main Scenario:**
1. User: `/ingest-source --kind transcript --source Lessons/ZeroOne/lesson-01.txt --output Lessons/ZeroOne/lesson-01/`
2. System (dispatcher): Resolves config, opens repo, dispatches → `wiki-source-transcript`.
3. System (adapter, step a): Validates abs(source) ⊆ abs(vault_root) (path-traversal защита, R-26).
4. System (adapter, step b): Validates skill+workflow presence; fail-fast если отсутствует.
5. System (adapter, step c): Spawns subprocess `claude -p "/generate-detailed-meeting-summary on transcript <source> output to <output>/summary.md"` (или эквивалент через MCP/CLI).
6. System (workflow inside subprocess): Запускает educational pipeline — PRE-FLIGHT → format detection → chunking (если > 100K chars) → content extraction → Mermaid generation → SECTION-anchors → Agent Metadata → completeness self-check.
7. System (adapter, step d, output validation): Reads generated `<output>/summary.md`. Validates:
   - frontmatter parseable
   - `<!-- SECTION:agent-metadata -->` marker present (доказывает что workflow дошёл до конца)
   - `Content Fingerprint` блок present
   - `type: lesson-summary` field есть
8. System (adapter, step e): Применяет **R-07.4 mapping** перед upsert (в памяти, на диске файл остаётся с `type: lesson-summary` для Obsidian-friendliness):
   - DB `pages.type` = `'summary'`
   - DB `tags` = original_tags ∪ {`lesson-summary`} ∪ slugified(concepts)
9. System: Вызывает `wiki-index-upsert` с применением **R-07.5 body normalization** (strip Mermaid + SECTION-anchors перед FTS5).
10. System: `repo.replace_refs(...)` — парсит body wiki-links (НЕ frontmatter prerequisites — те остаются только в `frontmatter_json`), trust_level='medium'.
11. System (`wiki-append-log`): `## [TIMESTAMP] ingest | transcript | <slug>` event.
12. System: Returns JSON `{action: "added"|"updated", slug, file_path, llm_tokens_used, concepts_extracted: N, mermaid_blocks: N}`.

**Alternative Scenarios:**

- **A1: Workflow или skill отсутствует**
  1. System: Returns `{error: "WORKFLOW_NOT_FOUND", expected_paths: [...]}`, exit ≠ 0. SQLite untouched.

- **A2: Subprocess crashed mid-generation**
  1. System: Detects exit_code ≠ 0 ИЛИ output file отсутствует ИЛИ `agent-metadata` marker отсутствует.
  2. Returns `{error: "WORKFLOW_INCOMPLETE", details}`. SQLite untouched. Partial output file логируется в `_raw/failed/<timestamp>-<slug>.md` для debug.

- **A3: Frontmatter `type` ≠ ожидаемому mapping-set** (`{summary, lesson-summary, summary-light, meeting-summary}`)
  1. System: проверяет `frontmatter.type ∈ §6.1 mapping table`. Если **mapped** (e.g., workflow вернул base `summary` без educational overlay) → standard upsert без R-07.4 mapping.
  2. Если **unmapped** (`type: lecture-notes` / `type: random-string`) → **fail-fast**: `{error: 'UNMAPPED_TYPE', received: <type>, allowed: <§6.1 frontmatter type list>}`, exit ≠ 0, SQLite untouched. NEVER attempt upsert с unknown `type` — CHECK constraint отвергнет, возможна partial-state leak.

- **A4: Re-ingest того же transcript-source** [idempotency via `source_state` table — SCHEMA §8]
  1. System: Computes `current_hash = sha256(read_bytes(source))`.
  2. System: Queries `SELECT value FROM source_state WHERE source_kind='transcript' AND scope = abs(source) AND key='source_hash'`. Если результат = `current_hash` → skip LLM re-generation, перепроиндексировать existing `<output>/summary.md` через `wiki-source-manual` flow (cheap re-upsert pages-row).
  3. Если no row или value ≠ current_hash → запускает workflow (Main scenario step 5+). После успешного upsert: `INSERT OR REPLACE INTO source_state(source_kind, scope, key, value, updated_at) VALUES ('transcript', abs(source), 'source_hash', current_hash, now_iso())`.
  4. Returns `{action: "unchanged"|"updated", llm_tokens_used: 0|N}`.

- **A5: Transcript > 100K chars**
  1. Workflow internally chunks (Step 6 of base skill). Adapter ничего особо не делает.
  2. Если subprocess превышает timeout (`> 10 min`) — fail-fast с предложением вручную разбить transcript.

- **A6: LLM API недоступен**
  1. Subprocess fails. Behaves как A2.

- **A7: Mermaid syntax invalid в output**
  1. Workflow's self-check (12-point checklist) ловит это и регенерирует.
  2. Если 3 попытки fail — workflow возвращает summary без Mermaid + warning. Adapter принимает (markdown валидный).

- **A8: Concurrent `/ingest-source --kind transcript` на тот же source**
  1. Adapter ensures `<vault>/_raw/.locks/` exists (`mkdir -p`) и acquires `flock(<vault>/_raw/.locks/transcript-<sha256(abs(source))[:12]>.lock)` (exclusive, non-blocking try first, blocking second-try до timeout=60s). **Rationale**: lock-file location привязан к `abs(source)` (matches A4 idempotency scope), а не к `<output>` — `<output>` dir может не существовать на первом запуске, и mkdir его до acquisition порождает TOCTOU; `_raw/.locks/` создаётся `wiki-init` (R-05.2) и всегда доступен.
  2. Если lock уже занят — waiting invocation после release повторно проверяет `source_state.source_hash` (A4 short-circuit). Если первый запуск успешно записал hash → second sees match → skip LLM (no double-spend).
  3. Если первый запуск crashed без записи hash — second берёт lock и запускает workflow.
  4. На timeout=60s ожидания lock → `{error: 'CONCURRENT_INGEST_TIMEOUT', hint: 'Another transcript ingest is in progress'}`.

- **A9: Stub-laden output (Content Fingerprint содержит unrendered placeholders)**
  1. Adapter parses `Content Fingerprint` block, extracts `Total concepts extracted: <N>`.
  2. Если `<N>` literally `{{N}}` или non-integer ИЛИ `< 1` → `{error: 'WORKFLOW_INCOMPLETE', reason: 'unrendered_template_placeholders'}`. Move partial output в `_raw/failed/`.
  3. Same check for `Source files:` — line должна содержать non-empty filename, не `{{file1.txt}}`.

**Postconditions:**
- 1 файл `<output>/summary.md` с `type: lesson-summary` frontmatter (на диске).
- 1 row в `pages` с `type='summary'` (в DB), tags содержит `lesson-summary` + slugified concepts.
- `page_entity_refs` rows для body wiki-links (НЕ для frontmatter `prerequisites` — те остаются в `frontmatter_json`).
- 1 row в log с event=ingest, kind=transcript.

**Acceptance Criteria:**
- ✅ После ingest: `SELECT type FROM pages WHERE slug='<slug>'` returns `'summary'` (НЕ `'lesson-summary'`).
- ✅ `SELECT 1 FROM pages, json_each(json_extract(frontmatter_json, '$.tags')) WHERE slug='<slug>' AND value='lesson-summary'` returns row.
- ✅ File on disk: `cat <output>/summary.md | head -5 | grep '^type: lesson-summary'` succeeds (file frontmatter preserves original).
- ✅ FTS5 body не содержит Mermaid syntax: `SELECT count(*) FROM pages_fts WHERE pages_fts MATCH 'flowchart LR'` = 0 даже если файл содержит `flowchart LR` в Mermaid block.
- ✅ FTS5 body не содержит HTML-anchors: `SELECT count(*) FROM pages_fts WHERE pages_fts MATCH 'SECTION:agent-metadata'` = 0.
- ✅ **Generic HTML comments preserved** в FTS5: body с `<!-- TODO: revisit -->` строкой → `SELECT count(*) FROM pages_fts WHERE pages_fts MATCH 'TODO'` ≥ 1 (whitelist regex по `SECTION:` prefix не должен трогать generic comments).
- ✅ **Unclosed Mermaid fence rejected**: body с строкой ` ```mermaid\nflowchart` БЕЗ closing ` ``` ` → upsert fails с `BodyNormalizationError`; SQLite не получает partial-stripped body. AC test required (R-07.5 anti-tail-eat).
- ✅ Все `concepts[]` из frontmatter slugified и добавлены в `tags`: `json_extract(frontmatter_json, '$.tags')` superset slugified(concepts) через `python-slugify` (`slugify("OAuth 2.0") == "oauth-2-0"`, `slugify("C++") == "c"` — известная lossy normalization, documented in R-07.4).
- ✅ **Concepts vs tags split**: оригинальные значения сохранены в `json_extract(frontmatter_json, '$.concepts')`; slugified — в `$.tags`. Collision (`"AI"` + `"a.i."` → `"ai"`) логируется как INFO в lint report (НЕ error).
- ✅ `prerequisites[]` присутствуют в `frontmatter_json`, НЕ в `page_entity_refs` (MVP behavior; promotion ⇒ Epic 7).
- ✅ Все refs из body wiki-links имеют `trust_level='medium'`.
- ✅ Idempotency: re-ingest того же transcript → `action='unchanged'`, `llm_tokens_used=0` (skip LLM re-gen).
- ✅ Workflow validation: missing `<!-- SECTION:agent-metadata -->` marker → `{error: "WORKFLOW_INCOMPLETE"}`, SQLite unchanged.
- ✅ Path-traversal: `--source ../../etc/passwd` → `{error: "PATH_OUTSIDE_VAULT"}`, subprocess не запускается.
- ✅ Latency: end-to-end ≤ 5 min для 30-min transcript (LLM-bound; не входит в §5.1 SLOs т.к. это LLM-call, не hot path).

---

### 5. Non-Functional Requirements

#### 5.1 Performance (numerical SLOs)

Из [TASK-ref-v2.md §28](./TASK-ref-v2.md). MVP-минимум — measurable benchmark на synthetic vault (R-14):

| Операция | 100 docs | 1000 docs | 10000 docs |
|---|---|---|---|
| `wiki-search "term"` | < 30ms | < 50ms | < 100ms |
| `wiki-index-upsert` | < 50ms | < 100ms | < 100ms |
| `wiki-index-render` | < 200ms | < 1s | < 5s |
| `wiki-lint` full | < 500ms | < 2s | < 30s |
| `wiki-reindex --full` | < 2s | < 20s | < 3min |
| `wiki-reindex --delta` (no changes) | < 100ms | < 500ms | < 2s |

**Verification**: benchmark-suite (R-14) автоматизирует измерение. CI fails если > target.

#### 5.2 Security

- **Никаких credentials в SQLite**. MCP/Auth tokens — `~/.config/wiki-mcp/keys.env` (env-file, не в репо).
- **SQL injection защита** — все queries через parameterized statements (`?` для SQLite). Никакого f-string concatenation для user-input в SQL.
- **Path traversal защита** — `wiki-source-manual` validates что path — внутри `vault_root` (для предотвращения `../../../etc/passwd`-attacks).
- **iCloud-coruption защита** — DB вне iCloud (R-03), warning при попытке override.

#### 5.3 Compatibility

- Python 3.11+ (для `match` statements + structural pattern matching, type hints).
- macOS, Linux primary; Windows best-effort.
- SQLite 3.38+ (для `JSON_EXTRACT` совместимости + FTS5 unicode61 tokenizer).
- Obsidian compatibility: `[[wiki-link|display]]` синтаксис, `<!-- ... -->` HTML comments OK.
- Markdown совместим с GitHub-flavor для `tmp2/` файлов.

#### 5.4 Idempotency

- **Все state-mutation скиллы** должны быть идемпотентны: повторный запуск с тем же input → same output / no extra changes.
- Conformance-tests в Epic E5.

---

### 6. Constraints and Assumptions

#### 6.1 Technical Constraints

- **Single-writer SQLite в MVP** — concurrent writers решаются через `BEGIN IMMEDIATE` блокировку (acceptable trade-off для personal-use). Multi-writer = future Epic 8 (Postgres).
- **No vector layer в MVP** — sqlite-vec opt-in, не включается по default. Все search в MVP — FTS5 only.
- **No multi-source в MVP** — только manual + transcript + light adapters. Email/telegram/web — future Epic 6.
- **No verify ensemble в MVP** — `wiki-verify-multi` future Epic 7.
- **Code location** (resolved): этот репо `obsidian-llm-wiki/`. Скиллы под `skills/wiki-*/`, Python DAL под `scripts/wiki_index/`, source adapters под `scripts/wiki_source/`.
- **`pages.project` PK fix** (CRITICAL): В schema (`SCHEMA-DRAFT.sql`) `project` имеет `NOT NULL DEFAULT '_vault_'`. Это sentinel для vault-wide pages, replacing NULL. Reason: SQLite (и ANSI SQL) treat NULLs in composite PK as distinct → `(slug, NULL)` × 2 = duplicate rows → idempotency нарушен. Aligned: `page_entity_refs.page_project` тоже NOT NULL DEFAULT '_vault_'. Все wiki-* скиллы при `project IS NULL`/missing → используют `'_vault_'`.
- **`required_frontmatter` для flat layout**: `wiki-init --layout flat` записывает в CLAUDE.md `lint.required_frontmatter: [type, title, date, tags]` (без `project`). Для `per-project` layout — `[type, title, date, tags, project]`.
- **Type-mapping rule (Karpathy-vault ↔ SQLite CHECK constraint)** [CRITICAL — affects R-07/R-24/UC-06/UC-07]: SCHEMA `pages.type` CHECK enum = `{summary, concept, query, brief, research, index, log}`. Frontmatter `type:` для специализированных summaries использует Obsidian-friendly значения, которые **на upsert нормализуются к одному из allowed enum-значений + тег-маркер**:
  | Frontmatter `type:` | DB `pages.type` | Tag-маркер (JSON-array `tags`) | Producer |
  |---|---|---|---|
  | `summary` | `summary` | — | `wiki-source-manual` (existing summaries) |
  | `summary-light` | `summary` | `summary-light` | `/wiki-enrich` (R-24 superseded → wiki-ingest manifest) |
  | `lesson-summary` | `summary` | `lesson-summary` | `/wiki-enrich` (R-06.3 superseded → wiki-ingest manifest) |
  | `meeting-summary` | `summary` | `meeting-summary` | future `wiki-source-meeting` (out of MVP, future Epic) |
  | `concept` | `concept` | — | future entity-resolver (Epic 7) |
  | `query` | `query` | — | future `/wiki-query` (Epic 7) |
  | `brief`, `research`, `index`, `log` | identity | — | future Epics |
  
  **Rationale**: schema-stability (single CHECK enum, < 10 values) vs Karpathy semantics (богатая taxonomy). Маркеры в tags позволяют filter через FTS5 без расширения CHECK при каждой новой kind. Файл на диске сохраняет оригинальный `type:` для Obsidian/agent compatibility — расхождение file↔DB **документировано** и **детерминированно** (mapping table выше). Расширение CHECK enum для добавления первоклассных типов (e.g., `prerequisite` для `page_entity_refs.ref_type`) — explicit Schema Change Request в future Epic, НЕ ad-hoc.

- **Karpathy-deviation (MVP intentional gap)**: Karpathy llm-wiki spec ([Reference/karpathy/llm-wiki.md §Operations:Ingest](../Reference/karpathy/llm-wiki.md)) утверждает «a single source might touch 10-15 wiki pages» — cross-page concept updates, backlink injection, contradiction flagging. **MVP intentionally violates this**: ingest (UC-02/UC-06/UC-07) touches source-page + `index.md` regen (R-08) + log row + (для transcript) `source_state` row. **Cross-page concept-promotion и contradiction-detection ⇒ Epic 7** (entity-resolver R-18, `wiki-extract-concepts`). Justification: type-safe entity resolution требует stable `entities` table + canonicalization logic (cybos two-tier confirmed/candidate pattern) — закладывается в Epic 7, не в MVP. **Trade-off acknowledged**: MVP wiki — не полная Karpathy compounding-artifact, а foundation layer (markdown + FTS5 + lint) на котором Epic 7 строит cross-page maintenance.

#### 6.2 Business Constraints

- **MVP — для одного пользователя** (innokentiy.georgievskiy@mdcloud.tech), один vault.
- **Open source** (или internal use) — нет PII protection требований сверх R-Privacy.
- **Бюджет токенов** [auditable математика — runtime verification через `llm_tokens_used` JSON field из UC-06 step 9 / UC-07 step 12]:
  - **Model pinning**: `wiki.transcript.model` в CLAUDE.md `wiki:` block, default `claude-sonnet-4-6` (latest stable Sonnet, knowledge cutoff Jan 2026). Price-table (Anthropic public pricing as of 2026-05): Sonnet 4.6 = $3 / $15 per M input/output tokens. Haiku 4.5 = $0.80 / $4 per M. Эти числа должны сверяться при benchmark-suite runs (R-14).
  - **MVP hot path** (search/lint/upsert/render) — pure SQL, **zero LLM**, $0/run.
  - `wiki-source-manual`: 0 LLM calls (re-index existing markdown).
  - `wiki-source-transcript`: **multi-pass** workflow (НЕ single-call) — `/generate-detailed-meeting-summary` запускает: (a) format detection, (b) chunking при > 100K chars (1 LLM call per ~50K-block с 2K overlap), (c) educational content extraction (1 large call), (d) Mermaid generation в рамках того же extraction, (e) self-check 12-point checklist (потенциально дополнительный re-scan), (f) optional Mermaid regeneration (до 3 retry — bounded). Concrete math для типичного 30-min transcript (~22K words ≈ 30K-40K input tokens на Cyrillic, ~25K-30K на Latin):
    - 30-min EN transcript: 40K input + 15K output ≈ **$0.35** (Sonnet 4.6).
    - 30-min RU transcript: 50K input + 18K output ≈ **$0.42** (Cyrillic ~3 chars/token vs ~4 для Latin).
    - 90-min transcript с chunking (3 × 50K blocks): 150K input + 35K output ≈ **$0.98**.
    - Worst-case (Mermaid retries × 3): + ~5K output ≈ +$0.075.
  - `wiki-light-summary`: ~1-3K tokens, single call (Haiku по default — `wiki.light_summary.model='claude-haiku-4-5'`). ~$0.001-0.005 per call.
  - **MVP validation budget**: tmp2/ (16 уже-сгенерированных summaries) → 0 LLM calls (manual re-index only). Для realistic ingestion 16 новых 30-min transcripts: **~$5-7 total** (Sonnet 4.6). CI/benchmark runs (R-14) NOT использует real LLM — synthetic vault generator создаёт fake summary files с заранее-заполненным frontmatter.
  - **Cost verification**: R-14 benchmark suite добавляет dimension `llm_tokens_used` per ingest-operation; CI compares actual vs budgeted (±30% tolerance) и fails при overspend.

#### 6.3 Assumptions

- `summarizing-meetings` skill доступен через git-submodule в `~/.claude/skills/` (см. Q-2 resolution).
- Пользователь иметь Python 3.11+ установленный (CLAUDE.md `LOCAL DEVELOPMENT RULES`: `pip + .venv`).
- Vault в iCloud Obsidian — допустимый, но обязателен workaround (R-03).
- `tmp2/` 16 файлов — представительный test-corpus для MVP validation.
- **Тестовая среда iCloud detection**: используется fixture-vault в `/private/tmp/wiki-test-vault/Mobile Documents/iCloud~md~obsidian/test-vault/` (используется `/private/tmp/` — не `/tmp/` — потому что macOS `/tmp` симлинк на `/private/tmp`, что может trip iCloud-detection regex).
- **Real iCloud-vault validation** делается на не-iCloud копии vault'а (например, `rsync -a ~/Library/Mobile Documents/.../ObsidianNotes/ /tmp/wiki-validation/`) для предотвращения коррупции реальных данных при отладке.

---

### 7. Open Questions

#### 7a. RESOLVED (decisions captured in §6 Constraints)

- **Q-1: Code location** — ✅ this repo `obsidian-llm-wiki/` (см. §6.1).
- **Q-2/Q-5: `summarizing-meetings` integration** — ✅ git-submodule в `~/.claude/skills/summarizing-meetings/` (или симлинк через user choice). transcript adapter включён в MVP (R-06.3 ✅).
- **Q-3: iCloud detection testing** — ✅ fixture-vault в `/private/tmp/wiki-test-vault/Mobile Documents/iCloud~md~obsidian/test-vault/` для integration; monkey-patch `Path` для unit tests (см. §6.3).
- **Q-4: Python package manager** — ✅ `pip + .venv` per CLAUDE.md.
- **Q-6: Validation vault** — ✅ `tmp2/` для bulk-migration check (R-13); `tests/fixtures/minimal-vault/` для unit/integration; `/private/tmp/wiki-validation/` (rsync copy не-iCloud) для realistic e2e.

#### 7b. Defer-able (may be answered during Plan/Dev phases)

- **D-1: Embedding модель для Epic 8 vector layer** — `all-MiniLM-L6-v2` (384-dim, fast, multilingual ok) vs `text-embedding-ada-002` (1536-dim, OpenAI, more accurate). Out of MVP scope; решается при включении vector layer.
- **D-2: light-summary LLM model choice** — Claude Haiku 4.5 (fast, cheap, ~$0.001/call) vs Sonnet (slightly better quality, ~$0.005/call). Default Haiku for cost; configurable in `wiki.light_summary.model`.
- **D-3: Cron / launchd для daily automation** — macOS launchd vs cron vs скрипт-демон. Out of MVP (R-06 future Epic).
- **D-4: Plugin packaging** — после MVP стабилизирован, упаковать в Claude Code plugin format. Out of MVP.

#### 7c. Out-of-scope (explicit non-goals)

- Multi-vault sync через cloud (CRDT/git-merge на SQLite) — never.
- Web UI for `wiki-search` — нет, CLI/Obsidian-only.
- Mobile-direct ingestion (Obsidian Mobile + Pythonista) — out of MVP, future research.

---

## Verification

После завершения этого TASK (имплементации Epics E1-E5):

1. На `tmp2/` после migration: 16 entries в SQLite, `wiki-search "shadow ai"` < 50ms возвращает ≥ 3 hits.
2. На synthetic vault 1000 docs: все SLOs из §5.1 проходят.
3. `wiki-lint` идентифицирует known orphans (`[[Школа менеджмента Стратоплан]]` и т. п.).
4. Re-ingest того же файла → no-op (idempotency).
5. iCloud detection: на `/tmp/fake-icloud/Mobile Documents/iCloud~md~obsidian/test/` → DB пишется в `~/Library/Application Support/wiki-index/` (НЕ внутрь fake-icloud).
6. **Transcript ingestion (via `/wiki-enrich`)** (replaces former UC-07 verification): `/wiki-enrich --vault <vid> --source <transcript>` на real lesson-transcript (e.g., `Lessons/ZeroOne Systems/.../lesson.txt`) → wiki-ingest синтезирует `_sources/<slug>.md` + concept/entity pages, manifest валиден, `wiki-enrich` индексирует все `written[]` paths в SQLite одной операцией, `log_event` мирорится в `log_events`, Mermaid-блоки НЕ попали в FTS5, `wiki-search "Sharpe score" --vaults <vid>` находит результат с BM25 ranking.

Если все 6 пунктов проходят — MVP готов, можно начинать Epic 6 (multi-source).
