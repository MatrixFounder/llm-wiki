"""TASK 030 bead 030-05 (R-030-3/6, closes R-X1-OBS-WALK) — `iter_pages`
single-pass rewrite: traversal counts, depth, and the 030-04 carry-forward
conformance cases.

RED-first on the per-glob engine: AC-3.3 (each dir scandir'd EXACTLY once; fat
karpathy subtrees ZERO; `**/_raw/**` subtrees pruned to ZERO) and AC-3.8
(≥1500-deep tree without RecursionError — Python-recursion would blow at ~1k).
AC-3.6 + the A4/absolute-glob/autoindex-collision conformance pins must be
green on BOTH engines (semantic pins).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts.wiki_index.layout_config import (
    PathEntry,
    iter_pages,
    load_layout_config,
)
from tests.test_task030_walk_pins import _cfg
from tests.walk030_util import (
    build_fat_karpathy_vault,
    build_para_vault,
    count_direntry_stats,
    count_for,
    count_scandirs,
)


# --------------------------------------------------------------------------- #
# AC-3.3 — traversal counts (RED on the per-glob engine)
# --------------------------------------------------------------------------- #


def test_para_vault_every_dir_scandired_exactly_once(tmp_path: Path) -> None:
    """(i) obsidian-personal: baseline was root ×4, every other dir ≥2×
    (docs/benchmarks/030-walk-baseline.md). Target: ≤1 per dir."""
    root = tmp_path / "vault"
    root.mkdir()
    build_para_vault(root, areas=3, subs=2, files_per_sub=4)
    cfg = load_layout_config(root, {"layout": "obsidian-personal"})
    with count_scandirs() as counts:
        pages = iter_pages(root, cfg)
    assert pages, "fixture must discover pages"
    assert count_for(counts, root) == 1, "root must be scandir'd exactly once (was 4)"
    area = root / "00 - Area0"
    assert count_for(counts, area) == 1, "area dirs must be scandir'd once (was 2)"
    sub = area / "Sub0"
    assert count_for(counts, sub) == 1


def test_fat_karpathy_subtrees_never_walked(tmp_path: Path) -> None:
    """(ii) §3.5 'root subtrees never walked' BY CONSTRUCTION: `.obsidian/`,
    `.git/`, `attachments/` get ZERO scandirs (parity with today's per-glob
    engine, which never enters them either — but now provably, instrumented)."""
    root = tmp_path / "vault"
    root.mkdir()
    build_fat_karpathy_vault(root, pages=12, fat=10)
    cfg = load_layout_config(root, {"layout": "karpathy"})
    with count_scandirs() as counts:
        pages = iter_pages(root, cfg)
    assert pages
    for fat_dir in (".obsidian", ".git", "attachments"):
        assert count_for(counts, root / fat_dir) == 0, f"{fat_dir} must never be walked"
    # the engine no longer re-walks the page dirs either
    assert count_for(counts, root / "_sources") == 1
    assert count_for(counts, root / "Lessons") == 1


def test_prunable_ignore_subtree_zero_scandirs(tmp_path: Path) -> None:
    """(iii) `**/_raw/**` subtrees under a numbered area: REAL pruning — zero
    scandirs (baseline: traversed by entry-4's `**` and post-filtered)."""
    root = tmp_path / "vault"
    root.mkdir()
    build_para_vault(root, areas=2, subs=1, files_per_sub=3)
    cfg = load_layout_config(root, {"layout": "obsidian-personal"})
    raw = root / "00 - Area0" / "Sub0" / "_raw"
    assert raw.is_dir()  # builder plants it
    with count_scandirs() as counts:
        iter_pages(root, cfg)
    assert count_for(counts, raw) == 0, "_raw subtree must be pruned, not post-filtered"


# --------------------------------------------------------------------------- #
# AC-3.8 — pathological depth: explicit stack, no RecursionError
# --------------------------------------------------------------------------- #


def test_deep_tree_walks_without_recursion_error(tmp_path: Path) -> None:
    """AC-3.8 (spec deviation recorded): the TASK named a ≥1500-deep fixture,
    but macOS PATH_MAX (1024 bytes) caps buildable trees at ~330 levels — the
    naive-recursion hazard is only reachable on longer-PATH_MAX systems. The
    property is pinned HONESTLY instead: a 120-deep tree walked under a
    temporarily-clamped `sys.recursionlimit` — a Python-recursive walk blows,
    the explicit stack does not."""
    depth = 120
    root = tmp_path / "vault"
    cur = root
    for i in range(depth):
        cur = cur / f"d{i % 10}"
    cur.mkdir(parents=True)
    (cur / "leaf.md").write_text("# leaf\n", encoding="utf-8")
    cfg = _cfg((PathEntry(glob="**/*.md", project="_vault_"),))
    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(depth // 2)  # recursive impl needs ≥1 frame/level
    try:
        pages = iter_pages(root, cfg)  # RED on a naive recursion
    finally:
        sys.setrecursionlimit(limit)
    assert [p.path.name for p in pages] == ["leaf.md"]


# --------------------------------------------------------------------------- #
# AC-3.6 — empty vault
# --------------------------------------------------------------------------- #


def test_empty_vault_yields_empty(tmp_path: Path) -> None:
    cfg = _cfg((PathEntry(glob="**/*.md", project="_vault_"),))
    assert iter_pages(tmp_path, cfg) == []


# --------------------------------------------------------------------------- #
# Conformance pins (green on BOTH engines; 030-04 carry-forwards)
# --------------------------------------------------------------------------- #


def test_case_mismatched_literal_glob_consistent_miss(tmp_path: Path) -> None:
    """UC-30-3 A4 (engine-level pin): a literal-case-mismatched glob misses
    CONSISTENTLY under the new matcher (today: FS-dependent — APFS would hit).
    This is the ONE enumerated matcher delta; it must be deterministic."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "f.md").write_text("# f\n", encoding="utf-8")
    cfg = _cfg((PathEntry(glob="Docs/*.md", project="cased"),))
    assert iter_pages(tmp_path, cfg) == []  # RED on APFS pre-rewrite (FS-insensitive hit)


def test_absolute_glob_is_silently_dead_not_crash(tmp_path: Path) -> None:
    """030-04 carry-forward (Q-030-2 delta-iii family): an ABSOLUTE glob is
    out-of-contract; today `Path.glob` CRASHES (`NotImplementedError`), the
    walk leaves the entry empty — loud in this test, never silent in prod
    docs (the conformance case the Sarcasmotron demanded)."""
    (tmp_path / "n").mkdir()
    (tmp_path / "n" / "a.md").write_text("# a\n", encoding="utf-8")
    cfg = _cfg((
        PathEntry(glob="/etc/*.md", project="abs"),
        PathEntry(glob="n/*.md", project="rel"),
    ))
    pages = iter_pages(tmp_path, cfg)  # RED: NotImplementedError pre-rewrite
    assert [(p.path.name, p.project) for p in pages] == [("a.md", "rel")]


def test_autoindex_output_colliding_with_glob_excluded(tmp_path: Path) -> None:
    """030-04 carry-forward: an autoindex output INSIDE a matched glob's range
    is excluded by the walk (differential coverage the decorative fixture
    lacked)."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "INDEX.md").write_text("# generated\n", encoding="utf-8")
    (tmp_path / "docs" / "real.md").write_text("# real\n", encoding="utf-8")
    cfg = _cfg(
        (PathEntry(glob="docs/**/*.md", project="docs"),),
        auto_indexes=({"source_type": "known-issue", "output": "docs/INDEX.md"},),
    )
    rels = {p.path.relative_to(tmp_path).as_posix() for p in iter_pages(tmp_path, cfg)}
    assert rels == {"docs/real.md"}


def test_p2_mtime_carried_by_single_stat(tmp_path: Path) -> None:
    """P-2 hold: every DiscoveredPage carries a real mtime from the walk."""
    (tmp_path / "n").mkdir()
    (tmp_path / "n" / "a.md").write_text("# a\n", encoding="utf-8")
    cfg = _cfg((PathEntry(glob="n/*.md", project="_vault_"),))
    pages = iter_pages(tmp_path, cfg)
    assert len(pages) == 1 and pages[0].mtime is not None and pages[0].mtime > 0


def test_walk_stats_each_file_exactly_once(tmp_path: Path) -> None:
    """P-2, walk side (Sarcasmotron 030-05 HIGH re-arm): the engine stats every
    DISCOVERED file exactly once via `DirEntry.stat()` — counted through the
    DirEntry proxy (the C type itself can't be monkeypatched). Companion to the
    re-armed TASK-017 detector (which now pins ZERO `Path.stat` calls)."""
    root = tmp_path / "vault"
    root.mkdir()
    build_para_vault(root, areas=2, subs=2, files_per_sub=3)
    cfg = load_layout_config(root, {"layout": "obsidian-personal"})
    with count_direntry_stats() as stats:
        pages = iter_pages(root, cfg)
    assert pages
    for p in pages:
        n = count_for(stats, p.path)
        assert n == 1, f"{p.path} stat'd {n}× (must be exactly once)"


def test_dot_glob_is_silently_dead_not_crash(tmp_path: Path) -> None:
    """Q-030-2 delta-(iii) family (Sarcasmotron 030-05 LOW): `glob: '.'` —
    out-of-contract; old engine raised ValueError, the walk leaves the entry
    empty while sibling entries work."""
    (tmp_path / "n").mkdir()
    (tmp_path / "n" / "a.md").write_text("# a\n", encoding="utf-8")
    cfg = _cfg((
        PathEntry(glob=".", project="dot"),
        PathEntry(glob="n/*.md", project="rel"),
    ))
    pages = iter_pages(tmp_path, cfg)
    assert [(p.path.name, p.project) for p in pages] == [("a.md", "rel")]