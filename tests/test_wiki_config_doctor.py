"""TASK 058 Phase 3 — doctor/fix/restore/set/unset: the write core.

Load-bearing properties: fix round-trip (finding gone, no new findings, comments
preserved as a CHECKED invariant), idempotency, tier gating (safe vs confirm →
exit 7), TOCTOU drift refusal, backup retention + reversible restore, and the
downgrade path (an unverifiable edit writes NOTHING)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.wiki_skills.wiki_config import main
from scripts.wiki_skills.wiki_config._backups import list_backups
from scripts.wiki_skills.wiki_config._edit import (
    EditDowngrade,
    PointerEdit,
    rewrite_text,
)
from scripts.wiki_skills.wiki_config._lint import lint_vault


def _folder_yaml(d: Path, text: str) -> None:
    (d / ".wiki").mkdir(parents=True, exist_ok=True)
    (d / ".wiki" / "sync.yaml").write_text(text, encoding="utf-8")


def _read(d: Path) -> str:
    return (d / ".wiki" / "sync.yaml").read_text(encoding="utf-8")


def _run(capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, dict[str, Any]]:
    code = main(argv)
    payload = json.loads(capsys.readouterr().out.strip())
    assert isinstance(payload, dict)
    return code, payload


_COMMENTED = (
    "# Root ingest config — the comments are load-bearing.\n"
    "resummarize:\n"
    "  mode: if-missing\n"
    "  detect:\n"
    "    mirror:\n"
    "      enabled: true\n"
    "      raw_dirs: [Transcripts]\n"
    "      # 8-digit DATE prefix, not the lesson number\n"
    "      group_key: '^(\\d{8})'\n"
    "      summary_ext: md\n"
)


# --------------------------------------------------------------------------- #
# the edit sandwich
# --------------------------------------------------------------------------- #


def test_rewrite_preserves_comments_and_layout() -> None:
    new = rewrite_text(_COMMENTED, [PointerEdit("set", "/resummarize/mode", "always")])
    assert "# Root ingest config — the comments are load-bearing." in new
    assert "# 8-digit DATE prefix, not the lesson number" in new
    assert "mode: always" in new
    # untouched value keeps its exact quoting
    assert "'^(\\d{8})'" in new


def test_rewrite_refuses_result_failing_schema() -> None:
    with pytest.raises(EditDowngrade):
        rewrite_text("summarize:\n  profile: auto\n",
                     [PointerEdit("set", "/summarize/profile", "bogus-profile")])


def test_rewrite_set_creates_intermediate_maps() -> None:
    new = rewrite_text("", [PointerEdit("set", "/summarize/profile", "meeting")])
    assert "profile: meeting" in new


# --------------------------------------------------------------------------- #
# fix round-trips per code
# --------------------------------------------------------------------------- #


def _fix_all(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    code, env = _run(capsys, ["fix", "--vault-root", str(tmp_path), "--yes"])
    assert code in (0, 7)
    return env


@pytest.mark.parametrize(
    ("text", "target_code"),
    [
        (_COMMENTED, "MIRROR_EXT_NO_DOT"),                       # safe
        ("zones: ['a/**', 'a/**']\n", "DUPLICATE_LIST_ITEM"),    # safe
        ("resummarize:\n  detect:\n    mirror:\n      enabled: true\n"
         '      group_key: "^\\\\d{8}"\n', "GROUP_KEY_NO_CAPTURE"),  # safe
        ("zonez: ['a/**']\n", "UNKNOWN_KEY_TYPO"),               # confirm
        ("summarize:\n  profile: meting\n", "SCHEMA_VIOLATION_ENUM"),  # confirm
    ],
)
def test_fix_round_trip(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], text: str, target_code: str
) -> None:
    _folder_yaml(tmp_path, text)
    before_findings, _ = lint_vault(tmp_path)
    assert target_code in {f.code for f in before_findings}
    _fix_all(tmp_path, capsys)
    after_findings, _ = lint_vault(tmp_path)
    after_codes = {f.code for f in after_findings}
    assert target_code not in after_codes
    # no NEW error findings introduced
    assert not [f for f in after_findings if f.kind.severity == "error"]
    # comments survive edits on the commented fixture
    if text is _COMMENTED:
        assert "# 8-digit DATE prefix, not the lesson number" in _read(tmp_path)


def test_fix_non_cascading_key_delete(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _folder_yaml(tmp_path, "zones: ['Zone/**']\n")
    zone = tmp_path / "Zone"
    _folder_yaml(zone, "exclude: ['x/**']\nsummarize:\n  profile: lesson\n")
    env = _fix_all(tmp_path, capsys)
    after = _read(zone)
    assert "exclude" not in after and "profile: lesson" in after
    zone_result = next(f for f in env["files"] if f["file"].startswith("Zone/"))
    assert zone_result["backup"]  # original preserved in backups


def test_fix_empty_file_and_orphan_dir(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _folder_yaml(tmp_path, "")
    (tmp_path / "Empty" / ".wiki").mkdir(parents=True)
    _fix_all(tmp_path, capsys)
    assert not (tmp_path / ".wiki" / "sync.yaml").exists()
    assert not (tmp_path / "Empty" / ".wiki").exists()


def test_fix_anchor_expansion_bounded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _folder_yaml(tmp_path, "zones: &z ['a/**']\nexclude: *z\n")
    env = _fix_all(tmp_path, capsys)
    after = _read(tmp_path)
    assert "&z" not in after and "*z" not in after
    findings, _ = lint_vault(tmp_path)
    assert "YAML_ANCHOR_BANNED" not in {f.code for f in findings}
    assert any(r["applied"] for r in env["files"])


def test_fix_idempotent_second_run_noop(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _folder_yaml(tmp_path, _COMMENTED)
    _fix_all(tmp_path, capsys)
    backups_after_first = len(list_backups(tmp_path))
    code, env = _run(capsys, ["fix", "--vault-root", str(tmp_path), "--yes"])
    assert code == 0
    assert all(not f["applied"] for f in env["files"]) or env["files"] == []
    assert len(list_backups(tmp_path)) == backups_after_first  # no new backup


def test_fix_tier_gating_exit_7_without_yes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # one safe (ext no dot) + one confirm (typo key) in the same vault
    _folder_yaml(tmp_path, _COMMENTED)
    zone = tmp_path / "Zone"
    _folder_yaml(zone, "zonez: []\n")
    code, env = _run(capsys, ["fix", "--vault-root", str(tmp_path)])
    assert code == 7
    root_result = next(f for f in env["files"] if f["file"] == ".wiki/sync.yaml")
    assert any(a["code"] == "MIRROR_EXT_NO_DOT" for a in root_result["applied"])
    zone_result = next(f for f in env["files"] if f["file"].startswith("Zone/"))
    assert zone_result["status"] == "confirm-required"
    assert "zonez" in _read(zone)  # untouched


def test_fix_dry_run_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _folder_yaml(tmp_path, _COMMENTED)
    before = _read(tmp_path)
    code, env = _run(capsys, ["fix", "--vault-root", str(tmp_path), "--dry-run", "--yes"])
    assert code == 0 and env["dry_run"] is True
    assert _read(tmp_path) == before
    assert list_backups(tmp_path) == []


def test_fix_from_plan_toctou_drift_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _folder_yaml(tmp_path, "zonez: []\n")
    sidecar = tmp_path / "plan.json"
    code, _ = _run(capsys, ["validate", "--vault-root", str(tmp_path),
                            "--json-sidecar", str(sidecar)])
    assert code == 6
    _folder_yaml(tmp_path, "zonez: []\n# drifted\n")  # mutate after planning
    before = _read(tmp_path)
    code, env = _run(capsys, ["fix", "--vault-root", str(tmp_path),
                              "--from-plan", str(sidecar), "--yes"])
    assert code == 2 and env["error"] == "CONFIG_DRIFTED"
    assert _read(tmp_path) == before          # zero writes
    assert list_backups(tmp_path) == []       # zero backups


def test_fix_downgrade_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A typo key whose REAL name contains a non-printable char: the sanitized
    pointer cannot address it, so the rename is unverifiable: downgraded, and
    NOTHING is written (the file stays byte-identical)."""
    _folder_yaml(tmp_path, '"zone\\x01s": []\n')  # PyYAML double-quote escape
    before = _read(tmp_path)
    code, env = _run(capsys, ["fix", "--vault-root", str(tmp_path), "--yes"])
    result = env["files"][0]
    assert result["fix_downgraded"] is True and result["status"] == "manual"
    assert _read(tmp_path) == before


