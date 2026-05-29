"""TASK 005-16 — durability round-trip acceptance, the ADR-002 §D8 gate (UC-14, UC-15).

The binding acceptance criterion: confirm-state, aliases, AND merges all
reconstruct from Class A markdown alone after a full DB rebuild, and AM-3 keeps
mentions/backlinks correct across the rebuild.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import frontmatter

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills import wiki_merge

VAULT_ID = "test-vault"


def _concept(vault: Path, slug: str, *, is_candidate: bool, name: str | None = None,
             aliases: list[str] | None = None) -> None:
    # reindex derives entities.name from the frontmatter `title` (pre-existing
    # behavior), so set both for a realistic display name.
    meta: dict[str, object] = {
        "type": "concept", "slug": slug,
        "name": name or slug.title(), "title": name or slug.title(),
        "date": "2026-05-29", "is_candidate": is_candidate,
        "tags": ["concept"] + (["candidate"] if is_candidate else []),
    }
    if aliases:
        meta["aliases"] = aliases
    (vault / "_concepts").mkdir(parents=True, exist_ok=True)
    (vault / "_concepts" / f"{slug}.md").write_text(
        frontmatter.dumps(frontmatter.Post(f"# {name or slug.title()}\n\nBody.", **meta)),
        encoding="utf-8",
    )


def _source(vault: Path, slug: str, body: str) -> None:
    (vault / "_sources").mkdir(parents=True, exist_ok=True)
    (vault / "_sources" / f"{slug}.md").write_text(
        f"---\ntype: summary\ntitle: {slug}\ndate: 2026-05-29\ntags: [t]\n---\n\n{body}\n",
        encoding="utf-8",
    )


def _rebuild_db(db: Path, vault: Path) -> SQLiteRepository:
    """Delete the DB and rebuild it from Class A markdown alone (§D8)."""
    if db.exists():
        db.unlink()
        for suffix in ("-wal", "-shm"):
            p = Path(str(db) + suffix)
            if p.exists():
                p.unlink()
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id=VAULT_ID, name="v", root_path=vault,
        schema_version="3.0", registered_at=datetime(2026, 5, 29),
    ))
    reindex_full(repo, VAULT_ID)
    return repo


def _state(repo: SQLiteRepository) -> dict[str, int]:
    return {
        r["slug"]: r["is_candidate"]
        for r in repo._connect().execute(
            "SELECT slug, is_candidate FROM entities WHERE vault_id = ?", (VAULT_ID,)
        ).fetchall()
    }


# --------------------------------------------------------------------------- #
# UC-14 — confirm-state + alias durability
# --------------------------------------------------------------------------- #
def test_uc14_confirm_and_alias_survive_full_reindex(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    db = tmp_path / "g.db"
    _concept(vault, "confirmed-one", is_candidate=False)
    _concept(vault, "candidate-one", is_candidate=True)
    _concept(vault, "aliased-one", is_candidate=False, aliases=["AnAlias"])

    repo = _rebuild_db(db, vault)
    before = _state(repo)
    assert before["confirmed-one"] == 0
    assert before["candidate-one"] == 1
    assert "AnAlias" in repo.list_aliases(VAULT_ID, "aliased-one")
    repo.close()

    # Delete the DB and reconstruct from markdown alone — §D8 round-trip.
    repo = _rebuild_db(db, vault)
    after = _state(repo)
    assert after == before, "confirm-state must reconstruct from Class A alone"
    assert repo.resolve_entity(VAULT_ID, "AnAlias").slug == "aliased-one"
    repo.close()


# --------------------------------------------------------------------------- #
# UC-15 — merge durability + AM-3 (mentions/backlinks survive the rebuild)
# --------------------------------------------------------------------------- #
def test_uc15_merge_survives_full_reindex(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    db = tmp_path / "g.db"
    _concept(vault, "hermes-agent", is_candidate=False, name="Hermes Agent")
    _concept(vault, "hermes-framework", is_candidate=False, name="Hermes Framework",
             aliases=["HF"])
    _source(vault, "note", "We rely on [[hermes-framework]] in production.")
    _rebuild_db(db, vault).close()

    # Merge via the CLI (Class A first, then DB mirror).
    rc = wiki_merge.main(["hermes-framework", "hermes-agent",
                          "--vault", VAULT_ID, "--db-path", str(db)])
    assert rc == 0
    assert not (vault / "_concepts" / "hermes-framework.md").exists()
    into_aliases = frontmatter.load(
        str(vault / "_concepts" / "hermes-agent.md")).metadata["aliases"]
    assert {"hermes-framework", "Hermes Framework", "HF"} <= set(into_aliases)

    # §D8: delete DB, rebuild from markdown alone.
    repo = _rebuild_db(db, vault)
    # from entity not re-materialised
    assert repo._connect().execute(
        "SELECT 1 FROM entities WHERE vault_id=? AND slug='hermes-framework'",
        (VAULT_ID,),
    ).fetchone() is None
    # surface resolves to the survivor through the rebuilt alias table
    assert repo.resolve_entity(VAULT_ID, "hermes-framework").slug == "hermes-agent"
    # AM-3: the [[hermes-framework]] ref canonicalized → counts toward into
    mc = repo._connect().execute(
        "SELECT mentions_count FROM entities WHERE vault_id=? AND slug='hermes-agent'",
        (VAULT_ID,),
    ).fetchone()[0]
    assert mc >= 1, "merged-away ref must survive the rebuild (AM-3)"
    # the stale [[hermes-framework]] link is NOT an orphan
    orphans = {o.target_slug for o in repo.find_orphan_links(VAULT_ID)}
    assert "hermes-framework" not in orphans
    # backlinks for the survivor include the re-pointed ref
    backlink_pages = {b.page_slug for b in repo.get_backlinks(VAULT_ID, "hermes-agent")}
    assert "note" in backlink_pages
    repo.close()
