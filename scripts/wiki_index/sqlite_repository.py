"""Concrete `IndexRepository` backed by SQLite (stub).

Every method in this stub raises `NotImplementedError` with a message that
references the task ID that will implement it. The class itself IS
instantiable — passing the Python ABC check — so the factory and downstream
skills can be wired now while logic is filled in incrementally during
task-001-15..19.

Connection management is intentionally deferred. `__init__` stores the
db_path but does NOT open a sqlite3.Connection until the first method needs
one (task-001-15, register_vault).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Literal

from scripts.wiki_index.layout import COURSE_TIER_DIR, PAGE_SUBDIRS
from scripts.wiki_index.models import (
    BatchMode,
    BatchRun,
    DriftReport,
    LogEvent,
    OrphanLink,
    Page,
    PageHit,
    PageRef,
    Vault,
)
from scripts.wiki_index.repository import IndexRepository

_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent / "sql" / "wiki-index-v2.sql"
)
"""Runtime DDL — apply via `apply_schema()` or external `sqlite3 db < ...`."""


class VaultRegistrationError(RuntimeError):
    """Raised on vault PK collision (duplicate vault_id) or UNIQUE violation
    (duplicate root_path). Wraps the underlying sqlite3.IntegrityError with a
    user-facing message."""


def _stub(method_name: str, impl_task: str) -> "NotImplementedError":
    """Build the stub-failure exception with a forward-pointer to the impl task.

    Not part of the IndexRepository surface — this is an internal helper that
    keeps the stub bodies one-line and grep-able.
    """
    return NotImplementedError(
        f"SQLiteRepository.{method_name} stub — implementation arrives in {impl_task}"
    )


class SQLiteRepository(IndexRepository):
    """SQLite-backed `IndexRepository`. Stub phase: every method raises.

    Phase 3a impl ordering:
      - task-001-15: vaults CRUD (also opens the sqlite3 connection lazily)
      - task-001-16: pages + page_entity_refs CRUD (M-4 ON CONFLICT contract)
      - task-001-17: search_pages (FTS5 + BM25 + --vaults filter)
      - task-001-18: lint queries (orphans, drift, cross-vault duplicates)
      - task-001-19: log_events CRUD + batch_runs
    """

    def __init__(self, db_path: Path) -> None:
        """Store the db_path. Does NOT open a connection — deferred to the
        first method that needs one via `_connect()` (lazy)."""
        self.db_path: Path = db_path
        self._conn: sqlite3.Connection | None = None

    # =========================================================================
    # Connection management (task-001-15)
    # =========================================================================

    def _connect(self) -> sqlite3.Connection:
        """Lazy-open the SQLite connection and apply pragmas. Idempotent."""
        if self._conn is not None:
            return self._conn
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        # Apply pragmas documented in sql/wiki-index-v2.sql §0
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("PRAGMA mmap_size = 268435456")
        conn.row_factory = sqlite3.Row
        self._conn = conn
        return conn

    def close(self) -> None:
        """Close the underlying connection if open. Idempotent."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "SQLiteRepository":
        self._connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    def apply_schema(self) -> None:
        """Apply the v2 DDL to the underlying DB. Idempotent (uses CREATE
        TABLE IF NOT EXISTS in the DDL). Intended for fresh-init flows + tests."""
        conn = self._connect()
        with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())

    # =========================================================================
    # Vault registry (task-001-15)
    # =========================================================================

    def register_vault(self, vault: Vault) -> None:
        conn = self._connect()
        config_json = json.dumps(vault.config_json) if vault.config_json is not None else None
        try:
            conn.execute(
                "INSERT INTO vaults (vault_id, name, root_path, schema_version, "
                "registered_at, config_json, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    vault.vault_id,
                    vault.name,
                    str(vault.root_path),
                    vault.schema_version,
                    vault.registered_at.isoformat(),
                    config_json,
                    vault.notes,
                ),
            )
        except sqlite3.IntegrityError as e:
            raise VaultRegistrationError(
                f"failed to register vault_id={vault.vault_id!r} "
                f"root_path={vault.root_path}: {e}"
            ) from e

    def get_vault(self, vault_id: str) -> Vault | None:
        conn = self._connect()
        row = conn.execute(
            "SELECT vault_id, name, root_path, schema_version, registered_at, "
            "config_json, notes FROM vaults WHERE vault_id = ?",
            (vault_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_vault(row)

    def list_vaults(self) -> list[Vault]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT vault_id, name, root_path, schema_version, registered_at, "
            "config_json, notes FROM vaults WHERE vault_id != '_global_' "
            "ORDER BY vault_id"
        ).fetchall()
        return [self._row_to_vault(r) for r in rows]

    def rename_vault(self, old_vault_id: str, new_vault_id: str) -> None:
        conn = self._connect()
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "UPDATE vaults SET vault_id = ? WHERE vault_id = ?",
                (new_vault_id, old_vault_id),
            )
            if cur.rowcount == 0:
                conn.execute("ROLLBACK")
                raise VaultRegistrationError(
                    f"rename failed: vault_id={old_vault_id!r} not found"
                )
            conn.execute("COMMIT")
        except sqlite3.IntegrityError as e:
            conn.execute("ROLLBACK")
            raise VaultRegistrationError(
                f"rename {old_vault_id!r} → {new_vault_id!r} failed: {e}"
            ) from e

    def get_vault_by_root_path(self, root_path: Path) -> Vault | None:
        row = self._connect().execute(
            "SELECT vault_id, name, root_path, schema_version, registered_at, "
            "config_json, notes FROM vaults WHERE root_path = ?",
            (str(root_path),),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_vault(row)

    @staticmethod
    def _row_to_vault(row: sqlite3.Row) -> Vault:
        """Hydrate a Vault dataclass from a sqlite3.Row."""
        config_json_raw = row["config_json"]
        config = json.loads(config_json_raw) if config_json_raw else None
        return Vault(
            vault_id=row["vault_id"],
            name=row["name"],
            root_path=Path(row["root_path"]),
            schema_version=row["schema_version"],
            registered_at=datetime.fromisoformat(row["registered_at"]),
            config_json=config,
            notes=row["notes"],
        )

    # =========================================================================
    # Pages CRUD (task-001-16) — M-4 contract: ON CONFLICT DO UPDATE.
    # NEVER `INSERT OR REPLACE` — would create new pages.id, break FTS5
    # rowid stability, CASCADE-delete page_entity_refs.
    # =========================================================================

    def upsert_page(self, page: Page) -> Literal["inserted", "updated", "unchanged"]:
        conn = self._connect()
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT file_hash FROM pages WHERE vault_id=? AND slug=? AND project=?",
                (page.vault_id, page.slug, page.project),
            ).fetchone()
            if row is not None and row["file_hash"] == page.file_hash:
                conn.execute("COMMIT")
                return "unchanged"
            outcome: Literal["inserted", "updated"] = (
                "updated" if row is not None else "inserted"
            )
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

    # =========================================================================
    # Refs (task-001-16 — bundled with pages CRUD)
    # =========================================================================

    def upsert_refs(self, refs: list[PageRef]) -> None:
        if not refs:
            return
        conn = self._connect()
        conn.executemany(
            """
            INSERT INTO page_entity_refs (vault_id, page_slug, page_project,
                                          entity_slug, ref_type, line_start,
                                          line_end, source_quote, trust_level)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(vault_id, page_slug, page_project, entity_slug, ref_type)
            DO UPDATE SET
                line_start=excluded.line_start,
                line_end=excluded.line_end,
                source_quote=excluded.source_quote,
                trust_level=excluded.trust_level
            """,
            [
                (
                    r.vault_id, r.page_slug, r.page_project, r.entity_slug,
                    r.ref_type, r.line_start, r.line_end, r.source_quote,
                    r.trust_level,
                )
                for r in refs
            ],
        )

    def replace_refs(
        self,
        vault_id: str,
        page_slug: str,
        page_project: str,
        refs: list[PageRef],
    ) -> None:
        # Dedupe by composite PK; first occurrence wins (preserves earliest
        # line_start/source_quote for provenance).
        seen: set[tuple[str, str, str, str, str]] = set()
        deduped: list[PageRef] = []
        for r in refs:
            key = (r.vault_id, r.page_slug, r.page_project, r.entity_slug, r.ref_type)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(r)
        conn = self._connect()
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "DELETE FROM page_entity_refs WHERE vault_id=? AND page_slug=? "
                "AND page_project=?",
                (vault_id, page_slug, page_project),
            )
            if deduped:
                conn.executemany(
                    "INSERT INTO page_entity_refs (vault_id, page_slug, page_project, "
                    "entity_slug, ref_type, line_start, line_end, source_quote, "
                    "trust_level) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            r.vault_id, r.page_slug, r.page_project, r.entity_slug,
                            r.ref_type, r.line_start, r.line_end, r.source_quote,
                            r.trust_level,
                        )
                        for r in deduped
                    ],
                )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def get_backlinks(self, vault_id: str, entity_slug: str) -> list[PageRef]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT vault_id, page_slug, page_project, entity_slug, ref_type, "
            "line_start, line_end, source_quote, trust_level "
            "FROM page_entity_refs WHERE vault_id=? AND entity_slug=? "
            "ORDER BY page_slug, COALESCE(line_start, 0)",
            (vault_id, entity_slug),
        ).fetchall()
        return [
            PageRef(
                vault_id=r["vault_id"],
                page_slug=r["page_slug"],
                page_project=r["page_project"],
                entity_slug=r["entity_slug"],
                ref_type=r["ref_type"],
                line_start=r["line_start"],
                line_end=r["line_end"],
                source_quote=r["source_quote"],
                trust_level=r["trust_level"],
            )
            for r in rows
        ]

    # =========================================================================
    # Search (task-001-17) — FTS5 + BM25 + multi-vault filter (R-29)
    # =========================================================================

    def search_pages(
        self,
        query: str,
        *,
        vaults: list[str] | None = None,
        types: list[str] | None = None,
        project: str | None = None,
        limit: int = 20,
    ) -> list[PageHit]:
        conn = self._connect()
        sql_parts: list[str] = [
            "SELECT p.vault_id, p.slug, p.project, p.type, p.title, p.file_path, "
            "p.tldr, p.date, p.last_modified, p.file_hash, p.frontmatter_json, "
            "p.body_excerpt, p.is_frozen, "
            "bm25(pages_fts) AS bm25_score, "
            "snippet(pages_fts, -1, '<b>', '</b>', '...', 16) AS snip "
            "FROM pages_fts JOIN pages p ON pages_fts.rowid = p.id "
            "WHERE pages_fts MATCH ?",
        ]
        params: list[Any] = [query]
        if vaults is not None:
            clause, vals = self._in_clause("p.vault_id", vaults)
            sql_parts.append(f" AND {clause}")
            params.extend(vals)
        if types is not None:
            clause, vals = self._in_clause("p.type", types)
            sql_parts.append(f" AND {clause}")
            params.extend(vals)
        if project is not None:
            sql_parts.append(" AND p.project = ?")
            params.append(project)
        sql_parts.append(" ORDER BY bm25_score ASC LIMIT ?")
        params.append(limit)
        sql = "".join(sql_parts)
        hits: list[PageHit] = []
        for row in conn.execute(sql, params).fetchall():
            page = self._row_to_page(row)
            hits.append(PageHit(
                page=page,
                bm25_score=row["bm25_score"],
                snippet=row["snip"] or "",
            ))
        return hits

    @staticmethod
    def _in_clause(column: str, values: list[str]) -> tuple[str, list[str]]:
        """Safe IN-clause string with `?` placeholders. Returns
        `(sql_fragment, params_list)`. Avoids SQL injection from joins."""
        placeholders = ",".join("?" * len(values))
        return f"{column} IN ({placeholders})", list(values)

    # =========================================================================
    # Lint (task-001-18)
    # =========================================================================

    def find_orphan_links(self, vault_id: str | None = None) -> list[OrphanLink]:
        sql = (
            "SELECT r.vault_id, r.page_slug, r.page_project, r.entity_slug, "
            "r.line_start, r.source_quote "
            "FROM page_entity_refs r "
            "LEFT JOIN entities e ON e.vault_id = r.vault_id AND e.slug = r.entity_slug "
            "LEFT JOIN pages p ON p.vault_id = r.vault_id AND p.slug = r.entity_slug "
            "WHERE e.slug IS NULL AND p.slug IS NULL"
        )
        params: list[Any] = []
        if vault_id is not None:
            sql += " AND r.vault_id = ?"
            params.append(vault_id)
        rows = self._connect().execute(sql, params).fetchall()
        return [
            OrphanLink(
                vault_id=r["vault_id"],
                source_page_slug=r["page_slug"],
                source_page_project=r["page_project"],
                target_slug=r["entity_slug"],
                line_start=r["line_start"],
                source_quote=r["source_quote"],
            )
            for r in rows
        ]

    def find_pages_missing_in_index(
        self, vault_id: str, vault_root: Path
    ) -> list[Path]:
        db_slugs = {
            r["slug"]
            for r in self._connect().execute(
                "SELECT slug FROM pages WHERE vault_id = ?", (vault_id,)
            ).fetchall()
        }
        missing: list[Path] = []
        scan_roots: list[Path] = [vault_root]
        lessons = vault_root / COURSE_TIER_DIR
        if lessons.is_dir():
            for course_dir in lessons.iterdir():
                if course_dir.is_dir():
                    scan_roots.append(course_dir)
        for root in scan_roots:
            for subdir in PAGE_SUBDIRS:
                base = root / subdir
                if base.is_dir():
                    for f in base.rglob("*.md"):
                        if f.stem not in db_slugs:
                            missing.append(f)
        return sorted(missing)

    def check_drift(self, vault_id: str) -> DriftReport:
        from scripts.wiki_source.parsing import compute_file_hash

        conn = self._connect()
        db_rows = {
            (r["slug"], r["project"]): (
                r["type"], r["file_hash"], r["file_path"], r["frontmatter_json"]
            )
            for r in conn.execute(
                "SELECT slug, project, type, file_hash, file_path, frontmatter_json "
                "FROM pages WHERE vault_id = ?", (vault_id,)
            ).fetchall()
        }
        vault = self.get_vault(vault_id)
        if vault is None:
            raise VaultRegistrationError(f"vault_id={vault_id!r} not registered")
        vault_root = vault.root_path

        missing_in_db: list[Path] = []
        hash_mismatch: list[tuple[str, str]] = []
        type_mismatch: list[tuple[str, str, str, str]] = []
        seen_on_disk: set[tuple[str, str]] = set()

        # Two-tier walk — must mirror reindex.discover_pages so course-local
        # pages aren't false-positived as missing-on-disk. Lazy-imported to
        # avoid circular dependency (reindex itself uses SQLiteRepository).
        from scripts.wiki_index.reindex import discover_pages
        for f, slug, project in discover_pages(vault_root):
            seen_on_disk.add((slug, project))
            key = (slug, project)
            if key not in db_rows:
                missing_in_db.append(f)
                continue
            db_type, db_hash, _, db_fm = db_rows[key]
            # Adapter convention: hash full file bytes (frontmatter + body).
            # See manual.py for why frontmatter-aware hashing matters.
            raw = f.read_bytes()
            cur_hash = compute_file_hash(raw)
            if cur_hash != db_hash:
                hash_mismatch.append((slug, project))
            file_type = self._extract_frontmatter_type(
                raw.decode("utf-8", errors="replace")
            )
            if file_type and file_type != db_type:
                if not self._is_intentional_mapping(file_type, db_type, db_fm or ""):
                    type_mismatch.append((slug, project, file_type, db_type))

        missing_on_disk: list[tuple[str, str]] = [
            (slug, project) for (slug, project) in db_rows
            if (slug, project) not in seen_on_disk
        ]
        return DriftReport(
            missing_in_db=missing_in_db,
            missing_on_disk=missing_on_disk,
            hash_mismatch=hash_mismatch,
            type_mismatch=type_mismatch,
        )

    @staticmethod
    def _is_intentional_mapping(file_type: str, db_type: str, db_fm_json: str) -> bool:
        """§6.1 type-mapping: file_type→db_type+tag marker. Not drift if the
        mapping holds AND the marker tag is present in db frontmatter."""
        mapping = {
            "lesson-summary": ("summary", "lesson-summary"),
            "summary-light": ("summary", "summary-light"),
            "meeting-summary": ("summary", "meeting-summary"),
        }
        if file_type not in mapping:
            return False
        expected_db_type, marker = mapping[file_type]
        if db_type != expected_db_type:
            return False
        try:
            fm = json.loads(db_fm_json) if db_fm_json else {}
        except json.JSONDecodeError:
            return False
        tags = fm.get("tags") or []
        return marker in tags

    @staticmethod
    def _extract_frontmatter_type(body: str) -> str | None:
        """Quick YAML frontmatter parse — returns `type:` value or None."""
        if not body.startswith("---\n"):
            return None
        parts = body.split("---\n", 2)
        if len(parts) < 3:
            return None
        import yaml as _yaml
        try:
            fm = _yaml.safe_load(parts[1]) or {}
        except _yaml.YAMLError:
            return None
        if isinstance(fm, dict):
            val = fm.get("type")
            return val if isinstance(val, str) else None
        return None

    def find_cross_vault_concept_duplicates(self) -> list[tuple[str, list[str]]]:
        rows = self._connect().execute(
            "SELECT slug, GROUP_CONCAT(vault_id, ',') AS vaults, "
            "       COUNT(DISTINCT vault_id) AS n "
            "FROM entities WHERE type = 'concept' "
            "GROUP BY slug HAVING n > 1 ORDER BY slug"
        ).fetchall()
        return [(r["slug"], sorted(r["vaults"].split(","))) for r in rows]

    # =========================================================================
    # Log events + batch runs (task-001-19)
    # =========================================================================

    def append_log_event(self, event: LogEvent) -> int:
        conn = self._connect()
        event_date = event.event_ts.date().isoformat()
        cur = conn.execute(
            "INSERT INTO log_events (vault_id, event_ts, event_date, event_type, "
            "subject, pages_created_json, pages_touched_json, contradictions_count, "
            "details_json, log_md_byte_offset) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event.vault_id,
                event.event_ts.isoformat(),
                event_date,
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

    # =========================================================================
    # Entity write-path — TASK 003 v2 / I-7.7a (R-37)
    # =========================================================================

    def upsert_entity(
        self,
        vault_id: str,
        slug: str,
        name: str,
        type: str,
        is_candidate: int,
        canonicalized_by: str,
        first_seen: str,
        last_updated: str,
        file_path: str,
    ) -> None:
        """INSERT or UPDATE entity row; SQL-level downgrade guard.

        ``ON CONFLICT(vault_id, slug) DO UPDATE SET is_candidate =
        MIN(excluded.is_candidate, entities.is_candidate)`` — once an
        entity is confirmed (``is_candidate=0``), incoming ``=1`` does
        NOT overwrite. R-37(b) — see ABC docstring for full rationale.
        """
        conn = self._connect()
        with conn:  # autocommit; rollback on exception
            conn.execute(
                """
                INSERT INTO entities
                    (vault_id, slug, name, type, is_candidate,
                     canonicalized_by, first_seen, last_updated, file_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(vault_id, slug) DO UPDATE SET
                    name = excluded.name,
                    type = excluded.type,
                    is_candidate = MIN(excluded.is_candidate, entities.is_candidate),
                    canonicalized_by = excluded.canonicalized_by,
                    last_updated = excluded.last_updated,
                    file_path = excluded.file_path
                """,
                (vault_id, slug, name, type, is_candidate,
                 canonicalized_by, first_seen, last_updated, file_path),
            )
