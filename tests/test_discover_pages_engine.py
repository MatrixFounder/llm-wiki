"""TASK 012-02 (PW-B/J/K/M) — config-driven discover_pages / iter_pages engine.

Covers: stable path sort (NFR-5 / C-5 pin), ignore[] (PW-K), file_extensions
(PW-M), project_pattern/template deep-hierarchy + no-PK-collision + Cyrillic stem
(PW-J), the `_unmatched_` + WARN policy (PW-J), the SYSTEM_FILES + auto_indexes[]
output implicit-ignore (architecture-review m1), the PW-J load-time error policy,
and the architecture-review C1 convergence of find_pages_missing_in_index onto
(slug, project).
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pytest

from scripts.wiki_index.layout_config import (
    UNMATCHED_PROJECT,
    LayoutConfig,
    LayoutConfigError,
    PathEntry,
    iter_pages,
    load_layout_config,
)
from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import discover_pages, reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository


def _touch(root: Path, rel: str, body: str = "x") -> None:
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
# PW-B: stable canonical sort
# --------------------------------------------------------------------------- #


def test_discover_pages_is_path_sorted(tmp_path: Path) -> None:
    """C-5 pin: discover_pages output is stably sorted by vault-relative POSIX
    path, independent of filesystem glob order."""
    for rel in ["_sources/z.md", "_sources/a.md", "_concepts/m.md"]:
        _touch(tmp_path, rel)
    got = discover_pages(tmp_path)  # no WIKI_SCHEMA → karpathy default
    rels = [p.relative_to(tmp_path).as_posix() for (p, _, _) in got]
    assert rels == sorted(rels)


# --------------------------------------------------------------------------- #
# PW-K ignore[] + the implicit-ignore set (m1)
# --------------------------------------------------------------------------- #


def test_ignore_excludes_matched_paths(tmp_path: Path) -> None:
    for rel in ["real.md", "_templates/tpl.md", ".obsidian/cache.md"]:
        _touch(tmp_path, rel)
    cfg = _cfg((PathEntry(glob="**/*.md", project="_all_"),),
               ignore=(".obsidian/**", "_templates/**"))
    rels = {d.path.relative_to(tmp_path).as_posix() for d in iter_pages(tmp_path, cfg)}
    assert rels == {"real.md"}  # both ignored paths excluded though **/*.md matched them


def test_system_files_and_autoindex_output_excluded(tmp_path: Path) -> None:
    """m1: a `*` glob never scoops WIKI_SCHEMA.md (SYSTEM_FILES) nor a generated
    auto_indexes output (no render→ingest feedback loop)."""
    for rel in ["real.md", "WIKI_SCHEMA.md", "KNOWN_ISSUES.md"]:
        _touch(tmp_path, rel)
    cfg = _cfg((PathEntry(glob="*.md", project="_all_"),),
               auto_indexes=({"source_type": "known-issue", "output": "KNOWN_ISSUES.md"},))
    rels = {d.path.relative_to(tmp_path).as_posix() for d in iter_pages(tmp_path, cfg)}
    assert rels == {"real.md"}


# --------------------------------------------------------------------------- #
# PW-M file_extensions allow-list
# --------------------------------------------------------------------------- #


def test_file_extensions_allowlist(tmp_path: Path) -> None:
    for rel in ["real.md", "notes.base", "diagram.canvas"]:
        _touch(tmp_path, rel)
    cfg = _cfg((PathEntry(glob="*", project="_all_"),), file_extensions=(".md",))
    rels = {d.path.relative_to(tmp_path).as_posix() for d in iter_pages(tmp_path, cfg)}
    assert rels == {"real.md"}  # .base / .canvas excluded by file_extensions


# --------------------------------------------------------------------------- #
# PW-J project derivation: deep hierarchy, no collision, Cyrillic, unmatched
# --------------------------------------------------------------------------- #


def _obsidian_cfg() -> LayoutConfig:
    return _cfg((
        PathEntry(glob="_inbox/**/*.md", project="_inbox", default_tags=("inbox", "draft")),
        PathEntry(glob="[0-9][0-9] - */*/*.md",
                  project_pattern=r"^(?P<num>\d+)\s*-\s*(?P<area>[^/]+)/(?P<sub>[^/]+)/",
                  project_template="${area}/${sub}"),
        PathEntry(glob="[0-9][0-9] - */*.md",
                  project_pattern=r"^(?P<num>\d+)\s*-\s*(?P<area>[^/]+)/",
                  project_template="${area}"),
        PathEntry(glob="*.md", project="_root_"),
    ), ignore=(".obsidian/**", "**/.DS_Store"))


def test_project_pattern_deep_hierarchy_no_collision(tmp_path: Path) -> None:
    """Three same-named `intake.md` under different <area>/<sub>/ → three distinct
    projects (no `UNIQUE(vault_id, slug, project)` collision)."""
    for rel in [
        "02 - Personal Home/Household/intake.md",
        "02 - Personal Home/Purchases/intake.md",
        "03 - Work/Reports/intake.md",
    ]:
        _touch(tmp_path, rel)
    pages = iter_pages(tmp_path, _obsidian_cfg())
    keys = {(d.slug, d.project) for d in pages}
    assert keys == {
        ("intake", "Personal Home/Household"),
        ("intake", "Personal Home/Purchases"),
        ("intake", "Work/Reports"),
    }
    assert len(keys) == 3  # no collapse → no PK collision


def test_project_pattern_single_component_and_cyrillic_stem(tmp_path: Path) -> None:
    _touch(tmp_path, "02 - Personal Home/Квартиры.md")
    pages = iter_pages(tmp_path, _obsidian_cfg())
    got = {(d.slug, d.project) for d in pages}
    assert got == {("Квартиры", "Personal Home")}  # stem preserved (identity)


def test_project_pattern_miss_yields_unmatched_and_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A file matched by the glob but NOT the project_pattern → UNMATCHED_PROJECT
    + a WARN (no silent drop — PW-J error policy (b))."""
    _touch(tmp_path, "notanumber/file.md")
    cfg = _cfg((PathEntry(glob="**/*.md",
                          project_pattern=r"^(?P<num>\d+)\s*-\s*(?P<area>[^/]+)/",
                          project_template="${area}"),),)
    with caplog.at_level(logging.WARNING):
        pages = iter_pages(tmp_path, cfg)
    assert {d.project for d in pages} == {UNMATCHED_PROJECT}
    assert any("unmatched-pattern" in r.message for r in caplog.records)


