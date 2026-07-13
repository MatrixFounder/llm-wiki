# TASK 063-15 — ★ **THE PROPERTY**: `(delta-clean) AND (G6)`

**Phase**: 5 (acceptance) · **RTM**: R-063-P (+ R-063-2, R-063-4, all of G1–G6) · **Type**: test · **Effort**: 4h
**Depends on**: 063-12, 063-13, 063-14 · **Unblocks**: 063-18
**Revision**: v2 — plan-review **C-1** (G6 was itself satisfiable by silence) and **C-5** (the gate was
anchored on a gitignored tree) applied. PLAN §8.

## Goal

The acceptance gate. **The property is a CONJUNCTION**, and this bead's only job is to make sure it is
tested as one — *and that neither half can be satisfied by doing nothing.*

> **`(delta-clean) AND (G6)`.**
> **The delta property catches HARM. G6 catches SILENCE.**
> *A rail that writes glob-invisible files — or that writes nothing at all — passes the delta property
> perfectly.*

---

## Half 1 — DELTA (harm)

> If the vault is `wiki-lint --strict`-clean **before** the run, it is still `--strict`-clean **after**
> `apply` + `wiki-reindex --full`.

**Test as `lint_issues_before == lint_issues_after`. NEVER as `lint_after == []`.** `--strict` fails on
**13 issue categories**, including pre-existing vault state the rail never touched. An `== []`
assertion tests the *fixture*, not the *rail*.

### ⚠️ `wiki-reindex --full`, NOT `--delta`

