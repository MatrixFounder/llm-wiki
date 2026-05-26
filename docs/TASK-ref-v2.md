# TASK-ref-v2: Karpathy-style LLM Wiki + cybos-style multi-source — гибрид с SQLite-первым индексом и pluggable source adapters

> **Статус**: Спецификация. Кода ещё нет.
> **Версия**: v2.0 (преемник [TASK-ref.md](./TASK-ref.md) v1.0).
> **Связанные документы**:
> - [SCHEMA-DRAFT.sql](./SCHEMA-DRAFT.sql) — DDL индексирующего слоя.
> - [SQLITE-VS-POSTGRES.md](./SQLITE-VS-POSTGRES.md) — выбор backend'а + DAL.
> - [MIGRATION-v1-to-v2.md](./MIGRATION-v1-to-v2.md) — переход с v1.

## Что нового по сравнению с v1

v1 — анализ соответствия Karpathy-канону + план реализации только wiki-методологии поверх manual transcripts. v2 расширяет под use-case **«много документов + скорость + email/telegram/external»**, добавляя:

1. **SQLite-индекс (FTS5+WAL)** как фундамент скорости (см. §27 + [SCHEMA-DRAFT.sql](./SCHEMA-DRAFT.sql)).
2. **Pluggable Source Adapters** — email, telegram, web research, manual; общий контракт (см. §15.bis–§15.quin).
3. **Cross-source aggregator** `wiki-brief` — daily digest из всех источников (см. §15.sex).
4. **Provenance v1.1** — `source_quote` + `source_span` + `trust_level` обязательны (см. §16, §27).
5. **Two-tier entity resolution** — confirmed vs candidate, multi-stage matching (§12).
6. **iCloud-aware**: SQLite вне vault'а, markdown в iCloud (§6.4).
7. **MCP fallback chain** (§24).
8. **Daily automation** (§22 + §26 решение #10).
9. **Performance budget & SLOs** — численные таргеты на 100/1000/10000 документов (§28).
10. **Postgres как opt-in** через DAL — для корпусов > 100K (§13 v1, документ [SQLITE-VS-POSTGRES.md](./SQLITE-VS-POSTGRES.md)).

Все правки сохраняют идею Karpathy: markdown — единственный source-of-truth; SQLite — derivative cache, который пересобирается из markdown. Выбросы: `index.md` как mutable file (теперь read-only projection из БД).

---

# ЧАСТЬ I — АНАЛИЗ СОВМЕСТИМОСТИ С КАНОНОМ KARPATHY

## 1. Канон Karpathy (выжимка из [gist 442a6bf5](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f))

Архитектура из 3 слоёв:

1. **Raw sources** — неизменяемые исходники (статьи, видео, транскрипты, **emails, telegram messages, web pages** — расширение под v2).
2. **Wiki** — LLM-сгенерированные markdown-страницы: summaries, entity pages, concept pages, comparisons, overview, synthesis.
3. **Schema** — конфигурационный документ (типа `CLAUDE.md`), который «makes the LLM a disciplined wiki maintainer rather than a generic chatbot».

Ключевая идея: «the wiki is a persistent, compounding artifact … the knowledge is compiled once and then *kept current*, not re-derived on every query».

3 операции:

- **Ingest** — LLM читает источник, обсуждает takeaways, пишет summary page, **обновляет index, обновляет relevant entity / concept pages, аппендит запись в log**.
- **Query** — поиск по wiki, синтез ответа с цитатами; ценные ответы **filed back as new pages**.
- **Lint** — health-check: contradictions between pages, stale claims, **orphan pages**, missing cross-references, data gaps.

Поддерживающие файлы: `index.md` (catalog по категориям, ссылка + однострочное summary), `log.md` (chronological append-only, parseable префиксы вида `## [2026-04-02] ingest | Article Title`).

Cross-references — «as valuable as the documents themselves» (отсылка к Memex Буша).

Главный анти-паттерн, на который явно указывает gist: жёсткая прескриптивность форматов. «Everything mentioned above is optional and modular — pick what's useful, ignore what isn't». То есть канон — про *операционный цикл*, а не про *шаблон страницы*.

## 2. Что фактически делает skill `summarizing-meetings` + workflow

На вход — один или несколько транскриптов одного урока. На выход — **один** richly-structured markdown-файл со следующими атрибутами (см. реальный пример `tmp2/day1-01-savochka-rukovoditel-2026.md`):

- YAML frontmatter с `type`, `title`, `tags`, `related: [[wiki-links]]`, плюс educational-расширение: `concepts: [...]`, `prerequisites: [[...]]`, `speaker`, `course`, `module_number`, `lesson_number`.
- **Pyramid Level 1**: `## Резюме верхнего уровня` (TL;DR) + `## Что запомнить` (takeaways).
- **Pyramid Level 2**: 5 фиксированных подсекций — Concepts / Structure / Techniques / Examples / Relationships.
- **Pyramid Level 3 (Agent Metadata)**: `Semantic Index`, `Concept Definitions`, `Chunk Boundaries`, `Content Fingerprint`.
- HTML-якоря `<!-- SECTION:* -->` — language-agnostic навигация для агентов.
- Tag taxonomy enforcement через `tag_taxonomy.md`.
- Self-check + completeness guarantee внутри одной страницы.

В v2 этот скилл становится **одним из source adapters** (`source_kind = transcript`), а не единственным ingest-путём. Email/telegram/web — это другие adapters со своими шаблонами output'а, но индексируются в ту же SQLite.

## 3. Совместимость со страницей-как-такой («summary page»)

**Очень высокая.** На уровне отдельной страницы выход даже более дисциплинирован, чем минимум канона:

| Канон Karpathy | Skill/workflow |
|---|---|
| Markdown-файл, Obsidian-friendly | ✅ нативно |
| YAML-метаданные | ✅ полный фронтматтер |
| Cross-references как ценность | ✅ `related: [[…]]`, `prerequisites: [[…]]` |
| Concept pages (атомарные понятия) | ⚠️ концепты *перечислены* в `concepts:` и определены в machine-readable таблице, но не вынесены в **отдельные** страницы (закрывает §12) |
| Schema disciplines the LLM | ✅ SKILL.md + workflow + generation_prompt.md + tag_taxonomy.md играют роль schema/CLAUDE.md |
| Citations / quotes | ✅ `## Ключевые цитаты спикера` |
| Chunk boundaries для RAG | ✅ явно прописаны |
| Tone, granularity, structure | ✅ pyramid + anchors + Mermaid |
| **Provenance (v1.1)** | ⚠️ Цитаты есть, но без machine-readable `source_quote/span/trust_level` — закрывается v2 (§27) |

**Параллельно** — этот же дизайн валидирован проектом [Gerstep/cybos](https://github.com/Gerstep/cybos), который реализует Karpathy-канон на VC-операциях с теми же примитивами (file-first markdown + SQLite index + multi-source). См. §29.

## 3.bis Что такое **concept page** (entity page) в каноне Karpathy

В выводе скилла есть фронтматтер `concepts: [Shadow AI, Workслоп, ...]` и таблица «Concept | Definition | Related». Это **перечень концептов внутри одной summary-страницы** — концепты живут *внутри* лекции.

Karpathy же говорит про **отдельные файлы-носители концепта** — `wiki/concepts/shadow-ai.md`. Этот файл:

- содержит **одну каноническую формулировку** (1–3 предложения), общую для всего vault'а;
- хранит список `appears_in: [[lesson1]], [[lesson2]], …` — обратные ссылки;
- линкует **related concepts**;
- **накапливает** упоминания: каждый ingest добавляет, не перезаписывает.

Зачем:
- **Один клик — одна страница**. `[[Shadow AI]]` ведёт в одно место с канонической формулировкой.
- **Граф знаний.** `Concepts/` — узлы; backlinks — рёбра.
- **Накопление контекста.** 5 лекций про «Shadow AI» → один синтез на concept-странице.
- **Дедупликация.** «Workслоп» / «AI слоп» → один slug `workslop`, alias `AI слоп`.

В v2 concept pages — частный случай **entities**. Все entities (concept, person, company, product, group) хранятся в одной таблице `entities` с разделением по `type`-полю (см. [SCHEMA-DRAFT.sql](./SCHEMA-DRAFT.sql) §1). Это — расширение канона под multi-source: имена людей и компаний резолвятся тем же механизмом, что и концепты.

## 4. Что в каноне покрывает skill+workflow, а что — нет (расширенная таблица)

**Скилл по дизайну делает summary-page и делает её отлично.** Остальные операции — отдельные артефакты v2.

| Часть канона | В scope `summarizing-meetings`? | Где добирается в v2 |
|---|---|---|
| Обновление `index.md` после ingest | вне scope | `wiki-index-upsert` (§10), генератор `wiki-index-render` |
| Append в `log.md` | вне scope | `wiki-append-log` с ротацией (§11) |
| Concept pages как отдельные файлы | вне scope | `wiki-extract-concepts` + entity-resolver (§12) |
| Cross-page Lint | вне scope | `wiki-lint` SQL-based (§13) |
| Query операция | вне scope | `wiki-query` RAG (§14) |
| «kept current, not re-derived» | частично | мета-workflow `ingest-source` (§15) с reconciliation |
| Dangling links | детектируются, не чинятся | `wiki-lint` + `wiki-research` (§24) |
| **Multi-source ingestion (email/telegram/web)** | вне scope (только transcripts) | **NEW**: `wiki-source-{email,telegram,web,manual}` (§15.ter–quin) |
| **Cross-source aggregation** | нет | **NEW**: `wiki-brief` (§15.sex) |
| **Index Layer (FTS+vector)** | нет (file-walking) | **NEW**: SQLite FTS5+WAL (§27, [SCHEMA-DRAFT.sql](./SCHEMA-DRAFT.sql)) |
| **Provenance v1.1** | citations, без machine-readable | **NEW**: source_quote/span/trust_level обязательны (§16, §27) |

## 5. Итоговый ответ на вопрос пользователя

1. **«Сами summary будут ли корректно следовать канону?»** — Да. На уровне отдельной страницы выход skill+workflow совместим с Karpathy и превосходит минимальные требования (HTML-якоря, Concept Definitions, Chunk Boundaries — бонус сверх канона). Любую из 16 страниц `tmp2/` можно использовать в LLM-wiki без переработки.

2. **«Совместим ли с подходом и принципами LLM wiki?»** — Да, как **компонент**. Skill закрывает один кирпич — генерацию summary-page. Остальные кирпичи — отдельные артефакты v2.

3. **«Будет ли работать с множеством документов и multi-source быстро?»** — Только если поверх skill'а поставить **индексирующий слой** (SQLite+FTS5+WAL) и **pluggable adapters** для email/telegram/web. Без этого file-walking упирается в O(N) на каждый запрос. Этот документ — план такой надстройки.

4. **Практическая рекомендация (полная методология)** — `summarizing-meetings` остаётся как есть, поверх него:
   - `wiki-init` — bootstrap vault'а + SQLite + директории.
   - `wiki-index-upsert` / `wiki-index-render` — DB upsert + read-only `index.md` projection.
   - `wiki-append-log` — chronological log с ротацией.
   - `wiki-extract-concepts` (+ entity-resolver) — выносит концепты в `Concepts/<slug>.md`.
   - `wiki-search` — FTS5 + опц. vector.
   - `wiki-lint` — SQL-based health-check.
   - `wiki-query` — RAG поверх FTS5 retrieval.
   - **NEW**: `wiki-source-email`, `wiki-source-telegram`, `wiki-source-web` — pull-источники.
   - **NEW**: `wiki-brief` — cross-source daily digest.
   - **NEW**: `wiki-research` (опц.) — web enrichment концептов.
   - **NEW**: `wiki-verify-multi` (опц., default off) — 4-критика ensemble.

   Над всем этим — `CLAUDE.md` в корне vault'а в роли schema (Karpathy-канон).

## 6. Где физически лежат скиллы и `CLAUDE.md` при множестве Obsidian-папок

Канон Karpathy сам подсказывает разделение: **skills = engine (универсальный код), CLAUDE.md = schema (под конкретный домен/vault)**.

### 6.1 Раскладка

| Что | Где | Почему |
|---|---|---|
| `wiki-*` (engine) | `~/.claude/skills/wiki-*/` или плагин | один экземпляр, доступен из любой CWD |
| `summarizing-meetings` | где сейчас (Universal-skills репо) | engine остаётся engine'ом |
| `CLAUDE.md` (schema) | в корне каждого vault'а | Claude Code читает снизу вверх |
| `index.md`, `log.md`, `Concepts/`, `Summaries/`, **`Sources/`** | внутри vault'а | per-vault state |
| **SQLite DB** (`wiki-index/<hash>.db`) | **ВНЕ vault'а** (см. §6.4) | предотвращает iCloud-коррупцию |
| Tag taxonomy | базовая в скилле, per-vault — в `taxonomy.md` рядом с `CLAUDE.md` | global + домен |

### 6.2 Что должен содержать `CLAUDE.md` (root)

См. §8.1 для полной schema. Минимум:

```yaml
wiki:
  version: 2
  language: ru
  layout: per-project
  index:
    backend: sqlite                 # sqlite | postgres
    location:
      sqlite:
        path: ~/.local/share/wiki-index/{vault_hash}.db
  sources: [transcript, email, telegram, web, manual]
  automations:
    daily_reindex: true
    daily_brief: true
```

### 6.3 Запуск

```bash
cd ~/Obsidian/MyVault
claude
> /wiki-init                                  # один раз
> /wiki-source-email --sync                   # по запросу
> /ingest-source --source _raw/lecture-01.txt # transcript
> /wiki-brief                                 # daily digest
> /wiki-search "shadow ai"
```

При первом запуске `wiki-init` создаёт SQLite вне vault'а, директории внутри vault'а, начальный `CLAUDE.md` если отсутствует.

### 6.4 SQLite database location vs iCloud (NEW)

**Критическое правило**: SQLite-файл **никогда** не лежит в iCloud-vault'е. Иначе через 2–4 недели — гарантированная коррупция (см. [SQLITE-VS-POSTGRES.md §5](./SQLITE-VS-POSTGRES.md#5-critical-workaround-sqlite--icloud)).

Default paths по платформам:

| Платформа | Default path |
|---|---|
| macOS | `~/Library/Application Support/wiki-index/<vault_hash>.db` |
| Linux | `~/.local/share/wiki-index/<vault_hash>.db` |
| Windows | `%LOCALAPPDATA%\wiki-index\<vault_hash>.db` |

`<vault_hash>` = `sha256(absolute_vault_root_path)[:12]`. Это позволяет иметь несколько vault'ов с непересекающимися БД.

`wiki-init` детектит iCloud-путь vault'а (содержит `Mobile Documents/iCloud~`) и:
1. Forces DB-путь вне iCloud.
2. Печатает warning пользователю: «vault в iCloud → SQLite вне iCloud (correct), reindex произведётся локально на каждом устройстве».
3. Создаёт `.icloud-vault-marker` в vault'е (так другие устройства поймут это).

**Multi-device behavior**:
- Каждое устройство (Mac, iPad, iPhone) имеет свой локальный SQLite.
- Markdown синкается через iCloud.
- Полный rebuild SQLite ≈ 1-5s на 1000 docs — это нормальный delay при первом запуске на новом устройстве.

### 6.5 Альтернатива через плагин

Если vault'ов 5+, упаковать `wiki-*` как Claude Code plugin → `.claude-plugin/`. В каждом vault'е остаётся только `CLAUDE.md`.

### 6.6 Анти-паттерны

- ❌ Класть `wiki-*` скиллы в `.claude/skills/` **внутри vault'а** — дублируется, версии расходятся.
- ❌ Класть `index.md` / `log.md` глобально — это per-vault state.
- ❌ Класть SQLite в iCloud-vault — коррупция (см. §6.4).
- ❌ Зашивать пути в скиллах — vault'ы устроены по-разному. Скилл *читает* пути из `CLAUDE.md`.
- ❌ Полагаться на cross-device SQLite sync через любой облачный сервис (Dropbox, OneDrive, iCloud) — все ломаются на бинарном WAL.

---

# ЧАСТЬ II — ДЕТАЛЬНЫЙ ПЛАН РЕАЛИЗАЦИИ

## 7. Scope и deliverables (расширенный)

| # | Артефакт | Тип | Tier | Что нового vs v1 |
|---|---|---|---|---|
| 1 | `wiki-config.schema.yaml` | JSON Schema | — | Расширена под `index`/`sources`/`automations`/`mcp` |
| 2 | [SCHEMA-DRAFT.sql](./SCHEMA-DRAFT.sql) | SQL DDL | — | **NEW** |
| 3 | `wiki-init` | skill | 2 | Создаёт SQLite, детектит iCloud |
| 4 | `wiki-reindex` | skill | 1 (script-first) | **NEW**: full / delta / extract-only modes |
| 5 | `wiki-index-upsert` (replaces `wiki-update-index`) | skill | 1 | Пишет в SQLite, не в `index.md` |
| 6 | `wiki-index-render` | skill | 1 (script) | **NEW**: regenerates `index.md` from SQLite |
| 7 | `wiki-append-log` | skill | 1 | + ротация по месяцам |
| 8 | `wiki-extract-concepts` | skill | 2 | + entity-resolver, two-tier |
| 9 | `wiki-search` | skill | 1 | FTS5-backed (was file-walking) |
| 10 | `wiki-lint` | skill | 1 | SQL-based (was file-walking) |
| 11 | `wiki-query` | skill | 2 | RAG over FTS5 retrieve |
| 12 | `wiki-source-manual` | skill | 1 | Wraps existing `summarizing-meetings` for transcripts (current ingest path) |
| 13 | `wiki-source-email` | skill | 2 | **NEW**: gmail-MCP + state.json dedup |
| 14 | `wiki-source-telegram` | skill | 2 | **NEW**: GramJS direct, per-person aggregation |
| 15 | `wiki-source-web` | skill | 2 | **NEW**: MCP fallback chain (exa→perplexity→firecrawl) |
| 16 | `wiki-brief` | skill | 1 | **NEW**: cross-source daily digest |
| 17 | `wiki-research` | skill | 2 | + apply-via-MCP |
| 18 | `wiki-verify-multi` | skill | 2 | Default off (was on) |
| 19 | `ingest-source` | meta-workflow | — | Обобщён до multi-source dispatcher |
| 20 | Шаблоны: `index.md`, `log.md`, `concept.md`, `brief.md`, `email.md`, `telegram.md`, `CLAUDE.md` | assets | — | Расширены |
| 21 | DAL: `IndexRepository` interface + `SQLiteRepository` + (opt) `PostgresRepository` | code | — | **NEW** |
| 22 | Benchmark suite | tests | — | **NEW**: synthetic vault generator + SLO checker |

**Не входит в этот план**:
- Переписывание `summarizing-meetings`. Скилл остаётся, оборачивается `wiki-source-manual`.
- Конкретный embedding-модель — выбор пользователя (miniLM-384 / OpenAI ada-1536 / etc.).
- Postgres-backend как обязательная цель — это opt-in, реализуется по запросу.

## 8. Schema — расширенная

Двухслойная конфигурация остаётся (root `CLAUDE.md` + per-project `.wiki.yaml`), но schema получает новые блоки.

### 8.1 Root `CLAUDE.md` (один на vault)

```yaml
# ~/Obsidian/MyVault/CLAUDE.md (YAML-блок внутри markdown)
wiki:
  version: 2
  language: ru                              # ru | en | mixed
  layout: per-project                       # per-project | flat

  # ===== Vault-wide layout (per-project) =====
  project_root: "03-Projects/"
  vault_paths:
    global_index:    "00-Vault-Index/index.md"
    global_log:      "00-Vault-Index/log.md"
    taxonomy:        "00-Vault-Index/taxonomy.md"
    vault_concepts:  "00-Vault-Index/00-Vault-Concepts/"

  project_paths:
    index:        "{project}/index.md"
    log:          "{project}/log.md"
    summaries:    "{project}/Summaries/"
    concepts:     "{project}/Concepts/"
    queries:      "{project}/Queries/"
    research:     "{project}/Research/"
    briefs:       "{project}/Briefs/"           # NEW
    sources_dir:  "{project}/Sources/"          # NEW: aggregator for email/telegram/web
    raw_sources:  "{project}/_raw/"

  naming:
    summary: "{date}-{slug}/"                   # CHANGED: subfolder, не flat-file
    concept: "{slug}.md"
    query:   "{date}-{question-slug}.md"
    brief:   "{date}-brief.md"
    email:   "{date}_{from-slug}_{subject-slug}/"
    telegram_per_person: "{slug}.md"

  # ===== NEW: Index layer (SQLite/Postgres) =====
  index:
    backend: "sqlite"                           # sqlite | postgres
    location:
      sqlite:
        path: "~/.local/share/wiki-index/{vault_hash}.db"
        # macOS auto: ~/Library/Application Support/wiki-index/...
      postgres:
        url: "postgresql://localhost:5432/wiki"
        schema: "wiki_{vault_name}"
    fts: "auto"                                 # auto = pick FTS5 (sqlite) or tsvector (postgres)
    vector:
      enabled: false                            # opt-in; нужен для semantic RAG
      dim: 384
      model_hint: "all-MiniLM-L6-v2"            # informational; embedding генерится отдельно
      backend: "auto"                           # sqlite-vec | pgvector
    rebuild:
      mode: "delta"                             # delta (mtime-based) | full
      schedule: "daily"                         # daily | manual | on-ingest

  # ===== NEW: Sources (pluggable adapters) =====
  sources:
    transcript:
      enabled: true
      raw_dir: "{project}/_raw/"
      output: "{project}/Summaries/"
    email:
      enabled: false                            # default off — opt-in
      backend: "gmail-mcp"
      sync_interval_hours: 6
      filter: "(is:unread OR is:important) after:N_days_ago"
      output: "{project}/Sources/email/"
      state_file: "{project}/Sources/email/.state.json"
    telegram:
      enabled: false
      backend: "gramjs"                         # NOT MCP — see §15.quater
      session_dir: "~/.local/share/wiki-telegram/"
      output_per_person: "{project}/Sources/telegram/"
    web:
      enabled: true
      mcp_chain: ["exa", "perplexity", "parallel-search", "firecrawl"]
      output: "{project}/Sources/web/"
    manual:
      enabled: true
      output: "{project}/Sources/manual/"

  # ===== NEW: Automations =====
  automations:
    daily_reindex: true                         # cron at 04:00
    daily_brief: true                           # cron at 08:00, generates {today}-brief.md
    weekly_lint: true                           # cron Sunday 02:00
    on_ingest_lint: false                       # heavy, opt-in

  # ===== NEW: MCP credentials/strategy =====
  mcp:
    keys_env: "~/.config/wiki-mcp/keys.env"     # location of MCP keys env file
    fallback_chains:
      web_research: ["exa", "perplexity", "parallel-search", "firecrawl"]
      web_fetch: ["exa", "firecrawl", "playwright"]

  # ===== Existing v1 blocks =====
  index_render:                                  # настройки рендера index.md
    group_by: "category"
    show_fields: [title, date, summary, tags]
    one_line_summary_max: 120

  log:
    timestamp_format: "%Y-%m-%d %H:%M"
    rotation: "monthly"                          # NEW: monthly | yearly | none
    event_types: [ingest, query, lint, manual, research, verify, brief]

  concepts:
    auto_extract: false                          # default off (lean mode)
    aliases_scope: "vault"
    aliases_strategy: "frontmatter"
    auto_link_in_summaries: false
    cross_project_concepts: "promote-to-vault"
    external_model: "unified"
    external_allowlist: []

  lint:
    orphan_links: true
    missing_backlinks: true
    stale_claims_months: 18
    required_frontmatter: [type, title, date, tags, project]
    forbidden_tags_outside_taxonomy: true

  taxonomy:
    inherit: "global"
    extra_tags: []
    allow_project_full_override: true

  research:
    web_backend: "auto"                          # auto = use mcp.fallback_chains.web_research
    max_sources_per_run: 10
    private_concepts: []
    private_tags: [confidential]

  query:
    default_scope: "project"
    file_back_threshold: "manual"
    citation_style: "obsidian"
    rag:
      retrieve_k: 20                             # FTS5 top-K
      rerank_k: 5                                # vector rerank top-K (if enabled)

  verify:
    enabled: false                                # NEW: default off (was on)
    critics: [structural]                         # default — only structural; opt-in полный 4-critic
    fail_on: "high"                              # high | medium | none

  human_edit:
    auto_block_marker: "AUTO-MAINTAINED"
    frozen_frontmatter_field: "frozen"
    conflict_policy: "human-wins"                 # NEW: explicit (was hand-waved in v1)
```

### 8.2 Per-project override `.wiki.yaml`

Минимальный остаётся как в v1:

```yaml
# ~/Obsidian/MyVault/03-Projects/Generation-Demand/.wiki.yaml
project:
  name: "Generation-Demand"
  description: "Курс по генерации спроса"
  language: ru
  taxonomy:
    extra_tags: [demand-generation, b2b-sales, abm]
```

Расширенный — для проекта, который активирует email/telegram source-адаптеры:

```yaml
project:
  name: "Client-Acme"
  description: "Active deal — daily email/telegram pull"
  sources:
    email:
      enabled: true
      filter: "from:acme.com OR to:acme.com"
      sync_interval_hours: 1                     # для активной сделки чаще
    telegram:
      enabled: true
      filter_users: ["@acme_pm", "@acme_cto"]
  concepts:
    auto_extract: true                            # этот проект графит
  automations:
    on_ingest_lint: true
```

### 8.3 Резолюция конфига при запуске

Не изменилась с v1 §8.3:

```python
def load_config(cwd: Path) -> WikiConfig:
    vault_root = find_vault_root(cwd)
    root_cfg   = parse_yaml_block(vault_root / "CLAUDE.md")["wiki"]
    project    = find_project_root(cwd, vault_root)
    if project:
        proj_cfg = yaml.safe_load((project / ".wiki.yaml").read_text())
        return deep_merge(root_cfg, proj_cfg)
    return root_cfg
```

`deep_merge` — рекурсивный merge с concat-дедупликацией списков.

### 8.4 PARA-маппинг (без изменений vs v1)

См. v1 §8.7. Layout `03-Projects/<project>/...` сохраняется. Дополнительно: в `00-Vault-Index/` появляется `00-Vault-Brief/` для cross-project briefs.

### 8.5 JSON Schema (`wiki-config.schema.yaml`)

Обязательный артефакт. Покрывает оба слоя:
- `WikiRootConfig` — для блока `wiki:` в root `CLAUDE.md` (расширенный с `index`, `sources`, `automations`, `mcp`).
- `WikiProjectOverride` — для `.wiki.yaml`.

Каждый скилл валидирует загруженный конфиг до запуска; невалидный → fail-fast.

## 9. Skill: `wiki-init`

**Назначение**: инициализация vault'а под LLM Wiki v2 + SQLite-индекс.

**Input**: `--root <path>` (default = CWD), `--language ru|en`, `--layout per-project|flat`, `--icloud-warning yes|no`.

**Output**:

```
<vault_root>/                       # markdown layer (in iCloud OK)
├── CLAUDE.md                       # root schema, см. §8.1
├── 00-Vault-Index/
│   ├── index.md                    # auto-generated, read-only
│   ├── log.md                      # log/2026-04.md если monthly rotation
│   ├── taxonomy.md
│   └── 00-Vault-Concepts/          # для cross-project concepts
├── 03-Projects/
│   ├── .gitkeep
├── _raw/
│   └── README.md                   # «класть сюда исходники, never edit»
└── Sources/                        # NEW: для email/telegram/web результатов
    ├── email/
    ├── telegram/
    ├── web/
    └── manual/

# SQLite layer (NOT in iCloud, separate path)
~/Library/Application Support/wiki-index/<vault_hash>.db    # macOS
```

**Алгоритм** (~150 строк python):

1. Detect iCloud-vault: путь содержит `Mobile Documents/iCloud~`?
2. Compute `vault_hash = sha256(abs_vault_root)[:12]`.
3. Determine SQLite path:
   - macOS: `~/Library/Application Support/wiki-index/{vault_hash}.db`
   - Linux: `~/.local/share/wiki-index/{vault_hash}.db`
4. Mkdir DB parent, init SQLite from [SCHEMA-DRAFT.sql](./SCHEMA-DRAFT.sql).
5. Set pragmas: `journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON`.
6. Insert seed `batch_runs` row.
7. Mkdir vault-internal dirs.
8. **Interactive prompts** (если не `--non-interactive`):
   - Layout: `per-project | flat`? (default: `per-project` если есть `03-Projects/`-подобная структура, иначе `flat`).
   - Concept-extraction auto-mode: «Включить auto-concept-extraction для этого vault'а?» (Default: `n`. Pro: Karpathy-канон полный с графом. Con: жжёт токены, плодит файлы. Реко: оставить off — есть `wiki-search` (§12.bis) для 80% задач, и `/wiki-extract-concept "X"` для on-demand).
   - Daily automation: «Установить cron для daily reindex и daily brief?» (Default: `n`).
   - Per-source: «Какие источники включить?» (multi-select: transcript / email / telegram / web / manual; default: `transcript, manual`).
9. Write `CLAUDE.md` template (§8.1) с заполненным `vault_hash`, language, layout, ответами из prompts'ов.
10. Write `taxonomy.md` (copy global + placeholder `extra_tags:`).
11. Write `index.md`, `log.md` со скелетами.
12. (Если daily automation enabled) Создать launchd / cron entry. Логирование в `~/.local/state/wiki-cron/<vault_hash>.log`.
13. Print banner: SQLite location, vault location, next-steps suggestion (`wiki-search`, `ingest-source`, `wiki-brief`).

**Idempotency**: file существует → не перезаписывать, warn. `--force` — overwrite.

**Self-check**: SQLite опrашивается `SELECT * FROM batch_runs LIMIT 1`. Все `wiki.paths` существуют. iCloud detection работает.

## 10. Skill: `wiki-index-upsert` (replaces v1 `wiki-update-index`)

**Назначение**: записать/обновить запись о странице в SQLite. **Файл `index.md` больше НЕ touched** — это projection (см. §10.bis).

**Input**:
- `--page <path>` — путь к summary/concept/query/brief/research-странице.
- `--config <path>` (опц.).

**Алгоритм** (~120 строк python через `IndexRepository`):

1. Resolve config + open repo (`make_repo(config)`).
2. Read frontmatter + body excerpt + file mtime + sha256.
3. Build `Page` row: slug, project, type, title, tldr, date, last_modified, file_hash, frontmatter_json, body_excerpt.
4. `repo.upsert_page(...)` — single SQL transaction. FTS5-trigger автоматически обновит `pages_fts`.
5. Parse [[wiki-links]] из body, build `page_entity_refs` rows. `repo.upsert_refs(page, [...])`.
6. Return JSON: `{action: "added"|"updated", slug, refs_added, refs_removed}`.

**Idempotency**: `INSERT ... ON CONFLICT(slug, project) DO UPDATE`. SQLite WAL гарантирует консистентность.

**Race-safety**: `BEGIN IMMEDIATE` на всю операцию. Если пользователь делает batch — последовательное применение в одном connection'е. Никаких потерянных записей (см. §3.9 v1).

**Edge cases**:
- Frontmatter сломан → `--json-errors` envelope с кодом `INVALID_FRONTMATTER`.
- Page удалён с диска → `repo.delete_page(slug, project)` + cascade delete refs. Это побочный эффект `wiki-reindex --delta`, не отдельной команды.

**Self-check**: после upsert — `repo.get_page(slug, project)` возвращает свежий row.

## 10.bis Skill: `wiki-index-render`

**Назначение**: сгенерировать `index.md` (и опц. shards `00-Index/by-{category}.md`) из SQLite. Файл — **read-only projection**.

**Input**: `--scope vault|project`, `--out <path>` (default из config).

**Алгоритм** (~80 строк python):

1. Open repo.
2. Query: `SELECT slug, project, type, title, tldr, date, json_extract(frontmatter_json, '$.tags') AS tags FROM pages ORDER BY date DESC`.
3. Group by `wiki.index_render.group_by` (category из tags / date / type / project).
4. Render markdown:

```markdown
---
type: wiki-index
last_updated: 2026-04-28 14:32
total_pages: 142
auto_generated: true
DO_NOT_EDIT_THIS_FILE: "Изменения здесь будут перезаписаны. Источник истины — SQLite. Edit markdown summaries, then run wiki-index-render."
---

# Wiki Index

<!-- AUTO-GENERATED — do not edit. Run `wiki-index-render` to refresh. -->

## Summaries

### Management & Leadership

- [[Summaries/2026-04-27-savochka-rukovoditel/body|Руководитель 2026]] — Антон Савочка о трёх кризисах и сложном мышлении [2026-04-27] `#lesson` `#strategy`
- ...

## Concepts

- [[Concepts/shadow-ai]] — теневое использование ИИ (3 mentions across 3 projects)
- ...
```

5. Atomic write через `tempfile + os.replace`.
6. (Опц.) Shard: если pages > 200 — генерируется `00-Index/by-category/{cat}.md` + `index.md` становится router'ом.

**Когда вызывать**: после `wiki-index-upsert` (опц. в `ingest-source` step), на cron daily, по запросу `/wiki-index-render`.

**Idempotency**: один и тот же state БД → один и тот же файл (deterministic).

## 11. Skill: `wiki-append-log`

**Назначение**: chronological append-only журнал событий wiki, **с ротацией**.

**Input**:
- `--event ingest|query|lint|manual|research|verify|brief`,
- `--entity <slug>`,
- `--note <text>` (опц.).

**Алгоритм** (~50 строк):

1. Read `wiki.log.rotation` config. If `monthly` — target file = `00-Vault-Index/log/{YYYY-MM}.md`.
2. Mkdir target dir if needed.
3. Append:
   ```markdown
   ## [2026-04-28 14:32] ingest | savochka-rukovoditel-2026
   Source: `_raw/transcripts/day1-01.txt` → [[Summaries/2026-04-27-savochka-rukovoditel/body]]. Concepts: 17. Index updated.
   ```
4. Update `00-Vault-Index/log/index.md` — router-table месяцев:
   ```markdown
   - [[2026-04|April 2026]] — 142 events
   - [[2026-03|March 2026]] — 87 events
   ```
5. Atomic append (`O_APPEND` + `fcntl.flock` если SQLite-mutex недоступен).

**Дополнительно**: одновременно записывается row в `batch_runs` или `interactions` (в зависимости от event-type) — для query'ов через SQL.

**Edge cases**:
- Concurrent writers — `flock` или single-writer SQLite-mutex.
- iCloud detect — если log в iCloud, log-файлу нужен no-lock-fallback (просто atomic append без flock; лог не критичен по race).

**Self-check**: последняя строка после записи парсится regex'ом.

## 12. Skill: `wiki-extract-concepts` — opt-in, с entity-resolver

**Важно**: по default'у этот скилл НЕ запускается на ingest. См. §26 решение #6 (lean mode).

**Когда активируется**:
1. **On-demand singleton**: `/wiki-extract-concept "Shadow AI"` — один концепт за раз.
2. **On-demand batch**: `wiki-extract-concepts --batch <glob>`.
3. **Per-project auto**: `<project>/.wiki.yaml::project.concepts.auto_extract: true`.

### Phase A — Скрипт (детерминистический)

1. Парсить frontmatter страницы → `concepts: [...]`.
2. Для каждого концепта:
   a. Slugify канонически (см. §22 — fixed function).
   b. Через `repo.resolve_entity(name=concept_name, type_hint='concept', fuzzy_threshold=0.85)`:
      - **Stage 0**: User identity (если name в `wiki.user.aliases`) → return user-entity (для concept-режима не применимо, но контракт repo единый).
      - **Stage 1**: Blocked names («Speaker», «Unknown», «Lecturer» из blacklist) → skip.
      - **Stage 2**: Email exact / handle exact (для concepts не релевантно).
      - **Stage 3**: Slug exact match → existing entity.
      - **Stage 4**: Alias exact match → existing entity (через `entity_aliases`).
      - **Stage 5**: Fuzzy name match (Levenshtein > 0.85) → existing с предложением add alias.
      - **Stage 6**: No match → create candidate (`is_candidate = true`).
   c. Достать definition из summary-страницы — regex по секции `### 1. Ключевые концепции и определения`.

### Phase B — LLM (с decision log)

LLM получает (`temperature=0`):
- Draft data из Phase A.
- Existing `Concepts/{slug}.md` if any.
- Aliases из `wiki-config.yaml`.
- **Previous merge decisions** из `Concepts/.merges.jsonl` (для определённости при повторных прогонах).

LLM решает:
- Канонизировать ли имя.
- Слить ли с existing.
- Обновить определение (предпочесть более раннюю/ясную).
- Какие related concepts добавить.

Если decision равен предыдущему — instant return. Если новый — append в `.merges.jsonl`:

```jsonl
{"date": "2026-04-28T14:32:00Z", "concept_name": "Workслоп", "decision": "merge_into:workslop", "reason": "alias of existing", "model": "claude-opus-4-7"}
```

### Phase C — Скрипт (запись)

Записать/обновить `Concepts/{slug}.md` по шаблону:

```markdown
---
type: concept
slug: shadow-ai
name: "Shadow AI"
aliases: [теневой ИИ, Shadow IT-аналог]
is_candidate: false
first_seen: 2026-04-27
last_updated: 2026-04-28
canonicalized_by: "llm:claude-opus-4-7@2026-04-28"
mentions_count: 3
related: ["[[Concepts/workslop]]", "[[Concepts/krizis-otvetstvennosti]]"]
tags: [concept, management, ai]
---

# Shadow AI

> Теневое использование ИИ внутри команд: внешне процесс выполняется как раньше, но фактически работу делает агент, а человек — лишь оператор.

## Канонический контекст

По наблюдению Антона Савочки, это «очень большое изменение последних 3 лет».

## Появления

<!-- AUTO-MAINTAINED:start id=appears-in -->
- [[Summaries/2026-04-27-savochka-rukovoditel/body]] — кейс Василисы и Ивана; вводится сам термин.
  > Source: «Василиса делает презентации через AI, не показывает Ивану…» (L412-L420, trust=high)
- [[Summaries/2026-04-28-prakht-silnyi/body]] — упоминается в контексте кризиса ответственности.
  > Source: «Shadow AI — это новая теневая IT…» (L88-L95, trust=medium)
<!-- AUTO-MAINTAINED:end id=appears-in -->

## Related

- [[Concepts/workslop]] — продукт Shadow AI.
- [[Concepts/krizis-otvetstvennosti]] — следствие.
```

Ключевое отличие от v1: **`appears_in` блок включает `source_quote` и `source_span`** (provenance v1.1).

### Phase D (опц.) — auto-link в summaries

Идентичен v1 §12 Phase D. Замены только в секциях `### 1. Ключевые концепции...` или `Agent Metadata`, не во всём теле.

**Edge cases**:
- LLM предлагает merge `shadow-ai` ↔ `shadow-it` → выйти с `EXIT_NEEDS_CONFIRM`.
- Concept с aliases в разных языках → primary slug + multi-language aliases.
- Cross-project promotion: если ≥2 проекта упомянули концепт, переместить из `<project>/Concepts/<slug>.md` в `00-Vault-Index/00-Vault-Concepts/<slug>.md`. Скрипт делает это автоматически при `cross_project_concepts: promote-to-vault` (default).

**Self-check**:
- Каждый concept из frontmatter имеет либо `Concepts/<slug>.md`, либо записан как candidate в SQLite.
- `appears_in` валиден: каждая ссылка → существует, source_quote находится в указанных line numbers исходной страницы.

## 12.bis Skill: `wiki-search` — FTS5-backed

**Назначение**: главный поисковый интерфейс. Заменяет concept-страницу как «место навигации» для 80% сценариев.

**Input**:
- `<query>` свободным текстом.
- (опц.) `--type summary|concept|query|brief|research`
- (опц.) `--project <name>`
- (опц.) `--vector` — добавить vector-rerank (если включено).
- (опц.) `--limit N` (default 20).

**Алгоритм** (~60 строк python):

1. Resolve config + open `IndexRepository`.
2. `repo.search_pages(query, project=..., types=..., limit=20)` — FTS5 BM25 ranking.
3. Если `--vector` и `wiki.index.vector.enabled` — `repo.search_pages_vector(emb, k=5)` для rerank top-K через cosine; merge results.
4. Для каждой топовой страницы — собрать co-occurrence из `v_concept_cooccurrence` (только для query типа concept).
5. Output:

```markdown
## "Shadow AI" — 3 mentions

- [[Summaries/2026-04-27-savochka-rukovoditel/body]] — Антон Савочка о трёх кризисах. (BM25=4.21)
  > "...теневое использование ИИ внутри команд..."
- [[Summaries/2026-04-28-prakht-silnyi/body]] — кризис ответственности. (BM25=3.87)
- [[Summaries/2026-05-15-orlov-buduschee/body]] — последствия для PM. (BM25=2.95)

Co-occurring concepts (≥ 2 mentions): Workслоп (3), Кризис доверия (2), Менеджер-проводник (2)

[Reranked by cosine similarity — vector layer enabled]
```

**Performance**: < 50ms на 100K документов (см. §28).

**Tier 1 script-first.** LLM не вовлечён, кроме генерации embedding'а query'я (если `--vector`).

## 13. Skill: `wiki-lint` — SQL-based health-check

**Назначение**: corpus health-check. **Lean-режим по умолчанию** (как в v1, но реализованный через SQL).

**Input**: `--root <path>`, `--fix`, `--report <path>`, `--strict`.

**Алгоритм** (~250 строк python, **все чеки через SQL**):

```python
def lint(repo: IndexRepository, strict: bool = False) -> LintReport:
    findings = []
    findings += check_orphan_links(repo)            # SQL: LEFT JOIN page_entity_refs ↔ entities
    findings += check_missing_backlinks(repo)
    findings += check_stale_claims(repo)            # SQL: WHERE date < now - 18 months
    findings += check_required_frontmatter(repo)
    findings += check_tag_taxonomy(repo)
    findings += check_index_drift(repo)             # SQL: pages WHERE NOT EXISTS (SELECT FROM pages_fts)
    findings += check_log_gaps(repo)
    if strict:
        findings += check_duplicate_concepts(repo)  # SQL: pg_trgm or Levenshtein post-query
    return LintReport(findings)
```

**Сравнение с v1 файл-walking**: O(N²) → O(N) с индексом. На 1000 pages: было 5–10s, стало < 1s.

### Чек-лист

| # | Чек | Severity | Запрос |
|---|---|---|---|
| 1 | Orphan links | info / error при --strict | `SELECT page, target FROM page_entity_refs WHERE entity_slug NOT IN (SELECT slug FROM entities) AND entity_slug NOT IN allowlist` |
| 2 | Missing backlinks | error если auto_extract on | Backlinks JOIN с проверкой что в исходной странице есть [[X]] |
| 3 | Stale claims | warning | `pages WHERE date < now() - INTERVAL '18 months' AND tags LIKE '%current%'` |
| 4 | Required frontmatter | error | `pages WHERE json_extract(frontmatter, ...) IS NULL` |
| 5 | Tag taxonomy violations | error | LEFT JOIN tags с taxonomy table |
| 6 | Index drift (file ↔ DB sync) | error | walk filesystem + LEFT JOIN |
| 7 | Log gaps | warning | `interactions LEFT JOIN log_events` |
| 8 | Duplicate concepts | error | `pg_trgm similarity > 0.9 OR Levenshtein < 3` |
| 9 | External-only orphans | info | `entities WHERE is_external = 1` без backlinks |

**Output (markdown report)** — как в v1 §13. Дополнительно — JSON sidecar для machine-consumption.

**Auto-fix `--fix`** — только safe:
- missing backlinks → INSERT в `page_entity_refs`.
- index drift → call `wiki-index-upsert` per orphaned file.
- log gaps → ничего (append-only).

**Self-check**: report-файл валидный markdown; счётчики совпадают.

## 14. Skill: `wiki-query` — RAG over FTS5

**Назначение**: канонический Karpathy Query-loop с filing-back ответов.

**Input**: `<question>`.

**Алгоритм**:

1. **Retrieve.** `repo.search_pages(question, limit=20)` — FTS5 top-20.
2. **Rerank.** Если vector enabled — embed question + `repo.search_pages_vector(...)` top-5; merge.
3. **Read.** Для top-5 загрузить full body (либо chunks по `chunk_boundaries` если token-budget жмёт).
4. **Synthesize.** LLM пишет ответ с цитатами `[[Summaries/X]]` / `[[Concepts/Y]]`.
5. **File-back** (опц.). Если `query.file_back_threshold: always` или user-confirm → создать `Queries/{date}-{slug}.md` со standard frontmatter + body.
6. После file-back → вызвать `wiki-index-upsert` + `wiki-append-log event=query`.

**Tier 2 prompt-first**, LLM в центре, FTS5 — retrieval primitive.

## 15. Meta-workflow: `ingest-source` (multi-source dispatcher)

**Назначение**: единый entry-point для всех источников. Делегирует к нужному `wiki-source-*` adapter'у.

**Файл**: `workflows/ingest-source.md`. Наследник [`generate-detailed-meeting-summary.md`](https://github.com/MatrixFounder/Universal-skills/blob/main/workflows/generate-detailed-meeting-summary.md), но обобщённый.

**Input**:
- `--kind transcript|email|telegram|web|manual` (default: detect by source path/protocol).
- `--source <ref>` — путь к файлу, gmail messageId, telegram chat-name, URL, etc.
- `--project <name>` (опц., иначе detect по CWD).
- (опц.) `--no-extract`, `--lint`, `--verify`.

**Шаги**:

1. **Resolve config.** Прочитать root + project. Detect `kind` если не указан.
2. **Dispatch** to `wiki-source-{kind}`:
   - `transcript` → `wiki-source-manual` → wraps `summarizing-meetings`.
   - `email` → `wiki-source-email`.
   - `telegram` → `wiki-source-telegram`.
   - `web` → `wiki-source-web`.
   - `manual` → just `wiki-index-upsert` on already-existing markdown.
3. Adapter возвращает: `{file_path, interaction_id, source_metadata}`.
4. **Index upsert**: `wiki-index-upsert --page <file_path>`.
5. **Concept extract** (если `concepts.auto_extract: true`).
6. **Verify multi** (если `verify.enabled: true` — default off).
7. **Log**: `wiki-append-log --event ingest --entity <slug>`.
8. **Lint** quick-pass (опц.) — на новые страницы, error-only severity.
9. **Final report** в stdout.

**Failure handling**:
- Adapter упал → ошибка в stdout, log запись `event=ingest, status=failed, kind=<kind>, source=<ref>`.
- Verify FAIL → файл в `_drafts/`, log `status=draft`.
- Index upsert упал → markdown остался, БД может быть несогласован → `wiki-lint` catch.

**Self-check**: source файл существует, БД row есть, log запись добавлена.

## 15.bis NEW: Source Adapters — общий контракт

Все pluggable extractors имеют единый interface. Списан с cybos `scripts/db/extractors/` pattern.

```python
# scripts/wiki_source/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Iterator

@dataclass
class SourceItem:
    """Один атомарный input — один email, один telegram message, один URL fetch."""
    source_kind: str
    source_id: str            # gmail messageId, tg msg_id, sha256(URL+date) for web
    timestamp: str            # ISO-8601
    sender: Optional[dict]    # {name, email, telegram_handle} — for entity resolution
    recipients: list[dict]
    subject: Optional[str]
    body: str
    metadata: dict

@dataclass
class SourceOutput:
    """Что adapter возвращает после обработки SourceItem."""
    file_path: str            # relative to vault — куда положили markdown
    interaction_id: str       # для SQLite взаимодействия
    summary_excerpt: str

class SourceAdapter(ABC):
    """Каждый источник имплементирует этот interface."""

    @property
    @abstractmethod
    def kind(self) -> str: ...    # 'email', 'telegram', etc.

    @abstractmethod
    def authenticate(self, config: dict) -> None: ...
    """First-run OAuth / login. Stateful — хранит token в config-paths."""

    @abstractmethod
    def fetch(self, since: Optional[str] = None) -> Iterator[SourceItem]:
        """Pull новых items с момента since. Использует state file для dedup."""

    @abstractmethod
    def normalize_to_md(self, item: SourceItem, vault_paths: dict) -> SourceOutput:
        """Сгенерировать markdown с frontmatter. Resolve entities через repo."""

    @abstractmethod
    def dedup_state_file(self, config: dict) -> str:
        """Путь к .state.json для этого adapter'а."""
```

**Регистрация** через config: `wiki.sources.<kind>` блок.

**Список реализуемых adapters в фазе 1-3 v2**:
- `manual` — простейший, оборачивает уже-существующий markdown в SQLite-индекс.
- `transcript` (`wiki-source-manual` для transcripts) — wraps `summarizing-meetings`.

**Фаза 4-6**:
- `email` (§15.ter)
- `telegram` (§15.quater)
- `web` (§15.quin)

**Дополнительно** (фаза 7+):
- `granola` (если пользователь использует Granola для звонков, как в cybos)
- `notion` (если пользователь хочет ingest из Notion-страниц)
- `obsidian-daily` (auto-pull из daily notes)

## 15.ter NEW: `wiki-source-email`

**Назначение**: pull emails через gmail-MCP, сохранить markdown + индекс в SQLite.

**Input**:
- `--sync` — pull последние N дней (default 3).
- `--days N` — переопределить.
- `--filter <gmail-query>` — переопределить config filter.
- `--account <email>` — для multi-account.

**Backend**: gmail-MCP (https://github.com/jeremyjordan/gmail-mcp или любой совместимый).

**Алгоритм** (~250 строк):

1. Load config + open repo.
2. Load `.state.json`: `{processed_message_ids: [...], last_sync: timestamp}`.
3. Через MCP query: `(is:unread OR is:important) after:N_days_ago` (config `wiki.sources.email.filter`).
4. Filter results — drop already-processed `messageId`s.
5. Для каждого нового email'а:
   a. Fetch full body через MCP.
   b. Resolve sender: `repo.resolve_entity(email=from_addr, name=from_name, type_hint='person')` → может вернуть existing person, либо создать candidate.
   c. Resolve recipients similarly.
   d. Generate slug: `{date}_{from-slug}_{subject-slug}` (truncated to 80 chars).
   e. Write `Sources/email/{slug}/body.md`:

```markdown
---
type: email
slug: 2026-04-28_john-smith_series-a-update
date: 2026-04-28T14:32:00Z
from: "[[Persons/john-smith]]"
to: ["[[Persons/me]]"]
subject: "Series A Update"
labels: [important]
gmail_message_id: 18a3b...
tags: [email, deal-acme]
project: client-acme
trust_level: high
---

# Series A Update

> From: John Smith (john@acme.com) — 2026-04-28 14:32 UTC

[email body как markdown]

## Auto-extracted

<!-- AUTO-MAINTAINED:start id=summary -->
**TL;DR:** Q4 metrics exceeded targets. Asks for next-step meeting.
<!-- AUTO-MAINTAINED:end id=summary -->

<!-- AUTO-MAINTAINED:start id=action-items -->
- [ ] Schedule call this week (owner: me, source: L42-L45, trust: high)
- [ ] Forward to investment committee (owner: me, source: L60, trust: medium)
<!-- AUTO-MAINTAINED:end id=action-items -->
```

   f. Сохранить metadata.json sibling-файл (gmail labels, headers).
   g. Insert `interactions` row в SQLite.
   h. (Опц.) LLM extraction (Claude Haiku) → `extracted_items` rows. См. §27 для типов.
   i. Append `processed_message_ids` в `.state.json`.
6. Atomic save `.state.json`.
7. Print summary: `N emails synced, K extracted items`.

**Performance**: 100 emails ≈ 30-60s (network-bound). Background-mode supported.

**Edge cases**:
- Re-sync того же интервала — все messageIds уже в state, no-op.
- Email от entity, которой нет в DB → создать `is_candidate=true` person. Пользователь может потом merge через `wiki-entity-confirm`.
- HTML email с inline images — text-extract; images → `Sources/email/{slug}/attachments/`.
- Quoted previous emails (`>`) — keep как есть, не разбирать рекурсивно.

**Self-check**: `.state.json` валиден; все processed messageIds существуют в SQLite `interactions`.

## 15.quater NEW: `wiki-source-telegram`

**Назначение**: pull Telegram messages, per-person aggregation.

**Backend**: **GramJS direct** (MTProto), **не MCP**. Обоснование:
- Telegram MTProto — stateful (session keys, encryption), плохо ложится на stateless MCP-обёртку.
- Cybos pattern (см. `scripts/telegram-gramjs.ts` 45 KB) — proven approach.
- TS+Node лучше всего поддерживается GramJS-библиотекой.

**Input**:
- `--count N` — process N unread dialogs (default 1).
- `--user @name|"Display Name"` — specific person.
- `--requests` — message requests folder.
- `--dry-run` — read only, don't save drafts back.
- `--no-mark-unread` — preserve unread state.

**Алгоритм** (~400 строк TypeScript, plus python wrapper для skill-glue):

1. Load config + auth: first-run OAuth (phone + code), session in `~/.local/share/wiki-telegram/`.
2. Connect via GramJS, list unread dialogs / requested user.
3. For each dialog:
   a. Resolve entity: `repo.resolve_entity(telegram_handle='@username', name=display_name, type_hint='person')` → existing entity или create candidate.
   b. Get-or-create per-person file: `Sources/telegram/<slug>.md` (per-person aggregation).
   c. Append messages to that file:

```markdown
---
type: telegram-thread
person_slug: anton-lobintsev
telegram_handle: "@anton_lob"
entity: "[[Persons/anton-lobintsev]]"
last_message: 2026-04-28T16:45:00Z
total_messages: 47
---

# Anton Lobintsev

## 2026-04-28

**16:45** [Anton]: Привет! Можешь глянуть Q1 деку?
**17:02** [Me]: Сейчас открою.
**17:15** [Anton]: Жду feedback.

## 2026-01-06

[earlier conversation...]
```

   d. (Опц.) Generate AI draft reply → `content/work/{date}-telegram-<slug>.md`.
   e. (Если не `--dry-run`) Save draft to Telegram via GramJS draft API.
   f. Insert `interactions` rows for each new message into SQLite.
4. Print summary.

**Performance**: dialogs read instantaneously; LLM-draft per dialog adds 5-15s.

**Edge cases**:
- New person without entity → create candidate, prompt user later via `wiki-entity-confirm`.
- Group chats — per-group file, not per-person.
- FloodWait from Telegram — exponential backoff.
- Voice messages → transcript via Whisper-MCP (опц.).

**Self-check**: per-person file валиден markdown, новые сообщения в SQLite.

## 15.quin NEW: `wiki-source-web`

**Назначение**: web research / fetch с MCP fallback chain.

**Input**:
- `--query <text>` — search query.
- `--url <url>` — fetch direct URL.
- `--depth quick|standard|deep` — intensity.
- `--save-as research|note|fact` — типу выходной страницы.

**Backend**: MCP fallback chain (config `wiki.mcp.fallback_chains.web_research`):
1. **exa** — primary. Best for company/topic search.
2. **perplexity** — fast search + deep research mode.
3. **parallel-search** / **parallel-task** — for deep autonomous research.
4. **firecrawl** — fallback scraper (last resort).

**Алгоритм**:

1. Load config + open repo.
2. Frame query: LLM генерирует 3-5 search queries (на языке + английский).
3. Execute через первый available MCP в chain. На failure (rate limit / API error) → next.
4. Top-N results filter (drop low-quality, prefer primary sources).
5. Deep-fetch top-3-5 (full text via WebFetch / MCP).
6. Synthesize: LLM пишет research-note (см. v1 §24.1 шаблон).
7. Output `Research/{date}-{slug}/report.md` + sibling `raw/` directory с raw fetched pages.
8. Insert `interactions` row(s) для каждого fetched URL.
9. Index upsert + log.

**Output structure (subfolder pattern, как в cybos):**

```
Research/
├── 2026-04-28-shadow-ai-current/
│   ├── report.md           # synthesized
│   ├── raw/
│   │   ├── hbr-article.md
│   │   ├── gartner-report.md
│   │   └── _fetch-log.json
│   └── metadata.json
```

**Edge cases**:
- All MCPs fail → fail-fast, suggest manual fetch.
- Private concept (`wiki.research.private_concepts` или `tags: [confidential]`) → fail-fast.
- API rate-limit → exponential backoff в chain.

## 15.sex NEW: `wiki-brief` — cross-source daily digest

**Назначение**: daily/weekly digest из всех источников.

**Триггер**: cron daily at 08:00 (config `automations.daily_brief`), или `/wiki-brief` on-demand.

**Алгоритм** (~150 строк python):

1. Load config + open repo.
2. SQL query — все interactions с date ≥ today (или yesterday для morning brief):

```sql
SELECT i.id, i.source_kind, i.subject, i.body, i.date,
       e.name AS sender_name, e.slug AS sender_slug
FROM interactions i
LEFT JOIN entities e ON e.slug = i.sender_entity
WHERE date >= ?
ORDER BY date DESC;

-- Plus open extracted_items
SELECT * FROM v_pending_items WHERE owner_entity = 'me' ORDER BY interaction_date DESC;
```

3. Group by source_kind. LLM synthesize (per group: top-N + summary).
4. Write `Briefs/{date}-brief.md`:

```markdown
---
type: brief
date: 2026-04-28
sources_summary: {emails: 12, telegram: 8, web: 3}
pending_items: 7
---

# Morning Brief — 2026-04-28

## TL;DR

3 deals progressing (Acme, Beta, Charlie). 7 open action items. 1 stale (Acme awaiting Q4 metrics, asked 2026-04-12).

## 📧 Emails (12 unread / important)

### High priority
- **John Smith — Series A Update** (Acme): «Q4 metrics exceeded targets» → schedule call.
  → [[Sources/email/2026-04-28_john-smith_series-a-update/body]]
- ...

## 💬 Telegram (8 conversations)

- **Anton Lobintsev**: Asks for Q1 deck feedback. Last my reply: yesterday.
  → [[Sources/telegram/anton-lobintsev]]
- ...

## 🌐 Web research

- Shadow AI: HBR article on enterprise prevalence. (research yesterday)
  → [[Research/2026-04-27-shadow-ai-current/report]]

## ✅ Pending action items (7)

- [ ] Forward Acme Q4 deck to investment committee (from email yesterday, **trust=high**)
- [ ] Schedule call with John Smith (from email today, trust=high)
- [ ] Reply to Anton (from telegram, trust=medium)
- ...

## 🗓 Calendar

(if calendar MCP enabled)

## 📎 Followups suggested by AI

- Anton mentioned «timing for Q1» but no commitment yet — clarify.
```

5. Index upsert (`type=brief`).
6. Log `event=brief`.

**Tier 1 script-first** для собирания SQL queries; LLM только для synthesis в каждой секции.

**Performance**: < 2s SQL, 10-30s LLM synthesis.

## 16. Форматы файлов (canonical, v2)

### 16.1 `index.md` — **READ-ONLY projection**

```markdown
---
type: wiki-index
last_updated: 2026-04-28 14:32
total_pages: 142
auto_generated: true
---

# Wiki Index

<!-- AUTO-GENERATED — do not edit. Source: SQLite. Run `wiki-index-render` to refresh. -->

## Summaries (90)

### Management & Leadership

- [[Summaries/2026-04-27-savochka-rukovoditel/body|Руководитель 2026]] — Антон Савочка о трёх кризисах [2026-04-27] `#lesson` `#strategy`
- ...

## Concepts (47)

- [[Concepts/shadow-ai]] — теневое использование ИИ (3 mentions)
- ...

## Briefs (5)

- [[Briefs/2026-04-28-brief]] — 12 emails, 8 telegram, 7 pending
- ...
```

Если pages > 200 — index.md автоматически становится router'ом, реальный контент в shards `00-Index/by-{category}.md`.

### 16.2 `log.md` (`log/{YYYY-MM}.md` после ротации)

```markdown
---
type: wiki-log
month: 2026-04
events_count: 142
---

# Wiki Log — April 2026

## [2026-04-28 14:32] ingest | savochka-rukovoditel-2026
Source: `_raw/transcripts/day1-01.txt` → [[Summaries/2026-04-27-savochka-rukovoditel/body]]. Concepts: 17 (3 new, 14 updated). Index updated.

## [2026-04-28 16:00] brief | morning-2026-04-28
12 emails, 8 telegram, 3 web. 7 pending items. → [[Briefs/2026-04-28-brief]].

## [2026-04-28 16:30] query | shadow-ai-i-menedzment
Question: "Что такое Shadow AI и почему это важно для менеджера?". Answer filed → [[Queries/2026-04-28-shadow-ai-i-menedzment]].
```

`log/index.md` — router-table месяцев.

### 16.3 `Concepts/<slug>.md`

См. §12 Phase C — обязательные `source_quote` + `source_span` + `trust_level` в `appears_in`.

### 16.4 NEW: `Sources/email/<slug>/body.md`

См. §15.ter.

### 16.5 NEW: `Sources/telegram/<person-slug>.md`

См. §15.quater. Один файл на person, append-only.

### 16.6 NEW: `Research/<date>-<slug>/report.md`

См. §15.quin.

### 16.7 NEW: `Briefs/<date>-brief.md`

См. §15.sex.

### 16.8 `Summaries/<date>-<slug>/` — SUBFOLDER

```
Summaries/2026-04-27-savochka-rukovoditel/
├── body.md                # main content
├── verify.json            # if verify-multi enabled, ensemble report
├── raw/                   # if multi-LLM, individual outputs
│   └── _agent-*.md
└── metadata.json          # source ref, ingest timestamp
```

Это изменение из v1 (flat `Summaries/{date}-{slug}.md`). Migration: см. [MIGRATION-v1-to-v2.md](./MIGRATION-v1-to-v2.md) §2.

## 17. Migration

См. отдельный файл [MIGRATION-v1-to-v2.md](./MIGRATION-v1-to-v2.md).

## 18. Порядок реализации (lean-приоритет, переупорядоченный)

| Фаза | Что | Зачем именно сейчас |
|---|---|---|
| 1 | `wiki-config.schema.yaml` + [SCHEMA-DRAFT.sql](./SCHEMA-DRAFT.sql) + шаблоны | Контракт |
| 2 | `IndexRepository` interface + SQLite implementation | Фундамент скорости |
| 3 | `wiki-init` (с SQLite-init и iCloud detect) | Возможность тестировать |
| 4 | `wiki-source-manual` (wraps `summarizing-meetings`) | Первый рабочий путь, оборачивает существующий |
| 5 | `wiki-index-upsert` + `wiki-index-render` | DB-driven projection |
| 6 | `wiki-search` (FTS5) | UX-критичный feedback loop |
| 7 | `wiki-append-log` (с ротацией) | Простейший, отлаживает atomic write |
| 8 | `wiki-lint` (lean-mode, SQL-based) | Health-check |
| 9 | `ingest-source` workflow (только manual + transcript) | **MVP wiki** |
| 10 | (опц.) `wiki-source-email` | Multi-source begins |
| 11 | (опц.) `wiki-source-telegram` | |
| 12 | (опц.) `wiki-source-web` + MCP chain | |
| 13 | (опц.) `wiki-brief` | Cross-source value |
| 14 | (опц.) `wiki-extract-concepts` (entity-resolver) | Граф концептов, если нужен |
| 15 | (опц.) `wiki-query` (RAG over FTS5) | Если корпус большой |
| 16 | (опц.) `wiki-research` | Web enrichment |
| 17 | (опц.) `wiki-verify-multi` | Quality assurance |
| 18 | (опц.) Vector layer (sqlite-vec) | Semantic search |
| 19 | (опц.) Postgres backend | Если SQLite упрётся |

**Точка остановки MVP**: после фазы 9 — single-source LLM Wiki по Karpathy с SQLite-индексом. Дальше — по необходимости.

**Multi-source точка**: фазы 10-13 = email + telegram + web + brief.

Каждая фаза заканчивается end-to-end проверкой на реальном vault'е (`tmp2/` для фазы 1-9).

## 19. Тестирование

На каждый скилл — unit-тесты + integration-тест на minimal vault.

### 19.1 Минимальный test vault

`tests/fixtures/minimal-vault/`:
- 2 summary-страницы (3 концепта + 2 концепта, один пересекается).
- 1 фейк email (offline mock).
- 1 фейк telegram thread.
- `wiki-config.yaml` с минимальной конфигурацией.

### 19.2 Integration test scenarios

1. `wiki-init` → SQLite создан, директории есть, FTS5 OK.
2. `ingest-source --kind transcript` → 1 row в pages, 17 concepts (если auto_extract on), 1 row в log.
3. Re-ingest same → idempotent, no duplicates.
4. `wiki-search "term"` < 50ms.
5. Удалить файл → `wiki-lint` ловит drift.
6. `wiki-source-email --sync` (mocked) → emails в SQLite, files на диске.
7. `wiki-brief` → markdown файл валиден, содержит все источники дня.

### 19.3 Performance benchmarks (NEW)

`scripts/wiki_index/benchmark.py`:
- Generate synthetic vault: 100 / 1000 / 10000 markdown files.
- Run each operation, measure latency.
- Compare against §28 SLOs.
- Fail CI если > target.

### 19.4 End-to-end на `tmp2/`

- Bulk-migration 16 → SQLite.
- `wiki-search` queries.
- `wiki-extract-concepts --batch` → concept-страницы.
- `wiki-lint` → orphans на `[[Школа менеджмента Стратоплан]]` и т. п.
- Решить: создать `Concepts/stratoplan.md` со `is_external: true` или mark в `external_allowlist`.

## 20. Доставка / packaging

**Вариант A. Отдельный репо `obsidian-llm-wiki/`**:

```
obsidian-llm-wiki/
├── skills/
│   ├── wiki-init/
│   ├── wiki-index-upsert/
│   ├── wiki-index-render/
│   ├── wiki-append-log/
│   ├── wiki-search/
│   ├── wiki-lint/
│   ├── wiki-extract-concepts/
│   ├── wiki-query/
│   ├── wiki-source-manual/
│   ├── wiki-source-email/
│   ├── wiki-source-telegram/
│   ├── wiki-source-web/
│   ├── wiki-brief/
│   ├── wiki-research/
│   └── wiki-verify-multi/
├── workflows/
│   └── ingest-source.md
├── schemas/
│   └── wiki-config.schema.yaml
├── sql/
│   └── wiki-index.sql                # = SCHEMA-DRAFT.sql
├── scripts/
│   ├── wiki_index/                    # Python DAL
│   │   ├── repository.py
│   │   ├── sqlite_repo.py
│   │   ├── postgres_repo.py
│   │   └── factory.py
│   ├── wiki_source/                   # adapters
│   │   ├── base.py
│   │   ├── email.py
│   │   ├── web.py
│   │   └── manual.py
│   └── wiki_telegram/                 # TypeScript GramJS
│       ├── client.ts
│       └── normalize.ts
├── tests/
│   └── fixtures/minimal-vault/
└── install.sh                         # симлинкует skills/* в ~/.claude/skills/
```

**Вариант B. Claude Code plugin** — то же + `.claude-plugin/plugin.json`.

Рекомендую **A на старте**, B при необходимости.

## 21. Зависимости

**Python 3.11+:**
- `sqlite3` (stdlib)
- `python-frontmatter`
- `python-slugify` (pinned: `>=8.0,<9.0`)
- `pyyaml`
- `jsonschema`
- (опц.) `sqlite-vec` extension (`.dylib` или `.so`)
- (опц.) `psycopg[binary]` для Postgres backend
- (опц.) `httpx` для MCP-вызовов

**Node.js 20+ / Bun:**
- `gramjs` для telegram
- `bun:sqlite` (если Bun-runtime)

**System:**
- `ripgrep` (для wiki-lint quick path)
- (опц.) Postgres 15+ с extensions: `pgvector`, `pg_trgm`

**MCP servers (для adapters):**
- gmail-MCP (zero-config OAuth, как в cybos)
- exa, perplexity, firecrawl (опц.)

## 22. Что важно НЕ забыть при имплементации

- **iCloud detect в `wiki-init` обязателен** + warning + DB вне vault'а. См. §6.4.
- Каждый скрипт принимает `--json-errors` и эмитит uniform error envelope.
- Atomic writes везде, где обновляется существующий файл (`tempfile + os.replace`).
- **Не редактировать** файлы под `wiki.paths.raw_sources` — immutable layer.
- **Slug-генерация** — единая функция в `scripts/wiki_index/slug.py`, golden-tests на 50+ кириллица/латиница пар, версия `python-slugify` pinned.
- **Все state-mutation скиллы** — single SQL transaction (BEGIN IMMEDIATE) для race-safety.
- **Per-source `.state.json`** — atomic replace через tempfile, dedup по messageId / msg_id.
- **MCP credentials**: location в `wiki.mcp.keys_env`, default `~/.config/wiki-mcp/keys.env`. Никогда не commit'ить.
- **MCP fallback chain**: первый доступный wins; failures логируются.
- **`wiki-extract-concepts`**: temperature=0 + decision log `Concepts/.merges.jsonl` для определённости.
- **`canonicalized_by:` frontmatter** — обязательно для LLM-сгенерированных concept-страниц.
- **Provenance**: `source_quote / source_span / trust_level` обязательны в `extracted_items` и `appears_in`-блоках.
- **`.gitignore`** в vault: `00-Vault-Index/.cache/`, `Concepts/.merges.jsonl`, `_drafts/`, lint-reports.
- **Никаких бэкапов и шифрования в скиллах** — vault уже под git/iCloud, скиллы не лезут.
- **Postgres opt-in**: schema generic-SQL, per-backend extensions в SQLITE-VS-POSTGRES.md §3.

## 23. Human-editable layer

Без существенных изменений по сравнению с v1 §23. Дополнения:

### 23.1 NEW для v2: `index.md` теперь read-only

`index.md` — auto-generated projection. Любая ручная правка перезапишется при `wiki-index-render`. Это явное архитектурное решение (см. §10.bis):

- Pro: SQLite — single source of truth для индексов, нет drift.
- Con: пользователь не может вписать «свой comment» в index.md.
- Workaround: пользователь может писать заметки в `00-Vault-Index/notes.md` (manual file, не auto-touched).

`index.md` начинается с явного header'а:

```markdown
<!-- AUTO-GENERATED — do not edit. Source: SQLite. Run `wiki-index-render` to refresh. -->
```

### 23.2 AUTO/MANUAL разметка (без изменений)

Идентично v1 §23.1 — `<!-- AUTO-MAINTAINED:start id=... -->` маркеры в Concept pages, Source-pages.

### 23.3 Frozen pages

В frontmatter `frozen: true` → скиллы не перегенерируют тело. v2 расширяет: `frozen` блокирует и concept-страницы, и source-pages, и briefs.

### 23.4 Conflict resolution

Default `conflict_policy: human-wins` (явно прописано в §8.1, было hand-waved в v1 §23.5).

### 23.5 Что не автоматизируется

`02-Home/`, `04-Areas/`, `06-Archive/` — out-of-scope. `excluded_paths` в config.

## 24. Research / enrichment

### 24.1 `wiki-research` — research-агент по концепту/вопросу

Идентичен v1 §24.1, с расширением:
- **MCP fallback chain**: использует `wiki.mcp.fallback_chains.web_research`.
- **Apply mode** учитывает provenance: каждое `Suggested update` хранит `source_quote / source_span / trust_level`.

### 24.2 `wiki-discover` — поиск тем для ingest

Идентичен v1 §24.2.

### 24.3 `wiki-enrich` — массовое обогащение

Идентичен v1 §24.3.

### 24.4 MCP architecture (расширено в v2)

**Конфиг credentials**:

```bash
# ~/.config/wiki-mcp/keys.env
EXA_API_KEY=...
PERPLEXITY_API_KEY=...
FIRECRAWL_API_KEY=...
PARALLEL_API_KEY=...
GMAIL_CLIENT_ID=...
GMAIL_CLIENT_SECRET=...
TELEGRAM_API_ID=...
TELEGRAM_API_HASH=...
```

**Fallback chains** (config `wiki.mcp.fallback_chains`):
- `web_research`: `[exa, perplexity, parallel-search, firecrawl]` — try in order, пропустить при rate-limit/down.
- `web_fetch`: `[exa, firecrawl, playwright]` — для single URL deep-fetch.

**Per-skill mapping**:
- `wiki-research` → `web_research` chain.
- `wiki-source-web` → `web_research` chain.
- `wiki-source-email` → gmail-MCP (нет chain — только один source).
- `wiki-source-telegram` → GramJS direct (НЕ MCP — обоснование §15.quater).

## 25. Verifier ensemble — `wiki-verify-multi` (default OFF)

**КЛЮЧЕВОЕ ИЗМЕНЕНИЕ от v1**: default `verify.enabled: false`. Включается явно `--verify` или `wiki.verify.enabled: true`.

**Обоснование**: 4 critic × full-page context на каждый ingest = ~50K input tokens × $cost-per-token. На 200 документов — $60-120. Большинство ingest'ов не требуют ensemble. Default off.

**Когда включать**:
- Деликатные документы (legal, financial).
- Active deals (per-project flag).
- При migration массовой → один прогон ensemble на корпус, потом disable.

**Critics** (без изменений vs v1 §25):
- `critic-factual`
- `critic-structural` — *самый детерминистический; рекомендуется как always-on default* в v2.
- `critic-taxonomy`
- `critic-narrative`

**Default config**:

```yaml
verify:
  enabled: false
  critics: [structural]                 # only structural always-on
  fail_on: high
```

Чтобы включить полный ensemble — `critics: [factual, structural, taxonomy, narrative]`.

**Orchestration / Output / Anti-patterns** — без изменений vs v1 §25.

## 26. Принятые архитектурные решения

| # | Тема | Решение |
|---|---|---|
| 1 | `raw_sources` scope | Project имеет приоритет; fallback на vault `01-Inbox/`. |
| 2 | External references | Unified data model `type: concept` + `external: true`; default `auto_extract: false`; lint orphan'ы как info. |
| 3 | Concept aliases scope | Vault-wide always. |
| 4 | Project taxonomy override | Полный override разрешён. |
| 5 | Privacy на `wiki-research` | Гибрид: frontmatter `private: true` + tag-list `[confidential]` + vault-wide allowlist. |
| 6 | Concept-page extraction | On-demand + per-project YAML override. Default `auto_extract: false`. |
| **7 (NEW)** | **Index backend** | **SQLite default + Postgres opt-in через DAL.** См. [SQLITE-VS-POSTGRES.md](./SQLITE-VS-POSTGRES.md). |
| **8 (NEW)** | **DB location** | **Вне vault'а, обязательно.** macOS `~/Library/Application Support/wiki-index/`, Linux `~/.local/share/wiki-index/`, Windows `%LOCALAPPDATA%\wiki-index\`. |
| **9 (NEW)** | **Source adapters** | **Pluggable.** Контракт §15.bis. На старте: manual + transcript. Фаза 2: email + telegram + web. |
| **10 (NEW)** | **MCP strategy** | **Fallback chains в config.** `web_research: [exa, perplexity, parallel-search, firecrawl]`. Credentials в `~/.config/wiki-mcp/keys.env`. |
| **11 (NEW)** | **Vector search** | **Opt-in.** Default off. Включается `wiki.index.vector.enabled: true`. SQLite → sqlite-vec; Postgres → pgvector+HNSW. |
| **12 (NEW)** | **Daily automation** | **On by default**, но cron-job создаётся `wiki-init` **только с явного user confirm**. `automations.daily_reindex / daily_brief / weekly_lint`. |
| **13 (NEW)** | **`index.md` mutability** | **Read-only projection.** Manual edits перезаписываются. Comments → `00-Vault-Index/notes.md`. |
| **14 (NEW)** | **Verify ensemble** | **Default off.** Только `critic-structural` always-on если verify enabled. Полный 4-critic — explicit opt-in. |
| **15 (NEW)** | **Provenance** | **Required.** `source_quote / source_span / trust_level` в `extracted_items` и `appears_in` блоках concept-pages. |
| **16 (NEW)** | **Layout default для `wiki-init`** | **per-project.** На vault root → fallback `flat`. `wiki-init` interactive prompt при ambiguity. |

Все решения встроены в JSON Schema (`wiki-config.schema.yaml`).

## 27. Index Layer — детальная спецификация

### 27.1 Schema

См. [SCHEMA-DRAFT.sql](./SCHEMA-DRAFT.sql) — полное DDL.

**Core tables (8 + 3 FTS virtual + 3 views)**:
- `entities` — concepts, persons, companies, products
- `entity_aliases` — name variations
- `pages` — markdown-страницы (summary/concept/query/brief/research)
- `page_entity_refs` — М:М связь page ↔ entity, с provenance
- `interactions` — raw sources (email/telegram/call/transcript/web/manual)
- `extracted_items` — LLM-extracted facts (promise/action_item/decision/question/metric/claim/definition/entity_context)
- `batch_runs` — reindex log
- `source_state` — per-source dedup state (messageIds, last_pull, etc.)
- `pages_fts`, `interactions_fts`, `entities_fts` — FTS5 virtual tables
- `v_entity_backlinks`, `v_concept_cooccurrence`, `v_pending_items` — views

### 27.2 IndexRepository interface

См. [SQLITE-VS-POSTGRES.md §4.1](./SQLITE-VS-POSTGRES.md#41-python-рекомендуется-для-wiki--скиллов).

Методы:
- Pages: `upsert_page`, `get_page`, `search_pages`, `search_pages_vector`, `delete_page`.
- Entities: `resolve_entity` (multi-stage), `upsert_entity`, `find_duplicates`, `merge_entities`.
- Refs: `upsert_refs`, `find_orphan_links`, `get_backlinks`.
- Lint: `find_pages_missing_in_index`, `check_drift`.
- Reindex: `begin_batch_run`, `finish_batch_run`, `last_batch_run`.
- Sources: `get_source_state`, `set_source_state`, `upsert_interaction`, `upsert_extracted_items`.

### 27.3 Reindex strategy

Три режима:

1. **Full**: walk vault filesystem, for each `.md` file → upsert page + refs. Drop pages where file no longer exists. Time: ~5s на 1000 docs.
2. **Delta** (default): compare `pages.last_modified` ↔ filesystem mtime. Only re-process changed. Time: ~500ms на 1000 docs (mostly no-op).
3. **Extract-only**: skip filesystem walk, only run LLM extraction on `interactions` where `extracted_at IS NULL`.

**Triggered by**:
- `wiki-reindex` CLI.
- Cron daily (config `automations.daily_reindex`).
- `ingest-source` workflow при наличии новых файлов в `_raw/` (опц.).

### 27.4 Entity resolution algorithm

См. [SQLITE-VS-POSTGRES.md §4.2-4.3](./SQLITE-VS-POSTGRES.md#42-sqlite-реализация-default).

Multi-stage matching (cybos-портированный):
- Stage 0: User identity (`wiki.user.aliases`)
- Stage 1: Blocked names (`Speaker`, `Unknown`, etc.)
- Stage 2: Email exact
- Stage 3: Telegram handle exact
- Stage 4: Slug exact
- Stage 5: Alias exact
- Stage 6: Fuzzy name (Levenshtein > 0.85 для SQLite, `pg_trgm % > 0.7` для Postgres)
- Stage 7: No match → create candidate

**Two-tier system**:
- `is_candidate=false` — confirmed (manually approved или high-confidence через email/handle).
- `is_candidate=true` — extracted from sources without exact match.
- `wiki-entity-confirm` (отдельный скилл, фаза 14+) для review/merge candidates.

### 27.5 Provenance v1.1 (required)

Каждая запись в `extracted_items` и `page_entity_refs` имеет:
- `source_quote` — verbatim 10-50 слов.
- `source_span` — line numbers (`L120-L138`) или timestamp (`mm:ss-mm:ss`) для timeline.
- `trust_level` — `high` / `medium` / `low`.

Это позволяет:
1. Audit: «откуда LLM взял это утверждение?».
2. Filtering: lint может игнорировать `low-trust` claims.
3. UI: при отображении concept-страницы — quote.

## 28. Performance budget & SLOs

См. [SQLITE-VS-POSTGRES.md §6](./SQLITE-VS-POSTGRES.md#6-performance-budget) для подробных таргетов SQLite vs Postgres.

**Сводная таблица для verification**:

| Операция | 100 docs | 1000 docs | 10000 docs | Метод verification |
|---|---|---|---|---|
| `wiki-search "term"` | < 30ms | < 50ms | < 100ms | benchmark.py |
| `wiki-search --vector` | < 100ms | < 150ms | < 300ms | (если enabled) |
| `wiki-index-upsert` | < 50ms | < 100ms | < 100ms | benchmark.py |
| `wiki-index-render` | < 200ms | < 1s | < 5s | (with sharding) |
| `wiki-lint` full | < 500ms | < 2s | < 30s | benchmark.py |
| `wiki-brief` | < 1s | < 2s | < 5s | (LLM-bound) |
| `wiki-reindex --full` | < 2s | < 20s | < 3min | benchmark.py |
| `wiki-reindex --delta` (no changes) | < 100ms | < 500ms | < 2s | benchmark.py |
| `ingest-source --kind transcript` | varies (LLM-bound) | varies | varies | manual measurement |

**SLO violations** → CI fails → дизайн пересматривается. Это страховка от drift'а в сторону медленных решений.

**Synthetic vault generator** (`scripts/wiki_index/benchmark.py`):
- Параметр `--n N` — генерирует N markdown файлов с реалистичной структурой (frontmatter, body, [[wiki-links]]).
- Прогоняет каждую операцию.
- Печатает таблицу: `op_name, n, p50, p95, p99, status (PASS/FAIL)`.

## 29. Cybos-приёмы, портированные в этот дизайн

Прозрачное cross-reference: что и почему взято из [Gerstep/cybos](https://github.com/Gerstep/cybos).

| Cybos-паттерн | Где портирован в v2 | Почему взято |
|---|---|---|
| File-first + SQLite index | §27, [SCHEMA-DRAFT.sql](./SCHEMA-DRAFT.sql) | Доказательно работает на multi-source personal AI; markdown не теряется. |
| FTS5 + WAL mode | §27, SCHEMA §0 + §9 | Sub-1ms latency на 100K rows; embedded — нет server'а. |
| Multi-stage entity resolution | §27.4 | Решает cross-source dedup корректно (email/handle exact > fuzzy). |
| Two-tier entities (confirmed/candidate) | §27.4, §12 | Предотвращает мусор от LLM-extracted entities на каждом ingest. |
| Provenance v1.1 (`source_quote/span/trust_level`) | §16, §27.5 | Audit + filtering + UI quote. Karpathy citations-as-first-class реализован машинно. |
| LLM extraction (Haiku, ~$0.01/interaction) | §15.ter, §15.quater (опц.), §27 | Cheap structured facts от каждого interaction. |
| Per-source `.state.json` для dedup | §15.ter, §15.quater | Re-sync не плодит дубликаты. |
| Per-person aggregation (`{slug}.md`) | §15.quater | Continuous conversation thread с одним человеком. |
| Cross-source brief (`/cyber-brief`) | §15.sex `wiki-brief` | Daily digest всех источников = ключевой UX для multi-source. |
| `MMDD-<slug>-YY/` subfolder | §16.8 (Summaries), §15.quin (Research) | Group related artifacts; легче для file pane Obsidian; git-history per-source. |
| Daily reindex cron | §22, §26 #12 | Не manual reindex на 1000+ файлов. |
| Freshness check на SessionStart | §22 (рекомендация) | UX-приятная нота, если БД устарела. |
| MCP fallback chain | §24.4 | Reliability over single MCP. |
| Telegram via GramJS direct (не MCP) | §15.quater | MTProto session-stateful, MCP плохо подходит. |

**Что НЕ взято**:
- Cybos's flat `~/.cybos/config.json` global config — заменено двухслойной схемой v1 (`CLAUDE.md` + `.wiki.yaml`), мощнее.
- Cybos's deal-context-as-folders (`/deals/<co>/`) — у нас более общий per-project layout.
- `quality-reviewer` agent (deep research only) — заменено более структурированным `verify-multi` (§25), хотя оба opt-in.

---

# Verification (для всего документа)

- Сравнить любую страницу из `tmp2/` против gist'а Karpathy → frontmatter, anchors, [[wiki-links]], Concept Definitions ✅.
- `ls tmp2/ | grep -E '^(index|log|Concepts|Sources|Briefs)$'` → пусто, подтверждает gap-list §4.
- `grep -l 'Shadow AI' tmp2/*.md` → концепт в нескольких лекциях, единой concept-страницы нет (закрывается §12).
- После имплементации: `wiki-search "shadow ai"` < 50ms на 1000 docs (benchmark §28).
- После имплементации: `wiki-source-email --sync` для тестового gmail → emails в `Sources/email/`, rows в `interactions`, `.state.json` записан.
- После имплементации: `wiki-brief` daily → markdown файл с TL;DR + emails + telegram + pending items.

---

# Дальнейшие шаги

1. Имплементация по фазам §18: фаза 1-9 = MVP wiki, фаза 10-13 = multi-source, фаза 14-19 = опц. enrichment.
2. Validation против `tmp2/` после каждой фазы.
3. Performance benchmark после фазы 6 (`wiki-search`) и фазы 8 (`wiki-lint`).
4. Опционально: запуск через `/full-robust` или `/vdd-multi` workflow для validated implementation.

**Этот документ — спецификация, а не реализация.** Скиллы реализуются в отдельных PR'ах по фазам.
