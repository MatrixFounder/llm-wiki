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

from scripts.wiki_index.layout_config import _apply_slug_strategy
from scripts.wiki_skills.wiki_extract_concepts._validation import (
    _NAME_ALLOWLIST,
    _is_valid_slug,
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
    """Frontmatter/inline-safe scalar: strip control chars + newlines AND backslashes so an
    orchestrator/fetched-content value cannot inject a YAML key, break a link, or escape the
    closing quote of a double-quoted scalar (a trailing `\\` makes `"v\\"` swallow the quote)
    — CWE-91 / H-6 frontmatter-injection guard."""
    return re.sub(r"[\x00-\x1f\x7f\\]+", " ", str(value or "")).strip()


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
    if aq and aq in body and not any(_INDEX_LINE_RE.match(ln.strip()) for ln in aq.splitlines()):
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
    tldr = _fm_scalar((note.get("tldr") or "").replace('"', "'"))[:300]
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
        f'sources:\n  - "{_fm_scalar(raw_rel_basename).replace(chr(34), chr(39))}"\n'
        f"tags: {_yaml_list(tags)}\n"
        f'tldr: "{tldr}"\n'
        "---\n"
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


def derive_candidates(
    entities: list[dict[str, Any]],
    note_text: str,
    *,
    slug_strategy: str,
    note_slug: str,
    existing_page_slugs: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Entities → extract-concepts candidates + a `skipped` report (R-4/R-5).

    Skips (reported, never silent): empty/unfilable name, dup slug, slug == the
    source note's own slug (self-collision), slug ∈ existing_page_slugs (a generic
    name that would evict an owner page), over the candidate cap (`max-candidates`),
    or no verbatim/mention support in the body (`no-verbatim-quote`). The last two are
    the RECOVERABLE-loss reasons the `apply` envelope surfaces loudly (the literal
    strings key `_LOSSY_SKIP_REASONS` there — keep them in sync). Every kept
    candidate's `source_quote` is a guaranteed-verbatim substring of `note_text`.
    """
    existing = set(existing_page_slugs)
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    note_lines = note_text.splitlines()  # hoisted: was re-split per kept candidate
    for e in entities:
        name = sanitize_name(e.get("name", ""))
        if not name_is_filable(name):
            skipped.append({"name": str(e.get("name")), "reason": "unfilable-name"})
            continue
        slug = _apply_slug_strategy(name, slug_strategy)
        if not _is_valid_slug(slug, max_len=None):
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
        if len(q.strip()) < 3:  # empty/degenerate body → no meaningful mention quote
            skipped.append({"name": name, "reason": "no-verbatim-quote"})
            continue
        seen.add(slug)
        q_lines = q.splitlines()
        first = q_lines[0] if q_lines else q  # multi-line quote → true start line
        line = next((i for i, l in enumerate(note_lines, 1)
                     if first[:40] and first[:40] in l), 1)
        out.append({
            "slug": slug, "name": name,
            "definition": e.get("definition", ""),
            "source_quote": q, "source_span": f"L{line}-L{line}",
            "entity_type": e.get("type", "concept"),
        })
    return out, skipped
