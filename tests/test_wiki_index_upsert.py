"""Tests for wiki-index-upsert + R-07.4/R-07.5 normalization (task-001-25)."""

from __future__ import annotations

import io
import json
import sqlite3
import sys
from pathlib import Path

import pytest

from scripts.wiki_index.normalization import (
    BodyNormalizationError,
    UnmappedTypeError,
    _slugify_concept,
    normalize_body_for_fts,
    normalize_frontmatter,
)
from scripts.wiki_skills.wiki_index_upsert import main


def _run(argv: list[str]) -> tuple[int, dict]:
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        code = main(argv)
    finally:
        sys.stdout = old
    return code, json.loads(buf.getvalue())


# =============================================================================
# R-07.4 normalize_frontmatter unit tests
# =============================================================================


def test_unit_01_slugify_lossy_cases():
    """Documented lossy cases: 'OAuth 2.0' → 'oauth-2-0'."""
    assert _slugify_concept("OAuth 2.0") == "oauth-2-0"
    # 'C++' → only 'c' survives (++ stripped); known lossy
    assert _slugify_concept("C++") == "c"


def test_unit_02_concepts_merged_and_deduplicated():
    fm = {
        "type": "lesson-summary",
        "tags": ["existing"],
        "concepts": ["OAuth 2.0", "OAuth 2.0", "Sharpe Ratio"],
    }
    updated, db_type = normalize_frontmatter(fm)
    assert db_type == "summary"
    # tags = existing + marker 'lesson-summary' + slugified concepts (deduped)
    assert "lesson-summary" in updated["tags"]
    assert "oauth-2-0" in updated["tags"]
    assert "sharpe-ratio" in updated["tags"]
    # No duplicates
    assert len(updated["tags"]) == len(set(updated["tags"]))


def test_unit_03_concepts_preserved_verbatim_in_frontmatter():
    """R-07.4: concepts[] preserved verbatim; slugified in tags."""
    fm = {"type": "lesson-summary", "tags": [], "concepts": ["Sharpe Ratio"]}
    updated, _ = normalize_frontmatter(fm)
    # concepts unchanged
    assert updated["concepts"] == ["Sharpe Ratio"]
    # tags get slugified version
    assert "sharpe-ratio" in updated["tags"]


def test_unit_07_unmapped_type_raises():
    with pytest.raises(UnmappedTypeError, match=r"lecture-notes"):
        normalize_frontmatter({"type": "lecture-notes"})


def test_unit_08_path_aware_type_fallback_concepts(tmp_path):
    """Files under `_concepts/` without explicit `type:` default to concept
    (real-world wiki-ingest convention; uses `kind:` not `type:`)."""
    p = tmp_path / "Lessons" / "Course-A" / "_concepts" / "tmux.md"
    fm, db_type = normalize_frontmatter(
        {"name": "Tmux Session", "kind": "concept"}, source_path=p,
    )
    assert db_type == "concept"


def test_unit_09_path_aware_type_fallback_entities(tmp_path):
    """Files under `_entities/` without `type:` default to external (maps
    to db_type=concept + tag=external)."""
    p = tmp_path / "_entities" / "Hermes Agent.md"
    fm, db_type = normalize_frontmatter({"name": "Hermes Agent"}, source_path=p)
    assert db_type == "concept"
    assert "external" in fm.get("tags", [])


def test_unit_10_entity_types_mapped(tmp_path):
    """Expanded TYPE_MAPPING accepts wiki-ingest entity types
    (external/person/company/product/group) — all map to db_type=concept."""
    for raw in ("external", "person", "company", "product", "group"):
        fm, db_type = normalize_frontmatter({"type": raw})
        assert db_type == "concept", f"raw={raw}"
        assert raw in fm.get("tags", []), f"raw={raw} tag missing"


def test_unit_11_no_type_no_path_still_raises(tmp_path):
    """Path fallback only fires when path is _concepts/_entities. A
    _sources/ file without explicit type still raises."""
    p = tmp_path / "_sources" / "x.md"
    with pytest.raises(UnmappedTypeError):
        normalize_frontmatter({}, source_path=p)
    # Same without path
    with pytest.raises(UnmappedTypeError):
        normalize_frontmatter({})


# =============================================================================
# R-07.5 normalize_body_for_fts unit tests
# =============================================================================


def test_unit_05_mermaid_stripped():
    body = "Before\n```mermaid\nflowchart LR\n    A --> B\n```\nAfter"
    out = normalize_body_for_fts(body)
    assert "flowchart" not in out
    assert "Before" in out
    assert "After" in out


