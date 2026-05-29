# Task Review: TASK 008 — `wiki-verify-multi` (R-8)

**Date:** 2026-05-29
**Reviewer:** task-reviewer (VDD gate, independent subagent)
**Status:** APPROVED WITH COMMENTS

## General Assessment

A high-quality, audit-ready VDD specification. The RTM is granular (10
requirements R-8.1..R-8.10, each with 3–5 binary sub-features), the four
operator-confirmed structural decisions are faithfully encoded (D-008-1..4) and
not re-litigated, and the operator's binding layout-agnostic constraint is
correctly threaded as **C-8 + NFR-7 + UC-28 + D-008-6** exactly as mandated. The
scope fence (C-4) cleanly holds R-8-only and explicitly keeps R-7 `wiki-research`
independent.

**All 13 §1.1 grounded-fact claims were independently verified against the actual
repo — every one is accurate.** This is the load-bearing section and it passed
adversarial inspection; nothing in it would mislead Architecture.

Verified claims (file:line confirmed):
- `pages.type` CHECK = `('summary','concept','query','brief','research','index')`
  at `sql/wiki-index-v2.sql:162-164` — **no `'verification'`** ✓; `TYPE_MAPPING`
  (`normalization.py:74-94`) has no `verification` key ✓.
- `page_entity_refs.ref_type` CHECK = `('mentioned','defined-here','related','cited')`
  at `:194-196`; PK `(vault_id, page_slug, page_project, entity_slug, ref_type)`
  at `:201` — **no `'verifies'`** ✓.
- `log_events.event_type` CHECK at `:225-230` — **no `'verify'`** ✓.
- `pages_fts_{ai,ad,au}` triggers at `:371-386` index every row, no `type`
  filter → verification pages FTS-searchable automatically ✓.
- `index_meta` view at `:393-402` filters `type IN ('summary','concept','query')` ✓.
- `PRAGMA user_version = 4` at `:452` ✓.
- R-6.5e read-side: `_cited_refs_from_frontmatter` at `reindex.py:91-147`;
  `if db_type == "query":` branches in `reindex_delta` (~237) and `reindex_full`
  (~350), both unioned into the single `replace_refs` ✓.
- `check_query_state`/`record_query_state` at `repository.py:380-397` ✓.
- `search_pages(..., exclude_types=...)` at `repository.py:120-127` ✓.
- `HOST_ONLY_SUBDIRS = (QUERIES_SUBDIR,)` + `PAGE_SUBDIRS` composition at
  `layout.py:48-57` ✓.
- `pages.file_path` is a stored vault-root-relative path (`:166`,
  `UNIQUE(vault_id, file_path)`) → layout-agnostic source access via `file_path`
  is genuinely possible ✓.
- `_PATH_TYPE_FALLBACK` at `normalization.py:110-131` ✓.

**Consistency checks all pass:** the "NOT zero-DDL" stance is internally coherent
everywhere (C-5, D-008-5, R-8.9, §1.1 DDL #1) with zero leftover "zero-DDL" claim.
The exit-code scheme is coherent with `wiki-query`'s conventions
(`skills/wiki-query/SKILL.md`: 0 success / 1 argparse / 2 input+TOCTOU / 4
apply-validation): NO_SOURCES=2, ANSWER_CHANGED=2 (the QUESTION_CHANGED analog),
FINDING_SOURCE_NOT_EXAMINED/INVALID_VERDICT=4 (the CITATION_NOT_RETRIEVED analog),
and **VERDICT_FAIL=6 is cleanly distinct from all error codes 1/2/4** — a
deliberate non-error verdict signal that won't collide. Decision-17 purity (no
`import anthropic`) is consistent throughout. The §D8 Class A/B/C assignment
(NFR-1) matches ADR-002 §D8: verdict markdown = Class A, `pages` row + refs =
Class B (reindex-rebuildable), `source_state` = Class C.

**PK collision-freedom verified:** a verdict page can simultaneously hold
`verifies` (→query), `cited` (→source), and body `mentioned` refs to the same
target — all distinct because `ref_type` is part of the composite PK. The TASK
correctly relies on this (R-8.4b).

No 🔴 CRITICAL and no 🟡 MAJOR issues. The TASK is approved to proceed to
Architecture. The comments below are non-blocking polish items.

## Comments

### 🔴 CRITICAL
None.

### 🟡 MAJOR
None.

### 🟢 MINOR

**M-1 — Cited commit hashes (reviewer's git view was stale → FALSE POSITIVE,
disposition recorded).** The reviewer flagged that HEAD `81d8abf` (line 26) and
predecessor R-6 `c6c249d` (line 20) did not appear in its git view (which showed
`ba4fa92` as latest). **Orchestrator triage:** the reviewer subagent inherited
the *session-start* gitStatus snapshot (`ba4fa92`), which predates the TASK 007
commits. `git log` confirms `81d8abf fixing task-007`, `37dbcad task-007 review`,
`c6c249d feat(task-007)` are the **real current commits** — the hashes in
`docs/TASK.md` are correct. **No change required.**

**M-2 — Q-008-a vs R-8.9(a) cross-note. [FIXED]** R-8.9(a) hardcoded `'verifies'`
while Q-008-a presents `'verifies'` vs `'cited'` as open. Folded in a cross-note
in R-8.9(a): "per Q-008-a's proposed default; if Architecture instead reuses
`'cited'`, R-8.5e/C-3/R-8.4b collapse accordingly — this sub-feature does not
foreclose Q-008-a."

**M-3 — UC-28 grep guard widened. [FIXED]** UC-28's forbidden-literal list was an
enumerated subset; widened to assert against **every `PAGE_SUBDIRS` member**
(`_sources`/`_concepts`/`_entities`/`_queries`/`_verifications`), so the
query-page read path is layout-agnostic too — making the C-8 guarantee airtight.

### Borderline-blocking open question — resolved correctly
Q-008-c (does `prepare` read `cites:` vs re-retrieve) is correctly flagged
borderline-blocking yet **correctly NOT blocking the TASK**: it carries a stated,
well-justified proposed default ("read `cites:`" — verify the answer as filed,
avoiding the Q-007-1 double-FTS cost) and is an Architecture/Planning decision,
not a spec gap. The remaining Open Questions (Q-008-a/b/d/e/f/g) are genuine
implementation-level deferrals with proposed defaults — none hides a true blocker.

## Final Recommendation

**APPROVED WITH COMMENTS — proceed to Architecture.** No revision round through
`analyst` is required. M-2 and M-3 are folded into `docs/TASK.md`; M-1 is a
false positive (correct hashes, stale reviewer git view). Architecture should
focus its scrutiny on the single biggest structural cost the TASK itself flags:
the **v4→v5 DDL bump + the R-8.5e reindex read-side** (the §D8 durability spine),
and should resolve Q-008-c before R-8.1/R-8.6 are decomposed.
