# Task 047-03 (P3) — evals + docs + dogfood

Beads: B9 (eval/unit) · B10 (docs) · B11 (dogfood). Runs after P1+P2 land.

## Goal
Prove the derived Mentions ledger is Class-A/B-rebuildable; document it; dogfood on a real `samples/` vault.

## Steps
1. **B9 — R-5 rebuildability** `tests/test_reindex_concept_mentions.py`: import two sources that mention
   one concept → `wiki-index-render --concept-mentions` → record the page's AUTO block; then delete the
   DB, `wiki-init --register-existing`, `wiki-reindex --full` (rebuilds `page_entity_refs` from the
   source notes' wiki-links), re-render → the AUTO blocks are **byte-identical** (Class A/B; quotes
   `sanitize_markdown_text`-safe, H-6). Optionally a `wiki-import` behaviour-eval case for the
   rendered-compounding discipline (2nd source appears after render, not via a Class-A merge).
2. **B10 — docs**: `docs/ARCHITECTURE.md` + `docs/architectures/functional-architecture.md` §2.3 — the
   derived concept-mentions ledger (the `BEGIN-AUTO:mentions` block rendered from `page_entity_refs`,
   preserve-rest, rebuildable); extend ADR-007 (write-grammar) with the decision AND a note recording
   the rejected body-merge alternative (pointer to `docs/reviews/plan-047-review.md`).
3. **B11 — dogfood** on `samples/<name>`: source A → concept page with an AUTO block listing A; source B
   (same concept) → `--concept-mentions` → the page lists A AND B; re-render → byte-identical; an
   operator paragraph added above the markers survives a re-render; `wiki-reindex --full` + render →
   identical AUTO blocks. Record the transcript.

## Acceptance
- [x] R-5 green — `test_reindex_full_rebuilds_concept_mentions` (`rm db → reindex --full → --concept-mentions`
  reproduces the AUTO block byte-identically; `is_candidate`/`source_page` frontmatter survives).
- [x] R-8 green — full suite **1762 passed / 5 skipped**, `mypy --strict` clean (60 files).
- [x] Docs — `docs/architectures/functional-architecture.md` §2.3 (derived ledger + retired file-layer)
  + ADR-007 "Extension (TASK 047)" + the P2 ARCHITECTURE/anatomy superseded banners.
- [x] Dogfood (real CLIs on `samples/task047-dogfood`, karpathy vault) — recorded below.

### Dogfood outcome (2026-07-01, `samples/task047-dogfood` — gitignored)
`wiki-init --register-existing` → `wiki-reindex --full` (3 pages, refs from the `## Entities` footers)
→ `wiki-index-render --concept-mentions`:
- **Compounds:** the `defi` concept page's AUTO block grew from `- [[src-a]]` to `- [[src-a]]` +
  `- [[src-b]]` once source B's `mentioned` ref was indexed.
- **Idempotent:** a second render returned `updated: []` (byte-identical); an operator paragraph added
  ABOVE the markers was byte-preserved.
- **Rebuildable (R-5):** `rm db → reindex --full → --concept-mentions` reproduced the block
  byte-identically, and the hand-edit persisted (Class A prose untouched; Class B block regenerated).

## Verification (whole task)
- `pytest tests/` green; `mypy --strict scripts/` clean.
- `grep -rn 'wiki_ingest' scripts/` clean of imports; `wiki-enrich` gone; README = 17 CLIs.
- Dogfood: a concept page whose Mentions ledger lists every source, regenerable from the DB, prose-preserving.
