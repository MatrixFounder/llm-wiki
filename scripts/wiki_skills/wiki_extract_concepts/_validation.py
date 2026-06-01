"""Validation and sanitization leaf for wiki-extract-concepts (TASK 016).

Dependency rule: imports ONLY stdlib + `._errors` + `scripts.wiki_skills._common`.
No import from the facade (`__init__`) or any other leaf.
"""
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Any

from scripts.wiki_skills._common import (
    sanitize_markdown_text as _sanitize_markdown_text,
)
from ._errors import ExtractionParseError


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

# H-8 (003-v3-05): operator-supplied attribution string that flows into
# `entities.canonicalized_by`. Strict charset: lowercase alphanumerics +
# `._:@-` (allows model names like `claude-opus-4-7@vendor`). Cap at
# 64 chars; rejects newlines, control chars, and shell metachars.
_ORCHESTRATOR_ID_RE = re.compile(r"^[a-z0-9._:@-]{1,64}$")

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

# v3.1 (003-v3-04) markdown sanitization helpers — H-7 / Q13 defense in
# depth against prompt-injection-style content surfacing in the concept
# page body or frontmatter.

# Iteration-2 N-5: allow Unicode word chars (Cyrillic, diacritics) by
# anchoring the regex with re.UNICODE flag.
_NAME_ALLOWLIST = re.compile(
    r"^[\w\s\-.,:;()\'\"!?]{1,200}$", flags=re.UNICODE,
)

_SPAN_REGEX = re.compile(r"^L(\d+)-L(\d+)$", re.ASCII)  # L-2: ASCII-only digits


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
