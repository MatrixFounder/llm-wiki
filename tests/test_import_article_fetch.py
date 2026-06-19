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
        assert "--stdout" not in argv                       # output-dir mode now
        (Path(argv[3]) / "x.reader.md").write_text(_HTML_OK, encoding="utf-8")
        return _cp(argv, 0, "")
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


# --- P2-3: a URL serving a PDF without a `.pdf` suffix falls back to the pdf skill ----
def test_url_serving_pdf_without_suffix_routes_to_pdf(monkeypatch):
    err = ('{"v":1,"error":"returns a PDF, not HTML","code":10,"type":"FetchFailed",'
           '"details":{"url":"u","kind":"pdf"}}')
    monkeypatch.setattr(subprocess, "run", lambda a, **k: _cp(a, 10, "", err))
    seen = {}
    monkeypatch.setattr(_fetch, "_fetch_pdf_url", lambda binp, url: (
        seen.setdefault("url", url),
        _fetch.FetchResult(ok=True, raw_text="PDF TEXT", engine="pdf"))[1])
    r = _fetch.dispatch_fetch("https://dl.acm.org/doi/pdf/10.1145/3517340",
                              html2md_bin=H2M, pdf_extract_bin=PDFX)
    assert r.ok and r.engine == "pdf" and r.raw_text == "PDF TEXT"
    assert seen["url"] == "https://dl.acm.org/doi/pdf/10.1145/3517340"


def test_pdf_download_uses_browser_ua(monkeypatch):
    # P2-4: _download_pdf must send a browser-like UA + Accept (hosts 403 a bare UA)
    captured = {}

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n=-1): return b""  # empty body → UA/headers are the point

    def _fake_urlopen(req, **kw):
        captured["ua"] = req.get_header("User-agent")
        captured["accept"] = req.get_header("Accept")
        return _Resp()
    monkeypatch.setattr(_fetch.urllib.request, "urlopen", _fake_urlopen)
    _fetch._download_pdf("https://host/x")
    assert "Mozilla/5.0" in (captured["ua"] or "") and "pdf" in (captured["accept"] or "")


# --- P2-5: x.com logged-out login wall is surfaced as needs-manual, not a junk raw ----
_X_WALL = ('---\ntitle: "x"\n---\n## Post\n[Log in](/i/flow/login)[Sign up](/x)\n'
           '## Post\n[![a](b)](c)\n[handle](d)\n[@handle](e)\n')


def _wa_run(content):  # mock html2md output-dir run: write content as the whole-page .md
    def fake_run(argv, **kw):
        (Path(argv[3]) / "x.md").write_text(content, encoding="utf-8")
        return _cp(argv, 0, "")
    return fake_run


def test_x_login_wall_is_not_ok(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _wa_run(_X_WALL))
    r = _fetch.dispatch_fetch("https://x.com/u/status/1", html2md_bin=H2M, pdf_extract_bin=PDFX)
    assert not r.ok and r.error["details"]["kind"] == "login_wall"


def test_x_with_real_post_text_is_ok(monkeypatch):
    # a captured first tweet (~280 prose chars, like a real thread opener) passes the gate
    md = ('---\ntitle: "t"\n---\n## Post\n[Log in](/x)[Sign up](/y)\n\n'
          'Airdrops are broken. They reward metrics anyone can game: tx counts, snapshots, '
          'etc. But they do not reward what matters to projects building something real: '
          'long-term conviction. So we analyzed ten past airdrops to discover who held vs '
          'dumped, and built a Holder Score for wallet addresses across many chains.\n')
    monkeypatch.setattr(subprocess, "run", _wa_run(md))
    r = _fetch.dispatch_fetch("https://x.com/u/status/1", html2md_bin=H2M, pdf_extract_bin=PDFX)
    assert r.ok and r.engine == "html2md"


def test_non_x_login_markers_not_flagged(monkeypatch):
    # the login-wall gate is scoped to x.com/twitter — a short non-x page is left alone
    monkeypatch.setattr(subprocess, "run", _wa_run(_X_WALL))
    r = _fetch.dispatch_fetch("https://example.com/p", html2md_bin=H2M, pdf_extract_bin=PDFX)
    assert r.ok


