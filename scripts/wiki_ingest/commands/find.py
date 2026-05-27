"""`find` subcommand — keyword search across vault pages.

Body-only scoring (L-M3): frontmatter list repetition does NOT inflate
rank. Defers full frontmatter parse until needed (P-M1). Output is
sanitised through `_safe_for_json` to prevent prompt-injection chains
via crafted titles (S-M6).
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from wiki_ingest._frontmatter import _strip_frontmatter_fast, split_frontmatter
from wiki_ingest._safety import _safe_for_json, die, read_text
from wiki_ingest._vault import SUBDIR_TO_KIND, _walk_pages


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("find",
                       help="keyword search across vault pages (returns ranked JSON)")
    p.add_argument("vault")
    p.add_argument("--terms", required=True,
                   help="space-separated search terms; case-insensitive substring match")
    p.add_argument("--limit", type=int, default=10,
                   help="max hits to return (default: 10)")
    p.add_argument("--kinds", help="comma-separated kinds filter: source,concept,entity")
    p.set_defaults(func=execute)


def execute(args: argparse.Namespace) -> int:
    vault = Path(args.vault).resolve()
    if not vault.is_dir():
        die(f"vault not a directory: {vault}")

    terms = [t.strip().lower() for t in args.terms.split() if t.strip()]
    if not terms:
        die("--terms is empty")

    kind_filter = set((args.kinds or "").split(",")) if args.kinds else None
    if kind_filter:
        kind_filter = {k.strip().lower() for k in kind_filter if k.strip()}

    # P-M5: build ONE merged regex with named groups so we score all
    # terms in a single O(L) sweep instead of N separate `.count()` passes.
    # For ≤4 terms `str.count` is competitive; for 5+ the merged scan wins.
    # (We always use the merged scan — overhead is minimal at N=1.)
    # Group names are `t0`, `t1`, … so we don't have to sanitise term text.
    merged_re = re.compile(
        "|".join(f"(?P<t{i}>{re.escape(t)})" for i, t in enumerate(terms))
    )

    hits = []
    need_fm = bool(kind_filter)
    for md in _walk_pages(vault):
        try:
            text = read_text(md)
        except OSError:
            continue
        # Score the BODY (post-frontmatter) — a repeated frontmatter list
        # entry like `concepts: [crypto, crypto, crypto]` should not inflate
        # rank beyond a genuine in-prose discussion (L-M3). We parse
        # frontmatter only when --kinds is set OR we end up needing the
        # title for a hit; otherwise we slice past the frontmatter cheaply.
        # (P-M1: avoid the full hand-rolled YAML parse on every page.)
        if need_fm:
            fm, body = split_frontmatter(text)
            page_kind = (fm.get("kind") or "").lower()
            if not page_kind:
                page_kind = SUBDIR_TO_KIND.get(md.parent.name, "")
            if page_kind not in kind_filter:
                continue
        else:
            fm = None
            body = _strip_frontmatter_fast(text)
        body_hay = body.lower()
        # Single-pass merged-regex scan: each match contributes +1 to the
        # term identified by its winning named group.
        per_term: dict[str, int] = {t: 0 for t in terms}
        score = 0
        for m in merged_re.finditer(body_hay):
            # `lastgroup` is the name of the winning alternation branch
            idx = int(m.lastgroup[1:])  # strip the "t" prefix
            per_term[terms[idx]] += 1
            score += 1
        if score == 0:
            continue
        if fm is None:
            fm, _ = split_frontmatter(text)
        title = fm.get("title") or fm.get("name") or md.stem
        hits.append({
            "path": str(md.relative_to(vault)),
            "title": title,
            "kind": fm.get("kind") or SUBDIR_TO_KIND.get(md.parent.name, "unknown"),
            "score": score,
            "term_counts": per_term,
        })

    hits.sort(key=lambda h: (-h["score"], h["path"]))
    top = hits[:args.limit]
    # Sanitize attacker-controlled scalars (title, term, etc.) before they
    # land in the agent's planning context — prevents prompt-injection
    # chains via crafted frontmatter (S-M6).
    print(json.dumps(_safe_for_json(
            {"query_terms": terms, "hits": top, "total_matches": len(hits)}),
                     indent=2, ensure_ascii=False))
    return 0
