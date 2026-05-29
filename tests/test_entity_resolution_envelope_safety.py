"""TASK 005-17 — error envelopes never echo operator-supplied content (CWE-117/209).

Architecture review m-2: extend the v3.1 "envelope never echoes content"
regression to the alias + merge surfaces. Error envelopes may name a safe kebab
*slug*, but never the raw operator-supplied surface string.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import frontmatter
import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills import wiki_alias, wiki_merge

VAULT_ID = "test-vault"
CANARY = "CANARY-zzz-do-not-echo"


def _seed(tmp_path: Path, slug: str, *, db: Path | None = None) -> Path:
    vault = tmp_path / "vault"
    (vault / "_concepts").mkdir(parents=True, exist_ok=True)
    db = db or (tmp_path / "g.db")
    fresh = not db.exists()
    repo = SQLiteRepository(db)
    if fresh:
        repo.apply_schema()
        repo.register_vault(Vault(
            vault_id=VAULT_ID, name="v", root_path=vault,
            schema_version="3.0", registered_at=datetime(2026, 5, 29),
        ))
    post = frontmatter.Post(f"# {slug}\n\nBody.", **{
        "type": "concept", "slug": slug, "name": slug.title(),
        "is_candidate": False, "tags": ["concept"],
    })
    (vault / "_concepts" / f"{slug}.md").write_text(frontmatter.dumps(post), encoding="utf-8")
    repo.upsert_entity(
        vault_id=VAULT_ID, slug=slug, name=slug.title(), type="concept",
        is_candidate=0, canonicalized_by="test", first_seen="2026-05-29",
        last_updated="2026-05-29", file_path=f"_concepts/{slug}.md",
    )
    repo.close()
    return db


def test_alias_collision_envelope_omits_surface(tmp_path, capsys) -> None:
    db = _seed(tmp_path, "ent-a")
    _seed(tmp_path, "ent-b", db=db)
    repo = SQLiteRepository(db)
    repo.add_alias(VAULT_ID, CANARY, "ent-a")  # canary resolves to ent-a
    repo.close()
    rc = wiki_alias.main(["ent-b", "--add", CANARY, "--vault", VAULT_ID, "--db-path", str(db)])
    out = capsys.readouterr().out
    assert rc == 5
    assert "ALIAS_COLLISION" in out
    assert CANARY not in out          # surface NOT echoed
    assert "ent-a" in out             # conflicting slug (safe) IS named


def test_alias_invalid_surface_envelope_omits_value(tmp_path, capsys) -> None:
    db = _seed(tmp_path, "ent-a")
    bad = "bad\x01" + CANARY          # control char → INVALID_ARG
    rc = wiki_alias.main(["ent-a", "--add", bad, "--vault", VAULT_ID, "--db-path", str(db)])
    out = capsys.readouterr().out
    assert rc == 2 and "INVALID_ARG" in out
    assert CANARY not in out          # raw value NOT echoed


def test_merge_self_envelope_clean(tmp_path, capsys) -> None:
    db = _seed(tmp_path, "ent-a")
    rc = wiki_merge.main(["ent-a", "ent-a", "--vault", VAULT_ID, "--db-path", str(db)])
    out = capsys.readouterr().out
    assert rc == 5 and "INVALID_MERGE" in out
