"""TASK 057 / W3 — "announcement → Broadcast/Space" tweets never produce a junk `_raw`.

Offline: subprocess + require_bin are mocked. Covers the pure heuristic (057-03), the
dispatch marker + temp-dir reclaim, and the prepare short-circuit (057-04).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import scripts.wiki_skills.wiki_import_article as wia
from scripts.wiki_skills.wiki_import_article import _context, _fetch
from scripts.wiki_skills.wiki_import_article._fetch import (
    FetchResult,
    _announcement_only,
    _normalized_prose,
)

H2M = "/fake/html2md.py"
PDFX = "/fake/pdf_extract.py"
TBIN = "/fake/transcript_fetch.py"

BC_URL = "https://x.com/i/broadcasts/1abcDEF"

# 004-shaped capture: short announcement + broadcast link + nav/trending chrome, prose < 600.
ANNOUNCEMENT_MD = f"""---
title: Building AI-Native Startups [004]
---

Building AI-Native Startups [004] — starting soon!

[Join the broadcast]({BC_URL})

[Home](https://x.com/home) [Explore](https://x.com/explore) [Notifications](https://x.com/notifications)

Trending now · What's happening · Show more
"""

SUBSTANTIVE_MD = f"""---
title: Long thread
---

{"We shipped a deep architectural rework of the ingestion pipeline this quarter. " * 12}

Watch the recording: [broadcast]({BC_URL})
"""

PLAIN_TWEET_MD = """---
title: A normal tweet
---

Just a normal text tweet with some substance and no broadcast link at all.
"""


# ---------------------------------------------------------------- 057-03 pure heuristic

def test_announcement_only_matches_004_shape():
    assert _announcement_only(ANNOUNCEMENT_MD) == BC_URL


def test_announcement_spaces_url_and_twitter_host():
    md = ANNOUNCEMENT_MD.replace(BC_URL, "https://twitter.com/i/spaces/9zyx")
    assert _announcement_only(md) == "https://twitter.com/i/spaces/9zyx"


def test_substantive_tweet_with_broadcast_link_passes_through():
    assert len(_normalized_prose(SUBSTANTIVE_MD)) >= _fetch._X_ANNOUNCEMENT_PROSE_FLOOR
    assert _announcement_only(SUBSTANTIVE_MD) is None


def test_short_tweet_without_broadcast_link_passes_through():
    assert _announcement_only(PLAIN_TWEET_MD) is None


def test_non_allowlisted_host_never_matches():
    md = ANNOUNCEMENT_MD.replace(BC_URL, "https://evil.com/i/broadcasts/1abc")
    assert _announcement_only(md) is None


def test_lookalike_host_never_matches():
    # x.com.evil.net must not pass the host shape (the regex anchors the registrable host)
    md = ANNOUNCEMENT_MD.replace(BC_URL, "https://x.com.evil.net/i/broadcasts/1abc")
    assert _announcement_only(md) is None


# ---------------------------------------------------------------- 057-04 dispatch marker

@pytest.fixture(autouse=True)
def _no_real_bins(monkeypatch):
    monkeypatch.setattr(_fetch, "require_bin", lambda p, label: p)
    monkeypatch.setattr(_fetch, "_transcript_python", lambda p: "python3")


def _html_run(md):
    def fake_run(argv, **kw):
        if H2M in argv:
            (Path(argv[3]) / "p.md").write_text(md, encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0, "", "")
        if TBIN in argv:
            out = Path(argv[argv.index("--out") + 1])
            out.write_text("spoken words\n", encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0, "", "")
        return subprocess.CompletedProcess(argv, 0, "", "")
    return fake_run


def _dispatch(url, **kw):
    return _fetch.dispatch_fetch(url, html_bin=H2M, pdf_extract_bin=PDFX,
                                 transcript_bin=TBIN, **kw)


def test_dispatch_announcement_marker_on_x_status(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _html_run(ANNOUNCEMENT_MD))
    r = _dispatch("https://x.com/cyberfund/status/123")
    assert not r.ok
    d = (r.error or {}).get("details", {})
    assert d.get("kind") == "announcement_only" and d.get("broadcast_url") == BC_URL


def test_dispatch_announcement_with_video_routes_concat(monkeypatch):
    # --video → the existing concat path; the heuristic never runs (W3-3).
    monkeypatch.setattr(subprocess, "run", _html_run(ANNOUNCEMENT_MD))
    r = _dispatch("https://x.com/cyberfund/status/123", video=True)
    assert r.ok and "## Video Transcript" in (r.raw_text or "")


def test_dispatch_plain_tweet_unaffected(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _html_run(PLAIN_TWEET_MD))
    r = _dispatch("https://x.com/jack/status/123")
    assert r.ok and "normal text tweet" in (r.raw_text or "")


def test_dispatch_non_x_page_with_broadcast_link_unaffected(monkeypatch):
    # the heuristic is scoped to ambiguous_x_status URLs — a blog page linking a
    # broadcast imports as html even when its prose is short
    monkeypatch.setattr(subprocess, "run", _html_run(ANNOUNCEMENT_MD))
    r = _dispatch("https://example.com/post")
    assert r.ok


# ---------------------------------------------------------------- 057-04 prepare wiring

@pytest.fixture
def vault(tmp_path):
    (tmp_path / "WIKI_SCHEMA.md").write_text(
        "---\nvault_id: testv\nlayout: obsidian-personal\nlanguage: ru\n---\n",
        encoding="utf-8")
    (tmp_path / "03 - Learning" / "Webinars").mkdir(parents=True)
    return tmp_path


@pytest.fixture(autouse=True)
def _stub_context(monkeypatch):
    monkeypatch.setattr(_context, "known_concepts",
                        lambda repo, v, root, *, fmt="full": [])
    monkeypatch.setattr(_context, "existing_page_slugs", lambda *a, **k: [])


def test_prepare_announcement_exit0_no_writes(vault, monkeypatch, capsys):
    ann = FetchResult(ok=False, engine="html", error={
        "error": "AnnouncementOnly", "type": "AnnouncementOnly", "exit_code": 0,
        "details": {"kind": "announcement_only", "broadcast_url": BC_URL,
                    "url": "https://x.com/cyberfund/status/123"}})
    monkeypatch.setattr(wia, "dispatch_fetch", lambda *a, **k: ann)
    before = {str(p) for p in vault.rglob("*")}
    rc = wia.main(["prepare", "--vault", "testv", "--vault-root", str(vault),
                   "--db-path", str(vault / "index.db"),
                   "--source", "https://x.com/cyberfund/status/123",
                   "--folder", "03 - Learning/Webinars"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["action"] == "announcement_only"
    assert out["broadcast_url"] == BC_URL
    assert "--video" in out["hint"] and "broadcast" in out["hint"]
    assert {str(p) for p in vault.rglob("*")} == before   # vault byte-identical


def test_dispatch_announcement_reclaims_html_tempdir(monkeypatch, tmp_path):
    # an image-bearing announcement capture must not leak the html skill's temp dir
    att = tmp_path / "html-tmp" / "_attachments"
    att.mkdir(parents=True)
    (att / "avatar.png").write_bytes(b"x")

    def fake_fetch_html(html_bin, target, *, download_images=False):
        return FetchResult(ok=True, raw_text=ANNOUNCEMENT_MD, engine="html",
                           attachments_dir=att)

    monkeypatch.setattr(_fetch, "_fetch_html", fake_fetch_html)
    r = _dispatch("https://x.com/cyberfund/status/123")
    d = (r.error or {}).get("details", {})
    assert d.get("kind") == "announcement_only"
    assert not att.parent.exists()   # reclaimed at the point the ok-result was replaced


# ------------------------------------------------ Phase-4 adversarial fixes (cycle 1)

def test_broadcast_id_with_underscore_and_hyphen_captured_fully():  # F2
    url = "https://x.com/i/broadcasts/1ab_cD-99"
    md = ANNOUNCEMENT_MD.replace(BC_URL, url)
    assert _announcement_only(md) == url


def test_login_walled_announcement_surfaces_broadcast_not_login_wall(monkeypatch):  # F6
    md = f"""---
title: Ep 5
---

Log in

Sign up

[live]({BC_URL})
"""
    monkeypatch.setattr(subprocess, "run", _html_run(md))
    r = _dispatch("https://x.com/cyberfund/status/123")
    d = (r.error or {}).get("details", {})
    assert d.get("kind") == "announcement_only" and d.get("broadcast_url") == BC_URL


def test_login_wall_without_broadcast_link_still_login_wall(monkeypatch):  # F6 guard
    md = "---\ntitle: T\n---\n\nLog in\n\nSign up\n"
    monkeypatch.setattr(subprocess, "run", _html_run(md))
    r = _dispatch("https://x.com/cyberfund/status/123")
    d = (r.error or {}).get("details", {})
    assert d.get("kind") == "login_wall"
