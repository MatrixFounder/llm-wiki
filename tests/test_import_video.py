"""TASK 044 — video sources for wiki-import via transcript-fetcher.

Covers `_video_host` (R-1), `_fetch_transcript` (R-3/7/8/9/10/11), the `dispatch_fetch`
media-tier (R-2/5/6, incl. C-1 no-html-fallback on unambiguous_video), and the opt-in
embedded-video discovery with ALWAYS-ON ad-exclusion (R-13, incl. ADV-1 youtube-IMA denylist).
All offline: subprocess + `_download_raw_html` are mocked (the transcript binary is never run).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.wiki_skills.wiki_import_article import _fetch
from scripts.wiki_skills.wiki_import_article._detect import detect_kind
from scripts.wiki_skills.wiki_import_article._errors import (
    EXIT_DEP_MISSING, EXIT_FETCH_FAILED, ImportArticleError,
)

H2M = "/fake/html2md.py"
PDFX = "/fake/pdf_extract.py"
TBIN = "/fake/transcript_fetch.py"


@pytest.fixture(autouse=True)
def _no_real_bins(monkeypatch):
    monkeypatch.setattr(_fetch, "require_bin", lambda p, label: p)
    # the venv-python probe must not depend on the host fs
    monkeypatch.setattr(_fetch, "_transcript_python", lambda p: "python3")


def _cp(args, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args, returncode, stdout, stderr)


def _transcript_stat(**over):
    s = {"source": "youtube", "transcript_origin": None, "chosen_track_kind": "auto",
         "chosen_track_lang": "en", "char_count": 42, "speaker_turn_count": 1,
         "quality_flag": None, "title": "Vid Title", "uploader": "Some Channel",
         "upload_date": "2025-01-02"}
    s.update(over)
    return s


def _run_factory(*, t_rc=0, t_txt="Spoken transcript body.\n", t_stat=None, html_md=None):
    """A subprocess.run double that dispatches on the bin in argv: transcript vs html."""
    def fake_run(argv, **kw):
        if TBIN in argv:
            out = Path(argv[argv.index("--out") + 1])
            if t_rc == 0:
                out.write_text(t_txt, encoding="utf-8")
                Path(str(out) + ".stat.json").write_text(
                    json.dumps(t_stat or _transcript_stat()), encoding="utf-8")
                return _cp(argv, 0)
            err = json.dumps({"v": 1, "error": "boom", "code": t_rc, "type": "X",
                              "details": {"remediation": "install ffmpeg + a whisper backend"}})
            return _cp(argv, t_rc, "", err)
        if H2M in argv:  # html skill: writes a single <slug>.md into the output dir (argv[3])
            (Path(argv[3]) / "page.md").write_text(
                html_md or "---\ntitle: Page\n---\n\nArticle prose.\n", encoding="utf-8")
            return _cp(argv, 0)
        return _cp(argv, 0)
    return fake_run


# ---------------------------------------------------------------- R-1 _video_host
@pytest.mark.parametrize("url,expected", [
    ("https://www.youtube.com/watch?v=abc", "unambiguous_video"),
    ("https://youtu.be/abc", "unambiguous_video"),
    ("https://music.youtube.com/watch?v=abc", "unambiguous_video"),
    ("https://vimeo.com/12345", "unambiguous_video"),
    ("https://player.vimeo.com/video/12345", "unambiguous_video"),
    ("https://www.skool.com/community/classroom/abc?md=lesson1", "unambiguous_video"),
    ("https://www.skool.com/community/about", "not_video"),
    ("https://x.com/i/broadcasts/1abc", "unambiguous_video"),
    ("https://twitter.com/i/spaces/1abc", "unambiguous_video"),
    ("https://x.com/jack/status/123", "ambiguous_x_status"),
    ("https://twitter.com/jack/status/123", "ambiguous_x_status"),
    ("https://example.com/article", "not_video"),
    ("https://evil-youtube.com/x", "not_video"),       # label-boundary
    ("https://youtube.com.evil.net/x", "not_video"),   # label-boundary
    ("/local/file.md", "not_video"),
])
def test_video_host_truth_table(url, expected):
    assert _fetch._video_host(url) == expected


# ---------------------------------------------------------------- R-3 _fetch_transcript
def test_fetch_transcript_ok_origin_falls_back_to_chosen_kind(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _run_factory())
    r = _fetch._fetch_transcript(TBIN, "https://youtu.be/x", lang="en")
    assert r.ok and r.raw_text.startswith("Spoken transcript")
    # transcript_origin is None for youtube → engine falls back to chosen_track_kind (S0 fix #1)
    assert r.engine == "transcript:auto"
    assert (r.title, r.author, r.date) == ("Vid Title", "Some Channel", "2025-01-02")


def test_fetch_transcript_argv_always_lang_with_description_json_errors(monkeypatch):
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"] = argv
        out = Path(argv[argv.index("--out") + 1])
        out.write_text("body\n", encoding="utf-8")
        Path(str(out) + ".stat.json").write_text(json.dumps(_transcript_stat()), encoding="utf-8")
        return _cp(argv, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    _fetch._fetch_transcript(TBIN, "https://youtu.be/x", lang="ru")
    argv = seen["argv"]
    assert "--json-errors" in argv and "--with-description" in argv
    assert argv[argv.index("--lang") + 1] == "ru"   # C-3: always forwarded, never the skill ru default


def test_fetch_transcript_origin_x_embedded_captions(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _run_factory(
        t_stat=_transcript_stat(transcript_origin="embedded-captions", source="x")))
    r = _fetch._fetch_transcript(TBIN, "https://x.com/i/broadcasts/1", lang="en")
    assert r.engine == "transcript:embedded-captions"


def test_fetch_transcript_quality_flag_surfaced(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _run_factory(
        t_stat=_transcript_stat(quality_flag="english_auto_translation")))
    r = _fetch._fetch_transcript(TBIN, "https://youtu.be/x", lang="en")
    assert r.quality_flag == "english_auto_translation"


def test_fetch_transcript_exit7_raises_dep_missing(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _run_factory(t_rc=7))
    with pytest.raises(ImportArticleError) as ei:
        _fetch._fetch_transcript(TBIN, "https://x.com/i/broadcasts/1", lang="en")
    assert ei.value.exit_code == EXIT_DEP_MISSING


def test_fetch_transcript_exit3_no_media_marker(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _run_factory(t_rc=3))
    r = _fetch._fetch_transcript(TBIN, "https://youtu.be/x", lang="en")
    assert not r.ok and r.error["details"]["kind"] == "no_media"


def test_fetch_transcript_exit5_cookies_hint(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _run_factory(t_rc=5))
    r = _fetch._fetch_transcript(TBIN, "https://vimeo.com/1", lang="en")
    assert not r.ok and r.error["details"]["kind"] == "auth"
    assert "cookies" in r.error["error"].lower()


def test_fetch_transcript_exit6_rate_limit(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _run_factory(t_rc=6))
    r = _fetch._fetch_transcript(TBIN, "https://youtu.be/x", lang="en")
    assert not r.ok and r.error["details"]["kind"] == "rate_limit"


# ---------------------------------------------------------------- R-2 dispatch media-tier
def _dispatch(url, **kw):
    return _fetch.dispatch_fetch(url, html_bin=H2M, pdf_extract_bin=PDFX, transcript_bin=TBIN, **kw)


def test_dispatch_youtube_auto_routes_transcript(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _run_factory())
    r = _dispatch("https://youtu.be/abc")
    assert r.ok and r.engine.startswith("transcript:")


def test_dispatch_x_status_default_stays_html(monkeypatch):
    calls = {"transcript": 0}

    def fake_run(argv, **kw):
        if TBIN in argv:
            calls["transcript"] += 1
        if H2M in argv:
            (Path(argv[3]) / "p.md").write_text("---\ntitle: T\n---\n\nTweet text.\n", encoding="utf-8")
        return _cp(argv, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    r = _dispatch("https://x.com/jack/status/123")   # no --video
    assert r.ok and r.engine == "html" and calls["transcript"] == 0   # NF-2: transcript NOT invoked


def test_dispatch_youtube_no_media_is_fetch_failed_no_html_fallback(monkeypatch):
    # C-1: exit-3 on an unambiguous_video URL → FETCH_FAILED, NO junk-html fallback.
    calls = {"html": 0}

    def fake_run(argv, **kw):
        if H2M in argv:
            calls["html"] += 1
            (Path(argv[3]) / "p.md").write_text("x", encoding="utf-8")
        if TBIN in argv:
            return _cp(argv, 3, "", json.dumps({"error": "x", "code": 3, "details": {}}))
        return _cp(argv, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    r = _dispatch("https://youtu.be/abc")
    assert not r.ok and calls["html"] == 0   # html never tried for an unambiguous-video host


def test_dispatch_broadcast_no_asr_raises(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _run_factory(t_rc=7))
    with pytest.raises(ImportArticleError) as ei:
        _dispatch("https://x.com/i/broadcasts/1abc")
    assert ei.value.exit_code == EXIT_DEP_MISSING


def test_dispatch_not_video_byte_unchanged(monkeypatch):
    # NF-2: a plain article URL takes the existing html path; no transcript/embedded work.
    monkeypatch.setattr(subprocess, "run", _run_factory(html_md="---\ntitle: A\n---\n\nProse.\n"))
    r = _dispatch("https://example.com/article")
    assert r.ok and r.engine == "html" and r.embed_log is None


# ---------------------------------------------------------------- R-5 x-status concat
def test_dispatch_x_status_video_concatenates(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _run_factory(
        html_md="---\ntitle: Tw\n---\n\nThe tweet prose.\n", t_txt="The spoken words.\n"))
    r = _dispatch("https://x.com/jack/status/123", video=True)
    assert r.ok
    assert "## Tweet" in r.raw_text and "## Video Transcript" in r.raw_text
    assert "The tweet prose." in r.raw_text and "The spoken words." in r.raw_text
    assert r.engine.startswith("html+transcript:")


def test_dispatch_x_status_video_dep_missing_but_html_ok_returns_html(monkeypatch):
    # dep-missing on the video but the tweet text IS available → graceful html-only (no raise).
    def fake_run(argv, **kw):
        if H2M in argv:
            (Path(argv[3]) / "p.md").write_text("---\ntitle: T\n---\n\nTweet text.\n", encoding="utf-8")
            return _cp(argv, 0)
        if TBIN in argv:
            return _cp(argv, 7, "", json.dumps({"error": "no asr", "code": 7, "details": {}}))
        return _cp(argv, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    r = _dispatch("https://x.com/jack/status/123", video=True)
    assert r.ok and r.engine == "html" and "Tweet text." in r.raw_text


def test_dispatch_x_status_video_dep_missing_and_html_failed_raises(monkeypatch):
    # VDD L-1: --video on a login-walled tweet (html fails) + no ASR backend (transcript exit 7)
    # → surface the actionable DEP_MISSING (exit 6), NOT a generic FETCH_FAILED.
    def fake_run(argv, **kw):
        if H2M in argv:
            return _cp(argv, 10, "", json.dumps({"error": "login wall", "type": "FetchFailed",
                                                 "exit_code": 10, "details": {"kind": "login_wall"}}))
        if TBIN in argv:
            return _cp(argv, 7, "", json.dumps({"error": "no asr", "code": 7,
                                                "details": {"remediation": "install ffmpeg"}}))
        return _cp(argv, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(ImportArticleError) as ei:
        _dispatch("https://x.com/jack/status/123", video=True)
    assert ei.value.exit_code == EXIT_DEP_MISSING


def test_derive_slug_caps_long_title():
    # Dogfood regression: a titleless x-status whose whole tweet body becomes the og:title yielded a
    # >255-byte filename → OSError 63. _derive_slug now byte-caps the slug filesystem-safe.
    from scripts.wiki_skills.wiki_import_article import _derive_slug
    slug = _derive_slug("word " * 200, "https://x.com/a/status/1", "preserve-unicode")
    assert 0 < len(slug.encode("utf-8")) <= 180
    assert not slug.startswith("-") and not slug.endswith("-")


def test_video_and_embedded_videos_mutually_exclusive():
    # R-13a: --video and --embedded-videos are mutually exclusive (argparse → exit 2).
    from scripts.wiki_skills.wiki_import_article import _build_parser
    parser = _build_parser()
    with pytest.raises(SystemExit) as ei:
        parser.parse_args(["prepare", "--vault", "v", "--vault-root", "/tmp/x",
                           "--source", "https://x.com/a/status/1", "--folder", "F",
                           "--video", "--embedded-videos"])
    assert ei.value.code == 2


def test_dispatch_x_status_video_no_media_falls_back_to_html(monkeypatch):
    def fake_run(argv, **kw):
        if H2M in argv:
            (Path(argv[3]) / "p.md").write_text("---\ntitle: Tw\n---\n\nJust text.\n", encoding="utf-8")
            return _cp(argv, 0)
        if TBIN in argv:   # no media in this tweet
            return _cp(argv, 3, "", json.dumps({"error": "x", "code": 3, "details": {}}))
        return _cp(argv, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    r = _dispatch("https://x.com/jack/status/123", video=True)
    assert r.ok and r.engine == "html" and "Just text." in r.raw_text


# ---------------------------------------------------------------- R-13 embedded discovery (pure)
def _iframe(src, *, wrap_open="", wrap_close=""):
    return f'{wrap_open}<iframe src="{src}"></iframe>{wrap_close}'


def test_discover_keep_plain_allowlisted():
    html = _iframe("https://www.youtube.com/embed/abc")
    assert _fetch._discover_embedded_videos(html) == [("https://www.youtube.com/embed/abc", "keep")]


def test_discover_not_allowlisted_googlesyndication():
    # ad-network on a non-allowlisted host → dropped at the allowlist step (ADV-1: NOT ad-denylist)
    html = _iframe("https://pagead2.googlesyndication.com/x")
    assert _fetch._discover_embedded_videos(html)[0][1] == "not-allowlisted"


def test_discover_denylist_youtube_ima():
    # ADV-1: an allowlist-PASSING youtube host whose src carries an ad endpoint → ad-denylist
    # (the only path that reaches the belt-and-braces step-3 denylist).
    html = _iframe("https://www.youtube.com/embed/x?u=https://googleads.g.doubleclick.net/pagead")
    assert _fetch._discover_embedded_videos(html)[0][1] == "ad-denylist"


def test_discover_ad_context_adsbygoogle():
    html = _iframe("https://www.youtube.com/embed/x",
                   wrap_open='<ins class="adsbygoogle">', wrap_close="</ins>")
    assert _fetch._discover_embedded_videos(html)[0][1] == "ad-context"


def test_discover_ad_context_aside_related():
    html = _iframe("https://www.youtube.com/embed/x",
                   wrap_open='<aside class="related-videos">', wrap_close="</aside>")
    assert _fetch._discover_embedded_videos(html)[0][1] == "ad-context"


def test_discover_ad_param():
    html = _iframe("https://www.youtube.com/embed/x?ad_type=video_ads")
    assert _fetch._discover_embedded_videos(html)[0][1] == "ad-param"


def test_discover_dedup():
    html = _iframe("https://youtu.be/dup") + _iframe("https://youtu.be/dup")
    reasons = [r for _, r in _fetch._discover_embedded_videos(html)]
    assert reasons == ["keep", "dedup"]


def test_discover_one_real_two_ads():
    html = (_iframe("https://player.vimeo.com/video/123")
            + _iframe("https://www.youtube.com/embed/ad1", wrap_open='<div class="advert">',
                      wrap_close="</div>")
            + _iframe("https://pagead2.googlesyndication.com/ad2"))
    reasons = [r for _, r in _fetch._discover_embedded_videos(html)]
    assert reasons.count("keep") == 1
    assert "ad-context" in reasons and "not-allowlisted" in reasons


# ---------------------------------------------------------------- R-13 dispatch embedded-append
def test_embedded_off_by_default_no_discovery(monkeypatch):
    called = {"download": 0}
    monkeypatch.setattr(_fetch, "_download_raw_html",
                        lambda u: called.__setitem__("download", called["download"] + 1) or "")
    monkeypatch.setattr(subprocess, "run", _run_factory())
    r = _dispatch("https://example.com/article")   # embedded_videos not set
    assert r.ok and called["download"] == 0 and r.embed_log is None


def test_embedded_appends_two_videos(monkeypatch):
    html = (_iframe("https://www.youtube.com/embed/a")
            + _iframe("https://player.vimeo.com/video/b"))
    monkeypatch.setattr(_fetch, "_download_raw_html", lambda u: html)
    monkeypatch.setattr(subprocess, "run", _run_factory(t_txt="EMBED BODY\n"))
    r = _dispatch("https://example.com/article", embedded_videos=True)
    assert r.ok and r.engine == "html+embedded:2"
    assert r.raw_text.count("## Embedded video") == 2
    fetched = [e for e in r.embed_log if e["reason"] == "fetched"]
    assert len(fetched) == 2


def test_embedded_cap(monkeypatch):
    html = "".join(_iframe(f"https://youtu.be/v{i}") for i in range(7))
    monkeypatch.setattr(_fetch, "_download_raw_html", lambda u: html)
    monkeypatch.setattr(subprocess, "run", _run_factory())
    r = _dispatch("https://example.com/article", embedded_videos=True, embedded_videos_max=5)
    assert r.engine == "html+embedded:5"
    assert sum(1 for e in r.embed_log if e["reason"] == "cap") == 2   # 2 dropped, logged not silent


def test_embedded_per_embed_failure_isolated(monkeypatch):
    # one embed transcript fails (exit 7 dep) → skipped, page import still ok (contrast C-1).
    html = _iframe("https://youtu.be/ok") + _iframe("https://youtu.be/bad")

    def fake_run(argv, **kw):
        if H2M in argv:   # the article page fetch
            (Path(argv[3]) / "p.md").write_text("---\ntitle: A\n---\n\nProse.\n", encoding="utf-8")
            return _cp(argv, 0)
        if "https://youtu.be/bad" in argv:
            return _cp(argv, 7, "", json.dumps({"error": "x", "code": 7, "details": {}}))
        out = Path(argv[argv.index("--out") + 1])
        out.write_text("ok body\n", encoding="utf-8")
        Path(str(out) + ".stat.json").write_text(json.dumps(_transcript_stat()), encoding="utf-8")
        return _cp(argv, 0)

    monkeypatch.setattr(_fetch, "_download_raw_html", lambda u: html)
    monkeypatch.setattr(subprocess, "run", fake_run)
    r = _dispatch("https://example.com/article", embedded_videos=True)
    assert r.ok and r.engine == "html+embedded:1"
    reasons = [e["reason"] for e in r.embed_log]
    assert "fetched" in reasons and "transcript-failure:dep" in reasons


# ---------------------------------------------------------------- R-12 / S9 _detect orthogonality
def test_detect_kind_orthogonal_x_status_is_thread():
    # the --kind axis is unchanged: an x.com source is `thread` regardless of body (verify-only).
    kind, _ = detect_kind("Some tweet body.", "https://x.com/jack/status/1", {})
    assert kind == "thread"


def test_detect_kind_orthogonal_transcript_body_is_meeting():
    body = "\n".join(f"[00:0{i}] Speaker {i}: words words words" for i in range(8))
    kind, _ = detect_kind(body, "https://youtu.be/abc", {})
    assert kind == "meeting"   # transcript-shaped body → meeting via _looks_like_transcript


# ---------------------------------------------------------------- TASK 057 W1: robustness knobs
def _argv_capture_run(seen):
    """subprocess.run double: records every transcript argv; html writes a page."""
    def fake_run(argv, **kw):
        if TBIN in argv:
            seen.append({"argv": list(argv), "timeout": kw.get("timeout")})
            out = Path(argv[argv.index("--out") + 1])
            out.write_text("body\n", encoding="utf-8")
            Path(str(out) + ".stat.json").write_text(
                json.dumps(_transcript_stat()), encoding="utf-8")
            return _cp(argv, 0)
        if H2M in argv:
            (Path(argv[3]) / "p.md").write_text(
                "---\ntitle: T\n---\n\nTweet prose.\n", encoding="utf-8")
            return _cp(argv, 0)
        return _cp(argv, 0)
    return fake_run


def _flag_val(argv, flag):
    return argv[argv.index(flag) + 1] if flag in argv else None


def test_w1_flags_reach_argv_unambiguous_video(monkeypatch):
    seen: list = []
    monkeypatch.setattr(subprocess, "run", _argv_capture_run(seen))
    r = _dispatch("https://x.com/i/broadcasts/1abc",
                  concurrent_fragments=8, media_timeout_sec=2400)
    assert r.ok
    assert _flag_val(seen[0]["argv"], "--concurrent-fragments") == "8"
    assert _flag_val(seen[0]["argv"], "--media-timeout-sec") == "2400"


def test_w1_flags_reach_argv_x_status_video(monkeypatch):
    seen: list = []
    monkeypatch.setattr(subprocess, "run", _argv_capture_run(seen))
    r = _dispatch("https://x.com/jack/status/123", video=True,
                  concurrent_fragments=4, media_timeout_sec=900)
    assert r.ok
    assert _flag_val(seen[0]["argv"], "--concurrent-fragments") == "4"
    assert _flag_val(seen[0]["argv"], "--media-timeout-sec") == "900"


def test_w1_flags_reach_argv_embedded_path(monkeypatch):
    seen: list = []
    monkeypatch.setattr(subprocess, "run", _argv_capture_run(seen))
    monkeypatch.setattr(_fetch, "_download_raw_html", lambda url: (
        '<iframe src="https://www.youtube.com/embed/abc123"></iframe>'))
    r = _dispatch("https://example.com/article", embedded_videos=True,
                  concurrent_fragments=6, media_timeout_sec=1200)
    assert r.ok and seen, "embed transcript fetch must have run"
    assert _flag_val(seen[0]["argv"], "--concurrent-fragments") == "6"
    assert _flag_val(seen[0]["argv"], "--media-timeout-sec") == "1200"


def test_w1_flags_omitted_absent_on_all_paths(monkeypatch):
    seen: list = []
    monkeypatch.setattr(subprocess, "run", _argv_capture_run(seen))
    monkeypatch.setattr(_fetch, "_download_raw_html", lambda url: (
        '<iframe src="https://www.youtube.com/embed/abc123"></iframe>'))
    _dispatch("https://x.com/i/broadcasts/1abc")
    _dispatch("https://x.com/jack/status/123", video=True)
    _dispatch("https://example.com/article", embedded_videos=True)
    assert len(seen) == 3
    for rec in seen:
        assert "--concurrent-fragments" not in rec["argv"]
        assert "--media-timeout-sec" not in rec["argv"]


# ---------------------------------------------------------------- TASK 057 W1-3: scoped wall-clock
def test_w1_wallclock_scoped_primary_vs_embed(monkeypatch):
    monkeypatch.delenv("WIKI_TRANSCRIPT_TIMEOUT_S", raising=False)
    seen: list = []
    monkeypatch.setattr(subprocess, "run", _argv_capture_run(seen))
    monkeypatch.setattr(_fetch, "_download_raw_html", lambda url: (
        '<iframe src="https://www.youtube.com/embed/abc123"></iframe>'))
    _dispatch("https://x.com/i/broadcasts/1abc")                      # primary
    _dispatch("https://example.com/article", embedded_videos=True)    # supplementary
    assert seen[0]["timeout"] == 3600   # primary hang-guard covers a ≥60-min broadcast
    assert seen[1]["timeout"] == 300    # embeds keep the old bound (Q-057-2)


def test_w1_wallclock_env_overrides_both_roles(monkeypatch):
    monkeypatch.setenv("WIKI_TRANSCRIPT_TIMEOUT_S", "120")
    assert _fetch._transcript_timeout(primary=True) == 120
    assert _fetch._transcript_timeout(primary=False) == 120


def test_w1_wallclock_env_garbage_falls_back_per_role(monkeypatch):
    monkeypatch.setenv("WIKI_TRANSCRIPT_TIMEOUT_S", "soon")
    assert _fetch._transcript_timeout(primary=True) == 3600
    assert _fetch._transcript_timeout(primary=False) == 300


def test_w1_media_timeout_raises_wallclock(monkeypatch):
    # Phase-4 logic F1: an explicit media budget larger than the wall-clock must RAISE
    # the hang-guard (budget + headroom), never be silently SIGKILLed at 3600.
    monkeypatch.delenv("WIKI_TRANSCRIPT_TIMEOUT_S", raising=False)
    seen: list = []
    monkeypatch.setattr(subprocess, "run", _argv_capture_run(seen))
    _dispatch("https://x.com/i/broadcasts/1abc", media_timeout_sec=5400)
    assert seen[0]["timeout"] == 5400 + 300
    seen.clear()
    _dispatch("https://x.com/i/broadcasts/1abc", media_timeout_sec=900)
    assert seen[0]["timeout"] == 3600      # small budget never LOWERS the hang-guard
