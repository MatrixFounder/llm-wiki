# TASK 045-02 — JSON output: file_path + obsidian_url (implementation GREEN)

## Goal
Implement the `file_path` and `obsidian_url` additions to the JSON results in
`scripts/wiki_skills/wiki_search.py` and make the 3 JSON test cases GREEN.

## Context
- Primary file to edit: `scripts/wiki_skills/wiki_search.py`
- Line numbers (may shift): results dict at lines ~212-217; `main()` at line 91
- Model: `scripts/wiki_index/models.py` — `Vault.root_path: Path`, `Page.file_path: str`
- DAL method: `repo.get_vault(vault_id: str) -> Vault | None` (defined in repository.py:94)
- `GLOBAL_VAULT_SENTINEL` = `"_global_"` (from `scripts.wiki_index.layout`)
- Tests to make GREEN: first 3 in `tests/test_wiki_search_obsidian_links.py`

## Steps

### Step 1: Add imports to `wiki_search.py`

Add at the top of the file (after existing imports):
```python
from urllib.parse import quote as _url_quote
```

Check if `Vault` is already imported (it may come in via the `make_repo` factory or
`PageHit` — if not, add):
```python
from scripts.wiki_index.models import Vault
```

### Step 2: Add the `_obsidian_url` helper function

Add before `main()`:
```python
def _obsidian_url(vault: Vault | None, file_path: str) -> str | None:
    """Build an obsidian://open URI for a search hit, or None if vault is unknown."""
    if vault is None:
        return None
    vault_name = _url_quote(vault.root_path.name, safe="")
    file_enc = _url_quote(file_path, safe="/-_.~")
    return f"obsidian://open?vault={vault_name}&file={file_enc}"
```

### Step 3: Build vault_cache inside `main()`

In `main()`, right before the `results = [...]` list comprehension (currently around
line 212), insert:
```python
# R-3: look up each unique vault once (cache avoids N DB calls for N hits)
vault_cache: dict[str, Vault | None] = {
    vid: (None if vid == GLOBAL_VAULT_SENTINEL else repo.get_vault(vid))
    for vid in {h.page.vault_id for h in hits}
}
```

### Step 4: Extend the `results` dict comprehension

Change the existing dict from:
```python
results = [{
    "vault_id": h.page.vault_id, "slug": h.page.slug,
    "project": h.page.project, "type": h.page.type,
    "title": h.page.title, "bm25_score": h.bm25_score,
    "snippet": h.snippet,
} for h in hits]
```
to:
```python
results = [{
    "vault_id": h.page.vault_id, "slug": h.page.slug,
    "project": h.page.project, "type": h.page.type,
    "title": h.page.title, "bm25_score": h.bm25_score,
    "snippet": h.snippet,
    "file_path": h.page.file_path,
    "obsidian_url": _obsidian_url(
        vault_cache.get(h.page.vault_id), h.page.file_path
    ),
} for h in hits]
```

### Step 5: Fill in the 3 JSON test functions

In `tests/test_wiki_search_obsidian_links.py`, replace the 3 JSON stub functions with
real implementations. Pattern to follow (use real DB + reindex like the existing
wiki-search tests):

