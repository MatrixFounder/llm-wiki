# TASK 063-07 — slug derivation via the LAYOUT'S `slug_strategy` + collision handling

**Phase**: 3 (apply validation) · **RTM**: R-063-12 · **Type**: code · **Effort**: 3h
**Depends on**: 063-05, 063-06 · **Unblocks**: 063-08, 063-09

## Goal

Derive every candidate's slug with **`_apply_slug_strategy(title, config.slug_strategy)`** — the
layout's own function — and enforce the two collision rules, which are **not** the same rule:

| collision | verdict | why |
|---|---|---|
| **IN-BATCH** — two candidates → one slug | **CONTRACT VIOLATION ⇒ refuse the batch, exit 4, zero writes** | ⚠️ cybos declares `slug_strategy: transliterate` and the source protocols are **Russian**. Two titles that transliterate to the same slug would have the second **silently overwrite the first on disk** — one decision lost, **one file, one DB row, ZERO lint issues**. Invisible to the delta property AND to a naive G6 count. |
| **EXISTING-PAGE** — a candidate's slug already exists (another source) | **benign drop + loud warning, exit 0** (the `CONCEPTS_DROPPED` precedent) — *subject to the normative ordering rule (063-09)* | it is someone else's page; we do not own it |

**Never a naive kebab.** This is the same "validate against the layout's grammar, never against an
assumption about it" invariant as G2 (063-10) and G4 (063-02), wearing a third costume.

## The re-check (a snapshot is not a guarantee)

`prepare`'s `existing_page_slugs` is a **snapshot**. A slug can appear between `prepare` and `apply`.
So **`apply` RE-CHECKS the collision set** against the repo it already has open — the snapshot is a
hint for the orchestrator, never the gate.

## Context — files

- **Edit** `scripts/wiki_skills/wiki_extract_decisions/_validation.py` (`derive_slugs`,
  `check_in_batch_collisions`), `__init__.py` (`_apply_validate` ordering).
- **Read** `scripts/wiki_index/layout_config.py::_apply_slug_strategy` (line 1112) — **the** slug
  function. Import it; do not reimplement it.
- **Read** `wiki_extract_concepts` `CONCEPTS_DROPPED` handling for the benign-drop envelope shape.

## Steps

1. `derive_slugs(candidates, config)` → `list[str]`, via `_apply_slug_strategy(cand["title"],
   config.slug_strategy)`.
2. `assert len(set(slugs)) == len(candidates)` — else `IN_BATCH_SLUG_COLLISION`, exit 4, listing
   **all** colliding pairs (one repair round).
3. Existing-page re-check on the open repo → `dropped: [{slug, reason: "existing-page-collision"}]`,
   loud `logger.warning`, exit 0. **The drop happens BEFORE G1/G2 — see 063-09.**

## Tests (RED first) — `tests/test_extract_decisions_slugs.py` (new)

- `test_transliterate_collision_refuses_the_batch` — the spec's case, verbatim: two Russian-titled
  candidates that transliterate to one slug ⇒ **exit 4, zero writes**, and the envelope names both.
  Assert on the **filesystem** (`len(list(decisions_dir.glob("*.md"))) == 0`), not only the envelope.
  **MUT:** drop the uniqueness assert ⇒ the test finds ONE file where it demanded ZERO ⇒ RED.
  *"Last one wins" is not a bug that shows up in lint. That is exactly why it needs its own gate.*
- `test_slug_uses_the_layout_strategy_not_a_kebab` — a Cyrillic title on cybos yields the
  **transliterated** slug; assert it equals `_apply_slug_strategy(title, "transliterate")` (call the
  engine in the test — never hardcode the expected string, or the test becomes the second source of
  truth).
- `test_existing_page_collision_is_a_benign_drop` — exit **0**, page not overwritten, warning
  emitted, `dropped[]` populated.
- `test_apply_rechecks_collisions_not_the_snapshot` — insert a colliding page into the DB *between*
  `prepare` and `apply` ⇒ `apply` still drops it. **MUT:** trust the snapshot ⇒ RED (the page gets
  clobbered).

## Exit criteria

- [ ] `pytest tests/ -q` ≥ 2477 passed. `mypy --strict scripts/` clean.
- [ ] **GREP:** `grep -rn "slugify\|kebab\|re.sub.*-" scripts/wiki_skills/wiki_extract_decisions/`
      ⇒ no hand-rolled slug derivation. The only slug source is `_apply_slug_strategy`.
- [ ] The in-batch refusal and the existing-page drop are **separate code paths with separate exit
      codes** — verified by both tests, not by one parameterised test that could pass with them fused.

## Rollback

Revert `_validation.py` slug helpers. `apply` still stubbed downstream.
