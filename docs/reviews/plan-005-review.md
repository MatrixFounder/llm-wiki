# Plan Review — TASK 005 (entity-resolution / Epic 7 R-4 + R-5 + wiki-merge)

- **Date:** 2026-05-29
- **Reviewer:** Plan Reviewer (self-correction loop, VDD `/vdd-plan`)
- **Status:** ✅ **APPROVED** (0 critical, 0 major; 1 minor folded in, 2 minor → Development)
- **Checklist:** `plan-review-checklist` v1.0 + `tdd-stub-first` + `planning-decision-tree`
- **Scope:** [docs/PLAN.md](../PLAN.md) + 17 task files [docs/tasks/task-005-01..17-*.md](../tasks/)

## General Assessment

The plan decomposes TASK 005 into **17 atomic, testable beads across 4 phases** with a correct spine-first ordering: schema v3 + the reindex round-trip (`is_candidate` read, alias mirror, **AM-3 ref-canonicalization**) land before any CLI, because the ADR-002 §D8 durability round-trip (UC-14/UC-15) is the binding acceptance gate and every later bead depends on it being closed. RTM traceability is strict (§5 maps every R-4.x/R-5.x **and** AM-3 to ≥1 bead; every checklist item is `[R-x.y]`-tagged). Stub-First is explicit and per-bead (§3 table gives Phase-1 stub + RED test + Phase-2 logic for each code bead), with a stated **green-throughout** invariant (abstractmethod + `SQLiteRepository` stub land together so the class is always instantiable). The DAG (§2) is acyclic with a clear critical path (01→03→08→11→16→17) and named parallel-safe sets. The risk register (§6) is concrete and pre-empts the two real traps a naïve implementation would hit (R-1 per-ref canonicalization N×M; R-6 `get_backlinks` alias-blindness).

## Use Case Coverage (traced)

| UC | Covered by | Verdict |
|---|---|---|
| UC-09 confirm | 005-05, 005-09 | ✅ |
| UC-10 auto-promote | 005-05, 005-09 | ✅ |
| UC-11 alias mgmt | 005-06, 005-07, 005-10 | ✅ |
| UC-12 search expansion | 005-04, 005-07, 005-12 | ✅ |
| UC-13 lint collision | 005-07, 005-13 | ✅ |
| UC-14 confirm/alias durability | 005-02, 005-03, 005-16 | ✅ |
| UC-15 merge durability | 005-03, 005-04, 005-08, 005-11, 005-16 | ✅ |

No orphan UCs; no orphan RTM IDs. AM-3 (architecture decision) is explicitly carried as a planned bead (005-03), not lost between phases.

## Structure Verification (Stub-First)

- ✅ Every code bead has a distinct Phase-1 (stub + RED test) and Phase-2 (logic) row in §3.
- ✅ Dependency order respects layering: DDL → reindex spine → DAL → CLIs → docs → acceptance.
- ✅ Docs/verify-only beads (005-15, 005-17) and regression-only (005-14) correctly skip the stub phase, stated explicitly.
- ✅ Task files exist for all 17 beads; naming matches `task-{ID}-{SubID}-{slug}.md`; each has Goal / Changes (exact paths + method signatures) / Test Cases / Acceptance Criteria / Notes.

## Comments

### 🔴 CRITICAL — None.
### 🟡 MAJOR — None.

### 🟢 MINOR
- **pm-1 (FOLDED IN):** plan-review-checklist §2.4 (tdd-strict for critical components) was initially unaddressed. **Fixed:** PLAN §9 item 7 now designates **005-03, 005-08, 005-16** as `skill-tdd-strict` (high-assurance) beads; the rest use standard Stub-First. *Resolved in-place.*
- **pm-2 (→ Development):** 005-08 `merge_entities` ref-dedup SQL shape (UPDATE-then-resolve-conflict vs INSERT-OR-IGNORE-into-temp + DELETE) is left to the developer. Both are set-based; pin the exact statement in 005-08 Phase-2 and assert no per-row Python loop (consistent with Risk R-1).
- **pm-3 (→ Development):** the new-CLI exit-code spaces (005-09/10/11) are illustrative per the architecture review; finalise the numeric map against the `wiki-extract-concepts` convention when the first CLI lands, and keep the three CLIs' spaces independent (no cross-binary collision — already noted in interfaces.md).

## Checklist Result

| Group | Item | Verdict |
|---|---|---|
| 1 Use Case Coverage | Total coverage / Traceability table | ✅ (§4 + §5) |
| 2 Structure & Formalism | Stub-First / Dependencies / Phasing / **Strict mode** | ✅ (pm-1 folded in) |
| 3 Task Descriptions | Existence / Naming / Sections / Depth | ✅ (17/17, signatures present) |

## Final Decision

**APPROVED — PROCEED to Development (`/vdd-develop-all` or per-bead `/vdd-develop`).** Start with **005-01** (schema v3 — blocks all alias work); {005-02} runs in parallel; {005-04, 005-05, 005-06} unlock once 005-01 lands. The §D8 acceptance gate (005-16) and regression gate (005-17) close the task.

```json
{ "review_file": "docs/reviews/plan-005-review.md", "has_critical_issues": false }
```
