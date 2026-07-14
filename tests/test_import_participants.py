"""TASK 052 — wiki-import: meeting participants → `participants:` frontmatter,
never a `_concepts/` person page.

R1 derive_candidates drops `person` — **for EVERY grammar** since TASK 064 / F1 (it was
   pyramid-only, and the article path leaked `уоррен-баффет` / `гарри-марковиц` into the
   operator's live vault; once `wiki-extract-concepts` started REFUSING `person`, that leak
   also turned batch-fatal, since `wiki-import` shells out to it) ·
R2 assemble_note stamps `participants:` for pyramid only (H-6 sanitized) — unchanged ·
R4 the drop is a quiet, non-lossy skip (no CONCEPTS_DROPPED warning) ·
R5 integration: a --kind meeting apply files 0 person concept pages + participants frontmatter.

Harness mirrors tests/test_import_grammar_toggles.py (stubbed _index_note/_file_concepts).
"""
from __future__ import annotations

import json

import pytest

import scripts.wiki_skills.wiki_import_article as wia
import scripts.wiki_skills.wiki_import_article._authoring as A

# A body that mentions every fixture entity verbatim, so each passes the quote gate and the
# ONLY thing that drops the person is the R1 grammar guard (not a missing quote).
_BODY = (
    "Сергей смотрит демо и даёт обратную связь.\n"
    "MasterData ведёт консалтинговую практику.\n"
    "Метамодель описывает предметную область.\n"
    "Айва это инструмент мета-моделирования.\n"
    "ArchiMate это нотация архитектуры.\n"
    "Архитектурный комитет согласует изменения.\n"
)
# TASK 064 / F1: every definition clears the concept rail's WORD floor (≥4). `wiki-import`
# has no concept writer — `_file_concepts` shells out to `wiki-extract-concepts apply` — so
# the rail's floors judge these candidates for real, and the old `"d"` placeholders are now
# legitimate `definition-too-short` drops that emptied the batch before the grammar guard
# these tests exist to pin ever got a say.
_ENTS = [
    {"name": "Сергей", "definition": "архитектор со стороны заказчика.", "quote": "Сергей смотрит демо и даёт обратную связь.", "type": "person"},
    {"name": "MasterData", "definition": "консалтинговая компания по управлению данными.", "quote": "MasterData ведёт консалтинговую практику.", "type": "company"},
    {"name": "Метамодель", "definition": "формальное описание предметной области.", "quote": "Метамодель описывает предметную область.", "type": "concept"},
    {"name": "Айва", "definition": "инструмент мета-моделирования и архитектуры.", "quote": "Айва это инструмент мета-моделирования.", "type": "product"},
    {"name": "ArchiMate", "definition": "нотация описания корпоративной архитектуры.", "quote": "ArchiMate это нотация архитектуры.", "type": "external"},
    {"name": "Архитектурный комитет", "definition": "коллегиальный орган согласования изменений.", "quote": "Архитектурный комитет согласует изменения.", "type": "group"},
]


# --- R1: derive_candidates person filter is grammar-gated -------------------

def test_derive_candidates_pyramid_drops_person_keeps_rest():
    cands, skipped = A.derive_candidates(
        _ENTS, _BODY, slug_strategy="preserve-unicode",
        note_slug="демо", existing_page_slugs=[], grammar="pyramid")
    kept = {c["slug"] for c in cands}
    assert "сергей" not in kept                      # the person is gone …
    assert {"masterdata", "метамодель", "айва", "archimate"} <= kept  # … everything else stays
    # group is deliberately KEPT (a committee can be a real domain concept — Q-052-1)
    assert "архитектурный-комитет" in kept
    # reported (never silently dropped), with the intentional reason
    assert {"name": "Сергей", "reason": "participant-not-concept"} in skipped


