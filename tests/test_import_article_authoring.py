"""S4 — `wiki_import_article._authoring` (R-4/R-5)."""
from __future__ import annotations

from scripts.wiki_skills.wiki_import_article import _authoring as A


def test_sanitize_name_rewrites_and_passes_gate():
    assert A.sanitize_name("стейкинг/бондинг") == "стейкинг бондинг"
    assert A.sanitize_name("TEE — ZK") == "TEE - ZK"
    assert A.sanitize_name("«Манифест»") == "Манифест"
    assert A.sanitize_name("A & B") == "A B"   # `&` → space (language-neutral, not RU "и")
    # all results must pass the downstream reject-gate
    for raw in ("стейкинг/бондинг", "TEE — ZK", "«Манифест»", "A & B"):
        assert A.name_is_filable(A.sanitize_name(raw))


def test_verbatim_quote_guarantees_substring():
    body = "## Заголовок\n\nAMM — это автоматический маркет-мейкер для DeFi.\n\nДругое.\n"
    # agent quote verbatim → returned as-is
    assert A.verbatim_quote("AMM — это автоматический маркет-мейкер для DeFi.", "AMM", body) in body
    # agent quote NOT verbatim but entity name IS mentioned → fall back to the name-line (real mention)
    q = A.verbatim_quote("totally invented quote not present", "AMM", body)
    assert q in body and "AMM" in q
    # neither a verbatim quote nor a name-mention line → "" (caller drops; no fabricated quote)
    q2 = A.verbatim_quote(None, "Несуществующее", body)
    assert q2 == ""


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
            san_names=["AMM", "DeFi"], lang="ru")   # RU vault → RU section headings
        assert fname == "Глубокое погружение в DeFi.md"
        # default mint = preserve-unicode → footer targets the lowercase slug, alias-displays name
        assert "[[amm|AMM]] · [[defi|DeFi]]" in text
        # the _raw original link is an Obsidian-clickable wikilink (not a backtick markdown link)
        assert "[[_raw/x|_raw/x.md]]" in text
        assert "[`_raw/" not in text   # the old non-clickable backtick form is gone
        assert must in text and mustnot not in text
        assert "type: article-summary" in text and 'URL: "https://e.com/x"' in text


def test_footer_links_resolve_under_identity_layout():
    # round-6 MEDIUM: under a karpathy/identity layout a verbatim `[[AMM]]` footer link orphans
    # (reindex resolves the target via identity = no-op → "AMM", but the concept page slug is
    # the lowercase "amm"). The footer must target the MINTED slug, which is a fixed-point of
    # every layout slug_strategy. karpathy's mint = preserve-unicode.
    from scripts.wiki_index.layout_config import _apply_slug_strategy
    note = {"title_ru": "T", "tldr": "t", "summary_bullets": ["b"], "ru_body": "x"}
    _, text = A.assemble_note(
        note, mode="summary", raw_rel_basename="r.md", source_url="u", source_lang="en",
        today="2026-06-18", san_names=["AMM", "Decentralized Finance"],
        mint_strategy="preserve-unicode")
    assert "[[amm|AMM]]" in text                                   # alias-display the name
    assert "[[decentralized-finance|Decentralized Finance]]" in text
    # the fixed-point property the fix relies on: re-slugifying the footer TARGET via the
    # karpathy `identity` strategy yields exactly the lowercase slug the concept page is filed
    # under → the inbound wikilink resolves, no orphan-link at reindex.
    for name in ("AMM", "Decentralized Finance"):
        minted = _apply_slug_strategy(name, "preserve-unicode")   # = concept page slug
        assert _apply_slug_strategy(minted, "identity") == minted  # identity reindex resolves it


def test_assemble_note_is_language_driven_not_hardcoded():
    # the project is international: section headings/labels follow `lang` (the vault language),
    # NOT a hardcoded locale. en is the fallback for an unconfigured/unknown language.
    note = {"title_ru": "T", "tldr": "t", "summary_bullets": ["b"], "ru_body": "x"}
    common = dict(mode="summary", raw_rel_basename="f/_raw/x.md", source_url="u",
                  source_lang="en", today="2026-06-18", san_names=[])
    _, en = A.assemble_note(note, lang="en", **common)
    assert "## Key takeaways" in en and "**Source:**" in en and "lang: en" in en
    assert "Ключев" not in en   # no Russian leaks into an English note
    _, ru = A.assemble_note(note, lang="ru", **common)
    assert "## Ключевые выводы" in ru and "**Источник:**" in ru and "lang: ru" in ru
    _, dflt = A.assemble_note(note, **common)                    # no lang → en fallback
    assert "## Key takeaways" in dflt
    _, unknown = A.assemble_note(note, lang="zz", **common)      # unknown lang → en fallback
    assert "## Key takeaways" in unknown


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


def test_derive_candidates_transliterate_keyspace_catches_collision():
    # HIGH (slug keyspace): on transliterate layouts (dev-project/cybos) a Cyrillic name
    # transliterates to the SAME ascii slug the indexer records, so the collides-existing
    # guard MUST compare in that keyspace — else the owner page is evicted at reindex.
    cands, skipped = A.derive_candidates(
        [{"name": "ДеФи", "definition": "d", "quote": "ДеФи это финансы.", "type": "concept"}],
        "ДеФи это финансы.\n", slug_strategy="transliterate",
        note_slug="x", existing_page_slugs=["defi"])  # transliterate("ДеФи") == "defi"
    assert cands == []
    assert {s["reason"] for s in skipped} == {"collides-existing-page"}


def test_verbatim_quote_skips_the_entity_index_footer_line():
    # the `## Ключевые сущности` footer is not real prose support → must not be captured
    body = "Вступление без упоминаний.\n\n[[AMM]] · [[DeFi]] · [[Uniswap]]\n"
    assert A.verbatim_quote(None, "AMM", body) == ""  # only the index line mentions it → drop


def test_verbatim_quote_fast_path_rejects_footer_line_quote():
    # round-7: the agent-quote fast path must ALSO skip a footer index line (alias form) — else
    # footer reconciliation shrinks that line and the captured quote stops being a substring of
    # the final note (EXTRACTION_PARSE_ERROR). Falls through to the line-scan, which also skips it.
    body = "Реальный абзац про AMM как маркет-мейкер.\n\n[[amm|AMM]] · [[defi|DeFi]]\n"
    footer_quote = "[[amm|AMM]] · [[defi|DeFi]]"           # an exact footer-line substring
    q = A.verbatim_quote(footer_quote, "AMM", body)
    assert q != footer_quote                                # NOT returned from the fast path
    assert "[[" not in q                                    # resolved to real prose (or "")
