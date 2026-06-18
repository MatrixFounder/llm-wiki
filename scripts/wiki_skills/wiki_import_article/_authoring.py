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
_MAX_CANDIDATES = 15
_QUOTE_CAP = 480
_TAGS_BASE = {
    "crypto": ["article", "defi", "crypto"],
    "invest": ["article", "investing", "finance"],
}
_EXTRA_TAGS = {"summary": ["paper", "summary"], "thread": ["thread", "opinion"], "full": []}


def sanitize_name(name: str) -> str:
    """Rewrite disallowed chars so the name passes the extract-concepts name gate."""
    name = (name or "")
    for bad, repl in (("/", " "), ("—", "-"), ("–", "-"), ("―", "-"),
                      ("«", ""), ("»", ""), ("“", '"'), ("”", '"'),
                      ("’", "'"), ("‘", "'"), ("&", " и ")):
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
    """Frontmatter/inline-safe scalar: strip control chars + newlines so an
    orchestrator/fetched-content value cannot inject a YAML key or break a link
    (CWE-91 / H-6 frontmatter-injection guard)."""
    return re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or "")).strip()


def verbatim_quote(agent_quote: str | None, name: str, body: str) -> str:
    """Return a verbatim substring of `body` that SUPPORTS `name`, or ``""`` when none
    exists. Order: (1) the agent's quote if it is an exact substring; (2) a body line that
    mentions the entity by name. If neither holds, return ``""`` so the caller DROPS the
    candidate (`no-verbatim-quote`) — we never attach an unrelated/fabricated mention quote.
    """
    aq = (agent_quote or "").strip()
    if aq and aq in body:
        return aq[:_QUOTE_CAP]
    for probe in (name, name[:14]):
        if not probe:
            continue
        idx = body.find(probe)
        if idx != -1:
            start = body.rfind("\n", 0, idx) + 1
            end = body.find("\n", idx)
            end = len(body) if end == -1 else end
            line = body[start:end].strip()
            if len(line) >= 20:
                return line[:_QUOTE_CAP]
    return ""  # no verbatim quote and no name-mention line → caller drops the candidate


def _yaml_list(items: list[str]) -> str:
    return "[" + ", ".join(items) + "]"


def assemble_note(
    note: dict[str, Any],
    *,
    mode: str,
    raw_rel_basename: str,
    source_url: str,
    source_lang: str,
    today: str,
    folder_kind: str,
    san_names: list[str],
) -> tuple[str, str]:
    """Build (filename, full note text) for the given mode. `san_names` are the
    already-sanitized entity names used for the `## Ключевые сущности` wikilinks."""
    # Frontmatter/inline scalars carry orchestrator/fetched-content values → newline &
    # control-strip them so they cannot inject a YAML key or break the source link (H-6).
    # The note BODY (ru_body / summary_bullets) is intentionally orchestrator-authored
    # markdown (same trust posture as wiki-ingest/summarizing-meetings summaries) and is
    # NOT escaped — escaping would mangle a legitimate translation's headings/lists.
    title = _fm_scalar(note.get("title_ru") or "untitled")
    fname = fname_sanitize(title) + ".md"
    tldr = _fm_scalar((note.get("tldr") or "").replace('"', "'"))[:300]
    author = _fm_scalar(note.get("author") or "")
    published = _fm_scalar(note.get("published") or "")
    url = _fm_scalar(source_url)
    title_orig = _fm_scalar(note.get("title_orig") or title)
    bullets = "\n".join(f"- {b.strip()}" for b in note.get("summary_bullets", []))
    wikilinks = " · ".join(f"[[{n}]]" for n in san_names)
    tags = _TAGS_BASE.get(folder_kind, ["article"]) + _EXTRA_TAGS.get(mode, [])

    if mode == "thread":
        origin = " · тред X (мнение автора)"
    elif source_lang == "ru":
        origin = " · оригинал RU"
    elif mode == "summary":
        origin = " · оригинал EN, RU-саммари"
    else:
        origin = " · оригинал EN, перевод RU"
    src_line = (f"> **Источник:** [{title_orig}]({url})"
                + (f" · автор {author}" if author else "")
                + (f" · {published}" if published else "")
                + origin + ".")

    fm = (
        "---\n"
        "type: article-summary\n"
        f'title: "{title.replace(chr(34), chr(39))}"\n'
        f'URL: "{url.replace(chr(34), chr(39))}"\n'
        + (f'author: "{author.replace(chr(34), chr(39))}"\n' if author else "")
        + (f'published: "{published.replace(chr(34), chr(39))}"\n' if published else "")
        + f"Created: {today}T13:00\nUpdated: {today}T13:00\nlang: ru\n"
        f'sources:\n  - "{raw_rel_basename}"\n'
        f"tags: {_yaml_list(tags)}\n"
        f'tldr: "{tldr}"\n'
        "---\n"
    )
    head = (f"\n# {title}\n\n{src_line}\n"
            f"> **Оригинал (raw):** `_raw/{raw_rel_basename.rsplit('/', 1)[-1]}`\n\n")
    if mode == "full":
        body = (head + f"## Саммари\n\n{bullets}\n\n"
                + f"## Ключевые сущности\n\n{wikilinks}\n\n"
                + f"## Полный текст (перевод)\n\n{(note.get('ru_body') or '').strip()}\n")
    elif mode == "summary":
        body = (head + (f"## Кратко\n\n{tldr}\n\n" if tldr else "")
                + f"## Ключевые выводы\n\n{bullets}\n\n"
                + f"## Ключевые сущности\n\n{wikilinks}\n\n"
                + f"_Полный текст оригинала — в_ `_raw/{raw_rel_basename.rsplit('/', 1)[-1]}`_._\n")
    else:  # thread
        body = (head + (f"## Кратко\n\n{tldr}\n\n" if tldr else "")
                + f"## Основные тезисы\n\n{bullets}\n\n"
                + f"## Ключевые сущности\n\n{wikilinks}\n\n"
                + f"## Конспект\n\n{(note.get('ru_body') or '').strip()}\n")
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
    name that would evict an owner page). Every kept candidate's `source_quote` is
    a guaranteed-verbatim substring of `note_text`.
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
        q = verbatim_quote(e.get("quote"), name, note_text)
        if len(q.strip()) < 3:  # empty/degenerate body → no meaningful mention quote
            skipped.append({"name": name, "reason": "no-verbatim-quote"})
            continue
        seen.add(slug)
        first = q.splitlines()[0] if q.splitlines() else q  # multi-line quote → true start line
        line = next((i for i, l in enumerate(note_text.splitlines(), 1)
                     if first[:40] and first[:40] in l), 1)
        out.append({
            "slug": slug, "name": name,
            "definition": e.get("definition", ""),
            "source_quote": q, "source_span": f"L{line}-L{line}",
            "entity_type": e.get("type", "concept"),
        })
    return out[:_MAX_CANDIDATES], skipped
