"""S1 — `wiki_import_article._fetch` dispatch (R-1/R-3)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.wiki_skills.wiki_import_article import _fetch
from scripts.wiki_skills.wiki_import_article._errors import (
    EXIT_DEP_MISSING, ImportArticleError,
)

H2M = "/fake/html2md.py"
PDFX = "/fake/pdf_extract.py"
_REAL_REQUIRE_BIN = _fetch.require_bin  # captured before the autouse fixture patches it

_HTML_OK = (
    '---\ntitle: "Deep Dive"\nauthor: Jane Doe\ndate: "2025-03-01"\ntags: []\n---\n\n'
    "# Deep Dive\n\nBody text here.\n"
)


@pytest.fixture(autouse=True)
def _no_real_bins(monkeypatch):
    # bypass the filesystem/PATH check — tests drive subprocess directly
    monkeypatch.setattr(_fetch, "require_bin", lambda p, label: p)


def _cp(args, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args, returncode, stdout, stderr)


def test_url_html_ok_parses_frontmatter(monkeypatch):
    def fake_run(argv, **kw):
        assert argv[1] == H2M and "https://example.com/x" in argv
        return _cp(argv, 0, _HTML_OK)
    monkeypatch.setattr(subprocess, "run", fake_run)
    r = _fetch.dispatch_fetch("https://example.com/x", html2md_bin=H2M, pdf_extract_bin=PDFX)
    assert r.ok and r.engine == "html2md"
    assert r.title == "Deep Dive" and r.author == "Jane Doe" and r.date == "2025-03-01"
    assert "Body text here." in r.raw_text


def test_url_html_empty_body_is_not_ok(monkeypatch):
    # html2md exit 0 but empty stdout → never-empty-raw guard trips (R-3)
    monkeypatch.setattr(subprocess, "run", lambda a, **k: _cp(a, 0, "   \n"))
    r = _fetch.dispatch_fetch("https://ex.com/x", html2md_bin=H2M, pdf_extract_bin=PDFX)
    assert not r.ok and r.raw_text is None


def test_html2md_fetchfailed_propagates(monkeypatch):
    err = '{"v":1,"error":"...403","code":10,"type":"FetchFailed","details":{"url":"u","status":403,"kind":"forbidden"}}'
    monkeypatch.setattr(subprocess, "run", lambda a, **k: _cp(a, 10, "", err))
    r = _fetch.dispatch_fetch("https://ex.com/x", html2md_bin=H2M, pdf_extract_bin=PDFX)
    assert not r.ok
    assert r.error["type"] == "FetchFailed"
    assert r.error["details"]["status"] == 403


def test_arxiv_no_html_falls_back_to_pdf(monkeypatch):
    calls = {"html": 0, "pdf": 0}

    def fake_run(argv, **kw):
        if argv[1] == H2M:
            calls["html"] += 1
            err = '{"error":"no html","code":10,"type":"FetchFailed","details":{"kind":"arxiv_no_html"}}'
            return _cp(argv, 10, "", err)
        # pdf python invocation
        calls["pdf"] += 1
        return _cp(argv, 0, '{"page_count":1,"pages":[{"text":"PDF body text"}]}')
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(_fetch, "_download_pdf", lambda url: Path("/tmp/fake.pdf"))
    monkeypatch.setattr(Path, "unlink", lambda self, missing_ok=False: None)
    r = _fetch.dispatch_fetch("https://arxiv.org/abs/2204.00251",
                              html2md_bin=H2M, pdf_extract_bin=PDFX)
    assert calls["html"] == 1 and calls["pdf"] == 1
    assert r.ok and r.engine == "pdf" and "PDF body text" in r.raw_text


def test_url_pdf_goes_straight_to_pdf(monkeypatch):
    monkeypatch.setattr(_fetch, "_download_pdf", lambda url: Path("/tmp/fake.pdf"))
    monkeypatch.setattr(Path, "unlink", lambda self, missing_ok=False: None)
    monkeypatch.setattr(subprocess, "run",
                        lambda a, **k: _cp(a, 0, '{"pages":[{"text":"ecb report"}]}'))
    r = _fetch.dispatch_fetch("https://ecb.europa.eu/x.pdf",
                              html2md_bin=H2M, pdf_extract_bin=PDFX)
    assert r.ok and r.engine == "pdf" and "ecb report" in r.raw_text


def test_local_md_passthrough(tmp_path, monkeypatch):
    f = tmp_path / "raw.md"
    f.write_text('---\ntitle: "Local"\n---\n\nhello\n', encoding="utf-8")
    r = _fetch.dispatch_fetch(str(f), html2md_bin=H2M, pdf_extract_bin=PDFX)
    assert r.ok and r.engine == "local-md" and r.title == "Local" and "hello" in r.raw_text


def test_require_bin_missing_raises_dep(monkeypatch):
    monkeypatch.setattr(_fetch.shutil, "which", lambda n: None)
    with pytest.raises(ImportArticleError) as ei:
        _REAL_REQUIRE_BIN("definitely-not-here-xyz", "html2md")
    assert ei.value.exit_code == EXIT_DEP_MISSING
