# PLAN 063 — `wiki-extract-decisions` (RFC-004): the typed-knowledge extraction rail

**Spec**: `docs/TASK.md` (v7, APPROVED after four blocking task-reviews + two operator requirements).
**Strategy**: Stub-First. Clone the proven Decision-17 `prepare` → orchestrator REASON → `apply`
rail from `wiki_extract_concepts`. 19 atomic beads, each independently shippable and **green at
every boundary**.

**Baseline (must never regress)**: `2477 passed, 5 skipped` · `mypy --strict scripts/` clean, 88 files.

---

## 0. The three rules that govern EVERY bead

These are not preamble. They are exit criteria, repeated per bead.

1. **GREEN AT EVERY BOUNDARY.** After each bead: `pytest tests/` ≥ 2477 passed, 0 failed;
   `mypy --strict scripts/` clean. A bead that leaves the tree red is not done.
2. **EVERY DENOMINATOR CLAIM CARRIES A GREP.** This project's signature failure mode — *asserting
   that a mechanism covers a surface without enumerating the surfaces it actually covers* — has
   recurred ~25 times, **four of them inside this spec**. Every instance was caught by a grep or a
   mutation test, **never by reasoning**. So: any bead whose exit criterion says *"covers all N"*,
   *"one X per Y"*, or names a population **MUST** carry an explicit **grep-the-surfaces** step that
   enumerates that population from the code, not from memory. Beads with such a claim:
   **00, 02, 04, 05, 08, 10, 12, 13, 15, 17, 18**.
3. **EVERY GATE IS MUTATION-TESTED.** For each new gate, the bead states the mutation and the test
   that must go RED under it: *would this test FAIL if the fix were reverted?* **A gate that cannot
   fail is the disease.** Recorded per bead as `MUT:`.

---

## 1. RTM — one requirement, one checklist item

Traceability is 1:1 with `docs/TASK.md` §4. Each item names the beads that discharge it.

- [ ] **[R-063-1]** `prepare` emits the ontology contract (roster, edge domain/range, status enums),
      known typed pages, `existing_page_slugs`, `--source-hash` handshake, house-standard
      denominators (`validation: {roster_size, edges_checked, properties_checked, links_checked}`)
      and a **`vacuous_validation: true`** marker when the layout declares no `ontology:`
      (dev-project). *A validator that examined nothing must not look green.* → **063-05**, **063-08**
- [ ] **[R-063-2]** **G1** — `apply` validates every candidate against the ontology BEFORE any write:
      class ∈ roster, edge **domain**, edge **RANGE** (out-of-batch target class resolved **from the
      DB**), `status` ∈ enum. **All** violations listed at once; validation failure ⇒ **ZERO** files
      written. → **063-08**, **063-09** (the normative ordering), **063-10** (G2, its ref-costume)
- [ ] **[R-063-3]** **G4** — typed pages go where the layout's READ globs can see them; placement
      (root-anchored vs sibling-of-source) is **DERIVED from the layout**, never hardcoded; every
      write path matches ≥1 of the layout's own `paths[]` globs (LOAD GATE). Supported set stated
      honestly: `cybos`, `dev-project`, and any vault whose `.wiki/layout.yaml` adds the classes;
      **karpathy and obsidian-personal map ZERO typed classes ⇒ `prepare` REFUSES.** → **063-02**,
      **063-05**, **063-12**
- [ ] **[R-063-3′]** **THE CONFIG SPLIT** — a new cascading `extract_decisions: {enabled, dirs}`
      block in **`.wiki/sync.yaml`** (schema-driven ⇒ visible in `wiki-config show`/`report`/`serve`
      with **zero interface-code changes**); the **CROSS-SYSTEM load gate** enforced in **BOTH**
      `wiki-config validate` (new finding code) **and** the rail's `prepare` preflight; an uncovered
      name is **REFUSED** with an actionable message (Q-063-5 = A, never auto-generate a glob).
      → **063-00**, **063-01**, **063-02**, **063-03**, **063-17**
- [ ] **[R-063-4]** Forward edges only; **inverses auto-derive at `wiki-reindex --full`** (M-1 intact).
      ⚠️ **NOT `--delta`** — inverse derivation is exactly what `--delta` leaves transiently stale
      (`lint.py:298`). → **063-12**, **063-15**
- [ ] **[R-063-5]** **Idempotent**: unchanged source ⇒ `action: unchanged`, zero writes; changed source
      ⇒ re-extract; `--force` bypasses. A **post-validation** failure leaves `source_state` **unset**
      ⇒ retry safe (`PARTIAL_INDEX_FAILURE`, exit 5). → **063-05**, **063-12**
