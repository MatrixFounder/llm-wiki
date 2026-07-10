"""TASK 057 / W2 — folder inference for `wiki-import prepare` (`_folder.py`).

057-00: scaffold tests (import + result-shape contract).
057-05/06/07 add the behavior tests bead by bead.
"""
from __future__ import annotations

from scripts.wiki_skills.wiki_import_article import _folder
from scripts.wiki_skills.wiki_import_article._folder import FolderInference


def test_module_surface() -> None:
    """The frozen 057-00 contract: all four entry points exist."""
    for name in ("series_stem", "folder_for_hit", "infer_folder", "active_note_folder"):
        assert callable(getattr(_folder, name))


def test_folder_inference_shape_defaults() -> None:
    """FolderInference defaults = the unresolved-empty outcome."""
    inf = FolderInference()
    assert inf.folder is None and inf.basis is None and inf.confidence is None
    assert inf.evidence == [] and inf.candidates == []
    # instances own their lists (field(default_factory) — no shared mutable default)
    inf.evidence.append("x")
    assert FolderInference().evidence == []


# ---------------------------------------------------------------- 057-05 series_stem

import json as _json
import os
import stat
import subprocess as _subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.wiki_skills.wiki_import_article as wia
from scripts.wiki_skills.wiki_import_article import _context
from scripts.wiki_skills.wiki_import_article._fetch import FetchResult


@pytest.mark.parametrize("title,expected", [
    ("Building AI-Native Startups [004]", "Building AI-Native Startups"),
    ("Building AI-Native Startups (4)", "Building AI-Native Startups"),
    ("System Design Interview #12", "System Design Interview"),
    ("ML Foundations Episode 7", "ML Foundations"),
    ("Криптоликбез выпуск 3", "Криптоликбез"),   # falls BELOW 2-word floor? no: 1 word → None
    ("Урок 12", None),                            # floor: residual too short
    ("Standup #42", None),                        # floor: 1 word
    ("GPT-4", None),                              # trailing number strip → floor
    ("A plain multiword title", "A plain multiword title"),  # no marker → itself
    ("Short 1", None),
    ("", None),
    (None, None),
])
def test_series_stem(title, expected):
    from scripts.wiki_skills.wiki_import_article._folder import series_stem
    if expected == "Криптоликбез":
        assert series_stem(title) is None   # 1-word residual → conservative None
    else:
        assert series_stem(title) == expected


# ---------------------------------------------------------------- 057-05 folder_for_hit

@pytest.mark.parametrize("file_path,subdir,expected", [
    ("03 - Learning/Webinars/x.md", "", "03 - Learning/Webinars"),
    ("Lessons/AI/_sources/x.md", "_sources", "Lessons/AI"),
    ("_sources/x.md", "_sources", "_sources"),           # vault-tier karpathy
    ("_concepts/x.md", "", None),                        # machinery
    ("_concepts/x.md", "_sources", None),                # machinery (wrong subdir)
    ("00-Vault-Index/index.md", "", None),               # index tree
    ("03 - Learning/_raw/x.md", "", None),               # _raw is machinery
    ("root-note.md", "", None),                          # vault root → nothing to propose
])
def test_folder_for_hit(file_path, subdir, expected):
    from scripts.wiki_skills.wiki_import_article._folder import folder_for_hit
    assert folder_for_hit(file_path, subdir) == expected


# ---------------------------------------------------------------- 057-05 infer_folder

class _FakeRepo:
    def __init__(self, hits, raise_exc=None):
        self._hits, self._exc = hits, raise_exc
        self.last_query = None

    def search_pages(self, query, *, vaults=None, limit=20):
        self.last_query = query
        if self._exc:
            raise self._exc
        return self._hits


def _hit(title, file_path, score=-1.0):
    return SimpleNamespace(page=SimpleNamespace(title=title, file_path=file_path),
                           bm25_score=score)


def test_infer_folder_single_sibling_proposes(monkeypatch):
    from scripts.wiki_skills.wiki_import_article._folder import infer_folder
    repo = _FakeRepo([_hit("Building AI-Native Startups 003 — Cyberfund воркшоп",
                           "03 - Learning/Webinars/Building AI-Native Startups 003 — Cyberfund воркшоп.md")])
    inf = infer_folder(repo, "v", "Building AI-Native Startups [004]", source_subdir="")
    assert inf.folder == "03 - Learning/Webinars"
    assert inf.basis == "series-sibling" and inf.confidence == "high"
    assert inf.evidence and "003" in inf.evidence[0]
    assert repo.last_query == '"Building AI-Native Startups"'   # FTS5 phrase-quoted


