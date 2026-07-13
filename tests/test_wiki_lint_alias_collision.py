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
from scripts.wiki_index.reindex import reindex_full
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
    # P-10 (TASK 006): the frontmatter-collision scan now reads
    # pages.frontmatter_json from the DB (not the files), so the pages must be
    # indexed first (operator workflow: reindex → lint).
    vault, db = _setup(tmp_path)
    (vault / "_concepts" / "a.md").write_text(
        '---\ntype: concept\nslug: a\ntitle: A\ndate: 2026-05-29\naliases: ["Dup"]\n---\n# A\n',
        encoding="utf-8")
    (vault / "_concepts" / "b.md").write_text(
        '---\ntype: concept\nslug: b\ntitle: B\ndate: 2026-05-29\naliases: ["Dup"]\n---\n# B\n',
        encoding="utf-8")
    repo = SQLiteRepository(db)
    reindex_full(repo, VAULT_ID)
    repo.close()
    code, out = _run(["--vault", VAULT_ID, "--db-path", str(db)])
    assert out["by_category"].get("alias-collision", 0) >= 1
    # confirm it's the frontmatter kind, sourced from the DB
    import json as _json
    sidecar = tmp_path / "fm.json"
    _run(["--vault", VAULT_ID, "--json-sidecar", str(sidecar), "--db-path", str(db)])
    # TASK 061 fix-loop (H1): sidecar is an OBJECT; the pre-061 array lives under `issues`.
    kinds = {e["details"]["kind"] for e in _json.loads(sidecar.read_text())["issues"]
             if e["category"] == "alias-collision"}
    assert "frontmatter" in kinds


def test_json_sidecar_parity(tmp_path: Path) -> None:
    vault, db = _setup(tmp_path)
    _entity(db, "foo")
    _entity(db, "bar")
    repo = SQLiteRepository(db)
    repo.add_alias(VAULT_ID, "foo", "bar")
    repo.close()
    sidecar = tmp_path / "lint.json"
    _run(["--vault", VAULT_ID, "--json-sidecar", str(sidecar), "--db-path", str(db)])
    # TASK 061 fix-loop (H1): sidecar is an OBJECT; the pre-061 array lives under `issues`.
    data = json.loads(sidecar.read_text())["issues"]
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


def test_frontmatter_collision_only_counts_entity_pages(tmp_path: Path) -> None:
    """vdd-multi MED fix: the frontmatter-collision scan joins `entities`, so a
    legal `aliases:` shared between a `_sources/` summary page and an entity page
    is NOT a collision (only entity pages count) — matching the reindex
    alias-mirror's `_concepts`/`_entities` tier gate."""
    import json as _json
    vault, db = _setup(tmp_path)
    (vault / "_sources").mkdir(exist_ok=True)
    (vault / "_concepts" / "ent-a.md").write_text(
        '---\ntype: concept\nslug: ent-a\ntitle: Ent A\ndate: 2026-05-29\naliases: ["Shared"]\n---\n# Ent A\n',
        encoding="utf-8")
    (vault / "_sources" / "src-note.md").write_text(
        '---\ntype: summary\nslug: src-note\ntitle: Src\ndate: 2026-05-29\naliases: ["Shared"]\n---\n# Src\n',
        encoding="utf-8")
    repo = SQLiteRepository(db)
    reindex_full(repo, VAULT_ID)
    repo.close()
    sidecar = tmp_path / "s.json"
    _run(["--vault", VAULT_ID, "--json-sidecar", str(sidecar), "--db-path", str(db)])
    # TASK 061 fix-loop (H1): sidecar is an OBJECT; the pre-061 array lives under `issues`.
    fm = [e for e in _json.loads(sidecar.read_text())["issues"]
          if e["category"] == "alias-collision" and e["details"]["kind"] == "frontmatter"]
    assert fm == [], f"a source-page alias must not trigger a frontmatter collision: {fm}"

    # Now add a SECOND entity page claiming "Shared" → that IS a collision.
    (vault / "_concepts" / "ent-b.md").write_text(
        '---\ntype: concept\nslug: ent-b\ntitle: Ent B\ndate: 2026-05-29\naliases: ["Shared"]\n---\n# Ent B\n',
        encoding="utf-8")
    repo = SQLiteRepository(db)
    reindex_full(repo, VAULT_ID)
    repo.close()
    _run(["--vault", VAULT_ID, "--json-sidecar", str(sidecar), "--db-path", str(db)])
    fm = [e for e in _json.loads(sidecar.read_text())["issues"]
          if e["category"] == "alias-collision" and e["details"]["kind"] == "frontmatter"]
    assert any(e["details"]["alias"] == "Shared" for e in fm), "two entity pages → collision"
