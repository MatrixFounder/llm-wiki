"""Stub tests for scripts/wiki_index/factory.py (task-001-05).

Covers:
- TC-E2E-01: `make_repo({...})` returns a usable repo handle.
- TC-UNIT-01: `_is_icloud_path` stub returns False for any input.
- TC-UNIT-02: `_resolve_db_path` returns a deterministic stub path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.wiki_index.factory import ICloudRejectionError
from scripts.wiki_index.repository import IndexRepository
from scripts.wiki_index.sqlite_repository import SQLiteRepository


# =============================================================================
# TC-E2E-01 — make_repo returns a usable repo handle
# =============================================================================


# Real make_repo tests are in tests/test_factory_impl.py (task-001-20).
# Stub tests previously here are obsolete and have been removed.


# =============================================================================
# Real impl tests for _is_icloud_path / _resolve_db_path are in
# tests/test_icloud_detection.py (task-001-14). The stub-specific tests
# previously living here are obsolete and have been removed.
# =============================================================================


# =============================================================================
# ICloudRejectionError class shape is final
# =============================================================================


def test_icloud_rejection_error_is_runtime_error_subclass():
    """ICloudRejectionError shape is final per task notes — no change in task-001-14."""
    err = ICloudRejectionError("vault at /tmp/iCloud~ is forbidden")
    assert isinstance(err, RuntimeError)
    assert "iCloud" in str(err)


def test_icloud_rejection_error_can_be_raised_and_caught():
    """Raising and catching ICloudRejectionError works as expected."""
    with pytest.raises(ICloudRejectionError, match="forbidden"):
        raise ICloudRejectionError("path is forbidden")
