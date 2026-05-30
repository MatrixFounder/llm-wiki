# Plan Review — TASK 009 (R-9 critic-prompt hardening)

**Gate:** Planning→Execution · **Reviewer:** plan-reviewer (independent) · **Date:** 2026-05-29
**Verdict:** **APPROVE-WITH-NITS** (`has_critical_issues: false`)

RTM 1:1 complete (R-9.1–9.6 + C2 → bead → verification, no gap, no orphan). The RED-before-fix
ordering (009-03 baseline MUST precede 009-04) judged **airtight** (stated in 3 places + a
file-existence gate). Stub-First mapping **faithful** (RED = baseline shows the bleed; GREEN =
recorded delta; green-throughout on the deterministic suite). The orchestrator-graded-vs-pytest
split honestly labelled (no un-pinnable LLM assertion smuggled into pytest; grade.py tested on
synthetic JSON). C2 carve-out traced end-to-end (009-01 `defect_id`+`injection_class` → 009-02
grade.py → 009-05). `_is_fail` pin code-verified importable.

## Findings (applied to the bead specs)
- **MINOR-2** — grade.py must IMPORT and CALL `_is_fail` (not "mirror"/reimplement). **Applied**
  (009-02 wording + TC).
- **MINOR-3** — add a matcher near-miss negative test (pin the overlap threshold). **Applied**
  (009-02 TC-06).
- **NIT-4** — case-3 `factual ≥ high` is a data-guaranteed C2 backstop (not run-time improvised).
  **Applied** (009-01).
- **NIT-5** — eval count `>= 7`, not `== 7`. **Applied.**
- **NIT-6** — the validator must not hard-require `evals/files/`. **Applied.**

Grouping of R-9.1/9.2/9.3/C2/9.6a-c into bead 009-04 judged cohesion (one prompt artifact,
combined effect measured by 009-05), not feature-grouping. C4 ("no code change") correctly
characterizes grade.py + tests as test-only/eval assets.
