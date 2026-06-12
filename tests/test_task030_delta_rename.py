"""TASK 030 bead 030-01 (R-030-1, closes DF-029-1) — rename-aware `--delta`.

RED-first under `tdd-strict`: every test below describes the POST-fix contract.
On the pre-fix engine the core tests fail (the mtime gate at reindex.py:429-430
skips any mtime-preserved new path; `new_path_ingested` doesn't exist; a stale
`UNIQUE(vault_id, file_path)` conflict crashes the whole run).

Covers UC-30-1 main + A1..A8 and AC-1.1..1.9 (TASK 030 v3).
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

import pytest

from scripts.wiki_index.lint import run_all_checks
from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_delta, reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository

OLD = time.time() - 86400  # well before any post-full cutoff


def _layout(root: Path, paths_yaml: str, slug_strategy: str = "identity") -> None:
    (root / ".wiki").mkdir(parents=True)
    (root / ".wiki" / "layout.yaml").write_text(
        f"schema_version: '2.0'\nlayout: karpathy\nslug_strategy: {slug_strategy}\n"
        f"paths:\n{paths_yaml}"
        "type_mapping:\n  summary: {db_type: summary, tag: null}\n",
        encoding="utf-8",
    )


def _write_old(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    os.utime(p, (OLD, OLD))
    return p


def _repo(tmp_path: Path, root: Path, vid: str) -> SQLiteRepository:
    r = SQLiteRepository(tmp_path / "g.db")
    r.apply_schema()
    r.register_vault(Vault(vault_id=vid, name=vid, root_path=root,
                           schema_version="2.0", registered_at=datetime(2026, 5, 1)))
    return r


def _file_path_of(r: SQLiteRepository, vid: str, slug: str) -> str | None:
    row = r._connect().execute(
        "SELECT file_path FROM pages WHERE vault_id=? AND slug=?", (vid, slug),
    ).fetchone()
    return row["file_path"] if row else None


def _row_count(r: SQLiteRepository, vid: str) -> int:
    return int(r._connect().execute(
        "SELECT COUNT(*) AS c FROM pages WHERE vault_id=?", (vid,)).fetchone()["c"])


# --------------------------------------------------------------------------- #
# AC-1.1 — the 029-06 live repro as a regression e2e
# --------------------------------------------------------------------------- #


def test_e2e_rename_with_inbound_links_absorbed_by_delta(tmp_path: Path) -> None:
    """Rename a note with 2 inbound wikilinks preserving mtime; neighbours are
    link-rewritten (fresh mtime). One `--delta` → lint: orphan-link 0,
    missing-in-db 0; envelope lists the renamed rel in `new_path_ingested`."""
    root = tmp_path / "vault"
    _layout(root, "  - {glob: 'notes/*.md', type: summary, project: '_vault_'}\n")
    _write_old(root, "notes/target.md", "# Target\n\nbody\n")
    _write_old(root, "notes/n1.md", "# N1\n\nsee [[target]]\n")
    _write_old(root, "notes/n2.md", "# N2\n\nalso [[target]]\n")
    r = _repo(tmp_path, root, "e2e-ren")
    try:
        reindex_full(r, "e2e-ren")
        base = [i for i in run_all_checks(r, vaults=["e2e-ren"])
                if i.category in ("orphan-link", "missing-in-db")]
        assert base == []
        # app-side rename: mtime PRESERVED; neighbours rewritten with fresh mtime
        (root / "notes" / "target.md").rename(root / "notes" / "renamed-note.md")
        fresh = time.time() + 60
        for n in ("n1.md", "n2.md"):
            p = root / "notes" / n
            p.write_text(p.read_text(encoding="utf-8").replace(
                "[[target]]", "[[renamed-note]]"), encoding="utf-8")
            os.utime(p, (fresh, fresh))
        result = reindex_delta(r, "e2e-ren")
        assert result["new_path_ingested"] == ["notes/renamed-note.md"]  # AC-1.4
        assert result["deleted"] == 1          # old (target, _vault_) row
        assert result["touched"] == 3          # renamed + 2 neighbours
        post = [i for i in run_all_checks(r, vaults=["e2e-ren"])
                if i.category in ("orphan-link", "missing-in-db")]
        assert post == []                      # the DF-029-1 symptom is gone
    finally:
        r.close()


# --------------------------------------------------------------------------- #
# AC-1.2 / AC-1.9 — A1 path-only move (content unchanged) + convergence
# --------------------------------------------------------------------------- #


def test_a1_same_key_move_refreshes_file_path_and_converges(tmp_path: Path) -> None:
    """Dir move preserving (slug, project) AND content: the upsert short-circuits
    "unchanged", so the fix's targeted refresh must update `file_path` — and the
    SECOND delta must be a true no-op (AC-1.9; without the refresh this loops)."""
    root = tmp_path / "vault"
    _layout(root,
            "  - {glob: 'a/*.md', type: summary, project: '_vault_'}\n"
            "  - {glob: 'b/*.md', type: summary, project: '_vault_'}\n")
    _write_old(root, "a/01.md", "# One\n\nsee [[other]]\n")
    _write_old(root, "a/other.md", "# Other\n\nx\n")
    r = _repo(tmp_path, root, "a1-move")
    try:
        reindex_full(r, "a1-move")
        (root / "b").mkdir()
        (root / "a" / "01.md").rename(root / "b" / "01.md")  # mtime preserved
        result = reindex_delta(r, "a1-move")
        assert result["new_path_ingested"] == ["b/01.md"]
        assert result["slug_collisions"] == []           # L-2 stays green
        assert _row_count(r, "a1-move") == 2             # no row churn
        assert _file_path_of(r, "a1-move", "01") == "b/01.md"   # AC-1.2
        refs = r._connect().execute(
            "SELECT entity_slug FROM page_entity_refs WHERE vault_id=? AND page_slug=?",
            ("a1-move", "01")).fetchall()
        assert {row["entity_slug"] for row in refs} == {"other"}  # refs intact
        # AC-1.9 — convergence: second delta is a TRUE no-op
        again = reindex_delta(r, "a1-move")
        assert again["touched"] == 0
        assert again["new_path_ingested"] == []
    finally:
        r.close()


# --------------------------------------------------------------------------- #
# AC-1.3 — A2 composite: mtime-preserved rename INTO a cross-batch collision
# --------------------------------------------------------------------------- #


def test_a2_rename_into_collision_one_directed_record(tmp_path: Path) -> None:
    """b/02.md is renamed (mtime-preserved) to b/01.md, colliding with the
    UNTOUCHED prior row from a/01.md → exactly ONE correctly-directed
    `slug_collisions` record; the seeded∩ingested=∅ invariant holds (the seeded
    row's path is in the DB set by definition, so it is never 'new')."""
    root = tmp_path / "vault"
    _layout(root,
            "  - {glob: 'a/*.md', type: summary, project: '_vault_'}\n"
            "  - {glob: 'b/*.md', type: summary, project: '_vault_'}\n")
    _write_old(root, "a/01.md", "# A1\n\nx\n")
    _write_old(root, "b/02.md", "# B2\n\ny\n")
    r = _repo(tmp_path, root, "a2-col")
    try:
        reindex_full(r, "a2-col")
        (root / "b" / "02.md").rename(root / "b" / "01.md")  # mtime preserved
        # snapshot the pre-delta DB path set — the seeded-rows superset
        pre_paths = {row["file_path"] for row in r._connect().execute(
            "SELECT file_path FROM pages WHERE vault_id=?", ("a2-col",)).fetchall()}
        result = reindex_delta(r, "a2-col")
        cols = result["slug_collisions"]
        assert len(cols) == 1                                  # no double-count
        assert cols[0]["kept"] == "b/01.md" and cols[0]["dropped"] == "a/01.md"
        assert result["new_path_ingested"] == ["b/01.md"]
        # AC-1.3 invariant, asserted DIRECTLY at the PATH level (the key-level
        # phrasing in the original bead spec is unsatisfiable in this very
        # scenario — the seeded KEY is the ingested file's key; the disjointness
        # that holds by construction is over PATHS; correction recorded in
        # TASK.md): seeded rows' file_paths ⊆ pre-delta DB paths, and a new-path
        # ingest requires rel ∉ that set.
        assert set(result["new_path_ingested"]).isdisjoint(pre_paths)
        assert result["deleted"] == 1                          # old (02) row orphaned
        assert _file_path_of(r, "a2-col", "01") == "b/01.md"
    finally:
        r.close()


# --------------------------------------------------------------------------- #
# AC-1.6 — A4 stale-row UNIQUE(file_path) conflict: per-file isolation, both orders
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("conflict_rel,real_rel,expect_skip", [
    # conflict file sorts BEFORE the stale row's real file → IntegrityError
    # isolated per-file; the rest of the run completes.
    ("a/cc.md", "a/zz.md", True),
    # real file sorts FIRST → its upsert frees the path → no error at all.
    ("z/cc.md", "a/aa.md", False),
])
def test_a4_stale_file_path_conflict_is_isolated(
    tmp_path: Path, conflict_rel: str, real_rel: str, expect_skip: bool,
) -> None:
    root = tmp_path / "vault"
    _layout(root,
            "  - {glob: 'a/*.md', type: summary, project: '_vault_'}\n"
            "  - {glob: 'm/*.md', type: summary, project: '_vault_'}\n"
            "  - {glob: 'z/*.md', type: summary, project: '_vault_'}\n")
    real = _write_old(root, real_rel, "# Real\n\nx\n")
    _write_old(root, "m/ok.md", "# OK\n\ny\n")
    r = _repo(tmp_path, root, "a4-stale")
    try:
        reindex_full(r, "a4-stale")
        # Simulate legacy drift: the real file's row claims the FUTURE conflict path.
        r._connect().execute(
            "UPDATE pages SET file_path=? WHERE vault_id=? AND slug=?",
            (conflict_rel, "a4-stale", real.stem))
        # New file appears at the claimed path (fresh mtime — ordinary ingest),
        # deriving a DIFFERENT slug ('cc') than the row holding the path.
        p = root / conflict_rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# CC\n\nz\n", encoding="utf-8")
        result = reindex_delta(r, "a4-stale")           # MUST NOT raise (RED: crashes)
        if expect_skip:
            assert any(conflict_rel in s["path"] for s in result["skipped"])
            assert _file_path_of(r, "a4-stale", "cc") is None  # isolated, not ingested
        else:
            assert result["skipped"] == []
            assert _file_path_of(r, "a4-stale", "cc") == conflict_rel
        # the untouched sibling is never collateral damage
        assert _file_path_of(r, "a4-stale", "ok") == "m/ok.md"
    finally:
        r.close()


# --------------------------------------------------------------------------- #
# AC-1.7 — A6 case-only rename (lowercasing vs identity layouts)
# --------------------------------------------------------------------------- #


def test_a6_case_only_rename_lowercasing_layout_one_wave(tmp_path: Path) -> None:
    """Under a lowercasing slug strategy a case-only rename keeps (slug, project)
    → ONE wave: re-ingest hits "unchanged" + targeted file_path refresh; no row
    churn; second delta converges (AC-1.9)."""
    root = tmp_path / "vault"
    _layout(root, "  - {glob: 'n/*.md', type: summary, project: '_vault_'}\n",
            slug_strategy="transliterate")
    _write_old(root, "n/foo.md", "# Foo\n\nbody\n")
    r = _repo(tmp_path, root, "a6-case")
    try:
        reindex_full(r, "a6-case")
        os.rename(root / "n" / "foo.md", root / "n" / "Foo.md")  # case-only, mtime kept
        result = reindex_delta(r, "a6-case")
        assert result["new_path_ingested"] == ["n/Foo.md"]
        assert _row_count(r, "a6-case") == 1                     # no churn
        assert _file_path_of(r, "a6-case", "foo") == "n/Foo.md"  # refreshed
        again = reindex_delta(r, "a6-case")
        assert again["touched"] == 0 and again["new_path_ingested"] == []
    finally:
        r.close()


def test_a6_case_only_rename_identity_layout_is_ordinary_rename(tmp_path: Path) -> None:
    """Under `identity` the slug changes case → an ordinary rename: new row +
    orphan-delete of the old; still converges."""
    root = tmp_path / "vault"
    _layout(root, "  - {glob: 'n/*.md', type: summary, project: '_vault_'}\n")
    _write_old(root, "n/foo.md", "# Foo\n\nbody\n")
    r = _repo(tmp_path, root, "a6-id")
    try:
        reindex_full(r, "a6-id")
        os.rename(root / "n" / "foo.md", root / "n" / "Foo.md")
        result = reindex_delta(r, "a6-id")
        assert result["new_path_ingested"] == ["n/Foo.md"]
        assert result["deleted"] == 1
        assert _row_count(r, "a6-id") == 1
        assert _file_path_of(r, "a6-id", "Foo") == "n/Foo.md"
        again = reindex_delta(r, "a6-id")
        assert again["touched"] == 0 and again["new_path_ingested"] == []
    finally:
        r.close()


# --------------------------------------------------------------------------- #
# A7 — rename + STALE-mtime content edit (cp -p class): ONE ingest, M-1 holds
# --------------------------------------------------------------------------- #


def test_a7_rename_plus_stale_mtime_edit_single_ingest(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    _layout(root,
            "  - {glob: 'a/*.md', type: summary, project: '_vault_'}\n"
            "  - {glob: 'b/*.md', type: summary, project: '_vault_'}\n")
    _write_old(root, "a/01.md", "# v1\n\nsee [[r1]]\n")
    r = _repo(tmp_path, root, "a7-edit")
    try:
        reindex_full(r, "a7-edit")
        _write_old(root, "b/01.md", "# v2\n\nsee [[r2]]\n")  # edited + stale mtime
        (root / "a" / "01.md").unlink()
        # M-1 pin, mechanism updated post-/vdd-multi (sanctioned): delta now
        # writes refs via the txn-free `_replace_refs_in_txn` inside ONE
        # per-file transaction (LOGIC-MED atomicity fix), so the counter wraps
        # the helper, not the public method.
        calls: list[tuple[str, str]] = []
        orig = SQLiteRepository._replace_refs_in_txn

        def counting(self: SQLiteRepository, conn: object, vault_id: str,
                     slug: str, project: str, refs: object) -> None:
            calls.append((slug, project))
            orig(self, conn, vault_id, slug, project, refs)  # type: ignore[arg-type]

        SQLiteRepository._replace_refs_in_txn = counting  # type: ignore[method-assign,assignment]
        try:
            result = reindex_delta(r, "a7-edit")
        finally:
            SQLiteRepository._replace_refs_in_txn = orig  # type: ignore[method-assign]
        assert result["touched"] == 1
        assert calls.count(("01", "_vault_")) == 1            # M-1: exactly ONE
        refs = r._connect().execute(
            "SELECT entity_slug FROM page_entity_refs WHERE vault_id=? AND page_slug=?",
            ("a7-edit", "01")).fetchall()
        assert {row["entity_slug"] for row in refs} == {"r2"}  # v2 content won
    finally:
        r.close()


# --------------------------------------------------------------------------- #
# AC-1.8 — empty vault + fresh-vault first delta (Q-030-3)
# --------------------------------------------------------------------------- #


def test_empty_vault_delta_noop(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    r = _repo(tmp_path, root, "empty-v")
    try:
        result = reindex_delta(r, "empty-v")
        assert result["touched"] == 0 and result["deleted"] == 0
        assert result["new_path_ingested"] == []
    finally:
        r.close()


def test_fresh_vault_first_delta_ingests_whole_vault(tmp_path: Path) -> None:
    """Q-030-3: files older than `registered_at`, never indexed — the first
    `--delta` now ingests them (index reflects disk)."""
    root = tmp_path / "vault"
    _layout(root, "  - {glob: 'n/*.md', type: summary, project: '_vault_'}\n")
    _write_old(root, "n/one.md", "# One\n\nx\n")
    _write_old(root, "n/two.md", "# Two\n\ny\n")
    r = _repo(tmp_path, root, "fresh-v")
    try:
        result = reindex_delta(r, "fresh-v")
        assert result["touched"] == 2
        assert result["new_path_ingested"] == ["n/one.md", "n/two.md"]  # sorted
        assert _row_count(r, "fresh-v") == 2
    finally:
        r.close()


# --------------------------------------------------------------------------- #
# A8 — persistently-failing new-path file: retried + re-reported, never fatal
# --------------------------------------------------------------------------- #


def test_a8_persistently_failing_file_rereported_every_delta(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    _layout(root, "  - {glob: 'n/*.md', type: summary, project: '_vault_'}\n")
    _write_old(root, "n/broken.md", "---\ntype: bizarro\ntitle: B\n---\n\nx\n")
    r = _repo(tmp_path, root, "a8-fail")
    try:
        for _ in range(2):  # every run, not only when touched
            result = reindex_delta(r, "a8-fail")
            assert any("broken.md" in s["path"] for s in result["skipped"])
            assert result["touched"] == 0
        assert _row_count(r, "a8-fail") == 0
    finally:
        r.close()


# --------------------------------------------------------------------------- #
# Concept-page boundary (UC-30-1 postcondition note): entities refresh on --full
# --------------------------------------------------------------------------- #


def test_concept_rename_pages_coherent_entities_on_full_only(tmp_path: Path) -> None:
    root = tmp_path / "vault"  # karpathy default layout (no .wiki override)
    _write_old(root, "_concepts/foo.md",
               "---\ntype: concept\ntitle: Foo\n---\n\nbody\n")
    r = _repo(tmp_path, root, "ent-b")
    try:
        reindex_full(r, "ent-b")
        (root / "_concepts" / "foo.md").rename(root / "_concepts" / "bar.md")
        reindex_delta(r, "ent-b")
        # pages/link layer coherent via --delta:
        assert _file_path_of(r, "ent-b", "bar") == "_concepts/bar.md"
        assert _file_path_of(r, "ent-b", "foo") is None
        # entities layer: documented boundary — stale until --full
        ent = r._connect().execute(
            "SELECT slug FROM entities WHERE vault_id=?", ("ent-b",)).fetchall()
        assert {row["slug"] for row in ent} == {"foo"}       # still the old one
        reindex_full(r, "ent-b")
        ent2 = r._connect().execute(
            "SELECT slug FROM entities WHERE vault_id=?", ("ent-b",)).fetchall()
        assert {row["slug"] for row in ent2} == {"bar"}      # --full refreshes
    finally:
        r.close()


# --------------------------------------------------------------------------- #
# AC-1.4 — `--all-vaults` aggregate: summed total, per-vault lists in results[]
# --------------------------------------------------------------------------- #


def test_all_vaults_delta_aggregates_new_path_total(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts.wiki_skills.wiki_reindex import main as reindex_main
    db = tmp_path / "g.db"
    r = SQLiteRepository(db)
    r.apply_schema()
    for vid in ("vault-one", "vault-two"):
        root = tmp_path / vid
        _layout(root, "  - {glob: 'n/*.md', type: summary, project: '_vault_'}\n")
        _write_old(root, "n/stale.md", f"# {vid}\n\nx\n")
        r.register_vault(Vault(vault_id=vid, name=vid, root_path=root,
                               schema_version="2.0",
                               registered_at=datetime(2026, 5, 1)))
    r.close()
    rc = reindex_main(["--delta", "--all-vaults", "--db-path", str(db)])
    assert rc == 0
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["new_path_ingested_total"] == 2
    assert all(r_["new_path_ingested"] == ["n/stale.md"] for r_ in envelope["results"])


# --------------------------------------------------------------------------- #
# /vdd-multi 030 post-ship fixes — regression pins
# --------------------------------------------------------------------------- #


def test_vddmulti_delta_midfile_failure_is_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LOGIC-MED: a transient `sqlite3.Error` in the refs leg used to COMMIT the
    page (new hash/FTS) while refs stayed stale — and the file was never
    retried (in `db_file_paths`, mtime ≤ advanced cutoff): permanent incoherence
    lint cannot see. Post-fix the per-file txn rolls the WHOLE file back —
    CONSISTENT-stale (old row + old refs), skipped once, run succeeds."""
    import sqlite3 as _sq

    root = tmp_path / "vault"
    _layout(root, "  - {glob: 'a/*.md', type: summary, project: '_vault_'}\n")
    f = _write_old(root, "a/01.md", "# v1\n\nsee [[alpha]]\n")
    r = _repo(tmp_path, root, "atomic-d")
    try:
        reindex_full(r, "atomic-d")
        old_hash = r._connect().execute(
            "SELECT file_hash FROM pages WHERE vault_id='atomic-d' AND slug='01'"
        ).fetchone()["file_hash"]
        # edit: [[alpha]] -> [[beta]], fresh mtime
        f.write_text("# v2\n\nsee [[beta]]\n", encoding="utf-8")
        import time as _t
        os.utime(f, (_t.time() + 60, _t.time() + 60))
        orig = SQLiteRepository._replace_refs_in_txn

        def failing(self: SQLiteRepository, conn: object, vault_id: str,
                    slug: str, project: str, refs: object) -> None:
            raise _sq.OperationalError("database is locked (injected)")

        monkeypatch.setattr(SQLiteRepository, "_replace_refs_in_txn", failing)
        result = reindex_delta(r, "atomic-d")
        monkeypatch.setattr(SQLiteRepository, "_replace_refs_in_txn", orig)
        assert any("01.md" in s["path"] for s in result["skipped"])
        row = r._connect().execute(
            "SELECT file_hash, body_excerpt FROM pages "
            "WHERE vault_id='atomic-d' AND slug='01'").fetchone()
        assert row["file_hash"] == old_hash          # page NOT half-updated
        assert "beta" not in row["body_excerpt"]      # consistent-stale
        refs = r._connect().execute(
            "SELECT entity_slug FROM page_entity_refs "
            "WHERE vault_id='atomic-d' AND page_slug='01'").fetchall()
        assert {x["entity_slug"] for x in refs} == {"alpha"}  # refs match the row
    finally:
        r.close()


def test_vddmulti_full_broken_frontmatter_single_skip(tmp_path: Path) -> None:
    """LOGIC-LOW: a frontmatter value surviving `_json_safe` but not JSON-
    serializable (YAML `!!binary` → bytes) used to be skipped TWICE (once at the
    accounting dump AFTER staging, once at flush). Accounting now precedes the
    append → exactly ONE skip, file not in DB."""
    root = tmp_path / "vault"
    _layout(root, "  - {glob: 'n/*.md', type: summary, project: '_vault_'}\n")
    p = root / "n" / "broken.md"
    p.parent.mkdir(parents=True)
    p.write_text(
        "---\ntype: summary\ntitle: B\nblob: !!binary aGk=\n---\n\nbody\n",
        encoding="utf-8")
    r = _repo(tmp_path, root, "binfm")
    try:
        result = reindex_full(r, "binfm")
        broken_skips = [s for s in result["skipped"] if "broken.md" in s["path"]]
        assert len(broken_skips) == 1                 # was 2
        assert _row_count(r, "binfm") == 0
    finally:
        r.close()