- [ ] **[R-063-6]** REASON contract at `skills/decision-extraction/SKILL.md`, mapping the protocol's
      **existing sections** ("Ключевые решения" → decision · НФТ/KPI → requirement · "Реестр рисков" →
      risk); bound to a named eval set at `skills/decision-extraction/evals/`. **MUST warn REASON that
      BARE IDs IN PROSE ARE REFS on cybos.** → **063-16**
- [ ] **[R-063-7]** **Anti-fabrication is a MECHANISM**: `CANDIDATE_COUNT_MIN = 0` (empty set =
      SUCCESS, exit 0); mandatory verbatim `source_quote`; the `WIKI_EXTRACT_NO_QUOTE_CHECK` escape is
      **NOT honoured**. Negative eval fixture required. → **063-06**, **063-16**
- [ ] **[R-063-8]** **G3 — supersede reconciliation, DRIFT-RULE-DRIVEN, never hardcoded.** Value =
      the matching `drift_rule`'s `expect_status`; **precondition = the drift rule's OWN firing
      condition** (`json_type($.status)=='text' AND status != expect_status`, `_health_rules.py:312-317`).
      Seven-clause authority envelope; a **protected terminal status refuses the batch**;
      `--no-reconcile` refuses the whole batch. → **063-13**
- [ ] **[R-063-9]** **Class-A ownership is sacred** — write-hash stored **out-of-band** in
      `source_state`; never clobber a hand-edited page (whole-page rewrite) — **except** the R-063-8
      single-scalar patch, which is safe by construction; hand-authored (no recorded hash) targets are
      still patched inside the authority envelope; stale pages **reported, never auto-deleted**.
      → **063-14**
- [ ] **[R-063-10]** **H-6 + governance** — `_sanitize_*`, YAML-delimiter-injection guard,
      `_is_valid_slug` traversal gate; **no declassification pump** (inherit the SOURCE's
      `classification:`); `apply` **never authors an `aliases:` key**. → **063-11**
- [ ] **[R-063-11]** **No `import anthropic`**; one JSON envelope + stable exit codes; caps stated;
      **overflow REFUSES, never truncates**. → **063-04**, **063-06**
- [ ] **[R-063-12]** **Slugs derived with the LAYOUT'S OWN `slug_strategy`**; **in-batch slug collision
      is a CONTRACT VIOLATION ⇒ refuse the batch** (`len(set(slugs)) == len(candidates)`); the
      existing-page collision re-check uses the same derivation. → **063-07**
- [ ] **[R-063-P]** ★ **THE PROPERTY — a CONJUNCTION: `(delta-clean) AND (G6)`.** `delta-clean` tested
      as `lint_before == lint_after` (**never** `lint_after == []`), under **`wiki-reindex --full`**
      (never `--delta`). **G6 is the POSITIVE half**: everything written is indexed, edges present,
      inverses derived, counts reconcile. *Delta catches HARM; G6 catches SILENCE.* → **063-15**

---

## 2. Bead sequence

