# Task 003-14: `mypy --strict` + regression sweep [ACCEPTANCE GATE]

## Meta

- **Bead ID**: `task-003-14-mypy-regression`
- **Slug**: `mypy-regression`
- **Maps to**: Issue **I-7.14**; RTM rows **R-43**, **R-41**, and implicitly **ALL** RTM rows of TASK 003 v2.
- **Depends on**: **all prior** beads task-003-00..task-003-13.
- **Estimated time**: 0.5 day
- **Priority**: Critical (the acceptance gate — gates task completion)

## Use Case Connection

- All UCs of TASK 003 — full end-to-end validation including the 12-step smoke recipe (TASK.md §7).

## Task Goal

Verify that the complete TASK 003 v2 surface ships without regressions:

1. **`mypy --strict scripts/` clean** — including the two new modules (`_manifest_consumer.py` + `wiki_extract_concepts.py`) and the modified `wiki_enrich.py` re-export shim. No new `# type: ignore` comments unless paired with a documented upstream-issue link.
2. **Full test suite passes** — `pytest tests/ -q` reports 332+ green, 0 failed (328 TASK-004 baseline + 4 from 003-00 + new unit tests from 003-03..003-13).
3. **Manual smoke recipe** — run TASK.md §7 steps 1-12 against a real vault (operator-driven). All steps return the expected output.
4. **Invariant grep checks** — Decision-15 (no `--manifest-*` flags on `wiki-enrich`), Decision-16 (no cross-skill imports), back-compat alias preserved.

This is a **verification-only** bead. No code changes expected beyond fixing any regressions the sweep surfaces.

## Stub-First Plan

**Phase 1 — n/a (verification-only per PLAN.md §3 row 003-14).**

**Phase 2 — Direct verification**:

1. **mypy sweep**:
   ```bash
   mypy --strict scripts/
   ```
   Expect `Success: no issues found`. If any new errors surface:
   - For genuine type bugs: fix in the original bead's source file.
   - For false-positives traceable to upstream type debt: add `# type: ignore[<error-code>]` paired with `# UPSTREAM-ISSUE: <link>` per the TASK 004 precedent. Document each one in the bead's PR description.

2. **Pytest sweep**:
   ```bash
   pytest tests/ -q
   ```
   Expect `332+ passed, 0 failed`. If any pre-existing test fails:
   - Diagnose: is it touching a refactored code path (003-00 candidate)?
   - Fix: revert the regression OR update the test to reflect the new contract (must be approved by code-review).

3. **Smoke recipe** (TASK.md §7) — operator runs against a real vault (e.g., `trade-agents`):
   ```bash
   source .venv/bin/activate
   export VAULT=trade-agents
   export VAULT_ROOT=/path/to/trade-agents

   # Step 1: baseline candidate count = 0
   sqlite3 ~/.local/share/wiki-index/global.db \
     "SELECT count(*) FROM entities WHERE vault_id='$VAULT' AND is_candidate=1;"
   # Expected: 0

   # Step 2: pick a source page
   sqlite3 ~/.local/share/wiki-index/global.db \
     "SELECT slug FROM pages WHERE vault_id='$VAULT' AND type='summary' LIMIT 1;"

   # Step 3a: inspection mode
   python -m scripts.wiki_skills.wiki_extract_concepts \
     --vault $VAULT --vault-root $VAULT_ROOT --source-page <SLUG> \
     > /tmp/extract-manifest.json
   echo "Exit: $?"  # Expected: 0

   # Step 3b: manifest passes neutral-module contract
   python -c "
   import json
   from pathlib import Path
   from scripts.wiki_skills._manifest_consumer import validate_manifest
   m = json.load(open('/tmp/extract-manifest.json'))
   validate_manifest(m, '$VAULT', Path('$VAULT_ROOT'))
   print(f'Concepts: {len(m[\"written\"])}; validate_manifest passed')
   "
   # Expected: Concepts: N; validate_manifest passed

   # Step 4: --ingest end-to-end
   python -m scripts.wiki_skills.wiki_extract_concepts \
     --vault $VAULT --vault-root $VAULT_ROOT --source-page <SLUG> --ingest \
     > /tmp/extract-with-ingest.json
   python -c "
   import json
   r = json.load(open('/tmp/extract-with-ingest.json'))
   assert r['extraction']['status'] == 'ok'
   assert isinstance(r['index']['upserted'], list)
   print(f'Indexed {len(r[\"index\"][\"upserted\"])} pages in-process')
   "

   # Step 5: is_candidate=1 count
   sqlite3 ~/.local/share/wiki-index/global.db \
     "SELECT count(*) FROM entities WHERE vault_id='$VAULT' AND is_candidate=1;"
   # Expected: >= N

   # Step 6: page_entity_refs provenance
   sqlite3 ~/.local/share/wiki-index/global.db \
     "SELECT count(*) FROM page_entity_refs
      WHERE vault_id='$VAULT' AND page_slug='<SLUG>'
      AND trust_level='medium' AND source_quote IS NOT NULL
      AND line_start IS NOT NULL AND line_end IS NOT NULL;"
   # Expected: >= N

   # Step 7: idempotency
   python -m scripts.wiki_skills.wiki_extract_concepts \
     --vault $VAULT --vault-root $VAULT_ROOT --source-page <SLUG> \
     | python -c "import json,sys; m=json.load(sys.stdin); assert m['action']=='unchanged'"

   # Step 8: concept pages on disk
   ls $VAULT_ROOT/_concepts/*.md | head -5

   # Step 9: wiki-enrich CLI surface unchanged (Decision-15 invariant)
   python -m scripts.wiki_skills.wiki_enrich --help | grep -E 'manifest-file|manifest-stdin' \
     && echo "FAIL" || echo "OK: wiki-enrich surface preserved"

   # Step 10: _manifest_consumer canonical (Decision-16 invariant)
   python -c "
   from scripts.wiki_skills._manifest_consumer import validate_manifest, index_from_manifest, WikiIngestError
   import scripts.wiki_skills.wiki_enrich as we
   assert we.validate_manifest is validate_manifest
   assert we.index_from_manifest is index_from_manifest
   assert we._validate_manifest is validate_manifest
   print('OK')
   "

   # Step 11: full test suite
   pytest tests/ -q
   # Expected: 332+ passed

   # Step 12: mypy strict on new modules
   mypy --strict scripts/wiki_skills/wiki_extract_concepts.py scripts/wiki_skills/_manifest_consumer.py
   # Expected: Success
   ```

