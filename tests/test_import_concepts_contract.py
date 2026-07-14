"""★★ TASK 064 / F1 — THE PRODUCER/CONSUMER CONTRACT BETWEEN `wiki-import` AND
`wiki-extract-concepts`, DRIVEN FOR REAL.

**`wiki-import` HAS NO CONCEPT WRITER OF ITS OWN.** `_file_concepts` SHELLS OUT to
`wiki-extract-concepts apply` (a real `subprocess`). So every gate on that rail runs on
candidates built by `wiki_import_article._authoring.derive_candidates` — and when the two
disagree, the import does not degrade, it is DESTROYED: one offending entity ⇒ exit 4 from
the rail ⇒ exit 6 + `action: partial` from `wiki-import` ⇒ **zero** concept pages, including
every legitimate one in the same batch, and a filed note whose footer wikilinks now dangle.

★ WHY THIS FILE EXISTS AT ALL — THE CAUTIONARY TALE.

TASK 064's first cut shipped exactly that breakage, **and the suite was GREEN over all of
it.** `tests/test_import_article_apply.py`, `test_import_grammar_toggles.py` and
`test_import_participants.py` each install an AUTOUSE fixture that monkeypatches
`_file_concepts` with a stub hardcoding `(0, {"created": len(cands)})`. The real subprocess
never ran. **The stub reported SUCCESS for precisely the payloads the gates reject.** A
green suite is worth nothing if the thing under test is stubbed out at the seam where the
bug lives.

So: **THIS MODULE INSTALLS NO STUBS.** It runs the real `wiki-import apply`, which runs the
real `wiki-index-upsert` and the real `wiki-extract-concepts apply --ingest` as child
processes, against a real registered vault and a real SQLite DB. It is slower than the
stubbed tests on purpose. It goes RED if the producer and the consumer ever diverge again —
which is the only property that actually protects the operator's on-ramp (and `wiki-sync`'s,
which delegates to `wiki-import` and inherits everything it does).

THE CONTRACT IT PINS, in one line: **a candidate the rail refuses is DROPPED and REPORTED in
`skipped[]` — never fatal to the batch.** A partial concept filing is correct; a zero-concept
import is not.

Covered offender classes (F1's list, one entity each), all in ONE import so the test also
proves they do not take the legitimate concepts down with them:
  * a `person` entity            → `participant-not-concept`  (G4 / ENTITY_TYPE_NOT_ALLOWED)
  * a TERSE definition           → `definition-too-short`     (G1 / FIELD_TOO_SHORT)
  * an ABSENT definition         → `definition-too-short`     (the note-JSON contract makes
                                                               `definition` optional)
  * a SHORT source_quote         → `no-verbatim-quote`        (G2 / FIELD_TOO_SHORT)
  * ★ a MULTI-LINE quote         → **FILED, NOT DROPPED**     (G9 / SOURCE_SPAN_QUOTE_MISMATCH)

That last one is the load-bearing one and it is an INVERTED assertion: the old
`span_for_quote` derived `L{n}-L{n}` from the quote's FIRST line only, so a multi-line quote
could NEVER satisfy the rail's new span check — structurally, on every input. It must now be
filed with a span that actually CONTAINS it.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pytest

import scripts.wiki_skills.wiki_import_article as wia
from scripts.wiki_index.models import Vault
from scripts.wiki_index.repository import IndexRepository

FOLDER = "05 - Материалы/Крипта"

# The note body. Two things are load-bearing:
#   * every entity's quote is a VERBATIM substring of it (else the drop we observe would be
#     `no-verbatim-quote` for the wrong reason — a false green for the gate under test);
#   * `_MULTILINE_QUOTE` spans a `\n`, which is the whole point of the F1 span fix.
_BODY = (
    "Бессрочный фьючерс не имеет даты экспирации, поэтому нет и естественного\n"
    "схождения цены контракта к споту.\n"
    "\n"
    "Ставка финансирования — это периодический платёж между держателями длинных и\n"
    "коротких позиций, который удерживает цену контракта у спота.\n"
    "\n"
    "Виталик Бутерин на конференции разбирал устройство деривативов подробно.\n"
    "Ликвидация происходит при недостатке маржи на счёте трейдера.\n"
    "Индексная цена считается как среднее по нескольким спотовым площадкам.\n"
    "Оракул поставляет внешние данные в смарт-контракт по расписанию.\n"
)

# ★ THE MULTI-LINE QUOTE — two body lines joined by the `\n` that is actually in the body.
# `str.split("\n")` (producer AND consumer, F5) must agree that this occupies TWO lines.
_MULTILINE_QUOTE = ("Ставка финансирования — это периодический платёж между держателями длинных и\n"
                    "коротких позиций, который удерживает цену контракта у спота.")

_SINGLE_LINE_QUOTE = "Ликвидация происходит при недостатке маржи на счёте трейдера."


def _entities() -> list[dict[str, Any]]:
    """One entity per offender class + two that MUST survive. Each offender violates exactly
    ONE rule, so a drop can only be attributed to the gate it is named for."""
    return [
        # ---- MUST BE FILED -------------------------------------------------------------
        # ★ the multi-line quote: the F1 span fix, inverted-asserted.
        {"name": "Ставка финансирования", "type": "concept",
         "definition": "периодический платёж между лонгами и шортами.",
         "quote": _MULTILINE_QUOTE},
        # a plain, well-formed candidate — the control. If the batch dies, this dies with it,
        # which is exactly the collateral damage F1 is about.
        {"name": "Ликвидация", "type": "concept",
         "definition": "принудительное закрытие позиции при нехватке маржи.",
         "quote": _SINGLE_LINE_QUOTE},

        # ---- MUST BE DROPPED INTO skipped[], WITHOUT KILLING THE BATCH -----------------
        # (1) a person — the operator's standing rule, and the live `уоррен-баффет` leak.
        {"name": "Виталик Бутерин", "type": "person",
         "definition": "сооснователь Ethereum и известный исследователь.",
         "quote": "Виталик Бутерин на конференции разбирал устройство деривативов подробно."},
        # (2) a TERSE definition (1 word) — everything else about it is valid.
        {"name": "Индексная цена", "type": "concept",
         "definition": "Метрика.",
         "quote": "Индексная цена считается как среднее по нескольким спотовым площадкам."},
        # (3) an ABSENT definition — legal in the note-JSON contract (`e.get("definition","")`),
        #     which is precisely why the rail's floor must not be fatal here.
        {"name": "Оракул", "type": "concept",
         "quote": "Оракул поставляет внешние данные в смарт-контракт по расписанию."},
        # (4) a SHORT quote (1 word, but genuinely present in the body → the ONLY thing wrong
        #     with it is that it is a token, not a phrase).
        {"name": "Спот", "type": "concept",
         "definition": "рынок с немедленной поставкой актива.",
         "quote": "споту"},
    ]


@pytest.fixture
def live_vault(tmp_path: Path, repo_factory: Callable[[], IndexRepository]) -> tuple[Path, str]:
    """A REGISTERED vault + a real DB on disk. No stubs anywhere.

    `wiki-import apply` spawns `wiki-index-upsert` and `wiki-extract-concepts apply` as
    child processes against this DB, so the vault must genuinely exist in `vaults`.
    """
    vault_root = tmp_path / "vault"
    (vault_root / FOLDER).mkdir(parents=True)
    (vault_root / "WIKI_SCHEMA.md").write_text(
        "---\nvault_id: testv\nlayout: obsidian-personal\nlanguage: ru\n---\n",
        encoding="utf-8")

    db_path = str(tmp_path / "wiki.db")
    bootstrap = repo_factory()
    bootstrap.apply_schema()  # type: ignore[attr-defined]
    bootstrap.register_vault(Vault(
        vault_id="testv", name="import-contract vault", root_path=vault_root,
        schema_version="2.0", registered_at=datetime(2026, 7, 14),
    ))
    bootstrap.close()
    # Promote the bootstrapped DB into the explicit --db-path the CLIs will be given.
    src_db = sorted(tmp_path.glob("wiki-*.db"))[0]
    Path(db_path).write_bytes(src_db.read_bytes())
    return vault_root, db_path


def _write_note(tmp_path: Path, **over: Any) -> Path:
    note: dict[str, Any] = {
        "title": "Перпы и фандинг",
        "tldr": "как устроены бессрочные фьючерсы.",
        "summary_bullets": ["ставка финансирования держит цену у спота"],
        "body": _BODY,
        "entities": _entities(),
    }
    note.update(over)
    f = tmp_path / "note.json"
    f.write_text(json.dumps(note, ensure_ascii=False), encoding="utf-8")
    return f


def _run_import(vault_root: Path, db_path: str, note_file: Path,
                kind: str = "article", mode: str = "full") -> int:
    """The REAL `wiki-import apply` — it will spawn the real `wiki-index-upsert` and the real
    `wiki-extract-concepts apply --ingest`. Nothing is monkeypatched."""
    return wia.main([
        "apply", "--vault", "testv", "--vault-root", str(vault_root),
        "--db-path", db_path, "--folder", FOLDER,
        "--mode", mode, "--kind", kind, "--note-file", str(note_file),
        "--raw-rel", f"{FOLDER}/_raw/x.md",
        "--source-url", "https://example.com/perps", "--today", "2026-07-14",
    ])


def _concept_files(vault_root: Path) -> set[str]:
    d = vault_root / FOLDER / "_concepts"
    return {p.stem for p in d.glob("*.md")} if d.is_dir() else set()


# ============================================================================
# ★ THE PROPERTY: offenders are SKIPPED, the legitimate concepts are still FILED.
# ============================================================================

@pytest.mark.parametrize("kind", ["article", "meeting"])
def test_rail_refusals_become_skips_never_a_zero_concept_import(
    live_vault: tuple[Path, str], tmp_path: Path, capsys: pytest.CaptureFixture[str],
    kind: str,
) -> None:
    """★ THE REGRESSION F1 NAMES, on BOTH grammars.

    At TASK 064's first cut this exact input produced **exit 6, `action: partial`, ZERO
    concept pages** (the `_concepts/` dir was not even created), with `skipped[] == []` and
    `warnings[] == []` — the legitimate concepts destroyed along with the offenders, and the
    filed note left carrying dangling footer wikilinks.

    Parametrised over `article` AND `meeting` because the pyramid path was ALREADY correct
    and the article path was not: the fix is "extend the pyramid's behaviour to every
    grammar", so both must now agree. (`meeting` also drives the `participants:` channel,
    which is pyramid-only and must stay that way.)
    """
    vault_root, db_path = live_vault
    rc = _run_import(vault_root, db_path, _write_note(tmp_path), kind=kind)
    out = json.loads(capsys.readouterr().out)

    # 1. THE IMPORT SUCCEEDS. One bad entity does not kill the run.
    assert rc == 0, out
    assert out["action"] == "imported", out

    # 2. THE LEGITIMATE CONCEPTS ARE ON DISK — written by the REAL subprocess, not a stub.
    filed = _concept_files(vault_root)
    assert {"ставка-финансирования", "ликвидация"} <= filed, (
        f"legitimate concepts were destroyed alongside the offenders; filed={filed}, "
        f"envelope={out}")

    # 3. …AND THE OFFENDERS ARE NOT.
    assert not ({"виталик-бутерин", "индексная-цена", "оракул", "спот"} & filed), filed

    # 4. EVERY OFFENDER IS REPORTED, with the reason that names its own gate.
    reasons = {s["name"]: s["reason"] for s in out["skipped"]}
    assert reasons.get("Виталик Бутерин") == "participant-not-concept"
    assert reasons.get("Индексная цена") == "definition-too-short"
    assert reasons.get("Оракул") == "definition-too-short"
    assert reasons.get("Спот") == "no-verbatim-quote"

    # 5. The concept-filing subprocess itself reported success for the survivors.
    assert out["concepts"].get("created") == 2 or out["candidates"] == 2, out


def test_multiline_quote_is_filed_with_a_span_that_contains_it(
    live_vault: tuple[Path, str], tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """★★ THE MULTI-LINE SPAN — the defect that was STRUCTURAL, not incidental.

    `span_for_quote` used to take the quote's FIRST line, find the body line containing it,
    and emit `L{n}-L{n}` — a ONE-LINE span. `wiki-extract-concepts` now VERIFIES that the
    span contains the quote (G9), so a quote spanning two lines could never satisfy it on ANY
    input: guaranteed `SOURCE_SPAN_QUOTE_MISMATCH` ⇒ exit 6 ⇒ zero pages.

    This asserts the repaired behaviour at the strongest point available: the span the rail
    ACCEPTED and PERSISTED into `page_entity_refs` — i.e. the provenance receipt — really
    does span two lines and really does bracket the quote in the bytes on disk.
    """
    vault_root, db_path = live_vault
    rc = _run_import(vault_root, db_path, _write_note(tmp_path))
    out = json.loads(capsys.readouterr().out)
    assert rc == 0, out

    note_text = (vault_root / out["note"]).read_text(encoding="utf-8")
    assert _MULTILINE_QUOTE in note_text, "the quote must be verbatim in the FILED note"

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT line_start, line_end, source_quote FROM page_entity_refs "
            "WHERE vault_id = ? AND entity_slug = ?",
            ("testv", "ставка-финансирования"),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, "the multi-line concept never reached page_entity_refs"
    start, end = int(row[0]), int(row[1])
    # the receipt itself is stored on the ref (TASK 047 moved it off the page body)
    assert row[2] == _MULTILINE_QUOTE

    # A REAL two-line span (the old derivation could only ever emit start == end here).
    assert end == start + 1, f"expected a 2-line span, got L{start}-L{end}"
    # …and the span genuinely brackets the quote in the filed bytes. `split("\n")`, never
    # `splitlines()` (F5) — the consumer counts `\n` and so must this assertion.
    lines = note_text.split("\n")
    assert 1 <= start <= end <= len(lines)
    assert _MULTILINE_QUOTE in "\n".join(lines[start - 1:end])


def test_a_person_only_note_files_no_concepts_and_still_exits_zero(
    live_vault: tuple[Path, str], tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """The degenerate edge of the same law: when the ONLY entity is an offender, the correct
    outcome is an import that files the note, files ZERO concepts, and **still exits 0**
    (G0 — an empty extraction is a SUCCESS, not a failure). The first cut exited 6 here.
    """
    vault_root, db_path = live_vault
    nf = _write_note(tmp_path, entities=[{
        "name": "Виталик Бутерин", "type": "person",
        "definition": "сооснователь Ethereum и известный исследователь.",
        "quote": "Виталик Бутерин на конференции разбирал устройство деривативов подробно.",
    }])
    rc = _run_import(vault_root, db_path, nf)
    out = json.loads(capsys.readouterr().out)

    assert rc == 0, out
    assert out["candidates"] == 0
    assert {"name": "Виталик Бутерин", "reason": "participant-not-concept"} in out["skipped"]
    assert _concept_files(vault_root) == set()
    # the note is filed, and carries NO dangling footer wikilink to the page that never existed
    note_text = (vault_root / out["note"]).read_text(encoding="utf-8")
    assert "[[виталик-бутерин" not in note_text


def test_the_stub_free_seam_is_real(
    live_vault: tuple[Path, str], tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """★ THE META-ASSERTION — the one that makes the rest of this file trustworthy.

    The whole reason F1 shipped is that three test modules stub `_file_concepts`, so the
    subprocess under test never ran and the stub returned success for payloads the real rail
    rejects. If someone ever adds such an autouse stub to THIS module (or to `conftest.py`),
    every assertion above would keep passing while testing nothing at all.

    So: prove the seam is live. `_file_concepts` must be the real function, and the concept
    page it writes must exist with the content the REAL `write_concept_page` produces (a stub
    writes no files at all).
    """
    assert wia._file_concepts.__module__ == "scripts.wiki_skills.wiki_import_article", (
        "`_file_concepts` is monkeypatched in this module — the contract test is inert")

    vault_root, db_path = live_vault
    rc = _run_import(vault_root, db_path, _write_note(tmp_path))
    out = json.loads(capsys.readouterr().out)
    assert rc == 0, out

    page = vault_root / FOLDER / "_concepts" / "ликвидация.md"
    assert page.is_file(), "no page on disk ⇒ the subprocess never ran ⇒ the test is inert"
    text = page.read_text(encoding="utf-8")
    assert "# Ликвидация" in text
    assert "принудительное закрытие позиции при нехватке маржи." in text

    # The quote receipt does NOT live in the page body — TASK 047 deleted the per-source
    # quote-block from it and moved the receipt onto `page_entity_refs.source_quote`, where
    # `wiki-search`/`wiki-graph` can actually use it. Assert it THERE, verbatim.
    conn = sqlite3.connect(db_path)
    try:
        quote = conn.execute(
            "SELECT source_quote FROM page_entity_refs "
            "WHERE vault_id = ? AND entity_slug = ?", ("testv", "ликвидация"),
        ).fetchone()
    finally:
        conn.close()
    assert quote is not None and quote[0] == _SINGLE_LINE_QUOTE
