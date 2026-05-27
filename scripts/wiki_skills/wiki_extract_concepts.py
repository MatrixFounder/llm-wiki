"""`wiki-extract-concepts` CLI — LLM-driven entity extraction for Epic 7 R-3.

Reads an already-indexed source summary page from a vault, calls Claude
Sonnet 4.6 to identify candidate concept entities, de-duplicates against
``entities`` rows already in the DB, writes derivative ``_concepts/<slug>.md``
pages, and emits a wiki-ingest v1.1-compatible manifest. When ``--ingest``
is passed, dispatches the manifest in-process to ``index_from_manifest``
from the neutral ``_manifest_consumer`` module (TASK 003 v2 / Decision-15
+ Decision-16 — no subprocess, no cross-skill coupling).

The 9 internal helper functions are scaffolded as ``NotImplementedError``
stubs in this bead (003-01) and filled in by 003-03..003-11. Module-top
import of the three neutral-consumer symbols is intentional (stable
``unittest.mock.patch`` target — see I-7.12 patch-target lock).

Exit codes (R-42):
    0 — success or idempotency short-circuit (status="unchanged")
    1 — argparse / usage error
    2 — input-validation failure family — JSON envelope's ``error`` field
        disambiguates: SOURCE_NOT_FOUND | INVALID_SOURCE_PATH (absolute
        path passed) | INVALID_SOURCE_SLUG (filename doesn't yield a
        valid kebab-case slug)
    3 — LLM_API_UNAVAILABLE (Anthropic SDK connection / auth / rate-limit
        / bad-request / 5xx failure)
    4 — EXTRACTION_PARSE_ERROR (LLM returned malformed JSON, oversized
        source body, or schema-violating output)
    5 — PARTIAL_INDEX_FAILURE (some concept pages written, indexer failed)
    6 — MANIFEST_INVALID (validate_manifest raised WikiIngestError)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import frontmatter

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.security import (
    PathTraversalError,
    validate_inside_vault,
)
from scripts.wiki_skills._common import emit
# TASK 003 I-7.0 + I-7.11 (Decisions 15+16): module-top import locks the
# patch target as `scripts.wiki_skills.wiki_extract_concepts.<symbol>`.
from scripts.wiki_skills._manifest_consumer import (
    WikiIngestError,
    index_from_manifest,
    validate_manifest,
)


# ============================================================================
# Stub-only exception classes (real raises land in 003-04)
# ============================================================================


class ExtractionParseError(Exception):
    """Raised when the LLM returns malformed JSON or schema-violating output.

    Bound to exit code 4 (R-42 d). Real raise in I-7.4 (bead 003-04).
    """


class LLMUnavailableError(Exception):
    """Raised when the Anthropic API is unreachable or auth fails.

    Bound to exit code 3 (R-42 c). Real raise in I-7.4 (bead 003-04).
    """


# ============================================================================
# Helper stubs — replaced one-by-one by beads 003-03..003-11.
# ============================================================================


def load_known_entities(repo: Any, vault_id: str) -> list[dict[str, Any]]:
    """SELECT entities LEFT JOIN entity_aliases WHERE vault_id=?.

    Returns CONTRACT §2 known-concepts format:
        [{"slug": "...", "name": "...", "type": "...", "aliases": [...]}]
    Empty vault → empty list (R-32c). Multi-vault isolation enforced via
    the `vault_id = ?` predicate (ADR-002 §D1.1).

    Implementation note: raw SQL via ``repo._connect()`` rather than a new
    DAL method, per TASK.md §1.3 non-goal (DAL extension surface tight).
    Same pattern used by ``scripts/wiki_index/reindex.py``.
    """
    conn = repo._connect()
    rows = conn.execute(
        "SELECT slug, name, type FROM entities WHERE vault_id = ? ORDER BY slug",
        (vault_id,),
    ).fetchall()
    if not rows:
        return []
    aliases_by_slug: dict[str, list[str]] = {}
    alias_rows = conn.execute(
        "SELECT entity_slug, alias FROM entity_aliases "
        "WHERE vault_id = ? ORDER BY entity_slug, alias",
        (vault_id,),
    ).fetchall()
    for entity_slug, alias in alias_rows:
        aliases_by_slug.setdefault(entity_slug, []).append(alias)
    return [
        {
            "slug": slug,
            "name": name,
            "type": type_,
            "aliases": aliases_by_slug.get(slug, []),
        }
        for slug, name, type_ in rows
    ]


_SOURCE_SPAN_RE = re.compile(r"^L\d+-L\d+$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_ALLOWED_ENTITY_TYPES = {
    "concept", "person", "company", "product",
    "group", "event", "work", "external",
}
_REQUIRED_LLM_KEYS = {
    "slug", "name", "definition", "source_quote", "source_span", "entity_type",
}
# M-1 (vdd-multi 2026-05-27 critic-logic): LLM input-size cap. Anthropic
# context window for sonnet-4-6 is ~200K tokens; our extraction prompt
# wraps the source body + known-concepts JSON + ~250 tokens of
# instruction. Bound the source body at 100K chars (~25K tokens) so the
# prompt never exceeds the model's context and we get a clear error
# envelope before the SDK rejects with a 400.
_MAX_SOURCE_BODY_CHARS = 100_000


def _build_extraction_prompt(
    source_body: str,
    known_entities: list[dict[str, Any]],
) -> str:
    """Compose the LLM extraction prompt.

    The known-concepts block (CONTRACT §2 shape — produced by
    `load_known_entities`) is embedded verbatim so the LLM can echo back
    the canonical `slug`/`name` for de-dup hits instead of inventing new
    ones (R-34).
    """
    known_block = json.dumps(known_entities, indent=2) if known_entities else "[]"
    types_block = ", ".join(sorted(_ALLOWED_ENTITY_TYPES))
    return (
        "You are a knowledge-graph entity extractor for a personal wiki.\n"
        "Identify 3-10 key concepts mentioned in the source page below.\n\n"
        "Known concepts already in this vault — USE THE EXACT slug + name "
        "when a mentioned concept matches an entry here (so the wiki can "
        "de-duplicate):\n"
        f"{known_block}\n\n"
        "Source page body:\n"
        f"{source_body}\n\n"
        'Reply with ONLY a JSON array (no prose, no markdown fence). '
        'Each item MUST be a JSON object with exactly these keys: '
        '{"slug": kebab-case-string, "name": "Human Name", '
        '"definition": "1-3 sentences", "source_quote": "10-50 words verbatim '
        'from the source body", "source_span": "L<start>-L<end>" (1-indexed '
        f'lines from the source), "entity_type": one of [{types_block}]}}.'
    )


def _validate_extraction_schema(items: list[Any]) -> None:
    """Assert every item in the LLM response matches the required schema.

    R-33(d-e), Decision-10. Raises ``ExtractionParseError`` on any
    deviation with the offending item dumped (truncated to 500 chars).

    M-2 (vdd-multi 2026-05-27 critic-logic): slug-regex check moved to
    this boundary so a malformed slug fails fast (exit 4
    EXTRACTION_PARSE_ERROR) rather than propagating to
    ``write_concept_page`` which would raise ``PathTraversalError`` —
    uncaught in ``main()`` and crashing the CLI with a stack trace.
    """
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ExtractionParseError(
                f"LLM item #{idx} not a dict: {str(item)[:500]}"
            )
        missing = _REQUIRED_LLM_KEYS - item.keys()
        if missing:
            raise ExtractionParseError(
                f"LLM item #{idx} missing keys {sorted(missing)}: "
                f"{json.dumps(item)[:500]}"
            )
        if not _SLUG_RE.match(str(item["slug"])):
            raise ExtractionParseError(
                f"LLM item #{idx} slug {item['slug']!r} fails kebab-case "
                f"regex ^[a-z0-9][a-z0-9-]{{0,62}}$"
            )
        if not _SOURCE_SPAN_RE.match(str(item["source_span"])):
            raise ExtractionParseError(
                f"LLM item #{idx} source_span {item['source_span']!r} does "
                f"not match Lstart-Lend (Decision-10)"
            )
        if item["entity_type"] not in _ALLOWED_ENTITY_TYPES:
            raise ExtractionParseError(
                f"LLM item #{idx} entity_type {item['entity_type']!r} not "
                f"in allowed set {sorted(_ALLOWED_ENTITY_TYPES)}"
            )


def extract_concepts_llm(
    source_body: str,
    known_entities: list[dict[str, Any]],
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 4096,
) -> list[dict[str, Any]]:
    """Claude Sonnet 4.6 extraction call (temperature=0, structured JSON).

    R-33, R-34. Returns a validated list of candidate concept dicts.
    Raises ``ExtractionParseError`` on malformed JSON / schema violation
    or oversized input (→ exit 4); raises ``LLMUnavailableError`` on
    connection/auth/rate-limit/bad-request failure (→ exit 3).
    """
    # M-1 (vdd-multi 2026-05-27 critic-logic): input-size cap before
    # building the prompt — prevents anthropic.BadRequestError on
    # multi-megabyte pages, and gives the operator a clear envelope
    # instead of an SDK stack trace.
    if len(source_body) > _MAX_SOURCE_BODY_CHARS:
        raise ExtractionParseError(
            f"source body too large ({len(source_body)} chars; max "
            f"{_MAX_SOURCE_BODY_CHARS}). Chunking is deferred to a "
            "future epic — for now, split the source page or summarize "
            "it before extraction."
        )
    import anthropic
    if max_tokens > 4096:
        max_tokens = 4096  # R-33(c) enforcement
    client = anthropic.Anthropic()
    prompt = _build_extraction_prompt(source_body, known_entities)
    try:
        response = client.messages.create(
            model=model,
            temperature=0,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
    except (
        anthropic.APIConnectionError,
        anthropic.AuthenticationError,
        anthropic.RateLimitError,
        anthropic.BadRequestError,
        anthropic.APIStatusError,
    ) as e:
        # M-1 follow-up: include BadRequestError (oversized prompt despite
        # our cap; model-side context-window mismatches) and the generic
        # APIStatusError so 5xx responses don't crash with a stack trace.
        # L-V3.3 (vdd-multi 2026-05-28 CWE-209): `from None` suppresses
        # the exception chain so the SDK exception's ``__cause__`` (which
        # may carry ``request_id``, partial headers, or auth context on
        # some SDK versions) cannot be surfaced by future ``__cause__``
        # consumers. The wrapper str uses ``type(e).__name__`` only — no
        # ``str(e)`` leak. Operators reading stderr/stdout get a clean
        # `LLM_API_UNAVAILABLE` envelope.
        raise LLMUnavailableError(
            f"{type(e).__name__}: Anthropic API call failed"
        ) from None

    # Anthropic SDK returns response.content = list[ContentBlock]; the first
    # text block has .text attr. We rely on temperature=0 + a clear prompt
    # to keep this single-block; fall back gracefully if structure changes.
    if not response.content:
        raise ExtractionParseError("LLM response has empty content")
    first_block = response.content[0]
    raw_text = getattr(first_block, "text", None)
    if not isinstance(raw_text, str):
        raise ExtractionParseError(
            f"LLM first content-block has no .text str (got {type(first_block).__name__})"
        )
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ExtractionParseError(
            f"LLM returned non-JSON: {raw_text[:500]}"
        ) from e
    if not isinstance(parsed, list):
        raise ExtractionParseError(
            f"LLM returned non-list (got {type(parsed).__name__}): {raw_text[:500]}"
        )
    _validate_extraction_schema(parsed)
    return parsed


def classify_candidates(
    llm_results: list[dict[str, Any]],
    known_slugs: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split LLM-extracted candidates into (create_list, mention_list).

    Each item is shallow-copied and annotated with ``action="create"`` or
    ``action="mention"`` (R-34) so 003-10 manifest builder and 003-08 refs
    upsert can dispatch off a single field. Defensive copy means callers
    can't surprise-mutate the LLM output through the classifier's return.
    """
    create_list: list[dict[str, Any]] = []
    mention_list: list[dict[str, Any]] = []
    for item in llm_results:
        annotated = {**item}
        if item["slug"] in known_slugs:
            annotated["action"] = "mention"
            mention_list.append(annotated)
        else:
            annotated["action"] = "create"
            create_list.append(annotated)
    return create_list, mention_list


