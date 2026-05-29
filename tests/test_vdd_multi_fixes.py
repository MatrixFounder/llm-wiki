"""Regression tests for the vdd-multi (TASK 005 adversarial review) fixes.

F1 — wiki-search expands aliases on the DEFAULT (no --vaults) search.
F3 — confirm/alias/merge refuse a symlinked entity file.
F4 — merge sanitizes absorbed alias surfaces (helper).
F5 — lint strips control chars from untrusted alias surfaces (helper).
F6 — wiki-confirm --auto rejects a non-positive --threshold.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import frontmatter
import pytest

from scripts.wiki_index.lint import _safe_surface
from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills import wiki_confirm, wiki_search
from scripts.wiki_skills._common import sanitize_alias_surface

VAULT_ID = "test-vault"


def _new_repo(tmp_path: Path, vault: Path) -> tuple[SQLiteRepository, Path]:
    db = tmp_path / "g.db"
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id=VAULT_ID, name="v", root_path=vault,
        schema_version="3.0", registered_at=datetime(2026, 5, 29),
    ))
    return repo, db


def _out(capsys: pytest.CaptureFixture[str]) -> dict:
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


# F1 — default (all-vaults) search expands aliases ----------------------------
def test_f1_default_search_expands_aliases(tmp_path, capsys) -> None:
    vault = tmp_path / "vault"
    (vault / "_concepts").mkdir(parents=True)
    (vault / "_sources").mkdir(parents=True)
    (vault / "_concepts" / "hermesagent.md").write_text(
        "---\ntype: concept\nslug: hermesagent\ntitle: Hermes Agent\n"
        'date: 2026-05-29\ntags: [concept]\naliases: ["ZetaProto"]\n---\n\n# Hermes Agent\n',
        encoding="utf-8")
    (vault / "_sources" / "zeta-note.md").write_text(
        "---\ntype: summary\ntitle: Zeta\ndate: 2026-05-29\ntags: [t]\n---\n\n"
        "ZetaProto is great.\n", encoding="utf-8")
    repo, db = _new_repo(tmp_path, vault)
    reindex_full(repo, VAULT_ID)
    repo.close()
    # NO --vaults flag → default all-vaults search must still expand the alias.
    rc = wiki_search.main(["hermesagent", "--db-path", str(db)])
    assert rc == 0
    hits = {h["slug"] for h in _out(capsys)["hits"]}
    assert "zeta-note" in hits


# F3 — symlinked entity file refused ------------------------------------------
def test_f3_symlinked_entity_file_refused(tmp_path, capsys) -> None:
    vault = tmp_path / "vault"
    (vault / "_concepts").mkdir(parents=True)
    real = tmp_path / "outside.md"
    real.write_text("---\nis_candidate: true\n---\n# x\n", encoding="utf-8")
    link = vault / "_concepts" / "foo.md"
    link.symlink_to(real)  # entity file is a symlink
    repo, db = _new_repo(tmp_path, vault)
    repo.upsert_entity(
        vault_id=VAULT_ID, slug="foo", name="Foo", type="concept", is_candidate=1,
        canonicalized_by="test", first_seen="2026-05-29", last_updated="2026-05-29",
        file_path="_concepts/foo.md")
    repo.close()
    rc = wiki_confirm.main(["foo", "--vault", VAULT_ID, "--db-path", str(db)])
    assert rc == 4 and _out(capsys)["error"] == "ENTITY_FILE_MISSING"


# F6 — non-positive threshold rejected ----------------------------------------
def test_f6_threshold_zero_rejected(tmp_path, capsys) -> None:
    vault = tmp_path / "vault"
    (vault / "_concepts").mkdir(parents=True)
    repo, db = _new_repo(tmp_path, vault)
    repo.close()
    rc = wiki_confirm.main(["--auto", "--threshold", "0", "--vault", VAULT_ID,
                            "--db-path", str(db)])
    assert rc == 2
    out = _out(capsys)
    assert out["error"] == "INVALID_ARG" and out["field"] == "threshold"


# F4 / F5 — sanitization helpers ----------------------------------------------
def test_f4_sanitize_alias_surface() -> None:
    assert sanitize_alias_surface("  Hermes  ") == "Hermes"
    assert sanitize_alias_surface("bad\x01ctrl\x1f") == "badctrl"
    assert sanitize_alias_surface("\x01\x02") is None
    assert sanitize_alias_surface("x" * 500) == "x" * 200  # capped


def test_f5_safe_surface_strips_control_chars() -> None:
    assert _safe_surface("Dup\x01\nname") == "Dupname"
    assert "\x01" not in _safe_surface("a\x01b")
    assert len(_safe_surface("z" * 500)) == 200
