"""TASK 034 / R-2 — the four NEW inverse-closed typed-edge pairs (schema v7):
invalidated_by↔invalidates, activated_by↔activates, uses↔used-by, owns↔owned-by.

Same machinery as TASK 032: forward edges ride the per-page write; inverses are
auto-derived (global pass). Both directions are authorable (TASK 032 parity).
Plus a DRIFT GUARD: every ref_type in the code maps must be admitted by the SQL
CHECK enum (the three sources of truth cannot diverge).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import (
    _EDGE_KEY_TO_REF_TYPE,
    _INVERSE_REF_TYPE,
    reindex_full,
)
from scripts.wiki_index.sqlite_repository import SQLiteRepository

_SCHEMA = Path(__file__).resolve().parent.parent / "sql" / "wiki-index-v2.sql"


def _vault(tmp_path: Path, files: dict[str, str]) -> SQLiteRepository:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "WIKI_SCHEMA.md").write_text(
        '---\nvault_id: cvault\nschema_version: "2.0"\nlanguage: en\nlayout: cybos\n---\n',
        encoding="utf-8")
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    repo.register_vault(Vault(vault_id="cvault", name="cvault", root_path=root,
                              schema_version="2.0", registered_at=datetime(2026, 6, 15)))
    return repo


def _refs(repo: SQLiteRepository) -> set[tuple[str, str, str]]:
    return {(r["page_slug"], r["entity_slug"], r["ref_type"]) for r in
            repo._connect().execute(
                "SELECT page_slug, entity_slug, ref_type FROM page_entity_refs "
                "WHERE vault_id='cvault'").fetchall()}


@pytest.mark.parametrize("key,fwd,inv", [
    ("invalidated_by", "invalidated-by", "invalidates"),
    ("activated_by", "activated-by", "activates"),
    ("uses", "uses", "used-by"),
    ("owns", "owns", "owned-by"),
])
def test_new_edge_forward_and_auto_inverse(tmp_path: Path, key: str, fwd: str, inv: str) -> None:
    """Author `<key>: [[b]]` on page a → forward (a→b, fwd) + derived inverse (b→a, inv)."""
    repo = _vault(tmp_path, {
        "decisions/a.md": f"---\ntype: decision\ntitle: A\n{key}: [[b]]\n---\nbody\n",
        "incidents/b.md": "---\ntype: incident\ntitle: B\n---\nbody\n",
    })
    try:
        assert reindex_full(repo, "cvault")["skipped"] == []
        refs = _refs(repo)
        assert ("a", "b", fwd) in refs          # forward (authored)
        assert ("b", "a", inv) in refs          # inverse (auto-derived, on target)
    finally:
        repo.close()


def test_reverse_direction_is_authorable(tmp_path: Path) -> None:
    """TASK 032 parity: authoring the INVERSE key directly also converges. Author
    `invalidates: [[d]]` on an incident → (inc→d, invalidates) + (d→inc, invalidated-by)."""
    repo = _vault(tmp_path, {
        "incidents/inc.md": "---\ntype: incident\ntitle: Inc\ninvalidates: [[d]]\n---\nbody\n",
        "decisions/d.md": "---\ntype: decision\ntitle: D\n---\nbody\n",
    })
    try:
        reindex_full(repo, "cvault")
        refs = _refs(repo)
        assert ("inc", "d", "invalidates") in refs
        assert ("d", "inc", "invalidated-by") in refs
    finally:
        repo.close()


def test_uses_owns_agent_memory_edges(tmp_path: Path) -> None:
    """RFC-002: an agent `uses` a tool and `owns` a workflow → traversable both ways."""
    repo = _vault(tmp_path, {
        "agents/claude.md": "---\ntype: agent\ntitle: Claude\nuses: [[wiki-query]]\nowns: [[wiki-sync]]\nimplements: [[ocr]]\n---\nx\n",
        "tools/wiki-query.md": "---\ntype: tool\ntitle: WQ\n---\nx\n",
        "workflows/wiki-sync.md": "---\ntype: workflow\ntitle: WS\n---\nx\n",
        "capabilities/ocr.md": "---\ntype: capability\ntitle: OCR\n---\nx\n",
    })
    try:
        reindex_full(repo, "cvault")
        refs = _refs(repo)
        assert ("claude", "wiki-query", "uses") in refs
        assert ("wiki-query", "claude", "used-by") in refs
        assert ("claude", "wiki-sync", "owns") in refs
        assert ("wiki-sync", "claude", "owned-by") in refs
        # "which agents implement OCR?" = the inverse of implements, on the capability
        assert ("ocr", "claude", "implemented-by") in refs
    finally:
        repo.close()


def test_idempotent_second_full(tmp_path: Path) -> None:
    repo = _vault(tmp_path, {
        "decisions/d.md": "---\ntype: decision\ntitle: D\nactivated_by: [[e]]\n---\nbody\n",
        "events/e.md": "---\ntype: event\ntitle: E\n---\nbody\n",
    })
    try:
        reindex_full(repo, "cvault")
        first = _refs(repo)
        reindex_full(repo, "cvault")
        assert _refs(repo) == first
        assert ("d", "e", "activated-by") in first and ("e", "d", "activates") in first
    finally:
        repo.close()


def test_code_maps_subset_of_sql_check_enum(tmp_path: Path) -> None:
    """DRIFT GUARD: every ref_type the code can emit (forward map values + both
    sides of the inverse map) MUST be admitted by the SQL CHECK enum. Proven by
    inserting each into a fresh schema DB (no IntegrityError)."""
    code_ref_types = (
        set(_EDGE_KEY_TO_REF_TYPE.values())
        | set(_INVERSE_REF_TYPE.keys())
        | set(_INVERSE_REF_TYPE.values())
    )
    conn = sqlite3.connect(tmp_path / "drift.db")
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    conn.execute("PRAGMA foreign_keys = OFF")
    for i, rt in enumerate(sorted(code_ref_types)):
        # Each must be accepted by the CHECK (would raise IntegrityError otherwise).
        conn.execute(
            "INSERT INTO page_entity_refs (vault_id, page_slug, page_project, "
            "entity_slug, ref_type) VALUES ('v','p',?,'e',?)", (f"proj{i}", rt))
    stored = {r[0] for r in conn.execute(
        "SELECT DISTINCT ref_type FROM page_entity_refs").fetchall()}
    assert code_ref_types <= stored
