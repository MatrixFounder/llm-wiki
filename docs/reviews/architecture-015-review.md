# ARCHITECTURE 015 Review

- **Date:** 2026-06-01
- **Reviewer:** Architecture Reviewer Agent (vdd-01-start-feature pipeline)
- **Status:** ⚠️ APPROVED WITH COMMENTS (1 MAJOR, 1 MINOR — fixable inline)

---

## General Assessment

The architectural changes for TASK 015 are **additive and backward-compatible**. No DDL.
The design correctly decomposes into: (a) a programmatic entry-point in `wiki_index_upsert`
with `main()` delegating to `upsert_one`, (b) an optional `repo` parameter on
`index_from_manifest` with clear lifecycle ownership, (c) a simple flag branch for P-6,
and (d) a batch surface for P-7 that naturally maps to per-entry isolation. The ARCHITECTURE.md
is in correct Index-Mode (375 lines index + chunked sections) and was updated in place.

---

## Comments

### 🟡 MAJOR — A-1: Per-entry transaction isolation in batch apply is unspecified

**Location:** `functional-architecture.md` — Concept Extractor, "Bulk-transaction semantics" +
new batch-apply design.

**Issue:** The existing single-page `apply` runs "all DB writes under a single `BEGIN
IMMEDIATE` transaction". For `apply --batch-candidates` with a shared repo, it is
**unspecified** whether each entry's DB writes commit independently or all-or-nothing.

The TASK specifies per-entry error isolation (one failure does not abort the batch), which
implies **independent commits per entry**. But the existing "single BEGIN IMMEDIATE"
wording could be misread as covering the whole batch.

**Consequence if not clarified:** a developer may inadvertently open one transaction across
all entries — one failed entry rolls back all successful ones, violating AC-015-6/7.

**Fix:** Add to the "Bulk-transaction semantics" paragraph:

> For `apply --batch-candidates`: each entry's DB writes (upsert_entity, replace_refs,
> source_state update) execute under their own independent `BEGIN IMMEDIATE` transaction.
> A per-entry failure rolls back ONLY that entry; previously committed entries in the same
> batch are unaffected. The shared `repo` connection is reused across entry transactions —
> one open + one close for the entire invocation.

---

### 🟢 MINOR — A-2: `--batch <slugs.json>` security path not documented

**Location:** `functional-architecture.md`, prepare CLI surface.

**Issue:** The architecture does not state whether `--batch <slugs.json>` requires the
file to be inside `--vault-root`. For `--candidates-file` this is explicitly enforced via
`validate_inside_vault`. The batch slugs file contains only slug *strings* (not content
written to the vault), so vault-containment enforcement is not technically required. But
the security model should be stated.

**Proposed wording:** "The `--batch` slugs file may reside anywhere readable by the
operator; it contains only vault-relative slug strings that are individually validated by
`_resolve_source_inside_sources` (vault-containment enforced on the resolved source paths,
not the slugs file itself)."

---

## Checklist Results

| Check | Result |
|-------|--------|
| All Use Cases (UC-015-1..5) mapped to architecture components | ✅ |
| No DDL changes / `user_version` stays 5 | ✅ |
| Backward compat (existing CLI surfaces unchanged) | ✅ |
| `upsert_one` SRP (no argparse, returns dict, `main()` delegates) | ✅ |
| `index_from_manifest` optional `repo` param, caller-owns lifecycle | ✅ |
| Batch per-entry isolation | ⚠️ (A-1 — needs clarification) |
| CWE-117/209 non-regression (R-015-NF4) called out in arch | ✅ |
| Security — batch slugs file path model | ⚠️ (A-2 — minor) |
| ARCHITECTURE.md in Index-Mode (375 lines) | ✅ |
| ARCHITECTURE.md updated in place (no per-task archive) | ✅ |
| No OWASP A03 regressions (all SQL via bound params) | ✅ |
| Simplicity / YAGNI | ✅ |

---

## Final Recommendation

**APPROVED WITH COMMENTS.** Apply A-1 (add transaction-isolation sentence to
functional-architecture.md "Bulk-transaction semantics") and A-2 (add security
model note for `--batch` slugs file) inline. No re-review needed — changes are
clarifications only, not scope changes.
