# Architecture Review — 001 wiki-mvp (ITERATION 2)

**Date:** 2026-04-28
**Reviewer:** Architecture Reviewer Agent
**Iteration:** 2 (post-fixes)
**Status:** **APPROVED WITH COMMENTS** — 0 CRITICAL, 2 MAJOR (new), 4 MINOR

---

## Iter1 Issue Closure

| Issue | Status |
|---|---|
| C-1 FTS5 trigger pattern | ✅ MOSTLY closed (see M-new-1) |
| C-2 entities_fts orphaned | ✅ Closed cleanly |
| C-3 SourceAdapter contract | ✅ Closed |
| M-1 R-26.3 missing | ✅ Closed |
| M-2 R-07/R-08 ambiguity | ⚠️ Partially closed (see M-new-2) |
| M-3 replace_refs atomicity | ✅ Closed |
| M-4 IndexRepository method drift | ✅ Closed |
| M-5 ABC over-engineering | ✅ Closed (test-isolation justification) |
| M-6 10K-char limit | ⚠️ Defer acknowledged |
| M-7 Q-A1 transcript subprocess | ⚠️ Defer acknowledged |
| All 5 minors | 2 closed (m-1, m-2), 3 deferred |

---

## New Findings

### 🟡 M-new-1 (MAJOR): FTS5 contentless `DELETE FROM <fts>` is invalid SQL

В FTS5 contentless mode прямой `DELETE FROM pages_fts WHERE rowid = ?` — runtime error («cannot DELETE from contentless fts5 table»). Корректный idiom — `'delete'` command:

```sql
INSERT INTO pages_fts(pages_fts, rowid, slug, project, title, tldr, body_excerpt, tags)
VALUES('delete', old.rowid, old.slug, ...);
```

Альтернатива — добавить `contentless_delete=1` flag (SQLite ≥ 3.43; bump from 3.38 в §6.3).

Recommend: `'delete'` command pattern (no version bump).

### 🟡 M-new-2 (MAJOR): wiki-index-upsert skill vs adapter direct-call — duplication

§3.2 wiki-index-upsert описывает 2 mode'а; §3.2 «Adapter <-> repository contract» утверждает adapter calls `repo.upsert_page` сам. Который путь канонический?

Recommend Option A: adapter всегда вызывает `repo.upsert_page(...)` напрямую. `wiki-index-upsert` skill — only standalone entry for already-on-disk files. Уточнить L271.

### 🟢 m-new-1 (MINOR): R-06.3 transcript flow AC weak

Verification Map L993 hand-wave «UC-02 by reference». Plan phase должен add explicit AC в I-3.3 для transcript→manual delegation.

---

## Final Recommendation

**APPROVED WITH COMMENTS.** Plan phase **может** стартовать.

Action items для Plan phase:
1. **M-new-1**: replace FTS5 DELETE pattern с `'delete'` command (Plan task в Epic E1 I-1.2 AC).
2. **M-new-2**: clarify wiki-index-upsert L271 (architect amend).
3. **m-new-1**: add explicit transcript→manual delegation AC в I-3.3.

```json
{"review_file": "docs/reviews/architecture-001-review-iter2.md", "has_critical_issues": false, "iteration": 2}
```
