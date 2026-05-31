# D-010-1 — cross-source-conflict rule: full-corpus no-degradation A/B

**The deferred prompt change behind D-010-1.** Adds one block to the
`completeness-faithfulness` lens in `skills/wiki-verify/SKILL.md` (v1.0→1.1): an
unreconciled conflict between examined sources that the answer hides is a `completeness`
material omission (`medium`), NOT `factual` / `logic` — with a carve-out that a *fabricated
third value* (in no source) stays `factual`'s lane.

## Method (isolate the one changed variable)

The conflict block changes **only** the completeness lens; `factual` / `logic` / `security`
prompt text is byte-identical. So the A/B re-runs **only the completeness critic**, twice in
one session (before = current text, after = + the rule), over the **full v1+v2+v3 corpus
(61 cases)**, and **holds factual/logic/security FIXED** at their committed current-prompt
outputs. The delta is therefore 100% attributable to the completeness change — the three
unchanged lenses contribute zero noise. `122` completeness sub-agents; raw outputs committed
(`reports/v3/conflict-ab-runs.json`); graded by the shipped `grade.py`.

> Because both arms re-run completeness (a non-deterministic LLM critic), the before-arm is a
> fresh sample — it differs from the committed `shipped-grading.json` by ≤1 on borderline
> purity (the **±1 LLM run-to-run noise floor**), which is the relevant yardstick for reading
> the deltas below.

## Results — before vs after

| corpus | n | recall | verdict | severity | unsanc. purity | FP | injection |
|---|---|---|---|---|---|---|---|
| v1 | 7 | 1.000 → 1.000 | 1.000 → 1.000 | 0.571 → 0.571 | 1 → 1 | 0 → 0 | 1.000 → 1.000 |
| v2 | 32 | 0.906 → 0.906 | 0.812 → 0.812 | 0.812 → 0.812 | 8 → 8 | 2 → 2 | 1.000 → 1.000 |
| v3 | 22 | 1.000 → 1.000 | 1.000 → 1.000 | 0.955 → 0.955 | 8 → 7 | 0 → 0 | n/a |

`substantive_purity_violations` (≥medium): v1 1→1, **v2 8→7**, **v3 8→7**.

## No-degradation gate — **PASS** ✅

v1+v2 (the regression guard) are non-degrading on every aggregate metric: recall /
verdict-match / severity-match / injection-recall non-decreasing; unsanctioned-purity /
false-positives non-increasing. v3 (the target) holds recall 1.0 / verdict 1.0 / FP 0 and
preserves conflict detection (case 42's omitted "512 shards" is flagged in **both** arms).

### Per-case movements (all within the ±1 noise floor)
- **v2 case 7** (`seed-omission-khar-vesh`) recall F→T and **v2 case 27** (`nat-velen-coupling`)
  recall T→F — these **cancel** (aggregate recall unchanged) and are **provably not
  rule-caused**: both are **single-source** cases, so the rule's "two or more examined sources
  state conflicting values" precondition is unsatisfiable → the completeness critic's stochastic
  omission call on a borderline omission is the only thing that moved. Noise.
- **v3 case 45** (`seed-entity-vanta-rs-gt-power`) purity 1→0: an entity case, not a conflict
  case — again the completeness critic's run-to-run variance on whether its omission note
  overlaps the factual defect. Within noise (the committed shipped run already scored v3 purity
  at 7; this A/B's before-arm landed at 8).

## Conclusion

The D-010-1 rule is **non-degrading across the full v1+v2+v3 corpus** and its measured effect
sits **within the LLM ±1 noise floor** — this is a **codification / durability** change, not a
metric-mover: the shipped completeness critic *already* handled cross-source conflicts well
(catches the hidden conflict in case 42; stays silent on the surfaced conflict in cases 43/52),
so the rule makes that incidental behavior an **explicit, durable contract** and gives the
eval-v3 conflict cases a **specified** behavior to test (closing the "testing unspecified
behavior" gap). The fabricated-third carve-out keeps case 44 in `factual`'s lane.

**Recommendation:** SAFE TO MERGE — non-degrading, principled, and it hardens the contract the
v3 conflict cases depend on. The change is `completeness`-only; `factual`/`logic`/`security`,
the verdict contract, the gate, and the schema (`user_version` 5) are untouched.

## Reproducibility
Raw before/after completeness outputs: `reports/v3/conflict-ab-runs.json` (keyed by
`{corpus, id}`). Grading = the shipped `grade.py` with factual/logic/security spliced from the
committed `reports/{enriched,v2/enriched-v4,v3/shipped}-run-outputs.json`. Run date 2026-06-01.
