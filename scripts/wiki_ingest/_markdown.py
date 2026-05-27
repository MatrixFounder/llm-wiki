"""F2 · Markdown engine for the wiki-ingest skill.

Deterministic, mask-once primitives for parsing + mutating Obsidian-flavour
markdown: fenced-code + inline-construct masking, section locators, body
extractors, wiki-link extraction (anchor-aware), and abbreviation-skipping
sentence segmentation. Currently uses only the stdlib `re` module; the
F2-may-import-F1 rule from the layered DAG is reserved for future
fatal-error paths (`die`) but is not exercised today.

Tested by `../tests/test__markdown.py`.
"""
from __future__ import annotations

import functools
import re


# ---------------------------------------------------------------- masking ---

def _mask_code_fences(text: str) -> str:
    """Replace the content of ``` fenced code blocks with spaces, preserving offsets.

    This lets section/header regexes operate on a 'logical' view of the document
    where markdown examples inside code fences don't trigger false header matches.
    Non-fence content is untouched.
    """
    out = []
    in_fence = False
    fence_marker = None
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if not in_fence:
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_fence = True
                fence_marker = stripped[:3]
                out.append(line)
            else:
                out.append(line)
        else:
            if stripped.startswith(fence_marker):
                in_fence = False
                fence_marker = None
                out.append(line)
            else:
                # Replace with spaces of equal length to preserve byte offsets,
                # keeping the trailing newline so line positions are stable.
                if line.endswith("\n"):
                    out.append(" " * (len(line) - 1) + "\n")
                else:
                    out.append(" " * len(line))
    return "".join(out)


# Inline-construct masking: removes content from regions where `[[link]]`
# patterns should NOT be treated as references — namely inline-code spans
# (single/double backticks) and HTML comments. Preserves offsets by
# substituting equal-length runs of spaces (newlines preserved).
_INLINE_CODE_RE = re.compile(r"`+[^`\n]*`+")
_HTML_COMMENT_INLINE_RE = re.compile(r"<!--.*?-->", re.S)


def _mask_inline_constructs(text: str) -> str:
    """Mask inline backticks and HTML comments in `text` (offset-preserving).

    Use AFTER `_mask_code_fences` for full wikilink-extraction safety —
    a `` `[[Foo]]` `` inline span or `<!-- [[Foo]] -->` HTML comment must
    not produce phantom dangling-link reports (L-H1).
    """
    def _blank(m):
        s = m.group(0)
        # Preserve newlines so line positions stay stable
        return "".join("\n" if c == "\n" else " " for c in s)
    text = _INLINE_CODE_RE.sub(_blank, text)
    text = _HTML_COMMENT_INLINE_RE.sub(_blank, text)
    return text


# --------------------------------------------------------------- sections ---

# Section body extends from the line after the header to (but not including)
# the next `## ` line OR EOF. Standalone `---` is NOT a boundary anymore —
# a user's Markdown horizontal rule inside a section is intentional content,
# and previously was silently stripped on rewrite (L-C3).
SECTION_BOUNDARY_RE = re.compile(r"^## ", re.M)

_H2_HEADER_RE = re.compile(r"^## (.+?)[ \t]*$", re.M)


def _ensure_masked(content: str, masked: str | None) -> str:
    return _mask_code_fences(content) if masked is None else masked


@functools.lru_cache(maxsize=128)
def _compile_section_header_re(header_text: str) -> "re.Pattern[str]":
    """Compile + cache the per-header `^## <header>[ \\t]*$` regex (P-M3).

    Previously rebuilt on every `find_section` / `find_all_sections` call;
    now memoised so batch rewrites of K sections pay the compile cost once.
    """
    return re.compile(rf"^## {re.escape(header_text)}[ \t]*$", re.M)