def test_infer_folder_fts_quote_escaping():
    from scripts.wiki_skills.wiki_import_article._folder import infer_folder
    repo = _FakeRepo([])
    infer_folder(repo, "v", 'The "Great" Series 004', source_subdir="")
    assert repo.last_query == '"The ""Great"" Series"'


def test_infer_folder_multi_folder_ambiguous_candidates():
    from scripts.wiki_skills.wiki_import_article._folder import infer_folder
    repo = _FakeRepo([
        _hit("Deep Series 001", "A/Deep Series 001.md", -5.0),
        _hit("Deep Series 002", "A/Deep Series 002.md", -4.0),
        _hit("Deep Series 003", "B/Deep Series 003.md", -6.0),
    ])
    inf = infer_folder(repo, "v", "Deep Series 004", source_subdir="")
    assert inf.folder is None
    assert inf.candidates == ["A", "B"]   # count desc (A=2), then best bm25


def test_infer_folder_body_only_match_is_not_sibling():
    from scripts.wiki_skills.wiki_import_article._folder import infer_folder
    repo = _FakeRepo([_hit("Some unrelated note", "C/other.md")])
    inf = infer_folder(repo, "v", "Deep Series 004", source_subdir="")
    assert inf.folder is None and inf.candidates == []


def test_infer_folder_dal_error_degrades_to_unresolved():
    from scripts.wiki_skills.wiki_import_article._folder import infer_folder
    repo = _FakeRepo([], raise_exc=ValueError("empty query"))
    inf = infer_folder(repo, "v", "Deep Series 004", source_subdir="")
    assert inf.folder is None and inf.candidates == []


def test_infer_folder_stem_floor_aborts():
    from scripts.wiki_skills.wiki_import_article._folder import infer_folder
    repo = _FakeRepo([_hit("Урок 11", "A/Урок 11.md")])
    inf = infer_folder(repo, "v", "Урок 12", source_subdir="")
    assert inf.folder is None and repo.last_query is None   # search never ran


# ---------------------------------------------------------------- 057-06 active_note_folder

