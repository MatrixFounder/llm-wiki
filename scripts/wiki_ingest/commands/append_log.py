"""`append-log` subcommand — append an ingest entry to log.md.

Shortcut for `log-event ingest`. Bounded-lookahead idempotency loop
defeats catastrophic regex backtracking (L-H4). Uses
`_LOG_FORBIDDEN_IN_DETAIL` (centralised in `_safety` per 015-01) for
heading-spoof rejection.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from wiki_ingest._safety import (
    _LOG_FORBIDDEN_IN_DETAIL,
    _collect_names,
    _safe_name,
    die,
    read_text,
    write_text,
)
from wiki_ingest._vault import LOG_FILE, ensure_schema, load_asset


def register(sub: argparse._SubParsersAction) -> None:
    """Attach the `append-log` subparser."""
    p = sub.add_parser("append-log",
                       help="append an ingest entry to log.md "
                            "(shortcut for log-event ingest)")
    p.add_argument("vault")
    p.add_argument("--title", required=True)
    p.add_argument("--slug", required=True)
    p.add_argument("--source-path", required=True)
    p.add_argument("--touched",
                   help="comma-separated slugs (DEPRECATED for names containing commas — use --touch-name instead)")
    p.add_argument("--created",
                   help="comma-separated slugs (DEPRECATED for names containing commas — use --create-name instead)")
    p.add_argument("--touch-name", action="append", default=[],
                   help="one touched slug; repeat the flag for each (safe for names containing commas)")
    p.add_argument("--create-name", action="append", default=[],
                   help="one created slug; repeat the flag for each (safe for names containing commas)")
    p.add_argument("--contradictions", type=int, default=0)
    p.add_argument("--date", help="YYYY-MM-DD (default: today)")
    p.add_argument("--force-log", action="store_true",
                   help="append even if an identical entry (heading + summary-page) is already present")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=execute)


def execute(args: argparse.Namespace) -> int:
    """Append a `## [date] ingest | title` entry; idempotent unless --force-log."""
    vault = Path(args.vault).resolve()
    ensure_schema(vault)
    log = vault / LOG_FILE
    content = read_text(log) or load_asset("log.template.md")

    # Reject newlines, pipes (would break the heading format) and a leading
    # '## [' that could spoof a fake log entry — same validation as log-event.
    safe_title = args.title.strip()
    if _LOG_FORBIDDEN_IN_DETAIL.search(safe_title) or "|" in safe_title:
        die("--title: newlines, pipes, or log-header prefixes are not allowed "
            "(would break grep-friendly log format)")
    safe_slug = _safe_name(args.slug, kind="slug")
    # `--source-path` is rendered inside a backtick code span; reject newlines
    # but otherwise let the path stand (backticks already neutralise most
    # markdown metacharacters).
    safe_source_path = args.source_path.strip()
    if "\n" in safe_source_path or "\r" in safe_source_path or "`" in safe_source_path:
        die("--source-path: newlines and backticks are not allowed")

    date = (args.date or datetime.today().strftime("%Y-%m-%d")).strip()
    if _LOG_FORBIDDEN_IN_DETAIL.search(date):
        die("--date: newlines and log-header prefixes are not allowed")

    heading = f"## [{date}] ingest | {safe_title}"
    summary_line = f"- Summary page: [[{safe_slug}]]"

    # Idempotency: if an entry with the same date+ingest+title heading AND the
    # same summary-page line already exists, skip (unless --force-log).
    # Bounded-lookahead loop instead of `(?:- .*\n)*?{summary}` regex — the
    # lazy quantifier between two anchored literals backtracks catastrophically
    # on long logs when the heading exists without the matching summary line
    # (L-H4). We scan the next ~10 lines after each heading occurrence.
    if not args.force_log:
        heading_re = re.compile(rf"^{re.escape(heading)}[ \t]*$", re.M)
        for hm in heading_re.finditer(content):
            tail = content[hm.end():hm.end() + 4096]
            # peek up to 10 following lines for the summary marker
            lines = tail.split("\n", 11)[:10]
            if any(line.strip() == summary_line.strip() for line in lines):
                print(json.dumps({
                    "log": str(log.relative_to(vault)),
                    "appended": False,
                    "skipped_reason": "duplicate (same heading + summary-page "
                                      "line already present); pass --force-log "
                                      "to append anyway",
                    "date": date,
                }, indent=2))
                return 0

    # Collect names from comma-separated --touched/--created (back-compat) and
    # repeatable --touch-name/--create-name (safe for names containing commas).
    touched_names = _collect_names(args.touched, args.touch_name)
    created_names = _collect_names(args.created, args.create_name)
    # Validate each name is filesystem-safe so injection through name lists
    # cannot fabricate `## [`-prefixed headers or break wiki-links.
    touched_names = [_safe_name(n, kind="touched") for n in touched_names]
    created_names = [_safe_name(n, kind="created") for n in created_names]

    entry = [
        f"\n{heading}",
        f"- Source path: `{safe_source_path}`",
        summary_line,
    ]
    if touched_names:
        entry.append("- Pages touched: " + ", ".join(f"[[{x}]]" for x in touched_names))
    if created_names:
        entry.append("- Pages created: " + ", ".join(f"[[{x}]]" for x in created_names))
    entry.append(f"- Contradictions flagged: {args.contradictions}")
    entry.append("")

    new_content = content.rstrip() + "\n" + "\n".join(entry) + "\n"
    write_text(log, new_content, args.dry_run)
    print(json.dumps({"log": str(log.relative_to(vault)), "appended": True, "date": date}, indent=2))
    return 0
