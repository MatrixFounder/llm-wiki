"""Deterministic fetch/convert dispatch for `wiki-import-article` (R-1/R-3).

**Composition, not reinvention (NF-2):** this module never parses HTML or PDFs
itself — it shells out to the existing global skills:
  * HTML / URL  → the `html` skill (which itself owns the Wikipedia-REST-HTML
    and arXiv-`/html/` rewrites + typed `EmptyExtraction`/`arxiv_no_html` exits).
  * PDF         → the `pdf` skill's `pdf_extract.py` (structured JSON dump).

The caller (the `prepare` facade) writes `_raw/<slug>.md` **only** when the result
is `ok` with a non-empty body — so a failed/empty fetch never persists an empty raw
(R-3). All html/pdf typed failures are propagated into `FetchResult.error`.
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
from urllib.parse import urlsplit

from ._errors import EXIT_DEP_MISSING, EXIT_FETCH_FAILED, ImportArticleError

_FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_ARXIV_RE = re.compile(r"arxiv\.org/(?:abs|pdf|html)/([\w.\-/]+?)(?:v\d+)?(?:\.pdf)?$")
_MAX_PDF_BYTES = 64 * 1024 * 1024  # 64 MiB cap on a downloaded PDF (DoS guard)
_HTML_TIMEOUT = 180
_PDF_TIMEOUT = 240
# Browser-like UA: many PDF hosts (CDNs, hubfs, journal sites) reject non-browser
# agents with 403. Operator-supplied URL — this fetches a document the operator asked
# for (not detection-evasion); mirrors what the html skill's fetch already sends.
_PDF_FETCH_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                 "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
# X/Twitter served logged-out: the html skill's lite fetch returns only the login chrome (no post
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

# ---- TASK 044: video sources via the transcript-fetcher skill ----------------
# Video-host classification (R-1) — pure URL-shape, label-boundary matched (reuses `_X_HOSTS`).
_VIDEO_HOSTS_YOUTUBE = ("youtube.com", "youtu.be", "youtube-nocookie.com")
_VIDEO_HOSTS_VIMEO = ("vimeo.com",)
_VIDEO_HOSTS_SKOOL = ("skool.com",)
_X_BROADCAST_RE = re.compile(r"/i/(?:broadcasts|spaces)/\w", re.I)   # has no usable text path
_X_STATUS_RE = re.compile(r"/[^/]+/status/\d+", re.I)               # text OR text+video (ambiguous)
_SKOOL_LESSON_RE = re.compile(r"/classroom/", re.I)                # a lesson page (host alone ≠ video)
_TRANSCRIPT_TIMEOUT_DEFAULT = 300                                   # Q-044-4 (env-overridable)

# Embedded-video discovery on a not_video html page (R-13). Discovery runs over RAW HTML (the html
# skill strips <iframe>/<video> before Markdown), so ad-exclusion is FIRST-CLASS & always-on.
_EMBED_FETCH_MAX_BYTES = 2 * 1024 * 1024                            # size-cap on the raw-HTML GET
_EMBED_CONTEXT_WINDOW = 600                                        # bounded char window for ad-context
_EMBED_ALLOW_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com", "vimeo.com")  # SSRF egress bound
_AD_NETWORK_HOSTS = ("doubleclick.net", "googlesyndication.com", "googleads.g.doubleclick.net",
                     "g.doubleclick.net", "imasdk.googleapis.com", "2mdn.net", "adnxs.com",
                     "adservice.google.")
_AD_PARAM_KEYS = ("ad_type", "adformat", "ad_companion")
# bounded, anchored alternation (no nested quantifiers — ReDoS-safe) over a fixed-length window
_AD_CONTEXT_RE = re.compile(
    r"\b(?:ads?|advert\w{0,12}|advertising|sponsored?|promo\w{0,8}|dfp|adsbygoogle|googlead\w{0,8}|"
    r"outbrain|taboola|recommend\w{0,4}|related|widget)\b", re.I)
_IFRAME_SRC_RE = re.compile(r"""<iframe\b[^>]{0,2000}?\bsrc=["']([^"']{1,2000})["']""", re.I)


@dataclass
class FetchResult:
    ok: bool
    raw_text: str | None = None          # converted markdown/text (None on failure)
    title: str | None = None
    author: str | None = None
    date: str | None = None
    engine: str = ""                     # provenance of the fetch (html / pdf / local-md / transcript:<origin>)
    error: dict[str, Any] | None = None  # html/pdf typed error envelope on failure
    attachments_dir: Path | None = None  # downloaded images (image-import ON) → caller files them
    quality_flag: str | None = None      # transcript stat quality_flag (e.g. english_auto_translation — R-8)
    embed_log: list[dict[str, Any]] | None = None  # per-embed discovery/skip log (--embedded-videos, R-13f)


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
    """Pull title/author/date out of an `html`-skill YAML frontmatter block (best effort)."""
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
    """True iff `target` is an x.com/twitter URL whose `html`-skill output is just the
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

