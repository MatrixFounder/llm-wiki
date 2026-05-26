# Architecture Review — 001 wiki-mvp

**Date:** 2026-04-28
**Reviewer:** Architecture Reviewer Agent
**Target:** `docs/ARCHITECTURE.md`
**Status:** **BLOCKING** — 3 CRITICAL, 7 MAJOR, 5 MINOR

---

## General Assessment

Архитектура хорошо проработана для MVP (YAGNI calls, traceability к TASK, продуманный hybrid Karpathy + cybos + iCloud-aware). Layered Architecture (L1–L5) appropriate; SQLite-default с Postgres-opt-in DAL хорошо обоснован. Security defensible.

Однако несколько **конкретных data-model и contract bugs** проявятся как data corruption, runtime failures или scope creep при имплементации.

---

## Critical Issues

### 🔴 C-1: FTS5 trigger pattern unsound для `content='pages'`

`pages_fts` declared с `content='pages'` (external-content mode), но триггеры insert/delete по `rowid` directly. В external-content mode правильный pattern требует `'delete'` command или contentless mode.

**Symptom**: UPDATE pages → stale FTS rows → duplicate hits. UC-03 search corruption.

**Fix**: либо drop `content='pages'` (contentless mode — recommended), либо rewrite triggers per FTS5 §4.4.2.

Same applies to `interactions_fts`.

### 🔴 C-2: `entities_fts` без triggers — orphaned FTS index

`entities_fts` declared but no maintenance triggers. Comment says "future Epic 7" but table создаётся в v1 DDL.

**Fix**: drop из v1 DDL (defer to Epic 7 migration), либо добавить triggers.

### 🔴 C-3: `SourceAdapter` abstract contract NOT defined в ARCHITECTURE

§2.1 list functions, но ни abstract method signatures, ни `SourceItem`/`SourceOutput` shapes, ни error model.

**Fix**: добавить explicit "SourceAdapter Interface" subsection в §3.2.

---

## Major Issues

- **M-1**: Verification Map gap — R-26.3 not covered.
- **M-2**: R-07/R-08 ambiguity — `wiki-index-upsert` vs `wiki-index-render` host components не ясны в Verification Map.
- **M-3**: `replace_refs` atomicity unverified для FTS sync — нужен explicit transactional boundary.
- **M-4**: `IndexRepository` method count differs ARCHITECTURE vs SQLITE-VS-POSTGRES.md.
- **M-5**: `IndexRepository` ABC для single MVP backend — over-engineering risk; defensible если есть test isolation argument.
- **M-6**: `wiki-source-light` 10K-char hard limit без обоснования.
- **M-7**: Subprocess contract для `wiki-source-transcript` ↔ `summarizing-meetings` undefined (Q-A1 acknowledged but not resolved before Plan).

---

## Minor Issues

- **m-1**: Layered Architecture count: 4 vs 5 inconsistency.
- **m-2**: Mermaid diagram uses `SAL` and `SAL2` для two different things.
- **m-3**: §6.4 JSON sidecar shape not cross-referenced.
- **m-4**: `Migration Tools` (§2.1) mentions `benchmark.py` — не migration tool.
- **m-5**: §9.1 retry counts vs SLO budget unclear.

---

## Coverage Cross-check

14/18 fully covered, 3 partial (R-06, R-07, R-08), 1 sub-req gap (R-26.3).

---

## Final Recommendation

**Status: BLOCKING.**

Минимальные revisions:
1. Fix C-1 (FTS5 contentless mode).
2. Fix C-2 (drop `entities_fts` из v1).
3. Fix C-3 (add SourceAdapter Interface section).
4. Fix M-1, M-2 (Verification Map).
5. (Optional but recommended) M-3, M-4, M-7.

Остальное mostly cosmetic — не блокирует Plan phase.

---

```json
{"review_file": "docs/reviews/architecture-001-review.md", "has_critical_issues": true}
```
