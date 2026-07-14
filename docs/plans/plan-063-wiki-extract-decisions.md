# PLAN 063 — `wiki-extract-decisions` (RFC-004): the typed-knowledge extraction rail

**Spec**: `docs/TASK.md` (v7, APPROVED after four blocking task-reviews + two operator requirements).
**Strategy**: Stub-First. Clone the proven Decision-17 `prepare` → orchestrator REASON → `apply`
rail from `wiki_extract_concepts`. 19 atomic beads, each independently shippable and **green at
every boundary**.

**Baseline (must never regress)**: `2477 passed, 5 skipped` · `mypy --strict scripts/` clean, 88 files.

**Revision**: **v2**, after a blocking plan-review (5 criticals, 4 majors — every one verified against
the code, every one applied). See **§8** for the change log. The review found the project's signature
lens **five more times, twice inside the beads written to prevent it** — §8 names each one, because a
fix whose *reason* is not recorded is a fix that gets reverted.

---

## 0. The three rules that govern EVERY bead

These are not preamble. They are exit criteria, repeated per bead.

1. **GREEN AT EVERY BOUNDARY.** After each bead: `pytest tests/` ≥ 2477 passed, 0 failed;
   `mypy --strict scripts/` clean. A bead that leaves the tree red is not done.
2. **EVERY DENOMINATOR CLAIM CARRIES A GREP — AND THE GREP MUST BE *RUN*, NOT IMAGINED.** This
   project's signature failure mode — *asserting that a mechanism covers a surface without
   enumerating the surfaces it actually covers* — has now recurred **~30 times**: four inside the
   spec, **five inside PLAN v1**. Every instance was caught by a grep or a mutation test, **never by
   reasoning**. PLAN v1 shipped a `no fnmatch` gate that **could never go green** (3 real hits) and a
   supported-layouts gate that **measured 1 of 2 conjuncts** — two ungrepped denominators *inside the
   anti-lens machinery itself*. So: any bead claiming *"covers all N"*, *"one X per Y"*, or naming a
   population **MUST** carry a grep that enumerates N **from the code**, and its author **MUST run
   that grep before writing the exit criterion**.
   Beads with such a claim: **00, 02, 04, 05, 08, 10, 12, 13, 14, 15, 17, 18**.
3. **EVERY GATE IS MUTATION-TESTED — AND THE MUTATION MUST BE *EXECUTED*.** Each bead states the
   mutation and the test that must go RED under it. **A gate that cannot fail is the disease** — and
   PLAN v1's G6 was exactly that (§8 C-1). Recorded per bead as `MUT:`.

---

## 1. ★ THE FIXTURE ROSTER — the single source of truth for "which layouts are supported"

PLAN v1 got this **factually wrong twice** (§8 C-2 / C-2b), for the same reason the spec got it wrong
in *its* v1: **G4 support is a CONJUNCTION**, and each draft measured one conjunct.

> **A layout supports this rail ⟺ its `type_mapping` maps the roster classes **AND** its read globs
> can SEE the write path.** Neither half alone is support. `dev-project` satisfies the first and fails
> the second (`layouts/dev-project.yaml:33-57` — no `decisions/**`, no catch-all). Stock
> `obsidian-personal` fails the first (zero typed classes).

Every bead uses these **named** fixtures. **No bead may invent its own layout fixture.**

| fixture | definition | typed classes? | globs cover? | verdict |
|---|---|---|---|---|
| **`cybos`** | stock `layouts/cybos.yaml` | ✅ 20+ | ✅ root-anchored `decisions/**/*.md` | **SUPPORTED** — root placement, **strict names** (a custom name is refused) |
| **`dev-project`** | stock **+ the three `paths[]` globs added in 063-02** | ✅ (`:75-77`) | ✅ **only after 063-02** | **SUPPORTED** — root placement; **NO `ontology:`, NO `drift_rules`** ⇒ *this* is the `vacuous_validation` fixture |
| **`para-typed`** | `obsidian-personal` **+ a `.wiki/layout.yaml`** unioning in the typed classes | ✅ via override | ✅ generic `[0-9][0-9] - */*/**/*.md` | **SUPPORTED** — **sibling** placement, **free names** (Cyrillic OK). *This is the operator's LIVE vault — what the spec means by "obsidian-personal + the operator's `paths`".* |
| **`karpathy`** | stock | ❌ zero | — | **REFUSED** by `prepare` (byte-identity-anchored — **never edit it**) |
| **`obsidian-personal` (stock)** | stock, no override | ❌ zero | — | **REFUSED** by `prepare` |

