# Task 003-v3-15: dogfood smoke on `trade-agents` vault (TASK §7 18 steps, incl. BREAKING CHANGE smoke)

## Meta

- **Bead ID**: `task-003-v3-15-dogfood-smoke`
- **Slug**: `dogfood-smoke`
- **Maps to**: Issue **I-V3.10**; RTM row **R-43**; H-4 (BREAKING CHANGE smoke).
- **Depends on**: task-003-v3-06 (code shipped), task-003-v3-09 (skill docs), task-003-v3-10 (anthropic dep dropped), task-003-v3-12 (integration tests).
- **Estimated time**: 0.5 day
- **Priority**: Critical (real-vault end-to-end gate).

## Use Case Connection

- Runs the 18-step recipe from TASK §7 on a real vault (`trade-agents` per TASK §1.2 / I-V3.10) using a real source page.

## Task Goal

Execute all 18 steps from `docs/TASK.md` §7:

1. **Setup** (one-time): vault registered + at least one source page indexed. Use `trade-agents` per spec.
2. **prepare**: invoke `wiki-extract-concepts prepare ...`; capture JSON; assert `is_unchanged=false`, `source_hash` is 64-char hex, `missing_concept_files` is a list (possibly empty).
3. **Operator synthesizes candidates** (smoke uses canned JSON inline):
   ```bash
   cat > /tmp/candidates.json <<'EOF'
   [{"slug":"sample-concept","name":"Sample Concept","definition":"Demo.",
     "source_quote":"this is a sample concept extracted from the source body",
     "source_span":"L5-L7","entity_type":"concept"}]
   EOF
   ```
4. **apply** with `--source-hash` from prepare.
5–10. **Adversarial smokes** (H-1, H-2, H-5, H-6, H-7, H-9 from §7): hash mismatch, empty candidates, candidates-file-outside-vault, oversized field, markdown injection, unknown-field.
11. **BREAKING CHANGE smoke (H-4)**: `bin/wiki-extract-concepts --vault X --source-page Y` (no subcommand) → argparse error containing `prepare` and `apply`.
12. `env | grep -i anthropic` → empty.
13. `grep anthropic requirements.txt` → empty + `python -c "import anthropic"` → ModuleNotFoundError.
14. `bin/wiki-extract-concepts prepare --help | grep source-page` and `bin/wiki-extract-concepts apply --help | grep source-hash` → both match.
15. Idempotency re-run: re-invoke prepare with same source → `is_unchanged=true`.
16. Error envelope content-leak audit (covered programmatically by 003-v3-17 + asserted in smoke as well).
17. Full `pytest tests/ -q` → ≥ 436 passed (Option A target).
18. `mypy --strict scripts/` → clean.

## Stub-First Plan

n/a (smoke recipe — verification only).

## Changes Description

No files edited. Smoke script may be saved at `scripts/dogfood/smoke-003-v3.sh` (optional artifact).

## Files Touched

- (optional) `scripts/dogfood/smoke-003-v3.sh`

## Acceptance Criteria

- [ ] All 18 smoke steps from TASK §7 execute and assert their expected outcome.
- [ ] **BREAKING CHANGE smoke (step 11 / H-4)**: argparse error mentions `prepare` AND `apply`.
- [ ] Adversarial smokes 5-10 all pass (each triggers the expected exit code + sub-envelope without leaking offending content).
- [ ] Step 17 (pytest sweep) → ≥ 436 passed.
- [ ] Step 18 (mypy) → no issues.

## Verification

The smoke recipe itself is the verification step. Run:

```bash
source .venv/bin/activate
export VAULT=trade-agents
export VAULT_ROOT=/path/to/trade-agents
export DB=/tmp/dogfood-v3.db

# Step 11 BREAKING CHANGE
bin/wiki-extract-concepts --vault $VAULT --source-page Y 2>&1 | grep -qE "prepare|apply" && echo "H-4 OK"

# Steps 2-10: full recipe from TASK §7

# Step 12-14: invariants
env | grep -i anthropic && echo "FAIL" || echo "OK: no anthropic env"
grep anthropic requirements.txt && echo "FAIL" || echo "OK: dep removed"
python -c "import anthropic" 2>&1 | grep -q "ModuleNotFoundError" && echo "OK: import fails"
bin/wiki-extract-concepts prepare --help | grep -q "source-page" && echo "OK: prepare"
bin/wiki-extract-concepts apply --help | grep -q "source-hash" && echo "OK: apply"

# Step 15: idempotency
# (re-run prepare after first apply succeeds; assert is_unchanged=true)

# Step 17-18
pytest tests/ -q
mypy --strict scripts/
```

## Rollback

n/a (no code changes).

## Notes

- If `trade-agents` vault is not available on the dev machine, the bead executor may use any registered vault with at least one source page. The bead's acceptance is the recipe completing successfully, not specifically against `trade-agents`.
- The smoke recipe in TASK §7 is authoritative; this bead's job is to run it and capture the results.