def test_derive_candidates_article_ALSO_drops_person():
    """★ TASK 064 / F1 — THE CONTRACT CHANGED, AND THIS TEST USED TO PIN THE BUG.

    It asserted `"сергей" in cands` for the ARTICLE grammar — i.e. it pinned the leak that
    put the live person pages `уоррен-баффет` and `гарри-марковиц` into the operator's
    vault. TASK 052 dropped `person` only under `grammar == "pyramid"`; the operator's
    standing rule has no grammar clause in it (an attendee belongs in `participants:`, a
    cited author in the note body, neither in `_concepts/`).

    It also became FATAL rather than merely wrong: `wiki-extract-concepts` now refuses
    `person` outright (G4 / ENTITY_TYPE_NOT_ALLOWED), and `wiki-import` shells out to it —
    so one `person` entity on the article path killed the WHOLE concept batch at exit 6,
    destroying every legitimate concept beside it. Dropped on EVERY grammar now.
    """
    cands, skipped = A.derive_candidates(
        _ENTS, _BODY, slug_strategy="preserve-unicode",
        note_slug="демо", existing_page_slugs=[], grammar="article")
    assert "сергей" not in {c["slug"] for c in cands}
    assert {"name": "Сергей", "reason": "participant-not-concept"} in skipped
    # …and nothing else is collateral damage: company/product/concept/external/group stay.
    assert {"masterdata", "метамодель", "айва", "archimate",
            "архитектурный-комитет"} <= {c["slug"] for c in cands}


def test_derive_candidates_default_grammar_drops_person():
    # no grammar kwarg → defaults to article → the person is dropped there too (F1).
    cands, skipped = A.derive_candidates(
        _ENTS, _BODY, slug_strategy="preserve-unicode",
        note_slug="демо", existing_page_slugs=[])
    assert "сергей" not in {c["slug"] for c in cands}
    assert {"name": "Сергей", "reason": "participant-not-concept"} in skipped


# --- R2: assemble_note participants frontmatter (pyramid only) --------------

_PART_NOTE = {
    "title": "Демо Айва", "tldr": "кратко", "summary_bullets": ["тезис"],
    "body": "## TL;DR\n\nтело протокола.\n",
    "participants": ["Сергей — MasterData", "Алексей Бондарев — Айва"],
    "entities": [],
}
_COMMON = dict(mode="full", raw_rel_basename="_raw/x.md", source_url="u",
               source_lang="ru", today="2026-07-08", san_names=[], lang="ru")


def test_assemble_note_pyramid_stamps_participants():
    _, text = A.assemble_note(_PART_NOTE, grammar="pyramid", **_COMMON)
    assert "participants:\n" in text
    assert '  - "Сергей — MasterData"' in text
    assert '  - "Алексей Бондарев — Айва"' in text


def test_assemble_note_article_omits_participants():
    _, text = A.assemble_note(_PART_NOTE, grammar="article", **_COMMON)
    assert "participants:" not in text  # participants channel is meeting/lesson-only


def test_assemble_note_pyramid_no_participants_no_block():
    note = dict(_PART_NOTE, participants=[])
    _, text = A.assemble_note(note, grammar="pyramid", **_COMMON)
    assert "participants:" not in text  # byte-identity vs today when there are none


def test_assemble_note_participants_h6_sanitized():
    # a hostile participant string must not inject a top-level YAML key or break the scalar
    note = dict(_PART_NOTE, participants=["Злой\ninjected: evil", "Ок\x00чел"])
    _, text = A.assemble_note(note, grammar="pyramid", **_COMMON)
    # newline/control-stripped → single-line quoted scalars, no injected key
    assert "\ninjected:" not in text
    assert '  - "Злой injected: evil"' in text
    fm = text.split("---\n", 2)[1]  # frontmatter block
    assert "\x00" not in fm


# --- R4/R5: integration — a meeting apply files no person concept page ------

