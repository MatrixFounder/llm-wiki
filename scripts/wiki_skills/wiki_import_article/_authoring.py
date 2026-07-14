"""S4 — authoring glue for `wiki-import-article apply` (R-4/R-5).

Pure functions (no I/O) the `apply` facade composes:
  * ``sanitize_name`` — a NORMALIZER that rewrites `/`, em-dash, guillemets, `&`
    to safe forms so the candidate then PASSES the existing
    ``wiki_extract_concepts._validation._sanitize_name`` reject-gate (reusing its
    ``_NAME_ALLOWLIST`` as the validation target — NOT a re-implementation, NF-2).
  * ``verbatim_quote`` — guarantees the concept-page mention quote is a real
    substring of the note body (extract-concepts apply hard-checks this).
  * ``assemble_note`` — per-mode (full / summary / thread) PARA note assembly.
  * ``derive_candidates`` — entities → extract-concepts candidates, applying the
    collision guard (skip self-slug + ``existing_page_slugs``; skipped→reported).
"""
from __future__ import annotations

import re
from typing import Any

from scripts.wiki_index.layout_config import LayoutConfig, _apply_slug_strategy
from scripts.wiki_skills.wiki_extract_concepts._errors import ExtractionParseError
from scripts.wiki_skills.wiki_extract_concepts._gates import (
    check_slugs_derived_from_names,
    derive_concept_slug,
)
from scripts.wiki_skills.wiki_extract_concepts._validation import (
    _NAME_ALLOWLIST,
    _is_valid_slug,
    _preflight_sanitize,
    _validate_candidates_schema,
)

_FNAME_BAD = re.compile(r'[/\\:*?"<>|#^\[\]]')
_ALLOWED_CHAR = re.compile(r"[\w\s\-.,:;()'\"!?]", re.UNICODE)
_MAX_CANDIDATES = 25  # was 15 — full articles legitimately carry 15–18 entities
_QUOTE_CAP = 480
# Obsidian image-embeds to fetched attachments: the html skill runs with --no-download-images,
# so `![[Attachments/<hash>.png]]` (often wrapped as `[![[…]]](url)`) never resolves in the
# target vault → it renders as a broken embed + counts as a dangling link. Strip the line.
_IMG_EMBED_LINE = re.compile(r"^[^\n]*\[\[Attachments/[^\n]*$\n?", re.MULTILINE)
# the entity-index footer: a `·`-separated run of `[[wikilinks]]` (and nothing
# else) — not real prose, so it is not a valid source for a verbatim entity quote.
_INDEX_LINE_RE = re.compile(r"^\[\[[^\]]+\]\]( · \[\[[^\]]+\]\])*$")
# a trailing parenthetical disambiguator on an entity name, e.g. "Зигзаг (волновой анализ)".
# `[^()]*` is bounded + non-nested → ReDoS-safe. Stripping it yields the BASE name the
# body actually prints (the suffix is a slug-collision avoider, not part of the prose).
_DISAMBIG_SUFFIX_RE = re.compile(r"\s*\([^()]*\)\s*$")
def _clean_tag(t: str) -> str:
    """One frontmatter-safe tag: lowercase, hyphenated, no control/special chars.
    Tags are a CONTENT property → they come from the REASON step (which read the
    article), NOT from a folder/topic heuristic (no fixed map covers arbitrary topics)."""
    t = re.sub(r"[\x00-\x1f\x7f]+", "", str(t or "")).strip().lower()
    return re.sub(r"[^\w\-]", "", re.sub(r"\s+", "-", t), flags=re.U).strip("-")


def sanitize_name(name: str) -> str:
    """Rewrite disallowed chars so the name passes the extract-concepts name gate.

    `&` (rejected by the gate) → a plain space — language-NEUTRAL (the project is
    international; never inject a locale's word for 'and'). Quotes/dashes/guillemets are
    punctuation-normalized, not localized."""
    name = (name or "")
    for bad, repl in (("/", " "), ("—", "-"), ("–", "-"), ("―", "-"),
                      ("«", ""), ("»", ""), ("“", '"'), ("”", '"'),
                      ("’", "'"), ("‘", "'"), ("&", " ")):
        name = name.replace(bad, repl)
    name = "".join(ch for ch in name if _ALLOWED_CHAR.match(ch))
    name = re.sub(r"\s+", " ", name).strip(" -")
    return name[:200]


