# Migration: TASK-ref.md (v1) → TASK-ref-v2.md

> Этот документ описывает переход с дизайна v1 (Karpathy-only, file-walking) на v2 (Karpathy + cybos hybrid, SQLite+FTS5+pluggable adapters). На момент создания v2 **никакие скиллы из v1 ещё не имплементированы** — миграция касается только спецификации и `tmp2/` корпуса (16 готовых summary-страниц).

---

## 1. Что изменилось концептуально

| Элемент | v1 | v2 |
|---|---|---|
| Source of truth | Markdown в vault'е | Markdown в vault'е (без изменений) |
| Search/lint engine | File-walking + frontmatter parse | SQLite FTS5 + GIN-style indexes |
| Index file (`index.md`) | Source-of-truth, mutable | **Read-only projection** из SQLite |
| Sources поддерживаемые | Только manual transcripts (`_raw/`) | transcript + email + telegram + web + manual |
| Concept extraction | Opt-in batch via `wiki-extract-concepts` | Auto via per-source extractors + `wiki-extract-concepts` для рефайна |
| Verify-multi | Default on (4 critics) | Default off, opt-in флагом |
| Folder layout | Flat `Summaries/{date}-{slug}.md` | Per-item subfolder `Summaries/{date}-{slug}/{body.md, raw/, verify.json}` |
| iCloud awareness | Не упомянуто | Explicit: SQLite вне iCloud, markdown в iCloud |
| Cross-source view | Нет | `wiki-brief` daily digest |
| Provenance | `appears_in:` backlink | `source_quote` + `source_span` + `trust_level` обязательны |

---

## 2. Что менять в существующем `tmp2/` корпусе

`tmp2/` содержит 16 готовых summary-страниц, сгенерированных текущим `summarizing-meetings`. Они совместимы с v2 за вычетом мелочей:

### 2.1 Совместимо без изменений

- YAML frontmatter (`type`, `title`, `tags`, `related`, `concepts`, `speaker`, `course`).
- Pyramid Level 1/2/3.
- HTML-якоря (`<!-- SECTION:* -->`).
- `## Ключевые цитаты спикера` (citations).
- Chunk Boundaries в Agent Metadata.

### 2.2 Желательные правки (необязательны для совместимости)

- Добавить `provenance:` блок на каждый concept в machine-readable таблице — `source_quote`, `source_span`, `trust_level`. v2 будет терпеть отсутствие, но lint пометит warning.
- Перенести из `tmp2/` в новую структуру: `tmp2/day1-01-savochka-rukovoditel-2026.md` → `Summaries/day1-01-savochka-rukovoditel-2026/body.md` + рядом `metadata.json` (опц.).

### 2.3 Bulk-миграция (выполняется один раз после имплементации v2)

```bash
# 1. Initialize v2 vault structure (создаёт SQLite, schema, директории)
wiki-init --vault tmp2/ --layout flat

# 2. Bulk-перенос (оборачивает каждый файл в subfolder)
wiki-migrate-flat-to-folders tmp2/Summaries/

# 3. Reindex весь корпус в SQLite
wiki-reindex --full

# 4. Опц: вынести концепты в Concepts/ (если включить auto_extract)
wiki-extract-concepts --batch 'Summaries/**/*.md'

# 5. Lint health check
wiki-lint --strict
```

---

## 3. Изменения в спецификации (по разделам v1 → v2)

