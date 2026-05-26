"""Tests for SQLiteRepository lint queries (task-001-18, §6.1, R-29)."""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import Entity, Page, PageRef, Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository


def _h(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


@pytest.fixture
def two_vaults_with_shared_concept(tmp_path):
    """Repo with vault-alpha + vault-beta both having `shadow-ai` concept entity."""
    r = SQLiteRepository(tmp_path / "test.db")
    r.apply_schema()
    for vid in ["vault-alpha", "vault-beta"]:
        r.register_vault(Vault(
            vault_id=vid, name=vid, root_path=tmp_path / vid,
            schema_version="2.0", registered_at=datetime(2026, 5, 26),
        ))
        r._connect().execute(
            "INSERT INTO entities (vault_id, slug, type, name, first_seen, "
            "last_updated, file_path) VALUES (?, 'shadow-ai', 'concept', "
            "'Shadow AI', '2026-05-26T00:00:00Z', '2026-05-26T00:00:00Z', "
            "'_concepts/shadow-ai.md')", (vid,)
        )
    yield r
    r.close()


def test_e2e_01_cross_vault_duplicates(two_vaults_with_shared_concept):
    """R-29: shared `shadow-ai` concept slug across vaults is reported."""
    dups = two_vaults_with_shared_concept.find_cross_vault_concept_duplicates()
    assert dups == [("shadow-ai", ["vault-alpha", "vault-beta"])]


def test_e2e_02_orphan_link(tmp_path):
    """A page_entity_ref pointing to a nonexistent target → OrphanLink."""
    r = SQLiteRepository(tmp_path / "t.db")
    r.apply_schema()
    r.register_vault(Vault(
        vault_id="trade-agents", name="t", root_path=tmp_path,
        schema_version="2.0", registered_at=datetime(2026, 5, 26),
    ))
    r.upsert_page(Page(
        vault_id="trade-agents", slug="src", project="_vault_", type="summary",
        title="src", file_path="_sources/src.md", date=date(2026, 5, 26),
        last_modified=datetime(2026, 5, 26), file_hash=_h("body"),
        frontmatter_json={}, body_excerpt="body", tags=[],
    ))
    # After task-001-25 schema fix: entity_slug FK removed → orphan refs
    # can be inserted directly without PRAGMA workaround.
    r._connect().execute(
        "INSERT INTO page_entity_refs (vault_id, page_slug, page_project, "
        "entity_slug, ref_type) VALUES ('trade-agents', 'src', '_vault_', "
        "'ghost-entity', 'mentioned')"
    )
    orphans = r.find_orphan_links()
    assert len(orphans) == 1
    assert orphans[0].target_slug == "ghost-entity"
    r.close()


def test_e2e_03_intentional_mapping_not_drift(tmp_path):
    """§6.1: file type 'lesson-summary' + DB type 'summary' + tag → NOT drift."""
    vault_root = tmp_path / "vault"
    (vault_root / "_concepts").mkdir(parents=True)
    body = (
        "---\n"
        "type: lesson-summary\n"
        "title: Hermes\n"
        "date: 2026-05-25\n"
        "tags: [lesson, lesson-summary]\n"
        "---\n"
        "body"
    )
    (vault_root / "_concepts" / "hermes.md").write_text(body)

    r = SQLiteRepository(tmp_path / "t.db")
    r.apply_schema()
    r.register_vault(Vault(
        vault_id="trade-agents", name="t", root_path=vault_root,
        schema_version="2.0", registered_at=datetime(2026, 5, 26),
    ))
    r.upsert_page(Page(
        vault_id="trade-agents", slug="hermes", project="_vault_",
        type="summary",  # mapped from lesson-summary
        title="Hermes", file_path="_concepts/hermes.md",
        date=date(2026, 5, 25), last_modified=datetime(2026, 5, 25),
        file_hash=_h(body),
        frontmatter_json={"tags": ["lesson", "lesson-summary"]},
        body_excerpt="body",
        tags=["lesson", "lesson-summary"],
    ))
    report = r.check_drift("trade-agents")
    assert report.type_mismatch == [], (
        "§6.1 mapping should suppress drift on lesson-summary→summary+tag"
    )
    r.close()


def test_e2e_04_unmapped_type_is_drift(tmp_path):
    """Unmapped file type (e.g. 'lecture-notes') vs DB 'summary' → drift."""
    vault_root = tmp_path / "vault"
    (vault_root / "_concepts").mkdir(parents=True)
    body = (
        "---\n"
        "type: lecture-notes\n"
        "title: x\n"
        "date: 2026-05-25\n"
        "---\n"
        "body"
    )
    (vault_root / "_concepts" / "x.md").write_text(body)

    r = SQLiteRepository(tmp_path / "t.db")
    r.apply_schema()
    r.register_vault(Vault(
        vault_id="vault-drift", name="t", root_path=vault_root,
        schema_version="2.0", registered_at=datetime(2026, 5, 26),
    ))
    r.upsert_page(Page(
        vault_id="vault-drift", slug="x", project="_vault_", type="summary",
        title="x", file_path="_concepts/x.md", date=date(2026, 5, 25),
        last_modified=datetime(2026, 5, 25), file_hash=_h(body),
        frontmatter_json={"tags": []}, body_excerpt="body", tags=[],
    ))
    report = r.check_drift("vault-drift")
    assert report.type_mismatch == [("x", "_vault_", "lecture-notes", "summary")]
    r.close()


def test_unit_01_intentional_mapping_covers_three_rows():
    """§6.1 rows: lesson-summary, summary-light, meeting-summary all mapped."""
    for ft, marker in [
        ("lesson-summary", "lesson-summary"),
        ("summary-light", "summary-light"),
        ("meeting-summary", "meeting-summary"),
    ]:
        fm = f'{{"tags": ["{marker}"]}}'
        assert SQLiteRepository._is_intentional_mapping(ft, "summary", fm)
    # Without tag: drift
    assert not SQLiteRepository._is_intentional_mapping(
        "lesson-summary", "summary", '{"tags": []}'
    )


def test_unit_06_check_drift_two_tier_walk(tmp_path):
    """check_drift must walk BOTH vault-root tier AND Lessons/<course>/ tier.

    Regression for dogfood finding: course-local pages were false-positived as
    missing-on-disk because check_drift only walked root tier (PAGE_SUBDIRS
    under vault_root, ignoring Lessons/*/PAGE_SUBDIRS).
    """
    from scripts.wiki_source.parsing import compute_file_hash
    vault = tmp_path / "v"
    vault.mkdir()
    course_sources = vault / "Lessons" / "Course-A" / "_sources"
    course_sources.mkdir(parents=True)
    body = "course-local lesson body"
    fm_body = f"---\ntype: summary\ntitle: L1\ndate: 2026-05-26\n---\n{body}\n"
    (course_sources / "lesson-01.md").write_text(fm_body)
    r = SQLiteRepository(tmp_path / "drift.db")
    r.apply_schema()
    r.register_vault(Vault(
        vault_id="two-tier", name="t", root_path=vault,
        schema_version="2.0", registered_at=datetime(2026, 5, 26),
    ))
    # Insert page with course project + the full-file hash convention.
    r.upsert_page(Page(
        vault_id="two-tier", slug="lesson-01", project="course-a",
        type="summary", title="L1",
        file_path="Lessons/Course-A/_sources/lesson-01.md",
        date=date(2026, 5, 26), last_modified=datetime(2026, 5, 26),
        file_hash=compute_file_hash(fm_body.encode("utf-8")),
        frontmatter_json={}, body_excerpt=body, tags=[],
    ))
    drift = r.check_drift("two-tier")
    assert drift.missing_on_disk == [], (
        f"course-local page false-positived as missing-on-disk: {drift.missing_on_disk}"
    )
    assert drift.hash_mismatch == [], (
        f"body-only hash convention broken: {drift.hash_mismatch}"
    )
    r.close()


def test_unit_05_single_vault_no_duplicates(tmp_path):
    """No duplicates when only one vault has the concept."""
    r = SQLiteRepository(tmp_path / "t.db")
    r.apply_schema()
    r.register_vault(Vault(
        vault_id="solo-vault", name="s", root_path=tmp_path,
        schema_version="2.0", registered_at=datetime(2026, 5, 26),
    ))
    r._connect().execute(
        "INSERT INTO entities (vault_id, slug, type, name, first_seen, "
        "last_updated, file_path) VALUES ('solo-vault', 'only', 'concept', "
        "'Only', '2026-05-26', '2026-05-26', '_c/only.md')"
    )
    assert r.find_cross_vault_concept_duplicates() == []
    r.close()
