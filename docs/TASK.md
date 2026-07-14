# TASK 066 — DF-064-4: the weak-model recall gap, and the harness that can prove it closed

## 0. Meta Information

| | |
|---|---|
| **Tracks** | [[df-064-4-weak-model-extraction-recall-gap\|DF-064-4]] (SEV-3, open) — the **HEAD** of ROADMAP **R-23** |
| **Folds in** | **R-23 Phase B** (re-scoped 2026-07-14: the corpus sweep was measured EMPTY; the detectors move to the WRITE path) |
| **Status** | v1 — Analysis |
| **Baseline** | `2848 passed, 14 skipped` · `mypy --strict scripts/` clean |

---

## 1. The problem, stated honestly

`skills/concept-extraction/SKILL.md` scores **9 / 11** on **Haiku 4.5**. Both misses are
**under-extraction** — *recall, not junk*:

| fixture | miss |
|---|---|
| **03** ui-chrome-and-primitives | found **1 of 2** durable concepts (dropped «Параметризованный запрос»); emitted **no** junk |
| **09** two-candidates-one-file | extracted only **«Падёж»**, under its **bare** name — the second concept («Грамматический падеж») dropped entirely, and the bare name is itself on the fixture's `forbidden` list |

**Nothing counts what was left behind.** No validator, no lint rule, no health check can see a
concept the extraction *dropped* — it is one of the three rules the SKILL's own honesty ledger names
as having **no mechanism at all**. The eval set is the only instrument that can observe it.

---

## 2. ★★ THE BLOCKER NOBODY FILED — the harness does not exist

DF-064-4's own fix sketch reads: *"any change must be re-run through the Haiku harness before it is
believed."*

**THAT HARNESS DOES NOT EXIST AS CODE.**

Verified, not assumed: `grep -rl "haiku|anthropic|messages.create"` over `tests/`, `scripts/`,
`skills/`, `bin/` returns **only the Decision-17 gates** — the tests that assert an LLM client is
*absent*. `tests/test_concept_extraction_evals.py` grades the **static `expected.json`**, never a
model run. The `evals/README.md` "Re-running it" section is **four sentences of prose**, not a script.

**The 9/11 was produced by hand** — one agent spawned per fixture, graded by hand-invoked validators.
That number is therefore:

