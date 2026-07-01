"""Unit tests for `scripts.wiki_skills._manifest_consumer`.

TASK 003 v2 / I-7.0 — exercises the public surface of the neutral
manifest-consumer module directly. (Its former co-consumer `wiki_enrich` and the
`test_wiki_enrich.py` back-compat mirror were retired in TASK 047; the module now
serves `wiki-extract-concepts --ingest` only.)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.wiki_skills._manifest_consumer import (
    WikiIngestError,
    validate_manifest,
)


def _build_manifest(vault_id: str, vault_root: Path, written: list[str]) -> dict:
    return {
        "status": "ok",
        "vault_id": vault_id,
        "vault_root": str(vault_root),
        "source": {"slug": "test-source", "hash": "deadbeef"},
        "written": [
            {"path": p, "action": "created", "kind": "concept", "scope": "vault"}
            for p in written
        ],
        "created": written,
        "touched": [],
        "contradictions": 0,
        "log_event": {
            "event_ts": "2026-05-27T12:00:00",
            "event_type": "ingest",
            "subject": "Neutral-consumer test",
            "log_md_byte_offset": 0,
        },
    }


def test_validate_manifest_happy_path(minimal_vault: Path) -> None:
    """Happy path: a v1.1-compatible manifest passes silently.

    Uses `_sources/alpha.md` from the minimal-vault fixture to satisfy the
    R-26 in-vault containment check.
    """
    m = _build_manifest("minimal-test", minimal_vault, ["_sources/alpha.md"])
    validate_manifest(m, "minimal-test", minimal_vault)


def test_validate_manifest_rejects_non_ok_status(tmp_path: Path) -> None:
    bad = {"status": "error"}
    with pytest.raises(WikiIngestError, match=r"status != 'ok'"):
        validate_manifest(bad, "test-vault", tmp_path)


def test_validate_manifest_rejects_vault_id_mismatch(tmp_path: Path) -> None:
    m = _build_manifest("wrong-vault", tmp_path, [])
    with pytest.raises(WikiIngestError, match=r"vault_id"):
        validate_manifest(m, "test-vault", tmp_path)


def test_validate_manifest_rejects_path_traversal(minimal_vault: Path) -> None:
    """A manifest claiming `../../etc/passwd` is rejected by the R-26 guard."""
    m = _build_manifest("minimal-test", minimal_vault, ["../../etc/passwd"])
    with pytest.raises(WikiIngestError, match=r"vault containment"):
        validate_manifest(m, "minimal-test", minimal_vault)
