# PLAN 047 — Derived concept-mentions ledger + retire `wiki-enrich`/`wiki_ingest`

Phases by dependency: **P1 → P2 → P3** (P2's delete needs nothing from P1 — the derived design ports
no `wiki_ingest` code — but is sequenced after so the suite stays green through the filing change).
Stub-first within each phase (RED → GREEN). RTM IDs (R-1…R-9) from `docs/TASK.md`.

> **Pivoted from body-merge to a derived/rendered ledger** (`docs/reviews/plan-047-review.md`): the
> Mentions section is Class-B, regenerated from `page_entity_refs` — so Decision-17 / Class-A-B /
> zero-DDL / H-6 / the TASK 039 guard all hold trivially, and the round-2 blockers don't exist.

---

## P1 — derived concept-mentions renderer → [task-047-01](tasks/task-047-01-mentions-render.md)

**Issue:** each concept page must show a `BEGIN-AUTO:mentions` block listing every source that
references the concept, regenerated from `page_entity_refs` (`get_backlinks`), preserving the rest.

- **B1 [STUB+RED]** — `tests/test_concept_mentions.py` (RED), driving the **full import→render path**
  (two sources mention one concept): R-1 the AUTO block lists BOTH as `- [[source]]` (deduped, sorted,
  **no** quote/span) + a typed-edge backlink to the same slug is EXCLUDED; R-2 re-render no-new-ref →
  byte-identical (no `GENERATED-AT`), +1 `mentioned` ref → +1 entry; R-3 name/definition/prose/
  `BEGIN-CUSTOM` islands byte-preserved; R-4 still renders after `wiki-confirm` (`is_candidate: false`);
  R-9 after `--concept-mentions` the page is NOT flagged `hash-mismatch` (re-indexed), and `write_concept_page`
  create emits the AUTO markers, NOT the legacy `## Mentions` quote-block.
- **B2 [RENDERER]** — `scripts/wiki_index/rendering.py`: `render_concept_mentions_block(repo, vault,
  entity_slug) -> str` — `get_backlinks(vault, slug, ref_type='mentioned')` → **distinct source slugs**,
  sorted → `- [[source]]` (`sanitize_markdown_text`), empty block if none, exclude self. Plus
  `apply_auto_block(existing_md, block_name, body) -> str` — a **NEW** non-greedy `BEGIN-AUTO:<name>`…
  `END-AUTO:<name>` replace (distinct from `_CUSTOM_BLOCK_RE`), preserve everything else, insert after
  the definition / before any `BEGIN-CUSTOM` if absent, **no timestamp**. Add a **single** DAL query
  enumerating a vault's concept-page entity slugs (avoid N+1). Deterministic, no `import anthropic`.
- **B3 [WIRE render mode + write_concept_page]** — `wiki-index-render --concept-mentions`: sweep concept
  pages, regenerate each AUTO block, atomic-write, **re-index each rewritten page (update `pages.file_hash`)**
  so no spurious `hash-mismatch` drift, log. `write_concept_page` create path emits the
  `BEGIN-AUTO:mentions`/`END-AUTO:mentions` markers (seeded with the create source) **in place of** the
  legacy `## Mentions <quote-block>`. **Update the karpathy concept-page byte-identity golden anchor +
  affected eval pins** for the new format (one-time re-baseline, called out).
- **B4 [WIRE recipes]** — `workflows/wiki-import.md` + `workflows/wiki-sync.md`: after a batch apply,
  run `wiki-index-render --concept-mentions`; rebuild path = `reindex --full` → `--concept-mentions`.
  (Recipe edit verified by the B11 dogfood, not a pytest — noted in RTM.)
- **B5 [GREEN]** — B1 green; existing `test_extract_concepts*`, `test_import_*`, `test_render*`,
  `test_wiki_*_evals` (incl. the updated karpathy anchor) pass; `mypy --strict` clean.

**Exit (R-8 gate):** R-1/R-2/R-3/R-4/R-9 green; full suite + mypy clean.

---

## P2 — retire `wiki-enrich` + vendored `wiki_ingest` (clean delete) → [task-047-02](tasks/task-047-02-retire-enrich.md)

**Issue:** the legacy on-ramp + vendored tree are dead weight; the derived design ports nothing from
them, so this is a pure delete + reference cleanup.

