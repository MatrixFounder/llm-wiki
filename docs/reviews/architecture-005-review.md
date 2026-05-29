# Architecture Review — TASK 005 (entity-resolution / Epic 7 R-4 + R-5)

- **Date:** 2026-05-29
- **Reviewer:** Architecture Reviewer (self-correction loop, VDD `/vdd-start-feature`)
- **Status:** ✅ **APPROVED WITH COMMENTS** (2 MAJOR data-model findings folded in; no critical)
- **Checklist:** `architecture-review-checklist` v1.1
- **Scope of review:** `docs/ARCHITECTURE.md` index + chunks `data-model.md`,
  `functional-architecture.md`, `interfaces.md`, `verification-map.md`.

## General Assessment

The design is **TASK-traceable** (every R-4.x/R-5.x maps to a component +
verification-map row) and respects the established invariants: ADR-002 §D8
Class A/B layering, the DAL boundary (no raw SQL in skills), the universal
CWE-117/209 envelope, and the single-indexer rule. The standout correctness
move is treating the feature as **closing a durability bug** (full reindex
silently confirming candidates / dropping aliases) rather than a greenfield
add — the UC-14 §D8 round-trip is the load-bearing gate. Data Model is the
right place to scrutinize, and two missing/redundant-index issues were caught
and fixed in this pass. Index-Mode integrity intact (193-line index, all chunk
links resolve, no per-task drift).

## Comments

### 🔴 CRITICAL (BLOCKING)
None.

### 🟡 MAJOR (both FOLDED IN)
- **AM-1 (FOLDED IN) — redundant index after PK change.** With PK →
  `(vault_id, alias)` (R-5.4), the pre-existing `idx_aliases_lookup ON
  entity_aliases(vault_id, alias)` becomes a duplicate of the PK's implicit
  index → dead weight maintained on every write (same anti-pattern as
  KNOWN_ISSUES P-5). **Fix:** §4.2 + §4.4 now mandate dropping it in the v2→v3
  DDL.
- **AM-2 (FOLDED IN) — missing reverse-lookup index.** `list_aliases`
  (R-5.2) and sibling-alias gathering for search expansion (R-5.5) query by
  `entity_slug`, but the old composite PK placed `entity_slug` as the 3rd
  column (not a usable prefix) and no other index covered it → table-scan on a
  frequent path. **Fix:** §4.2 + §4.4 now add `idx_aliases_entity
  (vault_id, entity_slug)`.

### 🟢 MINOR (deferred to Planning — non-blocking)
- **m-1:** Entity Resolver exit-code map (3/4/5) is illustrative; finalize
  against the `wiki-extract-concepts` code space in Planning (already noted
  inline in §2.1).
- **m-2 (security, track in Planning):** `wiki-alias --add "<surface>"` embeds
  an operator string into YAML frontmatter `aliases:`. The design reuses the
  `_sanitize_*` helpers (YAML-delimiter / list-injection defense) and NFR-3
  caps length — **Planning must extend the parametrised CWE-117/209 + YAML
  sanitisation regression suite to alias surfaces**, not just concept names.
