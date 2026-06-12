"""TASK 030 bead 030-03 (R-030-2b, closes P-1) — stage-then-flush chunked-tx
`reindex_full`.

RED-first: on the pre-030-03 engine the commit count is ~2N per-page commits
(AC-2.4 fails), the F-6 equal-hash collision corner keeps the FIRST file's
`file_path` (AC-2.6 fails), and derivation I/O runs outside any instrumentable
chunk (the lock-hold guard is vacuous pre-fix but RED via the commit count).

Q-030-5 (v3) semantics pinned: staging errors isolate OUTSIDE the txn;
mid-flush DML errors commit-with-chunk + `skipped`; a fatal COMMIT failure
rolls the chunk back with FTS staying in sync with `pages`.
"""

from __future__ import annotations

import math
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

import scripts.wiki_index.reindex as reindex_mod
from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_source.manual import ManualSourceAdapter

# Documented fixed overhead C on the CONSTRAINED fixture (zero log.md files,
# zero entities/aliases, karpathy-base custom layout with auto_indexes=[]):
#   1 — Step-1 wipe COMMIT
# Empirically verified (trace of every explicit txn statement): Step-3
# `_recompute_mentions`, the Step-4 synthetic `append_log_event`, and
# begin/finish_batch_run all ride AUTOCOMMIT on this connection — they emit no
# explicit BEGIN/COMMIT, so they do not contribute to C. Any future change
# that adds an explicit txn to those paths will (correctly) trip this pin.
FIXED_OVERHEAD_C = 1


def _layout(root: Path, n_globs: int = 1) -> None:
    globs = "".join(
        f"  - {{glob: 'd{i}/*.md', type: summary, project: '_vault_'}}\n"
        for i in range(n_globs))
    (root / ".wiki").mkdir(parents=True)
    (root / ".wiki" / "layout.yaml").write_text(
        "schema_version: '2.0'\nlayout: karpathy\nslug_strategy: identity\n"
        f"paths:\n{globs}"
        "type_mapping:\n  summary: {db_type: summary, tag: null}\n",
        encoding="utf-8",
    )


def _vault_with_n(root: Path, n: int) -> None:
    _layout(root)
    (root / "d0").mkdir()
    for i in range(n):
        (root / "d0" / f"p{i:03d}.md").write_text(
            f"# P{i}\n\nbody {i} links [[p000]]\n", encoding="utf-8")


def _repo(tmp_path: Path, root: Path, vid: str) -> SQLiteRepository:
    r = SQLiteRepository(tmp_path / "g.db")
    r.apply_schema()
    r.register_vault(Vault(vault_id=vid, name=vid, root_path=root,
                           schema_version="2.0",
                           registered_at=datetime(2026, 5, 1)))
    return r


class _TxTrace:
    """Counts explicit transaction statements via set_trace_callback."""

    def __init__(self) -> None:
        self.begins = 0
        self.commits = 0
        self.in_txn = False

    def __call__(self, stmt: str) -> None:
        s = stmt.strip().upper()
        if s.startswith("BEGIN"):          # both BEGIN and BEGIN IMMEDIATE
            self.begins += 1
            self.in_txn = True
        elif s.startswith("COMMIT"):
            self.commits += 1
            self.in_txn = False
        elif s.startswith("ROLLBACK"):
            self.in_txn = False


# --------------------------------------------------------------------------- #
# AC-2.4 — exact commit count: ceil(N/K) + C, at N<K and N%K==0
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("n_files", [3, 8])  # K=4 → 1 chunk / 2 chunks
def test_commit_count_is_chunked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, n_files: int,
) -> None:
    monkeypatch.setattr(reindex_mod, "REINDEX_TX_CHUNK", 4)
    root = tmp_path / "vault"
    _vault_with_n(root, n_files)
    r = _repo(tmp_path, root, "chunk-count")
    trace = _TxTrace()
    try:
        r._connect().set_trace_callback(trace)
        result = reindex_full(r, "chunk-count")
        r._connect().set_trace_callback(None)
        assert result["pages"] == n_files
        expected = math.ceil(n_files / 4) + FIXED_OVERHEAD_C
        assert trace.commits == expected, (
            f"commits={trace.commits}, expected ceil({n_files}/4)+{FIXED_OVERHEAD_C}"
            f"={expected} — per-page commits must be gone (P-1)")
    finally:
        r.close()


