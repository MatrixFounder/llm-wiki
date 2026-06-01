# Task 012-00: Golden byte-identity snapshot harness (regression anchor)

## Use Case Connection
- UC-29: Re-index a Karpathy vault byte-identically (the §D8 acceptance). This bead
  establishes the tripwire that proves UC-29 holds after every later bead.

## Task Goal
Capture the **current** (pre-refactor) layout engine's output as a golden snapshot, so
any byte-level drift introduced by the config-driven rewrite (012-01..07) fails loudly
and immediately. **No source change** — test-only. This is the Stub-First safety net for
the whole Epic and is written FIRST (`skill-tdd-strict`).

The snapshot covers both the discovery surface and the materialised-row surface:
1. `reindex.discover_pages(vault_root)` → the ordered + the **set** of `(slug, project)`.
2. A full `reindex_full` → the `pages` rows projected to
   `(slug, project, type, sorted(tags), file_path)` and the `page_entity_refs` rows
   projected to `(page_slug, page_project, entity_slug, ref_type)` — i.e. everything that
   is a pure function of the vault content (excludes `last_modified`, `id`, `file_hash`
   timestamps).

## Changes Description

### Changes in Test Files

#### File: `tests/test_karpathy_byte_identity.py` (NEW)
- Fixture: use the existing `multi_vault` (`vault-alpha` has a `Lessons/Course-A/` course
  tier — exercises both tiers) + `minimal_vault`.
- `_snapshot(repo, vault_id) -> dict` helper: returns
  `{"discover": sorted([(slug, project) for ...]), "pages": sorted([...]), "refs": sorted([...])}`
  with all volatile columns (`last_modified`, `file_hash`, `id`, `registered_at`) stripped.
- `test_discover_pages_snapshot_stable`: assert `discover_pages` output (as a **set** and
  as a **path-sorted list**) matches an inline golden literal captured from the current
  engine. (Capturing both forms means 012-02's new stable sort is already tolerated.)
- `test_reindex_full_rows_snapshot_stable`: register + `reindex_full` both vaults; assert
  the projected `pages`/`refs` rows match the golden literal.
- Mark the golden literal with a comment: `# GOLDEN — captured against pre-TASK-012 engine; must not drift (ADR-002 §D8 / R-X1 byte-identity).`

## Implementation Notes
- Capture the golden literals by running the helper once against the current engine and
  pasting the result (do NOT compute the golden at test time from the same code path — a
  self-referential snapshot proves nothing). The literal IS the contract.
- **Fixture-coverage precondition (plan-review MINOR-1):** add a one-line assert that the
  chosen fixtures collectively exercise **every `PAGE_SUBDIRS` member** (`_sources`,
  `_concepts`, `_entities`, `_queries`, `_verifications`) **and ≥1 nested course-tier
  page** (`Lessons/<course>/_sources/<sub>/…`). If `multi_vault`/`minimal_vault` lack a
  `_queries/`/`_verifications/` page or a nested course page, ADD one to the fixture so the
  byte-identity contract's *coverage* is pinned, not assumed (else a surface could drift
  silently in a vault shape the snapshot never saw).
- Keep volatile-field stripping centralised in `_snapshot` so later beads can't
  accidentally re-introduce a timestamp into the comparison.

## Acceptance Criteria
- ✅ `pytest tests/test_karpathy_byte_identity.py` green on **current** (pre-refactor) code.
- ✅ The golden literals are inline (the test fails if a later bead changes any
  `(slug, project, type, tags, file_path)` for the fixtures).
- ✅ `mypy --strict` clean.

## Definition of Done
This bead is the anchor: it stays green at **every** subsequent bead boundary. A red here
during 012-01..07 means a byte-identity regression — stop and fix before proceeding.
