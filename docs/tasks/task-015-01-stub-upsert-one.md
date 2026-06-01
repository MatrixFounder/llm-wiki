# task-015-01 — Stub `upsert_one` in `wiki_index_upsert.py`

**Parent:** TASK 015. **Depends on:** 015-00. **RTM:** R-015-1 (partial).

## Goal
Add the `upsert_one` function signature to `wiki_index_upsert.py` with a stub body
and write the RED test that will drive its implementation in 015-02.

## Design (locked — ARCHITECTURE.md functional-architecture §Concept Extractor + wiki-index-upsert)

```python
def upsert_one(
    vault_id: str,
    src: Path,
    vault_root: Path,
    repo: Any,
) -> dict[str, Any]:
    """Programmatic entry-point for upserting a single page into the index.

    Accepts an already-open repo (caller owns lifecycle — does NOT close it).
    Returns the envelope dict (does NOT call emit()).
    main() delegates to this function.
    """
    raise NotImplementedError  # stub — implemented in 015-02
```

## Steps

1. In `scripts/wiki_skills/wiki_index_upsert.py`:
   - Add import `from typing import Any` (already present likely; verify).
   - Add `upsert_one(vault_id, src, vault_root, repo) → dict[str, Any]` after
     `_find_vault_root`, before `main()`. Stub body: `raise NotImplementedError`.
   - `main()` is **unchanged** (still works as before).

2. In `tests/test_perf_hardening.py`, add a RED test:
   ```python
   import pytest
   from pathlib import Path
   from unittest.mock import MagicMock
   from scripts.wiki_skills.wiki_index_upsert import upsert_one

   def test_upsert_one_returns_envelope(tmp_path: Path) -> None:
       """upsert_one returns a dict with an 'action' key (RED until 015-02)."""
       repo = MagicMock()
       src = tmp_path / "test.md"
       src.write_text("---\ntitle: Test\n---\nBody.\n")
       result = upsert_one("test-vault", src, tmp_path, repo)
       assert isinstance(result, dict)
       assert "action" in result
   ```
   This test is RED (raises `NotImplementedError`).

3. Verify: `pytest tests/test_perf_hardening.py::test_upsert_one_returns_envelope -x`
   → FAILS with `NotImplementedError`. ✓ RED confirmed.

4. `pytest -q` full suite still ≥ 852 (the new test fails, but that's expected — count only
   UNEXPECTED failures as regressions).
   `mypy --strict scripts/` — 0 errors.

## Acceptance
- ✅ `upsert_one` is importable from `wiki_index_upsert`.
- ✅ `test_upsert_one_returns_envelope` is RED (NotImplementedError).
- ✅ Existing `test_wiki_index_upsert.py` tests still pass.
- ✅ mypy strict clean.

## Files
- `scripts/wiki_skills/wiki_index_upsert.py` (add `upsert_one` stub)
- `tests/test_perf_hardening.py` (add RED test)