# --------------------------------------------------------------------------- #
# PW-J load-time error policy (via load_layout_config override)
# --------------------------------------------------------------------------- #


def _override(root: Path, paths_yaml: str) -> None:
    (root / ".wiki").mkdir(exist_ok=True)
    (root / ".wiki" / "layout.yaml").write_text(
        "schema_version: '2.0'\nlayout: karpathy\nslug_strategy: identity\n"
        "type_mapping:\n  note: {db_type: summary, tag: null}\n"
        f"paths:\n{paths_yaml}",
        encoding="utf-8",
    )


def test_load_rejects_uncompilable_project_pattern(tmp_path: Path) -> None:
    root = tmp_path / "v"; root.mkdir()
    _override(root, "  - {glob: 'x/**/*.md', project_pattern: '(?P<bad', project_template: '${bad}'}\n")
    with pytest.raises(LayoutConfigError, match="failed to compile"):
        load_layout_config(root, {"layout": "karpathy"})


def test_load_rejects_template_missing_group(tmp_path: Path) -> None:
    root = tmp_path / "v"; root.mkdir()
    _override(root, "  - {glob: 'x/**/*.md', project_pattern: '^(?P<area>[^/]+)/', project_template: '${nope}'}\n")
    with pytest.raises(LayoutConfigError, match="not produced by project_pattern"):
        load_layout_config(root, {"layout": "karpathy"})


# --------------------------------------------------------------------------- #
# architecture-review C1: find_pages_missing_in_index compares (slug, project)
# --------------------------------------------------------------------------- #


def test_find_pages_missing_uses_slug_project_not_stem(tmp_path: Path) -> None:
    """A course-tier page sharing a STEM with an indexed vault-tier page must be
    reported missing (its (slug, project) is not in the index) — the old slug-only
    compare false-negatived it."""
    vault = tmp_path / "v"
    _touch(vault, "_concepts/dup.md", "---\ntype: concept\ntitle: Dup\n---\n\nbody\n")
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id="dup-vault", name="dup-vault", root_path=vault,
        schema_version="2.0", registered_at=datetime(2026, 5, 26),
    ))
    try:
        reindex_full(repo, "dup-vault")  # indexes (dup, _vault_) only
        # add a course-tier page with the SAME stem, NOT reindexed
        _touch(vault, "Lessons/Course-C/_concepts/dup.md",
               "---\ntype: concept\ntitle: Dup C\n---\n\nbody\n")
        missing = repo.find_pages_missing_in_index("dup-vault", vault)
        rels = {p.relative_to(vault).as_posix() for p in missing}
        # (dup, course-c) is NOT indexed → must be flagged; (dup, _vault_) IS → must not.
        assert "Lessons/Course-C/_concepts/dup.md" in rels
        assert "_concepts/dup.md" not in rels
    finally:
        repo.close()
