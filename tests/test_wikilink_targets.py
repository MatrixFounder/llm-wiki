"""Wikilink targets resolve in the APP, not only in the index.

THE BUG (regression-guarded here): every generated `[[…]]` used to carry the page SLUG.
That is right only where filename == slug — `_concepts/<slug>.md` under every layout, and
SOURCE notes only under `slug_strategy: identity` (karpathy). Under `obsidian-personal` a
note is filed under its HUMAN TITLE, so `[[<slug>]]` resolved in the INDEX (slug is the
primary key, `wiki-lint` stayed green) while the app showed the link as unresolved and
offered to create an EMPTY note on click. `page_link_targets` maps slug → filename; these
tests pin that mapping and the emission sites that must use it.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from scripts.wiki_index.models import Page, PageRef, Vault
from scripts.wiki_index.rendering import render_concept_mentions_body, render_index
from scripts.wiki_index.sqlite_repository import SQLiteRepository

_VAULT = "wl-test"


@pytest.fixture
def repo(tmp_path):
    r = SQLiteRepository(tmp_path / "wl.db")
    r.apply_schema()
    r.register_vault(Vault(vault_id=_VAULT, name=_VAULT, root_path=tmp_path / "v",
                           schema_version="7.0", registered_at=datetime(2026, 9, 1)))
    yield r
    r.close()


def _page(repo, slug: str, file_path: str, *, typ: str = "summary") -> None:
    repo.upsert_page(Page(
        vault_id=_VAULT, slug=slug, project="_vault_", type=typ, title=slug.title(),
        file_path=file_path, date=date(2026, 9, 1), last_modified=datetime(2026, 9, 1),
        file_hash=slug, frontmatter_json={"tags": []}, body_excerpt="x", tags=[]))


# --- the mapping itself ------------------------------------------------------------

def test_para_note_maps_to_its_filename_not_its_slug(repo):
    """The reported bug: a note filed under its human title."""
    _page(repo, "building-ai-native-startups-005-cyberfund-воркшоп",
          "03 - Learning/Webinars/Building AI-Native Startups 005 — Cyberfund воркшоп.md")
    got = repo.page_link_targets(_VAULT, ["building-ai-native-startups-005-cyberfund-воркшоп"])
    assert got == {"building-ai-native-startups-005-cyberfund-воркшоп":
                   "Building AI-Native Startups 005 — Cyberfund воркшоп"}


def test_karpathy_shape_is_the_identity_map(repo):
    """filename == slug (identity slug_strategy) → output must stay byte-identical."""
    _page(repo, "attention-is-all-you-need", "_sources/attention-is-all-you-need.md")
    assert repo.page_link_targets(_VAULT, ["attention-is-all-you-need"]) == {
        "attention-is-all-you-need": "attention-is-all-you-need"}


def test_concept_pages_are_unaffected(repo):
    """`_concepts/<slug>.md` is named by slug in every layout — the mapping is a no-op."""
    _page(repo, "posthog", "03 - Learning/Webinars/_concepts/posthog.md", typ="concept")
    assert repo.page_link_targets(_VAULT, ["posthog"]) == {"posthog": "posthog"}


def test_ambiguous_basename_falls_back_to_the_path(repo):
    """Two files share a basename → the bare name is ambiguous, so address by path."""
    _page(repo, "notes-a", "A/Notes.md")
    _page(repo, "notes-b", "B/Notes.md")
    got = repo.page_link_targets(_VAULT, ["notes-a", "notes-b"])
    assert got == {"notes-a": "A/Notes", "notes-b": "B/Notes"}


def test_unknown_slug_falls_back_to_itself(repo):
    """A forward edge to a page that does not exist yet must not lose its target."""
    assert repo.page_link_targets(_VAULT, ["not-indexed"]) == {"not-indexed": "not-indexed"}


def test_filename_with_wikilink_unsafe_chars_falls_back_to_slug(repo):
    """`[`/`]`/`|`/`#`/`^` cannot live inside `[[…]]` — keep the slug rather than emit a broken link."""
    _page(repo, "weird-note", "X/Weird [draft] | v2.md")
    assert repo.page_link_targets(_VAULT, ["weird-note"]) == {"weird-note": "weird-note"}


def test_empty_input_is_empty(repo):
    assert repo.page_link_targets(_VAULT, []) == {}
    assert repo.page_link_targets(_VAULT, ["", None]) == {}   # type: ignore[list-item]


def test_single_slug_convenience(repo):
    _page(repo, "s", "Folder/Human Title.md")
    assert repo.page_link_target(_VAULT, "s") == "Human Title"
    assert repo.page_link_target(_VAULT, "missing") == "missing"


# --- the emission sites ------------------------------------------------------------

def test_mentions_ledger_links_the_filename(repo):
    """`wiki-index-render --concept-mentions` — the block the user clicked through."""
    _page(repo, "src-note", "03 - Learning/Webinars/Human Readable Title.md")
    repo.upsert_refs([PageRef(vault_id=_VAULT, page_slug="src-note", page_project="_vault_",
                              entity_slug="workos", ref_type="mentioned", trust_level="high")])
    body = render_concept_mentions_body(repo, _VAULT, "workos")
    assert "- [[Human Readable Title]]" in body
    assert "[[src-note]]" not in body


def test_index_md_links_the_filename_and_keeps_the_title_as_display(repo):
    _page(repo, "src-note", "Area/Human Readable Title.md")
    md = render_index(repo, _VAULT)
    assert "[[Human Readable Title|Src-Note]]" in md
    assert "[[src-note|" not in md


def test_query_page_sources_link_the_filename():
    from scripts.wiki_skills.wiki_query import _render_query_page
    out = _render_query_page(
        "q?", "2026-09-16", ["_vault_/src-note"], "answer",
        link_targets={"src-note": "Human Readable Title"})
    assert "- [[Human Readable Title]]" in out
    out_nomap = _render_query_page("q?", "2026-09-16", ["_vault_/src-note"], "answer")
    assert "- [[src-note]]" in out_nomap          # no map → previous behaviour, never a crash


def test_verdict_page_sources_link_the_filename():
    from scripts.wiki_skills.wiki_verify_multi import _render_verdict_page
    out = _render_verdict_page(
        "_vault_", "q-1", "pass", ["c1"], "h" * 8, "2026-09-16", ["_vault_/src-note"], [],
        link_targets={"src-note": "Human Readable Title"})
    assert "- [[Human Readable Title]]" in out


def test_typed_page_cite_and_edges_link_the_filename():
    from scripts.wiki_skills.wiki_extract_decisions._pages import render_page
    out = render_page(
        {"class": "decision", "title": "T", "body": "B", "source_quote": "Q",
         "status": "accepted", "edges": {"supersedes": ["old-decision"]}},
        slug="new-decision", vault_id=_VAULT, source_slug="src-note", today=date(2026, 9, 16),
        link_targets={"src-note": "Human Readable Title", "old-decision": "Old Decision"})
    assert "[[Human Readable Title]]" in out      # body cite
    assert "[[Old Decision]]" in out              # frontmatter edge


# --- the guard that keeps it from coming back --------------------------------------

def test_lint_flags_a_slug_only_wikilink(tmp_path):
    """`wiki-lint` must SEE what `orphan-link` structurally cannot: an index-resolvable,
    app-unresolvable link. This is the check that would have caught the original bug."""
    from scripts.wiki_index.lint import check_slug_only_wikilinks
    root = tmp_path / "v"
    (root / "Notes").mkdir(parents=True)
    (root / "_concepts").mkdir(parents=True)
    r = SQLiteRepository(tmp_path / "lint.db")
    r.apply_schema()
    r.register_vault(Vault(vault_id=_VAULT, name=_VAULT, root_path=root,
                           schema_version="7.0", registered_at=datetime(2026, 9, 1)))
    # A note filed under its human title, and a concept linking it BY SLUG.
    (root / "Notes" / "Human Readable Title.md").write_text("# T\n", encoding="utf-8")
    (root / "_concepts" / "workos.md").write_text(
        "# WorkOS\n\n- [[src-note]]\n", encoding="utf-8")
    _page(r, "src-note", "Notes/Human Readable Title.md")
    _page(r, "workos", "_concepts/workos.md", typ="concept")

    issues = check_slug_only_wikilinks(r, _VAULT, root)
    assert [i.category for i in issues] == ["slug-only-wikilink"]
    assert issues[0].page_slug == "workos"
    assert issues[0].details["target"] == "src-note"
    assert "Human Readable Title" in issues[0].details["hint"]

    # Fixed → silent.
    (root / "_concepts" / "workos.md").write_text(
        "# WorkOS\n\n- [[Human Readable Title]]\n", encoding="utf-8")
    assert check_slug_only_wikilinks(r, _VAULT, root) == []
    r.close()


def test_lint_ignores_links_to_pages_that_were_never_filed(tmp_path):
    """A link to a page that does not exist is `orphan-link`, not this category — the
    check must stay narrow or it drowns in a real vault's pre-existing backlog."""
    from scripts.wiki_index.lint import check_slug_only_wikilinks
    root = tmp_path / "v"
    (root / "_concepts").mkdir(parents=True)
    r = SQLiteRepository(tmp_path / "lint2.db")
    r.apply_schema()
    r.register_vault(Vault(vault_id=_VAULT, name=_VAULT, root_path=root,
                           schema_version="7.0", registered_at=datetime(2026, 9, 1)))
    (root / "_concepts" / "c.md").write_text(
        "# C\n\n- [[never-filed]]\n- [[Attachments/img.png]]\n", encoding="utf-8")
    _page(r, "c", "_concepts/c.md", typ="concept")
    assert check_slug_only_wikilinks(r, _VAULT, root) == []
    r.close()