def _stub_resolver(tmp_path, monkeypatch, script_body):
    bin_dir = tmp_path / "stub-bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "obsidian-active-note"
    stub.write_text("#!/bin/sh\n" + script_body, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    return stub


def test_active_note_folder_success(tmp_path, monkeypatch):
    from scripts.wiki_skills.wiki_import_article._folder import active_note_folder
    vault = tmp_path / "vault"
    (vault / "03 - Learning").mkdir(parents=True)
    payload = _json.dumps({"path": "03 - Learning", "abs": str(vault / "03 - Learning")})
    _stub_resolver(tmp_path, monkeypatch, f"echo '{payload}'\n")
    assert active_note_folder(vault) == "03 - Learning"


def test_active_note_folder_nonzero_exit_skipped(tmp_path, monkeypatch):
    from scripts.wiki_skills.wiki_import_article._folder import active_note_folder
    vault = tmp_path / "vault"
    vault.mkdir()
    _stub_resolver(tmp_path, monkeypatch, "exit 3\n")   # no active file
    assert active_note_folder(vault) is None


def test_active_note_folder_outside_vault_skipped(tmp_path, monkeypatch):
    from scripts.wiki_skills.wiki_import_article._folder import active_note_folder
    vault = tmp_path / "vault"
    vault.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    payload = _json.dumps({"path": "elsewhere", "abs": str(outside)})
    _stub_resolver(tmp_path, monkeypatch, f"echo '{payload}'\n")
    assert active_note_folder(vault) is None


def test_active_note_folder_vault_root_skipped(tmp_path, monkeypatch):
    from scripts.wiki_skills.wiki_import_article._folder import active_note_folder
    vault = tmp_path / "vault"
    vault.mkdir()
    payload = _json.dumps({"path": "", "abs": str(vault)})
    _stub_resolver(tmp_path, monkeypatch, f"echo '{payload}'\n")
    assert active_note_folder(vault) is None   # whole-vault blast radius, never a hint


def test_active_note_folder_absent_binary(tmp_path, monkeypatch):
    from scripts.wiki_skills.wiki_import_article._folder import active_note_folder
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    assert active_note_folder(tmp_path) is None


def test_active_note_folder_hang_times_out(tmp_path, monkeypatch):
    from scripts.wiki_skills.wiki_import_article._folder import active_note_folder
    vault = tmp_path / "vault"
    vault.mkdir()
    _stub_resolver(tmp_path, monkeypatch, "sleep 5\n")
    assert active_note_folder(vault, timeout_s=1) is None


# ---------------------------------------------------------------- 057-07 prepare flow

@pytest.fixture
def vault(tmp_path):
    # the vault is a SUBDIR of tmp_path so the index db (vault.parent/index.db) stays
    # OUTSIDE the vault tree — the no-writes assertions snapshot the vault, and the
    # global-db default is likewise outside the vault in production. tmp_path is
    # per-test, so the db never leaks across tests.
    root = tmp_path / "vault"
    root.mkdir()
    (root / "WIKI_SCHEMA.md").write_text(
        "---\nvault_id: testv\nlayout: obsidian-personal\nlanguage: ru\n---\n",
        encoding="utf-8")
    (root / "03 - Learning" / "Webinars").mkdir(parents=True)
    return root


@pytest.fixture(autouse=True)
def _stub_context(monkeypatch):
    monkeypatch.setattr(_context, "known_concepts",
                        lambda repo, v, root, *, fmt="full": [])
    monkeypatch.setattr(_context, "existing_page_slugs", lambda *a, **k: [])


def _prepare_no_folder(vault, monkeypatch, fetch_result, extra=None):
    monkeypatch.setattr(wia, "dispatch_fetch", lambda *a, **k: fetch_result)
    return wia.main(["prepare", "--vault", "testv", "--vault-root", str(vault),
                     "--db-path", str(vault.parent / "index.db"),
                     "--source", "https://x.com/i/broadcasts/1abc",
                     "--kind", "meeting"] + (extra or []))


_FR = FetchResult(ok=True, raw_text="Spoken transcript body of episode four.\n",
                  engine="transcript:whisper-cli",
                  title="Building AI-Native Startups [004]",
                  author="cyberFund", date="2026-07-09")


def test_prepare_no_folder_proposal_envelope_and_no_writes(vault, monkeypatch, capsys):
    from scripts.wiki_skills.wiki_import_article._folder import FolderInference
    monkeypatch.setattr(wia._folder, "infer_folder",
                        lambda repo, v, t, *, source_subdir: FolderInference(
                            folder="03 - Learning/Webinars", basis="series-sibling",
                            confidence="high",
                            evidence=["03 - Learning/Webinars/Building AI-Native Startups 003.md"],
                            candidates=["03 - Learning/Webinars"]))
    monkeypatch.setattr(wia._folder, "active_note_folder",
                        lambda *a, **k: pytest.fail("hint must not run when series resolved"))
    before = {str(p) for p in vault.rglob("*")}
    rc = _prepare_no_folder(vault, monkeypatch, _FR)
    out = _json.loads(capsys.readouterr().out)
    assert rc == 0 and out["action"] == "folder_proposed"
    assert out["folder_inferred"] == "03 - Learning/Webinars"
    assert out["basis"] == "series-sibling" and out["confidence"] == "high"
    assert out["evidence"] and "003" in out["evidence"][0]
    assert out["kind"] == "meeting" and out["title"].endswith("[004]")
    assert {str(p) for p in vault.rglob("*")} == before      # NOTHING written in the vault
    staged = Path(out["staged_path"])
    assert staged.exists() and not str(staged).startswith(str(vault))  # staged OUTSIDE
    body = staged.read_text(encoding="utf-8")
    assert 'source: "https://x.com/i/broadcasts/1abc"' in body
    assert 'title: "Building AI-Native Startups [004]"' in body
    assert 'date: "2026-07-09"' in body
    staged.unlink()


def test_prepare_no_folder_unresolved_exit2(vault, monkeypatch, capsys):
    from scripts.wiki_skills.wiki_import_article._folder import FolderInference
    monkeypatch.setattr(wia._folder, "infer_folder",
                        lambda *a, **k: FolderInference(candidates=["A", "B"]))
    monkeypatch.setattr(wia._folder, "active_note_folder", lambda *a, **k: None)
    before = {str(p) for p in vault.rglob("*")}
    rc = _prepare_no_folder(vault, monkeypatch, _FR)
    out = _json.loads(capsys.readouterr().out)
    assert rc == 2 and out["error"] == "FOLDER_UNRESOLVED"
    assert out["candidates"] == ["A", "B"]
    assert Path(out["staged_path"]).exists()
    assert {str(p) for p in vault.rglob("*")} == before
    Path(out["staged_path"]).unlink()


def test_prepare_no_folder_active_note_fallback(vault, monkeypatch, capsys):
    from scripts.wiki_skills.wiki_import_article._folder import FolderInference
    monkeypatch.setattr(wia._folder, "infer_folder",
                        lambda *a, **k: FolderInference())          # series inconclusive
    monkeypatch.setattr(wia._folder, "active_note_folder",
                        lambda *a, **k: "03 - Learning/Webinars")   # hint lands
    rc = _prepare_no_folder(vault, monkeypatch, _FR)
    out = _json.loads(capsys.readouterr().out)
    assert rc == 0 and out["action"] == "folder_proposed"
    assert out["basis"] == "active-note" and out["confidence"] == "medium"
    Path(out["staged_path"]).unlink()


def test_prepare_staged_rerun_is_fetch_free_and_keeps_metadata(vault, monkeypatch, capsys):
    from scripts.wiki_skills.wiki_import_article._folder import FolderInference
    monkeypatch.setattr(wia._folder, "infer_folder",
                        lambda *a, **k: FolderInference(
                            folder="03 - Learning/Webinars", basis="series-sibling",
                            confidence="high", candidates=["03 - Learning/Webinars"]))
    rc = _prepare_no_folder(vault, monkeypatch, _FR)
    out = _json.loads(capsys.readouterr().out)
    assert rc == 0
    staged = out["staged_path"]

    # confirmed re-run: REAL dispatch_fetch (local-md path — offline), no network possible
    monkeypatch.undo()
    rc2 = wia.main(["prepare", "--vault", "testv", "--vault-root", str(vault),
                    "--db-path", str(vault.parent / "index.db"),
                    "--source", staged, "--folder", "03 - Learning/Webinars",
                    "--kind", "meeting"])
    out2 = _json.loads(capsys.readouterr().out)
    assert rc2 == 0 and out2["action"] == "prepared"
    assert out2["engine"] == "local-md"
    assert out2["title"] == "Building AI-Native Startups [004]"     # metadata survived
    assert out2["date"] == "2026-07-09"
    raw = vault / out2["raw_path"]
    assert raw.exists() and "_raw" in raw.parts                     # filed under the folder now
    assert 'source: "https://x.com/i/broadcasts/1abc"' in raw.read_text(encoding="utf-8")
    Path(staged).unlink()


def test_prepare_no_folder_hostile_title_h6(vault, monkeypatch, capsys):
    from scripts.wiki_skills.wiki_import_article._folder import FolderInference
    monkeypatch.setattr(wia._folder, "infer_folder",
                        lambda *a, **k: FolderInference(candidates=[]))
    monkeypatch.setattr(wia._folder, "active_note_folder", lambda *a, **k: None)
    hostile = FetchResult(ok=True, raw_text="body\n", engine="html",
                          title='Evil" \ninjected: yes')
    rc = _prepare_no_folder(vault, monkeypatch, hostile)
    out = _json.loads(capsys.readouterr().out)
    assert rc == 2
    body = Path(out["staged_path"]).read_text(encoding="utf-8")
    # the stamped scalar is _fm_safe'd (control/quote/backslash stripped, single line):
    # the hostile title must NOT have materialized a new `injected:` frontmatter key
    import re as _re
    fm_block = body.split("---")[1]
    assert not _re.search(r"^injected:", fm_block, _re.M)
    Path(out["staged_path"]).unlink()


def test_prepare_announcement_wins_over_inference(vault, monkeypatch, capsys):
    # ordering: an announcement marker short-circuits BEFORE staging/inference
    ann = FetchResult(ok=False, engine="html", error={
        "error": "AnnouncementOnly", "type": "AnnouncementOnly", "exit_code": 0,
        "details": {"kind": "announcement_only",
                    "broadcast_url": "https://x.com/i/broadcasts/1abc",
                    "url": "https://x.com/c/status/1"}})
    monkeypatch.setattr(wia._folder, "infer_folder",
                        lambda *a, **k: pytest.fail("inference must not run"))
    rc = _prepare_no_folder(vault, monkeypatch, ann)
    out = _json.loads(capsys.readouterr().out)
    assert rc == 0 and out["action"] == "announcement_only"
    assert "staged_path" not in out


def test_series_stem_hostile_long_title_is_bounded():
    """ReDoS guard (Phase-4 finding): a separator-flood og:title must not backtrack
    O(n**2) — the input is capped before the marker regex."""
    import time
    hostile = "Series " + "-" * 100_000
    t = time.perf_counter()
    from scripts.wiki_skills.wiki_import_article._folder import series_stem
    result = series_stem(hostile)
    assert time.perf_counter() - t < 1.0     # was ~minutes uncapped at this length
    assert result is None or isinstance(result, str)


def test_gc_staged_captures_age_based(tmp_path, monkeypatch):
    """Phase-4 F1: staged captures are swept by AGE (delete-on-consume would break the
    fetch-free re-run); fresh files and symlinks are preserved."""
    import tempfile as _tempfile
    import time as _time
    monkeypatch.setattr(_tempfile, "gettempdir", lambda: str(tmp_path))
    old = tmp_path / "wiki-import-staged-old.md"
    fresh = tmp_path / "wiki-import-staged-new.md"
    other = tmp_path / "unrelated.md"
    for f in (old, fresh, other):
        f.write_text("x", encoding="utf-8")
    stale = _time.time() - wia._STAGED_GC_AGE_S - 60
    os.utime(old, (stale, stale))
    os.utime(other, (stale, stale))
    link = tmp_path / "wiki-import-staged-link.md"
    link.symlink_to(other)
    wia._gc_staged_captures()
    assert not old.exists()                    # stale staged → swept
    assert fresh.exists()                      # fresh staged → kept (re-run window)
    assert other.exists()                      # non-staged names untouched
    assert link.is_symlink()                   # symlinks never unlinked through


# ------------------------------------------------ Phase-4 adversarial fixes (cycle 1)

def test_folder_for_hit_case_insensitive_machinery(  # F8
):
    from scripts.wiki_skills.wiki_import_article._folder import folder_for_hit
    assert folder_for_hit("Lessons/AI/_Sources/x.md", "_sources") == "Lessons/AI"
    assert folder_for_hit("00-VAULT-INDEX/index.md", "") is None


def test_hint_never_overrides_series_candidates(vault, monkeypatch, capsys):  # F10
    from scripts.wiki_skills.wiki_import_article._folder import FolderInference
    monkeypatch.setattr(wia._folder, "infer_folder",
                        lambda *a, **k: FolderInference(candidates=["A", "B"]))
    monkeypatch.setattr(wia._folder, "active_note_folder", lambda *a, **k: "C")
    rc = _prepare_no_folder(vault, monkeypatch, _FR)
    out = _json.loads(capsys.readouterr().out)
    assert rc == 2 and out["error"] == "FOLDER_UNRESOLVED"   # unrelated hint = bystander
    assert out["candidates"] == ["A", "B"]
    Path(out["staged_path"]).unlink()


def test_hint_may_pick_one_of_the_candidates(vault, monkeypatch, capsys):  # F10
    from scripts.wiki_skills.wiki_import_article._folder import FolderInference
    monkeypatch.setattr(wia._folder, "infer_folder",
                        lambda *a, **k: FolderInference(candidates=["A", "B"]))
    monkeypatch.setattr(wia._folder, "active_note_folder", lambda *a, **k: "B")
    rc = _prepare_no_folder(vault, monkeypatch, _FR)
    out = _json.loads(capsys.readouterr().out)
    assert rc == 0 and out["folder_inferred"] == "B" and out["basis"] == "active-note"
    Path(out["staged_path"]).unlink()


def test_post_stage_fault_unlinks_staged(vault, monkeypatch, capsys):  # F5
    import scripts.wiki_skills.wiki_import_article as _wia
    created: list = []
    real_stage = _wia._stage_capture

    def spy_stage(args, result):
        p = real_stage(args, result)
        created.append(p)
        return p

    monkeypatch.setattr(_wia, "_stage_capture", spy_stage)
    monkeypatch.setattr(_wia, "make_repo",
                        lambda cfg: (_ for _ in ()).throw(RuntimeError("db fault")))
    rc = _prepare_no_folder(vault, monkeypatch, _FR)
    out = _json.loads(capsys.readouterr().out)
    assert rc != 0 and out["error"] == "INTERNAL_ERROR"
    assert created and not created[0].exists()   # staged file not stranded


def test_titleless_staged_rerun_slug_from_original_source(vault, monkeypatch, capsys):  # F3
    from scripts.wiki_skills.wiki_import_article._folder import FolderInference
    titleless = FetchResult(ok=True, raw_text="plain body, no metadata\n",
                            engine="transcript:whisper-cli", title=None)
    monkeypatch.setattr(wia._folder, "infer_folder",
                        lambda *a, **k: FolderInference(
                            folder="03 - Learning/Webinars", basis="series-sibling",
                            confidence="high", candidates=["03 - Learning/Webinars"]))
    monkeypatch.setattr(wia, "dispatch_fetch", lambda *a, **k: titleless)
    rc = wia.main(["prepare", "--vault", "testv", "--vault-root", str(vault),
                   "--db-path", str(vault.parent / "index.db"),
                   "--source", "https://x.com/i/broadcasts/1FooBar99",
                   "--kind", "meeting"])
    out = _json.loads(capsys.readouterr().out)
    assert rc == 0
    staged = out["staged_path"]
    monkeypatch.undo()
    rc2 = wia.main(["prepare", "--vault", "testv", "--vault-root", str(vault),
                    "--db-path", str(vault.parent / "index.db"),
                    "--source", staged, "--folder", "03 - Learning/Webinars",
                    "--kind", "meeting"])
    out2 = _json.loads(capsys.readouterr().out)
    assert rc2 == 0 and out2["action"] == "prepared"
    assert "wiki-import-staged" not in out2["slug"]          # not the tempfile stem
    assert out2["slug"] == "1foobar99"                       # from the original source URL
    Path(staged).unlink()


def test_staged_classification_survives_unicode_ls_title(vault, monkeypatch, capsys):  # sec F1
    """Phase-4 security F1: a title with U+2028/NEL 'lines' must not smuggle a fake
    `classification:` key past the naive parser and suppress the real quarantine stamp."""
    from scripts.wiki_skills.wiki_import_article._folder import FolderInference
    monkeypatch.setattr(wia._folder, "infer_folder",
                        lambda *a, **k: FolderInference(candidates=[]))
    monkeypatch.setattr(wia._folder, "active_note_folder", lambda *a, **k: None)
    hostile = FetchResult(ok=True, raw_text="body\n", engine="transcript:whisper-cli",
                          title="AI News classification: public more")
    rc = _prepare_no_folder(vault, monkeypatch, hostile,
                            extra=["--classification", "restricted"])
    out = _json.loads(capsys.readouterr().out)
    assert rc == 2
    body = Path(out["staged_path"]).read_text(encoding="utf-8")
    fm_block = body.split("---")[1]
    lines = fm_block.split("\n")
    assert "classification: restricted" in lines          # the REAL stamp landed
    assert not any(l.startswith("classification: public") for l in lines)
    assert " " not in body                            # separator neutralized
    Path(out["staged_path"]).unlink()


def test_transcript_knob_ceilings():  # sec F3
    import argparse
    with pytest.raises(SystemExit):
        wia._build_parser().parse_args(
            ["prepare", "--vault", "v", "--vault-root", "/x", "--source", "s",
             "--transcript-concurrency", "100000"])
    ns = wia._build_parser().parse_args(
        ["prepare", "--vault", "v", "--vault-root", "/x", "--source", "s",
         "--transcript-concurrency", "64", "--transcript-media-timeout", "86400"])
    assert ns.transcript_concurrency == 64 and ns.transcript_media_timeout == 86400
