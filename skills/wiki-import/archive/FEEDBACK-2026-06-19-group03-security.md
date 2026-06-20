# Обратная связь: экстракция страниц (`wiki-import`) — прогон группы #03

**Дата:** 2026-06-19 · **Vault:** `personal` (TestVault, PARA / obsidian-personal)
**Источник:** BlockUniverse/321, группа #03 (Безопасность / cross-chain), 8 ссылок.
**Пайплайн:** `prepare` (fetch: html2md/pdf) → REASON (`summarizing-meetings`, параллельно в Workflow; всего 3 прохода: 6 источников + 2 рескью g2/g5 + 2 полные версии g4/g6) → adversarial-verify → **serialized** `apply` (concept-filing `wiki-extract-concepts` + index).

## Итог прогона
| Метрика | Значение |
|---|---|
| Импортировано | **8** заметок (6 авто + 2 — g2/g5 — через вручную сохранённый `.webarchive`) + **106** concept-страниц |
| needs-manual (этап авто-fetch) | **1** (g2 — ACM `Quantum Algorithm Implementations for Beginners`, HTTP 403 paywall); закрыто вручную сохранённым `.webarchive` → полная заметка в `Квантовые вычисления`. **Итоговых needs-manual: 0.** |
| Пропущено | **0**. g5 (X-Article «Reverse-Engineering the X Algorithm») авто-fetch упёрся в login-wall; закрыто `.webarchive` → импортирована и перемещена в `05 - Материалы/Social networks`. |
| Wikilinks | ~138 в 8 заметках; нерезолвится **10** forward-links (намеренные: `[[ICE]]`/`[[Castle Labs]]` из g8, `[[x-algorithm]]` из g5, и 7 терминов из g2-quantum); битые image-embed убраны вручную |
| known_concepts reuse | как `mentioned`, без дублей: `ethereum`×3 (g1/g7/g8), `tether`×1 (g8); полные g4/g6 переиспользуют ещё ряд существующих концептов (`абстракция-цепочек`, `aave`, `arbitrum`, `hyperlane`, …) — суммарно ~22 reuse-события |
| Коллизии-вытеснения | 0 (collision-guard сработал; пропущены кандидаты, совпавшие с существующими: g7=2, g4=5, g6=2, g2=2) |

---

## Что работает хорошо (сохранить)

1. **Adversarial-verify реально ловит ошибки** — главный выигрыш этого прогона:
   - **g8**: DTCC ошибочно отнесён к спонсорам/инвесторам Zero; на деле он — *советник* (funders = Citadel + Tether; advisors = ICE + DTCC). Исправлено до записи.
   - **g6**: выдуманное «критическая потребность» из *обрезанного* login-wall-тизера — удалено.
   - Чистка имён сущностей (`TCP/IP` → `TCP-IP`), проверка verbatim-цитат.
   Без этого слоя обе фактические ошибки попали бы в vault — это ровно те классы багов, что были в ручных (ad-hoc) импортах #01/DAO.
2. **Reuse `known_concepts`** — дисциплина держится: `ethereum`/`tether` и ряд других переиспользованы как `mentioned`, граф `ethereum` теперь связывает новые заметки + старые (quantum/DAO). Компаундинг работает.
3. **Collision-guard** — generic-слаги не вытесняют существующие страницы; пропуски явные.
4. **Layout-aware PARA filing** — заметка + sibling `_concepts/` легли в правильные папки/проекты (`Материалы/Security`, `Материалы/Криптовалюты`, и после ручного перемещения — `Материалы/Social networks`) без ручной правки путей.
5. **needs-manual для paywall (g2) — корректно**: авто-fetch не стал выдумывать контент за HTTP 403, а просигналил needs-manual. Дальше paywall закрыт вручную сохранённым `.webarchive` → g2 импортирована полностью (стаб удалён).
6. **Serialized apply** — 8 заметок + 106 концептов записаны (тремя проходами) без гонок и конкуренции за запись WAL.

