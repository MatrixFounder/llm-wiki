"""wiki-reindex --full impl — ADR-002 §D8 Class A → B reconstruction (task-001-30)."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import replace
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

from scripts.wiki_index.layout import (
    CONCEPTS_SUBDIR,
    ENTITIES_SUBDIR,
    LOG_SUBDIR,
    VAULT_INDEX_DIR,
)
from scripts.wiki_index.layout_config import (
    DiscoveredPage,
    LayoutConfig,
    RefRule,
    _apply_slug_strategy,
    derive_discovered_page,
    iter_pages,
    resolve_layout_config,
)
from scripts.wiki_index.logfile import parse_log_md
from scripts.wiki_index.models import Entity, LogEvent, Page, PageRef
from scripts.wiki_index.normalization import (
    BodyNormalizationError,
    UnmappedTypeError,
    normalize_body_for_fts,
    normalize_frontmatter,
)
from scripts.wiki_index.security import (
    PathTraversalError,
    assert_no_symlink_escape,
)
from scripts.wiki_source.base import SourceItem
from scripts.wiki_source.manual import ManualSourceAdapter
from scripts.wiki_source.parsing import extract_refs, first_h1

if TYPE_CHECKING:
    from scripts.wiki_index.repository import IndexRepository

_LOG = logging.getLogger("wiki_index.reindex")

# TASK 030 (R-030-2b, P-1): chunked-commit bounds for the `reindex_full`
# stage-then-flush loop. A chunk FLUSHES (one `BEGIN IMMEDIATE` … `COMMIT` of
# DML only) when EITHER bound fills: K pages, or the staged full-body payload
# (approximated as `len(page.body_excerpt)` chars) crosses the byte cap —
# full-body pages since TASK 024 make an unbounded buffer a real memory risk.
REINDEX_TX_CHUNK = 500
REINDEX_TX_CHUNK_BYTES = 32 * 1024 * 1024


def _detect_slug_collision(
    seen: dict[tuple[str, str], str], slug: str, project: str, rel: str,
    collisions: list[dict[str, Any]],
) -> None:
    """TASK 020 — surface a silent `(vault_id, slug, project)` PK collision (two
    distinct files resolving to the same DB identity → the later `upsert_page`
    overwrites the earlier row with NO signal). Call AFTER a successful
    `upsert_page`: if this `(slug, project)` was already written this run by a
    DIFFERENT file, record `{slug, project, kept, dropped}` (kept = the later
    POSIX-sorted file now in the DB; dropped = the earlier clobbered one) + WARN.
    Detection-only — the operator disambiguates via a per-folder `project`/
    `project_pattern`; we never auto-resolve."""
    key = (slug, project)
    prior = seen.get(key)
    if prior is not None and prior != rel:
        collisions.append({"slug": slug, "project": project,
                           "kept": rel, "dropped": prior})
        _LOG.warning(
            "[reindex] slug collision: %r and %r both resolve to "
            "(slug=%s, project=%s) — the later overwrote the earlier in the index "
            "(no row lost-count signal otherwise). Disambiguate via a per-folder "
            "project / project_pattern in .wiki/layout.yaml.",
            prior, rel, slug, project,
        )
    seen[key] = rel


def _coerce_is_candidate(fm: dict[str, Any]) -> int:
    """Map an entity-page frontmatter ``is_candidate`` value → the DB column.

    TASK 005 / R-4.1: ``is_candidate`` is **Class A canonical** (entity-page
    frontmatter, written by ``write_concept_page``). ``reindex_full`` previously
    omitted the column from its ``INSERT OR IGNORE`` → it defaulted to the schema
    ``0`` (confirmed), silently confirming every candidate on a full rebuild.
    This reads the flag back so a candidate survives ``wiki-reindex --full``.

    Truthy (``True`` / ``"true"`` / ``1`` / ``"yes"`` / ``"on"``) → ``1``
    (candidate); missing or falsey → ``0`` (confirmed) — the latter keeps
    back-compat with pre-TASK-005 vaults that have no ``is_candidate`` key.
    """
    val = fm.get("is_candidate")
    if isinstance(val, bool):
        return 1 if val else 0
    if isinstance(val, int):
        return 1 if val else 0
    if isinstance(val, str):
        return 1 if val.strip().lower() in ("true", "1", "yes", "on") else 0
    return 0


def discover_pages(vault_root: Path) -> list[tuple[Path, str, str]]:
    """Config-driven page discovery (TASK 012 / PW-B). Resolves the vault's layout
    grammar (`resolve_layout_config` — defaults to karpathy when no `WIKI_SCHEMA.md`)
    and walks it via `iter_pages`, replacing the former hardcoded two-tier walk.
    Yields `(path, slug, project)` tuples, stably sorted by vault-relative path.

    The built-in `karpathy.yaml` reproduces the previous behaviour byte-for-byte
    (root-tier `PAGE_SUBDIRS` → `_vault_`; `Lessons/<Course>/` → slugified course);
    the golden anchor `tests/test_karpathy_byte_identity.py` guards the invariant.
    """
    config = resolve_layout_config(vault_root)
    return [(d.path, d.slug, d.project) for d in iter_pages(vault_root, config)]


def _cited_refs(
    updated_fm: dict[str, Any], vault_id: str, page_slug: str,
    page_project: str, skipped: list[dict[str, Any]],
) -> list[PageRef]:
    """Parse a ``cites:`` frontmatter list into ``ref_type='cited'`` ``PageRef``s
    (TASK 007 / R-6.5e). Each entry is a ``"<project>/<slug>"`` string; only the
    **slug** is persisted as ``entity_slug`` (the project is parsed for shape
    validation only, so the reindex-rebuilt row and the apply-written row are
    byte-identical). ``line_start``/``line_end``/``source_quote`` are ``None``;
    ``trust_level='medium'``. Malformed/empty entries are recorded in ``skipped``
    (report-and-skip — never silent-drop, never raise; ``reason`` never echoes
    the offending value, CWE-117/209). De-dups on ``entity_slug``.
    """
    raw = updated_fm.get("cites")
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    refs: list[PageRef] = []
    for entry in raw:
        if not isinstance(entry, str) or "/" not in entry:
            skipped.append({
                "page_slug": page_slug,
                "reason": "malformed cites entry (expected 'project/slug' string)",
            })
            continue
        proj, _, cslug = entry.rpartition("/")
        cslug = cslug.strip()
        if not proj.strip() or not cslug:
            skipped.append({
                "page_slug": page_slug,
                "reason": "malformed cites entry (empty project or slug)",
            })
            continue
        if cslug in seen:
            continue
        seen.add(cslug)
        refs.append(PageRef(
            vault_id=vault_id, page_slug=page_slug, page_project=page_project,
            entity_slug=cslug, ref_type="cited", trust_level="medium",
        ))
    return refs


def _verifies_ref(
    updated_fm: dict[str, Any], vault_id: str, page_slug: str,
    page_project: str, skipped: list[dict[str, Any]],
) -> list[PageRef]:
    """Parse a ``type=verification`` page's ``verifies:`` frontmatter — a single
    ``"<project>/<slug>"`` string naming the audited query page — into one
    ``ref_type='verifies'`` ``PageRef`` (TASK 008 / R-8.5e, the verdict→query
    edge). Only the slug is persisted as ``entity_slug`` (project parsed for
    shape-validation only, byte-identical to the ``wiki-verify-multi apply``-
    written row); ``trust_level='medium'``, line/quote ``None``. A
    missing/blank/malformed ``verifies:`` is recorded in ``skipped`` (a verdict
    page should always carry one — ``apply`` writes it; report-and-skip, never
    raise; ``reason`` never echoes the value) and ``[]`` is returned.
    """
    raw = updated_fm.get("verifies")
    if isinstance(raw, str) and "/" in raw:
        proj, _, vslug = raw.rpartition("/")
        vslug = vslug.strip()
        if proj.strip() and vslug:
            return [PageRef(
                vault_id=vault_id, page_slug=page_slug, page_project=page_project,
                entity_slug=vslug, ref_type="verifies", trust_level="medium",
            )]
    skipped.append({
        "page_slug": page_slug,
        "reason": "missing or malformed verifies entry (expected 'project/slug' string)",
    })
    return []


# TASK 032 / R-032-1/2 (ADR-004 D2) — event-graph forward edge keys → ref_type.
# Each frontmatter KEY (underscore) maps to its ref_type ENUM value (hyphen). Each
# member is both authorable AND derivable (the inverse rows are auto-derived by the
# global pass in reindex_full — 032-02). `relates_to` reuses the symmetric `related`
# (NO parallel 'relates-to'). Keep in sync with the v6 CHECK enum (sql §5).
_EDGE_KEY_TO_REF_TYPE: dict[str, str] = {
    "implements": "implements",
    "implemented_by": "implemented-by",
    "supersedes": "supersedes",
    "superseded_by": "superseded-by",
    "causes": "causes",
    "caused_by": "caused-by",
    "relates_to": "related",
    # TASK 034 / R-2 (ADR-004 ext, schema v7) — temporal + agent-memory edges.
    # Both authorable directions (TASK 032 parity); the inverse is auto-derived.
    # `invalidated-by`/`activated-by` carry RFC-001 temporal causality — the
    # `wiki-search --as-of` valid_to walk reads `invalidated-by` ∥ `superseded-by`;
    # `uses`/`owns` carry RFC-002 agent↔tool/workflow relations.
    "invalidated_by": "invalidated-by",
    "invalidates": "invalidates",
    "activated_by": "activated-by",
    "activates": "activates",
    "uses": "uses",
    "used_by": "used-by",
    "owns": "owns",
    "owned_by": "owned-by",
}


def _strip_wikilink(v: str) -> str:
    """`[[Target]]` / `[[Target|alias]]` → `Target`; a bare slug passes through."""
    s = v.strip()
    if s.startswith("[[") and s.endswith("]]"):
        return s[2:-2].split("|", 1)[0].strip()
    return s


def _edge_refs(
    updated_fm: dict[str, Any], vault_id: str, page_slug: str,
    page_project: str, slug_strategy: str, skipped: list[dict[str, Any]],
) -> list[PageRef]:
    """Parse the TASK 032 event-graph edge keys (`implements`/`supersedes`/`caused_by`/
    `relates_to` + the directly-authorable inverses) into **FORWARD** ``PageRef``s
    (ADR-004 D2/D3). Each key → its ref_type via ``_EDGE_KEY_TO_REF_TYPE``; the value is
    a ``[[wikilink]]`` / bare slug or a LIST of them; the target is slugified via the
    layout ``slug_strategy`` (same as body ``'mentioned'`` refs — AM-3 later
    canonicalizes through the alias map, ``ref_type`` preserved). De-dups on
    ``(entity_slug, ref_type)``; skips self-loops; report-and-skip malformed (no value
    echo, CWE-117). FORWARD only — these ride the SOURCE page's single ``replace_refs``
    (M-1 intact); the inverse rows are derived by the global pass in ``reindex_full``."""
    refs: list[PageRef] = []
    seen: set[tuple[str, str]] = set()
    for key, ref_type in _EDGE_KEY_TO_REF_TYPE.items():
        raw = updated_fm.get(key)
        if raw is None:
            continue
        # YAML quirk: an unquoted Obsidian `[[wikilink]]` parses as a NESTED list
        # `[["x"]]` (not a string), while a list of bare slugs parses as `["x","y"]`.
        # Flatten ONE level so both the natural `[[x]]` form and the `[x, y]` form
        # (and a plain scalar) resolve identically.
        candidates: list[Any] = raw if isinstance(raw, list) else [raw]
        values: list[Any] = []
        for c in candidates:
            values.extend(c if isinstance(c, list) else [c])
        for v in values:
            if not isinstance(v, str):
                skipped.append({"page_slug": page_slug,
                                "reason": f"malformed {key} edge (expected string / [[wikilink]])"})
                continue
            target = _strip_wikilink(v)
            if not target:
                skipped.append({"page_slug": page_slug,
                                "reason": f"empty {key} edge target"})
                continue
            eslug = _apply_slug_strategy(target, slug_strategy)
            if not eslug:  # slugified to empty (e.g. all-punctuation target)
                skipped.append({"page_slug": page_slug,
                                "reason": f"{key} edge target slugified to empty"})
                continue
            if eslug == page_slug:  # vdd-multi LOW: surface the self-loop drop
                skipped.append({"page_slug": page_slug,
                                "reason": f"self-referential {key} edge target ignored"})
                continue
            dedup = (eslug, ref_type)
            if dedup in seen:
                continue
            seen.add(dedup)
            refs.append(PageRef(
                vault_id=vault_id, page_slug=page_slug, page_project=page_project,
                entity_slug=eslug, ref_type=ref_type, trust_level="medium",
            ))
    return refs


# TASK 032 (ADR-004 D3) — forward ref_type → its inverse. The symmetric `related`
# maps to itself. ONLY these typed edges get auto-inverse derivation;
# mentioned/cited/verifies/defined-here do NOT. Keep in sync with the v6 CHECK enum.
_INVERSE_REF_TYPE: dict[str, str] = {
    "implements": "implemented-by",
    "implemented-by": "implements",
    "supersedes": "superseded-by",
    "superseded-by": "supersedes",
    "causes": "caused-by",
    "caused-by": "causes",
    "related": "related",
    # TASK 034 / R-2 (schema v7) — four new inverse-closed pairs.
    "invalidated-by": "invalidates",
    "invalidates": "invalidated-by",
    "activated-by": "activates",
    "activates": "activated-by",
    "uses": "used-by",
    "used-by": "uses",
    "owns": "owned-by",
    "owned-by": "owns",
}


def _derive_inverse_edges(
    conn: "sqlite3.Connection", vault_id: str,
    source_slugs: set[str] | None = None,
) -> None:
    """TASK 032 / R-032-3 (ADR-004 D3) — the inverse-edge derivation pass. For every
    edge row ``(A→B, fwd)`` whose target B resolves to a real ``pages`` row, ensure the
    inverse ``(B→A, inv)`` exists ON THE TARGET page B. One ``INSERT … SELECT`` with
    ``INSERT OR IGNORE`` → idempotent + bidirectional-author convergent (PK collision is
    a no-op). The ``JOIN pages`` **skips ORPHAN targets** (arch-review M1 — the enforced
    FK on ``page_slug`` would else raise ``IntegrityError``) and supplies the target's
    ``page_project``; the ``NOT(…)`` skips self-page loops. The forward/inverse names are
    internal constants (no injection); the ``ref_type`` filter is bound.

    ``reindex_full``: ``source_slugs=None`` → GLOBAL pass over all edge rows, AFTER AM-3
    (canonical endpoints) and BEFORE ``_recompute_mentions`` (derived rows count, M2). On
    a freshly-wiped full this only ever inserts forward→inverse (the inverse-of-an-inverse
    would re-insert the original forward, already present → IGNORE).

    ``reindex_delta``: ``source_slugs`` = the TOUCHED source slugs → the pass derives only
    from THOSE pages' current edge rows (``f.page_slug IN source_slugs``). This is
    load-bearing: a delta must NOT reprocess a STALE inverse on an un-walked page, else it
    would derive the inverse-of-the-inverse and **resurrect** a forward the touched source
    just removed. Scoping to touched sources confines derivation to current rows."""
    kinds = tuple(_INVERSE_REF_TYPE)
    placeholders = ", ".join(["?"] * len(kinds))
    case = " ".join(f"WHEN '{fwd}' THEN '{inv}'"
                    for fwd, inv in _INVERSE_REF_TYPE.items())
    sql = (
        "INSERT OR IGNORE INTO page_entity_refs "
        "(vault_id, page_slug, page_project, entity_slug, ref_type, trust_level) "
        "SELECT f.vault_id, t.slug, t.project, f.page_slug, "
        f"       CASE f.ref_type {case} END, 'medium' "
        "FROM page_entity_refs f "
        "JOIN pages t ON t.vault_id = f.vault_id AND t.slug = f.entity_slug "
        "WHERE f.vault_id = ? "
        f"  AND f.ref_type IN ({placeholders}) "
        "  AND NOT (t.slug = f.page_slug AND t.project = f.page_project) "
        # vdd-multi MED: `entity_slug` is project-less, so a target slug shared across
        # projects (karpathy course tier / any project_pattern layout) would JOIN >1
        # page and fan the inverse onto pages the source never referenced. The forward
        # edge cannot disambiguate which project was meant, so derive the inverse ONLY
        # when the target slug resolves to EXACTLY ONE page (else skip — no phantom).
        "  AND (SELECT COUNT(*) FROM pages tc "
        "       WHERE tc.vault_id = f.vault_id AND tc.slug = f.entity_slug) = 1"
    )
    params: list[Any] = [vault_id, *kinds]
    if source_slugs is not None:
        if not source_slugs:
            return
        src_ph = ", ".join(["?"] * len(source_slugs))
        sql += f" AND f.page_slug IN ({src_ph})"
        params.extend(sorted(source_slugs))
    conn.execute(sql, params)
    # vdd-multi LOW: AM-3 alias canonicalization (Step 2.5, runs BEFORE this pass)
    # can rewrite a forward edge target to the SOURCE's own slug → a meaningless
    # (A,A) self-loop that the extraction-time guard (`_edge_refs`, pre-canonical)
    # never saw. Drop post-canonicalization self-loops for the typed edge kinds.
    conn.execute(
        "DELETE FROM page_entity_refs WHERE vault_id = ? AND page_slug = entity_slug "
        f"AND ref_type IN ({placeholders})", [vault_id, *kinds])


def _frontmatter_refs(
    db_type: str, updated_fm: dict[str, Any], vault_id: str, page_slug: str,
    page_project: str, skipped: list[dict[str, Any]],
    slug_strategy: str = "identity",
) -> list[PageRef]:
    """§D8 durability read-side dispatcher (TASK 007 R-6.5e + TASK 008 R-8.5e).

    Re-materialise the frontmatter-declared refs a host-only *compounding* page
    carries, so they survive a full DB rebuild from Class A markdown alone (the
    body-only ``extract_wiki_links`` path can produce only ``'mentioned'`` refs):

    * ``query``        → ``cites:`` list  → ``ref_type='cited'``
    * ``verification`` → ``verifies:`` str → ``ref_type='verifies'`` **plus** any
      ``cites:`` → ``ref_type='cited'`` (a verdict page may cite the sources a
      finding referenced — Q-008-f)
    * any other type   → ``[]`` (no-op — body ``mentioned`` refs are its only refs)

    The caller **unions the returned refs into the page's single
    ``replace_refs`` ref-set** (NOT a second ``replace_refs`` — that is
    delete-all-then-insert and would clobber the body ``mentioned`` refs, M-1).
    The composite PK ``(vault_id, page_slug, page_project, entity_slug,
    ref_type)`` keeps ``verifies`` / ``cited`` / ``mentioned`` refs to the same
    target distinct. Step 2.5 (AM-3) then canonicalizes every ref's
    ``entity_slug`` through the alias map, ``ref_type`` preserved.
    """
    refs: list[PageRef] = []
    if db_type in ("query", "verification"):
        refs.extend(_cited_refs(updated_fm, vault_id, page_slug, page_project, skipped))
    if db_type == "verification":
        refs.extend(_verifies_ref(updated_fm, vault_id, page_slug, page_project, skipped))
    # TASK 032 (ADR-004 D3): FORWARD event-graph edges — always-on, ANY page type
    # (Karpathy/_sources pages carry no edge keys → `_edge_refs` returns [] → byte-
    # identity preserved). Unioned into the page's single `replace_refs` (M-1); the
    # inverse rows are derived by the global post-pass in `reindex_full`.
    refs.extend(_edge_refs(
        updated_fm, vault_id, page_slug, page_project, slug_strategy, skipped))
    return refs


def _synthesize_fm(
    frontmatter: dict[str, Any], body: str, synthesis: dict[str, Any],
) -> dict[str, Any]:
    """PW-F frontmatter synthesis: when the layout enables it and the file has no
    `title:`, inject the first H1 as the title (→ `_build_page` falls back to the
    filename stem when there is no H1). The page `type` for a frontmatter-less file
    comes from the matched glob's `type` (glob_type) in `normalize_frontmatter`, so
    synthesis here only supplies the human title. No-op for Karpathy
    (`enabled: false`) → byte-identical."""
    if synthesis.get("enabled") and "title" not in frontmatter:
        h1 = first_h1(body)
        if h1:
            return {**frontmatter, "title": h1}
    return frontmatter


def _body_refs(
    out: Any, ref_rules: tuple[RefRule, ...], vault_id: str,
    slug_strategy: str = "identity", *,
    ref_extraction_operator_supplied: bool = False,
) -> list[PageRef]:
    """Body ``'mentioned'`` refs via the layout's ``ref_extraction`` rules
    (TASK 012 / PW-D) — config-driven, replacing the adapter's hardcoded
    wiki-link refs in the reindex path. The karpathy single wiki-link rule
    reproduces the previous ``out.refs`` byte-for-byte (golden anchor guards it);
    a dev-project layout additionally yields markdown-link + id-ref targets.

    TASK 014 / R-X1-REF-SLUGIFY: the extracted target is run through the layout's
    ``slug_strategy`` (``_apply_slug_strategy``) so it matches the way the TARGET
    page's slug was derived from its stem — otherwise a ``[[Title Case]]`` /
    ``[[Идеи]]`` link never resolves under a non-``identity`` strategy
    (transliterate / preserve-unicode) and is flagged a false ``orphan-link``.
    For ``identity`` (karpathy) this is a verbatim no-op → byte-identity preserved
    (golden anchor). ``cited``/``verifies`` refs (explicit slugs from frontmatter)
    are NOT touched — only body wiki/markdown-link targets."""
    return [
        PageRef(
            vault_id=vault_id, page_slug=out.page_slug, page_project=out.project,
            entity_slug=_apply_slug_strategy(target, slug_strategy),
            ref_type="mentioned", trust_level="high",
            line_start=line, line_end=line, source_quote=quote,
        )
        for (target, line, quote) in extract_refs(
            out.body_text, ref_rules,
            operator_supplied=ref_extraction_operator_supplied,
        )
        # A link into a `_raw/` capture (wiki-import's intentionally-unindexed source
        # original) is NOT a knowledge-graph ref → never record it (else it's a permanent
        # false orphan-link). Keyed on the pre-slugify target retaining the `_raw/` segment.
        if not (target.startswith("_raw/") or "/_raw/" in target)
    ]


def _build_page(out: Any, vault_id: str, db_type: str,
                src: Path, vault_root: Path,
                updated_fm: dict[str, Any],
                walk_mtime: float | None = None) -> Page:
    title = str(updated_fm.get("title") or out.page_slug)
    tldr_raw = updated_fm.get("tldr")
    tldr_val = tldr_raw if isinstance(tldr_raw, str) else None
    date_val: date_cls | None = None
    fm_date = updated_fm.get("date")
    if isinstance(fm_date, date_cls):
        date_val = fm_date
    elif isinstance(fm_date, str):
        try:
            date_val = date_cls.fromisoformat(fm_date)
        except ValueError:
            date_val = None
    # vdd-multi 030 PERF-LOW: honor the walk's single-stat contract — reuse
    # `DiscoveredPage.mtime` when the caller has it (full/touched-delta paths);
    # fall back to a stat for non-walk callers (upsert's disc carries 0.0 →
    # falsy → stat; wiki-query/verify/benchmark pass nothing).
    last_modified = (datetime.fromtimestamp(walk_mtime) if walk_mtime
                     else datetime.fromtimestamp(src.stat().st_mtime))
    return Page(
        vault_id=vault_id,
        slug=out.page_slug,
        project=out.project,
        type=db_type,  # type: ignore[arg-type]
        title=title,
        file_path=str(src.relative_to(vault_root)),
        tldr=tldr_val,
        date=date_val,
        last_modified=last_modified,
        file_hash=out.file_hash,
        frontmatter_json=updated_fm,
        # TASK 024 / Q-024-2 (R-2): store the FULL normalized body — `pages_fts`
        # indexes this column, so the search corpus is now the whole body (was
        # `[:1000]`, which made any term past char 1000 unfindable). Display stays
        # bounded: every search result renders `snippet(pages_fts, …, 16)`; no
        # consumer renders this column raw. The single write site (upsert + both
        # reindex paths all route through `_build_page` after Q-024-1).
        body_excerpt=normalize_body_for_fts(out.body_text),
        tags=list(updated_fm.get("tags") or []),
    )


def derive_indexed_page(
    adapter: ManualSourceAdapter,
    item: SourceItem,
    config: LayoutConfig,
    disc: DiscoveredPage | None,
    vault_id: str,
    cite_skipped: list[dict[str, Any]],
) -> tuple[Any, Page, dict[str, Any], list[PageRef]]:
    """TASK 024 / Q-024-1: the SINGLE per-file derivation shared by `reindex_full`,
    `reindex_delta`, AND `wiki-index-upsert.upsert_one` (3 sites → 1, prevents
    full/delta/upsert drift).

    Pipeline (byte-identical to the inline blocks it replaces — golden anchor):
    `adapter.fetch` (RETAINS the `validate_inside_vault` + `parse_frontmatter` +
    `compute_file_hash` seam) → layout-converged `(slug, project)` from `disc`
    (`replace(out, …)`) → `_synthesize_fm` (PW-F title) → layout-aware
    `normalize_frontmatter` (all 4 args: `type_mapping`, `path_type_fallback`,
    `extra_tags`, `glob_type`) → `_build_page` → `_body_refs` (slug-strategy-slugified
    targets) + `_frontmatter_refs`.

    `disc` is the layout's `DiscoveredPage` (reindex passes the `iter_pages` result;
    upsert passes `derive_discovered_page(...)`). `disc=None` (no layout glob matched)
    keeps the adapter's `derive_slug` identity + no `extra_tags`/`glob_type` — the
    legacy unmatched-file fallback (still uses the resolved layout's `type_mapping`).
    `cite_skipped` accumulates `_frontmatter_refs` cite-parse warnings (reindex
    surfaces it; `upsert_one` discards via `[]`). `UnmappedTypeError` /
    `BodyNormalizationError` / `PathTraversalError` / `OSError` propagate to the
    caller's per-file handler."""
    out = adapter.fetch(item)
    if disc is not None:
        out = replace(out, page_slug=disc.slug, project=disc.project)
        extra_tags: tuple[str, ...] = disc.extra_tags
        glob_type: str | None = disc.raw_type
    else:
        extra_tags = ()
        glob_type = None
    fm = _synthesize_fm(out.frontmatter, out.body_text, config.frontmatter_synthesis)
    updated_fm, db_type = normalize_frontmatter(
        fm, source_path=item.source_path,
        type_mapping=config.type_mapping,
        path_type_fallback=config.path_type_fallback,
        extra_tags=extra_tags,   # PW-N
        glob_type=glob_type,     # PW-C/F glob-inferred type
    )
    page = _build_page(out, vault_id, db_type, item.source_path, item.vault_root,
                       updated_fm,
                       walk_mtime=(disc.mtime if disc is not None else None))
    refs = _body_refs(
        out, config.ref_extraction, vault_id, config.slug_strategy,
        ref_extraction_operator_supplied=config.ref_extraction_operator_supplied)
    refs.extend(_frontmatter_refs(
        db_type, updated_fm, vault_id, out.page_slug, out.project, cite_skipped,
        slug_strategy=config.slug_strategy))
    return out, page, updated_fm, refs


def reindex_delta(repo: "IndexRepository", vault_id: str) -> dict[str, Any]:
    """mtime-based incremental reindex, rename-aware since TASK 030 (R-030-1):
    re-ingests files modified after the last log event AND any on-disk path
    absent from `pages.file_path` regardless of mtime; deletes DB rows for
    files removed from disk.

    Errors are recorded into the returned ``skipped`` list (parity with
    ``reindex_full``) rather than silently dropped. ``PathTraversalError``,
    OS-level errors AND per-file ``sqlite3.Error`` surface there (the latter
    since TASK 030 AC-1.6 — a systemic DB failure therefore degrades to
    per-file ``sqlite:<Type>`` skips with batch status "success"; deliberate,
    TASK-015 isolation precedent). Fatal-by-construction remain: the orphan-
    delete transaction (re-raises), the log append, and batch bookkeeping.
    """
    from scripts.wiki_index.sqlite_repository import SQLiteRepository
    if not isinstance(repo, SQLiteRepository):
        raise NotImplementedError("reindex_delta supports SQLiteRepository only")
    vault = repo.get_vault(vault_id)
    if vault is None:
        raise ValueError(f"vault_id={vault_id!r} not registered")
    vault_root = vault.root_path
    assert_no_symlink_escape(vault_root.resolve())
    config = resolve_layout_config(vault_root)  # PW-C/E: type-mapping source
    t0 = time.perf_counter()
    run_id = repo.begin_batch_run(vault_id, "delta")
    skipped: list[dict[str, Any]] = []
    slug_collisions: list[dict[str, Any]] = []          # TASK 020 / 021 (cross-batch)
    seen_keys: dict[tuple[str, str], str] = {}
    try:
        # TASK 050 (vdd-multi logic-MED): pure READ-telemetry rows must not
        # advance the delta cutoff — a `--log-retrieval`/`--log-access` event
        # (details.access=true) or an idempotent-apply trail (action=unchanged)
        # writes NO file/index state, so letting its event_ts become the cutoff
        # would silently skip a file modified just before it (stale index until
        # --full). Write-accompanied events (ingest/filed-apply/verify/reindex)
        # keep advancing it, as pre-050.
        row = repo._connect().execute(
            "SELECT MAX(event_ts) AS m FROM log_events WHERE vault_id = ? "
            "AND COALESCE(json_extract(details_json, '$.access'), 0) != 1 "
            "AND COALESCE(json_extract(details_json, '$.action'), '') "
            "    != 'unchanged'",
            (vault_id,),
        ).fetchone()
        cutoff = (datetime.fromisoformat(row["m"]) if row and row["m"]
                  else vault.registered_at)
        paths_on_disk = iter_pages(vault_root, config)
        on_disk_keys = {(d.slug, d.project) for d in paths_on_disk}
        # TASK 021 (HIGH-2, refined by review L-1/L-2 + PERF-021-1): cross-batch collision
        # detection. ONE pages read (`db_pages`), reused below for orphan deletion (was a
        # second scan → PERF-021-1) AND for the R-030-1 new-path membership set. Seed
        # `seen_keys` ONLY with prior-batch rows whose file is STILL on disk AND NOT part
        # of this batch's ingest set (mtime <= cutoff AND path already in the DB — a
        # mtime-stale NEW path is ingested by R-030-1 below, so it must not seed): a
        # touched file colliding with a genuinely-untouched prior row is reported, while
        # a re-walked survivor is left to the within-batch loop (L-1: no double-count /
        # inverted direction) and a renamed-away file is not falsely flagged (L-2 — its
        # row's file_path is no longer on disk). Seeded rows ∩ ingested files = ∅ by
        # construction: a seeded row's file_path IS in `db_file_paths`, hence never
        # "new-to-DB" (TASK 030 AC-1.3 invariant). Uses the walk's own mtime — no extra
        # stat. `_detect_slug_collision`'s `prior != rel` guard additionally makes a
        # same-path self-update a no-op.
        db_pages = repo._connect().execute(
            "SELECT slug, project, file_path FROM pages WHERE vault_id = ?",
            (vault_id,),
        ).fetchall()
        # R-030-1 (DF-029-1): the vault-rel string convention here MUST stay
        # `str(path.relative_to(vault_root))` — the same spelling `pages.file_path`
        # stores (F-2). No extra query: derived from the TASK-021 coalesced read.
        # The rel strings are computed ONCE per file and shared by the seeding
        # comprehension AND the ingest loop (Sarcasmotron 030-01 HIGH: a second
        # per-file `relative_to` on the no-op path measured +18% @10k).
        db_file_paths = {pre["file_path"] for pre in db_pages}
        disk_rels = [str(d.path.relative_to(vault_root)) for d in paths_on_disk]
        untouched_rels = {
            rel for d, rel in zip(paths_on_disk, disk_rels, strict=True)
            if d.mtime is not None and datetime.fromtimestamp(d.mtime) <= cutoff
        }
        for pre in db_pages:
            if pre["file_path"] in untouched_rels:
                seen_keys[(pre["slug"], pre["project"])] = pre["file_path"]
        touched = 0
        touched_slugs: set[str] = set()   # TASK 032: scope the inverse pass (no resurrect)
        new_path_ingested: list[str] = []
        adapter = ManualSourceAdapter()
        for disc, rel in zip(paths_on_disk, disk_rels, strict=True):
            path = disc.path
            # P-2 (TASK 017): reuse the mtime the `iter_pages` walk already stat'd —
            # no second `path.stat()` here. Fallback stat only for a hypothetical
            # non-iter_pages source that left `mtime` unset.
            if disc.mtime is not None:
                mtime = datetime.fromtimestamp(disc.mtime)
            else:
                try:
                    mtime = datetime.fromtimestamp(path.stat().st_mtime)
                except OSError as e:
                    skipped.append({"path": str(path), "error": f"stat: {e}"})
                    continue
            # R-030-1 (DF-029-1): a rename/move PRESERVES mtime, so the mtime gate
            # alone misses the moved file (its inbound links then orphan). Any on-disk
            # path absent from the vault's `pages.file_path` set is new-to-DB and must
            # be ingested regardless of mtime (also covers `cp -p` / archive / sync-
            # client imports, and the Q-030-3 fresh-vault first delta). Swap/rotation
            # renames (destination path already in the DB) stay out of reach —
            # documented residual (UC-30-1 A5): `wiki-lint` hash-drift detects,
            # `--full` remedies.
            is_new_path = rel not in db_file_paths
            if mtime <= cutoff and not is_new_path:
                continue
            try:
                item = SourceItem(kind="manual", source_path=path,
                                  vault_root=vault_root, vault_id=vault_id)
                # TASK 024 / Q-024-1: shared per-file derivation (full/delta/upsert
                # parity). Cite-parse warnings fold into `skipped` (R-6.5e symmetry).
                out, page, _updated_fm, delta_refs = derive_indexed_page(
                    adapter, item, config, disc, vault_id, skipped)
                # vdd-multi 030 LOGIC-MED: page + file_path refresh + refs run as
                # ONE per-file transaction (030-02 txn-free helpers) — a transient
                # mid-file `sqlite3.Error` used to commit the page (new hash/FTS)
                # while refs stayed stale, and the file was NEVER retried (in
                # `db_file_paths` + mtime ≤ the advanced cutoff): a permanent
                # page↔refs incoherence lint could not see. Now the whole file
                # rolls back — CONSISTENT-stale (old row intact; recorded
                # residual: re-ingest happens on the next touch or `--full`,
                # the `skipped` entry is the operator signal). Bonus: 2-3 txns
                # per touched file → 1.
                conn_d = repo._connect()
                conn_d.execute("BEGIN IMMEDIATE")
                try:
                    outcome = repo._upsert_page_in_txn(conn_d, page)
                    if is_new_path and outcome == "unchanged":
                        # Q-030-5 delta-sibling (arch-review HIGH-1): the hash
                        # short-circuit returns BEFORE any UPDATE, so a moved-
                        # but-unedited file's `file_path` would stay stale and
                        # re-detect as "new" on EVERY future delta (a loop, not
                        # a wave). One targeted refresh converges it (AC-1.9).
                        conn_d.execute(
                            "UPDATE pages SET file_path = ?, last_modified = ? "
                            "WHERE vault_id = ? AND slug = ? AND project = ?",
                            (rel, page.last_modified.isoformat(),
                             vault_id, out.page_slug, out.project))
                    repo._replace_refs_in_txn(conn_d, vault_id, out.page_slug,
                                              out.project, delta_refs)
                    conn_d.execute("COMMIT")
                except BaseException:
                    if conn_d.in_transaction:
                        conn_d.execute("ROLLBACK")
                    raise
                touched += 1
                touched_slugs.add(out.page_slug)
                if is_new_path:
                    new_path_ingested.append(rel)
                _detect_slug_collision(
                    seen_keys, out.page_slug, out.project, rel, slug_collisions)
            except (UnmappedTypeError, BodyNormalizationError) as e:
                skipped.append({"path": str(path), "error": str(e)})
            except (PathTraversalError, OSError, ValueError) as e:
                skipped.append({"path": str(path), "error": str(e)})
            except sqlite3.Error as e:
                # R-030-1 / AC-1.6 (TASK-015 per-entry precedent): a stale row
                # holding this path under another (slug, project) raises
                # IntegrityError on UNIQUE(vault_id, file_path) — isolate the
                # file, never the run. No value echo (CWE-209 posture).
                _LOG.warning("[delta-skip] sqlite error on %s: %s",
                             rel, type(e).__name__)
                skipped.append({"path": str(path),
                                "error": f"sqlite:{type(e).__name__}"})

        # Delete orphan rows inside a single transaction (atomicity contract). Reuses the
        # `db_pages` snapshot read once above (PERF-021-1) — a row deleted from disk this
        # run is in that pre-loop snapshot and absent from `on_disk_keys`; a newly-upserted
        # row is on disk so never an orphan, so the pre-loop snapshot is sufficient.
        conn = repo._connect()
        deleted = 0
        conn.execute("BEGIN IMMEDIATE")
        try:
            for r in db_pages:
                if (r["slug"], r["project"]) not in on_disk_keys:
                    repo.delete_page(vault_id, r["slug"], r["project"])
                    deleted += 1
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        # Step 4.5 (TASK 032 / R-032-3, ADR-004 D4): refresh inverse edges. Delta runs
        # the inverse-derivation pass SCOPED to the touched sources (`touched_slugs`) so
        # an edge added/changed on a re-walked source materializes its inverse on the
        # (possibly un-walked) target. Gated on `touched or deleted` to preserve the
        # AC-1.9 true-no-op delta. Runs once per delta run (the inverse pass is a single
        # set-based statement) on the cached singleton connection — `repo._connect()`
        # returns the same `conn`, NOT a new connection.
        #
        # TWO documented delta↔full divergence classes, both repaired by `--full`
        # (ADR-002 §D8 / TASK 030 A5 posture — delta is best-effort, `--full` is
        # authoritative); neither is safely closable in delta without a provenance column
        # (out of scope), because a stored `(B→A, inv)` row is INDISTINGUISHABLE from an
        # edge B AUTHORED directly (same ref_type):
        #   (1) Stale-inverse-after-removal: source A removes `implements: [[B]]`; the
        #       inverse `(B→A, implemented-by)` on the un-walked B persists until --full.
        #       Delta must NOT delete it (could clobber an edge B authored), AND the pass
        #       is scoped to A — NOT B — so it cannot re-derive `(A→B, implements)` back
        #       from that stale inverse (the resurrection bug; scoping is load-bearing).
        #   (2) Missing-derivation-from-untouched-source: under BIDIRECTIONAL authoring
        #       (A `superseded_by:[[B]]`, B `supersedes:[[A]]`), removing B's `supersedes`
        #       re-walks only B → B's forward goes, but A's still-authored `superseded_by`
        #       would re-derive `(B→A, supersedes)` on a --full. Delta's source-scoping to
        #       {B} does NOT process A's forward, so that inverse is temporarily MISSING
        #       (graph asymmetric) until --full. Broadening the scope to `entity_slug IN
        #       touched` would close this BUT reintroduce divergence (1)'s resurrection
        #       (it cannot tell A's authored forward from a stale inverse), so the scope
        #       stays source-only by design.
        if touched or deleted:
            conn_inv = repo._connect()  # cached singleton (same conn) — not a new handle
            conn_inv.execute("BEGIN IMMEDIATE")
            try:
                _derive_inverse_edges(conn_inv, vault_id, touched_slugs)
                conn_inv.execute("COMMIT")
            except Exception:
                conn_inv.execute("ROLLBACK")
                raise

        # Step 5 (PW-H, critic-logic HIGH-1): re-render auto_indexes so an
        # incremental edit/delete of a known-issue keeps the Class-B ledger
        # consistent — otherwise the supported `--delta` workflow leaves a stale
        # ledger that the PW-Q drift guard then false-flags. Reuses the `config`
        # resolved at the top (no re-resolve). No-op for layouts w/o auto_indexes.
        from scripts.wiki_index.rendering import render_and_write_auto_indexes
        auto_rendered = render_and_write_auto_indexes(
            repo, vault_id, vault_root, config,
            generated_at=datetime.now().isoformat(),
        )
        duration = time.perf_counter() - t0
        repo.append_log_event(LogEvent(
            vault_id=vault_id,
            event_ts=datetime.now(),
            event_type="reindex",
            subject="delta",
            pages_created_json=[],
            pages_updated_json=[],
            details_json={"touched": touched, "deleted": deleted,
                          "skipped": len(skipped)},
        ))
        repo.finish_batch_run(
            run_id, "success",
            notes=f"touched={touched} deleted={deleted} skipped={len(skipped)}",
        )
    except Exception as e:
        repo.finish_batch_run(run_id, "failed", notes=str(e))
        raise
    return {
        "action": "reindexed", "mode": "delta", "vault_id": vault_id,
        "touched": touched, "deleted": deleted, "skipped": skipped,
        "slug_collisions": slug_collisions,
        "new_path_ingested": sorted(new_path_ingested),  # R-030-1, additive (AC-1.4)
        "auto_rendered": auto_rendered,
        "duration_seconds": round(duration, 3),
    }


def reindex_full(repo: "IndexRepository", vault_id: str) -> dict[str, Any]:
    """Rebuild all DB rows for `vault_id` from filesystem.

    NOT a single atomic transaction (F8, vdd-multi): Step 1 wipes + commits,
    then Step 2 runs as **stage-then-flush chunked transactions** (TASK 030 /
    R-030-2b, closes P-1): per-file derivation (file I/O) STAGES outside any
    transaction into a buffer bounded by `REINDEX_TX_CHUNK` pages ∧
    `REINDEX_TX_CHUNK_BYTES`; each chunk then FLUSHES its DML (page + refs +
    entity + alias rows, via the 030-02 txn-free helpers) under ONE
    `BEGIN IMMEDIATE` — the write lock is held ms-scale, never across file
    I/O (Q-030-5; concurrent writers on a shared global.db stay live).
    Steps 2.5/3 ride autocommit as before. A mid-rebuild crash leaves the
    index half-populated (now at chunk granularity); recovery is to re-run
    `reindex --full` — the documented Phase-3a trade-off, not atomicity."""
    from scripts.wiki_index.sqlite_repository import SQLiteRepository
    if not isinstance(repo, SQLiteRepository):
        raise NotImplementedError("reindex_full supports SQLiteRepository only")

    vault = repo.get_vault(vault_id)
    if vault is None:
        raise ValueError(f"vault_id={vault_id!r} not registered")
    vault_root = vault.root_path
    config = resolve_layout_config(vault_root)  # PW-C/E: type-mapping source

    t0 = time.perf_counter()
    run_id = repo.begin_batch_run(vault_id, "full")
    conn = repo._connect()
    adapter = ManualSourceAdapter()
    pages_count = entities_count = log_events_count = 0
    aliases_count = 0
    skipped: list[dict[str, Any]] = []
    alias_collisions: list[dict[str, Any]] = []
    cite_skipped: list[dict[str, Any]] = []
    slug_collisions: list[dict[str, Any]] = []          # TASK 020
    seen_keys: dict[tuple[str, str], str] = {}          # (slug, project) → first file
    try:
        # Step 1: wipe existing rows in a short atomic transaction.
        conn.execute("BEGIN IMMEDIATE")
        try:
            for tbl in ("page_entity_refs", "pages", "entities"):
                conn.execute(f"DELETE FROM {tbl} WHERE vault_id = ?", (vault_id,))
            # TASK 050 (R-6b / Q-050-2): spare Class-C DB-ONLY audit events.
            # Mirrored rows (log_md_byte_offset set) are wiped + re-parsed from
            # log.md below (log.md stays authoritative for the mirror, no
            # dupes); a NULL offset means the row NEVER had a log.md line (the
            # apply/verify/--log-* audit shape) — a Class-B rebuild must not
            # destroy Class-C state (the source_state/query-state precedent).
            conn.execute(
                "DELETE FROM log_events WHERE vault_id = ? "
                "AND log_md_byte_offset IS NOT NULL", (vault_id,))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

        # Step 2 (TASK 030 / R-030-2b, closes P-1): STAGE-THEN-FLUSH. The
        # pre-030 contingency note here ("benchmark task flags if scale demands
        # chunked-tx strategy") is now implemented. Staging derives each file
        # (all file I/O) OUTSIDE any transaction; a chunk flushes its DML under
        # ONE caller-owned BEGIN IMMEDIATE via the 030-02 txn-free helpers —
        # the write lock never spans file I/O (Q-030-5 / arch-review HIGH-2).
        # Per-file error semantics: derivation errors isolate at STAGING with
        # zero DML (strictly better than the old committed-partial); mid-flush
        # DML errors are statement-atomic — the file's partial DML commits with
        # the chunk while the file lands in `skipped` (equivalent end-state to
        # the old per-call-txn path); a COMMIT/BEGIN failure is fatal → chunk
        # ROLLBACK + batch "failed" (FTS triggers ride the same tx — no desync).
        # staged tuple: (abs_path_str, page_slug, project, page,
        # entity_args | None, aliases, refs); entity/alias rows are PRE-COMPUTED
        # at staging (pure logic) so the flush is DML-only. Only the slug/project
        # STRINGS are staged — not the whole SourceOutput (avoids retaining
        # `body_text`+a second refs list on corpora where normalization copies).
        # vdd-multi 030 PERF-M1, CORRECTED attribution (iter-2 verifier): the
        # real ~2× peak (63.6 vs 32 MiB) was the **UTF-8 bind caches**
        # `sqlite3_bind_text`/`PyUnicode_AsUTF8` attaches to each staged body
        # string during the flush, held alive because `staged` survived until
        # post-COMMIT `clear()`. The flush therefore DRAINS the buffer per-row
        # (entry → None right after unpacking) so each body string + its bind
        # cache is freeable as soon as its DML ran — measured peak ≈ 33 MiB
        # (1× budget).
        staged: list[tuple[str, str, str, Page, tuple[Any, ...] | None,
                           list[str], list[PageRef]] | None] = []
        staged_bytes = 0

        def _flush_chunk() -> None:
            nonlocal pages_count, entities_count, aliases_count, staged_bytes
            if not staged:
                return
            conn.execute("BEGIN IMMEDIATE")
            try:
                for _i in range(len(staged)):
                    entry = staged[_i]
                    assert entry is not None  # filled by staging, drained once
                    (abs_path, s_slug, s_project, s_page, entity_args,
                     s_aliases, s_refs) = entry
                    staged[_i] = None  # PERF-M1 drain: free body + bind cache
                    del entry
                    try:
                        repo._upsert_page_in_txn(conn, s_page,
                                                 skip_unchanged_check=True)
                        repo._replace_refs_in_txn(conn, vault_id,
                                                  s_slug, s_project, s_refs)
                        pages_count += 1
                        _detect_slug_collision(
                            seen_keys, s_slug, s_project,
                            s_page.file_path, slug_collisions)
                        if entity_args is not None:
                            conn.execute(
                                "INSERT OR IGNORE INTO entities (vault_id, slug, "
                                "type, name, project, is_candidate, first_seen, "
                                "last_updated, file_path, mentions_count, "
                                "metadata_json) "
                                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
                                entity_args,
                            )
                            entities_count += 1
                            # R-5.3: report-and-skip on the hard PK collision —
                            # per-alias catch keeps the chunk tx alive
                            # (statement-level atomicity).
                            for alias in s_aliases:
                                try:
                                    conn.execute(
                                        "INSERT INTO entity_aliases "
                                        "(vault_id, alias, entity_slug, alias_type) "
                                        "VALUES (?, ?, ?, 'spelling_variant')",
                                        (vault_id, alias, s_slug),
                                    )
                                    aliases_count += 1
                                except sqlite3.IntegrityError:
                                    kept = conn.execute(
                                        "SELECT entity_slug FROM entity_aliases "
                                        "WHERE vault_id = ? AND alias = ?",
                                        (vault_id, alias),
                                    ).fetchone()
                                    alias_collisions.append({
                                        "alias": alias,
                                        "kept_slug": (kept["entity_slug"]
                                                      if kept else None),
                                        "skipped_slug": s_slug,
                                    })
                    except Exception as e:
                        # Q-030-5 A2: mid-flush DML error — partial per-file DML
                        # stays in the chunk; the file is reported. A COMMIT
                        # failure never lands here (outside this try).
                        skipped.append({"path": abs_path, "error": str(e)})
                conn.execute("COMMIT")
            except Exception:
                # Sarcasmotron 030-03 HIGH: SQLite auto-rolls-back on
                # SQLITE_FULL/IOERR/NOMEM — an unconditional ROLLBACK would then
                # raise "no transaction is active" and MASK the original fatal
                # error (corrupting batch_runs.notes). Guard on in_transaction.
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            staged.clear()
            staged_bytes = 0

        for disc in iter_pages(vault_root, config):
            path = disc.path
            try:
                item = SourceItem(kind="manual", source_path=path,
                                  vault_root=vault_root, vault_id=vault_id)
                # TASK 024 / Q-024-1: shared per-file derivation (full/delta/upsert
                # parity). R-6.5e + R-8.5e: `_frontmatter_refs` unions a host-only
                # compounding page's `cites:`/`verifies:` refs into the SINGLE
                # replace_refs ref-set (a second call would clobber body refs, M-1).
                # Step 2.5 (AM-3) below canonicalizes all refs' targets via aliases.
                out, page, updated_fm, all_refs = derive_indexed_page(
                    adapter, item, config, disc, vault_id, cite_skipped)
                # Pre-compute the entity row for _concepts/_entities files
                # (pure logic — DML happens in the flush).
                # entities.type follows the frontmatter's `type:` field
                # (concept | person | company | product | group | event |
                # work | external). Path is just the bucket discriminator;
                # the actual entity-kind comes from the file itself so
                # wiki-ingest's typed entities (e.g. type=person) survive
                # round-trip. Fall back: _concepts/* → concept, _entities/*
                # → external when frontmatter has no `type:`.
                entity_args: tuple[Any, ...] | None = None
                alias_list: list[str] = []
                rel_parts = path.relative_to(vault_root).parts
                if any(p in (CONCEPTS_SUBDIR, ENTITIES_SUBDIR) for p in rel_parts):
                    fm_type = updated_fm.get("type")
                    if fm_type in (
                        "concept", "person", "company", "product",
                        "group", "event", "work", "external",
                    ):
                        e_type = fm_type
                    elif CONCEPTS_SUBDIR in rel_parts:
                        e_type = "concept"
                    else:
                        e_type = "external"
                    ts_iso = datetime.now().isoformat()
                    # R-4.1: read is_candidate from Class A frontmatter (was
                    # omitted → schema default 0, which silently confirmed every
                    # candidate on a full rebuild).
                    # L-8 (TASK 006): concept pages emit `name:`, not `title:` —
                    # fall back title→name→slug so the entity's display name
                    # survives reindex (was: slug).
                    entity_args = (
                        vault_id, out.page_slug, e_type,
                        (updated_fm.get("title") or updated_fm.get("name")
                         or out.page_slug),
                        out.project, _coerce_is_candidate(updated_fm),
                        ts_iso, ts_iso,
                        str(path.relative_to(vault_root)), "{}",
                    )
                    # R-5.3: mirror Class A `aliases:` frontmatter →
                    # entity_aliases (Class B). The flat Obsidian list carries
                    # no type → 'spelling_variant' default (C-4 limitation).
                    raw_aliases = updated_fm.get("aliases")
                    if isinstance(raw_aliases, list):
                        alias_list = [a.strip() for a in raw_aliases
                                      if isinstance(a, str) and a.strip()]
                # Buffer accounting BEFORE the append (vdd-multi 030 LOGIC-LOW:
                # a frontmatter value surviving `_json_safe` but not JSON-
                # serializable raised HERE after the entry was already staged →
                # the same file skipped TWICE — once at staging, once at flush).
                # Honest approximation (Sarcasmotron 030-03 MED): full body +
                # the frontmatter dump (~µs/page; the upsert dumps it again) +
                # per-ref quote/slug payload, ×2 as a UTF-8 chars≈bytes fudge.
                staged_bytes += 2 * (
                    len(page.body_excerpt)
                    + len(json.dumps(page.frontmatter_json, ensure_ascii=False))
                    + sum(len(r.source_quote or "") + len(r.entity_slug) + 64
                          for r in all_refs)
                )
                staged.append((str(path), out.page_slug, out.project, page,
                               entity_args, alias_list, all_refs))
            except (UnmappedTypeError, BodyNormalizationError) as e:
                skipped.append({"path": str(path), "error": str(e)})
            except Exception as e:
                skipped.append({"path": str(path), "error": str(e)})
            # Sarcasmotron 030-03 CRITICAL: the flush trigger lives OUTSIDE the
            # per-file try — a fatal flush failure (e.g. "database is locked"
            # BEGIN on a contended shared DB) must PROPAGATE to the batch
            # "failed" path, never be swallowed as a per-file skip (which also
            # double-counted pages and replayed the uncleared buffer O(N²)).
            if (len(staged) >= REINDEX_TX_CHUNK
                    or staged_bytes >= REINDEX_TX_CHUNK_BYTES):
                _flush_chunk()
        _flush_chunk()  # tail chunk

        # Parse log.md files → reconstruct log_events
        log_dir = vault_root / VAULT_INDEX_DIR / LOG_SUBDIR
        for log_md in (log_dir.glob("*.md") if log_dir.is_dir() else []):
            for ts, etype, subject, offset in parse_log_md(log_md):
                try:
                    ev_id = repo.append_log_event(LogEvent(
                        vault_id=vault_id,
                        event_ts=ts,
                        event_type=etype,
                        subject=subject,
                        pages_created_json=[],
                        pages_updated_json=[],
                        details_json={},
                        log_md_path=str(log_md.relative_to(vault_root)),
                    ))
                    repo.update_log_event_offset(ev_id, offset)
                    log_events_count += 1
                except Exception:
                    # Skip events with unknown event_type (CHECK violations)
                    continue

        # Step 2.5 (AM-3): canonicalize page_entity_refs.entity_slug through the
        # alias table. A raw `[[surface]]` whose target is a registered alias is
        # re-pointed to the canonical entity, establishing the invariant "a ref
        # names the canonical entity whenever its raw target is a known alias".
        # This keeps recompute_mentions / get_backlinks (which key on
        # entity_slug = entities.slug) correct after a FULL rebuild — the merge
        # §D8 durability gate (UC-15) depends on it (else a `wiki-merge` would be
        # silently un-done on the next reindex). Built once from an in-memory map
        # (no per-ref SQL for resolution); only the rare alias-refs get a write.
        # On a (page, canonical, ref_type) PK collision the alias-ref is dropped —
        # the canonical ref already covers that mention.
        alias_map = {
            r["alias"]: r["entity_slug"]
            for r in conn.execute(
                "SELECT alias, entity_slug FROM entity_aliases WHERE vault_id = ?",
                (vault_id,),
            ).fetchall()
        }
        if alias_map:
            for ref in conn.execute(
                "SELECT rowid AS rid, entity_slug FROM page_entity_refs "
                "WHERE vault_id = ?",
                (vault_id,),
            ).fetchall():
                canon = alias_map.get(ref["entity_slug"])
                if canon is None or canon == ref["entity_slug"]:
                    continue
                try:
                    conn.execute(
                        "UPDATE page_entity_refs SET entity_slug = ? "
                        "WHERE rowid = ?",
                        (canon, ref["rid"]),
                    )
                except sqlite3.IntegrityError:
                    conn.execute(
                        "DELETE FROM page_entity_refs WHERE rowid = ?",
                        (ref["rid"],),
                    )

        # Step 2.6 (TASK 032 / R-032-3, ADR-004 D3): derive inverse edges globally,
        # AFTER AM-3 (canonical endpoints) and BEFORE _recompute_mentions (so the
        # derived rows are counted — arch-review M2). Skips orphan targets (M1).
        _derive_inverse_edges(conn, vault_id)

        # Step 3: recompute entities.mentions_count (I-5 invariant).
        # F12c (TASK 006): one shared helper (repo is a SQLiteRepository — checked
        # at function top) instead of a 4th hand-copied correlated UPDATE.
        repo._recompute_mentions(conn, vault_id)

        # Step 4: synthetic reindex log event
        repo.append_log_event(LogEvent(
            vault_id=vault_id,
            event_ts=datetime.now(),
            event_type="reindex",
            subject="full",
            pages_created_json=[],
            pages_updated_json=[],
            details_json={"pages": pages_count, "entities": entities_count,
                          "log_events": log_events_count,
                          "skipped": len(skipped)},
        ))
        # Step 5 (PW-H, TASK 012): render the layout's auto_indexes[] targets
        # (e.g. docs/KNOWN_ISSUES.md) from the now-indexed Class-A pages. No-op
        # for layouts without auto_indexes (Karpathy → byte-identical).
        from scripts.wiki_index.rendering import render_and_write_auto_indexes
        auto_rendered = render_and_write_auto_indexes(
            repo, vault_id, vault_root, config,
            generated_at=datetime.now().isoformat(),
        )

        repo.finish_batch_run(
            run_id, "success",
            notes=f"pages={pages_count} entities={entities_count} "
                  f"log_events={log_events_count} skipped={len(skipped)}",
        )
    except Exception as e:
        repo.finish_batch_run(run_id, "failed", notes=str(e))
        raise

    duration = time.perf_counter() - t0
    return {
        "action": "reindexed",
        "vault_id": vault_id,
        "pages": pages_count,
        "entities": entities_count,
        "log_events": log_events_count,
        "aliases": aliases_count,
        "alias_collisions": alias_collisions,
        "slug_collisions": slug_collisions,
        "cite_skipped": cite_skipped,
        "skipped": skipped,
        "auto_rendered": auto_rendered,
        "duration_seconds": round(duration, 3),
    }