def test_unit_05b_section_anchor_stripped():
    body = "Hello <!-- SECTION:agent-metadata --> World"
    out = normalize_body_for_fts(body)
    assert "SECTION:agent-metadata" not in out
    assert "Hello" in out
    assert "World" in out


def test_unit_05c_generic_comment_preserved():
    """Whitelist: only `SECTION:*` anchors stripped. Generic comments survive."""
    body = "Some text <!-- TODO: revisit --> more text"
    out = normalize_body_for_fts(body)
    assert "TODO" in out


def test_unit_06_unclosed_mermaid_fence_raises():
    """R-07.5 anti-tail-eat: unclosed mermaid fence → BodyNormalizationError."""
    body = "Before\n```mermaid\nflowchart LR\n    A --> B\nno closing fence here"
    with pytest.raises(BodyNormalizationError, match=r"unclosed mermaid"):
        normalize_body_for_fts(body)


# =============================================================================
# E2E via CLI
# =============================================================================


def test_e2e_01_upsert_alpha_inserted_then_unchanged(minimal_vault: Path, tmp_path):
    db = tmp_path / "g.db"
    # Bootstrap vault registration via wiki-init register-existing
    from scripts.wiki_skills.wiki_init import main as init_main
    init_buf = io.StringIO()
    old = sys.stdout
    sys.stdout = init_buf
    try:
        init_main(["--register-existing", "--vault", str(minimal_vault),
                   "--db-path", str(db)])
    finally:
        sys.stdout = old
    # First upsert: inserted
    code, out = _run([
        "--vault", "minimal-test",
        "--source", str(minimal_vault / "_sources" / "alpha.md"),
        "--vault-root", str(minimal_vault),
        "--db-path", str(db),
    ])
    assert code == 0
    assert out["action"] == "inserted"
    assert out["slug"] == "alpha"
    # Re-upsert: unchanged
    code, out = _run([
        "--vault", "minimal-test",
        "--source", str(minimal_vault / "_sources" / "alpha.md"),
        "--vault-root", str(minimal_vault),
        "--db-path", str(db),
    ])
    assert out["action"] == "unchanged"


def test_e2e_02_lesson_summary_type_mapping(minimal_vault: Path, tmp_path):
    """File `type: lesson-summary` → DB `pages.type='summary'` + tag marker."""
    # Override the alpha.md frontmatter with lesson-summary type
    p = minimal_vault / "_sources" / "alpha.md"
    p.write_text(
        "---\n"
        "type: lesson-summary\n"
        "title: Lesson Alpha\n"
        "date: 2026-05-01\n"
        "tags: [test]\n"
        "concepts: [Sharpe Score]\n"
        "---\n"
        "body content\n"
    )
    db = tmp_path / "g.db"
    from scripts.wiki_skills.wiki_init import main as init_main
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        init_main(["--register-existing", "--vault", str(minimal_vault),
                   "--db-path", str(db)])
    finally:
        sys.stdout = old

    code, out = _run([
        "--vault", "minimal-test",
        "--source", str(p),
        "--vault-root", str(minimal_vault),
        "--db-path", str(db),
    ])
    assert code == 0
    # Inspect DB
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT type, frontmatter_json FROM pages WHERE slug='alpha'"
    ).fetchone()
    assert row["type"] == "summary"  # mapped from lesson-summary
    fm = json.loads(row["frontmatter_json"])
    assert "lesson-summary" in fm["tags"]
    assert "sharpe-score" in fm["tags"]
    conn.close()


def test_e2e_07_unmapped_type_no_db_mutation(minimal_vault: Path, tmp_path):
    """`type: lecture-notes` → error JSON, no DB row."""
    p = minimal_vault / "_sources" / "alpha.md"
    p.write_text(
        "---\ntype: lecture-notes\ntitle: X\ndate: 2026-01-01\n---\nbody\n"
    )
    db = tmp_path / "g.db"
    from scripts.wiki_skills.wiki_init import main as init_main
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        init_main(["--register-existing", "--vault", str(minimal_vault),
                   "--db-path", str(db)])
    finally:
        sys.stdout = old
    code, out = _run([
        "--vault", "minimal-test", "--source", str(p),
        "--vault-root", str(minimal_vault), "--db-path", str(db),
    ])
    # Error envelopes now return exit_code=6 (H1 fix).
    assert code == 6
    assert out["error"] == "UnmappedTypeError"
    # DB has no row for alpha
    conn = sqlite3.connect(db)
    n = conn.execute("SELECT count(*) FROM pages WHERE slug='alpha'").fetchone()[0]
    assert n == 0
    conn.close()
