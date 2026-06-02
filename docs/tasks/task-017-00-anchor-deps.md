# task-017-00 — Anchor + dependencies (`regex`, `types-regex`)

**Parent:** TASK 017. **Depends on:** — (first bead). **RTM:** NF3, NF6.

## Goal
Establish the no-regression baseline and add the one new dependency the ReDoS guard needs,
before any code change.

## Steps
1. Add to `requirements.txt`: `regex>=2024.0` (runtime) and `types-regex` (dev — after the
   existing `types-jsonschema`). Keep the existing pins.
2. `source .venv/bin/activate && pip install -r requirements.txt` (regex already proven to
   install as `regex-2026.5.9`).
3. Capture baseline: `pytest -q` (expect **879 passed, 4 skipped**) + `mypy --strict scripts/`
   (expect clean, 69 files). Record both in the bead log.
4. Create `tests/test_task017_hardening.py` with one smoke test: `import regex` and
   `import scripts.wiki_index.layout_config` succeed.

## Verification
- `pytest -q tests/test_task017_hardening.py` GREEN (1 test).
- Full `pytest -q` ≥ 880 (baseline + 1); `mypy --strict scripts/` clean (the bare `import
  regex` in the test must not trip strict — `types-regex` present).
