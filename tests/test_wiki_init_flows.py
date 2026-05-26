"""Tests for wiki-init flows (tasks-001-21/22/23)."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from scripts.wiki_skills.wiki_init import main


def _run(argv: list[str]) -> tuple[int, dict]:
    """Invoke wiki_init.main(argv); capture stdout JSON + exit code."""
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        code = main(argv)
    finally:
        sys.stdout = old
    return code, json.loads(buf.getvalue())


# =============================================================================
# scaffold-new (task-001-21)
# =============================================================================


def test_scaffold_new_creates_layout(tmp_path):
    vault = tmp_path / "newvault"
    db = tmp_path / "g.db"
    code, out = _run([
        "--scaffold-new", "--vault", str(vault),
        "--vault-id", "test-vault", "--db-path", str(db),
    ])
    assert code == 0
    assert out["action"] == "scaffolded"
    assert (vault / "WIKI_SCHEMA.md").exists()
    assert (vault / "CLAUDE.md").exists()
    for sub in ["_sources", "_concepts", "_entities", "_raw/.locks",
                "_raw/failed", "00-Vault-Index/log"]:
        assert (vault / sub).is_dir(), f"missing {sub}"
    # Schema content
    schema = (vault / "WIKI_SCHEMA.md").read_text()
    assert "vault_id: test-vault" in schema


def test_scaffold_new_invalid_vault_id(tmp_path):
    code, out = _run([
        "--scaffold-new", "--vault", str(tmp_path / "v"),
        "--vault-id", "1bad",
        "--db-path", str(tmp_path / "g.db"),
    ])
    assert code == 6
    assert out["error"] == "INVALID_VAULT_ID"


def test_scaffold_new_requires_vault_arg(tmp_path):
    """--vault is mandatory: no silent cwd default (prevents accidental
    scaffolds in the project repo root)."""
    code, out = _run(["--scaffold-new", "--db-path", str(tmp_path / "g.db")])
    assert code == 1
    assert out["error"] == "MISSING_VAULT_ARG"


# =============================================================================
# register-existing (task-001-22)
# =============================================================================


def test_register_existing_minimal_vault(minimal_vault: Path, tmp_path):
    """Register the minimal_vault fixture; vault_id from frontmatter."""
    db = tmp_path / "g.db"
    code, out = _run([
        "--register-existing", "--vault", str(minimal_vault),
        "--db-path", str(db),
    ])
    assert code == 0
    assert out["action"] == "registered"
    assert out["vault_id"] == "minimal-test"
    assert out["is_two_tier"] is False


def test_register_existing_two_tier_detected(multi_vault: dict[str, Path], tmp_path):
    """vault-alpha has Lessons/Course-A/_concepts — is_two_tier=True."""
    db = tmp_path / "g.db"
    code, out = _run([
        "--register-existing", "--vault", str(multi_vault["vault-alpha"]),
        "--db-path", str(db),
    ])
    assert code == 0
    assert out["is_two_tier"] is True


def test_register_existing_missing_schema(tmp_path):
    bare = tmp_path / "no-schema"
    bare.mkdir()
    code, out = _run([
        "--register-existing", "--vault", str(bare),
        "--db-path", str(tmp_path / "g.db"),
    ])
    assert code == 6
    assert out["error"] == "MISSING_WIKI_SCHEMA"


def test_register_existing_missing_vault_id(tmp_path):
    """WIKI_SCHEMA.md without vault_id → fail-fast with suggestion."""
    vault = tmp_path / "no-vid"
    vault.mkdir()
    (vault / "WIKI_SCHEMA.md").write_text(
        "---\nname: WIKI_SCHEMA\nschema_version: '2.0'\n---\n"
    )
    code, out = _run([
        "--register-existing", "--vault", str(vault),
        "--db-path", str(tmp_path / "g.db"),
    ])
    assert code == 6
    assert out["error"] == "MISSING_VAULT_ID"
    assert out["suggested_vault_id"] == "no-vid"


def test_register_existing_idempotent(minimal_vault: Path, tmp_path):
    """Re-registering the same vault returns 'already-registered'."""
    db = tmp_path / "g.db"
    args = ["--register-existing", "--vault", str(minimal_vault),
            "--db-path", str(db)]
    _run(args)
    code, out = _run(args)
    assert code == 0
    assert out["action"] == "already-registered"


# =============================================================================
# reconcile (task-001-23)
# =============================================================================


def test_reconcile_no_change(minimal_vault: Path, tmp_path):
    db = tmp_path / "g.db"
    _run(["--register-existing", "--vault", str(minimal_vault),
          "--db-path", str(db)])
    code, out = _run(["--reconcile", "--vault", str(minimal_vault),
                      "--db-path", str(db)])
    assert code == 0
    assert out["action"] == "no-change"


def test_reconcile_unregistered(minimal_vault: Path, tmp_path):
    code, out = _run(["--reconcile", "--vault", str(minimal_vault),
                      "--db-path", str(tmp_path / "g.db")])
    assert code == 6
    assert out["error"] == "VAULT_NOT_REGISTERED"


def test_reconcile_rename_requires_confirm(minimal_vault: Path, tmp_path):
    db = tmp_path / "g.db"
    _run(["--register-existing", "--vault", str(minimal_vault),
          "--db-path", str(db)])
    # Mutate the WIKI_SCHEMA.md vault_id
    schema = (minimal_vault / "WIKI_SCHEMA.md").read_text()
    schema = schema.replace("vault_id: minimal-test", "vault_id: renamed-vault")
    (minimal_vault / "WIKI_SCHEMA.md").write_text(schema)
    # Without --confirm: warning + exit 7
    code, out = _run(["--reconcile", "--vault", str(minimal_vault),
                      "--db-path", str(db)])
    assert code == 7
    assert out["warning"] == "VAULT_RENAMED"
    # With --confirm: rename succeeds
    code, out = _run(["--reconcile", "--vault", str(minimal_vault),
                      "--db-path", str(db), "--confirm"])
    assert code == 0
    assert out["action"] == "renamed"
    assert out["old_vault_id"] == "minimal-test"
    assert out["new_vault_id"] == "renamed-vault"
