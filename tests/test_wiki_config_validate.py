"""TASK 058 Phase 2 — `wiki-config validate`: per-code fixtures, gate semantics,
CWE-209 value-suppression, and the golden run over the real samples/ configs."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from scripts.wiki_skills.wiki_config import main
from scripts.wiki_skills.wiki_config._findings import TAXONOMY, ConfigFinding
from scripts.wiki_skills.wiki_config._lint import lint_vault


def _folder_yaml(d: Path, text: str) -> None:
    (d / ".wiki").mkdir(parents=True, exist_ok=True)
    (d / ".wiki" / "sync.yaml").write_text(text, encoding="utf-8")


def _codes(findings: list[ConfigFinding]) -> set[str]:
    return {f.code for f in findings}


def _by_code(findings: list[ConfigFinding], code: str) -> list[ConfigFinding]:
    return [f for f in findings if f.code == code]


def _run(capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, dict[str, Any]]:
    exit_code = main(argv)
    payload = json.loads(capsys.readouterr().out.strip())
    assert isinstance(payload, dict)
    return exit_code, payload


# --------------------------------------------------------------------------- #
# hard gates (pass 1)
# --------------------------------------------------------------------------- #


def test_parse_error_and_not_a_mapping(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, ": : broken\n")
    sub = tmp_path / "List"
    _folder_yaml(sub, "- just\n- a list\n")
    findings, checked = lint_vault(tmp_path)
    assert checked == 2
    assert _by_code(findings, "PARSE_ERROR")[0].file == ".wiki/sync.yaml"
    assert _by_code(findings, "NOT_A_MAPPING")[0].file == "List/.wiki/sync.yaml"


def test_yaml_anchor_banned(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, "zones: &z ['a/**']\n")
    findings, _ = lint_vault(tmp_path)
    assert _codes(findings) & {"YAML_ANCHOR_BANNED", "YAML_ALIAS_BANNED"}


def test_symlink_refused(tmp_path: Path) -> None:
    outside = tmp_path / "outside.yaml"
    outside.write_text("zones: []\n", encoding="utf-8")
    vault = tmp_path / "vault"
    (vault / ".wiki").mkdir(parents=True)
    os.symlink(outside, vault / ".wiki" / "sync.yaml")
    findings, _ = lint_vault(vault)
    assert "SYMLINK" in _codes(findings)


def test_size_cap(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, "# pad\n" + "#" + "x" * (256 * 1024) + "\n")
    findings, _ = lint_vault(tmp_path)
    assert "SIZE_CAP" in _codes(findings)


def test_enumerate_schema_errors_reapplies_size_cap(tmp_path: Path) -> None:
    """Finding 6a: the schema-error enumeration pass re-reads the file to list
    ALL violations — it must re-apply the loader's 256 KiB cap rather than
    trust the FIRST read, which a TOCTOU swap could have outgrown (an
    anchorless-but-huge document is still expensive to parse)."""
    from scripts.wiki_skills.wiki_config._lint import _Linter, WIKI_SYNC_CONFIG_MAX_BYTES

    _folder_yaml(tmp_path, "zones: []\n")
    oversized = "zones:\n" + "  - 'x'\n" * (WIKI_SYNC_CONFIG_MAX_BYTES // 8 + 100)
    assert len(oversized.encode("utf-8")) > WIKI_SYNC_CONFIG_MAX_BYTES
    (tmp_path / ".wiki" / "sync.yaml").write_text(oversized, encoding="utf-8")

    linter = _Linter(tmp_path, None)
    linter._enumerate_schema_errors(".", tmp_path, ".wiki/sync.yaml")
    assert [f.code for f in linter.findings] == ["PARSE_ERROR"]
    assert linter.findings[0].message == "config changed during lint"


# --------------------------------------------------------------------------- #
# schema enumeration: typo layering (pass 1)
# --------------------------------------------------------------------------- #


def test_unknown_key_typo_vs_unknown_key(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, "zonez: ['a/**']\nxyzzy_qwerty: 1\n")
    findings, _ = lint_vault(tmp_path)
    typos = _by_code(findings, "UNKNOWN_KEY_TYPO")
    unknowns = _by_code(findings, "UNKNOWN_KEY")
    assert len(typos) == 1 and typos[0].data["suggestion"] == "zones"
    assert len(unknowns) == 1 and unknowns[0].data["key"] == "xyzzy_qwerty"
    # never both for one key
    assert typos[0].data["key"] == "zonez"


def test_enum_near_miss_suggestion(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, "summarize:\n  profile: meting\n")
    findings, _ = lint_vault(tmp_path)
    enum = _by_code(findings, "SCHEMA_VIOLATION_ENUM")[0]
    assert enum.pointer == "/summarize/profile"
    assert enum.data["suggestion"] == "meeting"
    # CWE-209: the operator's bad value is not echoed anywhere
    assert "meting" not in json.dumps(enum.to_json())


def test_schema_type_violation_enumerates_all(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, "zones: 'not-a-list'\ntag_namespace: [not, a, string]\n")
    findings, _ = lint_vault(tmp_path)
    types = _by_code(findings, "SCHEMA_VIOLATION_TYPE")
    assert {f.pointer for f in types} == {"/zones", "/tag_namespace"}


# --------------------------------------------------------------------------- #
# per-file advisory (pass 2)
# --------------------------------------------------------------------------- #


def test_empty_file(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, "")
    findings, _ = lint_vault(tmp_path)
    assert "EMPTY_FILE" in _codes(findings)


def test_non_cascading_key_in_subfolder(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, "zones: ['Zone/**']\n")
    sub = tmp_path / "Zone"
    _folder_yaml(sub, "exclude: ['x/**']\ntranscript_dedup:\n  enabled: true\n")
    findings, _ = lint_vault(tmp_path)
    finding = _by_code(findings, "NON_CASCADING_KEY_IN_SUBFOLDER")[0]
    assert finding.file == "Zone/.wiki/sync.yaml"
    assert set(finding.data["keys"]) == {"exclude", "transcript_dedup"}


def test_regex_findings_schema_driven(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, (
        "resummarize:\n"
        "  detect:\n"
        "    mirror:\n"
        "      enabled: true\n"
        "      group_key: '^(unclosed'\n"
    ))
    findings, _ = lint_vault(tmp_path)
    invalid = _by_code(findings, "INVALID_REGEX")[0]
    assert invalid.pointer == "/resummarize/detect/mirror/group_key"
    assert "unclosed" not in json.dumps(invalid.to_json())  # pattern never echoed


def test_group_key_no_capture_and_double_escape(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, (
        "resummarize:\n"
        "  detect:\n"
        "    mirror:\n"
        "      enabled: true\n"
        '      group_key: "^\\\\d+"\n'  # YAML double-quote: loads as ^\d+ (no capture)
    ))
    findings, _ = lint_vault(tmp_path)
    assert "GROUP_KEY_NO_CAPTURE" in _codes(findings)
    sub = tmp_path / "Esc"
    _folder_yaml(sub, (
        "resummarize:\n"
        "  detect:\n"
        "    mirror:\n"
        "      enabled: true\n"
        "      group_key: '^(\\\\d+)'\n"  # single-quote trap: literal backslash
    ))
    findings, _ = lint_vault(tmp_path)
    esc = _by_code(findings, "MIRROR_REGEX_DOUBLE_ESCAPE")
    assert esc and esc[0].file == "Esc/.wiki/sync.yaml"


def test_mirror_ext_no_dot(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, (
        "resummarize:\n"
        "  detect:\n"
        "    mirror:\n"
        "      enabled: true\n"
        "      summary_ext: md\n"
    ))
    findings, _ = lint_vault(tmp_path)
    assert "MIRROR_EXT_NO_DOT" in _codes(findings)


def test_duplicate_list_item(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, "zones: ['a/**', 'a/**']\n")
    findings, _ = lint_vault(tmp_path)
    dup = _by_code(findings, "DUPLICATE_LIST_ITEM")[0]
    assert dup.pointer == "/zones"


def test_zone_glob_no_match_and_live(tmp_path: Path) -> None:
    (tmp_path / "Real").mkdir()
    _folder_yaml(tmp_path, "zones: ['Real/**', 'Ghost/**']\nexclude: ['Nope/**']\n")
    findings, _ = lint_vault(tmp_path)
    zone_hits = _by_code(findings, "ZONE_GLOB_NO_MATCH")
    assert len(zone_hits) == 1 and zone_hits[0].pointer == "/zones/1"
    assert len(_by_code(findings, "EXCLUDE_GLOB_NO_MATCH")) == 1


def test_glob_probe_unbounded_classification() -> None:
    """Finding 6b: only patterns where pathlib CANNOT short-circuit on a
    missing literal prefix (measured: `<literal>/**` resolves in
    microseconds even on a big vault; a leading/un-anchored `**` scales with
    vault size) are flagged as unbounded."""
    from scripts.wiki_skills.wiki_config._lint import _glob_probe_unbounded

    assert _glob_probe_unbounded("_inbox/**") is False
    assert _glob_probe_unbounded("Zone/Sub/**") is False
    assert _glob_probe_unbounded("*.md") is False  # no ** at all
    assert _glob_probe_unbounded("**/x.md") is True
    assert _glob_probe_unbounded("*/**") is True


def test_check_globs_skips_unbounded_pattern_no_full_walk(tmp_path: Path) -> None:
    """A NON-matching un-anchored recursive pattern is silently skipped
    (finding 6b) rather than forcing a full-vault probe on every lint; the
    common `<zone>/**` shape (finding's OWN example) stays checked."""
    _folder_yaml(tmp_path, "zones: ['**/nope.md', 'Ghost/**']\n")
    findings, _ = lint_vault(tmp_path)
    by_pointer = {f.pointer: f.code for f in findings if f.code == "ZONE_GLOB_NO_MATCH"}
    assert "/zones/0" not in by_pointer          # unbounded shape — skipped
    assert by_pointer.get("/zones/1") == "ZONE_GLOB_NO_MATCH"  # bounded — still checked


def test_orphan_wiki_dir(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, "zones: []\n")
    (tmp_path / "Empty" / ".wiki").mkdir(parents=True)
    findings, _ = lint_vault(tmp_path)
    orphan = _by_code(findings, "ORPHAN_WIKI_DIR")[0]
    assert orphan.file == "Empty/.wiki"


# --------------------------------------------------------------------------- #
# cross-level (pass 3)
# --------------------------------------------------------------------------- #


def test_redundant_override_and_list_replace(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, (
        "resummarize:\n"
        "  mode: if-missing\n"
        "  detect:\n"
        "    provenance_ref:\n"
        "      enabled: true\n"
        "      fields: [source, sources]\n"
    ))
    sub = tmp_path / "Zone"
    _folder_yaml(sub, (
        "resummarize:\n"
        "  mode: if-missing\n"          # identical to inherited → redundant
        "  detect:\n"
        "    provenance_ref:\n"
        "      fields: [origin]\n"       # different list → replace shadow
    ))
    findings, _ = lint_vault(tmp_path)
    redundant = _by_code(findings, "REDUNDANT_OVERRIDE")
    assert any(f.pointer == "/resummarize/mode" for f in redundant)
    shadow = _by_code(findings, "LIST_REPLACE_SHADOW")[0]
    assert shadow.pointer == "/resummarize/detect/provenance_ref/fields"
    assert shadow.file == "Zone/.wiki/sync.yaml"


def test_group_key_shadowed_by_inherited_key_block(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, (
        "resummarize:\n"
        "  detect:\n"
        "    mirror:\n"
        "      enabled: true\n"
        "      key:\n"
        "        raw_regex: '^(?P<n>\\d+)'\n"
        "        template: '${n}'\n"
    ))
    sub = tmp_path / "Zone"
    _folder_yaml(sub, (
        "resummarize:\n"
        "  detect:\n"
        "    mirror:\n"
        "      group_key: '^(\\d{8})'\n"
    ))
    findings, _ = lint_vault(tmp_path)
    shadowed = _by_code(findings, "GROUP_KEY_SHADOWED_BY_KEY")
    assert any(f.file == "Zone/.wiki/sync.yaml" for f in shadowed)


def test_mirror_template_group_missing(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, (
        "resummarize:\n"
        "  detect:\n"
        "    mirror:\n"
        "      enabled: true\n"
        "      key:\n"
        "        raw_regex: '^(?P<lesson>\\d+)'\n"
        "        summary_regex: '^(?P<other>\\d+)'\n"
        "        template: '${lesson}'\n"
    ))
    findings, _ = lint_vault(tmp_path)
    missing = _by_code(findings, "MIRROR_TEMPLATE_GROUP_MISSING")
    assert any(f.data.get("side") == "summary" for f in missing)


def test_mirror_dir_outside_vault(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, (
        "resummarize:\n"
        "  detect:\n"
        "    mirror:\n"
        "      enabled: true\n"
        "      summary_dir: '../../outside'\n"
    ))
    findings, _ = lint_vault(tmp_path)
    assert "MIRROR_DIR_OUTSIDE_VAULT" in _codes(findings)


def test_mirror_scope_missing_and_keys_nothing(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, (
        "resummarize:\n"
        "  detect:\n"
        "    mirror:\n"
        "      enabled: true\n"
        "      raw_dirs: [Transcripts]\n"
        "      summary_dir: Summary\n"
    ))
    (tmp_path / "Course" / "Transcripts").mkdir(parents=True)
    findings, _ = lint_vault(tmp_path)
    assert "MIRROR_SCOPE_MISSING" in _codes(findings)
    # now create the scope but with summaries the default key regex cannot key
    summary = tmp_path / "Course" / "Summary"
    summary.mkdir()
    (summary / "no-digits-here.md").write_text("x", encoding="utf-8")
    findings, _ = lint_vault(tmp_path)
    assert "MIRROR_KEYS_NOTHING" in _codes(findings)


def test_shadowed_config(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, "exclude: ['Archive/**']\n")
    sub = tmp_path / "Archive" / "Old"
    _folder_yaml(sub, "summarize:\n  profile: article\n")
    findings, _ = lint_vault(tmp_path)
    shadowed = _by_code(findings, "SHADOWED_CONFIG")[0]
    assert shadowed.file == "Archive/Old/.wiki/sync.yaml"


def test_unsafe_target_subdir_cross_level(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, "summarize:\n  profile: article\n")
    sub = tmp_path / "Zone"
    _folder_yaml(sub, "summarize:\n  target_subdir: '../escape'\n")
    findings, _ = lint_vault(tmp_path)
    assert "UNSAFE_TARGET_SUBDIR" in _codes(findings)


# --------------------------------------------------------------------------- #
# sibling systems
# --------------------------------------------------------------------------- #


def test_layout_and_identity_invalid(tmp_path: Path) -> None:
    (tmp_path / ".wiki").mkdir()
    (tmp_path / ".wiki" / "layout.yaml").write_text(
        "layout:\n  no_such_top_key: {}\n", encoding="utf-8")
    (tmp_path / "WIKI_SCHEMA.md").write_text(
        "---\nvault_id: 42\n---\n", encoding="utf-8")  # vault_id must be a string
    findings, checked = lint_vault(tmp_path)
    codes = _codes(findings)
    assert "LAYOUT_CONFIG_INVALID" in codes
    assert "IDENTITY_CONFIG_INVALID" in codes
    assert checked >= 2


def test_project_override_invalid(tmp_path: Path) -> None:
    (tmp_path / ".wiki.yaml").write_text(": : :\n", encoding="utf-8")
    findings, _ = lint_vault(tmp_path)
    assert "PROJECT_OVERRIDE_INVALID" in _codes(findings)


# --------------------------------------------------------------------------- #
# CLI contract
# --------------------------------------------------------------------------- #


def test_validate_clean_vault_exit_0(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "Zone").mkdir()
    _folder_yaml(tmp_path, "zones: ['Zone/**']\nresummarize:\n  mode: if-missing\n")
    code, env = _run(capsys, ["validate", "--vault-root", str(tmp_path)])
    assert code == 0 and env["ok"] is True
    assert env["action"] == "validated" and env["files_checked"] == 1


def test_validate_error_exit_6_and_strict_promotion(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _folder_yaml(tmp_path, "zones: ['Zone/**']\n")
    (tmp_path / "Zone").mkdir()
    sub = tmp_path / "Zone"
    _folder_yaml(sub, "exclude: ['x/**']\n")  # warning only
    code, env = _run(capsys, ["validate", "--vault-root", str(tmp_path)])
    assert code == 0 and env["by_severity"]["warning"] >= 1
    code, env = _run(capsys, ["validate", "--vault-root", str(tmp_path), "--strict"])
    assert code == 6
    _folder_yaml(sub, "zonez: ['typo']\n")  # error
    code, env = _run(capsys, ["validate", "--vault-root", str(tmp_path)])
    assert code == 6 and env["ok"] is False


def test_validate_sidecar_and_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _folder_yaml(tmp_path, "zonez: []\n")
    sidecar = tmp_path / "f.json"
    report = tmp_path / "f.md"
    code, env = _run(capsys, [
        "validate", "--vault-root", str(tmp_path),
        "--json-sidecar", str(sidecar), "--report", str(report),
    ])
    assert code == 6
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload[0]["code"] == "UNKNOWN_KEY_TYPO"
    assert payload[0]["file_hash"]
    assert "UNKNOWN_KEY_TYPO" in report.read_text(encoding="utf-8")


def test_validate_folder_narrowing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _folder_yaml(tmp_path, "zones: []\n")
    a = tmp_path / "A"
    _folder_yaml(a, "exclude: ['x/**']\n")
    b = tmp_path / "B"
    _folder_yaml(b, "exclude: ['y/**']\n")
    code, env = _run(capsys, ["validate", "A", "--vault-root", str(tmp_path)])
    assert env["by_code"].get("NON_CASCADING_KEY_IN_SUBFOLDER") == 1


# --------------------------------------------------------------------------- #
# taxonomy hygiene + golden run
# --------------------------------------------------------------------------- #


def test_every_emitted_code_is_registered() -> None:
    assert {"UNKNOWN_KEY_TYPO", "MIRROR_KEYS_NOTHING", "SHADOWED_CONFIG"} <= set(TAXONOMY)
    for kind in TAXONOMY.values():
        assert kind.severity in {"error", "warning", "info"}
        assert kind.tier in {"safe", "confirm", "manual"}


@pytest.mark.skipif(
    not (Path(__file__).parent.parent / "samples").is_dir(),
    reason="samples/ scratch tree not present",
)
def test_golden_samples_no_error_findings() -> None:
    """The real dogfood configs must produce NO error-severity sync findings
    (warnings/info are data; sibling-system findings depend on scratch state)."""
    samples = Path(__file__).parent.parent / "samples"
    for vault in ("Demand-generation", "personal-vault-dogfood", "target-obsidian-vault"):
        root = samples / vault
        if not (root / ".wiki" / "sync.yaml").is_file():
            continue
        findings, _ = lint_vault(root)
        errors = [f for f in findings
                  if f.system == "sync" and f.kind.severity == "error"]
        assert errors == [], f"{vault}: {[f.to_json() for f in errors]}"


def test_zone_glob_message_does_not_imply_enforcement(tmp_path: Path) -> None:
    """TC-08-4 (TASK 061 / R-061-6) — `zones` and `exclude` read alike and behave
    nothing alike, and the lint used to give them the SAME message ("matches
    nothing on disk"), which implies `zones` gates something. It gates nothing:
    grep `\\.zones` across `scripts/` — the parse in `sync_config.py` is the only
    read. Only `exclude:` scopes the walk.

    Code / severity / tier are API and stay UNCHANGED (the two tests above assert
    on them); only the operator-facing message changes.
    """
    _folder_yaml(tmp_path, "zones: ['Ghost/**']\nexclude: ['Nope/**']\n")
    findings, _ = lint_vault(tmp_path)

    zone = _by_code(findings, "ZONE_GLOB_NO_MATCH")[0]
    assert zone.pointer == "/zones/0"          # unchanged
    assert zone.kind.severity == "info"        # unchanged
    assert zone.kind.tier == "manual"          # unchanged
    assert "advisory" in zone.message
    assert "never read by the sync walk" in zone.message

    # the ENFORCING sibling must NOT be told it is advisory
    exclude = _by_code(findings, "EXCLUDE_GLOB_NO_MATCH")[0]
    assert exclude.pointer == "/exclude/0"
    assert "advisory" not in exclude.message


# --------------------------------------------------------------------------- #
# TASK 063-03 — TYPED_DIR_NOT_COVERED_BY_LAYOUT: the CROSS-SYSTEM G4 gate
# --------------------------------------------------------------------------- #
#
# Why this finding exists at all, stated once: an uncovered `dirs.*` writes a
# GLOB-INVISIBLE page. `discover_pages` never walks it ⇒ `find_pages_missing_in_index`
# never reports it ⇒ `wiki-lint` raises ZERO issues. Lint is STRUCTURALLY INCAPABLE of
# seeing this loss — the delta property passes perfectly while a decision is gone. This
# gate is the only PREVENTIVE defence, and it must fire at config-edit time, where the
# operator can still act.
#
# ⚠️ Fixtures are PLAN §1's ROSTER. No test here invents its own layout fixture: the
# plan got "which layouts are supported" factually wrong twice, both times by measuring
# ONE of G4's two conjuncts.


def _vault_with_layout(root: Path, layout: str, override: dict[str, Any] | None = None) -> Path:
    (root / "WIKI_SCHEMA.md").write_text(
        f"---\nvault_id: test-vault\nlanguage: en\nlayout: {layout}\n"
        + ("layout_config: .wiki/layout.yaml\n" if override else "")
        + "---\n",
        encoding="utf-8")
    if override:
        import yaml
        (root / ".wiki").mkdir(parents=True, exist_ok=True)
        (root / ".wiki" / "layout.yaml").write_text(
            yaml.safe_dump(override, allow_unicode=True), encoding="utf-8")
    return root


# `para-typed` = obsidian-personal + a `.wiki/layout.yaml` unioning in the typed
# classes. It IS the operator's live vault (PARA, Cyrillic, sibling placement).
_PARA_TYPED = {
    "type_mapping": {
        "decision": {"db_type": "research", "tag": "decision"},
        "requirement": {"db_type": "brief", "tag": "requirement"},
        "risk": {"db_type": "research", "tag": "risk"},
    },
}


def test_typed_dir_not_covered_is_a_finding(tmp_path: Path) -> None:
    """cybos + a Cyrillic folder name ⇒ refused. cybos is STRICT BY DESIGN (its globs
    are root-anchored literals), not broken — and REFUSE, never auto-generate: a
    `sync.yaml` that mutated `layout.yaml` to "fix" this would silently rewrite the
    vault's read grammar for every OTHER tool (Q-063-5 = A).

    MUT: delete `_check_typed_dirs` ⇒ RED.
    """
    _vault_with_layout(tmp_path, "cybos")
    _folder_yaml(tmp_path, "extract_decisions:\n  dirs:\n    decision: 'решения'\n")
    findings, _ = lint_vault(tmp_path)

    hits = _by_code(findings, "TYPED_DIR_NOT_COVERED_BY_LAYOUT")
    assert len(hits) == 1
    assert hits[0].pointer == "/extract_decisions/dirs/decision"
    assert hits[0].kind.severity == "error"
    assert hits[0].kind.tier == "manual"      # never an auto-fix: it is a human choice
    assert hits[0].system == "sync"           # the pointer lives in sync.yaml
    assert hits[0].data["reason"] == "unmatched"


def test_covered_dir_is_clean(tmp_path: Path) -> None:
    """The default cybos names ⇒ ZERO findings of ANY kind. Not "no errors" — a
    spurious warning is a false alarm too, and a gate that cries wolf gets muted."""
    _vault_with_layout(tmp_path, "cybos")
    _folder_yaml(
        tmp_path,
        "extract_decisions:\n  enabled: true\n  dirs:\n"
        "    decision: decisions\n    requirement: requirements\n    risk: risks\n")
    findings, _ = lint_vault(tmp_path)
    assert findings == []


def test_cyrillic_dir_is_clean_on_para_typed(tmp_path: Path) -> None:
    """The SAME Cyrillic name that cybos refuses is CLEAN on the operator's live PARA
    vault, whose generic `[0-9][0-9] - */*/**/*.md` glob makes folder names free.

    Both layouts are correct. The gate's job is to make the difference VISIBLE at
    config time instead of losing pages at write time.
    """
    _vault_with_layout(tmp_path, "obsidian-personal", _PARA_TYPED)
    zone = tmp_path / "06 - BD" / "Acme"
    zone.mkdir(parents=True)
    _folder_yaml(zone, "extract_decisions:\n  enabled: true\n  dirs:\n    decision: 'решения'\n")
    findings, _ = lint_vault(tmp_path)
    assert _by_code(findings, "TYPED_DIR_NOT_COVERED_BY_LAYOUT") == []


def test_raw_dir_name_is_refused_even_though_a_glob_matches(tmp_path: Path) -> None:
    """★ THE C-3 CASE AT THE VALIDATE SURFACE — the whole reason `glob_covers` is the
    full filter chain rather than a `paths[]` match.

    `_raw` MATCHES the PARA glob. A `paths[]`-only gate reports COVERED. But
    `ignore: **/_raw/**` makes the walker skip it, so every decision written there is
    written, never indexed, and raises NO lint issue.

    The message must say WHY — "a glob matches but `ignore` excludes it" — because the
    operator, seeing that a glob plainly matches, would otherwise go widen a glob that
    already matches and never find the real cause.

    MUT: back `glob_covers` with a bare `paths[]` match ⇒ 0 findings ⇒ RED.
    """
    _vault_with_layout(tmp_path, "obsidian-personal", _PARA_TYPED)
    zone = tmp_path / "06 - BD" / "Acme"
    zone.mkdir(parents=True)
    _folder_yaml(zone, "extract_decisions:\n  dirs:\n    decision: '_raw'\n")
    findings, _ = lint_vault(tmp_path)

    hits = _by_code(findings, "TYPED_DIR_NOT_COVERED_BY_LAYOUT")
    assert len(hits) == 1
    assert hits[0].data["reason"] == "ignored"
    assert "ignore" in hits[0].message
    assert "no lint issue" in hits[0].message.lower()


@pytest.mark.parametrize("layout", ["karpathy", "obsidian-personal"])
def test_zero_typed_class_layout_refuses(tmp_path: Path, layout: str) -> None:
    """BOTH zero-typed-class layouts, not one (plan-review C-2b: v1 used STOCK
    obsidian-personal as the *supported* Cyrillic fixture while also declaring
    zero-class layouts refused — two mutually exclusive tests in one bead).

    They fail G4's FIRST conjunct (`type_mapping` maps no typed class), so the folder
    name is moot and the message says so — the operator learns it here rather than at
    the first `prepare`."""
    _vault_with_layout(tmp_path, layout)
    _folder_yaml(tmp_path, "extract_decisions:\n  dirs:\n    decision: decisions\n")
    findings, _ = lint_vault(tmp_path)

    hits = _by_code(findings, "TYPED_DIR_NOT_COVERED_BY_LAYOUT")
    assert len(hits) == 1
    assert hits[0].data["reason"] == "no-typed-classes"
    assert "maps NO typed classes" in hits[0].message


def test_message_never_echoes_an_unsafe_value(tmp_path: Path) -> None:
    """CWE-209/117: the folder name is operator-typed input ⇒ `safe_key`. A value that
    could break out of the report (control chars, a YAML delimiter) must not survive
    into the message."""
    _vault_with_layout(tmp_path, "cybos")
    _folder_yaml(
        tmp_path,
        'extract_decisions:\n  dirs:\n    decision: "evil\\u0007\\nnext"\n')
    findings, _ = lint_vault(tmp_path)
    hits = _by_code(findings, "TYPED_DIR_NOT_COVERED_BY_LAYOUT")
    assert len(hits) == 1
    assert "\n" not in hits[0].message and "\x07" not in hits[0].message
    assert "\n" not in hits[0].data["dir_name"]


def test_absent_block_is_silent(tmp_path: Path) -> None:
    """BACK-COMPAT: a vault with no `extract_decisions` block gets byte-identical
    findings to pre-change. Absence is silent — the finding fires on a key the operator
    typed, never on a default they never chose."""
    _vault_with_layout(tmp_path, "cybos")
    _folder_yaml(tmp_path, "summarize:\n  profile: meeting\n")
    findings, _ = lint_vault(tmp_path)
    assert _by_code(findings, "TYPED_DIR_NOT_COVERED_BY_LAYOUT") == []