def test_fix_drift_between_compute_and_write_consumes_no_backup_slot(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 9a (doctor spot): the TOCTOU re-read must run BEFORE the backup
    write — a drift-aborted fix must not consume a `.wiki/backups/` KEEP slot."""
    import scripts.wiki_skills.wiki_config._doctor as doctor_mod

    _folder_yaml(tmp_path, _COMMENTED)  # a single SAFE, edit-kind finding
    real_rewrite = doctor_mod.rewrite_text

    def _drift_after_rewrite(work: str, edits: Any, **kwargs: Any) -> str:
        result = real_rewrite(work, edits, **kwargs)
        # simulate an external writer landing between the plan being computed
        # and the (pre-fix) backup step
        (tmp_path / ".wiki" / "sync.yaml").write_text(
            work + "# drifted externally\n", encoding="utf-8")
        return result

    monkeypatch.setattr(doctor_mod, "rewrite_text", _drift_after_rewrite)
    code, env = _run(capsys, ["fix", "--vault-root", str(tmp_path), "--yes"])
    root_result = next(f for f in env["files"] if f["file"] == ".wiki/sync.yaml")
    assert root_result["status"] == "drifted"
    assert list_backups(tmp_path) == []


# --------------------------------------------------------------------------- #
# --from-plan hash_precheck envelope field (finding 9b)
# --------------------------------------------------------------------------- #


def test_fix_from_plan_with_hashes_precheck_ok(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _folder_yaml(tmp_path, _COMMENTED)
    sidecar = tmp_path / "plan.json"
    code, _ = _run(capsys, ["validate", "--vault-root", str(tmp_path),
                            "--json-sidecar", str(sidecar)])
    assert code == 6
    code, env = _run(capsys, ["fix", "--vault-root", str(tmp_path),
                              "--from-plan", str(sidecar), "--yes"])
    assert code == 0
    assert env["hash_precheck"] == "ok"


def test_fix_from_plan_hashless_sidecar_precheck_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _folder_yaml(tmp_path, _COMMENTED)
    sidecar = tmp_path / "plan.json"
    sidecar.write_text(json.dumps([
        {"code": "MIRROR_EXT_NO_DOT", "system": "sync",
         "file": ".wiki/sync.yaml",
         "pointer": "/resummarize/detect/mirror/summary_ext",
         "message": "missing dot"},  # no file_hash key at all
    ]), encoding="utf-8")
    code, env = _run(capsys, ["fix", "--vault-root", str(tmp_path),
                              "--from-plan", str(sidecar), "--yes"])
    assert code == 0
    assert env["hash_precheck"] == "skipped-no-hashes"


def test_fix_without_from_plan_omits_hash_precheck(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _folder_yaml(tmp_path, _COMMENTED)
    code, env = _run(capsys, ["fix", "--vault-root", str(tmp_path), "--yes"])
    assert "hash_precheck" not in env


# --------------------------------------------------------------------------- #
# backups + restore
# --------------------------------------------------------------------------- #


def test_backup_retention_prunes_to_10(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _folder_yaml(tmp_path, "summarize:\n  profile: auto\n")
    for i in range(12):
        profile = ["auto", "meeting", "lesson", "article"][i % 4]
        code, _ = _run(capsys, ["set", ".", "/summarize/profile", profile,
                                "--vault-root", str(tmp_path)])
        assert code == 0
    assert len(list_backups(tmp_path)) == 10


def test_restore_round_trip_and_reversible(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    original = "# precious comment\nsummarize:\n  profile: meeting\n"
    _folder_yaml(tmp_path, original)
    code, _ = _run(capsys, ["set", ".", "/summarize/profile", "article",
                            "--vault-root", str(tmp_path)])
    assert code == 0 and "article" in _read(tmp_path)
    # without --yes → plan + exit 7, nothing changed
    code, env = _run(capsys, ["restore", ".", "--vault-root", str(tmp_path)])
    assert code == 7 and env["action"] == "restore-plan"
    assert "article" in _read(tmp_path)
    # with --yes → byte-exact restore, current state itself backed up
    code, env = _run(capsys, ["restore", ".", "--vault-root", str(tmp_path), "--yes"])
    assert code == 0
    assert _read(tmp_path) == original
    assert env["backup_of_current"] and env["restored_file_valid"] is True
    # the pre-restore state is itself restorable (reversibility)
    assert any("sync.yaml" in e.name for e in list_backups(tmp_path))


def test_restore_no_backups_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _folder_yaml(tmp_path, "zones: []\n")
    code, env = _run(capsys, ["restore", ".", "--vault-root", str(tmp_path), "--yes"])
    assert code == 2 and env["error"] == "NO_BACKUPS"


def test_restore_oldest_backup_when_keep_full_byte_exact(tmp_path: Path) -> None:
    """A full KEEP=10 backup set + a live file: restoring the OLDEST backup
    must not destroy it. `restore_backup`'s own backup-of-current step prunes
    the oldest entry — exactly `source` when the oldest is what's being
    restored — so the source content must be read into memory BEFORE that
    prune runs, or the restore raises FileNotFoundError and loses the data."""
    from scripts.wiki_skills.wiki_config._backups import (
        list_backups,
        restore_backup,
        write_backup,
    )

    _folder_yaml(tmp_path, "summarize:\n  profile: auto\n")
    gens = []
    for i in range(10):
        text = f"summarize:\n  profile: auto\n# gen {i}\n"
        _folder_yaml(tmp_path, text)
        write_backup(tmp_path)  # backs up THIS generation's content
        gens.append(text)
    entries = list_backups(tmp_path)
    assert len(entries) == 10
    oldest = entries[-1]  # list_backups sorts newest-first (reverse=True)

    restored_from, backup_of_current = restore_backup(tmp_path, oldest.name)

    assert restored_from == oldest.name
    assert backup_of_current is not None  # the live file (gen 9) got backed up
    assert _read(tmp_path) == gens[0]  # byte-exact restore of the oldest gen
    # the 11th backup-of-current write pruned the true oldest entry — the
    # live restore succeeded ONLY because its content was captured first
    assert oldest.name not in {e.name for e in list_backups(tmp_path)}


# --------------------------------------------------------------------------- #
# ensure_wiki_writable — the CWE-59 write-path guard
# --------------------------------------------------------------------------- #


def test_ensure_wiki_writable_refuses_symlinked_wiki_dir(tmp_path: Path) -> None:
    import os

    from scripts.wiki_skills.wiki_config._backups import (
        WikiDirSymlinkError,
        ensure_wiki_writable,
    )

    vault = tmp_path / "vault"
    zone = vault / "Zone"
    zone.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, zone / ".wiki")
    with pytest.raises(WikiDirSymlinkError):
        ensure_wiki_writable(zone, vault)


def test_ensure_wiki_writable_refuses_symlinked_leaf(tmp_path: Path) -> None:
    import os

    from scripts.wiki_skills.wiki_config._backups import (
        WikiDirSymlinkError,
        ensure_wiki_writable,
    )

    vault = tmp_path / "vault"
    zone = vault / "Zone"
    (zone / ".wiki").mkdir(parents=True)
    outside_file = tmp_path / "planted.yaml"
    outside_file.write_text("zones: []\n", encoding="utf-8")
    os.symlink(outside_file, zone / ".wiki" / "sync.yaml")
    with pytest.raises(WikiDirSymlinkError):
        ensure_wiki_writable(zone, vault)


def test_ensure_wiki_writable_refuses_resolved_escape(tmp_path: Path) -> None:
    """Neither `.wiki` nor the leaf is ITSELF a symlink, but `folder` resolves
    outside the vault (the TOCTOU window a caller must re-check even when it
    already validated `folder` earlier) — the resolved-target check catches
    what the two leaf-level checks alone would miss."""
    import os

    from scripts.wiki_skills.wiki_config._backups import (
        WikiDirSymlinkError,
        ensure_wiki_writable,
    )

    vault = tmp_path / "vault"
    vault.mkdir()
    outside_zone = tmp_path / "outside_zone"
    (outside_zone / ".wiki").mkdir(parents=True)
    zone_link = vault / "Zone"
    os.symlink(outside_zone, zone_link)
    with pytest.raises(WikiDirSymlinkError):
        ensure_wiki_writable(zone_link, vault)


def test_ensure_wiki_writable_allows_ordinary_folder(tmp_path: Path) -> None:
    from scripts.wiki_skills.wiki_config._backups import ensure_wiki_writable

    vault = tmp_path / "vault"
    zone = vault / "Zone"
    (zone / ".wiki").mkdir(parents=True)
    (zone / ".wiki" / "sync.yaml").write_text("zones: []\n", encoding="utf-8")
    ensure_wiki_writable(zone, vault)  # no raise
    ensure_wiki_writable(vault / "Never-Configured", vault)  # .wiki absent — fine


# --------------------------------------------------------------------------- #
# set / unset
# --------------------------------------------------------------------------- #


def test_set_preserves_comments(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _folder_yaml(tmp_path, _COMMENTED)
    code, env = _run(capsys, ["set", ".", "/resummarize/mode", "always",
                              "--vault-root", str(tmp_path)])
    assert code == 0 and env["backup"]
    after = _read(tmp_path)
    assert "# 8-digit DATE prefix, not the lesson number" in after
    assert "mode: always" in after


def test_set_drift_between_compute_and_write_consumes_no_backup_slot(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 9a (set/unset spot): the TOCTOU re-read must run BEFORE the
    backup write in `_apply_single_edit` — a drift-aborted set must not
    consume a `.wiki/backups/` KEEP slot."""
    import scripts.wiki_skills.wiki_config as wc

    _folder_yaml(tmp_path, "summarize:\n  profile: auto\n")
    real_rewrite = wc.rewrite_text

    def _drift_after_rewrite(before: str, edits: Any, **kwargs: Any) -> str:
        result = real_rewrite(before, edits, **kwargs)
        (tmp_path / ".wiki" / "sync.yaml").write_text(
            before + "# drifted externally\n", encoding="utf-8")
        return result

    monkeypatch.setattr(wc, "rewrite_text", _drift_after_rewrite)
    code, env = _run(capsys, ["set", ".", "/summarize/profile", "meeting",
                              "--vault-root", str(tmp_path)])
    assert code == 2 and env["error"] == "CONFIG_DRIFTED"
    assert list_backups(tmp_path) == []


def test_set_root_only_key_in_subfolder_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    zone = tmp_path / "Zone"
    zone.mkdir()
    code, env = _run(capsys, ["set", "Zone", "/exclude", "['x/**']",
                              "--vault-root", str(tmp_path)])
    assert code == 2 and env["error"] == "SCOPE_ROOT_ONLY"
    assert not (zone / ".wiki").exists()


def test_set_unknown_pointer_suggests(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, env = _run(capsys, ["set", ".", "/summarize/profil", "meeting",
                              "--vault-root", str(tmp_path)])
    assert code == 2 and env["error"] == "UNKNOWN_POINTER"
    assert "/summarize/profile" in env["did_you_mean"]


def test_set_invalid_enum_value_exit_6_nothing_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _folder_yaml(tmp_path, "summarize:\n  profile: auto\n")
    before = _read(tmp_path)
    code, env = _run(capsys, ["set", ".", "/summarize/profile", "bogus",
                              "--vault-root", str(tmp_path)])
    assert code == 6
    assert _read(tmp_path) == before
    assert "bogus" not in json.dumps(env)  # CWE-209


def test_set_creates_file_in_unconfigured_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    zone = tmp_path / "Встречи BD"
    zone.mkdir()
    code, env = _run(capsys, ["set", "Встречи BD", "/summarize/extract_concepts",
                              "false", "--vault-root", str(tmp_path)])
    assert code == 0 and env["backup"] is None
    text = (zone / ".wiki" / "sync.yaml").read_text(encoding="utf-8")
    assert "extract_concepts: false" in text


def test_unset_and_missing_pointer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _folder_yaml(tmp_path, "summarize:\n  profile: meeting\n  diagrams: true\n")
    code, env = _run(capsys, ["unset", ".", "/summarize/diagrams",
                              "--vault-root", str(tmp_path)])
    assert code == 0
    assert "diagrams" not in _read(tmp_path)
    code, env = _run(capsys, ["unset", ".", "/summarize/diagrams",
                              "--vault-root", str(tmp_path)])
    assert code == 2 and env["error"] == "EDIT_REFUSED"


def test_ensure_wiki_writable_refuses_symlinked_backups_dir(tmp_path: Path) -> None:
    """vdd-multi iteration-2: the `backups/` leg is an escape one level down —
    `.wiki` and the leaf are real, `backups/` links outside the vault."""
    import os

    from scripts.wiki_skills.wiki_config._backups import (
        WikiDirSymlinkError, ensure_wiki_writable)

    vault = tmp_path / "vault"
    zone = vault / "Zone"
    (zone / ".wiki").mkdir(parents=True)
    (zone / ".wiki" / "sync.yaml").write_text("zones: []\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, zone / ".wiki" / "backups")
    with pytest.raises(WikiDirSymlinkError):
        ensure_wiki_writable(zone, vault)
