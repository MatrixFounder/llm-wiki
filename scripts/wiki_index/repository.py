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
import re
from datetime import datetime
from pathlib import Path
from typing import Literal

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

# TASK 013 (R-X3-META-FILTER): allowlist for frontmatter metadata-filter field
# names. A `wiki-search --where 'field=value'` filter compiles to a parameterized
# `json_extract(frontmatter_json, '$.<field>') = ?` predicate; the field name is
# interpolated into the JSON path, so it MUST be allow-listed to a safe shape
# (the path itself is still passed as a bound parameter — defense in depth, see
# `SQLiteRepository.search_pages`). Lowercase identifier: leading [a-z], then
# [a-z0-9_]. Rejects dots/brackets/quotes/`$`/whitespace → no JSON-path traversal
# or SQL metacharacter can reach the query. The VALUE is never validated here — it
# is always a bound parameter, so any string (incl. `SEV-2`, quotes) is safe.
# NOTE: matched with `re.fullmatch` (NOT `.match` + `$`) — Python's `$` matches
# *before* a single trailing `\n`, so `.match(r"…$")` would let `"status\n"` slip
# the allowlist (vdd-multi critic-security LOW). `fullmatch` requires the WHOLE
# string to match, closing that control-char gap.
_FILTER_FIELD_RE = re.compile(r"[a-z][a-z0-9_]*")


