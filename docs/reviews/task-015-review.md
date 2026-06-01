# TASK 015 Review

- **Date:** 2026-06-01
- **Reviewer:** Task Reviewer Agent (vdd-01-start-feature pipeline)
- **Status:** ⚠️ APPROVED WITH COMMENTS (2 MAJOR, 1 MINOR — fixable inline)

---

## General Assessment

The TASK is well-structured, covers all four requested issues (H-PERF-3, P-6, P-7, P-8),
and correctly scopes the fixes as additive / backward-compatible. The RTM has appropriate
granularity, and Use Cases have main + alternative scenarios. One architectural ambiguity
in the batch-apply + `--ingest` path needs clarification before Planning; two other
clarifications are minor.

---

## Comments

### 🟡 MAJOR — M-1: AC-015-8 and R-015-5(f) are ambiguous about `index_from_manifest` call count in batch mode

**Location:** R-015-5(f), AC-015-8

**Issue:** AC-015-8 says "assert `index_from_manifest` called once (not once per page)"
for a 2-source-page batch. But each source page produces its own manifest with its own
`log_event`. If `index_from_manifest` is called once total, how are N log_events handled?
The current `index_from_manifest` signature accepts a single manifest dict — combining N
manifests into one is a non-trivial aggregation.

**Proposed resolution:**
The fix for H-PERF-3 is connection reuse, not call-count reduction. For batch apply:
1. `index_from_manifest` is called once **per source entry** (N times for N pages), BUT
2. All N calls share ONE externally-provided repo (passed as an optional `repo` parameter).
3. `make_repo` is called exactly once for the entire batch-apply invocation.

Update R-015-2 sub-feature list to include:
> (g) `index_from_manifest` gains an optional `repo` parameter; when provided, it uses it
> instead of calling `make_repo` (and does NOT close it); caller owns the lifecycle.

Update AC-015-8 to:
> `test_apply_batch_with_ingest` — batch apply `--ingest` over 2 pages; assert `make_repo`
> called exactly once for the entire invocation (not once per source page or per concept
> page); `index_from_manifest` called N times with the shared repo.

This is a clean fix: `index_from_manifest(manifest, vault_id, vault_root, db_path=None, repo=None)`
with `repo` optional for backward compat.

---

### 🟡 MAJOR — M-2: R-015-2 missing the optional-repo extension for batch interop

**Location:** R-015-2 sub-features

**Issue:** R-015-2 describes single-call connection reuse for `index_from_manifest` but
does not mention the optional `repo` parameter needed by batch apply (see M-1). Without
it, the batch path opens N connections — defeating the purpose of R-015-2 for batch.

**Fix:** Add sub-feature (g) as described in M-1 above to R-015-2.

---

### 🟢 MINOR — N-1: UC-015-1 step 4 phrasing

**Location:** UC-015-1, step 4

**Issue:** "calls `index_from_manifest` with the same-or-new single repo (R-015-2)" —
"same-or-new" is ambiguous. The intent is "one repo, opened for this `apply` invocation".

**Fix:** Replace with "Apply opens one repo; calls `index_from_manifest` passing that repo
(R-015-2); all upserts and the log_event share the same connection."

---

## Checklist Results

| Check | Result |
|-------|--------|
| All 4 user issues covered (H-PERF-3/P-6/P-7/P-8) | ✅ |
| RTM has ≥3 sub-features per requirement | ✅ |
| Use Cases have actors, preconditions, main+alt scenarios | ✅ |
| Acceptance Criteria are verifiable pass/fail | ✅ (after M-1 fix) |
| Uses project terminology (`make_repo`, `vault_id`, `emit`, etc.) | ✅ |
| Respects architecture constraints (Decision-17, Decision-16, zero DDL) | ✅ |
| CWE-117/209 non-regression stated (R-015-NF4) | ✅ |
| Backward compat stated (R-015-NF2) | ✅ |
| No unrequested features | ✅ |
| Internal consistency | ✅ (after M-1/M-2 fix) |

---

## Final Recommendation

**APPROVED WITH COMMENTS.** Apply M-1 (update R-015-2 sub-feature (g) + reword AC-015-8)
and N-1 (UC-015-1 step 4) inline before proceeding to Architecture. No re-review needed —
changes are small and additive; they clarify design without changing scope.
