"""Shared FTS5 retrieval helpers (TASK 007 / C-6).

Extracted verbatim from `wiki_search` so the alias-expanded retrieval lives in
ONE place and `wiki-search` (R-5.5) + `wiki-query` (R-6.1) can never diverge.
Behaviour-preserving: `wiki-search` output stays byte-identical after the
extraction (pinned by `tests/test_wiki_query_prepare.py`).
"""

from __future__ import annotations

from typing import Any

from scripts.wiki_index.query_normalizer import fold_yo, stem_fts_query


def fts_quote(surface: str) -> str:
    """Wrap a surface as an FTS5 phrase, doubling embedded double-quotes."""
    return '"' + surface.replace('"', '""') + '"'


def alias_surfaces(
    repo: Any, query: str, vaults_list: list[str] | None
) -> set[str]:
    """R-5.5 *gather* half: the canonical name + sibling aliases that ``query``
    resolves to, scoped to the searched vaults (every registered vault when
    ``vaults_list`` is ``None`` — the all-vaults search). Empty when the term
    resolves to no entity/alias. Split out (TASK 028 / F-1) so callers can stem
    the query FIRST and OR-in these exact surfaces, instead of stemming AFTER
    ``expand_query`` (which quotes the whole raw query → would broaden nothing)."""
    if vaults_list:
        target_vaults = vaults_list
    else:
        target_vaults = [v.vault_id for v in repo.list_vaults()]
    surfaces: set[str] = set()
    for vid in target_vaults:
        for s in repo.expand_query_aliases(vid, query):
            surfaces.add(s)
    return surfaces


def expand_query(repo: Any, query: str, vaults_list: list[str] | None) -> str:
    """R-5.5: OR-expand ``query`` with the matched entity's canonical name +
    sibling aliases. No-op (returns ``query`` unchanged) when the term resolves
    to no entity/alias. (Retained for back-compat; ``wiki-search`` now composes
    via ``build_search_query``.)"""
    surfaces = alias_surfaces(repo, query, vaults_list)
    if not surfaces:
        return query
    surfaces.add(query)
    return " OR ".join(fts_quote(s) for s in sorted(surfaces))


def build_search_query(
    repo: Any, raw: str, vaults_list: list[str] | None, *,
    stem: bool, expand: bool,
) -> str:
    """``wiki-search`` MATCH builder (TASK 028 / Q-028-3, F-1 corrected order).

    Stem + ё-fold the BARE raw query first (``stem_fts_query`` — folds always,
    stems bare content tokens when ``stem``), then OR-in the (ё-folded, quoted,
    UNSTEMMED) alias surfaces: ``(<stemmed-folded-raw>) OR "alias1" OR …``. Alias
    surfaces stay exact (they are proper-noun-ish entity names); the user's typed
    words still get inflection broadening even on an alias hit."""
    base = stem_fts_query(raw, stem=stem)
    # Defense-in-depth (vdd-multi LOW): an empty/whitespace-only raw query yields
    # base='' → never paren-wrap it into `() OR …` (an FTS5 syntax error). Today
    # alias_surfaces is empty for such a query (exact-match resolution), but guard
    # the invariant so a future fuzzy alias lookup can't surface a `()`.
    if not base.strip():
        return base
    if not expand:
        return base
    surfaces = alias_surfaces(repo, raw, vaults_list)
    if not surfaces:
        return base
    clauses = ["(" + base + ")"]
    clauses.extend(fts_quote(fold_yo(s)) for s in sorted(surfaces))
    return " OR ".join(clauses)
