"""TASK 058 Phase 1 — `wiki-config show`/`tree` CLI contract (envelope + exit codes).

Pattern: call `main(argv)` directly, parse the one-line JSON stdout, assert
envelope + exit code (repo-wide test convention)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.wiki_skills.wiki_config import main


def _folder_yaml(d: Path, text: str) -> None:
    (d / ".wiki").mkdir(parents=True, exist_ok=True)
    (d / ".wiki" / "sync.yaml").write_text(text, encoding="utf-8")


def _run(capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, dict[str, Any]]:
    code = main(argv)
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert isinstance(payload, dict)
    return code, payload


_ROOT = (
    "exclude:\n"
    "  - '_inbox/**'\n"
    "resummarize:\n"
    "  mode: if-missing\n"
    "summarize:\n"
    "  profile: article\n"
)


def test_show_root(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _folder_yaml(tmp_path, _ROOT)
    code, env = _run(capsys, ["show", ".", "--vault-root", str(tmp_path)])
    assert code == 0
    assert env["action"] == "shown"
    assert env["folder"] == "."
    assert env["effective"]["summarize"]["profile"] == "article"
    assert env["provenance"]["/summarize/profile"]["origin"] == "root"
    assert env["provenance"]["/exclude"]["scope"] == "root-only"
    assert env["levels"][0]["file"] == ".wiki/sync.yaml"
    assert env["warnings"] == []


def test_show_subfolder_inheritance(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _folder_yaml(tmp_path, _ROOT)
    zone = tmp_path / "Zone"
    _folder_yaml(zone, "summarize:\n  profile: meeting\n")
    code, env = _run(capsys, ["show", "Zone", "--vault-root", str(tmp_path)])
    assert code == 0
    prof = env["provenance"]["/summarize/profile"]
    assert prof["origin"] == "Zone" and prof["shadows"] == ["root"]
    assert env["provenance"]["/resummarize/mode"]["origin"] == "root"


def test_show_missing_folder_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, env = _run(capsys, ["show", "NoSuch", "--vault-root", str(tmp_path)])
    assert code == 2 and env["error"] == "FOLDER_NOT_FOUND"


def test_show_escaping_folder_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "vault").mkdir()
    code, env = _run(
        capsys, ["show", "../..", "--vault-root", str(tmp_path / "vault")]
    )
    assert code == 2 and env["error"] == "FOLDER_NOT_FOUND"


def test_show_bad_vault_root_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    code, env = _run(capsys, ["show", ".", "--vault-root", "/no/such/dir-058"])
    assert code == 2 and env["error"] == "VAULT_ROOT_NOT_FOUND"


def test_show_defaults_to_cwd_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`wiki-config show` with NO folder argument targets the CURRENT folder."""
    _folder_yaml(tmp_path, _ROOT)
    zone = tmp_path / "Zone"
    _folder_yaml(zone, "summarize:\n  profile: meeting\n")
    monkeypatch.chdir(zone)
    code, env = _run(capsys, ["show", "--vault-root", str(tmp_path)])
    assert code == 0 and env["folder"] == "Zone"
    assert env["provenance"]["/summarize/profile"]["origin"] == "Zone"
    # CWD outside the vault → fall back to the vault root
    outside = tmp_path.parent / "elsewhere-058"
    outside.mkdir(exist_ok=True)
    monkeypatch.chdir(outside)
    code, env = _run(capsys, ["show", "--vault-root", str(tmp_path)])
    assert code == 0 and env["folder"] == "."


