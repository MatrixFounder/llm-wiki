"""TASK 005-02 — reindex_full reads is_candidate from Class A frontmatter (R-4.1).

Before TASK 005, reindex_full omitted is_candidate from its INSERT → schema
default 0, silently confirming every candidate on a full rebuild. These tests
pin the round-trip: a candidate page survives `wiki-reindex --full` as a
candidate; an absent key (pre-005 vaults) and an explicit `false` both map to
confirmed.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import _coerce_is_candidate, reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository


def _concept_page(vault: Path, slug: str, *, is_candidate: Any) -> None:
    d = vault / "_concepts"
    d.mkdir(parents=True, exist_ok=True)
    cand_line = "" if is_candidate is None else f"is_candidate: {is_candidate}\n"
    (d / f"{slug}.md").write_text(
        f"---\ntype: concept\nslug: {slug}\nname: {slug.title()}\n"
        f"title: {slug.title()}\ndate: 2026-05-29\ntags: [concept]\n"
        f"{cand_line}---\n\n# {slug.title()}\n\nBody about {slug}.\n",
        encoding="utf-8",
    )


def _reindexed_is_candidate(tmp_path: Path, vault: Path) -> dict[str, int]:
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id="test-vault", name="v", root_path=vault,
        schema_version="3.0", registered_at=datetime(2026, 5, 29),
    ))
    reindex_full(repo, "test-vault")
    rows = {
        r["slug"]: r["is_candidate"]
        for r in repo._connect().execute(
            "SELECT slug, is_candidate FROM entities WHERE vault_id = 'test-vault'"
        ).fetchall()
    }
    repo.close()
    return rows


def test_e2e_01_candidate_true_survives_reindex(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _concept_page(vault, "foo", is_candidate="true")
    assert _reindexed_is_candidate(tmp_path, vault)["foo"] == 1


def test_e2e_02_absent_key_is_confirmed(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _concept_page(vault, "bar", is_candidate=None)
    assert _reindexed_is_candidate(tmp_path, vault)["bar"] == 0


def test_e2e_03_candidate_false_is_confirmed(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _concept_page(vault, "baz", is_candidate="false")
    assert _reindexed_is_candidate(tmp_path, vault)["baz"] == 0


@pytest.mark.parametrize(
    "val,expected",
    [
        (True, 1), (False, 0), (1, 1), (0, 0),
        ("true", 1), ("True", 1), ("1", 1), ("yes", 1), ("on", 1),
        ("false", 0), ("0", 0), ("", 0), ("nonsense", 0),
    ],
)
def test_unit_coerce_is_candidate(val: Any, expected: int) -> None:
    assert _coerce_is_candidate({"is_candidate": val}) == expected


def test_unit_coerce_absent_key() -> None:
    assert _coerce_is_candidate({}) == 0
