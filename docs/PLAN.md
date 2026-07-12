# PLAN 061 — Honest denominators + the two fail-open fixes

Spec: `docs/TASK.md` (TASK 061, **v6** — v5 approved after three blocking task-reviews; **v6**
amends R-061-2 after the plan-review found the 7th recurrence of the task's own fractal: `wiki-lint`
runs **two** config-driven checks, not one).
Branch: `task-061-honest-denominators-and-fail-open-fixes`.
Plan revision: **v2** (plan-review CHANGES-REQUESTED: 1 blocking + 2 major + 2 minor, all folded in).

Each bead below is **independently shippable** and ends with `pytest tests/` +
`mypy --strict scripts/` **green** and one commit. Stub-First: Phase 1 lands
structure + contract tests (green on stubs); Phase 2 replaces stubs with logic and
flips the assertions to real values. The one *deliberately RED* test (R-061-5) is
landed as `@pytest.mark.xfail(strict=True)` so the suite stays green while the gate
is **mechanically proven** to fail before the fix (a strict xfail ERRORS if it passes).

---

## 0. The review lens (bake into every bead)

The task's thesis — *a check that examined nothing reports green* — proved **fractal**:
it recurred five times inside the spec written to fix it, always as the same failure
mode: **asserting that a mechanism covers a surface without enumerating the surfaces it
actually covers.**

> **Standing exit criterion.** Any bead that claims *"renders in all N surfaces"* or
> *"one X per Y"* MUST carry a **grep step that enumerates the surfaces**, and paste
> the enumeration into the bead's Notes. A count in this plan is a **floor, never a
> ceiling** — re-grep at implementation time; the code may have moved.

The census run during planning already found **five surfaces the spec's own RTM file-lists
missed** (see §5 *Planning refinements*). The plan-review then caught the **7th recurrence** —
in this plan: `wiki-lint` runs **two** config-driven semantic checks (`lifecycle-drift` **and**
`ontology-violation`), **both gating `--strict`** (the CI rail), and PLAN v1's `061-03` gave a
denominator to only one. Spec amended to **R-061-2 v6**; `061-03` rewritten. Expect more —
**re-grep at implementation time; every count in this plan is a floor, never a ceiling.**

## 1. Non-negotiable constraints (violating any of these fails review)

1. **Zero DDL.** `user_version` stays **7**. No `ALTER`, no new index (P-5). Envelope keys
   are **additive only** — no rename, no removal; every pre-061 key still parses.
2. **Frozen archives are NOT edited**: `docs/tasks/task-050-*.md`, `docs/plans/plan-050-*.md`,
   and the **Q-050 entries** in `docs/architectures/open-questions.md`. Verify with
   `git diff --name-only` before every commit.
3. **Do NOT assert `total_gaps ≤ examined`** — it is FALSE on correct data (two rules may
   target one class ⇒ one page can gap twice). Invariants are asserted **per rule**, against
   **that rule's own family denominator**.
4. **Do NOT reuse the bare noun `pages_examined`** for the ontology property family
   (`property_pages_examined`) — coverage already owns that noun for a different population.
5. **Fixtures:** the typed fixture for drift must carry **both typed pages AND the inverse
   edges** (`tests/_health_fixtures.py::build_health_vault` already does — `dec-old2` gets the
   derived inverse `superseded-by`), or `matched` stays 0 and the fixture proves nothing.
6. **Decision-17** preserved: no `import anthropic` anywhere; one JSON envelope + stable exit
   code per CLI. `wiki-health` **always exits 0** (ADR-006 unchanged).

---

## 2. Phase 1 — structure, stubs, contract tests (green on stubs)

- [ ] **[R-061-1]** `061-00` — Health-report **models + DAL report methods as stubs** +
      contract tests. New frozen dataclasses `RuleStat` / `CoverageReport` / `DriftReport` /
      `OntologyReport` in `scripts/wiki_index/models.py`; three abstract
      `find_*_report()` methods on `IndexRepository`; stub impls in `_health_rules.py` that
      delegate to today's finders and return denominators hardcoded to `0` + empty
      `rule_stats`. Contract test asserts the **shape** and that `report.findings == legacy
      list method` output. → `docs/tasks/task-061-00-health-report-models-stubs.md`