def name_is_filable(name: str) -> bool:
    """True iff `name` would pass the downstream `_NAME_ALLOWLIST` reject-gate."""
    return bool(name) and bool(_NAME_ALLOWLIST.match(name))


def fname_sanitize(title: str) -> str:
    title = _FNAME_BAD.sub("", title or "").strip().rstrip(".")
    return re.sub(r"\s+", " ", title)


def _fm_scalar(value: str) -> str:
    """Frontmatter/inline-safe scalar: strip control chars + newlines (incl. the Unicode line
    breaks NEL U+0085 / LS U+2028 / PS U+2029, which YAML 1.1 treats as line breaks) AND
    backslashes so an orchestrator/fetched-content value cannot inject a YAML key, break a link,
    escape the closing quote of a double-quoted scalar (a trailing `\\` makes `"v\\"` swallow the
    quote), or smuggle a mid-scalar `---`/`...` document separator — CWE-91 / H-6 guard."""
    return re.sub(r"[\x00-\x1f\x7f\x85\u2028\u2029\\]+", " ", str(value or "")).strip()


_TLDR_FM_CAP = 300  # the frontmatter `tldr:` is a PREVIEW scalar (an Obsidian property) \u2192 capped;
#                     the rendered BODY `## brief` section carries the FULL tldr (WI-1).


def _tldr_fm_preview(tldr: str, cap: int = _TLDR_FM_CAP) -> str:
    """The capped frontmatter `tldr:` preview scalar (WI-1). Only THIS frontmatter preview is
    truncated \u2014 the body `## \u041a\u0440\u0430\u0442\u043a\u043e`/`## \u0421\u0430\u043c\u043c\u0430\u0440\u0438` section renders the full tldr. Character-based
    (Python `str` slices by codepoint, so Cyrillic counts as ONE each \u2014 no byte/char mismatch),
    and the cut lands on a WORD boundary with a trailing `\u2026`, never mid-grapheme. A tldr already
    \u2264 `cap` is returned unchanged (byte-identity with pre-WI-1 output)."""
    tldr = tldr.strip()
    if len(tldr) <= cap:
        return tldr
    head = tldr[:cap].rstrip()
    cut = head.rsplit(" ", 1)[0] if " " in head else head  # drop the partial trailing word
    return cut.rstrip(" ,.;:\u2014-") + "\u2026"


def verbatim_quote(agent_quote: str | None, name: str, body: str) -> str:
    """Return a verbatim substring of `body` that SUPPORTS `name`, or ``""`` when none
    exists. Order: (1) the agent's quote if it is an exact substring; (2) a body line that
    mentions the entity by name. If neither holds, return ``""`` so the caller DROPS the
    candidate (`no-verbatim-quote`) — we never attach an unrelated/fabricated mention quote.
    """
    aq = agent_quote.strip() if isinstance(agent_quote, str) else ""  # tolerate non-str
    # Same footer guard as the line-scan path below: never source a quote from the
    # the entity-index wikilink-index line — footer reconciliation rebuilds it, so the
    # quote would no longer be a substring of the final on-disk note (→ EXTRACTION_PARSE_ERROR).
    # `split("\n")`, not `splitlines()` (F5): the LAST line-splitter on this path. A `\x0c`
    # (form feed — a routine PDF→markdown artifact) inside a quote must not be treated as a
    # line break here when neither the span deriver nor the rail's span check treats it as
    # one. One definition of "a line" across producer and consumer, or they disagree.
    if aq and aq in body and not any(_INDEX_LINE_RE.match(ln.strip()) for ln in aq.split("\n")):
        return aq[:_QUOTE_CAP]
    # Probe order: the two PRE-EXISTING probes first (full name, then a short prefix) so any line
    # the old code already matched is returned unchanged — then the BASE name with a trailing
    # `(disambiguator)` stripped (the body prints "Зигзаг (5-3-5)…", never the slug-collision suffix
    # "Зигзаг (волновой анализ)"). Deduped + last → strictly additive: `base` only fires when the
    # old two-probe path returned "", so it can ONLY rescue a previously-dropped candidate.
    base = _DISAMBIG_SUFFIX_RE.sub("", name).strip()
    seen_probes: set[str] = set()
    for probe in (name, name[:14], base):
        if not probe or probe in seen_probes:
            continue
        seen_probes.add(probe)
        pos = 0
        while (idx := body.find(probe, pos)) != -1:
            start = body.rfind("\n", 0, idx) + 1
            end = body.find("\n", idx)
            end = len(body) if end == -1 else end
            line = body[start:end].strip()
            pos = end + 1
            # Skip the entity-index wikilink-index line: it is not real prose
            # support, and the footer reconciliation rebuilds it — a quote captured from it
            # would no longer be a substring of the final note (invalid `source_quote`).
            if _INDEX_LINE_RE.match(line):
                continue
            if len(line) >= 20:
                return line[:_QUOTE_CAP]
    return ""  # no verbatim quote and no name-mention line → caller drops the candidate