- **B6 [REMOVE-CODE]** — `git rm` `bin/wiki-enrich`, `commands/wiki-enrich.md`, `skills/wiki-enrich/`,
  `workflows/wiki-enrich.md`, `scripts/wiki_skills/wiki_enrich.py`, the whole `scripts/wiki_ingest/`
  tree + any `.claude/`/`.agent/` symlinks. Verify nothing in `scripts/`/`bin/` imports
  `scripts.wiki_ingest` or shells `wiki-enrich`.
- **B7 [TESTS]** — delete the vendored-only tests (`test_vendored_ingest_api.py`,
  `test_vendored_import.py`, `test_wiki_enrich.py`, `test__page_merge.py`, `test__markdown.py`, the
  vendored half of `test_layout_invariants.py`). Add `test_no_wiki_ingest_imports.py` (R-6). Confirm
  no host code lost coverage (the derived renderer has its own tests from P1; nothing depended on the
  vendored masking).
- **B8 [DOCS]** — README (CLI 18→17, drop `wiki-enrich` row + ADR-001 Option-I diagram),
  `THIRD_PARTY_NOTICES.md` (drop `wiki_ingest`), `CLAUDE.md` (drop `wiki-enrich`/vendored `wiki-ingest`
  + WIKI-INGEST contract pointer + §7.4 vendoring policy), archive `docs/WIKI-INGEST-V1.1-CONTRACT.md`
  (ADR-001-superseded note), `.AGENTS.md` (both trees).

**Exit (R-8 gate):** R-6/R-7 green; `grep -rn 'wiki_ingest' scripts/ bin/` shows no code import; suite green.

---

## P3 — evals + docs + dogfood → [task-047-03](tasks/task-047-03-evals-docs.md)

- **B9 [EVAL/UNIT]** — R-5 `test_reindex_full_rebuilds_concept_mentions`: import two sources → render →
  delete DB → `wiki-init --register-existing` → `wiki-reindex --full` → `--concept-mentions` →
  byte-identical Mentions blocks (Class A/B; H-6-safe quotes). Optionally a wiki-import eval case for
  the rendered-compounding discipline.
- **B10 [DOCS]** — `docs/ARCHITECTURE.md` + functional-architecture §2.3 (the derived concept-mentions
  ledger; the AUTO-block pattern; rebuildability); extend ADR-007 with the decision (+ the rejected
  body-merge alternative, pointer to `plan-047-review.md`).
- **B11 [DOGFOOD]** — `samples/` vault: source A → concept page with AUTO block listing A; source B →
  render → lists A+B; re-render idempotent; a hand-edit above the markers survives; `--full` rebuild
  reproduces. Record the transcript.

**Exit (R-8 gate):** R-5 green; dogfood recorded; full gate (pytest + mypy + eval pins) clean.

---

## RTM → Bead map

| RTM | Bead(s) | Phase | Acceptance |
|-----|---------|-------|------------|
| R-1 | B1, B2, B3 | P1 | `test_concept_mentions_lists_all_sources` + `test_concept_mentions_excludes_typed_edges` |
| R-2 | B1, B2 | P1 | `test_concept_mentions_render_idempotent` |
| R-3 | B1, B2 | P1 | `test_concept_mentions_preserves_rest` |
| R-4 | B1, B2 | P1 | `test_concept_mentions_renders_after_confirm` |
| R-5 | B9 | P3 | `test_reindex_full_rebuilds_concept_mentions` |
| R-6 | B6, B7 | P2 | `test_no_wiki_ingest_imports` + grep |
| R-7 | B8 | P2 | doc-lint / `wiki-lint` |
| R-8 | exit gate | all | `pytest` + `mypy` + eval pins (incl. updated karpathy anchor) at every phase boundary |
| R-9 | B1, B3 | P1 | `test_concept_mentions_no_drift_after_render` + `test_write_concept_page_emits_auto_block_not_legacy` |
| (B4 recipe wiring) | B4 | P1 | non-pytest — verified by the B11 dogfood (recipe contains the render call) |

## Sequencing
1. **P1** (B1→B2→B3→B4→B5) — the derived renderer + `write_concept_page` AUTO-block + re-index-on-render + recipe wiring.
2. **P2** (B6→B7→B8) — clean delete of the on-ramp + vendored tree + references (no port).
3. **P3** (B9→B10→B11) — rebuildability proof, docs, dogfood.

Per-phase adversarial review (the TASK 046 rhythm). **B2/B3 are the highest-risk**: (a) the AUTO-block
replace must touch ONLY its region — a greedy/mis-anchored regex could eat the definition or a
`BEGIN-CUSTOM` island (mutation spot-check preserve-rest); (b) the re-index-on-render must update
`pages.file_hash` or every render leaves spurious drift.
