# Task 009-06: Security audit + code review + docs close-out (the mandatory C3 gate)

## Use Case Connection
- R-9.6d (no new prompt-surface findings), **C3** (SECURITY-SENSITIVE → code review AND security audit mandatory), the framework's living-docs sync.

## Task Goal
Discharge the **mandatory** security audit + code review on the TASK-009 change set (the few-shot additions are a new injection surface in a file loaded verbatim into the orchestrator's context), then sync the living docs and flip the ARCHITECTURE status to SHIPPED. No auto-commit (VDD invariant).

## Changes Description

### Security audit (security-auditor subagent) — the load-bearing gate
Audit `skills/wiki-verify/SKILL.md` (enriched) + `skills/wiki-verify/evals/*` for:
- **H-6 preserved/strengthened**: the untrusted-data framing, fenced-sentinel pattern, and "never obey" rule are intact; the anti-bleed scoping did NOT weaken injection defense-in-depth (both FAIL-lenses retain the injection per C2 — verified the non-FAIL lenses being silenced removes only noise, not gate-coverage).
- **Few-shot defang (the new surface)**: no example line is parseable as a **live** directive outside its `EXAMPLE` fenced sentinel; the canary tokens (`SYSTEM:`, `ignore previous`, `<|im_start|>`, `[[INST]]`) appear only inside fences (cross-check `test_wiki_verify_skill_contract.py` TC-03 — the audit confirms the mechanical check is sufficient, not bypassable by an alternate canary).
- **eval fixtures**: case-3 injection fixture is data the runner fences as untrusted; `grade.py` does no `eval`/`exec`/shell, no network, no SQL (pure JSON→JSON); `evals/*` introduces no path traversal.
- **No contract drift**: the verdict JSON / vocab / grounding gate are byte-stable (cross-check `test_wiki_verify_skill_contract.py`).

### Code review (code-reviewer subagent)
- `grade.py`: typed, deterministic, imports the gate's severity/FAIL semantics (no drift); tests cover the C2 carve-out + verdict parity.
- `evals.json` + fixtures: well-formed, self-contained, vocab pinned to the code enums.
- The whole `test_wiki_verify_*` suite green **without edits** (contract unchanged); `mypy --strict` clean.

### Docs close-out (living-docs sync — in place, never archived here)
- **`skills/.AGENTS.md`** — note the `wiki-verify` rubric + the `evals/` harness (what it is, that it's orchestrator-graded not pytest, and that committed fixtures live here NOT in `samples/`).
- **`docs/ARCHITECTURE.md`** index — flip the TASK-009 block from "IN PROGRESS" to "SHIPPED `<date>`" with the recorded delta headline (purity↑/severity↑/recall held).
- **`docs/architectures/functional-architecture.md`** §Verification Layer — drop a one-line "shipped + delta recorded in `evals/reports/delta.md`" pointer; the design subsections are already in place.
- **`docs/KNOWN_ISSUES.md`** — record any deferred LOW (e.g. Q4 sibling-skill rubric reuse; any eval-coverage gap surfaced in 009-05) under a TASK-009 closures block.
- **`tests/.AGENTS.md`** — note `test_wiki_verify_evals.py` / `_grade.py` / `_skill_contract.py` (deterministic) vs the orchestrator-graded eval run (not in pytest).
- **`docs/reviews/`** — write `security-audit-009.md` + `code-review-009.md` (+ the task/architecture/plan review records already produced).

## Test Cases
### Gate assertions
1. **TC-01 (audit clean)**: security-auditor returns no unresolved HIGH/CRITICAL on the prompt surface; H-6 preserved; defang control sufficient.
2. **TC-02 (review clean)**: code-reviewer passes `grade.py` + evals + the contract pins.
3. **TC-03 (suite green)**: full `pytest` green (incl. the 3 new deterministic test files); `mypy --strict` clean; verdict contract unchanged (no edits to the pre-existing `test_wiki_verify_*` assertions).
4. **TC-04 (docs synced)**: ARCHITECTURE TASK-009 → SHIPPED; `.AGENTS.md` ×2 updated; review records written.

## Acceptance Criteria
- [ ] Security audit + code review both clean (records in `docs/reviews/`); H-6 preserved; defang control verified non-bypassable.
- [ ] Living docs synced in place (ARCHITECTURE SHIPPED + delta headline; `skills/.AGENTS.md` + `tests/.AGENTS.md`; KNOWN_ISSUES closures).
- [ ] Full `pytest` green; `mypy --strict` clean; **no `scripts/`/`sql/` change**; `user_version` 5; no `import anthropic`.
- [ ] Nothing auto-committed (the commit decision is the operator's).

## Notes
The mandatory C3 gate + close-out. The security audit is NOT optional for this file (it is loaded verbatim into the orchestrator's LLM context — the H-5/H-6 class). The single most important audit finding to chase: can any few-shot example be read as a live directive outside its fence? If yes → back to 009-04. Depends on 009-05 (the final enriched prompt + recorded delta). After this bead the task is review-complete + documented; `/update-docs` (if run) only confirms the archive lockstep.