def _strip_image_embeds(text: str) -> str:
    """Drop `[[Attachments/…]]` image-embed lines (never resolve — the html skill fetched with
    --no-download-images) and collapse the gap, so they don't leak into the note body."""
    return re.sub(r"\n{3,}", "\n\n", _IMG_EMBED_LINE.sub("", text or ""))


def _yaml_list(items: list[str]) -> str:
    return "[" + ", ".join(items) + "]"


def _footer_link(name: str, mint_strategy: str) -> str:
    """An entity-index wikilink that resolves to the concept page under ANY layout.

    Targets the MINTED slug (what the page is filed as) — a fixed-point of every layout
    `slug_strategy`, so the reindex ref-extractor re-slugifies it back to itself and matches
    `entities.slug`. Uses the Obsidian alias form `[[slug|Name]]` to keep the human display
    when the name isn't already its own slug; a name that IS its slug stays a bare `[[name]]`."""
    slug = _apply_slug_strategy(name, mint_strategy)
    return f"[[{slug}|{name}]]" if slug and slug != name else f"[[{name}]]"


# Localized note-text templates (section headings, labels, origin phrases). The project is
# international: the rendered note language follows the vault's `language` (WIKI_SCHEMA), NOT a
# hardcoded locale. Add a language = add a dict entry (no other code change). `en` is the
# fallback for any unconfigured/unknown language. Placeholders: {lang}/{src}/{dst} = UPPER-cased
# language codes (e.g. EN, RU, DE). `ru` reproduces the pre-i18n output byte-for-byte.
NOTE_TEMPLATES: dict[str, dict[str, str]] = {
    "en": {
        "summary": "Summary", "key_findings": "Key takeaways", "theses": "Key points",
        "entities": "Key entities", "full_text": "Full text (translation)",
        "synopsis": "Synopsis", "brief": "TL;DR", "source": "Source", "author": "by",
        "raw": "Original (raw)", "raw_full": "Full original text in",
        "origin_thread": "thread on X (author's opinion)", "origin_same": "original in {lang}",
        "origin_summary": "{src} original, {dst} summary",
        "origin_translation": "{src} original, {dst} translation",
    },
    "ru": {
        "summary": "Саммари", "key_findings": "Ключевые выводы", "theses": "Основные тезисы",
        "entities": "Ключевые сущности", "full_text": "Полный текст (перевод)",
        "synopsis": "Конспект", "brief": "Кратко", "source": "Источник", "author": "автор",
        "raw": "Оригинал (raw)", "raw_full": "Полный текст оригинала — в",
        "origin_thread": "тред X (мнение автора)", "origin_same": "оригинал {lang}",
        "origin_summary": "оригинал {src}, {dst}-саммари",
        "origin_translation": "оригинал {src}, перевод {dst}",
    },
}


