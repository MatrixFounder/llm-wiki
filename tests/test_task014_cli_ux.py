"""TASK 014 — CLI-UX dogfood fixes.

R-MF14-2: `wiki-query prepare` no longer requires `--vault-root` (derived from the
registered vault's root_path; explicit flag still wins).
R-MF14-3: `wiki-alias --list` with no slug lists EVERY alias in the vault; a repo
`list_all_aliases` backs it; `--add`/`--remove` without a slug → SLUG_REQUIRED.
"""

from __future__ import annotations

import contextlib
import io
import json
from datetime import datetime
from pathlib import Path

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills import wiki_alias, wiki_query


def _run(mod, argv: list[str]) -> tuple[int, dict]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = mod.main(argv)
    return code, json.loads(buf.getvalue())


# --- R-MF14-2: derive --vault-root ------------------------------------------

def _seed_query_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / "_sources").mkdir(parents=True)
    (vault / "_sources" / "note.md").write_text(
        "---\ntype: summary\ntitle: Note\ndate: 2026-06-01\ntags: [t]\n---\n\n"
        "# Note\n\nHermes routes messages between trading agents.\n", encoding="utf-8")
    db = tmp_path / "g.db"
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id="query-vault", name="v", root_path=vault,
        schema_version="5.0", registered_at=datetime(2026, 6, 1)))
    reindex_full(repo, "query-vault")
    repo.close()
    return db


def test_prepare_without_vault_root(tmp_path: Path) -> None:
    db = _seed_query_vault(tmp_path)
    code, env = _run(wiki_query, ["prepare", "Hermes routing",
                                  "--vault", "query-vault", "--db-path", str(db)])
    assert code == 0
    assert env["retrieved_count"] >= 1  # worked without --vault-root


def test_prepare_explicit_vault_root_still_ok(tmp_path: Path) -> None:
    db = _seed_query_vault(tmp_path)
    code, env = _run(wiki_query, ["prepare", "Hermes routing", "--vault", "query-vault",
                                  "--vault-root", str(tmp_path / "vault"),
                                  "--db-path", str(db)])
    assert code == 0 and env["retrieved_count"] >= 1


# --- R-MF14-3: vault-wide alias listing -------------------------------------

def _seed_alias_vault(tmp_path: Path) -> Path:
    db = tmp_path / "a.db"
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id="alias-vault", name="v", root_path=tmp_path / "v",
        schema_version="5.0", registered_at=datetime(2026, 6, 1)))
    for slug, name in [("hermes-agent", "Hermes Agent"), ("zeta-proto", "Zeta")]:
        repo.upsert_entity(
            "alias-vault", slug, name, "concept", 0, "", "2026-06-01",
            "2026-06-01", f"_entities/{slug}.md")
    # add_alias(vault_id, ALIAS, entity_slug, alias_type)
    repo.add_alias("alias-vault", "Hermes", "hermes-agent", alias_type="nickname")
    repo.add_alias("alias-vault", "HMS", "hermes-agent", alias_type="acronym")
    repo.add_alias("alias-vault", "ZetaProto", "zeta-proto", alias_type="spelling_variant")
    repo.close()
    return db


def test_list_all_aliases_repo(tmp_path: Path) -> None:
    db = _seed_alias_vault(tmp_path)
    repo = SQLiteRepository(db)
    pairs = repo.list_all_aliases("alias-vault")
    repo.close()
    # ordered by (entity_slug, alias)
    assert pairs == [("HMS", "hermes-agent"), ("Hermes", "hermes-agent"),
                     ("ZetaProto", "zeta-proto")]


def test_alias_list_no_slug_lists_all(tmp_path: Path) -> None:
    db = _seed_alias_vault(tmp_path)
    code, env = _run(wiki_alias, ["--list", "--vault", "alias-vault", "--db-path", str(db)])
    assert code == 0
    assert env["count"] == 3
    assert {a["alias"] for a in env["aliases"]} == {"HMS", "Hermes", "ZetaProto"}


def test_alias_list_with_slug_still_scopes(tmp_path: Path) -> None:
    db = _seed_alias_vault(tmp_path)
    code, env = _run(wiki_alias, ["hermes-agent", "--list", "--vault", "alias-vault",
                                  "--db-path", str(db)])
    assert code == 0
    assert sorted(env["aliases"]) == ["HMS", "Hermes"]


def test_alias_add_without_slug_refused(tmp_path: Path) -> None:
    db = _seed_alias_vault(tmp_path)
    code, env = _run(wiki_alias, ["--add", "Foo", "--vault", "alias-vault",
                                  "--db-path", str(db)])
    assert code == 2
    assert env["error"] == "SLUG_REQUIRED"
