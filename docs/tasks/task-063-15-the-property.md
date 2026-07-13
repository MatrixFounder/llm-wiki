# TASK 063-15 — ★ **THE PROPERTY**: `(delta-clean) AND (G6)`

**Phase**: 5 (acceptance) · **RTM**: R-063-P (+ R-063-2, R-063-4, all of G1–G6) · **Type**: test · **Effort**: 4h
**Depends on**: 063-12, 063-13, 063-14 · **Unblocks**: 063-18

## Goal

The acceptance gate. **The property is a CONJUNCTION**, and this bead's only job is to make sure it is
tested as one.

> **`(delta-clean) AND (G6)`.**
> **The delta property catches HARM. G6 catches SILENCE.**
> *A rail that writes glob-invisible files — or that writes nothing at all — passes the delta property
> perfectly.*

## Half 1 — DELTA (harm)

> If the vault is `wiki-lint --strict`-clean **before** the run, it is still `--strict`-clean **after**
> `apply` + `wiki-reindex --full`.

**Test as `lint_issues_before == lint_issues_after`. NEVER as `lint_after == []`.**
`--strict` fails on **13 issue categories**, including pre-existing vault state the rail never touched.
An `== []` assertion tests the *fixture*, not the *rail*.

## ⚠️ `wiki-reindex --full`, NOT `--delta`

Drift reads the **auto-derived inverse** edges, and `--delta` leaves them transiently stale on one side
of a bidirectionally-authored edge (`scripts/wiki_index/lint.py:298`, verbatim: *"`--strict` drift
gating assumes a recent `--full`"*). A `--delta`-based test can report `lint_before == lint_after`
**while the vault is actually drifted** — *a check that examined nothing, reporting green, inside this
task's own acceptance criteria.* Pin it:

- [ ] `test_acceptance_uses_full_reindex` — greps this test module for `--delta` / `mode="delta"` and
      asserts **zero** hits. A comment saying "use --full" is not a gate; this is.

## Half 2 — ★ G6, the POSITIVE half (silence)

After `apply` + `wiki-reindex --full`, asserted **via the repo, not via lint** (lint is *structurally
incapable* of seeing a glob-invisible page: `find_pages_missing_in_index` walks via `discover_pages`,
so an unglobbed file is never even **discovered**):

| # | assertion |
|---|---|
| G6a | every written page has a `pages` row with the expected `slug` / `project` / `$.type` |
| G6b | every authored **forward** edge is in `page_entity_refs` **and its inverse is derived** |
| G6c | every **patched** page is re-indexed with its **new** hash (G5's positive half) |
| G6d | **counts reconcile**: `pages_written == pages_indexed`, `edges_authored == edges_indexed` |

## Tests — `tests/test_extract_decisions_property.py` (new)

Fixture: a **cybos** sample vault under `samples/` (gitignored per CLAUDE.md), seeded from a small
meeting summary + a realistic candidate batch (decisions + requirements + risks + a supersede).

1. `test_property_conjunction_on_a_clean_vault` — the full rail; assert **both** halves.
2. **★ `test_delta_property_alone_is_satisfiable_by_silence`** — the meta-test that justifies the
   conjunction. Monkeypatch `apply` to write **nothing**, run the delta check ⇒ **it passes**. Then
   run G6 ⇒ **it fails**. *This test asserts that our acceptance criterion is not satisfiable by doing
   nothing* — the structural twin of round 1's lesson, and the reason G6 exists.
   **If this test ever passes G6 with a no-op apply, G6 is not a gate.**
3. **★ `test_glob_invisible_page_is_caught_by_G6_not_by_lint`** — force a write outside the layout's
   globs (bypass the load gate in-test) ⇒ **lint delta is CLEAN** (proving lint's structural
   blindness) ⇒ **G6d's count reconciliation FAILS** (proving G6 catches it).
   *This is the empirical proof of the spec's central claim. Without it, "lint cannot see this" is an
   assertion; with it, it is a measurement.*
4. `test_supersede_creates_no_lifecycle_drift` — the 063-13 cases, end-to-end, under `--full`.
5. `test_prose_id_ref_creates_no_orphan_link` — the 063-10 case, end-to-end.
6. `test_dev_project_property_holds_vacuously_and_says_so` — dev-project: delta holds, and the
   envelope carries `vacuous_validation: true`. **Green, and honest about what it validated.**

## Exit criteria

- [ ] `pytest tests/ -q` ≥ 2477 passed (+ the new module). `mypy --strict scripts/` clean.
- [ ] **GREP-THE-SURFACES — the 13 lint categories are a denominator, and v1 asserted over them
      WITHOUT enumerating them (its first false claim).** Enumerate from the code:
      ```bash
      grep -rn "LintIssue(" scripts/wiki_index/lint.py | grep -o 'kind="[a-z-]*"' | sort -u | wc -l
      ```
      and assert in the test that the delta comparison is over the **full issue list**
      (`issues_before == issues_after` on the whole sorted list), never over a filtered subset. *A
      delta over a subset is the same lie in a smaller font.*
- [ ] **MUT (the load-bearing one):** make `apply` a no-op ⇒ the delta half **passes** and
      `test_property_conjunction_on_a_clean_vault` **fails on G6**. Verified by running it.
- [ ] **MUT:** swap `--full` → `--delta` ⇒ `test_acceptance_uses_full_reindex` RED.
- [ ] The fixture vault is **lint-clean before** the run — assert it (`lint_before` may be non-empty
      in principle, but the property's *premise* must be exercised; a fixture that is already dirty
      makes the delta trivially true).

## Rollback

n/a — this bead adds only tests. Its failure is the signal that an earlier bead is wrong.
