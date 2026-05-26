"""Abstract DAL contract for wiki-index.

`IndexRepository` is an `abc.ABC` — direct instantiation raises `TypeError`.
Concrete backends (`SQLiteRepository`, future `PostgresRepository`) inherit
and implement every abstract method. See `docs/PLAN.md` Phase 3a for the
SQLite impl task chain (001-04 stub → 001-15..20 impl).

Class A/B/C contract (ADR-002 §D8): this layer owns the DB-side cache.
All writes are Class B (rebuildable from markdown via `wiki-reindex --full`)
except `vaults.registered_at` (Class C strict).

Upsert contract (M-4): `upsert_page` MUST use
`INSERT … ON CONFLICT(vault_id, slug, project) DO UPDATE SET …` in the
SQLite impl. `INSERT OR REPLACE` is FORBIDDEN — it generates a new pages.id,
breaks FTS5 rowid stability, and CASCADE-deletes page_entity_refs.
"""

from __future__ import annotations

import abc
from datetime import datetime
from pathlib import Path
from typing import Literal

from scripts.wiki_index.models import (
    BatchMode,
    BatchRun,
    DriftReport,
    Entity,
    LogEvent,
    OrphanLink,
    Page,
    PageHit,
    PageRef,
    Vault,
)


class IndexRepository(abc.ABC):
    """Abstract repository for the multi-vault SQLite index.

    All read/write to the DB goes through this interface. Skills never
    construct raw SQL — they call repository methods. This boundary is what
    lets us swap SQLite for Postgres (Epic 8) without touching skill code.
    """

    # =========================================================================
    # Vault registry (R-27 multi-vault partitioning)
    # =========================================================================

    @abc.abstractmethod
    def register_vault(self, vault: Vault) -> None:
        """INSERT OR FAIL into `vaults`. Raises if vault_id already registered."""
        ...

    @abc.abstractmethod
    def get_vault(self, vault_id: str) -> Vault | None:
        """Fetch by primary key. None if not registered."""
        ...

    @abc.abstractmethod
    def list_vaults(self) -> list[Vault]:
        """All registered vaults (excluding the `_global_` sentinel by default
        in the SQLite impl)."""
        ...

    @abc.abstractmethod
    def rename_vault(self, old_vault_id: str, new_vault_id: str) -> None:
        """UPDATE vaults SET vault_id=? WHERE vault_id=?. CASCADE propagates
        to pages/entities/page_entity_refs/source_state/batch_runs/log_events.
        See ADR-002 §D8 reconciliation flow."""
        ...

    @abc.abstractmethod
    def get_vault_by_root_path(self, root_path: Path) -> Vault | None:
        """Lookup by root_path (UNIQUE indexed). Used by wiki-init reconcile
        to detect VAULT_RENAMED case per ADR-002 §D8."""
        ...

    def close(self) -> None:
        """Close underlying resources (connection, locks). Default no-op for
        backends without connection state; SQLite override closes the lazy
        Connection. Idempotent."""
        return None

    # =========================================================================
    # Pages CRUD (R-04 DAL, R-07 wiki-index-upsert)
    # =========================================================================

    @abc.abstractmethod
    def upsert_page(self, page: Page) -> Literal["inserted", "updated", "unchanged"]:
        """Insert-or-update via ON CONFLICT DO UPDATE (M-4 contract).

        Returns:
            'inserted' — new (vault_id, slug, project) tuple created.
            'updated' — existing row's file_hash differed, page was rewritten.
            'unchanged' — existing row's file_hash matched; no DB write
                (FTS5 trigger does not fire).
        """
        ...

    @abc.abstractmethod
    def get_page(self, vault_id: str, slug: str, project: str) -> Page | None:
        """Fetch page by composite identity. None if not present."""
        ...

    @abc.abstractmethod
    def delete_page(self, vault_id: str, slug: str, project: str) -> None:
        """DELETE FROM pages WHERE vault_id=? AND slug=? AND project=?.
        CASCADE deletes page_entity_refs entries."""
        ...

    # =========================================================================
    # Search (R-10 wiki-search, R-29 cross-vault filter)
    # =========================================================================

    @abc.abstractmethod
    def search_pages(
        self,
        query: str,
        *,
        vaults: list[str] | None = None,
        types: list[str] | None = None,
        project: str | None = None,
        limit: int = 20,
    ) -> list[PageHit]:
        """FTS5 + BM25 search.

        Args:
            query: FTS5 MATCH expression (caller is responsible for escaping
                special FTS operators).
            vaults: limit to these vault_ids; None = all registered vaults.
            types: limit to these `pages.type` values; None = all types.
            project: limit to this project (e.g. '_vault_' or '<course-slug>');
                None = all projects within the selected vaults.
            limit: max hits to return.
        """
        ...

    # =========================================================================
    # Refs (R-07 page_entity_refs)
    # =========================================================================

    @abc.abstractmethod
    def upsert_refs(self, refs: list[PageRef]) -> None:
        """Insert-or-update each row in `refs` via ON CONFLICT DO UPDATE.
        Does NOT delete existing refs not in the list. See `replace_refs` for
        full-rewrite semantics."""
        ...

    @abc.abstractmethod
    def replace_refs(
        self,
        vault_id: str,
        page_slug: str,
        page_project: str,
        refs: list[PageRef],
    ) -> None:
        """DELETE all existing refs for the given page, then INSERT `refs`.
        Atomic in a single transaction. Used by upsert_page when refs change."""
        ...

    @abc.abstractmethod
    def get_backlinks(self, vault_id: str, entity_slug: str) -> list[PageRef]:
        """All refs where `entity_slug=?` — i.e. pages that mention this
        entity. Karpathy 'cross-references as documents'."""
        ...

    # =========================================================================
    # Lint (R-11 wiki-lint, R-29 cross-vault duplicates)
    # =========================================================================

    @abc.abstractmethod
    def find_orphan_links(self, vault_id: str | None = None) -> list[OrphanLink]:
        """[[link]] targets that don't resolve to any indexed page or entity.
        None vault_id = all vaults."""
        ...

    @abc.abstractmethod
    def find_pages_missing_in_index(self, vault_id: str, vault_root: Path) -> list[Path]:
        """Walk filesystem; return files present on disk but not in `pages`.
        Used by `wiki-reindex --delta`."""
        ...

    @abc.abstractmethod
    def check_drift(self, vault_id: str) -> DriftReport:
        """Reconcile filesystem ↔ DB; returns drift items per category.
        Applies ADR-002 §6.1 type-mapping (lesson-summary → summary+tag is
        NOT drift)."""
        ...

    @abc.abstractmethod
    def find_cross_vault_concept_duplicates(self) -> list[tuple[str, list[str]]]:
        """Concepts (by slug) that appear in ≥ 2 vaults. R-29.

        Returns:
            List of (concept_slug, [vault_id, ...]) tuples where len(vault_ids) ≥ 2.
            Sorted by len descending then alphabetically.
        """
        ...

    # =========================================================================
    # Log events (R-28 structured log.md mirror)
    # =========================================================================

    @abc.abstractmethod
    def append_log_event(self, event: LogEvent) -> int:
        """INSERT into log_events; return autoincrement id.

        Caller is responsible for filling `log_md_byte_offset` afterwards via
        `update_log_event_offset` once the markdown line has been appended to
        log.md (bi-directional sync per ADR-002 §D2 + N-3 fix)."""
        ...

    @abc.abstractmethod
    def update_log_event_offset(self, event_id: int, byte_offset: int) -> None:
        """Set `log_events.log_md_byte_offset = ?` for the given event row.
        Called by wiki-append-log after the atomic file append (N-3 fix from
        plan review — replaces private `_connect()` access)."""
        ...

    @abc.abstractmethod
    def query_log_events(
        self,
        vault_id: str,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        event_types: list[str] | None = None,
    ) -> list[LogEvent]:
        """Slice log_events by date range and event type. Ordered by event_ts."""
        ...

    # =========================================================================
    # Batch runs (reindex operation tracking)
    # =========================================================================

    @abc.abstractmethod
    def begin_batch_run(self, vault_id: str, mode: BatchMode) -> int:
        """INSERT a 'running' batch row; return autoincrement id."""
        ...

    @abc.abstractmethod
    def finish_batch_run(
        self, run_id: int, status: str, notes: str | None = None
    ) -> None:
        """UPDATE the batch row with finished_at + status + notes."""
        ...

    @abc.abstractmethod
    def last_batch_run(self, vault_id: str) -> BatchRun | None:
        """Most recent (by started_at) batch row for this vault. None if no
        batches yet."""
        ...

    # =========================================================================
    # Entity resolution — Epic 7 stub
    # =========================================================================

    def resolve_entity(self, vault_id: str, slug: str) -> Entity | None:
        """Two-tier confirmed/candidate canonicalization. Epic 7 work; the
        default impl raises NotImplementedError so concrete repository
        subclasses inherit the stub without needing to override.

        Phase 3a code MUST NOT call this method.
        """
        raise NotImplementedError("entity resolution arrives in Epic 7")
