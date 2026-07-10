# 057-09 — [NF-1] final gates

**Goal:** the full regression bar is green before Phase 4 adversarial review.

**Steps:**
1. `source .venv/bin/activate && pytest tests/` — 0 failures.
2. `mypy --strict scripts/` — clean.
3. Envelope back-compat spot-check: existing `prepared`/`unchanged`/`fetch-failed` shapes
   untouched by W2/W3 diffs (covered by the untouched pre-057 test files staying green
   unmodified — list any test file that HAD to change and why in the completion note).
4. No new bin/command → no install-propagation step.

**Verification:** both gates green; paste the summary lines (test count, mypy) into the
session-state completion note.
