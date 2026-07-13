# TASK 061 — Honest denominators + the two fail-open fixes

## 0. Meta Information
- **Task ID**: 061
- **Slug**: honest-denominators-and-fail-open-fixes
- **Origin**: the R-16…R-22 enterprise-theme dogfood on the LIVE personal vault (2026-07-12).
  6 probes + adversarial verification (5 of 11 candidate findings **refuted**). Recorded in auto-memory
  `enterprise-theme-dogfood-2026-07`.
- **Type**: Fix (correctness + reporting honesty)
- **Effort**: M
- **Schema**: **zero DDL** (`user_version` stays 7). Read-side counts + one shared constant + tests + docs.
  Envelope keys are **additive only** — no renames/removals; existing consumers keep parsing (Decision-17
  one-envelope contract preserved).
- **Revision**: v4, after **three** BLOCKING task-reviews. v2 folded in C1–C4 + M1–M6 and carved Part E out
  to TASK 062. v3 folds in **C5** (Option A was false — `description` renders in `serve` only; adopt
  Option A′, generalize), **M7** (the denominator invariant was unimplementable and, as `total_gaps ≤
  examined`, *false*), and **M8** (Q-061-2's rationale re-based on Q-050-3 alignment; the 18-page residual
  made honest + test-pinned). v4 folds in **C6** — `find_ontology_violations` spans **two**
  populations (edges for domain/range, **pages** for property enums), so one denominator would have left
  the vacuous green alive and made the invariant false again.
  v5 = **APPROVED**, with E1 (R-061-7's fourth surface was a *frozen archive* the spec forbids touching →
  swapped for the LIVING arch doc, which restates the same claim) and E2 (drift's `matched: 0` could not
  distinguish "no typed pages" from "typed pages, no edges" → added its own `pages_examined`) folded in.
  **Pattern named (C3/C5/C6/E1/E2 are ONE failure mode):** *asserting that a single mechanism covers a
  surface without enumerating the surfaces it actually covers.* This task's own thesis — a check that
  examined nothing reports green — proved **fractal**, recurring five times inside the spec written to fix
  it. **Carry this as the review lens into implementation:** every "renders in all three surfaces" or
  "one denominator per check" in the diff needs a **grep, not a belief**.

## 1. Problem

The enterprise theme (R-16 policy / R-17 trust / R-18 freshness / R-19 ontology / R-22 config) is
**built correctly and fires on nothing**. Every mechanism was proven to work in scratch vaults; on the
real vault four of five layers are inert. Unifying diagnosis: **three bugs, one disease — a check that
examined nothing reports green.**

| Level | Reports green | Reality |
|---|---|---|
| **Data** | `wiki-health` → `0 violations` / `0 gaps` | **nothing was examined** — 0 typed pages; `page_entity_refs` holds only `mentioned` (empty typed event graph) |
| **Runtime** | `--min-trust internal` → "floored" · the always-on `trust` annotation → `internal` | **36 http-valued pages derive as `internal`** — the trust layer **fails OPEN**. Two mechanisms: **18** are a *case* variant (`Source:`) → **closed here** (R-061-3); **18** are *vault-specific keys* (`youtube:` 9, `teachable:` 9) → **remain open by decision**, tracked + test-pinned as **Q-061-4**. This task does **not** advertise a 36-page fix |
| **Test** | `test_evolution_new_schema_field_needs_no_code` → PASS | it exercises the case that *works*; the invariant it gates (R-058-10) is **violated** |

`{"total_gaps": 0}` is indistinguishable from a real green — that ambiguity invalidates the entire
baseline: every "0 violations" observed to date carries **zero information**.