def note_templates(lang: str) -> dict[str, str]:
    """The note-text template for `lang`, falling back to English (international default)."""
    return NOTE_TEMPLATES.get((lang or "en").lower(), NOTE_TEMPLATES["en"])


def assemble_note(
    note: dict[str, Any],
    *,
    mode: str,
    raw_rel_basename: str,
    source_url: str,
    source_lang: str,
    today: str,
    san_names: list[str],
    note_type: str = "article-summary",
    fname: str | None = None,
    mint_strategy: str = "preserve-unicode",
    lang: str = "en",
    grammar: str = "article",
    classification: str | None = None,
) -> tuple[str, str]:
    """Build (filename, full note text) for the given mode/grammar. `san_names` are the
    already-sanitized entity names used for the entity-index wikilinks.

    `grammar` (TASK 046) selects the note shape: ``"article"`` (default) keeps the per-`mode`
    section wrappers (Саммари/Ключевые сущности/Полный текст); ``"pyramid"`` (meeting/lesson)
    files the REASON-authored body VERBATIM under the frontmatter+header with NO article
    wrappers — the body already carries its own pyramid (TL;DR + decisions/sections). The
    entity footer is appended only when `san_names` is non-empty (concepts on; with
    --no-concepts the caller passes an empty `san_names` → no dangling footer).

    `lang` selects the localized section headings/labels (the vault's `language`; en fallback)
    — the project is international, so NO output string is hardcoded to one locale.
    `mint_strategy` is the keyspace the concept pages are filed under (the import's `mint`).
    The footer links MUST target the minted slug — not the verbatim name — so they resolve
    under EVERY layout: the minted slug is a fixed-point of every `slug_strategy`, whereas a
    verbatim `[[Name]]` orphans under an `identity` (karpathy) layout, where the reindex
    ref-extractor does NOT lowercase the target to match the lowercase concept-page slug."""
    t = note_templates(lang)
    # Frontmatter/inline scalars carry orchestrator/fetched-content values → newline &
    # control-strip them so they cannot inject a YAML key or break the source link (H-6).
    # The note BODY (ru_body / summary_bullets) is intentionally orchestrator-authored
    # markdown (same trust posture as wiki-ingest/summarizing-meetings summaries) and is
    # NOT escaped — escaping would mangle a legitimate translation's headings/lists.
    # neutral field names (international); `title_ru`/`ru_body` accepted as legacy back-compat
    title = _fm_scalar(note.get("title") or note.get("title_ru") or "untitled")
    # PARA files under the human title; karpathy passes an explicit slug-based fname
    # (its `identity` strategy makes filename == slug, which must be a valid lowercase slug).
    fname = fname or (fname_sanitize(title) + ".md")
    # WI-1: the FULL tldr feeds the rendered body `## brief` section (the REASON contract already
    # bounds tldr to "1–2 sentences", so the body needs no cap). Only the frontmatter `tldr:` scalar
    # is a preview → capped on a WORD boundary (never the old mid-word `[:300]` slice). Keep the raw
    # tldr (literal `"` intact) for the BODY so it byte-matches the orchestrator-authored text — the
    # verbatim-quote gate resolves against it, and this mirrors the sibling scalars (title/author/…)
    # which keep raw quotes in the variable and normalize `"`→`'` ONLY at the frontmatter emission.
    tldr = _fm_scalar(note.get("tldr") or "")
    tldr_fm = _tldr_fm_preview(tldr)
    author = _fm_scalar(note.get("author") or "")
    published = _fm_scalar(note.get("published") or "")
    url = _fm_scalar(source_url)
    title_orig = _fm_scalar(note.get("title_orig") or title)
    bullets = "\n".join(f"- {b.strip()}" for b in note.get("summary_bullets", []))
    body_text = _strip_image_embeds(note.get("body") or note.get("ru_body") or "").strip()
    wikilinks = " · ".join(_footer_link(n, mint_strategy) for n in san_names)
    # tags come from the REASON step (content-aware); fall back to a single generic tag.
    tags = [c for c in (_clean_tag(t) for t in (note.get("tags") or [])) if c] or ["article"]

    src = (source_lang or "").upper()
    dst = (lang or "en").upper()
    same_lang = bool(source_lang) and source_lang.lower() == (lang or "en").lower()
    if grammar == "pyramid":
        # TASK 046: a pyramid (meeting/lesson) is a DIGEST, not a verbatim translation, REGARDLESS
        # of --mode (which is orthogonal to --kind) — label it the same-language original or a
        # "{dst}-саммари/summary", never "перевод/translation" and never the thread phrasing.
        origin = " · " + (t["origin_same"].format(lang=src) if same_lang
                          else t["origin_summary"].format(src=src, dst=dst))
    elif mode == "thread":
        origin = " · " + t["origin_thread"]
    elif same_lang:
        origin = " · " + t["origin_same"].format(lang=src)
    elif mode == "summary":
        origin = " · " + t["origin_summary"].format(src=src, dst=dst)
    else:
        origin = " · " + t["origin_translation"].format(src=src, dst=dst)
    src_line = (f"> **{t['source']}:** [{title_orig}]({url})"
                + (f" · {t['author']} {author}" if author else "")
                + (f" · {published}" if published else "")
                + origin + ".")

    # TASK 052: a pyramid (meeting/lesson) records ATTENDEES in `participants:` frontmatter — a real
    # home so the REASON step stops smuggling people into `entities[]` (person concept pages). H-6:
    # each value is control/newline/backslash-stripped (`_fm_scalar`) so it cannot inject a YAML key
    # or break the scalar. Emitted ONLY for pyramid grammar with a non-empty list → article grammar
    # and a pyramid without participants stay byte-identical to pre-052 output.
    _pl = note.get("participants")
    _parts = ([p for p in (_fm_scalar(x) for x in _pl) if p]
              if grammar == "pyramid" and isinstance(_pl, list) else [])
    participants_fm = ("participants:\n"
                       + "".join(f'  - "{p.replace(chr(34), chr(39))}"\n'
                                 for p in dict.fromkeys(_parts))  # de-dup, preserve order
                       ) if _parts else ""

    fm = (
        "---\n"
        f"type: {note_type}\n"
        # TASK 049 (R-7): opt-in policy stamp. The value is argparse-shape-
        # validated ([a-z][a-z0-9_-]{0,15}) — safe as a bare YAML scalar; the
        # key is absent when the flag is omitted (NFR-1 byte-identity).
        + (f"classification: {classification}\n" if classification else "")
        + f'title: "{title.replace(chr(34), chr(39))}"\n'
        f'URL: "{url.replace(chr(34), chr(39))}"\n'
        + (f'author: "{author.replace(chr(34), chr(39))}"\n' if author else "")
        + (f'published: "{published.replace(chr(34), chr(39))}"\n' if published else "")
        + f"Created: {today}T13:00\nUpdated: {today}T13:00\nlang: {(lang or 'en').lower()}\n"
        + participants_fm
        + f'sources:\n  - "{_fm_scalar(raw_rel_basename).replace(chr(34), chr(39))}"\n'
        + f"tags: {_yaml_list(tags)}\n"
        # WI-1: capped word-boundary PREVIEW (the body carries the full tldr); `"`→`'` normalized
        # HERE at emission, like every sibling scalar — never baked into the body-facing `tldr`.
        + f'tldr: "{tldr_fm.replace(chr(34), chr(39))}"\n'
        + "---\n"
    )
    _raw_base = raw_rel_basename.rsplit('/', 1)[-1]
    _raw_stem = _raw_base.rsplit('.', 1)[0]
    # Obsidian-clickable wikilink to the sibling `_raw/` capture. The `_raw/` path prefix
    # both disambiguates the target AND lets reindex skip it from orphan-link lint (a link to
    # the intentionally-unindexed raw capture is not an orphan). `sources:` frontmatter keeps
    # the machine-readable PATH (resummarization matches it against the FS) — do not change it.
    _raw_link = f"[[_raw/{_raw_stem}|_raw/{_raw_base}]]"
    head = (f"\n# {title}\n\n{src_line}\n"
            f"> **{t['raw']}:** {_raw_link}\n\n")
    # Entity-index section — OMITTED entirely when there are no filable entities (e.g. TASK 046
    # --no-concepts, or all candidates dropped) so no empty "## Ключевые сущности" heading with a
    # blank body slips in. Byte-identical to the old output whenever `san_names` is non-empty.
    ents = f"## {t['entities']}\n\n{wikilinks}\n\n" if san_names else ""
    if grammar == "pyramid":
        # TASK 046: the REASON-authored pyramid IS the body — file it verbatim under the
        # header, NO article wrappers. Entity footer only when there are filable entities.
        body = head + body_text + "\n"
        if san_names:
            body += f"\n## {t['entities']}\n\n{wikilinks}\n"
    elif mode == "full":
        body = (head + f"## {t['summary']}\n\n{bullets}\n\n" + ents
                + f"## {t['full_text']}\n\n{body_text}\n")
    elif mode == "summary":
        body = (head + (f"## {t['brief']}\n\n{tldr}\n\n" if tldr else "")
                + f"## {t['key_findings']}\n\n{bullets}\n\n" + ents
                + f"_{t['raw_full']}_ {_raw_link}_._\n")
    else:  # thread
        body = (head + (f"## {t['brief']}\n\n{tldr}\n\n" if tldr else "")
                + f"## {t['theses']}\n\n{bullets}\n\n" + ents
                + f"## {t['synopsis']}\n\n{body_text}\n")
    return fname, fm + body


