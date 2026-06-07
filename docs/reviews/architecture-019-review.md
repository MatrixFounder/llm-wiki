# Architecture Review — TASK 019 (`sync-resummarize-policy`)

- **Date:** 2026-06-07
- **Reviewer:** Architecture Reviewer (self-review, `05_architecture_reviewer` +
  `architecture-review-checklist`)
- **Status:** ✅ **APPROVED WITH COMMENTS** (no BLOCKING; ready for Planning)
- **Surface reviewed:** `docs/ARCHITECTURE.md` — TASK 019 status block, §2 Sync Dispatcher
  pointer, §4 Data Model note, §11a **Q-019-1..9**, Verification Map row.

## 1. TASK Compliance
- ✅ **Coverage:** every AC mapped — AC-1→Q-019-1/4; AC-2/3/3b/12→Q-019-5; AC-4→Q-019-6;
  AC-5→Q-019-3; AC-7/10→Q-019-9; AC-8→Q-019-4; AC-9→Q-019-8; AC-11→Q-019-2; AC-13→Q-019-7.
  All 6 operator-resolved OQs are reflected (Option-A cascade, extended-regex mirror N:1,
  rel-path provenance + writeback, `exclude > policy`, `detect` default, `--force` scope).
- ✅ **Constraints:** zero-DDL (`user_version` 5), no `import anthropic`, back-compat
  byte-identity, determinism — all pinned.

## 2. Data Model (CRITICAL)
- ✅ **No new entity/column** — D1 reuses `SourceState` (`source_kind='sync'`), D2a reads
  `Page.frontmatter_json` (`json_extract`), D2b is filesystem-only. Migrations N/A (zero
  DDL). Business rules unchanged.
- ✅ **One new read-only DAL method** `find_pages_citing_source` (pure SELECT, parameterized
  → injection-safe, TASK 013 mechanism). 🟡 *MAJOR (Planning):* finalize its exact ABC
  signature + index usage in `architectures/interfaces.md` + `data-model.md` during the
  Stub-First DAL bead (the inline §11a Q-019-8 is authoritative for the gate; the chunk
  prose lags — same lag TASK 018 had).

## 3. System Design
- ✅ **Simplicity / least moving parts:** the gate is **monotone** (`ingest → skip` only),
  isolated in a new SRP module `_resummarize.py`, leaving `_sync.py` (classifier) and
  `wiki_sync.py` (CLI/plan) intact. Acyclic imports specified.
- ✅ **Boundaries:** detector union with cheapest-first short-circuit (D1 free → D2a indexed
  → D2b FS); config resolution memoized per directory.
- ✅ **Document size:** 702 lines ≤ 1500 → single living file, no Index-Mode split; no
  per-task drift (inline §11a log, no `architecture-019-*.md` snapshot).

## 4. Security
- ✅ **ReDoS:** operator `key.raw_regex`/`summary_regex` are a new operator-regex surface →
  guarded by the **TASK 017** infra (load-gate + per-file `regex` deadline; timeout →
  report-and-skip). Explicit (Q-019-5).
- ✅ **Untrusted config:** per-folder `.wiki/sync.yaml` reuse the size-cap + anchor-ban
  SafeLoader + raw-`is_symlink` refuse + `validate_inside_vault` (Q-019-2/3); errors never
  echo content (CWE-209/117).
- ✅ **Precedence:** `exclude > policy` (excluded paths pruned pre-classification) — no
  bypass of never-walk via an override.
- ✅ **Injection:** D2a query parameterized (`json_extract(…, ?)`), no value interpolation.

## 5. Scalability & Reliability
- ✅ **Perf:** per-dir config memoization (no per-file walk); D2a is an indexed query; D2b is
  a bounded sibling-dir scan. *Planning residual (LOW):* recursive-vs-flat summary scan.
- ✅ **Faults:** ReDoS timeout, empty-key, missing-mirror all degrade to "not covered →
  fall through" (never crash/hang); degenerate config → WARN, not crash (AC-11).

## Comments
- 🔴 Critical: none.
- 🟡 Major: (1) finalize `find_pages_citing_source` signature + interfaces/data-model chunk
  sync at the DAL Stub-First bead. (2) **Cross-task prerequisite** (Q-019-9): dogfood
  `samples/Demand-generation` summaries use `type: lesson-summary` (unmapped) → the `upsert`
  leg needs a layout `type_mapping` for it; track separately (TASK 012 surface), not a
  TASK 019 blocker.
- 🟢 Minor: detailed `architectures/{functional-architecture,interfaces,data-model}.md`
  chunks to gain a short TASK 019 subsection during Dev (inline §11a is authoritative now).

## Final Recommendation
**Proceed to the Planning phase** (`/vdd-plan`). Decompose Stub-First: (b1) `$def
Resummarize` schema + loader, (b2) per-folder cascade resolver + memoization + hardening,
(b3) detectors D1/D2a(`find_pages_citing_source`)/D2b(stem-relpath + group-key + ReDoS),
(b4) `_build_entries` gate + `--force` + reasons, (b5) workflow `--force` + `sources:`
writeback, (b6) back-compat byte-identity + dogfood on `samples/Demand-generation`.
