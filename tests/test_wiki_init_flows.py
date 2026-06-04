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
    assert (vault / "GEMINI.md").exists()      # per-vendor agent files
    assert out["agent_files"] == {"CLAUDE.md": "written", "GEMINI.md": "written"}
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


def test_register_existing_writes_agent_files_if_absent(tmp_path):
    """A registered vault with no agent files gets one PER vendor (CLAUDE.md +
    GEMINI.md) so any agent CLI launched at its root has wiki operating
    instructions (DF-018-INIT-1). GEMINI.md is an exact copy of CLAUDE.md for now."""
    vault = tmp_path / "personal-x"
    vault.mkdir()
    (vault / "WIKI_SCHEMA.md").write_text(
        '---\nvault_id: personal-x\nlayout: obsidian-personal\nlanguage: ru\n'
        'description: "My PARA vault"\n---\n# schema\n', encoding="utf-8")
    code, out = _run([
        "--register-existing", "--vault", str(vault), "--db-path", str(tmp_path / "g.db"),
    ])
    assert code == 0 and out["action"] == "registered"
    assert out["agent_files"] == {"CLAUDE.md": "written", "GEMINI.md": "written"}
    body = (vault / "CLAUDE.md").read_text()
    assert "personal-x" in body and "wiki-sync" in body   # rendered + substituted
    assert (vault / "GEMINI.md").read_text() == body       # exact copy for now


def test_register_existing_preserves_operator_agent_file(tmp_path):
    """An operator's own CLAUDE.md is NEVER clobbered without --force; the OTHER
    vendor (GEMINI.md) is still created (non-destructive, per-file)."""
    vault = tmp_path / "has-claude"
    vault.mkdir()
    (vault / "WIKI_SCHEMA.md").write_text(
        '---\nvault_id: has-claude\nlayout: karpathy\n---\n# schema\n', encoding="utf-8")
    (vault / "CLAUDE.md").write_text("# MY OWN INSTRUCTIONS\n", encoding="utf-8")
    code, out = _run([
        "--register-existing", "--vault", str(vault), "--db-path", str(tmp_path / "g.db"),
    ])
    assert code == 0
    assert out["agent_files"]["CLAUDE.md"] == "exists"
    assert (vault / "CLAUDE.md").read_text() == "# MY OWN INSTRUCTIONS\n"
    assert out["agent_files"]["GEMINI.md"] == "written"   # other vendor still scaffolded


def test_write_agent_files_resilient_to_missing_template(tmp_path, monkeypatch):
    """vdd-adversarial: a vendor pointing at a missing/misconfigured template must
    NOT crash init — the working vendors still get written, the broken one is
    reported as 'error' (best-effort, never a partial-state crash)."""
    from scripts.wiki_skills import wiki_init as wi
    monkeypatch.setattr(
        wi, "_agent_file_specs",
        lambda: [("CLAUDE.md", "CLAUDE.md.tmpl"), ("GEMINI.md", "MISSING.tmpl")],
    )
    ph = {"vault_id": "x-vault", "language": "en", "layout": "karpathy", "description": "y"}
    res = wi._write_agent_files(tmp_path, ph, force=False)   # must not raise
    assert res == {"CLAUDE.md": "written", "GEMINI.md": "error"}
    assert (tmp_path / "CLAUDE.md").exists()
    assert not (tmp_path / "GEMINI.md").exists()


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