---

## Что доработать (по приоритету)

### P0 — баг, блокировавший импорт (УЖЕ ИСПРАВЛЕН в этом сеансе)
1. **Утечка `PYTHONSAFEPATH` в дочерний `pdf_extract`.** Обёртка `bin/wiki-import` экспортирует `PYTHONSAFEPATH=1` (+`PYTHONPATH=<repo>`); они наследовались subprocess-ом `pdf_extract.py`, подавляя script-dir на `sys.path` → его `from _errors import …` падал → **каждый PDF** возвращал ложный `FETCH_FAILED`.
   - **Фикс:** `_skill_env()` в [`_fetch.py`](scripts/wiki_skills/wiki_import_article/_fetch.py) вычищает `PYTHONSAFEPATH`/`PYTHONPATH` перед вызовом html2md/pdf. mypy `--strict` ✓, 40 import/fetch-тестов ✓.
   - **TODO:** регресс-тест на env-санитайз. Утечка затрагивает только обёртку, которая **порождает дочерний процесс** html2md/pdf — то есть сам `wiki-import`. Проверено: `wiki-enrich` зовёт вендоренный `wiki_ingest` (in-process; на фолбэке — CLI `wiki-ingest`, не html2md/pdf), а `wiki-sync scan` — plan-only (без spawn). Их та же утечка **не** затрагивает (исходное утверждение было неточным).

### P1 — целостность Class B при удалении/переимпорте (обнаружено при замене g4/g6 на полные версии)
2. ⏳ **ОТКРЫТО (нужна отдельная задача — см. постановку ниже).** **Удаление concept-страницы + `wiki-reindex --delta` НЕ чистит строку в `entities`.** `--delta` снёс только строки `pages`, но `entities`-строки удалённых концептов остались (с `file_path` на уже несуществующий `.md`). При переимпорте `wiki-extract-concepts` сверяется с `entities` → счёл их существующими → **«mentioned» вместо «created»** → concept-страницы не пересоздались, а `[[вики-ссылки]]` заметки повисли (5 битых линков в g4/g6).
   - **Обход (сработал):** `wiki-reindex --full` пересобрал `entities` из markdown (5 фантомных строк исчезли) → повторный `apply` создал недостающие 5 страниц → 0 висячих ссылок.
   - **Доработки:** (а) удаление concept-`.md` должно каскадно чистить `entities` (+`page_entity_refs`) и при `--delta`, не только при `--full`; (б) `wiki-extract-concepts` перед «mentioned» проверять, что у entity реально есть `.md` на диске (иначе — `created`); (в) задокументировать в SKILL/workflow: **replace-flow = удалить заметку+концепты → `--full` → переимпорт** (не `--delta`).

### P2 — надёжность fetch
3. ✅ **ИСПРАВЛЕНО — PDF по URL без суффикса `.pdf`.** html2md сигналит `details.kind=="pdf"`; `dispatch_fetch` теперь делает fallback в `_fetch_pdf_url` (раньше — только для arxiv `arxiv_no_html`). Проверено live: ACM `doi/pdf/10.1145/3517340` (256 КБ) и `arxiv.org/pdf/2005.14282` (220 КБ) импортируются. Тест `test_url_serving_pdf_without_suffix_routes_to_pdf`.
4. ✅ **ИСПРАВЛЕНО — слабый User-Agent.** `_download_pdf` шлёт браузерный UA (`_PDF_FETCH_UA`) + `Accept: application/pdf` — этого хватило даже на 403-ивший ранее ACM. Тест `test_pdf_download_uses_browser_ua`.
5. ✅ **ИСПРАВЛЕНО — X login-wall как «успех».** `_is_x_login_wall` (scoped к `x.com`/`twitter.com`): голый login-wall (<220 знаков прозы + login-маркеры) → `FETCH_FAILED kind:login_wall` с подсказкой про `.webarchive`; реальный текст треда проходит. Тесты `test_x_login_wall_is_not_ok` / `test_x_with_real_post_text_is_ok` / `test_non_x_login_markers_not_flagged`. (Опционально не сделано: chrome-движок для `x.com` — достаёт первый твит, но реплаи/X-Articles всё равно за логином → `.webarchive` остаётся основным путём.)