def find_section(content: str, header_text: str,
                 occurrence: int = 0,
                 masked: str | None = None) -> tuple[int, int, int] | None:
    """Locate a '## <header_text>' section, ignoring headers inside code fences.

    Returns (header_start, body_start, body_end). The body spans from the
    character after the header line up to (but not including) the next
    '## ' line OR EOF (positions are valid in the original content, since
    the masked view preserves offsets). Returns None if the requested
    `occurrence` (0-indexed) is not present.

    `masked` is an optional pre-computed `_mask_code_fences(content)` result —
    pass it from a caller loop to avoid re-masking the same document on every
    call (OVERLAP-3 perf fix: O(K²·L) → O(K·L) on pages with many sections).
    """
    masked = _ensure_masked(content, masked)
    matches = list(_compile_section_header_re(header_text).finditer(masked))
    if occurrence < 0 or occurrence >= len(matches):
        return None
    h = matches[occurrence]
    body_start = h.end()
    if body_start < len(masked) and masked[body_start] == "\n":
        body_start += 1
    rest = masked[body_start:]
    nxt = SECTION_BOUNDARY_RE.search(rest)
    body_end = body_start + (nxt.start() if nxt else len(rest))
    return h.start(), body_start, body_end


def find_all_sections(content: str, header_text: str,
                      masked: str | None = None) -> list[tuple[int, int, int]]:
    """Return positions for ALL occurrences of `## <header_text>`.

    Single-pass: masks once (or reuses caller-supplied `masked`), finds all
    header matches, then computes body extent for each in one sweep.
    """
    masked = _ensure_masked(content, masked)
    matches = list(_compile_section_header_re(header_text).finditer(masked))
    out: list[tuple[int, int, int]] = []
    for h in matches:
        body_start = h.end()
        if body_start < len(masked) and masked[body_start] == "\n":
            body_start += 1
        rest = masked[body_start:]
        nxt = SECTION_BOUNDARY_RE.search(rest)
        body_end = body_start + (nxt.start() if nxt else len(rest))
        out.append((h.start(), body_start, body_end))
    return out


def get_all_section_bodies(content: str, header_text: str,
                           masked: str | None = None) -> list[str]:
    """Return body text for every occurrence of a `## <header_text>` section."""
    return [content[body_start:body_end]
            for _, body_start, body_end in
            find_all_sections(content, header_text, masked=masked)]


def get_section_body(content: str, header_text: str,
                     masked: str | None = None) -> str | None:
    loc = find_section(content, header_text, masked=masked)
    if loc is None:
        return None
    _, body_start, body_end = loc
    return content[body_start:body_end]


def replace_section_body(content: str, header_text: str, new_body: str,
                          masked: str | None = None) -> str:
    """Replace the body of an existing section. Preserves surrounding whitespace.

    Empty body case is special-cased to avoid emitting `\\n\\n\\n` (triple
    blank line) between an empty section and the next `## ` header.

    Trailing newlines BEFORE the next `## ` header are preserved exactly —
    only newlines AT the body's own end are normalised (L-H2 fix: prior
    impl's blanket `.lstrip("\\n")` on content[body_end:] could collapse
    mandated blank lines between sections).

    `masked` is propagated to `find_section` (P-M3-015-02): batch rewrites
    of K sections in one page now pay the mask cost ONCE instead of K times.
    """
    loc = find_section(content, header_text, masked=masked)
    if loc is None:
        return content
    _, body_start, body_end = loc
    stripped = new_body.strip("\n")
    if stripped:
        # normalise: one leading + one trailing blank line around body
        normalised = "\n" + stripped + "\n\n"
    else:
        # empty body: just one blank line between the header and what follows
        normalised = "\n"
    # L-H2: preserve any extra blank lines that the caller had BEFORE the
    # next `## ` boundary by stripping at most one leading `\n` (which was
    # consumed by the normalised trailing `\n\n`). The prior `.lstrip("\n")`
    # devoured ALL leading newlines, collapsing intentional spacing.
    tail = content[body_end:]
    if tail.startswith("\n"):
        tail = tail[1:]
    return content[:body_start] + normalised + tail


