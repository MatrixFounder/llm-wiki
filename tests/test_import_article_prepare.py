"""S3 — `wiki_import_article.prepare` facade (R-1/R-2/R-3)."""
from __future__ import annotations

import json

import pytest

import scripts.wiki_skills.wiki_import_article as wia
from scripts.wiki_skills.wiki_import_article import _context
from scripts.wiki_skills.wiki_import_article._fetch import FetchResult


@pytest.fixture
def vault(tmp_path):
    (tmp_path / "WIKI_SCHEMA.md").write_text(
        "---\nvault_id: testv\nlayout: obsidian-personal\n---\n", encoding="utf-8")
    (tmp_path / "05 - Материалы" / "Криптовалюты").mkdir(parents=True)
    return tmp_path


@pytest.fixture(autouse=True)
def _stub_context(monkeypatch):
    monkeypatch.setattr(_context, "known_concepts",
                        lambda repo, v, root: [{"slug": "amm", "name": "AMM"}])
    monkeypatch.setattr(_context, "existing_page_slugs",
                        lambda *a, **k: ["defi", "uniswap"])


def _run(vault, monkeypatch, fetch_result, extra=None):
    monkeypatch.setattr(wia, "dispatch_fetch", lambda *a, **k: fetch_result)
    db = vault / "index.db"
    argv = ["prepare", "--vault", "testv", "--vault-root", str(vault),
            "--db-path", str(db), "--source", "https://example.com/defi-guide",
            "--folder", "05 - Материалы/Криптовалюты", "--mode", "summary"]
    return wia.main(argv + (extra or []))


def test_prepare_ok_emits_envelope_and_writes_raw(vault, monkeypatch, capsys):
    fr = FetchResult(ok=True, raw_text="# Guide\n\nbody\n", title="DeFi Guide",
                     author="A", date="2025-01-01", engine="html2md")
    rc = _run(vault, monkeypatch, fr)
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["action"] == "prepared"
    assert out["slug"] == "defi-guide" and out["mode"] == "summary"
    assert out["project"] == "Материалы/Криптовалюты"
    assert out["known_concepts"] == [{"slug": "amm", "name": "AMM"}]
    assert out["existing_page_slugs"] == ["defi", "uniswap"]
    # R-2: content-type detection fields present in the envelope (auto-detected → article)
    assert out["kind"] == "article" and out["reason_harness"] == "summarizing-meetings"
    assert out["kind_confidence"] == "low"
    assert len(out["source_hash"]) == 64
    raw = vault / out["raw_path"]
    raw_text = raw.read_text()
    assert raw.exists() and raw.parent.name == "_raw"
    # invariant: _raw always carries a link to the original (injected when the fetch body
    # lacks a `source:`) plus the fetched body verbatim
    assert 'source: "https://example.com/defi-guide"' in raw_text
    assert raw_text.endswith("# Guide\n\nbody\n")


def test_prepare_files_downloaded_images(vault, monkeypatch, capsys, tmp_path):
    # image-import ON: prepare copies the fetched _attachments into _raw/_attachments,
    # reports the count, and cleans the html2md temp dir.
    att = tmp_path / "tmproot" / "_attachments"
    att.mkdir(parents=True)
    (att / "h.png").write_bytes(b"PNG")
    fr = FetchResult(
        ok=True, engine="html2md", title="Img",
        raw_text='---\nsource: "u"\n---\n\n# T\n\n![a](_attachments/h.png)\n',
        attachments_dir=att)
    rc = _run(vault, monkeypatch, fr)
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["images"] == 1
    raw = vault / out["raw_path"]
    assert (raw.parent / "_attachments" / "h.png").exists()   # image filed next to _raw
    assert not att.exists()                                    # temp dir cleaned


def test_prepare_fetch_failed_writes_no_raw(vault, monkeypatch, capsys):
    fr = FetchResult(ok=False, engine="html2md",
                     error={"type": "FetchFailed", "details": {"status": 403}})
    rc = _run(vault, monkeypatch, fr)
    out = json.loads(capsys.readouterr().out)
    assert rc == 10 and out["error"] == "FETCH_FAILED"
    assert out["upstream"]["details"]["status"] == 403
    # never-empty-_raw: nothing written
    assert not (vault / "05 - Материалы" / "Криптовалюты" / "_raw").exists()


def test_prepare_explicit_slug_override(vault, monkeypatch, capsys):
    fr = FetchResult(ok=True, raw_text="x\n", title="ignored", engine="html2md")
    rc = _run(vault, monkeypatch, fr, extra=["--slug", "custom-slug"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["slug"] == "custom-slug"