def _fetch_html(html_bin: str, target: str, *, download_images: bool = False) -> FetchResult:
    """URL/local HTML → markdown via the `html` skill, OUTPUT-DIR mode + ``--reader-only``:
    the skill writes a SINGLE ``<slug>.md`` = the reader extraction (main content, no
    nav/chrome), with its own whole-page fallback when the reader is empty/over-stripped —
    so notes never get the chrome-laden whole page and there is no variant to choose here.
    With ``download_images`` it keeps just the images the text references in a sibling
    ``_attachments/``; else remote URLs are kept verbatim. (The skill owns the
    Wikipedia-REST-HTML / arXiv rewrites + its own SSRF + ``--max-images`` bound.)"""
    bin_path = require_bin(html_bin, "html")
    tmpdir = tempfile.mkdtemp(prefix="wiki-import-fetch-")

    def _cleanup() -> None:
        shutil.rmtree(tmpdir, ignore_errors=True)

    def _fail(kind: str, code: int = 1) -> FetchResult:
        _cleanup()
        return FetchResult(ok=False, engine="html", error={
            "error": "FetchFailed", "type": "FetchFailed", "exit_code": code,
            "details": {"url": target, "kind": kind}})

    img_flag = "--download-images" if download_images else "--no-download-images"
    # --reader-only: the skill emits a SINGLE <slug>.md = reader extraction (with its OWN
    # whole-page fallback when reader is empty), so notes get clean body with no nav chrome
    # and no whole-page file to choose between.
    argv = ["python3", bin_path, target, tmpdir, img_flag,
            "--reader-only", "--json-errors", "--engine", "auto"]
    # A hung/over-long fetch (slow/hostile host, huge page — exactly what the timeout exists
    # for) must NOT escape as a raw traceback that ALSO orphans `tmpdir` (Decision-17 + the
    # mkdtemp lifecycle). `_fail` cleans the temp dir and returns a typed FETCH_FAILED.
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=_HTML_TIMEOUT, env=_skill_env())
    except subprocess.TimeoutExpired:
        return _fail("timeout", code=EXIT_FETCH_FAILED)
    except (OSError, ValueError):  # spawn failure — clean envelope, never a raw traceback
        return _fail("spawn_failed", code=EXIT_FETCH_FAILED)
    if proc.returncode != 0:
        _cleanup()
        return FetchResult(ok=False, engine="html",
                           error=_parse_skill_error(proc.stderr, proc.returncode))

    out = Path(tmpdir)
    # --reader-only ⇒ a SINGLE <slug>.md (the reader extraction, with the skill's own
    # whole-page fallback already applied). Read that one file; the reader-vs-whole choice
    # now lives in the skill, not here. (Exclude any `.reader.md` defensively.)
    mds = [p for p in out.glob("*.md") if not p.name.endswith(".reader.md")]
    md = mds[0].read_text(encoding="utf-8", errors="replace") if mds else ""
    if not md.strip():
        return _fail("no_output")
    if _is_x_login_wall(md, target):  # logged-out X chrome only → no post text
        _cleanup()
        return FetchResult(ok=False, engine="html", error={
            "error": "x.com returned only the logged-out login wall (no post text "
                     "captured); save the thread/article as a .webarchive while logged "
                     "in and import that file instead.",
            "type": "FetchFailed", "exit_code": EXIT_FETCH_FAILED,
            "details": {"url": target, "kind": "login_wall"}})

    # Keep only the images the markdown references (defensive prune; with --reader-only the
    # skill already downloads just the reader's images) — less junk in `_attachments/`.
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
        ok=True, raw_text=md, engine="html", attachments_dir=attach,
        title=fm.get("title") or None,
        author=fm.get("author") or None,
        date=(fm.get("date") or fm.get("published") or None))


def _parse_skill_error(stderr: str, returncode: int) -> dict[str, Any]:
    # generic: extracts the last single-line JSON error envelope from the html OR pdf skill stderr
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


