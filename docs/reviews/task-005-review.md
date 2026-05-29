# Task Review — TASK 005 (entity-resolution / Epic 7 R-4 + R-5)

- **Date:** 2026-05-29
- **Reviewer:** Task Reviewer (self-correction loop, VDD `/vdd-start-feature`)
- **Status:** ✅ **APPROVED WITH COMMENTS** (1 MAJOR folded in; rest deferred to Architecture)
- **Checklist:** `skill-task-review-checklist` v1.0

## General Assessment

The TASK faithfully covers the user request ("выполни Epic 7 завершение
(R-4 + R-5)"): R-4 (confirmed/candidate resolution) and R-5 (two-tier alias
table) are each decomposed into 6 traceable requirements with high
granularity. Every operator-facing fork was resolved with the operator at
analysis time (Decision Log D-005-1..4). The spec is **grounded in verified
repo facts** (§1.1 table cites exact files/lines), not invention — notably the
discovery that `is_candidate` is *already* Class A on write but ignored on
reindex, which reframes R-4 from "add persistence" to "close a round-trip
durability bug." RTM present and strict. No fundamental misunderstandings.

## Comments

### 🔴 CRITICAL (BLOCKING)
None.

### 🟡 MAJOR
- **M-1 (FOLDED IN):** With the operator-chosen **hard PK** `(vault_id, alias)`,
  an in-table same-alias→two-slugs collision becomes *unrepresentable in the
  DB*. The canonical conflict therefore survives only at the **Class A
  frontmatter** layer (two entity pages each declaring the same alias), and a
  naïve `INSERT OR IGNORE` mirror would silently drop one — hiding operator
  data loss. **Fix applied:** R-5.3(c) now mandates *report-and-skip, never
  silent OR IGNORE* on reindex PK conflict; R-5.6(e) adds a Class A frontmatter
  scan so lint stays authoritative on the source of truth. *Resolved in-place;
  no longer outstanding.*

### 🟢 MINOR (deferred to Architecture/Planning — non-blocking)
- **m-1:** UC-14 (durability round-trip) is terser than UC-09..13 (no explicit
  Actors/Postconditions lines). Acceptable — it is a System-only invariant
  test, and its Acceptance Criteria are the binding part.
- **m-2:** Error-envelope exit codes (3/4/5: `ENTITY_NOT_FOUND`,
  `ENTITY_FILE_MISSING`, `ALIAS_COLLISION`) are **illustrative**. Finalize the
  exit-code map against the `wiki-extract-concepts` envelope conventions in the
  Architecture phase (these are *new* programs with an independent code space,
  so no hard collision risk).
- **m-3:** `wiki-confirm --undo` (demotion) is beyond the literal R-4 text.
  Retained as MVP because it is the **correctness inverse of auto-promote**
  (N=3 can misfire, and the `MIN()` upsert guard otherwise makes a wrong
  confirm irreversible). Justification documented in §1.1 + C-1.
- **m-4:** `alias_type` round-trip limitation (C-4) is honestly disclosed —
  flat Obsidian `aliases:` loses type, so `--type` is Class B only. Acceptable;
  alias_type is not load-bearing for search/lint.

## Checklist Result

| Group | Item | Verdict |
|---|---|---|
| 1 Compliance | Requirements / Scope / Goal | ✅ (scope fence C-5; m-3 justified) |
| 2 Use Cases | Structure / Main / Alternatives / AC | ✅ (m-1 minor) |
| 3 Compatibility | Terminology / Architecture / Integrations | ✅ (m-2 minor) |
| 4 Consistency | Internal / Naming | ✅ |
| 5 Non-Functional | Performance / Security | ✅ (NFR-3, NFR-5) |

## Final Recommendation

**PROCEED to Architecture phase.** The single MAJOR was incorporated into the
TASK; remaining comments are implementation-level and correctly belong to
Architecture/Planning. No blocking issues.

```json
{ "review_file": "docs/reviews/task-005-review.md", "has_critical_issues": false }
```

---

## Re-Review — 2026-05-29 refinement (wiki-merge / R-4.7 folded in)

- **Trigger:** Operator re-invoked `/vdd-start-feature` and, via analysis-time
  clarification, **added duplicate-merge to scope** (Q3b). Prior R-4+R-5 spec
  was already APPROVED above; this re-review covers **only the merge delta**:
  R-4.7, R-4.5(d), UC-15 (§3.7), NFR-2 (+`merge_entities`, alias-aware
  `find_orphan_links`), C-1/C-5/C-7/C-8, Decision Log D-005-5, Q6.
- **Status:** ✅ **APPROVED WITH COMMENTS** (0 critical, 0 major; 3 minor → Planning).
- **Checklist:** `task-review-checklist` v1.0.

### Assessment of the delta

The merge addition is the **direct realisation of R-4's stated motivation**
("resolves the Hermes / Hermes Agent / Hermes Framework duplication") — the
prior spec delivered the candidate/confirmed flag + aliases but, as the
re-review correctly self-identifies, the flag alone never *merges* duplicates.
R-4.7 closes that gap. The strongest design decision is making the **alias
table the durable redirect** (C-7) rather than rewriting `[[...]]` wikilinks:
it keeps the merge expressible in Class A (delete `from` page + `into.aliases`
carry the surfaces) so the §D8 round-trip (UC-15 AC-4) still holds, and it
avoids a vault-wide Class-A source mutation. The grounded-facts row added to
§1.1 (page_entity_refs has **no FK** on `entity_slug`; PK dedup needed; refs
re-materialise on reindex → resolution must be alias-aware) is verified against
SCHEMA-v2.sql:231 and is exactly the non-obvious trap that would have bitten a
naïve implementation.

### Comments

#### 🔴 CRITICAL — None.
#### 🟡 MAJOR — None.

#### 🟢 MINOR (deferred to Architecture/Planning — non-blocking)
- **rm-1 (consistency, resolved):** `INVALID_MERGE` is exit 5 in `wiki-merge`
  while `ALIAS_COLLISION` is exit 5 in `wiki-alias`. **Not a collision** —
  prior m-2 established each new CLI owns an independent exit-code space; codes
  are illustrative and finalised in Architecture. The new `MERGE_MIRROR_FAILED`
  (exit 6, C-8) likewise belongs to `wiki-merge`'s space.
- **rm-2 (perf, Planning):** ref re-pointing dedup keeps "higher `trust_level`"
  on `(page, into, ref_type)` PK conflict. The tie-break order (`high > medium >
  low`) and the SQL shape (UPDATE-then-handle-conflict vs INSERT-OR-IGNORE +
  DELETE) is an implementation choice — pin it in Planning; both are set-based,
  no per-row Python loop.
- **rm-3 (Q6, Planning):** `from`-page hard-delete vs `_merged/` tombstone is
  recorded as a non-blocking open question with a safe default (hard-delete;
  git is the audit trail). Confirm in Architecture's data-model chunk.

### Final Recommendation

**PROCEED to update ARCHITECTURE.md for the merge component, then re-run the
architecture gate.** The merge delta introduces no contradiction with the
already-approved R-4/R-5 spec; UC-15 is fully structured (Actors / Pre / Main /
5 Alternatives / Post / 5 binary AC); scope stays fenced (C-5). No blocking
issues.

```json
{ "review_file": "docs/reviews/task-005-review.md", "has_critical_issues": false }
```