```python
"""TASK 045 — wiki-search: file_path + obsidian_url in CLI output."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.wiki_index.models import Vault, Page, PageHit
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills import wiki_search

VAULT_ID = "test-vault"


@pytest.fixture
def vault_db(tmp_path: Path) -> tuple[Path, Path]:
    """Returns (vault_root, db_path). Vault has one concept page."""
    vault = tmp_path / "MyVault"
    (vault / "_concepts").mkdir(parents=True)
    (vault / "_concepts" / "foo.md").write_text(
        "---\ntype: concept\nslug: foo\ntitle: Foo\n"
        "date: 2026-01-01\ntags: [concept]\n---\n\nFoo content.\n",
        encoding="utf-8",
    )
    db = tmp_path / "g.db"
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id=VAULT_ID, name="My Vault", root_path=vault,
        schema_version="2.0", registered_at=datetime(2026, 1, 1),
    ))
    reindex_full(repo, VAULT_ID)
    repo.close()
    return vault, db


def test_search_json_includes_file_path_and_obsidian_url(
    vault_db: tuple[Path, Path], capsys: pytest.CaptureFixture[str],
) -> None:
    """JSON hit has file_path and correct obsidian_url when vault is known (R-1, R-2)."""
    vault_root, db = vault_db
    rc = wiki_search.main(["foo", "--vaults", VAULT_ID, "--db-path", str(db)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["count"] >= 1
    hit = next(h for h in out["hits"] if h["slug"] == "foo")
    assert hit["file_path"] == "_concepts/foo.md"
    assert hit["obsidian_url"] == (
        f"obsidian://open?vault=MyVault&file=_concepts%2Ffoo.md"
    )


def test_search_json_obsidian_url_null_when_vault_unknown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """obsidian_url is null when vault registry returns None (R-2d)."""
    # Build a DB with one hit but NO vault registered (stale registry simulation).
    vault = tmp_path / "OldVault"
    (vault / "_concepts").mkdir(parents=True)
    (vault / "_concepts" / "bar.md").write_text(
        "---\ntype: concept\nslug: bar\ntitle: Bar\n"
        "date: 2026-01-01\ntags: [concept]\n---\n\nBar content.\n",
        encoding="utf-8",
    )
    db = tmp_path / "g.db"
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id="old-vault", name="Old Vault", root_path=vault,
        schema_version="2.0", registered_at=datetime(2026, 1, 1),
    ))
    reindex_full(repo, "old-vault")
    # Now remove the vault from the registry to simulate stale DB
    repo._conn.execute("DELETE FROM vaults WHERE vault_id = 'old-vault'")
    repo._conn.commit()
    repo.close()

    rc = wiki_search.main(["bar", "--vaults", "old-vault", "--db-path", str(db)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    hit = next(h for h in out["hits"] if h["slug"] == "bar")
    assert hit["file_path"] == "_concepts/bar.md"
    assert hit["obsidian_url"] is None


def test_search_json_vault_cache_called_once_per_unique_vault(
    vault_db: tuple[Path, Path], capsys: pytest.CaptureFixture[str],
) -> None:
    """get_vault called once per unique vault_id, not once per hit (R-3)."""
    vault_root, db = vault_db
    # Add a second concept page so we have ≥2 hits from the same vault
    (vault_root / "_concepts" / "baz.md").write_text(
        "---\ntype: concept\nslug: baz\ntitle: Baz\n"
        "date: 2026-01-01\ntags: [concept]\n---\n\nBaz content foo.\n",
        encoding="utf-8",
    )
    from scripts.wiki_index.sqlite_repository import SQLiteRepository as _R
    repo2 = _R(db)
    reindex_full(repo2, VAULT_ID)
    repo2.close()

    # Patch get_vault at the module level to count calls
    from scripts.wiki_index import sqlite_repository
    original_get_vault = sqlite_repository.SQLiteRepository.get_vault
    call_count = {"n": 0}

    def counting_get_vault(self, vault_id: str):  # type: ignore[override]
        call_count["n"] += 1
        return original_get_vault(self, vault_id)

    with patch.object(sqlite_repository.SQLiteRepository, "get_vault", counting_get_vault):
        rc = wiki_search.main(["foo", "--vaults", VAULT_ID, "--db-path", str(db)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    # Multiple hits from same vault, but get_vault called exactly once
    assert out["count"] >= 1
    assert call_count["n"] == 1, (
        f"Expected 1 get_vault call (cache), got {call_count['n']}"
    )
```

### Step 6: Verify gate

```bash
source .venv/bin/activate
pytest tests/test_wiki_search_obsidian_links.py::test_search_json_includes_file_path_and_obsidian_url \
       tests/test_wiki_search_obsidian_links.py::test_search_json_obsidian_url_null_when_vault_unknown \
       tests/test_wiki_search_obsidian_links.py::test_search_json_vault_cache_called_once_per_unique_vault \
       -v
# Expected: 3 PASSED
pytest tests/ -x -q  # no regressions
```

## Verification
```bash
source .venv/bin/activate
pytest tests/test_wiki_search_obsidian_links.py -k "json" -v
# 3 PASSED
pytest tests/ -q --tb=short
# 0 failures
grep "import anthropic" scripts/wiki_skills/wiki_search.py || echo "clean"
```
