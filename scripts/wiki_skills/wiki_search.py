"""`wiki-search` CLI — real impl per task-001-28."""

from __future__ import annotations

import argparse
import sqlite3
import sys

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout import GLOBAL_VAULT_SENTINEL
from scripts.wiki_index.models import PageHit
from scripts.wiki_index.repository import validate_filter_field
from scripts.wiki_skills._common import build_repo_config, emit, resolve_vault_root_for_cli
from scripts.wiki_skills._retrieval import expand_query as _expand_query
from scripts.wiki_skills._retrieval import fts_quote as _fts_quote


def _parse_where(expr: str) -> tuple[str, str]:
    """Parse a ``--where 'field=value'`` filter into a ``(field, value)`` pair
    (TASK 013 / R-X3-META-FILTER).

    Splits on the FIRST ``=`` (values may contain ``=``). Field + value are
    stripped of surrounding whitespace for ergonomics. The field name is
    allow-list validated (`validate_filter_field`); the value is returned
    verbatim (it becomes a bound SQL parameter, so any string is safe).

    Raises ``ValueError`` on a malformed expression (no ``=``) or an invalid
    field name. The message NEVER includes the filter VALUE (CWE-209/CWE-117) —
    only the field token, which is JSON-escaped on output.
    """
    if "=" not in expr:
        raise ValueError("filter must be in FIELD=VALUE form")
    field, _, value = expr.partition("=")
    validate_filter_field(field.strip())
    return field.strip(), value.strip()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wiki-search")
    p.add_argument("query", nargs="?", default=None,
                   help="FTS5 MATCH expression. Optional when a metadata filter "
                        "(--where/--status/--severity) is given — then a non-FTS "
                        "metadata listing is returned.")
    p.add_argument("--vaults", default=None,
                   help="Comma-separated vault_ids ('all' or omit for all).")
    p.add_argument("--types", default=None)
    p.add_argument("--project", default=None)
    p.add_argument("--where", action="append", default=None, metavar="FIELD=VALUE",
                   help="TASK 013: filter by a frontmatter metadata field "
                        "(e.g. --where 'status=open'). Repeatable; multiple "
                        "filters are AND-ed. Matches by equality on "
                        "pages.frontmatter_json (not full-text), so hyphenated "
                        "values like SEV-2 work.")
    p.add_argument("--status", default=None,
                   help="Convenience alias for --where 'status=<value>'.")
    p.add_argument("--severity", default=None,
                   help="Convenience alias for --where 'severity=<value>'.")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--format", choices=["markdown", "json"], default="json")
    p.add_argument("--no-expand-aliases", action="store_true",
                   help="Disable alias expansion (TASK 005 / R-5.5). By default "
                        "a query that resolves to an entity is OR-expanded with "
                        "that entity's canonical name + sibling aliases.")
    p.add_argument("--vault-root", default=None,
                   help="Vault root (resolve a local index_db); walks up from CWD when omitted.")
    p.add_argument("--db-path", default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    vaults_list = None
    if args.vaults and args.vaults != "all":
        vaults_list = [v.strip() for v in args.vaults.split(",") if v.strip()]
    types_list = None
    if args.types:
        types_list = [t.strip() for t in args.types.split(",") if t.strip()]

    # TASK 013 (R-X3-META-FILTER): assemble the frontmatter metadata predicates
    # from the general --where primitive + the --status/--severity sugar. Field
    # names are allow-list validated here (the user-input boundary); a bad field
    # or a malformed --where yields INVALID_FILTER (exit 2) WITHOUT echoing the
    # filter value (CWE-209/CWE-117).
    where_fields: list[tuple[str, str]] = []
    try:
        for expr in (args.where or []):
            where_fields.append(_parse_where(expr))
    except ValueError as exc:
        return emit({"error": "INVALID_FILTER", "reason": str(exc)}, 2)
    if args.status is not None:
        where_fields.append(("status", args.status))
    if args.severity is not None:
        where_fields.append(("severity", args.severity))

    # Reject two predicates on the SAME field (vdd-multi critic-logic MED):
    # filters are equality-only and AND-ed, so e.g. `--status open --where
    # 'status=fixed'` (or even via two --where) can never both match → a silent
    # always-empty result. Surface it as a usage error naming the FIELD only
    # (never the value — CWE-209/117) instead of returning a confusing 0 hits.
    seen_fields: set[str] = set()
    for field, _ in where_fields:
        if field in seen_fields:
            return emit({"error": "INVALID_FILTER", "field": field,
                         "reason": f"duplicate filter for field {field!r}; give "
                                   "at most one predicate per field"}, 2)
        seen_fields.add(field)

    # A bare invocation with neither an FTS term nor a metadata filter has
    # nothing to search.
    if not args.query and not where_fields:
        return emit({"error": "INVALID_QUERY", "field": "query",
                     "reason": "provide a search query or at least one metadata "
                               "filter (--where/--status/--severity)"}, 2)

    metadata_only = not args.query

    # When --vaults is not narrowed to a specific id, use the _global_ sentinel
    # (ADR-002 §D1.1) — factory accepts it without inventing a fake vault name.
    factory_vault = vaults_list[0] if vaults_list else GLOBAL_VAULT_SENTINEL
    config = build_repo_config(  # TASK 022
        factory_vault, vault_root=resolve_vault_root_for_cli(args),
        db_path_flag=args.db_path)
    repo = make_repo(config)
    try:
        wf = where_fields or None
        if metadata_only:
            # TASK 013 non-FTS path: no MATCH term → no alias expansion, no
            # DF-1 FTS-quote fallback (both operate on an FTS query).
            hits = repo.search_pages(
                None, vaults=vaults_list, types=types_list,
                project=args.project, where_fields=wf, limit=args.limit,
            )
        else:
            qstr: str = args.query  # truthy here (metadata_only is False)
            match_query = qstr
            if not args.no_expand_aliases:
                match_query = _expand_query(repo, qstr, vaults_list)

            def _search(q: str) -> list[PageHit]:
                return repo.search_pages(
                    q, vaults=vaults_list, types=types_list,
                    project=args.project, where_fields=wf, limit=args.limit,
                )

            # DF-1 (dogfood): a raw query with an FTS5-special char (e.g. the
            # hyphen in a slug like `hermes-agent`, which FTS5 reads as a
            # column/NOT operator) raised an unhandled sqlite3.OperationalError.
            # Fall back to a literal quoted-phrase search; only a genuinely
            # un-parseable query yields a clean INVALID_QUERY envelope (never a
            # stack trace).
            try:
                hits = _search(match_query)
            except sqlite3.OperationalError:
                try:
                    hits = _search(_fts_quote(qstr))
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
        # Metadata-only listings have no FTS query — describe the filter instead.
        heading = (
            f'"{args.query}"' if args.query
            else "filter " + " ".join(f"{f}={v}" for f, v in where_fields)
        )
        lines = [f'## {heading} — {len(results)} hits', ""]
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
