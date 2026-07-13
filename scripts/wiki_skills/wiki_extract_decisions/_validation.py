"""Candidate schema + the ontology validators (TASK 063).

BEAD 063-04 (STUB): the constants and the signatures. 063-06 fills the schema,
063-08 the G1 ontology check, 063-10 the G2 ref resolution.
"""
from __future__ import annotations

from typing import Any

# Payload ceilings. OVERFLOW REFUSES, NEVER TRUNCATES (R-063-11): a truncated
# candidate batch is a batch whose last decision vanished without a word.
CANDIDATES_MAX_BYTES = 512 * 1024
FIELD_MAX_CHARS = 8_000


def validate_candidates(payload: Any, *, body: str) -> list[dict[str, Any]]:
    """STUB (063-04) → LOGIC (063-06). Strict-validate the candidates payload and
    return the candidate list.

    Will enforce: known fields only; per-field length caps; a MANDATORY verbatim
    `source_quote` that must appear IN `body` (the anti-fabrication mechanism —
    and the `WIKI_EXTRACT_NO_QUOTE_CHECK` escape hatch is deliberately NOT
    honoured: an escape hatch on an anti-fabrication check is the fabrication
    path); and `CANDIDATE_COUNT_MIN = 0`, so an EMPTY set is SUCCESS.
    """
    raise NotImplementedError("063-06")


def validate_ontology(
    candidates: list[dict[str, Any]],
    *,
    ontology: dict[str, Any],
    db_classes: dict[str, str],
) -> list[dict[str, Any]]:
    """STUB (063-04) → LOGIC (063-08). G1 — every candidate against the ontology
    contract, BEFORE any write. Returns ALL violations at once (never fails on
    the first).

    Checks: class ∈ roster; each edge's DOMAIN; each edge's RANGE — including for
    a target OUTSIDE the batch, whose class is resolved from `db_classes` (the
    index), because an edge to an existing page is exactly where a range error
    hides; and `status` ∈ that class's enum.
    """
    raise NotImplementedError("063-08")
