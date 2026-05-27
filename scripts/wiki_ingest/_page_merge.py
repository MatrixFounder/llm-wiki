"""F2 · Additive-merge primitives for concept/entity page bodies.

Extracted from `commands/upsert_page.py` in TASK 016 bead 016-01 so that
both `commands/upsert_page.py` and the new `commands/promote.py` can
reuse the primitives without violating the architecture import-graph
invariant (no command may import another command).

Four functions, byte-identical to the originals:
- `upsert_source_row(content, slug, title, date)` — dedupes by `[[slug]]`.
- `append_fact(content, fact, slug)` — dedupes by full line.
- `append_contradiction(content, existing, new_fact, slug)` — dedupes by
  the "New claim from [[slug]]" line.
- `upsert_footnote(content, slug, title)` — dedupes by full line OR key.

**Mask-once optimisation (TASK 016 VDD-multi iter-1 Perf-H1 fix)**: every
primitive accepts an optional `masked=` parameter and forwards it to the
underlying `_markdown` helpers. Callers (notably `commands/promote.py`'s
fold loop) can compute `_mask_code_fences(content)` ONCE per primitive
call and avoid the O(L) re-mask cost that TASK 015's P-M3 optimisation
originally bought. After a primitive *mutates* the content (length
changes), the caller MUST recompute `masked` before the next call —
the parameter is a per-call cache, not a persistent view.

Imports F2 (`_markdown`) only. Tested by `../tests/test__page_merge.py`.
"""
from __future__ import annotations

import re

from wiki_ingest._markdown import (
    _existing_lines,
    get_section_body,
    insert_section_before,
    replace_section_body,
)


def upsert_source_row(content: str, source_slug: str, source_title: str,
                      source_date: str,
                      masked: str | None = None) -> str:
    row = f"- [[{source_slug}]] — {source_date} — {source_title}"
    body = get_section_body(content, "Sources mentioning this", masked=masked)
    if body is None:
        new_section = f"## Sources mentioning this\n\n{row}\n"
        return insert_section_before(content, "Footnotes", new_section)
    rows = _existing_lines(body)
    if any(f"[[{source_slug}]]" in r for r in rows):
        return content
    rows.append(row)
    return replace_section_body(content, "Sources mentioning this",
                                "\n".join(rows), masked=masked)


def append_fact(content: str, fact: str, source_slug: str,
                masked: str | None = None) -> str:
    line = f"- {fact.strip()} [^src-{source_slug}]"
    body = get_section_body(content, "Facts", masked=masked)
    if body is None:
        new_section = f"## Facts\n\n{line}\n"
        for anchor in ("Contradictions", "Sources mentioning this", "Footnotes"):
            if get_section_body(content, anchor, masked=masked) is not None:
                return insert_section_before(content, anchor, new_section)
        return content.rstrip() + "\n\n" + new_section
    rows = _existing_lines(body)
    if line in rows:
        return content
    rows.append(line)
    return replace_section_body(content, "Facts", "\n".join(rows),
                                masked=masked)


def append_contradiction(content: str, existing_claim: str, new_fact: str,
                         source_slug: str,
                         masked: str | None = None) -> str:
    block = (
        "> ⚠️ **Contradiction flagged** — operator review needed.\n"
        f"> - Existing claim: {existing_claim.strip()}\n"
        f"> - New claim from [[{source_slug}]]: "
        f"{new_fact.strip()} [^src-{source_slug}]\n"
    )
    body = get_section_body(content, "Contradictions", masked=masked)
    if body is None:
        new_section = f"## Contradictions\n\n{block}"
        for anchor in ("Sources mentioning this", "Footnotes"):
            if get_section_body(content, anchor, masked=masked) is not None:
                return insert_section_before(content, anchor, new_section)
        return content.rstrip() + "\n\n" + new_section
    new_claim_line = (f"> - New claim from [[{source_slug}]]: "
                      f"{new_fact.strip()} [^src-{source_slug}]")
    if new_claim_line in body:
        return content
    existing = body.strip("\n")
    return replace_section_body(content, "Contradictions",
                                existing + "\n\n" + block, masked=masked)


def upsert_footnote(content: str, source_slug: str, source_title: str,
                    masked: str | None = None) -> str:
    fn_line = f"[^src-{source_slug}]: [[{source_slug}]] — {source_title}"
    if fn_line in content:
        return content
    if re.search(rf"^\[\^src-{re.escape(source_slug)}\]: ", content, re.M):
        return content
    body = get_section_body(content, "Footnotes", masked=masked)
    if body is None:
        return content.rstrip() + "\n\n## Footnotes\n\n" + fn_line + "\n"
    rows = _existing_lines(body)
    rows.append(fn_line)
    return replace_section_body(content, "Footnotes", "\n".join(rows),
                                masked=masked)
