# TASK 045-05 — Final validation: mypy + full test suite

## Goal
Confirm all quality gates are green before requesting VDD reviewer pass.

## Context
- All implementation done in tasks 045-01 through 045-04.
- Python venv: `.venv/` (activated via `source .venv/bin/activate`).
- mypy target: `scripts/wiki_skills/wiki_search.py` (the only modified Python file).

## Steps

### Step 1: mypy strict check

```bash
source .venv/bin/activate
mypy --strict scripts/wiki_skills/wiki_search.py
```
Expected: `Success: no issues found in 1 source file`

If mypy fails:
- Missing `Vault` type annotation → ensure `from scripts.wiki_index.models import Vault`
  is at the top-level import (not inside a function).
- `vault_cache` type → must be declared as `dict[str, Vault | None]`.
- `obsidian_url` return type → `_obsidian_url` must return `str | None`.
- `obs_url: str | None = r["obsidian_url"]` in the markdown block → may need a cast
  if mypy doesn't infer from the dict type; use `cast(str | None, r["obsidian_url"])`.

### Step 2: Full test suite

```bash
source .venv/bin/activate
pytest tests/ -q --tb=short
```
Expected: all tests pass (including 5 new TASK 045 tests, 0 failures).

### Step 3: No anthropic import gate

```bash
grep "import anthropic" scripts/wiki_skills/wiki_search.py
```
Expected: no output (empty match).

### Step 4: Smoke check with real DB (if available)

```bash
source .venv/bin/activate
# Use any registered vault DB
wiki-search "test" --format json 2>/dev/null | python3 -c "
import json,sys
data = json.load(sys.stdin)
hits = data.get('hits', [])
if hits:
    h = hits[0]
    print('file_path:', h.get('file_path', 'MISSING'))
    print('obsidian_url:', h.get('obsidian_url', 'MISSING'))
else:
    print('0 hits — keys present check skipped')
"
```

### Step 5: Additive-only check (manual diff review)

Review the git diff for `scripts/wiki_skills/wiki_search.py`:
- Only additions: `_url_quote` import, `Vault` import, `_obsidian_url()` helper,
  `vault_cache` dict, two new keys in results dict, suffix logic in markdown block.
- No removals/renames of existing keys in the results dict.
- No changes to error envelopes, argparse, or exit-code logic.

## Verification
All 5 gates pass:
1. `mypy --strict scripts/wiki_skills/wiki_search.py` → `Success`
2. `pytest tests/` → 0 failures
3. `grep "import anthropic" scripts/wiki_skills/wiki_search.py` → empty
4. Smoke check confirms `file_path` + `obsidian_url` in output
5. Diff is additive-only

**When all pass:** mark for VDD review (`code-reviewer` + `critic-logic`).