### P3 — качество экстракции
6. ⏳ **ОТКРЫТО — PDF из 2 колонок теряет пробелы между словами.** g3 (arxiv-survey) извлёкся как `ASurveyonBlockchainInteroperability…`. Дефект во **внешнем** `pdf`-скилле (`pdf_extract.py`, отдельный репозиторий) — вне этого репо. См. постановку ниже.
7. ✅ **ИСПРАВЛЕНО — image-embeds в теле.** Истинная причина: html2md (`--no-download-images`) оставляет `![[Attachments/<hash>.png]]` в `ru_body`, который агент копирует из raw. `_strip_image_embeds` в `assemble_note` вырезает `[[Attachments/…]]`-строки из тела (full/thread) перед записью. Тест `test_full_mode_strips_dangling_image_embeds`.
8. ✅ **ИСПРАВЛЕНО — footer ↔ материализованные концепты + тихие дропы.** Истинная причина висячих `[[ICE]]`/`[[Castle Labs]]` (g8) была **не** name-gate, а **тихий обрез `out[:_MAX_CANDIDATES]`** (кэп был 15; у g8 — 17 filable сущностей → хвост из 2 молча отбрасывался). Фикс: (а) footer (`## Ключевые сущности`) строится только из резолвящихся сущностей — записанные кандидаты + `collides-existing-page` (страница уже есть) — остальные исключаются, без висячих ссылок; (б) overflow за кэп **репортится** в `skipped[]` (reason `max-candidates`), не молча; кэп поднят 15→25 (полные статьи несут 15–18 сущностей). Тесты `test_footer_omits_unresolvable_entities` / `test_overflow_entities_reported_not_silently_dropped`.

### P4 — оркестрация (harness/инструмент, не фреймворк)
9. ⏳ **ВНЕ РЕПО (harness).** **Workflow-tool `args` не дошёл до скрипта** (`args.items` = undefined → `pipeline() expects an array`). Обход: данные захардкожены в скрипт. Это контракт Claude Code Workflow, не obsidian-llm-wiki — проверить передачу `args` при запуске через `scriptPath`.

---

## Постановка для оставшихся доработок

Что в этом сеансе **исправлено + покрыто тестами**: P0 (env-утечка), P2-3/4/5 (PDF-роутинг, браузерный UA, X login-wall), P3-7 (image-embeds), P3-8 (footer-sync + репорт overflow, кэп 15→25). Полный прогон: `mypy --strict` ✓, `pytest` 1588 passed / 5 skipped. Ниже — то, что **намеренно НЕ** правилось «на ходу» (риск или вне репо) и оформлено как задачи.

### Задача A — каскадная очистка `entities`/`page_entity_refs` при удалении страницы (P1-2)
- **Проблема.** `repo.delete_page()` (`scripts/wiki_index/sqlite_repository.py`) удаляет строку только из `pages`. `wiki-reindex --delta` (`scripts/wiki_index/reindex.py:~732`) зовёт его для каждого исчезнувшего файла, но `entities`/`page_entity_refs` остаются. Удалённый концепт остаётся «существующим» для `wiki-extract-concepts` → при переимпорте он «mentioned», страница не пересоздаётся → висячие `[[ссылки]]`. (Сейчас лечится только `wiki-reindex --full`.)
- **Почему нельзя «в лоб».** `DELETE FROM entities WHERE vault_id=? AND slug=?` **опасен**: заметка и концепт могут делить слаг (кейс `defi` vs `Defi.md`) — удалится не та сущность. Каскад обязан матчить по **`file_path`** удаляемой страницы, не по слагу.
- **Дизайн.**
  1. Новый метод репозитория `delete_entity_by_file_path(vault_id, file_path)` → `DELETE FROM entities WHERE vault_id=? AND file_path=?` + каскад `page_entity_refs` (по `entity_slug`, который мы получаем из удаляемой строки entity).
  2. В `reindex.py` delta-ветке: у удаляемой строки `r` есть `file_path`/`type`; после `delete_page`, если `r["type"]=="concept"` (или безусловно по `file_path`), вызвать новый метод.
  3. Защита-в-глубину в `wiki-extract-concepts`: перед статусом «mentioned» проверять `Path(entity.file_path).exists()`; нет файла → трактовать как `created` (устойчивость к рассинхрону даже при оставшейся строке).
