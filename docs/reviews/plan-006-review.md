# Plan Review — TASK 006 (consolidation-hardening)

- **Date:** 2026-05-29
- **Reviewer:** Plan Reviewer (self-correction, VDD `/vdd-plan`)
- **Status:** ✅ **APPROVED** (0 critical, 0 major; 1 minor → Dev)
- **Checklist:** `plan-review-checklist` v1.0 + `tdd-stub-first`

## Assessment
6 beads, schema-first ordering (006-01 blocks 006-02/006-05; 006-03/006-04 are
independent; 006-06 gates). RTM matrix (§4) maps every in-scope ledger id
(P-5/L-5/L-2/MIG/L-8/F12c/P-10/F12b/L-1/L-6/L-7) to a bead; the deferred set stays
out (fenced in TASK §1). Stub-First table (§3) gives a RED-first test per code bead;
006-04 is correctly framed as a pure refactor guarded by the existing
mentions/auto-promote/merge/durability suite. DAG acyclic, critical path
001→005→006. Risk register pre-empts the two real traps (generated-column safety —
already cleared in arch m-1; P-10's `aliases`-in-`frontmatter_json` assumption —
gated with a fallback).

## Use Case Coverage
| UC | Beads |
|---|---|
| UC-16 (v3→v4 migration) | 006-01 |
| UC-17 (lint without 2nd YAML sweep) | 006-05 |
| UC-18 (entity display name survives) | 006-03 |
| UC-19 (generated event_date) | 006-01, 006-02 |

## Comments
- 🔴 CRITICAL — None. 🟡 MAJOR — None.
- 🟢 **pm-1 (→ Dev, 006-05):** the DB-sourced lint scan must first confirm `aliases`
  is present in `pages.frontmatter_json` for concept/entity rows (carried from
  task m-2 / arch am-1). The bead already states the pre-flight + fallback; ensure
  the dogfood collision fixtures gate the equivalence.

## Checklist
| Group | Verdict |
|---|---|
| 1 UC coverage / traceability | ✅ (§4 RTM + UC map) |
| 2 Stub-First / deps / phasing | ✅ (§3 table; schema-first) |
| 3 Task files (6/6) / naming / sections | ✅ |

## Decision
**APPROVED — PROCEED to `/vdd-develop-all`.** Start 006-01 (schema v4); {006-03, 006-04} may run any time.

```json
{ "review_file": "docs/reviews/plan-006-review.md", "has_critical_issues": false }
```
