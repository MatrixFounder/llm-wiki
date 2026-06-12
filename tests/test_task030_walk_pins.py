"""TASK 030 (bead 030-00) — GREEN semantic pins, written BEFORE the 030-05 engine
rewrite they protect.

Pins (all GREEN on the CURRENT per-glob `iter_pages` engine):
- AC-3.1 — overlap first-match-wins: the one built-in overlapping-glob case
  (obsidian-personal root `NN - Area.md` matches entries 6 AND 7) yields exactly
  ONE DiscoveredPage attributed to the EARLIER entry (closes the F-8 test gap —
  the `seen`-set dedup was previously unpinned by any test).
- AC-3.5 (i..v) — symlink semantics of the per-glob walk on Python 3.13+/3.14
  (F-10): `**` never descends a symlinked dir; an explicit non-`**` wildcard
  segment does; leaf file symlinks are discovered; the per-entry UNION semantics
  on overlap+symlink layouts (spec-validator H-1 fixture) — attribution to the
  explicit entry, no `**`-beyond-symlink inflation.

The 030-05 single-pass rewrite must keep every one of these green UNMODIFIED.
"""

from __future__ import annotations

from pathlib import Path

from scripts.wiki_index.layout_config import (
    DiscoveredPage,
    LayoutConfig,
    PathEntry,
    iter_pages,
    load_layout_config,
)


def _touch(root: Path, rel: str, body: str = "# t\n") -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def _cfg(paths: tuple[PathEntry, ...], **over: object) -> LayoutConfig:
    base: dict[str, object] = dict(
        schema_version="2.0", layout="test", slug_strategy="identity",
        paths=paths, type_mapping={"note": ("summary", None)},
    )
    base.update(over)
    return LayoutConfig(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# AC-3.1 — overlap dedup / first-match attribution (the F-8 gap)
# --------------------------------------------------------------------------- #


def test_iter_pages_overlap_first_match_wins(tmp_path: Path) -> None:
    """Root `01 - Health.md` under the REAL obsidian-personal built-in matches
    BOTH entry-6 (`[0-9][0-9] - *.md`, MOC) and entry-7 (`*.md`, `_root_`).
    First-match (entry-6, declared earlier) must own the file: exactly ONE
    DiscoveredPage, project derived from the area name, `moc` tag present."""
    _touch(tmp_path, "01 - Health.md")
    cfg = load_layout_config(tmp_path, {"layout": "obsidian-personal"})
    pages = iter_pages(tmp_path, cfg)
    assert len(pages) == 1  # the seen-set dedup: never emitted twice
    d = pages[0]
    assert d.project == "Health"        # entry-6 ${area}, NOT entry-7 "_root_"
    assert "moc" in d.extra_tags        # entry-6 extra_tags
    assert d.mtime is not None          # P-2 single-stat carried


# --------------------------------------------------------------------------- #
# AC-3.5 — symlink parity pins (current engine ground truth, F-10)
# --------------------------------------------------------------------------- #


def _rels(pages: list[DiscoveredPage], root: Path) -> set[str]:
    return {p.path.relative_to(root).as_posix() for p in pages}


def test_symlink_i_recursive_glob_does_not_descend_symlinked_dir(tmp_path: Path) -> None:
    """(i) `docs/**/*.md` never enters a symlinked dir — `**` has
    recurse_symlinks=False on 3.13+.

    Pure-negative pin (passes under an engine that discovers nothing) —
    acceptable ONLY because (ii)/(iii) below are positive controls over the
    same fixture shape (Sarcasmotron 030-00 LOW-2)."""
    _touch(tmp_path, "target/sub/a.md")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "link").symlink_to(tmp_path / "target")
    cfg = _cfg((PathEntry(glob="docs/**/*.md", project="deep"),))
    assert iter_pages(tmp_path, cfg) == []


def test_symlink_ii_explicit_wildcard_segment_descends_symlinked_dir(tmp_path: Path) -> None:
    """(ii) `docs/*/notes/*.md` — the non-`**` `*` component matches and
    traverses a symlinked dir."""
    _touch(tmp_path, "target2/notes/b.md")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "link2").symlink_to(tmp_path / "target2")
    cfg = _cfg((PathEntry(glob="docs/*/notes/*.md", project="explicit"),))
    assert _rels(iter_pages(tmp_path, cfg), tmp_path) == {"docs/link2/notes/b.md"}


def test_symlink_iii_leaf_file_symlink_discovered(tmp_path: Path) -> None:
    """(iii) a leaf symlink to a regular file IS discovered — `path.stat()`
    follows it and `S_ISREG` passes."""
    _touch(tmp_path, "real.md")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "leaf.md").symlink_to(tmp_path / "real.md")
    cfg = _cfg((PathEntry(glob="docs/*.md", project="docs"),))
    assert _rels(iter_pages(tmp_path, cfg), tmp_path) == {"docs/leaf.md"}


def _h1_fixture(tmp_path: Path) -> LayoutConfig:
    """The spec-validator H-1 topology: a dir reachable via BOTH a `**` pattern
    (declared FIRST) and an explicit-segment pattern (declared SECOND), where
    the shared component is a symlinked dir."""
    _touch(tmp_path, "tgt/notes/a.md")
    _touch(tmp_path, "tgt/other/b.md")
    (tmp_path / "Areas").mkdir()
    (tmp_path / "Areas" / "link").symlink_to(tmp_path / "tgt")
    return _cfg((
        PathEntry(glob="Areas/**/*.md", project="deep"),
        PathEntry(glob="Areas/*/notes/*.md", project="explicit"),
    ))


def test_symlink_iv_overlap_attribution_goes_to_explicit_entry(tmp_path: Path) -> None:
    """(iv) per-entry UNION semantics: the `**` entry's glob never enumerates
    the symlinked subtree, so `Areas/link/notes/a.md` is discovered ONLY by the
    explicit entry and carries ITS attribution — not the earlier-declared `**`
    entry's. (A symlink-blind global matcher would flip this to `deep`.)"""
    cfg = _h1_fixture(tmp_path)
    pages = iter_pages(tmp_path, cfg)
    by_rel = {p.path.relative_to(tmp_path).as_posix(): p for p in pages}
    assert "Areas/link/notes/a.md" in by_rel
    assert by_rel["Areas/link/notes/a.md"].project == "explicit"


def test_symlink_v_no_match_set_inflation_beyond_symlink(tmp_path: Path) -> None:
    """(v) `Areas/link/other/b.md` is reachable ONLY via `**`-through-a-symlink
    → NOT discovered today; the rewrite must not inflate the match set."""
    cfg = _h1_fixture(tmp_path)
    assert _rels(iter_pages(tmp_path, cfg), tmp_path) == {"Areas/link/notes/a.md"}
