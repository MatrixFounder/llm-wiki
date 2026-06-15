"""TASK 032-01 (R-032-2) — `_edge_refs` forward edge extraction (ADR-004 D2/D3).

Forward-only: the authored edge keys → PageRefs with ref_type per the key→ref_type
map, target slugified like body mentions. Inverse derivation is 032-02. Karpathy
byte-identity is unaffected (no edge keys → []).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import _edge_refs, _EDGE_KEY_TO_REF_TYPE, reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository


def _edges(fm: dict, slug_strategy: str = "identity"):
    skipped: list[dict] = []
    refs = _edge_refs(fm, "v", "src", "_vault_", slug_strategy, skipped)
    return {(r.entity_slug, r.ref_type) for r in refs}, skipped


def test_key_to_ref_type_map_complete() -> None:
    assert _EDGE_KEY_TO_REF_TYPE == {
        "implements": "implements", "implemented_by": "implemented-by",
        "supersedes": "supersedes", "superseded_by": "superseded-by",
        "causes": "causes", "caused_by": "caused-by",
        "relates_to": "related",
    }


def test_scalar_and_list_forms() -> None:
    got, sk = _edges({"implements": "[[req-x]]", "caused_by": ["inc-a", "inc-b"]})
    assert got == {("req-x", "implements"), ("inc-a", "caused-by"), ("inc-b", "caused-by")}
    assert sk == []


def test_relates_to_maps_to_related_and_superseded_by_authorable() -> None:
    got, _ = _edges({"relates_to": "[[foo]]", "superseded_by": "bar"})
    assert got == {("foo", "related"), ("bar", "superseded-by")}


def test_wikilink_strip_and_slug_strategy() -> None:
    # [[Title|alias]] → "Title" → transliterate slug
    got, _ = _edges({"implements": "[[Заметка Тест]]"}, slug_strategy="transliterate")
    assert ("zametka-test", "implements") in got


def test_self_loop_skipped_and_dedup() -> None:
    got, sk = _edges({"implements": ["src", "req-x", "req-x"]})  # 'src' == page_slug
    assert got == {("req-x", "implements")}  # self-loop dropped, dup collapsed
    # vdd-multi LOW: the self-loop drop is now observable in `skipped` (not silent)
    assert any("self-referential" in s["reason"] for s in sk)


def test_yaml_nested_list_wikilink_flattened() -> None:
    """YAML parses unquoted `implements: [[req-x]]` as a NESTED list [["req-x"]];
    flatten one level so the natural Obsidian wikilink form resolves (and [[a],[b]]
    / [a, b] too)."""
    got, sk = _edges({"implements": [["req-x"]], "caused_by": [["a"], ["b"]]})
    assert got == {("req-x", "implements"), ("a", "caused-by"), ("b", "caused-by")}
    assert sk == []


def test_no_edge_keys_yields_nothing() -> None:
    got, sk = _edges({"title": "X", "tags": ["a"], "cites": ["p/q"]})
    assert got == set() and sk == []


def test_e2e_forward_edges_indexed(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "WIKI_SCHEMA.md").write_text(
        '---\nvault_id: cvault\nschema_version: "2.0"\nlanguage: en\nlayout: cybos\n---\n',
        encoding="utf-8")
    (root / "decisions").mkdir()
    (root / "decisions" / "use-rabbitmq.md").write_text(
        "---\ntype: decision\ntitle: Use RabbitMQ\nimplements: [[req-throughput]]\n"
        "caused_by: inc-queue-overflow\n---\n\nbody\n", encoding="utf-8")
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    repo.register_vault(Vault(vault_id="cvault", name="cvault", root_path=root,
                              schema_version="2.0", registered_at=datetime(2026, 6, 15)))
    try:
        res = reindex_full(repo, "cvault")
        assert res["skipped"] == []
        rows = {(r["entity_slug"], r["ref_type"]) for r in repo._connect().execute(
            "SELECT entity_slug, ref_type FROM page_entity_refs "
            "WHERE vault_id='cvault' AND page_slug='use-rabbitmq'").fetchall()}
        assert ("req-throughput", "implements") in rows
        assert ("inc-queue-overflow", "caused-by") in rows
    finally:
        repo.close()
