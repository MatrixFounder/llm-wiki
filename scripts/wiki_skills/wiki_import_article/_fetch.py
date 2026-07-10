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

import importlib.util
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
_OFFICE_TIMEOUT = 240  # TASK 046: LibreOffice headless convert
# --- Vendor-agnostic external-skill binary resolution (no hardcoded harness list) ----
# The acquire skills (html/pdf/pptx/transcript-fetcher) are EXTERNAL — installed by the
# operator's harness into a per-harness skills dir. wiki-import must not assume Claude
# Code, NOR a fixed roster of harnesses (there are many, and new ones appear). A default
# bin path resolves via  $WIKI_<BIN> env  →  DISCOVERED skill roots (every `<dotdir>/skills`
# under $HOME + XDG dirs + $WIKI_SKILLS_DIRS — so claude/pi/codex/hermes/openclaw/… AND
# future harnesses are found with NO code change)  →  (later, in `require_bin`) PATH  →
# DEPENDENCY_MISSING. The scan also handles per-skill NAMING (the html skill dir is `html`
# on Claude but `html2md` on pi). A `--*-bin` flag and $WIKI_<BIN> (installer-populated
# skills.env) override everything below.
# key → (env var, candidate skill-dir names [first = canonical], entry path inside the skill)
_SKILL_BIN_SPEC: dict[str, tuple[str, tuple[str, ...], str]] = {
    "html":            ("WIKI_HTML_BIN",        ("html", "html2md"),      "scripts/html2md.py"),
    "pdf_extract":     ("WIKI_PDF_EXTRACT_BIN", ("pdf",),                 "scripts/pdf_extract.py"),
    "soffice_wrapper": ("WIKI_SOFFICE_WRAPPER", ("pptx",),               "scripts/_soffice.py"),
    "transcript":      ("WIKI_TRANSCRIPT_BIN",  ("transcript-fetcher",), "scripts/fetch.py"),
    "vtt_cleaner":     ("WIKI_VTT_CLEANER",     ("transcript-fetcher",), "scripts/sources/_vtt_to_text.py"),
}


def _discover_skill_roots() -> list[Path]:
    """Discover external-skill root dirs UNIVERSALLY — no hardcoded harness list. Order:
    explicit ``$WIKI_SKILLS_DIRS`` (os.pathsep-separated) first, then every ``<dotdir>/skills``
    under ``$HOME`` (any harness — ~/.claude, ~/.pi, ~/.codex, ~/.hermes, ~/.openclaw, …
    present OR future), then ``*/skills`` under ``$XDG_CONFIG_HOME``/``$XDG_DATA_HOME``.
    De-duplicated, existing dirs only (glob returns only what is on disk).
    """
    roots: dict[str, None] = {}
    for d in (os.environ.get("WIKI_SKILLS_DIRS") or "").split(os.pathsep):
        d = d.strip()
        if d:
            roots.setdefault(str(Path(d).expanduser()), None)
    home = Path.home()
    for p in sorted(home.glob(".*/skills")):
        roots.setdefault(str(p), None)
    for base in (os.environ.get("XDG_CONFIG_HOME") or str(home / ".config"),
                 os.environ.get("XDG_DATA_HOME") or str(home / ".local/share")):
        bp = Path(base).expanduser()
        if bp.is_dir():
            for p in sorted(bp.glob("*/skills")):
                roots.setdefault(str(p), None)
    return [Path(r) for r in roots]


def resolve_skill_bin(key: str) -> str:
    """Resolve the default path to an external acquire-skill binary, vendor-agnostically.

    Precedence: ``$WIKI_<BIN>`` env var → first EXISTING match while scanning the DISCOVERED
    skill roots (× per-skill dir-name candidates, e.g. ``html``/``html2md``) → a best-effort
    path for a clear ``DEPENDENCY_MISSING`` message. A ``--*-bin`` CLI flag overrides entirely.
    """
    env_var, dir_names, rel = _SKILL_BIN_SPEC[key]
    override = os.environ.get(env_var)
    if override:
        return str(Path(override).expanduser())
    roots = _discover_skill_roots()
    for root in roots:
        for dname in dir_names:
            cand = root / dname / rel
            if cand.exists():
                return str(cand)
    # Nothing on disk → a best-effort default so `require_bin` can emit an actionable error
    # (absence → PATH miss → DEPENDENCY_MISSING with "install the skill / set $WIKI_<BIN> /
    # pass --*-bin"): under a discovered root if any exist, else the bare entry name.
    return str(roots[0] / dir_names[0] / rel) if roots else Path(rel).name


