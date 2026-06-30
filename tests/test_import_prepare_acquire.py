"""TASK 046 P1b — wiki-import prepare: universal acquire+normalize for office + captions.

R-6 office (docx/pptx/xlsx) → _raw text via the hardened soffice wrapper · R-7 .vtt/.srt
de-timestamp → _raw text (SRT normalised to WebVTT first). Tests exercise dispatch_fetch's
local-file routing directly (the prepare facade mocks dispatch_fetch wholesale). The external
converters (the office skills' _soffice wrapper / the transcript-fetcher cleaner) are mocked
at their import boundary so the suite stays hermetic.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.wiki_skills.wiki_import_article import _fetch
from scripts.wiki_skills.wiki_import_article._errors import (
    EXIT_DEP_MISSING,
    ImportArticleError,
)


def _dispatch(source: str, **over):
    kw = dict(html_bin="/nonexistent-html", pdf_extract_bin="/nonexistent-pdf")
    kw.update(over)
    return _fetch.dispatch_fetch(source, **kw)


class _FakeSoffice:
    """Stand-in for the pptx skill's _soffice module (convert_to + find_soffice)."""
    def __init__(self, *, soffice_ok=True, convert_ok=True):
        self._soffice_ok = soffice_ok
        self._convert_ok = convert_ok

    def find_soffice(self):
        if not self._soffice_ok:
            raise RuntimeError("soffice (LibreOffice) not found")
        return "/fake/soffice"

    def convert_to(self, src, out_dir, target_format, *, timeout=180):
        if not self._convert_ok:
            raise RuntimeError("soffice failed (exit 1)")
        out = Path(out_dir) / f"{Path(src).stem}.txt"
        # soffice writes UTF-8-WITH-BOM → write a BOM to pin the strip in _office_to_text
        out.write_text("Конспект лекции про агентные циклы.\n", encoding="utf-8-sig")
        return out


# --- R-6: office → text via the hardened soffice wrapper --------------------

def test_import_prepare_office(tmp_path, monkeypatch):
    doc = tmp_path / "lecture.docx"
    doc.write_bytes(b"PK\x03\x04 fake docx")  # content irrelevant — the wrapper is mocked
    monkeypatch.setattr(_fetch, "_load_soffice", lambda *a, **k: _FakeSoffice())
    res = _dispatch(str(doc))
    assert res.ok is True
    assert res.engine == "convert-office"
    assert "агентные циклы" in (res.raw_text or "")
    assert not (res.raw_text or "").startswith("﻿")  # BOM stripped


def test_import_prepare_office_missing_wrapper(tmp_path):
    doc = tmp_path / "x.pptx"
    doc.write_bytes(b"PK fake")
    with pytest.raises(ImportArticleError) as ei:
        _dispatch(str(doc), soffice_wrapper="/nonexistent/_soffice.py")
    assert ei.value.exit_code == EXIT_DEP_MISSING


def test_import_prepare_office_soffice_absent(tmp_path, monkeypatch):
    doc = tmp_path / "x.xlsx"
    doc.write_bytes(b"PK fake")
    monkeypatch.setattr(_fetch, "_load_soffice", lambda *a, **k: _FakeSoffice(soffice_ok=False))
    with pytest.raises(ImportArticleError) as ei:
        _dispatch(str(doc))
    assert ei.value.exit_code == EXIT_DEP_MISSING


def test_import_prepare_office_convert_fails_is_soft(tmp_path, monkeypatch):
    # a conversion that runs but fails is a TYPED FetchResult error (caller → FETCH_FAILED),
    # not a hard dependency error and not a junk _raw.
    doc = tmp_path / "broken.docx"
    doc.write_bytes(b"PK garbage")
    monkeypatch.setattr(_fetch, "_load_soffice", lambda *a, **k: _FakeSoffice(convert_ok=False))
    res = _dispatch(str(doc))
    assert res.ok is False
    assert res.engine == "convert-office"
    assert (res.error or {}).get("error") == "OfficeConvertFailed"


# --- R-7: vtt/srt de-timestamp ---------------------------------------------

def test_import_prepare_vtt(tmp_path, monkeypatch):
    vtt = tmp_path / "talk.vtt"
    vtt.write_text(
        "WEBVTT\n\n00:00:09.390 --> 00:00:11.350\nHello and welcome.\n\n"
        "00:00:11.350 --> 00:00:14.000\nToday we discuss agent loops.\n",
        encoding="utf-8")

    seen = {}
    def fake_cleaner(raw: str) -> str:
        seen["raw"] = raw
        return "Hello and welcome. Today we discuss agent loops."

    monkeypatch.setattr(_fetch, "_load_vtt_cleaner", lambda *a, **k: fake_cleaner)
    res = _dispatch(str(vtt))
    assert res.ok is True
    assert res.engine == "vtt"
    assert res.raw_text == "Hello and welcome. Today we discuss agent loops."
    assert "00:00:09.390 -->" in seen["raw"]  # raw vtt handed to the cleaner verbatim


def test_import_prepare_vtt_missing_cleaner_dep(tmp_path, monkeypatch):
    vtt = tmp_path / "x.srt"
    vtt.write_text("1\n00:00:01,000 --> 00:00:02,000\nhi\n", encoding="utf-8")

    def boom(*a, **k):
        raise ImportArticleError("DEPENDENCY_MISSING", "vtt cleaner absent",
                                 exit_code=EXIT_DEP_MISSING, details={})
    monkeypatch.setattr(_fetch, "_load_vtt_cleaner", boom)
    with pytest.raises(ImportArticleError) as ei:
        _dispatch(str(vtt))
    assert ei.value.exit_code == EXIT_DEP_MISSING


def test_srt_normalization_unit():
    # comma→dot in cue timestamps; standalone sequence-index lines dropped (only before a cue)
    srt = ("1\n00:00:01,000 --> 00:00:02,000\nhello\n\n"
           "2\n00:00:02,000 --> 00:00:03,000\n42 apples\n")
    out = _fetch._srt_to_vtt(srt)
    assert out.startswith("WEBVTT")
    assert "00:00:01.000 --> 00:00:02.000" in out   # dot, normalised
    assert "00:00:01,000" not in out                # comma gone
    assert "\n1\n" not in ("\n" + out + "\n")       # index 1 dropped
    assert "42 apples" in out                        # a numeric-prefixed CAPTION is preserved


def test_import_prepare_srt_normalized_before_cleaner(tmp_path, monkeypatch):
    # .srt must be normalised to WebVTT BEFORE the (VTT-specific) cleaner sees it.
    srt = tmp_path / "talk.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello world.\n", encoding="utf-8")
    seen = {}
    monkeypatch.setattr(_fetch, "_load_vtt_cleaner",
                        lambda *a, **k: (lambda raw: (seen.__setitem__("raw", raw) or "Hello world.")))
    res = _dispatch(str(srt))
    assert res.ok is True and res.engine == "vtt"
    assert "00:00:01.000 -->" in seen["raw"]   # dot (normalised), not the SRT comma
    assert "00:00:01,000" not in seen["raw"]
