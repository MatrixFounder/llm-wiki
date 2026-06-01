"""Concept-page writing leaf for wiki-extract-concepts (TASK 016 bead 016-05).

Dependency rule: imports ONLY stdlib + `._errors` + `._validation` +
`scripts.wiki_index.layout` / `scripts.wiki_index.security` +
`scripts.wiki_skills._common`.
No import from the facade (`__init__`) or any other leaf (_sourcing, _db).
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

from scripts.wiki_index.layout import (
    CONCEPTS_SUBDIR,
)
from scripts.wiki_index.security import (
    PathTraversalError,
    validate_inside_vault,
)
from scripts.wiki_skills._common import (
    sanitize_markdown_text as _sanitize_markdown_text,
)
from ._errors import ExtractionParseError
from ._validation import (
    _sanitize_name,
    _sanitize_definition,
    _SLUG_RE,
    _SOURCE_SPAN_RE,
)

logger = logging.getLogger(__name__)


def _format_source_quote_block(
    source_quote: str, source_slug: str, source_span: str,
) -> str:
    """Render the source quote as a Markdown blockquote (``>``) line(s)
    followed by a provenance footer line.

    H-4: `source_quote` is sanitized via `_sanitize_markdown_text` so a
    hostile quote containing `<script>...`, `[[evil-wikilink]]`,
    `` `dataview LIST FROM ""` ``, or footnote-syntax injection cannot
    surface in the rendered concept page. The `> ` line prefix
    additionally neutralizes any leading-line block-markdown that
    survives the escape.
    """
    sanitized_quote = _sanitize_markdown_text(source_quote)
    quote_lines = sanitized_quote.split("\n")
    quoted = "\n".join(f"> {line}" for line in quote_lines)
    return f"{quoted}\n> — [[{source_slug}]] ({source_span})"


def write_concept_page(
    vault_root: Path,
    candidate: dict[str, Any],
    source_slug: str,
    today: date,
    vault_id: str | None = None,
    concepts_dir: Path | None = None,
) -> tuple[Path, str]:
    """Write ``<concepts_dir>/<slug>.md`` atomically with frontmatter + body.

    R-36, R-40. Atomic via tempfile + ``os.replace`` (Decision-12 default).
    Behavior:

      - Symlink refuse: if ``target.is_symlink()``, raises
        ``PathTraversalError`` BEFORE any read, hash-compute, or write.
      - Content-hash skip: if the file exists with byte-identical content
        to the would-be-written payload → return ``(target, "unchanged")``.
        If it exists with different content → atomic rewrite + return
        ``(target, "updated")`` + ``logger.warning``. New file →
        ``(target, "created")``.
      - Markdown sanitization: ``name``, ``definition``, ``source_quote``,
        and ``source_span`` are sanitized before being embedded into the
        body.

    The ``concepts_dir`` parameter is optional; if omitted, defaults to
    ``<vault_root>/_concepts/`` (vault-tier layout). Callers writing for
    a course-tier source page should pass the sibling course's
    ``_concepts/`` (e.g. ``<vault_root>/Lessons/<Course>/_concepts``).
    Regardless of where `concepts_dir` lives, the function asserts it
    resolves inside ``vault_root`` (path-traversal guard).

    The ``vault_id`` parameter is explicit so the function stays pure —
    callers should pass ``args.vault``.
    """
    slug = candidate["slug"]
    # R-26 / R-40(d) path-traversal guard. We can't call validate_inside_vault
    # on a not-yet-existing file (it uses .resolve(strict=True)). Pre-flight:
    # (1) slug must be kebab-case (operator-synthesised input is untrusted —
    # defense in depth even though `_validate_candidates_schema` also checks);
    # (2) the parent resolves inside vault after we mkdir; (3) the final
    # target's resolved parent must equal the validated concepts_dir.
    # L-3: use precompiled _SLUG_RE instead of a string literal — same
    # pattern, avoids the per-call `re` module cache lookup.
    if not _SLUG_RE.match(slug):
        raise PathTraversalError(
            f"slug {slug!r} fails kebab-case regex; possible path traversal"
        )
    if concepts_dir is None:
        concepts_dir = vault_root / CONCEPTS_SUBDIR
    concepts_dir.mkdir(parents=True, exist_ok=True)
    validated_dir = validate_inside_vault(concepts_dir, vault_root)
    target = validated_dir / f"{slug}.md"

    # Q15 / NEW-2: symlink refuse BEFORE any read or hash-compute. Risk R-5
    # (TOCTOU between is_symlink check and os.replace) is acknowledged: the
    # pre-check fails before any write so the worst case is a refused
    # operation, not a write-through-symlink. O_NOFOLLOW-based hardening
    # is deferred (iteration-2 LOW residual).
    if target.is_symlink():
        raise PathTraversalError(
            f"concept page target {target} is a symlink — refusing "
            "to read or write through it"
        )

    # Sanitize the three free-text fields BEFORE assembling the body.
    safe_name = _sanitize_name(str(candidate["name"]))
    safe_definition = _sanitize_definition(str(candidate["definition"]))

    # Defense-in-depth source_span regex check at body-construction time
    # (in addition to the upstream `_validate_candidates_schema` check).
    source_span = str(candidate["source_span"])
    if not _SOURCE_SPAN_RE.match(source_span):
        raise ExtractionParseError(
            "source_span body construction requires Lstart-Lend format",
            error="INVALID_SOURCE_SPAN",
            field="source_span",
            reason=("source_span must match ^L\\d+-L\\d+$ before embedding "
                    "into _concepts page body"),
        )
    safe_quote_block = _format_source_quote_block(
        str(candidate["source_quote"]), source_slug, source_span,
    )

    fm: dict[str, Any] = {
        "type": "concept",
        "vault_id": vault_id,
        "slug": slug,
        "name": safe_name,
        "date": today.isoformat() if isinstance(today, date) else str(today),
        "tags": ["concept", "candidate"],
        # R-4.6 (TASK 005) LOAD-BEARING PIN: is_candidate is Class A canonical.
        # reindex_full reads it back (R-4.1 / reindex._coerce_is_candidate), so a
        # freshly-applied candidate survives `wiki-reindex --full` as a candidate.
        # Guarded by tests/test_extract_concepts_candidate_regression.py.
        "is_candidate": True,
        "source_page": source_slug,
        "trust_level": "medium",
    }
    body = (
        f"# {safe_name}\n\n"
        f"{safe_definition}\n\n"
        f"## Mentions\n\n"
        f"{safe_quote_block}\n"
    )
    post = frontmatter.Post(body, **fm)
    payload = frontmatter.dumps(post)
    payload_bytes = payload.encode("utf-8")

    # C-1 content-hash skip semantics + M-5 symlink-follow defense:
    # existing-and-identical → "unchanged"; existing-and-different →
    # atomic rewrite + "updated" + warning; missing → atomic write +
    # "created". Risk R-4 mitigation: both sides normalized to UTF-8
    # bytes before sha256 so trailing-newline / frontmatter-encoding
    # differences cannot trigger spurious rewrites.
    # M-5: open the existing file with O_NOFOLLOW so a symlink swapped
    # in between the earlier is_symlink() check and this read cannot
    # leak content from outside the vault. ELOOP/ENOENT race → treat as
    # "not present" and write.
    action: str
    existing_bytes: bytes | None = None
    try:
        rd_fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        action = "created"
    except OSError:
        # ELOOP (target became a symlink after is_symlink check) or
        # other I/O race. Treat as not-present; the atomic write below
        # uses tempfile + os.replace which is rename(2) and DOES NOT
        # follow symlinks on POSIX — so even if the race persists, the
        # write goes to the intended path, not the symlink target.
        action = "created"
    else:
        try:
            existing_bytes = os.read(rd_fd, len(payload_bytes) + 1)
            # If the file is larger than the would-be-written payload,
            # we've already detected the mismatch; otherwise read the
            # exact remaining bytes to confirm length equality.
            while True:
                chunk = os.read(rd_fd, 65536)
                if not chunk:
                    break
                existing_bytes += chunk
        finally:
            os.close(rd_fd)
        if (hashlib.sha256(existing_bytes).hexdigest()
                == hashlib.sha256(payload_bytes).hexdigest()):
            return target, "unchanged"
        action = "updated"
        logger.warning(
            "write_concept_page: rewriting %s — existing content differs "
            "from would-be-written payload (content-hash mismatch)",
            target,
        )

    fd, tmp_name = tempfile.mkstemp(
        dir=str(concepts_dir),
        prefix=f".{slug}.",
        suffix=".md.tmp",
    )
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload_bytes)
        os.replace(tmp_name, target)
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise
    return target, action
