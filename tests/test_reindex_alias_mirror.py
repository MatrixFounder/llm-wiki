"""TASK 005-03 — reindex mirrors `aliases:` + AM-3 ref-canonicalization (R-5.3, AM-3).

- R-5.3: entity-page `aliases:` frontmatter → `entity_aliases` (Class B),
  report-and-skip on the hard PK (vault_id, alias) collision (never silent).
- AM-3: a `page_entity_refs` target that is a registered alias is re-pointed to
  the canonical entity at reindex build time, so mentions/backlinks survive a
  full rebuild (the merge §D8 durability gate depends on this).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository


def _write(vault: Path, rel: str, fm: str, body: str) -> None:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{fm}\n---\n\n{body}\n", encoding="utf-8")


def _repo(tmp_path: Path, vault: Path) -> SQLiteRepository:
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id="test-vault", name="v", root_path=vault,
        schema_version="3.0", registered_at=datetime(2026, 5, 29),
    ))
    return repo


def test_e2e_01_aliases_mirrored_from_frontmatter(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _write(
        vault, "_concepts/hermes-agent.md",
        "type: concept\nslug: hermes-agent\ntitle: Hermes Agent\n"
        'date: 2026-05-29\ntags: [concept]\naliases: ["Hermes", "Hermes Framework"]',
        "# Hermes Agent\n\nThe agent.",
    )
    repo = _repo(tmp_path, vault)
    result = reindex_full(repo, "test-vault")
    aliases = {
        (r["alias"], r["entity_slug"])
        for r in repo._connect().execute(
            "SELECT alias, entity_slug FROM entity_aliases WHERE vault_id = 'test-vault'"
        ).fetchall()
    }
    assert ("Hermes", "hermes-agent") in aliases
    assert ("Hermes Framework", "hermes-agent") in aliases
    assert result["aliases"] == 2
    repo.close()


def test_e2e_02_ref_canonicalized_through_alias(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _write(
        vault, "_concepts/hermes-agent.md",
        "type: concept\nslug: hermes-agent\ntitle: Hermes Agent\n"
        'date: 2026-05-29\ntags: [concept]\naliases: ["Hermes"]',
        "# Hermes Agent\n\nThe agent.",
    )
    _write(
        vault, "_sources/note.md",
        "type: summary\ntitle: Note\ndate: 2026-05-29\ntags: [t]",
        "# Note\n\nWe use [[Hermes]] heavily.",
    )
    repo = _repo(tmp_path, vault)
    reindex_full(repo, "test-vault")
    conn = repo._connect()
    refs = [
        r["entity_slug"] for r in conn.execute(
            "SELECT entity_slug FROM page_entity_refs "
            "WHERE vault_id = 'test-vault' AND page_slug = 'note'"
        ).fetchall()
    ]
    assert "hermes-agent" in refs, "raw alias target should canonicalize"
    assert "Hermes" not in refs
    mc = conn.execute(
        "SELECT mentions_count FROM entities "
        "WHERE vault_id = 'test-vault' AND slug = 'hermes-agent'"
    ).fetchone()[0]
    assert mc >= 1, "canonicalized ref must count toward mentions"
    repo.close()


def test_e2e_03_alias_collision_reported_not_silent(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _write(
        vault, "_concepts/hermes-agent.md",
        "type: concept\nslug: hermes-agent\ntitle: Hermes Agent\n"
        'date: 2026-05-29\ntags: [concept]\naliases: ["Hermes"]',
        "# Hermes Agent",
    )
    _write(
        vault, "_concepts/hermes-bus.md",
        "type: concept\nslug: hermes-bus\ntitle: Hermes Bus\n"
        'date: 2026-05-29\ntags: [concept]\naliases: ["Hermes"]',
        "# Hermes Bus",
    )
    repo = _repo(tmp_path, vault)
    result = reindex_full(repo, "test-vault")
    # Hard PK → exactly one DB row for alias "Hermes"; the loser is reported.
    rows = repo._connect().execute(
        "SELECT entity_slug FROM entity_aliases "
        "WHERE vault_id = 'test-vault' AND alias = 'Hermes'"
    ).fetchall()
    assert len(rows) == 1
    assert len(result["alias_collisions"]) == 1
    assert result["alias_collisions"][0]["alias"] == "Hermes"
    repo.close()


def test_l8_entity_name_falls_back_to_frontmatter_name(tmp_path: Path) -> None:
    """L-8 (TASK 006): a concept page with `name:` and no `title:` reindexes to
    its display name, not the slug (title→name→slug fallback)."""
    vault = tmp_path / "vault"
    _write(
        vault, "_concepts/foo-bar.md",
        "type: concept\nslug: foo-bar\nname: Foo Bar\n"
        "date: 2026-05-29\ntags: [concept]\nis_candidate: false",
        "# Foo Bar\n\nNo title key here.",
    )
    repo = _repo(tmp_path, vault)
    reindex_full(repo, "test-vault")
    name = repo._connect().execute(
        "SELECT name FROM entities WHERE vault_id='test-vault' AND slug='foo-bar'"
    ).fetchone()[0]
    assert name == "Foo Bar"   # was the slug 'foo-bar' before L-8
    repo.close()