# --- reader-first + image import (config-driven, default ON at the prepare layer) -----
def test_fetch_html_prefers_reader_and_prunes_unreferenced_images(monkeypatch):
    def fake_run(argv, **kw):
        assert "--download-images" in argv and "--stdout" not in argv  # output-dir mode
        outdir = Path(argv[3])
        # whole page = nav chrome + an unreferenced chrome image
        (outdir / "page.md").write_text(
            '---\nsource: "https://e.com/x"\n---\n\n[Skip to main](#)\n\n'
            '![logo](_attachments/logo.png)\n# T\n\n![a](_attachments/h.png)\n', encoding="utf-8")
        # reader extraction = clean body (references only h.png), well over the 200-char floor
        (outdir / "page.reader.md").write_text(
            '---\nsource: "https://e.com/x"\n---\n\n# T\n\nClean reader body with no nav chrome. '
            + ("This is the substantive article content the reader extraction keeps. " * 4)
            + '![a](_attachments/h.png)\n', encoding="utf-8")
        att = outdir / "_attachments"; att.mkdir()
        (att / "h.png").write_bytes(b"PNG"); (att / "logo.png").write_bytes(b"PNG")
        return _cp(argv, 0, "")
    monkeypatch.setattr(subprocess, "run", fake_run)
    r = _fetch.dispatch_fetch("https://e.com/x", html2md_bin=H2M, pdf_extract_bin=PDFX,
                              download_images=True)
    assert r.ok and r.engine == "html2md"
    assert "Clean reader body" in (r.raw_text or "") and "Skip to main" not in (r.raw_text or "")
    # only the reader-referenced image is kept; the chrome `logo.png` is pruned
    assert r.attachments_dir is not None
    assert (r.attachments_dir / "h.png").exists() and not (r.attachments_dir / "logo.png").exists()


def test_fetch_html_falls_back_to_whole_when_reader_too_thin(monkeypatch):
    def fake_run(argv, **kw):
        outdir = Path(argv[3])
        (outdir / "p.md").write_text('---\ntitle: "t"\n---\n\n# T\n\n' + "x" * 400 + "\n",
                                     encoding="utf-8")
        (outdir / "p.reader.md").write_text('---\ntitle: "t"\n---\n\nthin\n', encoding="utf-8")
        return _cp(argv, 0, "")
    monkeypatch.setattr(subprocess, "run", fake_run)
    r = _fetch.dispatch_fetch("https://e.com/x", html2md_bin=H2M, pdf_extract_bin=PDFX)
    assert r.ok and "x" * 400 in (r.raw_text or "")   # whole page (reader under the floor)


def test_fetch_html_no_images_keeps_remote(monkeypatch):
    # download_images=False (default) → --no-download-images, output-dir mode, no attachments
    seen = {}
    def fake_run(argv, **kw):
        seen["argv"] = argv
        (Path(argv[3]) / "p.reader.md").write_text(
            '---\ntitle: "t"\n---\n\n# T\n\n' + "body " * 60 + "\n", encoding="utf-8")
        return _cp(argv, 0, "")
    monkeypatch.setattr(subprocess, "run", fake_run)
    r = _fetch.dispatch_fetch("https://e.com/x", html2md_bin=H2M, pdf_extract_bin=PDFX)
    assert r.ok and r.attachments_dir is None
    assert "--no-download-images" in seen["argv"] and "--stdout" not in seen["argv"]


def test_ensure_source_frontmatter_cases():
    f = _fetch.ensure_source_frontmatter
    # (1) no frontmatter → prepend a source block
    assert f("# T\n\nbody\n", "https://e.com/x").startswith(
        '---\nsource: "https://e.com/x"\n---\n\n')
    # (2) frontmatter already cites the source → untouched
    md = '---\nsource: "u"\ntitle: "t"\n---\n\nbody\n'
    assert f(md, "https://other") == md
    # (3) frontmatter without source → inject one (still a single FM block)
    out = f('---\ntitle: "t"\n---\n\nbody\n', "https://e.com/x")
    assert 'source: "https://e.com/x"' in out and out.count("\n---\n") == 1