- **m-3 (perf):** default-on alias expansion adds one `expand_query_aliases`
  DAL round-trip + bounded OR-terms per search. Acceptable (bounded to the
  matched entity's own alias set; `--no-expand-aliases` opt-out), but note it
  in the scalability chunk if real-vault latency regresses.
- **m-4:** residual open questions Q-A4 (expansion breadth cap) + Q-A5
  (auto-promote log-event granularity) recorded in index §11c with safe
  defaults; resolve in Planning.

## Checklist Result

| Group | Item | Verdict |
|---|---|---|
| 1 TASK Compliance | Coverage / Constraints | ✅ (UC-09..14 + R-4/R-5 all mapped; NFR-1..6 addressed) |
| 2 Data Model (CRITICAL) | Completeness / Types / **Indexes** / Migrations / Business Rules | ✅ after AM-1 + AM-2 fixes; PK/FK/CHECK/NOT-NULL defined; v2→v3 migration = reindex |
| 3 System Design | Simplicity / Style / Boundaries / **Size** / No-drift | ✅ (193-line index; 2 separate CLIs = clean SRP; no overengineering) |
| 4 Security | Auth / OWASP / Secrets | ✅ (single-user; A01 path + A03 injection reused; envelope invariant; m-2 to extend tests) |
| 5 Scalability & Reliability | Scaling / Faults | ✅ (vertical; set-based recompute; report-and-skip on collision; m-3 noted) |

## Final Recommendation

**PROCEED to Planning (`/vdd-plan`).** The two MAJOR data-model findings were
incorporated; remaining comments are implementation-level. The Stub-First
decomposition should sequence: (1) schema v2→v3 + DAL methods (stubs + RED
tests), (2) reindex Class A read/mirror (R-4.1/R-5.3 — the durability spine),
(3) `wiki-confirm`, (4) `wiki-alias`, (5) search expansion + lint, (6)
UC-14 round-trip acceptance + docs/symlinks.

```json
{ "review_file": "docs/reviews/architecture-005-review.md", "has_critical_issues": false }
```

---

## Re-Review — 2026-05-29 refinement (wiki-merge / R-4.7 folded in)

- **Trigger:** Operator added duplicate-merge to scope (TASK Q3b / D-005-5).
  Prior R-4+R-5 architecture was already APPROVED above; this re-review covers
  **only the merge delta**: the Entity Resolver component now `wiki-confirm` +
  `wiki-alias` + **`wiki-merge`**; new DAL `merge_entities` + alias-aware
  `find_orphan_links`; data-model "Merge path" + "Merge re-pointing"; the
  `wiki-merge` independent exit-code table; index/migration notes; mermaid +
  index summaries; verification-map R-4.7 row.
- **Status:** ✅ **APPROVED WITH COMMENTS** (0 critical; **1 MAJOR data-model
  finding caught + folded in**; 2 minor → Planning).
- **Checklist:** `architecture-review-checklist` v1.1.
- **Scope of review:** index + `data-model.md`, `functional-architecture.md`,
  `interfaces.md`, `verification-map.md`.

### General Assessment of the delta

The merge design is **correct where it is hardest to be correct**: it makes the
fold expressible **entirely in Class A** (delete the `from` page + carry the old
surfaces as `into` aliases), so it needs **no merge-ledger table** and the §D8
round-trip still holds — exactly the right instinct, consistent with the
project's "DB is rebuildable" contract. The "alias *is* the redirect" choice
(C-7, no `[[...]]` wikilink rewriting) is the YAGNI-correct call: it avoids a
vault-wide Class-A *source-body* mutation with a large blast radius. The DAL
addition is pure DML (no DDL, no new index — reuses `idx_refs_entity` +
`idx_aliases_entity`), so it is Postgres-portable and the v3 schema is
unchanged by merge. Data-Model is, again, the right place to scrutinise — and
one non-obvious durability defect surfaced there.

### Comments

#### 🔴 CRITICAL (BLOCKING) — None.

#### 🟡 MAJOR (FOLDED IN)
- **AM-3 (FOLDED IN) — merge durability defect in `recompute_mentions` /
  `get_backlinks` under full reindex.** The first-draft merge re-pointed
  `page_entity_refs` in the DB, but source bodies still contain `[[from-slug]]`.
  A `wiki-reindex --full` rebuilds refs from that raw text → they re-materialise
  under `from-slug`. Since `recompute_mentions` and `get_backlinks` count
  `WHERE entity_slug = entities.slug`, the merged-away refs would be **silently
  dropped from `into`** after a rebuild — directly violating UC-15 AC
  ("`into.mentions_count` = de-duplicated union" + "full reindex reproduces the
  merged state"). The naïve design passes immediately-post-merge but **fails the
  §D8 round-trip**, the load-bearing gate. **Fix applied:** `reindex_full` now
  **canonicalizes each ref target through the alias table at build time**
  (phase order entities → aliases → refs → recompute_mentions), establishing the
  invariant *"a `page_entity_refs` row names the canonical entity whenever its
  raw target is a known alias."* Documented in §2.1 Entity Resolver durability
  ("Reindex ref-canonicalization (AM-3)") + §4.1 PageEntityRef ("Canonical-slug
  invariant (AM-3)") + verification-map R-4.7. `find_orphan_links` query-time
  alias-awareness (R-4.5d) remains the defense for partially-indexed states.
  *Resolved in-place; no longer outstanding.*

#### 🟢 MINOR (deferred to Planning — non-blocking)
- **am-1 (perf, Planning):** ref-canonicalization adds one alias-table lookup
  per ref during `reindex_full`. The alias table is small and PK-indexed, and a
  no-alias vault hits a single empty-set probe — but Planning should confirm the
  canonicalization is a set-based JOIN/UPDATE (or a cached alias map), **not** a
  per-ref Python query, to avoid an N×M regression on large vaults (cf. P-2/P-3
  reindex perf items).
- **am-2 (Planning):** merge write-order (C-8: Class A first, then the DB
  transaction) means a crash between the file ops and the DB commit leaves the
  DB stale-but-recoverable (`MERGE_MIRROR_FAILED` → `wiki-reindex --delta`).
  Planning should add a test that simulates the mid-merge failure and asserts a
  `--delta` reindex restores consistency from Class A.

### Checklist Result (delta)

| Group | Item | Verdict |
|---|---|---|
| 1 TASK Compliance | R-4.7 + UC-15 mapped; C-7/C-8 honored | ✅ |
| 2 Data Model (CRITICAL) | re-point PK-dedup; **canonical-slug invariant (AM-3)**; no new DDL/index; migration unaffected | ✅ after AM-3 fix |
| 3 System Design | merge = 3rd Entity-Resolver CLI, SRP intact; no merge-ledger table (YAGNI); index 193 lines | ✅ |
| 4 Security | reuses `O_NOFOLLOW`+atomic-temp for the `from`-page delete + `into` frontmatter write; envelope invariant extended to merge codes | ✅ |
| 5 Scalability & Reliability | pure set-based DML; C-8 recovery path; am-1/am-2 noted | ✅ |

### Final Recommendation

**PROCEED to Planning (`/vdd-plan`).** The one MAJOR (AM-3) — a genuine §D8
durability defect — was incorporated; remaining comments are implementation-level.
The Stub-First sequence from the original review still holds, with merge slotting
after the alias machinery (it depends on the alias table + alias-aware resolution):
(1) schema v2→v3 + DAL stubs + RED tests, (2) reindex Class A read/mirror **+
ref-canonicalization** (R-4.1/R-5.3/AM-3 — the durability spine), (3)
`wiki-confirm`, (4) `wiki-alias`, (5) search expansion + lint, (6) **`wiki-merge`**,
(7) UC-14 + UC-15 round-trip acceptance + docs/symlinks.

```json
{ "review_file": "docs/reviews/architecture-005-review.md", "has_critical_issues": false }
```
