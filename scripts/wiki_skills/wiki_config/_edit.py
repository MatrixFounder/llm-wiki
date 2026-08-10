"""TASK 058 — the ruamel "sandwich": comment-preserving sync.yaml edits whose
safety comes from the EXISTING hardened stack, never from ruamel.

The ONLY module in the repo importing ruamel. Contract for every write
(doctor fix / set / unset / init --merge / serve form save):

  1. **Gate BEFORE** — the input text runs the loader's own primitives from a
     string: size cap, `_NoAliasSafeLoader` (anchor/alias ban — ruamel never
     sees unvetted text), mapping check, and (when the file is currently
     schema-clean) the strict schema. A fix whose whole purpose is to repair a
     schema violation gates stages 0-2 only (`require_schema_before=False`).
  2. Edit via ruamel round-trip (comments + key order + quotes preserved).
  3. **Gate AFTER** — the rendered text re-runs the FULL hardened gate, and the
     parsed result must equal the PLANNED dict (the same edits applied to the
     plain-dict parse with plain-Python semantics) EXACTLY; for non-destructive
     edits every original comment line must survive. ANY verification failure
     raises `EditDowngrade` — the caller reports manual, nothing is written.

Callers own TOCTOU hashing, backups and the atomic write; this module is pure
text → text.
"""

from __future__ import annotations

import difflib
import io
from collections import Counter
from dataclasses import dataclass
from typing import Any

import yaml
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from scripts.wiki_index.sync_config import (
    WIKI_SYNC_CONFIG_MAX_BYTES,
    SyncConfigError,
    _NoAliasSafeLoader,
    _validate,
)


