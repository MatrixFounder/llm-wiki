"""TASK 008 / bead 008-04 — verify-state idempotency DAL (R-8.6).

`check_verify_state` / `record_verify_state` are thin typed wrappers over the
generic `source_state` table (`source_kind='verification'`, `scope=verification_slug`,
`key='verify_hash'`), the exact sibling of TASK 007's query-state pair. No new
table, no DDL; skills never touch `source_state` SQL directly (NFR-2).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from scripts.wiki_index.models import Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository


def _repo(tmp_path: Path) -> SQLiteRepository:
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    for vid in ("vlt-a", "vlt-b"):
        repo.register_vault(Vault(
            vault_id=vid, name=vid, root_path=tmp_path / vid,
            schema_version="5.0", registered_at=datetime(2026, 5, 29),
        ))
    return repo


def test_round_trip(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.record_verify_state("vlt-a", "vq1", "abc")
    assert repo.check_verify_state("vlt-a", "vq1") == "abc"
    repo.close()


def test_missing_is_none(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert repo.check_verify_state("vlt-a", "missing") is None
    repo.close()


def test_upsert_updates_single_row(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.record_verify_state("vlt-a", "vq1", "abc")
    repo.record_verify_state("vlt-a", "vq1", "def")
    assert repo.check_verify_state("vlt-a", "vq1") == "def"
    n = repo._connect().execute(
        "SELECT COUNT(*) AS n FROM source_state WHERE vault_id='vlt-a' "
        "AND source_kind='verification' AND scope='vq1'").fetchone()["n"]
    assert n == 1  # UPSERT, not a second row
    repo.close()


def test_multi_vault_isolation(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.record_verify_state("vlt-a", "vq1", "x")
    assert repo.check_verify_state("vlt-b", "vq1") is None
    repo.close()


def test_null_value_guard(tmp_path: Path, monkeypatch: object) -> None:
    """A corrupt `value IS NULL` row → None (re-verify), not a crash (mirrors
    check_query_state L-V3.2). `source_state.value` is `TEXT NOT NULL`, so NULL
    can't be inserted — simulate the corrupt row via a stub cursor."""
    repo = _repo(tmp_path)

    class _StubCur:
        def execute(self, *_a: object, **_k: object) -> "_StubCur":
            return self

        def fetchone(self) -> dict[str, object]:
            return {"value": None}

    monkeypatch.setattr(repo, "_connect", lambda: _StubCur())  # type: ignore[attr-defined]
    assert repo.check_verify_state("vlt-a", "vq1") is None


def test_source_kind_isolation(tmp_path: Path) -> None:
    """A `source_kind='query'` row with the same scope must NOT satisfy
    `check_verify_state` (different source_kind partition)."""
    repo = _repo(tmp_path)
    repo.record_query_state("vlt-a", "vq1", "query-hash")
    assert repo.check_verify_state("vlt-a", "vq1") is None
    repo.close()
