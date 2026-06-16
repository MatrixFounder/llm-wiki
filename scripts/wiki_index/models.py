"""Typed dataclasses for the wiki-index DAL boundary.

All dataclasses are `frozen=True` — once constructed they are immutable. This
makes them safe to pass between threads and use as dict keys / set members.

Class A/B/C labels (ADR-002 §D8) are documented per-field in docstrings, not
stored on the dataclass itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

# -----------------------------------------------------------------------------
# Type aliases — keep enums in one place, mirror SQLite CHECK constraints.
# -----------------------------------------------------------------------------

PageType = Literal[
    "summary", "concept", "query", "brief", "research", "index", "verification"
]
"""`pages.type` enum (sql/wiki-index-v2.sql §4). Class B mirror of file frontmatter `type:`.
Note: 'log' was removed from enum per architecture-review L-5.
TASK 008 / R-8.9 (schema v5) added 'verification' (wiki-verify-multi verdict page) —
kept in lockstep with the SQL CHECK so a `Page(type='verification')` type-checks."""

TrustLevel = Literal["high", "medium", "low"]
"""Provenance trust level (R-15.3). manual=high, transcript/light=medium."""

BatchMode = Literal["full", "delta"]
"""`batch_runs.mode` — full reindex or mtime-delta incremental."""

BatchStatus = Literal["success", "failure", "partial"]
"""`batch_runs.status` end state."""


# -----------------------------------------------------------------------------
# Vault — registry row (Class B mirror of WIKI_SCHEMA.md::vault_id + root path).
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Vault:
    """One row in `vaults` registry.

    Fields are Class B (mirror of file state) except `registered_at` which is
    Class C strict (DB-only, approximated from MIN(log_events.event_ts) on
    reindex per ADR-002 §D8).
    """

    vault_id: str
    """Stable kebab-case identity from <vault>/WIKI_SCHEMA.md::vault_id.
    REQUIRED (ADR-002 §D1.1). Format: ^[a-z][a-z0-9-]{1,30}[a-z0-9]$ + no
    double hyphens + length 3-32, OR the sentinel '_global_'."""

    name: str
    """Human-readable name from WIKI_SCHEMA.md."""

    root_path: Path
    """Absolute filesystem path. For '_global_' sentinel = Path('/dev/null')."""

    schema_version: str
    """WIKI_SCHEMA.md::schema_version (e.g. '2.0')."""

    registered_at: datetime
    """First-seen timestamp. Class C strict — only DB-only value in the schema.
    Approximated from earliest log_events.event_ts on full reindex."""

    config_json: dict[str, Any] | None = None
    """Snapshot of CLAUDE.md::wiki: + .wiki.yaml merged config. Class B."""

    notes: str | None = None
    """Free-text annotation; not derived from file state."""


# -----------------------------------------------------------------------------
# Page — wiki page (source / concept / query). Mirror of <vault>/_*/<slug>.md.
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Page:
    """One row in `pages`. Class B mirror of a vault markdown file.

    `id` (SQLite AUTOINCREMENT primary key) lives on the DB side only — not
    exposed at the DAL boundary; callers use (vault_id, slug, project) as the
    composite identity.
    """

    vault_id: str
    slug: str
    project: str
    """'_vault_' for vault-root tier, '<course-slug>' for course-local (per
    promotion-spec)."""

    type: PageType
    title: str
    file_path: str
    """Relative to vault root, e.g. '_sources/foo.md' or 'Lessons/X/_concepts/Bar.md'."""

    date: date | None
    """ISO date from frontmatter (None if absent)."""

    last_modified: datetime
    """File mtime, ISO-8601."""

    file_hash: str
    """sha256(body) — used by reindex --delta change detection."""

    frontmatter_json: dict[str, Any]
    """Full frontmatter as a Python dict (sourced from `python-frontmatter` parse)."""

    body_excerpt: str
    """The FULL normalized body (R-07.5: mermaid + SECTION anchors stripped) —
    the FTS search corpus indexed in `pages_fts` (TASK 024 / Q-024-2; was capped
    at the first 1000 chars, which made deeper terms unsearchable). Despite the
    name it is NOT a display field: search results render `snippet(pages_fts, …)`,
    a bounded match window — no consumer renders this column raw."""

    tags: list[str]
    """Denormalized from `frontmatter_json['tags']` for ergonomics. The JSON
    field is the source of truth."""

    tldr: str | None = None
    """One-line summary for index render. Optional."""

    is_frozen: bool = False
    """If True, ingest/upsert refuses to modify this page (operator override)."""


# -----------------------------------------------------------------------------
# Entity — canonical entity (concept, person, company, ...).
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Entity:
    """One row in `entities`. Class B mirror of <vault>/_concepts/<slug>.md or
    <vault>/_entities/<slug>.md frontmatter.
    """

    vault_id: str
    slug: str
    type: str
    """One of 'concept', 'person', 'company', 'product', 'group', 'event',
    'work', 'external' (sql/wiki-index-v2.sql §2 CHECK enum)."""

    name: str
    aliases: list[str]
    """From entity_aliases table. Empty list if no aliases."""

    description: str | None = None
    """Canonical 1-3 sentence definition (from frontmatter or body H1)."""

    is_external: bool = False
    """True for entities outside the vault scope (e.g. external companies
    referenced by name only). is_candidate stays in DB; not surfaced here."""


# -----------------------------------------------------------------------------
# PageHit — search result row (page + ranking info + snippet).
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class PageHit:
    """One row in a search_pages() result."""

    page: Page
    bm25_score: float
    """SQLite FTS5 bm25() score. Lower = better match (SQLite convention)."""

    snippet: str
    """HTML-highlighted excerpt from snippet() FTS function."""

    via_edge: dict[str, str] | None = None
    """TASK 032 / R-032-6 (ADR-004 D5): set on a hit pulled into the retrieval set by
    `wiki-query --follow-edges` graph expansion (NOT a direct FTS match) —
    ``{"from": <source-slug>, "ref_type": <edge>}``. ``None`` for FTS hits."""


# -----------------------------------------------------------------------------
# PageRef — provenance v1.1 row in page_entity_refs.
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class PageRef:
    """One row in `page_entity_refs`. Class B (derived from body wiki-link + footnote parse)."""

    vault_id: str
    page_slug: str
    page_project: str
    entity_slug: str
    ref_type: str
    """One of 'mentioned', 'defined-here', 'related', 'cited', 'verifies', plus the
    TASK 032 / R-032-1 (schema v6) event-graph typed edges 'implements',
    'implemented-by', 'supersedes', 'superseded-by', 'causes', 'caused-by', plus the
    TASK 034 / R-2 (schema v7) edges 'invalidated-by', 'invalidates', 'activated-by',
    'activates', 'uses', 'used-by', 'owns', 'owned-by'
    (sql/wiki-index-v2.sql §5 CHECK enum; 'verifies' added TASK 008 / R-8.9 — the
    verdict→query edge; the v6/v7 edges are inverse-closed [ADR-004 D1] — `relates_to`
    reuses the symmetric 'related'; forward authored, inverse auto-derived. The v7
    'invalidated-by'/'superseded-by' edges are read by the `wiki-search --as-of`
    temporal valid_to walk)."""

    trust_level: TrustLevel = "medium"
    line_start: int | None = None
    line_end: int | None = None
    source_quote: str | None = None
    """10-50 word verbatim from the page body. NULL if not capturable
    (e.g. transcript adapter without line tracking)."""


# -----------------------------------------------------------------------------
# LogEvent — structured mirror of one block in log.md (R-28).
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class LogEvent:
    """One row in `log_events`. Bi-directional sync with log.md (ADR-002 §D2).

    `log_md_byte_offset` enables round-trip: given a DB row, the caller can
    seek into the file and read the original Markdown block.
    """

    vault_id: str
    event_ts: datetime
    event_type: str
    """One of 'ingest', 'query', 'lint', 'reindex', 'promote', 'demote',
    'backfill', 'reclassify', 'resolve-contradiction', 'fix-dangling',
    'fix-orphan', 'verify' (sql/wiki-index-v2.sql §6 CHECK enum; 'verify'
    added TASK 008 / R-8.9 — the wiki-verify-multi audit event)."""

    pages_created_json: list[str]
    """List of page slugs that this event created. JSON-serialized on disk."""

    pages_updated_json: list[str]
    """List of page slugs this event touched (excluding `pages_created_json`)."""

    details_json: dict[str, Any]
    """Extensible event-type-specific payload."""

    id: int | None = None
    """AUTOINCREMENT PK. None when constructing a new event before INSERT."""

    subject: str | None = None
    """Brief title for the event (e.g. source title for ingest)."""

    log_md_path: str | None = None
    """Path to the log.md file (per-course in multi-course vaults). Relative
    to vault root."""

    log_md_byte_offset: int | None = None
    """Byte offset of the block start in log.md. None for events not yet
    written to disk (will be filled in by wiki-append-log atomic write)."""


# -----------------------------------------------------------------------------
# OrphanLink — wiki-lint output for an unresolved [[link]].
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class OrphanLink:
    """A wiki-link in a page that does not resolve to any indexed entity/page.
    Surfaced by find_orphan_links() (R-11)."""

    vault_id: str
    source_page_slug: str
    source_page_project: str
    target_slug: str
    """The [[link]] target as written in the source body."""

    line_start: int | None = None
    source_quote: str | None = None


# -----------------------------------------------------------------------------
# BatchRun — reindex operation log row.
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class BatchRun:
    """One row in `batch_runs`. Class C (forensic operational log;
    status/errors_json cannot be reconstructed from filesystem)."""

    vault_id: str
    mode: BatchMode
    started_at: datetime
    id: int | None = None
    finished_at: datetime | None = None
    status: BatchStatus | None = None
    """None while batch is still 'running'. Set on finish_batch_run()."""
    notes: str | None = None


# -----------------------------------------------------------------------------
# DriftReport — lint output for filesystem ↔ DB inconsistencies (R-11.1).
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class DriftReport:
    """Output of check_drift(). Each list is empty if no issues of that kind.

    `type_mismatch` accounts for §6.1 type-mapping rule from ADR-002 — file
    `type: lesson-summary` mapped to DB `type='summary'` + tag is NOT drift;
    only unmapped divergences appear here.
    """

    missing_in_db: list[Path]
    """Files exist on disk but no `pages`/`entities` row. (slug, project)
    not yet upserted."""

    missing_on_disk: list[tuple[str, str]]
    """DB row exists but file deleted. Tuples are (slug, project)."""

    hash_mismatch: list[tuple[str, str]]
    """pages.file_hash != sha256(current file body). (slug, project) pairs."""

    type_mismatch: list[tuple[str, str, str, str]]
    """File frontmatter `type:` doesn't match `pages.type` after §6.1 mapping.
    Tuple: (slug, project, file_frontmatter_type, db_type)."""


# -----------------------------------------------------------------------------
# AliasCollision — one wiki-lint alias-collision finding (TASK 005, R-5.6).
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class AliasCollision:
    """One alias-collision finding from `find_alias_collisions` / the lint scan.

    `kind`:
      - 'in_table'    — the same alias maps to >1 entity_slug in the DB
        (only reachable on a legacy / pre-v3-migration DB; the v3 PK
        `(vault_id, alias)` prevents new ones).
      - 'cross_slug'  — an alias string equals a *different* entity's `slug`.
      - 'cross_name'  — an alias string equals a *different* entity's `name`.
      - 'frontmatter' — two entity-page `aliases:` frontmatter blocks claim the
        same surface (file-layer; produced by the Lint Layer, not the DAL).
    """

    vault_id: str
    alias: str
    slugs: list[str]
    """The conflicting entity slugs (sorted)."""
    kind: str


# -----------------------------------------------------------------------------
# MergeReport — result of merge_entities (TASK 005, R-4.7).
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class MergeReport:
    """Summary of a `merge_entities(from, into)` duplicate-fold."""

    refs_repointed: int
    aliases_absorbed: int
    aliases_skipped: list[str]
    """Surfaces that could not be registered as `into` aliases because they
    already resolve to a *third* entity (reported, never silently dropped)."""


# -----------------------------------------------------------------------------
# Derived knowledge health — TASK 036 (R-15): lifecycle-drift + coverage.
# Read-only DAL boundary types (zero DDL — computed over pages.frontmatter_json
# + page_entity_refs). Rules are layout grammar (parsed by layout_config); hits
# are the DAL results. Defined here so layout_config / repository / sqlite_repository
# share ONE definition with no import cycle (models imports nothing internal).
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class DriftRule:
    """One lifecycle-drift rule (Slice A1): a page of class ``page_class`` that
    carries the typed edge ``edge`` (a STORED ref_type where
    ``page_entity_refs.page_slug`` IS the page — i.e. the auto-derived inverse such
    as ``superseded-by``/``invalidated-by``) but whose AUTHORED ``status``
    frontmatter contradicts that graph state is DRIFT. Exactly one of
    ``expect_status`` / ``forbid_status`` is set (enforced by the layout-config
    schema ``oneOf`` + a load-time check in ``layout_config``):

      - ``expect_status`` — drift when the page's status is PRESENT and != this
        value (a NULL/absent status is NEVER drift — only an explicit contradiction).
      - ``forbid_status`` — drift when the page's status is one of these values.

    Authored as built-in ``layouts/*.yaml`` ``drift_rules`` (cybos only); an operator
    override may supply its own. Grammar over existing data; derived, never stored."""

    page_class: str
    edge: str
    expect_status: str | None = None
    forbid_status: tuple[str, ...] = ()


@dataclass(frozen=True)
class CoverageRule:
    """One coverage-gap rule (Slice A2): a page of class ``page_class`` MISSING an
    expected relation. Exactly one of ``requires_edge`` / ``requires_field`` is set:

      - ``requires_edge`` — gap when the page has NO typed edge of this ref_type
        (e.g. a ``requirement`` with no ``implemented-by`` = nothing implements it).
      - ``requires_field`` — gap when the page's frontmatter scalar ``$.<field>`` is
        absent OR empty (e.g. a ``fact`` with an empty ``source:``). The field name
        is allow-listed (``validate_filter_field``)."""

    page_class: str
    requires_edge: str | None = None
    requires_field: str | None = None


@dataclass(frozen=True)
class DriftHit:
    """One lifecycle-drift finding (Slice A1): the page's AUTHORED ``status``
    contradicts its graph state (it carries ``edge``)."""

    vault_id: str
    page_slug: str
    page_project: str
    page_class: str
    edge: str
    status: str | None
    expected: str
    """Human-readable description of the non-drift state (e.g. ``status == superseded``
    or ``status not in {proposed, accepted}``)."""


@dataclass(frozen=True)
class CoverageGap:
    """One coverage-gap finding (Slice A2): a page missing an expected relation —
    an edge of ref_type ``detail`` when ``kind == 'edge'``, or a non-empty
    frontmatter field ``detail`` when ``kind == 'field'``."""

    vault_id: str
    page_slug: str
    page_project: str
    page_class: str
    kind: str
    detail: str