def write_concept_page(
    vault_root: Path,
    candidate: dict[str, Any],
    source_slug: str,
    today: date,
    vault_id: str | None = None,
) -> tuple[Path, str]:
    """Write ``_concepts/<slug>.md`` atomically with frontmatter + body.

    R-36, R-40. Atomic via tempfile + ``os.replace`` (Decision-12 default —
    repo-local primitive over the vendored ``_safety.atomic_write_text``).
    Skip-on-exists (R-36e): if the file already exists, return ``(path,
    "unchanged")`` without rewriting; otherwise return ``(path, "created")``.

    H-2 fix (vdd-multi 2026-05-27): returning the action label from this
    function (single stat inside the function) eliminates the TOCTOU race
    that the previous caller-side pre-check + internal re-check exposed.

    The ``vault_id`` parameter is explicit (per plan-reviewer nit #3) so
    the function stays pure — callers should pass ``args.vault``.
    """
    slug = candidate["slug"]
    # R-26 / R-40(d) path-traversal guard. We can't call validate_inside_vault
    # on a not-yet-existing file (it uses .resolve(strict=True)). Pre-flight:
    # (1) slug must be kebab-case (LLM-output is untrusted — defense in depth
    # even though _validate_extraction_schema also checks); (2) the parent
    # resolves inside vault after we mkdir; (3) the final target's resolved
    # parent must equal the validated concepts_dir.
    if not re.match(r"^[a-z0-9][a-z0-9-]{0,62}$", slug):
        raise PathTraversalError(
            f"slug {slug!r} fails kebab-case regex; possible path traversal"
        )
    concepts_dir = vault_root / "_concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)
    validated_dir = validate_inside_vault(concepts_dir, vault_root)
    target = validated_dir / f"{slug}.md"
    if target.exists():
        return target, "unchanged"
    fm: dict[str, Any] = {
        "type": "concept",
        "vault_id": vault_id,
        "slug": slug,
        "name": candidate["name"],
        "date": today.isoformat() if isinstance(today, date) else str(today),
        "tags": ["concept", "candidate"],
        "is_candidate": True,
        "source_page": source_slug,
        "trust_level": "medium",
    }
    body = (
        f"# {candidate['name']}\n\n"
        f"{candidate['definition']}\n\n"
        f"## Mentions\n\n"
        f"- [[{source_slug}]] — \"{candidate['source_quote']}\" "
        f"({candidate['source_span']})\n"
    )
    post = frontmatter.Post(body, **fm)
    payload = frontmatter.dumps(post)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(concepts_dir),
        prefix=f".{slug}.",
        suffix=".md.tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp_name, target)
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise
    return target, "created"