@pytest.fixture
def vault(tmp_path):
    (tmp_path / "WIKI_SCHEMA.md").write_text(
        "---\nvault_id: testv\nlayout: obsidian-personal\nlanguage: ru\n---\n", encoding="utf-8")
    (tmp_path / "06 - Business Development" / "Partnerships").mkdir(parents=True)
    return tmp_path


@pytest.fixture(autouse=True)
def _stub_subprocs(monkeypatch):
    calls = {"index": [], "concepts": []}
    monkeypatch.setattr(wia, "_index_note",
                        lambda v, root, db, p: (calls["index"].append(p) or (0, {"action": "upserted"})))
    monkeypatch.setattr(wia, "_file_concepts",
                        lambda v, root, db, sp, sh, cands: (calls["concepts"].append((sp, sh, cands)) or (0, {"created": len(cands)})))
    return calls


def _mtg_note(tmp_path, **over):
    note = {
        "title": "Демо платформы Айва", "tldr": "кратко о демо",
        "summary_bullets": ["тезис"],
        # "Айва это инструмент." is 3 `\w+` words — under the rail's ≥4-word `source_quote`
        # floor (F8), so it would drop as `no-verbatim-quote` and this fixture would stop
        # testing the person guard it exists for. The body sentence and the entity's quote
        # are widened together so the quote stays a VERBATIM substring of the body.
        "body": ("## TL;DR\n\nСергей смотрит демо и даёт обратную связь.\n"
                 "MasterData ведёт консалтинговую практику. Айва это инструмент мета-моделирования.\n"),
        "participants": ["Сергей — MasterData", "Алексей Бондарев — Айва"],
        "entities": [
            # definitions clear the concept rail's ≥4-word floor (F1) — see `_ENTS` above.
            {"name": "Сергей", "definition": "архитектор со стороны заказчика.", "quote": "Сергей смотрит демо и даёт обратную связь.", "type": "person"},
            {"name": "MasterData", "definition": "консалтинговая компания по управлению данными.", "quote": "MasterData ведёт консалтинговую практику.", "type": "company"},
            {"name": "Айва", "definition": "инструмент мета-моделирования и архитектуры.", "quote": "Айва это инструмент мета-моделирования.", "type": "product"},
        ],
    }
    note.update(over)
    f = tmp_path / "note.json"
    f.write_text(json.dumps(note, ensure_ascii=False), encoding="utf-8")
    return f


def _run(vault, note_file, *, kind, extra=None):
    argv = ["apply", "--vault", "testv", "--vault-root", str(vault),
            "--db-path", str(vault / "index.db"),
            "--folder", "06 - Business Development/Partnerships",
            "--mode", "full", "--kind", kind, "--note-file", str(note_file),
            "--raw-rel", "06 - Business Development/Partnerships/_raw/x.md",
            "--source-url", "", "--today", "2026-07-08"]
    return wia.main(argv + (extra or []))


def test_apply_meeting_person_not_filed_participants_stamped(vault, tmp_path, capsys, _stub_subprocs):
    rc = _run(vault, _mtg_note(tmp_path), kind="meeting")
    out = json.loads(capsys.readouterr().out)
    assert rc == 0, out
    # concept filing ran once; the candidate set has NO person, but keeps company/product
    assert len(_stub_subprocs["concepts"]) == 1
    cand_slugs = {c["slug"] for c in _stub_subprocs["concepts"][0][2]}
    assert "сергей" not in cand_slugs
    assert {"masterdata", "айва"} <= cand_slugs
    # the person is reported as an intentional, NON-lossy skip (no CONCEPTS_DROPPED warning)
    assert {"name": "Сергей", "reason": "participant-not-concept"} in out["skipped"]
    assert all(w.get("reason") != "participant-not-concept" for w in out["warnings"])
    # the note records people as participants, and never as a dangling footer wikilink
    text = (vault / out["note"]).read_text(encoding="utf-8")
    assert "participants:\n" in text
    assert '  - "Сергей — MasterData"' in text
    assert "[[сергей" not in text


