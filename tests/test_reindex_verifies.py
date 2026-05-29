"""TASK 008 / bead 008-03 — reindex `verifies:` → `ref_type='verifies'` (R-8.5e).

The §D8 durability read-side for verdict pages: a `type=verification` page's
`verifies:` frontmatter (a single `project/slug` naming the audited query page)
is re-materialised as a `verifies` `page_entity_ref` on `wiki-reindex --full`
AND `--delta`, unioned into the page's single `replace_refs` (so body `mentioned`
refs are NOT clobbered — M-1), canonicalized through the alias map by Step 2.5
(AM-3) with `ref_type` preserved (no degradation to `mentioned`). Optional
`cites:` on a verdict page → `cited` refs (Q-008-f). This generalises R-6.5e's
helper into `_frontmatter_refs(db_type, ...)`; the `type=query` `cites:` path
stays green (regression).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import (
    _frontmatter_refs,
    reindex_delta,
    reindex_full,
)
from scripts.wiki_index.sqlite_repository import SQLiteRepository


def _write(vault: Path, rel: str, fm: str, body: str) -> None:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{fm}\n---\n\n{body}\n", encoding="utf-8")


def _repo(tmp_path: Path, vault: Path, registered: datetime = datetime(2026, 5, 29)) -> SQLiteRepository:
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id="test-vault", name="v", root_path=vault,
        schema_version="5.0", registered_at=registered,
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


def test_e2e_01_verifies_ref_unioned_with_body_mentioned(tmp_path: Path) -> None:
    """§D8 core (M-1): a verdict page's `verifies:` becomes a `verifies` ref AND
    the body `[[bar]]` `mentioned` ref survives — full reindex, not clobbered."""
    vault = tmp_path / "vault"
    _write(
        vault, "_verifications/how-hermes-routes.md",
        "type: verification\ntitle: Verdict\ndate: 2026-05-29\n"
        "tags: [verification]\nverdict: pass\nverifies: _vault_/how-hermes-routes",
        "# Findings\n\nSee also [[bar]] for context.",
    )
    repo = _repo(tmp_path, vault)
    reindex_full(repo, "test-vault")
    refs = _refs(repo)
    assert ("how-hermes-routes", "how-hermes-routes", "verifies") in refs
    assert ("how-hermes-routes", "bar", "mentioned") in refs  # M-1: not clobbered
    repo.close()


def test_e2e_01b_verifies_ref_survives_delta(tmp_path: Path) -> None:
    """Delta-symmetry: `--delta` reconstructs the same `verifies` ref (old
    registered_at so the file mtime always exceeds the delta cutoff)."""
    vault = tmp_path / "vault"
    _write(
        vault, "_verifications/v1.md",
        "type: verification\ntitle: V\ndate: 2026-05-29\n"
        "tags: [verification]\nverdict: fail\nverifies: _vault_/q1",
        "# Findings\n\nbody.",
    )
    repo = _repo(tmp_path, vault, registered=datetime(2000, 1, 1))
    reindex_delta(repo, "test-vault")
    assert ("v1", "q1", "verifies") in _refs(repo)
    repo.close()


def test_e2e_02_verifies_target_canonicalized_through_alias(tmp_path: Path) -> None:
    """AM-3: a `verifies:` target that is a registered alias re-points to the
    canonical entity, `ref_type` STILL 'verifies' (not degraded to 'mentioned')."""
    vault = tmp_path / "vault"
    _write(
        vault, "_concepts/new-q.md",
        "type: concept\nslug: new-q\ntitle: New Q\ndate: 2026-05-29\n"
        'tags: [concept]\naliases: ["old-q"]',
        "# New Q\n\nbody.",
    )
    _write(
        vault, "_verifications/v.md",
        "type: verification\ntitle: V\ndate: 2026-05-29\n"
        "tags: [verification]\nverdict: pass\nverifies: _vault_/old-q",
        "# Findings\n\nbody.",
    )
    repo = _repo(tmp_path, vault)
    reindex_full(repo, "test-vault")
    refs = _refs(repo)
    assert ("v", "new-q", "verifies") in refs  # canonicalized, ref_type preserved
    assert ("v", "old-q", "verifies") not in refs
    repo.close()


def test_e2e_03_optional_cites_on_verdict_page(tmp_path: Path) -> None:
    """Q-008-f: a verdict page may also carry `cites:` → `cited` refs alongside
    the `verifies` ref."""
    vault = tmp_path / "vault"
    _write(
        vault, "_verifications/v.md",
        "type: verification\ntitle: V\ndate: 2026-05-29\ntags: [verification]\n"
        'verdict: pass\nverifies: _vault_/q\ncites: ["_vault_/foo"]',
        "# Findings\n\nbody.",
    )
    repo = _repo(tmp_path, vault)
    reindex_full(repo, "test-vault")
    refs = _refs(repo)
    assert ("v", "q", "verifies") in refs
    assert ("v", "foo", "cited") in refs
    repo.close()


def test_e2e_04_missing_verifies_reported_page_still_indexed(tmp_path: Path) -> None:
    """A verdict page with no `verifies:` is report-and-skipped (no verifies ref)
    but the page itself still indexes (found + upserted as type=verification)."""
    vault = tmp_path / "vault"
    _write(
        vault, "_verifications/v.md",
        "type: verification\ntitle: V\ndate: 2026-05-29\ntags: [verification]\nverdict: pass",
        "# Findings\n\nbody.",
    )
    repo = _repo(tmp_path, vault)
    result = reindex_full(repo, "test-vault")
    row = repo._connect().execute(
        "SELECT type FROM pages WHERE vault_id='test-vault' AND slug='v'").fetchone()
    assert row is not None and row["type"] == "verification"  # indexed, not skipped
    assert not any(rt == "verifies" for _ps, _es, rt in _refs(repo))
    assert any("verifies" in s.get("reason", "") for s in result["cite_skipped"])
    repo.close()


def test_e2e_05_query_cites_regression(tmp_path: Path) -> None:
    """The R-6.5e `type=query` `cites:` path still works post-generalisation."""
    vault = tmp_path / "vault"
    _write(
        vault, "_queries/q.md",
        "type: query\ntitle: Q\ndate: 2026-05-29\ntags: [query]\ncites: ['_vault_/foo']",
        "# Answer\n\nbody.",
    )
    repo = _repo(tmp_path, vault)
    reindex_full(repo, "test-vault")
    assert ("q", "foo", "cited") in _refs(repo)
    repo.close()


def test_unit_frontmatter_refs_verification() -> None:
    skipped: list[dict[str, object]] = []
    refs = _frontmatter_refs(
        "verification", {"verifies": "_vault_/q", "cites": ["_vault_/foo"]},
        "v", "vslug", "_vault_", skipped,
    )
    kinds = {(r.entity_slug, r.ref_type) for r in refs}
    assert ("q", "verifies") in kinds
    assert ("foo", "cited") in kinds
    assert all(r.trust_level == "medium" for r in refs)
    assert all(r.line_start is None and r.source_quote is None for r in refs)
    assert skipped == []


def test_unit_frontmatter_refs_query_unchanged() -> None:
    refs = _frontmatter_refs("query", {"cites": ["_vault_/foo"]}, "v", "q", "_vault_", [])
    assert {(r.entity_slug, r.ref_type) for r in refs} == {("foo", "cited")}


def test_unit_frontmatter_refs_other_type_is_noop() -> None:
    assert _frontmatter_refs(
        "concept", {"cites": ["_vault_/foo"]}, "v", "c", "_vault_", []) == []


def test_unit_verifies_malformed_recorded() -> None:
    skipped: list[dict[str, object]] = []
    refs = _frontmatter_refs(
        "verification", {"verifies": "noslash"}, "v", "v1", "_vault_", skipped)
    assert refs == []
    assert len(skipped) == 1
    assert "verifies" in skipped[0]["reason"]
