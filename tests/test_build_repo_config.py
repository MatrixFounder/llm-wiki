"""TASK 022 / bead 02-02 — `_common.build_repo_config` resolution chain.

`--db-path` flag > `index_db` (WIKI_SCHEMA.md) > global. No `db_path` key ⇒ global
fallback (byte-identity, R-022-6). `make_repo` is consumed unchanged (iCloud guard reused).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.wiki_skills._common import build_repo_config


def _vault(tmp_path: Path, index_db_line: str | None) -> Path:
    root = tmp_path / "v"
    root.mkdir()
    fm = "---\nvault_id: demo-vault\nschema_version: '2.0'\n"
    if index_db_line is not None:
        fm += f"{index_db_line}\n"
    fm += "---\n\n# schema\n"
    (root / "WIKI_SCHEMA.md").write_text(fm, encoding="utf-8")
    return root


def test_flag_wins_over_index_db(tmp_path):
    root = _vault(tmp_path, "index_db: .wiki/index.db")
    cfg = build_repo_config("demo-vault", vault_root=root, db_path_flag="/tmp/flag.db")
    assert cfg == {"vault_id": "demo-vault", "db_path": "/tmp/flag.db"}


def test_index_db_used_when_no_flag(tmp_path):
    root = _vault(tmp_path, "index_db: .wiki/index.db")
    cfg = build_repo_config("demo-vault", vault_root=root, db_path_flag=None)
    assert cfg["vault_id"] == "demo-vault"
    assert cfg["db_path"] == str(root / ".wiki" / "index.db")


def test_no_root_no_index_db_is_global(tmp_path):
    # vault_root=None → no index_db lookup → no db_path key → make_repo uses global
    cfg = build_repo_config("demo-vault", vault_root=None, db_path_flag=None)
    assert cfg == {"vault_id": "demo-vault"}
    assert "db_path" not in cfg


def test_root_without_index_db_is_global(tmp_path):
    root = _vault(tmp_path, None)
    cfg = build_repo_config("demo-vault", vault_root=root, db_path_flag=None)
    assert "db_path" not in cfg  # byte-identical global fallback


def test_invalid_index_db_emits_envelope_and_exits(tmp_path, capsys):
    """vdd-multi MED-2: a malformed/unsafe index_db → clean JSON envelope + exit 6,
    NOT a raw traceback (the orchestrator parses stdout). Value never echoed (CWE-209)."""
    root = tmp_path / "v"
    root.mkdir()
    (root / "WIKI_SCHEMA.md").write_text(
        "---\nvault_id: demo-vault\nindex_db: ../escape.db\n---\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        build_repo_config("demo-vault", vault_root=root, db_path_flag=None)
    assert exc.value.code == 6
    out = capsys.readouterr().out
    assert "INVALID_INDEX_DB" in out and "escape.db" not in out


def test_invalid_index_db_envelope_carries_actionable_hint(tmp_path, capsys):
    """TASK 042: the INVALID_INDEX_DB envelope must be ACTIONABLE — name the env var to set —
    while still NOT echoing the offending value (CWE-209)."""
    import json
    root = tmp_path / "v"
    root.mkdir()
    (root / "WIKI_SCHEMA.md").write_text(   # absolute, outside app-data, no env → rejected
        "---\nvault_id: demo-vault\nindex_db: /etc/passwd-wiki.db\n---\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        build_repo_config("demo-vault", vault_root=root, db_path_flag=None)
    out = json.loads(capsys.readouterr().out)
    assert out["error"] == "INVALID_INDEX_DB"
    assert "WIKI_ALLOW_ABSOLUTE_INDEX_DB" in out["hint"]
    assert "passwd-wiki" not in json.dumps(out, ensure_ascii=False)  # value not echoed


def test_mismatched_vault_id_falls_back_to_global(tmp_path):
    """vdd-multi HIGH-L1: addressing vault-a while vault_root belongs to vault-b → the
    index_db is ignored (no db_path → global), preventing a wrong-DB open."""
    root = tmp_path / "v"
    root.mkdir()
    (root / "WIKI_SCHEMA.md").write_text(
        "---\nvault_id: vault-b\nindex_db: .wiki/index.db\n---\n", encoding="utf-8")
    cfg = build_repo_config("vault-a", vault_root=root, db_path_flag=None)
    assert "db_path" not in cfg


def test_icloud_index_db_still_guarded_by_make_repo(tmp_path, monkeypatch):
    """An `index_db` resolving into an iCloud container still hits make_repo's R-03
    guard (make_repo is unchanged) → ICloudRejectionError."""
    from scripts.wiki_index.factory import ICloudRejectionError, make_repo
    icloud = tmp_path / "Mobile Documents" / "iCloud~md~obsidian" / "Documents" / "v"
    icloud.mkdir(parents=True)
    (icloud / "WIKI_SCHEMA.md").write_text(
        "---\nvault_id: demo-vault\nindex_db: .wiki/index.db\n---\n", encoding="utf-8")
    cfg = build_repo_config("demo-vault", vault_root=icloud, db_path_flag=None)
    with pytest.raises(ICloudRejectionError):
        make_repo(cfg)
