# Architecture Review — TASK 009 (R-9 critic-prompt hardening)

**Gate:** Architecture→Planning · **Reviewer:** architecture-reviewer (independent) · **Date:** 2026-05-29
**Verdict:** **APPROVE-WITH-NITS** (`has_critical_issues: false`)

Independently **code-verified** the two load-bearing claims against `wiki_verify_multi.py`:
(1) "zero code/schema change — vocab byte-stable" (enums 61-63, `apply` validation 443-448,
data-model migration ladder stops at v4→v5, `user_version` 5) and (2) "C2 backstop / FAIL
rule" (`_is_fail` 275-292 makes a `factual` finding ≥ threshold independently force FAIL, so
the dual `factual`+`security` injection report preserves gate redundancy without re-introducing
bleed). YAGNI: the eval-harness component is proportionate (the change's value is untestable by
assertion). Orchestrator-graded-not-pytest judged the right call.

## Findings (all applied in place)
- **F-1 (MINOR)** — lens-purity "exclude the sanctioned overlap" needs an operational predicate
  → added the grader-schema obligation (per-finding `defect_id` + per-case injection-class flag;
  a `factual`+`security` co-report on a NON-injection is still bleed). **Applied.**
- **F-2 (MINOR)** — few-shot defang under-specified for a SECURITY-SENSITIVE file → replaced
  "defanged" with a NAMED control (describe-not-render; fenced EXAMPLE sentinel; audit checks no
  bare directive). **Applied.**
- **F-3 (NIT)** — grader schema ownership → added a grader-output skeleton. **Applied.**
- **F-4 (NIT)** — softened the ephemeral-dogfood claim; the durable proof is the committed
  scenario-C eval case. **Applied.**
- **F-5 (NIT)** — added UC-1 to the R-9.1 trace. **Applied.**

Coverage: R-9.1–9.6 + C2 each map to an architecture location + a test/AC. No data-model /
interface / schema change (correctly asserted). Index-Mode in-place edits, no per-task snapshot.