**The gate that keeps this table true** (063-02 — and it is the one PLAN v1 fumbled):

```python
for name in layout_choices():                        # the population, from the registry
    cfg  = _config_for(name)                         # real API — see 063-02 m-10
    maps = bool({"decision","requirement","risk"} & set(cfg.type_mapping))
    sees = all(resolve_typed_write_dir(cfg, dir_name=d, source_rel=PROBE_SRC) is not None
               for d in ("decisions", "requirements", "risks"))
    assert (maps and sees) == (name in SUPPORTED)     # ★ the CONJUNCTION, not either half
```

---

## 2. RTM — one requirement, one checklist item

- [ ] **[R-063-1]** `prepare` emits the ontology contract (roster, edge domain/range, status enums),
      known typed pages, `existing_page_slugs`, the `--source-hash` handshake, house-standard
      denominators (`validation: {roster_size, edges_checked, properties_checked, links_checked}`) and
      a **`vacuous_validation: true`** marker when the layout declares no `ontology:` (**`dev-project`**).
      *A validator that examined nothing must not look green.* → **063-05**, **063-08**
- [ ] **[R-063-2]** **G1** — `apply` validates every candidate against the ontology BEFORE any write:
      class ∈ roster, edge **domain**, edge **RANGE** (out-of-batch target class resolved **from the
      DB**), `status` ∈ enum. **All** violations listed at once; failure ⇒ **ZERO** files written.
      → **063-08**, **063-09** (the normative ordering), **063-10** (G2, its ref-costume)
- [ ] **[R-063-3]** **G4** — typed pages go where the layout's read globs can see them; placement is
      **DERIVED from the layout**; the write path is visible to **the walker's FULL filter chain**
      (⚠️ **not** "matches a `paths[]` glob" — that is **1 of 5 conjuncts**; §8 C-3). Supported set =
      the §1 roster. → **063-02**, **063-05**, **063-12**
- [ ] **[R-063-3′]** **THE CONFIG SPLIT** — a cascading `extract_decisions: {enabled, dirs}` block in
      **`.wiki/sync.yaml`**, schema-driven ⇒ **RENDERED** by `wiki-config show`/`report`/`serve` with
      **zero interface-code changes** (asserted on the **rendered output**, not on the UI model — §8
      M-6); the **CROSS-SYSTEM load gate** in **BOTH** `wiki-config validate` **and** `prepare`; an
      uncovered name is **REFUSED** (Q-063-5 = A). → **063-00**, **063-01**, **063-02**, **063-03**,
      **063-17**
- [ ] **[R-063-4]** Forward edges only; **inverses auto-derive at `wiki-reindex --full`** (M-1 intact).
      ⚠️ **NOT `--delta`** (`lint.py:298`). → **063-12**, **063-15**
- [ ] **[R-063-5]** **Idempotent**: unchanged source ⇒ `action: unchanged`, zero writes; `--force`
      bypasses. A post-validation failure leaves `source_state` **unset** ⇒ retry safe (exit 5).
      → **063-05**, **063-12**
- [ ] **[R-063-6]** REASON contract at `skills/decision-extraction/SKILL.md`, mapping the protocol's
      **existing sections**; bound to a named eval set. **MUST warn REASON that BARE IDs IN PROSE ARE
      REFS on cybos.** → **063-16**
- [ ] **[R-063-7]** **Anti-fabrication is a MECHANISM**: `CANDIDATE_COUNT_MIN = 0` (empty set =
      SUCCESS, exit 0); mandatory verbatim `source_quote`; the `WIKI_EXTRACT_NO_QUOTE_CHECK` escape is
      **NOT honoured**. Negative eval fixture required. → **063-06**, **063-16**
- [ ] **[R-063-8]** **G3 — supersede reconciliation, DRIFT-RULE-DRIVEN, never hardcoded.** Value = the
      matching `drift_rule`'s `expect_status`; **precondition = the drift rule's OWN firing condition**
      (`_health_rules.py:312-317`); **a `forbid_status`-shaped rule has NO `expect_status` ⇒ patch
      NOTHING** (§8 M-9). A protected terminal status **refuses the batch**; `--no-reconcile` refuses
      the whole batch. → **063-13**
