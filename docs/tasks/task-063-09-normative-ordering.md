# TASK 063-09 — ★ the **NORMATIVE ORDERING** (the 7th surface)

**Phase**: 3 (apply validation) · **RTM**: R-063-2 (ordering) · **Type**: code · **Effort**: 2–3h
**Depends on**: 063-07, 063-08 · **Unblocks**: 063-10

## Goal

Pin the order of operations in `apply`, and make a violation of it **impossible** rather than
merely unlikely.

```
1. schema + anti-fabrication      (063-06)
2. slug derivation                (063-07)
3. IN-BATCH collision             (063-07)  → contract violation, exit 4
4. ★ EXISTING-PAGE collision RE-CHECK  → DROP the colliding candidates
5. ★ G1 + G2 validate the POST-DROP batch     (063-08, 063-10)
6. ★ if a SURVIVING candidate references a DROPPED one ⇒ CONTRACT VIOLATION, refuse, exit 4
7. write                          (063-12)
```

## Why this is a real bug and not bookkeeping

Validate `{D, R}` where `D.implements: [[r-slug]]` — the range check passes against the **in-batch**
R. Then drop R on a slug collision. Then write D anyway. **D's edge now resolves to the PRE-EXISTING
page of that slug** — whose class (`summary`) ∉ `implements.to` ⇒ **a new `ontology-violation`.**

And **both halves of the property are blind to it**:
- the counts still reconcile (the dropped candidate was never written) ⇒ **G6 passes**;
- G1/G2 already passed — **against a batch that no longer exists** ⇒ the delta property is what
  finally catches it, *after* the damage.

> **A validation computed against a hypothetical batch is not a validation of what got written.**
> A benign drop is benign only when nothing in the batch depends on it.

## Steps

1. Restructure `apply` so the drop set is computed **before** `validate_ontology` / `validate_refs`
   are called, and both receive the **post-drop** list. Not "call them in the right order" — pass the
   post-drop list as the **only** list they can see, so the wrong batch is not reachable.
2. After the drop, compute `referenced_dropped = {c for c in survivors
   if c.edges/links ∩ dropped_slugs}`. Non-empty ⇒ `DROPPED_CANDIDATE_STILL_REFERENCED`, **exit 4,
   zero writes**, listing each `(survivor, dropped_target)` pair.
3. **Escalation, not a warning.** The drop was benign; the *dependency on the drop* is not.

## Context — files

- **Edit** `scripts/wiki_skills/wiki_extract_decisions/__init__.py` (`_apply_validate` /
  `_apply_write` split — mirror the precedent's structure so the DB is opened once, after validation).

## Tests (RED first) — `tests/test_extract_decisions_ordering.py` (new)

- `test_the_spec_scenario_verbatim` — the `{D, R}` case above:
  seed an existing page `r-slug` of class `summary`; submit `{D(implements → r-slug), R(title → r-slug)}`;
  ⇒ **exit 4, `DROPPED_CANDIDATE_STILL_REFERENCED`, ZERO files written.**
  **MUT:** validate the **pre-drop** batch (i.e. call G1 before the drop) ⇒ D is written and the vault
  gains an `ontology-violation` ⇒ RED via the assert that the decisions dir is empty. *This is the
  test the 7th surface exists for.*
- `test_drop_with_no_dependents_is_still_benign` — a dropped candidate nobody references ⇒ exit **0**,
  the survivors are written, warning emitted. The escalation must not swallow the benign case.
- `test_g1_sees_the_post_drop_batch` — instrument `validate_ontology` (monkeypatch) and assert the
  list it received **excludes** the dropped candidate. Assert on the **input to the validator**, not
  on the outcome — an outcome test can pass for the wrong reason.

## Exit criteria

- [ ] `pytest tests/ -q` ≥ 2477 passed. `mypy --strict scripts/` clean.
- [ ] The post-drop list is the **only** list reachable by G1/G2 — verified by
      `test_g1_sees_the_post_drop_batch`, which inspects the validator's actual argument.
- [ ] **MUT:** reorder (drop after validate) ⇒ `test_the_spec_scenario_verbatim` RED.
- [ ] Code comment at the ordering site quotes the invariant verbatim, so a future refactor that
      "simplifies" the order meets the reason in situ.

## Rollback

Restore the naive order — and 063-15's property test fails. Which is the correct signal, and is why
the property is a conjunction.
