"""TASK 007 / bead 007-03 — query-state DAL (`check_query_state` /
`record_query_state`, R-6.6).

Thin typed wrappers over the generic `source_state` table
(`source_kind='query'`) — no new table, no raw SQL in any skill. Backs
`wiki-query`'s idempotency (`prepare` `is_unchanged` + `apply` record).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from scripts.wiki_index.models import Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository


def _repo(tmp_path: Path) -> SQLiteRepository:
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    for vid in ("vault-one", "vault-two"):
        repo.register_vault(Vault(
            vault_id=vid, name=vid, root_path=tmp_path / vid,
            schema_version="4.0", registered_at=datetime(2026, 5, 29),
        ))
    return repo


def test_record_then_check_roundtrip(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.record_query_state("vault-one", "q1", "abc123")
    assert repo.check_query_state("vault-one", "q1") == "abc123"
    repo.close()


def test_check_missing_returns_none(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert repo.check_query_state("vault-one", "nope") is None
    repo.close()


def test_record_upserts_not_duplicates(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.record_query_state("vault-one", "q1", "first")
    repo.record_query_state("vault-one", "q1", "second")
    assert repo.check_query_state("vault-one", "q1") == "second"
    # exactly one row
    n = repo._connect().execute(
        "SELECT COUNT(*) AS n FROM source_state "
        "WHERE vault_id='vault-one' AND source_kind='query' AND scope='q1'"
    ).fetchone()["n"]
    assert n == 1
    repo.close()


def test_multi_vault_isolation(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.record_query_state("vault-one", "q1", "x")
    assert repo.check_query_state("vault-two", "q1") is None
    repo.close()


def test_defensive_null_value_returns_none(
    tmp_path: Path, monkeypatch: object,
) -> None:
    """A corrupt `value IS NULL` row is treated as absent (re-synthesise), not a
    crash (mirrors check_idempotency L-V3.2). `source_state.value` is
    `TEXT NOT NULL`, so NULL can't be inserted — simulate the corrupt row via a
    stub cursor, exactly as the extract-concepts L-V3.2 regression does."""
    repo = _repo(tmp_path)

    class _StubCur:
        def execute(self, *_a: object, **_k: object) -> "_StubCur":
            return self

        def fetchone(self) -> dict[str, object]:
            return {"value": None}

    monkeypatch.setattr(repo, "_connect", lambda: _StubCur())  # type: ignore[attr-defined]
    assert repo.check_query_state("vault-one", "qnull") is None

