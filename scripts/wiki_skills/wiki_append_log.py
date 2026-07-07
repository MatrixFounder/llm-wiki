"""`wiki-append-log` CLI — real impl per task-001-27.

Bi-directional sync: INSERT into log_events, write line to log.md atomically
with flock, UPDATE log_events SET log_md_byte_offset.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.logfile import (
    append_atomic,
    render_event_line,
    rotate_log_path,
)
from scripts.wiki_index.models import LogEvent
from scripts.wiki_skills._common import (
    actor_id,
    build_repo_config,
    emit,
    resolve_vault_root_for_cli,
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wiki-append-log")
    p.add_argument("--vault", required=True)
    p.add_argument("--event-type", default="ingest")
    p.add_argument("--subject", default=None)
    p.add_argument("--details-json", default=None,
                   help="Inline JSON string or path to file with JSON.")
    p.add_argument("--vault-root", default=None,
                   help="Vault root (resolve a local index_db); walks up from CWD when omitted.")
    p.add_argument("--db-path", default=None)
    return p


def _parse_details(arg: str | None) -> dict[str, Any]:
    if not arg:
        return {}
    try:
        data = json.loads(arg)
        if isinstance(data, dict):
            return dict(data)
    except json.JSONDecodeError:
        pass
    p = Path(arg)
    if p.is_file():
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return dict(data)
    return {}


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    config = build_repo_config(  # TASK 022
        args.vault, vault_root=resolve_vault_root_for_cli(args),
        db_path_flag=args.db_path)
    repo = make_repo(config)
    try:
        vault = repo.get_vault(args.vault)
        if vault is None:
            return emit({"error": "VAULT_NOT_REGISTERED",
                         "vault_id": args.vault}, exit_code=6)
        now = datetime.now()
        log_path = rotate_log_path(vault.root_path, now)
        details = _parse_details(args.details_json)
        # TASK 050 (R-2): optional actor identity; an explicit operator-supplied
        # `actor` key in --details-json wins over the ambient env.
        _actor = actor_id()
        if _actor is not None and "actor" not in details:
            details["actor"] = _actor
        event = LogEvent(
            vault_id=args.vault,
            event_ts=now,
            event_type=args.event_type,
            subject=args.subject,
            pages_created_json=[],
            pages_updated_json=[],
            details_json=details,
            log_md_path=str(log_path.relative_to(vault.root_path)),
        )
        event_id = repo.append_log_event(event)
        try:
            line = render_event_line(event)
            byte_offset = append_atomic(log_path, line)
            repo.update_log_event_offset(event_id, byte_offset)
        except Exception as e:
            # Best-effort rollback of log_events row
            from scripts.wiki_index.sqlite_repository import SQLiteRepository
            if isinstance(repo, SQLiteRepository):
                repo._connect().execute(
                    "DELETE FROM log_events WHERE id = ?", (event_id,)
                )
            return emit({"error": "LOG_APPEND_FAILED",
                         "message": str(e),
                         "rolled_back_event_id": event_id}, exit_code=6)
        return emit({
            "action": "logged",
            "event_id": event_id,
            "log_md_path": str(log_path),
            "byte_offset": byte_offset,
        })
    finally:
        repo.close()


if __name__ == "__main__":
    sys.exit(main())
