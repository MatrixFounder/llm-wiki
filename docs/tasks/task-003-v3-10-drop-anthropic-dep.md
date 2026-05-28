# Task 003-v3-10: remove `anthropic>=0.34.0` from `requirements.txt`

## Meta

- **Bead ID**: `task-003-v3-10-drop-anthropic-dep`
- **Slug**: `drop-anthropic-dep`
- **Maps to**: Issue **I-V3.5**; RTM row **R-30**; Decision-17.
- **Depends on**: task-003-v3-06 (no anthropic import in scripts/), task-003-v3-11 (no anthropic mock in tests/).
- **Estimated time**: 0.1 day
- **Priority**: Low (after the dust settles).

## Use Case Connection

- Removes the LLM SDK Python dependency entirely. After this bead, `pip install -r requirements.txt` does not pull the `anthropic` package.

## Task Goal

1. Edit `requirements.txt` and remove the `anthropic>=0.34.0` line.
2. Run `pip uninstall anthropic -y` in the venv to remove the installed package.
3. Run `pip install -r requirements.txt` to confirm no transitive pull.
4. Run `python -c "import anthropic"` and confirm it raises `ModuleNotFoundError`.
5. Run `pytest tests/ -q` to confirm no test depends on the package being installed.

## Stub-First Plan

n/a (1-line dep change).

## Changes Description

### Edited files

- `requirements.txt`: delete the `anthropic>=0.34.0` line.

## Component Integration

- After this bead, the only Python deps are the ones that survived from v2 (`python-frontmatter`, etc.).
- `bin/wiki-extract-concepts` continues to work via the existing pass-through.

## Files Touched

- `requirements.txt`

## Acceptance Criteria

- [ ] **R-30 (Decision-17)**: `grep anthropic requirements.txt` → 0 matches.
- [ ] After `pip uninstall anthropic -y; pip install -r requirements.txt`, `python -c "import anthropic"` raises `ModuleNotFoundError`.
- [ ] `pytest tests/ -q` still green (no test imports anthropic).
- [ ] **Risk R-8 mitigation**: dogfood smoke (003-v3-15) re-confirms via `env | grep -i anthropic` empty AND `python -c "import anthropic"` raises ModuleNotFoundError.

## Verification

```bash
source .venv/bin/activate

# requirements.txt clean
grep anthropic requirements.txt && echo "FAIL" || echo "OK: dep removed"

# Uninstall + reinstall
pip uninstall anthropic -y
pip install -r requirements.txt

# Import fails
python -c "import anthropic" 2>&1 | grep -q "ModuleNotFoundError" && echo "OK: import fails"

# Tests still green
pytest tests/ -q
# expect: no anthropic ImportError; same pass count as immediately-prior bead
```

## Rollback

`echo "anthropic>=0.34.0" >> requirements.txt && pip install -r requirements.txt`.

## Notes

- This is the smallest bead in the task but is gated on 003-v3-06 (code deletion) and 003-v3-11 (test refactor) — both must land before this is safe.
- The `pip uninstall` step is not strictly necessary if the user is okay with a stale package in their venv that nothing imports. The acceptance criterion requires the uninstall for dogfood-smoke alignment (003-v3-15 step #13 asserts `import anthropic` raises).
