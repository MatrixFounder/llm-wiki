# Task Review — TASK 007 (`wiki-query` RAG layer / Epic 7 R-6)

- **Date:** 2026-05-29
- **Reviewer:** Task Reviewer (Analysis→Architecture gate, VDD mode)
- **Status (round 1):** 🔴 **BLOCKING** (1 CRITICAL + 3 MAJOR + 4 MINOR)
- **Status (round 2):** ✅ **APPROVED** — all findings addressed in TASK.md rev 2 (see Resolution Log).
- **Checklist:** `skill-task-review-checklist` v1.0 + anti-hallucination grounded-fact audit.

## General Assessment

Strong, well-grounded spec. Scope correctly fenced to **R-6 only** (R-7/R-8
deferred + gated — matches operator decisions D-007-1/2 and the ROADMAP).
Decision-17 `prepare`/`apply` split correctly modelled on shipped
`wiki-extract-concepts`. RTM granular; Use Cases carry binary acceptance
criteria. Most §1.1 grounded facts verify exactly against the repo. The one
load-bearing falsehood (round 1) was the durability round-trip claim — fixed in
rev 2.

## Grounded-fact audit (anti-hallucination — priority #1)

Verified TRUE against the repo: `pages.type` allows `'query'`
(`sql/wiki-index-v2.sql:162-164`); `TYPE_MAPPING["query"]` (`normalization.py:86`);
`page_entity_refs.ref_type` allows `'cited'` (`:194-196`);
`log_events.event_type` allows `'query'` (`:225`); `source_state` generic table
(`:341-349`); `_queries` NOT in `PAGE_SUBDIRS` and `_PATH_TYPE_FALLBACK` covers
only `_concepts`/`_entities` (`layout.py:30-32`, `normalization.py:106-109`);
`_sanitize_markdown_text` (`wiki_extract_concepts.py:485`); atomic-write +
symlink-refuse + `validate_inside_vault` (`_common.py`); `wiki-search` retrieval
chain (`wiki_search.py:37-105`); DAL methods exist; `PRAGMA user_version = 4`;
KNOWN_ISSUES H-6 / H-PERF-3 / P-8 / P-2 / CWE-117/209 accurately characterised.

Verified FALSE (round 1, now fixed): "`wiki-reindex --full` re-materialises
`cited` refs from the `cites:` frontmatter alone" — see C-1.

## Comments (round 1)

### 🔴 CRITICAL (BLOCKING)

**C-1 — UC-20 / R-6.5d durability round-trip is unimplementable as scoped; the
"zero structural change beyond `layout.py`" claim (C-5 / D-007-4) is false.**
Reindex ref-rebuild path: `reindex_full` → `ManualSourceAdapter.fetch()` →
`extract_wiki_links(body_text)` → `replace_refs(...)`. (1) `extract_wiki_links`
(`parsing.py:43`, regex `:15`) scans **body only** — `cites:` frontmatter is
invisible. (2) Every ref is hardcoded `ref_type="mentioned"` (`manual.py:44`).
(3) The frontmatter read-side in reindex (`is_candidate`/`aliases:`) is gated on
`_concepts`/`_entities` subdirs (`reindex.py:284`) — `_queries` pages never reach
it. So after a full reindex, a query page's citations are lost (if only in
`cites:`) or re-materialise as `'mentioned'` (if body wikilinks) — never
`'cited'`. This is the exact bug TASK 005 fixed for `aliases:` (its §1.1 line 48
+ RTM R-4.1/R-5.3). **Fix:** add an RTM item (R-6.5e) extending the reindex
ref-rebuild to parse `cites:` → `ref_type='cited'` for `type=query` pages, and
correct C-5/D-007-4 to admit the second structural change (reindex read-side, in
addition to `layout.py`; schema/DDL claim stays true — no DDL, `user_version`
stays 4).

### 🟡 MAJOR

