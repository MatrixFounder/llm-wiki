"""Error types + envelope helpers for the extraction rail (TASK 063).

Dependency **SINK** — imports nothing from the package, so every leaf may import
it without a cycle. `ExtractionParseError` is package-owned: every raiser and
catcher imports THIS definition. Do not re-define it in another leaf; two classes
with the same name is how an `except` clause silently stops catching.
"""
from __future__ import annotations

from typing import Any


class ExtractionParseError(Exception):
    """The candidates payload is malformed or violates the contract. Bound to
    exit code 4 — and exit 4 means **ZERO files written**, always.

    `.error` is the sub-envelope code (ONTOLOGY_VIOLATION, UNRESOLVED_REF,
    IN_BATCH_SLUG_COLLISION, …); `.field` names the offending field but NEVER
    carries its value (CWE-117 — the value is model-authored text that may hold
    control characters); `.reason` is a short structured reason; `.violations`
    carries the FULL list, because G1 lists every violation at once rather than
    failing on the first — a caller who has to re-run to find the second error
    will re-run with a fabricated fix for the first.
    """

    def __init__(
        self,
        message: str,
        *,
        error: str | None = None,
        field: str | None = None,
        reason: str | None = None,
        violations: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.error = error
        self.field = field
        self.reason = reason
        self.violations = violations or []


class PreflightError(Exception):
    """The vault cannot hold typed pages at all — bound to exit code 2, raised by
    `prepare` BEFORE any reasoning is asked for.

    Refusing here (rather than at write time) is the entire point of G4: it costs
    an operator one message; the alternative costs them a decision page that was
    written, never indexed, and raised no lint issue.
    """

    def __init__(self, message: str, *, error: str, detail: str = "") -> None:
        super().__init__(message)
        self.error = error
        self.detail = detail


def envelope_from_parse_error(exc: ExtractionParseError) -> dict[str, Any]:
    """The exit-4 error envelope. Value-free: field NAMES and stable codes only."""
    env: dict[str, Any] = {
        "action": "refused",
        "error": exc.error or "EXTRACTION_PARSE_ERROR",
        "message": str(exc),
        "written": [],  # stated, not implied: a refusal writes NOTHING
    }
    if exc.field:
        env["field"] = exc.field
    if exc.reason:
        env["reason"] = exc.reason
    if exc.violations:
        env["violations"] = exc.violations
    return env
