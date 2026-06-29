"""`wiki-search` CLI — real impl per task-001-28."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import date as _date_cls
from typing import cast
from urllib.parse import quote as _url_quote

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout import GLOBAL_VAULT_SENTINEL
from scripts.wiki_index.models import PageHit, Vault
from scripts.wiki_index.repository import validate_filter_field
from scripts.wiki_index.query_normalizer import fold_yo as _fold_yo
from scripts.wiki_skills._common import build_repo_config, emit, resolve_vault_root_for_cli
from scripts.wiki_skills._retrieval import build_search_query as _build_search_query
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
    p.add_argument("--tag", default=None,
                   help="TASK 033: convenience alias for --where 'tags=<value>' — "
                        "match a MEMBER of the frontmatter `tags` list (e.g. "
                        "--tag decision lists every typed-class 'decision' page). "
                        "List membership, not whole-list equality.")
    p.add_argument("--as-of", dest="as_of", default=None, metavar="YYYY-MM-DD",
                   help="TASK 034: temporal filter — return only pages ACTIVE as of "
                        "this date. 'Active' = created (pages.date / authored "
                        "valid_from) on-or-before the date AND not yet superseded/"
                        "invalidated by then (the event graph; or an authored "
                        "valid_to). Answers 'which decisions were active on the "
                        "incident date' without an LLM. Composes with the query and "
                        "the other filters; valid on its own.")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--format", choices=["markdown", "json"], default="json")
    p.add_argument("--no-expand-aliases", action="store_true",
                   help="Disable alias expansion (TASK 005 / R-5.5). By default "
                        "a query that resolves to an entity is OR-expanded with "
                        "that entity's canonical name + sibling aliases.")
    p.add_argument("--exact", "--no-stem", dest="exact", action="store_true",
                   default=False,
                   help="TASK 028: disable query-side stemming/inflection "
                        "broadening (precise literal terms). The always-on ё/е "
                        "fold still applies (the corpus is folded). Omit for "
                        "default inflection-tolerant search.")
    p.add_argument("--vault-root", default=None,
                   help="Vault root (resolve a local index_db); walks up from CWD when omitted.")
    p.add_argument("--db-path", default=None)
    return p


def _obsidian_url(vault: Vault | None, file_path: str) -> str | None:
    """Build an obsidian://open URI for a search hit.

    Returns None when the vault is unknown (stale registry / removed vault).
    vault_name is the root folder basename — the identifier Obsidian uses in
    its URI scheme (may differ from vault_id if the folder was renamed).
    """
    if vault is None:
        return None
    vault_name = _url_quote(vault.root_path.name, safe="")
    file_enc = _url_quote(file_path, safe="/-_.~")
    return f"obsidian://open?vault={vault_name}&file={file_enc}"


def _term_safe(s: str) -> str:
    """Strip C0/C1 control chars from untrusted DB strings before terminal output (H-6).

    Prevents terminal escape injection (CWE-150) when titles/snippets from
    externally-imported pages reach --format markdown on a TTY.
    """
    return "".join(
        c for c in s
        if not (ord(c) < 0x20 or ord(c) == 0x7F or 0x80 <= ord(c) <= 0x9F)
    )


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
    if args.tag is not None:
        # TASK 033 (R-2): --tag desugars to a `tags` predicate; the DAL predicate
        # matches it as a LIST MEMBER (json_each), and the dup-guard below covers
        # `--tag x --where tags=y` (field 'tags' seen twice → INVALID_FILTER).
        where_fields.append(("tags", args.tag))

    # TASK 034 (R-1a): validate + normalize --as-of to a canonical ISO YYYY-MM-DD
    # at the boundary. A bad date → INVALID_FILTER (exit 2) WITHOUT echoing the
    # value (CWE-209/117), mirroring the --where posture. The normalized form is
    # what the DAL binds (so `pages.date`/`valid_*` ISO strings compare cleanly).
    as_of: str | None = None
    if args.as_of is not None:
        try:
            as_of = _date_cls.fromisoformat(args.as_of.strip()).isoformat()
        except ValueError:
            return emit({"error": "INVALID_FILTER", "field": "as-of",
                         "reason": "not a valid ISO date; use YYYY-MM-DD"}, 2)

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
    # nothing to search. Strip the query at the boundary so a blank/whitespace-
    # only term is treated as "no query" (TASK 028 vdd-multi: the stemming lexer
    # collapses whitespace to '', which `search_pages` rejects with a ValueError
    # the DF-1 OperationalError net never caught → uncaught crash). Mirrors
    # wiki-query's question strip.
    query_arg = args.query.strip() if args.query else None
    if not query_arg and not where_fields and not as_of:
        return emit({"error": "INVALID_QUERY", "field": "query",
                     "reason": "provide a search query, at least one metadata "
                               "filter (--where/--status/--severity/--tag), or "
                               "--as-of <date>"}, 2)

    metadata_only = not query_arg

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
                project=args.project, where_fields=wf, as_of=as_of,
                limit=args.limit,
            )
        else:
            assert query_arg is not None  # metadata_only False ⇒ query_arg truthy
            qstr: str = query_arg
            # TASK 028 (Q-028-3): stem+fold the bare query, then OR-in the exact
            # alias surfaces (F-1 order). `--exact` disables stemming only — the
            # ё/е fold stays on (the corpus is folded).
            match_query = _build_search_query(
                repo, qstr, vaults_list,
                stem=not args.exact, expand=not args.no_expand_aliases)

            def _search(q: str) -> list[PageHit]:
                return repo.search_pages(
                    q, vaults=vaults_list, types=types_list,
                    project=args.project, where_fields=wf, as_of=as_of,
                    limit=args.limit,
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
                    # DF-1 fallback: literal quoted phrase, ё-folded to stay
                    # consistent with the folded corpus (TASK 028).
                    hits = _search(_fold_yo(_fts_quote(qstr)))
                except sqlite3.OperationalError:
                    return emit({"error": "INVALID_QUERY", "field": "query",
                                 "reason": "not a valid FTS5 expression; quote terms "
                                           "containing special characters (e.g. hyphens)"}, 2)
        # R-3: resolve each unique vault_id once (cache — not once per hit).
        # The _global_ sentinel never appears as a pages.vault_id in practice,
        # but guard it explicitly so get_vault is never called with a sentinel.
        vault_cache: dict[str, Vault | None] = {
            vid: (None if vid == GLOBAL_VAULT_SENTINEL else repo.get_vault(vid))
            for vid in {h.page.vault_id for h in hits}
        }
        results = [{
            "vault_id": h.page.vault_id, "slug": h.page.slug,
            "project": h.page.project, "type": h.page.type,
            "title": h.page.title, "bm25_score": h.bm25_score,
            "snippet": h.snippet,
            "file_path": h.page.file_path,
            "obsidian_url": _obsidian_url(
                vault_cache.get(h.page.vault_id), h.page.file_path
            ),
        } for h in hits]
        if args.format == "json":
            return emit({"action": "searched", "query": query_arg,
                         "hits": results, "count": len(results)})
        # Metadata-only listings have no FTS query — describe the filter instead.
        filter_bits = [f"{f}={v}" for f, v in where_fields]
        if as_of:
            filter_bits.append(f"as-of {as_of}")
        heading = (
            f'"{query_arg}"' if query_arg
            else "filter " + " ".join(filter_bits)
        )
        # R-4/R-5: detect TTY once; append OSC 8 link (iTerm2/VS Code/modern) or
        # plain URL (pipe, or Apple Terminal which ignores OSC 8 and leaves a
        # dangling [↗] glyph with no URL — useless without the fallback).
        _is_tty = sys.stdout.isatty()
        _osc8 = _is_tty and os.environ.get("TERM_PROGRAM") != "Apple_Terminal"
        lines = [f'## {heading} — {len(results)} hits', ""]
        for r in results:
            obs_url = cast("str | None", r["obsidian_url"])
            if obs_url is not None:
                if _osc8:
                    # OSC 8 hyperlink — clickable in iTerm2 / VS Code terminal
                    suffix = f"  →  \033]8;;{obs_url}\033\\[↗]\033]8;;\033\\"
                else:
                    suffix = f"  →  {obs_url}"
            else:
                suffix = ""
            # H-6: title/snippet are untrusted content (from wiki-import of external pages).
            # Strip C0/C1 control chars before writing to a TTY-targeted stream.
            safe_title = _term_safe(cast("str", r["title"]))
            safe_snippet = _term_safe(cast("str", r["snippet"]))
            lines.append(
                f"- [[{r['vault_id']}:{r['project']}/{r['slug']}|{safe_title}]] "
                f"(BM25={r['bm25_score']:.2f}) — \"{safe_snippet}\"{suffix}"
            )
        print("\n".join(lines))
        return 0
    finally:
        repo.close()


if __name__ == "__main__":
    sys.exit(main())
