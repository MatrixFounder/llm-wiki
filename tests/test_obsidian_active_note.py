"""Contract test for the obsidian-active-note resolver (TASK 041).

Deterministic — no live Obsidian. The resolver's single obsidian-invocation seam
(``_run_obsidian``) is monkeypatched with canned output drawn from the REAL captured
fixtures under ``skills/obsidian-cli/evals/fixtures/`` (provenance: obsidian 1.12.7,
2026-06-20). Asserts the parsers, the resolver chain, the F-1 wrong-target guard, and the
typed exit-code map.
"""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

_REPO = Path(__file__).resolve().parents[1]
_MOD_PATH = _REPO / "skills" / "obsidian-cli" / "scripts" / "obsidian_active_note.py"
_FIX = _REPO / "skills" / "obsidian-cli" / "evals" / "fixtures"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("obsidian_active_note", _MOD_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


oan = _load()


def _fix(name: str) -> str:
    return (_FIX / name).read_text()


_ROOT = "/Users/sergey/dev-projects/obsidian-llm-wiki"
# inline data (format derived from the real captures)
_TABS_WITH_NOTES = (
    "[markdown] GitHub Setup\n[markdown] Weekly Review\n"
    "[file-explorer] Файловый менеджер\n[search] Поиск\n"
)
_TABS_DUP_TITLE = "[markdown] Notes\n[markdown] Notes\n[search] Поиск\n"
_TSV_GH = "path\tDev/GitHub Setup.md\nname\tGitHub Setup\nextension\tmd\n"
_TSV_WR = "path\tNotes/Weekly Review.md\nname\tWeekly Review\nextension\tmd\n"


def _runner(mapping: dict[tuple[str, ...], tuple[str, int]]):
    """Build a fake _run_obsidian keyed on a tuple-prefix of the obsidian args."""

    def fake(args: list[str], *, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
        for key, (out, rc) in mapping.items():
            if tuple(args[: len(key)]) == key:
                return subprocess.CompletedProcess(args, rc, stdout=out, stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    return fake


_VAULT_OK = {
    ("vault", "info=path"): (_ROOT + "\n", 0),
    ("vault", "info=name"): ("obsidian-llm-wiki\n", 0),
}


def _patch(monkeypatch: pytest.MonkeyPatch, mapping: dict) -> None:
    monkeypatch.setattr(oan.shutil, "which", lambda _: "/usr/local/bin/obsidian")
    monkeypatch.setattr(oan, "_run_obsidian", _runner(mapping))


# ── parsers ─────────────────────────────────────────────────────────────────────
def test_parse_file_info_extracts_path() -> None:
    info = oan.parse_file_info(_fix("obsidian-file-active.tsv"))
    assert info["path"] == "README.md" and info["name"] == "README" and info["extension"] == "md"


def test_parse_tabs_real_fixture_has_no_markdown_notes() -> None:
    tabs = oan.parse_tabs(_fix("obsidian-tabs.txt"))
    assert len(tabs) == 10 and all("view_type" in t and "title" in t for t in tabs)
    assert oan.markdown_tabs(tabs) == []  # the live capture had no note open


def test_parse_tabs_ids_fixture_carries_id() -> None:
    assert all(t.get("id") for t in oan.parse_tabs(_fix("obsidian-tabs-ids.txt")))


def test_parse_tabs_id_anchored_not_title_split() -> None:
    # a trailing `\t<hex>` is the id; a tab elsewhere does NOT truncate the title
    tabs = oan.parse_tabs("[markdown] Plan\t4d0605ab76e1e572\n[markdown] A B C\n")
    assert tabs[0] == {"view_type": "markdown", "title": "Plan", "id": "4d0605ab76e1e572"}
    assert tabs[1] == {"view_type": "markdown", "title": "A B C"}


def test_markdown_tabs_filters_to_notes() -> None:
    md = oan.markdown_tabs(oan.parse_tabs(_TABS_WITH_NOTES))
    assert [t["title"] for t in md] == ["GitHub Setup", "Weekly Review"]


def test_match_descriptor_unique_and_none_and_many() -> None:
    md = oan.markdown_tabs(oan.parse_tabs(_TABS_WITH_NOTES))
    assert [t["title"] for t in oan.match_descriptor(md, "github")] == ["GitHub Setup"]
    assert oan.match_descriptor(md, "nonexistent topic") == []  # → LOW (ask)
    dup = oan.markdown_tabs(oan.parse_tabs(_TABS_DUP_TITLE))
    assert len(oan.match_descriptor(dup, "notes")) == 2  # → LOW (ask)


def test_detect_vault_from_cwd_matches(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    (tmp_path / ".obsidian").mkdir()  # mark tmp_path as a vault root
    monkeypatch.setattr(oan.shutil, "which", lambda _: "/usr/local/bin/obsidian")
    monkeypatch.setattr(oan, "_run_obsidian", _runner({
        ("vaults", "verbose"): (f"Other\t/somewhere/else\nMyVault\t{tmp_path}\n", 0),
    }))
    assert oan.detect_vault_from_cwd(str(tmp_path)) == "MyVault"
    # a deeper CWD inside the vault walks UP to the .obsidian root and still matches
    assert oan.detect_vault_from_cwd(str(tmp_path / "sub" / "deep")) == "MyVault"


def test_detect_vault_from_cwd_outside_any_vault(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(oan.shutil, "which", lambda _: "/usr/local/bin/obsidian")
    monkeypatch.setattr(oan, "_run_obsidian", _runner({("vaults", "verbose"): ("V\t/elsewhere\n", 0)}))
    assert oan.detect_vault_from_cwd(str(tmp_path)) is None  # no .obsidian above tmp_path → None


def test_vault_basename_count(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, {("files", "ext=md"): (_fix("obsidian-files-md.txt"), 0)})
    assert oan.vault_basename_count("GitHub Setup") == 2  # Dev/ + Archive/ → duplicate
    assert oan.vault_basename_count("Weekly Review") == 1
    assert oan.vault_basename_count("Nonexistent") == 0


# ── resolvers ───────────────────────────────────────────────────────────────────
def test_resolve_focused_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, {("file",): (_fix("obsidian-file-active.tsv"), 0), **_VAULT_OK})
    res = oan.resolve_focused()
    assert res["path"] == "README.md"
    assert res["abs"] == _ROOT + "/README.md"
    assert res["vault"] == "obsidian-llm-wiki"


def test_resolve_focused_no_active_file(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, {("file",): (_fix("obsidian-file-no-active.txt"), 0)})
    with pytest.raises(oan.ResolveError) as ei:
        oan.resolve_focused()
    assert ei.value.code == oan.EXIT_NO_ACTIVE_FILE


def test_resolve_title_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    # real `Error: File "X" not found.` fixture (rc=0) → anchored Error: prefix → NO_ACTIVE_FILE
    _patch(monkeypatch, {("file",): (_fix("obsidian-file-not-found.txt"), 0)})
    with pytest.raises(oan.ResolveError) as ei:
        oan.resolve_title("NoSuchNote")
    assert ei.value.code == oan.EXIT_NO_ACTIVE_FILE


def test_resolve_focused_app_not_running(monkeypatch: pytest.MonkeyPatch) -> None:
    # completed call, no Error: prefix, no parseable path → APP_NOT_RUNNING (not a false NO_ACTIVE_FILE)
    _patch(monkeypatch, {("file",): ("", 0)})
    with pytest.raises(oan.ResolveError) as ei:
        oan.resolve_focused()
    assert ei.value.code == oan.EXIT_APP_NOT_RUNNING


def test_resolve_focused_non_absolute_root(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, {("file",): (_fix("obsidian-file-active.tsv"), 0),
                         ("vault", "info=path"): ("", 0), ("vault", "info=name"): ("v\n", 0)})
    with pytest.raises(oan.ResolveError) as ei:
        oan.resolve_focused()
    assert ei.value.code == oan.EXIT_APP_NOT_RUNNING


def test_resolve_focused_recent_open_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    # No active FILE (focused leaf is the integrated terminal) → fall back to the most-recent
    # OPEN note (recents ∩ tabs), resolved by exact path=, tagged source=recent-open.
    rel = "05 - Материалы/Разработка/Версии в GitHub.md"
    tsv = f"path\t{rel}\nname\tВерсии в GitHub\nextension\tmd\n"

    def fake(args: list[str], *, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
        if args == ["file"]:  # active file → none (terminal focused)
            return subprocess.CompletedProcess(args, 0, stdout="Error: No active file.", stderr="")
        if args[:1] == ["file"] and any(a.startswith("path=") for a in args):
            return subprocess.CompletedProcess(args, 0, stdout=tsv, stderr="")
        if args == ["tabs"]:
            return subprocess.CompletedProcess(args, 0, stdout="[markdown] Версии в GitHub\n", stderr="")
        if args == ["recents"]:
            return subprocess.CompletedProcess(args, 0, stdout=f"{rel}\n05 - Материалы/Разработка.base\n", stderr="")
        if args == ["vault", "info=path"]:
            return subprocess.CompletedProcess(args, 0, stdout=_ROOT + "\n", stderr="")
        if args == ["vault", "info=name"]:
            return subprocess.CompletedProcess(args, 0, stdout="ObsidianNotes-Test\n", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(oan.shutil, "which", lambda _: "/usr/local/bin/obsidian")
    monkeypatch.setattr(oan, "_run_obsidian", fake)
    res = oan.resolve_focused()
    assert res["source"] == "recent-open"
    assert res["path"] == rel
    assert res["abs"].endswith(rel)


def test_resolve_focused_no_active_and_no_open_recent_reraises(monkeypatch: pytest.MonkeyPatch) -> None:
    # No active file AND no recent note that is also open → still NO_ACTIVE_FILE (no false hit)
    _patch(monkeypatch, {("file",): (_fix("obsidian-file-no-active.txt"), 0)})  # tabs/recents → "" (empty)
    with pytest.raises(oan.ResolveError) as ei:
        oan.resolve_focused()
    assert ei.value.code == oan.EXIT_NO_ACTIVE_FILE


def test_not_found_substring_in_name_is_not_a_false_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    # a real note literally named "Bug not found" must resolve OK (no unanchored substring trap)
    tsv = "path\tBugs/Bug not found.md\nname\tBug not found\nextension\tmd\n"
    _patch(monkeypatch, {("file",): (tsv, 0), **_VAULT_OK})
    assert oan.resolve_focused()["path"] == "Bugs/Bug not found.md"


# ── CLI exit-code map ───────────────────────────────────────────────────────────
def test_cli_focused_ok_after_position(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _patch(monkeypatch, {("file",): (_fix("obsidian-file-active.tsv"), 0), **_VAULT_OK})
    assert oan.main(["focused", "--format", "path"]) == oan.EXIT_OK  # option AFTER subcommand
    assert "README.md" in capsys.readouterr().out


def test_cli_option_before_subcommand(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, {("file",): (_fix("obsidian-file-active.tsv"), 0), **_VAULT_OK})
    assert oan.main(["--expect-vault", "obsidian-llm-wiki", "focused"]) == oan.EXIT_OK  # option BEFORE


def test_cli_cli_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oan.shutil, "which", lambda _: None)
    assert oan.main(["focused"]) == oan.EXIT_CLI_ABSENT


def test_cli_vault_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, {("file",): (_fix("obsidian-file-active.tsv"), 0), **_VAULT_OK})
    assert oan.main(["--expect-vault", "some-other-vault", "focused"]) == oan.EXIT_VAULT_MISMATCH


def test_cli_vault_mismatch_fail_closed_on_empty_vault(monkeypatch: pytest.MonkeyPatch) -> None:
    # vault info=name empty + --expect-vault set → fail-CLOSED (mismatch), never silent pass
    _patch(monkeypatch, {("file",): (_fix("obsidian-file-active.tsv"), 0),
                         ("vault", "info=path"): (_ROOT + "\n", 0), ("vault", "info=name"): ("", 0)})
    assert oan.main(["--expect-vault", "x", "focused"]) == oan.EXIT_VAULT_MISMATCH


def test_cli_match_unique_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, {
        ("tabs",): (_TABS_WITH_NOTES, 0),
        ("file",): (_TSV_WR, 0),  # resolves to Notes/Weekly Review.md (unique basename)
        ("files", "ext=md"): (_fix("obsidian-files-md.txt"), 0),
        **_VAULT_OK,
    })
    assert oan.main(["match", "--descriptor", "weekly"]) == oan.EXIT_OK


def test_cli_match_resolved_duplicate_basename_ambiguous(monkeypatch: pytest.MonkeyPatch) -> None:
    # F-1 guard: descriptor uniquely matches ONE open tab, but file=<title> resolves to a
    # basename shared by another vault file → cannot prove it's the open tab → AMBIGUOUS (ASK)
    _patch(monkeypatch, {
        ("tabs",): (_TABS_WITH_NOTES, 0),
        ("file",): (_TSV_GH, 0),  # Dev/GitHub Setup.md — but Archive/GitHub Setup.md also exists
        ("files", "ext=md"): (_fix("obsidian-files-md.txt"), 0),
        **_VAULT_OK,
    })
    assert oan.main(["match", "--descriptor", "github"]) == oan.EXIT_AMBIGUOUS


def test_cli_match_zero_basename_count_is_fail_safe_ambiguous(monkeypatch: pytest.MonkeyPatch) -> None:
    # F-1 guard fail-SAFE (critic LOW-R1 / security Gap-B): if `files ext=md` can't corroborate
    # the resolved basename (empty/glitch → count 0), the no-ask path must NOT proceed.
    _patch(monkeypatch, {
        ("tabs",): (_TABS_WITH_NOTES, 0),
        ("file",): (_TSV_WR, 0),
        ("files", "ext=md"): ("", 0),  # empty listing → count 0 → cannot prove uniqueness
        **_VAULT_OK,
    })
    assert oan.main(["match", "--descriptor", "weekly"]) == oan.EXIT_AMBIGUOUS


def test_cli_match_ambiguous_open_tabs(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, {("tabs",): (_TABS_DUP_TITLE, 0)})
    assert oan.main(["match", "--descriptor", "notes"]) == oan.EXIT_AMBIGUOUS


def test_cli_match_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, {("tabs",): (_TABS_WITH_NOTES, 0)})
    assert oan.main(["match", "--descriptor", "nothing here"]) == oan.EXIT_NO_ACTIVE_FILE


def test_cli_headless_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oan.shutil, "which", lambda _: "/usr/local/bin/obsidian")
    monkeypatch.setenv("WIKI_HEADLESS", "1")
    assert oan.main(["focused"]) == oan.EXIT_HEADLESS
