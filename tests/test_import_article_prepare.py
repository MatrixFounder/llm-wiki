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
        "---\nvault_id: testv\nlayout: obsidian-personal\nlanguage: ru\n---\n", encoding="utf-8")
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
                     author="A", date="2025-01-01", engine="html")
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
    # reports the count, and cleans the html temp dir.
    att = tmp_path / "tmproot" / "_attachments"
    att.mkdir(parents=True)
    (att / "h.png").write_bytes(b"PNG")
    fr = FetchResult(
        ok=True, engine="html", title="Img",
        raw_text='---\nsource: "u"\n---\n\n# T\n\n![a](_attachments/h.png)\n',
        attachments_dir=att)
    rc = _run(vault, monkeypatch, fr)
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["images"] == 1
    raw = vault / out["raw_path"]
    assert (raw.parent / "_attachments" / "h.png").exists()   # image filed next to _raw
    assert not att.exists()                                    # temp dir cleaned


def test_prepare_refuses_attachments_dir_symlink(vault, monkeypatch, capsys, tmp_path):
    # R-26: a pre-existing `_raw/_attachments` SYMLINK must be refused (write-through escape),
    # mirroring the _raw/<slug>.md symlink guard. The per-file guard alone misses the dir swap.
    raw_dir = vault / "05 - Материалы" / "Криптовалюты" / "_raw"
    raw_dir.mkdir(parents=True)
    outside = tmp_path / "evil"
    outside.mkdir()
    (raw_dir / "_attachments").symlink_to(outside, target_is_directory=True)
    att = tmp_path / "tmproot" / "_attachments"
    att.mkdir(parents=True)
    (att / "h.png").write_bytes(b"PNG")
    fr = FetchResult(ok=True, engine="html", title="Img",
                     raw_text='---\nsource: "u"\n---\n\n![a](_attachments/h.png)\n',
                     attachments_dir=att)
    rc = _run(vault, monkeypatch, fr)
    out = json.loads(capsys.readouterr().out)
    assert rc != 0 and out.get("error") == "REFUSED_SYMLINK"
    assert not any(outside.iterdir())   # nothing written through the symlink
    assert not att.exists()             # html temp dir still reclaimed on the early-return
    # the guard fires BEFORE the raw write → no partial _raw/<slug>.md artifact left behind
    assert not (raw_dir / "img.md").exists()


def test_prepare_gc_runs_on_no_image_reimport(vault, monkeypatch, capsys):
    # a re-import that fetches NO images this run must still GC orphans left by a PRIOR
    # image-bearing import (the GC is no longer gated on result.attachments_dir).
    raw_dir = vault / "05 - Материалы" / "Криптовалюты" / "_raw"
    dest_att = raw_dir / "_attachments"
    dest_att.mkdir(parents=True)
    (dest_att / "orphan.png").write_bytes(b"OLD")     # referenced by no _raw/*.md
    fr = FetchResult(ok=True, raw_text="# Guide\n\nno images\n", title="Img",
                     engine="html", attachments_dir=None)   # no images this run
    rc = _run(vault, monkeypatch, fr)
    assert rc == 0
    assert not (dest_att / "orphan.png").exists()     # reclaimed despite no fetch images


def test_prepare_gc_aborts_on_oversized_raw_keeps_images(vault, monkeypatch, capsys, tmp_path):
    # correctness over reclamation: a _raw/*.md over the read ceiling ABORTS the GC entirely
    # (we never delete an image a too-large note we didn't fully read might reference).
    monkeypatch.setattr(wia, "_GC_MD_MAX_BYTES", 16)
    raw_dir = vault / "05 - Материалы" / "Криптовалюты" / "_raw"
    dest_att = raw_dir / "_attachments"
    dest_att.mkdir(parents=True)
    (dest_att / "orphan.png").write_bytes(b"OLD")
    (raw_dir / "huge.md").write_text("x" * 1000, encoding="utf-8")   # exceeds the 16-byte cap
    att = tmp_path / "tmproot" / "_attachments"
    att.mkdir(parents=True)
    (att / "new.png").write_bytes(b"NEW")
    fr = FetchResult(ok=True, engine="html", title="Img",
                     raw_text='---\nsource: "u"\n---\n\n![a](_attachments/new.png)\n',
                     attachments_dir=att)
    rc = _run(vault, monkeypatch, fr)
    assert rc == 0
    assert (dest_att / "orphan.png").exists()   # GC aborted → orphan conservatively kept
    assert (dest_att / "new.png").exists()       # freshly filed image present


