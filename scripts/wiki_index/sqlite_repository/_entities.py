"""Entity domain of the SQLite DAL (TASK 056).

Methods relocated verbatim from the pre-056 monolith: upsert_entity,
_row_to_entity, resolve_entity, set_entity_candidate, list_candidates,
_recompute_mentions, recompute_mentions, auto_promote_candidates,
preview_promotable, add_alias, remove_alias, list_aliases, list_all_aliases,
expand_query_aliases.

dialect: generic SQL (CRUD + aggregate over `entities`/`entity_aliases`;
portable to Postgres as-is).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from scripts.wiki_index.models import Entity
from scripts.wiki_index.sqlite_repository._base import (
    AliasCollisionError,
    SQLiteRepositoryBase,
)


class _EntitiesMixin(SQLiteRepositoryBase):
    """Entity write-path (R-37) + resolution/candidates/aliases (TASK 005)."""

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
        definition: str | None = None,
    ) -> None:
        """INSERT or UPDATE entity row; SQL-level downgrade guard.

        ``ON CONFLICT(vault_id, slug) DO UPDATE SET is_candidate =
        MIN(excluded.is_candidate, entities.is_candidate)`` — once an
        entity is confirmed (``is_candidate=0``), incoming ``=1`` does
        NOT overwrite. R-37(b) — see ABC docstring for full rationale.

        ★ R-23 / DF-064-1 — ``definition`` was a schema column
        (``sql/wiki-index-v2.sql`` §2) that NOTHING EVER WROTE. It stayed NULL
        forever, so no SQL query, no ``wiki-lint`` rule and no ``wiki-health``
        check could inspect the one field a concept page exists to carry —
        while ``wiki-search`` retrieved it from FTS and ``wiki-query`` cited it
        as knowledge. (The ``entity_cards`` VIEW already selects
        ``definition AS tldr``: it was serving NULL to every consumer.)

        It is written HERE, and read back from the page body at reindex, so the
        Class-A → Class-B projection round-trips (ADR-002 §D8). **Callers must
        pass the definition EXACTLY as it appears in the page body** — i.e. the
        sanitized text, not the raw candidate — or ``wiki-reindex --full`` will
        not reproduce it and the DB stops being rebuildable.

        ``None`` leaves the column NULL (the `_entities/` external-page path and
        any hand-authored page with no prose).
        """
        conn = self._connect()
        with conn:  # autocommit; rollback on exception
            conn.execute(
                """
                INSERT INTO entities
                    (vault_id, slug, name, type, is_candidate,
                     canonicalized_by, first_seen, last_updated, file_path,
                     definition)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(vault_id, slug) DO UPDATE SET
                    name = excluded.name,
                    type = excluded.type,
                    is_candidate = MIN(excluded.is_candidate, entities.is_candidate),
                    canonicalized_by = excluded.canonicalized_by,
                    last_updated = excluded.last_updated,
                    file_path = excluded.file_path,
                    definition = excluded.definition
                """,
                (vault_id, slug, name, type, is_candidate,
                 canonicalized_by, first_seen, last_updated, file_path,
                 definition),
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