def _load_skills_env() -> None:
    """Auto-load the installer-written env pins so the acquire bins are picked up WITHOUT the
    operator sourcing anything by hand (this is what makes ``WIKI_*`` "automatic").

    Reads ``$XDG_CONFIG_HOME/obsidian-llm-wiki/skills.env`` (default ``~/.config/…``) and applies
    each ``WIKI_*`` assignment via ``setdefault`` — so a value already exported in the SHELL always
    wins over the file. Only ``WIKI_``-prefixed keys are honored (no arbitrary env import); an
    absent/malformed file is a silent no-op. Precedence end-to-end: ``--flag`` → shell ``$WIKI_*``
    → this file → harness-dir auto-scan → legacy fallback.
    """
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    env_file = Path(base) / "obsidian-llm-wiki" / "skills.env"
    try:
        text = env_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("export "):
            line = line[len("export "):]
        key, sep, val = line.partition("=")
        key = key.strip()
        if not sep or not key.startswith("WIKI_"):
            continue
        os.environ.setdefault(key, val.strip().strip('"').strip("'"))


_load_skills_env()  # populate os.environ from skills.env BEFORE the _DEFAULT_* below resolve

# TASK 046: the transcript-fetcher skill owns the canonical WebVTT de-timestamper; reuse it by
# path. TASK 046: the office skills ship a HARDENED soffice wrapper (throw-away UserInstallation
# profile, AF_UNIX sandbox shim, soffice-location fallback) — reuse it (ADR-001 "Wrap + Index").
# TASK 048: both now resolve vendor-agnostically via resolve_skill_bin (single source — no dup).
_DEFAULT_VTT_CLEANER = resolve_skill_bin("vtt_cleaner")
_DEFAULT_SOFFICE_WRAPPER = resolve_skill_bin("soffice_wrapper")
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
# TASK 057 (W3, Q-057-4): an x-status whose capture is just "<title>" + a link to a Broadcast/
# Space (+ chrome) is an ANNOUNCEMENT — importing the html is pure junk. AND-gated: BOTH a
# first-party broadcast/space link AND normalized prose under this floor (deliberately above
# the 220 login-wall floor — reader output for a bare announcement is chrome-heavy; a
# substantive tweet that merely links a broadcast must pass through — spec Risk 2).
_X_ANNOUNCEMENT_PROSE_FLOOR = 600
# absolute-URL form of the _X_BROADCAST_RE route shape; allowlisted hosts only (H-6).
# id alphabet [A-Za-z0-9_-] aligns with the routing regex's \w (Phase-4 logic F2: a
# mismatch would truncate the surfaced broadcast_url at the first _/- and 404 the hint).
_X_BROADCAST_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:x|twitter)\.com/i/(?:broadcasts|spaces)/[A-Za-z0-9_-]+", re.I)

