# Task 047-01 (P1) — derived concept-mentions renderer

Beads: B1 (stub+RED, full import→render path) · B2 (renderer + AUTO-block replace) · B3 (wire
`--concept-mentions` + write_concept_page + re-index-on-render) · B4 (wire recipes) · B5 (green).
**Derived-ledger, round-4 (links-only, rebuild-stable)** — `docs/reviews/plan-047-review.md`.

## Goal
Each concept page shows a `BEGIN-AUTO:mentions` block listing every source that **`mentioned`** the
concept as `- [[source]]` (deduped, sorted — **no quote/span**), **regenerated** from
`page_entity_refs` (Class B, rebuildable), preserving the rest of the page.

## Key design pins (from the 3 review rounds — do NOT regress)
- **Links only, `ref_type='mentioned'`** — the quote/span are NOT rendered (extract-time LLM
  quote+span ≠ `reindex --full` footer-line quote → not rebuild-stable). The linking-source SET is
  the only stable invariant (R-5). `get_backlinks` default returns ALL inbound edge kinds (typed
  edges, cited, …) → MUST filter to `ref_type='mentioned'` (R-1/ARCH-R3-4).
- **`write_concept_page` DOES change** — the create path emits the `BEGIN-AUTO:mentions` markers (seeded
  with the create source) **in place of** today's hardcoded `## Mentions <quote-block>`; else the legacy
  block duplicates/diverges from the rendered one (R047-2/ARCH-R3-5).
- **Re-index on render** — `--concept-mentions` rewrites bytes → it MUST update `pages.file_hash` for
  each page it rewrites, or every render leaves a spurious `hash-mismatch` drift (ARCH-R3-3). Rebuild
  path: `reindex --full` → `--concept-mentions`.
- **Byte-baseline** — the new block format re-baselines concept-page content hashes once AND changes
  the **karpathy concept-page byte-identity golden anchor** → update it + affected eval pins here (R047-4).
- **No `GENERATED-AT` timestamp** in the block (would break R-2/R-5 byte-identity). New non-greedy
  `BEGIN-AUTO:<name>` regex, distinct from `_CUSTOM_BLOCK_RE`. Empty block when no mentions; exclude self.
- **NO in-page lint drift-guard** — R-9 is NOT a lint check (PW-Q only covers whole-file `auto_indexes[]`);
  render corrects hand-edits on next run.

## Context (files)
- `scripts/wiki_index/sqlite_repository.py` — `get_backlinks(vault_id, entity_slug, ref_type=...)`;
  add a **single** query enumerating a vault's concept-page entity slugs (entities that HAVE a page;
  resolve each to its on-disk path via the layout's `_concepts/` dirs incl. course-tier) — avoid N+1.
- `scripts/wiki_index/rendering.py` — `sanitize_markdown_text`, `atomic_write`; the `BEGIN-CUSTOM`
  marker precedent (write a SEPARATE `BEGIN-AUTO` regex).
- `scripts/wiki_index/reindex.py` — how a single page's `file_hash` is computed/updated (reuse for re-index-on-render).
- `scripts/wiki_skills/wiki_index_render.py` — CLI (`--auto-indexes` precedent; add `--concept-mentions`).
- `scripts/wiki_skills/wiki_extract_concepts/_pages.py` — `write_concept_page` (replace legacy `## Mentions` with AUTO markers).
- `_validation.classify_candidates` + `__init__._apply_write` — UNCHANGED (re-mention upserts the ref; render reads it).

## Steps
1. **B1 — RED** `tests/test_concept_mentions.py` (full import→render path, two sources): R-1 block lists
   both `- [[source]]` deduped/sorted, **+ a typed-edge backlink to the same slug is EXCLUDED**; R-2
   re-render no-new-ref → byte-identical, +1 `mentioned` → +1 entry; R-3 name/definition/prose/`BEGIN-CUSTOM`
   byte-preserved; R-4 renders after `wiki-confirm`; R-9 no `hash-mismatch` after render + create emits
   AUTO markers not legacy `## Mentions`. Plus empty/self-ref/zero-mention cases.
2. **B2 — renderer** `rendering.py`: `render_concept_mentions_block(repo, vault, entity_slug)` (distinct
   `mentioned` source slugs, sorted, sanitized, empty-safe, self-excluded) + `apply_auto_block(existing_md,
   block_name, body)` (NEW non-greedy `BEGIN-AUTO:<name>`…`END` replace; preserve rest; insert after
   definition / before `BEGIN-CUSTOM`; no timestamp) + the single concept-page enumeration query.
   Deterministic, no `import anthropic`.
3. **B3 — wire** `wiki-index-render --concept-mentions` (sweep → regenerate → atomic-write →
   **re-index each rewritten page (update `pages.file_hash`)** → log). `write_concept_page` create →
   emit AUTO markers (seeded with the create source) in place of legacy `## Mentions`. **Update the
   karpathy byte-identity anchor + affected eval pins.**
4. **B4 — recipes** `workflows/wiki-import.md` + `workflows/wiki-sync.md`: after a batch apply, run
   `--concept-mentions`; document the `reindex --full → --concept-mentions` rebuild path. (Verified by B11 dogfood.)
5. **B5 — green**: B1 + existing `test_extract_concepts*`/`test_import_*`/`test_render*`/eval pins
   (incl. updated karpathy anchor) pass; `mypy --strict` clean.

## Acceptance
- [ ] R-1/R-2/R-3/R-4/R-9 green; no regression; `mypy --strict` clean; karpathy anchor updated intentionally.

## Risk (mutation spot-check in review)
- **B2 AUTO-block replace** — greedy/mis-anchored regex eats the definition or a `BEGIN-CUSTOM` island.
- **B3 re-index-on-render** — forgetting `file_hash` update → spurious drift on every render.
- Deterministic ordering of the source list (byte-stable R-2/R-5).
