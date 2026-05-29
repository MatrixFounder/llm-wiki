"""Shared FTS5 retrieval helpers (TASK 007 / C-6).

Extracted verbatim from `wiki_search` so the alias-expanded retrieval lives in
ONE place and `wiki-search` (R-5.5) + `wiki-query` (R-6.1) can never diverge.
Behaviour-preserving: `wiki-search` output stays byte-identical after the
extraction (pinned by `tests/test_wiki_query_prepare.py`).
"""

from __future__ import annotations

from typing import Any


def fts_quote(surface: str) -> str:
    """Wrap a surface as an FTS5 phrase, doubling embedded double-quotes."""
    return '"' + surface.replace('"', '""') + '"'


def expand_query(repo: Any, query: str, vaults_list: list[str] | None) -> str:
    """R-5.5: OR-expand ``query`` with the matched entity's canonical name +
    sibling aliases, scoped to the searched vaults. No-op (returns ``query``
    unchanged) when the term resolves to no entity/alias in any scoped vault —
    so default-on expansion never changes results for non-alias queries.

    When ``vaults_list`` is ``None`` (the all-vaults search), expand across every
    registered vault — otherwise default-on expansion would silently no-op for
    the most common invocation (vdd-multi F1, TASK 005)."""
    if vaults_list:
        target_vaults = vaults_list
    else:
        target_vaults = [v.vault_id for v in repo.list_vaults()]
    surfaces: set[str] = set()
    for vid in target_vaults:
        for s in repo.expand_query_aliases(vid, query):
            surfaces.add(s)
    if not surfaces:
        return query
    surfaces.add(query)
    return " OR ".join(fts_quote(s) for s in sorted(surfaces))