# ---- TASK 044: video sources via the transcript-fetcher skill ----------------
# Video-host classification (R-1) — pure URL-shape, label-boundary matched (reuses `_X_HOSTS`).
_VIDEO_HOSTS_YOUTUBE = ("youtube.com", "youtu.be", "youtube-nocookie.com")
_VIDEO_HOSTS_VIMEO = ("vimeo.com",)
_VIDEO_HOSTS_SKOOL = ("skool.com",)
_X_BROADCAST_RE = re.compile(r"/i/(?:broadcasts|spaces)/\w", re.I)   # has no usable text path
_X_STATUS_RE = re.compile(r"/[^/]+/status/\d+", re.I)               # text OR text+video (ambiguous)
_SKOOL_LESSON_RE = re.compile(r"/classroom/", re.I)                # a lesson page (host alone ≠ video)
# TASK 057 (W1-3, Q-057-2): the subprocess wall-clock is a HANG-GUARD, not a pacing knob
# (pacing = the skill's own duration-derived media timeout). Scoped by role: a PRIMARY fetch
# (the URL IS the content — unambiguous video / x-status --video) must cover parallel download
# + ASR of a ≥60-min broadcast; a SUPPLEMENTARY embedded-video fetch (best-effort, up to
# --embedded-videos-max sequential calls) keeps the old 300 s so hung embeds can never chain
# multi-hour stalls onto a page whose primary content already succeeded. Q-044-4 lineage:
# $WIKI_TRANSCRIPT_TIMEOUT_S (set → overrides BOTH roles) is unchanged; an explicit
# --transcript-media-timeout may additionally raise the PRIMARY hang-guard (never embeds).
_TRANSCRIPT_TIMEOUT_PRIMARY_S = 3600
_TRANSCRIPT_TIMEOUT_EMBED_S = 300

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
    source value cannot break the YAML, inject a key, or escape the closing quote (H-6).
    Includes the FULL `str.splitlines()` boundary set — NEL/LS/PS (\\x85 \\u2028 \\u2029) are
    line boundaries to `splitlines()` even though they are not \\n (Phase-4 security F1: an
    interior \\u2028 in a hostile title could smuggle a `classification:` "line" past the
    naive frontmatter parser and suppress the real quarantine stamp)."""
    return re.sub("[\\x00-\\x1f\\x7f\\x85\\u2028\\u2029\"\\\\]+", " ",
                  str(value or "")).strip()


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


def stamp_metadata_frontmatter(raw_text: str, *, title: str | None = None,
                               author: str | None = None,
                               date: str | None = None) -> str:
    """TASK 057 (W2 staging): fill MISSING `title:`/`author:`/`date:` frontmatter scalars so a
    staged out-of-vault capture round-trips its detected metadata through the local-md re-read
    (slug + provenance survive the fetch-free confirmed re-run). Existing keys always win;
    every stamped scalar routes through the same `_fm_safe` newline-strip+quote guard as
    `ensure_source_frontmatter` (H-6: a hostile page/broadcast title cannot break the YAML or
    inject a key). No-op when there is nothing to add."""
    fm = _parse_frontmatter(raw_text)
    additions = [f'{key}: "{_fm_safe(val)}"'
                 for key, val in (("title", title), ("author", author), ("date", date))
                 if val and not fm.get(key)]
    if not additions:
        return raw_text
    block = "\n".join(additions)
    if _FM_RE.match(raw_text):                       # existing FM at the very start
        return re.sub(r"\A---\n", f"---\n{block}\n", raw_text, count=1)
    return f"---\n{block}\n---\n\n{raw_text}"


def inject_classification(raw_text: str, level: str) -> str:
    """TASK 049 (R-7): stamp ``classification: <level>`` into the `_raw`
    capture's frontmatter — a DEDICATED injection, deliberately NOT riding
    ``ensure_source_frontmatter`` (whose already-cites-source early-return
    would silently skip the stamp — plan-review F3). Idempotent: an existing
    ``classification`` key is left untouched. ``level`` is argparse-shape-
    validated (``[a-z][a-z0-9_-]{0,15}``) so it is safe as a bare YAML scalar."""
    if "classification" in _parse_frontmatter(raw_text):
        return raw_text
    if _FM_RE.match(raw_text):                       # existing FM at the very start
        return re.sub(r"\A---\n", f"---\nclassification: {level}\n",
                      raw_text, count=1)
    return f"---\nclassification: {level}\n---\n\n{raw_text}"


# ---- helpers ---------------------------------------------------------------

def _parse_frontmatter(md: str) -> dict[str, str]:
    """Pull title/author/date out of an `html`-skill YAML frontmatter block (best effort).
    Splits on `\\n` ONLY — never `str.splitlines()`, whose wider boundary set (NEL/LS/PS)
    would let an exotic separator inside a quoted scalar masquerade as a new key line
    (Phase-4 security F1 defense-in-depth; PyYAML folds those separators, this naive
    parser must not out-split it)."""
    m = _FM_RE.match(md)
    out: dict[str, str] = {}
    if not m:
        return out
    for line in m.group(1).split("\n"):
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


def _normalized_prose(md: str) -> str:
    """The shared X-capture prose normalization (login-wall + announcement heuristics):
    drop frontmatter, drop `[..](..)`/`![..](..)` links, strip markdown punctuation,
    collapse whitespace. Behaviour-identical to the pre-057 inline login-wall code."""
    body = _FM_RE.sub("", md)                                   # drop frontmatter
    body = re.sub(r"!?\[[^\]]*\]\([^)]*\)", " ", body)          # drop [..](..) / ![..](..)
    return re.sub(r"\s+", " ", re.sub(r"[#>*`_|\[\]()\-]", " ", body)).strip()


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
    return len(_normalized_prose(md)) < _X_PROSE_FLOOR


def _announcement_only(md: str) -> str | None:
    """TASK 057 (W3): the broadcast/space URL when `md` (an x-status reader capture) is a
    contentless ANNOUNCEMENT of it, else None. AND-gated (Q-057-4): a first-party
    `/i/broadcasts/<id>` / `/i/spaces/<id>` link must be present AND the normalized prose
    must sit under `_X_ANNOUNCEMENT_PROSE_FLOOR` — a substantive tweet that also links a
    broadcast is NOT dropped. Searches the RAW markdown (links live in `[..](..)` targets,
    which the prose normalization strips). Pure string-shape — no network (Decision-17)."""
    m = _X_BROADCAST_URL_RE.search(md)
    if m is None:
        return None
    if len(_normalized_prose(md)) >= _X_ANNOUNCEMENT_PROSE_FLOOR:
        return None
    return m.group(0)


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
        # Phase-4 logic F6: a login-walled ANNOUNCEMENT (prose < 220 AND a broadcast link)
        # must still surface the broadcast_url + re-route hint (exit 0), not a dead-end
        # FETCH_FAILED — the actionable link is right there in the chrome.
        bc_url = _announcement_only(md)
        if bc_url is not None:
            return FetchResult(ok=False, engine="html", error={
                "error": "AnnouncementOnly", "type": "AnnouncementOnly", "exit_code": 0,
                "details": {"kind": "announcement_only",
                            "broadcast_url": bc_url, "url": target}})
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


# ---- TASK 046: office + caption local-file acquire -------------------------


def _read_text_fallback(path: Path) -> str:
    """Read a caption/text file tolerating non-UTF-8 (older RU captions ship CP1251/UTF-16).

    UTF-16 is detected by BOM and decoded FIRST: a bare ``utf-16`` decode reads any even-length
    byte string (so it would silently mis-decode BOM-less CP1251 as mojibake), and the near-total
    single-byte ``cp1251`` codec almost never raises (so a codec ladder with cp1251 before utf-16
    would shadow it — making UTF-16 support dead code). After the BOM check: ``utf-8-sig`` (strips
    a UTF-8 BOM, else == utf-8), then ``cp1251`` (legacy RU), then a lossy replace as last resort.
    UTF-32 is checked FIRST: a UTF-32 LE BOM (``\\xff\\xfe\\x00\\x00``) starts with the UTF-16 LE
    BOM bytes, so a 2-byte-first check would mis-decode a UTF-32 file as utf-16 mojibake.
    """
    data = path.read_bytes()
    if data[:4] in (b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff"):  # UTF-32 LE/BE BOM — BEFORE utf-16 (shares its 2-byte prefix)
        try:
            return data.decode("utf-32")
        except (UnicodeDecodeError, UnicodeError):
            pass
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):       # UTF-16 LE/BE BOM → the utf-16 codec auto-picks endianness
        try:
            return data.decode("utf-16")
        except (UnicodeDecodeError, UnicodeError):
            pass
    for enc in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return data.decode("utf-8", errors="replace")


def _load_vtt_cleaner(path: str = _DEFAULT_VTT_CLEANER) -> Any:
    """Import transcript-fetcher's `vtt_text_to_plain` by path (fail-fast, exit 6, if absent).

    Reusing the skill's tested cleaner (rolling-caption overlap, entity decode, encoding
    fallback) beats re-implementing it here — and the skill is already a wiki-import dependency.
    """
    p = Path(path).expanduser()
    spec = importlib.util.spec_from_file_location("_wiki_vtt_cleaner", p) if p.exists() else None
    if spec is None or spec.loader is None:
        raise ImportArticleError(
            "DEPENDENCY_MISSING",
            f"vtt cleaner not found at {path!r}; install the transcript-fetcher skill.",
            exit_code=EXIT_DEP_MISSING, details={"binary": path, "label": "vtt_cleaner"})
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.vtt_text_to_plain


# SubRip (.srt) cue header: `00:00:01,000 --> 00:00:02,000` (COMMA millisecond sep) and a
# standalone integer index line before each cue — neither is recognised by the VTT cleaner
# (its TS_RE requires a DOT). Normalise SRT → WebVTT-ish so the cleaner handles it.
_SRT_TS_RE = re.compile(
    r"^(\d{2}:\d{2}:\d{2}),(\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}),(\d{3})")
_SRT_INDEX_RE = re.compile(r"^\d+$")


def _srt_to_vtt(raw: str) -> str:
    """Minimal SRT→WebVTT normalisation: comma→dot in cue timestamps, and drop the standalone
    integer index line that precedes each cue (only when the next non-blank line IS a cue header).
    The index-line guard is BEST-EFFORT, not a guarantee — a bare-integer *caption* is preserved
    here, but the downstream cleaner skips bare-digit lines unconditionally, so such a caption may
    still be dropped later (and malformed SRT without cue separators is not handled)."""
    lines = raw.splitlines()
    out = ["WEBVTT", ""]
    for i, ln in enumerate(lines):
        s = ln.strip()
        m = _SRT_TS_RE.match(s)
        if m:
            out.append(f"{m.group(1)}.{m.group(2)} --> {m.group(3)}.{m.group(4)}")
            continue
        if _SRT_INDEX_RE.match(s):
            nxt = next((l.strip() for l in lines[i + 1:i + 3] if l.strip()), "")
            if _SRT_TS_RE.match(nxt):
                continue  # SRT sequence index → drop
        out.append(ln)
    return "\n".join(out)


def _vtt_to_text(path: Path, *, cleaner_path: str = _DEFAULT_VTT_CLEANER) -> FetchResult:
    """`.vtt`/`.srt` → de-timestamped plain text (TASK 046 R-7), via the skill's cleaner.
    `.srt` is normalised to WebVTT first (the cleaner is VTT-specific)."""
    raw = _read_text_fallback(path)
    if path.suffix.lower() == ".srt":
        raw = _srt_to_vtt(raw)
    cleaner = _load_vtt_cleaner(cleaner_path)
    text = cleaner(raw)
    return FetchResult(ok=bool(text and text.strip()), raw_text=text or None,
                       engine="vtt", title=path.stem)


def _load_soffice(path: str = _DEFAULT_SOFFICE_WRAPPER) -> Any:
    """Import the office skills' hardened soffice wrapper by path (fail-fast, exit 6, if absent).

    The wrapper (`pptx/scripts/_soffice.py`) gives a throw-away UserInstallation profile (no lock
    contention), the AF_UNIX sandbox shim, soffice-location fallback, and `convert_to()` — all of
    which a naive `soffice --headless` would miss. Same wrap-by-path posture as the vtt cleaner.
    """
    p = Path(path).expanduser()
    spec = importlib.util.spec_from_file_location("_wiki_soffice", p) if p.exists() else None
    if spec is None or spec.loader is None:
        raise ImportArticleError(
            "DEPENDENCY_MISSING",
            f"soffice wrapper not found at {path!r}; install the pptx/docx/xlsx skill "
            "(LibreOffice) or pass --soffice-wrapper.",
            exit_code=EXIT_DEP_MISSING, details={"binary": path, "label": "office"})
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _office_to_text(path: Path, *, wrapper_path: str = _DEFAULT_SOFFICE_WRAPPER) -> FetchResult:
    """`.docx`/`.pptx`/`.xlsx` → plain text via the hardened LibreOffice wrapper (TASK 046 R-6).

    Deterministic (Decision-17 — no LLM). A MISSING LibreOffice is a hard dependency error
    (exit 6, like html/pdf); a conversion that runs-but-fails is a TYPED FetchResult error
    (caller → FETCH_FAILED), never a junk `_raw`.
    """
    soffice = _load_soffice(wrapper_path)
    # Catch ONLY the wrapper's own error type (a RuntimeError subclass) — a genuine
    # TypeError/AttributeError from wrapper API drift must surface as a traceback, not be
    # mislabeled "install LibreOffice" / a soft convert failure.
    soffice_error = getattr(soffice, "SofficeError", Exception)
    try:
        soffice.find_soffice()  # LibreOffice itself absent → DEP_MISSING (exit 6)
    except soffice_error as e:
        raise ImportArticleError(
            "DEPENDENCY_MISSING", str(e), exit_code=EXIT_DEP_MISSING,
            details={"binary": "soffice", "label": "office"}) from e
    with tempfile.TemporaryDirectory() as td:
        try:
            produced = soffice.convert_to(path, td, "txt:Text", timeout=_OFFICE_TIMEOUT)
        except soffice_error:  # run-but-fail conversion → soft FETCH_FAILED
            # CWE-209: do NOT echo the SofficeError string — it carries the soffice command line
            # (the absolute source path) + raw LibreOffice stderr. Mirror the PDF path's posture:
            # a fixed typed error, no untrusted/path content in the structured envelope.
            return FetchResult(ok=False, engine="convert-office",
                               error={"error": "OfficeConvertFailed", "exit_code": 1,
                                      "detail": "LibreOffice could not convert the document"})
        # soffice writes UTF-8-with-BOM → utf-8-sig strips the leading ﻿ (else it would
        # surface as an invisible char at the head of the _raw body).
        text = Path(produced).read_text(encoding="utf-8-sig", errors="replace")
    return FetchResult(ok=bool(text.strip()), raw_text=text or None,
                       engine="convert-office", title=path.stem)


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


def _transcript_timeout(primary: bool = True) -> int:
    """Wall-clock for one transcript-fetcher subprocess. `WIKI_TRANSCRIPT_TIMEOUT_S` set →
    that value for BOTH roles; else 3600 s primary / 300 s embed (Q-057-2)."""
    default = _TRANSCRIPT_TIMEOUT_PRIMARY_S if primary else _TRANSCRIPT_TIMEOUT_EMBED_S
    try:
        return max(1, int(os.environ.get("WIKI_TRANSCRIPT_TIMEOUT_S", str(default))))
    except ValueError:
        return default


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
                      cookies_file: str | None = None,
                      concurrent_fragments: int | None = None,
                      media_timeout_sec: int | None = None,
                      primary: bool = True) -> FetchResult:
    """URL → transcript via the transcript-fetcher skill (R-3). Shells out (argv array — NF-3a)
    to the skill's own venv python, reads the `.txt` + sibling `.stat.json`, sets
    `engine="transcript:<origin>"`, and maps typed exits. Temp dir reclaimed in a `finally`
    (R-3g). `--with-description` (so the stat carries title/uploader/date — S0) + `--lang`
    (ALWAYS, never the skill's `ru` default — C-3) + `--json-errors` are always passed.
    TASK 057 (W1): `concurrent_fragments`/`media_timeout_sec` forward the skill's X-media
    robustness knobs — None OMITS the flag so the skill's own env/`.env`/duration-derived
    defaults rule (the policy stays skill-owned, never re-derived here)."""
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
    if concurrent_fragments is not None:
        argv += ["--concurrent-fragments", str(concurrent_fragments)]
    if media_timeout_sec is not None:
        argv += ["--media-timeout-sec", str(media_timeout_sec)]

    def _fail(kind: str) -> FetchResult:
        return FetchResult(ok=False, engine="transcript", error={
            "error": "FetchFailed", "type": "FetchFailed", "exit_code": EXIT_FETCH_FAILED,
            "details": {"url": url, "kind": kind}})

    # Phase-4 logic F1: an explicit --transcript-media-timeout larger than the wall-clock
    # would be silently SIGKILLed at the wall-clock — the exact W1 clip this task removes.
    # The operator's media budget therefore RAISES the hang-guard to budget + headroom —
    # on the PRIMARY role only (cycle-2 NEW-1): the skill applies the media budget to X
    # media alone, and embeds are youtube/vimeo-allowlisted, so on the embed role the knob
    # is a guaranteed no-op child-side and must never inflate the 300 s supplementary
    # bound (Q-057-2: hung embeds must not chain multi-hour stalls).
    wall_timeout = _transcript_timeout(primary)
    if primary:
        wall_timeout = max(wall_timeout, (media_timeout_sec or 0) + 300)
    try:
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=wall_timeout, env=_skill_env())
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
                               cookies_file: str | None = None,
                               concurrent_fragments: int | None = None,
                               media_timeout_sec: int | None = None) -> FetchResult:
    """Decision 3 (R-5): `--video` on an x-status → CONCATENATE the tweet prose (html) with the
    video transcript. A transcript failure (no-media/auth/rate/dep) degrades to html-only when the
    tweet text is available; only when html ALSO fails is the transcript error surfaced."""
    html_res = _fetch_html(html_bin, url, download_images=download_images)
    try:
        tr = _fetch_transcript(transcript_bin, url, lang=lang, max_duration_min=max_duration_min,
                               cookies_from_browser=cookies_from_browser, cookies_file=cookies_file,
                               concurrent_fragments=concurrent_fragments,
                               media_timeout_sec=media_timeout_sec)
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
                            lang: str, max_n: int,
                            concurrent_fragments: int | None = None,
                            media_timeout_sec: int | None = None) -> None:
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
            # embeds forward the W1 knobs too (the skill ignores them on non-X hosts);
            # primary=False → the 300 s supplementary wall-clock (Q-057-2)
            tr = _fetch_transcript(transcript_bin, url, lang=lang,
                                   concurrent_fragments=concurrent_fragments,
                                   media_timeout_sec=media_timeout_sec,
                                   primary=False)
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
                   soffice_wrapper: str = _DEFAULT_SOFFICE_WRAPPER,
                   download_images: bool = False,
                   transcript_bin: str | None = None, video: bool = False,
                   embedded_videos: bool = False, embedded_videos_max: int = 5,
                   lang: str = "en", max_duration_min: float | None = None,
                   cookies_from_browser: str | None = None,
                   cookies_file: str | None = None,
                   concurrent_fragments: int | None = None,
                   media_timeout_sec: int | None = None) -> FetchResult:
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
                                 cookies_file=cookies_file,
                                 concurrent_fragments=concurrent_fragments,
                                 media_timeout_sec=media_timeout_sec)
    if is_url and host_class == "ambiguous_x_status" and video:
        return _fetch_x_status_with_video(
            html_bin, transcript_bin or "", source, lang=lang,
            download_images=download_images, max_duration_min=max_duration_min,
            cookies_from_browser=cookies_from_browser, cookies_file=cookies_file,
            concurrent_fragments=concurrent_fragments,
            media_timeout_sec=media_timeout_sec)

    # --- existing dispatch (unchanged for not_video / default x-status) ---
    if is_url and not bare.endswith(".pdf"):
        res = _fetch_html(html_bin, source, download_images=download_images)
        if res.ok:
            # TASK 057 (W3): an x-status WITHOUT --video whose capture merely announces a
            # Broadcast/Space → typed marker, never a junk _raw. Reclaim the html temp dir
            # HERE (the ok-result is being replaced; prepare's _imgtmp owner never sees it) —
            # None-guarded: the no-images path already cleaned up (attachments_dir=None).
            if host_class == "ambiguous_x_status" and not video:
                bc_url = _announcement_only(res.raw_text or "")
                if bc_url is not None:
                    if res.attachments_dir:
                        shutil.rmtree(res.attachments_dir.parent, ignore_errors=True)
                    return FetchResult(ok=False, engine="html", error={
                        "error": "AnnouncementOnly", "type": "AnnouncementOnly",
                        "exit_code": 0,
                        "details": {"kind": "announcement_only",
                                    "broadcast_url": bc_url, "url": source}})
            # R-13: optionally append non-ad embedded-video transcripts on a not_video page
            if embedded_videos and host_class == "not_video":
                _append_embedded_videos(res, source, transcript_bin=transcript_bin or "",
                                        lang=lang, max_n=embedded_videos_max,
                                        concurrent_fragments=concurrent_fragments,
                                        media_timeout_sec=media_timeout_sec)
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
    if bare.endswith((".vtt", ".srt")):                       # TASK 046 R-7: caption → de-timestamp
        return _vtt_to_text(p)
    if bare.endswith((".docx", ".pptx", ".xlsx")):           # TASK 046 R-6: office → text (soffice)
        return _office_to_text(p, wrapper_path=soffice_wrapper)
    if bare.endswith((".md", ".markdown", ".txt")):
        text = p.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        return FetchResult(
            ok=bool(text.strip()), raw_text=text or None, engine="local-md",
            title=fm.get("title") or None, author=fm.get("author") or None,
            date=(fm.get("date") or fm.get("published") or None))
    # any other local file → let the html skill try (it handles .html/.htm/.mhtml/.webarchive)
    return _fetch_html(html_bin, str(p), download_images=download_images)
