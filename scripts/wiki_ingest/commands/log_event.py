"""`log-event` subcommand — append a generic event entry to log.md.

Used for `query`, `lint`, `reindex` audit trail entries.
`_LOG_FORBIDDEN_IN_DETAIL` (shared with `append_log` via `_safety`)
rejects newlines + `^## [` prefixes that would spoof a fake heading.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from wiki_ingest._safety import _LOG_FORBIDDEN_IN_DETAIL, die, read_text, write_text
from wiki_ingest._vault import LOG_FILE, ensure_schema, load_asset


def register(sub: argparse._SubParsersAction) -> None:
    """Attach the `log-event` subparser."""
    p = sub.add_parser("log-event",
                       help="append a generic event entry to log.md "
                            "(query, lint, etc.)")
    p.add_argument("vault")
    p.add_argument("--event", required=True,
                   help="event type label, e.g. 'query', 'lint', 'reindex'")
    p.add_argument("--title", required=True,
                   help="short title shown after the event label in the heading")
    p.add_argument("--detail", action="append",
                   help="key=value detail line; pass multiple times for multiple lines")
    p.add_argument("--date", help="YYYY-MM-DD (default: today)")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=execute)


def execute(args: argparse.Namespace) -> int:
    """Append a `## [date] <event> | <title>` block; return 0 on success."""
    vault = Path(args.vault).resolve()
    ensure_schema(vault)
    log = vault / LOG_FILE
    content = read_text(log) or load_asset("log.template.md")

    safe_event = args.event.strip()
    if any(ch in safe_event for ch in ("\n", "\r", "|", "[", "]")):
        die(f"--event {safe_event!r}: must not contain newline, pipe, "
            f"or square brackets (would break log-heading format, S-L1)")
    safe_title = args.title.strip()
    if "\n" in safe_title:
        die("--title must not contain newlines")

    date = args.date or datetime.today().strftime("%Y-%m-%d")
    header = f"\n## [{date}] {safe_event} | {safe_title}"
    lines = [header]
    for kv in (args.detail or []):
        if "=" not in kv:
            die(f"--detail expects key=value, got {kv!r}")
        k, v = kv.split("=", 1)
        k = k.strip()
        v = v.strip()
        # reject control chars and a leading '## [' that could spoof a log header
        if _LOG_FORBIDDEN_IN_DETAIL.search(k) or _LOG_FORBIDDEN_IN_DETAIL.search(v):
            die(f"--detail {kv!r}: newlines and log-header prefixes are not allowed "
                f"(would break grep-friendly log format)")
        if "\n" in k or "\n" in v:
            die(f"--detail {kv!r}: newlines are not allowed")
        lines.append(f"- {k}: {v}")
    lines.append("")

    new_content = content.rstrip() + "\n" + "\n".join(lines) + "\n"
    write_text(log, new_content, args.dry_run)
    print(json.dumps({"log": str(log.relative_to(vault)), "appended": True,
                      "date": date, "event": safe_event}, indent=2))
    return 0
