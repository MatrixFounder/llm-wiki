"""Deterministic fetch/convert dispatch for `wiki-import-article` (R-1/R-3).

**Composition, not reinvention (NF-2):** this module never parses HTML or PDFs
itself — it shells out to the existing global skills:
  * HTML / URL  → the `html2md` skill (which itself owns the Wikipedia-REST-HTML
    and arXiv-`/html/` rewrites + typed `EmptyExtraction`/`arxiv_no_html` exits).
  * PDF         → the `pdf` skill's `pdf_extract.py` (structured JSON dump).

The caller (the `prepare` facade) writes `_raw/<slug>.md` **only** when the result
is `ok` with a non-empty body — so a failed/empty fetch never persists an empty raw
(R-3). All html2md/pdf typed failures are propagated into `FetchResult.error`.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._errors import EXIT_DEP_MISSING, EXIT_FETCH_FAILED, ImportArticleError

_FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_ARXIV_RE = re.compile(r"arxiv\.org/(?:abs|pdf|html)/([\w.\-/]+?)(?:v\d+)?(?:\.pdf)?$")
_MAX_PDF_BYTES = 64 * 1024 * 1024  # 64 MiB cap on a downloaded PDF (DoS guard)
_HTML2MD_TIMEOUT = 180
_PDF_TIMEOUT = 240
# Browser-like UA: many PDF hosts (CDNs, hubfs, journal sites) reject non-browser
# agents with 403. Operator-supplied URL — this fetches a document the operator asked
# for (not detection-evasion); mirrors what the html2md skill's fetch already sends.
_PDF_FETCH_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                 "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
# X/Twitter served logged-out: html2md's lite fetch returns only the login chrome (no post
# text). Detect it (scoped to these hosts) so we surface a needs-manual signal instead of
# writing a junk _raw. Conservative threshold — a captured first tweet (~300+ prose chars)
# is NOT flagged; only the bare login wall (<220 prose chars) is.
_X_HOSTS = ("x.com", "twitter.com")
# Login-wall markers, split by robustness. URL markers are LOCALE-INDEPENDENT (X serves these
# login-flow paths regardless of UI language) → the primary signal. The text markers are
# English-only best-effort secondary coverage; a non-English wall is still caught by the URL
# markers (they're OR-ed together below) + the <_X_PROSE_FLOOR prose gate.
_X_LOGIN_URL_MARKERS = ("/i/flow/login", "onboarding/web?mode=login", "mode=login", "/login?")
_X_LOGIN_TEXT_MARKERS = ("Log in", "Sign up")
_X_LOGIN_MARKERS = _X_LOGIN_URL_MARKERS + _X_LOGIN_TEXT_MARKERS
_X_PROSE_FLOOR = 220


@dataclass
class FetchResult:
    ok: bool
    raw_text: str | None = None          # converted markdown/text (None on failure)
    title: str | None = None
    author: str | None = None
    date: str | None = None
    engine: str = ""                     # provenance of the fetch (html2md / pdf / local-md)
    error: dict[str, Any] | None = None  # html2md/pdf typed error envelope on failure
    attachments_dir: Path | None = None  # downloaded images (image-import ON) → caller files them


def _fm_safe(value: str) -> str:
    """Frontmatter-scalar-safe: strip control/newlines + quotes + backslashes so an injected
    source value cannot break the YAML, inject a key, or escape the closing quote (H-6)."""
    return re.sub(r'[\x00-\x1f\x7f"\\]+', " ", str(value or "")).strip()


def ensure_source_frontmatter(raw_text: str, source: str) -> str:
    """Guarantee the `_raw` markdown carries a link to the original in its frontmatter.
    PDFs (text dump, no FM) get a fresh block; an existing FM without `source:`/`url:`
    gets one injected; a FM that already cites the source is left untouched."""
    fm = _parse_frontmatter(raw_text)
    if fm.get("source") or fm.get("url"):
        return raw_text
    src = _fm_safe(source)
    if _FM_RE.match(raw_text):                       # existing FM at the very start
        return re.sub(r"\A---\n", f'---\nsource: "{src}"\n', raw_text, count=1)
    return f'---\nsource: "{src}"\n---\n\n{raw_text}'


# ---- helpers ---------------------------------------------------------------

def _parse_frontmatter(md: str) -> dict[str, str]:
    """Pull title/author/date out of an html2md YAML frontmatter block (best effort)."""
    m = _FM_RE.match(md)
    out: dict[str, str] = {}
    if not m:
        return out
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            out[k.strip().lower()] = v.strip().strip('"').strip("'")
    return out


def require_bin(path_or_name: str, label: str) -> str:
    """Resolve an external skill binary path; fail-fast (exit 6) if absent."""
    if Path(path_or_name).expanduser().exists():
        return str(Path(path_or_name).expanduser())
    found = shutil.which(path_or_name)
    if found is None:
        raise ImportArticleError(
            "DEPENDENCY_MISSING",
            f"{label} not found at {path_or_name!r}; install the skill "
            f"or pass --{label.replace('_', '-')}-bin.",
            exit_code=EXIT_DEP_MISSING,
            details={"binary": path_or_name, "label": label})
    return found


def _pdf_python(script_path: str) -> str:
    """The pdf skill ships deps in `scripts/.venv`; prefer that interpreter."""
    venv_py = Path(script_path).expanduser().resolve().parent / ".venv" / "bin" / "python"
    return str(venv_py) if venv_py.exists() else "python3"


def _skill_env() -> dict[str, str]:
    """Env for an external skill subprocess.

    Drops our own bin-wrapper's ``PYTHONSAFEPATH`` / ``PYTHONPATH`` so the child
    skill resolves its OWN script-dir sibling imports. The ``wiki-import`` wrapper
    exports ``PYTHONSAFEPATH=1`` (+ ``PYTHONPATH=<repo>``); inherited by e.g.
    ``pdf_extract.py`` it suppresses the script-dir entry on ``sys.path`` and breaks
    its ``from _errors import …`` (the failure surfaced as a spurious FETCH_FAILED).
    """
    env = dict(os.environ)
    env.pop("PYTHONSAFEPATH", None)
    env.pop("PYTHONPATH", None)
    return env


def _arxiv_pdf_url(url: str) -> str | None:
    m = _ARXIV_RE.search(url)
    return f"https://arxiv.org/pdf/{m.group(1)}" if m else None


def _is_x_login_wall(md: str, target: str) -> bool:
    """True iff `target` is an x.com/twitter URL whose html2md output is just the
    logged-out login chrome (no post text) — so the caller fails instead of writing
    a junk `_raw`. Conservative: requires a login marker AND <`_X_PROSE_FLOOR` chars
    of real prose, so a captured first tweet still passes through."""
    host = target.split("/", 3)[2].lower() if "://" in target else ""
    if not any(host == h or host.endswith("." + h) for h in _X_HOSTS):
        return False
    if not any(mark in md for mark in _X_LOGIN_MARKERS):
        return False
    body = _FM_RE.sub("", md)                                   # drop frontmatter
    body = re.sub(r"!?\[[^\]]*\]\([^)]*\)", " ", body)          # drop [..](..) / ![..](..)
    prose = re.sub(r"\s+", " ", re.sub(r"[#>*`_|\[\]()\-]", " ", body)).strip()
    return len(prose) < _X_PROSE_FLOOR


# ---- fetch strategies ------------------------------------------------------

def _fetch_html(html2md_bin: str, target: str, *, download_images: bool = False) -> FetchResult:
    """URL/local HTML → markdown via html2md, OUTPUT-DIR mode (the only mode that yields
    html2md's dual output). **Prefers the reader extraction** (`<slug>.reader.md` — main
    content, no nav/chrome) and falls back to the whole page only when reader is missing
    or over-stripped. With ``download_images`` it keeps just the images the chosen text
    references in a sibling ``_attachments/``; else remote URLs are kept verbatim. (html2md
    owns the Wikipedia-REST-HTML / arXiv rewrites + its own SSRF + ``--max-images`` bound.)"""
    bin_path = require_bin(html2md_bin, "html2md")
    tmpdir = tempfile.mkdtemp(prefix="wiki-import-fetch-")

    def _cleanup() -> None:
        shutil.rmtree(tmpdir, ignore_errors=True)

    def _fail(kind: str, code: int = 1) -> FetchResult:
        _cleanup()
        return FetchResult(ok=False, engine="html2md", error={
            "error": "FetchFailed", "type": "FetchFailed", "exit_code": code,
            "details": {"url": target, "kind": kind}})

    img_flag = "--download-images" if download_images else "--no-download-images"
    argv = ["python3", bin_path, target, tmpdir, img_flag,
            "--json-errors", "--engine", "auto"]
    # A hung/over-long fetch (slow/hostile host, huge page — exactly what the timeout exists
    # for) must NOT escape as a raw traceback that ALSO orphans `tmpdir` (Decision-17 + the
    # mkdtemp lifecycle). `_fail` cleans the temp dir and returns a typed FETCH_FAILED.
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=_HTML2MD_TIMEOUT, env=_skill_env())
    except subprocess.TimeoutExpired:
        return _fail("timeout", code=EXIT_FETCH_FAILED)
    except (OSError, ValueError):  # spawn failure — clean envelope, never a raw traceback
        return _fail("spawn_failed", code=EXIT_FETCH_FAILED)
    if proc.returncode != 0:
        _cleanup()
        return FetchResult(ok=False, engine="html2md",
                           error=_parse_skill_error(proc.stderr, proc.returncode))

    out = Path(tmpdir)
    reader = sorted(out.glob("*.reader.md"))
    whole = [p for p in out.glob("*.md") if not p.name.endswith(".reader.md")]
    reader_txt = reader[0].read_text(encoding="utf-8", errors="replace") if reader else ""
    # Reader-first: take the reader extraction when it has a substantial body; only read the
    # (larger, nav/chrome-laden) whole-page output LAZILY when reader is missing/over-stripped
    # — on the common path this avoids a wasted read+decode + transient ~2× peak memory.
    if reader_txt and len(_FM_RE.sub("", reader_txt).strip()) >= 200:
        md = reader_txt
    else:
        whole_txt = whole[0].read_text(encoding="utf-8", errors="replace") if whole else ""
        md = whole_txt or reader_txt
    if not md.strip():
        return _fail("no_output")
    if _is_x_login_wall(md, target):  # logged-out X chrome only → no post text
        _cleanup()
        return FetchResult(ok=False, engine="html2md", error={
            "error": "x.com returned only the logged-out login wall (no post text "
                     "captured); save the thread/article as a .webarchive while logged "
                     "in and import that file instead.",
            "type": "FetchFailed", "exit_code": EXIT_FETCH_FAILED,
            "details": {"url": target, "kind": "login_wall"}})

    # Keep only the images the CHOSEN text references (drops nav/chrome images html2md
    # downloaded for the whole page) — less junk in `_attachments/`.
    attach: Path | None = None
    adir = out / "_attachments"
    if download_images and adir.is_dir():
        referenced = set(re.findall(r"_attachments/([^\s)\]]+)", md))
        for f in list(adir.iterdir()):
            if f.is_file() and f.name not in referenced:
                f.unlink()
        attach = adir if any(adir.iterdir()) else None
    if attach is None:  # nothing to file → drop the temp dir now
        _cleanup()
    fm = _parse_frontmatter(md)
    return FetchResult(
        ok=True, raw_text=md, engine="html2md", attachments_dir=attach,
        title=fm.get("title") or None,
        author=fm.get("author") or None,
        date=(fm.get("date") or fm.get("published") or None))


def _parse_skill_error(stderr: str, returncode: int) -> dict[str, Any]:
    # generic: extracts the last single-line JSON error envelope from html2md OR pdf stderr
    for line in reversed((stderr or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                env = json.loads(line)
                if isinstance(env, dict):
                    env.setdefault("exit_code", returncode)
                    return env
            except json.JSONDecodeError:
                continue
    return {"error": "FetchFailed", "type": "FetchFailed",
            "exit_code": returncode, "details": {}}


def _download_pdf(url: str) -> Path:
    """Download a PDF URL to a temp file, size-capped. (Operator-supplied URL; the
    SSRF surface is the operator's — documented residual. NOTE: urllib follows 30x
    redirects, so the residual includes a redirect to a private/link-local host; run
    untrusted imports in an egress-restricted sandbox.)"""
    req = urllib.request.Request(
        url, headers={"User-Agent": _PDF_FETCH_UA, "Accept": "application/pdf,*/*"})
    fd, name = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)            # close the mkstemp fd — we re-open by path below (no fd leak)
    tmp = Path(name)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (operator URL)
            total = 0
            with tmp.open("wb") as fh:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > _MAX_PDF_BYTES:
                        raise ImportArticleError(
                            "FETCH_FAILED", f"PDF exceeds {_MAX_PDF_BYTES}-byte cap",
                            exit_code=EXIT_FETCH_FAILED, details={"url": url})
                    fh.write(chunk)
    except BaseException:   # never leak the temp file on any error/abort path
        tmp.unlink(missing_ok=True)
        raise
    return tmp


def _pdf_to_text(pdf_extract_bin: str, pdf_path: Path) -> FetchResult:
    bin_path = require_bin(pdf_extract_bin, "pdf_extract")
    proc = subprocess.run(
        [_pdf_python(bin_path), bin_path, str(pdf_path), "--json-errors"],
        capture_output=True, text=True, timeout=_PDF_TIMEOUT, env=_skill_env())
    if proc.returncode != 0:
        return FetchResult(
            ok=False, engine="pdf",
            error=_parse_skill_error(proc.stderr, proc.returncode))
    try:
        data = json.loads(proc.stdout)
        pages = data.get("pages") or []
        text = "\n\n".join(
            (p.get("text") or "") if isinstance(p, dict) else str(p) for p in pages)
    except (json.JSONDecodeError, AttributeError):
        return FetchResult(ok=False, engine="pdf",
                           error={"error": "PdfDumpUnparsable", "exit_code": 1})
    return FetchResult(ok=bool(text.strip()), raw_text=text or None, engine="pdf")


def _fetch_pdf_url(pdf_extract_bin: str, url: str) -> FetchResult:
    pdf = _download_pdf(url)
    try:
        return _pdf_to_text(pdf_extract_bin, pdf)
    finally:
        pdf.unlink(missing_ok=True)


# ---- public dispatch -------------------------------------------------------

def dispatch_fetch(source: str, *, html2md_bin: str, pdf_extract_bin: str,
                   download_images: bool = False) -> FetchResult:
    """Route `source` (URL or local file) to html2md / pdf and return a FetchResult.

    `download_images` (config-driven; default ON at the prepare layer) makes the html2md
    path download images into a sibling `_attachments/`. PDFs are text-only — no images.
    Never writes anything — the caller persists `_raw/` only on a non-empty `ok` result.
    """
    is_url = source.startswith(("http://", "https://"))
    bare = source.split("?", 1)[0].lower()

    if is_url and not bare.endswith(".pdf"):
        res = _fetch_html(html2md_bin, source, download_images=download_images)
        if res.ok:
            return res
        # html2md says "HTML-only article has no HTML, use the PDF" → fall back.
        kind = (res.error or {}).get("details", {}).get("kind")
        if kind == "arxiv_no_html":
            pdf_url = _arxiv_pdf_url(source)
            if pdf_url:
                return _fetch_pdf_url(pdf_extract_bin, pdf_url)
        # The URL serves a PDF despite no `.pdf` suffix (e.g. dl.acm.org/doi/pdf/…,
        # CDN/hubfs links): html2md reports details.kind=="pdf". Download + extract via
        # the pdf skill rather than failing. (A real paywall still surfaces as FETCH_FAILED.)
        if kind == "pdf":
            return _fetch_pdf_url(pdf_extract_bin, source)
        return res

    if is_url and bare.endswith(".pdf"):
        return _fetch_pdf_url(pdf_extract_bin, source)

    # local file
    p = Path(source).expanduser()
    if bare.endswith(".pdf"):
        return _pdf_to_text(pdf_extract_bin, p)
    if bare.endswith((".md", ".markdown", ".txt")):
        text = p.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        return FetchResult(
            ok=bool(text.strip()), raw_text=text or None, engine="local-md",
            title=fm.get("title") or None, author=fm.get("author") or None,
            date=(fm.get("date") or fm.get("published") or None))
    # any other local file → let html2md try (it handles .html/.htm/.mhtml/.webarchive)
    return _fetch_html(html2md_bin, str(p), download_images=download_images)
