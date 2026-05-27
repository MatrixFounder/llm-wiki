"""`update-index` subcommand — add rows to `index.md`.

Adds a Source row + N Concept rows + M Entity rows to the three default
index sections. Dedup is case-insensitive on the slug + per-list-item
(not substring of the entire body — L-H3 fix). `_collect_names` is
imported from `_safety` (centralised in 015-01; shared with `append_log`).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from wiki_ingest._markdown import (
    _existing_lines,
    get_section_body,
    replace_section_body,
)
from wiki_ingest._safety import (
    _collect_names,
    _safe_inline,
    _safe_name,
    read_text,
    write_text,
)
from wiki_ingest._vault import INDEX_FILE, ensure_schema, load_asset

INDEX_SECTIONS = {
    "sources": "Sources",
    "concepts": "Concepts",
    "entities": "Entities",
}


def add_index_row(content: str, section_header_text: str, row: str, slug_key: str) -> str:
    """Add row under '## <section_header_text>' if not already present.

    Dedup is case-INSENSITIVE on `slug_key` and checks each LIST ITEM in turn
    (not a substring scan of the full body) — so a row whose Notes-section
    cousin happens to cite `[[foo]]` no longer blocks a legitimate
    Sources/Concepts row with `[[foo]]` as its target (L-H3).
    """
    body = get_section_body(content, section_header_text)
    if body is None:
        # append section at end of file
        return content.rstrip() + f"\n\n## {section_header_text}\n\n{row}\n"
    rows = _existing_lines(body)
    slug_key_lc = slug_key.lower()
    for r in rows:
        # consider a row a duplicate iff slug_key appears as a wiki-link
        # ANYWHERE in the row — but we look at LIST ITEMS, not the whole body.
        if slug_key_lc in r.lower():
            return content
    rows.append(row)
    return replace_section_body(content, section_header_text, "\n".join(rows))


def register(sub: argparse._SubParsersAction) -> None:
    """Attach the `update-index` subparser."""
    p = sub.add_parser("update-index", help="add/update rows in index.md")
    p.add_argument("vault")
    p.add_argument("--source-slug", required=True)
    p.add_argument("--source-title", required=True)
    p.add_argument("--source-date", required=True)
    p.add_argument("--summary", required=True)
    p.add_argument("--new-concepts",
                   help="comma-separated names (DEPRECATED for names containing commas — use --new-concept instead)")
    p.add_argument("--new-entities",
                   help="comma-separated names (DEPRECATED for names containing commas — use --new-entity instead)")
    p.add_argument("--new-concept", action="append", default=[],
                   help="one concept name; repeat the flag for each name (safe for names containing commas)")
    p.add_argument("--new-entity", action="append", default=[],
                   help="one entity name; repeat the flag for each name (safe for names containing commas)")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=execute)


def execute(args: argparse.Namespace) -> int:
    """Apply Source/Concept/Entity row additions to `index.md`."""
    vault = Path(args.vault).resolve()
    ensure_schema(vault)
    index = vault / INDEX_FILE
    content = read_text(index) or load_asset("index.template.md")

    safe_slug = _safe_name(args.source_slug, kind="source-slug")
    safe_title = _safe_inline(args.source_title, "source-title")
    safe_date = _safe_inline(args.source_date, "source-date")
    safe_summary = _safe_inline(args.summary, "summary")

    source_row = (f"- [[{safe_slug}]] — {safe_date} — "
                  f"{safe_title} — {safe_summary}")
    content = add_index_row(content, INDEX_SECTIONS["sources"], source_row,
                            slug_key=f"[[{safe_slug}]]")

    concept_names = _collect_names(args.new_concepts, args.new_concept)
    entity_names = _collect_names(args.new_entities, args.new_entity)

    # Validate each new concept/entity name is filesystem-safe before writing
    # it into the index — otherwise the index acquires links to pages that
    # `upsert-page` will later refuse to create.
    concept_names = [_safe_name(n, kind="new-concept") for n in concept_names]
    entity_names = [_safe_name(n, kind="new-entity") for n in entity_names]

    for name in concept_names:
        row = f"- [[{name}]] — introduced by [[{safe_slug}]]"
        content = add_index_row(content, INDEX_SECTIONS["concepts"], row,
                                slug_key=f"[[{name}]]")

    for name in entity_names:
        row = f"- [[{name}]] — introduced by [[{safe_slug}]]"
        content = add_index_row(content, INDEX_SECTIONS["entities"], row,
                                slug_key=f"[[{name}]]")

    write_text(index, content, args.dry_run)
    print(json.dumps({"index": str(index.relative_to(vault)), "updated": True}, indent=2))
    return 0
