# wiki-import eval run — negative + xfail tripwire (TASK 046 P4 add) — 2026-06-30

Supplement to `2026-06-30-sonnet-produce-opus-grade-converged.md`, adding the two
acquire-degradation cases (the scanned-PDF / OCR gap). Same harness + model matrix
(produce = **sonnet**, grade = **opus**, with an `impl_leak` check).

- **Result: WI-20 PASS · WI-21 xfail (expected fail) · never_relax failures: 0 · impl leaks: 0.**
- The xfail mechanism is validated end-to-end: a documented gap fails cleanly *and* is exempt from
  the gate; a future xPASS becomes the promote-me signal.

| Case | Class | flag | Verdict | Meaning |
|---|---|---|---|---|
| WI-20 | acquire-degradation | `never_relax` | **PASS** | graceful `FETCH_FAILED` + needs-ocr stub; no fabricated summary |
| WI-21 | acquire-degradation | `expected_fail` (`tracks: df-046-1`) | **xfail** (failed as expected) | scanned-PDF → real summary is unattainable today (no OCR) |

## Notes

- **WI-20** (`never_relax`): given a scanned/image-only PDF where `prepare` returns `FETCH_FAILED`
  (DocumentScanned, exit 10) and writes no `_raw`, the producer treated it as a hard stop —
  *"no _raw, no REASON, no apply, no note JSON"* — and filed a **needs-manual / needs-ocr stub by
  hand** instead of inventing content. It reproduced a hypothetical note shape only as explicitly
  non-executing reference (*"Not applicable… none of that executes"*); no `wiki-import apply` command
  was proposed. This pins the honesty invariant: **an unreadable source must never become a
  fabricated summary.**
- **WI-21** (xfail tripwire, `tracks: df-046-1`): the producer faithfully **refused** —
  *"prepare exits 10 … no _raw, REASON never runs, apply files nothing"*, with OCR named only as an
  **external** operator workaround the plan does not perform. Both graded fields
  (`expect_produces_summary`, `expect_statement`) are therefore not satisfied → `pass=false`, which
  **is** the expected xfail outcome for the OCR gap. The grader notes: *"an xPASS here would signal
  the OCR gap had closed."* When `wiki-import prepare` gains OCR (df-046-1), re-running this case will
  xPASS → drop `expected_fail` and re-baseline the floor.

## Gate impact

The full 21-case set is now **20 expected_pass + 1 xfail**. The gate (R-13) is unchanged: no
`never_relax` failure (WI-20 green) and the floor (15, over expected_pass) is met/raised. WI-21's
failure is expected and does not count against the gate.

## Reproduce

Workflow `task046-p4-evals` (produce=sonnet, grade=opus). Shape pinned by
`tests/test_wiki_import_evals.py::test_expected_fail_cases_are_tracked_and_not_never_relax`
(+ the floor-over-expected_pass assertion).