def insert_section_before(content: str, anchor_header_text: str,
                          new_section_md: str) -> str:
    """Insert `new_section_md` immediately before the section with `anchor_header_text`.

    If the anchor section is not found, append at the end of the document
    (but before any trailing standalone '---' + footnote block).
    """
    anchor = re.search(rf"^## {re.escape(anchor_header_text)}\s*$", content, re.M)
    block = "\n" + new_section_md.strip("\n") + "\n\n"
    if anchor:
        return content[:anchor.start()] + block + content[anchor.start():]
    # fall back: insert before the first footnote definition or before a standalone --- + footnote
    fn = re.search(r"^\[\^[^\]]+\]: ", content, re.M)
    if fn:
        # walk back to skip any leading '---' separator
        cut = fn.start()
        pre = content[:cut].rstrip()
        if pre.endswith("---"):
            cut = pre.rfind("---")
            pre = content[:cut].rstrip()
        return pre + "\n\n" + new_section_md.strip("\n") + "\n\n" + content[cut:]
    return content.rstrip() + "\n\n" + new_section_md.strip("\n") + "\n"


# ----------------------------------------------------- list-item helpers ---

# Exact placeholder lines emitted by `render_stub_page` for empty sections.
# Keep this list short and literal — the previous broad pattern
# `^_Additional .*?_$` swallowed user-authored italic notes that happened
# to start with "Additional".
_PLACEHOLDER_LINES = frozenset({
    "_Definition pending — first ingest did not extract a one-sentence summary._",
})


def _is_placeholder_line(line: str) -> bool:
    return line.strip() in _PLACEHOLDER_LINES


def _existing_lines(body: str) -> list[str]:
    """Return existing non-placeholder, non-blank list items in a section body.

    Multi-line list items (lines indented under a `- ` or `* ` parent) are
    STITCHED back into one entry preserving original indentation, so a
    markdown renderer still folds the continuation. Pure indented
    continuations without a `-` parent are kept verbatim.

    **Blockquote handling** (L-L3 fix): a `> ` line is treated as a
    continuation of the most recent list item if one is open, OR as a
    standalone-block start if not. Previously `> ` was treated as a
    top-level "list marker", which split contradiction blocks into
    re-ordered fragments on upsert.
    """
    out: list[str] = []
    current: list[str] | None = None
    in_blockquote = False
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            # blank line: terminate any open multi-line item / blockquote
            if current is not None:
                out.append("\n".join(current))
                current = None
            in_blockquote = False
            continue
        if _is_placeholder_line(line):
            if current is not None:
                out.append("\n".join(current))
                current = None
            in_blockquote = False
            continue
        indent = len(line) - len(line.lstrip(" \t"))
        lstripped = line.lstrip()
        is_blockquote = lstripped.startswith("> ") or lstripped == ">"
        is_list_marker = lstripped.startswith(("- ", "* "))

        # L-L3: contiguous `> ` lines stitch into one blockquote entry so
        # Contradiction blocks (which use `> ` lines) survive upsert intact.
        if is_blockquote:
            if in_blockquote and current is not None:
                current.append(line.rstrip())
            else:
                if current is not None:
                    out.append("\n".join(current))
                current = [line.rstrip()]
                in_blockquote = True
            continue

        if is_list_marker and indent == 0:
            # new top-level list item
            if current is not None:
                out.append("\n".join(current))
            current = [line.rstrip()]
            in_blockquote = False
        elif current is not None and indent > 0:
            # continuation line under the open item
            current.append(line.rstrip())
        else:
            # standalone line (e.g. paragraph row), no continuation tracking
            if current is not None:
                out.append("\n".join(current))
                current = None
            in_blockquote = False
            out.append(stripped)
    if current is not None:
        out.append("\n".join(current))
    return out


# --------------------------------------------------------------- wikilinks --

