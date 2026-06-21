# obsidian-llm-wiki — краткий справочник CLI

> 🇷🇺 Русское зеркало [`cli-quick-reference.md`](cli-quick-reference.md).

Шпаргалка на одну страницу для повседневной работы **из терминала, открытого в папке
вашего vault** (та же папка, что открывает Obsidian), и **через Claude CLI**, запущенный
там же. Полный справочник — [obsidian-llm-wiki_manual.ru.md](obsidian-llm-wiki_manual.ru.md);
первичная настройка на реальном vault —
[../runbooks/personal-vault-adoption.md](../runbooks/personal-vault-adoption.md).

**Ментальная модель.** Вы пишете markdown в Obsidian; индекс SQLite — это *перестраиваемый
кэш* (ADR-002 §D8). CLI поддерживают слой поиска/знаний в актуальном состоянии — они
читают markdown и никогда не блокируют к нему доступ. `vault_id` (например, `personal`)
объявлен в `WIKI_SCHEMA.md`. Запускайте команды **изнутри vault**: корень vault
определяется автоматически (передавайте `--vault-root .`, только если команда этого
требует). Для iCloud-vault индексная БД лежит вне синхронизируемого диска — по
абсолютному пути под OS app-data (напр. `~/Library/Application Support/…`), который
**доверяется автоматически — env-переменная НЕ нужна**. (Абсолютный путь *вне* app-data
по-прежнему требует `export WIKI_ALLOW_ABSOLUTE_INDEX_DB=1`.)

> **Какое значение `--vault <id>`? (два РАЗНЫХ «vault» — не путайте)**
> - `wiki-* --vault`/`--vaults <id>` принимают **вики `vault_id`** — он объявлен в
>   `WIKI_SCHEMA.md` (`vault_id:`), например `personal`. Его выбираете **вы**.
> - `obsidian …` и `obsidian-active-note --vault <NAME>` принимают **имя вокса в Obsidian**
>   (имя папки в приложении, например `ObsidianNotes`; см. `obsidian vaults verbose`).
> - Они **могут отличаться** (например `personal` vs `ObsidianNotes`). Узнать `vault_id`:
>   ```bash
>   grep '^vault_id:' WIKI_SCHEMA.md                                   # изнутри вокса (источник истины)
>   sqlite3 "<index_db>" "SELECT vault_id, root_path FROM vaults;"     # список всех зарегистрированных воксов
>   #   <index_db> = значение `index_db:` из WIKI_SCHEMA.md, либо глобальный дефолт
>   #   ~/Library/Application Support/wiki-index/global.db
>   ```
>   Каждая JSON-строка `wiki-search`/`wiki-reindex` тоже эхает `"vault_id"`. (Отдельной
>   `wiki-* --list-vaults` нет — список даёт запрос `sqlite3` выше.)

---

## A. Вручную — набираете команды сами

```bash
cd "/path/to/your/Obsidian/Vault"     # the vault root (has WIKI_SCHEMA.md)
```

**Поиск (то, что делаете чаще всего) — FTS5, <100 мс**
```bash
wiki-search "дофамин"                       --vaults personal
wiki-search "lasso regularization"          --vaults personal --limit 5
wiki-search "переговоры" --vaults personal --project "Learning/Переговоры"
wiki-search --vaults personal --where "type=lesson-summary" --limit 10   # фильтр по полю frontmatter (без FTS-запроса)
wiki-search --vaults cybos --tag decision --as-of 2026-04-20               # ВРЕМЕННОЙ срез: решения, АКТИВНЫЕ на дату (TASK 034; вытесненные/аннулированные к этой дате исключаются — без LLM и без ручного valid_to)
wiki-search "smart money" --vaults personal --types summary               # restrict to a db type
wiki-search "агент" --vaults personal --exact                            # точный поиск: без стемминга (ё/е всё равно сводятся)
```