**M-1 — NFR-2 "no raw SQL in the skill" vs the `source_state` precedent.** The
precedent (`wiki_extract_concepts.py:870-901`) accesses `source_state` via raw
SQL through `repo._connect()`; no `record_source_state`/`check_source_state` DAL
method exists. **Fix:** make NFR-2 honest — add proper
`record_query_state`/`check_query_state` `IndexRepository` methods (cleaner than
the precedent's `_connect()` shortcut), per the H-PERF-3 "real method, not
`main(argv)`" lesson.

**M-2 — R-6.4d self-index path risks re-introducing H-PERF-3 / P-8.** R-6.4d
points at the `--ingest`/`index_from_manifest`→`main(argv)`-per-row pattern,
which IS the open SEV-2 N+1 (`KNOWN_ISSUES H-PERF-3`,
`_manifest_consumer.py:91-139`) — and NFR-5 forbids it. **Fix:** specify `apply`
self-indexes the single query page via direct `upsert_page` + `replace_refs` on
one repo connection, NOT via the manifest machinery (one page → manifest
machinery is unwarranted regardless).

**M-3 — UC-21 / R-6.7d grounding key namespace ambiguity.** `prepare` hits carry
`{vault_id, slug, project}` (slug unique only per `(vault_id, project)`), while
Q4 proposes `cites:` are `project/slug`. The grounding check's identity tuple is
unpinned → false-accept/reject hazard at the anti-hallucination gate. **Fix:**
pin the comparison key to the full `project/slug` (matching Q4), recorded from
`prepare` and validated in `apply`.

### 🟢 MINOR

- **m-1** `--limit` default 10 contradicts "exactly like `wiki-search`" (whose
  default is 20, `wiki_search.py:22`). Keep 10 (Q5); drop "exactly like" for the
  default (keep it for flag semantics).
- **m-2** `concept-extraction` source-of-truth skill lives at repo-root
  `skills/concept-extraction/` (symlinked into `.agent/skills/`); cite repo-root.
- **m-3** `sql/wiki-index-v2.sql` filename says "v2" but encodes `user_version`
  4 — note the filename is legacy so a reader doesn't mistake it for stale v2.
- **m-4** Q3 (hash question only vs question + retrieved-slug-set) is
  borderline-blocking: it decides UC-17 `is_unchanged` semantics. Elevate from
  "non-blocking" to "decide in Architecture before R-6.6 is planned."

## Resolution Log (round 2 — TASK.md rev 2)

- **C-1 → FIXED:** added **R-6.5e** (reindex read-side: `type=query` pages'
  `cites:` → `ref_type='cited'`, mirroring TASK 005 R-5.3); rewrote **C-5**,
  **D-007-4**, **R-6.4b**, **R-6.5d**, **UC-20**, and **NFR-1** to state the
  structural change set = `layout.py` **+** reindex ref-rebuild read-side (schema
  stays DDL-free, `user_version` 4). Added grounded-fact rows for
  `manual.py:44` / `parsing.py:43` / `reindex.py:284`.
- **M-1 → FIXED:** NFR-2 + C-7 now specify new `record_query_state`/
  `check_query_state` DAL methods (no `repo._connect()` raw SQL in the skill).
- **M-2 → FIXED:** R-6.4d + NFR-5 now mandate direct `upsert_page` +
  `replace_refs` on one connection; explicitly forbid `index_from_manifest`/
  `main(argv)` (H-PERF-3).
- **M-3 → FIXED:** R-6.7d + UC-21 + C-3/C-8 pin the grounding/citation key to the
  full `project/slug` tuple.
- **m-1..m-4 → FIXED:** `--limit` wording; `concept-extraction` path; schema
  filename note; Q3 elevated to "decide in Architecture before R-6.6."

## Final Recommendation

Round 1: route back to analyst for one revision (narrow, fixable).
Round 2: **APPROVED** — proceed to the Architecture phase. Scope fence clean (no
R-7/R-8 leakage); Decision-17 split correct; durability story now matches the
reindex pipeline.
