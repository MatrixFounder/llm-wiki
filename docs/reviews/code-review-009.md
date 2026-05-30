# Code Review — TASK 009 (`wiki-verify` grader + eval harness)

**Gate:** Execution→Merge · **Reviewer:** code-reviewer (independent) · **Date:** 2026-05-29
**Verdict:** **APPROVE** (`has_critical_issues: false`)

Ran the suite: 25 target tests pass; the 45 pre-existing `test_wiki_verify_*`/`test_verify_*`
tests pass **unedited** (the byte-stable-contract gate); full deterministic suite green;
`mypy --strict skills/wiki-verify/evals/grade.py` clean.

## Pillars
- **Compliance** — `grade.py` IMPORTS + CALLS `_is_fail`/`_SEV_ORDER` (no FAIL-rule
  reimplementation — MINOR-2); `_FAIL_ON="high"` matches the shipped argparse default → exact
  verdict parity. Lens-purity−C2 predicate matches the README verbatim (both arms test-verified).
  Zero `scripts/`/`sql/` change.
- **Quality/logic** — deterministic, typed, no dead code / speculative complexity. The matcher
  (`_overlap` + lens-preference + `_match_text`) is sound on the probed edge cases (empty findings,
  missing keys, one-finding→multi-defect, below-floor recall, near-miss negative).
- **Testing (no over-mocking)** — grader tests use hand-written **synthetic critic JSON**, never a
  mocked model. Coverage: C2 carve-out both arms + logic-on-injection, `_is_fail` parity, matcher
  near-miss negative, recall miss, severity drift, false-positive. The canary-defang fence/inline
  detection is correct.
- **Eval-set quality** — well-formed, self-contained, vocab pinned to the code enums; the 7 cases
  meaningfully exercise clean/bleed/injection/logic/omission/FP/severity. **Calibration corrections
  machine-verified internally consistent**: `_is_fail(expected_findings, "high")` derives the exact
  `expected_verdict` for all 7 cases; corrections transparently documented in `delta.md §Calibration`
  + applied symmetrically.

## Findings
- **MINOR (non-actionable, doc drift)** — `docs/tasks/task-009-01-*.md` still describes the
  pre-calibration case 6/7 expectations; superseded by `evals.json` + documented in `delta.md`.
  Provenance noise in an archived spec, not a code defect.
