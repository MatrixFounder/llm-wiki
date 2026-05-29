"""Dogfood regression tests — TASK 005 /update-docs dogfood (2026-05-29).

DF-1: wiki-search must not crash on a hyphenated bare query. FTS5 reads the
      hyphen in `hermes-agent` as a NOT/column operator → sqlite3.OperationalError.
      The CLI now falls back to a literal quoted-phrase search.
DF-3: wiki-init --scaffold-new must emit a WIKI_SCHEMA.md whose frontmatter is
      valid YAML. The default description `LLM Wiki vault: <id>` had an unquoted
      colon → invalid YAML → --register-existing failed with MISSING_VAULT_ID
      (breaking the §D8 rebuild-from-Class-A path for every scaffolded vault).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import frontmatter
import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills import wiki_alias, wiki_init, wiki_search


def _out(capsys: pytest.CaptureFixture[str]) -> dict:
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def _seed_named(tmp_path: Path, slug: str, name: str, *, db: Path | None = None) -> Path:
    """Seed an entity (with its concept page on disk) into a vault + DB."""
    vault = tmp_path / "v"
    (vault / "_concepts").mkdir(parents=True, exist_ok=True)
    db = db or (tmp_path / "g.db")
    fresh = not db.exists()
    repo = SQLiteRepository(db)
    if fresh:
        repo.apply_schema()
        repo.register_vault(Vault(
            vault_id="cvault", name="v", root_path=vault,
            schema_version="3.0", registered_at=datetime(2026, 5, 29)))
    (vault / "_concepts" / f"{slug}.md").write_text(
        f"---\ntype: concept\nslug: {slug}\ntitle: {name}\n"
        f"date: 2026-05-29\ntags: [concept]\nis_candidate: false\n---\n\n# {name}\n",
        encoding="utf-8")
    repo.upsert_entity(
        vault_id="cvault", slug=slug, name=name, type="concept", is_candidate=0,
        canonicalized_by="t", first_seen="2026-05-29", last_updated="2026-05-29",
        file_path=f"_concepts/{slug}.md")
    repo.close()
    return db


def test_df1_search_hyphenated_query_does_not_crash(tmp_path: Path, capsys) -> None:
    vault = tmp_path / "v"
    (vault / "_concepts").mkdir(parents=True)
    (vault / "_concepts" / "hermes-agent.md").write_text(
        "---\ntype: concept\nslug: hermes-agent\ntitle: Hermes Agent\n"
        "date: 2026-05-29\ntags: [concept]\n---\n\n# Hermes Agent\nbody\n",
        encoding="utf-8")
    db = tmp_path / "g.db"
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id="dfvault", name="v", root_path=vault,
        schema_version="3.0", registered_at=datetime(2026, 5, 29)))
    reindex_full(repo, "dfvault")
    repo.close()
    # Hyphenated bare query + --no-expand-aliases previously raised
    # sqlite3.OperationalError("no such column: agent"); now graceful.
    rc = wiki_search.main(
        ["hermes-agent", "--vaults", "dfvault", "--no-expand-aliases",
         "--db-path", str(db)])
    assert rc == 0
    assert "hermes-agent" in {h["slug"] for h in _out(capsys)["hits"]}


def test_df3_scaffold_emits_valid_yaml_and_registers(tmp_path: Path, capsys) -> None:
    vault = tmp_path / "scaffolded"
    db = tmp_path / "g.db"
    rc = wiki_init.main(["--scaffold-new", "--vault", str(vault),
                         "--vault-id", "dfscaffold", "--db-path", str(db)])
    assert rc == 0
    capsys.readouterr()  # drain scaffold envelope

    # The regression: WIKI_SCHEMA.md frontmatter must parse as valid YAML and
    # carry vault_id, even though the description contains a colon.
    meta = frontmatter.load(str(vault / "WIKI_SCHEMA.md")).metadata
    assert meta["vault_id"] == "dfscaffold"
    assert ":" in meta["description"]  # colon preserved, now quoted-safe

    # And the §D8 rebuild path (--register-existing reading vault_id from
    # Class A) must succeed against a fresh DB.
    db2 = tmp_path / "g2.db"
    rc = wiki_init.main(["--register-existing", "--vault", str(vault),
                         "--db-path", str(db2)])
    assert rc == 0
    assert _out(capsys)["vault_id"] == "dfscaffold"


def test_df4_add_refuses_cross_name_hijack(tmp_path: Path, capsys) -> None:
    """wiki-alias --add must refuse a surface equal to a DIFFERENT entity's
    name (would hijack that name's resolution). Previously accepted (exit 0)."""
    db = _seed_named(tmp_path, "alpha", "Alpha System")
    _seed_named(tmp_path, "beta", "Beta Engine", db=db)
    rc = wiki_alias.main(["alpha", "--add", "Beta Engine", "--vault", "cvault",
                          "--db-path", str(db)])
    out = _out(capsys)
    assert rc == 5 and out["error"] == "ALIAS_COLLISION"
    assert "beta" in out["reason"]


def test_df4_add_allows_own_name(tmp_path: Path, capsys) -> None:
    """Aliasing an entity's OWN name is fine (not a hijack)."""
    db = _seed_named(tmp_path, "alpha", "Alpha System")
    rc = wiki_alias.main(["alpha", "--add", "Alpha System", "--vault", "cvault",
                          "--db-path", str(db)])
    assert rc == 0 and _out(capsys)["action"] == "added"


def test_df5_add_own_slug_is_unchanged_not_redundant_alias(tmp_path: Path, capsys) -> None:
    """Adding an entity's own slug as an alias is a no-op, not a redundant row."""
    db = _seed_named(tmp_path, "alpha", "Alpha System")
    rc = wiki_alias.main(["alpha", "--add", "alpha", "--vault", "cvault",
                          "--db-path", str(db)])
    assert rc == 0 and _out(capsys)["action"] == "unchanged"
    repo = SQLiteRepository(db)
    assert "alpha" not in repo.list_aliases("cvault", "alpha")  # no self-alias row
    repo.close()