Drift reads the **auto-derived inverse** edges, and `--delta` leaves them transiently stale on one side
of a bidirectionally-authored edge (`scripts/wiki_index/lint.py:298`, verbatim: *"`--strict` drift
gating assumes a recent `--full`"*). A `--delta` test can report `lint_before == lint_after` **while
the vault is actually drifted** — *a check that examined nothing, reporting green, inside this task's
own acceptance criteria.* Pin it:

- [ ] `test_acceptance_uses_full_reindex` — greps **this test module** for `--delta` / `mode="delta"`
      and asserts **zero** hits. A comment saying "use --full" is not a gate; this is.

---

## ★ Half 2 — G6, the POSITIVE half — **ANCHORED ON THE SUBMITTED CANDIDATE BATCH** (C-1)

> 🔴 **v1's G6 was itself satisfiable by silence.** It specced G6d as
> `pages_written == pages_indexed` / `edges_authored == edges_indexed` — **both numbers reported by
> the rail itself.** Under this bead's own no-op-`apply` meta-test: `written = []` ⇒ G6a/b/c
> **vacuously true**, G6d is **`0 == 0`** ⇒ **G6 PASSES.** The meta-test could not demonstrate what it
> claimed, and its `MUT:` line was **decorative**.
>
> **A self-consistency check between two of the rail's own outputs is not an external measurement.**

**The only external ground truth in the test is the candidate batch the test itself submitted.**
Anchor every clause on it, and read the "after" side from the **repo**, never from the rail's envelope
(lint is *structurally incapable* of seeing a glob-invisible page: `find_pages_missing_in_index` walks
via `discover_pages`, so an unglobbed file is never even **discovered**).

| # | assertion — LHS is the SUBMITTED BATCH, RHS is the REPO |
|---|---|
| **G6a** | for **every** candidate `c`: a `pages` row exists at `derive_slug(c)` with the expected `$.type` and `project` |
| **G6b** | for **every** authored forward edge in the batch: the ref row exists **and its inverse is derived** |
| **G6c** | for **every** page the batch *patched* (063-13): its `pages` row carries the **new** content hash (G5's positive half) |
| **G6d** | **`pages_indexed == len(candidates)`** and **`edges_indexed == Σ len(c.edges) (+ inverses)`** — counted from the **repo**, compared against the **batch** |

*(Why this anchor and not another: `test_glob_invisible_page_is_caught_by_G6_not_by_lint` passes under
**either** anchor — 3 written vs 2 indexed. Only the **batch** anchor also fails the no-op case. A
single anchor must satisfy **both** tests, and only this one does.)*

---

## ★ Fixture: build the vault in `tmp_path` — **NOT `samples/`** (C-5)

v1 anchored the flagship test on *"a cybos sample vault under `samples/`"* — and **`samples/` is
gitignored** (`.gitignore:39`). The house precedent is explicit: the one samples-dependent test is
`skipif`-guarded (`tests/test_wiki_config_validate.py:460`). **On a clean checkout, v1's acceptance
gate would SKIP — and a skipped gate joins the baseline's "5 skipped" silently.** *A check that
examined nothing, reporting green — in this task's acceptance criteria, for the third revision
running.*

**So:** build the cybos vault in `tmp_path` (seed a small meeting summary + a realistic candidate batch
— decisions, requirements, risks, a supersede). `samples/` is reserved for **063-18's manual dogfood**.

---

## Tests — `tests/test_extract_decisions_property.py` (new)

1. `test_property_conjunction_on_a_clean_vault` — the full rail; assert **both** halves.
2. ★ **`test_delta_property_alone_is_satisfiable_by_silence`** — the meta-test that *justifies* the
   conjunction. Monkeypatch `apply` to write **nothing**; then:
   - the delta half ⇒ **PASSES** (assert it — this is the point);
   - **G6 ⇒ FAILS** on G6a (candidate 1's `pages` row is absent) and G6d
     (`0 != len(candidates)`).
   **This test asserts that our acceptance criterion is not satisfiable by doing nothing.**
   **MUT (and this one is now REAL, not decorative):** re-anchor G6d on the rail's own
   `pages_written` ⇒ G6 passes under the no-op ⇒ **this test goes RED.** Run it. If G6 ever passes a
   no-op `apply`, **G6 is not a gate.**
3. ★ `test_glob_invisible_page_is_caught_by_G6_not_by_lint` — force a write outside the layout's globs
   (bypass the 063-02 load gate in-test) ⇒ **the lint delta is CLEAN** (proving lint's structural
   blindness — assert it) ⇒ **G6a/G6d FAIL** (3 submitted, 2 indexed). *This is the empirical proof of
   the spec's central claim: without it, "lint cannot see this" is an assertion; with it, it is a
   measurement.*
4. `test_supersede_creates_no_lifecycle_drift` — the 063-13 cases, end-to-end, under `--full`.
5. `test_prose_id_ref_creates_no_orphan_link` — the 063-10 case, end-to-end.
6. `test_dev_project_property_holds_vacuously_and_says_so` — **`dev-project` (post-063-02)**: the
   delta holds and the envelope carries `vacuous_validation: true`. **Green, and honest about what it
   validated.** ⚠️ This test is only *reachable* because **063-02 added dev-project's three `paths[]`
   globs** — before that, `prepare` **refused** the layout and this test could never pass (plan-review
   C-2). It is a dependency, not a detail.

## Exit criteria

- [ ] `pytest tests/ -q` ≥ 2477 passed (+ the new module), **0 skipped in this module** — verify with
      `pytest tests/test_extract_decisions_property.py -q -rs` that **nothing is skipped**. A skipped
      acceptance gate is the failure mode C-5 exists to prevent.
- [ ] `mypy --strict scripts/` clean.
- [ ] **GREP-THE-SURFACES — the 13 lint categories are a denominator, and the spec's v1 asserted over
      them WITHOUT enumerating them (its first false claim).** Enumerate from the code:
      ```bash
      grep -rn "LintIssue(" scripts/wiki_index/lint.py | grep -o 'kind="[a-z-]*"' | sort -u
      ```
      and assert the delta compares the **full sorted issue list**, never a filtered subset. *A delta
      over a subset is the same lie in a smaller font.*
- [ ] **MUT (the load-bearing one):** make `apply` a no-op ⇒ the delta half **passes** and
      `test_property_conjunction_on_a_clean_vault` **FAILS on G6a/G6d.** **Execute this mutation** —
      v1's version of it was decorative and nobody would have noticed.
- [ ] **MUT:** swap `--full` → `--delta` ⇒ `test_acceptance_uses_full_reindex` RED.
- [ ] The fixture vault is **lint-clean before** the run — **assert it**. The property's *premise* must
      be exercised; a fixture that is already dirty makes the delta trivially true.

## Rollback

n/a — this bead adds only tests. Its failure is the signal that an earlier bead is wrong, which is
what it is for.
