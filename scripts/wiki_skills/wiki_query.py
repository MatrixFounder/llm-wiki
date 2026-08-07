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
from scripts.wiki_index.policy import (
    FOREIGN_UNCLASSIFIED_SENTINEL,
    TRUST_TIERS,
    PolicyError,
    PolicyProfile,
    allowed_levels,
    effective_level,
    resolve_policy,
    trust_tier,
)
from scripts.wiki_index.repository import IndexRepository
from scripts.wiki_index.security import PathTraversalError, validate_inside_vault
from scripts.wiki_skills._common import (
    ORCH_ID_RE,
    actor_id,
    atomic_write_text,
    build_repo_config,
    emit,
    emit_prepare_with_integrity,
    resolve_vault_root_for_cli,
    sanitize_answer_markdown,
)
from scripts.wiki_index.query_normalizer import fold_yo, normalize_term
from scripts.wiki_skills._retrieval import fts_quote

_MAX_QUESTION_LEN = 1000
_MAX_SLUG_LEN = 80
_MAX_ANSWER_BYTES = 256 * 1024  # 256 KiB
_MAX_CITATIONS_BYTES = 64 * 1024  # 64 KiB
_MAX_CITATIONS = 50
_SLUG_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_ORCH_RE = ORCH_ID_RE  # TASK 050: shared shape (no copy to drift)


def _orchestrator_id(value: str) -> str:
    """argparse validator for --orchestrator-id (007-05 spec regex). Defends a
    library caller too; the CLI default 'orchestrator' passes."""
    if not _ORCH_RE.fullmatch(value):  # fullmatch: `$` alone admits a trailing \n
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