def _lookup_entity_row(
    repo: Any, vault_id: str, slug: str,
) -> dict[str, Any] | None:
    """Direct lookup bypassing repo.resolve_entity (still a stub per
    Phase 3a — TASK.md §1.3 keeps it as NotImplementedError until R-4)."""
    row = repo._connect().execute(
        "SELECT slug, name, is_candidate, first_seen, type "
        "FROM entities WHERE vault_id = ? AND slug = ?",
        (vault_id, slug),
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def upsert_extracted_entity(
    repo: Any,
    vault_id: str,
    candidate: dict[str, Any],
    source_slug: str,
    today: date,
) -> str:
    """Upsert an extracted entity row with defensive downgrade-guard.

    Returns one of:
        - "confirmed"  — existing row had is_candidate=0; SKIPPED (no write).
        - "created"    — row did not exist; INSERTED with is_candidate=1.
        - "updated"    — existing candidate row was UPDATED.

    The SQL-level guard in ``upsert_entity`` (003-07a) is the *primary*
    defense; this call-layer skip is defense-in-depth — both let confirmed
    entities (R-37b) survive intact. Skipping at the call layer also
    avoids a no-op write that would touch last_updated unnecessarily.
    """
    existing = _lookup_entity_row(repo, vault_id, candidate["slug"])
    if existing is not None and existing.get("is_candidate") == 0:
        return "confirmed"
    today_iso = today.isoformat() if isinstance(today, date) else str(today)
    model = candidate.get("model", "claude-sonnet-4-6")
    canonicalized_by = f"llm:{model}@{today_iso}"
    first_seen = existing["first_seen"] if existing else today_iso
    repo.upsert_entity(
        vault_id=vault_id,
        slug=candidate["slug"],
        name=candidate["name"],
        type=candidate["entity_type"],
        is_candidate=1,
        canonicalized_by=canonicalized_by,
        first_seen=first_seen,
        last_updated=today_iso,
        file_path=f"_concepts/{candidate['slug']}.md",
    )
    return "updated" if existing else "created"


_SPAN_REGEX = re.compile(r"^L(\d+)-L(\d+)$")


def _parse_source_span(span: str) -> tuple[int, int]:
    """Parse Decision-10 ``"Lstart-Lend"`` format into (line_start, line_end).

    Raises ``ExtractionParseError`` on malformed format or inverted range.
    """
    m = _SPAN_REGEX.match(span)
    if not m:
        raise ExtractionParseError(
            f"Malformed source_span (expected 'L<start>-L<end>'): {span!r}"
        )
    start, end = int(m.group(1)), int(m.group(2))
    if end < start:
        raise ExtractionParseError(f"source_span end before start: {span!r}")
    return start, end


def upsert_entity_refs(
    repo: Any,
    vault_id: str,
    source_slug: str,
    source_project: str,
    all_candidates: list[dict[str, Any]],
) -> None:
    """Atomic ``replace_refs`` for all extracted entities (create + mention).

    R-38, R-40. Atomic DELETE+INSERT keyed on (vault_id, page_slug, project)
    so re-extraction on a changed body (UC-09 Scenario B) does not leave
    stale refs interleaved with new ones.
    """
    from scripts.wiki_index.models import PageRef
    refs: list[PageRef] = []
    for cand in all_candidates:
        line_start, line_end = _parse_source_span(cand["source_span"])
        refs.append(PageRef(
            vault_id=vault_id,
            page_slug=source_slug,
            page_project=source_project,
            entity_slug=cand["slug"],
            ref_type="mentioned",
            trust_level="medium",
            line_start=line_start,
            line_end=line_end,
            source_quote=cand["source_quote"],
        ))
    repo.replace_refs(
        vault_id=vault_id,
        page_slug=source_slug,
        page_project=source_project,
        refs=refs,
    )


_SOURCE_KIND = "extract-concepts"


def check_idempotency(
    repo: Any,
    vault_id: str,
    source_slug: str,
    current_hash: str,
) -> bool:
    """Return True if source page is unchanged since last extraction.

    R-39, UC-09 Scenario A. Query ``source_state`` for the recorded hash;
    match → caller should short-circuit (no LLM call, no DB mutations).

    L-V3.2 (vdd-multi 2026-05-28): explicit NULL check on row["value"].
    The schema declares ``value TEXT NOT NULL`` so this case shouldn't
    arise, but defensive — if a row exists with NULL (corruption / future
    schema change) we treat it as "unknown" → False → re-extract,
    avoiding silent misuse.
    """
    row = repo._connect().execute(
        "SELECT value FROM source_state "
        "WHERE vault_id = ? AND source_kind = ? AND scope = ? AND key = ?",
        (vault_id, _SOURCE_KIND, source_slug, "source_hash"),
    ).fetchone()
    if row is None or row["value"] is None:
        return False
    return bool(row["value"] == current_hash)


def update_idempotency_state(
    repo: Any,
    vault_id: str,
    source_slug: str,
    new_hash: str,
) -> None:
    """Upsert the source_state row with the new hash.

    Called from ``main()`` at the END of a successful extraction so that
    partial failures leave the row un-updated → next run retries.
    """
    conn = repo._connect()
    now = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.execute(
            "INSERT INTO source_state "
            "(vault_id, source_kind, scope, key, value, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(vault_id, source_kind, scope, key) DO UPDATE SET "
            "value = excluded.value, updated_at = excluded.updated_at",
            (vault_id, _SOURCE_KIND, source_slug, "source_hash", new_hash, now),
        )


def build_manifest(
    vault_id: str,
    source_slug: str,
    source_hash: str,
    create_list: list[dict[str, Any]],
    mention_list: list[dict[str, Any]],
    log_event: dict[str, Any],
    vault_root: Path,
) -> dict[str, Any]:
    """Assemble wiki-ingest v1.1-compatible manifest dict (R-35).

    Two distinct ``action`` semantics live here (planner note + R-35):
      - ``written[i].action`` ∈ {"created", "unchanged"} — page-file write
        outcome; ``write_concept_page`` returns the path either fresh or
        pre-existing. Caller annotates ``file_write_action`` on the
        candidate dict before passing in.
      - top-level ``mentioned[i].action`` ∈ {"created","updated","confirmed",
        "mentioned"} — entity-row outcome from ``upsert_extracted_entity``
        (for create_list items) or "mentioned" for pure mention_list items.

    Output is contract-checked against
    ``_manifest_consumer.validate_manifest`` by R-43(b) tests so this
    skill's output is consumable by ``index_from_manifest`` in-process.
    """
    written: list[dict[str, Any]] = []
    for cand in create_list:
        page_action = cand.get("file_write_action", "created")
        written.append({
            "kind": "concept",
            "path": f"_concepts/{cand['slug']}.md",
            "action": page_action,
            "scope": "vault",
            "slug": cand["slug"],
        })
    mentioned: list[dict[str, Any]] = []
    for cand in create_list:
        # entity_action from 003-07b: created / updated / confirmed
        mentioned.append({
            "slug": cand["slug"],
            "action": cand.get("entity_action", "created"),
        })
    for cand in mention_list:
        mentioned.append({
            "slug": cand["slug"],
            "action": "mentioned",
        })
    return {
        "status": "ok",
        "vault_id": vault_id,
        "source": {"slug": source_slug, "hash": source_hash},
        "written": written,
        "mentioned": mentioned,
        "log_event": log_event,
        "extraction_summary": {
            "create_count": len(create_list),
            "mention_count": len(mention_list),
        },
    }


def dispatch_to_indexer(
    manifest_dict: dict[str, Any],
    vault_id: str,
    vault_root: Path,
    db_path: str | None,
) -> dict[str, Any]:
    """In-process dispatch to the neutral manifest consumer (Decision-15).

    Calls ``validate_manifest`` then ``index_from_manifest`` from
    ``_manifest_consumer`` — both bound at module top of this file
    (003-01 patch-target lock; tests patch
    ``scripts.wiki_skills.wiki_extract_concepts.<symbol>``, NOT the
    source-of-truth module). Raises ``WikiIngestError`` on contract
    violation (caller maps to exit 6).
    """
    validate_manifest(manifest_dict, vault_id, vault_root)
    return index_from_manifest(
        manifest_dict,
        vault_id,
        vault_root,
        db_path=db_path,
    )


# ============================================================================
# argparse + main
# ============================================================================


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="wiki-extract-concepts",
        description="LLM-driven concept extraction (Epic 7 R-3 entry-point)",
    )
    p.add_argument("--vault", required=True,
                   help="Vault ID (must be registered in vaults table)")
    p.add_argument("--vault-root", required=True, type=Path,
                   help="Absolute path to vault root directory")
    p.add_argument("--source-page", required=True,
                   help="Source page slug or relative path within vault")
    p.add_argument("--db-path", default=None,
                   help="Override global DB path (default: standard XDG location)")
    p.add_argument("--model", default="claude-sonnet-4-6",
                   help="Anthropic model ID (default: claude-sonnet-4-6)")
    p.add_argument("--ingest", action="store_true",
                   help="In-process indexer dispatch (Decision-15) — "
                        "call index_from_manifest after manifest emit")
    p.add_argument("--max-tokens", type=int, default=4096,
                   help="LLM extraction max_tokens cap (R-33c, default: 4096)")
    return p


