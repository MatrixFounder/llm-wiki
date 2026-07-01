"""Neutral manifest-consumer module — sub-layer below the skills tier.

Created by TASK 003 / I-7.0 to break cross-skill coupling (Decision-16).
``wiki_extract_concepts.py`` imports from this module (via ``wiki-index-upsert``'s
``upsert_one``) so no skill depends on another skill at IMPORT TIME for manifest
validation and SQLite-index mirroring. (Historically ``wiki_enrich.py`` also imported
it; that on-ramp was retired in TASK 047.)
TASK 015 / R-015-2 (H-PERF-3 + P-8): ``index_from_manifest`` now imports
``upsert_one`` at module load and accepts an optional ``repo`` parameter.
When provided, the caller's connection is reused (no new open/close cycle).

Public surface (the "integration contract"):
    - WikiIngestError       — exception raised on contract violations
    - validate_manifest()   — assert manifest conforms to WIKI-INGEST v1.1
    - index_from_manifest() — mirror manifest.written[] into SQLite +
                              insert manifest.log_event row

Function bodies originated in the ``wiki_enrich`` bridge (retired in TASK 047),
extracted here in the TASK 003 I-7.0 refactor (Decision-16); the only semantic
difference was the rename ``_validate_manifest`` → ``validate_manifest`` (promoted
to public). The module is retained: `wiki-extract-concepts --ingest` still mirrors a
concept manifest into the index through it.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout import SYSTEM_FILES
from scripts.wiki_index.models import LogEvent
from scripts.wiki_index.security import (
    PathTraversalError,
    validate_inside_vault,
)
from scripts.wiki_skills.wiki_index_upsert import upsert_one


class WikiIngestError(Exception):
    """Raised on any wiki-ingest subprocess problem (missing, old, failed)
    OR on v1.1 manifest contract violations consumed in-process."""


def validate_manifest(manifest: dict[str, Any], expected_vault_id: str,
                      vault_root: Path) -> None:
    """Check the manifest matches the WIKI-INGEST v1.1 contract surface used
    here. Raises WikiIngestError if any required field is missing or wrong."""
    if manifest.get("status") != "ok":
        raise WikiIngestError(
            f"manifest status != 'ok': {manifest.get('status')!r}"
        )
    if manifest.get("vault_id") != expected_vault_id:
        raise WikiIngestError(
            f"manifest vault_id {manifest.get('vault_id')!r} != "
            f"expected {expected_vault_id!r} (ADR-002 §D1.1 mismatch)"
        )
    if not isinstance(manifest.get("written"), list):
        raise WikiIngestError("manifest missing 'written[]' list")
    for idx, entry in enumerate(manifest["written"]):
        rel = entry.get("path")
        if not rel or not isinstance(rel, str):
            # M-1 (vdd-multi 2026-05-28): emit position only, not the
            # whole entry dict. Earlier wording echoed entry contents
            # into the error message, leaking through `str(e)` to the
            # MANIFEST_INVALID envelope (partial CWE-117).
            raise WikiIngestError(
                f"manifest written entry #{idx} missing 'path' key"
            )
        # R-26: paths must resolve inside vault_root.
        try:
            validate_inside_vault(vault_root / rel, vault_root)
        except (PathTraversalError, FileNotFoundError) as e:
            raise WikiIngestError(
                f"manifest path {rel!r} fails vault containment: {e}"
            ) from e


def index_from_manifest(
    manifest: dict[str, Any],
    vault_id: str,
    vault_root: Path,
    db_path: str | None = None,
    repo: Any = None,
) -> dict[str, Any]:
    """For each manifest.written[].path → upsert into SQLite. Mirror
    manifest.log_event into log_events. Returns summary stats.

    When ``repo`` is provided (not None), the caller owns the connection —
    it is reused directly and NOT closed here. When ``repo`` is None, one
    connection is opened and closed by this function (H-PERF-3 / P-8 fix).

    Top-level system files (index.md, log.md, WIKI_SCHEMA.md, and the per-vendor
    agent files CLAUDE.md/GEMINI.md — the full set is `layout.SYSTEM_FILES`)
    are skipped — Class B/C per ADR-002 §D8: index.md is projected by
    wiki-index-render, log.md is mirrored via log_event below. Filter is
    top-level-only so legitimate subdir pages like ``_concepts/index.md``
    still reach upsert.
    """
    _owns_repo = repo is None
    if _owns_repo:
        repo_to_use: Any = make_repo({
            "vault_id": vault_id,
            **({"db_path": db_path} if db_path else {}),
        })
    else:
        repo_to_use = repo

    upserted: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    log_event_id: int | None = None
    try:
        for entry in manifest["written"]:
            rel = entry["path"]
            # TODO: extend if promotion-spec introduces course-tier `Lessons/<C>/index.md`.
            rel_path = Path(rel)
            # vdd-multi critic-logic M-1: defense-in-depth — reject absolute paths
            # at the upsert boundary (validate_manifest should have caught them,
            # but if a future caller invokes index_from_manifest() directly
            # without validation, the system-file skip would be bypassed for an
            # absolute path like `/abs/index.md` and the upsert step would try
            # to read OUTSIDE the vault).
            if rel_path.is_absolute():
                failed.append({"path": rel,
                               "envelope": {"error": "ABSOLUTE_PATH_IN_MANIFEST",
                                            "message": f"manifest written entry has absolute path: {rel}"}})
                continue
            if rel_path.parent == Path(".") and rel_path.name in SYSTEM_FILES:
                continue
            abs_path = (vault_root / rel).resolve()
            # Catch only EXPECTED failure modes — `OSError` for FS errors,
            # `ValueError` for frontmatter parse, `KeyError` for missing schema
            # fields, `RuntimeError` for explicit raise-with-context. Programming
            # errors (`MemoryError`, `RecursionError`, `AttributeError`, etc.)
            # MUST propagate — silently routing them to `failed[]` masked refactor
            # regressions per vdd-multi critic-logic C-1 + critic-security M-3.
            try:
                result = upsert_one(vault_id, abs_path, vault_root, repo_to_use)
            except (OSError, ValueError, KeyError, RuntimeError) as e:
                failed.append({"path": rel,
                               "envelope": {"error": type(e).__name__,
                                            "message": str(e)}})
                continue
            exit_code: int = result.pop("_exit_code", 0)
            if exit_code != 0 or "error" in result:
                failed.append({"path": rel, "envelope": result})
            else:
                upserted.append({"path": rel, "action": result.get("action", "?")})

        log_event = manifest.get("log_event")
        if log_event and not failed:
            ev_ts_raw = log_event.get("event_ts")
            ev_ts = (datetime.fromisoformat(ev_ts_raw) if ev_ts_raw
                     else datetime.now())
            log_event_id = repo_to_use.append_log_event(LogEvent(
                vault_id=vault_id,
                event_ts=ev_ts,
                event_type=log_event.get("event_type", "ingest"),
                subject=log_event.get("subject"),
                pages_created_json=manifest.get("created", []),
                pages_updated_json=manifest.get("touched", []),
                details_json={
                    "source_slug": manifest.get("source", {}).get("slug"),
                    "source_hash": manifest.get("source", {}).get("hash"),
                    "llm_tokens_used": manifest.get("llm_tokens_used"),
                    "contradictions": manifest.get("contradictions", 0),
                },
                log_md_byte_offset=log_event.get("log_md_byte_offset"),
            ))
    finally:
        if _owns_repo:
            repo_to_use.close()

    return {
        "upserted": upserted,
        "failed": failed,
        "log_event_id": log_event_id,
    }