**Explicitly NOT in the problem set** (refuted during the dogfood — do not re-raise): the stale inverse
edge after `--delta` (documented: inverse-removal deferred to `--full`, provenance-safe); the BD zone's
`extract_concepts: true` (**correct** — the TASK 052 participants guard is in code, keyed on pyramid
grammar, not on that flag; only the zone's *comment* is stale).

## 2. Goal

Make the shipped capability **tell the truth**, and close the two things that are silently wrong.
Adoption of typed knowledge on real content is **TASK 062** (prerequisite: this task).

## 3. Requirements Traceability Matrix

| ID | Requirement | Acceptance | Files |
|---|---|---|---|
| **R-061-1** | **A denominator PER POPULATION, with the correct noun, positively defined.** There are **three** populations across the two checks — `find_coverage_gaps` iterates pages; `find_ontology_violations` iterates **both** edges (domain/range) **and** pages (property enums) in one call. Emit:<br>• **`pages_examined`** (coverage) = pages whose **authored** class (`$.type`) ∈ ⋃ the coverage rules' `class` fields (the ADR-003 typed classes). Pages with **no** `$.type`, or a non-typed class (`concept` / `moc` / `*-summary`), are **NOT examined**.<br>**⚠️ `find_ontology_violations` spans TWO populations in ONE call** — it needs **two** denominators, bound to `OntologyViolation.kind`:<br>• **`edges_examined`** = refs whose `ref_type` ∈ the layout ontology's **declared edge vocabulary** (positive definition; `verifies` is not merely undeclared but **undeclarable** — it is ∉ `_INVERSE_REF_TYPE`, so `validate_ontology` rejects it). Binds kinds **`domain` + `range`** (`for edge in ontology.edges` → `FROM page_entity_refs`).<br>• **`property_pages_examined`** = pages whose `$.type` ∈ ⋃ `ontology.properties[].class`. Binds kind **`property`** (`for prop in ontology.properties` → `FROM pages p`). **Do NOT reuse the bare noun `pages_examined`** — coverage already uses it for a *different* population (⋃ `coverage_rules[].class` ≠ ⋃ `ontology.properties[].class`).<br>• per-rule **`matched`** = rows meeting that rule's precondition | **Invariant, asserted PER RULE, against its OWN family's denominator:**<br>`∀ coverage rule r: gaps_r ≤ matched_r ≤ pages_examined`<br>`∀ edge rule e: violations_e ≤ matched_e ≤ edges_examined`<br>`∀ property rule p: violations_p ≤ matched_p ≤ property_pages_examined`<br>⚠️ **Totals MAY exceed their denominator** — the schema permits two rules on one class, so one page can gap/violate twice. **Do NOT assert `total_gaps ≤ examined`** (it fails on correct data).<br>⚠️ A single `edges_examined` for the whole ontology check would leave the vacuous green alive exactly where this task claims to kill it: `{"total_violations": 12, "edges_examined": 0}` is **incoherent** (property rules examined pages, not edges) — and would bite hardest right after TASK 062.<br>Anchored on **in-repo fixtures**: untyped fixture ⇒ denominators `0`; typed fixture ⇒ non-zero. **LIVE anchor (confirmatory):** reads **0 despite 713 `concept` pages**. Exit code stays **0 always** (ADR-006 unchanged) | `scripts/wiki_index/sqlite_repository/_health_rules.py`, `scripts/wiki_skills/wiki_health.py`, `tests/` |
| **R-061-2** | **BOTH** of `wiki-lint`'s config-driven semantic checks report denominators — **`lifecycle-drift`** (`lint.py:185`→`find_lifecycle_drift`) **AND `ontology-violation`** (`lint.py:221`→`find_ontology_violations`). **Both gate `--strict`**, i.e. the CI rail; naming only drift (as v1–v5 did — the **7th** recurrence of this task's own fractal) would leave `wiki-lint` printing `ontology-violation: 0` with no denominator on the one surface that gates CI, while R-061-1 has *already computed* those numbers and thrown them away. Lint's payload is **per-check-keyed** (`lifecycle-drift.pages_examined` vs `ontology-violation.{edges_examined,property_pages_examined}`) so the `pages_examined` noun never collides across populations in one envelope.<br>Drift emits per-rule `matched` **AND `pages_examined`** = pages whose `$.type` ∈ ⋃ `drift_rules[].class`. **Why both:** the drift precondition is `$.type = class` **AND `EXISTS(ref_type = edge)`** (`_health_rules.py:59-65`), so `matched` counts only pages that *already carry the edge* — meaning bare `matched: 0` cannot distinguish **"no `decision` pages at all"** (today's LIVE state) from **"50 `decision` pages, none with a `superseded-by` edge"** (the state right after TASK 062). Same disease, one requirement over | **Invariant:** `∀ drift rule r: drift_r ≤ matched_r ≤ pages_examined`. **Fixture must carry BOTH typed pages AND the inverse edges** — a typed-pages-only fixture leaves `matched` at 0 and would "prove" non-vacuity while proving nothing. Advisory-by-default + `--strict` gating unchanged | `scripts/wiki_index/lint.py`, `_health_rules.py` |
| **R-061-3** | **One shared constant** defines the external-origin provenance keys **with their case variants**, and is **rendered into both halves** (Python `_is_external` + the `_EXT` SQL literal). Docstrings **reference** the constant instead of re-enumerating it | The 18 `Source:` pages derive as `external` and are floored by `--min-trust internal`. The SQL↔Python alignment test (Q-050-3) is **parametrized FROM the constant**, so a future key cannot drift the halves apart.<br>**The residual is stated in the same breath, not buried:** after this task **18 pages carrying vault-specific provenance keys (`youtube:`/`teachable:`) still derive as `internal`** — known, tracked as **Q-061-4**.<br>**Residual is TEST-PINNED** (the task's own ethic applied to itself): a fixture page with `youtube: https://…` asserts `trust == "internal"` **today**, docstring citing Q-061-4; when Q-061-4 lands the test **flips to `external`**. An invisible residual becomes a visible, tracked one.<br>**Blast radius (state in docs):** default search output is UNCHANGED; only explicit `--min-trust internal\|verified` callers see the pages drop out | `scripts/wiki_index/policy.py:243,251`, `scripts/wiki_index/sqlite_repository/_search.py:149-159`, `scripts/wiki_index/repository.py:259`, `skills/wiki-query/SKILL.md:87`, `docs/architectures/functional/policy-and-trust.md:38`, `tests/test_trust_tier.py` |
| **R-061-4** | `wiki-config show`'s `effective` is built by **overlaying** the parsed dataclass onto the merged raw dict, for **every parsed cascading block** — currently `summarize` **and `resummarize`** (both take the frozen-dataclass path at `_provenance.py:320-324`), stated generically so a future parsed block inherits the fix | A new field inside **either** block appears in `show.effective` **and** gets an HTML-report row. **Invariant (tested):** `show` never emits a `provenance` pointer with no corresponding `effective` value | `scripts/wiki_skills/wiki_config/_provenance.py:319-334`, `_report.py:110` |
| **R-061-5** | **ADD** a gating test for the parsed-block case (do **not** retarget the existing `future_block` test — it legitimately covers the raw-passthrough `else` branch at `_provenance.py:326`). Parametrized over `summarize` **and** `resummarize`, asserting on the **rendered report**, not just `build_ui_model` | The new test **FAILS before R-061-4 and passes after** (a real gate, not a vacuous one). The existing `future_block` test still passes | `tests/test_wiki_config_provenance.py` |
| **R-061-6** | `zones:` is surfaced as **advisory — not enforced** (parsed + linted, but never read by `iter_sync_candidates()`; only `exclude:` scopes the walk). **Decision: Q-061-3 Option A′ — GENERALIZE, don't badge.** `FieldSpec.description` is currently rendered by **`serve` only** (`_server.py:195`); `_report.py` never reads it (0 hits) and `_cmd_show` bypasses `build_ui_model` entirely. So make **one small generic change** — render `FieldSpec.description` in `show` and in `_report.py` (which already holds `ui_model`). The `zones` advisory text is then **data, not code**. Also re-word the `ZONE_GLOB_NO_MATCH` lint so it stops implying enforcement | After the one-time generic change, the `zones` advisory text appears in **all three** surfaces — **and every future field's `description` does too, with zero further code**. This **strengthens** the TASK 058 schema-driven invariant rather than eroding it (a strictly smaller and more general change than the `x-wiki-advisory` + badge path, which stays deferred). Manual line 539 corrected | `config/sync-config.schema.yaml`, `scripts/wiki_skills/wiki_config/{__init__.py,_report.py,_lint.py,_findings.py}`, `docs/manuals/obsidian-llm-wiki_manual.md:539` |
| **R-061-7** | Correct the **four LIVING** surfaces claiming a `_raw/` capture appears in retrieval (all built-in layouts exclude `**/_raw/**`, so that limb cannot fire in normal operation). Name the http(s) frontmatter key as the operative signal; document `_raw/` as a backstop for direct upserts / custom layouts. **The frozen archive `docs/tasks/task-050-*.md` (UC-3) is deliberately NOT corrected** — it records what was believed *at authoring time*, and rewriting it is exactly what the frozen-archive rule prevents. The corrected belief lives **here**, in TASK 061, which is its right home | All four read correctly; no predicate or SQL change | `skills/wiki-query/SKILL.md:86`, `skills/wiki-query-synthesis/SKILL.md:29`, the `--min-trust` argparse help, **`docs/architectures/functional/policy-and-trust.md:38`** (the LIVING arch doc — it restates the `_raw/` path-segment claim, so it is a surface here as well as for R-061-3) |

**Frozen archives must NOT be edited** (they record state at authoring time): `docs/tasks/task-050-*.md`,
`docs/plans/plan-050-*.md`, and the Q-050 entries in `docs/architectures/open-questions.md`.

## 4. Open Questions (decisions recorded, not left to the implementer)

- **Q-061-1 — denominator nouns.** *Settled:* **three** denominators, because there are **three
  populations**, not two — coverage → `pages_examined`; ontology edge rules → `edges_examined`; ontology
  **property** rules → `property_pages_examined`. Rationale: `find_ontology_violations` iterates edges for
  domain/range **and pages for property enums**, in one call. Collapsing them onto one noun reproduces the
  very bug this task fixes — a check reporting a denominator for a population it never examined (on LIVE
  that would have meant answering "how many pages did the ontology check?" with a count of 8836
  `mentioned` **refs**). One noun per population, or the honesty fix is itself dishonest.
- **Q-061-2 — enumerate vs case-fold the provenance keys.** *Settled: **enumerate the case variants from
  one shared constant**.* **The binding constraint is Q-050-3 alignment, not performance.** The SQL and
  Python halves must stay **provably identical**; SQL `json_extract` paths are case-**sensitive**, so a
  true fold requires `json_each` + `lower(key)` **in SQL only** — i.e. the cheap-looking asymmetric fix
  (fold in Python, enumerate in SQL) is exactly what Q-050-3 forbids. Enumerating
  `{source, Source, SOURCE, url, Url, URL}` from one constant keeps both halves renderable from the same
  source of truth, and the parametrized alignment test prevents future drift.
  *Honest limits:* this closes **100% of the observed leak**, not a class — a typo-shaped key (`uRL:`,
  `Source_URL:`) would still fail open; no tool emits those. `SOURCE`/`Url` have **0** LIVE pages and are
  cheap defense-in-depth (`_EXT` grows 8→14 `LIKE` disjuncts) — **not** justified by P-5, which is about
  speculative *indexes*, and must not be cited here.
- **Q-061-3 — `zones:` advisory marker.** *Settled: **Option A′ — generalize, don't badge.*** `FieldSpec`
  (`_uimodel.py:89-98`) is a **closed** dataclass and `x-wiki-*` annotations are **hand-read** — so
  `x-wiki-advisory` could NOT render with "zero interface code" (the TASK 058 invariant is *a new schema
  **field** needs no code*, not *a new **annotation kind** needs no code*). But plain **Option A was also
  false**: `description` is rendered by **`serve` only** — `_report.py` never reads it and `_cmd_show`
  bypasses `build_ui_model`. So: make the one-time change **generic** (render `FieldSpec.description` in
  `show` + `report`), which turns *every* field's description into rendered data forever. Option B
  (extend `FieldSpec` + badge) stays deferred until a **second** advisory field exists.
- **Q-061-4 — vault-specific provenance keys (`youtube:` 9, `teachable:` 9 — 18 http-valued pages).**
  *Deferred by mechanism, NOT by defect.* The **mechanism** differs (a shared constant vs. a new per-vault
  `external_keys:` config surface — a new config surface does not belong in a fix task). The **defect does
  not**: a page whose provenance is an `http(s)` URL derives as `internal`. The trust contract is about
  external *origin*, not key spelling.
  **Raised stakes:** §5 withdraws the `--min-trust` floor and names the always-on per-hit `trust`
  **annotation** "the valuable half" — and that annotation will label these 18 pages `internal`. So the
  residual is **not** "an unused filter leaks"; it is **"the surface the operator actually uses mislabels
  18 pages."** That raises Q-061-4's follow-up priority accordingly. Pinned by the R-061-3 regression test.

## 5. Out of scope (deliberate, recorded)

- **Activating policy on LIVE** — re-keys the `question_hash` of already-filed answers; the operator's
  documented posture (declared-but-OFF) is correct.
- **Flipping BD to `resummarize.mode: if-changed`** — would trigger a re-ingest storm: the
  provenance-gated sources have no recorded hash, so `if-changed` falls through to ingest.
- **Adopting `--min-trust internal`** — withdrawn by the dogfood: on this vault `external` ≈ the operator's
  curated reference library (693 of 707 external pages are clippings/Learning), and the floor drops the
  best-scoring hits. The always-on per-hit `trust` annotation is the valuable half.
- **Making `zones:` enforcing** — a behavior change; R-061-6 only makes its advisory nature honest.
- **The typed-knowledge pilot on the LIVE vault** → **TASK 062** (carved out per task-review C4: different
  risk class, different verification regime — operator-attested vs CI-verifiable).

## 6. Completion

**SHIPPED 2026-07-13** — 11 beads (`061-00` … `061-10`), one commit each.

### Test counts

| | Before (pre-061 baseline) | After |
|---|---|---|
| `pytest tests/` | **2266 passed, 5 skipped** | **2325 passed, 5 skipped** (**+59**) |
| `mypy --strict scripts/` | clean, 88 files | **clean, 88 files** |

### The gates, each as a command that was run (not asserted)

| Gate | Result |
|---|---|
| **Zero DDL** | `git diff --stat 75e1425..HEAD -- sql/` → **empty**; no `ALTER TABLE` / `CREATE INDEX` added in any code file; `PRAGMA user_version` still **7**, pinned by `tests/test_schema_v4.py:31` + `test_schema_v5.py:39`. All denominators are read-side `COUNT(*)`. |
| **Additive-only envelopes** | The pre-061 key sets were **enumerated from git** (`git show 75e1425:…`), not remembered: coverage `{action, vault, rules, total_gaps, by_class, gaps}` · ontology `{action, vault, total_violations, by_kind, by_class, violations}` (+`note` on the no-contract path) · lint `{action, vault, total_issues, by_category}`. Each is frozen as a literal and asserted a **subset** of the emitted keys (`test_tc_02_4_additive_only_*`, `test_lint_envelope_additive_and_non_gating`). |
| **Frozen archives** | `git diff --name-only 75e1425..HEAD \| grep -E "docs/(tasks/task-050\|plans/plan-050)"` → **empty**. No `Q-050` line removed or modified in `open-questions.md` (the only Q-050 mentions in the diff are **new `+` lines** inside Q-061-2, which *cites* Q-050-3 by name). |
| **Decision-17** | `grep -rnE "^\s*(import anthropic\|from anthropic)" scripts/` → **empty**. |
| **No `total ≤ examined`** | Every `<= …examined` line in the suite is **per-rule** (`stat.findings[k] <= stat.matched <= <family>_examined`). The forbidden **total** form appears **nowhere**, and two tests carry an explicit comment saying why it is forbidden (`test_lint_denominators.py:129`, `test_health_denominators.py:240`). |
| **Noun discipline** | `pages_examined` is used **only** by coverage and by drift (their own, disjoint populations, never in one envelope — P-061-D). The ontology property family uses **`property_pages_examined`**, always. |

### LIVE confirmatory anchor — the whole thesis, made visible

Run **read-only** against a `sqlite3 .backup` snapshot of the live `personal` DB
(3267 pages · authored-type census `(none) 2403 · concept 713 · lesson-summary 66 ·
article-summary 51 · meeting-summary 30 · moc 2` · ref census **`mentioned` 8836 and nothing
else**). All three surfaces exit **0**, as they always did:

```
wiki-health coverage → {"rules": 3, "total_gaps": 0, "pages_examined": 0, …,
  "note": "coverage rules are configured, but NO page carries an authored $.type in those
           classes — nothing was examined (this is not a clean bill of health)"}

wiki-health ontology → {"total_violations": 0, "edges_examined": 0,
  "property_pages_examined": 0, …,
  "note": "an ontology contract is configured, but NO page_entity_refs row carries a declared
           edge type AND no page carries an authored $.type in the property classes —
           nothing was examined (this is not a clean bill of health)"}

wiki-lint → denominators.personal.lifecycle-drift.pages_examined            = 0
            denominators.personal.ontology-violation.edges_examined         = 0
            denominators.personal.ontology-violation.property_pages_examined = 0
```

**Before this task all three printed a bare `0` and looked healthy.** They now say, in the
same breath, that they examined **nothing** — across **24 declared rules** (3 coverage +
3 drift + 7 edge + 11 property), every one of which matched **0 rows**.

### What the plan got WRONG (found only by hitting the code)

1. **The LIVE vault's rules are NOT absent — they are declared and empty.** The spec, the
   plan, ADR-006 and both `.AGENTS.md` all say the health/ontology rules are *"cybos only"*.
   That is true of the **built-in** layouts **only**: the live `personal` vault ships its own
   `.wiki/layout.yaml` carrying **3 coverage + 3 drift + 18 ontology rules**. This makes the
   anchor *stronger* than predicted (the surfaces are in the **declared-but-vacuous** state,
   not the no-op state — exactly the case D-036-4 exists to expose), and it means the bare
   *"cybos only"* claim was itself a small instance of this task's fractal. Corrected in
   ADR-006 D-036-3 and both module-memory files; `models.py` already had it right.
   *(Still un-corrected, out of this bead's scope:* `docs/ROADMAP.md` 606/806/817/1153,
   `docs/manuals/obsidian-llm-wiki_manual.md:901`, `docs/ARCHITECTURE.md:247` — historical
   shipped-log entries; flagged, not rewritten.)*
2. **Bead `061-10` assumed a knowledge-health section exists in `docs/architectures/`.** It
   does not — `grep -rln "coverage_rules\|drift_rules\|lifecycle-drift" docs/architectures/`
   returns only `open-questions.md`. The real body is **`docs/adr/ADR-006`**, so the
   denominator contract landed there as amendment **D-036-4** (ADR-002/ADR-008 set the
   amendment precedent) plus a shipped entry in the living `docs/ARCHITECTURE.md`.
3. **`policy.py` had no `.AGENTS.md` entry at all** — the module owning
   `EXTERNAL_PROVENANCE_KEYS`, the one constant this task made load-bearing, was invisible to
   module memory. Added, with the "edit the constant, never the SQL literal" rule stated.

### Still open (deliberate)

- **Q-061-4** — vault-specific provenance keys (`youtube:` 9 pages, `teachable:` 9) still
  derive `internal` despite an `http(s)` value. Deferred by **mechanism** (it needs a
  per-vault `external_keys:` config surface, which does not belong in a fix task), **not** by
  defect. **Test-pinned in its known-wrong state on both halves**
  (`test_vault_specific_provenance_key_still_internal_q0614`) — when Q-061-4 lands, the test
  flips to `external` and the pin becomes the gate.
- **TASK 062** — adoption of typed knowledge on real content. This task is its prerequisite:
  it is what makes TASK 062's progress *measurable* (the denominators go from 0 to non-zero).
- **Q-061-3 Option B** (`x-wiki-advisory` + a rendered badge) stays deferred until a **second**
  advisory field exists; Option A′ (generalize `FieldSpec.description`) shipped instead.