# ---- TASK 044: video-host classification + transcript fetch ----------------

def _video_host(url: str) -> str:
    """Classify `url` by video modality — PURE, URL-shape only, no I/O (R-1). Returns one of
    `"unambiguous_video"` (the URL IS a video — YouTube/Vimeo/Skool-lesson/X-broadcast/space),
    `"ambiguous_x_status"` (an x.com status — text OR text+video), or `"not_video"`. Host matching
    is label-boundary (`evil-youtube.com` / `youtube.com.evil.net` → `not_video`)."""
    if not url.startswith(("http://", "https://")):
        return "not_video"
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    path = parts.path or ""

    def _host_in(hosts: tuple[str, ...]) -> bool:
        return any(host == h or host.endswith("." + h) for h in hosts)

    if _host_in(_VIDEO_HOSTS_YOUTUBE) or _host_in(_VIDEO_HOSTS_VIMEO):
        return "unambiguous_video"
    if _host_in(_VIDEO_HOSTS_SKOOL):
        return "unambiguous_video" if _SKOOL_LESSON_RE.search(path) else "not_video"
    if _host_in(_X_HOSTS):
        if _X_BROADCAST_RE.search(path):
            return "unambiguous_video"
        if _X_STATUS_RE.search(path):
            return "ambiguous_x_status"
    return "not_video"


def _transcript_python(script_path: str) -> str:
    """transcript-fetcher ships its deps in `scripts/.venv`; prefer that interpreter (mirrors
    `_pdf_python`). Falls back to `python3` when the venv is absent."""
    venv_py = Path(script_path).expanduser().resolve().parent / ".venv" / "bin" / "python"
    return str(venv_py) if venv_py.exists() else "python3"


def _transcript_timeout() -> int:
    try:
        return max(1, int(os.environ.get("WIKI_TRANSCRIPT_TIMEOUT_S",
                                         str(_TRANSCRIPT_TIMEOUT_DEFAULT))))
    except ValueError:
        return _TRANSCRIPT_TIMEOUT_DEFAULT


def _transcript_origin(stat: dict[str, Any]) -> str:
    """Provenance label for `engine="transcript:<origin>"`. `transcript_origin` is X-media-only
    (S0 finding — youtube/vimeo/skool never set it), so fall back to `chosen_track_kind`
    (+ `asr_backend` when ASR) rather than emit a meaningless `unknown` for the common case."""
    origin = stat.get("transcript_origin")
    if not origin:
        kind = stat.get("chosen_track_kind")
        origin = (stat.get("asr_backend") or "asr") if kind == "asr" else (kind or "unknown")
    return str(origin)


def _map_transcript_error(rc: int, stderr: str, url: str) -> FetchResult:
    """Map a transcript-fetcher non-zero exit into a wiki-import result (S0 translation table).
    Exit 7 (MissingDependency) RAISES `ImportArticleError` → prepare exit 6 (R-7); 3/5/6/other →
    a typed `FetchResult.error` the caller routes (no-media fallback / cookies hint / etc.)."""
    upstream = _parse_skill_error(stderr, rc)
    if rc == 7:  # MissingDependency (no ffmpeg / no ASR backend) → wiki-import DEP_MISSING (exit 6)
        remediation = (upstream.get("details", {}) or {}).get("remediation") \
            or "install ffmpeg + a whisper backend (whisper-cli, whisper.cpp, or MacWhisper)"
        raise ImportArticleError(
            "DEP_MISSING",
            f"transcript-fetcher reports a missing dependency: {remediation}",
            exit_code=EXIT_DEP_MISSING,
            details={"url": url, "kind": "no_asr_backend", "remediation": remediation,
                     "upstream": upstream})
    if rc == 3:  # no transcript producible → typed no-media marker (consumed by dispatch — R-6)
        return FetchResult(ok=False, engine="transcript", error={
            "error": "NoMedia", "type": "FetchFailed", "exit_code": EXIT_FETCH_FAILED,
            "details": {"url": url, "kind": "no_media", "upstream": upstream}})
    if rc == 5:  # source-auth (HTTP 401/403) → cookies guidance (R-10)
        return FetchResult(ok=False, engine="transcript", error={
            "error": "transcript source needs auth (HTTP 401/403); supply "
                     "--cookies-from-browser <browser> or --cookies-file <path>.",
            "type": "FetchFailed", "exit_code": EXIT_FETCH_FAILED,
            "details": {"url": url, "kind": "auth", "upstream": upstream}})
    if rc == 6:  # source rate-limit (HTTP 429) → transient FETCH_FAILED (S0 #3)
        return FetchResult(ok=False, engine="transcript", error={
            "error": "transcript source rate-limited (HTTP 429); retry later.",
            "type": "FetchFailed", "exit_code": EXIT_FETCH_FAILED,
            "details": {"url": url, "kind": "rate_limit", "upstream": upstream}})
    return FetchResult(ok=False, engine="transcript", error={  # 2 usage / 1 unexpected / other
        "error": "FetchFailed", "type": "FetchFailed", "exit_code": EXIT_FETCH_FAILED,
        "details": {"url": url, "kind": "transcript_error", "rc": rc, "upstream": upstream}})


