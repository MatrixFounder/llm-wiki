# Анализ: `summarizing-meetings` + `generate-detailed-meeting-summary` vs. Karpathy "LLM Wiki"

## Context

Пользователь задаёт исследовательский вопрос (не задачу на код): совместим ли результат работы skill [summarizing-meetings](https://github.com/MatrixFounder/Universal-skills/blob/main/skills/summarizing-meetings/SKILL.md) и workflow [generate-detailed-meeting-summary.md](https://github.com/MatrixFounder/Universal-skills/blob/main/workflows/generate-detailed-meeting-summary.md) с подходом «LLM wiki» Карпатого ([gist 442a6bf5](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)). Образцы выходов — в `tmp2/` (16 markdown-файлов, day1…day4, ~440 строк каждый).

Этот файл — аналитический ответ, не план имплементации. Никаких изменений в скилл ниже не предлагается; если пользователь захочет привести скилл к канону — список «GAP» в §4 готов послужить чек-листом.

---

## 1. Каноном Карпатого считаем (выжимка) из [gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f))

Архитектура из 3 слоёв:

1. **Raw sources** — неизменяемые исходники (статьи, видео, транскрипты).
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

---

## 2. Что фактически делает skill + workflow

На вход — один или несколько транскриптов одного урока. На выход — **один** richly-structured markdown-файл со следующими атрибутами (см. реальный пример `tmp2/day1-01-savochka-rukovoditel-2026.md`):

- YAML frontmatter с `type`, `title`, `tags`, `related: [[wiki-links]]`, плюс educational-расширение: `concepts: [...]`, `prerequisites: [[...]]`, `speaker`, `course`, `module_number`, `lesson_number`.
- **Pyramid Level 1**: `## Резюме верхнего уровня` (TL;DR) + `## Что запомнить` (takeaways).
- **Pyramid Level 2**: 5 фиксированных подсекций — Concepts / Structure / Techniques / Examples / Relationships, каждая с `> **Summary**:` зачином и опциональными Mermaid-диаграммами.
- **Pyramid Level 3 (Agent Metadata)**: `Semantic Index`, `Concept Definitions` (machine-readable таблица «Concept | Definition | Related»), `Chunk Boundaries` с anchor-ссылками + token-estimate, `Content Fingerprint`.
- HTML-якоря `<!-- SECTION:concepts -->` и т. п. — language-agnostic навигация для агентов.
- Tag taxonomy enforcement через [tag_taxonomy.md](https://github.com/MatrixFounder/Universal-skills/blob/main/skills/summarizing-meetings/references/tag_taxonomy.md).
- Self-check + completeness guarantee внутри одной страницы.

---

## 3. Совместимость со страницей-как-такой (canonically: «summary page»)

**Очень высокая.** На уровне *одной страницы* выход даже более дисциплинирован, чем минимум, который описывает Карпатый:

| Канон Карпатого | Skill/workflow |
|---|---|
| Markdown-файл, Obsidian-friendly | ✅ нативно |
| YAML-метаданные | ✅ полный фронтматтер |
| Cross-references как ценность | ✅ `related: [[…]]`, `prerequisites: [[…]]` |
| Concept pages (атомарные понятия) | ⚠️ концепты *перечислены* в `concepts:` и определены в machine-readable таблице, но не вынесены в **отдельные** страницы |
| Schema disciplines the LLM | ✅ SKILL.md + workflow + generation_prompt.md + tag_taxonomy.md играют роль schema/CLAUDE.md |
| Сitations / quotes | ✅ `## Ключевые цитаты спикера` |
| Chunk boundaries для RAG | ✅ явно прописаны |
| Tone, granularity, structure | ✅ pyramid + anchors + Mermaid |

**Вердикт по самим summary**: каноничному «LLM wiki» они подходят как готовая «summary layer». Любую из 16 страниц `tmp2/` можно положить в Karpathy-style wiki как `wiki/lessons/<slug>.md` без переработки — фронтматтер, якоря, [[wiki-links]] и Concept Definitions table уже соответствуют тому, что просит канон от страницы.

---

## 3.bis Что такое **concept page** (entity page) в каноне Karpathy

В выводе скилла есть фронтматтер `concepts: [Shadow AI, Workслоп, ...]` и таблица «Concept | Definition | Related». Это **перечень концептов внутри одной summary-страницы** — концепты живут *внутри* лекции, к которой они относятся.

Karpathy же говорит про **отдельные файлы-носители концепта** — `wiki/concepts/shadow-ai.md`, по одному файлу на каждый канонический термин/сущность. Этот файл:

- содержит **одну каноническую формулировку** (1–3 предложения), общую для всего vault'а;
- хранит список `appears_in: [[lesson1]], [[lesson2]], …` — обратные ссылки на все источники, где концепт упоминается;
- линкует **related concepts** — соседние понятия в графе;
- **накапливает** упоминания: каждый новый ingest добавляет туда строку, не перезаписывая старое.

Зачем это нужно:

- **Один клик — одна страница.** В Obsidian/Karpathy-wiki клик на `[[Shadow AI]]` из любой лекции ведёт в *одно и то же место* с канонической формулировкой и историей всех упоминаний. Сейчас, без concept-страниц, клик на `[[Shadow AI]]` вообще ни к чему не ведёт (orphan).
- **Граф знаний.** `Concepts/` директория — это узлы графа; backlinks — рёбра. Obsidian Graph View показывает осмысленную карту. Без отдельных файлов — нет узлов, нет графа.
- **Накопление контекста.** Если 5 лекций упоминают «Shadow AI», concept-страница агрегирует все 5 углов зрения. Читая её — получаешь синтез по всему корпусу. Без неё — приходится открывать 5 лекций и сшивать вручную.
- **Дедупликация.** «Workслоп» и «AI слоп» — это один концепт под двумя именами. Concept-страница хранит `aliases: [AI слоп]` → wiki не плодит дубликаты.

Пример минимальной concept-страницы — в §16.3 (полный шаблон) и §12 (как генерируется).

В этом плане: скилл `wiki-extract-concepts` (§12) выносит концепты из summary-страниц в `Concepts/<slug>.md` и поддерживает их актуальными между ingests. Это и есть тот недостающий «concept page»-слой канона, про который в §4 идёт речь.

---

## 4. Что в каноне покрывает skill+workflow, а что — нет

**Скилл по дизайну делает summary-page, и делает её отлично.** Остальные операции LLM-wiki (index, log, concept pages, lint, query) в его scope не входили — это сознательное решение, а не дефект. Раздел ниже — про то, как summary-page стыкуется с *остальными* частями канона, которые добираются отдельными артефактами (см. Часть II).

| Часть канона | В scope скилла? | Где добирается |
|---|---|---|
| Обновление `index.md` после каждого ingest | вне scope | новый скилл `wiki-update-index` (§10) |
| Append в `log.md` (`## [2026-04-27] ingest \| <title>`) | вне scope | новый скилл `wiki-append-log` (§11) |
| Извлечение **концептных страниц** ("Shadow AI" и т. п.) как отдельных файлов | вне scope | новый скилл `wiki-extract-concepts` (§12) |
| Cross-page **Lint**: orphan pages, contradictions, stale claims | вне scope (внутри-страничный self-check у скилла есть) | новый скилл `wiki-lint` (§13) |
| **Query** операция | вне scope | новый скилл `wiki-query` (§14) |
| «kept current, not re-derived» (wiki как compounding artifact) | частично — skill пишет одну страницу; reconciliation с прежним состоянием отсутствует | оркестратор `ingest-source` (§15) делает chained update вместо re-derive |
| Dangling links вроде `[[Школа менеджмента Стратоплан]]` | детектируются, но не чинятся | `wiki-lint` ловит, человек или `wiki-research` (§24) разрешает |

---

## 5. Итоговый ответ на вопрос пользователя

1. **«Сами summary будут ли корректно следовать канону?»** — Да. На уровне отдельной страницы выход skill+workflow совместим с подходом Karpathy и даже превосходит его минимальные требования (HTML-якоря для агентов, machine-readable Concept Definitions, Chunk Boundaries — это бонус сверх канона). Любую из страниц `tmp2/` можно использовать как summary-page в LLM-wiki без переработки.

2. **«Совместим ли с подходом и принципами LLM wiki?»** — Да, как **компонент**. Skill закрывает один кирпич канона — генерацию summary-page — и делает это с запасом. Остальные кирпичи (index, log, concept pages, lint, query) — отдельные артефакты, которые ставятся **поверх** скилла, не вместо него. Скилл не нужно переделывать; он остаётся ingest-stage.

3. **Практическая рекомендация (если хочется собрать всю методологию целиком)** — `summarizing-meetings` остаётся как есть. Поверх него — sibling-скиллы:
   - `wiki-update-index` — после каждого summary append/обновляет `index.md`;
   - `wiki-append-log` — chronological `log.md` с парсимыми префиксами;
   - `wiki-extract-concepts` — выносит концепты из `concepts:` фронтматтера в отдельные `concepts/<slug>.md` страницы и обратно линкует;
   - `wiki-lint` — orphan/contradiction/stale-claim сканер по всему корпусу;
   - (опционально) `wiki-query` — RAG-поиск по `tmp2/` с filing-back ответов.

   Над всем этим — `CLAUDE.md` в корне `tmp2/` в роли schema (как в каноне).

---

## 6. Где физически лежат скиллы и `CLAUDE.md` при множестве Obsidian-папок

Канон Karpathy сам подсказывает разделение: **skills = engine (универсальный код), CLAUDE.md = schema (под конкретный домен/vault)**. То есть скиллы инсталлируются один раз глобально, а `CLAUDE.md` живёт внутри каждой тематической папки Obsidian.

### Раскладка

| Что | Где | Почему |
|---|---|---|
| `wiki-update-index`, `wiki-append-log`, `wiki-extract-concepts`, `wiki-lint`, `wiki-query` (engine) | `~/.claude/skills/<name>/` | один экземпляр, доступен из любой CWD; обновляется в одном месте |
| `summarizing-meetings` + workflow `generate-detailed-meeting-summary.md` | уже там, где сейчас (репо Universal-skills, симлинком/плагином в `~/.claude/skills/`) | engine остаётся engine'ом |
| `CLAUDE.md` (schema) | в **корне каждого vault'а / тематической папки**, например `~/Obsidian/Generation-Demand/CLAUDE.md`, `~/Obsidian/Management-2026/CLAUDE.md` | Claude Code читает `CLAUDE.md` снизу вверх от CWD — запуск `claude` из папки vault'а автоматически подхватит его schema |
| `index.md`, `log.md`, `concepts/`, `summaries/` (state — сама wiki) | внутри vault'а, рядом с `CLAUDE.md` | это часть данных vault'а, не общая |
| Tag taxonomy | базовая в скилле ([tag_taxonomy.md](https://github.com/MatrixFounder/Universal-skills/blob/main/skills/summarizing-meetings/references/tag_taxonomy.md)), per-vault расширение — в `CLAUDE.md` или `wiki-taxonomy.md` рядом с ним | глобальные теги + доменные расширения |

### Что должен содержать per-vault `CLAUDE.md`

Karpathy описывает schema как «documents how the wiki is structured, what the conventions are, and what workflows to follow». Конкретно для vault'а:

```yaml
# Пример: ~/Obsidian/Generation-Demand/CLAUDE.md
wiki:
  index:        "00 - Index/index.md"
  log:          "00 - Index/log.md"
  summaries:    "Summaries/"          # куда складывать ingest-output
  concepts:     "Concepts/"           # куда выносить концепт-страницы
  raw_sources:  "_transcripts/"       # где лежат transcripts (не трогать)
  tag_taxonomy: "00 - Index/tags.md"  # vault-local расширение
naming:
  summary:  "{date}-{slug}.md"
  concept:  "{slug}.md"
language: ru
```

Скиллы из `~/.claude/skills/wiki-*/` читают эту schema → знают, куда писать `index.md`, куда выносить концепты, какой taxonomy следовать в **этом** vault'е.

### Запуск

Пользователь:

```bash
cd ~/Obsidian/Generation-Demand   # ИЛИ ~/Obsidian/Management-2026 — любая папка
claude
> /generate-detailed-meeting-summary on _transcripts/lecture-01.txt
```

Что происходит:

1. Claude CLI стартует, видит `~/Obsidian/Generation-Demand/CLAUDE.md` (schema этого vault'а) + `~/.claude/CLAUDE.md` (глобальные правила, если есть).
2. Workflow `generate-detailed-meeting-summary` создаёт summary page в `Summaries/` *этого* vault'а.
3. Sibling-скиллы (когда будут) читают `wiki:` блок из `CLAUDE.md` и обновляют `index.md`/`log.md`/`concepts/` *этого* vault'а.

Между vault'ами всё изолировано: переключение vault'а = просто `cd` в другую папку. Engine один, состояние своё.

### Альтернатива через плагин (если vault'ов много)

Если их 5+ и хочется атомарной установки:

- Запаковать `wiki-*` скиллы как Claude Code plugin → `.claude-plugin/`.
- Установить плагин одной командой → доступен глобально.
- В каждом vault'е остаётся только `CLAUDE.md`.

Это тот же подход, отличается только механикой доставки engine'а.

### Анти-паттерны

- ❌ Класть `wiki-*` скиллы в `.claude/skills/` **внутри vault'а** — придётся дублировать в каждом vault'е, расходятся версии.
- ❌ Класть `index.md` / `log.md` глобально в `~/.claude/` — это per-vault state, vault'ы перетрут друг друга.
- ❌ Зашивать пути в скиллах (`wiki/concepts/...`) — vault'ы устроены по-разному. Скилл *читает* пути из `CLAUDE.md`, не предполагает.

### Связь с существующим Universal-skills репо

`Universal-skills/` остаётся source-of-truth для engine. Доставка в `~/.claude/skills/`:

- симлинком (`ln -s "$(pwd)/skills/wiki-update-index" ~/.claude/skills/wiki-update-index`),
- или через плагинную упаковку,
- или через `init_skill.py` из [skill-creator](https://github.com/MatrixFounder/Universal-skills/tree/main/skills/skill-creator).

Vault'ы Obsidian к репо `Universal-skills` отношения не имеют — это разные слои (engine vs domain state).

---

## Verification (для §1–§6, аналитики)

- Сравнить любую страницу из `tmp2/` против gist'а Karpathy → проверить, что фронтматтер, anchors, [[wiki-links]] и Concept Definitions table присутствуют (✅ в `tmp2/day1-01-savochka-rukovoditel-2026.md`).
- `ls tmp2/ | grep -E '^(index|log)\.md$|^concepts$'` → пусто, подтверждает §4.
- `grep -l 'Shadow AI' tmp2/*.md` → концепт в нескольких лекциях, единой concept-страницы нет.

---

# ЧАСТЬ II — ДЕТАЛЬНЫЙ ПЛАН РЕАЛИЗАЦИИ

Цель: добрать вторую половину канона Karpathy — превратить набор изолированных summary-страниц в self-maintaining LLM Wiki. Реализуется в отдельном проекте/репо (`obsidian-llm-wiki/` или внутри существующего vault'а как `.claude/skills/`).

## 7. Scope и deliverables

| # | Артефакт | Тип | Тier |
|---|---|---|---|
| 1 | `wiki-init` | skill | 2 |
| 2 | `wiki-update-index` | skill | 1 (script-first) |
| 3 | `wiki-append-log` | skill | 1 (script-first) |
| 4 | `wiki-extract-concepts` | skill | 2 (prompt-first с скриптами) |
| 5 | `wiki-lint` | skill | 1 (script-first) |
| 6 | `wiki-query` | skill | 2 |
| 7 | `ingest-source` | meta-workflow | — |
| 8 | `wiki-config.schema.yaml` | JSON Schema | — |
| 9 | Шаблоны: `index.md`, `log.md`, `concept.md`, `CLAUDE.md` | assets | — |

**Не входит** в этот план: переписывание `summarizing-meetings`. Скилл остаётся как есть, к нему добавляется post-hook вызов `ingest-source` workflow.

---

## 8. Schema — мульти-проектный vault, без копипасты `CLAUDE.md`

**Проблема, которую решаем:** в одном Obsidian-vault'е лежат много тематических папок-проектов (`Generation-Demand/`, `Management-2026/`, `AI-Engineering/`, …). Класть в каждую папку отдельный `CLAUDE.md` с одинаковыми правилами — копипаста, версии разъезжаются.

**Решение — двухслойная конфигурация:**

1. **Vault-root `CLAUDE.md`** — *один* файл в корне vault'а. Описывает общие правила: язык, taxonomy, lint-параметры, naming-схему. Это «defaults» для всех проектов.
2. **Per-project override** — опциональный маленький файл `<project>/.wiki.yaml` (или YAML-блок в первом `## Project config` чанке `<project>/README.md`). Содержит *только то, что отличается* от root: имя проекта, локальные пути, дополнительные теги.

Скиллы при запуске:
- определяют **активный проект** по CWD (поднимаются вверх до ближайшего `.wiki.yaml`),
- читают root `CLAUDE.md` → получают defaults,
- мерджат поверх per-project override → получают финальную конфигурацию,
- если CWD = vault root (нет активного проекта) — работают с vault-wide files.

### 8.1 Root `CLAUDE.md` — общая schema (один на весь vault)

```yaml
# ~/Obsidian/MyVault/CLAUDE.md (YAML-блок внутри markdown)
wiki:
  version: 1
  language: ru                          # ru | en | mixed

  # ===== Соглашения, общие для всего vault'а =====

  layout: "per-project"                 # per-project | flat
  # per-project — каждый проект = подпапка с собственными Summaries/Concepts/...
  # flat — единые Summaries/, Concepts/ в корне vault'а (один проект = весь vault)

  vault_paths:                          # vault-wide артефакты (если layout=per-project)
    global_index: "00-Vault-Index/index.md"   # сводный каталог по всем проектам
    global_log:   "00-Vault-Index/log.md"     # сводный журнал
    taxonomy:     "00-Vault-Index/taxonomy.md"

  project_paths:                        # шаблон путей внутри каждого проекта
    index:        "{project}/index.md"
    log:          "{project}/log.md"
    summaries:    "{project}/Summaries/"
    concepts:     "{project}/Concepts/"
    queries:      "{project}/Queries/"
    raw_sources:  "{project}/_raw/"
    research:     "{project}/Research/"

  naming:
    summary: "{date}-{slug}.md"
    concept: "{slug}.md"
    query:   "{date}-{question-slug}.md"

  index:
    group_by: "category"
    show_fields: [title, date, summary, tags]
    one_line_summary_max: 120

  log:
    timestamp_format: "%Y-%m-%d %H:%M"
    event_types: [ingest, query, lint, manual, research, verify]

  concepts:
    auto_extract: false                 # ВАЖНО: vault-wide default — не плодить concept-страницы автоматически.
                                        # Можно переопределить per-project в .wiki.yaml
    aliases_scope: "vault"              # vault — алиасы глобальны (рекомендация); project — per-project
    aliases_strategy: "frontmatter"
    auto_link_in_summaries: false       # default off (соответствует lean-подходу)
    cross_project_concepts: "promote-to-vault"  # если 2+ проекта упоминают концепт — перенос в vault-wide
    vault_wide_concepts_path: "00-Vault-Concepts/"
    external_model: "unified"           # unified — в Concepts/ с external: true; separate — в Stubs/; allowlist — только список
    external_allowlist: []              # имена/паттерны, которые lint игнорирует как orphan informational

  lint:
    orphan_links: true
    missing_backlinks: true
    stale_claims_months: 18
    required_frontmatter: [type, title, date, tags, project]
    forbidden_tags_outside_taxonomy: true

  taxonomy:
    inherit: "global"                   # extends summarizing-meetings/references/tag_taxonomy.md
    extra_tags: []                      # extra-теги уровня vault'а (если есть)
    allow_project_full_override: true   # проект может полностью заменить vault-wide taxonomy

  research:
    web_backend: "webfetch"             # webfetch | mcp-firecrawl | mcp-puppeteer
    max_sources_per_run: 10
    private_concepts: []                # имена концептов, не отправлять в web
    private_tags: [confidential]        # концепты с этими тегами — не отправлять в web

  query:
    default_scope: "project"            # project | vault — по умолчанию ищем в текущем проекте
    file_back_threshold: "manual"
    citation_style: "obsidian"

  human_edit:                            # см. §23
    auto_block_marker: "AUTO-MAINTAINED"
    frozen_frontmatter_field: "frozen"
```

### 8.2 Per-project override — `<project>/.wiki.yaml`

Минимальный (почти всегда хватает):

```yaml
# ~/Obsidian/MyVault/Generation-Demand/.wiki.yaml
project:
  name: "Generation-Demand"
  description: "Курс по генерации спроса (мастер-данные, ABM, sales playbooks)"
  language: ru                          # override, если отличается от vault'а
  taxonomy:
    extra_tags: [demand-generation, b2b-sales, abm, master-data]
```

Расширенный (если проект кардинально устроен по-другому):

```yaml
project:
  name: "AI-Engineering"
  language: en                          # override: проект на английском
  paths:                                # override: своя layout
    summaries: "lessons/"
    concepts:  "glossary/"
    raw_sources: "transcripts/"
  naming:
    summary: "{module}/{lesson_number}-{slug}.md"
  concepts:
    auto_extract: true                  # включаем автосбор: для этого проекта граф концептов важен
    auto_link_in_summaries: true
  taxonomy:
    full_override: true                 # своя taxonomy, не наследует vault-wide
    tags: [llm, agents, evals, prompting, finetune]
```

### 8.3 Резолюция конфига при запуске

Псевдокод (одинаков во всех wiki-* скиллах):

```python
def load_config(cwd: Path) -> WikiConfig:
    vault_root = find_vault_root(cwd)            # ближайший CLAUDE.md с wiki: блоком
    root_cfg   = parse_yaml_block(vault_root / "CLAUDE.md")["wiki"]
    project    = find_project_root(cwd, vault_root)  # ближайший .wiki.yaml между cwd и vault_root
    if project:
        proj_cfg = yaml.safe_load((project / ".wiki.yaml").read_text())
        return deep_merge(root_cfg, proj_cfg)    # project поверх root
    return root_cfg                              # CWD = vault root, нет project override
```

`deep_merge` — рекурсивное слияние словарей (project значения побеждают), для списков — concat с дедупликацией (например, `taxonomy.extra_tags` объединяются).

### 8.4 Минимальный setup

- 1 файл (`CLAUDE.md` в корне vault'а) — для одного-проектного vault'а с `layout: flat`.
- 1 + N файлов (`CLAUDE.md` + по `.wiki.yaml` в каждом проекте) — для мульти-проектного. `.wiki.yaml` обычно ≤ 5–10 строк.
- **Никакой копипасты:** общие правила живут только в `CLAUDE.md` vault'а; в проекте — только различия.

### 8.5 Вырожденные случаи

- **Один проект на весь vault** → `layout: flat`, `project_paths` игнорируются, используется root напрямую без `.wiki.yaml`.
- **Несколько vault'ов на машине** → у каждого свой `CLAUDE.md`; `~/.claude/CLAUDE.md` (user-level) может задавать совсем глобальные defaults (язык, taxonomy inherit), но это опционально.

### 8.6 JSON Schema (`wiki-config.schema.yaml`)

Обязательный артефакт. Покрывает оба слоя:
- `WikiRootConfig` — для блока `wiki:` в root `CLAUDE.md`,
- `WikiProjectOverride` — для `.wiki.yaml`.
Каждый скилл валидирует загруженный конфиг до запуска; невалидный → fail-fast с понятной ошибкой.

### 8.7 Маппинг на реальный vault пользователя (PARA-подобная нумерованная раскладка)

User's vault: `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/ObsidianNotes/`, корень содержит `01-Inbox/`, `02-Home/`, `03-Projects/`, …

Под этот layout настройка одна и **минимальная** — vault уже разделён по темам, нужно только показать скиллам, какие из этих папок проектные:

```
ObsidianNotes/
├── CLAUDE.md                       # один файл — общая schema на весь vault
├── 01-Inbox/                       # raw_sources по умолчанию (свалка идей, transcripts)
├── 02-Home/                        # личные ноты — vault-wide concepts/queries сюда
├── 03-Projects/
│   ├── Generation-Demand/
│   │   ├── .wiki.yaml              # 5 строк override
│   │   ├── Summaries/
│   │   ├── Concepts/
│   │   ├── _raw/                   # local transcripts (если не общий 01-Inbox)
│   │   └── index.md
│   ├── Management-2026/
│   │   ├── .wiki.yaml
│   │   └── …
│   └── AI-Engineering/
│       ├── .wiki.yaml
│       └── …
├── 04-Areas/
├── 05-Resources/
├── 06-Archive/
└── 00-Vault-Index/                 # auto-maintained: vault-wide index, log, taxonomy
    ├── index.md                    # сводка по всем 03-Projects/* + cross-cutting
    ├── log.md
    ├── taxonomy.md
    └── 00-Vault-Concepts/          # концепты, встречающиеся в 2+ проектах (promote-to-vault)
```

Соответствующий root `CLAUDE.md`:

```yaml
wiki:
  version: 1
  language: ru
  layout: per-project

  # PARA-подобный vault: проекты живут под одним «контейнером»
  project_root: "03-Projects/"        # скиллы автоматически считают подпапки здесь проектами
  # альтернатива: project_globs: ["03-Projects/*", "04-Areas/*"]

  vault_paths:
    global_index: "00-Vault-Index/index.md"
    global_log:   "00-Vault-Index/log.md"
    taxonomy:     "00-Vault-Index/taxonomy.md"

  project_paths:
    index:        "{project}/index.md"
    log:          "{project}/log.md"
    summaries:    "{project}/Summaries/"
    concepts:     "{project}/Concepts/"
    queries:      "{project}/Queries/"
    research:     "{project}/Research/"
    raw_sources:  "{project}/_raw/"     # либо переопределить на vault-wide "01-Inbox/" в .wiki.yaml

  concepts:
    cross_project_concepts: "promote-to-vault"
    vault_wide_concepts_path: "00-Vault-Index/00-Vault-Concepts/"

  # … остальное как в §8.1
```

**Правило resolve проекта** (важно для PARA-layout):

```python
def find_project(cwd, vault_root, cfg):
    project_root = vault_root / cfg["wiki"]["project_root"]   # 03-Projects/
    rel = cwd.relative_to(project_root)
    return project_root / rel.parts[0]   # 03-Projects/<first-segment>
    # → если cwd = 03-Projects/Generation-Demand/Summaries/foo,
    #   то project = 03-Projects/Generation-Demand
```

CWD вне `03-Projects/` (например, в `01-Inbox/` или прямо в корне) → активного проекта нет, используется только vault-wide layer (`00-Vault-Index/`). `wiki-query` по умолчанию ищет по всему корпусу; ingest без `--project` фейлится с подсказкой запустить из папки проекта.

`01-Inbox/` тут естественно играет роль «Drop transcripts here»: можно сделать `wiki-inbox-sweep` в будущем, который смотрит файлы там, спрашивает «в какой проект ингестить» и вызывает `ingest-source --source X --project Y` (опционально, не в первой фазе).

### 8.8 Runtime: что происходит, когда `claude` запущен в корне, а потом `cd` в подпапку

Вопрос важный: **сессия Claude Code загружает `CLAUDE.md` один раз, на старте**. Скиллы — другое: **скрипты читают конфиг с диска при каждом вызове** (stateless re-resolve). Эти два слоя живут параллельно и не мешают друг другу.

#### Слой 1: что Claude Code (агент) знает о vault'е

При запуске `claude` в любой директории vault'а агент собирает контекст по фиксированной иерархии:

1. `~/.claude/CLAUDE.md` — глобальные пользовательские правила (всегда).
2. **Самый верхний** `CLAUDE.md` в дереве от CWD до `~/` — это твой vault-root (`~/ObsidianNotes/CLAUDE.md`).
3. Любые `CLAUDE.md` ниже по дереву от CWD — если запустился глубже.

Этот контекст — **read-only снимок на момент старта**. Он не «следует» за `cd` в течение сессии. Это нормально: vault-root `CLAUDE.md` нужен агенту для общего понимания («это wiki по PARA-схеме, основной язык ru, taxonomy.md там-то»), а не для каждой конкретной операции.

В нашем дизайне (см. §8) **в подпапках проектов нет своего `CLAUDE.md`** — там `.wiki.yaml`. Это сознательное решение: Claude Code не знает про `.wiki.yaml`, не загружает его в контекст и не путается. `.wiki.yaml` — машинная конфигурация для скиллов, не для агента.

#### Слой 2: что делают скилл-скрипты при каждом вызове

Каждый wiki-* скрипт при запуске **заново** проходит резолюцию:

```python
def resolve(cwd: Path) -> WikiConfig:
    vault_root = walk_up_until(cwd, has_file="CLAUDE.md", contains="wiki:")
    project    = walk_up_until(cwd, has_file=".wiki.yaml", stop_at=vault_root)
    return deep_merge(
        load_yaml_block(vault_root / "CLAUDE.md")["wiki"],
        load_yaml(project / ".wiki.yaml") if project else {}
    )
```

Это происходит **на каждый вызов** `wiki-update-index`, `wiki-extract-concepts`, любого другого. Скрипт не помнит прошлый CWD, не кэширует — всегда смотрит актуальный.

#### Конкретный сценарий пользователя

```bash
~ $ cd ~/ObsidianNotes/                                  # vault root
~/ObsidianNotes $ claude
```

Что Claude Code делает:
- Читает `~/ObsidianNotes/CLAUDE.md` (vault-wide schema, taxonomy, общие правила) → в контекст.
- Читает `~/.claude/CLAUDE.md` → в контекст.
- Скиллов в этой сессии **никаких** не запустилось.

```
> cd 03-Projects/Generation-Demand
```

`cd` в Claude Code просто меняет CWD shell-процесса. **Никакой перезагрузки CLAUDE.md не происходит**, и не нужно — контекст уже есть.

```
> /ingest-source --source _raw/lecture-01.txt
```

Workflow вызывает скрипты wiki-* по очереди. **Каждый** скрипт делает свежий resolve:
- CWD = `~/ObsidianNotes/03-Projects/Generation-Demand`.
- Walk-up для `.wiki.yaml` → находит `~/ObsidianNotes/03-Projects/Generation-Demand/.wiki.yaml` (project layer).
- Walk-up для `CLAUDE.md` с `wiki:` блоком → находит `~/ObsidianNotes/CLAUDE.md` (vault layer).
- Project = `Generation-Demand` (per §8.7 правилу `find_project`).
- Merge → финальный config: пути типа `03-Projects/Generation-Demand/Summaries/`, taxonomy = global + project extras.
- Скилл пишет в правильное место **этого** проекта.

```
> cd ../Management-2026
> /ingest-source --source _raw/lecture-05.txt
```

Тот же агент, та же сессия, тот же контекст CLAUDE.md в памяти. Но при следующем вызове `/ingest-source`:
- CWD теперь `~/ObsidianNotes/03-Projects/Management-2026`.
- Скрипты опять resolve'ят с нуля → находят `Management-2026/.wiki.yaml`, мержат с тем же vault-root → пишут в `Management-2026/Summaries/`.

**Никакого рестарта `claude` не нужно.** Сессия одна, vault-context один, проекты переключаются через `cd`.

#### Граничные случаи

| CWD на момент вызова скилла | Поведение |
|---|---|
| Vault root (`~/ObsidianNotes/`) | Активный проект не определён. `wiki-update-index`/`wiki-append-log` работают с vault-wide файлами (`00-Vault-Index/`). `ingest-source` фейлится с подсказкой: «cd into a project folder or pass `--project <name>`». |
| `01-Inbox/` или вне `03-Projects/` | То же: нет активного проекта. Опц. — `--project` argument для override. |
| `03-Projects/Generation-Demand/Summaries/foo` (вглубь проекта) | Project всё равно резолвится в `Generation-Demand` через `find_project` (§8.7) — берётся первый сегмент после `project_root`. |
| Совсем не в vault'е (например, `/tmp`) | Vault root не находится — fail-fast: «not inside a wiki-enabled vault. Run `wiki-init` or cd into one.» |
| `claude` запущен из подпапки проекта сразу (без `cd` через root) | Vault root всё равно находится через walk-up. Контекст `CLAUDE.md` загружается тот же. Проект определён сразу. |

#### Что **не** работает (и почему это ОК)

- **Менять config «на лету».** Если ты редактируешь vault-root `CLAUDE.md` посреди сессии — текущий agent context остаётся со старой версией (Claude Code не перезагружает). Скилл-скрипты увидят новую версию (они читают с диска), но агент — нет, до рестарта `claude`. Это редкий кейс; если возникает — рестарт сессии.
- **Несколько vault'ов в одной сессии.** Если `cd ~/AnotherVault/` мид-сессии, агент всё ещё думает про первый vault (из-за слой-1 кэша). Скилл-скрипты будут работать с новым vault'ом корректно, но guidance в агенте — устаревший. Practice: один `claude` на один vault.

#### Резюме

- **Один `claude` на vault, неважно из какой подпапки запущен.**
- **Один `CLAUDE.md` в корне vault'а** для агента — описывает методологию.
- **N `.wiki.yaml`** в проектах для скиллов — описывают локальные различия.
- **`cd` свободно переключает проекты** в течение сессии. Скилл-скрипты сами поймут, где они.
- Никакого session reload, никакого рестарта, никакой синхронизации руками не требуется.

---

## 9. Skill: `wiki-init`

**Назначение:** инициализация структуры vault'а под LLM Wiki. Запускается ОДИН РАЗ в новом vault'е.

**Input:** `--root <path>` (default = CWD), `--language ru|en` (default из system locale).

**Output:**

```
<root>/
├── CLAUDE.md                # с минимальным wiki: блоком + reference на схему
├── 00-Index/
│   ├── index.md             # пустой каталог с заголовками категорий
│   ├── log.md               # один log-entry: ingest=init
│   └── taxonomy.md          # копия глобальной taxonomy + extra_tags placeholder
├── Summaries/
│   ├── .gitkeep
├── Concepts/
│   └── .gitkeep
├── Queries/
│   └── .gitkeep
└── _raw/
    └── README.md            # «класть сюда исходники, never edit»
```

**Алгоритм:** 5–10 строк python — `os.makedirs` + копирование шаблонов из `assets/`. Никакого LLM.

**Idempotency:** если файл существует → не перезаписывать, warn. `--force` — overwrite.

**Self-check:** все пути из `wiki.paths` существуют после init.

---

## 10. Skill: `wiki-update-index`

**Назначение:** добавить/обновить запись в `index.md` после ingest или ручного создания страницы.

**Input:**
- `--page <path>` — путь к summary/concept/query странице,
- (опц.) `--config <path>` — иначе ищет `CLAUDE.md`/`.claude/wiki-config.yaml` вверх по дереву.

**Алгоритм (script-first, ~80 строк python):**

1. Прочитать YAML frontmatter страницы (использовать `python-frontmatter` или ручной парсер).
2. Извлечь `title`, `date`, `type`, `tags`, первый параграф TL;DR (или `description` из frontmatter) → один-line-summary (truncate до `index.one_line_summary_max`).
3. Определить категорию через `index.group_by`:
   - `category` → из `tags` берётся первый «категориальный» тег (по taxonomy);
   - `date` → `YYYY / YYYY-MM`;
   - `tag` → каждый тег = своя секция (страница появляется N раз);
   - `course` → frontmatter `course`.
4. Открыть `index.md`, найти секцию `## <категория>`. Если нет — создать (под нужное место, alphabet или date-sorted).
5. Сформировать строку:
   ```markdown
   - [[Summaries/2026-04-27-savochka-rukovoditel|Руководитель 2026: что делает менеджера сильным]] — Антон Савочка о трёх кризисах и сложном мышлении [2026-04-27] `#lesson` `#strategy`
   ```
6. **Idempotency:** ищется по slug страницы. Если найдена — replace всю строку (не дублировать). Иначе — insert в правильное место сортировки.
7. Записать `index.md` обратно атомарно (`tempfile` + `os.replace`).
8. Вернуть JSON: `{action: "added"|"updated", category, line_number}`.

**Edge cases:**
- Frontmatter сломан → `--json-errors` envelope с кодом `INVALID_FRONTMATTER`.
- `index.md` отсутствует → создать (с шаблоном из `wiki-init`).
- Несколько категорий (multi-tag with `group_by: tag`) → запись N раз, каждая в своей секции.

**Self-check:** после записи прогнать `markdown-link-check` или regex по новой строке — все ссылки разрешаются.

---

## 11. Skill: `wiki-append-log`

**Назначение:** chronological append-only журнал событий wiki.

**Input:**
- `--event ingest|query|lint|manual`,
- `--entity <slug>` (страница, query, lint-run id),
- `--note <text>` (опц., 1 строка).

**Алгоритм (script-first, ~30 строк):**

1. Прочитать `wiki.paths.log`.
2. Append в конец файла:
   ```markdown
   ## [2026-04-27 14:32] ingest | savochka-rukovoditel-2026
   Source: `_raw/transcripts/day1-01.txt` → [[Summaries/2026-04-27-savochka-rukovoditel]]. Concepts extracted: 17. Index updated.
   ```
3. Никогда не редактировать прошлые записи. Только append.
4. Atomic write через `O_APPEND`.

**Парсимость:** префикс `## [TIMESTAMP] EVENT | ENTITY` фиксированный — `wiki-lint` и `wiki-query` могут грепать его regex'ом.

**Edge cases:**
- `log.md` отсутствует → создать и сразу append (сначала ingest=init).
- Concurrent writes — `fcntl.flock` обернуть.

**Self-check:** последняя строка после записи парсится regex'ом `^## \[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\] (ingest|query|lint|manual) \| .+$`.

---

## 12. Skill: `wiki-extract-concepts` — **opt-in, не по умолчанию**

**Важно:** по умолчанию этот скилл НЕ запускается на ingest. Концепты остаются метками во `frontmatter.concepts:` саммари, никаких отдельных файлов не плодится. Это сделано осознанно: автосоздание concept-страниц для каждого ingest съедает токены и засоряет vault десятками файлов, многие из которых пользователю не нужны.

Скилл активируется в трёх режимах:

1. **On-demand singleton** (рекомендуемый): `/wiki-extract-concept "Shadow AI"` — пользователь явно просит вынести **один** конкретный концепт, скилл пробегает по всем саммари, агрегирует упоминания, создаёт `Concepts/shadow-ai.md`. Один концепт = один LLM-запрос.
2. **On-demand batch:** `wiki-extract-concepts --batch <glob>` — для сценария «я хочу превратить весь корпус в граф концептов», осознанное решение и осознанный token-budget.
3. **Per-project auto** (для папок, где нужен граф): в `<project>/.wiki.yaml` ставится `project.concepts.auto_extract: true` → `ingest-source` для **этого** проекта автоматически прогоняет extract на каждый ingest. Vault-wide default — `false`.

В обычном vault'е с PARA-layout: лекционные курсы, где граф концептов важен (например, методологический курс), включают auto в своём `.wiki.yaml`; conference-summaries и proj-докалы оставляют off.

**Input:**
- `--concept "<name>"` — singleton-режим: один концепт по имени.
- `--page <path>` — все концепты одной страницы (только если включён auto или вызвано осознанно).
- `--batch <glob>` (например, `Summaries/**/*.md`) — пакетный.

**Алгоритм (prompt-first, со скриптовым каркасом):**

### Phase A — Скрипт (детерминистический)

1. Парсить frontmatter страницы → `concepts: [...]` массив.
2. Для каждого концепта:
   a. Slugify канонически: `Shadow AI` → `shadow-ai`. Кириллицу транслитерировать (использовать `python-slugify` с `--allow-unicode` или translit).
   b. Проверить наличие `Concepts/{slug}.md`.
   c. Достать из summary-страницы определение этого концепта — Phase A ищет по regex в секции `### 1. Ключевые концепции и определения` строку, начинающуюся с `**{concept}**` или `**{concept} (...)** —`.
3. Сформировать **draft data** для LLM: `{concept_name, slug, definition_excerpt, source_page, mentioned_in_lessons[]}`.

### Phase B — LLM

LLM получает:
- Draft data из Phase A.
- Существующий `Concepts/{slug}.md`, если есть (full content).
- Aliases от пользователя из `wiki-config.yaml`, если объявлены.

LLM решает:
- Канонизировать ли имя (например, «Workслоп / AI слоп» → каноническое `workslop`, alias `AI слоп`).
- Слить ли с существующим (если есть `Concepts/shadow-it.md`, а пришёл `Shadow AI` — это разные? спросить или отметить).
- Обновить определение (предпочесть более раннюю/ясную формулировку, или объединить нюансы).
- Какие related concepts добавить (по co-occurrence в summary-странице).

### Phase C — Скрипт (запись)

Записать/обновить `Concepts/{slug}.md` по шаблону:

```markdown
---
type: concept
name: "Shadow AI"
slug: shadow-ai
aliases: [теневой ИИ, Shadow IT-аналог]
first_seen: 2026-04-27
last_updated: 2026-04-27
mentions_count: 3
appears_in:
  - "[[Summaries/2026-04-27-savochka-rukovoditel]]"
  - "[[Summaries/2026-04-28-prakht-silnyi-rukovoditel]]"
related:
  - "[[Concepts/workslop]]"
  - "[[Concepts/gibridnye-roli]]"
tags: [concept, management, ai]
---

# Shadow AI

> Теневое использование ИИ внутри команд: внешне процесс выполняется как раньше, но фактически работу делает агент, а человек — лишь оператор.

## Канонический контекст

По наблюдению Антона Савочки, это «очень большое изменение последних 3 лет».

## Появления

- [[Summaries/2026-04-27-savochka-rukovoditel]] — кейс Василисы и Ивана; вводится сам термин.
- [[Summaries/2026-04-28-prakht-silnyi-rukovoditel]] — упоминается в контексте кризиса ответственности.

## Related

- [[Concepts/workslop]] — продукт Shadow AI.
- [[Concepts/krizis-otvetstvennosti]] — следствие.

<!-- agent-metadata -->
- canonical: Shadow AI
- aliases: теневой ИИ, Shadow IT-аналог
- first_seen: 2026-04-27 (savochka-rukovoditel)
```

Идемпотентность критична: повторный прогон `--page X` не должен дублировать `appears_in:` или `Появления:`. Скрипт делает merge по `[[Summaries/...]]`-ссылке.

### Phase D (опц.) — auto-link в summaries

Если `concepts.auto_link_in_summaries: true`:
- Для каждого зарегистрированного концепта найти plain-text вхождения в summary-странице.
- Заменить **только в `### 1. Ключевые концепции и определения`** или в `Agent Metadata` секции — не во всём тексте (чтобы не сломать форматирование).
- Использовать regex с word-boundary, учитывая Cyrillic.

**Edge cases:**
- Concept имя содержит slash `Workслоп / AI слоп` → slug = `workslop`, alias = `AI слоп`.
- Mixed Cyrillic + Latin → транслит для slug, оригинал для name.
- LLM предлагает merge `shadow-ai` ↔ `shadow-it` → требует user confirmation (выйти с `EXIT_NEEDS_CONFIRM`, не перезаписывать).

**Self-check:**
- Каждый концепт из `frontmatter.concepts` исходной страницы → имеет `Concepts/<slug>.md`.
- В каждом `Concepts/<slug>.md` ссылка на исходную страницу есть в `appears_in:`.
- Backlinks в summary-странице (если auto-link) указывают на существующие concept-страницы.

---

## 12.bis Skill: `wiki-search` — поиск без файлов (lean concept-graph)

**Назначение:** заменяет «концепт-страницу как место навигации» на простой поиск. Когда пользователь хочет узнать «где в корпусе упоминается Shadow AI?» — `wiki-search` грепает `frontmatter.concepts:` всех саммари и возвращает список. Никаких файлов не создаёт, никаких токенов не тратит.

**Input:** `<concept-name>` свободным текстом (поиск с алиасами и регистронезависимый).

**Алгоритм (script-first, ~50 строк):**

1. Walk-up до vault root, прочитать config.
2. Глобом по `wiki.project_paths.summaries` (все проекты) собрать список `.md` саммари.
3. Распарсить frontmatter каждой → собрать `concepts: [...]` в индекс `{concept → [pages]}`.
4. Поиск по входному имени: case-insensitive, fuzzy (Levenshtein ≤ 2 для опечаток), плюс алиасы из `wiki-config.yaml` (если объявлены глобально).
5. Output:
   ```markdown
   ## "Shadow AI" — 3 mentions

   - [[Summaries/2026-04-27-savochka-rukovoditel]] — Антон Савочка о трёх кризисах.
   - [[Summaries/2026-04-28-prakht-silnyi]] — кризис ответственности.
   - [[Summaries/2026-05-15-orlov-buduschee]] — последствия для PM.

   Co-occurring concepts (≥ 2 mentions): Workслоп (3), Кризис доверия (2), Менеджер-проводник (2)
   ```

**Где это даёт ценность:**
- Заменяет concept-страницу для 80% задач за 0 токенов и 0 файлов.
- Co-occurrence матрица на лету — побочный продукт того же скана.
- Если результат «стоит файла» — пользователь руками вызывает `/wiki-extract-concept "Shadow AI"` (§12) или вручную делает заметку.

**Tier 1 script-first.** Никакого LLM. Может работать оффлайн.

---

## 13. Skill: `wiki-lint`

**Назначение:** health-check корпуса. **Lean-режим по умолчанию**: проверяет структурную целостность (что обязательно), не пристаёт по поводу orphan'ов из `related:` (это информационно).

**Input:** `--root <path>` (default = CWD), `--fix` (опц., применить безопасные автофиксы), `--report <path>` (куда сохранить отчёт), `--strict` (опц., повышает orphan'ы до errors).

**Алгоритм (script-first, ~250 строк):**

Чек-лист с категориями `error | warning | info` (каждый — отдельная функция):

1. **Orphan links** [info по умолчанию, error при `--strict`]. Грепнуть все `[[X]]` во всех `.md` → проверить что target существует. Игнорировать `wiki.concepts.external_allowlist`. Concept-orphan'ы проверяются только если в каком-то проекте `auto_extract: true`.
2. **Missing backlinks** [error, только если auto_extract включён в проекте]. Для каждого `Concepts/X.md` с `appears_in: [[A]], [[B]]` — проверить что A.md действительно содержит ссылку на X.
3. **Stale claims** [warning]. Страницы старше `lint.stale_claims_months` с тегом `#current`.
4. **Required frontmatter** [error]. Каждая страница имеет все поля из `lint.required_frontmatter`.
5. **Tag taxonomy violations** [error, если `forbidden_tags_outside_taxonomy: true`]. Каждый тег есть в taxonomy (учитывая project full_override).
6. **Index drift** [error]. Каждая `Summaries/*.md` (и `Concepts/`, `Queries/` — если есть) упомянута в `index.md`.
7. **Log gaps** [warning]. Каждый ingest имеет log-запись.
8. **Duplicate concepts** [error, только если auto_extract]. Два concept-файла с пересекающимися `aliases:` или схожими `name:` (Levenshtein < 3).
9. **External-only orphans** [info]. Подсветить ссылки на `external: true` концепты, но не считать их ошибкой.

**Output (markdown report):**

```markdown
# Wiki Lint Report — 2026-04-27 14:55

## Summary
- 16 summaries, 47 concepts, 3 queries.
- ❌ 12 issues found (4 orphan, 5 missing backlinks, 2 stale, 1 duplicate).

## Orphan Links (4)
- `Summaries/day1-01.md` → `[[Школа менеджмента Стратоплан]]` — no such page.
...
```

**Auto-fix (`--fix`)** — только безопасное:
- missing backlinks → добавить в `appears_in:`,
- index drift → `wiki-update-index` для каждой пропущенной страницы,
- log gaps → ничего (append-only журнал нельзя back-fill автоматически).

**Self-check:** report-файл корректный markdown; счётчики в `## Summary` совпадают с числом пунктов в секциях.

---

## 14. Skill: `wiki-query` (можно отложить)

**Назначение:** канонический Query-loop.

**Input:** `<question>` свободным текстом.

**Алгоритм:**
1. **Retrieve.** ripgrep / fts по корпусу, top-N pages. Если есть `qmd` (см. gist) — использовать его. Иначе — простой rg по keywords из вопроса.
2. **Read.** загрузить top-N страниц целиком (или их Chunk Boundaries из Agent Metadata, если token-budget жмёт).
3. **Synthesize.** LLM пишет ответ с цитатами `[[Summaries/X]]`/`[[Concepts/Y]]`.
4. **File-back (опц.).** Если `query.file_back_threshold: always` или пользователь подтвердил → создать `Queries/{date}-{slug}.md`:

```markdown
---
type: query
question: "Что такое Shadow AI и почему это важно для менеджера?"
date: 2026-04-27
sources: [[Summaries/day1-01]], [[Concepts/shadow-ai]]
tags: [query, management]
---

# Shadow AI и менеджмент

> Краткий ответ.

## Подробно
...
## Источники
- [[Summaries/day1-01]]
- [[Concepts/shadow-ai]]
```

5. После file-back → вызвать `wiki-update-index` + `wiki-append-log event=query`.

**Tier 2 prompt-first**, основная логика в LLM, скрипт только обёртка.

---

## 15. Meta-workflow: `ingest-source`

Оркестратор, который соединяет существующий `summarizing-meetings` со всеми wiki-* скиллами в один запуск.

**Файл:** `workflows/ingest-source.md` (по структуре — наследник [`generate-detailed-meeting-summary.md`](https://github.com/MatrixFounder/Universal-skills/blob/main/workflows/generate-detailed-meeting-summary.md), оттуда же берутся проверенные паттерны: PRE-FLIGHT, completeness guarantee, self-check, rationalization table).

**Что переиспользуется из существующего `generate-detailed-meeting-summary.md`:**

| Паттерн оттуда | Как используется здесь |
|---|---|
| `extends: <skill>` директива в frontmatter | `extends: summarizing-meetings` — переиспользуем skill как ingest-engine, не дублируем PRE-FLIGHT/chunking/completeness |
| Division of responsibility блок | в начале `ingest-source.md` явно: skill = «source → page», workflow = «page → wiki state (index/log/concepts/lint)» |
| Pyramid (Level 0/1/2/3) | extend на корпус: Level 0 = vault `index.md`, Level 1 = project `index.md` / category overview, Level 2 = summary-page (как сейчас), Level 3 = chunks + Concepts |
| HTML section anchors `<!-- SECTION:* -->` | переносим в `index.md`, `log.md`, `Concepts/*.md` для агентского навигирования |
| Self-check checklist | расширяем: добавляем corpus-level пункты (index updated, log appended, concepts extracted, no orphans) |
| Verification Loop (re-read end-to-end) | для ingest — re-read summary-страницы перед commit'ом в wiki, проверить что concepts из frontmatter все имеют файлы |
| Rationalization Table («Agent Excuse → Counter-Argument») | для wiki-операций: «orphan link можно оставить» → «нет, `wiki-lint --strict` упадёт; либо stub-page, либо `wiki-research`» |
| Chunk Boundaries в Agent Metadata | используется `wiki-query` для targeted retrieval по якорю, не по полной странице |
| Mermaid-диаграммы | `wiki-lint --report` рисует mermaid-граф связей концептов; `index.md` опционально может содержать project-level mindmap |

**Input:** `--source <transcript-path>` (или массив `--sources [...]`), `--project <name>` (опц., иначе detect по CWD).

**Шаги:**

1. **Resolve config.** Прочитать root `CLAUDE.md` + `<project>/.wiki.yaml` (см. §8.3). Если vault не инициализирован — abort и предложить `wiki-init`.
2. **PRE-FLIGHT** (как у `generate-detailed-meeting-summary`): валидация transcript'а, language detection, ASR quality. Failure → STOP.
3. **Run `summarizing-meetings`** с `meeting_type=discovery`. Получить путь к summary-странице. Output path = резолвится из `project_paths.summaries` + `naming.summary`.
4. **Verify summary-page** до коммита в wiki: запустить `wiki-verify-multi` (см. §25) если включено. Если verdict=FAIL — STOP, оставить страницу в `_drafts/` для ручной правки.
5. **`wiki-update-index`** на summary-страницу (project index + vault index).
6. **`wiki-extract-concepts`** на summary-страницу — **ТОЛЬКО ЕСЛИ** `concepts.auto_extract: true` в финальном merged конфиге проекта. По умолчанию пропускается. Если выключено — этап вообще не запускается, экономим токены.
7. **`wiki-update-index`** на каждую новую concept-страницу — также под флагом `auto_extract`.
8. **`wiki-append-log`** event=ingest, entity=<slug>, note включает счётчики только если auto_extract был активен.
9. **`wiki-lint`** quick-pass на новые страницы (опц., через `--lint` флаг). Orphan'ы из `related:` — informational, не блокирующие. Concept-orphan'ы — только если auto_extract включён (иначе concept-страниц физически нет).
10. **Final report** в stdout: какие файлы созданы/изменены, ссылка на log-entry, статус verify. Если `auto_extract: false` — отчёт упоминает «concept-extraction skipped (off in this project); use `/wiki-extract-concept "X"` для on-demand».

**Failure handling:**
- Шаг 3 упал → ошибка summarizing-meetings, ничего не создалось — clean exit.
- Шаг 4 упал (verify=FAIL) → summary в `_drafts/`, log запись `event=ingest, status=draft, reason=verify-failed`, в stdout — список замечаний.
- Шаги 5–9 упали → log запись `event=ingest, status=partial, failed_at=<step>`. Summary-страница остаётся, но wiki-state может быть несогласован → следующий `wiki-lint` поймает.

**Self-check (в конце workflow):**
```
□ Summary-page существует и валидна (frontmatter, anchors)
□ В index.md есть запись на summary
□ В log.md есть ingest-запись с правильным timestamp
□ wiki-lint quick-pass: 0 critical issues (orphan-warnings — информационно)
□ Verify ensemble: PASS (или явный override от человека)
□ ЕСЛИ auto_extract=true: каждый concept из frontmatter.concepts имеет Concepts/<slug>.md;
  каждая Concepts/<slug>.md::appears_in содержит ссылку на summary
□ ЕСЛИ auto_extract=false: ничего concept-related не проверяется (это норма)
```

---

## 16. Форматы файлов (canonical)

### 16.1 `index.md`

```markdown
---
type: wiki-index
last_updated: 2026-04-27 14:32
total_pages: 66
---

# Wiki Index

> Auto-maintained by `wiki-update-index`. Manual edits are OK between dividers.

## Summaries

### Management & Leadership

- [[Summaries/2026-04-27-savochka-rukovoditel|Руководитель 2026]] — Антон Савочка о трёх кризисах и сложном мышлении [2026-04-27] `#lesson` `#strategy`
- [[Summaries/2026-04-28-prakht-silnyi]] — ...

### Demand Generation

- ...

## Concepts

- [[Concepts/shadow-ai]] — теневое использование ИИ в командах (3 mentions)
- [[Concepts/workslop]] — продукт без реальной мыслительной работы (5 mentions)
- ...

## Queries

- [[Queries/2026-04-27-shadow-ai-i-menedzment]] — Shadow AI и менеджмент
```

### 16.2 `log.md`

```markdown
---
type: wiki-log
started: 2026-04-25 09:00
---

# Wiki Log

## [2026-04-25 09:00] ingest | _init
Vault initialized via `wiki-init`. 0 pages.

## [2026-04-27 14:32] ingest | savochka-rukovoditel-2026
Source: `_raw/transcripts/day1-01.txt` → [[Summaries/2026-04-27-savochka-rukovoditel]]. Concepts: 17 (3 new, 14 updated). Index updated.

## [2026-04-27 15:10] query | shadow-ai-i-menedzment
Question: "Что такое Shadow AI и почему это важно для менеджера?". Answer filed → [[Queries/2026-04-27-shadow-ai-i-menedzment]].

## [2026-04-27 16:00] lint | full
12 issues: 4 orphan, 5 missing-backlinks, 2 stale, 1 duplicate. Report: [[00-Index/lint-2026-04-27.md]].
```

### 16.3 `Concepts/<slug>.md` — см. §12.

---

## 17. Migration существующих `tmp2/` outputs

Чтобы не выбрасывать 16 уже сгенерированных страниц:

1. `wiki-init` в `tmp2/` (или скопировать в новый vault). `--force` для перезаписи дефолтного `CLAUDE.md`, если он мешает.
2. Переместить 16 `day*.md` в `Summaries/`.
3. Прогнать batch:
   ```bash
   for f in Summaries/*.md; do
     wiki-update-index --page "$f"
     wiki-extract-concepts --page "$f"
     wiki-append-log --event ingest --entity "$(basename "$f" .md)" --note "backfill"
   done
   ```
4. Прогнать `wiki-lint` → ожидаемо много orphan'ов на `[[Школа менеджмента Стратоплан]]` и т. п. → решить per-vault: создать stub-страницы или пометить как «external reference» (новый тип файла `Stubs/<slug>.md`, исключаемый из orphan-чекера).

---

## 18. Порядок реализации (фазы) — lean-приоритет

Фазы 1–7 — **минимальный жизнеспособный wiki** без extract-concepts. После 7 у тебя уже работающий corpus с index/log/lint/search и опц. research/query. Всё, что выше — опциональное обогащение.

| Фаза | Что | Зачем именно сейчас |
|---|---|---|
| 1 | `wiki-config.schema.yaml` + шаблоны | Контракт, на котором все остальные скиллы стоят |
| 2 | `wiki-init` | Возможность сразу тестировать на реальном vault'е |
| 3 | `wiki-append-log` | Простейший, отлаживает паттерн «прочитать config + atomic write» |
| 4 | `wiki-update-index` | Idempotent merge — каркас для всех state-mutation скиллов |
| 5 | `wiki-search` (§12.bis) | **Заменяет concept-страницы для 80% задач** за 0 токенов. Закрывает «где упоминается X?» без файлов. |
| 6 | `wiki-lint` (lean mode) | Health-check корпуса. Без extract-concept-чеков — они активируются позже только если включён auto. |
| 7 | `ingest-source` workflow (без шага 6 extract) | Связать summarizing-meetings + index + log + lint в один UX. **MVP wiki**. |
| 8 | (опц.) `wiki-research` + `wiki-verify-multi` | Когда нужно обогащать или проверять качество ingest'ов |
| 9 | (опц.) `wiki-extract-concepts` (§12) | Только если решишь, что какой-то проект нуждается в графе концептов |
| 10 | (опц.) `wiki-query` | Когда корпус достаточно большой, чтобы query был ценным |

**Точка остановки**: после фазы 7 у тебя — рабочий self-maintaining wiki по Karpathy в lean-режиме. Дальше — по необходимости. Не делай 8/9/10, пока реальный use-case не появится.

Каждая фаза заканчивается end-to-end проверкой на реальном vault'е (не на синтетических фикстурах) — `tmp2/` подходит как первый dogfood-vault.

---

## 19. Тестирование

На каждый скилл — unit-тесты + integration-тест на minimal vault.

**Минимальный test vault** (`tests/fixtures/minimal-vault/`):
- 2 summary-страницы (одна с 3 концептами, одна с 2, один концепт пересекается).
- `wiki-config.yaml` с минимальной конфигурацией.

**Сценарии integration-тестов:**

1. `wiki-init` → проверить, что директории и stub-файлы созданы.
2. `ingest-source` на 1 страницу → 1 запись в index, 1 в log, N concept-файлов.
3. `ingest-source` на 2-ю страницу с пересекающимся концептом → concept обновлён (mentions_count=2), не дублирован.
4. Удалить файл вручную → `wiki-lint` ловит index drift и orphan.
5. `wiki-lint --fix` → drift восстановлен, orphan остался (нет автофикса для удалённого target'а).

**End-to-end:** прогнать на 16 файлах из `tmp2/` (миграция §17) → измерить количество концептов, дубликатов, orphan'ов до и после ручной чистки.

---

## 20. Доставка / packaging

Два варианта на выбор:

**Вариант A. Отдельный репо `obsidian-llm-wiki/`.**
```
obsidian-llm-wiki/
├── skills/
│   ├── wiki-init/
│   ├── wiki-update-index/
│   ├── wiki-append-log/
│   ├── wiki-extract-concepts/
│   ├── wiki-lint/
│   └── wiki-query/
├── workflows/
│   └── ingest-source.md
├── schemas/
│   └── wiki-config.schema.yaml
├── tests/
│   └── fixtures/minimal-vault/
└── install.sh        # симлинкует skills/* в ~/.claude/skills/
```

**Вариант B. Claude Code plugin.** Та же структура + `.claude-plugin/plugin.json`. Установка через `claude plugin add ...`. Плюс — атомарная установка/обновление, минус — больше boilerplate.

Рекомендую **A на старте**, миграция в B если станет несколько vault'ов и захочется shared updates.

---

## 21. Зависимости

- Python 3.11+ для скрипта-каркаса.
- Пакеты: `python-frontmatter`, `python-slugify`, `pyyaml`, `jsonschema`, `ripgrep` (системный, для `wiki-query`).
- Никаких внешних API кроме самого LLM.
- Для idempotent atomic writes — stdlib `tempfile.NamedTemporaryFile` + `os.replace`, `fcntl.flock`.

---

## 22. Что важно НЕ забыть при имплементации

- Каждый скрипт принимает `--json-errors` и эмитит uniform error envelope (паттерн уже есть в исходном репо: [`_errors.py`](https://github.com/MatrixFounder/Universal-skills/blob/main/skills/docx/scripts/_errors.py)).
- Atomic writes везде, где обновляется существующий файл (`index.md`, концепт-страницы).
- **Не редактировать** файлы под `wiki.paths.raw_sources` — это immutable layer канона.
- Slug-генерация для кириллицы должна быть детерминированной и стабильной (одно и то же имя → один и тот же slug всегда). Зафиксировать функцию и покрыть её unit-тестами.
- `wiki-extract-concepts` — единственный скилл, где LLM может «домыслить» канонический name. Это нужно явно метить в frontmatter `canonicalized_by: llm` для аудита.
- Все скиллы должны fail-fast при отсутствии `wiki-config` — не угадывать пути.
- Все markdown-выходы — Obsidian-friendly: `[[wiki-link|display text]]` синтаксис, не `[text](path.md)`.
- **Никаких бэкапов и шифрования.** Vault уже под контролем пользователя (git/iCloud/что-то ещё) — скиллы в эту зону не лезут.

---

## 23. Human-editable layer — vault, который можно вести руками

**Проблема:** в каноне Karpathy LLM ведёт wiki сам. В реальности:
- иногда LLM недоступен (нет интернета, нет квоты, режим focus),
- человек хочет дописать своё мнение / факт-чек / личный комментарий,
- ручные правки не должны теряться при следующем `ingest-source` или `wiki-lint --fix`.

Решение — **жёстко разграниченные «человеческая» и «авто» зоны** во всех файлах, плюс протокол ручных правок.

### 23.1 AUTO/MANUAL разметка внутри файлов

Авто-генерируемые блоки оборачиваются HTML-комментариями:

```markdown
<!-- AUTO-MAINTAINED:start id=appears-in -->
- [[Summaries/2026-04-27-savochka]] — кейс Василисы и Ивана.
- [[Summaries/2026-04-28-prakht]] — кризис ответственности.
<!-- AUTO-MAINTAINED:end id=appears-in -->
```

Правило для всех скиллов: **редактирование только между парными маркерами**. Текст вне маркеров — НЕ ТРОГАТЬ. Ни при `--fix`, ни при reingest, ни при concept merge.

Где обязательно:
- `Concepts/<slug>.md`: блоки `appears_in`, `related`, agent-metadata — auto. Каноническое определение и блок «Канонический контекст» — human.
- `index.md`: блоки списков — auto. Заголовки секций и любой текст между ними — human.
- `log.md`: append-only, маркеры не нужны (никогда не редактируется).
- `Summaries/*.md`: тело саммари — генерится один раз и **по умолчанию иммутабельно** (не перезаписывается при reingest). Только агентский blocks — auto.

### 23.2 Frozen pages

В фронтматтере любой страницы:

```yaml
frozen: true
frozen_reason: "вычитано вручную, LLM не трогать"
```

Скиллы при `frozen: true`:
- НЕ перегенерируют тело страницы,
- НЕ перезаписывают auto-blocks (даже если вне frozen — конфликт разрешается в пользу человека),
- `wiki-lint` всё равно проверяет orphan/backlink, но `--fix` не применяется,
- `ingest-source` при reingest того же source видит `frozen: true` → пропускает шаг 3 (summary), идёт сразу к concept-extract.

### 23.3 Прозрачность changes для человека

После каждого автоматического изменения:
- `git diff`-friendly (atomic writes, мелкие правки, не reflow всего файла),
- лог-запись в `log.md` с указанием `changed_files: [...]` (можно потом `git blame` сопоставить),
- опц.: `wiki-lint --report` показывает «files modified by automation в последние 24ч» — для ревью человеком.

Сильно рекомендуется vault держать в git — даёт человеку полноценный rollback.

### 23.4 Ручные правки без LLM

Человек может вести vault руками без всяких скиллов. Условия совместимости:

1. **Schema простая.** `CLAUDE.md` и `.wiki.yaml` — обычный YAML, читается глазами; вручную добавить запись в `index.md` или создать `Concepts/foo.md` по шаблону можно за минуту.
2. **Шаблоны доступны.** В `wiki-init` копируются `templates/` (concept.md, summary.md, query.md) → человек делает `cp templates/concept.md Concepts/new.md` и редактирует.
3. **`wiki-lint --strict` без `--fix`** — единственная LLM-независимая операция, чисто валидация. Человек может запустить когда угодно, увидеть что не сходится, и поправить руками. После этого следующий запуск с LLM «принимает» ручную правку, ничего не отменяет.
4. **Frontmatter required-поля минимальны** — `type`, `title`, `date`, `tags`. Остальное опционально.

### 23.5 Конфликт резолюция

Если человек правил блок, помеченный `AUTO-MAINTAINED`, и потом запустился скилл:
- Скилл detects конфликт (текущее содержимое блока не совпадает с тем, что он сам туда писал в прошлый раз — гипотетически храня прошлую версию в shadow-state, либо просто детект по «contains user-only markers»).
- **Default policy:** human wins. Скилл логирует «conflict at file X block Y, kept human version, my proposed change saved to log». В `log.md` — полный текст того, что скилл хотел записать, чтобы человек мог посмотреть и применить вручную.
- Альтернатива в config: `human_edit.conflict_policy: human-wins | auto-wins | abort` (default `human-wins`).

### 23.6 Что **не** автоматизируется никогда

- `02-Home/` (личные ноты), `04-Areas/`, `06-Archive/` — out-of-scope для wiki-* скиллов. Конфиг это знает: `excluded_paths: ["02-Home/", "04-Areas/", "06-Archive/"]`.
- Любой файл с `frozen: true`.
- Любой файл вне `project_root` и vault-wide layers.

---

## 24. Research / enrichment — агенты для поиска и обогащения

Канон: «valuable answers should be filed back as new pages», «orphan pages, missing cross-references» — поводы пойти искать дополнительный контент. Скиллы ниже закрывают этот цикл.

### 24.1 `wiki-research` — research-агент по концепту или вопросу

**Назначение:** для слабо-определённого концепта или открытого вопроса — провести web-research и создать `Research/<slug>.md`, обогатить concept-страницу.

**Триггеры:**
- Concept-страница имеет `mentions_count: 1` и определение < 200 символов → `wiki-lint` помечает как «under-developed», предлагает запустить research.
- Orphan link `[[Школа менеджмента Стратоплан]]` → research выясняет, что это, и создаёт stub `Concepts/stratoplan.md` или `Stubs/stratoplan.md`.
- Вручную: `/wiki-research --concept shadow-ai` или `/wiki-research --question "Как Klarna откатывала AI-replacement?"`.

**Алгоритм (Tier 2, prompt-first с web tools):**

1. **Frame query.** На входе concept name / question; LLM формулирует 3–5 поисковых запросов (на языке концепта + английский для покрытия).
2. **Search.** WebSearch / WebFetch (Claude Code tools), top-N результатов на запрос. Bing/Google/DuckDuckGo — по доступности.
3. **Filter.** Отбросить low-quality (SEO-spam, content farms). Предпочесть: первичные источники (книги, академические работы), Wikipedia/Wikidata, признанные эксперты.
4. **Deep-fetch.** Для top-3–5 источников — полный текст (`WebFetch` или `markitdown`).
5. **Synthesize.** LLM пишет research-note по шаблону:

```markdown
---
type: research-note
topic: "Shadow AI"
concept: "[[Concepts/shadow-ai]]"     # обратная ссылка на концепт
sources:
  - url: https://hbr.org/...
    title: "..."
    author: "..."
    date: 2025-09-12
    credibility: high
  - url: ...
date: 2026-04-27
tags: [research, shadow-ai, management]
---

# Research: Shadow AI

> Краткий синтез из 5 источников.

## What we found

…

## Conflicts / open questions

- HBR vs Gartner расходятся в определении границ Shadow AI…

## Suggested updates to wiki

- [[Concepts/shadow-ai]] definition can be expanded with «...»
- Add `aliases: [BYOAI, Bring Your Own AI]` to concept page
- New related concept: [[Concepts/byoai]] (worth extracting)

<!-- AUTO-MAINTAINED:start id=raw-citations -->
…full extracted quotes with URLs…
<!-- AUTO-MAINTAINED:end id=raw-citations -->
```

6. **Optional auto-apply.** Если флаг `--apply` или config `research.auto_apply_to_concept: true` — LLM применяет «Suggested updates» к concept-странице (только в auto-blocks). Иначе human apply'ит вручную.
7. **Log + index.** `wiki-append-log event=research`, `wiki-update-index` для research-страницы.

**Ограничения:**
- Web access обязателен — fail-fast если нет сети.
- Каждый source цитируется с URL и датой fetch — по канону citations-as-first-class.
- Никогда не молча инлайнит web-материал в основное тело wiki — только через research-note + явный suggested-update review.

### 24.2 `wiki-discover` — поиск тем для ingest

**Назначение:** «что ещё стоит ингестить?» — анализ корпуса + web для предложения новых источников.

**Алгоритм:**

1. Собрать `concepts.json` — все концепты vault'а с counts.
2. Отметить «edge concepts» — концепты, которые упомянуты, но не раскрыты (singleton mentions, короткие определения).
3. Для каждого — найти в web: видео-лекции, статьи, книги, podcast-episodes на эту тему.
4. Сформировать `Research/discover-{date}.md` со списком предложений: `<source-url> — релевантность <high|med|low> — <зачем>`.
5. Человек выбирает что ингестить → запускает `ingest-source` в обычном порядке.

Tier 2, запускается реже (например, раз в неделю), не в основном ingest-цикле.

### 24.3 `wiki-enrich` — массовое обогащение существующих страниц

**Назначение:** проход по всем `Concepts/*.md`, для каждого с `mentions_count < N` или короткой definition — запустить `wiki-research`. Batch-вариант 24.1 для регулярного maintenance.

Tier 2, опасный (расходует API quota и web-fetches) — нужен флаг `--budget <N>` для ограничения.

### 24.4 Размещение и MCP

Web access — через Claude Code WebFetch/WebSearch tools (in-process). Опционально — через MCP-сервер (например, `mcp-puppeteer`, `mcp-firecrawl`) для более мощного scraping'а; в этом случае config:

```yaml
research:
  web_backend: "webfetch"  # webfetch | mcp-firecrawl | mcp-puppeteer
  max_sources_per_run: 10
  budget_per_day_calls: 100
  cite_format: "obsidian"
  auto_apply_to_concept: false
```

---

## 25. Verifier ensemble — `wiki-verify-multi` (по мотивам vdd-multi)

**Идея:** перед commit'ом ingested страницы (или перед `--fix` от lint, или после `wiki-research auto-apply`) — прогнать ensemble критиков. Это страховка от «LLM написал плохо, никто не заметил, через год корпус полон мусора».

Источник вдохновения — [vdd-multi](https://github.com/MatrixFounder/Agentic-development/blob/main/.agent/workflows/vdd-multi.md): три параллельных критика с разными ролями, merge с дедупликацией, severity-эскалация при пересечении.

### 25.1 Критики (parallel spawn в одной message-уду через Agent tool)

Для wiki — 4 критика, не 3, под специфику контента:

| Critic | Domain | Что проверяет |
|---|---|---|
| `critic-factual` | Фактическая точность | Цифры, даты, имена, цитаты в summary совпадают с исходным transcript / source. Никаких hallucinations. |
| `critic-structural` | Структура | Frontmatter полный, anchors на месте, все required sections заполнены, pyramid не сломан, chunk boundaries валидны. |
| `critic-taxonomy` | Тегирование и concepts | Теги из taxonomy, концепты канонизованы, нет дубликатов с alias-овершалами, related concepts реально существуют в vault'е. |
| `critic-narrative` | Связность и совместимость с корпусом | Не противоречит ли страница уже существующим в vault'е (особенно concept-страницам). Стиль/тон совпадает с языком vault'а. Нет ли стилистических отклонений. |

### 25.2 Orchestration

Тот же паттерн, что в vdd-multi:

1. **PARALLEL SPAWN** (одно сообщение, 4 Agent tool-uses) — каждый критик получает страницу + relevant context (например, `critic-factual` получает исходный transcript; `critic-taxonomy` — `taxonomy.md` + список существующих концептов; `critic-narrative` — соседние concept-страницы).
2. Каждый critic возвращает structured findings:
   ```yaml
   findings:
     - severity: high|medium|low|info
       location: "frontmatter.concepts[3]"
       issue: "Концепт «Workслоп» — alias of existing «workslop». Duplicate."
       suggested_fix: "Удалить из concepts; в теле заменить на [[Concepts/workslop]]."
   ```
3. **Merge phase.** Дедупликация findings по `(file, location ± 3 lines)`, severity-escalation если 2+ critics flag одно место, hallucination-filtering (если critic ссылается на несуществующий line — отбросить).
4. **Verdict.** `--fail-on=high` (default) → если хоть одно high-severity → FAIL. `--fail-on=none` → всегда PASS, отчёт информативный.
5. **Apply.** При `--fix` — applies только safe фиксы (single-suggested-fix, severity ≥ medium, no manual judgement). Остальное — выводится в отчёт.

### 25.3 Где встраивается в pipeline

- **`ingest-source` шаг 4** (как уже описано в §15) — после `summarizing-meetings`, перед commit в wiki.
- **`wiki-lint --strict`** опц. — после собственных чеков прогнать ensemble на N страниц с самыми старыми датами или новейшими modifications.
- **`wiki-research` шаг 6 auto-apply** — verify до того, как research-suggestions попадут в concept-страницу.

### 25.4 Output

Стандартный merged report (markdown):

```markdown
# Wiki Verify Multi — 2026-04-27 14:55

## Target
- File: `03-Projects/Generation-Demand/Summaries/2026-04-27-savochka.md`
- Source: `_raw/day1-01.txt`

## Verdict: FAIL (1 high, 3 medium, 5 low)

## Findings

### [HIGH] critic-factual @ frontmatter.date
Указан `2026-04-27`, в transcript явно «12 марта 2026». Galuc.

Suggested: исправить date.

### [MEDIUM] critic-taxonomy @ frontmatter.concepts
Концепт «Workслоп» — дубликат `[[Concepts/workslop]]` (existing alias).

Suggested: удалить, оставить только канонический slug.

…

## Convergence
- critic-factual: clean (no further iterations needed)
- critic-structural: clean
- critic-taxonomy: clean
- critic-narrative: diminishing-returns (3 minor stylistic findings, acceptable)
```

И machine-readable JSON sidecar для `ingest-source` orchestrator'а.

### 25.5 Anti-patterns (унаследованы из vdd-multi)

- ❌ Sequential spawn критиков (теряется независимость, второй видит вывод первого).
- ❌ Запускать на пустой / draft странице (нечего верифицировать → false-positives).
- ❌ Auto-apply medium-severity без human review (особенно от `critic-narrative` — это стиль, субъективно).
- ❌ Прогонять весь vault на каждом ingest (дорого) — только новые/модифицированные страницы.

### 25.6 Деградация

Если LLM-доступ ограничен / quota — graceful degrade:
- 1 critic вместо 4 (оставить `critic-structural` — он наиболее детерминистический, можно сделать почти без LLM, чисто на regex/jsonschema).
- `--fail-on=critical` only — не блокировать ingest на medium issues.
- Skip ensemble целиком при флаге `--no-verify` (как в vdd-multi есть `--no-fix`).

---

## 26. Принятые архитектурные решения

Все вопросы из этого раздела закрыты до старта имплементации. Ниже — финальные решения, на которые опираются скиллы.

| # | Тема | Решение |
|---|---|---|
| 1 | `raw_sources` scope | **Оба, project имеет приоритет.** Скиллы сначала смотрят `<project>/_raw/`, при отсутствии — fallback на vault-wide `01-Inbox/`. См. §8.7. |
| 2 | External references (`[[Школа Стратоплан]]`) | **Unified data model: `type: concept` + `external: true`** — НО с default `wiki.concepts.auto_extract: false`, поэтому файлы по умолчанию не создаются вовсе. Lint отчитывает orphan'ы как `info`, не error. Plus `external_allowlist` для имён, которые молча игнорировать. |
| 3 | Concept aliases scope | **Vault-wide всегда.** `wiki.concepts.aliases_scope: "vault"`. Никакой фрагментации между проектами; promote-to-vault работает без коллизий. |
| 4 | Project taxonomy override | **Полный override разрешён.** Project может в `.wiki.yaml::project.taxonomy.full_override: true` объявить свою taxonomy полностью. Default — extension через `extra_tags`. |
| 5 | Privacy на `wiki-research` | **Гибрид: флаг во frontmatter + tag-list.** Concept-страница с `private: true` или `tags: [confidential]` → research fail-fast. Плюс vault-wide `wiki.research.private_concepts: [...]` и `private_tags: [confidential]`. Default — пустые списки. |
| 6 | Concept-page extraction | **On-demand + per-project YAML override.** Default `wiki.concepts.auto_extract: false` — никаких concept-страниц на ingest. Команда `/wiki-extract-concept "X"` — singleton on-demand. Per-project `.wiki.yaml::project.concepts.auto_extract: true` — для папок, где граф концептов нужен. См. §12 и §12.bis (`wiki-search` как замена для 80% случаев). |

Все эти решения встроены в JSON Schema (`wiki-config.schema.yaml`, §8.6) с правильными defaults — пользователь может ничего не указывать в `.wiki.yaml` для типичных проектов.

