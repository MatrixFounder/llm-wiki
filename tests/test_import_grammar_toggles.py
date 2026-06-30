"""TASK 046 P1 — wiki-import output-grammar (pyramid vs article) + toggles.

R-1 meeting→pyramid · R-2 lesson kind/type · R-3 article unchanged · R-4 --diagrams ·
R-5 --concepts/--no-concepts. Harness mirrors tests/test_import_article_apply.py
(stubbed _index_note/_file_concepts; assertions over the on-disk note + the envelope).
"""
from __future__ import annotations

import json

import pytest

import scripts.wiki_skills.wiki_import_article as wia


@pytest.fixture
def vault(tmp_path):
    (tmp_path / "WIKI_SCHEMA.md").write_text(
        "---\nvault_id: testv\nlayout: obsidian-personal\nlanguage: ru\n---\n", encoding="utf-8")
    (tmp_path / "03 - Learning" / "Webinars").mkdir(parents=True)
    return tmp_path


@pytest.fixture(autouse=True)
def _stub_subprocs(monkeypatch):
    calls = {"index": [], "concepts": []}
    monkeypatch.setattr(wia, "_index_note",
                        lambda v, root, db, p: (calls["index"].append(p) or (0, {"action": "upserted"})))
    monkeypatch.setattr(wia, "_file_concepts",
                        lambda v, root, db, sp, sh, cands: (calls["concepts"].append((sp, sh, cands)) or (0, {"created": len(cands)})))
    return calls


def _pyramid_note(tmp_path, **over):
    """A REASON-authored pyramid: the `body` IS the structured note (TL;DR + sections)."""
    note = {
        "title": "Вебинар по AI-агентам", "tldr": "кратко о вебинаре",
        "summary_bullets": ["тезис один"],
        "body": ("## TL;DR\n\nкраткое содержание вебинара про агентов.\n\n"
                 "## Детальное содержание\n\n### 1. Циклы\n\nагент работает в цикле и это важно.\n"),
        "entities": [
            {"name": "AMM", "definition": "маркет-мейкер",
             "quote": "агент работает в цикле и это важно.", "type": "concept"},
        ],
    }
    note.update(over)
    f = tmp_path / "note.json"
    f.write_text(json.dumps(note, ensure_ascii=False), encoding="utf-8")
    return f


def _run(vault, note_file, *, kind, mode="full", extra=None):
    argv = ["apply", "--vault", "testv", "--vault-root", str(vault),
            "--db-path", str(vault / "index.db"), "--folder", "03 - Learning/Webinars",
            "--mode", mode, "--kind", kind, "--note-file", str(note_file),
            "--raw-rel", "03 - Learning/Webinars/_raw/x.md",
            "--source-url", "https://x.com/i/broadcasts/1", "--today", "2026-06-30"]
    return wia.main(argv + (extra or []))


# --- R-1 + R-2: meeting/lesson → pyramid grammar (parametrized so BOTH pyramid kinds
# share the grammar guard — pins _PYRAMID_KINDS membership for each) ----------

@pytest.mark.parametrize("kind,exp_type", [
    ("meeting", "meeting-summary"),
    ("lesson", "lesson-summary"),
])
def test_import_apply_pyramid_grammar(vault, tmp_path, capsys, kind, exp_type):
    rc = _run(vault, _pyramid_note(tmp_path), kind=kind)
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["grammar"] == "pyramid"
    text = (vault / out["note"]).read_text(encoding="utf-8")
    assert f"type: {exp_type}" in text
    # the REASON-authored pyramid body is present verbatim …
    assert "## Детальное содержание" in text
    assert "агент работает в цикле и это важно." in text
    # … and the ARTICLE wrappers are NOT applied (no "Полный текст" translation section,
    # no bullets-only "Саммари" section that the article grammar emits)
    assert "Полный текст" not in text
    assert "## Саммари" not in text
    # a pyramid is a DIGEST → the source line labels it a summary, never a verbatim translation
    assert "саммари" in text
    assert "перевод" not in text
    # concepts are ON by default → the entity footer IS rendered (pins the footer block;
    # a mutation dropping it must fail here — the symmetric half of the --no-concepts test)
    assert "## Ключевые сущности" in text
    assert "[[amm|AMM]]" in text


def test_import_apply_pyramid_thread_mode_keeps_digest_origin(vault, tmp_path, capsys):
    # --mode and --kind are orthogonal: a pyramid kind with --mode thread must STILL read as a
    # digest ("RU-саммари"), not be mislabeled a Twitter thread ("тред X (мнение автора)").
    rc = _run(vault, _pyramid_note(tmp_path), kind="meeting", mode="thread")
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    text = (vault / out["note"]).read_text(encoding="utf-8")
    assert "саммари" in text
    assert "тред" not in text


# --- R-3: article kind unchanged (article wrapper still emitted) ------------

def test_import_apply_article_unchanged(vault, tmp_path, capsys):
    rc = _run(vault, _pyramid_note(tmp_path), kind="article", mode="full")
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    text = (vault / out["note"]).read_text(encoding="utf-8")
    assert "type: article-summary" in text
    # article/full grammar keeps its section wrappers AND the entity footer the `ents` var
    # controls (so the byte-identity claim is actually guarded, not just the prose sections).
    # The pre-existing tests/test_import_article_apply.py is the broader R-3 byte-identity backstop.
    assert "## Саммари" in text
    assert "Полный текст" in text
    assert "## Ключевые сущности" in text
    assert "[[amm|AMM]]" in text


# --- R-4: --diagrams surfaced in the manifest ------------------------------

def test_import_apply_diagrams_flag(vault, tmp_path, capsys):
    rc = _run(vault, _pyramid_note(tmp_path), kind="meeting", extra=["--diagrams"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["diagrams"] is True


def test_import_apply_diagrams_default_false(vault, tmp_path, capsys):
    rc = _run(vault, _pyramid_note(tmp_path), kind="meeting")
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["diagrams"] is False


# --- R-5: --concepts / --no-concepts toggle --------------------------------

def test_import_apply_concepts_toggle(vault, tmp_path, capsys, _stub_subprocs):
    # default → concepts filed (the AMM entity has a verbatim quote in the body)
    _run(vault, _pyramid_note(tmp_path), kind="meeting")
    capsys.readouterr()
    assert len(_stub_subprocs["concepts"]) == 1

    # --no-concepts → concept filing skipped, manifest marks deferral, no footer dangling
    _stub_subprocs["concepts"].clear()
    rc = _run(vault, _pyramid_note(tmp_path), kind="meeting", extra=["--no-concepts"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert _stub_subprocs["concepts"] == []
    assert out["concepts_deferred"] is True
    text = (vault / out["note"]).read_text(encoding="utf-8")
    assert "## Ключевые сущности" not in text  # no entity footer when concepts deferred


def test_import_apply_article_no_concepts_no_empty_entities(vault, tmp_path, capsys):
    # --no-concepts on an ARTICLE kind must NOT leave a dangling empty "## Ключевые сущности"
    # heading (the entities section is omitted when there are no filable entities).
    rc = _run(vault, _pyramid_note(tmp_path), kind="article", mode="full", extra=["--no-concepts"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    text = (vault / out["note"]).read_text(encoding="utf-8")
    assert "## Ключевые сущности" not in text
    assert "## Саммари" in text  # the rest of the article grammar is intact