- [ ] **[R-063-9]** **Class-A ownership is sacred** — the write hash is **out-of-band** in
      `source_state`; never clobber a hand-edited page (whole-page rewrite) — **except** the
      single-scalar patch; hand-authored targets are still patched inside the envelope; stale pages are
      **reported, never auto-deleted**. → **063-14**
- [ ] **[R-063-10]** **H-6 + governance** — sanitizers, YAML-delimiter guard, traversal gate; **no
      declassification pump**; `apply` **never authors an `aliases:` key**. → **063-11**
- [ ] **[R-063-11]** **No `import anthropic` AND no `from anthropic`** (⚠️ the house gate asserts
      **both** — `tests/test_wiki_sync.py:634-639`; §8 M-8); one JSON envelope + stable exit codes;
      **overflow REFUSES, never truncates**. → **063-04**, **063-06**
- [ ] **[R-063-12]** **Slugs derived with the LAYOUT'S OWN `slug_strategy`**; an **in-batch** slug
      collision is a **CONTRACT VIOLATION ⇒ refuse the batch**. → **063-07**
- [ ] **[R-063-P]** ★ **THE PROPERTY — a CONJUNCTION: `(delta-clean) AND (G6)`.** `delta-clean` tested
      as `lint_before == lint_after` (**never** `lint_after == []`), under **`--full`**. **G6 is the
      POSITIVE half, and it is anchored on the SUBMITTED CANDIDATE BATCH — never on the rail's own
      output** (⚠️ PLAN v1's G6 compared two rail-reported numbers and therefore **passed under a
      no-op `apply`**; §8 C-1). *Delta catches HARM; G6 catches SILENCE.* → **063-15**

---

## 3. Bead sequence

| # | Bead | Phase | RTM | Task file |
|---|---|---|---|---|
| 063-00 | `extract_decisions` schema block + typed dataclasses | 0 · config | R-063-3′ | [task-063-00](tasks/task-063-00-sync-schema-extract-decisions.md) |
| 063-01 | per-folder cascade resolver | 0 · config | R-063-3′ | [task-063-01](tasks/task-063-01-cascade-resolver.md) |
| 063-02 | **walker-chain** coverage helper · placement derivation · **dev-project globs** | 1 · gate | R-063-3, R-063-3′ | [task-063-02](tasks/task-063-02-glob-coverage-and-placement.md) |
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

**Dependency order is the numeric order.** Two independently shippable sub-chains:
`063-00 → 063-01 → 063-02 → 063-03` (the config surface — ships value alone) and
`063-04 → … → 063-15` (the rail). **063-02 is the join point**: `prepare`'s preflight (063-05) reuses
the same helper `wiki-config validate` (063-03) calls — *one gate, two callers, never two
implementations.* 063-02 also owns the `dev-project.yaml` glob addition, because *"make the write
placement and the read grammar agree"* is **one** goal, not two (§8 C-2).

---

## 4. Phase map (Stub-First)

**Phase 0–1 · Config surface + cross-system gate** (063-00 … 063-03). No LLM, no rail. Delivers the
operator requirement on its own: the three `dirs.*` keys **render** in `wiki-config
show`/`report`/`serve` with zero interface-code changes, and an uncovered folder name is refused.

**Phase 2 · [STUB CREATION]** (063-04). Package, argparse, exit-code table, JSON envelopes — stubs
returning hardcoded envelopes. The E2E test passes **on the stubs**. The `anthropic` gate lands here,
before any logic exists to violate it.

**Phase 2–4 · [LOGIC IMPLEMENTATION]** (063-05 … 063-14). Stub → real, one guarantee at a time. Each
of G1/G2/G3/G4/G5 gets its own bead, because **each is a different surface** (spec §2).

**Phase 5 · Acceptance** (063-15 … 063-18).

---

## 5. Verification protocol (normative)

```bash
# per bead
pytest tests/ -q                         # ≥ 2477 passed, 0 failed
mypy --strict scripts/                   # clean, 88+ files

# the acceptance rail (063-15) — on a cybos vault built in tmp_path (NOT samples/ — §8 C-5)
wiki-lint --vault <v> --strict --json  >  before.json      # MUST be clean: the property's premise
wiki-extract-decisions prepare  --vault <v> --source-page <s>  ...
wiki-extract-decisions apply    --vault <v> --source-page <s> --source-hash <h> --candidates-file c.json
wiki-reindex --vault <v> --full          # ⚠️ --full, NEVER --delta (lint.py:298)
wiki-lint --vault <v> --strict --json  >  after.json
# assert: issues(before) == issues(after)          ← delta-clean (HARM)  — NEVER `after == []`
# assert: G6 vs the SUBMITTED CANDIDATE BATCH      ← SILENCE (external ground truth — §8 C-1)
```

