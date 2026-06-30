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
- [ ] R-5 green (reindex --full + render reproduces the Mentions blocks deterministically).
- [ ] R-8 green: full `pytest` + `mypy --strict` + the extract-concepts/import/sync/render eval pins pass.
- [ ] Docs updated; dogfood recorded (two sources → one page listing both; idempotent; rebuildable; prose preserved).

## Verification (whole task)
- `pytest tests/` green; `mypy --strict scripts/` clean.
- `grep -rn 'wiki_ingest' scripts/` clean of imports; `wiki-enrich` gone; README = 17 CLIs.
- Dogfood: a concept page whose Mentions ledger lists every source, regenerable from the DB, prose-preserving.
