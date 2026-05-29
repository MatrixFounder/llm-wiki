"""wiki-reindex --full impl — ADR-002 §D8 Class A → B reconstruction (task-001-30)."""

from __future__ import annotations

import sqlite3
import time
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

from slugify import slugify

from scripts.wiki_index.layout import (
    CONCEPTS_SUBDIR,
    COURSE_TIER_DIR,
    ENTITIES_SUBDIR,
    LOG_SUBDIR,
    PAGE_SUBDIRS,
    VAULT_INDEX_DIR,
    VAULT_TIER_PROJECT,
)
from scripts.wiki_index.logfile import parse_log_md
from scripts.wiki_index.models import Entity, LogEvent, Page
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

if TYPE_CHECKING:
    from scripts.wiki_index.repository import IndexRepository


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
    """Walk both tiers; yield (path, slug, project) tuples."""
    out: list[tuple[Path, str, str]] = []
    # Root tier
    for sub in PAGE_SUBDIRS:
        base = vault_root / sub
        if base.is_dir():
            for f in base.rglob("*.md"):
                if f.is_file():
                    out.append((f, f.stem, VAULT_TIER_PROJECT))
    # Course tier under Lessons/
    lessons = vault_root / COURSE_TIER_DIR
    if lessons.is_dir():
        for course_dir in lessons.iterdir():
            if not course_dir.is_dir():
                continue
            proj = slugify(course_dir.name, lowercase=True, separator="-")
            for sub in PAGE_SUBDIRS:
                base = course_dir / sub
                if base.is_dir():
                    for f in base.rglob("*.md"):
                        if f.is_file():
                            out.append((f, f.stem, proj))
    return out


def _build_page(out: Any, vault_id: str, db_type: str,
                src: Path, vault_root: Path,
                updated_fm: dict[str, Any]) -> Page:
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
    last_modified = datetime.fromtimestamp(src.stat().st_mtime)
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
        body_excerpt=normalize_body_for_fts(out.body_text)[:1000],
        tags=list(updated_fm.get("tags") or []),
    )


def reindex_delta(repo: "IndexRepository", vault_id: str) -> dict[str, Any]:
    """mtime-based incremental reindex. Re-ingests files modified after the
    last log event; deletes DB rows for files removed from disk.

    Errors are recorded into the returned ``skipped`` list (parity with
    ``reindex_full``) rather than silently dropped. ``PathTraversalError`` and
    OS-level errors surface there; truly fatal sqlite errors propagate.
    """
    from scripts.wiki_index.sqlite_repository import SQLiteRepository
    if not isinstance(repo, SQLiteRepository):
        raise NotImplementedError("reindex_delta supports SQLiteRepository only")
    vault = repo.get_vault(vault_id)
    if vault is None:
        raise ValueError(f"vault_id={vault_id!r} not registered")
    vault_root = vault.root_path
    assert_no_symlink_escape(vault_root.resolve())
    t0 = time.perf_counter()
    run_id = repo.begin_batch_run(vault_id, "delta")
    skipped: list[dict[str, Any]] = []
    try:
        row = repo._connect().execute(
            "SELECT MAX(event_ts) AS m FROM log_events WHERE vault_id = ?",
            (vault_id,),
        ).fetchone()
        cutoff = (datetime.fromisoformat(row["m"]) if row and row["m"]
                  else vault.registered_at)
        paths_on_disk = discover_pages(vault_root)
        on_disk_keys = {(slug, project) for (_, slug, project) in paths_on_disk}
        touched = 0
        adapter = ManualSourceAdapter()
        for path, slug, project in paths_on_disk:
            try:
                mtime = datetime.fromtimestamp(path.stat().st_mtime)
            except OSError as e:
                skipped.append({"path": str(path), "error": f"stat: {e}"})
                continue
            if mtime <= cutoff:
                continue
            try:
                item = SourceItem(kind="manual", source_path=path,
                                  vault_root=vault_root, vault_id=vault_id)
                out = adapter.fetch(item)
                updated_fm, db_type = normalize_frontmatter(
                    out.frontmatter, source_path=path,
                )
                page = _build_page(out, vault_id, db_type, path, vault_root,
                                   updated_fm)
                repo.upsert_page(page)
                repo.replace_refs(vault_id, out.page_slug, out.project,
                                  out.refs)
                touched += 1
            except (UnmappedTypeError, BodyNormalizationError) as e:
                skipped.append({"path": str(path), "error": str(e)})
            except (PathTraversalError, OSError, ValueError) as e:
                skipped.append({"path": str(path), "error": str(e)})

        # Delete orphan rows inside a single transaction (atomicity contract).
        conn = repo._connect()
        db_pages = conn.execute(
            "SELECT slug, project FROM pages WHERE vault_id = ?", (vault_id,)
        ).fetchall()
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
        "duration_seconds": round(duration, 3),
    }


