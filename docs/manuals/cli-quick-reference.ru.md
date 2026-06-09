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
требует). Для iCloud-vault держите в шелле `export WIKI_ALLOW_ABSOLUTE_INDEX_DB=1`
(индексная БД лежит вне синхронизируемого диска).

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
wiki-search --vaults personal --where "type=lesson-summary" --limit 10   # list by frontmatter field (no FTS query)
wiki-search "smart money" --vaults personal --types summary               # restrict to a db type
```

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

**Проверка здоровья** (drift, висячие `[[links]]`, расхождение хэшей, межвалтовые дубли)
```bash
wiki-lint --vault personal
```

**Задать вопрос и получить синтез с цитатами (RAG)** — в два шага `prepare`/`apply`:
```bash
wiki-query prepare "compare X and Y" --vault personal     # retrieves context (LLM cites it)
# (the answer is composed, then) wiki-query apply …        # files a compounding _queries/<slug>.md
```

**Прочие полезные**
```bash
wiki-enrich --vault personal --vault-root . --source "./raw.md"   # ingest+index a raw source
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
`/wiki-reindex`, `/wiki-lint`, `/wiki-enrich`. Агент держит вас в курсе всего, что пишет
(саммари, новые заметки), и безопасен к повторному запуску (идемпотентность по файлам).

---

## C. Типовые циклы

| Когда | Что делать |
|-------|------------|
| **После правки заметок в Obsidian** | `wiki-reindex --delta --vault personal` → `wiki-search …` |
| **Новый транскрипт / raw-документ в зоне курса** | Claude CLI: «просканируй и суммаризируй `<zone>`» → он планирует (`wiki-sync scan`), затем исполняет; повторный запуск — no-op (уже суммаризированные raw пропускаются) |
| **Что-то найти** | `wiki-search "…" --vaults personal` (или попросить Claude) |
| **Нужен синтезированный ответ с цитатами** | `wiki-query prepare/apply` (или попросить Claude) |
| **Периодическое здоровье** | `wiki-lint --vault personal` (бэклог orphan-links ожидаем; со временем дренируется) |
| **Индекс выглядит неверно / после большого перемещения** | `wiki-reindex --full --vault personal` (безопасно — пересборка из markdown) |

**Тюнинг** живёт в двух per-vault файлах (см. runbook): `<vault>/.wiki/layout.yaml`
(что индексировать — `ignore`, `type_mapping`) и `<vault>/.wiki/sync.yaml` (как
`wiki-sync` маршрутизирует зону — `zones`, `transcript_dedup`, `resummarize`).
