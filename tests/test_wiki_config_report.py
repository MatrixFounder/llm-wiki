"""TASK 058 Phase 5 — the self-contained HTML report: badges, escaping,
determinism, CSP self-containment, and the CLI envelope."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.wiki_skills.wiki_config import main
from scripts.wiki_skills.wiki_config._lint import lint_vault
from scripts.wiki_skills.wiki_config._report import build_report_model, render_html


def _folder_yaml(d: Path, text: str) -> None:
    (d / ".wiki").mkdir(parents=True, exist_ok=True)
    (d / ".wiki" / "sync.yaml").write_text(text, encoding="utf-8")


def _run(capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, dict[str, Any]]:
    code = main(argv)
    payload = json.loads(capsys.readouterr().out.strip())
    assert isinstance(payload, dict)
    return code, payload


def _render(vault_root: Path, **kwargs: Any) -> str:
    findings, _ = lint_vault(vault_root)
    return render_html(build_report_model(vault_root, findings, **kwargs))


_ROOT = (
    "exclude: ['_inbox/**']\n"
    "resummarize:\n"
    "  mode: if-missing\n"
    "  detect:\n"
    "    mirror:\n"
    "      enabled: true\n"
    "      raw_dirs: [Transcripts]\n"
    "      summary_dir: Summary\n"
    "      group_key: '^(\\d+)'\n"
)
_LESSONS = (
    "resummarize:\n"
    "  detect:\n"
    "    mirror:\n"
    "      group_key: '^(\\d{8})'\n"
)


def test_report_badges_for_three_level_cascade(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, _ROOT)
    lessons = tmp_path / "Курсы" / "Lessons 2026"
    _folder_yaml(lessons, _LESSONS)
    html_text = _render(tmp_path)
    # root-only keys get ROOT; the lessons override gets HERE; cascaded values
    # get ↑ <ancestor> (root included); parser defaults get `default`
    assert 'class="badge b-root">ROOT' in html_text
    assert 'class="badge b-here">HERE' in html_text
    assert 'class="badge b-inherited"' in html_text and "↑ root" in html_text
    assert 'class="badge b-default">default' in html_text
    # shadows column names the displaced level
    assert "levels this value overrides" in html_text


def test_report_ignored_badge_and_finding(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, "exclude: ['x/**']\n")
    zone = tmp_path / "Zone"
    _folder_yaml(zone, "transcript_dedup:\n  enabled: true\n")
    html_text = _render(tmp_path)
    assert "NON_CASCADING_KEY_IN_SUBFOLDER" in html_text


def test_report_escapes_hostile_folder_names(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, "resummarize:\n  mode: if-missing\n")
    evil = tmp_path / '<img src=x onerror="alert(1)">'
    _folder_yaml(evil, "summarize:\n  profile: article\n")
    html_text = _render(tmp_path)
    assert "<img src=x" not in html_text
    assert "&lt;img src=x" in html_text


def test_report_invalid_file_section(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, ": broken :\n")
    html_text = _render(tmp_path)
    assert "c-invalid" in html_text or "PARSE_ERROR" in html_text


def test_report_deterministic_and_self_contained(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, _ROOT)
    one, two = _render(tmp_path), _render(tmp_path)
    assert one == two  # no timestamps, stable ordering
    assert "Content-Security-Policy" in one and "default-src 'none'" in one
    for marker in ("http://", "https://", "src=", "@import"):
        # no external references (data comes only from our own strings)
        for line in one.splitlines():
            if marker in ("http://", "https://") and marker in line:
                raise AssertionError(f"external ref smuggled in: {line[:120]}")


def test_report_commands_are_shell_quoted(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, "resummarize:\n  mode: if-missing\n")
    zone = tmp_path / "06 - Business Development"
    _folder_yaml(zone, "summarize:\n  profile: meeting\n")
    html_text = _render(tmp_path)
    assert "'06 - Business Development'" in html_text  # shlex-quoted


def test_report_cli_envelope_and_md_projection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _folder_yaml(tmp_path, _ROOT)
    md_path = tmp_path / "Config overview.md"
    code, env = _run(capsys, ["report", "--vault-root", str(tmp_path),
                              "--md", str(md_path)])
    assert code == 0 and env["action"] == "reported"
    out = Path(env["out"])
    assert out == tmp_path / ".wiki" / "config-report.html"
    text = out.read_text(encoding="utf-8")
    assert text.startswith("<!DOCTYPE html>")
    md_text = md_path.read_text(encoding="utf-8")
    assert md_text.startswith("<!-- BEGIN-AUTO:config-overview -->")
    assert "wiki-config tree" in md_text


def test_report_includes_ancestors_of_configured_folders(tmp_path: Path) -> None:
    """Real-vault feedback: the nav must read as a hierarchy — a configured
    deep folder pulls its unconfigured ANCESTORS into the spine."""
    _folder_yaml(tmp_path, _ROOT)
    deep = tmp_path / "03 - Learning" / "Courses" / "Rukovoditel"
    _folder_yaml(deep, "summarize:\n  profile: lesson\n")
    html_text = _render(tmp_path)
    # both intermediate ancestors present, marked as inherited-only (no own file)
    assert "03 - Learning" in html_text and "Courses" in html_text
    assert "inherited only" in html_text
    # unrelated unconfigured folders still hidden by default
    (tmp_path / "Unrelated").mkdir()
    assert "Unrelated" not in _render(tmp_path)


def test_report_nested_root_only_keys_get_root_badge(tmp_path: Path) -> None:
    """Real-vault dogfood bug: /transcript_dedup/enabled rendered an anonymous
    inherited badge — nested pointers of a root-only block must fall back to
    the block's own origin (ROOT), never an empty ↑."""
    _folder_yaml(tmp_path, (
        "transcript_dedup:\n"
        "  enabled: true\n"
        "  identity: before-first-dot\n"
    ))
    html_text = _render(tmp_path)
    assert "↑ </span>" not in html_text and '">↑ <' not in html_text
    # both nested rows (enabled, identity) carry the ROOT badge inherited
    # from the /transcript_dedup block origin
    assert html_text.count('class="badge b-root">ROOT') >= 2


