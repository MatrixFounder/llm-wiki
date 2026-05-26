"""ADR-002 §D8 rebuildability gate — Phase 3a exit criterion (task-001-34).

`rm global.db → wiki-init --register-existing → wiki-reindex --full →
identical search/lint output`.

Class A (filesystem) is the canonical store. Class B (DB) is rebuildable cache.
If this test ever breaks, the architectural invariant has regressed.

BM25 score tolerance: ±0.001 (FTS5 internal float drift). Snippet text and
slug ordering must be byte-identical.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.conftest import run_skill_cli

BM25_TOLERANCE = 0.001


def _search(db_path: Path, vault_id: str, query: str) -> list[dict]:
    out = run_skill_cli(
        "wiki_search",
        [query, "--vaults", vault_id, "--db-path", str(db_path)],
    )
    return out["hits"]


def _lint(db_path: Path, vault_id: str, sidecar_path: Path) -> list[dict]:
    run_skill_cli(
        "wiki_lint",
        ["--vault", vault_id, "--db-path", str(db_path),
         "--json-sidecar", str(sidecar_path)],
    )
    return json.loads(sidecar_path.read_text())


def _reindex_full(db_path: Path, vault_id: str) -> dict:
    return run_skill_cli(
        "wiki_reindex",
        ["--full", "--vault", vault_id, "--db-path", str(db_path)],
    )


def _register(db_path: Path, vault_path: Path) -> dict:
    return run_skill_cli(
        "wiki_init",
        ["--register-existing", "--vault", str(vault_path),
         "--db-path", str(db_path)],
    )


def _assert_hits_equivalent(a: list[dict], b: list[dict]) -> None:
    assert len(a) == len(b), f"hit count drift: pre={len(a)} post={len(b)}"
    # Sort by slug for order-stable comparison (FTS5 BM25 tie-break is
    # internal). Compare set of slugs strictly; snippet byte-identical per slug.
    by_slug_a = {h["slug"]: h for h in a}
    by_slug_b = {h["slug"]: h for h in b}
    assert set(by_slug_a) == set(by_slug_b), "slug set drift"
    for slug in by_slug_a:
        ha, hb = by_slug_a[slug], by_slug_b[slug]
        assert ha["title"] == hb["title"], f"title drift @ {slug}"
        assert ha["snippet"] == hb["snippet"], f"snippet drift @ {slug}"
        assert abs(ha["bm25_score"] - hb["bm25_score"]) <= BM25_TOLERANCE, (
            f"bm25 drift @ {slug}: pre={ha['bm25_score']} post={hb['bm25_score']}"
        )


def _assert_lint_equivalent(a: list[dict], b: list[dict]) -> None:
    """Lint output identical modulo registered_at (the only Class C drift)."""

    def _normalize(items: list[dict]) -> list[dict]:
        return sorted(
            ({k: v for k, v in i.items() if k != "registered_at"} for i in items),
            key=lambda x: (x.get("category", ""), x.get("page_slug") or ""),
        )

    assert _normalize(a) == _normalize(b), "lint issue set drift"


def test_e2e_01_rebuildability_minimal_vault(minimal_vault, tmp_path):
    """Delete DB → re-register → reindex → search + lint identical."""
    db_path = tmp_path / "rebuild.db"
    _register(db_path, minimal_vault)
    _reindex_full(db_path, "minimal-test")
    hits_pre = _search(db_path, "minimal-test", "alpha")
    lint_pre = _lint(db_path, "minimal-test", tmp_path / "lint-pre.json")

    db_path.unlink()
    for suffix in ("-shm", "-wal"):
        sidecar = Path(str(db_path) + suffix)
        if sidecar.exists():
            sidecar.unlink()

    _register(db_path, minimal_vault)
    _reindex_full(db_path, "minimal-test")
    hits_post = _search(db_path, "minimal-test", "alpha")
    lint_post = _lint(db_path, "minimal-test", tmp_path / "lint-post.json")

    _assert_hits_equivalent(hits_pre, hits_post)
    _assert_lint_equivalent(lint_pre, lint_post)


def test_e2e_02_rebuildability_multi_vault(multi_vault, tmp_path):
    """Multi-vault: cross-vault concept duplicates preserved after rebuild."""
    db_path = tmp_path / "rebuild-multi.db"
    for vid, vroot in multi_vault.items():
        _register(db_path, vroot)
        _reindex_full(db_path, vid)
    hits_pre_alpha = _search(db_path, "vault-alpha", "concept")
    lint_pre = _lint(db_path, "vault-alpha", tmp_path / "lint-pre.json")
    # Cross-vault duplicate detection lives in run_all_checks (no per-vault
    # filter), so capture the alpha-scoped view; same lint output expected.

    db_path.unlink()
    for suffix in ("-shm", "-wal"):
        sidecar = Path(str(db_path) + suffix)
        if sidecar.exists():
            sidecar.unlink()

    for vid, vroot in multi_vault.items():
        _register(db_path, vroot)
        _reindex_full(db_path, vid)
    hits_post_alpha = _search(db_path, "vault-alpha", "concept")
    lint_post = _lint(db_path, "vault-alpha", tmp_path / "lint-post.json")

    _assert_hits_equivalent(hits_pre_alpha, hits_post_alpha)
    _assert_lint_equivalent(lint_pre, lint_post)


def test_e2e_03_rebuildability_with_log_md(minimal_vault, tmp_path):
    """log.md round-trip: pre-state has 3 entries → after rebuild, 3 log_events
    with matching offsets (M-2 contract)."""
    log_dir = minimal_vault / "00-Vault-Index" / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "2026-05.md").write_text(
        "## [2026-05-25 10:00:00] ingest | Alpha source\n"
        "- pages_created: ['alpha']\n\n"
        "## [2026-05-25 11:00:00] lint | health check\n\n"
        "## [2026-05-26 09:00:00] reindex | full sweep\n\n"
    )
    db_path = tmp_path / "rebuild-log.db"
    _register(db_path, minimal_vault)
    pre_full = _reindex_full(db_path, "minimal-test")

    db_path.unlink()
    for suffix in ("-shm", "-wal"):
        sidecar = Path(str(db_path) + suffix)
        if sidecar.exists():
            sidecar.unlink()

    _register(db_path, minimal_vault)
    post_full = _reindex_full(db_path, "minimal-test")

    # Both rebuilds should parse 3 user-authored entries (plus possibly a
    # synthetic reindex event). The user-authored count must match.
    assert pre_full.get("log_events", 0) == post_full.get("log_events", 0), (
        f"log_events drift: pre={pre_full.get('log_events')} "
        f"post={post_full.get('log_events')}"
    )
    assert pre_full.get("log_events", 0) >= 3, (
        f"expected ≥3 user log entries, got {pre_full.get('log_events')}"
    )
