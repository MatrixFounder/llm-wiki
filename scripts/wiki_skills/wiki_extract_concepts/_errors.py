"""Error types + envelope helper for the concept extractor (TASK 016 leaf).

Dependency **sink** — imports nothing from the package. `ExtractionParseError`
is package-owned (every raiser/catcher imports this single definition; do NOT
re-define it in another leaf). `WikiIngestError` is NOT here — it is re-exported
from `_manifest_consumer` by the facade and must keep its source identity.
"""
from __future__ import annotations

from typing import Any


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
