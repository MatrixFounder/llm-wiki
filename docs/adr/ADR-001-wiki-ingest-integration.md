# ADR-001: Wiki-Ingest Integration (Wrap + Index)

- **Status**: Accepted (2026-05-25)
- **Decider**: kuptsov.sergey@gmail.com
- **Consulted**: VDD adversarial review (`docs/reviews/TASK-vdd-adversarial-2026-05-25*.md`)
- **Supersedes**: §6.1 "Karpathy-deviation (MVP intentional gap)" in [TASK 002 wiki-mvp](../tasks/task-002-wiki-mvp.md) — obsolete since Phase 3a archived.

## Context

При планировании MVP TASK.md изначально декомпозировал работу на:
- per-source markdown summaries (`Summaries/<slug>/body.md` через `summarizing-meetings` + `/generate-detailed-meeting-summary`)
- SQLite index с FTS5 (R-02/R-04/R-10)
- lint поверх SQL (R-11)
- index render из SQLite (R-08)

В процессе аудита (см. [reviews/](../reviews/)) выяснилось, что MVP **не закрывает Karpathy llm-wiki pattern полностью** — нет concept/entity-page CRUD, additive merge, footnote-citations, contradiction flagging. Все эти capabilities были запланированы в Epic 7 (entity-resolver).

Параллельно у пользователя существует **глобальный skill `wiki-ingest`** (изначально временный stop-gap для проектов без БД). При повторном анализе обнаружилось:
- `wiki-ingest` v1.0 — это **полноценный maintenance layer**: 4 mode (ingest/query/lint/reindex), 40+ функций в `wiki_ops.py`, templates, references.
- Перекрытие с MVP по R-06/R-08/R-10/R-11 составляет 50-90%.
- При этом `wiki-ingest` НЕ имеет SQLite, FTS5, < 50ms SLO, iCloud-aware persistence, path-traversal hardening, sentinel-PK fix, multi-source adapters.

Это **два комплементарных слоя** — file maintenance (wiki-ingest) и index/persistence (MVP). Текущий TASK.md строит их как два конкурирующих слоя, что приводит к дублированию логики и неполной Karpathy-vault поддержке.

## Decision

**Option I: Wrap + Index.** Pivot MVP architecture к модели, где:

1. **`wiki-ingest` — canonical file-layer.** Vendored как git-submodule (по аналогии с `summarizing-meetings`). Владеет:
   - Concept/entity-page CRUD (`_concepts/<slug>.md`, `_entities/<slug>.md`)
   - Additive merge с footnote citations (`[^src-<slug>]`)
   - Contradiction flagging (`⚠️ Contradiction:` blocks, never auto-resolve)
   - File-level lint (orphans, dangling links, missing pages)
   - File-level reindex (`index.md` rebuild с preservation of custom sections)
   - `WIKI_SCHEMA.md` scaffolding (vault conventions)
   - Vault scaffolding (`_sources/`, `_concepts/`, `_entities/`, `index.md`, `log.md`)

2. **MVP — production-grade indexing & persistence layer.** Обрачивает `wiki-ingest` и добавляет:
   - SQLite FTS5 index (< 50ms на 1000+ docs) — R-02, R-04, R-10
   - Provenance v1.1 storage с reconciliation с file footnotes — R-15
   - iCloud-aware DB placement — R-03
   - Path-traversal hardening + sentinel-PK fix — R-26
   - Multi-source adapters (manual/transcript/light) — все funneled через `wiki-ingest`
   - Benchmark suite + SLO enforcement — R-14
   - Two-tier confirmed/candidate entity canonicalization (future Epic 7+, поверх `_concepts/`/`_entities/`)

3. **Data flow**: file = source of truth, SQLite = derived projection.

```
USER → /ingest-source --kind transcript --source X
  ↓
ingest-source dispatcher (MVP I-4.3)
  ↓
wiki-ingest ingest --source X --vault $VAULT [--known-concepts <from-MVP>]
  ├─ scan vault
  ├─ delegate to summarizing-meetings + known-concepts ctx
  ├─ write _sources/<slug>.md
  ├─ additive-upsert _concepts/*.md
  ├─ additive-upsert _entities/*.md
  ├─ flag contradictions
  ├─ update index.md (file)
  └─ append log.md
  ↓ emits manifest JSON: {written_paths: [...], created: [...], touched: [...]}
  ↓
MVP wiki-index-upsert (post-hook)
  For each written_path:
    parse frontmatter → R-07.5 body normalization → upsert pages row →
    replace_refs (provenance v1.1) → FTS5 trigger
  ↓
MVP wiki-append-log + SQLite vault_metadata update
```

