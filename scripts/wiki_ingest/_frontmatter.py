"""F2 · YAML frontmatter parser + structural splice for wiki-ingest.

Hand-rolled YAML parser tuned to the subset wiki-ingest writes: flat
scalars, indented `- value` lists, `- subkey: value` list-of-dicts,
flow-style `[a, "b, c"]` lists. Single-pass, line-anchored delimiter
detection (defeats `\\n---` substrings inside block scalars — L-C2).
`_strip_frontmatter_fast` returns the body without paying the parse
cost (P-M1). `_splice_frontmatter_fields` rebuilds chosen list fields
in-place for the L-H5 / P-M2 normalisation path.

Currently uses only stdlib (`json`, `re`); the F2-may-import-F1 rule
from the layered DAG is reserved for future fatal-error paths.

Tested by `../tests/test__frontmatter.py`.
"""
from __future__ import annotations

import json
import re


# Module-level helpers — compiled once per process (P-H5).
_FM_CLOSER_RE = re.compile(r"^---[ \t]*$", re.M)
_FM_KEY_RE = re.compile(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$")


def _strip_quotes(s: str) -> str:
    """Strip matched surrounding quotes; pass through unbalanced or unquoted.

    Mismatched quotes (e.g. `'foo"` — single-open, double-close) are NOT
    stripped — returned as-is, preserving operator-visible asymmetry
    instead of silently corrupting the value (S-L3 fix-closed semantics).
    Only EXACTLY-matched pairs of `'` or `"` at both endpoints reduce.
    """
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        return s[1:-1]
    return s


def _parse_flow_list(value: str) -> list[str]:
    """Parse YAML flow-style list: `[a, "b, c", d]` → ['a', 'b, c', 'd']."""
    inner = value[1:-1]
    items: list[str] = []
    cur: list[str] = []
    in_q: str | None = None
    for ch in inner:
        if in_q:
            if ch == in_q:
                in_q = None
            else:
                cur.append(ch)
        elif ch in ("'", '"'):
            in_q = ch
        elif ch == ",":
            items.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        items.append("".join(cur).strip())
    return [_strip_quotes(it) for it in items if it]


def _strip_trailing_comment(v: str) -> str:
    """Strip ` # comment` suffix from a YAML scalar value (respects quotes)."""
    in_q = None
    for i, ch in enumerate(v):
        if in_q:
            if ch == in_q:
                in_q = None
        elif ch in ("'", '"'):
            in_q = ch
        elif ch == "#" and (i == 0 or v[i - 1] in (" ", "\t")):
            return v[:i].rstrip()
    return v.rstrip()


def _strip_frontmatter_fast(content: str) -> str:
    """Return body without parsing the frontmatter dict.

    O(1) extra work after locating the closing `---` line — used by
    `cmd_find` when `--kinds` is not set, so we score body content alone
    without paying the hand-rolled YAML parse (P-M1). Mirrors the
    delimiter logic of `split_frontmatter` so behaviour stays consistent.
    """
    if content.startswith("﻿"):
        content = content[1:]
    if not content.startswith("---"):
        return content
    first_nl = content.find("\n")
    if first_nl == -1 or content[:first_nl].rstrip() != "---":
        return content
    closer = _FM_CLOSER_RE.search(content, first_nl + 1)
    if closer is None:
        return content
    body_start = closer.end()
    if body_start < len(content) and content[body_start] == "\n":
        body_start += 1
    return content[body_start:]


def split_frontmatter(content: str,
                      warnings: list[str] | None = None) -> tuple[dict, str]:
    """YAML frontmatter parser with limited nested-mapping support.

    Handles:
    - flat `key: value`
    - `key:` followed by indented `- value` items (list of strings)
    - `key:` followed by `- subkey: value` + indented continuations (list of dicts)
    - flow-style lists: `key: [a, b, "c, d"]`
    - quoted strings (single or double)
    - comment lines `#` (skipped)

    Does NOT handle: multi-line scalars (`|`, `>`), deeply nested mappings
    beyond `list-item-dict`, anchors, references.

    If `warnings` is provided, malformed top-level lines are appended to it
    (operator-visible) rather than silently skipped — see L-M5.
    """
    # Strip a leading UTF-8 BOM that some Windows editors prepend; otherwise
    # the `---` frontmatter delimiter check would silently fail.
    if content.startswith("﻿"):
        content = content[1:]
    if not content.startswith("---"):
        return {}, content
    # Require a leading delimiter that's on its own line (BOM-stripped content
    # may begin with `---\n` or `---` at EOF).
    first_nl = content.find("\n")
    if first_nl == -1 or content[:first_nl].rstrip() != "---":
        return {}, content
    # Find the FIRST closer that's on its own line ("---" or "---   ").
    # Search from after the opening line — line-anchored to avoid catching
    # `\n---` substrings inside YAML block scalars or quoted values (L-C2).
    closer = _FM_CLOSER_RE.search(content, first_nl + 1)
    if closer is None:
        return {}, content
    fm_raw = content[first_nl + 1: closer.start()].strip("\n")
    body_start = closer.end()
    if body_start < len(content) and content[body_start] == "\n":
        body_start += 1
    body = content[body_start:]
    fm: dict = {}

    current_key: str | None = None       # last top-level key with a list value
    list_item_dict: dict | None = None   # the dict we're currently filling inside a list
    list_item_indent: int = -1           # indent of the '- ' marker for current list

    key_re = _FM_KEY_RE  # module-cached for cheap reuse (P-H5)

    for line in fm_raw.splitlines():
        if not line.strip():
            continue
        # skip YAML comments
        if line.lstrip().startswith("#"):
            continue

        indent = len(line) - len(line.lstrip(" \t"))
        stripped = line.lstrip(" \t").rstrip()

        # Zero-indent list item: attach to most recent open list-valued key.
        # PyYAML's default block-style output for `key:\n- a\n- b` produces
        # zero-indent list items, which is valid YAML — must be supported.
        if indent == 0 and stripped.startswith("- ") and current_key is not None \
                and isinstance(fm.get(current_key), list):
            item_text = stripped[2:].strip()
            inline = key_re.match(item_text)
            if inline:
                sub_key = inline.group(1)
                sub_val = _strip_trailing_comment(inline.group(2).strip())
                new_dict: dict = {sub_key: _strip_quotes(sub_val) if sub_val else ""}
                fm[current_key].append(new_dict)
                list_item_dict = new_dict
                list_item_indent = indent
            else:
                fm[current_key].append(_strip_quotes(item_text))
                list_item_dict = None
                list_item_indent = -1
            continue

        # CASE A: top-level key:value (indent 0)
        if indent == 0:
            m = key_re.match(stripped)
            if m:
                key, value = m.group(1), _strip_trailing_comment(m.group(2).strip())
                current_key = key
                list_item_dict = None
                list_item_indent = -1
                if value == "":
                    fm[key] = []   # list to be filled by subsequent indented '- ...'
                elif value.startswith("[") and value.endswith("]"):
                    fm[key] = _parse_flow_list(value)
                else:
                    fm[key] = _strip_quotes(value)
                continue
            # unknown top-level construct — skip, but record so the operator
            # is not silently surprised by missing concept lists (L-M5).
            if warnings is not None:
                warnings.append(f"frontmatter: dropped malformed top-level "
                                f"line {stripped[:80]!r}")
            continue

        # CASE B: list item `- ...` at indent > 0
        if stripped.startswith("- ") and current_key is not None:
            item_text = stripped[2:].strip()
            fm.setdefault(current_key, [])
            if not isinstance(fm[current_key], list):
                # key was assigned a scalar earlier; do not corrupt
                continue
            # Inline mapping start: `- key: value`
            inline = key_re.match(item_text)
            if inline:
                sub_key = inline.group(1)
                sub_val = _strip_trailing_comment(inline.group(2).strip())
                new_dict: dict = {sub_key: _strip_quotes(sub_val) if sub_val else ""}
                fm[current_key].append(new_dict)
                list_item_dict = new_dict
                list_item_indent = indent
            else:
                fm[current_key].append(_strip_quotes(item_text))
                list_item_dict = None
                list_item_indent = -1
            continue

        # CASE C: indented `key: value` continuation of current list-item dict
        if list_item_dict is not None and indent > list_item_indent:
            m = key_re.match(stripped)
            if m:
                k = m.group(1)
                v = _strip_trailing_comment(m.group(2).strip())
                list_item_dict[k] = _strip_quotes(v) if v else ""
                continue

        # If we drop below list-item indent, exit the list-item-dict context
        if list_item_dict is not None and indent <= list_item_indent:
            list_item_dict = None
            list_item_indent = -1
            # re-evaluate this line as a non-list-item (fall through)
            if stripped.startswith("- ") and current_key is not None:
                # rare case: shouldn't happen if logic is right, but be safe
                continue

    return fm, body


def _serialize_yaml_list_field(key: str, values: list) -> str:
    """Render a list-valued frontmatter field as block-style YAML.

    Supports two shapes (TASK 016 bead 016-02):

    1. `list[str]` (TASK 015 baseline):
           key:
             - value1
             - "value with: colon"

    2. `list[dict]` (`promoted_from: [{course, date}, ...]`):
           key:
             - sub1: "value1"
               sub2: 2026-05-26
             - sub1: "value2"
               sub2: 2026-05-26

    Strings containing YAML metacharacters are double-quoted with backslash
    escaping. Inside a list-of-dicts entry, keys are emitted in
    insertion order (Python 3.7+ `dict` guarantee). Used by
    `_splice_frontmatter_fields`.
    """
    def _needs_quoting(s: str) -> bool:
        if not s:
            return True
        if s[0] in "&*!@`%>|#?,[]{}\"'-":
            return True
        if any(ch in s for ch in (":", "#")):
            return True
        if s.strip() != s:
            return True
        return False

    def _scalar(v) -> str:
        if not isinstance(v, str):
            return json.dumps(v, ensure_ascii=False)
        if _needs_quoting(v):
            return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
        return v

    lines = [f"{key}:"]
    for v in values:
        if isinstance(v, dict):
            # `- subkey: value` for the first key; indented `subkey: value`
            # for the rest (matches what `split_frontmatter` round-trips).
            keys = list(v.keys())
            if not keys:
                lines.append("  - {}")
                continue
            for idx, sub in enumerate(keys):
                prefix = "  - " if idx == 0 else "    "
                lines.append(f"{prefix}{sub}: {_scalar(v[sub])}")
        else:
            lines.append(f"  - {_scalar(v)}")
    return "\n".join(lines)


def _splice_frontmatter_fields(text: str, fields: list[str], fm: dict) -> str:
    """Rebuild the listed list-valued frontmatter fields in-place.

    Locates each `field:` block (the key line + all of its indented `- item`
    continuations) inside the frontmatter region and replaces it with a freshly
    serialized block from `fm[field]`. Only the targeted fields are touched —
    every other line in the document (including non-affected frontmatter,
    body prose, code blocks) is byte-identical to the input.

    **Replace-only semantics**: if a requested field is NOT present in the
    frontmatter, the splice is a no-op for that field (no insertion). Callers
    that need to add a brand-new key must add the key line first (e.g. by
    re-emitting the entire frontmatter). Tested by
    `test__frontmatter.test_field_not_present_is_noop`.
    """
    if not text.startswith("---"):
        return text
    first_nl = text.find("\n")
    if first_nl == -1 or text[:first_nl].rstrip() != "---":
        return text
    closer = _FM_CLOSER_RE.search(text, first_nl + 1)
    if closer is None:
        return text
    fm_start = first_nl + 1
    fm_end = closer.start()
    fm_region = text[fm_start:fm_end]
    body_tail = text[fm_end:]

    lines = fm_region.split("\n")
    out_lines: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:", line)
        if m and m.group(1) in fields:
            field_name = m.group(1)
            # consume this key line + all subsequent indented or '- '-prefix lines
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if nxt.strip() == "":
                    i += 1
                    continue
                if nxt.startswith(" ") or nxt.startswith("\t") or nxt.startswith("- "):
                    i += 1
                    continue
                break
            # Removal semantics (TASK 016 bead 016-02): if the new value is
            # explicitly None, OMIT the key entirely. Used by `demote` to
            # strip `promoted_from:`.
            new_value = fm.get(field_name)
            if new_value is None:
                continue  # consume the block, emit nothing
            # emit fresh block (list[str] or list[dict])
            out_lines.append(_serialize_yaml_list_field(field_name, new_value))
            continue
        out_lines.append(line)
        i += 1

    new_fm_region = "\n".join(out_lines)
    # Ensure exactly one trailing newline before the closing `---` line so
    # that a rebuilt list block doesn't collide with the closer (e.g.
    # `…- Normal Name---` instead of the intended `…- Normal Name\n---`).
    if not new_fm_region.endswith("\n"):
        new_fm_region += "\n"
    return text[:fm_start] + new_fm_region + body_tail