WIKILINK_RE = re.compile(r"(?<!!)\[\[([^\]|#]+?)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
# Anchor-aware variant: captures (target, anchor-or-None) so callers can
# surface `[[Foo#API]]` instead of bare `Foo` in dangling-link reports (L-L4).
WIKILINK_ANCHOR_RE = re.compile(
    r"(?<!!)\[\[([^\]|#]+?)(#[^\]|]+)?(?:\|[^\]]+)?\]\]")
WORD_RE = re.compile(r"[A-Za-z][\w-]*")


def _extract_wikilinks_with_anchors(
    body: str, masked: str | None = None,
) -> dict[str, set[str]]:
    """Return `{target: {anchor_or_empty, ...}}` for every wiki-link.

    Ignores links inside fenced code blocks, inline-code spans
    (`` `[[X]]` ``), and HTML comments (`<!-- [[X]] -->`) — wiki-links shown
    in markdown examples are not real references (L-H1).

    Used by `cmd_lint` to surface specific dangling anchors (`Foo#API`)
    instead of bare targets (L-L4). The empty-string anchor key represents
    an anchor-less reference, distinct from `#API` etc.

    `masked` is an optional pre-computed fully-masked view (fences + inline
    constructs); pass it from a caller loop to avoid double-masking on every
    call (used by `cmd_lint`'s OVERLAP-2 cached-enrichment path).
    """
    if masked is None:
        masked = _mask_inline_constructs(_mask_code_fences(body))
    out: dict[str, set[str]] = {}
    for m in WIKILINK_ANCHOR_RE.finditer(masked):
        target = m.group(1).strip()
        if not target:
            continue
        anchor = (m.group(2) or "").strip()  # includes leading "#"
        out.setdefault(target, set()).add(anchor)
    return out


# --------------------------------------------------- sentence segmentation --

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_TLDR_BOLD_RE = re.compile(r"\*\*TL;DR\*\*:?\s*", re.I)

# Common abbreviations that end with "." but do NOT terminate a sentence —
# prevents one-line summaries from truncating at "Dr.", "Mr.", etc. (L-M4).
_ABBREV_RE = re.compile(
    r"\b(?:Dr|Mr|Mrs|Ms|Sr|Jr|St|Prof|Inc|Ltd|Co|Corp|"
    r"vs|etc|i\.e|e\.g|cf|al|approx)\.\s*$",
    re.IGNORECASE,
)


def _first_sentence(text: str) -> str:
    # Hard cap so a hostile single-line file (e.g. via a symlinked target,
    # though those are now skipped) can't allocate gigabytes here (S-M3).
    if len(text) > 16384:
        text = text[:16384]
    text = text.strip()
    if not text:
        return ""
    # strip leading blockquote markers, bold-TL;DR labels, and inline comments
    text = _HTML_COMMENT_RE.sub("", text).strip()
    while text.startswith(">"):
        text = text.lstrip("> ").strip()
    text = _TLDR_BOLD_RE.sub("", text).strip()
    # skip any leading markdown header lines (## Executive Summary etc.)
    while text.startswith("#"):
        nl = text.find("\n")
        if nl == -1:
            return ""
        text = text[nl + 1:].lstrip("> ").strip()
        text = _HTML_COMMENT_RE.sub("", text).strip()
        text = _TLDR_BOLD_RE.sub("", text).strip()
    # Iterate sentence-end candidates, skipping abbreviation false-positives.
    sentence_end_re = re.compile(r"[.!?](\s|$)|\n\n")
    pos = 0
    while pos < len(text):
        m = sentence_end_re.search(text, pos)
        if not m:
            return text[:200].rstrip().replace("\n", " ")
        cut = m.start() + 1
        candidate = text[:cut]
        # If the candidate ends with a known abbreviation, advance past it
        # and keep scanning.
        if _ABBREV_RE.search(candidate):
            pos = m.end()
            continue
        return candidate.rstrip().replace("\n", " ")
    return text[:200].rstrip().replace("\n", " ")
