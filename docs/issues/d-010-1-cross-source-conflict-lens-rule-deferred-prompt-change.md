---
id: D-010-1
type: known-issue
status: fixed
opened_at: 2026-05-31
category: security
slug: d-010-1-cross-source-conflict-lens-rule-deferred-prompt-change
---

# cross-source conflict lens rule (deferred prompt change)

- **Symptom**: When two or more `examined` sources state *conflicting* values for the same
  fact and a `wiki-query` answer presents only one without surfacing the disagreement, the
  shipped `wiki-verify` four-lens contract is **silent** on which lens owns it. The
  `wiki-verify` SKILL.md does not tell any critic to flag an unreconciled cross-source conflict.
- **Root cause**: v2's 32 eval cases all had exactly **one** `examined` source, so the
  multi-source audit path was never exercised and the gap was never surfaced. TASK 010's
  eval-v3 adds the multi-document cases that expose it.
- **Decision (D-010-1)**: an unreconciled cross-source conflict the answer hides is owned by
  **`completeness`** (a *material omission of a source fact* — quote the omitted conflicting
  **source** phrase) at `medium`. It is **NOT** `factual` (each value IS grounded in *a*
  source, and SKILL.md forbids flagging a source-supported claim) and **NOT** `logic` (logic
  is scoped "within the answer", the inconsistency is across sources). Because `completeness`
  does not move `_is_fail`, a conflict-only answer is `verdict:"pass"` (advisory gap, not a
  grounding failure).
- **Affected components**: `skills/wiki-verify/SKILL.md` (`completeness-faithfulness` lens —
  the additive sentence specifying D-010-1).
- **Fix plan**: the `evals-v3.json` cross-source-conflict cases ship in **TASK 010** (they
  measure whether the *unguided* prompt incidentally surfaces conflicts — the "before" half).
  The `SKILL.md` sentence is **deferred to a separate PR** because `skills/wiki-verify/` is
  SECURITY-SENSITIVE (code review + security audit + SECURITY label mandated by the file's
  banner). That PR runs the full-corpus v1+v2+v3 no-degradation A/B (PLAN §"Regression
  safety") + a 2-case conflict before/after to justify the rule.
- **Prevention**: TASK 010's `evals-v3.json` multi-document group is the standing regression
  for the multi-source audit path; the deferred rule cannot land without the no-degradation gate.
- **Resolution (2026-06-01, D-010-1 PR)**: added the cross-source-conflict block to the
  `completeness-faithfulness` lens in `skills/wiki-verify/SKILL.md` (v1.0→1.1) — completeness
  owns the omitted conflicting source value at `medium`, with explicit carve-outs (don't fire
  when the answer *surfaces* the conflict; a *fabricated third value* stays `factual`'s lane).
  Ran the **full-corpus v1+v2+v3 no-degradation A/B** (completeness-only re-run, factual/logic/
  security held fixed at committed outputs to isolate the one variable; 122 sub-agents):
  **GATE PASS** — v1+v2 non-degrading on every aggregate metric, v3 conflict detection preserved
  (case 42's "512 shards" omission flagged in both arms), FP 0. The measured effect is **within
  the LLM ±1 noise floor** (the shipped critic already handled conflicts well) — this is a
  **codification/durability** change that makes the eval-v3 conflict cases test a *specified*
  contract. Report: `reports/v3/conflict-rule-ab.md`; raw data `reports/v3/conflict-ab-runs.json`.
  Contract pins (`tests/test_wiki_verify_skill_contract.py`) green; full suite green.
