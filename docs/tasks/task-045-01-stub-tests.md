# TASK 045-01 — Stub tests RED (branch + test file skeleton)

## Goal
Create the git branch and the test file with all 5 test functions as stubs so the test
suite collects them (SKIP or documented-fail) without import errors.

## Context
- Primary file to create: `tests/test_wiki_search_obsidian_links.py`
- Reference test style: `tests/test_wiki_search_alias_expansion.py` (uses
  `SQLiteRepository` + `reindex_full` + `wiki_search.main(argv)` pattern)
- Task spec: `docs/TASK.md` §5 (Acceptance — 5 test scenarios)

## Steps

1. **Create branch:**
   ```bash
   git checkout -b task-045-wiki-search-obsidian-links
   ```

2. **Create `tests/test_wiki_search_obsidian_links.py`** with these 5 skeleton functions
   (mark each with `pytest.mark.skip(reason="stub — implement in task-045-02/03")`):

   ```python
   """TASK 045 — wiki-search: file_path + obsidian_url in CLI output (R-1..R-6, R-8)."""
   from __future__ import annotations
   import pytest

   @pytest.mark.skip(reason="stub")
   def test_search_json_includes_file_path_and_obsidian_url() -> None:
       """JSON hit has file_path and correct obsidian_url when vault is known."""
       ...

   @pytest.mark.skip(reason="stub")
   def test_search_json_obsidian_url_null_when_vault_unknown() -> None:
       """obsidian_url is null (None in JSON) when repo.get_vault returns None."""
       ...

   @pytest.mark.skip(reason="stub")
   def test_search_json_vault_cache_called_once_per_unique_vault() -> None:
       """get_vault called exactly once per unique vault_id, not once per hit."""
       ...

   @pytest.mark.skip(reason="stub")
   def test_search_markdown_tty_osc8_link() -> None:
       """--format markdown + TTY → OSC 8 escape sequence present in output."""
       ...

   @pytest.mark.skip(reason="stub")
   def test_search_markdown_pipe_plain_url() -> None:
       """--format markdown + non-TTY → plain URL appended, no ANSI escapes."""
       ...
   ```

3. **Verify gate:**
   ```bash
   source .venv/bin/activate && pytest tests/test_wiki_search_obsidian_links.py -v
   ```
   Expected: 5 tests collected, all SKIPPED (not ERROR).

## Verification
```bash
source .venv/bin/activate
pytest tests/test_wiki_search_obsidian_links.py -v
# Expected: 5 SKIPPED (or 5 PASSED on skip)
```