- [ ] **[R-061-5]** `061-05` — the **RED gate**, landed first and proven RED:
      `tests/test_wiki_config_provenance.py::test_parsed_block_unknown_key_reaches_effective`,
      **ADDED** (the existing `test_evolution_new_schema_field_needs_no_code` /`future_block`
      test is **NOT retargeted** — it legitimately covers the raw-passthrough `else` branch at
      `_provenance.py:326`). Parametrized over `summarize` **and** `resummarize` **and** a
      NESTED pointer (`/resummarize/detect/…`); asserts on the **rendered HTML report**, not
      just `build_ui_model`. Marked `@pytest.mark.xfail(strict=True)` ⇒ suite green, gate
      proven. → `docs/tasks/task-061-05-parsed-block-gating-test.md`

## 3. Phase 2 — logic

### 3a. Honest denominators (R-061-1, R-061-2)

- [ ] **[R-061-1]** `061-01` — **three denominators, three populations**, per-rule `matched`
      in `_health_rules.py`; the legacy list methods become thin wrappers over the report
      (one code path, no drift). Coverage → `pages_examined`; ontology **edge** rules →
      `edges_examined`; ontology **property** rules → `property_pages_examined`. Untyped
      fixture ⇒ all denominators `0`; typed fixture ⇒ exact non-zero counts; per-rule
      invariants (domain and range asserted **separately** against `matched_e` — see §4 P-061-A).
      → `docs/tasks/task-061-01-three-denominators-dal.md`

- [ ] **[R-061-1]** `061-02` — `wiki-health` **envelopes carry the denominators** (additive
      keys: `pages_examined` / `edges_examined` / `property_pages_examined` / `by_rule[]`),
      plus an `examined_nothing` note so `{"total_gaps": 0}` can never again be mistaken for a
      real green. Exit code stays 0 always. → `docs/tasks/task-061-02-wiki-health-envelopes.md`

