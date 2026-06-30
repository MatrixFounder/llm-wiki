# Plan review — TASK 047 (additive concept-merge) — REJECTED → reworked

Adversarial 3-lens plan review (rtm-atomicity / architecture-invariants / risk-gaps), each
adversarial. **4 blocker · 7 high · 9 medium · 2 nit.** All three lenses: not ready to develop.
The draft plan targeted the **wrong function**; reworked before any code.

## Blockers (all confirmed against the code)
- **B-1 (merge path unreachable).** A 2nd source mentioning an existing concept routes via
  `classify_candidates` (`_validation.py`) to `mention_list`, and `_apply_write` (`__init__.py`)
  only calls `write_concept_page` for `create_list`. So rewriting `write_concept_page` never fires
  for the compounding scenario — the page never grows. **Fix:** the merge hook is the **mention
  path**, not the create path.
- **B-2 (upstream collision guard pre-drops the re-mention).** `wiki_import_article._authoring.derive_candidates`
  drops a candidate whose slug ∈ `existing_page_slugs` as `collides-existing-page`; `existing_page_slugs`
  (`_context.py`) is built from indexed slugs ∪ **every on-disk `_concepts/*.md` stem**. So after
  source A files `foo`, source B's `foo` is dropped before apply. **Fix:** make the guard
  **ownership-aware** — an engine-owned colliding page passes through (→ merge); a foreign page is
  still dropped.
