# Task 068-09: architecture §2.2.2 + final gates

**Phase:** 2 — Docs/security · **RTM:** R-068-1, R-068-10 · **Priority:** High · **Depends on:** 068-07, 068-08 · **Tag:** [DOC/GATES]

## Goal
Record the feature in the living architecture doc (in place, not archived) and run the whole-suite gates
that discharge R-068-10 and the §9 acceptance criteria.

## Changes — architecture (in-place edits)
- `docs/architectures/functional/native-app-control.md`: add **§2.2.2 "Editor-selection bridge (TASK 068)"**
  matching the §2.2.1 style — the production channel = the `agent-bridge` plugin (T2, least-privilege vs
  `eval`'s RCE); the channel-independent write-back contract (atomic path+range+`somethingSelected` guard,
  `replaceRange` + `save`, base64 both directions, result-by-shape, the typed degradation ladder); the
  Decision-17 wrapper `obsidian_selection.py` (plugin-only, never `eval`, coherence dispatch marker);
  and the carried Open Questions (OQ1 callback-under-focus INFERRED; OQ3 cross-machine `.obsidian/` sync;
  OQ5 ARG_MAX/payload threshold). Update the chunk's "Contents" list with the new anchor.
- `docs/ARCHITECTURE.md`: a one-line note in the security section (consistent with how TASK 041 recorded
  §2.2.1) — "selection read/replace via the `agent-bridge` T2 plugin channel; `eval` stays T3 and is never
  auto-dispatched (TASK 068 / §2.2.2)".

## Gates (caller-side)
- **G1 (R-068-10):** `pytest tests/ -q` → **0 NEW failures AND ≥2930 passed** vs the §0 Baseline
  (`2930 passed, 14 skipped, 0 failed`); record the exact new count + skips.
- **G2 (A-14):** `mypy --strict skills/obsidian-cli/scripts/obsidian_selection.py` clean (and
  `mypy --strict scripts/` unaffected).
- **G3 (R-068-1):** re-affirm the plugin type-check — `npx tsc --noEmit` from `plugin/agent-bridge/`
  exits 0 (or the recorded symbol-review fallback), post-Phase-1.
- **G4 (A-11):** `git diff sql/` empty — zero DDL, no schema change.
- **G5 (A-12):** `grep -E "import anthropic|from anthropic" skills/obsidian-cli/scripts/obsidian_selection.py`
  → no hits; one JSON envelope + stable exit code per invocation.
- **G6:** `python3 .agent/skills/skill-spec-validator/scripts/validate.py --mode plan docs/PLAN.md docs/TASK.md`
  → "Success: All 10 requirements covered."
- **G7:** record the Baseline diff + any carve-out in `docs/TASK.md`'s Completion section on ship (A-13).

## Acceptance criteria
- [ ] §2.2.2 added to native-app-control.md (in place) + the ARCHITECTURE.md security one-liner.
- [ ] G1–G6 all pass; results recorded.

## Notes
`[DOC/GATES]`. No new archived architecture doc — this is a small in-place edit to a living document, as
the parent placement decision fixed. The eval-behaviour cases (E-27/E-28) run as part of the eval harness,
not pytest.
