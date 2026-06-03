# Architecture Review — TASK 018 `wiki-sync`

- **Date:** 2026-06-03
- **Reviewer:** Architecture Reviewer (05) — VDD gate
- **Target:** `docs/ARCHITECTURE.md` (header TASK 018 block + §2/§11a Q-018-1..7) +
  chunks `functional-architecture.md` (*Sync Dispatcher*), `interfaces.md` §5.4,
  `security.md` §7.5, `verification-map.md` (Sync Dispatcher).
- **Status:** ✅ **APPROVED WITH COMMENTS** (no BLOCKING; 1 MAJOR + 3 MINOR — MAJOR + 1 MINOR fixed inline, see §Resolution)

## General Assessment

Sound, appropriately lean design. The **Decision-17 shape is correctly forced**
from a verified repo fact (vendored `ingest()` is summary-passthrough), not assumed
— this is the right call and keeps `wiki-sync` `anthropic`-free and consistent with
`wiki-query`/`wiki-extract-concepts`. **Zero DDL** is justified (no new page type;
idempotency reuses existing state). Boundaries are clean (scan=classify,
workflow=execute, convert=skills, enrich/upsert=existing CLIs — good SRP and YAGNI;
the `wiki-sync apply` convenience is correctly deferred). Security §7.5 is thorough
(path-traversal, H-6, resource bounds, config-injection, no new regex/ReDoS or
authZ surface). The only-a-view anti-over-flag guard (from the task-review) is
carried into the architecture. Document size 525 lines — within limits, updated in
place, no snapshots. Use-Case → component coverage is complete (verification-map).

## Comments

### 🔴 CRITICAL (BLOCKING)
_None._

### 🟡 MAJOR
- **AM-1 — Idempotency source is conflated.** The design states "idempotency via
  `source_state`" uniformly and the plan field is `is_unchanged`, but the two action
  classes have **different** idempotency stores: a **ready-note `upsert`** is
  idempotent on **`pages.file_hash`** (what `wiki-index-upsert` compares), whereas a
  **raw `ingest`** is idempotent on **`source_state`** (what `wiki-enrich` /
  `wiki-extract-concepts` write). If `scan` keys `is_unchanged` on `source_state`
  uniformly, it will **never skip an unchanged ready note** (always re-upsert), and
  for `ingest` it must read the **same `(source_kind, scope, key)`** the chosen
  chain writes or the flag is wrong. **Fix:** specify `is_unchanged` as
  **action-specific** — `upsert` → compare file hash to `pages.file_hash` (via the
  index, which doubles as the scalability fast-path: an already-indexed unchanged
  note needs no re-read/re-hash); `ingest`/`convert+ingest` → `source_state` hash
  matching the writer's key.

### 🟢 MINOR
- **am-1 — Vendored-private import coupling.** Q-018-2 reuses
  `wiki_ingest._classify` *private* helpers; the vendored module is a synced
  snapshot, so depending on its privates risks breakage on `sync_wiki_ingest.sh`.
  Advisory: reuse only if stable; otherwise reimplement the small needed bits in
  `_sync` (the routing logic is mostly new anyway).
- **am-2 — Classification read cost.** Classifying `.md` requires reading
  frontmatter/head per file (O(N_md) reads in-zone). Mitigated by AM-1's index
  fast-path (skip unchanged indexed notes) + keeping zones scoped (course folders,
  not the whole vault) — worth stating.
- **am-3 — `needs_ocr` is post-execution, not a scan action.** The plan
  `summary.needs_ocr` can't be known at deterministic `scan` time (the text-layer
  probe lives in the converter, Q-018-6). Clarify it is populated by the
  **executor's report**, not by `scan`; `scan` plans `.pdf` as `convert+ingest`.

## Data Model / Security / Scalability traces
- **Data model:** no new entities; `source_state`/`pages.file_hash` reuse traced (see AM-1). Migrations N/A (zero DDL, `user_version` 5). ✓ after AM-1 fix.
- **Security:** OWASP traced — path-traversal (`validate_inside_vault` + symlink refuse), injection (params-only; strict `.wiki/sync.yaml` schema), prompt-injection (H-6 binding), ReDoS (globs path-only, no new regex), secrets (none; no `anthropic`). ✓
- **Scalability/Reliability:** bounded single-stat walk + early binary skip; per-file isolation; atomic in-vault writes; no silent drops. ✓ (+ am-2 note).

## Resolution (architect applied inline; loop converged)
- **AM-1:** functional-arch *Plan JSON* + *Operational invariants* updated — `is_unchanged` made action-specific (upsert→`pages.file_hash` index fast-path; ingest→`source_state`); ARCHITECTURE.md §11a Q-018 idempotency note added.
- **am-3:** functional-arch clarified — `needs_ocr` is an executor-report bucket, not a scan action.
- **am-1, am-2:** recorded as advisory; am-1 folded into Q-018-2 wording (reuse only if stable), am-2 covered by the AM-1 fast-path note. No further change required.

## Final Recommendation
**PROCEED to Planning phase** (`/vdd-plan`). Architecture is feasible, secure, and
zero-DDL; the idempotency contract is now unambiguous. No BLOCKING issues remain.

```json
{ "review_file": "docs/reviews/architecture-018-review.md", "has_critical_issues": false }
```
