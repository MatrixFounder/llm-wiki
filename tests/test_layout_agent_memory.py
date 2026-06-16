"""TASK 034 / R-3 — agent-memory classification via the cybos layout (config only).

`agent`/`tool`/`workflow`/`capability`/`execution`/`pattern` route onto an existing
db_type bucket + a filterable tag (TASK 031 pattern). No UnmappedTypeError; the
typed-class tag is matchable via `--tag` (TASK 033). Zero Python, zero DDL.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository

VAULT_ID = "amvault"

_FILES = {
    "agents/claude.md": "---\ntype: agent\ntitle: Claude\n---\nx\n",
    "tools/wiki-query.md": "---\ntype: tool\ntitle: WQ\n---\nx\n",
    "workflows/wiki-sync.md": "---\ntype: workflow\ntitle: WS\n---\nx\n",
    "capabilities/ocr.md": "---\ntype: capability\ntitle: OCR\n---\nx\n",
    "executions/run-1.md": "---\ntype: execution\ntitle: Run 1\nstatus: failed\n---\nx\n",
    "patterns/p-1.md": "---\ntype: pattern\ntitle: P1\n---\nx\n",
}

# raw class -> expected db_type (must match cybos.yaml type_mapping)
_EXPECTED_DB_TYPE = {
    "claude": "concept", "wiki-query": "concept", "wiki-sync": "brief",
    "ocr": "concept", "run-1": "summary", "p-1": "research",
}


def _build(tmp_path: Path) -> SQLiteRepository:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "WIKI_SCHEMA.md").write_text(
        f'---\nvault_id: {VAULT_ID}\nschema_version: "2.0"\nlanguage: en\nlayout: cybos\n---\n',
        encoding="utf-8")
    for rel, content in _FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    repo.register_vault(Vault(vault_id=VAULT_ID, name=VAULT_ID, root_path=root,
                              schema_version="2.0", registered_at=datetime(2026, 6, 15)))
    return repo


def test_all_agent_memory_classes_indexed_no_skips(tmp_path: Path) -> None:
    repo = _build(tmp_path)
    try:
        res = reindex_full(repo, VAULT_ID)
        assert res["skipped"] == []          # no UnmappedTypeError
        assert res["pages"] == len(_FILES)
    finally:
        repo.close()


def test_db_type_routing(tmp_path: Path) -> None:
    repo = _build(tmp_path)
    try:
        reindex_full(repo, VAULT_ID)
        rows = dict(repo._connect().execute(
            "SELECT slug, type FROM pages WHERE vault_id=?", (VAULT_ID,)).fetchall())
        assert rows == _EXPECTED_DB_TYPE
    finally:
        repo.close()


@pytest.mark.parametrize("tag,slug", [
    ("agent", "claude"), ("tool", "wiki-query"), ("workflow", "wiki-sync"),
    ("capability", "ocr"), ("execution", "run-1"), ("pattern", "p-1"),
])
def test_typed_class_tag_is_filterable(tmp_path: Path, tag: str, slug: str) -> None:
    """Each class routes its tag into tags[] → `--tag <class>` (TASK 033) finds exactly it."""
    repo = _build(tmp_path)
    try:
        reindex_full(repo, VAULT_ID)
        hits = repo.search_pages(None, vaults=[VAULT_ID], where_fields=[("tags", tag)], limit=100)
        assert {h.page.slug for h in hits} == {slug}
    finally:
        repo.close()
