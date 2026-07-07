# TASK 047 — Derived "Mentions across sources" ledger on concept pages; retire `wiki-enrich` + vendored `wiki_ingest`

## 0. Meta Information
- **Task ID**: 047
- **Slug**: additive-concept-merge
- **Depends on**: TASK 046 (converged construct path — merged to `main`)
- **Decision history**: review chose *option 2* (compound concept pages, then retire the legacy
  on-ramp). Two adversarial plan-review rounds on a **body-merge** design surfaced a blocker +
  6 high (it fights the confirm lifecycle, the entity/page slug duality, the pure-fn collision
  guard, layout `_concepts`-dir resolution, H-6, and concurrency). **Pivoted to a derived/rendered
  ledger** (`docs/reviews/plan-047-review.md`): same visible result, Class-A/B-clean, none of those
  hazards exist by construction.

## Problem / Motivation
1. **Concept pages don't compound.** A concept page (`# name / definition / ## Mentions <one
   source quote-block>`) is re-filed by **content-hash overwrite**; a 2nd source mentioning the same
   concept never adds to the page. The accumulating behaviour lived only in the vendored `wiki_ingest`
   (reachable solely via the legacy `wiki-enrich` on-ramp).
2. **`wiki-enrich` is a redundant on-ramp** (6,372 LOC of vendored `scripts/wiki_ingest/` + a
   vendoring policy §7.4 + drift tests), dead after TASK 046's converged `wiki-import`/`wiki-sync`.

## Goal
Make each concept page show a **compounding "Mentions across sources"** section that is **derived**
(Class B, rebuildable) from the existing `page_entity_refs` table — NOT a Class-A read-modify-write
merge. Then **retire** `wiki-enrich` + the vendored `wiki_ingest` (a clean delete — the derived
design needs nothing ported).

## Design / Architecture (derived-ledger — grounded in existing machinery)

The data already exists: every source note's wiki-link to a concept is indexed in
**`page_entity_refs`**, queryable via **`get_backlinks(vault_id, entity_slug, ref_type='mentioned')`**. So:

```
# <name>
<definition>                              ← Class A, authored by wiki-extract-concepts (overwrite-on-create)

<!-- BEGIN-AUTO:mentions -->              ← Class B, DERIVED — regenerated from page_entity_refs
## Mentions across sources
- [[source-a]]
- [[source-b]]                            ← appears automatically once source-b's `mentioned` ref is indexed
<!-- END-AUTO:mentions -->
```

- **Source LINKS only — deduped, sorted, no quote/span (the rebuild-stability fix, ARCH-R3-1).** The
  block renders one `- [[source]]` per **distinct** source slug that has a **`ref_type='mentioned'`**
  inbound ref, sorted by slug. It does NOT render the quote/line-span: those are NOT a pure function
  of Class A — extract-time stores the LLM quote+multi-line span, but `wiki-reindex --full` rebuilds
  refs from the source's `## Entities` **footer-line** wikilink (a single-line, different quote). Only
  the *set of linking sources* agrees across both paths → only it is rebuild-stable (R-5). No
  `GENERATED-AT` timestamp in the block (would break byte-identity). Self-references and zero-mention
  pages render an empty (but present) block.
- **The block is rendered, never hand-merged**, preserving everything else on the page (name,
  definition, operator prose, any `BEGIN-CUSTOM` islands). Reuses `rendering.py` (`sanitize_markdown_text`,
  `atomic_write`) + a **NEW** non-greedy `BEGIN-AUTO:<name>`…`END-AUTO:<name>` regex (distinct from
  `_CUSTOM_BLOCK_RE`). On first render the block is inserted after the definition, before any `BEGIN-CUSTOM`.