- **Критерии приёмки.** Тест: создать концепт → удалить `.md` → `wiki-reindex --delta` → строка `entities` исчезла (+ её `page_entity_refs`); затем переимпорт **пересоздаёт** страницу (а не «mentioned»). `wiki-reindex --full` остаётся идемпотентным (rebuildability). `mypy --strict` ✓.
- **Тесты.** `tests/test_reindex*.py` (delta-каскад) + extract-concepts existence-check.
- **Риск.** Средний — трогает delete-путь Class B. Обязательны rebuildability + delete-тесты. Поэтому отдельная задача, не правка на ходу.
- **Документация.** В `skills/wiki-import/SKILL.md` + `workflows/wiki-import.md` зафиксировать **replace-flow**: «удалить заметку + её `_concepts/` → `wiki-reindex --full` → переимпорт» (не `--delta`) — до внедрения каскада это обязательный обход.

### Задача B — расстановка пробелов в многоколоночных PDF (P3-6)
- **Проблема.** `pdf_extract.py` на 2-колоночной академической вёрстке склеивает слова (`ASurveyonBlockchain…`).
- **Репро-PDF (g3).** [`arxiv.org/pdf/2005.14282`](https://arxiv.org/pdf/2005.14282) — Belchior et al., *«A Survey on Blockchain Interoperability: Past, Present, and Future Trends»* (та же статья, что в P2-3 выше использовалась как live-тест PDF-роутинга).
- **Где.** Внешний/вендоренный `pdf`-скилл (`~/.claude/skills/pdf/scripts/pdf_extract.py`, отдельный репозиторий) — **вне** obsidian-llm-wiki. Заводить в его трекере.
- **Обход (работает сейчас).** Для таких PDF — `--mode summary` (REASON-агент сегментирует слипшийся текст в детальные буллеты); качество приемлемо (g3 так и прошёл).

### Задача C — контракт `args` Workflow-tool (P4-9)
- **Вне репо** (harness Claude Code). Обход — хардкод данных в скрипт workflow. Проверить передачу `args` при `scriptPath` на стороне инструмента.

---

## Дополнительно реализовано (этот сеанс) — self-contained `_raw` + импорт картинок
По итогам разбора заметки StripChain («поломан и без картинок»):
1. ✅ **`_raw` всегда несёт `source:`-ссылку на оригинал.** `ensure_source_frontmatter` в [`_fetch.py`](scripts/wiki_skills/wiki_import_article/_fetch.py) инъектит `source:` (для PDF/текст-дампов без фронтматтера и captures без `source`). Тест `test_ensure_source_frontmatter_cases` / `test_prepare_ok_emits_envelope_and_writes_raw`.
2. ✅ **Импорт картинок — config-driven, по умолчанию ВКЛ.** Новое поле `LayoutConfig.import_images` (default `true`; override `import_images: false` в `.wiki/layout.yaml`, zero-Python). При ВКЛ `_fetch_html` идёт в OUTPUT-DIR-режим html2md (`--download-images`) → картинки в `_raw/_attachments/` с относительными `![](_attachments/<sha>)`-ссылками; `prepare` раскладывает их и чистит temp. Envelope даёт `images: <N>`. Тесты `test_fetch_html_download_images_output_dir` / `test_prepare_files_downloaded_images` / `test_import_images_default_on_and_overridable`. Live-проверка: verkle → `images=4`, `_raw/_attachments/` = 4 файла, temp очищен. (PDF — text-only, картинок нет by design.)
3. ✅ **Заметка ссылается и на `_raw`, и на оригинал.** `assemble_note`: `Источник` = кликабельная ссылка на URL оригинала; `Оригинал (raw)` теперь кликабельная `[\`_raw/<slug>\`](_raw/<slug>)` (+ `sources:` фронтматтер).
4. ✅ **Reader-first fetch (баг: захватывали whole-page с мусором).** `_fetch_html` шёл с `--no-reader` → в `_raw` попадал весь шум страницы (`Skip to main content`, `Edit page`, nav). Теперь html2md в OUTPUT-DIR-режиме отдаёт dual-output, и мы **предпочитаем `.reader.md`** (чистый контент), с фолбэком на whole при over-strip (<200 знаков тела); в `_attachments/` остаются только картинки, на которые ссылается выбранный текст (аватары/chrome-иконки отсеиваются). Тесты `test_fetch_html_prefers_reader_and_prunes_unreferenced_images` / `..._falls_back_to_whole_when_reader_too_thin`.
5. ✅ **Существующие заметки группы #03 починены** (без re-apply → без риска Задачи A): все 8 `_raw` получили `source:`; 5 article-источников переимпортированы reader-clean с локальными картинками (verkle/layer-zero/stripchain/quantum/vibhu), 44 orphan-картинки от прежнего whole-page фетча вычищены (GC); все заметки — кликабельная `_raw`-ссылка; StripChain — починена битая `[Отредактировано]:`-строка.

Полный прогон после правок: `mypy --strict scripts/` ✓ (84 файла), `pytest` ✓ (1593 passed / 5 skipped).

---

## Здоровье после импорта
- `wiki-lint`: orphan-backlog **6563** (ожидаемо для реального PARA-vault — постепенно разбирается со временем), `lifecycle-drift` **1** (пред-существующий; заметки `article-summary` без `status` дрифт не создают).
- Вклад импорта в orphans: **10** forward-link — намеренные `[[ICE]]`/`[[Castle Labs]]` (g8), `[[x-algorithm]]` (g5) и 7 терминов из g2-quantum (`los-alamos-national-laboratory`, `rsa`, `квантовая-томография`, `алгоритм-бернштейна-вазирани`, `задача-о-скрытой-подгруппе-hsp`, `поперечная-модель-изинга`, `квантовый-метод-главных-компонент-pca`); реальные сущности/термины, зарезолвятся будущими заметками.
- Все **8** новых страниц проиндексированы с верными `project` (g5 — `Материалы/Social networks` после ручного перемещения, g2 — `Материалы/Квантовые вычисления`); `wiki-search`/`wiki-graph` находят новые концепты.

## Резюме
Пайплайн **готов к продакшену**: layout-aware filing, reuse концептов и adversarial-verify дают качественный компаундинг. В этом сеансе **закрыты** P0 (env-утечка), весь **край fetch** (P2-3 PDF-роутинг, P2-4 браузерный UA, P2-5 X login-wall) и **качество тела** (P3-7 image-embeds, P3-8 footer-sync + репорт overflow, кэп 15→25) — все с тестами (`pytest` 1588 passed, `mypy --strict` ✓). **Остаётся** (оформлено постановкой выше): A — каскад `entities` при `--delta`-удалении (P1-2, средний риск → отдельная задача; обход — `--full`), B — пробелы в 2-колоночных PDF (P3-6, внешний `pdf`-скилл), C — контракт `args` Workflow (вне репо).
