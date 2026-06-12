"""TASK 030 bead 030-04 (R-030-3/6, unit leg — UNWIRED) — pure alive-set
matcher units for the 030-05 single-pass walk.

RED-first: `_PatternState` / `_prunable_ignore` don't exist yet. The units are
NOT called by `iter_pages` in this bead (zero behavior change — pinned).

Semantics under test (Q-030-2 v4 / Q-030-6):
- NFA-style per-pattern state over dir segments; `**` consumes >=0 segments.
- SYMLINK rule: entering a symlinked dir keeps a position alive ONLY via an
  explicit (non-`**`) segment consume — per-entry `Path.glob` union parity.
- PROPER-prefix descent: a dir that fully exhausts the pattern (e.g. a
  DIRECTORY named `foo.md` vs `*.md`) cannot descend.
- File match at a dir = the remaining pattern matches exactly the filename
  (incl. trailing-`**`, which matches files on 3.13+).
- `_prunable_ignore`: ONLY `<prefix>/**`-shaped ignore globs prune a dir;
  file-shaped patterns (`**/*.base`) never prune.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest

from scripts.wiki_index.layout_config import (
    PathEntry,
    _PatternState,
    _prunable_ignore,
    iter_pages,
)
from tests.test_task030_walk_pins import _cfg  # shared minimal-config builder


def _advance_path(state: _PatternState, rel_dir: str,
                  symlinks: frozenset[str] = frozenset()) -> _PatternState | None:
    """Advance a state across every segment of `rel_dir` (test helper);
    `symlinks` = set of rel dir paths that are symlinked."""
    cur: _PatternState | None = state
    walked: list[str] = []
    for seg in PurePosixPath(rel_dir).parts:
        walked.append(seg)
        assert cur is not None
        cur = cur.advance(seg, is_symlink="/".join(walked) in symlinks)
        if cur is None:
            return None
    return cur


# --------------------------------------------------------------------------- #
# Descent tables (Q-030-6) — karpathy / obsidian-personal / dev-project shapes
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("glob,rel_dir,descend", [
    # karpathy: literal-anchored — fat dirs never prefix-match
    ("_sources/**/*.md", "_sources", True),
    ("_sources/**/*.md", ".obsidian", False),
    ("Lessons/*/_sources/**/*.md", "Lessons", True),
    ("Lessons/*/_sources/**/*.md", "Lessons/Course-X", True),
    ("Lessons/*/_sources/**/*.md", "Lessons/Course-X/_sources", True),
    ("Lessons/*/_sources/**/*.md", "Lessons/Course-X/_sources/deep", True),
    ("Lessons/*/_sources/**/*.md", "Lessons/Course-X/attachments", False),
    ("Lessons/*/_sources/**/*.md", ".git", False),
    # obsidian-personal: numbered areas
    ("[0-9][0-9] - */*/**/*.md", "02 - Area", True),
    ("[0-9][0-9] - */*/**/*.md", "02 - Area/RandomSubdir", True),
    ("[0-9][0-9] - */*/**/*.md", "_daily", False),
    ("[0-9][0-9] - */*.md", "02 - Area", True),
    ("[0-9][0-9] - */*.md", "02 - Area/Sub", False),     # exhausted past files
    ("_daily/**/*.md", "_daily", True),
    ("_daily/**/*.md", "_daily/2026", True),
    # PROPER-prefix rule: a DIRECTORY named like a file-glob match cannot descend
    ("*.md", "foo.md", False),
    ("*.md", "docs", False),
    # operator catch-all
    ("docs/**/*.md", "docs", True),
    ("docs/**/*.md", "docs/a/b/c", True),
    ("docs/**/*.md", "src", False),
    # mid-** then literal
    ("docs/**/img/*.md", "docs", True),
    ("docs/**/img/*.md", "docs/x/y", True),
    ("docs/**/img/*.md", "docs/x/img", True),
    # trailing-** (3.13+ matches files too) — stays open-ended
    ("Lessons/**", "Lessons", True),
    ("Lessons/**", "Lessons/a/b", True),
    # A4 case-sensitivity pin (UC-30-3): the units are case-SENSITIVE
    # everywhere — Path.glob on APFS would match dir 'docs' via 'Docs/*.md';
    # the units go dead (the ONE enumerated matcher delta).
    ("Docs/*.md", "docs", False),
    # `..` segments: Path.glob traverses them (escaping pattern anchoring!);
    # the units dead-end them EFFECTIVELY — `os.scandir` never yields a child
    # named '..', so the position can never advance past it: any REAL child
    # dir kills the pattern, and no file ever matches at 'v'. Enumerated
    # delta (iii), vault-containment-positive (Q-030-2 v4 / MED-2).
    ("v/../*.md", "v/sub", False),
])
def test_descent_table(glob: str, rel_dir: str, descend: bool) -> None:
    st = _advance_path(_PatternState.for_glob(glob), rel_dir)
    assert ((st is not None) and st.can_descend) is descend


# --------------------------------------------------------------------------- #
# File-match tables
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("glob,rel_dir,fname,matches", [
    ("_sources/**/*.md", "_sources", "a.md", True),
    ("_sources/**/*.md", "_sources/deep", "a.md", True),
    ("_sources/**/*.md", "_sources", "a.txt", False),
    ("[0-9][0-9] - */*.md", "02 - Area", "x.md", True),
    ("[0-9][0-9] - *.md", "", "02 - Area.md", True),     # root-level MOC
    ("*.md", "", "foo.md", True),
    ("docs/**/img/*.md", "docs/x/img", "p.md", True),
    ("docs/**/img/*.md", "docs/x", "p.md", False),
    ("Lessons/**", "Lessons/a", "b.md", True),           # trailing-** file match
    ("Lessons/**", "Lessons", "b.md", True),
    # Sarcasmotron 030-04 HIGH: a trailing `**` after a FINAL explicit segment
    # must consume >=1 segment — Path.glob('a.md/**') on FILE a.md yields [].
    ("a.md/**", "", "a.md", False),
    ("*.md/**", "", "x.md", False),
    # MED-1: trailing-slash glob = 3.13+ dirs-only semantics → no file matches.
    ("docs/*.md/", "docs", "f.md", False),
    # MED-2 (delta iii): a `..` segment never matches a real filename either.
    ("v/../*.md", "v", "x.md", False),
])
def test_file_match_table(glob: str, rel_dir: str, fname: str, matches: bool) -> None:
    st: _PatternState | None = _PatternState.for_glob(glob)
    if rel_dir:
        st = _advance_path(st, rel_dir)  # type: ignore[arg-type]
    assert st is not None
    assert st.matches_file(fname) is matches


# --------------------------------------------------------------------------- #
# Symlink rule (Q-030-2 v3): explicit-segment survival, **-death, dual-reach
# --------------------------------------------------------------------------- #


def test_symlink_kills_doublestar_consume() -> None:
    st = _advance_path(_PatternState.for_glob("Areas/**/*.md"),
                       "Areas/link", symlinks={"Areas/link"})
    assert st is None  # only ** could consume 'link' → dead across a symlink


def test_symlink_survives_explicit_segment() -> None:
    st = _advance_path(_PatternState.for_glob("Areas/*/notes/*.md"),
                       "Areas/link", symlinks={"Areas/link"})
    assert st is not None and st.can_descend


def test_symlink_dual_reach_h1_fixture() -> None:
    """The H-1 counterexample: below the symlinked dir, ONLY the explicit
    entry stays alive — `**`-pattern dead for descent AND attribution."""
    deep = _advance_path(_PatternState.for_glob("Areas/**/*.md"),
                         "Areas/link", symlinks={"Areas/link"})
    explicit = _advance_path(_PatternState.for_glob("Areas/*/notes/*.md"),
                             "Areas/link", symlinks={"Areas/link"})
    assert deep is None
    assert explicit is not None
    nxt = explicit.advance("notes", is_symlink=False)
    assert nxt is not None and nxt.matches_file("a.md")
    # 'other' subtree: explicit pattern requires 'notes' → dead
    assert explicit.advance("other", is_symlink=False) is None


def test_doublestar_zero_consume_then_explicit_crosses_symlink() -> None:
    """`**` matching ZERO segments hands consumption to the NEXT explicit
    segment — which IS allowed to cross a symlink (Path.glob parity:
    `docs/**/sub/*.md` enumerates `docs/sub/...` even when `sub` is symlinked,
    because the concrete `sub` component does the matching)."""
    st = _advance_path(_PatternState.for_glob("docs/**/sub/*.md"),
                       "docs/sub", symlinks={"docs/sub"})
    assert st is not None and st.matches_file("a.md")


# --------------------------------------------------------------------------- #
# _prunable_ignore — only <prefix>/** shapes prune
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("rel_dir,ignore,pruned", [
    (".obsidian", (".obsidian/**",), True),
    # Deeper dirs under a pruned subtree are unreachable (the walk prunes at
    # `.obsidian` itself); the predicate is deliberately conservative — a
    # non-top dir under-prunes and the per-file `_matches_ignore` still
    # excludes its descendants. Correct, not a hole.
    (".obsidian/plugins", (".obsidian/**",), False),
    ("02 - A/Sub/_raw", ("**/_raw/**",), True),
    ("_templates", ("_templates/**",), True),
    ("notes", ("**/*.base",), False),                 # file pattern never prunes
    ("notes", (".obsidian/**",), False),
    ("_raw", ("**/_raw/**",), True),
])
def test_prunable_ignore_table(rel_dir: str, ignore: tuple[str, ...],
                               pruned: bool) -> None:
    assert _prunable_ignore(rel_dir, ignore) is pruned


# --------------------------------------------------------------------------- #
# Property check: full DiscoveredPage-tuple equality vs the CURRENT engine
# --------------------------------------------------------------------------- #


def _reference_walk(root: Path, cfg: object) -> list[tuple[str, str, str, tuple[str, ...], str | None]]:
    """A minimal alive-set walker built ONLY on the 030-04 units (the 030-05
    prototype living in test code): returns sorted (rel, slug, project,
    extra_tags, raw_type) tuples.

    DELIBERATE OMISSIONS vs the real engine (030-05 must NOT copy them; they
    are stat-layer concerns outside the matcher units under test): the single
    `stat()` + `S_ISREG` gate (broken leaf symlinks emit here, skip there),
    `OSError → continue`, and `DiscoveredPage.mtime`. The FILTER chain is
    modeled fully: ext → SYSTEM_FILES → autoindex_outputs → ignore (F-9)."""
    import os
    from scripts.wiki_index.layout import SYSTEM_FILES
    from scripts.wiki_index.layout_config import (
        LayoutConfig, _apply_slug_strategy, _derive_project, _matches_ignore,
    )
    assert isinstance(cfg, LayoutConfig)
    exts = set(cfg.file_extensions)
    autoindex_outputs = {
        str(ai["output"]) for ai in cfg.auto_indexes if ai.get("output")
    }
    out = []
    # (dir_abs, rel_posix, [(entry_idx, state), ...])
    init = [(i, _PatternState.for_glob(e.glob)) for i, e in enumerate(cfg.paths)]
    stack: list[tuple[Path, str, list[tuple[int, _PatternState]]]] = [
        (root, "", init)]
    while stack:
        d, rel_d, alive = stack.pop()
        for entry in os.scandir(d):
            name = entry.name
            rel = f"{rel_d}/{name}" if rel_d else name
            if entry.is_dir(follow_symlinks=True):
                is_link = entry.is_symlink()
                nxt = [(i, s2) for i, s in alive
                       if (s2 := s.advance(name, is_symlink=is_link)) is not None
                       and s2.can_descend]
                if nxt and not _prunable_ignore(rel, cfg.ignore):
                    stack.append((Path(entry.path), rel, nxt))
                continue
            if Path(name).suffix not in exts or name in SYSTEM_FILES:
                continue
            if rel in autoindex_outputs or _matches_ignore(rel, cfg.ignore):
                continue
            for i, s in alive:
                if s.matches_file(name):
                    e = cfg.paths[i]
                    out.append((
                        rel,
                        _apply_slug_strategy(Path(name).stem, cfg.slug_strategy),
                        _derive_project(rel, e, operator_supplied=cfg.paths_operator_supplied),
                        tuple(e.default_tags) + tuple(e.extra_tags),
                        e.type,
                    ))
                    break
    return sorted(out)


def _engine_tuples(root: Path, cfg: object) -> list[tuple[str, str, str, tuple[str, ...], str | None]]:
    from scripts.wiki_index.layout_config import LayoutConfig
    assert isinstance(cfg, LayoutConfig)
    return sorted(
        (d.path.relative_to(root).as_posix(), d.slug, d.project,
         tuple(d.extra_tags), d.raw_type)
        for d in iter_pages(root, cfg))


def _build_tree(root: Path, rels: list[str]) -> None:
    for rel in rels:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# x\n", encoding="utf-8")


@pytest.mark.parametrize("layout", ["karpathy", "obsidian-personal", "dev-project"])
def test_property_builtin_layouts_full_tuple_equality(
    tmp_path: Path, layout: str,
) -> None:
    from scripts.wiki_index.layout_config import load_layout_config
    _build_tree(tmp_path, [
        "_sources/a.md", "_concepts/b.md", "Lessons/C1/_sources/d.md",
        "_daily/2026/e.md", "_inbox/f.md", "01 - Area/g.md",
        "01 - Area/Sub/h.md", "01 - Area/Sub/deep/i.md", "01 - Area.md",
        "root-note.md", "issues/x.md", "issues/resolved/y.md", "tasks/t.md",
        "TASK.md", "02 - Z/Sub/_raw/raw.md", ".obsidian/cache.md",
        "_templates/tpl.md", "attachments/pic.md",
        "notanarea/file.md", "foo.md/inner.md",   # a DIRECTORY named foo.md
        ".hidden.md", "docs/.dotdir/j.md",
        "KNOWN_ISSUES.md",                        # dev-project autoindex output
    ])
    cfg = load_layout_config(tmp_path, {"layout": layout})
    assert _reference_walk(tmp_path, cfg) == _engine_tuples(tmp_path, cfg)


def test_property_operator_overlap_layout(tmp_path: Path) -> None:
    _build_tree(tmp_path, [
        "docs/a.md", "docs/x/b.md", "docs/x/img/c.md", "docs/x/img/deep/d.md",
        "Lessons/e.md", "Lessons/f/g.md",
    ])
    cfg = _cfg((
        PathEntry(glob="docs/**/img/*.md", project="img"),
        PathEntry(glob="docs/**/*.md", project="docs"),
        PathEntry(glob="Lessons/**", project="lessons"),
    ))
    assert _reference_walk(tmp_path, cfg) == _engine_tuples(tmp_path, cfg)


def test_property_symlink_topology(tmp_path: Path) -> None:
    """The H-1 dual-reach topology + a leaf symlink + a **-only symlink."""
    _build_tree(tmp_path, [
        "tgt/notes/a.md", "tgt/other/b.md", "real.md", "t2/sub/c.md",
        "Areas/plain/notes/p.md",
    ])
    (tmp_path / "Areas" / "link").symlink_to(tmp_path / "tgt")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "leaf.md").symlink_to(tmp_path / "real.md")
    (tmp_path / "dd").mkdir()
    (tmp_path / "dd" / "ll").symlink_to(tmp_path / "t2")
    cfg = _cfg((
        PathEntry(glob="Areas/**/*.md", project="deep"),
        PathEntry(glob="Areas/*/notes/*.md", project="explicit"),
        PathEntry(glob="docs/*.md", project="docs"),
        PathEntry(glob="dd/**/*.md", project="ddeep"),
    ))
    assert _reference_walk(tmp_path, cfg) == _engine_tuples(tmp_path, cfg)


# --------------------------------------------------------------------------- #
# Wiring pin — DESIGNED ROTATION of the 030-04 scaffold pin: that bead pinned
# "units NOT called by iter_pages" (zero behavior change); bead 030-05 wires
# them, so the pin inverts to its positive form (the only sanctioned test edit
# of the cycle — recorded here per the AC-3.2 stop-and-re-review rule).
# --------------------------------------------------------------------------- #


def test_units_wired_into_iter_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.wiki_index.layout_config as lc
    called: list[str] = []
    real = lc._PatternState.for_glob

    def spy(glob: str) -> object:
        called.append(glob)
        return real(glob)

    monkeypatch.setattr(lc._PatternState, "for_glob", staticmethod(spy))
    (tmp_path / "n").mkdir()
    (tmp_path / "n" / "a.md").write_text("# a\n", encoding="utf-8")
    iter_pages(tmp_path, _cfg((PathEntry(glob="n/*.md", project="_vault_"),)))
    assert called == ["n/*.md"]  # 030-05: the alive-set engine IS the walk

# --------------------------------------------------------------------------- #
# /vdd-multi 030 SEC-HIGH — glob-complexity pins
# --------------------------------------------------------------------------- #


def test_for_glob_collapses_consecutive_doublestar() -> None:
    """Stacked `**` runs fold to one (Path.glob parity) — kills the O(dirs×k²)
    alive-set blowup an operator glob of k stacked `**` produced (measured
    3.1 s vs 0.17 s at k=200 pre-fix)."""
    st = _PatternState.for_glob("**/**/**/**/*.md")
    assert st.segments == ("**", "*.md")
    # alternating segments do NOT fold (correctness preserved)
    st2 = _PatternState.for_glob("**/x/**/*.md")
    assert st2.segments == ("**", "x", "**", "*.md")


def test_operator_glob_segment_cap_rejected(tmp_path: Path) -> None:
    """Load-gate: an operator glob exceeding 64 post-collapse segments is
    rejected at config load (exit-6 envelope path), value not echoed verbatim
    beyond the established error style."""
    from scripts.wiki_index.layout_config import LayoutConfigError, load_layout_config
    hostile = "/".join(["**", "x"] * 40) + "/*.md"   # 81 post-collapse segments
    (tmp_path / ".wiki").mkdir()
    (tmp_path / ".wiki" / "layout.yaml").write_text(
        "schema_version: '2.0'\nlayout: karpathy\nslug_strategy: identity\n"
        f"paths:\n  - {{glob: '{hostile}', type: summary, project: '_vault_'}}\n"
        "type_mapping:\n  summary: {db_type: summary, tag: null}\n",
        encoding="utf-8")
    with pytest.raises(LayoutConfigError, match="segments"):
        load_layout_config(tmp_path, {"layout": "karpathy"})