def test_apply_article_ALSO_drops_person_still_no_participants(vault, tmp_path, capsys, _stub_subprocs):
    """★ TASK 064 / F1 — the article path drops the person too.

    This asserted `"сергей" in cand_slugs` — it PINNED the leak that put the live person
    pages `уоррен-баффет` / `гарри-марковиц` into the operator's vault.

    The `participants:` frontmatter block stays PYRAMID-ONLY (TASK 052 / R2 — that half is
    unchanged), so on an article the person lands in NEITHER `_concepts/` nor
    `participants:`: it is dropped and reported. That is right for a cited author — they
    belong in the note body's prose, which the REASON step authors.
    """
    rc = _run(vault, _mtg_note(tmp_path), kind="article")
    out = json.loads(capsys.readouterr().out)
    assert rc == 0, out
    cand_slugs = {c["slug"] for c in _stub_subprocs["concepts"][0][2]}
    assert "сергей" not in cand_slugs                   # F1: a person is not a concept, EVER
    assert {"masterdata", "айва"} <= cand_slugs         # the real concepts still file
    assert {"name": "Сергей", "reason": "participant-not-concept"} in out["skipped"]
    # intentional drop → never a lossy CONCEPTS_DROPPED warning
    assert all(w.get("reason") != "participant-not-concept" for w in out["warnings"])
    text = (vault / out["note"]).read_text(encoding="utf-8")
    assert "participants:" not in text                  # article grammar → no participants block
    assert "[[сергей" not in text                       # …and no dangling footer wikilink


# --- R4: malformed `participants` is rejected / tolerated, never iterated per-CHAR ----

def test_apply_rejects_non_list_participants(vault, tmp_path, capsys):
    # a bare string (not a list) must fail with the Decision-17 JSON envelope, not a raw
    # traceback and not a per-char `participants: [С, е, р, …]` block.
    rc = _run(vault, _mtg_note(tmp_path, participants="Сергей"), kind="meeting")
    out = json.loads(capsys.readouterr().out)
    assert rc != 0
    assert out["error"] == "BAD_NOTE_JSON"


def test_assemble_note_non_list_participants_no_block():
    # the pure function is also defensive (called directly by other callers/tests): a non-list
    # participants yields NO block (isinstance guard), never a per-char iteration.
    note = dict(_PART_NOTE, participants="Сергей")
    _, text = A.assemble_note(note, grammar="pyramid", **_COMMON)
    assert "participants:" not in text


def test_assemble_note_participants_unicode_linebreak_sanitized():
    # H-6 hardening: Unicode line breaks (NEL U+0085 / LS U+2028 / PS U+2029) — which YAML 1.1
    # treats as breaks — must be stripped so a name can't smuggle a mid-scalar `---` document
    # separator and break the frontmatter parse (availability).
    import frontmatter
    note = dict(_PART_NOTE, participants=["Alice\u2028--- x", "Bob\u2029... y", "C\x85d"])
    _, text = A.assemble_note(note, grammar="pyramid", **_COMMON)
    for cp in ("\x85", "\u2028", "\u2029"):
        assert cp not in text
    post = frontmatter.loads(text)               # must not raise — frontmatter stays parseable
    assert isinstance(post.get("participants"), list)


def test_assemble_note_participants_deduped():
    # a REASON step that lists the same attendee twice must not emit a duplicate frontmatter line
    note = dict(_PART_NOTE, participants=["\u0421\u0435\u0440\u0433\u0435\u0439 \u2014 MasterData",
                                          "\u0421\u0435\u0440\u0433\u0435\u0439 \u2014 MasterData"])
    _, text = A.assemble_note(note, grammar="pyramid", **_COMMON)
    assert text.count('  - "\u0421\u0435\u0440\u0433\u0435\u0439 \u2014 MasterData"') == 1