- **not reproducible** by anyone but the person who ran it,
- **not defensible** against regression — the "floor is 9" cannot fail a build,
- **not vendor-agnostic** (the operator's standing requirement), and
- **not a gate** — every future SKILL edit is, today, believed rather than measured.

> **The first deliverable is the instrument.** Every other requirement in this task is unverifiable
> without it, and the issue's own fix sketch presumes it.

---

## 3. ★ THE PERVERSE INCENTIVE — a defect in the CODE, not the prompt (new; not in the issue)

Fixture 09 expects two disambiguated concepts («Падёж скота», «Грамматический падеж»); the **bare**
`падёж` / `падеж` are on its `forbidden` list, because under `transliterate` they **collapse to one
slug** and the second page silently overwrites the first.

The rail **has** a mechanism for this: `IN_BATCH_SLUG_COLLISION` — exit 4, zero writes.

**But it only fires if the model extracts BOTH.**

A model that **drops one** creates no collision, passes every gate, and is written. So:

> **The collision gate REWARDS under-extraction.** The safest way for a weak model to survive it is
> to extract fewer concepts — which is exactly the failure this task exists to fix.

That is a property of the code. Teaching the SKILL to disambiguate is necessary but not sufficient:
a model that cannot see the ambiguity will keep taking the exit the mechanism holds open for it.

---

## 4. ★ THE COUPLING RISK — a precision guard can DESTROY recall

R-23 Phase B folds in here: the **tautology / stub guard** moves to the write path, because the live
corpus was measured **clean** (685/685 definitions, **0 empty, 0 tautological**) and a health check
over it would fire on nothing.

But this SKILL's entire history is **precision and recall trading against each other**:

| SKILL state | Haiku | failure |
|---|---|---|
| *"extract only what the source EXPLAINS"* | 7/11 | returned `[]` on an incident report — the notes the rail exists for |
| that rule removed | 6/11 | **over**-extracted (6 concepts where 2 belong) |
| + theme-vs-prop table + count smell test | **9/11** | under-extracts on 03 / 09 |

**Three edits, three trades.** A new *refusal* on the write path is a fourth: a weak model that fears
rejection extracts less. **The guard's effect on RECALL must be MEASURED on the same harness, not
reasoned about.** A guard that buys precision at the cost of the 9-floor is a regression, whatever
its own test says.

---

## 5. Requirements Traceability Matrix

| ID | Requirement |
|---|---|
| **R-066-1** | ★ **THE HARNESS.** A runnable weak-model eval harness: one **fresh context per fixture**, given only `SKILL.md` + the **real** `prepare` envelope + the source body in the H-6 sentinel. Output graded through the **REAL** validators **and** the fixture's `expect` census **and** its `forbidden` list — **never by eye**. **Vendor-agnostic**: the model provider is pluggable, not hardcoded. |
| **R-066-2** | ★ **THE HARNESS MUST BE PROVEN ABLE TO FAIL.** Run it against a deliberately degraded SKILL ⇒ the score **MUST drop**. A harness that cannot go red is not an instrument — it is a green light with a number printed on it. |
| **R-066-3** | The harness **reproduces the 9/11 baseline** on the *unchanged* SKILL, **before** any edit. A harness that reports a different number is not measuring the thing the floor was set on, and no subsequent delta means anything. |
| **R-066-4** | Close **fixture 03**: 2 of 2 durable concepts, and **zero** `forbidden` names. |
| **R-066-5** | Close **fixture 09**: 2 of 2, **disambiguated** («Падёж скота» / «Грамматический падеж»), and **no bare** `падёж`. |
| **R-066-6** | ★ **The collision gate must stop REWARDING under-extraction** (§3). Whatever the fix, a model that drops one of two colliding concepts must not sail through more easily than one that extracts both. |
| **R-066-7** | **R-23 Phase B**: the **tautology / stub guard on the WRITE path**, calibrated on the **measured population** (IDF over the live 685: garbage **4.6–22.0**, corpus **min 29.3**) — **never on the example that motivated it** (the 0.88 lesson). Its **boundary is STATED**: an IDF measure calibrated on its own corpus cannot see garbage typical of that corpus. |
| **R-066-8** | ★ **R-066-7 MUST NOT REGRESS RECALL** — measured on the harness (§4), not argued. |
| **R-066-9** | Any miss that remains ships as an **`xfail(strict=True)` tripwire** carrying `tracks: df-064-4` — so an unexpected **xPASS** signals the gap closed and the floor is re-baselined, instead of the miss quietly becoming the norm. |
| **R-066-P** | ★ **THE PROPERTY — a CONJUNCTION.** `(score ≥ 9)` **AND** `(zero forbidden names emitted)`. *The floor catches REGRESSION; the forbidden list catches the TRADE.* A fix that buys recall by emitting junk passes the first half perfectly — and this SKILL's history is three such trades. |

---

## 6. Acceptance criteria

- [ ] `pytest tests/` ≥ 2848 passed, 0 failed. `mypy --strict scripts/` clean.
- [ ] **The harness runs from a clean checkout** and prints a per-fixture verdict + a total.
- [ ] **R-066-2 EXECUTED**: the degraded-SKILL run is **RED**. Recorded with its score.
- [ ] **R-066-3 EXECUTED**: the unchanged SKILL scores **9/11**, and the two failures are **03** and
      **09** — the *same* two. A different 9 is a different skill.
- [ ] Final score **≥ 9**, `forbidden` emissions **= 0**, and every remaining miss carries an
      `xfail(strict=True)` tripwire.
- [ ] **Decision-17 survives**: the harness is a **dev instrument**, not part of the rail. The
      `no import anthropic` gate over `scripts/wiki_skills/` stays green — asserted, not assumed.
- [ ] **Zero DDL** — `user_version` stays 7.

---

## 7. Out of scope

- `wiki-health definitions` **as a corpus sweep** — measured EMPTY (R-23 Phase B, re-scoped). If a
  future sweep finds a non-empty population it is reconsidered; the sweep is now a one-liner because
  Phase A shipped.
- **DF-064-2** (the O(n²) near-duplicate scan) — independent; `wiki-lint --strict` measures **1.8 s**
  on the live vault today (re-measured 2026-07-14, with a vacuity probe taken *from* the timed op).
- Re-litigating the **0.88 near-duplicate cutoff** — it was correctly demoted to a warning; no scalar
  cutoff exists.

---

## 8. Open questions

- **Q-066-1** — **Where does the harness live, given Decision-17?** The rail carries no LLM client by
  contract. An eval harness *is* an LLM caller. Candidate: `skills/concept-extraction/harness/` with a
  pluggable provider, **outside** `scripts/wiki_skills/` so the house gate is untouched — and the gate
  must be re-asserted, not assumed unaffected. **Blocking** — it is a boundary question, and this
  project's failures come from unstated boundaries.
- **Q-066-2** — **How is the fix for §3 shaped?** The collision gate cannot refuse what it cannot see.
  Options: (a) `prepare` surfaces "these known concepts would collide under your slug_strategy" as a
  warning the model reads; (b) the SKILL carries a disambiguation rule; (c) both. **(c) is likely, but
  the split must be measured** — a SKILL-only fix is another untested trade.
