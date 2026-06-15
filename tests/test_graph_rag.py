"""TASK 032-05 (R-032-6, ADR-004 D5) — graph-aware RAG: wiki-query --follow-edges
deterministically expands the FTS hit set along typed edges."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills.wiki_query import _build_parser, _question_hash, _retrieve


def _rag_vault(tmp_path: Path) -> SQLiteRepository:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "WIKI_SCHEMA.md").write_text(
        '---\nvault_id: rvault\nschema_version: "2.0"\nlanguage: en\nlayout: cybos\n---\n',
        encoding="utf-8")
    (root / "decisions").mkdir()
    (root / "incidents").mkdir()
    (root / "decisions" / "rabbitmq.md").write_text(
        "---\ntype: decision\ntitle: Use RabbitMQ\ncauses: [[outage]]\n---\n"
        "Adopt RabbitMQ for async messaging.\n", encoding="utf-8")
    (root / "incidents" / "outage.md").write_text(
        "---\ntype: incident\ntitle: Queue outage\n---\nThe broker queue overflowed badly.\n",
        encoding="utf-8")
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    repo.register_vault(Vault(vault_id="rvault", name="rvault", root_path=root,
                              schema_version="2.0", registered_at=datetime(2026, 6, 15)))
    assert reindex_full(repo, "rvault")["skipped"] == []
    return repo


def _args(follow: bool):
    argv = ["prepare", "q", "--vault", "rvault", "--limit", "10"]
    if follow:
        argv += ["--follow-edges"]
    return _build_parser().parse_args(argv)


def test_follow_edges_pulls_caused_neighbor(tmp_path: Path) -> None:
    repo = _rag_vault(tmp_path)
    try:
        base = _retrieve(repo, "RabbitMQ", _args(follow=False))
        assert {h.page.slug for h in base} == {"rabbitmq"}  # FTS hit only
        expanded = _retrieve(repo, "RabbitMQ", _args(follow=True))
        slugs = {h.page.slug for h in expanded}
        assert "rabbitmq" in slugs and "outage" in slugs   # edge-pulled the caused incident
        pulled = [h for h in expanded if h.page.slug == "outage"][0]
        assert pulled.via_edge == {"from": "rabbitmq", "ref_type": "causes"}
    finally:
        repo.close()


def test_follow_edges_deterministic_hash(tmp_path: Path) -> None:
    """C1: the expansion is stable → prepare/apply re-derive the same question_hash."""
    repo = _rag_vault(tmp_path)
    try:
        h1 = _question_hash("RabbitMQ", _retrieve(repo, "RabbitMQ", _args(follow=True)))
        h2 = _question_hash("RabbitMQ", _retrieve(repo, "RabbitMQ", _args(follow=True)))
        assert h1 == h2
        # and the graph-expanded hash differs from the plain one (expansion took effect)
        h_plain = _question_hash("RabbitMQ", _retrieve(repo, "RabbitMQ", _args(follow=False)))
        assert h1 != h_plain
    finally:
        repo.close()


def test_default_off_no_via_edge(tmp_path: Path) -> None:
    repo = _rag_vault(tmp_path)
    try:
        hits = _retrieve(repo, "RabbitMQ", _args(follow=False))
        assert all(getattr(h, "via_edge", None) is None for h in hits)
    finally:
        repo.close()


def test_follow_edges_capped_and_deterministic(tmp_path: Path) -> None:
    """PERF-032-1: a hub page with > _MAX_EDGE_PULLED typed-edge neighbors yields a
    pulled set capped at _MAX_EDGE_PULLED, and the sorted truncation is deterministic
    (so prepare/apply still agree on question_hash)."""
    from scripts.wiki_skills.wiki_query import _MAX_EDGE_PULLED, _follow_edges
    root = tmp_path / "vault"
    root.mkdir()
    (root / "WIKI_SCHEMA.md").write_text(
        '---\nvault_id: hvault\nschema_version: "2.0"\nlanguage: en\nlayout: cybos\n---\n',
        encoding="utf-8")
    (root / "decisions").mkdir()
    (root / "incidents").mkdir()
    n = _MAX_EDGE_PULLED + 10
    causes = "\n".join(f"  - '[[inc-{i:03d}]]'" for i in range(n))
    (root / "decisions" / "hub.md").write_text(
        f"---\ntype: decision\ntitle: Hub\ncauses:\n{causes}\n---\nHub decision.\n",
        encoding="utf-8")
    for i in range(n):
        (root / "incidents" / f"inc-{i:03d}.md").write_text(
            f"---\ntype: incident\ntitle: Inc {i}\n---\nbody {i}\n", encoding="utf-8")
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    repo.register_vault(Vault(vault_id="hvault", name="hvault", root_path=root,
                              schema_version="2.0", registered_at=datetime(2026, 6, 15)))
    assert reindex_full(repo, "hvault")["skipped"] == []
    try:
        hub_hits = [h for h in _retrieve(repo, "Hub", _build_parser().parse_args(
            ["prepare", "q", "--vault", "hvault", "--limit", "10"]))
            if h.page.slug == "hub"]
        assert hub_hits
        pulled1 = _follow_edges(repo, hub_hits, 1)
        pulled2 = _follow_edges(repo, hub_hits, 1)
        assert len(pulled1) == _MAX_EDGE_PULLED                               # capped
        assert [h.page.slug for h in pulled1] == [h.page.slug for h in pulled2]  # stable
    finally:
        repo.close()