- **`write_concept_page` DOES change (R047-2/ARCH-R3-5).** The create path emits the
  `BEGIN-AUTO:mentions`/`END-AUTO:mentions` markers **in place of** today's hardcoded `## Mentions
  <quote-block>` (else the legacy block duplicates/diverges from the rendered one) — seeded with the
  create source as the first `- [[source]]` entry. The re-mention path (`mention_list`) is unchanged
  (it upserts the ref; the render reads it). No ownership guard, no `derive_candidates` change, no slug-duality.
  > **Byte-baseline note (R047-4):** the new block format re-baselines every concept page's content
  > hash once (a one-time `updated` sweep) and changes the **karpathy concept-page byte-identity
  > anchor** — P1 updates that golden anchor + the affected eval pins (in-scope, called out, not a surprise).
- **Render↔reindex ordering (ARCH-R3-3).** Rewriting a page changes its bytes, so `--concept-mentions`
  **re-indexes each page it rewrites** (updates `pages.file_hash`) so it never leaves a spurious
  `hash-mismatch` drift. The full rebuild path is `reindex --full` (rebuild refs) → `--concept-mentions`
  (render + re-hash). Idempotent — re-running with no new refs is a no-op.
- **Fully rebuildable (Class A/B).** `wiki-reindex --full` rebuilds `page_entity_refs` from the source
  notes' footer wiki-links; the render rebuilds every Mentions block (a pure function of the linking-
  source set) → deterministic. The name/definition above the markers stays Class-A canonical. (No
  in-page lint-drift guard — render overwrites any hand-edit on the next run; the existing
  `hash-mismatch` drift already surfaces page edits. R-9 dropped — PW-Q only covers whole-file
  `auto_indexes[]` targets, not an in-page block.)
- **No hazards by construction:** no read-modify-write of accumulated state (regeneration); confirm
  lifecycle irrelevant (keys on refs, not `is_candidate`); H-6 = `sanitize_markdown_text`; concurrency
  = idempotent regeneration; no entity-vs-page slug coupling (render by `entity_slug`).

## Phases (stub-first within each)

- **P1 — derived mentions-ledger renderer (the meat).**
  `rendering.py`: `render_concept_mentions(repo, vault, entity_slug)` (or per-vault sweep) → build the
  `## Mentions across sources` list from `get_backlinks`, inject/replace ONLY the `BEGIN-AUTO:mentions`
  block, preserve the rest. Wire a `wiki-index-render --concept-mentions` mode. `write_concept_page`
  seeds the empty AUTO block on create. RED tests first (drive import of 2 sources → render → page
  shows both; rebuildable; idempotent; rest-preserved; confirmed concept still renders).
- **P2 — retire `wiki-enrich` + vendored `wiki_ingest` (clean delete).**
  Remove `bin/wiki-enrich`, `commands/wiki-enrich.md`, `skills/wiki-enrich/`, `workflows/wiki-enrich.md`,
  `scripts/wiki_skills/wiki_enrich.py`, the whole `scripts/wiki_ingest/` tree, and the vendored tests
  (`test_vendored_*`, `test_wiki_enrich`, `test__page_merge`, `test__markdown`, the vendored half of
  `test_layout_invariants`). **No port needed.** Update README (CLI 18→17, drop the ADR-001 Option-I
  diagram), `THIRD_PARTY_NOTICES.md`, `CLAUDE.md`, `WIKI-INGEST-V1.1-CONTRACT.md` (archive), §7.4
  vendoring policy, `.AGENTS.md`.
- **P3 — evals + docs + dogfood.**
  R-5 rebuildability test (reindex --full + render reproduces the Mentions blocks deterministically);
  update `docs/ARCHITECTURE.md` + functional-architecture §2.3 + extend ADR-007; dogfood on a
  `samples/` vault (two sources → a concept page showing both; re-render idempotent; `--full` rebuild
  reproduces). Final gate.

## Requirements (RTM)