def test_report_all_folders_includes_unconfigured(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, _ROOT)
    (tmp_path / "Plain").mkdir()
    default_html = _render(tmp_path)
    full_html = _render(tmp_path, all_folders=True)
    assert "Plain" not in default_html
    assert "Plain" in full_html


# --------------------------------------------------------------------------- #
# TASK 061 / R-061-6 — FieldSpec.description renders as a row hint
# --------------------------------------------------------------------------- #


def test_report_renders_shipped_zones_advisory_in_the_html(tmp_path: Path) -> None:
    """TC-08-2 — the SHIPPED schema's `/zones` row, asserted in the RENDERED HTML.

    Not a synthetic field: this is the assertion that must FAIL LOUDLY if the
    description does not resolve. A naive `pointer in ui_model` lookup would
    silently render `""` and this test would be the only thing that noticed —
    which is the whole thesis of TASK 061 (a surface that examined nothing and
    reports fine) applied to the fix for it.
    """
    _folder_yaml(tmp_path, "zones: ['Lessons/**']\nexclude: ['_inbox/**']\n")
    (tmp_path / "Lessons").mkdir()
    html = _render(tmp_path)
    assert "<code>/zones</code>" in html
    assert "ADVISORY" in html
    # the hint hangs off the /zones row, not off some other key's
    zones_cell = html.split("<code>/zones</code>", 1)[1].split("</td>", 1)[0]
    assert "ADVISORY" in zones_cell
    assert 'class="hint"' in zones_cell
    # `exclude` DOES scope the walk — it must not inherit the advisory text
    exclude_cell = html.split("<code>/exclude</code>", 1)[1].split("</td>", 1)[0]
    assert "ADVISORY" not in exclude_cell
    assert "pruned from the walk" in exclude_cell


def test_report_escapes_description_html(tmp_path: Path) -> None:
    """TC-08-5 — a description is escaped like every other interpolated string.

    Descriptions are repo-owned (they come from the schema in git, not from a
    vault), so this is defense-in-depth — but `_report.py`'s XSS discipline
    ("every interpolated string is UNTRUSTED") does not carve out exceptions,
    and a future schema could be vendored or operator-overridden.
    """
    from scripts.wiki_skills.wiki_config._report import _row_html

    row = {
        "pointer": "/zones",
        "value": "[]",
        "origin": "root",
        "scope": "root-only",
        "shadows": [],
        "description": "<script>alert(1)</script> & <b>bold</b>",
    }
    html = _row_html(row, ".")
    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&amp;" in html


def test_report_row_without_a_description_renders_no_hint(tmp_path: Path) -> None:
    """A row whose key has no schema description gets NO empty `<p class="hint">`
    (an empty hint element is the silent-empty-string failure, wearing markup)."""
    from scripts.wiki_skills.wiki_config._report import _row_html

    row = {"pointer": "/extensions/text", "value": "[]", "origin": "default",
           "scope": "root-only", "shadows": [], "description": ""}
    assert 'class="hint"' not in _row_html(row, ".")
