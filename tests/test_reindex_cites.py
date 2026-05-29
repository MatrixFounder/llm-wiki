"""TASK 007 / bead 007-02 — reindex `cites:` → `ref_type='cited'` (R-6.5e).

The §D8 durability read-side: a `type=query` page's `cites:` frontmatter is
re-materialised as `cited` `page_entity_refs` on `wiki-reindex --full`, unioned
into the page's single `replace_refs` call (so body `mentioned` refs are NOT
clobbered — Arch M-1), and canonicalized through the alias map by Step 2.5
(AM-3) with `ref_type` preserved (Arch M-2).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import (
    _cited_refs_from_frontmatter,
    reindex_full,
)
from scripts.wiki_index.sqlite_repository import SQLiteRepository


def _write(vault: Path, rel: str, fm: str, body: str) -> None:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{fm}\n---\n\n{body}\n", encoding="utf-8")


def _repo(tmp_path: Path, vault: Path) -> SQLiteRepository:
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id="test-vault", name="v", root_path=vault,
        schema_version="4.0", registered_at=datetime(2026, 5, 29),
    ))
    return repo


def _refs(repo: SQLiteRepository) -> set[tuple[str, str, str]]:
    return {
        (r["page_slug"], r["entity_slug"], r["ref_type"])
        for r in repo._connect().execute(
            "SELECT page_slug, entity_slug, ref_type FROM page_entity_refs "
            "WHERE vault_id = 'test-vault'"
        ).fetchall()
    }


def test_e2e_01_cited_ref_unioned_with_body_mentioned(tmp_path: Path) -> None:
    """The §D8 core (Arch M-1): a query page's `cites:` becomes a `cited` ref
    AND the body `[[bar]]` `mentioned` ref survives — both present, not
    clobbered, after a full reindex."""
    vault = tmp_path / "vault"
    _write(
        vault, "_queries/how-hermes-routes.md",
        "type: query\ntitle: How Hermes routes\ndate: 2026-05-29\n"
        'tags: [query]\ncites: ["_vault_/foo"]',
        "# Answer\n\nSee also [[bar]] for context.",
    )
    repo = _repo(tmp_path, vault)
    result = reindex_full(repo, "test-vault")
    refs = _refs(repo)
    assert ("how-hermes-routes", "foo", "cited") in refs, "cites: not materialised as cited"
    assert ("how-hermes-routes", "bar", "mentioned") in refs, "body mentioned ref clobbered (M-1 regression)"
    assert result["cite_skipped"] == []
    repo.close()


def test_e2e_02_cited_target_canonicalized_through_alias_reftype_preserved(
    tmp_path: Path,
) -> None:
    """AM-3 (Arch M-2): a `cites:` target that is a registered alias re-points to
    the canonical entity, with `ref_type` STILL `'cited'` (never degraded to
    `'mentioned'`)."""
    vault = tmp_path / "vault"
    _write(
        vault, "_concepts/hermes-agent.md",
        "type: concept\nslug: hermes-agent\ntitle: Hermes Agent\n"
        'date: 2026-05-29\ntags: [concept]\naliases: ["old-name"]',
        "# Hermes Agent\n\nThe agent.",
    )
    _write(
        vault, "_queries/q.md",
        "type: query\ntitle: Q\ndate: 2026-05-29\ntags: [query]\n"
        'cites: ["_vault_/old-name"]',
        "# Answer\n\nbody.",
    )
    repo = _repo(tmp_path, vault)
    reindex_full(repo, "test-vault")
    refs = _refs(repo)
    assert ("q", "hermes-agent", "cited") in refs, "cited target not canonicalized through alias"
    assert ("q", "old-name", "cited") not in refs, "stale alias slug left behind"
    # explicit anti-degradation: the canonicalized row is still 'cited'
    assert not any(s == "q" and rt == "mentioned" for (s, _e, rt) in refs)
    repo.close()


def test_e2e_03_malformed_cites_skip_and_report(tmp_path: Path) -> None:
    """Report-and-skip on malformed `cites:` entries — never silent-drop, never
    raise; the valid entry still lands."""
    vault = tmp_path / "vault"
    _write(
        vault, "_queries/q.md",
        "type: query\ntitle: Q\ndate: 2026-05-29\ntags: [query]\n"
        'cites: ["", "no-slash", "_vault_/ok"]',
        "# Answer\n\nbody.",
    )
    repo = _repo(tmp_path, vault)
    result = reindex_full(repo, "test-vault")
    refs = _refs(repo)
    assert ("q", "ok", "cited") in refs
    # two malformed entries ("" → no '/'; "no-slash" → no '/') recorded
    assert len(result["cite_skipped"]) == 2
    # CWE-117/209: the report names the page + a generic reason, never the value
    for entry in result["cite_skipped"]:
        assert entry["page_slug"] == "q"
        assert "malformed" in entry["reason"]
    repo.close()


def test_unit_cited_refs_parser() -> None:
    """TC-UNIT: `_cited_refs_from_frontmatter` parses `project/slug`, dedups on
    slug, and stores only the slug as entity_slug with the expected columns."""
    skipped: list[dict[str, object]] = []
    refs = _cited_refs_from_frontmatter(
        {"cites": ["_vault_/foo", "courseA/bar", "_vault_/foo"]},
        "v", "qslug", "_vault_", skipped,
    )
    assert {r.entity_slug for r in refs} == {"foo", "bar"}  # dedup foo
    assert all(r.ref_type == "cited" for r in refs)
    assert all(r.trust_level == "medium" for r in refs)
    assert all(r.line_start is None and r.source_quote is None for r in refs)
    assert all(r.page_slug == "qslug" for r in refs)
    assert skipped == []


def test_unit_cited_refs_parser_malformed_recorded() -> None:
    skipped: list[dict[str, object]] = []
    refs = _cited_refs_from_frontmatter(
        {"cites": ["", "noslash", "_vault_/", "/onlyslug", 42, "_vault_/ok"]},
        "v", "q", "_vault_", skipped,
    )
    assert {r.entity_slug for r in refs} == {"ok"}
    assert len(skipped) == 5  # "", noslash, _vault_/ (empty slug), /onlyslug (empty proj), 42
    # non-list cites → empty, no skip
    assert _cited_refs_from_frontmatter({"cites": "nope"}, "v", "q", "_vault_", []) == []
    assert _cited_refs_from_frontmatter({}, "v", "q", "_vault_", []) == []
