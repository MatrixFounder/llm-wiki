"""Sanity tests for tests/conftest.py fixtures (task-001-10)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.wiki_index.repository import IndexRepository


def _frontmatter(path: Path) -> dict:
    text = path.read_text()
    assert text.startswith("---\n"), f"{path}: no YAML frontmatter"
    _, fm, _ = text.split("---\n", 2)
    return yaml.safe_load(fm)


def test_e2e_01_minimal_vault_has_valid_schema(minimal_vault: Path):
    """minimal_vault fixture yields a path with WIKI_SCHEMA.md::vault_id."""
    schema_path = minimal_vault / "WIKI_SCHEMA.md"
    assert schema_path.exists()
    fm = _frontmatter(schema_path)
    assert fm["vault_id"] == "minimal-test"
    assert fm["schema_version"] == "2.0"


def test_e2e_01b_minimal_vault_pages_present(minimal_vault: Path):
    """All 3 fixture pages exist in the copied vault."""
    assert (minimal_vault / "_sources" / "alpha.md").exists()
    assert (minimal_vault / "_sources" / "beta.md").exists()
    assert (minimal_vault / "_concepts" / "example-concept.md").exists()
    assert (minimal_vault / "log.md").exists()


def test_unit_01_multi_vault_distinct_ids(multi_vault: dict[str, Path]):
    """Both vaults present with distinct vault_id values."""
    assert set(multi_vault.keys()) == {"vault-alpha", "vault-beta"}
    fm_a = _frontmatter(multi_vault["vault-alpha"] / "WIKI_SCHEMA.md")
    fm_b = _frontmatter(multi_vault["vault-beta"] / "WIKI_SCHEMA.md")
    assert fm_a["vault_id"] == "vault-alpha"
    assert fm_b["vault_id"] == "vault-beta"


def test_unit_02_shared_shadow_ai_slug(multi_vault: dict[str, Path]):
    """`shadow-ai.md` exists in both vaults' `_concepts/` — R-29 driver."""
    a = multi_vault["vault-alpha"] / "_concepts" / "shadow-ai.md"
    b = multi_vault["vault-beta"] / "_concepts" / "shadow-ai.md"
    assert a.exists() and b.exists()
    # Bodies differ even though slugs match (so cross-vault detection has
    # something to surface beyond mere filename).
    assert a.read_text() != b.read_text()


def test_unit_02b_course_local_paths(multi_vault: dict[str, Path]):
    """Course-local concept layer present in both vaults — promotion-spec §5.1."""
    assert (multi_vault["vault-alpha"] / "Lessons" / "Course-A" / "_concepts" /
            "local-only.md").exists()
    assert (multi_vault["vault-beta"] / "Lessons" / "Course-B" / "_concepts" /
            "beta-local.md").exists()


def test_repo_factory_returns_sqlite_repo(repo_factory):
    """`repo_factory()` returns a fresh SQLiteRepository (IndexRepository subclass)."""
    repo = repo_factory()
    assert isinstance(repo, IndexRepository)


def test_repo_factory_unique_db_paths(repo_factory):
    """Each call returns a repo with a distinct db_path."""
    r1 = repo_factory()
    r2 = repo_factory()
    assert r1.db_path != r2.db_path


def test_fixtures_are_isolated(minimal_vault: Path):
    """Mutating the tmp copy does not affect the source fixture."""
    (minimal_vault / "_sources" / "alpha.md").write_text("mutated")
    src = Path(__file__).parent / "fixtures" / "minimal-vault" / "_sources" / "alpha.md"
    assert "mutated" not in src.read_text()