> Поиск по умолчанию **устойчив к словоформам**: одиночные термины автоматически
> приводятся к основе с префиксом (`сценарии`→`сценар*`, `agents`→`agent*`) и
> **сводят ё/е**, поэтому одна введённая форма находит свои словоформы, а `ещё`/`еще`
> — один токен. `--exact` (`--no-stem`) ОТКЛЮЧАЕТ стемминг для точного буквального
> поиска. Свёртка ё/е в теле требует разовой `wiki-reindex --full`; стемминг и
> свёртка ё/е в запросе работают сразу.

**Поддерживайте индекс в актуальном состоянии после правок/добавления заметок в Obsidian**
```bash
wiki-reindex --delta --vault personal       # fast: only changed files (mtime/hash)
wiki-reindex --full  --vault personal        # wipe + rebuild from markdown (rare; authoritative)
```

**Проиндексировать одну готовую заметку сразу** (layout-aware: правильные project/type/refs)
```bash
wiki-index-upsert --vault personal --source "./03 - Learning/Courses/X/note.md"
```

**Авто-маршрутизация смешанной зоны** (транскрипты — суммаризировать, документы —
конвертировать, заметки — индексировать, view-сайдкары — пропустить). `scan` только
ПЛАНИРУЕТ — ничего не пишет:
```bash
wiki-sync scan "03 - Learning" --vault personal              # JSON plan
wiki-sync scan "03 - Learning" --vault personal --dry-run     # human-readable plan
# Executing the plan (summarising etc.) is orchestrator/LLM work → use Claude CLI (§B).
```

**Проверка здоровья** (drift, висячие `[[links]]`, расхождение хэшей, межвалтовые дубли + lifecycle-drift)
```bash
wiki-lint --vault personal                   # SQL-здоровье + lifecycle-drift (авторский status против графа)
wiki-lint --vault personal --strict           # ненулевой выход при любой проблеме (CI-гейт)
```

