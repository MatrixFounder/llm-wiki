"""`wiki-query` CLI — RAG over FTS5 + entity graph (TASK 007 / R-6).

Decision-17 two-pass skill: deterministic Python plumbing only — the LLM
synthesis between `prepare` and `apply` lives in the calling agent's context
(the `wiki-query-synthesis` prompt skill). There is no `import anthropic`.

- `prepare "<question>"` (R-6.1): alias-expanded FTS retrieval → a context
  envelope `{vault_id, question, query_slug, question_hash, is_unchanged,
  retrieved_count, hits[]}`. Refuses `NO_CONTEXT` below `--min-hits`.
- `apply` (R-6.3/6.4/6.6/6.7): grounding-checked write-back of
  `_queries/<slug>.md` + self-index. (Lands in beads 007-05 / 007-06.)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import date as _date
from datetime import datetime as _datetime
from pathlib import Path

import frontmatter

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout import QUERIES_SUBDIR
from scripts.wiki_index.models import LogEvent, PageHit
from scripts.wiki_index.repository import IndexRepository
from scripts.wiki_index.security import PathTraversalError, validate_inside_vault
from scripts.wiki_skills._common import (
    atomic_write_text,
    emit,
    sanitize_markdown_text,
)
from scripts.wiki_skills._retrieval import fts_quote

_MAX_QUESTION_LEN = 1000
_MAX_SLUG_LEN = 80
_MAX_ANSWER_BYTES = 256 * 1024  # 256 KiB
_MAX_CITATIONS_BYTES = 64 * 1024  # 64 KiB
_MAX_CITATIONS = 50
_SLUG_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_ORCH_RE = re.compile(r"^[a-z0-9._:@-]{1,64}$")


def _orchestrator_id(value: str) -> str:
    """argparse validator for --orchestrator-id (007-05 spec regex). Defends a
    library caller too; the CLI default 'orchestrator' passes."""
    if not _ORCH_RE.match(value):
        raise argparse.ArgumentTypeError(
            "must match ^[a-z0-9._:@-]{1,64}$")
    return value


class _InvalidQuery(Exception):
    """Raised when an FTS5 MATCH expression is un-parseable after the DF-1
    quoted-phrase fallback (caller maps to INVALID_QUERY exit 2)."""


class _PayloadTooLarge(Exception):
    """Answer / citations payload exceeded its byte cap."""


# -----------------------------------------------------------------------------
# helpers
# -----------------------------------------------------------------------------
def _derive_query_slug(question: str) -> str:
    """Deterministic kebab slug from a free-text question (Q-A7); operator
    `--slug` overrides this. Truncated to a filesystem-safe length; falls back
    to ``"query"`` if nothing kebab-able remains."""
    from slugify import slugify

    s = slugify(question, lowercase=True, separator="-",
                regex_pattern=r"[^a-z0-9\-]")
    s = s[:_MAX_SLUG_LEN].strip("-")
    return s or "query"


def _question_hash(question: str, hits: list[PageHit]) -> str:
    """Q-A6 binding shape: sha256 over the question + the ordered retrieved
    ``project/slug`` set, so a re-query after the corpus changed re-synthesises
    (defines `is_unchanged` semantics + whether the compounding loop picks up
    new sources). BM25 order is preserved (search_pages returns ranked hits)."""
    parts = [question]
    parts.extend(f"{h.page.project}/{h.page.slug}" for h in hits)
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _hit_dict(h: PageHit) -> dict[str, object]:
    return {
        "vault_id": h.page.vault_id, "slug": h.page.slug,
        "project": h.page.project, "type": h.page.type,
        "title": h.page.title, "bm25_score": h.bm25_score,
        "snippet": h.snippet,
    }


def _scope(args: argparse.Namespace) -> tuple[list[str] | None, list[str] | None]:
    """Parse the search scope from the shared retrieval flags. ``--vaults all``
    → every vault (None); explicit list → that list; omitted → the home
    ``--vault`` (a query defaults to its own vault)."""
    if args.vaults == "all":
        vaults_list: list[str] | None = None
    elif args.vaults:
        vaults_list = [v.strip() for v in args.vaults.split(",") if v.strip()]
    else:
        vaults_list = [args.vault]
    types_list = ([t.strip() for t in args.types.split(",") if t.strip()]
                  if args.types else None)
    return vaults_list, types_list


def _build_match_query(
    repo: IndexRepository, question: str, vaults_list: list[str] | None,
    expand: bool,
) -> str:
    """Turn a natural-language QUESTION into an FTS5 OR-of-terms query (keyword
    retrieval — match-any, BM25-ranked), NOT a raw phrase.

    A raw question passed straight to FTS5 MATCH is an **implicit AND over every
    token** (incl. stopwords / question-words like 'how'/'does'/'the'), so a real
    question almost never matches any document → spurious NO_CONTEXT (dogfood
    DF-Q1). OR-of-terms + BM25 is the standard RAG-over-FTS retrieval: documents
    matching the salient content tokens rank highest; stopwords that match
    nothing contribute nothing. Tokenisation is Unicode-aware (no hardcoded
    English stopword list — the vault may be multilingual / Cyrillic).

    When `expand`, each token is alias-expanded through the entity table
    (`expand_query_aliases`) so a surface like 'hermes' also pulls in its
    canonical name + sibling aliases (R-5.5 reuse, at token granularity)."""
    tokens = list(dict.fromkeys(re.findall(r"[^\W_]+", question.lower())))
    if not tokens:
        return fts_quote(question)
    surfaces: set[str] = set(tokens)
    if expand:
        targets = vaults_list or [v.vault_id for v in repo.list_vaults()]
        for vid in targets:
            for tok in tokens:
                surfaces.update(repo.expand_query_aliases(vid, tok))
    return " OR ".join(fts_quote(s) for s in sorted(surfaces))


def _retrieve(repo: IndexRepository, question: str, args: argparse.Namespace) -> list[PageHit]:
    """Alias-expanded keyword FTS retrieval shared by `prepare` AND `apply` — so
    `apply` reproduces `prepare`'s exact retrieval to recompute `question_hash`
    (the QUESTION_CHANGED TOCTOU check). Raises `_InvalidQuery` on an
    un-parseable expression after the DF-1 quoted-phrase fallback."""
    vaults_list, types_list = _scope(args)
    match_query = _build_match_query(
        repo, question, vaults_list, not args.no_expand_aliases)

    # Default-exclude prior query answers from RAG retrieval: a synthesised
    # answer grounds on PRIMARY sources, not on other answers (avoids circular
    # citation), AND it keeps re-querying idempotent — a filed query page matches
    # its own question, so without this a same-question re-query would see a
    # changed hit set (its own answer) and never report `is_unchanged`. Operators
    # who genuinely want to search prior answers opt in with `--types query`
    # (an explicit allowlist overrides the exclusion). **The exclusion is pushed
    # into the SQL (exclude_types) so it is applied BEFORE the LIMIT** — a
    # post-LIMIT Python filter would let a self-indexed query page consume a
    # top-`limit` slot and silently evict a real hit, breaking idempotency at
    # any corpus with >= `limit` matching pages (vdd-multi HIGH). Done in the
    # SHARED path so `prepare` and `apply` compute the same question_hash.
    exclude = ["query"] if types_list is None else None

    def _search(q: str) -> list[PageHit]:
        return repo.search_pages(
            q, vaults=vaults_list, types=types_list, exclude_types=exclude,
            project=args.project, limit=args.limit,
        )

    try:
        return _search(match_query)
    except sqlite3.OperationalError:
        try:
            return _search(fts_quote(question))
        except sqlite3.OperationalError as exc:
            raise _InvalidQuery() from exc


def _read_payload(
    use_stdin: bool, file_arg: str | None, vault_root: Path, cap: int,
) -> str:
    """Read an answer / citations payload from stdin or a vault-inside file,
    bounded to ``cap`` bytes. The file form is validated inside the vault root
    and read with ``O_NOFOLLOW`` (symlink refuse). Raises `_PayloadTooLarge` /
    `PathTraversalError` / `OSError`."""
    if use_stdin:
        data = sys.stdin.buffer.read(cap + 1)
        if len(data) > cap:
            raise _PayloadTooLarge()
        return data.decode("utf-8")
    assert file_arg is not None
    path = validate_inside_vault(Path(file_arg), vault_root)
    if path.is_symlink():
        raise PathTraversalError(f"refusing symlinked payload file")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        data = os.read(fd, cap + 1)
    finally:
        os.close(fd)
    if len(data) > cap:
        raise _PayloadTooLarge()
    return data.decode("utf-8")


# -----------------------------------------------------------------------------
# prepare (R-6.1)
# -----------------------------------------------------------------------------
def prepare(args: argparse.Namespace) -> int:
    question = (args.question or "").strip()
    if not question:
        return emit({"error": "INVALID_QUESTION", "field": "question",
                     "reason": "empty question"}, 2)
    if len(question) > _MAX_QUESTION_LEN:
        return emit({"error": "INVALID_QUESTION", "field": "question",
                     "reason": f"exceeds {_MAX_QUESTION_LEN} chars"}, 2)
    if args.slug is not None and not _SLUG_RE.match(args.slug):
        return emit({"error": "INVALID_SLUG", "field": "slug",
                     "reason": "must be kebab-case ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$"}, 2)

    config: dict[str, str] = {"vault_id": args.vault}
    if args.db_path:
        config["db_path"] = args.db_path
    repo = make_repo(config)
    try:
        try:
            hits = _retrieve(repo, question, args)
        except _InvalidQuery:
            return emit({"error": "INVALID_QUERY", "field": "question",
                         "reason": "not a valid FTS5 expression; quote terms "
                                   "with special characters"}, 2)

        if len(hits) < args.min_hits:
            return emit({"error": "NO_CONTEXT", "field": "retrieved_count",
                         "reason": f"{len(hits)} hits < --min-hits {args.min_hits}; "
                                   "refusing to synthesise from no/low context"}, 2)

        query_slug = args.slug or _derive_query_slug(question)
        q_hash = _question_hash(question, hits)
        is_unchanged = repo.check_query_state(args.vault, query_slug) == q_hash
        return emit({
            "vault_id": args.vault,
            "question": question,
            "query_slug": query_slug,
            "question_hash": q_hash,
            "is_unchanged": is_unchanged,
            "retrieved_count": len(hits),
            "hits": [_hit_dict(h) for h in hits],
        })
    finally:
        repo.close()


# -----------------------------------------------------------------------------
# apply (R-6.3 / 6.4 / 6.6 / 6.7)
# -----------------------------------------------------------------------------
def _render_query_page(
    question: str, today: str, citations: list[str], answer: str,
) -> str:
    """Build the Class A `_queries/<slug>.md` content: frontmatter
    (`type: query`, question, date, cites, tags) + the sanitised answer body +
    a trailing `## Sources` wikilink list (Q-A8 — `cites:` frontmatter stays the
    machine-readable source of truth). The answer is sanitised by the caller."""
    post = frontmatter.Post(
        answer,
        type="query",
        question=question,
        date=today,
        cites=list(citations),
        tags=["query"],
    )
    body = frontmatter.dumps(post)
    if citations:
        # Obsidian-native `[[slug]]` (resolves by note name, not folder path);
        # the `cites:` frontmatter keeps the disambiguated `project/slug`. The
        # bare slug also makes the body `mentioned` ref (from extract_wiki_links
        # on reindex) share the cited ref's entity_slug — a clean dual-ref to the
        # same target (Q-A9), byte-identical to the reindex rebuild.
        sources = "\n".join(f"- [[{c.rpartition('/')[2]}]]" for c in citations)
        body = f"{body}\n\n## Sources\n\n{sources}\n"
    return body


def _index_query_page(
    repo: IndexRepository, vault_id: str, vault_root: Path, page_path: Path,
) -> None:
    """Self-index the filed query page into the DB (R-6.4) via DIRECT DAL calls
    on the repo's single connection — ``upsert_page`` + ``replace_refs``.

    Explicitly NOT via ``_manifest_consumer.index_from_manifest`` /
    ``wiki_index_upsert.main(argv)`` (the open H-PERF-3 / P-8 argparse-in-loop
    N+1) — a query page is exactly one page, so the manifest machinery is
    unwarranted (NFR-5).

    Reuses the reindex page-build + ``cites:`` parse so the apply-written rows
    are **byte-identical** to what ``wiki-reindex --full`` rebuilds — the UC-20
    durability cross-check (007-08) depends on this symmetry. The body
    ``## Sources`` ``[[slug]]`` wikilinks additionally yield a ``mentioned`` ref
    per source (extract_wiki_links), coexisting with the ``cited`` ref via the
    composite PK (Q-A9 dual-ref) — again matching the reindex rebuild.
    """
    from scripts.wiki_index.normalization import normalize_frontmatter
    from scripts.wiki_index.reindex import (
        _build_page,
        _frontmatter_refs,
    )
    from scripts.wiki_source.base import SourceItem
    from scripts.wiki_source.manual import ManualSourceAdapter

    item = SourceItem(kind="manual", source_path=page_path,
                      vault_root=vault_root, vault_id=vault_id)
    out = ManualSourceAdapter().fetch(item)
    updated_fm, db_type = normalize_frontmatter(out.frontmatter,
                                                source_path=page_path)
    page = _build_page(out, vault_id, db_type, page_path, vault_root, updated_fm)
    repo.upsert_page(page)
    all_refs = list(out.refs)
    all_refs.extend(_frontmatter_refs(
        db_type, updated_fm, vault_id, out.page_slug, out.project, []))
    repo.replace_refs(vault_id, out.page_slug, out.project, all_refs)


def apply(args: argparse.Namespace) -> int:
    # The answer and citations payloads can't BOTH read stdin (the first read
    # drains it, the second gets b'' → a misleading INVALID_CITATIONS). Reject
    # the conflict up front with a clear message (vdd-multi LOW).
    if args.answer_stdin and args.citations_stdin:
        return emit({"error": "INVALID_ARGS",
                     "field": "answer-stdin/citations-stdin",
                     "reason": "answer and citations cannot both read stdin; pipe "
                               "one and use the --file form for the other"}, 2)
    question = (args.question or "").strip()
    if not question:
        return emit({"error": "INVALID_QUESTION", "field": "question",
                     "reason": "empty question"}, 2)
    if len(question) > _MAX_QUESTION_LEN:
        return emit({"error": "INVALID_QUESTION", "field": "question",
                     "reason": f"exceeds {_MAX_QUESTION_LEN} chars"}, 2)
    if not _HASH_RE.match(args.question_hash):
        return emit({"error": "INVALID_QUESTION_HASH", "field": "question-hash",
                     "reason": "must be 64 lowercase hex chars"}, 2)
    if not _SLUG_RE.match(args.query_slug):
        return emit({"error": "INVALID_SLUG", "field": "query-slug",
                     "reason": "must be kebab-case"}, 2)

    try:
        vault_root = Path(args.vault_root).resolve(strict=True)
    except OSError:
        return emit({"error": "INVALID_VAULT_ROOT", "field": "vault-root",
                     "reason": "does not exist"}, 2)

    config: dict[str, str] = {"vault_id": args.vault}
    if args.db_path:
        config["db_path"] = args.db_path
    repo = make_repo(config)
    try:
        # 1. Reproduce prepare's retrieval → recompute hash (TOCTOU / R-6.7).
        try:
            hits = _retrieve(repo, question, args)
        except _InvalidQuery:
            return emit({"error": "INVALID_QUERY", "field": "question",
                         "reason": "not a valid FTS5 expression"}, 2)
        if _question_hash(question, hits) != args.question_hash:
            return emit({"error": "QUESTION_CHANGED", "field": "question-hash",
                         "reason": "retrieval set changed since prepare; re-run "
                                   "wiki-query (no auto-retry)"}, 2)

        # 2. Load answer + citations (bounded, vault-inside, O_NOFOLLOW).
        try:
            answer = _read_payload(args.answer_stdin, args.answer_file,
                                   vault_root, _MAX_ANSWER_BYTES)
        except _PayloadTooLarge:
            return emit({"error": "ANSWER_TOO_LARGE", "field": "answer",
                         "reason": f"exceeds {_MAX_ANSWER_BYTES} bytes"}, 4)
        except (PathTraversalError, OSError):
            return emit({"error": "INVALID_ANSWER_PATH", "field": "answer-file",
                         "reason": "not a regular file inside the vault root"}, 4)
        try:
            cit_raw = _read_payload(args.citations_stdin, args.citations_file,
                                    vault_root, _MAX_CITATIONS_BYTES)
        except _PayloadTooLarge:
            return emit({"error": "INVALID_CITATIONS", "field": "citations",
                         "reason": f"exceeds {_MAX_CITATIONS_BYTES} bytes"}, 4)
        except (PathTraversalError, OSError):
            return emit({"error": "INVALID_CITATIONS", "field": "citations-file",
                         "reason": "not a regular file inside the vault root"}, 4)

        # 3. Validate the citations payload shape.
        try:
            citations = json.loads(cit_raw)
        except json.JSONDecodeError:
            return emit({"error": "INVALID_CITATIONS", "field": "citations",
                         "reason": "not valid JSON"}, 4)
        if (not isinstance(citations, list)
                or not all(isinstance(c, str) for c in citations)
                or len(citations) > _MAX_CITATIONS):
            return emit({"error": "INVALID_CITATIONS", "field": "citations",
                         "reason": "must be a JSON list of <=50 'project/slug' strings"}, 4)
        if not all(("/" in c and c.rpartition("/")[0] and c.rpartition("/")[2])
                   for c in citations):
            return emit({"error": "INVALID_CITATIONS", "field": "citations",
                         "reason": "each citation must be a 'project/slug' string"}, 4)

        # 4. Grounding gate (R-6.7d): every citation must be a retrieved hit,
        # keyed on the full project/slug tuple. Never echo the offending value.
        retrieved_keys = {f"{h.page.project}/{h.page.slug}" for h in hits}
        if any(c not in retrieved_keys for c in citations):
            return emit({"error": "CITATION_NOT_RETRIEVED", "field": "citations",
                         "reason": "a citation is not in the retrieved hit set"}, 4)

        # 5. Render Class A page (answer body sanitised — egress injection guard).
        today = _date.today().isoformat()
        content = _render_query_page(
            question, today, citations, sanitize_markdown_text(answer))

        # 6. Atomic write to _queries/<slug>.md (symlink-refuse + content-hash
        # skip). The slug is kebab-validated (no '/' or '..'), so the filename
        # cannot traverse; we mkdir the page dir then validate IT is inside the
        # vault (strict resolve needs an existing path) — defence-in-depth.
        queries_dir = vault_root / QUERIES_SUBDIR
        queries_dir.mkdir(parents=True, exist_ok=True)
        try:
            safe_dir = validate_inside_vault(queries_dir, vault_root)
        except PathTraversalError:
            return emit({"error": "INVALID_VAULT_ROOT", "field": "vault-root",
                         "reason": "queries dir resolves outside the vault root"}, 2)
        page_path = safe_dir / f"{args.query_slug}.md"
        if page_path.is_symlink():
            return emit({"error": "INVALID_QUERY_PAGE", "field": "query-slug",
                         "reason": "target is a symlink (refused)"}, 4)
        # Content-hash skip: read any existing file via O_NOFOLLOW so a symlink
        # swapped in after the is_symlink() check (sub-ms TOCTOU) cannot redirect
        # the hash-compare read to external content — matches write_concept_page.
        # (atomic_write_text's os.replace never follows a symlink at the target.)
        changed = True
        if page_path.exists() and not args.force:
            try:
                fd = os.open(page_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            except OSError:
                fd = None  # symlink swapped in (ELOOP) etc. → treat as changed
            if fd is not None:
                try:
                    existing = os.read(fd, _MAX_ANSWER_BYTES + 1)
                finally:
                    os.close(fd)
                if existing.decode("utf-8", errors="replace") == content:
                    changed = False
        if changed:
            atomic_write_text(page_path, content)

        # 7. Self-index (R-6.4) + record idempotency state (R-6.6) + one `query`
        # log event (Q6) — all on the repo's single connection.
        indexed = False
        if changed:
            _index_query_page(repo, args.vault, vault_root, page_path)
            repo.record_query_state(args.vault, args.query_slug, args.question_hash)
            repo.append_log_event(LogEvent(
                vault_id=args.vault, event_ts=_datetime.now(),
                event_type="query", subject=args.query_slug,
                pages_created_json=[], pages_updated_json=[],
                # Provenance: record which orchestrator filed the answer (the
                # 007-05 spec's intent for --orchestrator-id; was previously
                # inert — vdd-multi-verify LOW).
                details_json={"cites": len(citations),
                              "orchestrator_id": args.orchestrator_id},
            ))
            indexed = True

        return emit({
            "vault_id": args.vault,
            "query_slug": args.query_slug,
            "cites": citations,
            "page_indexed": indexed,
            "action": "filed" if changed else "unchanged",
        })
    finally:
        repo.close()


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wiki-query")
    sub = p.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("prepare", help="Deterministic FTS retrieval pass.")
    pp.add_argument("question")
    pp.add_argument("--vault", required=True)
    pp.add_argument("--vault-root", required=True)
    pp.add_argument("--vaults", default=None,
                    help="Comma-separated search scope ('all' = every vault). "
                         "Default: the home --vault.")
    pp.add_argument("--types", default=None)
    pp.add_argument("--project", default=None)
    pp.add_argument("--limit", type=int, default=10)
    pp.add_argument("--no-expand-aliases", action="store_true")
    pp.add_argument("--slug", default=None,
                    help="Override the derived query slug (kebab-case).")
    pp.add_argument("--min-hits", type=int, default=1)
    pp.add_argument("--db-path", default=None)
    pp.set_defaults(func=prepare)

    ap = sub.add_parser("apply", help="Grounding-checked write-back + index.")
    ap.add_argument("--vault", required=True)
    ap.add_argument("--vault-root", required=True)
    ap.add_argument("--query-slug", required=True)
    ap.add_argument("--question", required=True)
    ap.add_argument("--question-hash", required=True)
    # Retrieval-scope flags MUST mirror `prepare` so `apply` reproduces the same
    # retrieval and recomputes the same question_hash (the QUESTION_CHANGED
    # TOCTOU check). The architecture's "re-run the same retrieval" requires
    # these; pass the identical values the operator passed to `prepare`.
    ap.add_argument("--vaults", default=None)
    ap.add_argument("--types", default=None)
    ap.add_argument("--project", default=None)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--no-expand-aliases", action="store_true")
    g_ans = ap.add_mutually_exclusive_group(required=True)
    g_ans.add_argument("--answer-stdin", action="store_true")
    g_ans.add_argument("--answer-file", default=None)
    g_cit = ap.add_mutually_exclusive_group(required=True)
    g_cit.add_argument("--citations-stdin", action="store_true")
    g_cit.add_argument("--citations-file", default=None)
    ap.add_argument("--orchestrator-id", default="orchestrator",
                    type=_orchestrator_id)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--db-path", default=None)
    ap.set_defaults(func=apply)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    func = args.func
    return int(func(args))


if __name__ == "__main__":
    sys.exit(main())