| ID | Requirement | Phase | Acceptance test |
|----|-------------|-------|-----------------|
| R-1 | After two sources mention a concept, the rendered `BEGIN-AUTO:mentions` block lists **both** sources as `- [[source]]` (deduped, sorted, `ref_type='mentioned'` only — no quote/span, no typed-edge backlinks), via the full import→render path | P1 | `test_concept_mentions_lists_all_sources` + `test_concept_mentions_excludes_typed_edges` |
| R-2 | The render is **idempotent** — re-running with no new refs leaves the page byte-identical (no `GENERATED-AT` stamp; deterministic order); a new `mentioned` ref adds exactly one entry | P1 | `test_concept_mentions_render_idempotent` |
| R-3 | The render **replaces ONLY** the AUTO block — name, definition, operator prose, and `BEGIN-CUSTOM` islands are byte-preserved (non-greedy `BEGIN-AUTO` regex) | P1 | `test_concept_mentions_preserves_rest` |
| R-4 | A **confirmed** concept (`is_candidate: false` after `wiki-confirm`) still renders its Mentions block (render keys on refs, not lifecycle) | P1 | `test_concept_mentions_renders_after_confirm` |
| R-5 | `wiki-reindex --full` (rebuild refs from footers) + `--concept-mentions` reproduces every block **byte-deterministically** (Class A/B — the linking-source SET is the stable invariant; quotes/spans intentionally NOT rendered) | P3 | `test_reindex_full_rebuilds_concept_mentions` |
| R-6 | `wiki-enrich` (bin/cmd/skill/workflow/script) and `scripts/wiki_ingest/` removed; no runtime import of `wiki_ingest` remains | P2 | `test_no_wiki_ingest_imports` + grep |
| R-7 | Docs reflect 17 CLIs; `THIRD_PARTY_NOTICES` drops `wiki_ingest`; no dangling links | P2 | doc-lint / `wiki-lint` |
| R-8 | **Per-phase exit gate**: full suite green + `mypy --strict` clean; existing extract-concepts/import/sync/render evals pass (incl. the **updated karpathy concept-page byte-identity anchor**) | all | `pytest` + `mypy` + eval pins |
| R-9 | `--concept-mentions` **re-indexes each page it rewrites** (updates `pages.file_hash`) → no spurious `hash-mismatch` drift; `write_concept_page`'s create path emits the AUTO markers **in place of** the legacy `## Mentions` quote-block (no duplicate) | P1 | `test_concept_mentions_no_drift_after_render` + `test_write_concept_page_emits_auto_block_not_legacy` |

## Invariants to preserve
- **Class A/B/C** — name/definition = Class A; the Mentions block = Class B (regenerated from
  `page_entity_refs`, which `wiki-reindex --full` rebuilds). No accumulation lives only in Class A.
- **Decision-17** — the renderer is deterministic Python; no `import anthropic`.
- **Zero-DDL** — `page_entity_refs` already exists; no schema change.
- **H-6** — rendered source links/titles pass `sanitize_markdown_text` (as index.md rendering does).
- **Collision guard (TASK 039)** — untouched: the **overwrite-on-create** semantics + the existing
  collision guard are unchanged. (`write_concept_page`'s create-time BODY changes — legacy `## Mentions`
  → AUTO markers — but it still fires only for a NEW concept; the re-mention path is untouched.)

## Out of scope
- The collision guard / `derive_candidates` / the REASON contract / the re-mention routing (all unchanged).
- A literal Class-A body-merge (the rejected design — `docs/reviews/plan-047-review.md`).
- **Per-source quote/span in the ledger** — not rendered: not rebuild-stable across extract-vs-reindex
  (ARCH-R3-1). Links only.
- **An in-page lint drift-guard** for the AUTO block — render corrects any hand-edit on the next run;
  the existing `hash-mismatch` drift already surfaces page edits; PW-Q covers only whole-file
  `auto_indexes[]` targets, so no new lint machinery is built (R-9 reframed to the re-index contract).
- `## Contradictions` / definition reconciliation across sources (definition stays the latest authored one).

## Verification
- `pytest tests/` green; `mypy --strict scripts/` clean.
- `samples/` dogfood: import source A → concept page with an AUTO-mentions block listing A; import
  source B (same concept) → render → the page lists A **and** B; re-render → byte-identical;
  `wiki-reindex --full` + render → identical Mentions blocks.
- `grep -rn 'wiki_ingest' scripts/` clean of imports; `wiki-enrich` gone; README = 17 CLIs.