def test_prepare_gc_reclaims_reimport_orphans_keeps_siblings(vault, monkeypatch, capsys, tmp_path):
    # re-import churn: a stale image (no longer referenced) is GC'd, but an image referenced by
    # a SIBLING _raw/*.md is preserved (the GC is folder-wide, not just this note).
    raw_dir = vault / "05 - Материалы" / "Криптовалюты" / "_raw"
    dest_att = raw_dir / "_attachments"
    dest_att.mkdir(parents=True)
    (dest_att / "stale.png").write_bytes(b"OLD")                         # orphan from a prior run
    (dest_att / "keep.png").write_bytes(b"KEEP")                         # referenced by a sibling
    (raw_dir / "sibling.md").write_text("![s](_attachments/keep.png)\n", encoding="utf-8")
    att = tmp_path / "tmproot" / "_attachments"
    att.mkdir(parents=True)
    (att / "new.png").write_bytes(b"NEW")
    fr = FetchResult(ok=True, engine="html", title="Img",
                     raw_text='---\nsource: "u"\n---\n\n![a](_attachments/new.png)\n',
                     attachments_dir=att)
    rc = _run(vault, monkeypatch, fr)
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["images"] == 1
    assert (dest_att / "new.png").exists()      # freshly filed
    assert (dest_att / "keep.png").exists()     # sibling-referenced → preserved
    assert not (dest_att / "stale.png").exists()  # orphan reclaimed


def test_prepare_emits_target_language(vault, monkeypatch, capsys):
    # the orchestrator must summarise into the vault's language (international) — prepare emits it
    fr = FetchResult(ok=True, raw_text="# G\n\nbody\n", title="T", engine="html")
    rc = _run(vault, monkeypatch, fr)
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["language"] == "ru"   # vault WIKI_SCHEMA language: ru


def test_prepare_missing_folder_clean_envelope(vault, monkeypatch, capsys):
    # a non-existent --folder must yield a clean INVALID_FOLDER envelope (Decision-17), NOT an
    # uncaught FileNotFoundError traceback (validate_inside_vault does resolve(strict=True)).
    fr = FetchResult(ok=True, raw_text="x\n", title="t", engine="html")
    monkeypatch.setattr(wia, "dispatch_fetch", lambda *a, **k: fr)
    argv = ["prepare", "--vault", "testv", "--vault-root", str(vault),
            "--db-path", str(vault / "index.db"), "--source", "https://e.com/x",
            "--folder", "05 - Материалы/Несуществующая тема", "--mode", "summary"]
    rc = wia.main(argv)
    out = json.loads(capsys.readouterr().out)
    assert rc != 0 and out.get("error") == "INVALID_FOLDER"
    assert "does not exist" in out["message"]


def test_prepare_missing_vault_root_clean_envelope(tmp_path, capsys):
    # a non-existent --vault-root must yield a clean INVALID_VAULT_ROOT envelope, not an
    # uncaught resolve(strict=True) FileNotFoundError traceback (Decision-17 entry-point guard).
    argv = ["prepare", "--vault", "testv", "--vault-root", str(tmp_path / "nope"),
            "--db-path", str(tmp_path / "i.db"), "--source", "https://e.com/x",
            "--folder", "F", "--mode", "summary"]
    rc = wia.main(argv)
    out = json.loads(capsys.readouterr().out)
    assert rc != 0 and out.get("error") == "INVALID_VAULT_ROOT"


def test_prepare_fetch_failed_writes_no_raw(vault, monkeypatch, capsys):
    fr = FetchResult(ok=False, engine="html",
                     error={"type": "FetchFailed", "details": {"status": 403}})
    rc = _run(vault, monkeypatch, fr)
    out = json.loads(capsys.readouterr().out)
    assert rc == 10 and out["error"] == "FETCH_FAILED"
    assert out["upstream"]["details"]["status"] == 403
    # never-empty-_raw: nothing written
    assert not (vault / "05 - Материалы" / "Криптовалюты" / "_raw").exists()


def test_prepare_explicit_slug_override(vault, monkeypatch, capsys):
    fr = FetchResult(ok=True, raw_text="x\n", title="ignored", engine="html")
    rc = _run(vault, monkeypatch, fr, extra=["--slug", "custom-slug"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["slug"] == "custom-slug"
