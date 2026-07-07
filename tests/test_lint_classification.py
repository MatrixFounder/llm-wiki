"""TASK 049 (R-6) — DAL `find_classification_leaks`/`find_invalid_classifications`
+ the `wiki-lint` `classification-leak`/`invalid-classification` categories.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from scripts.wiki_index.lint import check_classification_policy, run_all_checks
from scripts.wiki_index.models import Page, PageRef, Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository

VID = "leak-vault"
LEVELS = ["public", "internal", "restricted"]


def _page(slug: str, *, cls: object = "__absent__", project: str = "_vault_",
          ptype: str = "summary") -> Page:
    fm: dict[str, object] = {"tags": ["t"]}
    if cls != "__absent__":
        fm["classification"] = cls
    return Page(
        vault_id=VID, slug=slug, project=project, type=ptype, title=slug,
        file_path=f"{project}/_sources/{slug}.md", date=date(2026, 7, 1),
        last_modified=datetime(2026, 7, 1), file_hash=f"h-{slug}",
        frontmatter_json=fm, body_excerpt="b", tags=["t"], tldr="t",
    )


def _ref(page_slug: str, target: str, ref_type: str,
         project: str = "_vault_") -> PageRef:
    return PageRef(vault_id=VID, page_slug=page_slug, page_project=project,
                   entity_slug=target, ref_type=ref_type)


@pytest.fixture
def repo(tmp_path: Path):
    r = SQLiteRepository(tmp_path / "leak.db")
    r.apply_schema()
    r.register_vault(Vault(
        vault_id=VID, name=VID, root_path=tmp_path / VID,
        schema_version="7.0", registered_at=datetime(2026, 7, 1)))
    yield r
    r.close()


# =============================================================================
# 049-06 — DAL unit tests (in-bead RED per plan-review F4)
# =============================================================================

def test_leak_found_via_cited_and_verifies(repo):
    repo.upsert_page(_page("digest", cls="public", ptype="query"))
    repo.upsert_page(_page("secret", cls="restricted"))
    repo.upsert_page(_page("verdict", cls="public", ptype="verification"))
    repo.replace_refs(VID, "digest", "_vault_", [_ref("digest", "secret", "cited")])
    repo.replace_refs(VID, "verdict", "_vault_",
                      [_ref("verdict", "secret", "verifies")])
    leaks = repo.find_classification_leaks(VID, LEVELS, "public")
    assert {(l.page_slug, l.target_slug, l.ref_type) for l in leaks} == {
        ("digest", "secret", "cited"), ("verdict", "secret", "verifies")}
    assert all(l.page_level == "public" and l.target_level == "restricted"
               for l in leaks)


def test_no_leak_same_or_lower_level_or_default(repo):
    repo.upsert_page(_page("digest", cls="restricted", ptype="query"))
    repo.upsert_page(_page("peer", cls="restricted"))
    repo.upsert_page(_page("open", cls="public"))
    repo.upsert_page(_page("unlabeled"))          # default = public
    repo.replace_refs(VID, "digest", "_vault_", [
        _ref("digest", "peer", "cited"),
        _ref("digest", "open", "cited"),
        _ref("digest", "unlabeled", "cited"),
    ])
    assert repo.find_classification_leaks(VID, LEVELS, "public") == []


def test_same_slug_two_projects_not_flagged_count1_guard(repo):
    """Q-049-3: the project-less entity_slug resolves to >1 page → skip."""
    repo.upsert_page(_page("digest", cls="public", ptype="query"))
    repo.upsert_page(_page("dup", cls="restricted", project="proj-a"))
    repo.upsert_page(_page("dup", cls="public", project="proj-b"))
    repo.replace_refs(VID, "digest", "_vault_", [_ref("digest", "dup", "cited")])
    assert repo.find_classification_leaks(VID, LEVELS, "public") == []


def test_out_of_ladder_label_skipped_by_leak_flagged_invalid(repo):
    repo.upsert_page(_page("digest", cls="public", ptype="query"))
    repo.upsert_page(_page("weird", cls="geheim"))
    repo.upsert_page(_page("numeric", cls=7))
    repo.upsert_page(_page("nulled", cls=None))
    repo.replace_refs(VID, "digest", "_vault_", [_ref("digest", "weird", "cited")])
    assert repo.find_classification_leaks(VID, LEVELS, "public") == []
    bad = repo.find_invalid_classifications(VID, LEVELS)
    assert {b.page_slug for b in bad} == {"weird", "numeric"}   # null NOT flagged


def test_mentioned_refs_never_flagged(repo):
    repo.upsert_page(_page("digest", cls="public", ptype="query"))
    repo.upsert_page(_page("secret", cls="restricted"))
    repo.replace_refs(VID, "digest", "_vault_",
                      [_ref("digest", "secret", "mentioned")])
    assert repo.find_classification_leaks(VID, LEVELS, "public") == []


# =============================================================================
# 049-07 — lint check + wiring
# =============================================================================

def _vault_with_schema(tmp_path: Path, policy: str) -> Path:
    root = tmp_path / VID
    root.mkdir(exist_ok=True)
    (root / "WIKI_SCHEMA.md").write_text(
        f"---\nname: WIKI_SCHEMA\nvault_id: {VID}\n"
        "schema_version: '2.0'\nlanguage: en\nlayout: karpathy\n"
        + policy + "---\n\n# s\n")
    return root


_POLICY = "policy:\n  levels: [public, internal, restricted]\n"


def test_lint_no_policy_block_is_silent(repo, tmp_path):
    root = _vault_with_schema(tmp_path, "")
    repo.upsert_page(_page("digest", cls="public", ptype="query"))
    repo.upsert_page(_page("secret", cls="restricted"))
    repo.replace_refs(VID, "digest", "_vault_", [_ref("digest", "secret", "cited")])
    assert check_classification_policy(repo, VID, root, strict=False) == []


def test_lint_leak_warning_then_error_under_strict(repo, tmp_path):
    root = _vault_with_schema(tmp_path, _POLICY)
    repo.upsert_page(_page("digest", cls="public", ptype="query"))
    repo.upsert_page(_page("secret", cls="restricted"))
    repo.replace_refs(VID, "digest", "_vault_", [_ref("digest", "secret", "cited")])
    issues = check_classification_policy(repo, VID, root, strict=False)
    assert [i.category for i in issues] == ["classification-leak"]
    assert issues[0].severity == "warning"
    assert issues[0].page_slug == "digest"
    strict = check_classification_policy(repo, VID, root, strict=True)
    assert strict[0].severity == "error"


def test_lint_invalid_classification_warning_never_strict_gated(repo, tmp_path):
    root = _vault_with_schema(tmp_path, _POLICY)
    repo.upsert_page(_page("weird", cls="s3cret-tier"))
    for strict in (False, True):
        issues = check_classification_policy(repo, VID, root, strict=strict)
        assert [i.category for i in issues] == ["invalid-classification"]
        assert issues[0].severity == "warning"
        # CWE-209: the value is withheld from the report.
        assert "s3cret-tier" not in str(issues[0].details)


def test_lint_malformed_policy_block_surfaces(repo, tmp_path):
    root = _vault_with_schema(
        tmp_path, "policy:\n  levels: [public, public]\n")
    issues = check_classification_policy(repo, VID, root, strict=False)
    assert [i.category for i in issues] == ["invalid-policy"]


def test_run_all_checks_wires_classification(repo, tmp_path):
    _vault_with_schema(tmp_path, _POLICY)
    repo.upsert_page(_page("digest", cls="public", ptype="query"))
    repo.upsert_page(_page("secret", cls="restricted"))
    repo.replace_refs(VID, "digest", "_vault_", [_ref("digest", "secret", "cited")])
    issues = run_all_checks(repo, vaults=[VID])
    assert any(i.category == "classification-leak" for i in issues)