**Производное «здоровье знаний»** (vault'ы с типизированными классами, напр. `cybos`) — чего НЕ ХВАТАЕТ
```bash
wiki-health coverage --vault cybos                       # страницы без ожидаемого ребра/поля (всегда exit 0)
wiki-health coverage --vault cybos --class requirement   # напр. requirement'ы, которые ничто не реализует
```

**Задать вопрос и получить синтез с цитатами (RAG)** — в два шага `prepare`/`apply`:
```bash
wiki-query prepare "compare X and Y" --vault personal     # retrieves context (LLM cites it)
# (the answer is composed, then) wiki-query apply …        # files a compounding _queries/<slug>.md
```

**Прочие полезные**
```bash
wiki-enrich --vault personal --vault-root . --source "./raw.md"   # Karpathy: ingest+index сырого источника
# импорт внешнего URL/PDF/треда/транскрипта (любой layout; шаг REASON между — работа оркестратора).
# prepare отдаёт `language` (язык хранилища из WIKI_SCHEMA, фолбэк en) → суммаризируйте НА этом языке:
wiki-import prepare --vault personal --vault-root . --kind auto \
    --source "https://example.com/article" --folder "05 - Материалы/Криптовалюты" --mode full
#   …перевести/суммаризировать НА prepare.language, переиспользуя known_concepts; note JSON — нейтральные
#   {title, body, summary_bullets, entities[]} (легаси title_ru/ru_body тоже принимаются). Затем:
wiki-import apply --vault personal --vault-root . --folder "05 - Материалы/Криптовалюты" --kind "<prepare.kind>" \
    --mode full --raw-rel "<prepare.raw_path>" --source-url "<URL>" \
    --existing-page-slugs '<prepare.existing_page_slugs>' --note-stdin
wiki-index-render --vault personal --auto-indexes                  # (re)generate index/ledger pages
wiki-init --register-existing --vault .                            # one-time: register this vault
```

> Совет: каждая команда печатает JSON-конверт — направьте его в `python3 -m json.tool`
> для чтения, или в `jq`, если установлен.

---

## B. Через Claude CLI — пусть агент управляет

Запустите Claude в корне vault; он читает `CLAUDE.md` этого vault и вызывает CLI за вас.
Просто просите обычным языком — флаги запоминать не нужно:

```bash
cd "/path/to/your/Obsidian/Vault"
claude        # or your Claude Code launcher
```

> **Чтобы прекратить постоянные подтверждения команд.** Один раз скопируйте в vault
> готовый шаблон прав: `mkdir -p .claude && cp <repo>/templates/vault.claude-settings.json
> .claude/settings.json`. Он авто-запускает `wiki-*` CLI + безопасные read-команды и
> авто-принимает правки файлов, при этом опасные операции (`rm -rf`, `sudo`, egress)
> остаются под запросом/блоком. См. секцию `.claude/settings.json` в runbook.

Затем, например:
- *«Найди в моём wiki, что я записал про дофамин, и суммаризируй.»*
- *«Я закинул новые транскрипты в `03 - Learning/Courses/<Course>/_transcripts/` —
  просканируй зону, суммаризируй новые, разложи их по файлам и переиндексируй.»* (агент
  запускает `wiki-sync scan`, затем executor из `workflows/wiki-sync.md`: снятие таймштампов
  → суммаризация → `wiki-index-upsert` → `wiki-sync record`, идемпотентно.)
- *«Что мой vault говорит про X и Y? Дай ответ с цитатами.»* (запускает `wiki-query`.)
- *«Я отредактировал кучу заметок — обнови индекс и прогони lint.»*
- *«Разложи этот meeting-summary как заметку в `04 - Work projects/<Client>/` и проиндексируй.»*

Для частых действий есть и слэш-команды: `/wiki-search`, `/wiki-query`, `/wiki-sync`,
`/wiki-reindex`, `/wiki-lint`, `/wiki-health`, `/wiki-import` (единый on-ramp для внешних
источников, любой layout), `/wiki-enrich` (legacy Karpathy-raw). Агент держит вас в курсе всего, что пишет
(саммари, новые заметки), и безопасен к повторному запуску (идемпотентность по файлам).

---

## C. Типовые циклы

| Когда | Что делать |
|-------|------------|
| **После правки заметок в Obsidian** | `wiki-reindex --delta --vault personal` → `wiki-search …` |
| **Новый транскрипт / raw-документ в зоне курса** | Claude CLI: «просканируй и суммаризируй `<zone>`» → он планирует (`wiki-sync scan`), затем исполняет; повторный запуск — no-op (уже суммаризированные raw пропускаются) |
| **Что-то найти** | `wiki-search "…" --vaults personal` (или попросить Claude) |
| **Нужен синтезированный ответ с цитатами** | `wiki-query prepare/apply` (или попросить Claude) |
| **Периодическое здоровье** | `wiki-lint --vault personal` (бэклог orphan-links ожидаем; со временем дренируется); `--strict` — гейт по lifecycle-drift |
| **Пробелы покрытия (типизированные vault'ы)** | `wiki-health coverage --vault cybos` — requirement'ы без реализатора, факты без источника; пробел это данные, exit 0 |
| **Индекс выглядит неверно / после большого перемещения** | `wiki-reindex --full --vault personal` (безопасно — пересборка из markdown) |

**Тюнинг** живёт в двух per-vault файлах (см. runbook): `<vault>/.wiki/layout.yaml`
(что индексировать — `ignore`, `type_mapping`; например, внедрите типизированные классы
знаний из TASK 031 — `decision`/`requirement`/`risk`/`incident`/`hypothesis`/`fact`/`event` —
добавив их под `type_mapping` здесь, они ОБЪЕДИНЯТСЯ (UNION) со встроенным layout) и
`<vault>/.wiki/sync.yaml` (как `wiki-sync` маршрутизирует зону — `zones`,
`transcript_dedup`, `resummarize`). Новые формы целого vault — тоже конфиг: положите
`layouts/<name>.yaml` (например встроенный `cybos`) → `wiki-init --layout <name>`
подхватит его, ноль кода.
