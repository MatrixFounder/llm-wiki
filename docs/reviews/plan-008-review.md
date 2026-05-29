# Plan Review — TASK 008 `wiki-verify-multi` (R-8)

**Date:** 2026-05-29
**Reviewer:** plan-reviewer (VDD gate, independent subagent)
**Status:** APPROVED WITH COMMENTS → all comments resolved in place (see Dispositions)

## General Assessment

A high-quality, deeply-grounded plan that decomposes the architecture's three-part
durability spine, the off-by-default skill, and the schema bump into 11 atomic,
single-responsibility beads. Every load-bearing grounded fact was independently
re-verified against the live source tree (`sql/wiki-index-v2.sql` CHECK enums +
`index_meta` view + `user_version=4`; `layout.py` `HOST_ONLY_SUBDIRS`→`PAGE_SUBDIRS`/
`SCAFFOLD_DIRS` flow; `functional-architecture.md:51` `check/record_verify_state` +
direct-DAL self-index). All accurate.

The plan correctly captures the arch-review M-1 finding as a first-class,
separately-tested bead (008-02) with an explicit indexed-not-skipped regression
guard (008-09 TC-ACC-03), Stub-First + green-throughout are honoured at every
boundary, the DAG is acyclic with a correct critical path, and no settled decision
(Q-008-a/b/c/e, the `answer_hash` rename) is contradicted. No CRITICAL issues.

## Verification-duty results
1. RTM coverage 1-to-1 (all R-8.x + R-8.5e + AM-3 + C-8/NFR-7 + UC-22..28 mapped). **PASS** (precision gap M-3).
2. Stub-First per-bead + §3 table; green-throughout (008-04 ABC+impl together; 008-01 version-pin in-bead). **PASS.**
3. M-1 durability-spine capture: 008-02 carries `TYPE_MAPPING`; 008-09 TC-ACC-03 guards indexed-not-skipped; invariant #2 names the three-part change. **PASS.**
4. Atomicity 0.25–1.25 day, single-responsibility; clean write/index split; 008-08 isolated. **PASS.**
5. DAG acyclic; 008-07 dep 008-01 AND 008-02; 008-09 dep full spine + 06/07. **PASS** (M-1-plan phrasing gap).
6. Strict-TDD 008-03/06/09 right; 008-07 under-classified. **MOSTLY PASS** (M-2).
7. Risk register covers R-1..R-10 with bead-tied mitigations. **PASS.**
8. No contradiction of settled decisions; R-8-only; layout-agnostic grep guard is acceptance. **PASS.**

## Findings + Dispositions

### 🔴 CRITICAL — None.

### 🟡 MAJOR

**M-1-plan — 008-09's "RED before 008-03 / GREEN after" phrasing is misleading** (it can't run until 006/007 land, so it's a whole-spine joint gate, not a per-bead gate on 008-03). **[FIXED]** Reworded 008-09 AC line 4 + Notes: the test is collected (skipped) from creation and un-skips→GREEN only once 008-01/02/03 **and** 008-06/07 all land; the still-skipped state is expected, not a regression. §1/§2 dependency edges were already correct and unchanged.

**M-2 — 008-07's byte-identical-rows symmetry is the §D8 keystone 008-09 leans on, yet 008-07 wasn't strict-TDD.** **[FIXED]** Marked 008-07 strict-TDD in PLAN §1 (bead line) + §9 item 6 (with rationale: if `apply`'s `verifies` row differs from a `reindex._build_page` rebuild, 008-09's round-trip comparison is vacuous) + the 008-07 bead header banner; TC-UNIT-01 (byte-identity) is now written test-first.

**M-3 — §1 bead-header tags omit `C-8/NFR-7` though §5 maps it to 008-02/05/10, weakening the 1-to-1 audit.** **[FIXED]** Added `C-8/NFR-7` to the §1 headers of 008-02, 008-05, 008-10 so §1 and §5 agree.

### 🟢 MINOR

**m-1 — Risk register completeness.** No action — all briefed risks (R-1..R-10) present; R-6/R-8 are appropriate additions. Noted for completeness.

**m-2 — 008-08/008-11 `.AGENTS.md` ownership was a soft "if cleaner" hand-off.** **[FIXED]** Made deterministic: 008-11 (the doc-sweep bead) owns **all** `.AGENTS.md` edits incl. the `skills/.AGENTS.md` SECURITY-SENSITIVE note; 008-08 dropped the "if cleaner" clause and ships only skill/command/workflow files + symlinks.

**m-3 — 008-05's missing-cite (`get_page` returns no row) behaviour was under-specified ("record or skip").** **[FIXED]** Single chosen behaviour: a cited slug with no `pages` row is **excluded from the `examined` set** and recorded in a `missing_cites` report field (so a finding citing it correctly trips `FINDING_SOURCE_NOT_EXAMINED` in 008-06). No crash.

## Final Recommendation

**APPROVED.** The plan faithfully decomposes the approved architecture, captures the
M-1 durability-spine trap, honours Stub-First + green-throughout, and contradicts no
settled decision. All three MAJOR (precision/rigor) and two actionable MINOR items
are resolved in place by the planner. Execution may begin with **008-01** (schema
v4→v5) and the parallel **008-04** (verify-state DAL). The `/vdd-plan` phase is
complete.
