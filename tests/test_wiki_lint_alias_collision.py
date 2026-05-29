"""TASK 005-13 — wiki-lint alias-collision detection (R-5.6).

Covers cross-table (DB) collisions, the Class A frontmatter scan, --json
sidecar parity, and the --strict advisory exit code.
"""

from __future__ import annotations

import io
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills import wiki_lint

VAULT_ID = "test-vault"


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    vault = tmp_path / "vault"
    (vault / "_concepts").mkdir(parents=True)
    db = tmp_path / "g.db"
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id=VAULT_ID, name="v", root_path=vault,
        schema_version="3.0", registered_at=datetime(2026, 5, 29),
    ))
    repo.close()
    return vault, db


def _entity(db: Path, slug: str, *, name: str | None = None) -> None:
    repo = SQLiteRepository(db)
    repo.upsert_entity(
        vault_id=VAULT_ID, slug=slug, name=name or slug.title(), type="concept",
        is_candidate=0, canonicalized_by="test", first_seen="2026-05-29",
        last_updated="2026-05-29", file_path=f"_concepts/{slug}.md",
    )
    repo.close()


def _run(argv: list[str]) -> tuple[int, dict]:
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        code = wiki_lint.main(argv)
    finally:
        sys.stdout = old
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


def test_cross_table_collision_detected(tmp_path: Path) -> None:
    _, db = _setup(tmp_path)
    _entity(db, "foo")
    _entity(db, "bar")
    repo = SQLiteRepository(db)
    repo.add_alias(VAULT_ID, "foo", "bar")  # alias "foo" == entity foo's slug
    repo.close()
    code, out = _run(["--vault", VAULT_ID, "--db-path", str(db)])
    assert code == 0  # default mode reports only
    assert out["by_category"].get("alias-collision", 0) >= 1


def test_frontmatter_scan_collision(tmp_path: Path) -> None:
    vault, db = _setup(tmp_path)
    (vault / "_concepts" / "a.md").write_text(
        '---\ntype: concept\ntitle: A\naliases: ["Dup"]\n---\n# A\n', encoding="utf-8")
    (vault / "_concepts" / "b.md").write_text(
        '---\ntype: concept\ntitle: B\naliases: ["Dup"]\n---\n# B\n', encoding="utf-8")
    code, out = _run(["--vault", VAULT_ID, "--db-path", str(db)])
    assert out["by_category"].get("alias-collision", 0) >= 1


def test_json_sidecar_parity(tmp_path: Path) -> None:
    vault, db = _setup(tmp_path)
    _entity(db, "foo")
    _entity(db, "bar")
    repo = SQLiteRepository(db)
    repo.add_alias(VAULT_ID, "foo", "bar")
    repo.close()
    sidecar = tmp_path / "lint.json"
    _run(["--vault", VAULT_ID, "--json-sidecar", str(sidecar), "--db-path", str(db)])
    data = json.loads(sidecar.read_text())
    cats = {entry["category"] for entry in data}
    assert "alias-collision" in cats
    alias_entries = [e for e in data if e["category"] == "alias-collision"]
    assert alias_entries[0]["details"]["alias"] == "foo"
    assert alias_entries[0]["details"]["kind"] == "cross_slug"


def test_strict_advisory_exit(tmp_path: Path) -> None:
    _, db = _setup(tmp_path)
    _entity(db, "foo")
    _entity(db, "bar")
    repo = SQLiteRepository(db)
    repo.add_alias(VAULT_ID, "foo", "bar")
    repo.close()
    code, _ = _run(["--vault", VAULT_ID, "--strict", "--db-path", str(db)])
    assert code == 1  # --strict + issues → non-zero advisory exit