## Consequences

### Positive

- **No duplication.** Один canonical file-layer вместо двух конкурирующих.
- **Karpathy-complete.** MVP получает compounding wiki сразу, не deferred to Epic 7.
- **Cleaner roles.** `wiki-ingest` = text ops (LLM judgment + deterministic file mutations). MVP = index ops (SQL, FTS5, performance).
- **Provenance reconcilable.** Footnotes в файлах + `page_entity_refs` в DB — оба производные одного ingest, consistency checkable.
- **Epic 7 упрощается.** Entity-resolver становится "two-tier canonicalization поверх существующих `_concepts/`/`_entities/`", не "build the whole entity layer".

### Negative

- **Зависимость от wiki-ingest stability.** Если у глобального skill'а ломается контракт — MVP падает. Vendored copy через git-submodule фиксирует версию.
- **Subprocess overhead.** Каждый ingest = subprocess invocation `wiki-ingest`. Acceptable для cold path (UC-07 latency 5 min budget).
- **Two-script coordination.** `wiki-ingest` пишет файлы, MVP индексирует. Нужны атомарность (manifest emit) и idempotency (R-07.4 / `source_state`).

### Neutral

- **TASK.md рефакторинг.** ~30% переписывания R-06.3, R-08, R-11, UC-07, §6.1. Объём управляемый, но не trivial.
- **Текущие правки TASK.md (5/25 session) остаются валидными** — type-mapping, R-07.5, subprocess contract — все станут частью integration spec, просто реорганизуются.

## Implementation Path

**Phase 1 (NOW):** Зафиксировать решение.
- [x] `docs/adr/ADR-001-wiki-ingest-integration.md` (этот файл)
- [ ] `docs/WIKI-INGEST-V1.1-CONTRACT.md` — спека того, что v1.1 должен предоставить
- [ ] Маркер `ARCHITECTURAL-PIVOT-PENDING` в TASK.md §0

**Phase 2 (Wait for wiki-ingest v1.1):** Развитие глобального skill'а.
- Implement v1.1 contract (см. WIKI-INGEST-V1.1-CONTRACT.md)
- Reach stability + version-pin

**Phase 3 (Coordinated rework):** Однократный, целостный реворк TASK.md.
- Rewrite R-06.3, R-08, R-10, R-11 под Option I
- Удалить §6.1 "Karpathy-deviation" (становится неприменимой)
- Сжать UC-07 (становится thin wrapper)
- Add new R-XX vault-layout (matching `wiki-ingest` schema)
- Vendor `wiki-ingest` v1.1 как git-submodule
- Update ARCHITECTURE.md соответственно
- Re-run /vdd-adversarial на reworked TASK

**Phase 4 (Implementation):** Standard Epic E1-E5 execution с обновлённым scope.

## References

- [Reference/karpathy/llm-wiki.md](../Reference/karpathy/llm-wiki.md) — source pattern
- [tasks/task-002-wiki-mvp.md](../tasks/task-002-wiki-mvp.md) — MVP spec (Phase 3a archived 2026-05-27)
- [tasks/task-003-v3.1-wiki-extract-concepts.md](../tasks/task-003-v3.1-wiki-extract-concepts.md) — Phase 3b ship that consumes this contract via in-process dispatch (Decision-15+16)
- [reviews/TASK-vdd-adversarial-2026-05-25.md](../reviews/TASK-vdd-adversarial-2026-05-25.md) — adversarial review Pass 1
- [reviews/TASK-vdd-adversarial-2026-05-25-pass2.md](../reviews/TASK-vdd-adversarial-2026-05-25-pass2.md) — adversarial review Pass 2 (Zero-Slop)
- `~/.claude/skills/wiki-ingest/SKILL.md` — global wiki-ingest skill (v1.0)
- `~/.claude/skills/summarizing-meetings/SKILL.md` — base summary skill (precedent for git-submodule vendoring)
