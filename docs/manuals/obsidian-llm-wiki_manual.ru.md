# obsidian-llm-wiki — Руководство

> 🇷🇺 Русское зеркало [`obsidian-llm-wiki_manual.md`](obsidian-llm-wiki_manual.md).

> **Дополнение к [`README.md`](../../README.md).** README — это *точка входа*
> (что представляет собой проект, как его установить, индекс команд). **Это руководство —
> *методология***: зачем нужна каждая команда, как работать с markdown-документами
> vault (стандартными и пользовательскими layout) и как подключить wiki к другому
> агенту как внешний источник знаний. Если вы хотите просто начать работу, читайте
> README. Если вы хотите *грамотно эксплуатировать* wiki — читайте это. Однострочную
> повседневную шпаргалку (основные команды, manual + Claude CLI) см. в
> [`cli-quick-reference.ru.md`](cli-quick-reference.ru.md).

---

## Содержание

- [Обзор](#обзор)
- [Зачем вообще нужен слой index (методология)](#зачем-вообще-нужен-слой-index-методология)
- [Как запускать команды](#как-запускать-команды)
  - [Три поверхности вызова](#три-поверхности-вызова)
  - [Какая поверхность для какой команды](#какая-поверхность-для-какой-команды)
- [Словарь команд по назначению](#словарь-команд-по-назначению)
  - [1. Создание знаний](#1-создание-знаний)
  - [2. Поиск и извлечение](#2-поиск-и-извлечение)
  - [3. Разрешение сущностей](#3-разрешение-сущностей)
  - [4. Ответ и проверка (RAG)](#4-ответ-и-проверка-rag)
  - [5. Поддержание работоспособности](#5-поддержание-работоспособности)
  - [6. Жизненный цикл vault](#6-жизненный-цикл-vault)
- [Работа с документами в Obsidian](#работа-с-документами-в-obsidian)
  - [Стандартный layout (karpathy)](#стандартный-layout-karpathy)
  - [Анатомия страницы и инварианты аудируемости](#анатомия-страницы-и-инварианты-аудируемости)
  - [Контракт автора: markdown канонический](#контракт-автора-markdown-канонический)
  - [Регистрация готового саммари (не raw)](#регистрация-готового-саммари-не-raw)
  - [Кастомные layout'ы: движок layout](#кастомные-layoutы-движок-layout)
  - [Справочник: типы страниц и типы связей (модель знаний)](#справочник-типы-страниц-и-типы-связей-модель-знаний)
  - [Смешанный vault: области только для поиска + course-зоны, доступные для enrich](#смешанный-vault-области-только-для-поиска--course-зоны-доступные-для-enrich)
  - [Автоматизация смеси: `wiki-sync` (пофайловая маршрутизация, конвертация, OCR)](#автоматизация-смеси-wiki-sync-пофайловая-маршрутизация-конвертация-ocr)
- [Использование wiki как внешнего ресурса для других агентов](#использование-wiki-как-внешнего-ресурса-для-других-агентов)
  - [Модель интеграции: JSON-конверты + коды выхода](#модель-интеграции-json-конверты--коды-выхода)
  - [Контракт `prepare` / `apply` (Decision-17)](#контракт-prepare--apply-decision-17)
  - [Wiki как backend для RAG](#wiki-как-backend-для-rag)
  - [Недоверенные данные: позиция H-6](#недоверенные-данные-позиция-h-6)
- [Здоровье и обслуживание, методологически](#здоровье-и-обслуживание-методологически)
- [Анти-паттерны (НЕ делайте)](#анти-паттерны-не-делайте)
- [Приложение со справочником команд](#приложение-со-справочником-команд)
- [См. также](#см-также)
---

## Обзор

**obsidian-llm-wiki** — это *слой index + инструментарий* для
[llm-wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) в стиле
Obsidian. Файловый слой (синтез страниц с помощью LLM) принадлежит навыку `wiki-ingest`,
встроенному in-process; этот репозиторий считывает его вывод в index SQLite и
обслуживает быстрые структурированные запросы, граф сущностей, RAG-ответы со ссылками
и слой проверки.

| Свойство | Значение |
|---|---|
| **Тип** | Index базы знаний на множество vault + набор CLI-инструментов |
| **Канонический источник** | Markdown в vault Obsidian (Class A) |
| **Производный кэш** | Один глобальный SQLite-DB (FTS5 + WAL), партиционированный по `vault_id` (Class B/C) |
| **Поверхность** | 16 CLI (`wiki-*`), каждая также является slash-командой `/wiki-*` внутри Claude Code |
| **Контракт ввода-вывода** | stdin/аргументы на вход → однострочный JSON-конверт в stdout + код возврата |
| **Ключевой инвариант** | DB на 100% перестраивается из markdown (`wiki-reindex --full`) |
| **Схема** | `user_version = 7` (`sql/wiki-index-v2.sql`) |
| **Среда выполнения** | Python 3.14+; зависимости в `requirements.txt` |

---

## Зачем вообще нужен слой index (методология)

Стандартный паттерн RAG **не имеет состояния**: каждый вопрос заново выводит знание
из сырых документов, и ничего не накапливается. llm-wiki Карпатого переворачивает это —
LLM **инкрементально строит и поддерживает постоянную, взаимосвязанную wiki**, которая
располагается между вами и сырыми источниками. Знание **накапливается**: каждый ingest
обогащает корпус, который читает следующий запрос.

`wiki-ingest` выполняет *файловую* половину этого цикла (синтезирует страницы, сливает
аддитивно, помечает противоречия). Этот репозиторий выполняет ту половину, которая делает
накопление *применимым в масштабе*:

```mermaid
flowchart LR
    SRC["raw source /<br/>external summary"] --> C
    C["CONSTRUCT<br/>enrich · extract · upsert"] -->|"writes"| MD["MARKDOWN<br/>Class A — canonical"]
    MD -->|"index / reindex"| DB["SQLITE INDEX<br/>Class B/C — rebuildable"]
    DB -->|"rebuild (--full)"| MD
    DB -->|"retrieve"| ANS["ANSWER + VERIFY<br/>cited RAG (wiki-query / wiki-verify-multi)"]
    ANS -->|"filed back as a page"| MD
    MD -.->|"MAINTAIN: lint · resolve · render"| DB
    classDef canon fill:#eef7ee,stroke:#5a5;
    classDef cache fill:#e8f0ff,stroke:#5577cc;
    class MD canon;
    class DB cache;
```

Методологические следствия, которым служит каждая команда ниже:

1. **Markdown канонический; DB — это кэш.** Ручные правки файлов vault являются
   первоклассными. DB никогда не хранит знание, которого нет в markdown —
   его всегда можно выбросить и перестроить. (ADR-002 §D8, контракт Class A/B/C.)
2. **Каждый факт аудируем.** Утверждения прослеживаются к своему источнику через
   сноски-цитаты; ответы цитируют только извлечённые источники; ничто не «просто известно».
3. **Система никогда не выбирает победителя молча.** Противоречия *помечаются*,
   а не разрешаются. Неудачная проверка *фиксируется*, а не исправляется автоматически.
4. **Хорошие ответы накапливаются.** RAG-ответ со ссылками подшивается обратно как
   первоклассная страница, чтобы следующий запрос мог его найти.

---

## Как запускать команды

Команды `wiki-*` — это обычные **shell-CLI**, которые работают с markdown-файлами vault.
Сам Obsidian их не *выполняет* — роль Obsidian в том, чтобы быть редактором/просмотрщиком
markdown Class A, — но вы можете запускать их прямо в окне Obsidian с помощью community-плагина
`Terminal` (встроенный настоящий shell; см.
ниже), так что на практике покидать Obsidian вовсе не нужно. По умолчанию index SQLite
располагается целиком вне vault (`~/Library/Application Support/wiki-index/global.db` на
macOS) — один глобальный DB, общий для всех vault, партиционированный по `vault_id`. Вместо этого vault может
владеть **vault-local** index, который путешествует вместе с ним (`index_db: .wiki/index.db` в
`WIKI_SCHEMA.md`); вы выбираете global или local один раз, при инициализации — см.
[Выбор базы данных index](#choosing-the-index-database-global-default-vs-vault-local)
в разделе «Жизненный цикл vault». Рабочий цикл такой: **правьте в Obsidian → запустите команду → reindex
подтягивает кэш → search / query это отражает** — и Obsidian подхватывает изменения
на диске вживую.

```mermaid
flowchart LR
    OBS["Edit in Obsidian<br/>Class A markdown (canonical)"] --> RUN["Run a wiki-* command<br/>terminal · Terminal plugin ·<br/>Claude Code · Gemini CLI"]
    RUN --> RIDX["reindex / index-upsert<br/>cache catches up to canon"]
    RIDX --> SRCH["search / query / lint<br/>reflects the change"]
    SRCH -.->|"cited answers filed back as pages"| OBS
    classDef canon fill:#eef7ee,stroke:#5a5;
    classDef act fill:#e8f0ff,stroke:#5577cc;
    class OBS canon;
    class RUN act;
```

### Три поверхности вызова

**1. Обычный терминал (базовый вариант).** После `bin/install-globally.sh` обёртки
`~/.local/bin/wiki-*` находятся в `PATH` и запускаются из любого каталога — каждая
обёртка делает `cd` в репозиторий, активирует `.venv` и выполняет CLI, так что
ручная настройка не требуется:

```bash
wiki-search "vault bottleneck" --vaults my-vault
wiki-lint --vault my-vault
wiki-reindex --delta --vault my-vault
```

Obsidian при этом даже не обязан быть открыт. Это правильная поверхность для
**детерминированных** команд.

**2. Внутри Obsidian, через community-плагин `Terminal`.** Плагин
[Terminal](https://github.com/polyipseity/obsidian-terminal) встраивает *настоящий*
интегрированный shell внутрь Obsidian (как терминал в VS Code). Поскольку это
подлинный shell, обёртки `wiki-*` разрешаются через `PATH` и активируют venv
точно так же, как в любом терминале, — так что вы можете править заметку и запускать
`wiki-reindex --delta` в одном и том же окне, без переключения по alt-tab. (Более лёгкая
альтернатива, плагин **Shell commands**, привязывает фиксированный вызов `wiki-*` к
команде/горячей клавише Obsidian — удобно для `wiki-lint` в одно нажатие, но разумно
только для детерминированных команд.)

**3. Внутри сессии агента (Claude Code — рекомендуется для LLM-команд).**
Те же команды доступны как slash-команды `/wiki-*`; агент автоматически предлагает их по
триггерам SKILL.md. Для `wiki-query` / `wiki-verify-multi` / `wiki-extract-concepts`
/ `wiki-enrich` это фактически *обязательная* поверхность, потому что в середине
их контракта `prepare`/`apply` находится шаг рассуждения LLM, которым владеет orchestrator (см.
[контракт `prepare`/`apply`](#the-prepare--apply-contract-decision-17)). Вы
*можете* запускать их детерминированные половины вручную, но тогда вам придётся
делать синтез/критику самостоятельно. Другие поставщики (Gemini CLI и т. п.) управляют теми же
вендоро-нейтральными бинарниками — раздел `## Fallback` каждого workflow объясняет
путь не для Claude Code (встроить навык-контракт в системный контекст вместо
`Skill({…})`).

### Какая поверхность для какой команды

| Команда | Обычный терминал / плагин `Terminal` Obsidian | `/wiki-*` Claude Code | Gemini / другие агенты |
|---|---|---|---|
| `init` · `search` · `lint` · `reindex` · `index-upsert` · `index-render` · `confirm` · `alias` · `merge` · `append-log` · `sync scan` · `sync record` | ✅ запуск напрямую | ✅ | ✅ |
| `query` · `verify-multi` · `extract-concepts` · `enrich` · `sync` *(исполнитель)* *(нужен шаг LLM)* | ⚠️ только детерминированные половины — рассуждение LLM придётся подавать вручную | ✅ **рекомендуется** | ✅ через `## Fallback` каждого workflow |

> **Единственная дисциплина, которая важна:** после того как вы вручную правите markdown в Obsidian,
> сообщите об этом index — `wiki-index-upsert` для одного файла, `wiki-reindex --delta` для
> многих. Пока вы этого не сделаете, `wiki-search` возвращает устаревшие snippet, а `wiki-lint` сообщает
> о расхождении хэшей. Markdown канонический; reindex — это то, как кэш узнаёт об изменениях.

---

## Словарь команд по назначению

16 CLI — это не плоский список: каждая играет роль в цикле выше. Ниже
каждая команда описана как *зачем она существует* и *когда к ней обращаться*, а не просто
по её флагам (они живут в каждом [`SKILL.md`](../../skills/)).

### 1. Создание знаний

Эти команды превращают сырой материал в накапливающиеся страницы.

| Команда | Зачем существует / что делает |
|---|---|
| **`wiki-sync`** | **Диспетчер уровня зоны** (вход для множества файлов). `scan <zone>` классифицирует *каждый* файл по расширению + тегу `#wiki/*` + форме содержимого и выдаёт детерминированный **план** (convert / ingest / upsert / skip); [workflow `wiki-sync`](#automating-the-mix-wiki-sync-per-note-routing-conversion-ocr) исполняет его идемпотентно (office/PDF→md, **OCR отсканированных PDF**, удаление таймстампов из `.vtt`, summarise→enrich→extract, upsert готовых заметок, пропуск sidecar-представлений). Обращайтесь к ней вместо ручной маршрутизации папки разнородных вбросов файл за файлом. Детерминированное ядро, без LLM; `wiki-sync record` — это per-file маркер фиксации. |
| **`wiki-enrich`** | Вход для **сырого материала** (один файл). Передайте ей сырой файл-источник; она вызывает (встроенный) слой синтеза `wiki-ingest` (который **суммирует источник с помощью LLM**), затем зеркалит полученный манифест в index. ⚠️ `wiki-enrich` **всегда трактует `--source` как сырой** — режима «пропустить summary» нет. Если у вас *уже есть готовый summary*, **не** используйте `wiki-enrich`; вместо этого используйте [рецепт готового summary](#registering-a-pre-made-summary-not-raw). (`wiki-sync` под капотом компонует `wiki-enrich` для файлов, маршрутизированных на `ingest`.) |
| **`wiki-extract-concepts`** | *Ретроспективный* вход. Для страницы-источника, уже находящейся в index, она извлекает концепты/сущности, которые та упоминает, но для которых ещё нет страницы, — превращая неявное знание в явные, связываемые страницы. Двухпроходный навык `prepare`/`apply` (см. [ниже](#the-prepare--apply-contract-decision-17)). Используйте её, чтобы *уплотнить* существующий корпус, или после импорта множества источников разом — **независимо от того, как страница-источник попала в index** (сырой ingest или ручная регистрация). |
| **`wiki-index-upsert`** | Примитив для одного файла. Индексирует один markdown-файл идемпотентно (совпадение file-hash — это no-op). Используйте её, когда вы написали вручную, отредактировали вручную **или подложили готовый summary из другого места** и хотите, чтобы index отразил это немедленно, без полного reindex — **без LLM, без обработки сырого материала**. |
| **`wiki-append-log`** | Пишет структурированное событие в `log.md` *и* зеркалит его в таблицу `log_events` атомарно (flock + fsync, двунаправленный контракт M-2). Лог — это удобная для grep хронологическая память для будущих сессий агента: git diff — для людей, лог — для следующего LLM. |

### 2. Поиск и извлечение

Повседневный путь чтения — **сначала search, потом grep**.

| Команда | Зачем существует / что делает |
|---|---|
| **`wiki-search`** | Полнотекстовый поиск FTS5 BM25 по одному или многим vault, ранжированный, со snippet, по умолчанию расширяющийся через алиасы сущностей. **Поиск по умолчанию устойчив к словоформам** (TASK 028): одиночные термины автоматически приводятся к основе с префиксом (по письменности — кириллица→russian, латиница→english) и **сводят ё/е** в запросе и в теле, так что одна введённая форма находит свои словоформы, а `ещё`/`еще` — один токен. `--exact` (`--no-stem`) отключает стемминг для точного буквального поиска (свёртка ё/е сохраняется). Это быстрый поиск, заменяющий перечитывание сырых файлов. Он *также* выполняет **фильтрацию по метаданным**: `--status` / `--severity` / `--where 'field=value'` компилируются в предикат `CAST(json_extract(frontmatter_json, …) AS TEXT) = ? OR EXISTS(json_each … = ?)` (не полнотекстовый), так что **скалярные** значения с дефисами (`SEV-2`) и числовые (`priority=1`) сопоставляются по строке, А ТАКЖЕ совпадает **элемент списка** (TASK 033) — `--tag decision` (сахар для `--where 'tags=decision'`) перечисляет все страницы типизированного класса `decision` одной командой; опустите запрос для чистого *перечисления* по метаданным. Он *также* выполняет **временную фильтрацию** (TASK 034): `--as-of YYYY-MM-DD` возвращает только страницы, **активные на эту дату** — созданные не позже неё И ещё не вытесненные/аннулированные к этому моменту, *выводится* из `pages.date` + графа supersede/invalidate (без LLM, без ручного `valid_to`; `valid_from`/`valid_to` — необязательные override). Напр. `--tag decision --as-of 2026-04-15` отвечает «какие решения были активны на 2026-04-15». Свёртка ё/е в теле вступает в силу после ближайшей `wiki-reindex --full`; стемминг и свёртка ё/е в запросе — сразу. |
| **`wiki-index-render`** | Перегенерирует `index.md` — *доступную только для чтения проекцию* DB — сохраняя любые блоки `<!-- BEGIN-CUSTOM:name -->`, созданные оператором. С `--auto-indexes` он также рендерит реестры Class-B «перестраиваемого markdown» (например, `KNOWN_ISSUES.md`, свёрнутый из файлов-источников по отдельным issue). Используйте его, чтобы обновить просматриваемый человеком каталог после ingest. |

### 3. Разрешение сущностей

Корпус накапливает *кандидатов* в сущности (предположенных LLM) и дублирующиеся написания.
Эти команды курируют граф сущностей, чтобы он оставался графом, а не кучей.

| Команда | Зачем существует / что делает |
|---|---|
| **`wiki-confirm`** | Повышает *кандидата* в сущность (`is_candidate = 1`, извлечённого LLM, непроверенного) до *подтверждённой* — ваше редакторское одобрение того, что это реальная, каноническая сущность. `--undo` понижает; `--auto --threshold N` массово повышает всё, что упоминается ≥ N раз. Состояние подтверждения — Class A (frontmatter страницы сущности), зеркалится в DB. |
| **`wiki-alias`** | Регистрирует алиасы поверхностных строк («Hermes» → `hermes-agent`). Алиасы **жёстко уникальны в пределах vault** (одна поверхностная строка → ровно одна сущность), и `wiki-search` расширяется через них, так что запрос по любому написанию находит каноническую страницу. Frontmatter Class A + зеркало в DB. |
| **`wiki-merge`** | Сворачивает дублирующую сущность в каноническую (`hermes-framework` → `hermes-agent`): перенаправляет все ссылки, поглощает + регистрирует redirect-алиасы и удаляет дублирующую страницу. Таблица алиасов *и есть* долговечный redirect — нет переписывания wikilink, которое могло бы рассинхронизироваться. |

### 4. Ответ и проверка (RAG)

Накопительная отдача: превратить корпус в ответы со ссылками и проверить их.

| Команда | Зачем существует / что делает |
|---|---|
| **`wiki-query`** | Ответ, дополненный извлечением. `prepare` извлекает (FTS5 BM25 + расширение по алиасам/графу сущностей); агент-orchestrator синтезирует ответ *со ссылками*; `apply` подшивает его как первоклассную накапливающуюся страницу `_queries/<slug>.md` — индексированную, доступную для поиска FTS, с обратными ссылками `cited`, которые переживают полный reindex. Это «хорошие ответы можно подшить обратно в wiki», сделанное долговечным. |
| **`wiki-verify-multi`** | **Выключенный по умолчанию** аудит прозы четырьмя критиками (factual-grounding / logic-coherence / security-injection / completeness-faithfulness) поданного ответа *относительно процитированных им источников*. Он подшивает страницу-вердикт `_verifications/verify-<slug>.md`. FAIL **фиксирует вердикт и завершается с ненулевым кодом — он никогда не редактирует ответ**. Обращайтесь к нему для ответов с высокой ставкой, где молчаливая галлюцинация обошлась бы дорого. |
| **`wiki-graph`** | Read-only обход **графа событий** (TASK 032/034 / ADR-004): типизированные рёбра между страницами (`implements`/`supersedes`/`causes`/`relates-to`, плюс рёбра TASK-034 `invalidated-by`/`activated-by`/`uses`/`owns`, + авто-выведенные инверсии), заданные во frontmatter и проиндексированные при reindex. `backlinks` (входящие) / `neighbors` (один шаг, in/out/both, по `--kind`) / `chain` (ограниченная цепочка supersession/causation). Работает в паре с `wiki-query prepare --follow-edges`, который вплетает соседей-по-рёбрам в цитируемый ответ (по умолчанию OFF; детерминирован). «Что вызвало это решение / что заменяет X / родословная». |

### 5. Поддержание работоспособности

| Команда | Зачем существует / что делает |
|---|---|
| **`wiki-lint`** | Проверка работоспособности на уровне SQL по одному vault или по всем сразу. Выявляет **сиротские ссылки** (страницы без входящих ссылок), **висячие ссылки** (`[[X]]` без страницы X), **отсутствующие на диске** страницы (расхождение DB/диск), **расхождение хэшей** (файл изменился, но не был переиндексирован), **несоответствия типов** и **дубликаты концептов между vault**. Запускайте её периодически; у находок есть естественный приоритет действий (висячие → противоречия → отсутствующие → сироты). `--mtime-skip` меняет целостность полного хэша на скорость. |
| **`wiki-reindex`** | Перестраивает DB из markdown. `--full` стирает и перестраивает (это **проверка перестраиваемости** — если vault не переживает `--full`, контракт Class A→B нарушен); `--delta` выполняет инкрементальный проход на основе mtime/хэшей после ручных правок. Авторитетное согласование кэша ↔ канона. |

### 6. Жизненный цикл vault

| Команда | Зачем существует / что делает |
|---|---|
| **`wiki-init`** | Берёт vault под управление. `--register-existing` индексирует уже существующий vault; `--scaffold-new --layout <name>` создаёт свежий скелет vault; `--reconcile` переименовывает/перенаправляет зарегистрированный vault. Добавьте `--local` (или `--index-db <path>`), чтобы дать vault **собственный** index DB вместо общего глобального — см. ниже. Однократная настройка для каждого vault. |

#### Выбор базы данных index: глобальная (по умолчанию) или vault-local

Есть два способа хранить index vault, и вы выбираете **один раз, при инициализации**:

| | **Глобальная (по умолчанию)** | **Vault-local** |
|---|---|---|
| Где живёт DB | `~/Library/Application Support/wiki-index/global.db` (macOS) — *вне* каждого vault | внутри vault, например `<vault>/.wiki/index.db` |
| Объявлена в `WIKI_SCHEMA.md`? | нет (`index_db` отсутствует) | да (`index_db: .wiki/index.db`) |
| Хороша, когда | много vault, по которым вы ищете вместе; одна машина | vault должен быть **переносимым** — клонируете/перемещаете его, и index едет с ним; или вы хотите один DB на проект, в gitignore и перестраиваемый |
| `--vault all` охватывает | каждый vault, зарегистрированный в глобальном DB | только этот vault (это **остров** — без федерации между DB) |

Три рецепта — **единственная** разница в том, что `wiki-init` пишет в `WIKI_SCHEMA.md`:

```bash
# (a) GLOBAL — the default. Nothing extra to declare.
wiki-init --register-existing --vault /path/to/MyVault

# (b) VAULT-LOCAL — DB at <vault>/.wiki/index.db (vault-relative & contained:
#     a symlink or `..` escape out of the vault is refused). --local writes
#     `index_db: .wiki/index.db` into WIKI_SCHEMA.md and registers into THAT DB.
wiki-init --register-existing --vault /path/to/MyVault --local
#     ...or a custom in-vault path:
wiki-init --register-existing --vault /path/to/MyVault --index-db db/index.db

# (c) CLOUD-SYNCED vault (iCloud / Dropbox) — SQLite must NOT sit inside the
#     byte-syncing folder (WAL/shm corruption). Point at an ABSOLUTE path OUTSIDE
#     the sync root. Because WIKI_SCHEMA.md travels with the vault, an absolute
#     path needs an explicit opt-in so a synced/cloned config can't silently
#     redirect writes elsewhere on your disk:
WIKI_ALLOW_ABSOLUTE_INDEX_DB=1 \
  wiki-init --register-existing --vault /path/to/MyVault \
            --index-db ~/wiki-dbs/myvault.db
```

`--local` / `--index-db` — это чистое удобство: эквивалентно можно вручную отредактировать
`WIKI_SCHEMA.md` и добавить `index_db: .wiki/index.db` во frontmatter. **Приоритет
всегда такой: `--db-path` (переопределение на одну команду, в основном для тестов) > `index_db`
(в `WIKI_SCHEMA.md`) > глобальный.** Так что vault остаётся глобальным до того дня, когда вы добавите
`index_db`; уберите ключ — и он снова глобальный, байт-в-байт. **Пути iCloud
автоматически отклоняются, где бы они ни появились**, чтобы предотвратить повреждение WAL/shm в SQLite.

---
## Работа с документами в Obsidian

Именно эту половину большинство операторов понимают неправильно: **как выглядят
файлы, что мне можно править руками и как подогнать инструментарий под vault,
форма которого отличается от Karpathy?** Три части: стандартный layout, контракт
страницы и кастомные layout'ы.

### Стандартный layout (karpathy)

`wiki-init --scaffold-new --layout karpathy` создаёт (и инструментарий ожидает)
именно такую форму. Папки с ведущим подчёркиванием следуют соглашению Obsidian о
системных папках — они сортируются в начало и сигнализируют «мета-контент, а не
пользовательские заметки»:

```
<vault>/
├── WIKI_SCHEMA.md          # this vault's identity + conventions (REQUIRED — holds vault_id)
├── index.md                # read-only catalog projection (## Sources / ## Concepts / ## Entities)
├── log.md                  # chronological append-only journal (mirrors log_events)
├── _sources/               # per-source summary pages         (type=summary)   ← wiki-ingest
├── _concepts/              # abstract concepts                (entities)        ← wiki-ingest
├── _entities/              # concrete people/companies/...     (entities)        ← wiki-ingest
├── _queries/               # filed RAG answers                (type=query)      ← wiki-query
├── _verifications/         # verdict pages                    (type=verification) ← wiki-verify-multi
├── _raw/                   # immutable raw source files (never modified)
│   ├── .locks/             # ingest lock files
│   └── failed/             # quarantined failed ingests
├── 00-Vault-Index/
│   └── log/                # monthly log.md files
└── Lessons/<Course>/       # (optional) course-tier sub-vaults (ADR-002 §D6)
```

Ключевые различия:

- **`_sources/` против `_concepts/`/`_entities/`.** Sources — это *неизменяемые
  саммари одного входа*; concepts/entities — это *аддитивные, перекрёстно
  связанные абстракции*, построенные из множества источников. Первое — это лист;
  второе — это граф.
- **Vault-уровень против course-уровня.** Страница в корне vault имеет
  `pages.project = '_vault_'`. Страница под `Lessons/<Course>/` несёт slug
  названия курса в качестве своего `project` — это позволяет одному vault держать
  множество course-подкорпусов без пересечений.
- **`index.md` и автогенерируемые реестры — это Class B** — *генерируемые*. Не
  пишите туда знание; пишите его на страницах, затем `wiki-index-render`.
  Единственное исключение: явные блоки
  `<!-- BEGIN-CUSTOM:name --> … <!-- END-CUSTOM:name -->` сохраняются дословно
  при рендерах.
- **`WIKI_SCHEMA.md` — это удостоверение личности vault.** Это discovery-маркер
  для `wiki-init`, и он держит **обязательный** `vault_id`
  (`^[a-z][a-z0-9-]{2,31}$`, без hash-fallback) плюс `layout:` и `language:`.

### Анатомия страницы и инварианты аудируемости

Страница concept/entity (создаётся файловым слоем, индексируется этим репозиторием)
несёт frontmatter + разбитое на секции тело + сноски-цитаты. Два инварианта,
которые нельзя ломать вручную:

**1. Сноска-цитата (инвариант аудируемости).** Каждый факт прослеживается до
своего источника через Markdown-сноску, ключ которой совпадает со slug страницы
источника:

```markdown
## Definition
Risk-adjusted return: `(R_p − R_f) / σ_p`. [^src-hermes-trading-agent]

## Footnotes
[^src-hermes-trading-agent]: [[hermes-trading-agent]] — AI Trading Agent Holy Grail
```

Кликни по сноске → перейди к источнику. Именно это держит wiki аудируемым на
50 ingest'ах вместо превращения в кучу шума.

**2. Блок противоречий (инвариант «не выбирай победителя»).** Когда новый источник
не согласуется с существующим утверждением, инструментарий вставляет блок
`## Contradictions` для рассмотрения оператором, а не молча перезаписывает:

```markdown
## Contradictions
> ⚠️ **Contradiction flagged** — operator review needed.
> - Existing claim: min Sharpe of 1 recommended
> - New claim from [[conservative-crypto-guide]]: a minimum Sharpe of 0.5 is sufficient.
```

Оператор разрешает противоречия, редактируя страницу — задача машины *обозначить*,
а не *решить*.

Поля frontmatter, которые читает index: `type`, `title`, `date`, `tags`,
`concepts:`/`related:` (цели ссылок), `aliases:`, `is_candidate`, а также поля
ссылок вроде `cites:` (→ `cited` refs) и `verifies:` (→ `verifies` refs). Столбец
`frontmatter_json` хранит весь блок целиком, и именно это питает
`wiki-search --where`.

### Контракт автора: markdown канонический

Поскольку БД — это перестраиваемый кэш, **ручное редактирование markdown
поддерживается и ожидается** — но у него есть дисциплина:

| Вы сделали это | Затем сделайте это | Почему |
|---|---|---|
| Отредактировали одну страницу руками | `wiki-index-upsert --file <path>` (или `wiki-reindex --delta`) | index должен узнать об изменении; иначе `wiki-lint` сообщит о **hash drift**. |
| Отредактировали много страниц / реструктурировали | `wiki-reindex --delta` (или `--full`) | Delta ловит изменения mtime; full — это авторитетная перестройка. |
| Добавили факт на страницу concept | Добавьте сноску `[^src-…]` | Сохраните аудируемость — утверждение без сноски — это осиротевшее заявление. |
| Хотите изменить соглашение на диске | Отредактируйте layout (см. ниже), а не отдельные страницы | Соглашения — это конфиг, а не пофайловые правки. |

> **Безопасность:** `wiki-index-render` и `wiki-reindex --full` перезаписывают
> генерируемый markdown (`index.md`, реестры). Сначала закоммитьте в git.
> Авторские *страницы* этими командами никогда не перезаписываются — только
> проекции.

### Регистрация готового саммари (не raw)

Очень частый случай: **у вас уже есть готовая статья/саммари** — созданная другим
инструментом, написанная вручную, экспортированная откуда-то — и вы хотите её в
vault как страницу-источник, чтобы позже извлечь из неё концепты. Вы **не** хотите
прогонять её через raw-пайплайн LLM-саммаризации (это уже саммари).

**Какой on-ramp использовать?** Это самая частая путаница, так что решите её явно:

```mermaid
flowchart TD
    Q{"What do you have?"}
    Q -->|"raw material<br/>(transcript, article, notes)<br/>— needs summarising"| ENR["wiki-enrich --source &lt;file&gt;<br/>= wiki-ingest LLM-summarises → _sources/ → index"]
    Q -->|"a FINISHED summary<br/>(already distilled elsewhere)"| REG["1. place it at _sources/&lt;slug&gt;.md (with frontmatter)<br/>2. wiki-index-upsert --source &lt;abs path&gt;<br/>= indexed verbatim, NO LLM, NOT raw"]
    ENR --> IDX["source page is now indexed (type=summary)"]
    REG --> IDX
    IDX -->|"optional: densify"| EXT["wiki-extract-concepts prepare/apply<br/>--source-page &lt;slug&gt;<br/>→ concept/entity pages"]
    classDef raw fill:#fdeede,stroke:#e0a050;
    classDef premade fill:#eef7ee,stroke:#5a5;
    class ENR raw;
    class REG premade;
```

`wiki-enrich` — **только** для raw-материала — он всегда вызывает `wiki-ingest`,
чтобы *саммаризировать*. Для готового саммари полностью пропустите его и
зарегистрируйте страницу напрямую. Полный рецепт:

**Шаг 1 — Поместите саммари в `_sources/` с валидным frontmatter.** Layout
karpathy *требует* `type:` (он не синтезирует его), и странице нужен `title`.
Минимальный frontmatter страницы-источника:

```markdown
---
type: summary            # → pages.type=summary (also: lesson-summary, meeting-summary, summary-light)
title: "My Article Title"
date: 2026-06-02         # optional; real-world sources may be undated
tags: [imported, crypto] # optional; powers wiki-search --where
---

# My Article Title

…the summary prose. Any [[wiki-links]] in the body become reference edges
(orphan links until the target pages exist — wiki-extract-concepts can create them).
```

(Для layout `dev-project` / кастомного `type:` может быть выведен из пути или
синтезирован — см. [Кастомные layout'ы](#custom-layouts-the-layout-engine) — но в
`_sources/` под karpathy frontmatter `type:` обязателен, иначе upsert выбросит
`UnmappedTypeError`.)

**Шаг 2 — Проиндексируйте её (без LLM, без raw-шага):**

```bash
wiki-index-upsert --vault my-vault --source /abs/path/to/MyVault/_sources/my-article.md
# idempotent: re-running on unchanged content is a no-op (file-hash match)
```

Страница теперь полноценный источник `type=summary`, сразу доступный для поиска
через FTS.

**Шаг 3 (опционально) — Извлеките из неё концепты.** Поскольку источник теперь
проиндексирован, `wiki-extract-concepts` работает с ним ровно так же, как со
страницей, прошедшей raw-ingest — ему всё равно, как страница попала сюда:

```bash
wiki-extract-concepts prepare --vault my-vault --vault-root /abs/path/to/MyVault \
    --source-page my-article
# → orchestrator synthesises candidate concepts JSON (concept-extraction contract)
wiki-extract-concepts apply   --vault my-vault --vault-root /abs/path/to/MyVault \
    --source-page my-article --source-hash <hash from prepare> \
    --candidates-stdin --ingest < candidates.json
```

Внутри сессии Claude Code просто скажите *«зарегистрируй саммари по `<path>` в
`my-vault` (не саммаризируй заново), затем извлеки из него концепты»* — агент
выполнит upsert и проведёт двухпроходный поток `wiki-extract-concepts`.

> **Почему не просто навести `wiki-enrich` на него?** `wiki-enrich` передаст ваше
> саммари в `wiki-ingest` как *raw-вход* и произведёт **саммари-вашего-саммари** —
> дважды дистиллированное, с новыми slug'ами. Прямая регистрация сохраняет ваш
> текст дословным и каноническим. Используйте `wiki-enrich` только тогда, когда
> LLM *должна* выполнить дистилляцию.

### Кастомные layout'ы: движок layout

Не каждый vault имеет форму Karpathy. Дерево `docs/` программного репозитория,
личный Obsidian-vault с нумерованными папками и Unicode-заголовками — им нужна
другая грамматика «где живут страницы / какого они типа». Начиная с TASK 012 эта
грамматика — **YAML-конфиг, а не код** (`scripts/wiki_index/layout_config.py`,
схема `config/layout-config.schema.yaml`).

Четыре layout-*грамматики* поставляются встроенными (`scripts/wiki_index/layouts/`),
доступные как шесть значений `--layout` (`flat`/`per-project` — алиасы `karpathy`):

| Layout | Форма | Стратегия slug |
|---|---|---|
| `karpathy` | Стандартный layout выше. **Байт-в-байт идентичен** легаси-захардкоженному поведению (защищён golden-anchor). Алиасы: `flat`, `per-project`. | `identity` (дословный stem) |
| `dev-project` | `docs/` репозитория — `tasks/*.md`, `adr/*.md`, `issues/*.md` и т. д. | `transliterate` (ASCII-безопасный) |
| `obsidian-personal` | Нумерованные папки + Unicode | `preserve-unicode` |
| `cybos` | **Vault типизированных знаний / «операционной памяти»** (TASK 031/034): `decisions/ requirements/ risks/ incidents/ hypotheses/ facts/ events/` + инженерный костяк `tasks/ adr/ plans/` + классы агентной памяти TASK-034 `agents/ tools/ workflows/ capabilities/ executions/ patterns/`. Дом для типизированных классов знаний И модели агентной памяти. | `transliterate` |

Выберите один при init: `wiki-init --scaffold-new --vault <path> --layout dev-project`.

**Создание кастомного layout.** YAML layout'а отображает файлы → `(type, project)`,
отображает эти raw-типы на enum `pages.type` в БД и объявляет, как извлекаются
перекрёстные ссылки. Вот эта форма, с пояснениями (настоящий `dev-project.yaml` —
лучший проработанный пример):

```yaml
schema_version: '2.0'
layout: my-layout
slug_strategy: transliterate          # identity | preserve-unicode | transliterate | ascii-only
ignore: [".git/**", "**/.DS_Store"]   # globs never indexed
file_extensions: ['.md']

# Globs evaluated in order, first-match-wins (relative to vault_root):
paths:
  - {glob: "tasks/*.md", type: task, project: "_vault_"}
  - {glob: "adr/*.md",   type: adr,  project: "_vault_"}
  # project can also be DERIVED from the path via a (guarded) regex:
  - {glob: "Lessons/*/*.md", type: lesson,
     project_pattern: "Lessons/(?P<name>[^/]+)/", project_template: "${name}",
     project_slug_strategy: course-slug}

# Route your raw types onto the live pages.type CHECK enum + a filterable tag.
# This is how NEW doc types get indexed with ZERO schema change (no DDL):
type_mapping:
  task: {db_type: brief,    tag: task}
  adr:  {db_type: research, tag: adr}

path_type_fallback: {}                # raw_type when neither paths[].type nor frontmatter set it

# How to pull [[links]] / [md](links.md) / ID-refs out of a page body:
ref_extraction:
  - {kind: wiki-link, regex: '\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', target_group: 1}
  - {kind: id-ref,    regex: '\b(ADR-\d+|task-\d+)\b',         target_group: 1}

# Synthesise a title for docs that lack frontmatter (e.g. a bare ROADMAP.md):
frontmatter_synthesis: {enabled: true, title_source: first_h1, fallback_title: filename_stem}

# Render a rebuildable-markdown ledger from a set of source pages:
auto_indexes:
  - {source_type: known-issue, output: KNOWN_ISSUES.md, group_by: category,
     sort_within_group: [severity, opened_at, id]}
```

Переопределите для конкретного vault через `<vault>/.wiki/layout.yaml` или
указатель `layout_config:` во frontmatter `WIKI_SCHEMA.md`.

> **Семантика слияния override — острый край (TASK 025).** Override на уровне vault
> НЕ сливается однородно: скаляры накладываются; **`ignore` ОБЪЕДИНЯЕТ** встроенный
> список, а **`type_mapping` глубоко СЛИВАЕТСЯ (deep-MERGE)**; но **`paths` и
> `ref_extraction` ЗАМЕЩАЮТ** весь встроенный список в тот момент, когда вы задаёте
> ключ. Чтобы расширить/углубить `paths` (например, добавить правило project на
> уровне модуля к дереву курса), вы должны **дословно переобъявить `paths` базового
> layout плюс ваше новое правило** — голый override `paths:` с одним правилом молча
> отбрасывает всю встроенную маршрутизацию.

> **Кастомный frontmatter `type:` (TASK 025).** Заметка, чей `type:` отсутствует в
> `type_mapping` layout'а, выбрасывает `UnmappedTypeError` и пропускается при
> reindex (`skip:unmappable-type` в `wiki-sync`). Если ваш vault несёт подтип,
> которого нет во встроенном, добавьте его под `type_mapping:` в
> `.wiki/layout.yaml` (он deep-merge поверх базового), например
> `tutorial-summary: {db_type: summary, tag: tutorial}`. Встроенный
> obsidian-personal заранее отображает распространённое семейство summary
> (`summary`/`lesson-`/`meeting-`/`webinar-`/`tutorial-`/`article-`/`book-`/`video-`/
> `podcast-`/`course-summary` + `moc`); всё остальное вы отображаете сами.

> **Типизированные классы знаний (TASK 031) + классы агентной памяти (TASK 034).** Семь
> классов знаний — `decision`, `requirement`, `risk`, `incident`, `hypothesis`, `fact`,
> `event` — плюс шесть классов агентной памяти TASK-034 — `agent`, `tool`, `workflow`,
> `capability`, `execution`, `pattern` — поставляются как zero-DDL `type_mapping` tag-route
> (на существующий enum `pages.type`). Они первоклассны в layout **`cybos`** (по папкам), а
> классы знаний доступны опционально в **`dev-project`** (через явный frontmatter `type:`).
> Чтобы внедрить их в любой другой vault (например `obsidian-personal`), добавьте блок в
> `.wiki/layout.yaml` — он ОБЪЕДИНЯЕТСЯ (UNION; проверено на реальном PARA-vault). Поиск по
> классу — фильтр членства в списке (`wiki-search --tag decision`, TASK 033). **Шаблоны**
> заметок — в `templates/page-types/*.md`; полная справка —
> [`docs/layouts/cybos.md`](../layouts/cybos.md). Типизированные *рёбра* между страницами —
> собственно граф событий (`wiki-graph`) — **поставлены** в TASK 032/034 (ADR-004, схема v7):
> задавайте `implements`/`supersedes`/`caused_by`/`invalidated_by`/`uses`/`owns`/… во
> frontmatter в одном направлении, инверсия выводится автоматически. Запрос «что было активно
> на дату X» — это без-LLM `wiki-search --as-of` (TASK 034).

Три факта дизайна, которые стоит усвоить:

- **Две отдельные системы конфигурации.** *Identity* на уровне vault
  (`config_loader.py` / `wiki-config.schema.yaml` — кто этот vault, его `vault_id`)
  намеренно отделена от *грамматики* на уровне класса layout (движок выше — как
  устроен этот *вид* vault). Не смешивайте их.
- **Layout'ы самоописательны — новый встроенный layout это чистый drop-in YAML (TASK 031).**
  Набор значений `--layout`, карта легаси-алиасов и семейство two-tier-scaffold нигде не
  захардкожены: каждый `layouts/*.yaml` объявляет свои опциональные ключи `aliases:` и
  `init_scaffold:` (`two-tier` | `none`), а реестр (`layout_config.layout_choices` /
  `resolve_alias` / `is_two_tier_scaffold`) выводит всё, глоббя эту папку. Положили новый
  `layouts/<name>.yaml` → `--layout <name>` сразу валиден, **ноль правок Python**.
- **Операторские regex защищены от ReDoS.** Кастомные `ref_extraction[].regex` и
  `paths[].project_pattern` проверяются *во время загрузки* (бюджетный гейт на
  stdlib-`re`; ошибочно написанный ключ грамматики — это жёсткая ошибка загрузки,
  exit 6, а не молчаливый поток) и *во время выполнения* (пофайловый дедлайн через
  движок PyPI `regex` с `timeout=`, переопределяемый через окружение
  `WIKI_REDOS_BUDGET_S`, по умолчанию 2.0 с — по таймауту файл пропускается с WARN,
  никогда не зависает). Встроенные layout'ы используют stdlib `re` и не несут
  никаких накладных расходов (TASK 012 + 017).

### Справочник: типы страниц и типы связей (модель знаний)

Ценность wiki — в *типизации* того, ЧЕМ является заметка и КАК заметки СВЯЗАНЫ. **Тип**
заметки маршрутизирует её в бакет `pages.type` + фильтруемый `tag` (так что
`wiki-search --tag <type>` выводит все заметки этого вида); её **связи** — это типизированные
рёбра между страницами в event-графе, которые обходит `wiki-graph` и читает
`wiki-search --as-of`. Тип и рёбра вы задаёте во frontmatter — ниже меню и назначение каждого
пункта.

#### Типы страниц — для чего каждый

**Классы знаний (TASK 031 — слой «что произошло / что мы знаем»):**

| `type:` | Назначение — когда использовать | бакет `pages.type` |
|---|---|---|
| `decision` | Принятое решение с обоснованием («выбрали X, потому что Y»). | research |
| `requirement` | То, что система ОБЯЗАНА делать — спека / критерий приёмки. | brief |
| `risk` | То, что *может* пойти не так (pre-mortem / открытая угроза). | research |
| `incident` | То, что *пошло* не так — сбой / постмортем. | research |
| `hypothesis` | Непроверенное предположение, которое намерены проверить. | research |
| `fact` | Атомарное проверяемое утверждение. | concept |
| `event` | Событие с датой — встреча, релиз, веха. | summary |

**Инженерный костяк (общий с layout `dev-project`):**

| `type:` | Назначение | `pages.type` |
|---|---|---|
| `task` | Единица работы и её спека. | brief |
| `adr` | Architecture Decision Record. | research |
| `plan` | План реализации. | brief |

**Классы агентной памяти (TASK 034 — слой «кто действует / что выполняется»; моделируют саму агентную систему):**

| `type:` | Назначение | `pages.type` |
|---|---|---|
| `agent` | Автономный актор — LLM-агент или человеческая роль. | concept |
| `tool` | Вызываемая поверхность возможностей — CLI / API, который вызывает агент. | concept |
| `workflow` | Процедура / конечный автомат (`draft`→`active`→`deprecated`→`superseded`). | brief |
| `capability` | Атомарный навык, который умеет агент (напр. OCR, суммаризация). | concept |
| `execution` | Запись одного запуска с датой (`status: success/failed/partial`) — операционная память. | summary |
| `pattern` | Консолидированный вывод *второго порядка* («большинство инцидентов — из-за пропущенных требований»). | research |

**Базовые типы контента (доступны всегда):** `note` (обычная заметка), `summary` (нарратив с
датой — напр. саммари встречи/урока), `concept` (атомарная дефиниция), плюс специфика layout —
`daily-note`, `clipping`, `moc` (map-of-content). Два системных типа, которые не пишут руками:
`query` (накапливаемый цитируемый RAG-ответ, который пишет `wiki-query`) и `verification`
(страница-вердикт `wiki-verify-multi`).

> Типы маршрутизируются `type_mapping` layout'а, поэтому *один и тот же* сырой `type:`
> попадает в нужный бакет CHECK-enum `pages.type` **без изменения схемы**. `--types <bucket>` —
> грубый фильтр; `--tag <class>` (точное совпадение по члену списка для класса) — то, что нужно
> обычно. **Шаблоны** заметок для каждого класса лежат в `templates/page-types/*.md` в репозитории;
> `wiki-init` **копирует все 13 в `<vault>/.wiki/page-types/`** для existing-tree layout'ов
> (`cybos`/`dev-project`/`obsidian-personal`), чтобы агент или человек, работающий В vault, имел
> их локально (под `.wiki/` — поэтому они никогда не индексируются).

#### Типы связей — для чего каждое ребро

Рёбра — это **типизированные связи между страницами**, заданные во frontmatter на ИСХОДНОЙ
странице (значение = `[[wikilink]]` / slug, скаляр или список). Вы задаёте **одно**
направление; **инверсия выводится автоматически** на целевой странице при reindex, так что граф
навигируем в обе стороны без двойного учёта. Обход: `wiki-graph backlinks/neighbors/chain
--kind <edge>`.

| Ключ во frontmatter | Смысл (источник → цель) | Авто-инверсия | Пример |
|---|---|---|---|
| `implements` | источник реализует / удовлетворяет цель | `implemented-by` | `decision` *implements* `requirement` |
| `supersedes` | источник заменяет цель | `superseded-by` | `decision v2` *supersedes* `v1` |
| `superseded_by` | источник заменён целью (другой конец) | `supersedes` | `v1` *superseded_by* `v2` |
| `causes` | источник вызывает цель | `caused-by` | `decision` *causes* `incident` |
| `caused_by` | источник вызван целью | `causes` | `incident` *caused_by* `decision` |
| `invalidated_by` | цель аннулирует / обнуляет источник (TASK 034) | `invalidates` | `decision` *invalidated_by* `incident` |
| `activated_by` | цель включает источник / вводит его в действие (TASK 034) | `activates` | `decision` *activated_by* событие раскатки |
| `uses` | источник (`agent`/`workflow`) вызывает целевой tool/capability (TASK 034) | `used-by` | `agent` *uses* `tool` |
| `owns` | источник (`agent`) владеет / управляет целевым workflow (TASK 034) | `owned-by` | `agent` *owns* `workflow` |
| `relates_to` | симметричная ненаправленная связь | `related` (симметрично) | `fact` *relates_to* `decision` |

> **Два ребра питают временно́й запрос.** `wiki-search --as-of <date>` считает страницу
> переставшей быть активной, как только прошла дата её ближайшего преемника по
> **`superseded-by`** *или* **`invalidated-by`** — поэтому эти два ребра (плюс собственная
> `date` страницы или необязательный override `valid_to`) отвечают на «что было активно на дату
> X» без LLM. `activated_by` **не** снимает страницу с активности (он лишь фиксирует, что её
> включило); *начало* активности задаётся датой создания `date` / `valid_from`.
>
> **Системные ref-типы, которые не пишут руками** (выводятся автоматически, для полноты):
> `mentioned` (обычный `[[wikilink]]` в теле), `cited` (страница `query` → процитированный
> источник), `verifies` (страница `verification` → проверенный ею запрос), `defined-here`. Во
> frontmatter задаются только типизированные рёбра из таблицы выше.

#### Примеры — как создавать страницы (и что это открывает)

Страница — это просто markdown-файл: `type:` и ключи-рёбра идут во frontmatter, содержимое —
в тело. В vault **`cybos`** каждый тип лежит в своей папке (`decisions/`, `requirements/`, …),
так что `type:` можно даже опустить; в **`obsidian-personal`** / **`dev-project`** добавьте
блок `type_mapping` (выше) — и явный `type:` работает где угодно. Значения рёбер — это
`[[wikilinks]]` (или голые slug), скаляр или список — **задаёте одно направление, инверсия
выводится автоматически.**

Небольшой связный сценарий (повторяет поставленный `08 - CybOS Demo`):

```markdown
# requirements/throughput.md
---
type: requirement
title: Пропускная способность ≥ 10k/с
date: 2026-01-10
---
Брокер должен держать 10 000 сообщений/с на пике.
```
```markdown
# decisions/use-rabbitmq.md
---
type: decision
title: Использовать RabbitMQ для асинхронных сообщений
status: superseded            # proposed | accepted | superseded | rejected
date: 2026-02-01              # ← задаёт --as-of (когда решение вступило в силу)
implements: [[throughput]]    # → удовлетворяет требование   (инверсия: implemented-by)
causes: [[queue-overflow]]    # → привело к инциденту         (инверсия: caused-by)
superseded_by: [[switch-to-kafka]]  # → позже заменено        (инверсия: supersedes)
---
Выбран за операционную простоту.
```
```markdown
# decisions/switch-to-kafka.md
---
type: decision
title: Перейти на брокер Kafka
status: accepted
date: 2026-05-01
implements: [[throughput]]
supersedes: [[use-rabbitmq]]  # родословная вытеснения
---
Партиционированный лог масштабируется за потолок одного брокера RabbitMQ.
```
```markdown
# incidents/queue-overflow.md
---
type: incident
title: Сбой из-за переполнения очереди
status: resolved
date: 2026-03-15
caused_by: [[use-rabbitmq]]
---
Неограниченный рост очереди при всплеске нагрузки.
```

Поддерживающие классы так же коротки — `risk` (`relates_to: [[use-rabbitmq]]`),
`hypothesis` (`relates_to: [[queue-overflow]]`), `fact` (отдельное утверждение),
`event` (`type: event`, `date: 2026-05-01`, `relates_to: [[switch-to-kafka]]`).

И сторона агентной памяти — моделируем саму систему:

```markdown
# agents/claude-code.md
---
type: agent
title: Claude Code
status: active
uses: [[wiki-query]]          # → инструмент, который он вызывает (инверсия: used-by)
owns: [[ingest-pipeline]]     # → workflow, которым он управляет   (инверсия: owned-by)
implements: [[ocr]]           # → возможность, которую он даёт     (инверсия: implemented-by)
---
Агент-оркестратор.
```

с `tool` (`# tools/wiki-query.md`), `workflow` (`# workflows/ingest-pipeline.md`,
`status: active`, при желании `supersedes:` прошлую версию), `capability`
(`# capabilities/ocr.md`), `execution` (`# executions/run-2026-06-16.md`, `type: execution`,
`status: failed`, `date: 2026-06-16`, `relates_to: [[ingest-pipeline]]`) и `pattern`
(`# patterns/missing-reqs.md`, `relates_to: [[queue-overflow]]`).

**Что эти страницы теперь открывают — без LLM:**

```bash
wiki-search --tag decision --vaults V                # все решения (совпадение по члену tags[])
wiki-search --tag decision --as-of 2026-04-01 --vaults V   # → use-rabbitmq (активно тогда; kafka — 05-01)
wiki-search --tag decision --as-of 2026-06-01 --vaults V   # → switch-to-kafka (rabbitmq вытеснено 05-01)
wiki-graph chain switch-to-kafka --kind supersedes --vault V   # родословная → use-rabbitmq
wiki-graph backlinks throughput --kind implements --vault V    # что реализует требование → оба решения
wiki-graph backlinks ocr        --kind implements --vault V    # какие агенты умеют OCR → claude-code
wiki-graph neighbors use-rabbitmq --direction out --vault V    # все его исходящие рёбра
wiki-search --tag execution --status failed --vaults V         # упавшие запуски (операционная память)
wiki-query prepare "почему ушли от RabbitMQ?" --vault-root V --follow-edges  # цитируемый RAG, расширенный графом
```

### Смешанный vault: области только для поиска + course-зоны, доступные для enrich

Большинство реальных личных vault'ов *смешанные*: основная масса — это готовые
заметки, которые вы хотите только **искать**, но несколько подпапок — это
**зоны-коллекторы**: вы кладёте туда транскрипты / raw-материал и хотите, чтобы
система `enrich`'ила их в накапливающуюся wiki (например, `Webinars/` или папка на
курс под `03 - Learning/`).

**Почему здесь нужны два vault'а, а не один layout.** `wiki-enrich` всегда
производит виды страниц karpathy (`_sources/_concepts/_entities/`) — эти имена
папок фиксированы вендоренным `wiki-ingest`, не настраиваемы — а личный layout
(`obsidian-personal`) их не индексирует. Так что один layout не может обслуживать
обе половины. Чистая модель — это **два зарегистрированных vault'а, разделяющих
одну глобальную БД** (ровно для этого и существует multi-vault-партиционирование);
поиск унифицируется через `--vaults a,b`.

```mermaid
flowchart TD
    OBS["your Obsidian vault (root)"] --> P["Vault P: personal<br/>layout = obsidian-personal<br/>SEARCH-ONLY"]
    OBS -->|"subtree: 03 - Learning/Courses/**"| L["Vault L: courses<br/>layout = karpathy<br/>ENRICH-able"]
    P -.->|"ignore: 03 - Learning/Courses/**"| X[" "]
    RAW["transcript / raw material"] -->|"wiki-enrich"| L
    SUMM["ready summary (your Summaries/)"] -->|"wiki-index-upsert (no LLM)"| L
    Q["wiki-search / wiki-query --vaults personal,courses"] --> DB[("one global.db")]
    P --> DB
    L --> DB
    style X fill:none,stroke:none
    classDef so fill:#eef7ee,stroke:#5a5;
    classDef en fill:#fdeede,stroke:#e0a050;
    class P so;
    class L en;
```

> **Управление запущенным приложением Obsidian (скилл `obsidian-cli`).** Смешанный
> vault — это всё ещё *живой* vault Obsidian. Скилл [`obsidian-cli`](../../skills/obsidian-cli/SKILL.md)
> (официальный CLI Obsidian 1.12+) позволяет агенту делать то, чего не умеет связка
> файлы+SQLite: **безопасное для ссылок** `rename`/`move` (приложение переписывает
> беклинки; обычный `mv` осиротил бы их), установку типизированных свойств,
> переключение задач, дозапись в дневную заметку, запрос к Base в JSON, восстановление
> из истории файла. Запросы знаний он маршрутизирует СНАЧАЛА в `wiki-search`/`wiki-query`,
> несёт 3-уровневую модель безопасности (чтение / мутация / запрещённые-по-умолчанию
> `eval`+`dev:*`), и после любой мутации через приложение обновляет индекс в том же ходу —
> `wiki-index-upsert` для правки содержимого, **`wiki-reindex --delta` для rename/move**
> (начиная с TASK 030 delta распознаёт rename: новый путь индексируется несмотря на
> сохранённый mtime; `--full` — универсальный фолбэк и средство от swap-класса).

**Правило границы (единственный инвариант, который должен держаться):** vault для
поиска должен `ignore`'ить зону enrich, а enrich-vault укоренён внутри этой зоны.
Тогда каждый файл индексируется ровно один раз — без двойного обхода, без
дублирующих строк.

```
<Obsidian root>/                       ← Vault P (obsidian-personal, search-only)
├── 02 - Personal Home/ · 05 - Материалы/ …   ← indexed by P
└── 03 - Learning/
    ├── Переговоры/ · Работа с людьми/ …       ← personal notes → indexed by P
    └── Courses/                                ← P IGNORES this subtree
        └── AI Hard Fork 2026/                  ← Vault L (karpathy) — its own vault
            ├── _raw/         ← raw drops (transcripts, zoom_chat)
            ├── _sources/     ← enrich writes summaries here (+ your ready notes → upsert)
            ├── _concepts/    ← enrich builds concept pages
            └── _entities/    ← …and entity pages
```

**Два способа сформировать зону enrich** (оба karpathy):
- **Vault-на-курс** — каждая папка курса — это свой `karpathy` vault_root с
  `_sources/_concepts/_entities/`. Простейшая ментальная модель; подходит для
  самодостаточной папки курса. Новый курс = новая папка + один
  `WIKI_SCHEMA.md (layout: karpathy)` + `wiki-init --register-existing`.
- **Один vault курсов + course-уровень** — много курсов в одном vault_id, каждый
  живёт под `Lessons/<Course>/_sources/…`; enrich маршрутизирует через
  `--ingest-arg=--course="AI Hard Fork 2026"`. Меньше настройки на курс, когда вы
  продолжаете добавлять курсы.

**Рецепт (сначала тестируйте на копии):**

```bash
cp -R "/path/to/RealVault" samples/mixed-test            # never iterate on the live vault

# --- Vault P: personal, search-only ---
#  <root>/WIKI_SCHEMA.md:   layout: obsidian-personal
#  <root>/.wiki/layout.yaml: copy obsidian-personal, add "03 - Learning/Courses/**" to ignore
wiki-init --register-existing --vault personal
wiki-reindex --full --vault personal
wiki-search "переговоры с поставщиком" --vaults personal

# --- Vault L: a course (karpathy), enrich-able ---
#  ".../Courses/AI Hard Fork 2026/WIKI_SCHEMA.md":  layout: karpathy
wiki-init --register-existing --vault ai-hard-fork-2026
wiki-enrich --vault ai-hard-fork-2026 \
    --vault-root "samples/mixed-test/03 - Learning/Courses/AI Hard Fork 2026" \
    --source     ".../zoom_chat_20260224.txt"            # raw → summary + concepts
wiki-index-upsert --vault ai-hard-fork-2026 \
    --source ".../Courses/AI Hard Fork 2026/_sources/<ready-summary>.md"   # ready note, no LLM

# --- Unified search / RAG across everything ---
wiki-search "scaling laws" --vaults personal,ai-hard-fork-2026
```

**Оговорки:**
- **Вложенные vault root'ы** (L внутри P) разрешены на уровне БД (`root_path`
  UNIQUE); пересечение убирается через `ignore` у P. Проверьте на копии перед
  живым vault.
- **enrich создаёт `_sources/_concepts/_entities/`** в папке курса — это ожидаемо
  (это управляемая системой зона). Уже дистиллированные заметки (ваш `Summaries/`)
  проходят через `wiki-index-upsert` (см. [готовое саммари](#registering-a-pre-made-summary-not-raw));
  через `wiki-enrich` идёт только новый raw.
- **HTML / office-источники**: `wiki-ingest` ожидает текст — сначала конвертируйте
  `.html` в `.txt`/`.md`.
- **Личный vault остаётся нетронутым** (только индексируется); enrich пишет
  исключительно в зону курса.

---

### Автоматизация смеси: `wiki-sync` (пофайловая маршрутизация, конвертация, OCR)

Рецепт с двумя vault выше делит работу *по папкам*. **`wiki-sync`** (TASK 018 /
R-11) идёт на уровень тоньше: наведите его на **зону**, и он классифицирует
**каждый файл** — по расширению, по пофайловому тегу `#wiki/*` и по форме контента
— затем маршрутизирует каждый в **convert / ingest / upsert / skip**. Брошенный в
папку курса транскрипт, `.docx` или даже *сканированный* PDF теперь «просто»
становится накапливающимися страницами wiki, без ручного вызова `wiki-enrich` /
`wiki-index-upsert` на каждый файл.

**Две фазы (Decision-17 — детерминированный план, исполнение во владении
orchestrator):**

- **`wiki-sync scan <zone> --vault <id>`** — *чистый Python.* Обход → классификация
  → `sha256` → `is_unchanged` → строгий **план JSON** (`entries[]` + `summary{}`).
  **Без LLM, без сети, без мутаций.** `--dry-run` печатает человеко-читаемый отчёт о
  каждом действии + причине. Это та часть, которую вы проверяете перед тем, как
  что-либо будет записано.
- **[`workflows/wiki-sync.md`](../../workflows/wiki-sync.md)** — *исполнитель*
  orchestrator. По каждой записи плана он конвертирует / убирает таймстемпы /
  **ставит H-6-fence** / саммаризирует / enrich'ит / извлекает / upsert'ит /
  пропускает, затем пишет пофайловый **commit-маркер** (`wiki-sync record`), так
  что повторный прогон становится no-op. (`/wiki-sync` управляет всем процессом.)

```mermaid
flowchart TD
    F["file in the zone"] --> EXT{"extension<br/>(case-folded)"}
    EXT -->|".docx .xlsx .pptx .pdf"| CONV["convert+ingest<br/>→ _raw/.staging/&lt;slug&gt;-&lt;ext&gt;.md<br/>(scanned PDF → OCR)"]
    EXT -->|".txt .vtt .srt"| ING["ingest<br/>(.vtt/.srt → de-timestamp first)"]
    EXT -->|"image · .canvas · .excalidraw · .base"| SKb["skip (binary / view-artifact)"]
    EXT -->|".md"| TAG{"#wiki tag /<br/>wiki: field?"}
    TAG -->|"skip"| SKt["skip: wiki/skip"]
    TAG -->|"raw  (or under _raw/)"| ING
    TAG -->|"none / keep"| VIEW{"generated-view<br/>sidecar?"}
    VIEW -->|"only-a-view block"| SKv["skip: view:dbfolder/base/dataview/folder-note"]
    VIEW -->|"embeds a view + real prose"| TYPE
    VIEW -->|"plain note"| TYPE{"type: mappable?<br/>(same layout resolution<br/>wiki-index-upsert uses)"}
    TYPE -->|"yes"| UP["upsert (no LLM)"]
    TYPE -->|"no"| SKu["skip: unmappable-type"]
    CONV --> ING
    ING --> REC["on full success →<br/>wiki-sync record (commit-marker)"]
    UP --> REC
    classDef act fill:#fdeede,stroke:#e0a050;
    classDef sk fill:#eef0f2,stroke:#99a;
    class CONV,ING,UP,REC act;
    class SKb,SKt,SKv,SKu sk;
```

**Маршрутизация по расширению** (с приведением регистра — `.PDF` == `.pdf`):

| Расширение | Действие |
|---|---|
| `.docx` `.xlsx` `.pptx` `.pdf` | **convert** → staged `_raw/.staging/<slug>-<ext>.md` (*необходаемая* директория) → **ingest** |
| `.txt` `.vtt` `.srt` | **ingest** (`.vtt`/`.srt` сначала очищаются от таймстемпов) |
| `.md` | правила по контенту (теги → view → type, ниже) |
| images · `.canvas` · `.excalidraw.md` · `.base` · неизвестное | **skip** (бинарник / view-артефакт / неизвестное расширение) |

**Маршрутизация по пофайловому тегу** (только `.md`) — приоритет
**`skip` > `raw` > `keep` > default**. Принимает как инлайн-тег `#<ns>/x` (вне
код-fence'ов), так и запись `tags:` во frontmatter, и поле `<ns>:` (`<ns>` =
`tag_namespace`, по умолчанию `wiki`):

| Тег / сигнал | Эффект |
|---|---|
| `#wiki/skip` (или `wiki: skip`) | никогда не индексировать эту заметку |
| `#wiki/raw` (или файл под `_raw/`) | трактовать как **raw** → полный ingest (саммаризация → концепты) |
| `#wiki/keep` | **спасти** `.md` из зоны `exclude:` (спасает только `keep` — не `raw`) |
| *(нет тега)* | **отображаемый `type:`** → `upsert`; иначе `skip: unmappable-type` |

**Sidecar'ы генерируемых view пропускаются** — это навигация, а не знание: DB
Folder (`database-plugin:` во frontmatter и/или блок ` ```yaml:dbfolder `), Bases
(` ```base `), Dataview (` ```dataview `/` ```dataviewjs `), folder-notes
(stem == dir). **Защита only-a-view** пропускает их *только* тогда, когда заметка
по сути — это один блок view; настоящая заметка, которая *встраивает* view рядом с
прозой, — это контент → `upsert` (без избыточной пометки).

**Сканированные PDF проходят OCR** (подключено 2026-06-03): `.pdf` без текстового
слоя (`pdf_extract.py` exit `10 DocumentScanned`) прогоняется через `pdf_ocr.py`
скилла `pdf` (`ocrmypdf`, языки по умолчанию **`eng+rus`**) → текст с возможностью
поиска → ingest. Если движок OCR не установлен
(`bash <pdf-skill>/scripts/install.sh --with-ocr` + системные
tesseract/ghostscript), файл помечается **`needs-ocr`** и пропускается — никогда
не отбрасывается молча.

**Конфиг** — `<vault>/.wiki/sync.yaml` (опционально): `zones`, `exclude`,
`tag_namespace` (по умолчанию `wiki`) и переопределения `extensions`. Строгая схема
(ошибочно написанный ключ — это ошибка загрузки); недоверенный файл ограничен по
размеру (256 KiB) + запрещены anchor'ы + отказ от symlink.

**Рецепт (сначала тестируйте на копии):**

```bash
# 1. PLAN — deterministic, writes nothing; review every action + reason
wiki-sync scan "courses/AI Hard Fork 2026" --vault ai-hard-fork-2026 --dry-run

# 2. EXECUTE the plan — the orchestrator recipe (convert/ingest/upsert/skip per file).
#    Invoke /wiki-sync, or follow workflows/wiki-sync.md step by step.

# 3. RE-RUN — every recorded file now reports is_unchanged (a no-op).
wiki-sync scan "courses/AI Hard Fork 2026" --vault ai-hard-fork-2026 --dry-run
```

**Политика повторной саммаризации — не саммаризируй заново то, что уже
саммаризировано** (TASK 019, opt-in). Добавьте блок `resummarize:` в
`.wiki/sync.yaml`, и `wiki-sync` направит raw-источник в **`skip`** вместо
`ingest`, когда для него уже существует саммари — так что повторный прогон scan по
курсу, который вы уже саммаризировали, не сжигает токены на переделку. «Саммари
существует» — это объединение трёх детекторов (от самого дешёвого): **`source_state`**
(именно этот raw синхронизировался ранее) ∪ **provenance** (frontmatter некоторого
саммари `source:`/`sources:` цитирует этот raw) ∪ **зеркало файловой системы** (sibling
`Summary/` разделяет ключ raw — `stem-relpath` 1:1, или `group_key`/`key` N:1, так
что много транскриптов сворачиваются в одно саммари урока). `--force` обходит гейт
(саммаризировать всё равно). Правила **переопределяемы на уровне папки** (более
глубокий `<folder>/.wiki/sync.yaml` deep-merge поверх корня vault — например, зона
`Lessons/`, ключуемая по дате вместо номера урока).

> **Режим сопоставления provenance (TASK 025) — `vault-rel-path` против
> `basename`.** `provenance_ref.match` детектора provenance выбирает, как
> цитируемый в саммари `file:` сопоставляется с raw. **`vault-rel-path`** (по
> умолчанию) — это точное равенство полного пути — строго, но ПРОПУСКАЕТ саммари,
> которое цитирует raw только по *basename*. **`basename`** берёт basename ОТ
> цитируемого значения И от цели raw, так что сопоставляет саммари, цитирующие по
> basename ИЛИ по полному пути — надёжный выбор, когда basename'ы источников
> глобально уникальны (например, транскрипты с YouTube-id `ID.ru.txt`) или
> существующий корпус уже цитирует по basename. Его единственный режим сбоя — два
> разных raw, разделяющих basename между папками. Выбирайте `basename` для
> корпусов транскриптов с id-именами; `vault-rel-path` — когда вы контролируете
> writeback и хотите строгого равенства путей. (По умолчанию намеренно
> `vault-rel-path` — его переключение могло бы слить разные raw с одинаковым
> basename.)

> **Новый raw под уже саммаризированным ключом → merge или split?** (TASK 021) Если
> вы кладёте *новый* транскрипт, чей ключ уже имеет саммари, которое его не
> цитирует, `wiki-sync` продолжает его пропускать (ваше намерение «группа
> саммаризирована → готово»), но логирует **merge/split WARN**. Разрешите это явно:
> **MERGE** → `wiki-sync scan <zone> --force` перегенерирует саммари из всех raw,
> разделяющих ключ, и запишет их в `sources:`; **SPLIT** → дайте новому raw
> отдельный ключ (более тонкий `group_key` / собственный scope) или напишите второе
> саммари, цитирующее его; **SUPERSEDE** → заархивируйте старый raw, затем
> `--force`. `sources:` — это авторитетная запись; ключ — это лишь группировка по
> умолчанию. См. `workflows/wiki-sync.md` Шаг 6.

**Идемпотентность и безопасность:** исполнитель пишет commit-маркер `source_state`
на файл **только при полном успехе** — частичный сбой не записывает ничего, так что
файл переплинируется на следующем прогоне (никакое полуготовое состояние не
выживает). План **детерминирован** (записи отсортированы по пути, без таймстемпа →
два scan'а байт-в-байт идентичны). Пофайловая изоляция: один плохой файл
(`needs-ocr` / неконвертируемый / oversize) помечается и пропускается, никогда не
обрушивая весь батч. **Zero DDL** — идемпотентность едет на партиции
`source_state` поверх существующей схемы.

> **`wiki-sync` против разделения на два vault:** они компонуются. Используйте
> границу `ignore` с двумя vault, чтобы держать области только-для-поиска вне
> машинерии enrich; используйте `wiki-sync` *внутри* зоны enrich, чтобы
> маршрутизировать её разнородные дропы пофайлово. См. `skills/wiki-sync/SKILL.md`
> для полного контракта план-JSON + кодов выхода.

---
## Использование wiki как внешнего ресурса для других агентов

Второй агент — другая сессия Claude Code, cron-задача, шаг CI, любой
orchestrator — может рассматривать wiki как **backend знаний**. Контракт
намеренно прост и удобен для машинной обработки.

### Модель интеграции: JSON-конверты + коды выхода

Каждый CLI следует одной и той же форме:

- **Входные данные** через аргументы и/или stdin (крупные полезные нагрузки — тело
  ответа, массив цитирований — передаются через stdin или временный файл внутри
  корня vault).
- **Выходные данные** — это ровно **одна строка JSON в stdout** (`ensure_ascii=False`),
  *конверт*. Конверты успеха несут поля результата; конверты сбоя несут ключ
  `"error"` со стабильным машиночитаемым кодом.
- **Код выхода** сигнализирует результат для управления потоком на основе `$?`.
  Соглашения:

| Код выхода | Значение |
|---|---|
| `0` | Успех. |
| `2` | Ошибка pipeline/предусловия (например, `wiki-query` `NO_CONTEXT`, `QUESTION_CHANGED`). |
| `4` | Нарушение контракта в переданном содержимом (например, `CITATION_NOT_RETRIEVED`, `ANSWER_TOO_LARGE`). |
| `6` | Ошибка валидации/поиска — *или* записанный отрицательный вердикт (`wiki-verify-multi` FAIL). |
| `7` | Предупреждение о необходимости интерактивного подтверждения. |

Каждый `SKILL.md` точно документирует свои собственные коды — рассматривайте
таблицу выше как общий хребет, а не гарантию того, что каждый код встречается в
каждом инструменте. Золотое правило для интегрирующего агента: **сначала
ветвитесь по коду выхода, затем читайте поле `error` конверта — никогда не
выскребайте человеческую прозу.**

Минимальный цикл внешнего агента:

```bash
out=$(wiki-search "vault bottleneck" --vaults my-vault) || { echo "search failed: $out"; exit 1; }
top_slug=$(printf '%s' "$out" | jq -r '.hits[0].slug')   # structured, not regex-on-prose
```

### Контракт `prepare` / `apply` (Decision-17)

Три skill выполняют работу LLM-формы, но содержат **ноль импортов `anthropic`**:
`wiki-query`, `wiki-verify-multi`, `wiki-extract-concepts`. Python — это
детерминированная обвязка; шаг LLM принадлежит *вызывающему агенту*, зажат
между двумя вызовами CLI. Именно это делает wiki компонуемым *любым* агентом —
агент поставляет рассуждение; CLI поставляет retrieval, валидацию и долговечную
запись.

```mermaid
flowchart LR
    Q["question"] --> P["wiki-query prepare<br/>deterministic retrieval"]
    P -->|"envelope: hits[] + question_hash"| A["agent reasoning<br/>wiki-query-synthesis contract:<br/>cited answer + citations JSON"]
    A --> AP["wiki-query apply<br/>strict validators"]
    AP -->|"files"| PG["_queries/&lt;slug&gt;.md<br/>indexed · FTS · cited backlinks"]
    classDef det fill:#e8f0ff,stroke:#5577cc;
    classDef llm fill:#ffe9cc,stroke:#e08a00;
    class P,AP det;
    class A llm;
```

Детерминированный CLI владеет retrieval + валидацией + записью; агент владеет
только рассуждением посередине. Рецепт `wiki-query` на практике (остальные имеют
ту же форму — см. [`workflows/`](../../workflows/)):

```mermaid
sequenceDiagram
    autonumber
    participant Op as Operator / agent
    participant CLI as wiki-query CLI — deterministic
    participant LLM as Orchestrator — LLM
    participant Vault as Vault + index

    Op->>CLI: prepare "question" --vault … [scope]
    CLI->>Vault: retrieve (FTS5 BM25 + alias expansion)
    Vault-->>CLI: hits[]
    CLI-->>Op: envelope {query_slug, question_hash, is_unchanged, hits[]}
    Note over Op,LLM: exit 2 NO_CONTEXT → STOP (no outside-vault synthesis)<br/>is_unchanged → STOP (already filed)
    Op->>LLM: synthesise per wiki-query-synthesis (cite ONLY hits)
    LLM-->>Op: answer.md + citations JSON
    Op->>CLI: apply --question-hash [verbatim] --answer-stdin --citations-file … [same scope]
    CLI->>Vault: re-retrieve, recompute hash, validate citations ⊆ hits
    Note over CLI: hash mismatch → exit 2 QUESTION_CHANGED<br/>citation ∉ hits → exit 4 CITATION_NOT_RETRIEVED
    CLI->>Vault: file the _queries page (indexed, cited backlinks)
    CLI-->>Op: envelope {query_slug, cites, page_indexed}
```

Шаг за шагом:

1. **`wiki-query prepare "<question>" --vault <vid> --vault-root <path> [scope…]`**
   → конверт с `query_slug`, `question_hash`, `is_unchanged`, `hits[]`.
   - Exit 2 `NO_CONTEXT` → у vault нет основания. **Остановитесь; не синтезируйте
     извне vault** (защита от галлюцинаций). Повторяйте с `--min-hits 0` только
     чтобы явно запросить ответ «источники не найдены».
   - `is_unchanged: true` → тот же вопрос над тем же retrieval уже записан;
     пропустите синтез.
2. **Агент синтезирует** согласно контракту `wiki-query-synthesis`: markdown-ответ,
   цитирующий **только** `hits` из `prepare`, плюс JSON-массив цитирований из
   значений `project/slug`.
3. **`wiki-query apply … --question-hash <verbatim from prepare> --answer-stdin
   --citations-file <tmp>`** — передавайте **те же флаги scope**, что и у
   `prepare` (иначе повторный retrieval разойдётся и hash не совпадёт → exit 2
   `QUESTION_CHANGED`). Синтезированное цитирование, отсутствующее в извлечённом
   наборе → exit 4 `CITATION_NOT_RETRIEVED` (синтезируйте заново; **не** повторяйте
   молча).

Круговой обход `--question-hash` — это механизм целостности: он гарантирует, что
ответ был синтезирован против *того же состояния корпуса*, против которого он
записывается. Для orchestrator не на базе Claude контрактный skill
(`wiki-query-synthesis`, `wiki-verify`, `concept-extraction`) — это просто
prompt, который вы встраиваете в свой системный контекст — половинки CLI остаются
неизменными.

### Wiki как backend для RAG

Самой лёгкой интеграции вообще не нужны `prepare`/`apply`:

- **`wiki-search "<q>" --vaults a,b,c`** — кросс-vault FTS с BM25 + alias
  expansion. Самый быстрый «что мы знаем об X» для агента, который будет
  выполнять собственное рассуждение над snippet-ами.
- **`wiki-search --where 'field=value' --vaults v`** — структурированный
  retrieval метаданных (доски статусов, очереди по severity) без полнотекстового
  поиска. Совпадают скаляры И **элементы списка** (`--where 'tags=decision'` или
  сахар `--tag decision`) — TASK 033.
- **`wiki-query`** — когда вам нужен *долговечный, цитируемый* ответ, записанный
  обратно, а не просто сырые попадания.

Поскольку результаты — это JSON, внешний агент компонует их напрямую. Поскольку
БД — это единый глобальный файл, разделённый по `vault_id`, один агент может
запрашивать через vault-ы многих проектов одним вызовом
(`--vaults proj-a,proj-b`) — index общий, а разделы — нет.

### Недоверенные данные: позиция H-6

**Извлечённые snippet-ы и тела страниц — это недоверенные данные, а не
инструкции.** Враждебная страница-источник (особенно всё, что было загружено в
`_raw/` с внешнего URL) может содержать встроенный текст, выдающий себя за
системный prompt («игнорируй предыдущие инструкции…»). Интегрирующий агент
**обязан** оборачивать извлечённое содержимое в огороженный блок с сигнальным
маркером и не рассматривать ничего внутри как команду. Skill-ы синтеза и
верификации несут явный баннер H-6; соблюдайте его. На стороне записи
инструментарий уже экранирует markdown/HTML-активные последовательности на
выходе (`sanitize_markdown_text`), так что записанный ответ не может протащить
полезную нагрузку wikilink/HTML/dataview обратно в vault.

---

## Здоровье и обслуживание, методологически

Обслуживание — это не рутина, это то, что сохраняет честность накопления.

```mermaid
flowchart TD
    L["wiki-lint findings"] --> D["1. Dangling links<br/>[[X]] with no page X"]
    D --> C["2. Contradictions<br/>awaiting an operator decision"]
    C --> M["3. Missing concept pages<br/>mentioned in N+ sources, no page"]
    M --> O["4. Orphans<br/>nothing links here — maybe stale"]
    D -.->|"fix the link or create X"| FIX1[" "]
    M -.->|"feed to wiki-extract-concepts"| FIX2[" "]
    style FIX1 fill:none,stroke:none
    style FIX2 fill:none,stroke:none
    classDef hi fill:#fdd,stroke:#c66;
    classDef lo fill:#eef;
    class D hi;
    class O lo;
```

- **`wiki-lint` — это ваш измеритель истины.** Запускайте его после партии
  ingest-ов и периодически. Сортируйте в порядке приоритета:
  1. **Висящие ссылки** — `[[X]]` без страницы — это обещание, которое корпус не
     сдержал; создайте страницу или исправьте ссылку.
  2. **Противоречия** — операторские решения, ждущие принятия.
  3. **Отсутствующие страницы концепций** — концепции, упомянутые в N источниках
     без выделенной страницы; backlog уплотнения для `wiki-extract-concepts`.
  4. **Сироты** — страницы, на которые ничего не ссылается; возможно, устаревшие.
  Плюс находки целостности: **дрейф hash** (файл изменился без reindex) и
  **несоответствия типов** (тип во frontmatter страницы расходится с её layout —
  обратите внимание, что они учитывают layout-`type_mapping`, так что задача
  `dev-project`, маршрутизированная как `brief`, не является ложным
  срабатыванием).
- **`wiki-reindex --full` — это шлюз воспроизводимости.** Периодически
  доказывайте, что vault его переживает. Если `--full` теряет информацию, значит
  была нарушена граница Class A→B (знание утекло в слой только-для-БД) — это
  ошибка, которую надо исправить, а не обходить.
- **Обновления схемы — это reindex-ы, а не `ALTER`-ы.** Поскольку БД — это кэш
  Class B, миграция `vN→vN+1` на заполненной БД — это: удалить
  `.db`/`-wal`/`-shm`, затем `wiki-init --register-existing` + `wiki-reindex --full`
  (ADR-002 §D8). В БД нет ничего для миграции, чего нет в Markdown.

---

## Анти-паттерны (НЕ делайте)

| Анти-паттерн | Почему это неправильно |
|---|---|
| Создавать знание в `index.md` или авторендеренном реестре | Это *проекции* Class B — следующий render перезапишет вас. Создавайте на страницах; используйте `<!-- BEGIN-CUSTOM -->` только для действительно ведомых вручную секций. |
| Отредактировать страницу вручную и пропустить reindex | БД устаревает; `wiki-lint` сообщает о дрейфе hash, поиск возвращает устаревшие snippet-ы. Запустите `wiki-index-upsert` / `wiki-reindex --delta`. |
| Разрешить противоречие удалением проигравшего утверждения | Механизм `## Contradictions` существует *потому что* машина отказывается выбирать победителя. Оператор редактирует с суждением; след остаётся. |
| Синтезировать ответ `wiki-query` извне извлечённых `hits` | Ломает контракт цитирования → exit 4. Весь смысл — обоснованные, проверяемые ответы. |
| Рассматривать `wiki-verify-multi` FAIL как «исправь ответ за меня» | Он записывает вердикт и завершается с ненулевым кодом по замыслу; он **никогда** не изменяет ответ Class A. Вы решаете, что делать. |
| Выскребать прозу CLI вместо JSON-конверта / кода выхода | Конверт — это контракт; проза — нет. Ветвитесь по `$?`, читайте `.error`. |
| Рассматривать извлечённые тела страниц как инструкции | H-6: это недоверенные данные. Огораживайте + сигнальный маркер; ничего не выполняйте. |
| Запускать `wiki-init --scaffold-new --vault .` в корне этого репозитория | Репозиторий *является* реализацией, а не vault — отвергается по замыслу. |
| Класть операторские regex в layout, не ожидая шлюза ReDoS | Паттерн с катастрофическим backtracking отвергается при загрузке (exit 6) или пропускается по дедлайну во время выполнения. Пишите линейные паттерны. |

---

## Приложение со справочником команд

Полные контракты (флаги, каждый код выхода, точный JSON-конверт) живут в
`SKILL.md` каждого skill. Быстрый указатель:

| Команда | Одной строкой | Skill |
|---|---|---|
| `wiki-init` | Scaffold / регистрация / reconcile vault | [skills/wiki-init](../../skills/wiki-init/SKILL.md) |
| `wiki-reindex` | Перестроить БД из Markdown (`--full` / `--delta`) | [skills/wiki-reindex](../../skills/wiki-reindex/SKILL.md) |
| `wiki-index-upsert` | Проиндексировать один Markdown-файл (идемпотентно) | [skills/wiki-index-upsert](../../skills/wiki-index-upsert/SKILL.md) |
| `wiki-index-render` | Отрендерить `index.md` / реестры из БД | [skills/wiki-index-render](../../skills/wiki-index-render/SKILL.md) |
| `wiki-search` | Поиск FTS5 + по метаданным через vault-ы | [skills/wiki-search](../../skills/wiki-search/SKILL.md) |
| `wiki-query` | RAG: retrieve → цитируемый синтез → запись ответа | [skills/wiki-query](../../skills/wiki-query/SKILL.md) |
| `wiki-verify-multi` | Аудит записанного ответа 4 критиками | [skills/wiki-verify-multi](../../skills/wiki-verify-multi/SKILL.md) |
| `wiki-sync` | Формато-зависимый диспетчер: `scan` зоны → план → convert/ingest/upsert/skip (+ OCR сканированных PDF); `record` = маркер коммита | [skills/wiki-sync](../../skills/wiki-sync/SKILL.md) |
| `wiki-enrich` | Ingest сырого источника, затем его индексация | [skills/wiki-enrich](../../skills/wiki-enrich/SKILL.md) |
| `wiki-extract-concepts` | Двухпроходное извлечение концепций | [skills/wiki-extract-concepts](../../skills/wiki-extract-concepts/SKILL.md) |
| `wiki-append-log` | Добавить структурированное событие в log | [skills/wiki-append-log](../../skills/wiki-append-log/SKILL.md) |
| `wiki-confirm` | Повысить/понизить кандидатную сущность | [skills/wiki-confirm](../../skills/wiki-confirm/SKILL.md) |
| `wiki-alias` | Управление alias-ами сущностей | [skills/wiki-alias](../../skills/wiki-alias/SKILL.md) |
| `wiki-merge` | Свернуть дублирующую сущность | [skills/wiki-merge](../../skills/wiki-merge/SKILL.md) |
| `wiki-lint` | Проверка здоровья на уровне SQL | [skills/wiki-lint](../../skills/wiki-lint/SKILL.md) |

Контрактные skill-ы (на стороне LLM, без CLI; загружаются orchestrator-ом между
`prepare`/`apply`): `wiki-query-synthesis`, `wiki-verify`, `concept-extraction`.

---

## См. также

- [`README.md`](../../README.md) — обзор, установка, указатель команд.
- [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) — живая архитектура.
- [`docs/adr/ADR-001-*`](../adr/ADR-001-wiki-ingest-integration.md) — wrap + index.
- [`docs/adr/ADR-002-*`](../adr/ADR-002-multi-vault-bottleneck-corrections.md) — multi-vault + контракт Class A/B/C.
- [`docs/WIKI-INGEST-V1.1-CONTRACT.md`](../WIKI-INGEST-V1.1-CONTRACT.md) — контракт skill файлового слоя.
- [`sql/wiki-index-v2.sql`](../../sql/wiki-index-v2.sql) — DDL схемы.
- [`workflows/`](../../workflows/) — рецепты orchestrator-а для skill-ов `prepare`/`apply`.
