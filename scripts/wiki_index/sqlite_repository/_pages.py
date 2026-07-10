"""Pages-CRUD domain of the SQLite DAL (TASK 056).

Methods relocated verbatim from the pre-056 monolith: _upsert_page_in_txn,
upsert_page, get_page, delete_page, _row_to_page.

dialect: mostly generic SQL; the ON CONFLICT DO UPDATE upsert is shared
syntax (SQLite ≥3.24 / Postgres ≥9.5); FTS5 shadow-table maintenance rides
DB triggers, not this module.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any, Literal

from scripts.wiki_index.models import Page
from scripts.wiki_index.sqlite_repository._base import SQLiteRepositoryBase


class _PagesMixin(SQLiteRepositoryBase):
    # M-4 contract: upserts use ON CONFLICT DO UPDATE — the replace-style
    # INSERT variant is banned (see the section marker below + the grep guard
    # in tests/test_pages_upsert.py).
    """Pages CRUD (task-001-16)."""

    # =========================================================================
    # Pages CRUD (task-001-16) — M-4 contract: ON CONFLICT DO UPDATE.
    # NEVER `INSERT OR REPLACE` — would create new pages.id, break FTS5
    # rowid stability, CASCADE-delete page_entity_refs.
    # =========================================================================

    def _upsert_page_in_txn(
        self, conn: sqlite3.Connection, page: Page, *,
        skip_unchanged_check: bool = False,
    ) -> Literal["inserted", "updated", "unchanged"]:
        """TASK 030 (R-030-2a): the txn-free DML body of `upsert_page`.

        Contract: the CALLER MUST hold an open transaction — this method issues
        no BEGIN/COMMIT/ROLLBACK. Never call it bare: under
        `isolation_level=None` each statement would commit as its own implicit
        transaction, forfeiting atomicity. Private by design: NOT on the
        `IndexRepository` ABC; callers are the public wrapper below and the
        `reindex_full` chunked flush (consumer-to-be, bead 030-03).
        `skip_unchanged_check=True` skips the per-page hash pre-SELECT (the
        full-rebuild path, F-6) — outcome bookkeeping is then nominal
        ("inserted"; a within-batch PK conflict still resolves via ON CONFLICT,
        deliberately letting the LAST file's row win — Q-030-5).
        """
        if not skip_unchanged_check:
            row = conn.execute(
                "SELECT file_hash FROM pages WHERE vault_id=? AND slug=? AND project=?",
                (page.vault_id, page.slug, page.project),
            ).fetchone()
            if row is not None and row["file_hash"] == page.file_hash:
                return "unchanged"
            outcome: Literal["inserted", "updated"] = (
                "updated" if row is not None else "inserted"
            )
        else:
            outcome = "inserted"
        conn.execute(
            """
            INSERT INTO pages (vault_id, slug, project, type, title, file_path,
                               tldr, date, last_modified, file_hash,
                               frontmatter_json, body_excerpt, is_frozen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(vault_id, slug, project) DO UPDATE SET
                type=excluded.type,
                title=excluded.title,
                file_path=excluded.file_path,
                tldr=excluded.tldr,
                date=excluded.date,
                last_modified=excluded.last_modified,
                file_hash=excluded.file_hash,
                frontmatter_json=excluded.frontmatter_json,
                body_excerpt=excluded.body_excerpt,
                is_frozen=excluded.is_frozen
            """,
            (
                page.vault_id, page.slug, page.project, page.type, page.title,
                page.file_path, page.tldr,
                page.date.isoformat() if page.date is not None else None,
                page.last_modified.isoformat(),
                page.file_hash,
                json.dumps(page.frontmatter_json, ensure_ascii=False),
                page.body_excerpt,
                int(page.is_frozen),
            ),
        )
        return outcome

    def upsert_page(self, page: Page) -> Literal["inserted", "updated", "unchanged"]:
        """Owns its transaction (M-4 sibling contract) — delegates the DML to
        `_upsert_page_in_txn` (TASK 030 split; behavior-equivalent: identical
        statement trace, outcomes, and exception classes)."""
        conn = self._connect()
        conn.execute("BEGIN IMMEDIATE")
        try:
            outcome = self._upsert_page_in_txn(conn, page)
            conn.execute("COMMIT")
            return outcome
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def get_page(self, vault_id: str, slug: str, project: str) -> Page | None:
        conn = self._connect()
        row = conn.execute(
            "SELECT vault_id, slug, project, type, title, file_path, tldr, date, "
            "last_modified, file_hash, frontmatter_json, body_excerpt, is_frozen "
            "FROM pages WHERE vault_id=? AND slug=? AND project=?",
            (vault_id, slug, project),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_page(row)

    def delete_page(self, vault_id: str, slug: str, project: str) -> None:
        conn = self._connect()
        conn.execute(
            "DELETE FROM pages WHERE vault_id=? AND slug=? AND project=?",
            (vault_id, slug, project),
        )

    @staticmethod
    def _row_to_page(row: sqlite3.Row) -> Page:
        """Hydrate a Page from a sqlite3.Row."""
        from datetime import date as date_cls

        fm: dict[str, Any] = (
            json.loads(row["frontmatter_json"]) if row["frontmatter_json"] else {}
        )
        page_date: date_cls | None = (
            date_cls.fromisoformat(row["date"]) if row["date"] else None
        )
        return Page(
            vault_id=row["vault_id"],
            slug=row["slug"],
            project=row["project"],
            type=row["type"],
            title=row["title"],
            file_path=row["file_path"],
            date=page_date,
            last_modified=datetime.fromisoformat(row["last_modified"]),
            file_hash=row["file_hash"],
            frontmatter_json=fm,
            body_excerpt=row["body_excerpt"] or "",
            tags=list(fm.get("tags") or []),
            tldr=row["tldr"],
            is_frozen=bool(row["is_frozen"]),
        )