def span_for_quote(quote: str, text: str) -> str | None:
    """The `L{start}-L{end}` span that ACTUALLY CONTAINS `quote` in `text` — or `None`.

    ★★ F1 (TASK 064 FIX-LOOP) — THE OLD DERIVATION WAS **STRUCTURALLY INCAPABLE** OF
    DESCRIBING A MULTI-LINE QUOTE. It took the quote's FIRST line, found the body line
    containing it, and emitted `L{line}-L{line}` — a ONE-LINE span. `wiki-extract-concepts`
    now VERIFIES that the span contains the quote (G9), so any quote spanning two lines
    could never satisfy it: guaranteed `SOURCE_SPAN_QUOTE_MISMATCH`, and the whole import
    dies at exit 6 with ZERO concept pages written.

    ★ `\\n`-ONLY, NEVER `splitlines()` (F5). `str.splitlines()` also breaks on `\\x0c`
    (form feed — a routine PDF→markdown artifact, and `wiki-import` IS the PDF on-ramp),
    `\\x0b`, `\\x85`, `U+2028`, `U+2029`. The consumer counts `\\n`; so must the producer,
    or the two disagree about what line 12 is on exactly the sources this rail is fed.
    """
    idx = text.find(quote)
    if idx == -1:
        return None
    start = text.count("\n", 0, idx) + 1
    end = start + quote.count("\n")
    return f"L{start}-L{end}"