def reindex_full(repo: "IndexRepository", vault_id: str) -> dict[str, Any]:
    """Rebuild all DB rows for `vault_id` from filesystem.

    NOT a single atomic transaction (F8, vdd-multi): Step 1 wipes + commits,
    then Steps 2/2.5/3 run in autocommit (each `upsert_page`/`replace_refs`
    owns its own short tx — see Step 2 note). A mid-rebuild crash leaves the
    index half-populated; recovery is to re-run `reindex --full`. This is the
    documented Phase-3a SLO trade-off (KNOWN_ISSUES P-1), not atomicity."""
    from scripts.wiki_index.sqlite_repository import SQLiteRepository
    if not isinstance(repo, SQLiteRepository):
        raise NotImplementedError("reindex_full supports SQLiteRepository only")

    vault = repo.get_vault(vault_id)
    if vault is None:
        raise ValueError(f"vault_id={vault_id!r} not registered")
    vault_root = vault.root_path

    t0 = time.perf_counter()
    run_id = repo.begin_batch_run(vault_id, "full")
    conn = repo._connect()
    adapter = ManualSourceAdapter()
    pages_count = entities_count = log_events_count = 0
    aliases_count = 0
    skipped: list[dict[str, Any]] = []
    alias_collisions: list[dict[str, Any]] = []
    try:
        # Step 1: wipe existing rows in a short atomic transaction.
        conn.execute("BEGIN IMMEDIATE")
        try:
            for tbl in ("page_entity_refs", "pages", "entities", "log_events"):
                conn.execute(f"DELETE FROM {tbl} WHERE vault_id = ?", (vault_id,))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

        # Step 2: rebuild row-by-row. upsert_page manages its own transaction
        # per call; can't nest BEGIN IMMEDIATE. Phase 3a SLO (1K-10K pages)
        # tolerates non-atomic rebuild; benchmark task (001-33) flags if scale
        # demands chunked-tx strategy.
        for path, slug, project in discover_pages(vault_root):
            try:
                item = SourceItem(kind="manual", source_path=path,
                                  vault_root=vault_root, vault_id=vault_id)
                out = adapter.fetch(item)
                updated_fm, db_type = normalize_frontmatter(
                    out.frontmatter, source_path=path,
                )
                page = _build_page(out, vault_id, db_type, path, vault_root,
                                   updated_fm)
                repo.upsert_page(page)
                repo.replace_refs(vault_id, out.page_slug, out.project,
                                  out.refs)
                pages_count += 1
                # Register entity row for _concepts/_entities files.
                # entities.type follows the frontmatter's `type:` field
                # (concept | person | company | product | group | event |
                # work | external). Path is just the bucket discriminator;
                # the actual entity-kind comes from the file itself so
                # wiki-ingest's typed entities (e.g. type=person) survive
                # round-trip. Fall back: _concepts/* → concept, _entities/*
                # → external when frontmatter has no `type:`.
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
                    conn.execute(
                        "INSERT OR IGNORE INTO entities (vault_id, slug, "
                        "type, name, project, is_candidate, first_seen, "
                        "last_updated, file_path, mentions_count, metadata_json) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
                        (vault_id, out.page_slug, e_type,
                         # L-8 (TASK 006): concept pages emit `name:`, not
                         # `title:` — fall back title→name→slug so the entity's
                         # display name survives reindex (was: slug).
                         (updated_fm.get("title") or updated_fm.get("name")
                          or out.page_slug),
                         out.project, _coerce_is_candidate(updated_fm),
                         ts_iso, ts_iso,
                         str(path.relative_to(vault_root)), "{}"),
                    )
                    entities_count += 1
                    # R-5.3: mirror Class A `aliases:` frontmatter → entity_aliases
                    # (Class B). Report-and-skip on the hard PK (vault_id, alias)
                    # collision — NEVER a silent INSERT OR IGNORE: two pages
                    # claiming the same surface is operator-visible data the lint
                    # layer must see. The flat Obsidian list carries no type, so
                    # the mirror defaults to 'spelling_variant' (C-4 limitation).
                    raw_aliases = updated_fm.get("aliases")
                    if isinstance(raw_aliases, list):
                        for _alias in raw_aliases:
                            if not isinstance(_alias, str) or not _alias.strip():
                                continue
                            alias = _alias.strip()
                            try:
                                conn.execute(
                                    "INSERT INTO entity_aliases "
                                    "(vault_id, alias, entity_slug, alias_type) "
                                    "VALUES (?, ?, ?, 'spelling_variant')",
                                    (vault_id, alias, out.page_slug),
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
                                    "kept_slug": kept["entity_slug"] if kept else None,
                                    "skipped_slug": out.page_slug,
                                })
            except (UnmappedTypeError, BodyNormalizationError) as e:
                skipped.append({"path": str(path), "error": str(e)})
            except Exception as e:
                skipped.append({"path": str(path), "error": str(e)})

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
        "skipped": skipped,
        "duration_seconds": round(duration, 3),
    }
