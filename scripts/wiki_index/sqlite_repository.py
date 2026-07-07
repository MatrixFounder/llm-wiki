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
import re
import sqlite3
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType
from typing import Any, Literal

from scripts.wiki_index.models import (
    AliasCollision,
    BatchMode,
    BatchRun,
    ClassificationLeakHit,
    CoverageGap,
    CoverageRule,
    DriftHit,
    DriftReport,
    DriftRule,
    Entity,
    InvalidClassificationHit,
    LogEvent,
    MergeReport,
    OrphanLink,
    Page,
    PageHit,
    PageRef,
    Vault,
)
from scripts.wiki_index.repository import IndexRepository, validate_filter_field

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

    def _replace_refs_in_txn(
        self,
        conn: sqlite3.Connection,
        vault_id: str,
        page_slug: str,
        page_project: str,
        refs: list[PageRef],
    ) -> None:
        """TASK 030 (R-030-2a): the txn-free DML body of `replace_refs`
        (PK-dedupe + DELETE-all + INSERT). The CALLER MUST hold an open
        transaction — same contract as `_upsert_page_in_txn`, and here the
        hazard is concrete: a bare autocommit call makes the DELETE and each
        INSERT row SEPARATE transactions, so a crash mid-call destroys every
        ref for the page with no rollback. Never call it outside an open tx.
        Private, not on the ABC."""
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

    def replace_refs(
        self,
        vault_id: str,
        page_slug: str,
        page_project: str,
        refs: list[PageRef],
    ) -> None:
        """Owns its transaction — delegates the DML to `_replace_refs_in_txn`
        (TASK 030 split; behavior-equivalent, atomic DELETE+INSERT; the
        pure-Python dedupe now runs inside the lock window — observably
        identical, negligible delta)."""
        conn = self._connect()
        conn.execute("BEGIN IMMEDIATE")
        try:
            self._replace_refs_in_txn(conn, vault_id, page_slug, page_project, refs)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    @staticmethod
    def _ref_from_row(r: Any) -> PageRef:
        return PageRef(
            vault_id=r["vault_id"], page_slug=r["page_slug"],
            page_project=r["page_project"], entity_slug=r["entity_slug"],
            ref_type=r["ref_type"], line_start=r["line_start"],
            line_end=r["line_end"], source_quote=r["source_quote"],
            trust_level=r["trust_level"],
        )

    _REF_COLS = ("vault_id, page_slug, page_project, entity_slug, ref_type, "
                 "line_start, line_end, source_quote, trust_level")

    def get_backlinks(
        self, vault_id: str, entity_slug: str, ref_type: str | None = None,
    ) -> list[PageRef]:
        """INBOUND refs (pages pointing AT `entity_slug`). TASK 032 / R-032-4:
        optional `ref_type` kind-filter (default None = all kinds — existing
        merge/lint callers unaffected)."""
        conn = self._connect()
        sql = (f"SELECT {self._REF_COLS} FROM page_entity_refs "
               "WHERE vault_id=? AND entity_slug=?")
        params: list[Any] = [vault_id, entity_slug]
        if ref_type is not None:
            sql += " AND ref_type=?"
            params.append(ref_type)
        sql += " ORDER BY page_slug, ref_type, COALESCE(line_start, 0)"
        return [self._ref_from_row(r) for r in conn.execute(sql, params).fetchall()]

    def concept_pages(self, vault_id: str) -> list[tuple[str, str, str]]:
        """TASK 047 — every concept page in the vault, as `(slug, project, file_path)`.
        Concept/entity pages are written by `wiki-extract-concepts` with a hardcoded
        `type: concept`, so a single indexed-type query enumerates them all (no N+1, no
        per-layout `_concepts/` dir re-resolution — `file_path` is already resolved)."""
        return [
            (str(r["slug"]), str(r["project"]), str(r["file_path"]))
            for r in self._connect().execute(
                "SELECT slug, project, file_path FROM pages "
                "WHERE vault_id=? AND type='concept' ORDER BY slug, project",
                (vault_id,),
            ).fetchall()
        ]

    # Page types that are NOT content "sources": the concept's own page (self / concept→concept),
    # the auto-rendered index, and the DERIVED RAG/verdict artefacts (query, verification). The
    # ledger lists genuine source content (summary / brief / research) that MENTIONS the concept.
    _NON_SOURCE_PAGE_TYPES = ("concept", "index", "query", "verification")

    def mentioning_source_pages(self, vault_id: str, entity_slug: str) -> list[str]:
        """TASK 047 — the DISTINCT, sorted slugs of CONTENT-SOURCE pages that carry a
        `ref_type='mentioned'` inbound ref to `entity_slug` (the "Mentions across sources" set).
        The `mentioned`-only filter excludes typed-edge / `cited` / `verifies` backlinks; the
        `pages.type NOT IN (concept, index, query, verification)` join excludes the concept's own
        page (self-reference) + concept→concept cross-links + the derived index/RAG/verdict pages —
        leaving the genuine source notes. This SET is the rebuild-stable invariant (`reindex --full`
        re-derives the same `mentioned` refs from the source footers); per-ref quote/span are NOT
        rendered (they differ between extract-time and reindex, so they are deliberately omitted)."""
        placeholders = ",".join("?" * len(self._NON_SOURCE_PAGE_TYPES))
        return [
            str(r["page_slug"])
            for r in self._connect().execute(
                "SELECT DISTINCT r.page_slug FROM page_entity_refs r "
                "JOIN pages p ON (p.vault_id=r.vault_id AND p.slug=r.page_slug "
                "                 AND p.project=r.page_project) "
                "WHERE r.vault_id=? AND r.entity_slug=? AND r.ref_type='mentioned' "
                f"  AND p.type NOT IN ({placeholders}) "
                "ORDER BY r.page_slug",
                (vault_id, entity_slug, *self._NON_SOURCE_PAGE_TYPES),
            ).fetchall()
        ]

    def refs_from(
        self, vault_id: str, page_slug: str, page_project: str,
        ref_type: str | None = None,
    ) -> list[PageRef]:
        """OUTBOUND refs FROM a page (the source). TASK 032 / R-032-4."""
        conn = self._connect()
        sql = (f"SELECT {self._REF_COLS} FROM page_entity_refs "
               "WHERE vault_id=? AND page_slug=? AND page_project=?")
        params: list[Any] = [vault_id, page_slug, page_project]
        if ref_type is not None:
            sql += " AND ref_type=?"
            params.append(ref_type)
        sql += " ORDER BY entity_slug, ref_type"
        return [self._ref_from_row(r) for r in conn.execute(sql, params).fetchall()]

    def neighbors(
        self, vault_id: str, slug: str, project: str,
        direction: str = "both", ref_type: str | None = None,
    ) -> list[PageRef]:
        """One-hop typed-edge refs touching a page. `direction`: 'out' (refs_from),
        'in' (get_backlinks), 'both' (TASK 032 / R-032-4)."""
        refs: list[PageRef] = []
        if direction in ("out", "both"):
            refs.extend(self.refs_from(vault_id, slug, project, ref_type))
        if direction in ("in", "both"):
            refs.extend(self.get_backlinks(vault_id, slug, ref_type))
        return refs

    def edge_chain(
        self, vault_id: str, start_slug: str, ref_type: str,
        direction: str = "out", max_depth: int = 8,
    ) -> list[tuple[str, int]]:
        """Bounded BFS over a SINGLE `ref_type` from `start_slug` (slug-based, like
        the edge model). `direction` 'out' follows page→entity; 'in' follows
        entity→page. Returns `(slug, depth)` reachable within `max_depth` in BFS
        order — **cycle-safe** (visited set) + **depth-capped** (TASK 032 / R-032-4;
        no unbounded recursion — TASK 018/030 DoS posture). One query (no N+1):
        loads the ref_type's edges into an in-memory adjacency, then BFS."""
        conn = self._connect()
        rows = conn.execute(
            "SELECT page_slug, entity_slug FROM page_entity_refs "
            "WHERE vault_id=? AND ref_type=?", (vault_id, ref_type),
        ).fetchall()
        adj: dict[str, set[str]] = {}
        for r in rows:
            src, dst = ((r["page_slug"], r["entity_slug"]) if direction == "out"
                        else (r["entity_slug"], r["page_slug"]))
            adj.setdefault(src, set()).add(dst)
        out: list[tuple[str, int]] = []
        visited = {start_slug}
        frontier: deque[tuple[str, int]] = deque([(start_slug, 0)])  # popleft O(1)
        while frontier:
            node, depth = frontier.popleft()
            if depth >= max_depth:
                continue
            for nxt in sorted(adj.get(node, set())):
                if nxt in visited:
                    continue
                visited.add(nxt)
                out.append((nxt, depth + 1))
                frontier.append((nxt, depth + 1))
        return out

    # =========================================================================
    # Search (task-001-17) — FTS5 + BM25 + multi-vault filter (R-29)
    # =========================================================================

    def search_pages(
        self,
        query: str | None,
        *,
        vaults: list[str] | None = None,
        types: list[str] | None = None,
        exclude_types: list[str] | None = None,
        project: str | None = None,
        where_fields: list[tuple[str, str]] | None = None,
        as_of: str | None = None,
        allowed_classifications: list[str] | None = None,
        classification_default: str | None = None,
        classification_home_vault: str | None = None,
        min_trust: str | None = None,
        limit: int = 20,
        _use_fts_narrowing: bool = True,
    ) -> list[PageHit]:
        # `_use_fts_narrowing` is a PRIVATE test seam (TASK 035) — not in the ABC
        # contract. Default True = production (FTS-narrow the metadata `tags`
        # membership path); the equivalence tests pass False to drive the REAL plain
        # scan over the same input and assert byte-identical results (ADR-005 D2).
        conn = self._connect()
        has_match = bool(query)
        if not has_match and not where_fields and not as_of:
            # TASK 013: a search with neither an FTS term nor a metadata filter
            # (TASK 034: nor an `as_of` temporal filter) is meaningless. The CLI
            # refuses this before calling; the DAL defends the library-caller path.
            raise ValueError(
                "search_pages requires a non-empty query, at least one "
                "where_fields predicate, or an as_of date"
            )
        # Shared page-column projection for both paths so `_row_to_page` sees an
        # identical row shape.
        page_cols = (
            "p.vault_id, p.slug, p.project, p.type, p.title, p.file_path, "
            "p.tldr, p.date, p.last_modified, p.file_hash, p.frontmatter_json, "
            "p.body_excerpt, p.is_frozen"
        )
        # TASK 035: the AND-clauses below are IDENTICAL across the FTS-query path, the
        # metadata scan, and the metadata FTS-narrowed path — built ONCE into
        # `clause_parts`/`clause_params` (separate from the SELECT prefix) so the three
        # query shapes can never drift.
        clause_parts: list[str] = []
        clause_params: list[Any] = []
        if vaults is not None:
            clause, vals = self._in_clause("p.vault_id", vaults)
            clause_parts.append(f" AND {clause}")
            clause_params.extend(vals)
        if types is not None:
            clause, vals = self._in_clause("p.type", types)
            clause_parts.append(f" AND {clause}")
            clause_params.extend(vals)
        if exclude_types:
            # TASK 007: applied in SQL BEFORE the LIMIT (not post-filtered) so an
            # excluded type cannot consume a top-`limit` slot and evict a real hit.
            placeholders = ",".join("?" * len(exclude_types))
            clause_parts.append(f" AND p.type NOT IN ({placeholders})")
            clause_params.extend(exclude_types)
        if project is not None:
            clause_parts.append(" AND p.project = ?")
            clause_params.append(project)
        if (allowed_classifications is None) != (classification_default is None):
            # TASK 049: both-or-neither (library-caller defense, arch-review
            # MED-2) — a lone allowed-list would make an UNCLASSIFIED page
            # vanish via COALESCE(NULL, NULL) instead of falling back to the
            # vault default_level.
            raise ValueError(
                "allowed_classifications and classification_default must be "
                "provided together")
        if allowed_classifications is not None:
            if not allowed_classifications:
                raise ValueError("allowed_classifications must be non-empty")
            # TASK 049 (R-2 / ADR-009): the policy visibility filter. Fixed
            # literal JSON path; default + every level bound; applied via the
            # shared clause_parts so it lands on all three query shapes BEFORE
            # the LIMIT (exclude_types rationale — a filtered page must never
            # consume a top-limit slot). CAST normalizes a numeric/boolean
            # authored value to text (the where_fields scalar-branch rationale).
            # Unknown/foreign labels are excluded automatically — fail-closed.
            placeholders = ",".join("?" * len(allowed_classifications))
            if classification_home_vault is not None:
                # vdd-multi SEC-2: the default_level fallback applies ONLY to
                # the profile's HOME vault — a foreign vault's UNCLASSIFIED
                # page must not inherit it (its own vault may intend a higher
                # default). CASE yields NULL for foreign rows → COALESCE stays
                # NULL → `NULL IN (...)` is not true → fail closed; a foreign
                # page explicitly labeled with an in-ladder level still passes.
                clause_parts.append(
                    " AND COALESCE(CAST(json_extract(p.frontmatter_json,"
                    " '$.classification') AS TEXT),"
                    " CASE WHEN p.vault_id = ? THEN ? END)"
                    f" IN ({placeholders})"
                )
                clause_params.append(classification_home_vault)
                clause_params.append(classification_default)
            else:
                # No known home vault (built-in ladder outside any vault, or
                # an unregistered root): the default applies uniformly —
                # documented; matches the single-vault case where every page
                # IS the home vault's.
                clause_parts.append(
                    " AND COALESCE(CAST(json_extract(p.frontmatter_json,"
                    " '$.classification') AS TEXT), ?)"
                    f" IN ({placeholders})"
                )
                clause_params.append(classification_default)
            clause_params.extend(allowed_classifications)
        if min_trust is not None:
            # TASK 050 (R-6): derived-trust floor, pre-LIMIT on all three query
            # shapes. Predicates are FIXED LITERALS (no params) test-pinned to
            # policy.trust_tier (Q-050-3): `_` is a LIKE wildcard so the _raw
            # segment is ESCAPE'd; the http(s):// prefix is exact (never bare
            # 'http' — httpx:// must not match); LIKE's default ASCII-ci fold
            # matches the Python .lower() on both halves; json_extract of a
            # non-scalar yields '['/'{' text, which the prefix LIKE rejects —
            # non-scalar sources are NOT external on either side.
            if min_trust not in ("external", "internal", "verified"):
                raise ValueError(
                    "min_trust must be one of external|internal|verified")
            # COALESCE to '' — an absent key json_extract's to SQL NULL, and
            # `FALSE OR NULL` = NULL would make `NOT (<ext>)` exclude EVERY
            # unadorned page (three-valued logic); '' LIKE 'http://%' is a
            # clean FALSE.
            _J = ("COALESCE(CAST(json_extract(p.frontmatter_json, '$.{k}')"
                  " AS TEXT), '')")
            _EXT = (
                "(p.file_path LIKE '\\_raw/%' ESCAPE '\\'"
                " OR p.file_path LIKE '%/\\_raw/%' ESCAPE '\\'"
                + "".join(
                    f" OR {_J.format(k=k)} LIKE '{scheme}://%'"
                    for k in ("source", "URL", "url")
                    for scheme in ("http", "https"))
                + ")"
            )
            if min_trust in ("internal", "verified"):
                clause_parts.append(f" AND NOT {_EXT}")
            if min_trust == "verified":
                clause_parts.append(
                    " AND EXISTS (SELECT 1 FROM page_entity_refs vr"
                    "             WHERE vr.vault_id = p.vault_id"
                    "               AND vr.entity_slug = p.slug"
                    "               AND vr.ref_type = 'verifies')")
            # min_trust == 'external' imposes no clause (the lowest floor).
        for field, value in where_fields or []:
            # TASK 013 (R-X3-META-FILTER) + TASK 033 (R-1, list membership):
            # library-caller defense — re-validate the field name (CLI validates
            # too), then bind the JSON path and the value as parameters (FOUR per
            # field, order `(path, value, path, value)` — B-1; positional `?` can't
            # be reused across the two subexpressions). No operator string ever
            # reaches the SQL text.
            #
            # Branch 1 — SCALAR equality. `CAST(... AS TEXT)` matches by STRING
            #   representation: `json_extract` returns the value in its native JSON
            #   storage class (INTEGER 1 for `priority: 1`), which SQLite will NOT
            #   equate to a TEXT-bound `'1'`; the CAST normalises both sides so a
            #   numeric/boolean frontmatter value matches the (always-string) CLI
            #   value, while string values stay byte-identical.
            # Branch 2 — LIST MEMBERSHIP (TASK 033). `json_each` over a list field
            #   (`tags: [eg-demo, decision]` — the TASK-031 typed-class tag) yields
            #   one row per member, so `value = ?` matches a single member that the
            #   scalar branch's whole-array text never could. Over a SCALAR field
            #   json_each yields one row equal to the scalar (so the OR is a strict
            #   superset → scalar `--status`/`--severity` result sets are UNCHANGED,
            #   AC-3); over an ABSENT path it yields zero rows (no match, no error).
            #   This is the proven `find_pages_citing_source` shape (M-1: the
            #   membership branch is text-only — no CAST — so a NUMERIC list member
            #   is not string-coerced; the typed-class `tags[]` use case is all text).
            validate_filter_field(field)
            clause_parts.append(
                " AND (CAST(json_extract(p.frontmatter_json, ?) AS TEXT) = ?"
                " OR EXISTS (SELECT 1 FROM json_each(p.frontmatter_json, ?)"
                "            WHERE value = ?))"
            )
            json_path = f"$.{field}"
            clause_params.append(json_path)
            clause_params.append(value)
            clause_params.append(json_path)
            clause_params.append(value)
        if as_of is not None:
            # TASK 034 / R-1 — temporal "active as of DATE" filter. A page is active
            # iff its effective_from <= DATE AND DATE < its effective_to, where:
            #   effective_from = COALESCE(authored valid_from, pages.date)
            #   effective_to   = authored valid_to  (explicit override, half-open),
            #                    ELSE the date of the earliest page that SUPERSEDES or
            #                    INVALIDATES it (the TASK 032/034 graph), ELSE +inf.
            # Frontmatter dates are stored as ISO strings (`_json_safe`, normalization
            # .py) and `pages.date` is `.isoformat()` TEXT, so the comparisons are
            # lexicographic = chronological. The `valid_from`/`valid_to` JSON paths are
            # FIXED literals (no user field name → no allowlist needed); DATE is bound
            # 3× as a parameter (never interpolated). A page with neither valid_from nor
            # a `date` is EXCLUDED (the IS NOT NULL clause) so non-temporal pages do not
            # pollute the result. The `NOT EXISTS` successor-walk rides idx_refs_page +
            # the pages PK and is bounded by the outer LIMIT.
            # `substr(...,1,10)` takes the DATE part of an authored valid_from/valid_to
            # so a datetime-valued override (`2026-02-01 14:30` → ISO `...T14:30:00`)
            # keeps the half-open [from, to) DAY boundary (vdd-multi logic MED-2);
            # bare-date overrides are unchanged (`substr` is a no-op on `YYYY-MM-DD`).
            # `pages.date` is already a pure ISO date (Page.date.isoformat()), so it is
            # NOT wrapped. The successor walk excludes a target slug that resolves to >1
            # page: the project-less `entity_slug` cannot disambiguate, so — mirroring
            # `_derive_inverse_edges`' COUNT=1 guard — an unrelated same-slug page in
            # ANOTHER project can never wrongly retire P (vdd-multi logic MED-1; a no-op
            # on single-project vaults where every slug is unique, conservative
            # "stay active when ambiguous" otherwise).
            clause_parts.append(
                " AND COALESCE(substr(json_extract(p.frontmatter_json, '$.valid_from'), 1, 10),"
                "              p.date) IS NOT NULL"
                " AND COALESCE(substr(json_extract(p.frontmatter_json, '$.valid_from'), 1, 10),"
                "              p.date) <= ?"
                " AND (substr(json_extract(p.frontmatter_json, '$.valid_to'), 1, 10) > ?"
                "      OR (json_extract(p.frontmatter_json, '$.valid_to') IS NULL"
                "          AND NOT EXISTS (SELECT 1 FROM page_entity_refs r"
                "             JOIN pages s ON s.vault_id = r.vault_id"
                "                         AND s.slug = r.entity_slug"
                "             WHERE r.vault_id = p.vault_id AND r.page_slug = p.slug"
                "               AND r.ref_type IN ('superseded-by', 'invalidated-by')"
                "               AND s.date IS NOT NULL AND s.date <= ?"
                "               AND (SELECT COUNT(*) FROM pages tc"
                "                    WHERE tc.vault_id = r.vault_id"
                "                      AND tc.slug = r.entity_slug) = 1)))"
            )
            clause_params.append(as_of)
            clause_params.append(as_of)
            clause_params.append(as_of)
        clause_sql = "".join(clause_parts)

        if has_match:
            # FTS path (today's behaviour): BM25-ranked. Untouched by TASK 035 —
            # the issue notes the json_extract/json_each predicates run only on the
            # already-small MATCH candidate set here (a non-issue).
            sql = (
                f"SELECT {page_cols}, bm25(pages_fts) AS bm25_score, "
                "snippet(pages_fts, -1, '<b>', '</b>', '...', 16) AS snip "
                "FROM pages_fts JOIN pages p ON pages_fts.rowid = p.id "
                "WHERE pages_fts MATCH ?"
                + clause_sql + " ORDER BY bm25_score ASC LIMIT ?"
            )
            rows = conn.execute(sql, [query, *clause_params, limit]).fetchall()
        else:
            # TASK 013 metadata path: pure listing, no BM25 (score 0.0, empty
            # snippet); deterministic (project, slug, vault_id) ordering — vault_id
            # breaks ties across vaults in an all-vaults listing.
            meta_cols = f"SELECT {page_cols}, 0.0 AS bm25_score, '' AS snip "
            meta_tail = clause_sql + " ORDER BY p.project, p.slug, p.vault_id LIMIT ?"
            scan_sql = meta_cols + "FROM pages p WHERE 1=1" + meta_tail
            scan_params: list[Any] = [*clause_params, limit]

            # TASK 035 (R-X3-MF-SCAN, ADR-005): when an only-metadata query carries a
            # `tags` membership predicate, narrow the candidate set through the
            # ALREADY-EXISTING, already-maintained `pages_fts.tags` index ("FTS
            # narrows, json_each confirms") instead of scanning the whole partition.
            # The json_each(...) = ? confirm above stays, so the result is BYTE-
            # IDENTICAL to the scan: the FTS column-match is a superset (the same
            # unicode61 tokenizer folds both sides, so an exact array element's
            # tokens always appear in that element's FTS text — all-or-nothing per
            # value), and the confirm removes the FTS extras.
            fts_value: str | None = None
            if _use_fts_narrowing:
                for field, value in where_fields or []:
                    # `isinstance(str)` guards a non-str library-caller value (the CLI
                    # only ever sends str): an int/float `value` would crash
                    # `any(c.isalnum() ...)` AND has no FTS-phrase form — skip
                    # narrowing → the scan binds it into json_each exactly as before
                    # (vdd-multi critic-logic MED; the scan path never crashed on it).
                    # `any(isalnum)` is then a PERF fast-path only (skip the FTS probe
                    # for an obviously-tokenless value) — NOT the correctness gate;
                    # that is the FTS-empty→scan fallback below (ADR-005 D3).
                    if (field == "tags" and isinstance(value, str)
                            and any(c.isalnum() for c in value)):
                        fts_value = value
                        break
            if fts_value is not None:
                # `tags` is a FIXED literal column name; the value is the single bound
                # MATCH parameter, FTS-phrase-quoted ('"'-doubled) so any FTS operator
                # or quote inside it is inert (the SQL text carries only `MATCH ?`).
                # Mirror of `scripts/wiki_skills/_retrieval.fts_quote`, inlined to
                # avoid a wiki_index→wiki_skills layering inversion (ADR-005 D5).
                match_param = 'tags : "' + fts_value.replace('"', '""') + '"'
                fts_sql = (
                    meta_cols + "FROM pages_fts JOIN pages p "
                    "ON pages_fts.rowid = p.id WHERE pages_fts MATCH ?" + meta_tail
                )
                try:
                    rows = conn.execute(
                        fts_sql, [match_param, *scan_params]).fetchall()
                except sqlite3.OperationalError:
                    # Belt-and-braces: a degenerate MATCH (near-unreachable — the
                    # phrase-quote always emits a valid FTS literal) → fall back.
                    rows = conn.execute(scan_sql, scan_params).fetchall()
                else:
                    # Load-bearing safety net (ADR-005 D3): a value FTS can't tokenize
                    # (e.g. `½`/`②` — isalnum-true but no unicode61 token) yields ∅,
                    # which — because the match is all-or-nothing per value — is
                    # indistinguishable from a genuinely-empty result. Re-run the scan
                    # so a literal-tag page can never be silently under-matched.
                    if not rows:
                        rows = conn.execute(scan_sql, scan_params).fetchall()
            else:
                rows = conn.execute(scan_sql, scan_params).fetchall()

        hits: list[PageHit] = []
        for row in rows:
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

    def find_lifecycle_drift(
        self, vault_id: str, rules: list[DriftRule]
    ) -> list[DriftHit]:
        # TASK 036 / R-15 (Slice A1) — a page whose AUTHORED `$.status` contradicts its
        # event-graph state. Keyed on frontmatter `$.type` (the RAW class, NOT pages.type
        # which is the db-bucket) + an EXISTS over page_entity_refs where page_slug IS this
        # page (the auto-derived INVERSE edge, e.g. superseded-by — unambiguous on the page
        # side, so no cross-project COUNT guard is needed: the inverse was only derived when
        # the forward target resolved uniquely). page_class/edge/status values are BOUND
        # params; the `$.type`/`$.status` JSON paths are FIXED literals (no user field name).
        # Read-only; zero DDL.
        #
        # NOTE (vdd-multi): the inverse-edge reliance means drift can UNDER-report right
        # after a `wiki-reindex --delta` that re-walked only ONE side of a bidirectionally-
        # authored edge — the inverse on the un-walked page is restored on the next `--full`
        # (see reindex.py). So `wiki-lint --strict` drift gating assumes a recent `--full`.
        # COST: one scan of `pages` PER rule (O(N·rules); `$.type` is unindexed by design,
        # P-5) — fine for the small typed vaults; revisit a single CASE/CTE pass only if a
        # typed partition grows large.
        conn = self._connect()
        out: list[DriftHit] = []
        for rule in rules:
            sql = (
                "SELECT p.slug, p.project, "
                "CAST(json_extract(p.frontmatter_json, '$.status') AS TEXT) AS status "
                "FROM pages p "
                "WHERE p.vault_id = ? "
                "AND json_extract(p.frontmatter_json, '$.type') = ? "
                "AND EXISTS (SELECT 1 FROM page_entity_refs r "
                "            WHERE r.vault_id = p.vault_id "
                "              AND r.page_slug = p.slug "
                "              AND r.page_project = p.project "
                "              AND r.ref_type = ?) "
            )
            params: list[Any] = [vault_id, rule.page_class, rule.edge]
            # Only a SCALAR text status is a clean contradiction. `json_type(...) = 'text'`
            # excludes BOTH an absent status (path missing → NULL → not 'text') AND a
            # NON-scalar status (a YAML list `status: [superseded]` json_extract's to the
            # text `["superseded"]`, which would otherwise phantom-match `<> expected`;
            # vdd-multi critic-logic MED). So NULL/list/object statuses are never drift.
            sql += "AND json_type(p.frontmatter_json, '$.status') = 'text' "
            if rule.expect_status is not None:
                # Drift = scalar status present and != expected.
                sql += "AND CAST(json_extract(p.frontmatter_json, '$.status') AS TEXT) <> ? "
                params.append(rule.expect_status)
                expected = f"status == {rule.expect_status}"
            elif rule.forbid_status:
                # Drift = scalar status IN the forbidden set.
                placeholders = ",".join("?" * len(rule.forbid_status))
                sql += (f"AND CAST(json_extract(p.frontmatter_json, '$.status') AS TEXT) "
                        f"IN ({placeholders}) ")
                params.extend(rule.forbid_status)
                expected = "status not in {" + ", ".join(rule.forbid_status) + "}"
            else:
                # Defensive (critic-security LOW-1, parity with find_coverage_gaps): a
                # hand-built rule (bypassing the config-load gate) with NEITHER branch would
                # otherwise build a degenerate `IN ()`. Skip it — never crash, never inject.
                continue
            sql += "ORDER BY p.project, p.slug"
            for r in conn.execute(sql, params).fetchall():
                out.append(DriftHit(
                    vault_id=vault_id, page_slug=r["slug"], page_project=r["project"],
                    page_class=rule.page_class, edge=rule.edge,
                    status=r["status"], expected=expected,
                ))
        return out

    def find_coverage_gaps(
        self, vault_id: str, rules: list[CoverageRule]
    ) -> list[CoverageGap]:
        # TASK 036 / R-15 (Slice A2) — a page MISSING an expected relation. Keyed on
        # frontmatter `$.type`. `requires_edge` → NOT EXISTS a page_entity_refs row
        # (page_slug IS this page) of that ref_type. `requires_field` → the frontmatter
        # scalar `$.<field>` is absent OR empty (''). Field names are re-validated
        # (library-caller defense; the config-load gate already validated built-ins) and
        # the JSON path is bound as a param. Read-only; zero DDL.
        conn = self._connect()
        out: list[CoverageGap] = []
        for rule in rules:
            params: list[Any] = [vault_id, rule.page_class]
            if rule.requires_edge is not None:
                sql = (
                    "SELECT p.slug, p.project FROM pages p "
                    "WHERE p.vault_id = ? "
                    "AND json_extract(p.frontmatter_json, '$.type') = ? "
                    "AND NOT EXISTS (SELECT 1 FROM page_entity_refs r "
                    "                WHERE r.vault_id = p.vault_id "
                    "                  AND r.page_slug = p.slug "
                    "                  AND r.page_project = p.project "
                    "                  AND r.ref_type = ?) "
                    "ORDER BY p.project, p.slug"
                )
                params.append(rule.requires_edge)
                kind, detail = "edge", rule.requires_edge
            else:
                field = validate_filter_field(rule.requires_field or "")
                json_path = f"$.{field}"
                # Gap = the scalar is absent (NULL), an empty string, or an EMPTY container
                # (`source: []` / `{}` — "no value", json_extract's to the text '[]'/'{}';
                # vdd-multi critic-logic MED). A non-empty scalar OR a non-empty list/object
                # counts as covered. The IN-list is a fixed literal (no params).
                sql = (
                    "SELECT p.slug, p.project FROM pages p "
                    "WHERE p.vault_id = ? "
                    "AND json_extract(p.frontmatter_json, '$.type') = ? "
                    "AND (json_extract(p.frontmatter_json, ?) IS NULL "
                    "     OR CAST(json_extract(p.frontmatter_json, ?) AS TEXT) IN ('', '[]', '{}')) "
                    "ORDER BY p.project, p.slug"
                )
                params.extend([json_path, json_path])
                kind, detail = "field", field
            for r in conn.execute(sql, params).fetchall():
                out.append(CoverageGap(
                    vault_id=vault_id, page_slug=r["slug"], page_project=r["project"],
                    page_class=rule.page_class, kind=kind, detail=detail,
                ))
        return out

    def find_classification_leaks(
        self, vault_id: str, levels: list[str], default_level: str,
    ) -> list[ClassificationLeakHit]:
        # TASK 049 (R-6) — SQL fetches candidate ('cited','verifies') ref pairs
        # with both sides' classification; RANK COMPARISON IS IN PYTHON (the
        # partitions are small; SQL rank gymnastics rejected — P-5 posture).
        # The target join through the project-less entity_slug carries the
        # COUNT=1 same-slug guard (Q-049-3 — mirrors the --as-of successor walk
        # + _derive_inverse_edges) so an unrelated same-slug page in another
        # project can never flag a phantom leak. The ref_type pair is a fixed
        # literal (an enum constant, same style as the as-of walk); vault_id is
        # bound. Read-only; zero DDL.
        conn = self._connect()
        rank = {lvl: i for i, lvl in enumerate(levels)}
        sql = (
            "SELECT r.page_slug, r.page_project, r.ref_type, "
            "CAST(json_extract(src.frontmatter_json, '$.classification') AS TEXT)"
            " AS src_cls, "
            "t.slug AS tgt_slug, "
            "CAST(json_extract(t.frontmatter_json, '$.classification') AS TEXT)"
            " AS tgt_cls "
            "FROM page_entity_refs r "
            "JOIN pages src ON src.vault_id = r.vault_id "
            "               AND src.slug = r.page_slug "
            "               AND src.project = r.page_project "
            "JOIN pages t ON t.vault_id = r.vault_id AND t.slug = r.entity_slug "
            "WHERE r.vault_id = ? AND r.ref_type IN ('cited', 'verifies') "
            "AND (SELECT COUNT(*) FROM pages tc WHERE tc.vault_id = r.vault_id "
            "     AND tc.slug = r.entity_slug) = 1 "
            "ORDER BY r.page_project, r.page_slug, t.slug, r.ref_type"
        )
        out: list[ClassificationLeakHit] = []
        for row in conn.execute(sql, (vault_id,)).fetchall():
            src = row["src_cls"] if row["src_cls"] is not None else default_level
            tgt = row["tgt_cls"] if row["tgt_cls"] is not None else default_level
            if src not in rank or tgt not in rank:
                # Out-of-ladder label — rank-incomparable; the
                # invalid-classification check surfaces it separately.
                continue
            if rank[tgt] > rank[src]:
                out.append(ClassificationLeakHit(
                    vault_id=vault_id, page_slug=row["page_slug"],
                    page_project=row["page_project"], page_level=src,
                    target_slug=row["tgt_slug"], target_level=tgt,
                    ref_type=row["ref_type"],
                ))
        return out

    def find_invalid_classifications(
        self, vault_id: str, levels: list[str],
    ) -> list[InvalidClassificationHit]:
        # TASK 049 (R-6) — an authored, non-null classification that is not a
        # declared level (out-of-ladder string OR any non-string value) fails
        # closed out of every scoped retrieval; surface the page (NEVER the
        # value — CWE-209/NFR-4). Absent / JSON-null extract to SQL NULL and
        # are skipped (null ≡ absent). All level values bound.
        conn = self._connect()
        placeholders = ",".join("?" * len(levels))
        sql = (
            "SELECT p.slug, p.project FROM pages p "
            "WHERE p.vault_id = ? "
            "AND json_extract(p.frontmatter_json, '$.classification') IS NOT NULL "
            "AND (json_type(p.frontmatter_json, '$.classification') <> 'text' "
            f"     OR CAST(json_extract(p.frontmatter_json, '$.classification') "
            f"        AS TEXT) NOT IN ({placeholders})) "
            "ORDER BY p.project, p.slug"
        )
        return [
            InvalidClassificationHit(
                vault_id=vault_id, page_slug=r["slug"], page_project=r["project"])
            for r in conn.execute(sql, [vault_id, *levels]).fetchall()
        ]

    def find_verified_slugs(
        self, pairs: list[tuple[str, str]],
    ) -> set[tuple[str, str]]:
        # TASK 050 (R-5) — batched inbound-`verifies` membership, grouped BY
        # VAULT (vdd-multi perf-MED): the `vault_id = ? AND entity_slug IN
        # (...)` shape is guaranteed to seek idx_refs_entity(vault_id,
        # entity_slug), whereas a row-value `(a,b) IN (VALUES ...)` plan is
        # cost-model-dependent and could degrade to an O(refs) scan on the
        # UNCONDITIONAL prepare path. Chunk 400 slugs: well under both the
        # 999-variable cap AND (for the record — vdd-multi logic-LOW) the
        # SQLITE_MAX_COMPOUND_SELECT=500 limit that bounds long VALUES lists.
        # Read-only; zero DDL.
        if not pairs:
            return set()
        conn = self._connect()
        by_vault: dict[str, list[str]] = {}
        for vid, slug in pairs:
            by_vault.setdefault(vid, []).append(slug)
        out: set[tuple[str, str]] = set()
        chunk = 400
        for vid, slugs in by_vault.items():
            for i in range(0, len(slugs), chunk):
                part = slugs[i:i + chunk]
                placeholders = ",".join("?" * len(part))
                rows = conn.execute(
                    "SELECT DISTINCT r.entity_slug FROM page_entity_refs r "
                    "WHERE r.vault_id = ? AND r.ref_type = 'verifies' "
                    f"AND r.entity_slug IN ({placeholders})",
                    [vid, *part],
                ).fetchall()
                out.update((vid, row["entity_slug"]) for row in rows)
        return out

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

    def check_drift(self, vault_id: str, *, trust_mtime: bool = False) -> DriftReport:
        """Detect Class A↔B drift. **Default = always full sha256** (D-017-B,
        integrity-first: a preserved-mtime tamper must not slip). `trust_mtime=True`
        (the opt-in `wiki-lint --mtime-skip`) skips the read+hash for files whose
        stored `last_modified` still matches disk mtime — fast, integrity-relaxed."""
        from scripts.wiki_source.parsing import compute_file_hash

        conn = self._connect()
        db_rows = {
            (r["slug"], r["project"]): (
                r["type"], r["file_hash"], r["file_path"], r["frontmatter_json"],
                r["last_modified"],
            )
            for r in conn.execute(
                "SELECT slug, project, type, file_hash, file_path, frontmatter_json, "
                "last_modified FROM pages WHERE vault_id = ?", (vault_id,)
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

        # Walk via iter_pages — the canonical config-driven walk that
        # discover_pages wraps — so each DiscoveredPage carries the SINGLE walk
        # stat's mtime, reused by the P-3 --mtime-skip fast-path (no second stat,
        # TASK 017). The (slug, project) set is identical to discover_pages, so this
        # still mirrors the reindex walk (no false missing-on-disk). layout_config
        # does not import SQLiteRepository → cycle-free local import.
        from scripts.wiki_index.layout_config import iter_pages, resolve_layout_config
        config = resolve_layout_config(vault_root)
        for disc in iter_pages(vault_root, config):
            f, slug, project = disc.path, disc.slug, disc.project
            seen_on_disk.add((slug, project))
            key = (slug, project)
            if key not in db_rows:
                missing_in_db.append(f)
                continue
            db_type, db_hash, _, db_fm, db_lastmod = db_rows[key]
            # P-3 --mtime-skip (opt-in, integrity-relaxed): stored mtime == disk
            # mtime → treat as unchanged, skip read+sha256+type. Default ALWAYS
            # hashes (trust_mtime=False, D-017-B). Comparison is crash-proof: an
            # aware-vs-naive datetime (TypeError) or a malformed stored value
            # (ValueError) degrades to hashing — never raises (fail-safe).
            if trust_mtime and db_lastmod is not None and disc.mtime is not None:
                try:
                    unchanged = (datetime.fromtimestamp(disc.mtime)
                                 == datetime.fromisoformat(db_lastmod))
                except (TypeError, ValueError):
                    unchanged = False
                if unchanged:
                    continue
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
                if not self._is_intentional_mapping(file_type, db_type, db_fm or "",
                                                    config.type_mapping):
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
    def _is_intentional_mapping(
        file_type: str, db_type: str, db_fm_json: str,
        type_mapping: dict[str, tuple[str, str | None]] | None = None,
    ) -> bool:
        """§6.1 type-mapping: a file's raw `type:` legitimately mapped onto the
        stored `db_type` is NOT drift. Sources, unioned (layout takes precedence):

        - **DF-017-1**: the resolved layout's `type_mapping` (config-driven, TASK 012)
          — without it, non-karpathy layouts (dev-project `known-issue→research`,
          `task/plan→brief`, …) false-positive every mapped page as `type-mismatch`.
        - the karpathy §6.1 defaults (back-compat / when no layout mapping is passed).

        A mapping carrying a marker `tag` additionally requires that tag in the db
        frontmatter — this disambiguates raw types that share a `db_type`
        (lesson-summary/summary-light → summary; dev-project task/plan → brief), so a
        genuine raw-type change is still caught. A null-marker mapping (the layout maps
        the raw type unconditionally) needs only the `db_type` to match."""
        mapping: dict[str, tuple[str, str | None]] = {
            "lesson-summary": ("summary", "lesson-summary"),
            "summary-light": ("summary", "summary-light"),
            "meeting-summary": ("summary", "meeting-summary"),
        }
        if type_mapping:
            mapping = {**mapping, **type_mapping}
        entry = mapping.get(file_type)
        if entry is None:
            return False
        expected_db_type, marker = entry
        if db_type != expected_db_type:
            return False
        if marker is None:
            return True
        try:
            fm = json.loads(db_fm_json) if db_fm_json else {}
        except json.JSONDecodeError:
            return False
        tags = fm.get("tags") or []
        return marker in tags

    # P-3 (TASK 017): line-anchored fast-path for the common `type: <bare-slug>`
    # case, avoiding a full PyYAML parse per page in check_drift. The strict token
    # class is exactly the real type vocabulary (concept, lesson-summary, query, …);
    # because it is letter-led and anchored to EOL, ANY non-trivial value — quoted,
    # flow `[`/`{`, folded/literal `|`/`>`, anchor `&`, inline `# comment`, spaces,
    # or numeric — simply fails to match and falls back to PyYAML, so the result is
    # byte-identical to the previous always-PyYAML behaviour on the corpus. The `[ \t]+`
    # (≥1 space) after the colon mirrors YAML's mapping rule: `type:foo` (no space) is a
    # plain scalar, NOT a mapping → must fall back to PyYAML (yields None), not match "foo".
    _FM_TYPE_RE = re.compile(r"^type:[ \t]+([A-Za-z][A-Za-z0-9._-]*)[ \t]*$", re.MULTILINE)

    @staticmethod
    def _extract_frontmatter_type(body: str) -> str | None:
        """Return the frontmatter `type:` value or None (regex fast-path → PyYAML
        fallback for anything non-trivial; see `_FM_TYPE_RE`)."""
        if not body.startswith("---\n"):
            return None
        parts = body.split("---\n", 2)
        if len(parts) < 3:
            return None
        fm_block = parts[1]
        m = SQLiteRepository._FM_TYPE_RE.search(fm_block)
        if m is not None:
            return m.group(1)            # clean bare-slug type → trust the fast path
        import yaml as _yaml
        try:
            fm = _yaml.safe_load(fm_block) or {}
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

    def list_all_aliases(self, vault_id: str) -> list[tuple[str, str]]:
        conn = self._connect()
        return [
            (r["alias"], r["entity_slug"]) for r in conn.execute(
                "SELECT alias, entity_slug FROM entity_aliases "
                "WHERE vault_id = ? ORDER BY entity_slug, alias",
                (vault_id,),
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

    def get_source_state(
        self, vault_id: str, source_kind: str, scope: str, key: str
    ) -> str | None:
        """TASK 018 / Q-018-8 — generic `source_state` read. Defensive NULL guard
        mirrors `check_query_state` (a corrupt `value IS NULL` row → None)."""
        row = self._connect().execute(
            "SELECT value FROM source_state "
            "WHERE vault_id = ? AND source_kind = ? AND scope = ? AND key = ?",
            (vault_id, source_kind, scope, key),
        ).fetchone()
        if row is None or row["value"] is None:
            return None
        return str(row["value"])

    def set_source_state(
        self, vault_id: str, source_kind: str, scope: str, key: str, value: str
    ) -> None:
        """TASK 018 / Q-018-8 — generic `source_state` UPSERT (commit marker).
        `'sync'` needs no DDL: `source_state.source_kind` has no CHECK, so the
        partition is pure data (`user_version` stays 5)."""
        conn = self._connect()
        now = datetime.now(timezone.utc).isoformat()
        with conn:
            conn.execute(
                "INSERT INTO source_state "
                "(vault_id, source_kind, scope, key, value, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(vault_id, source_kind, scope, key) DO UPDATE SET "
                "value = excluded.value, updated_at = excluded.updated_at",
                (vault_id, source_kind, scope, key, value, now),
            )

    def find_pages_citing_source(
        self, vault_id: str, rel_path: str, fields: tuple[str, ...]
    ) -> list[str]:
        """TASK 019 / Q-019-4 — D2a provenance over `pages.frontmatter_json`.

        For each allowlisted `field`, a page cites `rel_path` iff the frontmatter
        value equals it as a **scalar** (`json_extract` + `CAST … AS TEXT`) OR as a
        **list element** (`json_each`, the N:1 `sources: [...]` case). Both the JSON
        path and the value are BOUND parameters (no operator string reaches the SQL
        text). A field failing `validate_filter_field` is skipped (never raises)."""
        conn = self._connect()
        seen: set[str] = set()
        out: list[str] = []
        for field in fields:
            try:
                validate_filter_field(field)
            except ValueError:
                continue  # misconfigured field → skip, never crash the scan
            json_path = f"$.{field}"
            rows = conn.execute(
                "SELECT slug FROM pages WHERE vault_id = ? AND ("
                "  CAST(json_extract(frontmatter_json, ?) AS TEXT) = ?"
                "  OR EXISTS (SELECT 1 FROM json_each(frontmatter_json, ?) "
                "             WHERE value = ?)"
                ")",
                (vault_id, json_path, rel_path, json_path, rel_path),
            ).fetchall()
            for r in rows:
                slug = str(r["slug"])
                if slug not in seen:
                    seen.add(slug)
                    out.append(slug)
        return out

    def all_cited_sources(self, vault_id: str, fields: tuple[str, ...]) -> set[str]:
        """TASK 019 / Q-019-4 (perf) — one `json_each` scan per field → the set of
        all cited source paths. `json_each(frontmatter_json, '$.<field>')` yields the
        scalar for a string field AND each element for a list field (`sources:`), so a
        single query covers both shapes. Path bound as a parameter; field allowlisted
        (non-conforming → skipped). Hoisted once per scan by `_resummarize` to replace
        the per-file N+1 (vdd-multi PERF-HIGH).

        TASK 023 — a `sources:` element may be a STRUCTURED OBJECT (e.g. the
        ``{id, url, file}`` shape emitted by `generate-detailed-meeting-summary`)
        rather than a bare path string. SQLite `json_each` over the list yields
        such an element as the object's JSON text with `type='object'`; we parse
        it and harvest every scalar string member, so a basename/path match can
        still find the citeable value (all members describe the SAME source, so
        harvesting the extra id/url alongside the file path is safe — a false
        match would need an unrelated string to equal the target path/basename)."""
        conn = self._connect()
        out: set[str] = set()
        for field in fields:
            try:
                validate_filter_field(field)
            except ValueError:
                continue
            json_path = f"$.{field}"
            rows = conn.execute(
                "SELECT je.value AS v, je.type AS t FROM pages, "
                "json_each(pages.frontmatter_json, ?) je "
                "WHERE pages.vault_id = ? AND je.value IS NOT NULL",
                (json_path, vault_id),
            ).fetchall()
            for r in rows:
                if r["t"] == "object":
                    try:
                        obj = json.loads(r["v"])
                    except (TypeError, ValueError):
                        continue
                    if isinstance(obj, dict):
                        for sv in obj.values():
                            if isinstance(sv, str) and sv:
                                out.add(sv)
                    continue
                out.add(str(r["v"]))
        return out

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
