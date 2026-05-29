"""TASK 005 Phase 3 — entity-resolution CLIs (wiki-confirm / wiki-alias / wiki-merge).

Drives each CLI's `main(argv)` directly (fast; capsys captures the JSON envelope)
against a real on-disk vault + temp DB. Covers R-4.2/4.3/4.4 (confirm),
R-5.1/5.2 (alias), R-4.7 (merge) including Class A frontmatter round-trip.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import frontmatter
import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills import wiki_alias, wiki_confirm, wiki_merge

VAULT_ID = "test-vault"


def _seed(
    tmp_path: Path, slug: str, *, is_candidate: bool = True,
    aliases: list[str] | None = None, name: str | None = None,
) -> tuple[Path, Path]:
    """Create / extend a vault + DB with one entity page + row. Reused per slug."""
    vault = tmp_path / "vault"
    (vault / "_concepts").mkdir(parents=True, exist_ok=True)
    db = tmp_path / "g.db"
    fresh = not db.exists()
    repo = SQLiteRepository(db)
    if fresh:
        repo.apply_schema()
        repo.register_vault(Vault(
            vault_id=VAULT_ID, name="v", root_path=vault,
            schema_version="3.0", registered_at=datetime(2026, 5, 29),
        ))
    meta: dict[str, object] = {
        "type": "concept", "slug": slug, "name": name or slug.title(),
        "is_candidate": is_candidate,
        "tags": ["concept"] + (["candidate"] if is_candidate else []),
    }
    if aliases:
        meta["aliases"] = aliases
    post = frontmatter.Post(f"# {name or slug.title()}\n\nBody.", **meta)
    (vault / "_concepts" / f"{slug}.md").write_text(
        frontmatter.dumps(post), encoding="utf-8")
    repo.upsert_entity(
        vault_id=VAULT_ID, slug=slug, name=name or slug.title(), type="concept",
        is_candidate=1 if is_candidate else 0, canonicalized_by="test",
        first_seen="2026-05-29", last_updated="2026-05-29",
        file_path=f"_concepts/{slug}.md",
    )
    if aliases:
        for a in aliases:
            repo.add_alias(VAULT_ID, a, slug)
    repo.close()
    return vault, db


def _seed_ref(db: Path, page: str, entity_slug: str) -> None:
    repo = SQLiteRepository(db)
    conn = repo._connect()
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(
        "INSERT INTO page_entity_refs "
        "(vault_id, page_slug, page_project, entity_slug, ref_type) "
        "VALUES (?, ?, '_vault_', ?, 'mentioned')",
        (VAULT_ID, page, entity_slug),
    )
    conn.execute("PRAGMA foreign_keys = ON")
    repo.close()


def _out(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def _db_is_candidate(db: Path, slug: str) -> int:
    repo = SQLiteRepository(db)
    row = repo._connect().execute(
        "SELECT is_candidate FROM entities WHERE vault_id = ? AND slug = ?",
        (VAULT_ID, slug),
    ).fetchone()
    repo.close()
    return row["is_candidate"]


def _fm(vault: Path, slug: str) -> dict[str, object]:
    return frontmatter.load(str(vault / "_concepts" / f"{slug}.md")).metadata


# --------------------------------------------------------------------------- #
# wiki-confirm — R-4.2/4.3/4.4
# --------------------------------------------------------------------------- #
class TestWikiConfirm:
    def test_confirm_flips_frontmatter_and_db(self, tmp_path, capsys) -> None:
        vault, db = _seed(tmp_path, "hermes-agent", is_candidate=True)
        rc = wiki_confirm.main(["hermes-agent", "--vault", VAULT_ID, "--db-path", str(db)])
        assert rc == 0
        out = _out(capsys)
        assert out["status"] == "confirmed" and out["changed"] is True
        assert _fm(vault, "hermes-agent")["is_candidate"] is False
        assert "candidate" not in _fm(vault, "hermes-agent").get("tags", [])
        assert _db_is_candidate(db, "hermes-agent") == 0

    def test_confirm_idempotent(self, tmp_path, capsys) -> None:
        _, db = _seed(tmp_path, "foo", is_candidate=False)
        rc = wiki_confirm.main(["foo", "--vault", VAULT_ID, "--db-path", str(db)])
        assert rc == 0 and _out(capsys)["changed"] is False

    def test_undo_demotes(self, tmp_path, capsys) -> None:
        vault, db = _seed(tmp_path, "foo", is_candidate=False)
        rc = wiki_confirm.main(["foo", "--vault", VAULT_ID, "--undo", "--db-path", str(db)])
        assert rc == 0 and _out(capsys)["status"] == "candidate"
        assert _fm(vault, "foo")["is_candidate"] is True
        assert _db_is_candidate(db, "foo") == 1

    def test_not_found(self, tmp_path, capsys) -> None:
        _, db = _seed(tmp_path, "foo")
        rc = wiki_confirm.main(["ghost", "--vault", VAULT_ID, "--db-path", str(db)])
        assert rc == 3 and _out(capsys)["error"] == "ENTITY_NOT_FOUND"

    def test_auto_promote_and_dry_run(self, tmp_path, capsys) -> None:
        vault, db = _seed(tmp_path, "hot", is_candidate=True)
        _seed(tmp_path, "cold", is_candidate=True)
        for p in ("a", "b", "c"):
            _seed_ref(db, p, "hot")
        _seed_ref(db, "a", "cold")
        # dry-run writes nothing
        rc = wiki_confirm.main(["--auto", "--threshold", "3", "--dry-run",
                                "--vault", VAULT_ID, "--db-path", str(db)])
        assert rc == 0
        out = _out(capsys)
        assert out["would_promote"] == ["hot"] and out["dry_run"] is True
        assert _db_is_candidate(db, "hot") == 1  # unchanged by dry-run
        # real run promotes hot, flips its frontmatter
        rc = wiki_confirm.main(["--auto", "--threshold", "3",
                                "--vault", VAULT_ID, "--db-path", str(db)])
        assert rc == 0 and _out(capsys)["promoted"] == ["hot"]
        assert _db_is_candidate(db, "hot") == 0
        assert _fm(vault, "hot")["is_candidate"] is False


# --------------------------------------------------------------------------- #
# wiki-alias — R-5.1/5.2
# --------------------------------------------------------------------------- #
class TestWikiAlias:
    def test_add_writes_frontmatter_and_db(self, tmp_path, capsys) -> None:
        vault, db = _seed(tmp_path, "hermes-agent")
        rc = wiki_alias.main(["hermes-agent", "--add", "Hermes",
                              "--vault", VAULT_ID, "--db-path", str(db)])
        assert rc == 0 and _out(capsys)["action"] == "added"
        assert "Hermes" in _fm(vault, "hermes-agent")["aliases"]
        repo = SQLiteRepository(db)
        assert repo.list_aliases(VAULT_ID, "hermes-agent") == ["Hermes"]
        repo.close()

    def test_add_idempotent(self, tmp_path, capsys) -> None:
        _, db = _seed(tmp_path, "hermes-agent", aliases=["Hermes"])
        rc = wiki_alias.main(["hermes-agent", "--add", "Hermes",
                              "--vault", VAULT_ID, "--db-path", str(db)])
        assert rc == 0 and _out(capsys)["action"] == "unchanged"

    def test_add_collision(self, tmp_path, capsys) -> None:
        _seed(tmp_path, "hermes-agent", aliases=["Hermes"])
        _, db = _seed(tmp_path, "hermes-bus")
        rc = wiki_alias.main(["hermes-bus", "--add", "Hermes",
                              "--vault", VAULT_ID, "--db-path", str(db)])
        out = _out(capsys)
        assert rc == 5 and out["error"] == "ALIAS_COLLISION"
        assert "hermes-agent" in out["reason"]

    def test_remove_and_list(self, tmp_path, capsys) -> None:
        vault, db = _seed(tmp_path, "hermes-agent", aliases=["Hermes", "HMS"])
        rc = wiki_alias.main(["hermes-agent", "--remove", "Hermes",
                              "--vault", VAULT_ID, "--db-path", str(db)])
        assert rc == 0 and _out(capsys)["action"] == "removed"
        assert "Hermes" not in _fm(vault, "hermes-agent").get("aliases", [])
        rc = wiki_alias.main(["hermes-agent", "--list",
                              "--vault", VAULT_ID, "--db-path", str(db)])
        assert rc == 0 and _out(capsys)["aliases"] == ["HMS"]


# --------------------------------------------------------------------------- #
# wiki-merge — R-4.7
# --------------------------------------------------------------------------- #
class TestWikiMerge:
    def test_merge_folds_duplicate(self, tmp_path, capsys) -> None:
        vault, db = _seed(tmp_path, "hermes-agent", is_candidate=False, name="Hermes Agent")
        _seed(tmp_path, "hermes-framework", is_candidate=False, name="Hermes Framework",
              aliases=["HF"])
        _seed_ref(db, "note", "hermes-framework")
        rc = wiki_merge.main(["hermes-framework", "hermes-agent",
                              "--vault", VAULT_ID, "--db-path", str(db)])
        assert rc == 0
        out = _out(capsys)
        assert out["action"] == "merged" and out["refs_repointed"] == 1
        # from page deleted
        assert not (vault / "_concepts" / "hermes-framework.md").exists()
        # into frontmatter carries the redirect surfaces
        into_aliases = _fm(vault, "hermes-agent")["aliases"]
        assert "hermes-framework" in into_aliases
        assert "Hermes Framework" in into_aliases
        assert "HF" in into_aliases
        # DB: resolve through the redirect; from entity gone
        repo = SQLiteRepository(db)
        assert repo.resolve_entity(VAULT_ID, "hermes-framework").slug == "hermes-agent"
        repo.close()

    def test_dry_run_writes_nothing(self, tmp_path, capsys) -> None:
        vault, db = _seed(tmp_path, "into-e", name="Into")
        _seed(tmp_path, "from-e", name="From")
        rc = wiki_merge.main(["from-e", "into-e", "--dry-run",
                              "--vault", VAULT_ID, "--db-path", str(db)])
        assert rc == 0 and _out(capsys)["dry_run"] is True
        assert (vault / "_concepts" / "from-e.md").exists()  # not deleted

    def test_self_merge_rejected(self, tmp_path, capsys) -> None:
        _, db = _seed(tmp_path, "foo")
        rc = wiki_merge.main(["foo", "foo", "--vault", VAULT_ID, "--db-path", str(db)])
        assert rc == 5 and _out(capsys)["error"] == "INVALID_MERGE"

    def test_missing_endpoint(self, tmp_path, capsys) -> None:
        _, db = _seed(tmp_path, "foo")
        rc = wiki_merge.main(["foo", "ghost", "--vault", VAULT_ID, "--db-path", str(db)])
        out = _out(capsys)
        assert rc == 3 and out["error"] == "ENTITY_NOT_FOUND" and out["field"] == "into_slug"