**Why `--full`, spelled out once so no bead re-derives it wrong:** drift reads the auto-derived
**inverse** edges, and `--delta` leaves them transiently stale on one side of a bidirectionally
authored edge (`scripts/wiki_index/lint.py:298`, verbatim: *"`--strict` drift gating assumes a recent
`--full`"*). A `--delta` acceptance test can report `lint_before == lint_after` **while the vault is
actually drifted**.

---

## 6. Invariants the implementation must not break

| # | Invariant | Enforced by |
|---|---|---|
| I-1 | **Zero DDL** — `user_version` stays 7 | 063-18 (`git diff sql/` empty) |
| I-2 | **No `import anthropic` AND no `from anthropic`** — over the whole package, globbed at runtime | 063-04, 063-17 |
| I-3 | **Decision-17** — `prepare`/`apply` are deterministic plumbing; the orchestrator owns REASON | 063-04, 063-16, 063-17 |
| I-4 | **One JSON envelope + stable exit code** per invocation | 063-04 + every bead |
| I-5 | **Class A canonical**; the write hash is **out-of-band** in `source_state` (Class C) | 063-14 |
| I-6 | **DERIVE FROM CONFIG, NEVER RESTATE** — supersede value *and* precondition from `drift_rules`; refs via `ref_extraction`; slugs via `slug_strategy`; visibility via **the walker's own filter chain** | 063-02, 063-07, 063-08, 063-10, 063-13 |
| I-7 | **Contract violation ⇒ refuse the batch, exit 4, ZERO writes**; benign skip ⇒ drop + loud warning, exit 0 | 063-06 … 063-13 |
| I-8 | **Validate the POST-DROP batch** — a validation computed against a hypothetical batch is not a validation of what got written | 063-09 |
| I-9 | ★ **No acceptance criterion may be satisfiable by doing nothing.** Every gate is anchored on an **external** ground truth (the submitted batch; a real `iter_pages` walk) — **never on the rail's own report** | 063-02, 063-15 |

---

## 7. Risk register

| Risk | Why it bites | Mitigation (bead) |
|---|---|---|
| **G6 is itself satisfiable by silence** — `pages_written == pages_indexed` compares two of the rail's **own** outputs; under a no-op `apply` it is `0 == 0` ⇒ **PASSES** | It is the half that exists to catch silence | Anchor G6 on the **submitted candidate batch** (**063-15**) |
| The delta property is **satisfiable by SILENCE** — a glob-invisible file is never *discovered*, so never *reported* | It is the acceptance criterion itself | The **conjunction** with G6 (**063-15**) + the preventive load gate (**063-02**) |
| **The G4 gate has the G4 hole** — `paths[]` is **1 of 5** walker conjuncts; `dirs.decision: "_raw"` matches a PARA glob, yet `**/_raw/**` makes the walker skip it | The gate written to prevent glob-invisible pages *permits one* | `glob_covers` = the **full filter chain**, **MEASURED** against a real `iter_pages` walk (**063-02**) |
| "**dev-project is supported**" — true of `type_mapping`, **false** of the globs | Three planned tests could never pass; the anti-lens gate measured one conjunct | The §1 **fixture roster** + the **conjunction** gate (**063-02**, **063-05**) |
| A `--delta` acceptance test reports a **FALSE GREEN** | `lint.py:298` | `--full` mandated (**063-15**) |
| Hardcoded `status: superseded` **violates G1**; a hardcoded precondition **never patches a workflow**; a `forbid_status` rule has **no** `expect_status` | v2's bug, v3's bug, and the shape neither caught | All three read from `drift_rules` (**063-13**) |
| Cloning `_CANDIDATE_COUNT_MIN = 1` ⇒ *"no decisions"* is an **exit-4 failure** ⇒ the model's cheapest green is to **invent one** | The precedent literally has MIN=1 | MIN=0 + the negative eval fixture (**063-06**, **063-16**) |
| Two Russian titles → one `transliterate` slug ⇒ a decision **silently lost**, zero lint issues | Invisible to *both* halves of the property | In-batch uniqueness = contract violation (**063-07**) |
| An acceptance test anchored on **gitignored `samples/`** silently **skips** on a clean checkout | A skipped gate joins the baseline's "5 skipped" | Build the vault in **`tmp_path`** (**063-15**) |

---

## 8. ★ Change log — PLAN v1 → v2 (the plan-review, applied)

The reviewer **passed** Stub-First, atomicity, the DAG, 063-02 as the single join point, the two-chain
split, and 063-09's argument-level assertion — and verified every load-bearing citation. It then found
the lens **five more times**. Each fix is recorded **with its reason**, because a fix whose reason is
not recorded is a fix that gets reverted.

| # | Finding | Fix | Beads |
|---|---|---|---|
| **C-1** | 🔴 **G6 — the half that "catches SILENCE" — is itself satisfiable by silence.** `pages_written == pages_indexed` compares **two numbers the rail reports**. Under the meta-test's no-op `apply`: `written = []` ⇒ G6a/b/c vacuously true, G6d is `0 == 0` ⇒ **G6 PASSES** — so `test_delta_property_alone_is_satisfiable_by_silence` could not demonstrate what it claimed, and its `MUT:` line was **decorative**. *A self-consistency check between two of the rail's own outputs is not an external measurement.* | G6 is anchored on the **submitted candidate batch** — the only external ground truth in the test: every candidate's derived slug has a `pages` row with the expected `$.type`; `pages_indexed == len(candidates)`; `edges_indexed == Σ len(c.edges)` + inverses derived. *(The glob-invisible test passes under either anchor — 3 written vs 2 indexed — which is exactly why only the **batch** anchor satisfies **both** tests.)* | **15** |
| **C-2** | 🔴 **"dev-project is supported" is one conjunct short.** No `decisions/**` / `requirements/**` / `risks/**` glob and no catch-all (`layouts/dev-project.yaml:33-57`) ⇒ `resolve_typed_write_dir` returns `None` ⇒ **`prepare` REFUSES dev-project via its own preflight** ⇒ three planned tests could never pass. And 063-05's anti-lens gate measured `type_mapping` **only** — **the gate written to stop the lens was an instance of it.** | The spec's §"File surface" **already names `layouts/dev-project.yaml` as a file to edit** — so **063-02 adds the three `paths[]` globs** (additive, zero-DDL; no such dirs exist ⇒ no walk change). The supported-set gate now asserts the **CONJUNCTION** `type_mapping ∧ resolve_typed_write_dir(...) is not None`. | **02**, **05**, **08**, **15** |
| **C-2b** | 🔴 **Same defect for `obsidian-personal` — and 063-03 contradicted itself**: stock maps **zero** typed classes ⇒ must be refused, yet three beads used it as the *supported* Cyrillic/sibling fixture while 063-03 step 4 said zero-class layouts are refused. Two mutually exclusive tests in one bead. | The **§1 FIXTURE ROSTER** — one table, named fixtures, no bead may invent its own. The Cyrillic/sibling fixture is now explicitly **`para-typed`** = obsidian-personal **+ a `.wiki/layout.yaml`** unioning in the typed classes — which is what the spec meant by *"obsidian-personal + the operator's `paths`"*. | **§1**, **02**, **03**, **12** |
| **C-3** | 🔴 **The G4 gate has the G4 hole.** `iter_pages` visibility (`layout_config.py:1197-1213`) is a **5-way conjunction**: `suffix ∈ file_extensions` ∧ `name ∉ SYSTEM_FILES` ∧ `rel ∉ auto_indexes[].output` ∧ **`¬_matches_ignore(rel, config.ignore)`** ∧ `∃ paths[] match`. v1's helper enumerated **one**, and its docstring said *"i.e. the READ walker can SEE a file written there"* — **that "i.e." is the lens.** Live failure: `dirs.decision: "_raw"` on the operator's PARA vault **matches** the generic glob ⇒ gate says COVERED ⇒ `**/_raw/**` makes the walker **skip it** ⇒ glob-invisible page, zero lint issues — *the precise loss G4 exists to prevent, through the conjunct the gate didn't enumerate.* | `glob_covers` implements the **full filter chain**, and the test **MEASURES** it rather than asserting it: write the probe into a tmp vault, run **`iter_pages`**, assert `glob_covers(...) ⟺ the file appears in the walk`. That mechanically covers all five conjuncts **forever** — including ones added later. | **02** |
| **C-4** | 🔴 **The `no fnmatch` exit criterion is FACTUALLY FALSE and can never go green.** The engine **imports** fnmatch (`:30`) and calls `fnmatch.fnmatchcase` at **`:1055`** and **`:1085`** — the per-**segment** matcher of the TASK-030 single-pass walk, where it is **correct** (it never crosses `/`). "Exactly one matcher" was itself an **ungrepped denominator** — and a developer "satisfying" the gate by deleting those calls **breaks the walk**. | The gate is **scoped to the new helper** (`glob_covers` must use `full_match`, never `fnmatch`), and the 3 pre-existing hits are **pinned by line + count** so the gate cannot be satisfied by deleting them. | **02**, **18** |
| **C-5** | 🔴 **The flagship property test was anchored on gitignored `samples/`** (`.gitignore:39`; the house `skipif` precedent is `tests/test_wiki_config_validate.py:460`) ⇒ on a clean checkout it **skips or fails**, and a skipped acceptance gate joins the baseline's "5 skipped" **silently**. *A check that examined nothing, reporting green — in this task's acceptance criteria, for the third revision running.* | The cybos vault is built in **`tmp_path`**. `samples/` is reserved for 063-18's **manual dogfood**. | **15**, **18** |
| **M-6** | 🟡 **063-00 asserted the UI MODEL, not the RENDERED surface** — the exact TASK-061 bug shape (`FieldSpec.description` lived in the model and rendered only in `serve`). The existing generic guards do **not** cover it: `test_evolution_new_schema_field_needs_no_code` asserts on the model; `test_description_reaches_every_surface…` injects into an **existing** parsed block — `extract_decisions` is a **NEW top-level PARSED cascading block** (`_PARSED_BLOCKS` + frozen dataclass + `_overlay_parsed`), a shape **neither** exercises. | Assert `/extract_decisions/dirs/decision` in **(a)** `show`'s JSON envelope, **(b)** `render_html(build_report_model(...))`, **(c)** `/api/schema`. | **00** |
| **M-7** | 🟡 **063-00 missed a test its own change turns RED.** **Two** tests pin the cascading denominator: `:612` (which v1 named) **and `:426`** `test_ui_model_matches_shipped_schema` (which it did not). "Green at every boundary" failed **literally as written**. | Both pins updated, and the bead now *enumerates the pins by grep* rather than naming one from memory. | **00** |
| **M-8** | 🟡 **The `anthropic` gate is narrower than the house precedent it clones.** `tests/test_wiki_sync.py:634-639` asserts **both** `"import anthropic"` **and** `"from anthropic"`; v1 greps only the first — `from anthropic import Anthropic` **slips through**. | Both patterns, over the runtime-globbed package. | **04**, **17**, **18** |
| **M-9** | 🟡 **G3's drift-rule read has an unguarded shape.** `DriftRule` carries **exactly one** of `expect_status` / `forbid_status` (`models.py:384-391`); an operator's `.wiki/layout.yaml` may declare the `forbid_status` shape for `(class, superseded-by)` ⇒ `rule.expect_status is None` ⇒ **the patch value is undefined**. | Stated as a rule: **no `expect_status` ⇒ patch NOTHING** (the same branch as "no rule at all"). Tested. | **13** |
| **m-10** | 🟢 `resolve_layout_config_by_name` **does not exist**. | Real APIs: `resolve_layout_config(vault_root)`, `load_layout_config(vault_root, root_config)`, `_builtin_registry()`, `layout_choices()`. | **02**, **05** |
| **m-11** | 🟢 063-09's `referenced_dropped` peeked at candidate fields ad hoc. | Defined over **the same extracted-ref set G2 uses** (`extract_refs` over the rendered page). | **09** |
| **m-12** | 🟢 The config chain ships **ahead** of the rail ⇒ `enabled: true` could silently over-promise. | The `enabled:` schema description states the rail is required (TASK 063) and that the marker is inert without it. | **00** |

---

## 9. Blocking questions

**None.** Q-063-1 … Q-063-5 are settled in the spec.

**One non-blocking spec inconsistency, flagged for the record:** §7 *"Out of scope"* still lists
*"Auto-chaining from `wiki-import` (Q-063-2)"*, but §5 Q-063-2 was **REVERSED by operator requirement
in v6** (config-driven invocation via a dispatch marker). The v6/v7 requirement governs; **063-17**
implements the marker and **063-18** corrects the stale §7 line on ship. Recorded rather than silently
resolved, because a plan that quietly picks one of two contradictory spec clauses is how a requirement
gets lost.
