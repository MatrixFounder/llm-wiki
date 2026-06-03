# Task Review — TASK 018 `wiki-sync`

- **Date:** 2026-06-03
- **Reviewer:** Task Reviewer (03) — VDD gate
- **Target:** `docs/TASK.md` (TASK 018, R-11)
- **Status:** ✅ **APPROVED WITH COMMENTS** (no BLOCKING; 1 MAJOR + 3 MINOR — fixes applied inline, see §Resolution)

## General Assessment

Strong, well-grounded spec. Scope matches the operator decision (Full R-11). The
**§1.1 Grounding facts** block is the standout: it anchors the design to verified
repo reality (summary-passthrough `ingest` ⇒ Decision-17 shape; existing
`classify_folder`/`scan`/`register_summary` to build on; conversion skills present;
PDF-OCR upstream gap) rather than assumed capability — exactly what prevents a
hallucinated architecture. Epics→Issues decomposition is granular (≥3 sub-features
per Issue), Use Cases carry actors + alternatives + error isolation, and Acceptance
Criteria are binary. RTM present (not LIGHT). Compatible with ARCHITECTURE (zero
DDL, no `anthropic`, `source_state` idempotency, H-6).

## Comments

### 🔴 CRITICAL (BLOCKING)
_None._

### 🟡 MAJOR
- **M-1 — View-detection over-flagging not guarded.** E2.2 / AC-2 prove that a
  *pure* generated-view sidecar is skipped, but there is **no negative criterion**:
  a legitimate content note that merely *contains* a `dataview`/`base` block
  alongside real prose MUST NOT be skipped (else `wiki-sync` silently drops
  knowledge — an over-flag, the behavioural twin of a false positive). **Fix:**
  tighten E2.2 to "body is *essentially/only* a single view block (modulo
  frontmatter)" and add a negative Acceptance Criterion + fixture.

### 🟢 MINOR
- **m-1 — Empty / no-eligible-files zone.** No UC/AC for "zone has nothing to do".
  **Fix:** add an alternative branch (empty plan, exit 0, report says "0 actions").
- **m-2 — Scan walk cost on large zones.** The operator's vault has 6000+ excluded
  binaries + large `_daily`; the deterministic scan should not be O(restat). **Fix:**
  note the mitigation (reuse R-X1 `iter_pages` single-stat walk; skip-binary early
  by extension before any read/hash) as a non-functional line.
- **m-3 — UC-2..UC-5 omit explicit Preconditions/Postconditions.** Acceptable (UC-1
  establishes the shared preconditions and AC compensates), but a one-liner
  "Preconditions: as UC-1" would tighten structure. Optional.

## Compatibility / Consistency / Non-Functional
- Terminology ✓ (Decision-17, `source_state`, `_sources`, enrich/upsert, H-6, layout engine).
- Architecture ✓ (zero DDL; no `anthropic`; builds on documented primitives). ARCHITECTURE.md §wiki-sync to be added in the next phase (expected).
- Internal consistency ✓; naming consistent (`#wiki/raw`, `_raw/`).
- Security ✓ (E4.3/AC-7: H-6, path-traversal, atomic in-vault write, no-exec).
- Performance — addressed by m-2 fix.

## Resolution (analyst applied inline; loop converged)
- **M-1:** E2.2 sub-feature reworded to "*body is only/essentially* a single view
  block"; **AC-2b** (negative) added; UC-3 gains a "note-with-embedded-dataview →
  upsert" line.
- **m-1:** UC-6 (empty zone) added.
- **m-2:** §2 Epic E3.1 sub-feature + a Non-Functional note added (single-stat walk,
  early binary skip).
- **m-3:** left as-is (optional; AC compensates).

## Final Recommendation
**PROCEED to Architecture phase.** The 7 Open Questions are correctly scoped as
architect-phase decisions (shape lock, classifier reuse, conversion wiring, config
home, raw→ingest chain, PDF-OCR handling, tag surface). No BLOCKING issues remain
after the inline fixes.

```json
{ "review_file": "docs/reviews/task-018-review.md", "has_critical_issues": false }
```