def test_byte_cap_forces_early_flush(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-2.7: with a tiny byte cap every staged page exceeds it → one chunk
    (commit) per file even though K is large."""
    monkeypatch.setattr(reindex_mod, "REINDEX_TX_CHUNK", 500)
    monkeypatch.setattr(reindex_mod, "REINDEX_TX_CHUNK_BYTES", 10)
    root = tmp_path / "vault"
    _vault_with_n(root, 3)
    r = _repo(tmp_path, root, "chunk-bytes")
    trace = _TxTrace()
    try:
        r._connect().set_trace_callback(trace)
        result = reindex_full(r, "chunk-bytes")
        r._connect().set_trace_callback(None)
        assert result["pages"] == 3
        assert trace.commits == 3 + FIXED_OVERHEAD_C
    finally:
        r.close()


def test_empty_vault_full_reindex(tmp_path: Path) -> None:
    """AC-2.7 N=0: no chunk commits, envelope sane."""
    root = tmp_path / "vault"
    _layout(root)
    r = _repo(tmp_path, root, "chunk-empty")
    try:
        result = reindex_full(r, "chunk-empty")
        assert result["pages"] == 0
        assert result["skipped"] == []
    finally:
        r.close()


# --------------------------------------------------------------------------- #
# AC-2.4b — lock-hold guard: NO file I/O between BEGIN IMMEDIATE and COMMIT
# --------------------------------------------------------------------------- #


def test_no_file_io_inside_chunk_txn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reindex_mod, "REINDEX_TX_CHUNK", 4)
    root = tmp_path / "vault"
    _vault_with_n(root, 10)
    r = _repo(tmp_path, root, "lockhold")
    trace = _TxTrace()
    violations: list[str] = []
    real_fetch = ManualSourceAdapter.fetch

    def guarded_fetch(self: ManualSourceAdapter, item: Any) -> Any:
        if trace.in_txn:
            violations.append(str(item.source_path))
        return real_fetch(self, item)

    monkeypatch.setattr(ManualSourceAdapter, "fetch", guarded_fetch)
    try:
        r._connect().set_trace_callback(trace)
        result = reindex_full(r, "lockhold")
        r._connect().set_trace_callback(None)
        assert result["pages"] == 10
        assert violations == [], (
            "derive_indexed_page (file I/O) ran inside an open write txn — "
            "stage-then-flush violated (Q-030-5 / arch-review HIGH-2)")
    finally:
        r.close()


# --------------------------------------------------------------------------- #
# AC-2.1 — row parity: chunked rebuild == public-DAL per-page replay
# --------------------------------------------------------------------------- #


def _dump(r: SQLiteRepository, vid: str) -> dict[str, list[tuple[Any, ...]]]:
    conn = r._connect()
    pages = conn.execute(
        "SELECT slug, project, type, title, file_path, tldr, file_hash, "
        "body_excerpt, is_frozen FROM pages WHERE vault_id=? "
        "ORDER BY slug, project", (vid,)).fetchall()
    refs = conn.execute(
        "SELECT page_slug, page_project, entity_slug, ref_type, line_start "
        "FROM page_entity_refs WHERE vault_id=? "
        "ORDER BY page_slug, entity_slug, ref_type", (vid,)).fetchall()
    fts = conn.execute(
        "SELECT p.slug FROM pages_fts f JOIN pages p ON p.id = f.rowid "
        "WHERE f.pages_fts MATCH 'body' AND p.vault_id=? ORDER BY p.slug",
        (vid,)).fetchall()
    return {"pages": [tuple(x) for x in pages],
            "refs": [tuple(x) for x in refs],
            "fts": [tuple(x) for x in fts]}


def test_row_parity_chunked_vs_public_dal_replay(tmp_path: Path) -> None:
    """Post-030-02 the public `upsert_page`/`replace_refs` ARE the old per-page
    path — replaying the same derivation through them must yield identical
    pages/refs/FTS rows (volatile timestamp columns excluded)."""
    from scripts.wiki_index.layout_config import iter_pages, resolve_layout_config
    from scripts.wiki_index.reindex import derive_indexed_page
    from scripts.wiki_source.base import SourceItem

    root = tmp_path / "vault"
    _vault_with_n(root, 7)
    # chunked engine
    r1 = _repo(tmp_path, root, "parity-vault")
    reindex_full(r1, "parity-vault")
    dump_chunked = _dump(r1, "parity-vault")
    r1.close()
    (tmp_path / "g.db").unlink()
    # public-DAL replay (the pre-030 per-page path)
    r2 = _repo(tmp_path, root, "parity-vault")
    cfg = resolve_layout_config(root)
    adapter = ManualSourceAdapter()
    cite_skipped: list[dict[str, Any]] = []
    for disc in iter_pages(root, cfg):
        item = SourceItem(kind="manual", source_path=disc.path,
                          vault_root=root, vault_id="parity-vault")
        out, page, _fm, refs = derive_indexed_page(
            adapter, item, cfg, disc, "parity-vault", cite_skipped)
        r2.upsert_page(page)
        r2.replace_refs("parity-vault", out.page_slug, out.project, refs)
    dump_replay = _dump(r2, "parity-vault")
    r2.close()
    assert dump_chunked == dump_replay


# --------------------------------------------------------------------------- #
# AC-2.6 — F-6 equal-hash within-batch collision: DB row aligns with `kept`
# --------------------------------------------------------------------------- #


def test_equal_hash_collision_file_path_matches_kept(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    _layout(root, n_globs=2)
    (root / "d0").mkdir(); (root / "d1").mkdir()
    body = "# Same\n\nidentical bytes\n"
    (root / "d0" / "01.md").write_text(body, encoding="utf-8")
    (root / "d1" / "01.md").write_text(body, encoding="utf-8")  # byte-identical
    r = _repo(tmp_path, root, "eqhash")
    try:
        result = reindex_full(r, "eqhash")
        cols = result["slug_collisions"]
        assert len(cols) == 1
        assert cols[0]["kept"] == "d1/01.md"        # later POSIX-sorted
        row = r._connect().execute(
            "SELECT file_path FROM pages WHERE vault_id=? AND slug='01'",
            ("eqhash",)).fetchone()
        # RED pre-fix: the hash pre-SELECT short-circuits → 'd0/01.md' survives,
        # MISREPORTING vs the collision record. Post-fix: ON CONFLICT fires →
        # the DB row aligns with `kept` (Q-030-5, deliberate delta).
        assert row["file_path"] == cols[0]["kept"]
    finally:
        r.close()


# --------------------------------------------------------------------------- #
# Q-030-5 error paths
# --------------------------------------------------------------------------- #


def test_mid_flush_dml_error_isolated_per_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(i) refs DML raises for ONE slug → that file lands in `skipped`, the
    chunk commits, every other file is present, run reports success."""
    monkeypatch.setattr(reindex_mod, "REINDEX_TX_CHUNK", 10)
    root = tmp_path / "vault"
    _vault_with_n(root, 5)
    r = _repo(tmp_path, root, "midflush")
    real = SQLiteRepository._replace_refs_in_txn

    def poisoned(self: SQLiteRepository, conn: sqlite3.Connection, vid: str,
                 slug: str, project: str, refs: Any) -> None:
        if slug == "p002":
            raise sqlite3.OperationalError("poisoned refs DML")
        real(self, conn, vid, slug, project, refs)

    monkeypatch.setattr(SQLiteRepository, "_replace_refs_in_txn", poisoned)
    try:
        result = reindex_full(r, "midflush")
        assert any("p002" in s["path"] for s in result["skipped"])
        assert result["pages"] == 4
        slugs = {row["slug"] for row in r._connect().execute(
            "SELECT slug FROM pages WHERE vault_id=?", ("midflush",)).fetchall()}
        # Q-030-5 A2: the poisoned file's PAGE row committed with the chunk
        # (statement-level atomicity; equivalent to today's committed-partial).
        assert slugs == {"p000", "p001", "p002", "p003", "p004"}
    finally:
        r.close()


class _CommitBomb:
    """Connection proxy: raises on the Nth COMMIT, passes everything else."""

    def __init__(self, conn: sqlite3.Connection, fail_on_commit: int) -> None:
        self._conn = conn
        self._commits = 0
        self._fail_on = fail_on_commit

    def execute(self, sql: str, *a: Any) -> Any:
        if sql.strip().upper().startswith("COMMIT"):
            self._commits += 1
            if self._commits == self._fail_on:
                raise sqlite3.OperationalError("disk I/O error (injected)")
        return self._conn.execute(sql, *a)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


def test_fatal_commit_failure_rolls_back_chunk_fts_in_sync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(ii) a COMMIT failure is OUTSIDE the per-file catch → chunk rolls back,
    batch_runs records 'failed', FTS row count stays equal to pages (no desync)."""
    root = tmp_path / "vault"
    _vault_with_n(root, 3)
    r = _repo(tmp_path, root, "fatal")
    real_conn = r._connect()
    bomb = _CommitBomb(real_conn, fail_on_commit=2)  # 1=wipe, 2=first chunk
    monkeypatch.setattr(r, "_connect", lambda: bomb)
    try:
        with pytest.raises(sqlite3.OperationalError):
            reindex_full(r, "fatal")
        n_pages = real_conn.execute(
            "SELECT COUNT(*) AS c FROM pages WHERE vault_id='fatal'").fetchone()["c"]
        n_fts = real_conn.execute(
            "SELECT COUNT(*) AS c FROM pages_fts WHERE vault_id='fatal'").fetchone()["c"]
        assert n_pages == 0 and n_fts == 0          # chunk rolled back, in sync
        status = real_conn.execute(
            "SELECT status FROM batch_runs WHERE vault_id='fatal' "
            "ORDER BY id DESC LIMIT 1").fetchone()["status"]
        assert status == "failed"
    finally:
        monkeypatch.undo()
        r.close()


def test_fatal_midloop_flush_failure_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sarcasmotron 030-03 CRITICAL regression pin: a fatal failure on a
    MID-LOOP chunk (the only kind a real >K-page vault hits) must PROPAGATE —
    not be swallowed into `skipped` with double-counted pages, a 'success'
    batch, and an uncleared buffer replayed O(N²). Also pins the HIGH: the
    ORIGINAL error survives (no ROLLBACK-masking) in batch_runs.notes."""
    monkeypatch.setattr(reindex_mod, "REINDEX_TX_CHUNK", 2)
    root = tmp_path / "vault"
    _vault_with_n(root, 5)                     # K=2 → mid-loop chunks exist
    r = _repo(tmp_path, root, "fatal-mid")
    real_conn = r._connect()
    bomb = _CommitBomb(real_conn, fail_on_commit=2)  # 1=wipe, 2=FIRST MID-LOOP chunk
    monkeypatch.setattr(r, "_connect", lambda: bomb)
    try:
        with pytest.raises(sqlite3.OperationalError, match="disk I/O error"):
            reindex_full(r, "fatal-mid")
        n_pages = real_conn.execute(
            "SELECT COUNT(*) AS c FROM pages WHERE vault_id='fatal-mid'"
        ).fetchone()["c"]
        n_fts = real_conn.execute(
            "SELECT COUNT(*) AS c FROM pages_fts WHERE vault_id='fatal-mid'"
        ).fetchone()["c"]
        assert n_pages == 0 and n_fts == 0      # rolled back, in sync
        row = real_conn.execute(
            "SELECT status, notes FROM batch_runs WHERE vault_id='fatal-mid' "
            "ORDER BY id DESC LIMIT 1").fetchone()
        assert row["status"] == "failed"
        assert "disk I/O error" in (row["notes"] or "")  # original error preserved
    finally:
        monkeypatch.undo()
        r.close()