4. **Invariant grep checks** (Decision-15 + Decision-16):
   ```bash
   # No --manifest-* flags surfaced on wiki-enrich
   grep -E "manifest-file|manifest-stdin" scripts/wiki_skills/wiki_enrich.py
   # expect: empty

   # No cross-skill imports (wiki_extract_concepts importing from wiki_enrich for these symbols)
   grep "from scripts.wiki_skills.wiki_enrich import" scripts/wiki_skills/wiki_extract_concepts.py
   # expect: empty (only _manifest_consumer is allowed as the import source)

   # Back-compat alias preserved
   python -c "import scripts.wiki_skills.wiki_enrich as we; assert we._validate_manifest is we.validate_manifest; print('OK')"

   # Stale-doc sweep (Decision-15 retraction residue)
   grep -rn "manifest-file\|manifest-stdin\|dispatch_to_wiki_enrich\|R-44\|I-7.15" \
     docs/ skills/ .claude/commands/ scripts/ \
     | grep -v "docs/TASK.md\|docs/tasks/\|docs/plans/plan-004"
   # expect: empty
   ```

## Changes Description

### New Files

- None (verification-only).

### Changes in Existing Files

- Potentially: fixes to any code surfaced by the mypy/test sweep. Each fix lands as a discrete commit referencing the original bead it touches.

## Files Touched (explicit list)

- No edits expected. Files inspected (read-only via verification commands):
  - `scripts/wiki_skills/_manifest_consumer.py`
  - `scripts/wiki_skills/wiki_extract_concepts.py`
  - `scripts/wiki_skills/wiki_enrich.py`
  - `tests/test_wiki_extract_concepts.py`
  - `tests/test_wiki_extract_concepts_integration.py`
  - `tests/test_manifest_consumer.py`
  - `tests/test_sqlite_repository.py`

## Test Surface

- No new tests. This bead runs the entire existing surface.

## Acceptance Criteria (the TASK 003 v2 acceptance gate)

- [ ] **`mypy --strict scripts/` clean** — no errors, no new `# type: ignore` without `# UPSTREAM-ISSUE` link.
- [ ] **`pytest tests/ -q`** → **332+ passed, 0 failed** (328 baseline + 4 from 003-00 + new unit/integration tests).
- [ ] **Smoke 1** (baseline candidate count = 0) → expected.
- [ ] **Smoke 2** (pick source page) → returns one slug.
- [ ] **Smoke 3a** (inspection mode without `--ingest`) → exit 0, manifest JSON on stdout.
- [ ] **Smoke 3b** (manifest passes `_manifest_consumer.validate_manifest`) → no exception.
- [ ] **Smoke 4** (`--ingest` end-to-end) → exit 0, combined `{"extraction":...,"index":...}` JSON.
- [ ] **Smoke 5** (`is_candidate=1` count) → >= N.
- [ ] **Smoke 6** (`page_entity_refs` provenance) → >= N rows with all 4 provenance fields populated.
- [ ] **Smoke 7** (idempotency) → `action='unchanged'`, no LLM call.
- [ ] **Smoke 8** (concept pages on disk) → N new files.
- [ ] **Smoke 9** (`wiki-enrich` CLI surface unchanged) → "OK: wiki-enrich surface preserved" (Decision-15 invariant).
- [ ] **Smoke 10** (`_manifest_consumer` canonical + alias preserved) → "OK" (Decision-16 invariant).
- [ ] **Smoke 11** (full test suite) → 332+ green.
- [ ] **Smoke 12** (mypy strict on new modules) → Success.
- [ ] **Invariant grep checks**: all four pass (no `--manifest-*` flags, no cross-skill imports, alias preserved, no stale-doc residue).

## Verification

See the "Smoke recipe" block in the Stub-First Plan §Phase 2 above — that IS the verification.

## Rollback

No code rollback for this bead (verification-only). If the sweep surfaces a regression, revert the offending bead's commit per its own rollback section.

## Notes

- This bead is the **gate**. Plan-reviewer and code-reviewer both verify against this checklist before the task is marked complete.
- The smoke recipe assumes a real vault is available (`trade-agents` per Phase 3a dogfooding). If unavailable, the operator may substitute any registered vault with at least one indexed `type='summary'` page. The point of the smoke recipe is to verify the live LLM path works end-to-end — CI's mocked path proves the wiring, but the smoke proves the SDK integration.
- If any smoke fails on the operator's vault, debug per bead → fix in the originating bead → re-run smoke. Do NOT modify this bead's verification recipe to work around a real issue.
- The smoke recipe step numbers match TASK.md §7 1:1 — keep them aligned if either is edited.
- Once this bead passes, TASK 003 v2 is **DONE**. Update `docs/TASK.md` Status → `SHIPPED`; update `docs/ROADMAP.md` §P1 R-3 entry; archive `docs/TASK.md` → `docs/tasks/task-003-wiki-extract-concepts.md` (overwriting the v1 archive per `skill-archive-task` semantics; or appending a v2 suffix if the operator prefers).