def main(argv: list[str] | None = None) -> int:
    """CLI entry-point. Returns process exit code (R-42 mapping)."""
    args = _build_parser().parse_args(argv)
    vault_root = args.vault_root.resolve(strict=True)

    # Resolve source-page (slug → relative path) and validate inside vault.
    src_page = args.source_page
    # H-1 fix (vdd-multi 2026-05-27 critic-logic): absolute --source-page
    # bypasses the slug-form convention and conflates path-traversal with
    # missing-file errors. Reject absolutes up front with a distinct error
    # code so the operator sees the actual problem.
    if Path(src_page).is_absolute():
        return emit({
            "error": "INVALID_SOURCE_PATH",
            "message": (f"--source-page must be a vault-relative slug or "
                        f"path, not absolute ({src_page!r}). Pass the "
                        "page slug (e.g., 'self-improving-agent') or a "
                        "relative path inside --vault-root."),
        }, exit_code=2)

    # Try slug-form first (most common): `_sources/<slug>.md`.
    sources_dir = vault_root / "_sources"
    slug_path = sources_dir / f"{src_page}.md"
    if slug_path.is_file():
        candidate_path = slug_path
    else:
        candidate_path = vault_root / src_page

    try:
        source_path = candidate_path.resolve(strict=True)
        validate_inside_vault(source_path, vault_root)
    except (FileNotFoundError, PathTraversalError) as e:
        return emit({"error": "SOURCE_NOT_FOUND",
                     "message": f"source-page {src_page!r} not found in vault: {e}"},
                    exit_code=2)

    today = date.today()
    repo = make_repo({
        "vault_id": args.vault,
        **({"db_path": args.db_path} if args.db_path else {}),
    })

    try:
        # The full extraction pipeline.
        source_body = source_path.read_text(encoding="utf-8")
        current_hash = hashlib.sha256(source_body.encode("utf-8")).hexdigest()

        # H-3 fix (vdd-multi 2026-05-27 critic-logic): validate the derived
        # source_slug against the kebab regex BEFORE any writes. Dotted
        # filenames like `Foo.Bar.md` would otherwise produce slug="Foo.Bar"
        # and fail at the DB CHECK constraint AFTER pages are on disk —
        # leaving dangling artifacts and a half-success manifest.
        source_slug = source_path.stem
        if not _SLUG_RE.match(source_slug):
            return emit({
                "error": "INVALID_SOURCE_SLUG",
                "message": (f"source-page filename {source_slug!r} does not "
                            "yield a valid kebab-case slug "
                            "(^[a-z0-9][a-z0-9-]{0,62}$). Rename the file or "
                            "pass --source-page with the canonical slug."),
            }, exit_code=2)

        if check_idempotency(repo, args.vault, source_slug, current_hash):
            return emit({"status": "ok", "action": "unchanged",
                         "manifest": None})

        known = load_known_entities(repo, args.vault)
        known_slugs = {e["slug"] for e in known}

        candidates = extract_concepts_llm(
            source_body, known, args.model, args.max_tokens,
        )
        create_list, mention_list = classify_candidates(candidates, known_slugs)

        # Write concept pages + upsert entity rows for create-list. H-2 fix
        # (vdd-multi 2026-05-27): use the (path, action) tuple returned by
        # write_concept_page so the caller doesn't TOCTOU-race the
        # pre-existence check.
        for cand in create_list:
            _path, file_action = write_concept_page(
                vault_root, cand, source_slug, today, vault_id=args.vault,
            )
            cand["file_write_action"] = file_action
            cand["entity_action"] = upsert_extracted_entity(
                repo, args.vault, cand, source_slug, today,
            )

        upsert_entity_refs(
            repo, args.vault, source_slug, "_vault_",
            create_list + mention_list,
        )

        log_event = {
            "event_ts": today.isoformat() + "T00:00:00",
            "event_type": "ingest",
            "subject": source_slug,
        }
        manifest = build_manifest(
            args.vault, source_slug, current_hash,
            create_list, mention_list, log_event, vault_root,
        )

        # C-1 fix (vdd-multi 2026-05-27 critic-logic CRITICAL): defer
        # source_state update until AFTER the optional dispatch step. If
        # dispatch fails (exit 5 PARTIAL_INDEX_FAILURE) we MUST NOT mark
        # the source as processed — next run must retry the index step.
        if args.ingest:
            summary = dispatch_to_indexer(
                manifest, args.vault, vault_root, args.db_path,
            )
            if summary.get("failed"):
                # Do NOT update_idempotency_state — operator re-runs to retry.
                return emit({"action": "partial",
                             "error": "PARTIAL_INDEX_FAILURE",
                             "extraction": manifest,
                             "index": summary}, exit_code=5)
            update_idempotency_state(repo, args.vault, source_slug, current_hash)
            return emit({"extraction": manifest, "index": summary})
        # No-ingest path: extraction completed successfully → safe to record.
        update_idempotency_state(repo, args.vault, source_slug, current_hash)
        return emit(manifest)

    except LLMUnavailableError as e:
        return emit({"error": "LLM_API_UNAVAILABLE", "message": str(e)},
                    exit_code=3)
    except ExtractionParseError as e:
        return emit({"error": "EXTRACTION_PARSE_ERROR", "message": str(e)},
                    exit_code=4)
    except WikiIngestError as e:
        return emit({"error": "MANIFEST_INVALID", "message": str(e)},
                    exit_code=6)
    finally:
        repo.close()


if __name__ == "__main__":
    sys.exit(main())
