# Task 003-v3-13: ARCHITECTURE.md drift-verification (no editorial pass — already done in analysis)

## Meta

- **Bead ID**: `task-003-v3-13-arch-update`
- **Slug**: `arch-update`
- **Maps to**: Issue **I-V3.8**; RTM rows **R-30**, **R-33′**, **R-42**.
- **Depends on**: task-003-v3-06 (code matches the described v3.1 shape).
- **Estimated time**: 0.1 day
- **Priority**: Low (verification gate).

## Use Case Connection

- ARCHITECTURE.md is the source of truth for the system shape. v3.1 §2.1 + §3.4 + status header were **already updated** during the analysis phase (per TASK §1.2). This bead VERIFIES no drift between TASK + PLAN + code + ARCH.

## Task Goal

Grep ARCHITECTURE.md for v3.1 invariants and confirm presence/absence of expected strings:

### Must be present (v3.1 invariants):

- `prepare` and `apply` subcommand names — in §2.1.
- Exit-code table mentioning codes `0/1/2/4/5/6` — in §2.1.
- New sub-envelopes: `SOURCE_TOO_LARGE`, `SOURCE_CHANGED_DURING_EXTRACTION`, `INVALID_CANDIDATES_PATH`, `CANDIDATES_TOO_LARGE`, `CANDIDATE_COUNT_OUT_OF_BOUNDS`, `FIELD_TOO_LONG`, `UNKNOWN_FIELD`, `FIELD_QUOTE_NOT_IN_BODY`.
- `Decision-17` reference.
- `v3.1 target architecture` or equivalent status header marker.
- §3.4 sequence diagram step `[3]` updated to describe orchestrator-driven synthesis (NOT embedded LLM call).

### Must be absent (v2-only references in v3.1 sections):

- `extract_concepts_llm` (the deleted helper).
- `LLMUnavailableError` (the deleted exception class).
- `--model` (the deleted CLI flag).
- `--max-tokens` (the deleted CLI flag).
- `claude-sonnet-4-6` as a hardcoded reference (replaced by `--orchestrator-id`).
- `exit-3` or `LLM_API_UNAVAILABLE` (the retired exit code).

If drift found, edit ARCH inline to correct (use the existing v3.1 content as the model). If clean, mark bead complete.

## Stub-First Plan

n/a (verification only).

## Changes Description

### Edited files

- `docs/ARCHITECTURE.md` (ONLY if drift found; expected: no edits).

## Files Touched

- `docs/ARCHITECTURE.md` (read; possibly edited).

## Acceptance Criteria

- [ ] All must-be-present strings appear in `docs/ARCHITECTURE.md` (§2.1 and §3.4 sections).
- [ ] None of the must-be-absent strings appear in the v3.1 sections (status-header references to v2 historical state are fine; what matters is the §2.1 component description and §3.4 sequence diagram have no live v2-only references).
- [ ] If any drift was found, the file has been edited to correct; this bead's acceptance step lists the diffs.

## Verification

```bash
# Must be present
grep -q "prepare" docs/ARCHITECTURE.md && echo "OK: prepare"
grep -q "apply" docs/ARCHITECTURE.md && echo "OK: apply"
grep -q "Decision-17" docs/ARCHITECTURE.md && echo "OK: Decision-17"
grep -q "v3.1 target architecture" docs/ARCHITECTURE.md && echo "OK: status marker"
grep -q "SOURCE_TOO_LARGE" docs/ARCHITECTURE.md && echo "OK: SOURCE_TOO_LARGE"
grep -q "SOURCE_CHANGED_DURING_EXTRACTION" docs/ARCHITECTURE.md && echo "OK: SOURCE_CHANGED"
grep -q "INVALID_CANDIDATES_PATH" docs/ARCHITECTURE.md && echo "OK: INVALID_CANDIDATES_PATH"
grep -q "CANDIDATES_TOO_LARGE" docs/ARCHITECTURE.md && echo "OK: CANDIDATES_TOO_LARGE"
grep -q "CANDIDATE_COUNT_OUT_OF_BOUNDS" docs/ARCHITECTURE.md && echo "OK: COUNT_OUT_OF_BOUNDS"
grep -q "FIELD_TOO_LONG" docs/ARCHITECTURE.md && echo "OK: FIELD_TOO_LONG"
grep -q "UNKNOWN_FIELD" docs/ARCHITECTURE.md && echo "OK: UNKNOWN_FIELD"

# Must be absent in v3.1 sections (sanity check — coarse-grained grep)
# Note: status-header may reference v2 history; the §2.1 + §3.4 sections must not.
# We do a coarse-grained check that the v2 deleted helpers don't appear as
# "live" component descriptions.
awk '/## 2.1|### 2.1|## 3.4|### 3.4/,/^## [0-9]/' docs/ARCHITECTURE.md | \
  grep -nE "extract_concepts_llm|LLMUnavailableError|--model |--max-tokens|LLM_API_UNAVAILABLE"
# expect: empty OR only annotation references like "v2 had X" or "removed"
```

## Rollback

If edits were made, `git checkout HEAD~1 docs/ARCHITECTURE.md`.

## Notes

- This bead is intentionally low-effort because ARCH was updated in the analysis phase. If significant drift is found (e.g., the status header still says "v2"), something went wrong in the analysis phase — escalate to architect-reviewer.
- The verification commands above are illustrative; the bead executor may use any equivalent grep/diff combination to confirm the invariants.
