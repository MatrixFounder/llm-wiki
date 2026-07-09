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


def test_wi1_tldr_fm_preview_word_boundary_and_ellipsis():
    # WI-1 unit: the frontmatter preview caps on a WORD boundary + `…` (never mid-grapheme), is
    # character-based (Cyrillic = 1 each), and returns a ≤300-char tldr unchanged (byte-identity).
    assert A._tldr_fm_preview("кратко") == "кратко"                 # short → unchanged
    long = " ".join(["слово"] * 100)                                 # 600 chars, word-separated
    prev = A._tldr_fm_preview(long)
    assert prev.endswith("…") and len(prev) <= 301                   # capped + ellipsis
    assert not prev[:-1].endswith("слов")                            # not cut mid-word
    assert long.startswith(prev[:-1])                                # a genuine prefix span


def test_wi1_full_tldr_in_body_but_capped_in_frontmatter():
    # WI-1: a tldr > 300 chars renders IN FULL in the body `## brief` section; only the frontmatter
    # `tldr:` scalar is capped — on a word boundary + `…`, never the old mid-word `[:300]` slice.
    import re as _re
    long_tldr = ("Метод прицельно перемаскирует только вероятно неверные токены и тем самым "
                 "ускоряет диффузионное декодирование без потери качества генерации текста на "
                 "широком классе задач обработки естественного языка и машинного рассуждения "
                 "современных языковых моделей глубокого обучения что подтверждено многочисленными "
                 "экспериментами на публичных бенчмарках и проверено независимыми исследователями.")
    assert len(long_tldr) > 300
    note = {"title_ru": "T", "tldr": long_tldr, "summary_bullets": ["b1"], "ru_body": "x"}
    _, text = A.assemble_note(
        note, mode="summary", raw_rel_basename="f/_raw/x.md", source_url="u",
        source_lang="en", today="2026-06-18", san_names=[], lang="ru")
    assert long_tldr in text                                          # body carries the FULL tldr
    fm_tldr = _re.search(r'^tldr: "(.*)"$', text, _re.MULTILINE).group(1)
    assert fm_tldr.endswith("…") and len(fm_tldr) <= 301             # frontmatter capped
    preview = fm_tldr[:-1]
    assert long_tldr.startswith(preview)                             # genuine prefix
    assert not long_tldr[len(preview):len(preview) + 1].isalnum()    # cut at a boundary, not mid-word


def test_wi1_tldr_keeps_raw_quotes_in_body_normalizes_in_frontmatter():
    # WI-1 (+ vdd logic/security converge): the body-rendered tldr keeps its literal `"` so it
    # byte-matches the orchestrator-authored text (verbatim-quote resolution) and is consistent with
    # the sibling scalars; the frontmatter `tldr:` preview normalizes `"`→`'` at emission (YAML-safe).
    note = {"title_ru": "T", "tldr": 'Он назвал это "ремаскингом" токенов.',
            "summary_bullets": ["b"], "ru_body": "x"}
    _, text = A.assemble_note(
        note, mode="summary", raw_rel_basename="f/_raw/x.md", source_url="u",
        source_lang="en", today="2026-06-18", san_names=[], lang="ru")
    assert '## Кратко\n\nОн назвал это "ремаскингом" токенов.' in text     # body: raw quotes intact
    assert 'tldr: "Он назвал это \'ремаскингом\' токенов."' in text          # frontmatter: normalized
    assert 'tldr: "Он назвал это "' not in text                            # scalar never broken by a raw `"`


