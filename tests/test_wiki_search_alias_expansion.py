"""TASK 005-12 — wiki-search alias expansion, default on (R-5.5).

A source page that mentions only a *non-substring* alias ("ZetaProto") of the
entity `hermes-agent` is returned for query "hermes-agent" by default (alias
expansion), but NOT under --no-expand-aliases (byte-identical to pre-005).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills import wiki_search

VAULT_ID = "test-vault"


@pytest.fixture
def vault_db(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / "_concepts").mkdir(parents=True)
    (vault / "_sources").mkdir(parents=True)
    # Single-token slug so the bare --no-expand query is valid FTS5 (a hyphenated
    # bare query like "hermes-agent" is invalid FTS syntax — `-` is a NOT/column
    # operator; that pre-existing escaping limitation is orthogonal to R-5.5).
    (vault / "_concepts" / "hermesagent.md").write_text(
        "---\ntype: concept\nslug: hermesagent\ntitle: Hermes Agent\n"
        'date: 2026-05-29\ntags: [concept]\naliases: ["ZetaProto"]\n---\n\n'
        "# Hermes Agent\n\nThe agent.\n", encoding="utf-8",
    )
    (vault / "_sources" / "zeta-note.md").write_text(
        "---\ntype: summary\ntitle: Zeta Note\ndate: 2026-05-29\ntags: [t]\n---\n\n"
        "# Zeta Note\n\nZetaProto is great and revolutionary.\n", encoding="utf-8",
    )
    db = tmp_path / "g.db"
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id=VAULT_ID, name="v", root_path=vault,
        schema_version="3.0", registered_at=datetime(2026, 5, 29),
    ))
    reindex_full(repo, VAULT_ID)
    repo.close()
    return db


def _hits(capsys: pytest.CaptureFixture[str]) -> set[str]:
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    return {h["slug"] for h in out["hits"]}


def test_default_expansion_finds_alias_only_page(vault_db: Path, capsys) -> None:
    rc = wiki_search.main(["hermesagent", "--vaults", VAULT_ID, "--db-path", str(vault_db)])
    assert rc == 0
    assert "zeta-note" in _hits(capsys)  # found via the ZetaProto alias


def test_no_expand_excludes_alias_only_page(vault_db: Path, capsys) -> None:
    rc = wiki_search.main(["hermesagent", "--vaults", VAULT_ID,
                           "--no-expand-aliases", "--db-path", str(vault_db)])
    assert rc == 0
    assert "zeta-note" not in _hits(capsys)  # bare query can't reach the alias-only page


def test_non_alias_query_unaffected(vault_db: Path, capsys) -> None:
    """A query that resolves to no entity expands to itself (no behavior change)."""
    rc = wiki_search.main(["revolutionary", "--vaults", VAULT_ID, "--db-path", str(vault_db)])
    assert rc == 0
    assert "zeta-note" in _hits(capsys)
