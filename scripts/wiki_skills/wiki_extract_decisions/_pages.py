"""Typed-page renderer + atomic writer (TASK 063).

The write contract is the house one (`wiki_extract_concepts/_pages.py`): symlink
REFUSE before any read/hash/write, content-hash skip, `tempfile` + `os.replace`
(rename(2) does not follow symlinks on POSIX), and an `O_NOFOLLOW` re-read that
closes the TOCTOU window between the symlink check and the read.

★ THE RENDERER IS SHARED WITH G2 (063-10). `validate_refs` runs the layout's
`ref_extraction` rules over the page text THIS module produces — not over an
approximation of it. Rendering twice, slightly differently, would validate a page
that is not the page that ships, which is the same class of bug as a gate that
disagrees with the code it gates.
"""
from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import frontmatter

from scripts.wiki_index.security import PathTraversalError, validate_inside_vault
from scripts.wiki_skills._common import sanitize_markdown_text

from ._validation import is_valid_slug

logger = logging.getLogger("wiki_extract_decisions.pages")

# ★ FORWARD EDGES ONLY (R-063-4 / M-1). We author `implements:`; we NEVER author
# `implemented-by:` — the inverse is auto-derived by `wiki-reindex --full` (ADR-004).
# Authoring both sides would make the graph's two halves independently editable, and
# a page could then assert an edge whose inverse says otherwise.
#
# ⚠️ `--full`, NOT `--delta`: inverse derivation is exactly what `--delta` leaves
# transiently stale (`lint.py:298`).


def render_page(
    candidate: dict[str, Any],
    *,
    slug: str,
    vault_id: str,
    source_slug: str,
    today: date,
    classification: str | None = None,
    source_indexable: bool = True,
) -> str:
    """One typed page, rendered — frontmatter + body.

    ★ `apply` NEVER AUTHORS AN `aliases:` KEY (R-063-10(c)). That closes the
    `alias-collision` lint category BY CONSTRUCTION rather than by validation: a
    category you cannot enter needs no guard. Aliases belong to the entity-resolution
    layer (`wiki-alias` / `wiki-merge`), and a rail that could mint them could
    silently merge two distinct entities.

    ★ CLASSIFICATION IS INHERITED FROM THE SOURCE, never defaulted (R-063-10(b)).
    Honest statement of what this does TODAY: nothing observable — policy is
    declared-but-off, and `classification-leak` fires only on `cited`/`verifies`
    refs, which typed pages do not carry. It is written anyway because the moment
    R-16 is switched on, a decision extracted from a `confidential` transcript that
    silently picked up the vault's `default_level` would turn this rail into a
    DECLASSIFICATION PUMP — a security regression created by a config flip somewhere
    else, in a rail nobody re-audits. Inheriting now costs one line.

    ★ THE PROVENANCE BACKLINK IS A WIKILINK **ONLY IF THE WALKER CAN SEE THE SOURCE**
    (`source_indexable`). This is not a nicety — it was found by G2 refusing our own
    output, which is the gate doing exactly its job on the rail that built it.

    A typed page cites the note it came from. If that note is glob-invisible — and on
    cybos a protocol in `meetings/` IS, because cybos declares no `meetings/**` glob —
    then the cited slug will never be a page in the index, and our own backlink
    becomes an ORPHAN LINK that `wiki-lint` reports. The rail would be manufacturing
    the very defect it exists to avoid.

    Extracting from a source the index does not carry is LEGITIMATE (a raw transcript
    in `_raw/` is exactly wiki-sync's flow), so refusing would be wrong. The honest
    answer is to record provenance WITHOUT authoring a ref: `extracted_from:` stays in
    the frontmatter as a plain string either way, and only the body's `[[…]]` is
    conditional.
    """
    fm: dict[str, Any] = {
        "type": str(candidate["class"]),
        "vault_id": vault_id,
        "slug": slug,
        "title": str(candidate["title"]),
        "status": str(candidate["status"]),
        "date": str(candidate.get("date") or today.isoformat()),
        # A plain string, never a wikilink: provenance that cannot orphan.
        "extracted_from": source_slug,
    }
    if classification:
        fm["classification"] = classification
    for edge, targets in (candidate.get("edges") or {}).items():
        # FORWARD ONLY. Rendered as wikilinks so the layout's own ref_extraction sees
        # them — the frontmatter is part of the page G2 scans.
        fm[str(edge)] = [f"[[{t}]]" for t in targets]

    cite = f"[[{source_slug}]]" if source_indexable else f"`{source_slug}`"
    body = (
        f"# {sanitize_markdown_text(str(candidate['title']))}\n\n"
        f"{sanitize_markdown_text(str(candidate['body']))}\n\n"
        f"## Источник\n\n"
        f"> {sanitize_markdown_text(str(candidate['source_quote']))}\n\n"
        f"— {cite}\n"
    )
    return str(frontmatter.dumps(frontmatter.Post(body, **fm)))


def write_page(
    vault_root: Path, typed_dir: str, slug: str, payload: str
) -> tuple[Path, str]:
    """Atomic write → `(path, action)` with `action ∈ {created, updated, unchanged}`.

    `typed_dir` comes from `resolve_typed_write_dir` (063-02) — the LAYOUT-DERIVED,
    walker-VERIFIED directory. Never a hardcoded `decisions/`, never a hardcoded
    "sibling": the same class name belongs at the vault root on cybos and beside the
    source note on a PARA vault, because those are the folders each layout's read
    globs can see. A page written anywhere else is written, never indexed, and raises
    no lint issue.
    """
    if not is_valid_slug(slug):
        raise PathTraversalError(f"slug fails validation; possible path traversal")

    out_dir = vault_root / typed_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    validated_dir = validate_inside_vault(out_dir, vault_root)
    target = validated_dir / f"{slug}.md"

    # Symlink REFUSE before any read, hash or write. The residual TOCTOU (a symlink
    # swapped in after this check) is closed on the write side by `os.replace`, which
    # is rename(2) and does not follow symlinks — so the worst case is a refusal, not
    # a write-through.
    if target.is_symlink():
        raise PathTraversalError(
            f"typed page target is a symlink — refusing to read or write through it")

    payload_bytes = payload.encode("utf-8")
    action = "created"
    try:
        fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        pass                      # missing, or the symlink race → write it
    else:
        try:
            existing = b""
            while chunk := os.read(fd, 65536):
                existing += chunk
        finally:
            os.close(fd)
        if hashlib.sha256(existing).hexdigest() == hashlib.sha256(payload_bytes).hexdigest():
            return target, "unchanged"
        action = "updated"
        logger.warning(
            "write_page: rewriting %s — existing content differs from the payload",
            target)

    fd_tmp, tmp_name = tempfile.mkstemp(
        dir=str(validated_dir), prefix=f".{slug}.", suffix=".md.tmp")
    try:
        with os.fdopen(fd_tmp, "wb") as fh:
            fh.write(payload_bytes)
        os.replace(tmp_name, target)
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise
    return target, action
