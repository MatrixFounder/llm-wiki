"""`wiki-extract-concepts` CLI (v3.1) — deterministic concept-extraction skill.

Two subcommands:

* ``prepare`` — read the source summary page, compute its sha256, query
  ``source_state`` for ``is_unchanged``, load the vault's known concepts,
  sweep for disk/DB drift, emit a JSON recon envelope. NO LLM call.
* ``apply``   — consume the orchestrator-synthesised candidates JSON
  (``--candidates-file`` or ``--candidates-stdin``), hash-check against
  ``--source-hash`` from prepare, validate the schema (strict), write
  ``_concepts/<slug>.md`` pages (atomic + content-hash skip + symlink
  refuse + markdown sanitization), upsert entity rows + refs, emit a
  wiki-ingest v1.1-compatible manifest, optionally dispatch the manifest
  in-process to ``index_from_manifest`` from the neutral
  ``_manifest_consumer`` module (Decision-15 + Decision-16 — no
  subprocess, no cross-skill coupling).

Synthesis lives outside this skill (TASK 003 v3.1 / Decision-17). The
orchestrator runs ``prepare``, loads the ``concept-extraction`` skill
into its own context, reads the source body, generates candidates JSON,
and pipes them into ``apply``. This module makes ZERO model-provider
SDK calls (the v2 LLM-call code path was deleted in bead 003-v3-06).

Module-top import of the three neutral-consumer symbols is intentional
(stable ``unittest.mock.patch`` target — see PLAN R-1 patch-target lock).

Exit codes (R-42 v3.1 + vdd-multi 2026-05-28 hardening):
    0 — success (manifest or {extraction, index} envelope)
    1 — argparse / usage error
    2 — input-validation failure: SOURCE_NOT_FOUND | INVALID_SOURCE_PATH
        | INVALID_SOURCE_SLUG | SOURCE_TOO_LARGE |
        SOURCE_CHANGED_DURING_EXTRACTION | INVALID_CANDIDATES_PATH |
        INVALID_SOURCE_HASH (new in vdd-multi-fix C-1; library-caller
        defense — argparse already gates the CLI path)
    4 — candidates payload error: EXTRACTION_PARSE_ERROR |
        CANDIDATES_TOO_LARGE | CANDIDATE_COUNT_OUT_OF_BOUNDS |
        FIELD_TOO_LONG | UNKNOWN_FIELD | FIELD_QUOTE_NOT_IN_BODY |
        INVALID_NAME_FORMAT | INVALID_SOURCE_SPAN
    5 — PARTIAL_INDEX_FAILURE (with --ingest; source_state NOT updated
        per C-1 invariant so a retry is safe) OR
        IDEMPOTENCY_UPDATE_FAILED (new in vdd-multi-fix H-3; pages /
        entities / refs committed but source_state UPSERT raised
        OperationalError — next run will safely re-extract)
    6 — MANIFEST_INVALID (with --ingest)

(The v2 exit-3 envelope for upstream-API failures is retired in v3.1.)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import frontmatter

logger = logging.getLogger(__name__)

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout import (
    CONCEPTS_SUBDIR,
    COURSE_TIER_DIR,
    SOURCES_SUBDIR,
)
from scripts.wiki_index.security import (
    PathTraversalError,
    validate_inside_vault,
)
from scripts.wiki_skills._common import emit
from scripts.wiki_skills._common import (
    sanitize_markdown_text as _sanitize_markdown_text,
)
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
    """Raised when the candidates payload returned by the calling agent is
    malformed JSON or schema-violating.

    Bound to exit code 4 (R-42 d).

    v3.1 (003-v3-02) extends the v2 message-only surface with three optional
    structured attributes for sub-envelope routing:
        .error  — sub-envelope code (e.g. "UNKNOWN_FIELD", "FIELD_TOO_LONG",
                  "CANDIDATE_COUNT_OUT_OF_BOUNDS", "FIELD_QUOTE_NOT_IN_BODY").
        .field  — the offending field name (NEVER the value — CWE-117 guard).
        .reason — short structured reason string; the apply() caller maps this
                  into the JSON error envelope's `reason` key.
    Legacy callers that pass only a single message string continue to work.
    """

    def __init__(
        self,
        message: str,
        *,
        error: str | None = None,
        field: str | None = None,
        reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error = error
        self.field = field
        self.reason = reason


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


# L-2 (vdd-multi 2026-05-28): `\d` in Python 3 matches Unicode digits
# (Arabic-Indic, Devanagari, ...) by default. We want ASCII-only digits
# in source-span line numbers — anchor with re.ASCII so the schema
# rejects e.g. `L١-L٢` at validation rather than silently coercing.
_SOURCE_SPAN_RE = re.compile(r"^L\d+-L\d+$", re.ASCII)
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_ALLOWED_ENTITY_TYPES = {
    "concept", "person", "company", "product",
    "group", "event", "work", "external",
}

# C-1 (vdd-multi 2026-05-28): operator-supplied sha256-hex must match
# /^[0-9a-f]{64}$/ exactly. Without this, an uppercased hex value (e.g.,
# PowerShell `toupper` pipeline) silently misroutes to
# SOURCE_CHANGED_DURING_EXTRACTION; and unvalidated values become a
# CWE-117 log-injection vector in the envelope reason field.
_SOURCE_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
# M-3 (TASK 003 v3.1): DoS protection on prepare's sha256+read pipeline.
# Stat-checks st_size BEFORE read_text to bound memory. 10 MiB matches the
# existing validate_manifest body cap pattern.
_MAX_SOURCE_BODY_BYTES = 10_485_760  # 10 MiB

# H-5 / H-6 (TASK 003 v3.1 / 003-v3-03): DoS protection on candidates input
# (file or stdin). Capped BEFORE any JSON parse so a 5 GB payload cannot
# OOM the interpreter. Risk R-6 mitigation: stdin read uses cap+1 bytes
# so we never accumulate beyond the limit even if the producer streams.
_MAX_CANDIDATES_BYTES = 1_048_576  # 1 MiB

# H-8 (003-v3-05): operator-supplied attribution string that flows into
# `entities.canonicalized_by`. Strict charset: lowercase alphanumerics +
# `._:@-` (allows model names like `claude-opus-4-7@vendor`). Cap at
# 64 chars; rejects newlines, control chars, and shell metachars.
_ORCHESTRATOR_ID_RE = re.compile(r"^[a-z0-9._:@-]{1,64}$")


def _path_is_absolute(p: Path | str) -> bool:
    """Cross-platform absolute-path detection (M-6).

    `Path.is_absolute()` treats `/foo` as non-absolute on Windows (it's
    drive-relative there) and `C:\\foo` as non-absolute on POSIX. For the
    skill's input-validation gates we want "looks absolute on EITHER
    platform" semantics so the same operator mistake (`--source-page
    /etc/passwd`) produces the same envelope regardless of OS.
    """
    s = str(p)
    if not s:
        return False
    if Path(s).is_absolute():
        return True
    # POSIX-style absolute path on Windows (drive-relative under Windows
    # path rules but operator-intent is clearly "absolute").
    if s.startswith("/") or s.startswith("\\"):
        return True
    # Windows drive prefix on POSIX (e.g. "C:\foo" or "C:/foo").
    if len(s) >= 2 and s[1] == ":" and s[0].isalpha():
        return True
    return False


def _validate_source_hash(value: str) -> str:
    """argparse `type=` validator for `--source-hash`.

    C-1 invariant: case-normalize to lowercase + reject anything that
    isn't exactly 64 hex chars. Without this validator, an upper-cased
    hex pipeline (PowerShell `toupper`, awk transforms) silently
    misroutes to SOURCE_CHANGED_DURING_EXTRACTION, AND the unvalidated
    value lands unescaped in stdout JSON (CWE-117 log-injection vector
    via embedded ANSI/JSON-breaking sequences). Both vectors close by
    forcing the value through this lowercased-hex gate at argparse time.
    """
    normalized = value.lower()
    if not _SOURCE_HASH_RE.match(normalized):
        raise argparse.ArgumentTypeError(
            "--source-hash must be exactly 64 lowercase hex chars "
            "(sha256 hex digest from `prepare`'s envelope)"
        )
    return normalized


def _validate_orchestrator_id(value: str) -> str:
    """argparse `type=` validator for `--orchestrator-id`.

    On regex fail, raises ``argparse.ArgumentTypeError`` so the operator
    sees an argparse-level usage error (exit 2 / SystemExit 2) rather
    than the exit-4 EXTRACTION_PARSE_ERROR envelope.
    """
    if not _ORCHESTRATOR_ID_RE.match(value):
        raise argparse.ArgumentTypeError(
            f"--orchestrator-id must match regex "
            f"{_ORCHESTRATOR_ID_RE.pattern!r}"
        )
    return value

# v3.1 strict-validator caps (003-v3-02 / H-2 / H-6 / H-9):
_REQUIRED_CANDIDATE_KEYS = {
    "slug", "name", "definition", "source_quote", "source_span", "entity_type",
}
_CANDIDATE_COUNT_MIN = 1
_CANDIDATE_COUNT_MAX = 25
_FIELD_CAPS = {
    "name": 200,
    "definition": 2000,
    "source_quote": 500,
}


def _validate_candidates_schema(
    items: list[Any], source_body: str | None = None,
) -> None:
    """Strict-mode validation of the calling-agent's candidates payload.

    v3.1 (003-v3-02) extends the v2-era validator:
      * **strict-equality on keys** (H-9): rejects extra keys with
        UNKNOWN_FIELD (was: subset check that silently ignored extras).
      * **count bound 1≤N≤25** (H-2): rejects empty arrays and N≥26 with
        CANDIDATE_COUNT_OUT_OF_BOUNDS.
      * **per-field caps** (H-6): name≤200, definition≤2000,
        source_quote≤500 → FIELD_TOO_LONG.
      * **optional quote-in-body check** (M-5): if `source_body` is passed
        AND env var WIKI_EXTRACT_NO_QUOTE_CHECK is NOT set, assert
        item['source_quote'] is a substring of source_body. Mismatch →
        FIELD_QUOTE_NOT_IN_BODY.
      * **CWE-117 / CWE-209 invariant**: the raised ExtractionParseError
        carries .error / .field / .reason structured attrs. The offending
        VALUE is NEVER included in any attribute. The apply() caller maps
        these into the JSON envelope without echoing content.
    """
    # L-1 (vdd-multi 2026-05-28): defensive top-level type guard. The
    # apply caller goes through `_load_candidates` which already enforces
    # `isinstance(parsed, list)`, but `_validate_candidates_schema` is a
    # module-level public-ish symbol with other call sites (tests, future
    # library consumers). Reject non-lists here so envelopes stay
    # consistent regardless of entry point.
    if not isinstance(items, list):
        raise ExtractionParseError(
            "candidates payload top-level is not a list",
            error="EXTRACTION_PARSE_ERROR",
            field=None,
            reason=(f"payload is {type(items).__name__}, expected JSON array"),
        )

    # H-2: count bound
    if not (_CANDIDATE_COUNT_MIN <= len(items) <= _CANDIDATE_COUNT_MAX):
        raise ExtractionParseError(
            f"candidates count={len(items)} out of bounds "
            f"[{_CANDIDATE_COUNT_MIN}, {_CANDIDATE_COUNT_MAX}]",
            error="CANDIDATE_COUNT_OUT_OF_BOUNDS",
            field=None,
            reason=(f"count={len(items)} not in "
                    f"[{_CANDIDATE_COUNT_MIN}, {_CANDIDATE_COUNT_MAX}]"),
        )

    # L-1 (vdd-multi 2026-05-28): also type-check the non-capped fields
    # so a `null` slug / span / entity_type produces a clear
    # "not a string" envelope instead of `re.match` on coerced `"None"`.
    _NONCAPPED_STR_FIELDS = ("slug", "source_span", "entity_type")

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ExtractionParseError(
                f"candidate #{idx} not a dict",
                error="EXTRACTION_PARSE_ERROR",
                field=None,
                reason=f"item #{idx} is not a JSON object",
            )

        # H-9: strict-equality on keys (no extras, no missing).
        extra = item.keys() - _REQUIRED_CANDIDATE_KEYS
        missing = _REQUIRED_CANDIDATE_KEYS - item.keys()
        if extra:
            offending = sorted(extra)[0]
            raise ExtractionParseError(
                f"candidate #{idx} has unknown key (envelope omits value)",
                error="UNKNOWN_FIELD",
                field=offending,
                reason=f"item #{idx} has unknown key {offending!r} "
                       "(strict mode rejects extras)",
            )
        if missing:
            offending = sorted(missing)[0]
            raise ExtractionParseError(
                f"candidate #{idx} missing keys {sorted(missing)}",
                error="EXTRACTION_PARSE_ERROR",
                field=offending,
                reason=f"item #{idx} missing keys {sorted(missing)}",
            )

        # H-6: per-field caps (length check; offending value NOT echoed).
        for field_name, cap in _FIELD_CAPS.items():
            value = item[field_name]
            if not isinstance(value, str):
                raise ExtractionParseError(
                    f"candidate #{idx} field {field_name!r} not a string",
                    error="EXTRACTION_PARSE_ERROR",
                    field=field_name,
                    reason=(f"item #{idx} field {field_name!r} is "
                            f"{type(value).__name__}, expected str"),
                )
            if len(value) > cap:
                raise ExtractionParseError(
                    f"candidate #{idx} field {field_name!r} exceeds cap",
                    error="FIELD_TOO_LONG",
                    field=field_name,
                    reason=(f"item #{idx} field {field_name!r} length "
                            f"{len(value)} exceeds cap {cap}"),
                )

        # L-1: type-check non-capped string fields first (so `null` slug
        # yields "not a string" instead of `re.match("None")` confusion).
        for field_name in _NONCAPPED_STR_FIELDS:
            value = item[field_name]
            if not isinstance(value, str):
                raise ExtractionParseError(
                    f"candidate #{idx} field {field_name!r} not a string",
                    error="EXTRACTION_PARSE_ERROR",
                    field=field_name,
                    reason=(f"item #{idx} field {field_name!r} is "
                            f"{type(value).__name__}, expected str"),
                )

        # Preserved v2 invariants: slug regex, span regex, entity_type whitelist.
        if not _SLUG_RE.match(item["slug"]):
            raise ExtractionParseError(
                f"candidate #{idx} slug fails kebab-case regex",
                error="EXTRACTION_PARSE_ERROR",
                field="slug",
                reason=(f"item #{idx} slug fails regex "
                        "^[a-z0-9][a-z0-9-]{0,62}$"),
            )
        if not _SOURCE_SPAN_RE.match(item["source_span"]):
            raise ExtractionParseError(
                f"candidate #{idx} source_span fails Lstart-Lend regex",
                error="EXTRACTION_PARSE_ERROR",
                field="source_span",
                reason=(f"item #{idx} source_span does not match "
                        "^L\\d+-L\\d+$ (Decision-10)"),
            )
        if item["entity_type"] not in _ALLOWED_ENTITY_TYPES:
            raise ExtractionParseError(
                f"candidate #{idx} entity_type not in allowed set",
                error="EXTRACTION_PARSE_ERROR",
                field="entity_type",
                reason=(f"item #{idx} entity_type not in "
                        f"{sorted(_ALLOWED_ENTITY_TYPES)}"),
            )

        # M-5: optional quote-in-body check.
        if (source_body is not None
                and not os.environ.get("WIKI_EXTRACT_NO_QUOTE_CHECK")):
            if item["source_quote"] not in source_body:
                raise ExtractionParseError(
                    f"candidate #{idx} source_quote not found in body",
                    error="FIELD_QUOTE_NOT_IN_BODY",
                    field="source_quote",
                    reason=(f"item #{idx} source_quote is not a verbatim "
                            "substring of source_body (set "
                            "WIKI_EXTRACT_NO_QUOTE_CHECK=1 to skip)"),
                )


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


# v3.1 (003-v3-04) markdown sanitization helpers — H-7 / Q13 defense in
# depth against prompt-injection-style content surfacing in the concept
# page body or frontmatter.

# Iteration-2 N-5: allow Unicode word chars (Cyrillic, diacritics) by
# anchoring the regex with re.UNICODE flag.
_NAME_ALLOWLIST = re.compile(
    r"^[\w\s\-.,:;()\'\"!?]{1,200}$", flags=re.UNICODE,
)

def _sanitize_name(name: str) -> str:
    """Sanitize a concept name for safe embedding into the H1 + frontmatter.

    Strips leading ``#`` (markdown header injection) and ``-`` / ``---``
    (YAML frontmatter delimiter injection), then enforces the
    `_NAME_ALLOWLIST` regex. If the post-strip string fails the allowlist
    or is empty, raises ``ExtractionParseError(error="INVALID_NAME_FORMAT")``.
    """
    stripped = name.lstrip("#").lstrip("-").strip()
    if not _NAME_ALLOWLIST.match(stripped):
        raise ExtractionParseError(
            "candidate name fails sanitization allowlist",
            error="INVALID_NAME_FORMAT",
            field="name",
            reason=("name contains disallowed characters after stripping "
                    "leading '#'/'-' and trimming whitespace"),
        )
    return stripped


def _sanitize_definition(definition: str) -> str:
    """Sanitize a candidate's definition for safe embedding in concept body.

    Delegates to the shared `_sanitize_markdown_text` (H-4 v3.2 — text-
    only allowlist replacing v3.1's denylist).
    """
    return _sanitize_markdown_text(definition)


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
    orchestrator_id: str = "orchestrator",
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

    v3.1 (003-v3-05 / H-8): the ``orchestrator_id`` parameter populates
    ``canonicalized_by = f"llm:{orchestrator_id}@{today}"``. Defaults to
    the literal string ``"orchestrator"`` so operators who omit
    ``--orchestrator-id`` get an honest unknown rather than a hallucinated
    model attribution (Q9-v3.1).
    """
    existing = _lookup_entity_row(repo, vault_id, candidate["slug"])
    if existing is not None and existing.get("is_candidate") == 0:
        return "confirmed"
    today_iso = today.isoformat() if isinstance(today, date) else str(today)
    canonicalized_by = f"llm:{orchestrator_id}@{today_iso}"
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


_SPAN_REGEX = re.compile(r"^L(\d+)-L(\d+)$", re.ASCII)  # L-2: ASCII-only digits


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


def _build_parser_v3() -> argparse.ArgumentParser:
    """v3.1 argparse surface (Decision-17): two subcommands, calling-agent
    drives synthesis. `prepare` does deterministic recon + idempotency check;
    `apply` consumes operator-synthesized candidates JSON and writes pages +
    entities + manifest. Legacy single-command invocation now fails at
    argparse with a `prepare`/`apply` hint (H-4 BREAKING CHANGE).
    """
    p = argparse.ArgumentParser(
        prog="wiki-extract-concepts",
        description=(
            "Deterministic concept-extraction skill (v3.1). "
            "Calling agent runs `prepare` (recon), synthesises candidates "
            "JSON in its own context, then runs `apply` to write pages + "
            "entities + manifest. BREAKING CHANGE vs v2: legacy single-"
            "command shape is no longer accepted."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True,
                           metavar="{prepare,apply}")

    # ---- prepare subparser ----
    pp = sub.add_parser("prepare",
                        help="Recon + idempotency check; emits JSON envelope.")
    pp.add_argument("--vault", required=True,
                    help="Vault ID (must be registered in vaults table)")
    pp.add_argument("--vault-root", required=True, type=Path,
                    help="Absolute path to vault root directory")
    pp.add_argument("--source-page", required=True,
                    help="Source page slug or relative path within vault")
    pp.add_argument("--db-path", default=None,
                    help="Override global DB path (default: standard XDG location)")

    # ---- apply subparser ----
    pa = sub.add_parser("apply",
                        help="Consume candidates JSON, write pages + manifest.")
    pa.add_argument("--vault", required=True,
                    help="Vault ID (must be registered in vaults table)")
    pa.add_argument("--vault-root", required=True, type=Path,
                    help="Absolute path to vault root directory")
    pa.add_argument("--source-page", required=True,
                    help="Source page slug or relative path within vault")
    pa.add_argument("--db-path", default=None,
                    help="Override global DB path (default: standard XDG location)")
    pa.add_argument("--source-hash", required=True,
                    type=_validate_source_hash,
                    help="sha256 hex (64 lowercase hex chars) of the source "
                         "body, as emitted by `prepare`; mismatch → "
                         "SOURCE_CHANGED_DURING_EXTRACTION (Q5). Case-"
                         "normalized to lowercase at argparse time (C-1).")
    pa.add_argument("--ingest", action="store_true",
                    help="In-process indexer dispatch (Decision-15) — "
                         "call index_from_manifest after manifest emit")
    pa.add_argument("--orchestrator-id",
                    type=_validate_orchestrator_id,
                    default="orchestrator",
                    help="Free-form orchestrator identifier "
                         "(e.g., 'claude-opus-4-7'). Populates "
                         "entities.canonicalized_by. Regex: "
                         f"{_ORCHESTRATOR_ID_RE.pattern}. "
                         "Default: literal 'orchestrator' (Q9-v3.1).")
    cand_group = pa.add_mutually_exclusive_group(required=True)
    cand_group.add_argument("--candidates-file", type=Path, default=None,
                            help="Path to JSON file inside the vault with candidates "
                                 "array (mutex with --candidates-stdin).")
    cand_group.add_argument("--candidates-stdin", action="store_true",
                            help="Read candidates JSON from stdin "
                                 "(mutex with --candidates-file).")
    return p


def prepare(args: argparse.Namespace) -> int:
    """`wiki-extract-concepts prepare` subcommand (v3.1).

    Deterministic recon + idempotency check. Reads the source page, computes
    sha256, queries source_state for is_unchanged, loads known entities, and
    builds a missing_concept_files drift list. Emits a JSON envelope the
    calling orchestrator consumes to decide whether to short-circuit (UC-09
    v3.1 is_unchanged path) or proceed to LLM-driven synthesis + `apply`.

    No LLM call in this path — Decision-17.
    """
    vault_root = args.vault_root.resolve(strict=True)
    src_page = args.source_page

    # H-1 (regression migration from 003-v3-11a): absolute --source-page →
    # INVALID_SOURCE_PATH (distinct from SOURCE_NOT_FOUND so the operator
    # sees the actual problem). Fire BEFORE any other resolution work.
    if _path_is_absolute(src_page):
        return emit({
            "error": "INVALID_SOURCE_PATH",
            "message": (f"--source-page must be a vault-relative slug or "
                        f"path, not absolute ({src_page!r}). Pass the "
                        "page slug (e.g., 'self-improving-agent') or a "
                        "relative path inside --vault-root."),
        }, exit_code=2)

    resolved = _resolve_source_inside_sources(src_page, vault_root)
    if isinstance(resolved, dict):  # error envelope
        return emit(resolved, exit_code=2)
    source_path, source_slug = resolved

    # M-3 + M-5: stat-check size BEFORE read AND read via O_NOFOLLOW so
    # a symlink swap between resolve and read can't redirect to a file
    # outside the vault. ELOOP/race → SOURCE_NOT_FOUND envelope.
    try:
        source_body_bytes = _read_file_bounded(
            source_path, _MAX_SOURCE_BODY_BYTES,
        )
    except _FileTooLargeError:
        return emit({
            "error": "SOURCE_TOO_LARGE",
            "reason": (f"source-page exceeds the {_MAX_SOURCE_BODY_BYTES}-byte "
                       "cap (10 MiB); refuse to read into memory."),
        }, exit_code=2)
    except OSError:
        return emit({
            "error": "SOURCE_NOT_FOUND",
            "reason": (f"source-page {src_page!r} could not be opened "
                       "(symlink swap race or transient I/O error)"),
        }, exit_code=2)
    source_body = source_body_bytes.decode("utf-8")
    source_hash = hashlib.sha256(source_body_bytes).hexdigest()

    repo = make_repo({
        "vault_id": args.vault,
        **({"db_path": args.db_path} if args.db_path else {}),
    })
    try:
        is_unchanged = check_idempotency(repo, args.vault, source_slug, source_hash)
        known = load_known_entities(repo, args.vault)
        known_slugs = [e["slug"] for e in known]

        # M-7: one os.scandir per `_concepts/` dir found in the vault.
        # Course-tier layout (Karpathy / Lessons pattern) puts concept
        # pages under `Lessons/<Course>/_concepts/` — sweep BOTH tiers
        # so the drift report is correct on any layout.
        present_concept_files: set[str] = set()
        for concepts_dir in _all_concepts_dirs(vault_root):
            for entry in os.scandir(concepts_dir):
                if entry.is_file() and entry.name.endswith(".md"):
                    present_concept_files.add(entry.name[:-3])  # strip .md
        missing_concept_files = sorted(
            slug for slug in known_slugs if slug not in present_concept_files
        )

        # M-2 (vdd-multi 2026-05-28): emit RELATIVE source_path instead
        # of absolute. The orchestrator already knows --vault-root and
        # can join. CWE-209: stop leaking operator home directory /
        # vault location into logs.
        try:
            source_path_rel = str(source_path.relative_to(vault_root))
        except ValueError:
            source_path_rel = str(source_path)  # defensive (shouldn't happen)

        return emit({
            "vault_id": args.vault,
            "source_slug": source_slug,
            "source_path": source_path_rel,
            "source_hash": source_hash,
            "is_unchanged": is_unchanged,
            "known_concepts": known,
            "missing_concept_files": missing_concept_files,
        })
    finally:
        repo.close()


class _FileTooLargeError(OSError):
    """Raised by `_read_file_bounded` when fstat shows size > cap."""


def _read_file_bounded(path: Path, cap_bytes: int) -> bytes:
    """Open `path` with O_NOFOLLOW, fstat-check size, read up to cap+1 bytes.

    M-3 / M-5: closes the TOCTOU between `Path.stat().st_size` and a
    subsequent `Path.read_bytes()` AND defends against symlink-swap
    races (O_NOFOLLOW → ELOOP if the path became a symlink after the
    earlier resolve). The fstat-then-bounded-read pattern guarantees
    we never accumulate more than `cap_bytes + 1` bytes from the FD.
    Raises:
      - _FileTooLargeError if fstat shows size > cap OR the read
        produced more than cap bytes.
      - OSError on ELOOP / ENOENT / EACCES (caller maps to envelope).
    """
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        if st.st_size > cap_bytes:
            raise _FileTooLargeError(
                f"file size {st.st_size} > cap {cap_bytes}"
            )
        data = os.read(fd, cap_bytes + 1)
        if len(data) > cap_bytes:
            raise _FileTooLargeError(
                f"read returned > cap {cap_bytes} bytes (TOCTOU growth)"
            )
        return data
    finally:
        os.close(fd)


def _derive_source_project(source_path: Path, vault_root: Path) -> str:
    """Derive the `pages.project` column value for `source_path`.

    TASK 012 / architecture-review C1: delegates to the shared, config-driven
    `layout_config.derive_project_for_path` so the apply-side project matches what
    the reindexer (`iter_pages`) records — the `page_entity_refs` FK on
    `(vault_id, page_slug, page_project) → pages(vault_id, slug, project)`
    requires the two paths to agree. For a Karpathy vault this yields the same
    two-tier result as before (vault-tier → `VAULT_TIER_PROJECT`; course-tier →
    slugified course); for dev/obsidian layouts it follows the layout config
    (previously this hardcoded the Karpathy two-tier walk and would have drifted).
    """
    from scripts.wiki_index.layout_config import derive_project_for_path

    return derive_project_for_path(source_path, vault_root)


def _all_concepts_dirs(vault_root: Path) -> list[Path]:
    """Enumerate every `_concepts/` directory present in `vault_root`.

    Supports both layouts (per `layout.py::COURSE_TIER_DIR`):
    - vault-tier:  `<vault_root>/_concepts/`
    - course-tier: `<vault_root>/Lessons/<Course>/_concepts/`

    Returns only directories that actually exist on disk. Order is
    deterministic (vault-tier first, then course-tier sorted by course
    name) so callers building a `set[slug]` get reproducible behavior.
    """
    from scripts.wiki_index.layout import COURSE_TIER_DIR

    found: list[Path] = []
    vault_tier = vault_root / CONCEPTS_SUBDIR
    if vault_tier.is_dir():
        found.append(vault_tier)
    course_tier_root = vault_root / COURSE_TIER_DIR
    if course_tier_root.is_dir():
        for course_dir in sorted(course_tier_root.iterdir()):
            if not course_dir.is_dir():
                continue
            concepts_dir = course_dir / CONCEPTS_SUBDIR
            if concepts_dir.is_dir():
                found.append(concepts_dir)
    return found


def _resolve_source_inside_sources(
    src_page: str, vault_root: Path,
) -> dict[str, Any] | tuple[Path, str]:
    """Resolve `--source-page` to a real path inside SOME `_sources/`.

    Returns either an error envelope `dict` (caller emits at exit 2) or
    a `(resolved_path, source_slug)` tuple on success.

    Supports both layouts:
    - vault-tier:  `<vault_root>/_sources/<slug>.md`
    - course-tier: `<vault_root>/Lessons/<Course>/_sources/<slug>.md`
      (per `layout.py::COURSE_TIER_DIR` — the Karpathy pattern; real
      operator vaults like `trade-agents` use this exclusively).

    Slug-form lookup tries vault-tier first, then globs course-tier.
    Ambiguous matches (same slug under two different `_sources/`) yield
    `AMBIGUOUS_SOURCE_SLUG` so the operator passes the full path instead.

    Layout invariant: the resolved file MUST live in a directory whose
    name is exactly `SOURCES_SUBDIR` (closes the
    `_sources/../_concepts/foo.md` traversal escape — operator cannot
    drive a `_concepts/` page through extraction by spelling a relative
    path that resolves inside the vault but outside `_sources/`).
    """
    # Slug-form search: try every `_sources/<slug>.md` under the vault.
    # Vault-tier first (deterministic), course-tier glob second.
    candidate_path: Path | None = None
    vault_tier = vault_root / SOURCES_SUBDIR / f"{src_page}.md"
    if vault_tier.is_file():
        candidate_path = vault_tier
    else:
        course_tier_root = vault_root / COURSE_TIER_DIR
        if course_tier_root.is_dir():
            course_matches = sorted(
                course_tier_root.glob(f"*/{SOURCES_SUBDIR}/{src_page}.md")
            )
            course_matches = [p for p in course_matches if p.is_file()]
            if len(course_matches) > 1:
                rels = [str(p.relative_to(vault_root)) for p in course_matches]
                return {
                    "error": "AMBIGUOUS_SOURCE_SLUG",
                    "reason": (f"slug {src_page!r} matches multiple "
                               f"_sources/ entries: {rels}. Pass the full "
                               "vault-relative path instead of the slug."),
                }
            if course_matches:
                candidate_path = course_matches[0]
    # Fall back to treating `src_page` as a vault-relative path verbatim.
    if candidate_path is None:
        candidate_path = vault_root / src_page

    try:
        source_path = candidate_path.resolve(strict=True)
        validate_inside_vault(source_path, vault_root)
    except (FileNotFoundError, PathTraversalError) as e:
        return {
            "error": "SOURCE_NOT_FOUND",
            "reason": f"source-page {src_page!r} not found in vault: {e}",
        }

    # H-1: the resolved file's parent directory MUST be named SOURCES_SUBDIR
    # (regardless of where in the vault tree that `_sources/` lives —
    # vault-tier, course-tier, or any other future layout per `layout.py`).
    # Rejects `_sources/../_concepts/foo.md` traversals that resolve to
    # `_concepts/`, `_entities/`, or any other non-source directory.
    if source_path.parent.name != SOURCES_SUBDIR:
        return {
            "error": "INVALID_SOURCE_PATH",
            "reason": (f"source-page {src_page!r} resolves outside "
                       "a `_sources/` directory (layout invariant: "
                       "inputs live in _sources/ only)"),
        }

    source_slug = source_path.stem
    if not _SLUG_RE.match(source_slug):
        return {
            "error": "INVALID_SOURCE_SLUG",
            "reason": (f"source-page filename {source_slug!r} does not "
                       "yield a valid kebab-case slug "
                       "(^[a-z0-9][a-z0-9-]{0,62}$). Rename the file or "
                       "pass --source-page with the canonical slug."),
        }

    return source_path, source_slug


def _load_candidates(
    args: argparse.Namespace, vault_root: Path,
) -> list[Any]:
    """Load + cap + path-validate + parse the candidates JSON payload.

    Encapsulates the four `apply()` failure modes that fire BEFORE any
    schema validation:

      - `CANDIDATES_TOO_LARGE` (exit 4, H-6 / R-6) — stdin or file payload
        exceeds `_MAX_CANDIDATES_BYTES`. For stdin we read cap+1 bytes via
        `sys.stdin.buffer.read(...)` so the cap holds even under streaming.
      - `INVALID_CANDIDATES_PATH` (exit 2, H-5) — `--candidates-file` does
        not exist OR resolves to a location outside the vault root. Envelope
        emits the operator-supplied path STRING (never the file contents).
      - `EXTRACTION_PARSE_ERROR` (exit 4) — JSON decode error. Envelope
        emits the SDK-style `at line N column M` locator, never the
        offending byte stream (CWE-117 invariant).

    All three are raised as `ExtractionParseError` with `.error` populated
    so the apply() caller can map straight into a JSON envelope.
    """
    if args.candidates_stdin:
        # Risk R-6 mitigation: bound the read so a malicious producer
        # streaming one byte at a time cannot drive memory growth past
        # the cap. cap+1 bytes lets us detect overflow with one check.
        data = sys.stdin.buffer.read(_MAX_CANDIDATES_BYTES + 1)
        if len(data) > _MAX_CANDIDATES_BYTES:
            raise ExtractionParseError(
                "candidates stdin payload exceeds size cap",
                error="CANDIDATES_TOO_LARGE",
                field=None,
                reason=(f"stdin payload > {_MAX_CANDIDATES_BYTES} bytes "
                        "(1 MiB cap)"),
            )
    else:
        candidates_file = args.candidates_file
        # H-5 / M-6 (cross-platform): path-validate BEFORE any read. Both
        # FileNotFoundError and PathTraversalError map to
        # INVALID_CANDIDATES_PATH so the envelope never discloses on-disk
        # existence outside the vault. If the operator passed a relative
        # path, resolve it against vault_root (instead of CWD which would
        # produce inconsistent envelopes across operator shells).
        if not _path_is_absolute(candidates_file):
            candidates_file = vault_root / candidates_file
        try:
            resolved = validate_inside_vault(candidates_file, vault_root)
        except (FileNotFoundError, PathTraversalError):
            raise ExtractionParseError(
                "candidates file is not inside vault root",
                error="INVALID_CANDIDATES_PATH",
                field=None,
                reason=(f"--candidates-file {str(candidates_file)!r} is "
                        "missing or outside --vault-root"),
            ) from None
        # H-2: FIFO/device/socket bypasses stat-cap (st_size=0 for
        # FIFOs/char devices); reject anything that isn't a regular file.
        # M-3/M-5: open the file with O_NOFOLLOW + read at most cap+1
        # bytes from THAT FD so a TOCTOU swap between stat and read
        # cannot exceed the cap. The fstat-then-bounded-read pattern
        # closes both the FIFO bypass and the swap race.
        if not resolved.is_file():
            raise ExtractionParseError(
                "candidates file is not a regular file",
                error="INVALID_CANDIDATES_PATH",
                field=None,
                reason=(f"--candidates-file {str(candidates_file)!r} is "
                        "not a regular file (FIFOs/devices/sockets "
                        "rejected; H-2 bypass guard)"),
            )
        try:
            fd = os.open(resolved, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError:
            # ELOOP if target became a symlink between is_file() and open;
            # EACCES / ENOENT on race. All map to INVALID_CANDIDATES_PATH.
            raise ExtractionParseError(
                "candidates file open failed",
                error="INVALID_CANDIDATES_PATH",
                field=None,
                reason=(f"--candidates-file {str(candidates_file)!r} "
                        "could not be opened (possible symlink-swap race)"),
            ) from None
        try:
            data = os.read(fd, _MAX_CANDIDATES_BYTES + 1)
            if len(data) > _MAX_CANDIDATES_BYTES:
                raise ExtractionParseError(
                    "candidates file exceeds size cap",
                    error="CANDIDATES_TOO_LARGE",
                    field=None,
                    reason=(f"--candidates-file size > "
                            f"{_MAX_CANDIDATES_BYTES} bytes (1 MiB cap)"),
                )
        finally:
            os.close(fd)

    try:
        parsed = json.loads(data.decode("utf-8"))
    except json.JSONDecodeError as e:
        # CWE-117: never echo the raw payload — only the SDK locator.
        raise ExtractionParseError(
            "candidates payload is not valid JSON",
            error="EXTRACTION_PARSE_ERROR",
            field=None,
            reason=f"JSON decode failed at line {e.lineno} column {e.colno}",
        ) from None
    except UnicodeDecodeError:
        raise ExtractionParseError(
            "candidates payload is not valid UTF-8",
            error="EXTRACTION_PARSE_ERROR",
            field=None,
            reason="payload bytes are not decodable as UTF-8",
        ) from None
    if not isinstance(parsed, list):
        raise ExtractionParseError(
            "candidates payload top-level shape is not a JSON array",
            error="EXTRACTION_PARSE_ERROR",
            field=None,
            reason=(f"top-level JSON is {type(parsed).__name__}, "
                    "expected array"),
        )
    return parsed


def _envelope_from_parse_error(
    e: ExtractionParseError,
) -> dict[str, Any]:
    """Build the structured JSON envelope from an ExtractionParseError.

    CWE-117 / CWE-209 invariant: only `.error`, `.field`, `.reason` from the
    exception attrs land in the envelope — never the message string and
    never the offending value. The apply() caller drives the exit code
    off the envelope's `error` key.
    """
    payload: dict[str, Any] = {
        "error": e.error or "EXTRACTION_PARSE_ERROR",
    }
    if e.field is not None:
        payload["field"] = e.field
    if e.reason is not None:
        payload["reason"] = e.reason
    return payload


def apply(args: argparse.Namespace) -> int:
    """`wiki-extract-concepts apply` subcommand (v3.1).

    Consumes operator-synthesised candidates JSON and writes pages +
    entities + manifest. Hash-checks the source body against the
    `--source-hash` emitted by `prepare` so an edit-during-extraction
    race surfaces as a clean exit 2 SOURCE_CHANGED_DURING_EXTRACTION
    envelope (H-1, Q5) instead of corrupting the manifest.

    Exit codes (R-42):
      0 — success (manifest or {extraction, index} envelope)
      2 — input validation (INVALID_SOURCE_PATH, SOURCE_NOT_FOUND,
          INVALID_SOURCE_SLUG, SOURCE_TOO_LARGE,
          SOURCE_CHANGED_DURING_EXTRACTION, INVALID_CANDIDATES_PATH)
      4 — candidates payload errors (CANDIDATES_TOO_LARGE,
          EXTRACTION_PARSE_ERROR, UNKNOWN_FIELD, FIELD_TOO_LONG,
          CANDIDATE_COUNT_OUT_OF_BOUNDS, FIELD_QUOTE_NOT_IN_BODY)
      5 — PARTIAL_INDEX_FAILURE (some concept pages written, indexer
          rejected at least one; source_state NOT updated so a retry is
          safe — C-1 invariant carried forward from v2)
      6 — MANIFEST_INVALID
    """
    vault_root = args.vault_root.resolve(strict=True)

    # Step 1 — load candidates (cap + path-validate + parse).
    try:
        candidates = _load_candidates(args, vault_root)
    except ExtractionParseError as e:
        envelope = _envelope_from_parse_error(e)
        exit_code = 2 if envelope["error"] == "INVALID_CANDIDATES_PATH" else 4
        return emit(envelope, exit_code=exit_code)

    # Step 2 — resolve + read source. Same gating as prepare(): absolute
    # source-page → INVALID_SOURCE_PATH (cross-platform via
    # _path_is_absolute, M-6), escape outside `_sources/` → also
    # INVALID_SOURCE_PATH (H-1 layout invariant), missing →
    # SOURCE_NOT_FOUND, dotted slug → INVALID_SOURCE_SLUG, oversize →
    # SOURCE_TOO_LARGE. Read via O_NOFOLLOW (M-3/M-5).
    src_page = args.source_page
    if _path_is_absolute(src_page):
        return emit({
            "error": "INVALID_SOURCE_PATH",
            "reason": (f"--source-page must be a vault-relative slug or "
                       f"path, not absolute ({src_page!r})."),
        }, exit_code=2)

    resolved = _resolve_source_inside_sources(src_page, vault_root)
    if isinstance(resolved, dict):
        return emit(resolved, exit_code=2)
    source_path, source_slug = resolved

    try:
        source_body_bytes = _read_file_bounded(
            source_path, _MAX_SOURCE_BODY_BYTES,
        )
    except _FileTooLargeError:
        return emit({
            "error": "SOURCE_TOO_LARGE",
            "reason": (f"source-page exceeds the {_MAX_SOURCE_BODY_BYTES}-byte "
                       "cap (10 MiB); refuse to read into memory."),
        }, exit_code=2)
    except OSError:
        return emit({
            "error": "SOURCE_NOT_FOUND",
            "reason": (f"source-page {src_page!r} could not be opened "
                       "(symlink swap race or transient I/O error)"),
        }, exit_code=2)
    source_body = source_body_bytes.decode("utf-8")
    current_hash = hashlib.sha256(source_body_bytes).hexdigest()

    # Step 3 — hash check (H-1, Q5 + C-1). Argparse normalizes
    # --source-hash via _validate_source_hash; this belt-and-braces
    # check defends library/test callers that construct `args` directly
    # (and would otherwise bypass argparse). Envelope emits truncated
    # prefixes only; never the source body or the supplied hash in full.
    supplied_hash = str(args.source_hash).lower()
    if not _SOURCE_HASH_RE.match(supplied_hash):
        return emit({
            "error": "INVALID_SOURCE_HASH",
            "reason": ("--source-hash must be exactly 64 lowercase hex "
                       "chars (sha256 hex digest from `prepare`)"),
        }, exit_code=2)
    if current_hash != supplied_hash:
        return emit({
            "error": "SOURCE_CHANGED_DURING_EXTRACTION",
            "reason": (f"expected={supplied_hash[:16]}, "
                       f"got={current_hash[:16]} "
                       "(source body changed between prepare and apply; "
                       "re-run prepare to refresh)"),
        }, exit_code=2)

    # Step 4 — strict schema validation (incl. optional quote-in-body).
    try:
        _validate_candidates_schema(candidates, source_body=source_body)
    except ExtractionParseError as e:
        return emit(_envelope_from_parse_error(e), exit_code=4)

    # Step 4b (M-4 vdd-multi 2026-05-28): SANITIZATION PRE-FLIGHT. Run
    # the per-candidate sanitizers in a dry pass BEFORE any filesystem /
    # DB mutation. Prevents the original mid-loop failure that left
    # items #0..N-1 committed to disk while item #N raised
    # INVALID_NAME_FORMAT. After this check passes, the write loop's
    # actual sanitizer calls are guaranteed to succeed for the same
    # inputs.
    try:
        _preflight_sanitize(candidates)
    except ExtractionParseError as e:
        return emit(_envelope_from_parse_error(e), exit_code=4)

    # M-9 (vdd-multi 2026-05-28): log a warning when the operator
    # omitted --orchestrator-id, since `entities.canonicalized_by`
    # then records the opaque literal "orchestrator" which is useless
    # for audit/forensics.
    orchestrator_id_val = getattr(args, "orchestrator_id", "orchestrator")
    if orchestrator_id_val == "orchestrator":
        logger.warning(
            "apply: --orchestrator-id not supplied; entity provenance "
            "will record opaque literal 'orchestrator'. Pass "
            "--orchestrator-id <model-id> for an auditable canonicalized_by."
        )

    # Step 5+ — write pages, upsert entities + refs, build manifest,
    # optionally dispatch, then update idempotency state. The C-1
    # invariant is preserved: update_idempotency_state() runs ONLY when
    # the dispatch (if requested) reports zero failures.
    today = date.today()
    repo = make_repo({
        "vault_id": args.vault,
        **({"db_path": args.db_path} if args.db_path else {}),
    })
    # Symmetric to the source-side H-1 layout invariant: write concept
    # pages to the `_concepts/` sibling of the source page's `_sources/`.
    # For vault-tier sources → `<vault_root>/_concepts/`. For course-tier
    # sources → `<vault_root>/Lessons/<Course>/_concepts/`. Keeps the
    # course tier's inputs and outputs co-located on disk, matching the
    # operator's existing vault layout.
    target_concepts_dir = source_path.parent.parent / CONCEPTS_SUBDIR

    # Derive `pages.project` from the source path so the
    # `page_entity_refs` FK on `(vault_id, page_slug, page_project)`
    # matches the indexer's recorded value. Vault-tier → VAULT_TIER_PROJECT;
    # course-tier → slugified course-directory name.
    source_project = _derive_source_project(source_path, vault_root)

    try:
        try:
            known = load_known_entities(repo, args.vault)
            known_slugs = {e["slug"] for e in known}
            create_list, mention_list = classify_candidates(candidates, known_slugs)

            for cand in create_list:
                _target, file_action = write_concept_page(
                    vault_root, cand, source_slug, today, vault_id=args.vault,
                    concepts_dir=target_concepts_dir,
                )
                cand["file_write_action"] = file_action
                cand["entity_action"] = upsert_extracted_entity(
                    repo, args.vault, cand, source_slug, today,
                    orchestrator_id=orchestrator_id_val,
                )

            upsert_entity_refs(
                repo, args.vault, source_slug, source_project,
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
        except ExtractionParseError as e:
            # v2 parity: downstream raises (e.g. _parse_source_span on an
            # inverted L10-L5 range that the regex validator passed) map
            # to exit 4 with the structured envelope rather than an
            # uncaught traceback.
            return emit(_envelope_from_parse_error(e), exit_code=4)

        if args.ingest:
            try:
                summary = dispatch_to_indexer(
                    manifest, args.vault, vault_root, args.db_path,
                )
            except WikiIngestError as e:
                return emit({"error": "MANIFEST_INVALID",
                             "reason": str(e)}, exit_code=6)
            if summary.get("failed"):
                # C-1 invariant: do NOT update_idempotency_state on
                # partial failure so the next run retries.
                return emit({
                    "action": "partial",
                    "error": "PARTIAL_INDEX_FAILURE",
                    "extraction": manifest,
                    "index": summary,
                }, exit_code=5)
            if not _try_update_idempotency_state(
                repo, args.vault, source_slug, current_hash, manifest,
            ):
                return emit({
                    "action": "partial",
                    "error": "IDEMPOTENCY_UPDATE_FAILED",
                    "extraction": manifest,
                    "index": summary,
                    "reason": ("pages/entities/indexer all committed, "
                               "but source_state update failed; next "
                               "run will safely re-extract"),
                }, exit_code=5)
            return emit({"extraction": manifest, "index": summary})

        if not _try_update_idempotency_state(
            repo, args.vault, source_slug, current_hash, manifest,
        ):
            # Pages + entities + refs committed; only source_state row
            # update failed. Treat as PARTIAL (exit 5) so the operator
            # knows retry-safety is degraded.
            return emit({
                "action": "partial",
                "error": "IDEMPOTENCY_UPDATE_FAILED",
                "extraction": manifest,
                "reason": ("pages/entities/refs committed, but "
                           "source_state update failed; next run will "
                           "safely re-extract"),
            }, exit_code=5)
        return emit(manifest)
    finally:
        repo.close()


def _preflight_sanitize(candidates: list[Any]) -> None:
    """M-4: run per-candidate sanitizers in a dry pass.

    Raises `ExtractionParseError` on the first failure. After this
    function returns cleanly, the subsequent `write_concept_page` loop
    is guaranteed to succeed for the same inputs (same sanitizers run
    over the same data → same outcome). Closes the partial-commit
    window where item #N's sanitization failure left items #0..N-1
    written to disk.
    """
    for idx, cand in enumerate(candidates):
        try:
            _sanitize_name(str(cand["name"]))
            _sanitize_definition(str(cand["definition"]))
            _sanitize_markdown_text(str(cand["source_quote"]))
            if not _SOURCE_SPAN_RE.match(str(cand["source_span"])):
                raise ExtractionParseError(
                    f"candidate #{idx} source_span fails preflight regex",
                    error="INVALID_SOURCE_SPAN",
                    field="source_span",
                    reason=("source_span must match ^L\\d+-L\\d+$ "
                            "before embedding into _concepts body"),
                )
        except ExtractionParseError:
            raise


def _try_update_idempotency_state(
    repo: Any, vault_id: str, source_slug: str, current_hash: str,
    manifest: dict[str, Any],
) -> bool:
    """H-3: wrap `update_idempotency_state` in defensive try/except.

    Returns True on success, False if the DB UPDATE failed (caller maps
    to IDEMPOTENCY_UPDATE_FAILED envelope). Without this wrap, an
    OperationalError ("database locked", "disk full") after pages /
    entities / refs are committed leaves the caller with a Python
    traceback on stderr + a successfully-built manifest on stdout =
    split-brain. Treating the failure as PARTIAL keeps the envelope
    contract intact and signals "retry is safe" to the operator.
    """
    import sqlite3
    try:
        update_idempotency_state(repo, vault_id, source_slug, current_hash)
        return True
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
        logger.warning(
            "apply: update_idempotency_state failed for "
            "(vault=%s, source_slug=%s): %s — emitting "
            "IDEMPOTENCY_UPDATE_FAILED envelope, manifest preserved",
            vault_id, source_slug, type(e).__name__,
        )
        return False


def main(argv: list[str] | None = None) -> int:
    """CLI entry-point (v3.1). Dispatches to `prepare` or `apply` subcommand.

    BREAKING CHANGE vs v2: legacy single-command shape (no subcommand) is
    rejected at argparse with a usage error pointing at `{prepare,apply}`.
    See 003-v3-11a (deletion of legacy-shape main() tests) + this bead's
    dispatch shim.
    """
    args = _build_parser_v3().parse_args(argv)
    if args.cmd == "prepare":
        return prepare(args)
    if args.cmd == "apply":
        return apply(args)
    # argparse(required=True) makes this unreachable, but mypy-strict
    # likes the safety net.
    return 1


if __name__ == "__main__":
    sys.exit(main())