class EditDowngrade(Exception):
    """A planned edit could not be applied+verified — the caller must degrade
    the fix to MANUAL and write nothing. `detail` is value-free."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True)
class PointerEdit:
    """One mechanical edit addressed by JSON pointer.

    op ∈ {set, unset, rename-key, dedupe-list}. `set` creates missing
    intermediate mappings, and a `set` of a LIST over a list reconciles it
    element-wise (`_reconcile_seq`) rather than replacing it, because the web
    editor saves an array field whole and a replaced sequence loses every
    comment between its items; `rename-key` moves value+position+attached
    comments; `dedupe-list` keeps first occurrences. `destructive` ops (unset,
    rename-key of commented nodes) exempt the comment-survival check wholesale —
    the pre-write backup is the record. A list `set` does NOT: it forgives
    exactly the lines that left with a removed item, so one removed entry cannot
    disarm the check for the other edits saved in the same batch."""

    op: str
    pointer: str
    value: Any = None
    new_key: str | None = None


def parse_text_no_schema(text: str) -> dict[str, Any]:
    """Stages 0-2 of the loader gate, from a string: size cap + anchor-ban
    parse + mapping check. Raises `SyncConfigError` (same codes/reasons)."""
    if len(text.encode("utf-8")) > WIKI_SYNC_CONFIG_MAX_BYTES:
        raise SyncConfigError(
            "INVALID_SYNC_CONFIG", "config exceeds the 256 KiB cap", reason="SIZE_CAP")
    try:
        raw = yaml.load(text, Loader=_NoAliasSafeLoader)  # noqa: S506 (hardened loader)
    except SyncConfigError:
        raise
    except (yaml.YAMLError, RecursionError, ValueError) as exc:
        raise SyncConfigError(
            "INVALID_SYNC_CONFIG", "config is not parseable", reason="PARSE") from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise SyncConfigError(
            "INVALID_SYNC_CONFIG", "config must be a YAML mapping", reason="NOT_MAPPING")
    return raw


def gate_text(text: str) -> dict[str, Any]:
    """The FULL hardened gate from a string (stages 0-2 + strict schema)."""
    raw = parse_text_no_schema(text)
    _validate(raw)
    return raw


# --------------------------------------------------------------------------- #
# plain-dict edit semantics (the verification oracle)
# --------------------------------------------------------------------------- #


def _pointer_parts(pointer: str) -> list[str]:
    return [p for p in pointer.split("/") if p]


def apply_edits_plain(raw: dict[str, Any], edits: list[PointerEdit]) -> dict[str, Any]:
    """The PLANNED result: the same edits with plain-Python semantics. This is
    what the ruamel render must parse back to, exactly."""
    import copy

    planned = copy.deepcopy(raw)
    for edit in edits:
        parts = _pointer_parts(edit.pointer)
        if not parts:
            raise EditDowngrade("empty pointer")
        parent: dict[str, Any] = planned
        for part in parts[:-1]:
            nxt = parent.get(part)
            if nxt is None and edit.op == "set":
                nxt = parent[part] = {}
            if not isinstance(nxt, dict):
                raise EditDowngrade("pointer traverses a non-mapping")
            parent = nxt
        leaf = parts[-1]
        if edit.op == "set":
            parent[leaf] = edit.value
        elif edit.op == "unset":
            if leaf not in parent:
                raise EditDowngrade("pointer not present")
            del parent[leaf]
        elif edit.op == "rename-key":
            if leaf not in parent or not edit.new_key:
                raise EditDowngrade("rename source missing")
            if edit.new_key in parent:
                raise EditDowngrade("rename target already exists")
            items = [(edit.new_key if k == leaf else k, v) for k, v in parent.items()]
            parent.clear()
            parent.update(items)
        elif edit.op == "dedupe-list":
            seq = parent.get(leaf)
            if not isinstance(seq, list):
                raise EditDowngrade("dedupe target is not a list")
            seen: set[str] = set()
            kept = []
            for item in seq:
                if str(item) not in seen:
                    seen.add(str(item))
                    kept.append(item)
            parent[leaf] = kept
        else:
            raise EditDowngrade("unknown edit op")
    return planned


# --------------------------------------------------------------------------- #
# ruamel application
# --------------------------------------------------------------------------- #


def _rt() -> YAML:
    rt = YAML(typ="rt")
    rt.preserve_quotes = True
    rt.width = 4096  # never re-wrap operator lines
    return rt


def _plain(node: Any) -> Any:
    """A ruamel node reduced to its plain-Python value, so an item's identity
    does not depend on how it happened to be quoted."""
    if isinstance(node, str):  # incl. ruamel's quoted-scalar subclasses
        return str(node)
    if isinstance(node, dict):
        return {str(k): _plain(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_plain(v) for v in node]
    return node


def _seq_key(item: Any) -> str:
    """Identity of a list element for the element-wise diff. `repr` keeps the
    type distinct, so the string "1" never matches the integer 1."""
    return repr(_plain(item))


def _token_comment_lines(entry: Any) -> list[str]:
    """The comment lines carried by one ruamel `ca.items` entry, in the shape
    `_comment_lines` produces — so the survival check can subtract exactly the
    lines that left with a removed item, and nothing else."""
    lines: list[str] = []
    for slot in entry or []:
        for token in slot if isinstance(slot, list) else [slot]:
            value = getattr(token, "value", None)
            if isinstance(value, str):
                lines += [line.strip() for line in value.splitlines()
                          if line.lstrip().startswith("#")]
    return lines


def _drop_seq_item(seq: Any, index: int) -> list[str]:
    """Delete one item, keeping the comment block that annotates the item BELOW
    it. ruamel keys a comment by the item it FOLLOWS, so the block preceding
    item N is stored on N-1: dropping N must discard the block on N-1 (it
    describes the item being removed) and re-key the block on N (it describes
    the survivor). Without the re-key ruamel keeps N-1 and discards N — the
    surviving item inherits a comment about a line that is no longer there.

    Returns the lines discarded WITH the item, which is the only comment loss
    this edit is allowed. Index 0 has no predecessor to re-key onto, so ruamel
    drops item 1's leading block and this function cannot report it — the
    survival check then sees an unaccounted loss and refuses the edit, which is
    the honest outcome for a case the mechanism cannot do losslessly."""
    gone: list[str] = []
    ca_items = getattr(getattr(seq, "ca", None), "items", None)
    if isinstance(ca_items, dict) and index >= 1:
        gone = _token_comment_lines(ca_items.pop(index - 1, None))
        if index in ca_items:
            ca_items[index - 1] = ca_items.pop(index)
    del seq[index]
    return gone


def _insert_seq_item(seq: Any, index: int, item: Any) -> None:
    """Insert one item, keeping the comment block above the item it annotates.
    That block is stored on `index - 1` and ruamel shifts only the keys at or
    after `index`, so it would stay put and end up describing the NEW item."""
    seq.insert(index, item)
    ca_items = getattr(getattr(seq, "ca", None), "items", None)
    if isinstance(ca_items, dict) and index >= 1:
        if index - 1 in ca_items and index not in ca_items:
            ca_items[index] = ca_items.pop(index - 1)


def _reconcile_seq(seq: Any, wanted: list[Any]) -> list[str]:
    """Turn `seq` into `wanted` ELEMENT-WISE — an item present on both sides is
    left untouched, so the comment block attached to it survives. Assigning the
    list instead renders a fresh sequence and every interleaved comment is gone.
    Returns the comment lines that left with a removed item."""
    matcher = difflib.SequenceMatcher(
        a=[_seq_key(item) for item in seq],
        b=[_seq_key(item) for item in wanted],
        autojunk=False,
    )
    removed: list[str] = []
    # reversed: an opcode's indices address the sequence as it was BEFORE any
    # later opcode was applied, so editing from the tail keeps them valid.
    for tag, i1, i2, j1, j2 in reversed(matcher.get_opcodes()):
        if tag == "equal":
            continue
        # An item REWRITTEN in place — the typo fix, the commonest edit of all —
        # is assigned over, never delete+inserted. Both keep the value, but only
        # this keeps the comment describing the entry the operator was editing.
        if tag == "replace" and (i2 - i1) == (j2 - j1):
            for offset, item in enumerate(wanted[j1:j2]):
                seq[i1 + offset] = item
            continue
        if tag in ("delete", "replace"):
            for index in range(i2 - 1, i1 - 1, -1):
                removed += _drop_seq_item(seq, index)
        if tag in ("insert", "replace"):
            for offset, item in enumerate(wanted[j1:j2]):
                _insert_seq_item(seq, i1 + offset, item)
    return removed


# A whole-list `set` diffs the two sides, which costs O(n·m) in the degenerate
# case (thousands of IDENTICAL items). Measured inside the 256 KiB cap: 2000
# items 0.32s, 20000 items 23s — a visible hang of the single-threaded `serve`.
# Past the guard the edit falls back to plain assignment, so a commented list
# that large is REFUSED by the survival check rather than silently reflowed.
_MAX_RECONCILE_ITEMS = 2000


def _apply_edits_ruamel(data: Any, edits: list[PointerEdit]) -> list[str]:
    """Apply the edits to the round-trip tree. Returns the comment lines that
    left with a REMOVED list item — the only loss `rewrite_text`'s survival
    check forgives, because they describe a line that is gone."""
    dropped: list[str] = []
    for edit in edits:
        parts = _pointer_parts(edit.pointer)
        parent = data
        for part in parts[:-1]:
            nxt = parent.get(part) if hasattr(parent, "get") else None
            if nxt is None and edit.op == "set":
                nxt = CommentedMap()
                parent[part] = nxt
            if nxt is None or not hasattr(nxt, "get"):
                raise EditDowngrade("pointer traverses a non-mapping")
            parent = nxt
        leaf = parts[-1]
        if edit.op == "set":
            current = parent.get(leaf)
            if (isinstance(edit.value, list) and isinstance(current, list)
                    and max(len(current), len(edit.value))
                    <= _MAX_RECONCILE_ITEMS):
                dropped += _reconcile_seq(current, edit.value)
            else:
                parent[leaf] = edit.value
        elif edit.op == "unset":
            if leaf not in parent:
                raise EditDowngrade("pointer not present")
            del parent[leaf]
        elif edit.op == "rename-key":
            if leaf not in parent or not edit.new_key:
                raise EditDowngrade("rename source missing")
            if edit.new_key in parent:
                raise EditDowngrade("rename target already exists")
            keys = list(parent.keys())
            index = keys.index(leaf)
            value = parent.pop(leaf)
            parent.insert(index, edit.new_key, value)
            ca_items = getattr(getattr(parent, "ca", None), "items", None)
            if isinstance(ca_items, dict) and leaf in ca_items:
                ca_items[edit.new_key] = ca_items.pop(leaf)
        elif edit.op == "dedupe-list":
            seq = parent.get(leaf)
            if seq is None:
                raise EditDowngrade("dedupe target is not a list")
            seen: set[str] = set()
            drop: list[int] = []
            for i, item in enumerate(seq):
                key = str(item)
                if key in seen:
                    drop.append(i)
                seen.add(key)
            for i in reversed(drop):
                del seq[i]
        else:
            raise EditDowngrade("unknown edit op")
    return dropped


def _comment_lines(text: str) -> Counter[str]:
    return Counter(
        line.strip() for line in text.splitlines() if line.lstrip().startswith("#")
    )


def rewrite_text(
    text: str,
    edits: list[PointerEdit],
    *,
    require_schema_before: bool = True,
) -> str:
    """The full sandwich (module docstring). Returns the rendered new text.
    Raises `SyncConfigError` when the INPUT fails its gate, `EditDowngrade`
    when the edit cannot be applied or the verification fails."""
    raw = gate_text(text) if require_schema_before else parse_text_no_schema(text)
    planned = apply_edits_plain(raw, edits)

    rt = _rt()
    data = rt.load(io.StringIO(text))
    if data is None:
        data = CommentedMap()
    dropped = _apply_edits_ruamel(data, edits)
    buf = io.StringIO()
    rt.dump(data, buf)
    new_text = buf.getvalue()

    # Gate AFTER: full hardened gate + exact semantic equality.
    try:
        parsed_after = gate_text(new_text)
    except SyncConfigError as exc:
        raise EditDowngrade(f"edited text fails the hardened gate ({exc.reason})") from exc
    if parsed_after != planned:
        raise EditDowngrade("rendered result differs from the planned edit")

    # Comment survival (checked, not assumed) for non-destructive edits. A list
    # `set` that removed an item forgives EXACTLY the lines that left with that
    # item — never the whole batch, or one removed list entry would disarm the
    # check for every other edit saved alongside it.
    destructive = {e.op for e in edits} & {"unset", "rename-key"}
    if not destructive:
        lost = _comment_lines(text) - _comment_lines(new_text) - Counter(dropped)
        if lost:
            raise EditDowngrade("a comment line would be lost by this edit")
    return new_text