def _fetch_transcript(transcript_bin: str, url: str, *, lang: str,
                      max_duration_min: float | None = None,
                      cookies_from_browser: str | None = None,
                      cookies_file: str | None = None) -> FetchResult:
    """URL → transcript via the transcript-fetcher skill (R-3). Shells out (argv array — NF-3a)
    to the skill's own venv python, reads the `.txt` + sibling `.stat.json`, sets
    `engine="transcript:<origin>"`, and maps typed exits. Temp dir reclaimed in a `finally`
    (R-3g). `--with-description` (so the stat carries title/uploader/date — S0) + `--lang`
    (ALWAYS, never the skill's `ru` default — C-3) + `--json-errors` are always passed."""
    bin_path = require_bin(transcript_bin, "transcript")
    tmpdir = tempfile.mkdtemp(prefix="wiki-import-transcript-")
    out_txt = Path(tmpdir) / "t.txt"
    argv = [_transcript_python(bin_path), bin_path, url, "--out", str(out_txt),
            "--json-errors", "--with-description", "--lang", lang]
    if max_duration_min is not None:
        argv += ["--max-duration-min", str(max_duration_min)]
    if cookies_from_browser:
        argv += ["--cookies-from-browser", cookies_from_browser]
    if cookies_file:
        argv += ["--cookies-file", cookies_file]

    def _fail(kind: str) -> FetchResult:
        return FetchResult(ok=False, engine="transcript", error={
            "error": "FetchFailed", "type": "FetchFailed", "exit_code": EXIT_FETCH_FAILED,
            "details": {"url": url, "kind": kind}})

    try:
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=_transcript_timeout(), env=_skill_env())
        except subprocess.TimeoutExpired:
            return _fail("timeout")
        except (OSError, ValueError):
            return _fail("spawn_failed")
        if proc.returncode != 0:
            return _map_transcript_error(proc.returncode, proc.stderr, url)
        raw_text = out_txt.read_text(encoding="utf-8", errors="replace") if out_txt.exists() else ""
        if not raw_text.strip():
            return _fail("no_output")
        stat: dict[str, Any] = {}
        sidecar = Path(str(out_txt) + ".stat.json")
        if sidecar.exists():
            try:
                loaded = json.loads(sidecar.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    stat = loaded
            except (json.JSONDecodeError, OSError):
                stat = {}
        return FetchResult(
            ok=True, raw_text=raw_text, engine=f"transcript:{_transcript_origin(stat)}",
            title=(stat.get("title") or None), author=(stat.get("uploader") or None),
            date=(stat.get("upload_date") or None), quality_flag=(stat.get("quality_flag") or None))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _fetch_x_status_with_video(html_bin: str, transcript_bin: str, url: str, *, lang: str,
                               download_images: bool = False,
                               max_duration_min: float | None = None,
                               cookies_from_browser: str | None = None,
                               cookies_file: str | None = None) -> FetchResult:
    """Decision 3 (R-5): `--video` on an x-status → CONCATENATE the tweet prose (html) with the
    video transcript. A transcript failure (no-media/auth/rate/dep) degrades to html-only when the
    tweet text is available; only when html ALSO fails is the transcript error surfaced."""
    html_res = _fetch_html(html_bin, url, download_images=download_images)
    try:
        tr = _fetch_transcript(transcript_bin, url, lang=lang, max_duration_min=max_duration_min,
                               cookies_from_browser=cookies_from_browser, cookies_file=cookies_file)
    except ImportArticleError:
        # video dep-missing: the tweet text is still useful → html-only WHEN html succeeded; but if
        # html ALSO failed (e.g. a login-walled tweet) re-raise so prepare surfaces the actionable
        # DEP_MISSING (exit 6 + remediation), not a generic FETCH_FAILED (symmetric with the no-media/
        # auth/rate branch below; matches this function's contract — VDD L-1).
        if html_res.ok:
            return html_res
        raise
    if not tr.ok:
        return html_res if html_res.ok else tr   # no-media/auth/rate → html-only (R-5d/R-6)
    if not html_res.ok:
        return tr                                 # transcript-only (R-5c)
    body = (f"## Tweet\n\n{html_res.raw_text}\n\n"
            f"## Video Transcript\n\n{tr.raw_text}")
    return FetchResult(ok=True, raw_text=body, engine=f"html+{tr.engine}",
                       title=(html_res.title or tr.title),
                       author=(html_res.author or tr.author),
                       date=(html_res.date or tr.date),
                       quality_flag=tr.quality_flag,
                       attachments_dir=html_res.attachments_dir)


# ---- TASK 044 / R-13: embedded-video discovery (opt-in --embedded-videos) ----

def _download_raw_html(url: str) -> str:
    """Size-capped raw-HTML GET for embed discovery (mirrors `_download_pdf`; R-13b). The network
    call lives HERE so `_discover_embedded_videos` stays a pure string→list function (Decision-17)."""
    req = urllib.request.Request(
        url, headers={"User-Agent": _PDF_FETCH_UA, "Accept": "text/html,*/*"})
    chunks: list[bytes] = []
    total = 0
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (operator URL)
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > _EMBED_FETCH_MAX_BYTES:
                break
            chunks.append(chunk)
    return b"".join(chunks).decode("utf-8", errors="replace")


def _embed_allowlisted(url: str) -> bool:
    """SSRF egress bound (R-13c): only youtube/vimeo embed hosts are ever fetched."""
    host = (urlsplit(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in _EMBED_ALLOW_HOSTS)


def _discover_embedded_videos(raw_html: str) -> list[tuple[str, str]]:
    """PURE string→list (R-13b): scan raw HTML for `<iframe src>` and run the FIXED ad-exclusion
    filter chain — allowlist → ad-network denylist → ad-context → ad-param → dedup. Returns an
    ORDERED `(url, reason)` log for EVERY discovered embed (reason ∈ keep/not-allowlisted/
    ad-denylist/ad-context/ad-param/dedup) — no silent drops (R-13f). Ad-exclusion is always-on."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for m in _IFRAME_SRC_RE.finditer(raw_html):
        url = m.group(1).strip()
        if url.startswith("//"):
            url = "https:" + url
        if not _embed_allowlisted(url):
            out.append((url, "not-allowlisted"))
            continue
        if any(h in url.lower() for h in _AD_NETWORK_HOSTS):   # belt-and-braces: youtube-hosted IMA/ad
            out.append((url, "ad-denylist"))
            continue
        window = raw_html[max(0, m.start() - _EMBED_CONTEXT_WINDOW):m.start()]
        if _AD_CONTEXT_RE.search(window):                      # enclosing ad/related/aside slot
            out.append((url, "ad-context"))
            continue
        if any(k in urlsplit(url).query.lower() for k in _AD_PARAM_KEYS):
            out.append((url, "ad-param"))
            continue
        if url in seen:
            out.append((url, "dedup"))
            continue
        seen.add(url)
        out.append((url, "keep"))
    return out


def _append_embedded_videos(res: FetchResult, page_url: str, *, transcript_bin: str,
                            lang: str, max_n: int) -> None:
    """R-13: discover allowlisted, NON-AD video embeds on a `not_video` page and APPEND their
    transcripts to `res.raw_text` (best-effort, additive — a per-embed failure NEVER aborts the
    page; contrast the hard-fail on an unambiguous_video URL). Records the full skip-reason log on
    `res.embed_log` (R-13f). Cap-dropped keeps are logged `cap`; nothing is silently truncated."""
    try:
        raw_html = _download_raw_html(page_url)
    except Exception as e:  # noqa: BLE001 — the page import already succeeded; embeds are best-effort
        res.embed_log = [{"reason": "discovery-failed", "detail": str(e)[:200]}]
        return
    log: list[dict[str, Any]] = []
    sections: list[str] = []
    fetched = 0
    qflag: str | None = None
    for url, reason in _discover_embedded_videos(raw_html):
        if reason != "keep":
            log.append({"url": url, "reason": reason})
            continue
        if fetched >= max_n:
            log.append({"url": url, "reason": "cap"})
            continue
        try:
            tr = _fetch_transcript(transcript_bin, url, lang=lang)
        except ImportArticleError:
            log.append({"url": url, "reason": "transcript-failure:dep"})
            continue
        if not tr.ok:
            k = (tr.error or {}).get("details", {}).get("kind", "fail")
            log.append({"url": url, "reason": f"transcript-failure:{k}"})
            continue
        fetched += 1
        qflag = qflag or tr.quality_flag
        log.append({"url": url, "reason": "fetched", "origin": tr.engine})
        sections.append(f"\n\n## Embedded video {fetched} — {tr.title or url}\n\n{tr.raw_text}")
    if sections:
        res.raw_text = (res.raw_text or "") + "".join(sections)
        res.engine = f"{res.engine}+embedded:{fetched}"
        if qflag and not res.quality_flag:
            res.quality_flag = qflag
    res.embed_log = log


# ---- public dispatch -------------------------------------------------------

def dispatch_fetch(source: str, *, html_bin: str, pdf_extract_bin: str,
                   download_images: bool = False,
                   transcript_bin: str | None = None, video: bool = False,
                   embedded_videos: bool = False, embedded_videos_max: int = 5,
                   lang: str = "en", max_duration_min: float | None = None,
                   cookies_from_browser: str | None = None,
                   cookies_file: str | None = None) -> FetchResult:
    """Route `source` (URL or local file) to transcript / html / pdf and return a FetchResult.

    TASK 044 prepends a media-tier BEFORE the html branch: an `unambiguous_video` URL goes to the
    transcript-fetcher skill; an `ambiguous_x_status` goes to transcript ONLY with `video=True`
    (else the existing html path, zero regression — NF-2). `embedded_videos` additively appends
    transcripts of allowlisted, non-ad embeds found on a `not_video` html page. With all new flags
    unset (and `transcript_bin=None`), behavior is byte-for-byte the pre-TASK-044 html/pdf dispatch.

    `download_images` (config-driven; default ON at the prepare layer) makes the html skill path
    download images into a sibling `_attachments/`. Never writes anything — the caller persists
    `_raw/` only on a non-empty `ok` result.
    """
    is_url = source.startswith(("http://", "https://"))
    bare = source.split("?", 1)[0].lower()
    host_class = _video_host(source) if is_url else "not_video"

    # --- media-tier (R-2) ---
    if is_url and host_class == "unambiguous_video":
        # the URL IS the video → transcript only; no html fallback (exit-3 no-media is a hard
        # FETCH_FAILED here — C-1; exit-7 dep raises → prepare exit 6 — R-7).
        return _fetch_transcript(transcript_bin or "", source, lang=lang,
                                 max_duration_min=max_duration_min,
                                 cookies_from_browser=cookies_from_browser,
                                 cookies_file=cookies_file)
    if is_url and host_class == "ambiguous_x_status" and video:
        return _fetch_x_status_with_video(
            html_bin, transcript_bin or "", source, lang=lang,
            download_images=download_images, max_duration_min=max_duration_min,
            cookies_from_browser=cookies_from_browser, cookies_file=cookies_file)

    # --- existing dispatch (unchanged for not_video / default x-status) ---
    if is_url and not bare.endswith(".pdf"):
        res = _fetch_html(html_bin, source, download_images=download_images)
        if res.ok:
            # R-13: optionally append non-ad embedded-video transcripts on a not_video page
            if embedded_videos and host_class == "not_video":
                _append_embedded_videos(res, source, transcript_bin=transcript_bin or "",
                                        lang=lang, max_n=embedded_videos_max)
            return res
        # the html skill says "HTML-only article has no HTML, use the PDF" → fall back.
        kind = (res.error or {}).get("details", {}).get("kind")
        if kind == "arxiv_no_html":
            pdf_url = _arxiv_pdf_url(source)
            if pdf_url:
                return _fetch_pdf_url(pdf_extract_bin, pdf_url)
        # The URL serves a PDF despite no `.pdf` suffix (e.g. dl.acm.org/doi/pdf/…,
        # CDN/hubfs links): the html skill reports details.kind=="pdf". Download + extract via
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
    # any other local file → let the html skill try (it handles .html/.htm/.mhtml/.webarchive)
    return _fetch_html(html_bin, str(p), download_images=download_images)
