# PLAN 066 — the instrument, then the measurement, then (and only then) the fix

**Spec**: `docs/TASK.md` (v3, after **two** blocking reviews — 8 criticals, three of which deleted
requirements the author had written).
**Baseline**: `2848 passed, 14 skipped` · `mypy --strict scripts/` clean.

---

## 0. The three rules that govern every bead

1. **GREEN AT EVERY BOUNDARY.** `pytest tests/` ≥ 2848, `mypy --strict` clean, after each bead.
2. **EVERY DENOMINATOR CARRIES A CENSUS — AND THE CENSUS IS *RUN*.** This task exists because a
   number (9/11) was believed rather than measured, and every review round found another one.
3. **EVERY GATE IS MUTATION-TESTED, AND THE MUTATION IS *EXECUTED*.** A gate that cannot fail is the
   disease this whole project keeps catching.

---

## 1. ★ The architecture, in one picture — and why the runner is NOT code

```
 ORCHESTRATOR (me / codex / gemini)          ← Decision-17: the caller owns the reasoning step
   │  for each fixture: FRESH context
   │    ├─ SKILL.md          (verbatim)
   │    ├─ the REAL prepare envelope  (slug_strategy, known_concepts)
   │    └─ input.md body, H-6-wrapped
   │  × K runs at temperature 0
   ▼
 record.py            ← deterministic Python. NO model call. NO SDK. NO new dependency.
   │  stamps: skill_sha256 · per-fixture input_sha256 / grading_sha256 · model · temperature · K
   ▼
 evals/reports/<model>-<date>.json          ← COMMITTED artifact (the raw model outputs)
   │
   ▼
 tests/test_concept_extraction_weak_model.py   ← the GATE. Offline. Deterministic. CI-safe.
      ├─ REFUSES a stale artifact  (skill_sha256 ≠ sha256(SKILL.md) ⇒ "re-run the harness")
      ├─ grades every run through the REAL validators + `expect` census + `forbidden` list
      ├─ verdict = per-fixture MAJORITY over K
      └─ compares against evals/baseline.json — NO FIXTURE THAT PASSES MAY FAIL
```

**The runner is a procedure, not a program.** `requirements.txt` carries **no `anthropic`** (removed
by `task-003-v3-10`), and `skills/concept-extraction/` is **symlinked into user installs** — a client
there would ship this repo's first LLM SDK *inside the rail whose defining invariant is "no LLM client
here."* The orchestrator running the fixtures **is** Decision-17, not an exception to it.

---

## 2. RTM — one requirement, one bead

- [ ] **R-066-1** the runner (procedure + executed) → **066-05**
- [ ] **R-066-2** the recorder + the stamps → **066-01**
- [ ] **R-066-3** the offline gate; **fails on a stale artifact** → **066-02**
- [ ] **R-066-4** the gate proven able to fail — **targeted** mutation, blast radius named first → **066-06**
- [ ] **R-066-5** the contamination census, **as a test** (9/19) → **066-03**
- [ ] **R-066-6** the honest baseline — 3 ways, K=3, per-fixture, forbidden count recorded → **066-05**
- [ ] **R-066-7** the cross-source `mention` **WARNING** (never a refusal — live population = 0) → **066-07**
- [ ] **R-066-8** the IDF refutation **as committed code** → **066-04**
- [ ] **R-066-P** `(no PASS may become FAIL)` ∧ `(forbidden ≤ baseline)` → **066-02**

---

## 3. Bead sequence

| # | bead | phase | RTM |
|---|---|---|---|
| **066-01** | `record.py` — the artifact schema + the stamps | 1 · instrument | R-066-2 |
| **066-02** | ★ the GATE — stale-refusal · real validators · census · forbidden · majority · baseline | 1 · instrument | R-066-3, R-066-P |
| **066-03** | ★ the CONTAMINATION CENSUS as a test (9/19, asserted) | 1 · instrument | R-066-5 |
| **066-04** | the IDF refutation, as committed code + artifact | 1 · instrument | R-066-8 |
| **066-05** | ★★ **RUN THE INSTRUMENT** — K=3 Haiku, record, and READ THE DIAGNOSIS | 2 · measure | R-066-1, R-066-6 |
| **066-06** | ★ the TARGETED mutation — blast radius **named before the run** | 2 · measure | R-066-4 |
| **066-07** | the `mention` warning (a bug-fix; not the headline) | 3 · fix | R-066-7 |
| **066-08** | docs, `evals/README.md:117` correction, final gates | 3 · fix | all |

**066-05 is the pivot.** Everything before it is the instrument; everything after is informed by what
it says. **The recall fix is NOT a bead** — it is the next task, authored from the diagnosis.

---

## 4. ★ What 066-05 must NOT do

- **It must not tune the harness until it prints 9.** A different number is a **fact**, not a failure:
  record it, re-baseline, say so out loud. Re-running until the expected number appears is p-hacking
  the baseline the whole task is measured against.
- **It must not read the score as a scalar.** Report **three**: overall · the **CLEAN** subset
  {03, 04, 05} · the **contaminated** subset. Fixture **08**'s entire six-key answer is printed in
  `SKILL.md` — a pass there is not evidence of anything.

---

## 5. Invariants

| # | invariant | enforced by |
|---|---|---|
| I-1 | **No LLM client, no new dependency, nothing new in the shipped payload** | 066-01; the Decision-17 census **derived by grep at test time**, never hand-listed (v2 hand-listed 3 gates; there are ≥5) |
| I-2 | **The gate cannot go green on a stale artifact** | 066-02 + its executed mutation |
| I-3 | **Zero DDL** | `git diff sql/` empty |
| I-4 | **No refusal is added on a currently-exit-0 path** — the live population is 0, and that is how 0.88 came to block correct work | 066-07 |
| I-5 | **No acceptance criterion is satisfiable by doing nothing** | 066-02's mutation; 066-06's targeted mutation |

---

## 6. Risk register

| risk | why it bites | mitigation |
|---|---|---|
| The gate greens on a **stale** recording | `SKILL.md` **is** the artifact under test — a contributor edits it and the gate keeps grading the old skill | `skill_sha256` stamp; **mutation executed** (066-02) |
| The baseline is **re-run until it prints 9** | it is the number the whole task is measured against | temperature 0, K=3, **majority**; "a different number is a fact" written into the bead |
| The **scalar floor** gets easier as fixtures grow | 9/11 → add a fixture → 9/12 clears the same bar while being weaker | **per-fixture regression**, never a scalar (066-02) |
| The instrument reproduces 9/11 and we learn **nothing** | then the diagnosis is "the honest baseline agrees" — and the fix is still unknown | that is a legitimate outcome: **the floor becomes enforceable**, which it is not today |
| A `mention` **refusal** blocks correct work | exactly how 0.88 died | **warning only** (066-07); live population measured **= 0** |
