# TASK 019 Review — `sync-resummarize-policy`

- **Date:** 2026-06-07
- **Reviewer:** Task Reviewer (self-review, `03_task_reviewer` + `task-review-checklist`)
- **Status:** ✅ **APPROVED WITH COMMENTS** (no BLOCKING; ready for operator read →
  Architecture boundary)

## General Assessment

TASK 019 fully covers the cumulative operator request: re-summarize only on `--force`
or when no summary exists (E1), the operator-chosen **D1 ∪ D2** semantics with both D2
forms — provenance-ref (E2.2) and structural mirror (E2.3) — rules **in YAML** (E3.1),
**per-folder overrides** (E3.2, the late-added requirement), and **worked examples**
throughout (UC-1..6: tree + config + walkthrough each, as explicitly requested). RTM
granularity ≥ 3 sub-features/row; Acceptance Criteria are binary; scope is guarded
(§6); back-compat + zero-DDL + no-`anthropic` invariants are pinned (E4.2). Terminology
matches the codebase (`source_state`, `frontmatter_json`, Decision-17, `_raw/.staging`),
and the change is correctly framed as a gate that can only turn `ingest`→`skip`
(architecture-compatible, non-invasive to the executor contract).

## Comments

### 🔴 Critical (BLOCKING)
- None.

### 🟡 Major
1. **OQ-1 (per-folder override mechanism)** — ✅ **RESOLVED by operator (2026-06-07) →
   Option A (cascade): folder rules override global, deepest-wins.** E3.2 + UC-4 updated;
   AC-5 (mechanism-agnostic) still holds. No longer open. *(Also resolved: OQ-2 mirror N:1
   + configurable dir names; OQ-3 rel-path match; OQ-4 `exclude` kept, precedence
   `exclude > policy`; OQ-5 `detect` default `{source_state: true}`; OQ-6 `--force`
   zone-scoped + `mode: always` for persistence.)*
2. **D2a depends on index currency** — a manually-authored summary not yet
   `wiki-reindex`-ed is invisible to the provenance query → false "no summary" →
   re-ingest. *Fix applied:* added E2.2(f) + expanded OQ-3 with the recommendation to
   keep `scan` index-backed for D2a and rely on the **D1 ∪ D2b (mirror, FS-based)**
   union for the not-yet-indexed case. Resolved at spec level.

### 🟢 Minor
- Cross-reference hygiene: an initial "Constraints §4a" pointer was corrected to OQ-3
  (no such section existed). Fixed.
- AC-9 honestly softens to "a new read-only DAL method is acceptable (no schema
  change)" — consistent with TASK 018's same correction; not a defect.

## Final Recommendation

**All six Open Questions are now operator-resolved (2026-06-07)** and folded into the RTM /
Use Cases / Acceptance Criteria. The Analysis artifact is complete and internally
consistent. **Ready for the Architecture phase** — whose job is now pure design of the
locked decisions: the Option-A cascade resolver (read + deepest-wins deep-merge, per-dir
memoization, symlink/size/anchor hardening), the `$def Resummarize` schema (incl.
`mirror.match ∈ {stem-relpath, group-key}` + the extended `key:` block —
`raw_regex`/`summary_regex` named groups + `template` + `flags` — **ReDoS-guarded via the
TASK 017 infra**), the D2a `frontmatter_json` provenance query (rel-path, list-valued) +
**`sources:` writeback** on generated summaries, and `exclude > policy` precedence.
