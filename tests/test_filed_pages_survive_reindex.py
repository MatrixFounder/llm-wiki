"""DF-049-1 — filed `_queries/`/`_verifications/` pages must survive reindex on
EVERY built-in layout, not just karpathy.

The RAG write path (`wiki-query apply` / `wiki-verify-multi apply`) files to
`<root>/_queries/` + `<root>/_verifications/` unconditionally and self-indexes
with project `_vault_` (`derive_slug`). Pre-fix, the non-karpathy layouts had
no globs for those subdirs, so the next `wiki-reindex --delta`/`--full` pruned
the self-indexed row while the Class-A file stayed on disk.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_delta, reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository

_SCHEMA_FM = ("---\nname: WIKI_SCHEMA\nvault_id: {vid}\nschema_version: '2.0'\n"
              "language: en\nlayout: {layout}\n---\n\n# s\n")

_QUERY_PAGE = ("---\ntype: query\nquestion: what is x\ndate: '2026-07-07'\n"
               "cites: ['_vault_/some-src']\ntags: [query]\n---\n\nAnswer body.\n")
_VERDICT_PAGE = ("---\ntype: verification\ntitle: 'Verdict: q'\n"
                 "verifies: _vault_/filed-q\nverdict: pass\ncritics: [c1]\n"
                 "answer_hash: " + "a" * 64 + "\ndate: '2026-07-07'\n"
                 "tags: [verification]\n---\n\n_No findings._\n")


@pytest.mark.parametrize("layout", ["obsidian-personal", "dev-project", "cybos",
                                    "karpathy"])
def test_filed_rag_pages_survive_full_and_delta(tmp_path: Path, layout: str) -> None:
    vid = f"filed-{layout[:8].rstrip('-')}"
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "WIKI_SCHEMA.md").write_text(
        _SCHEMA_FM.format(vid=vid, layout=layout))
    q = vault / "_queries" / "filed-q.md"
    v = vault / "_verifications" / "verify-filed-q.md"
    q.parent.mkdir()
    v.parent.mkdir()
    q.write_text(_QUERY_PAGE)
    v.write_text(_VERDICT_PAGE)

    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id=vid, name=vid, root_path=vault,
        schema_version="7.0", registered_at=datetime(2026, 7, 7)))
    try:
        # --full walks the layout grammar: both pages must be discovered with
        # the karpathy-compatible identity (project `_vault_`, db_type intact —
        # `wiki-verify-multi` loads query pages at VAULT_TIER_PROJECT).
        reindex_full(repo, vid)
        qp = repo.get_page(vid, "filed-q", "_vault_")
        vp = repo.get_page(vid, "verify-filed-q", "_vault_")
        assert qp is not None and qp.type == "query", layout
        assert vp is not None and vp.type == "verification", layout

        # --delta on an unchanged tree must not prune them (the DF-049-1 bug:
        # rows self-indexed by apply were deleted as walk-invisible).
        reindex_delta(repo, vid)
        assert repo.get_page(vid, "filed-q", "_vault_") is not None, layout
        assert repo.get_page(vid, "verify-filed-q", "_vault_") is not None, layout

        # The R-6.5e read-side: the query page's `cites:` frontmatter yields a
        # `cited` ref on rebuild (this is what the TASK-049 classification-leak
        # lint check joins over).
        refs = {(r.entity_slug, r.ref_type)
                for r in repo.refs_from(vid, "filed-q", "_vault_")}
        assert ("some-src", "cited") in refs, layout
    finally:
        repo.close()
