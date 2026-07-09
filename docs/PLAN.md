# PLAN — TASK 055: wiki-import note-processing fixes

Stub-First is degenerate here (no new module/scaffold) — each bead is a small, TDD-style
change: write/adjust the failing test, apply the fix, re-run the targeted test, then the full
suite. Every RTM ID from `docs/TASK.md` maps to exactly one bead below.

## Beads (atomic, ordered)

- [ ] **[WI-1]** tldr: keep the full tldr for the rendered body; cap **only** the frontmatter
  scalar on a word boundary + `…`.
  - Add `_authoring._tldr_fm_preview(tldr, cap=300)` — full when ≤ cap, else word-boundary cut +
    ellipsis (char-based; Cyrillic-safe).
  - In `assemble_note`: compute the full `tldr` (no `[:300]`) for the body sections (`## brief`
    in summary/thread); use `_tldr_fm_preview(tldr)` for the `tldr:` frontmatter scalar only.
  - Test: `test_assemble_note_full_tldr_in_body_capped_in_frontmatter` (long tldr → full in body,
    `…` in frontmatter; short tldr → byte-identical both slots).

- [ ] **[WI-2]** Contract clarity + verification (behavior already correct — fallback searches the
  rendered note). No code change to the quote path.
  - Edit `reason-contract.md` Hard rule 2 + the depth-by-mode note: carve out `mode=summary`
    (body null → quote MUST be a verbatim substring of `tldr`/`summary_bullets`; the "body-line"
    fallback searches the **rendered** summary text (tldr + bullets); drops surface as
    `CONCEPTS_DROPPED`).
  - Test: `test_summary_mode_quote_fallback_searches_rendered_bullets` — a paraphrased quote whose
    entity name appears in a bullet line resolves via the fallback; a name absent from tldr+bullets
    drops `no-verbatim-quote`.

- [ ] **[WI-3]** published: accept partial dates + apply-side fallback to prepare's `date`.
  - Edit `reason-contract.md`: `published` type → `YYYY | YYYY-MM | YYYY-MM-DD | null`.
  - `__init__.py`: add `apply --published` (prepare's extracted `date`); when the note JSON's
    `published` is null/empty, fall back to it before assembling. Plumb through the SKILL/workflow docs.
  - Test: `test_apply_published_fallback_to_source_date` (note `published:null` + `--published 2025-10`
    → `published: "2025-10"`); `test_apply_published_note_wins_over_fallback`.

- [ ] **[P-6R]** `--known-concepts-format {full,slugs-only}` on `wiki-import prepare`.
  - `_context.known_concepts(..., fmt="full")` → returns `[{slug,name}]` (full) or `[slug,…]`
    (slugs-only).
  - `__init__.py::prepare`: add the argparse flag (default `full`), pass `fmt=args.known_concepts_format`.
  - Test: `test_known_concepts_slugs_only_shape` + `test_known_concepts_full_default_shape`.

## Verification checkpoints
1. After each bead: targeted `pytest tests/test_import_article_*.py -k <bead>` green.
2. After all beads: full `pytest tests/` + `mypy --strict scripts/` clean.
3. Adversarial review (logic/security/perf) converged.
4. Issues closed (`status: fixed` + Resolution) + `docs/KNOWN_ISSUES.md` regenerated.
