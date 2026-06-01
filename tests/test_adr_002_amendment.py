"""TASK 012-08 — acceptance pin for the ADR-002 §D8 TASK-012 amendment.

The amendment (drafted in the Architecture phase) registers the Class-B
"rebuildable markdown" sub-case and the well-defined rebuildability invariant
that PW-H (012-09) depends on. This test machine-checks it is present + well-formed
so the gate-before-PW-H ordering (C-7) cannot silently regress.
"""

from __future__ import annotations

from pathlib import Path

ADR = Path(__file__).parent.parent / "docs" / "adr" / "ADR-002-multi-vault-bottleneck-corrections.md"


def _adr_text() -> str:
    return ADR.read_text(encoding="utf-8")


def test_task_012_amendment_present() -> None:
    text = _adr_text()
    assert "Amendment (TASK 012" in text


def test_class_b_rebuildable_markdown_subcase_defined() -> None:
    text = _adr_text()
    for needle in ("rebuildable markdown", "docs/issues/", "wiki-index-render --auto-indexes"):
        assert needle in text, f"§D8 TASK-012 amendment missing: {needle!r}"


def test_rebuildability_invariant_is_well_defined() -> None:
    """Architecture-review M2: the invariant must pin determinism + the single
    excluded volatile line, so PW-H's byte-identity round-trip is meaningful."""
    # Normalize blockquote markers + line wraps so multi-word phrases match.
    norm = " ".join(_adr_text().replace(">", " ").split())
    for needle in ("GENERATED-AT", ".wiki/state.json", "tiebreaker",
                   "pure deterministic function"):
        assert needle in norm, f"rebuildability invariant under-specified: {needle!r}"


def test_zero_ddl_clause_present() -> None:
    text = _adr_text()
    assert "tag-route" in text
    assert "user_version` stays **5**" in text or "user_version stays 5" in text