- [ ] **[R-061-2]** `061-03` — `wiki-lint`: denominators for **BOTH** config-driven semantic
      checks (spec **v6**) — `lifecycle-drift` (`lint.py:185`) **AND `ontology-violation`**
      (`lint.py:221`); **both gate `--strict`**, i.e. the CI rail, and `061-01` has already
      computed the ontology numbers. Drift gets per-rule `matched` **and its own
      `pages_examined`** (so `matched: 0` distinguishes *"no `decision` pages at all"* from *"50
      decisions, none carrying the edge"*). `run_all_checks_report()` +
      `check_lifecycle_drift_report()` + `check_ontology_violations_report()` added; the existing
      list-returning functions stay as wrappers (`scripts/benchmark.py` + tests untouched); both
      no-ops (no `drift_rules` / no `ontology:` ⇒ **no DAL call**) preserved. Payload is
      **per-check-keyed** (P-061-D). Advisory-by-default + `--strict` gating unchanged.
      → `docs/tasks/task-061-03-lint-check-denominators.md`

### 3b. The trust fail-open (R-061-3)

- [ ] **[R-061-3]** `061-04` — **one shared constant, rendered into BOTH halves** — pure
      refactor, ZERO behavior change: `policy.EXTERNAL_PROVENANCE_KEYS` (today's 3 keys) drives
      the Python `_is_external` loop **and** the `_EXT` SQL literal in `_search.py`; the
      Q-050-3 alignment test is re-parametrized **from the constant**; a grep-test forbids a
      second enumeration anywhere in `scripts/`.
      → `docs/tasks/task-061-04-shared-external-key-constant.md`

- [ ] **[R-061-3]** `061-06` — **extend the constant to the case variants**
      `{source, Source, SOURCE, url, Url, URL}` (`_EXT` grows 8 → 14 `LIKE` disjuncts) ⇒ the 18
      `Source:` pages derive `external` and are floored by `--min-trust internal`. **The
      residual is test-pinned in the same breath:** a `youtube: https://…` fixture asserts
      `trust == "internal"` **today**, docstring citing **Q-061-4**; when Q-061-4 lands the test
      flips to `external`. → `docs/tasks/task-061-06-case-variant-keys-and-q0614-pin.md`

### 3c. wiki-config: the parsed-block fail-open (R-061-4) and the advisory `zones` (R-061-6)

- [ ] **[R-061-4]** `061-07` — `show.effective` is built by **overlaying the parsed dataclass
      onto the merged raw dict** for **every parsed cascading block** (`summarize` AND
      `resummarize`), via a generic dispatch table so a future parsed block inherits the fix.
      Removes the `xfail` from `061-05` ⇒ **RED → GREEN**. Adds the invariant test: *show never
      emits a `provenance` pointer with no corresponding `effective` value*.
      → `docs/tasks/task-061-07-parsed-block-overlay.md`

- [ ] **[R-061-6]** `061-08` — **Q-061-3 Option A′: generalize, don't badge.** Render
      `FieldSpec.description` in `show` **and** `_report.py` (it renders in `serve` **only**
      today — `_report.py` has 0 `description` hits and `_cmd_show` bypasses `build_ui_model`).
      The `zones` advisory text then becomes **data, not code** — and every future field's
      description renders with zero further code. Re-word `ZONE_GLOB_NO_MATCH` so it stops
      implying enforcement; correct the manual's `.wiki/sync.yaml` row (+ its RU mirror).
      → `docs/tasks/task-061-08-fieldspec-description-and-zones-advisory.md`

### 3d. Docs — the `_raw/` retrieval claim (R-061-7)

- [ ] **[R-061-7]** `061-09` — correct **every LIVING surface** claiming a `_raw/` capture
      appears in retrieval (all 4 built-in layouts ignore `**/_raw/**` — verified — so that limb
      cannot fire in normal operation). Name the **http(s) frontmatter key** as the operative
      signal; document `_raw/` as a **backstop** for direct upserts / custom layouts. The census
      found **9 sites across 7 files** (the RTM named 4). Record **Q-061-1…Q-061-4** as NEW
      entries in `open-questions.md`. Frozen archives untouched.
      → `docs/tasks/task-061-09-raw-retrieval-claim-and-open-questions.md`

## 4. Phase 3 — gates

- [ ] **[R-061-1..7]** `061-10` — final gates: full `pytest tests/`, `mypy --strict scripts/`,
      the **additive-only envelope proof** (a test asserting every pre-061 envelope key still
      exists), the **zero-DDL proof** (`PRAGMA user_version == 7`), the **frozen-archive proof**
      (`git diff --name-only` excludes `task-050-*`/`plan-050-*`/Q-050), module-memory
      `.AGENTS.md` updates, and the optional LIVE confirmatory anchor (`wiki-health coverage`
      on the personal vault reads `pages_examined: 0` despite 713 `concept` pages).
      → `docs/tasks/task-061-10-final-gates.md`

---

## 5. Planning refinements (derived during planning — apply as written)

**P-061-A — the ontology edge invariant is per (rule × KIND), not per rule.**
The RTM writes `∀ edge rule e: violations_e ≤ matched_e ≤ edges_examined`. Taken as
*violations_e = domain_e + range_e*, that is **FALSE on correct data**: one examined ref row
can be **both** a domain violation (bad source class) **and** a range violation (bad target
class) ⇒ `violations_e = 2 > matched_e = 1`. This is the *same* error class the spec itself
forbids for totals. So assert:

```
∀ edge rule e:  domain_e ≤ matched_e   AND   range_e ≤ matched_e   AND   matched_e ≤ edges_examined
∀ property rule p:  property_p ≤ matched_p ≤ property_pages_examined
∀ coverage rule r:  gaps_r     ≤ matched_r ≤ pages_examined
∀ drift rule d:     drift_d    ≤ matched_d ≤ pages_examined   (drift's own denominator)
```

(`domain_e ≤ matched_e` holds because domain findings are de-duplicated per
`(page, project, edge)`; `range_e ≤ matched_e` because each examined row yields at most one
range finding.) Hence `RuleStat.findings` is a **dict of per-kind counts**, not one integer.

**P-061-B — the surface census found 5 sites the RTM's file-lists missed.** Grepped, not
believed:

| Surface | Why it is a surface | Bead |
|---|---|---|
| `scripts/wiki_skills/wiki_query.py:877` | a **SECOND** `--min-trust` argparse help (on `apply`) — the RTM says "the argparse help", singular | 061-06 / 061-09 |
| `docs/architectures/security.md:198-200` | LIVING arch doc: names `Source:` as an **accepted evasion** — R-061-3 **closes** it, so leaving it makes the doc false | 061-09 |
| `docs/manuals/obsidian-llm-wiki_manual.md:1811` | enumerates the key list **and** the `_raw/` claim | 061-09 |
| `docs/manuals/obsidian-llm-wiki_manual.md:2089` | glossary: "`external` (web capture / `_raw/`)" | 061-09 |
| `docs/manuals/obsidian-llm-wiki_manual.ru.md:1860` | the RU mirror of 1811 (TASK 059 keeps EN/RU in lockstep) | 061-09 |

**P-061-C — degenerate-SQL guard.** Every new denominator query is an `IN (...)` over a class
/ edge set that **may be empty** (a layout with no rules). Never compose `IN ()` — return `0`
before touching SQL (the `_health_rules.py` "hand-built rule → skip, never crash, never
inject" precedent).

**P-061-D — the bare noun `pages_examined` now names TWO populations.** Coverage's = ⋃
`coverage_rules[].class`; drift's = ⋃ `drift_rules[].class`. This is safe **only** because they
never share an envelope (`wiki-health` vs `wiki-lint`) **and** because lint's payload is
**per-check-keyed** (`lifecycle-drift.pages_examined` vs
`ontology-violation.{edges_examined, property_pages_examined}`). **Any future surface that merges
these payloads MUST re-qualify the noun** — flattening them reruns C6 (two populations, one
denominator) on a new surface. The sentence lives in `LintReport`'s docstring, not only here.

**P-061-E — report-row pointer keying (verified, not assumed).** `_report_md._flatten` recurses
on **`dict` only** — a list is a **leaf**, so a list key's report row is `/zones` (which *does*
have a FieldSpec), never `/zones/0`. A naive `pointer in ui_model` lookup would therefore
*silently* yield `""` for any pointer that ever falls outside the model. `061-08` resolves the
description by **nearest ancestor**, mirroring `resolve_origin` — the precedent already used at
`_report.py:117` for exactly this problem.

---

## 6. RTM coverage

| RTM ID | Requirement (short) | Beads |
|---|---|---|
| **R-061-1** | three denominators + per-rule `matched` + per-family invariants | `061-00`, `061-01`, `061-02` |
| **R-061-2** (v6) | **BOTH** lint checks report denominators — `lifecycle-drift` (per-rule `matched` + its own `pages_examined`) **AND** `ontology-violation` (`edges_examined` / `property_pages_examined`); both gate `--strict` | `061-03` |
| **R-061-3** | one shared external-key constant → both halves; parametrized alignment test; Q-061-4 pin | `061-04`, `061-06` |
| **R-061-4** | `show.effective` overlays the parsed dataclass onto the merged raw dict, every parsed block | `061-07` |
| **R-061-5** | ADDED parsed-block gating test; RED before R-061-4, GREEN after; asserts on the rendered report | `061-05`, `061-07` |
| **R-061-6** | `FieldSpec.description` rendered in `show` + `_report.py`; `zones` advisory; `ZONE_GLOB_NO_MATCH` re-worded | `061-08` |
| **R-061-7** | four (→ nine) LIVING `_raw/` surfaces corrected; frozen archive untouched | `061-09` |
| *(all)* | zero-DDL / additive-envelope / frozen-archive / suite gates | `061-10` |

## 7. Dependency order

```
061-00 ──► 061-01 ──► 061-02
                └───► 061-03
061-04 ──► 061-06
061-05 ──► 061-07 ──► 061-08
061-06 ─┐
061-08 ─┼─► 061-09 ──► 061-10
061-02 ─┘
061-03 ─┘
```

`061-00`, `061-04` and `061-05` are independent and may be landed in any order.
