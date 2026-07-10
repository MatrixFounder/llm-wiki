"""TASK 058 Phase 4 — templates: registry, vars, level enforcement, init
composition (create / --merge / --force), modeline, drift lint, determinism."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.wiki_skills.wiki_config import main
from scripts.wiki_skills.wiki_config._edit import gate_text
from scripts.wiki_skills.wiki_config._lint import lint_vault
from scripts.wiki_skills.wiki_config._templates import (
    MODELINE_PREFIX,
    discover_templates,
    render_for_init,
)

BUILTINS = {"meeting-zone", "lessons-mirror", "connector-zone",
            "article-zone", "root-baseline"}


def _folder_yaml(d: Path, text: str) -> None:
    (d / ".wiki").mkdir(parents=True, exist_ok=True)
    (d / ".wiki" / "sync.yaml").write_text(text, encoding="utf-8")


def _run(capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, dict[str, Any]]:
    code = main(argv)
    payload = json.loads(capsys.readouterr().out.strip())
    assert isinstance(payload, dict)
    return code, payload


def _read(d: Path) -> str:
    return (d / ".wiki" / "sync.yaml").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #


def test_builtins_discovered_and_valid() -> None:
    registry = discover_templates(None)
    assert BUILTINS <= set(registry)
    for name in BUILTINS:
        template = registry[name]
        assert template.valid, f"{name}: {template.error}"
        assert template.source == "builtin"
        # rendered-with-defaults body passes the full hardened gate
        defaults = {v.name: v.default or "" for v in template.variables}
        gate_text(render_for_init(template, defaults))


def test_builtin_levels_and_vars() -> None:
    registry = discover_templates(None)
    assert registry["root-baseline"].level == "root"
    assert registry["meeting-zone"].level == "subfolder"
    lessons = registry["lessons-mirror"]
    var = next(v for v in lessons.variables if v.name == "group_key")
    assert var.kind == "regex" and var.default == "^(\\d+)"


def test_vault_template_and_builtin_shadowing(tmp_path: Path) -> None:
    vdir = tmp_path / ".wiki" / "templates"
    vdir.mkdir(parents=True)
    (vdir / "my-zone.yaml").write_text(
        "# wiki-config template: my-zone v0.1.0\n"
        "# level: any\n"
        "# purpose: vault-local test template\n"
        "summarize:\n  profile: auto\n",
        encoding="utf-8")
    (vdir / "imposter.yaml").write_text(
        "# wiki-config template: meeting-zone v9.9.9\n"
        "# level: any\n"
        "# purpose: impersonation attempt\n"
        "summarize:\n  profile: article\n",
        encoding="utf-8")
    registry = discover_templates(tmp_path)
    assert registry["my-zone"].source == "vault" and registry["my-zone"].valid
    # builtin wins the name collision; the vault copy is listed shadowed
    assert registry["meeting-zone"].source == "builtin"
    shadowed = registry["meeting-zone (vault)"]
    assert shadowed.shadowed is True


def test_invalid_vault_template_listed_unusable(tmp_path: Path) -> None:
    vdir = tmp_path / ".wiki" / "templates"
    vdir.mkdir(parents=True)
    (vdir / "broken.yaml").write_text("no header\nzonez: []\n", encoding="utf-8")
    registry = discover_templates(tmp_path)
    assert registry["broken"].valid is False


# --------------------------------------------------------------------------- #
# init
# --------------------------------------------------------------------------- #


def test_init_fresh_folder_with_modeline_and_stamp(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    zone = tmp_path / "BD Встречи"
    zone.mkdir()
    code, env = _run(capsys, ["init", "BD Встречи", "--template", "meeting-zone",
                              "--vault-root", str(tmp_path)])
    assert code == 0 and env["mode"] == "create"
    text = _read(zone)
    assert text.splitlines()[0].startswith(MODELINE_PREFIX)
    assert "# wiki-config template: meeting-zone v1.0.0" in text
    assert "extract_concepts: false" in text
    gate_text(text)


def test_init_deterministic_byte_identical(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a, b = tmp_path / "A", tmp_path / "B"
    a.mkdir(); b.mkdir()
    _run(capsys, ["init", "A", "--template", "article-zone",
                  "--vault-root", str(tmp_path)])
    _run(capsys, ["init", "B", "--template", "article-zone",
                  "--vault-root", str(tmp_path)])
    assert _read(a) == _read(b)  # no timestamps anywhere


def test_init_var_substitution_and_redos_gate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    zone = tmp_path / "Course"
    zone.mkdir()
    code, env = _run(capsys, [
        "init", "Course", "--template", "lessons-mirror",
        "--var", "group_key=^(\\d{8})", "--vault-root", str(tmp_path)])
    assert code == 0
    assert "group_key: '^(\\d{8})'" in _read(zone)
    # a catastrophic regex var is refused at exit 6, value not echoed
    # (`^(a|a)+$` trips the load-gate battery; patterns the gate misses are
    # still bounded by the runtime `guarded_search` deadline — two layers)
    zone2 = tmp_path / "Course2"
    zone2.mkdir()
    evil = "^(a|a)+$"
    code, env = _run(capsys, [
        "init", "Course2", "--template", "lessons-mirror",
        "--var", f"group_key={evil}", "--vault-root", str(tmp_path)])
    assert code == 6 and env["error"] == "INVALID_TEMPLATE_VAR"
    assert evil not in json.dumps(env)
    assert not (zone2 / ".wiki").exists()


def test_init_var_quote_escaping_cannot_break_yaml(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    zone = tmp_path / "Q"
    zone.mkdir()
    code, _ = _run(capsys, [
        "init", "Q", "--template", "lessons-mirror",
        "--var", "group_key=^(x')y", "--vault-root", str(tmp_path)])
    # either cleanly written AND gate-valid, or refused — never a broken file
    if code == 0:
        gate_text(_read(zone))
    else:
        assert not (zone / ".wiki" / "sync.yaml").exists()


def test_init_unknown_and_missing_vars(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    zone = tmp_path / "V"
    zone.mkdir()
    code, env = _run(capsys, ["init", "V", "--template", "lessons-mirror",
                              "--var", "no_such=1", "--vault-root", str(tmp_path)])
    assert code == 2 and env["error"] == "UNKNOWN_VAR" and env["vars"] == ["no_such"]


def test_init_root_template_in_subfolder_hard_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    zone = tmp_path / "Zone"
    zone.mkdir()
    code, env = _run(capsys, ["init", "Zone", "--template", "root-baseline",
                              "--vault-root", str(tmp_path)])
    assert code == 2 and env["error"] == "TEMPLATE_LEVEL_MISMATCH"
    assert not (zone / ".wiki").exists()
    # at the root it works, with the var default applied
    code, env = _run(capsys, ["init", ".", "--template", "root-baseline",
                              "--vault-root", str(tmp_path)])
    assert code == 0
    assert "tag_namespace: 'wiki'" in _read(tmp_path)


def test_init_existing_exit_7_then_merge_then_force(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    zone = tmp_path / "Zone"
    _folder_yaml(zone, "# operator note\nsummarize:\n  profile: article\n")
    code, env = _run(capsys, ["init", "Zone", "--template", "meeting-zone",
                              "--vault-root", str(tmp_path)])
    assert code == 7 and env["error"] == "CONFIG_EXISTS"
    # --merge: existing summarize wins wholesale; missing resummarize appended
    code, env = _run(capsys, ["init", "Zone", "--template", "meeting-zone",
                              "--merge", "--vault-root", str(tmp_path)])
    assert code == 0 and env["merged_blocks"] == ["resummarize"]
    text = _read(zone)
    assert "# operator note" in text            # existing comments preserved
    assert "profile: article" in text            # existing value wins
    assert "mode: if-missing" in text            # template block appended
    assert env["backup"]
    gate_text(text)
    # re-merge is a no-op
    code, env = _run(capsys, ["init", "Zone", "--template", "meeting-zone",
                              "--merge", "--vault-root", str(tmp_path)])
    assert code == 0 and env["merged_blocks"] == []
    # --force replaces (with backup)
    code, env = _run(capsys, ["init", "Zone", "--template", "meeting-zone",
                              "--force", "--vault-root", str(tmp_path)])
    assert code == 0 and env["backup"]
    assert "profile: meeting" in _read(zone)


def test_templates_list_envelope(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, env = _run(capsys, ["templates", "--vault-root", str(tmp_path)])
    assert code == 0
    names = {t["name"] for t in env["templates"]}
    assert BUILTINS <= names
    lessons = next(t for t in env["templates"] if t["name"] == "lessons-mirror")
    assert lessons["required_vars"][0]["name"] == "group_key"


# --------------------------------------------------------------------------- #
# drift + modeline lint / fix
# --------------------------------------------------------------------------- #


def test_template_drift_and_modeline_findings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    zone = tmp_path / "Zone"
    zone.mkdir()
    _run(capsys, ["init", "Zone", "--template", "article-zone",
                  "--vault-root", str(tmp_path)])
    text = _read(zone)
    # simulate an OLD generated file: stale version stamp + stripped modeline
    aged = text.replace("article-zone v1.0.0", "article-zone v0.9.0")
    aged = "\n".join(aged.splitlines()[1:]) + "\n"
    (zone / ".wiki" / "sync.yaml").write_text(aged, encoding="utf-8")
    findings, _ = lint_vault(tmp_path)
    codes = {f.code for f in findings}
    assert "TEMPLATE_DRIFT" in codes
    assert "SCHEMA_MODELINE_MISSING" in codes
    # fix --yes restores the modeline (line 1 only, content untouched)
    before_content = aged
    code, env = _run(capsys, ["fix", "--vault-root", str(tmp_path), "--yes"])
    assert code == 0
    after = _read(zone)
    assert after.splitlines()[0].startswith(MODELINE_PREFIX)
    assert "\n".join(after.splitlines()[1:]) + "\n" == before_content
    # drift is manual: still reported, file version untouched
    findings, _ = lint_vault(tmp_path)
    assert "TEMPLATE_DRIFT" in {f.code for f in findings}


def test_hand_authored_files_not_nagged_about_modeline(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, "summarize:\n  profile: auto\n")  # no template stamp
    findings, _ = lint_vault(tmp_path)
    assert "SCHEMA_MODELINE_MISSING" not in {f.code for f in findings}


def test_schema_json_identity_with_yaml_source() -> None:
    """config/sync-config.schema.json is a committed projection — regeneration
    is a deliberate event; this test fails until it is regenerated."""
    import yaml

    from scripts.wiki_skills.wiki_config._templates import SCHEMA_JSON
    from scripts.wiki_skills.wiki_config._uimodel import SYNC_SCHEMA_PATH

    json_doc = json.loads(SCHEMA_JSON.read_text(encoding="utf-8"))
    yaml_doc = yaml.safe_load(SYNC_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert json_doc == yaml_doc
