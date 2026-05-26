"""log.md ↔ log_events bi-directional sync primitives (task-001-27)."""

from __future__ import annotations

import fcntl
import os
import re
from datetime import datetime
from pathlib import Path

from scripts.wiki_index.layout import LOG_SUBDIR, VAULT_INDEX_DIR
from scripts.wiki_index.models import LogEvent

_EVENT_HEADER_RE = re.compile(
    r"^## \[(?P<date>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})\] "
    r"(?P<etype>[a-z][a-z-]*) \| (?P<subject>.+)$",
    re.MULTILINE,
)


def rotate_log_path(vault_root: Path, when: datetime) -> Path:
    """Monthly-rotated log file: <vault>/<VAULT_INDEX_DIR>/<LOG_SUBDIR>/{YYYY-MM}.md."""
    p = (vault_root / VAULT_INDEX_DIR / LOG_SUBDIR
         / f"{when.strftime('%Y-%m')}.md")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def render_event_line(event: LogEvent) -> str:
    """Format an event as one log.md block (header + structured bullets)."""
    ts = event.event_ts.strftime("%Y-%m-%d %H:%M:%S")
    subject = event.subject or ""
    lines = [
        f"## [{ts}] {event.event_type} | {subject}",
    ]
    if event.pages_created_json:
        lines.append(f"- pages_created: {event.pages_created_json}")
    if event.pages_updated_json:
        lines.append(f"- pages_updated: {event.pages_updated_json}")
    lines.append("")
    return "\n".join(lines) + "\n"


def append_atomic(log_path: Path, line: str) -> int:
    """Append `line` to log_path with exclusive flock. Returns byte offset
    of the line start. Creates the file if missing.

    Durable: loops on partial writes (POSIX write may write fewer bytes than
    requested under signal interrupt) and fsyncs the fd before releasing the
    lock so the offset returned matches bytes persisted to disk. flock is
    advisory; non-flock writers can still corrupt — wiki-* is the sole writer
    by convention.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(log_path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            byte_offset = os.lseek(fd, 0, os.SEEK_END)
            data = line.encode("utf-8")
            remaining = memoryview(data)
            while remaining:
                n = os.write(fd, remaining)
                if n <= 0:
                    raise OSError(f"os.write returned {n}; refusing to spin")
                remaining = remaining[n:]
            os.fsync(fd)
            return byte_offset
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def parse_log_md(path: Path) -> list[tuple[datetime, str, str, int]]:
    """Reverse of append_atomic: parses log.md → list of (event_ts, event_type,
    subject, byte_offset). Used by reindex (task-001-30) for round-trip."""
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    out: list[tuple[datetime, str, str, int]] = []
    for m in _EVENT_HEADER_RE.finditer(text):
        ts_raw = m.group("date").replace(" ", "T")
        ts = datetime.fromisoformat(ts_raw)
        out.append((ts, m.group("etype"), m.group("subject"), m.start()))
    return out