def test_show_no_args_inside_registered_vault(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Zero arguments: vault root via WIKI_SCHEMA.md walk-up, folder = CWD."""
    _folder_yaml(tmp_path, _ROOT)
    (tmp_path / "WIKI_SCHEMA.md").write_text(
        "---\nvault_id: demo\nschema_version: '5.0'\n---\n", encoding="utf-8")
    zone = tmp_path / "Zone"
    _folder_yaml(zone, "summarize:\n  profile: lesson\n")
    monkeypatch.chdir(zone)
    code, env = _run(capsys, ["show"])
    assert code == 0 and env["folder"] == "Zone"
    assert env["effective"]["summarize"]["profile"] == "lesson"


def _stub_active_note(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                      script_body: str) -> None:
    import os
    import stat

    bin_dir = tmp_path / "stub-bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "obsidian-active-note"
    stub.write_text("#!/bin/sh\n" + script_body, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")


def test_show_defaults_to_active_note_folder_over_cwd(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The interactive loop: the ACTIVE Obsidian note's folder wins over CWD."""
    import json as _json

    vault = tmp_path / "vault"
    _folder_yaml(vault, _ROOT)
    notes = vault / "03 - Learning"
    _folder_yaml(notes, "summarize:\n  profile: lesson\n")
    cwd_zone = vault / "Elsewhere"
    cwd_zone.mkdir()
    payload = _json.dumps({"path": "03 - Learning", "abs": str(notes)})
    _stub_active_note(tmp_path, monkeypatch, f"echo '{payload}'\n")
    monkeypatch.chdir(cwd_zone)
    code, env = _run(capsys, ["show", "--vault-root", str(vault)])
    assert code == 0
    assert env["folder"] == "03 - Learning"
    assert env["folder_source"] == "active-note"
    # resolver unavailable (exit 3) → falls back to CWD
    _stub_active_note(tmp_path, monkeypatch, "exit 3\n")
    code, env = _run(capsys, ["show", "--vault-root", str(vault)])
    assert code == 0
    assert env["folder"] == "Elsewhere" and env["folder_source"] == "cwd"
    # explicit argument always wins
    code, env = _run(capsys, ["show", ".", "--vault-root", str(vault)])
    assert env["folder"] == "." and env["folder_source"] == "argument"


def test_relative_vault_root_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dogfood regression (TASK 058): `--vault-root samples/foo` (relative)
    must resolve — every label computation assumes an absolute root."""
    vault = tmp_path / "vaults" / "demo"
    zone = vault / "Zone"
    _folder_yaml(vault, _ROOT)
    _folder_yaml(zone, "summarize:\n  profile: meeting\n")
    monkeypatch.chdir(tmp_path)
    code, env = _run(capsys, ["show", "Zone", "--vault-root", "vaults/demo"])
    assert code == 0
    assert env["provenance"]["/summarize/profile"]["origin"] == "Zone"
    code, env = _run(capsys, ["tree", "--vault-root", "vaults/demo"])
    assert code == 0 and env["files"] == 2


def test_show_broken_ancestor_exit_6(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _folder_yaml(tmp_path, _ROOT)
    bad = tmp_path / "Bad"
    _folder_yaml(bad, "resummarize: [broken\n")
    leaf = bad / "Leaf"
    leaf.mkdir()
    code, env = _run(capsys, ["show", "Bad/Leaf", "--vault-root", str(tmp_path)])
    assert code == 6
    assert env["error"] == "INVALID_SYNC_CONFIG"
    assert env["level"] == "Bad" and env["reason"] == "PARSE"
    # CWE-209: the broken file's content is never echoed
    assert "broken" not in json.dumps(env)


def test_tree_envelope(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _folder_yaml(tmp_path, _ROOT)
    zone = tmp_path / "Zone"
    _folder_yaml(zone, "summarize:\n  profile: meeting\nexclude: ['x/**']\n")
    code, env = _run(capsys, ["tree", "--vault-root", str(tmp_path)])
    assert code == 0
    assert env["action"] == "tree" and env["files"] == 2
    nodes = {n["folder"]: n for n in env["nodes"]}
    assert nodes["."]["overridden_by"]["/summarize/profile"] == ["Zone"]
    assert nodes["Zone"]["ignored"] == ["exclude"]
    assert env["warnings"][0]["code"] == "NON_CASCADING_KEY_IN_SUBFOLDER"


def test_tree_always_exit_0_with_broken_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _folder_yaml(tmp_path, ": :\n")
    code, env = _run(capsys, ["tree", "--vault-root", str(tmp_path)])
    assert code == 0
    assert env["nodes"][0]["error"]["code"] == "INVALID_SYNC_CONFIG"


def test_show_report_sidecar(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _folder_yaml(tmp_path, _ROOT)
    report = tmp_path / "out" ; report.mkdir()
    report_file = report / "show.md"
    code, env = _run(capsys, [
        "show", ".", "--vault-root", str(tmp_path), "--report", str(report_file),
    ])
    assert code == 0 and env["report"] == str(report_file)
    text = report_file.read_text(encoding="utf-8")
    assert "/summarize/profile" in text and "origin" in text


def test_tree_report_sidecar(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _folder_yaml(tmp_path, _ROOT)
    report_file = tmp_path / "tree.md"
    code, env = _run(capsys, [
        "tree", "--vault-root", str(tmp_path), "--report", str(report_file),
    ])
    assert code == 0
    assert "wiki-config tree" in report_file.read_text(encoding="utf-8")
