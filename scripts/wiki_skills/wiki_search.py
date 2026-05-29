"""`wiki-search` CLI — real impl per task-001-28."""

from __future__ import annotations

import argparse
import sqlite3
import sys

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout import GLOBAL_VAULT_SENTINEL
from scripts.wiki_index.models import PageHit
from scripts.wiki_skills._common import emit


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wiki-search")
    p.add_argument("query", help="FTS5 MATCH expression.")
    p.add_argument("--vaults", default=None,
                   help="Comma-separated vault_ids ('all' or omit for all).")
    p.add_argument("--types", default=None)
    p.add_argument("--project", default=None)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--format", choices=["markdown", "json"], default="json")
    p.add_argument("--no-expand-aliases", action="store_true",
                   help="Disable alias expansion (TASK 005 / R-5.5). By default "
                        "a query that resolves to an entity is OR-expanded with "
                        "that entity's canonical name + sibling aliases.")
    p.add_argument("--db-path", default=None)
    return p


def _fts_quote(surface: str) -> str:
    """Wrap a surface as an FTS5 phrase, doubling embedded double-quotes."""
    return '"' + surface.replace('"', '""') + '"'


def _expand_query(repo: object, query: str, vaults_list: list[str] | None) -> str:
    """R-5.5: OR-expand `query` with the matched entity's canonical name +
    sibling aliases, scoped to the searched vaults. No-op (returns `query`
    unchanged) when the term resolves to no entity/alias in any scoped vault —
    so default-on expansion never changes results for non-alias queries.

    When `vaults_list` is None (the default all-vaults search), expand across
    every registered vault — otherwise default-on expansion would silently
    no-op for the most common invocation (vdd-multi F1)."""
    if vaults_list:
        target_vaults = vaults_list
    else:
        target_vaults = [v.vault_id for v in repo.list_vaults()]  # type: ignore[attr-defined]
    surfaces: set[str] = set()
    for vid in target_vaults:
        for s in repo.expand_query_aliases(vid, query):  # type: ignore[attr-defined]
            surfaces.add(s)
    if not surfaces:
        return query
    surfaces.add(query)
    return " OR ".join(_fts_quote(s) for s in sorted(surfaces))


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    vaults_list = None
    if args.vaults and args.vaults != "all":
        vaults_list = [v.strip() for v in args.vaults.split(",") if v.strip()]
    types_list = None
    if args.types:
        types_list = [t.strip() for t in args.types.split(",") if t.strip()]
    # When --vaults is not narrowed to a specific id, use the _global_ sentinel
    # (ADR-002 §D1.1) — factory accepts it without inventing a fake vault name.
    factory_vault = vaults_list[0] if vaults_list else GLOBAL_VAULT_SENTINEL
    config: dict[str, str] = {"vault_id": factory_vault}
    if args.db_path:
        config["db_path"] = args.db_path
    repo = make_repo(config)
    try:
        match_query = args.query
        if not args.no_expand_aliases:
            match_query = _expand_query(repo, args.query, vaults_list)

        def _search(q: str) -> list[PageHit]:
            return repo.search_pages(
                q, vaults=vaults_list, types=types_list,
                project=args.project, limit=args.limit,
            )

        # DF-1 (dogfood): a raw query with an FTS5-special char (e.g. the hyphen
        # in a slug like `hermes-agent`, which FTS5 reads as a column/NOT
        # operator) raised an unhandled sqlite3.OperationalError. Fall back to a
        # literal quoted-phrase search; only a genuinely un-parseable query
        # yields a clean INVALID_QUERY envelope (never a stack trace).
        try:
            hits = _search(match_query)
        except sqlite3.OperationalError:
            try:
                hits = _search(_fts_quote(args.query))
            except sqlite3.OperationalError:
                return emit({"error": "INVALID_QUERY", "field": "query",
                             "reason": "not a valid FTS5 expression; quote terms "
                                       "containing special characters (e.g. hyphens)"}, 2)
        results = [{
            "vault_id": h.page.vault_id, "slug": h.page.slug,
            "project": h.page.project, "type": h.page.type,
            "title": h.page.title, "bm25_score": h.bm25_score,
            "snippet": h.snippet,
        } for h in hits]
        if args.format == "json":
            return emit({"action": "searched", "query": args.query,
                         "hits": results, "count": len(results)})
        lines = [f'## "{args.query}" — {len(results)} hits', ""]
        for r in results:
            lines.append(
                f"- [[{r['vault_id']}:{r['project']}/{r['slug']}|{r['title']}]] "
                f"(BM25={r['bm25_score']:.2f}) — \"{r['snippet']}\""
            )
        print("\n".join(lines))
        return 0
    finally:
        repo.close()


if __name__ == "__main__":
    sys.exit(main())