def test_run_all_checks_wires_the_new_category(tmp_path):
    """Wiring guard: the check must reach `run_all_checks` (what the `wiki-lint` CLI calls),
    not just be importable. A check nobody runs is the same as no check."""
    from scripts.wiki_index.lint import run_all_checks
    root = tmp_path / "v"
    (root / "Notes").mkdir(parents=True)
    (root / "_concepts").mkdir(parents=True)
    (root / "WIKI_SCHEMA.md").write_text(
        "---\nvault_id: wl-test\nlayout: obsidian-personal\nlanguage: ru\n---\n", encoding="utf-8")
    (root / "Notes" / "Human Readable Title.md").write_text("# T\n", encoding="utf-8")
    (root / "_concepts" / "workos.md").write_text(
        "# WorkOS\n\n- [[src-note]]\n", encoding="utf-8")
    r = SQLiteRepository(tmp_path / "wired.db")
    r.apply_schema()
    r.register_vault(Vault(vault_id=_VAULT, name=_VAULT, root_path=root,
                           schema_version="7.0", registered_at=datetime(2026, 9, 1)))
    _page(r, "src-note", "Notes/Human Readable Title.md")
    _page(r, "workos", "_concepts/workos.md", typ="concept")
    cats = [i.category for i in run_all_checks(r, vaults=[_VAULT])]
    r.close()
    assert "slug-only-wikilink" in cats