# `wiki-extract-concepts` refusal code → the `skipped[]` reason we report instead.
#
# ★★ THE POINT OF THIS TABLE: `wiki-import` HAS NO CONCEPT WRITER OF ITS OWN — `_file_concepts`
# SHELLS OUT to `wiki-extract-concepts apply`. So the rail's gates run on candidates THIS file
# produces, and a producer/consumer divergence does not degrade the import, it DESTROYS it:
# one offending entity ⇒ exit 4 from the rail ⇒ exit 6 + `action: partial` from `wiki-import`
# ⇒ **zero** concept pages, including every legitimate one in the same batch, and a filed note
# whose footer wikilinks now dangle. That is exactly what TASK 064's first cut shipped.
#
# The repair is not "keep the two in sync by being careful" — that is the promise that just
# failed. `finalize_candidates` runs the RAIL'S OWN VALIDATORS and turns each refusal into a
# per-candidate SKIP. A future gate added to the rail lands here as a skip, never as a batch
# kill, and `tests/test_import_concepts_contract.py` drives the real subprocess to prove it.
_SKIP_REASON_BY_CODE = {
    "DEFINITION_IS_QUOTE": "definition-is-quote",
    "DEFINITION_NOT_PROSE": "definition-not-prose",
    "ENTITY_TYPE_NOT_ALLOWED": "participant-not-concept",
    "FIELD_QUOTE_NOT_IN_BODY": "no-verbatim-quote",
    "FIELD_TOO_LONG": "field-too-long",
    "INVALID_NAME_FORMAT": "unfilable-name",
    "INVALID_SLUG_CHARSET": "invalid-slug",
    "SLUG_NOT_DERIVED_FROM_NAME": "invalid-slug",
    "SOURCE_SPAN_OUT_OF_RANGE": "no-verbatim-quote",
    "SOURCE_SPAN_QUOTE_MISMATCH": "no-verbatim-quote",
}
# FIELD_TOO_SHORT is per-FIELD: an empty definition and a one-token quote are different
# operator problems with different fixes, and one hint cannot serve both.
_SKIP_REASON_BY_SHORT_FIELD = {
    "definition": "definition-too-short",
    "source_quote": "no-verbatim-quote",
    "name": "unfilable-name",
}