| # | Bead | Phase | RTM | Task file |
|---|---|---|---|---|
| 063-00 | `extract_decisions` schema block + typed dataclasses | 0 · config | R-063-3′ | [task-063-00](tasks/task-063-00-sync-schema-extract-decisions.md) |
| 063-01 | per-folder cascade resolver | 0 · config | R-063-3′ | [task-063-01](tasks/task-063-01-cascade-resolver.md) |
| 063-02 | glob-coverage helper + **placement derivation** | 1 · gate | R-063-3, R-063-3′ | [task-063-02](tasks/task-063-02-glob-coverage-and-placement.md) |
| 063-03 | `wiki-config validate` cross-system finding | 1 · gate | R-063-3′ | [task-063-03](tasks/task-063-03-wiki-config-cross-system-finding.md) |
| 063-04 | **[STUB CREATION]** package + CLI + exit codes | 2 · rail | R-063-11 | [task-063-04](tasks/task-063-04-package-stubs-and-cli.md) |
| 063-05 | **[LOGIC]** `prepare` — contract, preflight, handshake | 2 · rail | R-063-1, R-063-3, R-063-5 | [task-063-05](tasks/task-063-05-prepare-logic.md) |
| 063-06 | candidates schema + **anti-fabrication mechanism** | 3 · validate | R-063-7, R-063-11 | [task-063-06](tasks/task-063-06-candidates-schema-antifabrication.md) |
| 063-07 | slug derivation + collision refusal | 3 · validate | R-063-12 | [task-063-07](tasks/task-063-07-slugs-and-collisions.md) |
| 063-08 | **G1** ontology validation (domain + RANGE + status) | 3 · validate | R-063-1, R-063-2 | [task-063-08](tasks/task-063-08-g1-ontology-validation.md) |
| 063-09 | ★ **the normative ORDERING** (7th surface) | 3 · validate | R-063-2 | [task-063-09](tasks/task-063-09-normative-ordering.md) |
| 063-10 | **G2** ref-resolution via the layout's OWN rules | 3 · validate | R-063-2 | [task-063-10](tasks/task-063-10-g2-ref-resolution.md) |
| 063-11 | H-6 hardening + no declassification pump | 3 · validate | R-063-10 | [task-063-11](tasks/task-063-11-h6-hardening.md) |
| 063-12 | write typed pages + manifest + idempotency | 4 · write | R-063-3, R-063-4, R-063-5 | [task-063-12](tasks/task-063-12-write-and-manifest.md) |
| 063-13 | **G3** supersede reconciliation (drift-rule-driven) | 4 · write | R-063-8 | [task-063-13](tasks/task-063-13-supersede-reconciliation.md) |
| 063-14 | re-extraction reconciliation (Class-A sacred) | 4 · write | R-063-9 | [task-063-14](tasks/task-063-14-reextraction-reconciliation.md) |
| 063-15 | ★ **THE PROPERTY**: `(delta-clean) AND (G6)` | 5 · accept | R-063-P, R-063-4 | [task-063-15](tasks/task-063-15-the-property.md) |
| 063-16 | `decision-extraction` SKILL.md + eval set | 5 · accept | R-063-6, R-063-7 | [task-063-16](tasks/task-063-16-skill-and-evals.md) |
| 063-17 | config-driven **dispatch marker** (sync + import) | 5 · accept | R-063-3′ | [task-063-17](tasks/task-063-17-dispatch-marker.md) |
| 063-18 | docs, ADR/ARCHITECTURE, final gates | 5 · accept | all | [task-063-18](tasks/task-063-18-docs-and-final-gates.md) |

**Dependency order** is the numeric order. Two independently shippable sub-chains:
`063-00 → 063-01 → 063-02 → 063-03` (the config surface — ships value alone: the editor gains the
keys and `validate` gains the cross-system gate, with no rail yet) and `063-04 → … → 063-15`
(the rail). 063-02 is the **join point**: `prepare`'s preflight (063-05) reuses the same helper
`wiki-config validate` (063-03) does — *one gate, two callers, never two implementations.*

---

## 3. Phase map (Stub-First)

**Phase 0–1 · Config surface + cross-system gate** (063-00 … 063-03). No LLM, no rail. Delivers the
operator requirement on its own: the three `dirs.*` keys appear in the `wiki-config` web editor with
**zero interface-code changes** (the TASK-058 evolution invariant), and an uncovered folder name is
refused by `wiki-config validate`.

**Phase 2 · [STUB CREATION]** (063-04). Package, argparse, exit-code table, JSON envelopes — all
stubs returning hardcoded envelopes. E2E test passes **on the stubs** (asserts the stub envelope
shape + exit codes). `import anthropic` grep gate lands here, before any logic exists to violate it.

**Phase 2–4 · [LOGIC IMPLEMENTATION]** (063-05 … 063-14). Stub → real, one guarantee at a time.
Each of G1/G2/G3/G4/G5 gets its own bead, because **each is a different surface** (spec §2).

**Phase 5 · Acceptance** (063-15 … 063-18). The conjunction property, the REASON contract + evals,
the config-driven dispatch, docs.

---

## 4. Verification protocol (normative — it is part of the deliverable)

```bash
# per bead
pytest tests/ -q                         # ≥ 2477 passed, 0 failed
mypy --strict scripts/                   # clean, 88+ files

# the acceptance rail (063-15) — on a cybos sample vault under samples/
wiki-lint --vault <v> --strict --json  >  before.json      # MUST be clean: the property's premise
wiki-extract-decisions prepare  --vault <v> --source-page <s>  ...
wiki-extract-decisions apply    --vault <v> --source-page <s> --source-hash <h> --candidates-file c.json
wiki-reindex --vault <v> --full          # ⚠️ --full, NEVER --delta (lint.py:298)
wiki-lint --vault <v> --strict --json  >  after.json
# assert: issues(before) == issues(after)      ← delta-clean (HARM)   — NEVER `after == []`
# assert: G6 positive half (pages/edges/inverses/hashes/counts)  ← SILENCE
```

