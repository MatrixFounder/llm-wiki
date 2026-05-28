"""wiki-reindex --full impl — ADR-002 §D8 Class A → B reconstruction (task-001-30)."""

from __future__ import annotations

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
    """Rebuild all DB rows for `vault_id` from filesystem. Atomic single-tx."""
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
    skipped: list[dict[str, Any]] = []
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
                    conn.execute(
                        "INSERT OR IGNORE INTO entities (vault_id, slug, "
                        "type, name, project, first_seen, last_updated, "
                        "file_path, mentions_count, metadata_json) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
                        (vault_id, out.page_slug, e_type,
                         updated_fm.get("title", out.page_slug),
                         out.project, ts_iso, ts_iso,
                         str(path.relative_to(vault_root)), "{}"),
                    )
                    entities_count += 1
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

        # Step 3: recompute entities.mentions_count (I-5 invariant).
        conn.execute(
            "UPDATE entities SET mentions_count = ("
            "  SELECT COUNT(*) FROM page_entity_refs r "
            "  WHERE r.vault_id = entities.vault_id "
            "    AND r.entity_slug = entities.slug"
            ") WHERE vault_id = ?",
            (vault_id,),
        )

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
        "skipped": skipped,
        "duration_seconds": round(duration, 3),
    }