def _skip_reason(err: ExtractionParseError) -> str:
    if err.error == "FIELD_TOO_SHORT":
        return _SKIP_REASON_BY_SHORT_FIELD.get(err.field or "", "rejected-by-concept-rail")
    return _SKIP_REASON_BY_CODE.get(err.error or "", "rejected-by-concept-rail")


def finalize_candidates(
    candidates: list[dict[str, Any]],
    note_text: str,
    config: LayoutConfig,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Re-derive each candidate's span against the FINAL note text, then run the RAIL'S OWN
    validators over it. Returns ``(kept, dropped)`` — **it never raises.**

    ★ WHY THE SPAN MUST BE RE-DERIVED HERE. `apply` assembles the note, derives candidates,
    then RECONCILES THE FOOTER and re-assembles — and on the `full`/`summary`/`thread`
    grammars the entity-index footer sits in the MIDDLE of the note (`head + summary +
    bullets + ENTS + full_text`). Dropping one entity from that footer shifts every
    subsequent line UP. A span computed against the pre-reconciliation text is therefore
    simply WRONG for the bytes that reach disk — which nobody noticed while the rail
    accepted spans unverified, and which becomes an instant `SOURCE_SPAN_QUOTE_MISMATCH`
    now that it verifies them. Spans are derived from the text that is actually WRITTEN.

    ★ AND WHY THE VALIDATION IS THE RAIL'S, NOT A COPY OF IT. See `_SKIP_REASON_BY_CODE`.
    A re-implementation is a second contract that can drift from the first; calling the
    real `_validate_candidates_schema` / `check_slugs_derived_from_names` /
    `_preflight_sanitize` means the producer is judged by the consumer's own law. A
    candidate that fails is DROPPED and REPORTED — never fatal to the batch, because a
    partial concept filing is correct and a zero-concept import is not.
    """
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, str]] = []
    for cand in candidates:
        span = span_for_quote(str(cand["source_quote"]), note_text)
        if span is None:
            # The quote is not in the FINAL bytes (it was only supported by a footer line
            # that reconciliation removed). Nothing to point a span at.
            dropped.append({"name": str(cand["name"]), "reason": "no-verbatim-quote"})
            continue
        probe = {**cand, "source_span": span}
        try:
            _validate_candidates_schema([probe], source_body=note_text)
            check_slugs_derived_from_names([probe], config)
            _preflight_sanitize([probe])
        except ExtractionParseError as err:
            dropped.append({"name": str(cand["name"]), "reason": _skip_reason(err),
                            "code": str(err.error or "EXTRACTION_PARSE_ERROR")})
            continue
        cand["source_span"] = span
        kept.append(cand)
    return kept, dropped


def derive_candidates(
    entities: list[dict[str, Any]],
    note_text: str,
    *,
    slug_strategy: str,
    note_slug: str,
    existing_page_slugs: list[str],
    grammar: str = "article",
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Entities → extract-concepts candidates + a `skipped` report (R-4/R-5).

    This is the SELECTION pass. The spans it emits are provisional — `finalize_candidates`
    re-derives them against the note text that is actually written, and applies the rail's
    own validators (see its docstring).

    Skips (reported, never silent): empty/unfilable name, a **`person` entity on ANY
    grammar** (`participant-not-concept`), dup slug, slug == the source note's own slug
    (self-collision), slug ∈ existing_page_slugs (a generic name that would evict an owner
    page), over the candidate cap (`max-candidates`), or no verbatim/mention support in the
    body (`no-verbatim-quote`). The RECOVERABLE ones are surfaced loudly by the `apply`
    envelope (the literal strings key `_LOSSY_SKIP_REASONS` there — keep them in sync).
    Every kept candidate's `source_quote` is a guaranteed-verbatim substring of `note_text`.
    """
    existing = set(existing_page_slugs)
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for e in entities:
        name = sanitize_name(e.get("name", ""))
        if not name_is_filable(name):
            skipped.append({"name": str(e.get("name")), "reason": "unfilable-name"})
            continue
        # ★★ F1 (TASK 064 FIX-LOOP) — `person` IS DROPPED ON **EVERY** GRAMMAR.
        #
        # TASK 052 dropped it only under `grammar == "pyramid"`, so the ARTICLE path leaked:
        # `уоррен-баффет` and `гарри-марковиц` are LIVE person pages in the operator's vault,
        # filed by this very function. `wiki-extract-concepts` now refuses `person` outright
        # (G4, `ENTITY_TYPE_NOT_ALLOWED`) — so on the article path the leak did not merely
        # continue, it turned FATAL: one `person` entity killed the entire concept batch.
        # The operator's standing rule has no grammar clause in it: an attendee belongs in
        # `participants:`, a cited author in the note body, neither in `_concepts/`.
        #
        # INTENTIONAL, not a recoverable loss → deliberately NOT in `_LOSSY_SKIP_REASONS`
        # (visible in `skipped[]`, no CONCEPTS_DROPPED warning). `group` is deliberately
        # KEPT: a committee/team can be a real domain concept (Q-052-1).
        if str(e.get("type", "")).strip().lower() == "person":
            skipped.append({"name": name, "reason": "participant-not-concept"})
            continue
        # Mint through the RAIL's own derivation (`_gates.derive_concept_slug`), which
        # normalises `_`→`-` and rejects a degenerate result — so the slug this function
        # produces is one the rail's charset gate and G8 both accept, by construction.
        slug = derive_concept_slug(name, slug_strategy)
        if slug is None:
            skipped.append({"name": name, "reason": "invalid-slug"})
            continue
        if slug in seen:
            skipped.append({"name": name, "reason": "duplicate"})
            continue
        if slug == note_slug:
            skipped.append({"name": name, "reason": "self-collision"})
            continue
        if slug in existing:
            skipped.append({"name": name, "reason": "collides-existing-page"})
            continue
        # Cap reached → REPORT the overflow (never silently drop — else the tail becomes
        # dangling `[[wikilinks]]` in the footer) and skip the O(body) verbatim_quote scan.
        if len(out) >= _MAX_CANDIDATES:
            skipped.append({"name": name, "reason": "max-candidates"})
            continue
        q = verbatim_quote(e.get("quote"), name, note_text)
        if not q.strip():  # empty/degenerate body → no meaningful mention quote
            skipped.append({"name": name, "reason": "no-verbatim-quote"})
            continue
        seen.add(slug)
        out.append({
            "slug": slug, "name": name,
            "definition": str(e.get("definition", "") or ""),
            "source_quote": q,
            # Provisional — `finalize_candidates` recomputes it against the FINAL bytes.
            "source_span": span_for_quote(q, note_text) or "L1-L1",
            "entity_type": str(e.get("type", "concept") or "concept"),
        })
    return out, skipped