def validate_filter_field(field: str) -> str:
    """Return ``field`` unchanged iff it matches the metadata-filter allowlist
    (a lowercase identifier `[a-z][a-z0-9_]*`, whole-string); otherwise raise
    ``ValueError``.

    Shared by the CLI (`wiki-search --where` parsing, the user-input boundary)
    and re-applied in the DAL (`search_pages`, library-caller defense) per the
    skill-family convention. The ``ValueError`` message names the field only —
    callers MUST NOT echo the filter VALUE into error output (CWE-209/CWE-117).
    """
    if not _FILTER_FIELD_RE.fullmatch(field):
        raise ValueError(f"invalid filter field name: {field!r}")
    return field


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
        query: str | None,
        *,
        vaults: list[str] | None = None,
        types: list[str] | None = None,
        exclude_types: list[str] | None = None,
        project: str | None = None,
        where_fields: list[tuple[str, str]] | None = None,
        limit: int = 20,
    ) -> list[PageHit]:
        """FTS5 + BM25 search, optionally filtered by frontmatter metadata.

        Args:
            query: FTS5 MATCH expression (caller is responsible for escaping
                special FTS operators). May be ``None``/empty **iff**
                ``where_fields`` is non-empty — then a non-FTS metadata-only
                listing is returned (TASK 013). Empty query AND empty
                ``where_fields`` → ``ValueError`` (nothing to search).
            vaults: limit to these vault_ids; None = all registered vaults.
            types: limit to these `pages.type` values; None = all types.
            exclude_types: drop these `pages.type` values **before** the LIMIT
                (TASK 007 — applied in SQL, not post-filtered, so it composes
                correctly with the LIMIT window). None = exclude nothing.
                `wiki-query prepare` passes `['query']` so a RAG retrieval grounds
                on primary sources and a self-indexed answer page can never evict
                a real hit from the top-`limit` window (idempotency).
            project: limit to this project (e.g. '_vault_' or '<course-slug>');
                None = all projects within the selected vaults.
            where_fields: TASK 013 (R-X3-META-FILTER) — frontmatter metadata
                predicates as ``(field, value)`` pairs. Each compiles to a
                parameterized ``CAST(json_extract(p.frontmatter_json, '$.<field>')
                AS TEXT) = ?`` clause; multiple pairs are AND-ed. The ``CAST``
                matches by **string representation**, so a numeric/boolean
                frontmatter value (e.g. ``priority: 1``) matches the string filter
                ``("priority", "1")``. Field names MUST satisfy
                `validate_filter_field` (re-validated here as library-caller
                defense); values are bound parameters (any string is safe,
                incl. hyphenated `SEV-2`). When ``query`` is empty the search
                takes a non-FTS path ordered by ``(project, slug, vault_id)`` —
                the full page identity, so ties are deterministic — with no BM25
                score. None/empty = no metadata filter (today's behaviour).
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
    def check_drift(self, vault_id: str, *, trust_mtime: bool = False) -> DriftReport:
        """Reconcile filesystem ↔ DB; returns drift items per category.
        Applies ADR-002 §6.1 type-mapping (lesson-summary → summary+tag is
        NOT drift). `trust_mtime=True` (the `wiki-lint --mtime-skip` opt-in, TASK
        017 / P-3) skips the re-hash for mtime-unchanged files — integrity-relaxed;
        the default always full-hashes."""
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

    @abc.abstractmethod
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
        """Insert or update an entity row.

        TASK 003 v2 / I-7.7a (R-37). Atomic ``INSERT … ON CONFLICT
        (vault_id, slug) DO UPDATE``. **SQL-level downgrade guard**:
        ``is_candidate = MIN(excluded.is_candidate, entities.is_candidate)``
        — once an entity is confirmed (``is_candidate=0``), incoming
        ``is_candidate=1`` does NOT overwrite. The guard lives at the SQL
        layer (not just Python) so even a misconfigured caller cannot
        demote a confirmed entity.

        ``file_path`` is required by the schema's
        ``UNIQUE(vault_id, file_path)`` constraint; callers pass the
        relative-to-vault-root path of the concept page they just wrote.

        Phase 3a stub `resolve_entity` is the read counterpart (still
        ``NotImplementedError`` until R-4 ships).
        """
        ...

    # =========================================================================
    # Entity resolution — Epic 7 (TASK 005, R-4 + R-5)
    # =========================================================================

    @abc.abstractmethod
    def set_entity_candidate(
        self, vault_id: str, slug: str, is_candidate: int
    ) -> bool:
        """Explicit confirm/undo setter (R-4.2/4.3). **Bypasses** the
        ``upsert_entity`` ``MIN()`` downgrade-guard — operator intent is
        authoritative. Writes the Class B mirror only (the caller writes Class A
        frontmatter first). Returns ``True`` iff the stored value changed
        (``False`` = already in the target state ⇒ idempotent ``changed:false``)."""
        ...

    @abc.abstractmethod
    def list_candidates(self, vault_id: str) -> list[Entity]:
        """All ``is_candidate=1`` entities in the vault (drives ``--auto`` +
        operator review)."""
        ...

    @abc.abstractmethod
    def recompute_mentions(self, vault_id: str) -> None:
        """Set-based ``UPDATE entities.mentions_count = COUNT(page_entity_refs)``
        (R-4.4 freshness; identical query to reindex Step 3)."""
        ...

    @abc.abstractmethod
    def auto_promote_candidates(self, vault_id: str, threshold: int) -> list[str]:
        """Recompute mentions, then promote every candidate with
        ``mentions_count >= threshold`` to confirmed. Returns the promoted
        slugs (R-4.4)."""
        ...

    @abc.abstractmethod
    def preview_promotable(self, vault_id: str, threshold: int) -> list[str]:
        """**Read-only** counterpart of ``auto_promote_candidates`` for
        ``--dry-run`` (R-4.4): candidates whose *freshly-counted* mentions
        ``>= threshold``, computed with a sub-SELECT and **no writes** (the AC
        requires ``--dry-run`` to mutate neither DB nor frontmatter)."""
        ...

    @abc.abstractmethod
    def add_alias(
        self, vault_id: str, alias: str, entity_slug: str,
        alias_type: str = "spelling_variant",
    ) -> None:
        """Register a Class B alias mirror (R-5.1). Idempotent for a same-target
        re-add; raises ``AliasCollisionError`` if the surface already resolves to
        a *different* entity (the hard ``(vault_id, alias)`` PK)."""
        ...

    @abc.abstractmethod
    def remove_alias(self, vault_id: str, alias: str) -> bool:
        """Drop an alias mirror (R-5.2). Returns ``True`` iff a row was removed."""
        ...

    @abc.abstractmethod
    def list_aliases(self, vault_id: str, entity_slug: str) -> list[str]:
        """All alias surfaces registered for an entity (R-5.2)."""
        ...

    @abc.abstractmethod
    def list_all_aliases(self, vault_id: str) -> list[tuple[str, str]]:
        """All ``(alias, entity_slug)`` pairs in the vault, ordered by
        ``(entity_slug, alias)`` (TASK 014 / R-MF14-3 — the vault-wide listing
        surface for ``wiki-alias --list`` with no entity)."""
        ...

    @abc.abstractmethod
    def expand_query_aliases(self, vault_id: str, term: str) -> list[str]:
        """Given a surface term, return the matched entity's canonical name +
        sibling aliases for FTS OR-expansion (R-5.5). Bounded to the matched
        entity's own alias set (no transitive expansion). ``[]`` on no match."""
        ...

    @abc.abstractmethod
    def check_query_state(self, vault_id: str, query_slug: str) -> str | None:
        """TASK 007 / R-6.6 — return the recorded ``question_hash`` for a filed
        query, or ``None`` if absent. Reads ``source_state`` with
        ``source_kind='query'``, ``scope=query_slug``, ``key='question_hash'``.
        Backs ``wiki-query prepare``'s ``is_unchanged`` short-circuit. Defensive
        NULL guard: a corrupt ``value IS NULL`` row → ``None`` (re-synthesise)."""
        ...

    @abc.abstractmethod
    def record_query_state(
        self, vault_id: str, query_slug: str, question_hash: str,
    ) -> None:
        """TASK 007 / R-6.6 — UPSERT the query-idempotency row in
        ``source_state`` (``source_kind='query'``, ``scope=query_slug``,
        ``key='question_hash'``). Called by ``wiki-query apply`` after a
        successful Class A write + self-index. No raw SQL in the skill — this is
        the DAL access path (NFR-2)."""
        ...

    @abc.abstractmethod
    def check_verify_state(self, vault_id: str, verification_slug: str) -> str | None:
        """TASK 008 / R-8.6 — return the recorded ``verify_hash`` for a filed
        verdict, or ``None`` if absent. Reads ``source_state`` with
        ``source_kind='verification'``, ``scope=verification_slug``,
        ``key='verify_hash'``. Backs ``wiki-verify-multi prepare``'s
        ``is_unchanged`` short-circuit. Defensive NULL guard: a corrupt
        ``value IS NULL`` row → ``None`` (re-verify). Sibling of
        ``check_query_state``."""
        ...

    @abc.abstractmethod
    def record_verify_state(
        self, vault_id: str, verification_slug: str, verify_hash: str,
    ) -> None:
        """TASK 008 / R-8.6 — UPSERT the verify-idempotency row in
        ``source_state`` (``source_kind='verification'``,
        ``scope=verification_slug``, ``key='verify_hash'``). Called by
        ``wiki-verify-multi apply`` after a successful Class A write +
        self-index. No raw SQL in the skill (NFR-2). Sibling of
        ``record_query_state``."""
        ...

    @abc.abstractmethod
    def find_alias_collisions(self, vault_id: str) -> list[AliasCollision]:
        """All alias collisions (R-5.6), each tagged by ``AliasCollision.kind``:
        ``in_table`` (legacy/pre-migration), ``cross_slug``/``cross_name`` (alias
        == a *different* entity's slug/name), and ``frontmatter`` (≥2 *entity*
        pages claim the same ``aliases:`` surface). As of TASK 006 / P-10 the
        frontmatter check reads ``pages.frontmatter_json`` here in the DAL (via
        ``json_each``, restricted to entity pages) — it no longer re-parses files
        in the Lint Layer."""
        ...

    @abc.abstractmethod
    def merge_entities(
        self, vault_id: str, from_slug: str, into_slug: str
    ) -> MergeReport:
        """Fold the duplicate ``from`` into the canonical ``into`` in a single
        transaction (R-4.7): re-point ``page_entity_refs`` (PK-dedup, keep higher
        ``trust_level``); re-point ``from``'s aliases to ``into``; register
        ``from``'s slug + name as ``former_name`` aliases of ``into`` (skip+report
        on a third-entity collision); delete the ``from`` entity row; recompute
        ``into.mentions_count``. The caller (``wiki-merge``) performs the Class A
        mutations (append ``into.aliases`` + delete the ``from`` page) **before**
        this call (C-8 write-order)."""
        ...

    @abc.abstractmethod
    def get_entity_file_path(self, vault_id: str, slug: str) -> str | None:
        """The entity's Class A ``file_path`` (relative to vault root), or
        ``None`` if the entity does not exist. The confirm/alias/merge CLIs need
        it to locate the markdown for Class A write-back (skills never run raw
        SQL — this is the DAL read that backs that locate step)."""
        ...

    @abc.abstractmethod
    def find_entity_by_name(self, vault_id: str, name: str) -> str | None:
        """Slug of the entity whose canonical ``name`` exactly equals ``name``,
        or ``None``. Lets ``wiki-alias --add`` refuse a surface that would
        *hijack* another entity's display name (DF-4) — `resolve_entity` only
        catches slug/alias collisions, not name collisions."""
        ...
