"""S5 — `wiki_import_article.apply` facade (R-4/R-5/R-7)."""
from __future__ import annotations

import json

import pytest

import scripts.wiki_skills.wiki_import_article as wia


@pytest.fixture
def vault(tmp_path):
    (tmp_path / "WIKI_SCHEMA.md").write_text(
        "---\nvault_id: testv\nlayout: obsidian-personal\n---\n", encoding="utf-8")
    (tmp_path / "05 - Материалы" / "Криптовалюты").mkdir(parents=True)
    return tmp_path


@pytest.fixture(autouse=True)
def _stub_subprocs(monkeypatch):
    calls = {"index": [], "concepts": []}
    monkeypatch.setattr(wia, "_index_note",
                        lambda v, root, db, p: (calls["index"].append(p) or (0, {"action": "upserted"})))
    monkeypatch.setattr(wia, "_file_concepts",
                        lambda v, root, db, sp, sh, cands: (calls["concepts"].append((sp, sh, cands)) or (0, {"created": len(cands)})))
    return calls


def _note(tmp_path, **over):
    note = {
        "title_ru": "DeFi гайд", "tldr": "кратко",
        "summary_bullets": ["вывод"], "ru_body": "AMM это маркет-мейкер. полный текст.",
        "entities": [
            {"name": "AMM", "definition": "автоматический маркет-мейкер",
             "quote": "AMM это маркет-мейкер.", "type": "concept"},
            {"name": "DeFi", "definition": "финансы", "quote": "x", "type": "concept"},
            {"name": "DeFi гайд", "definition": "сам гайд", "quote": "y", "type": "concept"},
        ],
    }
    note.update(over)
    f = tmp_path / "note.json"
    f.write_text(json.dumps(note, ensure_ascii=False), encoding="utf-8")
    return f


def _run(vault, note_file, db, extra=None, existing='["defi"]'):
    argv = ["apply", "--vault", "testv", "--vault-root", str(vault),
            "--db-path", str(db), "--folder", "05 - Материалы/Криптовалюты",
            "--mode", "summary", "--note-file", str(note_file),
            "--raw-rel", "05 - Материалы/Криптовалюты/_raw/x.md",
            "--source-url", "https://e.com/x", "--today", "2026-06-18",
            "--existing-page-slugs", existing]
    return wia.main(argv + (extra or []))


def test_apply_meeting_kind_sets_meeting_summary_type(vault, tmp_path, capsys, _stub_subprocs):
    rc = _run(vault, _note(tmp_path), vault / "index.db", extra=["--kind", "meeting"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert "type: meeting-summary" in (vault / out["note"]).read_text()


def test_apply_karpathy_files_note_to_sources(tmp_path, capsys, _stub_subprocs):
    # a karpathy vault → note lands in _sources/, type falls back to `summary`
    # (karpathy.yaml has no `article-summary` mapping)
    (tmp_path / "WIKI_SCHEMA.md").write_text(
        "---\nvault_id: kv\nlayout: karpathy\n---\n", encoding="utf-8")
    (tmp_path / "_sources").mkdir()
    nf = tmp_path / "note.json"
    nf.write_text(json.dumps({
        "title_ru": "Kp Article", "tldr": "t", "summary_bullets": ["b"],
        "ru_body": "AMM body.", "entities": [
            {"name": "AMM", "definition": "d", "quote": "AMM body.", "type": "concept"}]},
        ensure_ascii=False), encoding="utf-8")
    rc = wia.main([
        "apply", "--vault", "kv", "--vault-root", str(tmp_path), "--db-path", str(tmp_path / "i.db"),
        "--folder", "_sources", "--mode", "full", "--kind", "article", "--note-file", str(nf),
        "--raw-rel", "_sources/_raw/x.md", "--source-url", "https://e.com/x", "--today", "2026-06-18"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["note"].startswith("_sources/")          # filed under _sources/ (karpathy)
    assert "type: summary" in (tmp_path / out["note"]).read_text()  # layout-safe fallback


def test_apply_writes_note_and_files_concepts(vault, tmp_path, capsys, _stub_subprocs):
    rc = _run(vault, _note(tmp_path), vault / "index.db")
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["action"] == "imported"
    assert out["note"] == "05 - Материалы/Криптовалюты/DeFi гайд.md"
    note_path = vault / out["note"]
    assert note_path.exists()
    assert "## Ключевые выводы" in note_path.read_text()
    assert len(out["note_hash"]) == 64
    # only AMM survives the collision guard
    assert out["candidates"] == 1
    reasons = {s["reason"] for s in out["skipped"]}
    assert reasons == {"collides-existing-page", "self-collision"}
    # _file_concepts got the FRESH note hash + the note's own rel path as source-page
    sp, sh, cands = _stub_subprocs["concepts"][0]
    assert sp == out["note"] and sh == out["note_hash"]
    assert [c["slug"] for c in cands] == ["amm"]


def test_apply_no_candidates_skips_concept_filing(vault, tmp_path, capsys, _stub_subprocs):
    # every entity collides → no candidates → _file_concepts not called
    nf = _note(tmp_path, entities=[{"name": "DeFi", "definition": "d", "quote": "q", "type": "concept"}])
    rc = _run(vault, nf, vault / "index.db")
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["candidates"] == 0
    assert _stub_subprocs["concepts"] == []


def test_apply_partial_on_index_failure(vault, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(wia, "_index_note", lambda *a: (6, {"error": "UPSERT_FAILED"}))
    monkeypatch.setattr(wia, "_file_concepts", lambda *a: (0, {"created": 1}))
    rc = _run(vault, _note(tmp_path), vault / "index.db")
    out = json.loads(capsys.readouterr().out)
    assert rc == 6 and out["action"] == "partial"


def test_apply_frontmatter_injection_is_neutralized(vault, tmp_path, capsys, _stub_subprocs):
    # hostile orchestrator fields: newline in title_ru/author → must NOT inject a YAML key
    nf = _note(tmp_path, title_ru="Заголовок\ninjected_key: pwned",
               author="Автор\nadmin: true",
               entities=[{"name": "AMM", "definition": "d", "quote": "AMM это маркет-мейкер.", "type": "concept"}])
    rc = _run(vault, nf, vault / "index.db")
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    text = (vault / out["note"]).read_text()
    fm = text.split("---\n", 2)[1]  # the frontmatter block
    # the hostile content is harmlessly inside QUOTED scalars — no STANDALONE injected key line
    keys = {ln.split(":", 1)[0].strip() for ln in fm.splitlines() if ":" in ln and not ln.startswith(" ")}
    assert "injected_key" not in keys and "admin" not in keys
    # and it must parse as valid YAML with the expected top-level keys only
    import yaml
    parsed = yaml.safe_load(fm)
    assert "injected_key" not in parsed and "admin" not in parsed


def test_apply_existing_slugs_scalar_does_not_crash(vault, tmp_path, capsys, _stub_subprocs):
    # a non-array --existing-page-slugs must be treated as empty, not list('defi')
    rc = _run(vault, _note(tmp_path), vault / "index.db", existing='"defi"')
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    # with no real existing-slug guard, DeFi is no longer collides-existing (slug set empty),
    # but the note's own-slug self-collision still fires
    reasons = {s["reason"] for s in out["skipped"]}
    assert "self-collision" in reasons