def test_wi2_summary_mode_quote_fallback_searches_rendered_bullets():
    # WI-2: in mode=summary `body` is null → the entity quote resolves against the RENDERED summary
    # note (tldr + bullets). derive_candidates runs on that rendered text, so a bullet line naming the
    # entity IS a valid fallback; an entity absent from tldr+bullets drops `no-verbatim-quote`.
    note = {"title_ru": "Обзор диффузии", "tldr": "Диффузионные LLM ускоряют декодирование.",
            "summary_bullets": ["Ремаскинг перемаскирует только вероятно неверные токены.",
                                "Качество генерации сохраняется на широких бенчмарках."],
            "ru_body": None}
    _, rendered = A.assemble_note(
        note, mode="summary", raw_rel_basename="f/_raw/x.md", source_url="u",
        source_lang="en", today="2026-06-18", san_names=[], lang="ru")
    assert "## Полный текст" not in rendered                          # summary mode → no body section
    ents = [
        {"name": "Ремаскинг", "definition": "d",                     # verbatim bullet substring → kept
         "quote": "Ремаскинг перемаскирует только вероятно неверные токены.", "type": "concept"},
        {"name": "Качество генерации", "definition": "d",            # paraphrased quote, name in a bullet
         "quote": "выдуманная цитата которой нет", "type": "concept"},  # → rescued by name-mention fallback
        {"name": "Квантовая телепортация", "definition": "d",        # named nowhere → dropped
         "quote": "тоже нет", "type": "concept"},
    ]
    cands, skipped = A.derive_candidates(
        ents, rendered, slug_strategy="preserve-unicode",
        note_slug="obzor-diffuzii", existing_page_slugs=[])
    kept = {c["name"] for c in cands}
    assert "Ремаскинг" in kept                                        # exact bullet quote
    assert "Качество генерации" in kept                               # resolved via a bullet-line mention
    assert {"name": "Квантовая телепортация", "reason": "no-verbatim-quote"} in skipped
    assert all(c["source_quote"] in rendered for c in cands)          # every kept quote is verbatim


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


def test_verbatim_quote_matches_base_name_ignoring_disambiguator():
    # TASK 042: a slug-collision disambiguator suffix "(волновой анализ)" is NOT printed in the
    # body — the body says "Зигзаг (5-3-5) …". The name-mention fallback must probe the BASE name
    # so a paraphrased agent quote still resolves to a real body line (was dropped before).
    body = ("Вступление.\n\nЗигзаг (5-3-5) — быстрый откат против тренда; на медвежьем "
            "рынке формируется в обратном направлении.\n")
    q = A.verbatim_quote("Зигзаг — простая модель из трёх волн A–B–C",   # paraphrase, not in body
                         "Зигзаг (волновой анализ)", body)
    assert q and q in body and "Зигзаг (5-3-5)" in q       # rescued via the base-name probe
    # a base name that appears NOWHERE still drops (no fabricated quote)
    assert A.verbatim_quote(None, "Несуществующее (волновой анализ)", body) == ""


def test_verbatim_quote_prefix_probe_precedes_base_probe():
    # TASK 042 additivity lock: the base-name probe must NOT override a line the pre-existing
    # name[:14] probe already matched (else an EXISTING candidate's quote could change). Probe
    # order is (name, name[:14], base) — name[:14]="Зигзаг (волнов" wins over the earlier bare
    # "Зигзаг" line. (The wrong order (name, base, name[:14]) would return line_base instead.)
    line_base = "Зигзаг — это коррекционная модель волнового анализа подробно."
    line_prefix = "Зигзаг (волновой) тип описан здесь в деталях достаточно."
    body = f"{line_base}\n\n{line_prefix}\n"
    assert A.verbatim_quote(None, "Зигзаг (волновой анализ)", body) == line_prefix


def test_derive_candidates_keeps_disambiguated_entity():
    # TASK 042 integration: the exact shape that silently dropped "Зигзаг"/"Плоскость" — a
    # disambiguated name + a quote paraphrased from the raw source — is now KEPT (base name is
    # in the body), and its stored source_quote is a verbatim substring.
    body = ("Зигзаг (5-3-5) — быстрый откат против тренда.\n\n"
            "Плоскость (3-3-5) — консолидация перед продолжением тренда.\n")
    ents = [
        {"name": "Зигзаг (волновой анализ)", "definition": "d",
         "quote": "Зигзаг (5-3-5) — простая модель из трёх волн", "type": "concept"},   # paraphrase
        {"name": "Плоскость (волновой анализ)", "definition": "d",
         "quote": "Плоскость (3-3-5) — структура консолидации", "type": "concept"},     # paraphrase
    ]
    cands, skipped = A.derive_candidates(
        ents, body, slug_strategy="preserve-unicode",
        note_slug="volny-elliotta", existing_page_slugs=[])
    assert skipped == []                                   # nothing dropped
    assert len(cands) == 2
    assert all(c["source_quote"] in body for c in cands)   # verbatim substrings of the note body
