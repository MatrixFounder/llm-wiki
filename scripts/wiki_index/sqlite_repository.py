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
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType
from typing import Any, Literal

from scripts.wiki_index.models import (
    AliasCollision,
    BatchMode,
    BatchRun,
    DriftReport,
    Entity,
    LogEvent,
    MergeReport,
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


class AliasCollisionError(RuntimeError):
    """Raised by `add_alias` when the surface already resolves to a *different*
    entity (the hard `(vault_id, alias)` PK, TASK 005 / R-5.1). Carries the
    conflicting canonical slug so the CLI can name it in the error envelope —
    the slug is a safe kebab identifier, NOT the operator-supplied surface (so
    the CWE-117/209 never-echo-content invariant holds)."""

    def __init__(self, conflicting_slug: str) -> None:
        super().__init__(f"alias already resolves to entity {conflicting_slug!r}")
        self.conflicting_slug = conflicting_slug


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
        exclude_types: list[str] | None = None,
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
        if exclude_types:
            # TASK 007: applied in SQL BEFORE the LIMIT (not post-filtered) so an
            # excluded type cannot consume a top-`limit` slot and evict a real hit.
            placeholders = ",".join("?" * len(exclude_types))
            sql_parts.append(f" AND p.type NOT IN ({placeholders})")
            params.extend(exclude_types)
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
        # R-4.5d (TASK 005): alias-aware. A ref whose target is a registered
        # alias resolves to its canonical entity → NOT an orphan. This is what
        # keeps a merged-away `from` slug (still `[[from-slug]]` in source bodies)
        # from polluting lint after a `wiki-merge`.
        sql = (
            "SELECT r.vault_id, r.page_slug, r.page_project, r.entity_slug, "
            "r.line_start, r.source_quote "
            "FROM page_entity_refs r "
            "LEFT JOIN entities e ON e.vault_id = r.vault_id AND e.slug = r.entity_slug "
            "LEFT JOIN pages p ON p.vault_id = r.vault_id AND p.slug = r.entity_slug "
            "LEFT JOIN entity_aliases a ON a.vault_id = r.vault_id AND a.alias = r.entity_slug "
            "WHERE e.slug IS NULL AND p.slug IS NULL AND a.alias IS NULL"
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
        # TASK 012 / architecture-review C1: route through the one config-driven
        # walk (discover_pages) and compare on (slug, project) — NOT bare f.stem.
        # The old inline walk compared slug-only, which false-negatived a
        # course-tier page sharing a stem with a vault-tier page. Lazy-import to
        # avoid the reindex↔SQLiteRepository import cycle (mirrors check_drift).
        from scripts.wiki_index.reindex import discover_pages

        db_keys = {
            (r["slug"], r["project"])
            for r in self._connect().execute(
                "SELECT slug, project FROM pages WHERE vault_id = ?", (vault_id,)
            ).fetchall()
        }
        missing = [
            f for (f, slug, project) in discover_pages(vault_root)
            if (slug, project) not in db_keys
        ]
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

    # =========================================================================
    # Entity resolution — Epic 7 (TASK 005, R-4 + R-5)
    # =========================================================================

    def _row_to_entity(self, conn: sqlite3.Connection, row: sqlite3.Row) -> Entity:
        aliases = [
            r["alias"] for r in conn.execute(
                "SELECT alias FROM entity_aliases "
                "WHERE vault_id = ? AND entity_slug = ? ORDER BY alias",
                (row["vault_id"], row["slug"]),
            ).fetchall()
        ]
        return Entity(
            vault_id=row["vault_id"],
            slug=row["slug"],
            type=row["type"],
            name=row["name"],
            aliases=aliases,
            description=row["definition"],
            is_external=bool(row["is_external"]),
        )

    def resolve_entity(self, vault_id: str, slug: str) -> Entity | None:
        """R-4.5: resolve a canonical slug OR an alias surface → its Entity.

        Tries the entities table first; on miss, treats `slug` as an
        `entity_aliases.alias` and resolves through it. None on both misses
        (no raise — retires the Epic-7 NotImplementedError stub)."""
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM entities WHERE vault_id = ? AND slug = ?",
            (vault_id, slug),
        ).fetchone()
        if row is None:
            arow = conn.execute(
                "SELECT entity_slug FROM entity_aliases "
                "WHERE vault_id = ? AND alias = ?",
                (vault_id, slug),
            ).fetchone()
            if arow is None:
                return None
            row = conn.execute(
                "SELECT * FROM entities WHERE vault_id = ? AND slug = ?",
                (vault_id, arow["entity_slug"]),
            ).fetchone()
            if row is None:
                return None
        return self._row_to_entity(conn, row)

    def set_entity_candidate(
        self, vault_id: str, slug: str, is_candidate: int
    ) -> bool:
        """R-4.2/4.3: explicit confirm/undo setter; bypasses the MIN() guard.

        Returns True iff the stored value changed (False = already in target
        state → idempotent). The caller pre-checks existence (resolve_entity);
        a missing row returns False defensively."""
        conn = self._connect()
        row = conn.execute(
            "SELECT is_candidate FROM entities WHERE vault_id = ? AND slug = ?",
            (vault_id, slug),
        ).fetchone()
        if row is None or row["is_candidate"] == is_candidate:
            return False
        conn.execute(
            "UPDATE entities SET is_candidate = ?, last_updated = ?, "
            "canonicalized_by = 'human' WHERE vault_id = ? AND slug = ?",
            (is_candidate, datetime.now().isoformat(), vault_id, slug),
        )
        return True

    def list_candidates(self, vault_id: str) -> list[Entity]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM entities WHERE vault_id = ? AND is_candidate = 1 "
            "ORDER BY slug",
            (vault_id,),
        ).fetchall()
        return [self._row_to_entity(conn, r) for r in rows]

    def _recompute_mentions(
        self, conn: sqlite3.Connection, vault_id: str, slug: str | None = None
    ) -> None:
        """F12c (TASK 006): the single correlated `mentions_count` recompute,
        issued on the caller's `conn` (the caller owns the transaction). `slug`
        scopes to one entity (merge); None recomputes the whole vault (reindex
        Step 3 / `recompute_mentions` / `auto_promote_candidates`). Replaces the
        4 hand-copied UPDATEs so a future index change can't silently desync them.
        """
        sql = (
            "UPDATE entities SET mentions_count = ("
            "  SELECT COUNT(*) FROM page_entity_refs r "
            "  WHERE r.vault_id = entities.vault_id "
            "    AND r.entity_slug = entities.slug"
            ") WHERE vault_id = ?"
        )
        params: list[Any] = [vault_id]
        if slug is not None:
            sql += " AND slug = ?"
            params.append(slug)
        conn.execute(sql, params)

    def recompute_mentions(self, vault_id: str) -> None:
        self._recompute_mentions(self._connect(), vault_id)

    def auto_promote_candidates(self, vault_id: str, threshold: int) -> list[str]:
        """R-4.4: recompute mentions, then promote candidates with
        mentions_count >= threshold. Returns promoted slugs. Atomic."""
        conn = self._connect()
        conn.execute("BEGIN IMMEDIATE")
        try:
            self._recompute_mentions(conn, vault_id)
            promoted = [
                r["slug"] for r in conn.execute(
                    "SELECT slug FROM entities WHERE vault_id = ? "
                    "AND is_candidate = 1 AND mentions_count >= ? ORDER BY slug",
                    (vault_id, threshold),
                ).fetchall()
            ]
            if promoted:
                conn.execute(
                    "UPDATE entities SET is_candidate = 0, last_updated = ?, "
                    "canonicalized_by = 'auto:mentions' WHERE vault_id = ? "
                    "AND is_candidate = 1 AND mentions_count >= ?",
                    (datetime.now().isoformat(), vault_id, threshold),
                )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return promoted

    def preview_promotable(self, vault_id: str, threshold: int) -> list[str]:
        """Read-only would-promote set (R-4.4 --dry-run). Fresh COUNT via a
        sub-SELECT; no UPDATE, no mutation."""
        conn = self._connect()
        return [
            r["slug"] for r in conn.execute(
                "SELECT slug FROM entities e WHERE e.vault_id = ? "
                "AND e.is_candidate = 1 AND ("
                "  SELECT COUNT(*) FROM page_entity_refs r "
                "  WHERE r.vault_id = e.vault_id AND r.entity_slug = e.slug"
                ") >= ? ORDER BY slug",
                (vault_id, threshold),
            ).fetchall()
        ]

    def add_alias(
        self, vault_id: str, alias: str, entity_slug: str,
        alias_type: str = "spelling_variant",
    ) -> None:
        """R-5.1: register a Class B alias mirror. Idempotent same-target re-add;
        raises AliasCollisionError if the surface already maps to a different
        entity (the hard (vault_id, alias) PK)."""
        conn = self._connect()
        existing = conn.execute(
            "SELECT entity_slug FROM entity_aliases WHERE vault_id = ? AND alias = ?",
            (vault_id, alias),
        ).fetchone()
        if existing is not None:
            if existing["entity_slug"] == entity_slug:
                return  # idempotent
            raise AliasCollisionError(existing["entity_slug"])
        conn.execute(
            "INSERT INTO entity_aliases (vault_id, alias, entity_slug, alias_type) "
            "VALUES (?, ?, ?, ?)",
            (vault_id, alias, entity_slug, alias_type),
        )

    def remove_alias(self, vault_id: str, alias: str) -> bool:
        conn = self._connect()
        cur = conn.execute(
            "DELETE FROM entity_aliases WHERE vault_id = ? AND alias = ?",
            (vault_id, alias),
        )
        return cur.rowcount > 0

    def list_aliases(self, vault_id: str, entity_slug: str) -> list[str]:
        conn = self._connect()
        return [
            r["alias"] for r in conn.execute(
                "SELECT alias FROM entity_aliases "
                "WHERE vault_id = ? AND entity_slug = ? ORDER BY alias",
                (vault_id, entity_slug),
            ).fetchall()
        ]

    def expand_query_aliases(self, vault_id: str, term: str) -> list[str]:
        """R-5.5: canonical name + sibling aliases for the entity `term` resolves
        to. Bounded to that entity's own alias set (no transitive expansion).
        [] on no match. Order-stable, de-duplicated."""
        ent = self.resolve_entity(vault_id, term)
        if ent is None:
            return []
        out: list[str] = []
        seen: set[str] = set()
        for surface in [ent.name, *ent.aliases]:
            if surface and surface not in seen:
                seen.add(surface)
                out.append(surface)
        return out

    def check_query_state(self, vault_id: str, query_slug: str) -> str | None:
        """TASK 007 / R-6.6 — recorded `question_hash` for a filed query, or
        None. Defensive NULL guard mirrors `check_idempotency` (L-V3.2)."""
        row = self._connect().execute(
            "SELECT value FROM source_state "
            "WHERE vault_id = ? AND source_kind = 'query' AND scope = ? "
            "AND key = 'question_hash'",
            (vault_id, query_slug),
        ).fetchone()
        if row is None or row["value"] is None:
            return None
        return str(row["value"])

    def record_query_state(
        self, vault_id: str, query_slug: str, question_hash: str,
    ) -> None:
        """TASK 007 / R-6.6 — UPSERT the query-idempotency row in `source_state`
        (`source_kind='query'`, `scope=query_slug`, `key='question_hash'`)."""
        conn = self._connect()
        now = datetime.now(timezone.utc).isoformat()
        with conn:
            conn.execute(
                "INSERT INTO source_state "
                "(vault_id, source_kind, scope, key, value, updated_at) "
                "VALUES (?, 'query', ?, 'question_hash', ?, ?) "
                "ON CONFLICT(vault_id, source_kind, scope, key) DO UPDATE SET "
                "value = excluded.value, updated_at = excluded.updated_at",
                (vault_id, query_slug, question_hash, now),
            )

    def check_verify_state(self, vault_id: str, verification_slug: str) -> str | None:
        """TASK 008 / R-8.6 — recorded `verify_hash` for a filed verdict, or
        None. Defensive NULL guard mirrors `check_query_state` (L-V3.2)."""
        row = self._connect().execute(
            "SELECT value FROM source_state "
            "WHERE vault_id = ? AND source_kind = 'verification' AND scope = ? "
            "AND key = 'verify_hash'",
            (vault_id, verification_slug),
        ).fetchone()
        if row is None or row["value"] is None:
            return None
        return str(row["value"])

    def record_verify_state(
        self, vault_id: str, verification_slug: str, verify_hash: str,
    ) -> None:
        """TASK 008 / R-8.6 — UPSERT the verify-idempotency row in `source_state`
        (`source_kind='verification'`, `scope=verification_slug`,
        `key='verify_hash'`)."""
        conn = self._connect()
        now = datetime.now(timezone.utc).isoformat()
        with conn:
            conn.execute(
                "INSERT INTO source_state "
                "(vault_id, source_kind, scope, key, value, updated_at) "
                "VALUES (?, 'verification', ?, 'verify_hash', ?, ?) "
                "ON CONFLICT(vault_id, source_kind, scope, key) DO UPDATE SET "
                "value = excluded.value, updated_at = excluded.updated_at",
                (vault_id, verification_slug, verify_hash, now),
            )

    def find_alias_collisions(self, vault_id: str) -> list[AliasCollision]:
        """R-5.6: in-DB (legacy) + cross-table alias collisions. The Class A
        frontmatter scan lives in the Lint Layer."""
        conn = self._connect()
        out: list[AliasCollision] = []
        # in-table (only reachable on a legacy / pre-v3 DB; the v3 PK prevents
        # new ones): same alias → >1 entity_slug.
        for r in conn.execute(
            "SELECT alias, GROUP_CONCAT(entity_slug) AS slugs FROM entity_aliases "
            "WHERE vault_id = ? GROUP BY alias HAVING COUNT(DISTINCT entity_slug) > 1",
            (vault_id,),
        ).fetchall():
            out.append(AliasCollision(
                vault_id=vault_id, alias=r["alias"],
                slugs=sorted((r["slugs"] or "").split(",")), kind="in_table",
            ))
        # cross-slug: alias equals a DIFFERENT entity's slug.
        for r in conn.execute(
            "SELECT a.alias, a.entity_slug, e.slug AS other FROM entity_aliases a "
            "JOIN entities e ON e.vault_id = a.vault_id AND e.slug = a.alias "
            "WHERE a.vault_id = ? AND e.slug != a.entity_slug",
            (vault_id,),
        ).fetchall():
            out.append(AliasCollision(
                vault_id=vault_id, alias=r["alias"],
                slugs=sorted([r["entity_slug"], r["other"]]), kind="cross_slug",
            ))
        # cross-name: alias equals a DIFFERENT entity's name.
        for r in conn.execute(
            "SELECT a.alias, a.entity_slug, e.slug AS other FROM entity_aliases a "
            "JOIN entities e ON e.vault_id = a.vault_id AND e.name = a.alias "
            "WHERE a.vault_id = ? AND e.slug != a.entity_slug",
            (vault_id,),
        ).fetchall():
            out.append(AliasCollision(
                vault_id=vault_id, alias=r["alias"],
                slugs=sorted([r["entity_slug"], r["other"]]), kind="cross_name",
            ))
        # frontmatter (P-10/F12b, TASK 006): a surface claimed by ≥2 *entity*
        # pages' Class A `aliases:` blocks — read from pages.frontmatter_json
        # (already in the DB) via json_each, NOT a 2nd O(N) file+YAML sweep. The
        # frontmatter_json is always valid (json.dumps at upsert), so there is no
        # swallowed-parse case (F12b) — a malformed source file is recorded in the
        # reindex `skipped` report, never silently dropped here.
        # vdd-multi MED fix: JOIN entities to restrict to *entity* pages only —
        # the deleted file-scan walked only `_concepts`/`_entities` (the same
        # tier the reindex alias-mirror gates on). Without this join the scan
        # would also flag legal `aliases:` shared between `_sources/` summary
        # pages — a false collision (and an error under `--strict`).
        for r in conn.execute(
            "SELECT je.value AS alias, GROUP_CONCAT(DISTINCT p.slug) AS slugs "
            "FROM pages p "
            "JOIN entities e ON e.vault_id = p.vault_id AND e.slug = p.slug "
            "JOIN json_each(p.frontmatter_json, '$.aliases') je "
            "WHERE p.vault_id = ? "
            "  AND json_type(p.frontmatter_json, '$.aliases') = 'array' "
            "GROUP BY je.value HAVING COUNT(DISTINCT p.slug) > 1",
            (vault_id,),
        ).fetchall():
            out.append(AliasCollision(
                vault_id=vault_id, alias=str(r["alias"]),
                slugs=sorted((r["slugs"] or "").split(",")), kind="frontmatter",
            ))
        return out

    _TRUST_RANK = {"high": 3, "medium": 2, "low": 1}

    def merge_entities(
        self, vault_id: str, from_slug: str, into_slug: str
    ) -> MergeReport:
        """R-4.7: fold `from` into `into` in one transaction. See ABC docstring.

        Caller (`wiki-merge`) does the Class A mutations first (C-8)."""
        conn = self._connect()
        refs_repointed = 0
        aliases_absorbed = 0
        aliases_skipped: list[str] = []

        conn.execute("BEGIN IMMEDIATE")
        try:
            # F2 (vdd-multi): read from_name INSIDE the tx — sampling it in
            # autocommit was a TOCTOU window on the shared multi-vault DB. Raise
            # if the row vanished so the DAL is self-consistent (the CLI's
            # resolve_entity pre-check is itself outside this tx).
            from_row = conn.execute(
                "SELECT name FROM entities WHERE vault_id = ? AND slug = ?",
                (vault_id, from_slug),
            ).fetchone()
            if from_row is None:
                raise ValueError(f"merge source entity {from_slug!r} not found")
            from_name = from_row["name"]
            # 1. re-point page_entity_refs, dedup on the PK keeping higher trust.
            from_refs = conn.execute(
                "SELECT rowid AS rid, page_slug, page_project, ref_type, "
                "trust_level FROM page_entity_refs "
                "WHERE vault_id = ? AND entity_slug = ?",
                (vault_id, from_slug),
            ).fetchall()
            for fr in from_refs:
                existing = conn.execute(
                    "SELECT rowid AS rid, trust_level FROM page_entity_refs "
                    "WHERE vault_id = ? AND page_slug = ? AND page_project = ? "
                    "AND entity_slug = ? AND ref_type = ?",
                    (vault_id, fr["page_slug"], fr["page_project"],
                     into_slug, fr["ref_type"]),
                ).fetchone()
                if existing is None:
                    conn.execute(
                        "UPDATE page_entity_refs SET entity_slug = ? WHERE rowid = ?",
                        (into_slug, fr["rid"]),
                    )
                else:
                    if (self._TRUST_RANK.get(fr["trust_level"], 0)
                            > self._TRUST_RANK.get(existing["trust_level"], 0)):
                        conn.execute(
                            "UPDATE page_entity_refs SET trust_level = ? "
                            "WHERE rowid = ?",
                            (fr["trust_level"], existing["rid"]),
                        )
                    conn.execute(
                        "DELETE FROM page_entity_refs WHERE rowid = ?", (fr["rid"],)
                    )
                refs_repointed += 1

            # 2. re-point from's existing aliases to into (alias PK unique → no
            #    collision possible; simple set-based UPDATE).
            cur = conn.execute(
                "UPDATE entity_aliases SET entity_slug = ? "
                "WHERE vault_id = ? AND entity_slug = ?",
                (into_slug, vault_id, from_slug),
            )
            aliases_absorbed += cur.rowcount

            # 3. register the durable redirect: from's slug + name as
            #    former_name aliases of into. Skip+report on a third-entity PK
            #    collision (never silent).
            for surface in [s for s in (from_slug, from_name) if s]:
                ex = conn.execute(
                    "SELECT entity_slug FROM entity_aliases "
                    "WHERE vault_id = ? AND alias = ?",
                    (vault_id, surface),
                ).fetchone()
                if ex is not None:
                    if ex["entity_slug"] != into_slug:
                        aliases_skipped.append(surface)
                    continue
                conn.execute(
                    "INSERT INTO entity_aliases "
                    "(vault_id, alias, entity_slug, alias_type) "
                    "VALUES (?, ?, ?, 'former_name')",
                    (vault_id, surface, into_slug),
                )
                aliases_absorbed += 1

            # 4. delete the from entity row.
            conn.execute(
                "DELETE FROM entities WHERE vault_id = ? AND slug = ?",
                (vault_id, from_slug),
            )

            # 5. recompute into.mentions_count within the same tx (F12c helper).
            self._recompute_mentions(conn, vault_id, slug=into_slug)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return MergeReport(
            refs_repointed=refs_repointed,
            aliases_absorbed=aliases_absorbed,
            aliases_skipped=aliases_skipped,
        )

    def get_entity_file_path(self, vault_id: str, slug: str) -> str | None:
        row = self._connect().execute(
            "SELECT file_path FROM entities WHERE vault_id = ? AND slug = ?",
            (vault_id, slug),
        ).fetchone()
        return row["file_path"] if row else None

    def find_entity_by_name(self, vault_id: str, name: str) -> str | None:
        row = self._connect().execute(
            "SELECT slug FROM entities WHERE vault_id = ? AND name = ? "
            "ORDER BY slug LIMIT 1",
            (vault_id, name),
        ).fetchone()
        return row["slug"] if row else None