| Раздел v1 | Действие | Раздел в v2 |
|---|---|---|
| §1 Канон Karpathy | Keep | §1 |
| §2 Что делает skill+workflow | Keep | §2 |
| §3 Совместимость | Keep + ref на cybos | §3 |
| §3.bis Concept page | Keep | §3.bis |
| §4 Что покрывает | Расширенная таблица | §4 |
| §5 Итоговый ответ | Дополнен про multi-source | §5 |
| §6 Где лежат скиллы | + iCloud warning | §6 + §6.4 (NEW) |
| §7 Scope/deliverables | Rewrite — расширенная таблица | §7 |
| §8 Schema | Edit — добавлены `wiki.index`, `wiki.sources`, `wiki.automations`, `wiki.mcp` | §8 |
| §9 wiki-init | Edit — создаёт SQLite | §9 |
| §10 wiki-update-index | Rewrite — теперь `wiki-index-upsert` (DB), `index.md` projection | §10 |
| §11 wiki-append-log | Edit — ротация по месяцам | §11 |
| §12 wiki-extract-concepts | Edit — интегрировано с entity-resolver | §12 |
| §12.bis wiki-search | Rewrite — FTS5 backed | §12.bis |
| §13 wiki-lint | Rewrite — SQL-based | §13 |
| §14 wiki-query | Edit — RAG over FTS5 | §14 |
| §15 ingest-source | Rewrite — multi-source dispatcher | §15 |
| **(NEW) §15.bis** Source Adapters | Add | §15.bis |
| **(NEW) §15.ter** wiki-source-email | Add | §15.ter |
| **(NEW) §15.quater** wiki-source-telegram | Add | §15.quater |
| **(NEW) §15.quin** wiki-source-web | Add | §15.quin |
| **(NEW) §15.sex** wiki-brief | Add | §15.sex |
| §16 Форматы файлов | Edit — index.md теперь auto-generated | §16 |
| §17 Migration | Replaced by this file | этот файл |
| §18 Порядок реализации | Rewrite — фаза 1 = SQLite, фаза 2-13 = адаптеры | §18 |
| §19 Тестирование | + Performance benchmarks | §19 |
| §20 Доставка | Edit — pinned deps | §20 |
| §21 Зависимости | Edit — sqlite-vec, gramjs, gmail-mcp | §21 |
| §22 Что не забыть | Edit — iCloud, slug-stability, MCP, per-source state | §22 |
| §23 Human-editable | Keep — index.md теперь read-only нота добавлена | §23 |
| §24 Research | Edit — MCP fallback chain | §24 |
| §25 verify-multi | Edit — default off | §25 |
| §26 Принятые решения | Edit — добавлены решения 7-12 | §26 |
| **(NEW) §27** Index Layer detailed spec | Add | §27 |
| **(NEW) §28** Performance budget & SLOs | Add | §28 |
| **(NEW) §29** Cybos-приёмы | Add | §29 |

---

## 4. Что выбрасывается из v1

Ничего. v1 остаётся в репозитории как `docs/TASK-ref.md` — анализ соответствия Karpathy-канону. v2 — расширенный план реализации.

---

## 5. Совместимость артефактов

| Артефакт | v1 → v2 совместимость |
|---|---|
| Markdown summary frontmatter | 100% совместим, но желательно добавить provenance fields |
| `[[wiki-links]]` synataxis | 100% совместим |
| HTML anchors (`<!-- SECTION:* -->`) | 100% совместим |
| Concept page format | Совместим, но aliases-семантика расширена |
| `index.md` ручные правки | **Несовместимо** — теперь read-only projection |
| `log.md` старый flat | Совместим, но рекомендуется ротация |
| `wiki-config.yaml` | Schema расширена; v1 валиден, новые поля опциональны |

---

## 6. Когда мигрировать

- **На текущем этапе (TASK-ref-v2.md только что создан, скиллов нет)**: ничего не мигрировать. Мигрировать пока нечего.
- **После имплементации фазы 1-3 v2 (SQLite + wiki-init + wiki-search)**: запустить bulk-миграцию `tmp2/` (см. §2.3 выше) для проверки.
- **Если кто-то в будущем имплементирует v1**: следовать §3 как diff'у; v2 — backward-compatible с v1 markdown за исключением read-only `index.md`.

---

## 7. Rollback

Если v2 окажется хуже v1 на практике:

1. Markdown — нетронут (он source-of-truth и в v1 и в v2).
2. SQLite-файл удалить (`rm ~/.local/share/wiki-index/<hash>.db`).
3. `index.md` пересоздать руками (или прогнать v1 `wiki-update-index` поштучно).
4. v1 скиллы продолжают работать поверх того же markdown.

Цена rollback'а — низкая, потому что markdown остаётся первоклассным носителем смысла. SQLite-индекс и любые v2-only файлы — derivative.
