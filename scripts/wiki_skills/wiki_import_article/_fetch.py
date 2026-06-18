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


@dataclass
class FetchResult:
    ok: bool
    raw_text: str | None = None          # converted markdown/text (None on failure)
    title: str | None = None
    author: str | None = None
    date: str | None = None
    engine: str = ""                     # provenance of the fetch (html2md / pdf / local-md)
    error: dict[str, Any] | None = None  # html2md/pdf typed error envelope on failure


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


def _arxiv_pdf_url(url: str) -> str | None:
    m = _ARXIV_RE.search(url)
    return f"https://arxiv.org/pdf/{m.group(1)}" if m else None


# ---- fetch strategies ------------------------------------------------------

def _fetch_html(html2md_bin: str, target: str) -> FetchResult:
    """URL or local HTML → markdown via html2md (handles Wikipedia/arXiv/empty itself)."""
    bin_path = require_bin(html2md_bin, "html2md")
    proc = subprocess.run(
        ["python3", bin_path, target, "--stdout", "--no-reader",
         "--no-download-images", "--json-errors", "--engine", "auto"],
        capture_output=True, text=True, timeout=_HTML2MD_TIMEOUT)
    if proc.returncode == 0 and len((proc.stdout or "").strip()) > 0:
        md = proc.stdout
        fm = _parse_frontmatter(md)
        return FetchResult(
            ok=True, raw_text=md, engine="html2md",
            title=fm.get("title") or None,
            author=fm.get("author") or None,
            date=(fm.get("date") or fm.get("published") or None))
    err = _parse_skill_error(proc.stderr, proc.returncode)
    return FetchResult(ok=False, engine="html2md", error=err)


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
    req = urllib.request.Request(url, headers={"User-Agent": "wiki-import-article/1.0"})
    tmp = Path(tempfile.mkstemp(suffix=".pdf")[1])
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
    return tmp


def _pdf_to_text(pdf_extract_bin: str, pdf_path: Path) -> FetchResult:
    bin_path = require_bin(pdf_extract_bin, "pdf_extract")
    proc = subprocess.run(
        [_pdf_python(bin_path), bin_path, str(pdf_path), "--json-errors"],
        capture_output=True, text=True, timeout=_PDF_TIMEOUT)
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

def dispatch_fetch(source: str, *, html2md_bin: str, pdf_extract_bin: str) -> FetchResult:
    """Route `source` (URL or local file) to html2md / pdf and return a FetchResult.

    Never writes anything — the caller persists `_raw/` only on a non-empty `ok` result.
    """
    is_url = source.startswith(("http://", "https://"))
    bare = source.split("?", 1)[0].lower()

    if is_url and not bare.endswith(".pdf"):
        res = _fetch_html(html2md_bin, source)
        if res.ok:
            return res
        # html2md says "HTML-only article has no HTML, use the PDF" → fall back.
        kind = (res.error or {}).get("details", {}).get("kind")
        if kind == "arxiv_no_html":
            pdf_url = _arxiv_pdf_url(source)
            if pdf_url:
                return _fetch_pdf_url(pdf_extract_bin, pdf_url)
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
    return _fetch_html(html2md_bin, str(p))