- **B-3 (owner discriminator wrong & unreliable).** `write_concept_page` hardcodes `type: concept`
  for every entity type, and `type` is not an ownership marker (an operator can author `type: concept`).
  **Fix:** owner = frontmatter `is_candidate: True` **AND** `source_page` present **AND** the `## Mentions`
  structure (the engine's own load-bearing markers, guarded by `test_extract_concepts_candidate_regression`).
- **B-4 (collision guard mislocated in the plan).** `wiki_extract_concepts apply` has no
  `existing_page_slugs`/owner check at all; the guard is purely upstream in a different skill. The
  merge must **self-guard inside the engine** so the direct-`apply` + `wiki-sync` paths are protected.

## High (folded into the rework)
- append_mentions_block is **net-new** code, not a "port" (the vendored primitives use a different
  `## Facts`/`## Sources` line-item shape; the host uses blockquote Mentions). Port only the
  `_markdown` masking + section helpers; **drop** `append_fact`/`upsert_source_row`/`upsert_footnote`.
- `append_contradiction` / materially-different-definition is unspecified + untested → **out of scope**
  (deterministic first-wins definition; later definitions ignored).
- Merge must **preserve existing frontmatter** (first-seen `date`, `is_candidate`, `type`, `source_page`,
  `name`, first-wins `definition`); only the `## Mentions` section is appended.
- **Same-source re-file with changed quote/span**: dedupe-by-source = **upsert** (replace that source's
  block) so idempotency holds and re-extraction updates; identical → `unchanged`.
- Concurrency: additive merge is read-modify-write → **single-writer** posture documented (apply is
  serialized; a per-concept lock is a follow-up).
- Tests must drive the **full apply loop** with `known_slugs` pre-populated (end-to-end growth), not
  call `write_concept_page` directly.

## Medium/nit (folded)
dedupe by **exact** attribution line (not substring → no `foo`/`foo-bar` prefix mis-fire); migration
fixture (pre-047 page grows on next mention); hand-edited page preservation (only `## Mentions` touched);
reindex must preserve `is_candidate` + stable Mentions ordering + line-number stability (R-5);
provenance-completeness (a Mentions block for every filed source); CONCEPTS_DROPPED/footer/manifest
accounting for the formerly-`collides-existing-page` candidate now merged; R-8 reframed as a per-phase
exit gate.

## Resolution (round 1)
TASK 047 §Design + RTM + PLAN P1 + task-047-01 reworked to the **mention-path + ownership-aware-guard**
design; re-reviewed.

## Round 2 — 4 blockers → 1 blocker + 6 high + 12 medium (design keeps revealing depth)
The rework cleared the original blockers but surfaced that body-merge fights several existing invariants:
- **ARCH-1 (blocker)** — owner discriminator used `is_candidate: True`, but `wiki-confirm` flips it to
  `false`; a CONFIRMED concept page (still engine-owned, the one that SHOULD compound) would be read as
  foreign → compounding silently dies on confirm. (Fix: key on the `is_candidate` *key presence* +
  `source_page` + `## Mentions`, not its value.)
- **F1 (high)** — `known_slugs` (entities table) ≠ `existing_page_slugs` (pages ∪ on-disk stems); a
  passed-through collision can classify as `create` → overwrite, not `mention` → merge.
- **F2/ARCH-2 (high)** — `derive_candidates` is pure/no-I/O and `existing_page_slugs` is a flat
  `list[str]` (no slug→path); the ownership check needs the page path + a frontmatter read, across the
  prepare→apply envelope.
- **RG-1/2/3 (high)** — merge-only applies must still bump `source_state` (idempotency); ownership lookup
  must resolve ONLY against the layout's `_concepts/` dir (note-slug / other-stem collisions); course-tier /
  multi-`_concepts` layouts must target the SAME dir `write_concept_page` would, or provenance forks.
- **ARCH-5 (medium, security)** — merged quotes on the import/sync path bypass `write_concept_page`'s H-6
  sanitization.
- + first-wins definition silently loses corrections (ARCH-4); intra-source double-mention (RG-5);
  concurrency lost-update (RG-7); pre-047 migration shape (RG-6).

**Assessment:** all are fixable ("pin-the-behaviour-and-add-a-test"), and the plan IS converging — but
body-merge is a large, invariant-sensitive change (confirm lifecycle, entity/page/slug duality, pure-fn
boundary, layout dir resolution, H-6, concurrency) for a benefit (literal page-body growth) that a
**derived/rendered** mentions-ledger could deliver Class-A/B-cleanly at a fraction of the risk. Escalated
to the user to re-decide approach before a round-3 rework.

## PIVOT — user chose the derived-ledger. Re-planned + re-reviewed (round 3)
TASK/PLAN/task-files rewritten to a **derived ledger**: concept-page bodies stay per-source; a
`BEGIN-AUTO:mentions` block is RENDERED from `page_entity_refs` (`get_backlinks`) by a new
`wiki-index-render --concept-mentions` mode. All 3 lenses confirmed the **direction is sound** (it
dissolves the body-merge hazards), but round 3 found **4 blockers + 7 high** — all *spec-tightening,
convergent* (not "can't work"). Folded into a round-4 rework:
- **ARCH-R3-1 (blocker) → render LINKS ONLY.** Quote/span are not rebuild-stable (extract-time LLM
  quote+span ≠ `reindex --full` footer-line quote); only the *set of linking sources* agrees across
  both paths. Ledger = `- [[source]]` deduped/sorted, no quote/span. (Simpler AND correct.)
- **RTM-1/ARCH-R3-2/R047-1 (blocker) → drop R-9 lint.** PW-Q only covers whole-file `auto_indexes[]`,
  not an in-page block; render corrects hand-edits on next run; existing `hash-mismatch` drift surfaces
  edits. R-9 reframed to the real re-index-on-render contract.
- **R047-2/ARCH-R3-5 (high) → `write_concept_page` emits the AUTO markers in place of the legacy
  `## Mentions`** (no duplicate).
- **ARCH-R3-3 (high) → `--concept-mentions` re-indexes each rewritten page** (`pages.file_hash`) — no
  spurious drift; rebuild path `reindex --full → --concept-mentions`.
- **ARCH-R3-4/R047-3 (high) → `ref_type='mentioned'`** (exclude typed-edge/cited backlinks).
- **R047-4 (high) → byte-baseline called out:** the new format re-baselines concept-page hashes once +
  updates the **karpathy byte-identity golden anchor** (in P1, not a surprise).
- Mediums folded: single concept-page enumeration query (no N+1), empty/self-ref cases, no
  `GENERATED-AT` timestamp, distinct `BEGIN-AUTO` regex, deterministic ordering.

**Round-4 status:** the derived design is now tight + internally consistent. Ready for a final
confirmation review or to develop, at the user's call.