**Why `--full`, spelled out once so no bead re-derives it wrong:** drift reads the auto-derived
**inverse** edges, and `--delta` leaves them transiently stale on one side of a bidirectionally
authored edge (`scripts/wiki_index/lint.py:298`, verbatim: *"`--strict` drift gating assumes a
recent `--full`"*). A `--delta`-based acceptance test can therefore report **`lint_before ==
lint_after` while the vault is actually drifted** — a check that examined nothing, reporting green,
inside this task's own acceptance criteria.

---

## 5. Invariants the implementation must not break

| # | Invariant | Enforced by |
|---|---|---|
| I-1 | **Zero DDL** — `user_version` stays 7 | 063-18 grep gate (`git diff sql/` empty) |
| I-2 | **No `import anthropic`** anywhere in the package | 063-04 grep gate over **every** file in the package (enumerated, not sampled) |
| I-3 | **Decision-17** — `prepare`/`apply` are deterministic plumbing; the orchestrator owns REASON | 063-04, 063-16 |
| I-4 | **One JSON envelope + stable exit code** per invocation | 063-04 (table), every bead's tests |
| I-5 | **Class A canonical** — the DB never holds knowledge the markdown doesn't; the write hash is **out-of-band** in `source_state` (Class C) | 063-14 |
| I-6 | **DERIVE FROM CONFIG, NEVER RESTATE BY HAND** — supersede value *and* precondition from `drift_rules`; refs via the layout's `ref_extraction`; slugs via `slug_strategy`; globs via `PurePosixPath.full_match` (**not `fnmatch`**) | 063-02, 063-07, 063-08, 063-10, 063-13 |
| I-7 | **Contract violation ⇒ refuse the batch, exit 4, ZERO writes**; benign skip ⇒ drop + loud warning, exit 0. An **in-batch** slug collision is NOT benign | 063-06 … 063-13 |
| I-8 | **Validate the POST-DROP batch** — a validation computed against a hypothetical batch is not a validation of what got written | 063-09 |

---

## 6. Risk register

| Risk | Why it bites | Mitigation (bead) |
|---|---|---|
| The delta property is **satisfiable by SILENCE** — `find_pages_missing_in_index` walks via `discover_pages`, so a glob-invisible file is never *discovered*, never *reported*, and `lint_before == lint_after` passes. **So does a rail that writes nothing.** | It is the acceptance criterion itself | The property is a **CONJUNCTION** with G6's positive half (**063-15**) + the preventive load gate (**063-02**) |
| A `--delta` acceptance test reports a **FALSE GREEN** | `lint.py:298` | `--full` mandated in §4 and re-asserted per bead (**063-15**) |
| Hardcoding `status: superseded` **violates G1** (the `requirement` enum has no `superseded`) | v2 authored the exact contradiction G1 prevents | Value **and** precondition read from `drift_rules` (**063-13**) |
| Hardcoding the precondition `{proposed, accepted}` **never patches a `workflow`** | v3's bug, one field to the left | Precondition = `status != rule.expect_status` (**063-13**) |
| `fnmatch` gives the **wrong answer** on `**` | An earlier draft measured with it and reported a false result | `PurePosixPath.full_match` + a discriminating test (**063-02**) |
| Cloning `_CANDIDATE_COUNT_MIN = 1` makes *"no decisions"* an **exit-4 failure** ⇒ the model's cheapest green is to **invent one** | The precedent literally has MIN=1 | `CANDIDATE_COUNT_MIN = 0` + negative eval fixture (**063-06**, **063-16**) |
| Two Russian titles → one `transliterate` slug ⇒ **one decision silently lost**, zero lint issues | Invisible to *both* halves of the property | In-batch uniqueness = contract violation (**063-07**) |
| `typed_dirs` in `layout.yaml` would **never appear in the editor** (`_uimodel.py:24` reads only the sync schema) | The v5 architectural defect | The block lives in `sync.yaml` + a cross-system gate (**063-00**, **063-03**) |

---

## 7. Blocking questions

**None.** All of Q-063-1 … Q-063-5 are settled in the spec.

**One non-blocking spec inconsistency, flagged for the record:** §7 *"Out of scope"* still lists
*"Auto-chaining from `wiki-import` (Q-063-2)"*, but §5 Q-063-2 was **REVERSED by operator requirement
in v6** (config-driven invocation via a dispatch marker). The v6/v7 operator requirement governs;
**063-17 implements the dispatch marker**, and **063-18** corrects the stale §7 line when TASK.md is
finalised on ship. Recorded here rather than silently resolved, because a plan that quietly picks one
of two contradictory spec clauses is how a requirement gets lost.
