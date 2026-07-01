"""Vendor-agnostic external-skill bin resolution (`resolve_skill_bin` + `_discover_skill_roots`).

The acquire skills (html/pdf/pptx/transcript-fetcher) live in a per-harness skills dir
(~/.claude, ~/.pi, ~/.codex, … — and future harnesses) and are named differently per harness
(the html skill dir is `html` on Claude but `html2md` on pi). Resolution must not assume Claude
Code NOR a fixed harness roster:
  $WIKI_<BIN>  →  DISCOVERED roots ($WIKI_SKILLS_DIRS + every `<dotdir>/skills` + XDG) → best-effort.
The `--*-bin` CLI flag overrides it entirely (tested elsewhere).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.wiki_skills.wiki_import_article import _fetch

_ALL_WIKI_ENV = ("WIKI_HTML_BIN", "WIKI_PDF_EXTRACT_BIN", "WIKI_SOFFICE_WRAPPER",
                 "WIKI_TRANSCRIPT_BIN", "WIKI_VTT_CLEANER", "WIKI_SKILLS_DIRS")


def _isolate(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    """Point discovery at a throw-away $HOME and clear every WIKI_*/XDG override."""
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))
    for v in _ALL_WIKI_ENV:
        monkeypatch.delenv(v, raising=False)


def _make_skill(home: Path, harness: str, skill_dir: str, rel: str) -> Path:
    p = home / harness / "skills" / skill_dir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    return p


def test_env_var_overrides_and_expands(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WIKI_HTML_BIN", "~/custom/html2md.py")
    assert _fetch.resolve_skill_bin("html") == str(Path("~/custom/html2md.py").expanduser())


def test_discovers_ANY_harness_no_hardcoded_list(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # A harness we hardcode NOWHERE — proves discovery is a glob, not a fixed roster.
    binp = _make_skill(tmp_path, ".some-future-harness", "html2md", "scripts/html2md.py")
    _isolate(monkeypatch, tmp_path)
    assert _fetch.resolve_skill_bin("html") == str(binp)   # found via <dotdir>/skills glob + html2md candidate


def test_wiki_skills_dirs_explicit_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # $WIKI_SKILLS_DIRS points at a non-dotdir, non-HOME location (e.g. a system/shared install).
    root = tmp_path / "opt" / "shared-skills"
    binp = root / "pdf" / "scripts" / "pdf_extract.py"
    binp.parent.mkdir(parents=True)
    binp.write_text("x", encoding="utf-8")
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("WIKI_SKILLS_DIRS", str(root))
    assert _fetch.resolve_skill_bin("pdf_extract") == str(binp)


def test_canonical_dir_name_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # If a harness ships BOTH `html` and `html2md`, the canonical (`html`, first candidate) wins.
    canonical = _make_skill(tmp_path, ".claude", "html", "scripts/html2md.py")
    _make_skill(tmp_path, ".claude", "html2md", "scripts/html2md.py")
    _isolate(monkeypatch, tmp_path)
    assert _fetch.resolve_skill_bin("html") == str(canonical)


def test_fallback_bare_name_when_no_roots(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # No harness anywhere → the bare entry name (require_bin then does PATH → DEPENDENCY_MISSING).
    _isolate(monkeypatch, tmp_path)   # empty home, no skills
    assert _fetch.resolve_skill_bin("html") == "html2md.py"


def test_every_bin_key_resolves(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, (env_var, _dirs, rel) in _fetch._SKILL_BIN_SPEC.items():
        monkeypatch.delenv(env_var, raising=False)
        got = _fetch.resolve_skill_bin(key)
        assert got and (got.endswith(rel) or got == Path(rel).name), f"{key}: {got!r}"


def test_load_skills_env_populates_and_shell_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = tmp_path / "obsidian-llm-wiki"
    cfg.mkdir(parents=True)
    (cfg / "skills.env").write_text(
        'export WIKI_HTML_BIN="/from/file.py"\nWIKI_PDF_EXTRACT_BIN=/bare/file.py\n# comment\n',
        encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("WIKI_HTML_BIN", raising=False)
    monkeypatch.setenv("WIKI_PDF_EXTRACT_BIN", "/from/shell.py")   # shell must win over the file
    _fetch._load_skills_env()
    assert os.environ["WIKI_HTML_BIN"] == "/from/file.py"          # loaded from skills.env
    assert os.environ["WIKI_PDF_EXTRACT_BIN"] == "/from/shell.py"  # shell env preserved (setdefault)


def test_load_skills_env_missing_file_is_noop(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "nonexistent"))
    _fetch._load_skills_env()   # must not raise


def test_env_example_documents_every_var() -> None:
    # The committed config/skills.env.example must document every WIKI_* the resolver honors,
    # so the shipped template can't silently drift from the code.
    import re
    spec_vars = {env for env, _d, _r in _fetch._SKILL_BIN_SPEC.values()} | {"WIKI_SKILLS_DIRS"}
    repo = Path(__file__).resolve().parent.parent
    example = (repo / "config" / "skills.env.example").read_text(encoding="utf-8")
    documented = set(re.findall(r"WIKI_[A-Z_]+", example))
    assert spec_vars <= documented, f"skills.env.example is missing: {spec_vars - documented}"


def test_soffice_default_single_source() -> None:
    # DRY: the module default (used by _office_to_text) is the shared resolver, so it can no
    # longer silently diverge from the argparse default in __init__.py.
    import scripts.wiki_skills.wiki_import_article as pkg
    assert _fetch._DEFAULT_SOFFICE_WRAPPER == pkg._DEFAULT_SOFFICE_WRAPPER