def _question_hash(
    question: str, hits: list[PageHit], audience: str | None = None,
    min_trust: str | None = None,
) -> str:
    """Q-A6 binding shape: sha256 over the question + the ordered retrieved
    ``project/slug`` set, so a re-query after the corpus changed re-synthesises
    (defines `is_unchanged` semantics + whether the compounding loop picks up
    new sources). BM25 order is preserved (search_pages returns ranked hits).

    TASK 049: the audience level folds in ONLY when a policy profile is active
    (``audience is not None``) — OFF keeps the hash bytes unchanged, so filed
    queries recorded pre-049 still match (NFR-1). A prepare/apply audience
    mismatch therefore fails loudly as QUESTION_CHANGED. The ``\\x00`` prefix
    cannot collide with a ``project/slug`` line (slugs are kebab-case)."""
    parts = [question]
    parts.extend(f"{h.page.project}/{h.page.slug}" for h in hits)
    if audience is not None:
        parts.append("\x00audience:" + audience)
    if min_trust is not None:
        # TASK 050 (R-6): folds whenever the FLAG IS PRESENT — including the
        # no-clause `external` floor — so prepare/apply symmetry is unambiguous.
        parts.append("\x00min_trust:" + min_trust)
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _hit_dict(h: PageHit, trust: str | None = None) -> dict[str, object]:
    d: dict[str, object] = {
        "vault_id": h.page.vault_id, "slug": h.page.slug,
        "project": h.page.project, "type": h.page.type,
        "title": h.page.title, "bm25_score": h.bm25_score,
        "snippet": h.snippet,
    }
    if trust is not None:  # TASK 050: derived provenance tier (always-on in prepare)
        d["trust"] = trust
    if h.via_edge is not None:  # TASK 032: graph-RAG edge provenance
        d["via_edge"] = h.via_edge
    return d


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
    expand: bool, stem: bool,
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

    TASK 028 (Q-028-3, F-2): wiki-query already `fts_quote`s every token, so
    stemming happens at the TOKEN level BEFORE quoting — each token →
    ``normalize_term`` → ``"<stem>"*`` (broadening) or the folded literal
    ``"<term>"`` (``--exact``, acronyms, short stems). ё is always folded. (The
    acronym ALL-CAPS guard never fires here — tokens are lowercased for the
    OR/match-any model, which is forgiving of mild over-broadening.) Alias
    surfaces use the RAW token for lookup, folded + quoted, NEVER stemmed.

    The final ``sorted`` join — not token order — is what anchors `question_hash`
    determinism (C1); do not "optimise" the dedup away.

    When `expand`, each token is alias-expanded through the entity table
    (`expand_query_aliases`) so a surface like 'hermes' also pulls in its
    canonical name + sibling aliases (R-5.5 reuse, at token granularity)."""
    tokens = list(dict.fromkeys(re.findall(r"[^\W_]+", question.lower())))
    if not tokens:
        return fts_quote(fold_yo(question))
    surfaces: set[str] = set()
    for tok in tokens:
        atom, is_prefix = normalize_term(tok, stem=stem)
        q = fts_quote(atom)
        surfaces.add(q + "*" if is_prefix else q)
    if expand:
        targets = vaults_list or [v.vault_id for v in repo.list_vaults()]
        for vid in targets:
            for tok in tokens:
                for s in repo.expand_query_aliases(vid, tok):
                    surfaces.add(fts_quote(fold_yo(s)))
    return " OR ".join(sorted(surfaces))


# TASK 032 / R-032-6 (ADR-004 D5) — graph-aware RAG. The typed edge kinds whose
# neighbors `--follow-edges` pulls into retrieval (query/verification neighbors are
# excluded — ground on primary sources, mirroring the FTS exclude-prior-answers).
_EDGE_KINDS_RAG = (
    "implements", "implemented-by", "supersedes", "superseded-by",
    "causes", "caused-by", "related",
)
_MAX_EDGE_DEPTH = 3
# vdd-multi PERF-032-1: hard ceiling on the number of edge-pulled pages. `--edge-depth`
# alone bounds expansion only by CORPUS size (frontier fan-out is multiplicative across
# levels — a hub `decision`/`incident` page on a dense `cybos` vault can pull a large
# fraction of the vault into one answer + N+1 `get_page`). The cap is applied to the
# already-canonically-sorted candidate stream, so the truncation point is identical on
# prepare and apply → `question_hash` still round-trips (C1).
_MAX_EDGE_PULLED = 50


def _follow_edges(
    repo: IndexRepository, hits: list[PageHit], depth: int,
    allowed: list[str] | None = None, cls_default: str | None = None,
    home_vault: str | None = None, min_trust: str | None = None,
) -> list[PageHit]:
    """Expand the FTS hit set along typed edges (ADR-004 D5 / Q-032-4). For each hit,
    take its one-hop typed-edge neighbors (both directions), resolve each to a real
    page, exclude `query`/`verification`, dedup against the running set, and append in
    a CANONICAL order — sorted `(ref_type, project, slug)` per depth level — so the
    expansion is STABLE and `question_hash` round-trips across prepare/apply (C1).
    Depth-capped (≤ `_MAX_EDGE_DEPTH`) + dedup = cycle-safe; the total pulled set is
    bounded by `_MAX_EDGE_PULLED` (deterministic sorted truncation — PERF-032-1) so a
    dense hub can't pull the whole corpus or fan out an unbounded `get_page` N+1.
    Edge-pulled hits carry `via_edge` provenance + `bm25_score` 0.0 (no FTS rank).
    Outbound neighbors resolve in the source page's project (the common flat-vault
    case; cross-project outbound targets are skipped — ADR-004 D5 / Q-032-4)."""
    depth = max(1, min(depth, _MAX_EDGE_DEPTH))
    seen = {(h.page.vault_id, h.page.project, h.page.slug) for h in hits}
    pulled: list[PageHit] = []
    frontier = list(hits)
    for _ in range(depth):
        if len(pulled) >= _MAX_EDGE_PULLED:
            break
        # (inbound, vid, proj, slug, from, ref_type). `inbound=0` (the hit's OWN
        # outbound edge) sorts first, so when both a forward edge and its auto-derived
        # inverse connect the hit to a neighbor, the natural outbound provenance wins
        # (e.g. "rabbitmq —causes→ outage", not the mirror "outage caused-by rabbitmq").
        cand: list[tuple[int, str, str, str, str, str]] = []
        for h in frontier:
            vid = h.page.vault_id
            for r in repo.neighbors(vid, h.page.slug, h.page.project, "both"):
                if r.ref_type not in _EDGE_KINDS_RAG:
                    continue
                if r.page_slug == h.page.slug and r.page_project == h.page.project:
                    nslug, nproj, inbound = r.entity_slug, h.page.project, 0  # outbound
                else:
                    nslug, nproj, inbound = r.page_slug, r.page_project, 1    # inbound
                cand.append((inbound, vid, nproj, nslug, h.page.slug, r.ref_type))
        nxt: list[PageHit] = []
        # TASK 050 (R-6, pinned contract): the verified-floor membership is
        # resolved ONCE per depth level over the candidate (vid, slug) pairs
        # from neighbors() — no extra get_page, no per-neighbor N+1; consumed
        # as order-independent membership below.
        level_verified: set[tuple[str, str]] = set()
        if min_trust == "verified" and cand:
            level_verified = repo.find_verified_slugs(
                sorted({(c[1], c[3]) for c in cand}))
        for inbound, vid, nproj, nslug, frm, rt in sorted(
                cand, key=lambda c: (c[2], c[3], c[0], c[5])):
            if len(pulled) >= _MAX_EDGE_PULLED:  # deterministic sorted truncation
                break
            key = (vid, nproj, nslug)
            if key in seen:
                continue
            # Mark BEFORE the fetch (vdd-multi perf MED): a key rejected by any
            # skip below is never appended to pulled/nxt regardless, so marking
            # it early changes NOTHING about the pulled set/order (question_hash
            # C1 holds) — it only stops re-get_page'ing the same rejected page
            # from every other frontier neighbor / deeper level.
            seen.add(key)
            page = repo.get_page(vid, nslug, nproj)
            if page is None or page.type in ("query", "verification"):
                continue
            # TASK 049 (R-4): under an active policy profile an out-of-tier
            # neighbor is skipped exactly like the type-skip above — inside the
            # canonically-sorted stream, BEFORE the _MAX_EDGE_PULLED truncation,
            # so the expansion stays deterministic and identical across
            # prepare/apply (the question_hash C1 invariant). SEC-2: the
            # default_level applies only to HOME-vault pages — a foreign
            # unclassified neighbor fails closed (sentinel), matching the SQL
            # CASE-scoped default.
            if allowed is not None and cls_default is not None:
                page_default = (cls_default
                                if home_vault is None or vid == home_vault
                                else FOREIGN_UNCLASSIFIED_SENTINEL)
                if effective_level(page.frontmatter_json, page_default) \
                        not in allowed:
                    continue
            if min_trust is not None:
                # TASK 050 (R-6): same floor as the SQL predicate — inside the
                # sorted stream, BEFORE the cap break (question_hash C1).
                tier = trust_tier(
                    page.frontmatter_json, page.file_path,
                    (vid, nslug) in level_verified)
                if TRUST_TIERS.index(tier) < TRUST_TIERS.index(min_trust):
                    continue
            hit = PageHit(page=page, bm25_score=0.0, snippet="",
                          via_edge={"from": frm, "ref_type": rt})
            pulled.append(hit)
            nxt.append(hit)
        frontier = nxt
    return pulled


def _retrieve(
    repo: IndexRepository, question: str, args: argparse.Namespace,
    profile: PolicyProfile | None = None,
) -> list[PageHit]:
    """Alias-expanded keyword FTS retrieval shared by `prepare` AND `apply` — so
    `apply` reproduces `prepare`'s exact retrieval to recompute `question_hash`
    (the QUESTION_CHANGED TOCTOU check). Raises `_InvalidQuery` on an
    un-parseable expression after the DF-1 quoted-phrase fallback. TASK 032 (R-032-6):
    with `--follow-edges`, the FTS hits are deterministically expanded along typed
    edges (`_follow_edges`) — folded into `question_hash`, so prepare/apply agree.
    TASK 049: an active `profile` threads the classification filter into the FTS
    path AND the DF-1 fallback (one closure) AND the edge expansion — a
    restricted page can never enter the envelope on any branch."""
    vaults_list, types_list = _scope(args)
    allowed = allowed_levels(profile) if profile is not None else None
    cls_default = profile.default_level if profile is not None else None
    match_query = _build_match_query(
        repo, question, vaults_list, not args.no_expand_aliases,
        not args.exact)  # TASK 028: --exact disables stemming (fold stays)

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

    # SEC-2: --vault is the profile's HOME vault (its policy block resolved
    # the profile) — the default_level fallback is scoped to it in SQL and in
    # the edge gate; a foreign vault's unclassified pages fail closed.
    home_vault = args.vault if profile is not None else None

    min_trust: str | None = getattr(args, "min_trust", None)

    def _search(q: str) -> list[PageHit]:
        return repo.search_pages(
            q, vaults=vaults_list, types=types_list, exclude_types=exclude,
            project=args.project,
            allowed_classifications=allowed,
            classification_default=cls_default,
            classification_home_vault=home_vault,
            min_trust=min_trust,
            limit=args.limit,
        )

    try:
        hits = _search(match_query)
    except sqlite3.OperationalError:
        try:
            # DF-1 fallback: literal quoted phrase, ё-folded to stay consistent
            # with the folded corpus (TASK 028).
            hits = _search(fts_quote(fold_yo(question)))
        except sqlite3.OperationalError as exc:
            raise _InvalidQuery() from exc
    if getattr(args, "follow_edges", False):
        hits = hits + _follow_edges(
            repo, hits, getattr(args, "edge_depth", 1),
            allowed=allowed, cls_default=cls_default, home_vault=home_vault,
            min_trust=min_trust)
    return hits


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
def _derive_vault_root(
    args: argparse.Namespace, repo: IndexRepository,
) -> Path | None:
    """Resolve the vault root (TASK 014 / R-MF14-2): an explicit ``--vault-root``
    wins; otherwise fall back to the registered vault's ``root_path``. Returns
    ``None`` when neither is available (vault not registered + no flag)."""
    if args.vault_root:
        return Path(args.vault_root)
    vault = repo.get_vault(args.vault)
    return Path(vault.root_path) if vault is not None else None


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

    # TASK 022: resolve index_db BEFORE make_repo (the downstream _derive_vault_root then
    # reads the same local DB the helper opened).
    config = build_repo_config(
        args.vault, vault_root=resolve_vault_root_for_cli(args), db_path_flag=args.db_path)
    repo = make_repo(config)
    try:
        # TASK 049 (R-4): resolve the policy profile at the TOP of prepare —
        # the hash fold + envelope echo live here, not in _retrieve (Q-049-4).
        # Home-vault ladder; flag > declared default_audience > OFF.
        try:
            profile = resolve_policy(_derive_vault_root(args, repo), args.audience)
        except PolicyError as exc:
            err = ("INVALID_AUDIENCE" if exc.field == "audience"
                   else "INVALID_POLICY")
            return emit({"error": err, "field": exc.field,
                         "reason": str(exc)}, 2)
        try:
            hits = _retrieve(repo, question, args, profile)
        except _InvalidQuery:
            return emit({"error": "INVALID_QUERY", "field": "question",
                         "reason": "not a valid FTS5 expression; quote terms "
                                   "with special characters"}, 2)

        if len(hits) < args.min_hits:
            return emit({"error": "NO_CONTEXT", "field": "retrieved_count",
                         "reason": f"{len(hits)} hits < --min-hits {args.min_hits}; "
                                   "refusing to synthesise from no/low context"}, 2)

        query_slug = args.slug or _derive_query_slug(question)
        q_hash = _question_hash(
            question, hits,
            audience=profile.audience if profile is not None else None,
            min_trust=args.min_trust)
        is_unchanged = repo.check_query_state(args.vault, query_slug) == q_hash
        # TASK 050 (R-5): derived per-hit trust tier — ONE batched DAL call
        # over the final hit list (never per-hit N+1). Always-on: the ONLY
        # unconditional envelope addition of TASK 050 (additive key; the
        # is_unchanged hash does not include it).
        verified_pairs = repo.find_verified_slugs(
            sorted({(h.page.vault_id, h.page.slug) for h in hits}))
        payload: dict[str, object] = {
            "vault_id": args.vault,
            "question": question,
            "query_slug": query_slug,
            "question_hash": q_hash,
            "is_unchanged": is_unchanged,
            "retrieved_count": len(hits),
            "hits": [_hit_dict(h, trust=trust_tier(
                h.page.frontmatter_json, h.page.file_path,
                (h.page.vault_id, h.page.slug) in verified_pairs))
                for h in hits],
        }
        if profile is not None:
            # Echoed ONLY when active — the OFF envelope stays byte-identical.
            payload["audience"] = profile.audience
        if args.min_trust is not None:
            payload["min_trust"] = args.min_trust
        if getattr(args, "log_retrieval", False):
            # TASK 050 (R-3): opt-in retrieval audit — ONE Class-C DB-only
            # `query` event with the retrieved slug set. Best-effort: telemetry
            # must never fail a read path (sqlite3.Error covers the FK
            # IntegrityError of an unregistered-vault --db-path DB).
            details: dict[str, object] = {
                "access": True,
                "retrieved": [f"{h.page.project}/{h.page.slug}" for h in hits],
            }
            if profile is not None:
                details["audience"] = profile.audience
            actor = actor_id()
            if actor is not None:
                details["actor"] = actor
            try:
                repo.append_log_event(LogEvent(
                    vault_id=args.vault, event_ts=_datetime.now(),
                    event_type="query", subject=query_slug,
                    pages_created_json=[], pages_updated_json=[],
                    details_json=details,
                ))
                payload["access_logged"] = True
            except sqlite3.Error:
                payload["access_logged"] = False
        # H-5: verify the wiki-query-synthesis contract's pin before the orchestrator loads it.
        return emit_prepare_with_integrity(payload, "wiki-query-synthesis")
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

    config = build_repo_config(
        args.vault, vault_root=resolve_vault_root_for_cli(args), db_path_flag=args.db_path)
    repo = make_repo(config)
    try:
        # TASK 014 / R-MF14-2: --vault-root is optional. When omitted, derive it
        # from the registered vault's root_path (an explicit flag still wins).
        vr = _derive_vault_root(args, repo)
        if vr is None:
            return emit({"error": "INVALID_VAULT_ROOT", "field": "vault-root",
                         "reason": "vault not registered; pass --vault-root "
                                   "explicitly"}, 2)
        try:
            vault_root = vr.resolve(strict=True)
        except OSError:
            return emit({"error": "INVALID_VAULT_ROOT", "field": "vault-root",
                         "reason": "does not exist"}, 2)
        # TASK 049 (R-4): resolve the policy profile at the TOP of apply, from
        # the SAME home vault root — --audience MUST match prepare's (the hash
        # fold below turns a mismatch into a loud QUESTION_CHANGED).
        try:
            profile = resolve_policy(vault_root, args.audience)
        except PolicyError as exc:
            err = ("INVALID_AUDIENCE" if exc.field == "audience"
                   else "INVALID_POLICY")
            return emit({"error": err, "field": exc.field,
                         "reason": str(exc)}, 2)
        # 1. Reproduce prepare's retrieval → recompute hash (TOCTOU / R-6.7).
        try:
            hits = _retrieve(repo, question, args, profile)
        except _InvalidQuery:
            return emit({"error": "INVALID_QUERY", "field": "question",
                         "reason": "not a valid FTS5 expression"}, 2)
        recomputed = _question_hash(
            question, hits,
            audience=profile.audience if profile is not None else None,
            min_trust=args.min_trust)
        if recomputed != args.question_hash:
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
        # 3b. Grounding FLOOR (TASK 072 P1a). The shape gate above bounds citations ABOVE
        # only, so an empty list satisfied every check in this block VACUOUSLY — including
        # the grounding gate below, whose `any(...)` over `[]` is False. The result was a
        # complete exit-0 path to a filed, self-indexed `cites: []` answer page: the
        # anti-hallucination mechanism passing because it examined nothing. This is the
        # population-of-zero failure the project names elsewhere, inside the gate itself.
        # Placed AFTER the shape checks (so a non-list still yields the more specific
        # INVALID_CITATIONS) and BEFORE any `all()`/`any()` that would pass on an empty set.
        # There is deliberately NO env bypass and NO --allow-uncited: per the
        # FIELD_QUOTE_NOT_IN_BODY doctrine, the ABSENCE of an escape hatch is what makes
        # this a mechanism rather than a suggestion. (`--force` is not an override — it is
        # consumed downstream, at the content-hash skip.)
        if not citations:
            return emit({"error": "NO_CITATIONS", "field": "citations",
                         "reason": "at least one citation is required"}, 4)
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
        #
        # DF-072-9: `sanitize_ANSWER_markdown`, not `sanitize_markdown_text`. Same escape
        # set (HTML entities · every backtick · every bracket); the ONE difference is that
        # an ATX heading or a `- ` bullet keeps its leading character instead of becoming
        # a visible `\##` / `\-`. Found by the first end-to-end dogfood: apply exited 0,
        # the page indexed, citations validated, the whole suite was green — and the filed
        # answer rendered in Obsidian as a wall of backslashes. The synthesis contract asks
        # the orchestrator for "a concise markdown answer"; escaping structure made that
        # instruction impossible to satisfy. The strict function stays exactly as it is for
        # every FIELD-level value built from untrusted extracted text.
        today = _date.today().isoformat()
        content = _render_query_page(
            question, today, citations, sanitize_answer_markdown(answer))

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

        # 7. Self-index (R-6.4) + record idempotency state (R-6.6) — write-side
        # work stays gated on `changed`; the AUDIT event does not (below).
        indexed = False
        if changed:
            _index_query_page(repo, args.vault, vault_root, page_path)
            repo.record_query_state(args.vault, args.query_slug, args.question_hash)
            indexed = True
        # TASK 050 (R-1): the `query` audit event fires on EVERY successful
        # apply — an idempotent re-query leaves an `action: unchanged` trail —
        # and records the CITED SLUGS (not just a count) + the active audience
        # + the WIKI_ACTOR_ID actor. Class-C DB-only (no log.md line; the
        # `log_md_byte_offset` stays NULL — Q-050-2); survives `--full` via the
        # R-6b reindex carve-out.
        details: dict[str, object] = {
            "cites": len(citations),               # back-compat count
            "cited": list(citations),
            "action": "filed" if changed else "unchanged",
            "orchestrator_id": args.orchestrator_id,
        }
        if profile is not None:
            details["audience"] = profile.audience
        actor = actor_id()
        if actor is not None:
            details["actor"] = actor
        try:
            repo.append_log_event(LogEvent(
                vault_id=args.vault, event_ts=_datetime.now(),
                event_type="query", subject=args.query_slug,
                pages_created_json=[], pages_updated_json=[],
                details_json=details,
            ))
        except sqlite3.Error:
            # Best-effort, consistent with the D3 read paths: the Class A
            # write already happened — an audit-insert failure (e.g. missing
            # vault FK row on a bare --db-path DB) must not raw-traceback.
            pass

        out: dict[str, object] = {
            "vault_id": args.vault,
            "query_slug": args.query_slug,
            "cites": citations,
            "page_indexed": indexed,
            "action": "filed" if changed else "unchanged",
        }
        if profile is not None:
            # Echoed ONLY when active — the OFF envelope stays byte-identical.
            out["audience"] = profile.audience
        if args.min_trust is not None:
            out["min_trust"] = args.min_trust
        return emit(out)
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
    pp.add_argument("--vault-root", default=None,
                    help="Optional (prepare does not read it; accepted for "
                         "symmetry with apply). Derived from the registered "
                         "vault when omitted.")
    pp.add_argument("--vaults", default=None,
                    help="Comma-separated search scope ('all' = every vault). "
                         "Default: the home --vault.")
    pp.add_argument("--types", default=None)
    pp.add_argument("--project", default=None)
    pp.add_argument("--limit", type=int, default=10)
    pp.add_argument("--no-expand-aliases", action="store_true")
    pp.add_argument("--exact", "--no-stem", dest="exact", action="store_true",
                    default=False,
                    help="TASK 028: disable query-side stemming/inflection "
                         "broadening (ё/е fold still applies). MUST match the "
                         "value passed to `apply` or the question_hash diverges "
                         "→ QUESTION_CHANGED.")
    pp.add_argument("--follow-edges", action="store_true", default=False,
                    help="TASK 032: graph-aware RAG — expand the retrieval set along "
                         "typed edges (implements/supersedes/causes/relates-to + "
                         "inverses). MUST match `apply` or the question_hash diverges "
                         "→ QUESTION_CHANGED.")
    pp.add_argument("--edge-depth", type=int, default=1,
                    help="TASK 032: edge-follow hop depth (default 1, capped at 3).")
    pp.add_argument("--audience", default=None, metavar="LEVEL",
                    help="TASK 049 (ADR-009): retrieval-scope policy level — "
                         "pages above this level never enter the envelope "
                         "(filtered in SQL before the limit; edge expansion "
                         "gated too). MUST match the value passed to `apply` "
                         "or the question_hash diverges → QUESTION_CHANGED.")
    pp.add_argument("--slug", default=None,
                    help="Override the derived query slug (kebab-case).")
    pp.add_argument("--min-trust", dest="min_trust", default=None,
                    choices=["external", "internal", "verified"],
                    help="TASK 050 (R-6): derived-trust retrieval floor — "
                         "'internal' excludes external-origin pages (in "
                         "practice: an http(s) URL under a provenance key in "
                         "frontmatter — source/sources/url + case variants — "
                         "as a scalar, a list, or a list of {url: ...} objects; "
                         "a _raw/ path also counts but no "
                         "built-in layout indexes _raw/, so it is a backstop "
                         "for direct upserts); 'verified' additionally "
                         "requires an inbound verifies ref. Filtered in SQL "
                         "before the limit; folds into question_hash whenever "
                         "PRESENT (incl. 'external') — MUST match `apply`.")
    pp.add_argument("--log-retrieval", dest="log_retrieval", action="store_true",
                    default=False,
                    help="TASK 050 (R-3): opt-in read-audit — append one DB-only "
                         "`query` event recording the retrieved project/slug set "
                         "(+ audience/actor when active). Best-effort: a failed "
                         "insert reports access_logged: false, never a crash.")
    pp.add_argument("--min-hits", type=int, default=1)
    pp.add_argument("--db-path", default=None)
    pp.set_defaults(func=prepare)

    ap = sub.add_parser("apply", help="Grounding-checked write-back + index.")
    ap.add_argument("--vault", required=True)
    ap.add_argument("--vault-root", default=None,
                    help="Optional — derived from the registered vault's "
                         "root_path when omitted (TASK 014). Explicit value wins.")
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
    ap.add_argument("--exact", "--no-stem", dest="exact", action="store_true",
                    default=False,
                    help="TASK 028: MUST match the value passed to `prepare` "
                         "(retrieval must reproduce → same question_hash).")
    ap.add_argument("--follow-edges", action="store_true", default=False,
                    help="TASK 032: MUST match `prepare` (retrieval must reproduce "
                         "→ same question_hash).")
    ap.add_argument("--edge-depth", type=int, default=1,
                    help="TASK 032: MUST match `prepare` (default 1, capped at 3).")
    ap.add_argument("--audience", default=None, metavar="LEVEL",
                    help="TASK 049: MUST match the value passed to `prepare` "
                         "(retrieval must reproduce → same question_hash).")
    ap.add_argument("--min-trust", dest="min_trust", default=None,
                    choices=["external", "internal", "verified"],
                    help="TASK 050: MUST match the value passed to `prepare` "
                         "(folds into question_hash whenever present).")
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
