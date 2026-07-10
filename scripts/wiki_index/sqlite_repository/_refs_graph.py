"""Refs + typed-edge-graph domain of the SQLite DAL (TASK 056).

Methods relocated verbatim from the pre-056 monolith: upsert_refs,
_replace_refs_in_txn, replace_refs, _ref_from_row, get_backlinks,
concept_pages, mentioning_source_pages, refs_from, neighbors, edge_chain.

dialect: generic SQL (self-joins over `page_entity_refs`; the bounded
edge_chain walk is Python-side BFS, not a recursive CTE — portable as-is).
"""

from __future__ import annotations

import sqlite3
from collections import deque
from typing import Any

from scripts.wiki_index.models import PageRef
from scripts.wiki_index.sqlite_repository._base import SQLiteRepositoryBase


class _RefsGraphMixin(SQLiteRepositoryBase):
    """page_entity_refs CRUD + backlinks + typed-edge traversal (ADR-004)."""

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

