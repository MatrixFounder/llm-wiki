"""S4 — `wiki_import_article._authoring` (R-4/R-5)."""
from __future__ import annotations

from scripts.wiki_skills.wiki_import_article import _authoring as A


def test_sanitize_name_rewrites_and_passes_gate():
    assert A.sanitize_name("стейкинг/бондинг") == "стейкинг бондинг"
    assert A.sanitize_name("TEE — ZK") == "TEE - ZK"
    assert A.sanitize_name("«Манифест»") == "Манифест"
    assert A.sanitize_name("A & B") == "A и B"
    # all results must pass the downstream reject-gate
    for raw in ("стейкинг/бондинг", "TEE — ZK", "«Манифест»", "A & B"):
        assert A.name_is_filable(A.sanitize_name(raw))


def test_verbatim_quote_guarantees_substring():
    body = "## Заголовок\n\nAMM — это автоматический маркет-мейкер для DeFi.\n\nДругое.\n"
    # agent quote verbatim → returned as-is
    assert A.verbatim_quote("AMM — это автоматический маркет-мейкер для DeFi.", "AMM", body) in body
    # agent quote NOT verbatim → fallback still a substring
    q = A.verbatim_quote("totally invented quote not present", "AMM", body)
    assert q in body
    # no name match → first prose line, still a substring
    q2 = A.verbatim_quote(None, "Несуществующее", body)
    assert q2 in body


def test_assemble_note_per_mode():
    note = {"title_ru": "Глубокое погружение в DeFi", "tldr": "кратко",
            "summary_bullets": ["вывод 1", "вывод 2"], "ru_body": "полный текст",
            "author": "X", "published": "2025-01-01"}
    for mode, must, mustnot in (
        ("full", "## Полный текст (перевод)", "## Ключевые выводы"),
        ("summary", "## Ключевые выводы", "## Полный текст (перевод)"),
        ("thread", "## Конспект", "## Полный текст (перевод)"),
    ):
        fname, text = A.assemble_note(
            note, mode=mode, raw_rel_basename="05 - Материалы/Крипто/_raw/x.md",
            source_url="https://e.com/x", source_lang="en", today="2026-06-18",
            folder_kind="crypto", san_names=["AMM", "DeFi"])
        assert fname == "Глубокое погружение в DeFi.md"
        assert "[[AMM]] · [[DeFi]]" in text
        assert must in text and mustnot not in text
        assert "type: article-summary" in text and 'URL: "https://e.com/x"' in text


def test_derive_candidates_collision_guard():
    body = "AMM это маркет-мейкер. DeFi это финансы. Bonding это связывание.\n"
    ents = [
        {"name": "AMM", "definition": "d", "quote": "AMM это маркет-мейкер.", "type": "concept"},
        {"name": "DeFi", "definition": "d", "quote": "DeFi это финансы.", "type": "concept"},          # collides existing
        {"name": "Глубокое погружение в DeFi", "definition": "d", "quote": "x", "type": "concept"},     # == note slug
        {"name": "AMM", "definition": "dup", "quote": "y", "type": "concept"},                          # dup slug
        {"name": "///", "definition": "d", "quote": "z", "type": "concept"},                            # unfilable
    ]
    cands, skipped = A.derive_candidates(
        ents, body, slug_strategy="preserve-unicode",
        note_slug="глубокое-погружение-в-defi", existing_page_slugs=["defi"])
    kept = {c["slug"] for c in cands}
    assert kept == {"amm"}
    reasons = {s["reason"] for s in skipped}
    assert reasons == {"collides-existing-page", "self-collision", "duplicate", "unfilable-name"}
    # every kept quote is verbatim in the body
    assert all(c["source_quote"] in body for c in cands)


def test_derive_candidates_skips_when_no_verbatim_quote():
    # degenerate/empty body → no meaningful quote → candidate skipped, not filed with ""
    cands, skipped = A.derive_candidates(
        [{"name": "AMM", "definition": "d", "quote": "x", "type": "concept"}],
        "   \n  ", slug_strategy="preserve-unicode",
        note_slug="note", existing_page_slugs=[])
    assert cands == []
    assert skipped == [{"name": "AMM", "reason": "no-verbatim-quote"}]
