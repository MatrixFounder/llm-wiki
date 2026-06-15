"""TASK 032-03 (R-032-4, ADR-004 D-DAL) — typed-edge DAL reads."""

from __future__ import annotations

from pathlib import Path

from tests._graph_fixtures import build_graph_vault


def test_get_backlinks_kind_filter(tmp_path: Path) -> None:
    repo, _ = build_graph_vault(tmp_path)
    try:
        # inbound to req-1, filtered to 'implements' → dec-1 implements req-1
        bl = repo.get_backlinks("gvault", "req-1", ref_type="implements")
        assert {r.page_slug for r in bl} == {"dec-1"}
        # default (no filter) returns all kinds inbound to dec-1 (incl. derived inverses)
        allk = {r.ref_type for r in repo.get_backlinks("gvault", "dec-1")}
        assert {"supersedes", "implements", "caused-by"} <= allk  # forwards pointing AT dec-1
    finally:
        repo.close()


def test_refs_from_outbound(tmp_path: Path) -> None:
    repo, _ = build_graph_vault(tmp_path)
    try:
        out = repo.refs_from("gvault", "dec-1", "_vault_", ref_type="supersedes")
        assert {r.entity_slug for r in out} == {"dec-0"}  # dec-1 supersedes dec-0 (forward)
        # dec-1 also carries DERIVED inverses (superseded-by from dec-2; implemented-by from task-1)
        inv = {r.ref_type for r in repo.refs_from("gvault", "dec-1", "_vault_")}
        assert {"implements", "supersedes", "superseded-by", "implemented-by", "causes"} <= inv
    finally:
        repo.close()


def test_neighbors_both_directions(tmp_path: Path) -> None:
    repo, _ = build_graph_vault(tmp_path)
    try:
        nb = repo.neighbors("gvault", "dec-1", "_vault_", direction="both")
        slugs = {r.entity_slug for r in nb} | {r.page_slug for r in nb}
        assert {"req-1", "dec-0", "dec-2", "task-1", "inc-1", "dec-1"} <= slugs
    finally:
        repo.close()


def test_edge_chain_multi_hop(tmp_path: Path) -> None:
    repo, _ = build_graph_vault(tmp_path)
    try:
        # supersession lineage: dec-2 → dec-1 → dec-0
        chain = repo.edge_chain("gvault", "dec-2", "supersedes", direction="out", max_depth=8)
        assert chain == [("dec-1", 1), ("dec-0", 2)]
    finally:
        repo.close()


def test_edge_chain_cycle_terminates(tmp_path: Path) -> None:
    repo, _ = build_graph_vault(tmp_path)
    try:
        # f1 -[related]- f2 -[related]- f1 (symmetric cycle): must terminate
        chain = repo.edge_chain("gvault", "f1", "related", direction="out", max_depth=50)
        assert ("f2", 1) in chain
        assert all(d <= 2 for _, d in chain)  # cycle does not run away
    finally:
        repo.close()
