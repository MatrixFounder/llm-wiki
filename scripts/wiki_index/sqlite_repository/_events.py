"""Log-events + batch-runs domain of the SQLite DAL (TASK 056).

Methods relocated verbatim from the pre-056 monolith: append_log_event,
update_log_event_offset, query_log_events, _row_to_log_event,
begin_batch_run, finish_batch_run, last_batch_run.

dialect: generic SQL except the `_in_clause` `?`-placeholder helper inherited
from `_base` (psycopg uses `%s`) and TEXT-serialized timestamps (Postgres:
TIMESTAMPTZ).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from scripts.wiki_index.models import BatchMode, BatchRun, LogEvent
from scripts.wiki_index.sqlite_repository._base import SQLiteRepositoryBase


class _EventsMixin(SQLiteRepositoryBase):
    """Log events + batch runs (task-001-19)."""

    def append_log_event(self, event: LogEvent) -> int:
        conn = self._connect()
        # TASK 006 / L-2: event_date is a STORED generated column
        # (substr(event_ts,1,10)) as of schema v4 — do NOT supply it (inserting
        # into a generated column raises); the DB derives it from event_ts.
        cur = conn.execute(
            "INSERT INTO log_events (vault_id, event_ts, event_type, "
            "subject, pages_created_json, pages_touched_json, contradictions_count, "
            "details_json, log_md_byte_offset) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event.vault_id,
                event.event_ts.isoformat(),
                event.event_type,
                event.subject,
                json.dumps(event.pages_created_json),
                json.dumps(event.pages_updated_json),
                0,  # contradictions_count — derived in Phase 3b
                json.dumps(event.details_json),
                event.log_md_byte_offset,
            ),
        )
        return int(cur.lastrowid or 0)

    def update_log_event_offset(self, event_id: int, byte_offset: int) -> None:
        self._connect().execute(
            "UPDATE log_events SET log_md_byte_offset = ? WHERE id = ?",
            (byte_offset, event_id),
        )

    def query_log_events(
        self,
        vault_id: str,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        event_types: list[str] | None = None,
    ) -> list[LogEvent]:
        sql_parts = [
            "SELECT id, vault_id, event_ts, event_type, subject, "
            "pages_created_json, pages_touched_json, details_json, "
            "log_md_byte_offset FROM log_events WHERE vault_id = ?"
        ]
        params: list[Any] = [vault_id]
        if since is not None:
            sql_parts.append(" AND event_ts >= ?")
            params.append(since.isoformat())
        if until is not None:
            sql_parts.append(" AND event_ts <= ?")
            params.append(until.isoformat())
        if event_types is not None:
            clause, vals = self._in_clause("event_type", event_types)
            sql_parts.append(f" AND {clause}")
            params.extend(vals)
        sql_parts.append(" ORDER BY event_ts ASC, id ASC")
        rows = self._connect().execute("".join(sql_parts), params).fetchall()
        return [self._row_to_log_event(r) for r in rows]

    @staticmethod
    def _row_to_log_event(row: sqlite3.Row) -> LogEvent:
        return LogEvent(
            id=row["id"],
            vault_id=row["vault_id"],
            event_ts=datetime.fromisoformat(row["event_ts"]),
            event_type=row["event_type"],
            subject=row["subject"],
            pages_created_json=json.loads(row["pages_created_json"] or "[]"),
            pages_updated_json=json.loads(row["pages_touched_json"] or "[]"),
            details_json=json.loads(row["details_json"] or "{}"),
            log_md_path=None,
            log_md_byte_offset=row["log_md_byte_offset"],
        )

    def begin_batch_run(self, vault_id: str, mode: BatchMode) -> int:
        conn = self._connect()
        cur = conn.execute(
            "INSERT INTO batch_runs (vault_id, mode, started_at, status) "
            "VALUES (?, ?, ?, 'running')",
            (vault_id, mode, datetime.now().isoformat()),
        )
        return int(cur.lastrowid or 0)

    def finish_batch_run(
        self, run_id: int, status: str, notes: str | None = None
    ) -> None:
        self._connect().execute(
            "UPDATE batch_runs SET finished_at = ?, status = ?, notes = ? "
            "WHERE id = ?",
            (datetime.now().isoformat(), status, notes, run_id),
        )

    def last_batch_run(self, vault_id: str) -> BatchRun | None:
        row = self._connect().execute(
            "SELECT id, vault_id, mode, started_at, finished_at, status, notes "
            "FROM batch_runs WHERE vault_id = ? "
            "ORDER BY started_at DESC, id DESC LIMIT 1",
            (vault_id,),
        ).fetchone()
        if row is None:
            return None
        return BatchRun(
            id=row["id"],
            vault_id=row["vault_id"],
            mode=row["mode"],
            started_at=datetime.fromisoformat(row["started_at"]),
            finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
            status=row["status"],
            notes=row["notes"],
        )

