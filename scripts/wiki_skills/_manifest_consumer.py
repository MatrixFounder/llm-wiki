"""Neutral manifest-consumer module — sub-layer below the skills tier.

Created by TASK 003 / I-7.0 to break cross-skill coupling (Decision-16).
Both ``wiki_enrich.py`` (back-compat re-export) and ``wiki_extract_concepts.py``
(new in TASK 003 v2) import from this module so no skill depends on another
skill at IMPORT TIME for v1.1 manifest validation and SQLite-index mirroring.
(Note: ``index_from_manifest`` still reaches into ``wiki_index_upsert`` via a
lazy in-function import — runtime neutrality is therefore not absolute, but
the import graph at module load is clean.)

Public surface (the "integration contract"):
    - WikiIngestError       — exception raised on contract violations
    - validate_manifest()   — assert manifest conforms to WIKI-INGEST v1.1
    - index_from_manifest() — mirror manifest.written[] into SQLite +
                              insert manifest.log_event row

Function bodies moved verbatim from ``scripts.wiki_skills.wiki_enrich`` in
the TASK 003 I-7.0 refactor (Decision-16). The only semantic difference is
the rename ``_validate_manifest`` → ``validate_manifest`` (no leading
underscore — promoted to public). ``wiki_enrich.py`` preserves
``_validate_manifest = validate_manifest`` as a back-compat alias for one
release cycle.
"""
from __future__ import annotations

import contextlib
import io
import json
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


def index_from_manifest(manifest: dict[str, Any], vault_id: str,
                        vault_root: Path, db_path: str | None = None
                        ) -> dict[str, Any]:
    """For each manifest.written[].path → upsert into SQLite. Mirror
    manifest.log_event into log_events. Returns summary stats.

    Top-level system files (index.md, log.md, WIKI_SCHEMA.md, CLAUDE.md)
    are skipped — Class B/C per ADR-002 §D8: index.md is projected by
    wiki-index-render, log.md is mirrored via log_event below. Filter is
    top-level-only so legitimate subdir pages like ``_concepts/index.md``
    still reach upsert.
    """
    from scripts.wiki_skills.wiki_index_upsert import main as upsert_main

    upserted: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
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
        argv = [
            "--vault", vault_id,
            "--source", str(abs_path),
            "--vault-root", str(vault_root),
        ]
        if db_path:
            argv.extend(["--db-path", db_path])
        # wiki_index_upsert.main writes a JSON envelope to stdout; capture it.
        # Catch only EXPECTED failure modes — `OSError` for FS errors,
        # `ValueError` for frontmatter parse, `KeyError` for missing schema
        # fields, `RuntimeError` for explicit raise-with-context. Programming
        # errors (`MemoryError`, `RecursionError`, `AttributeError`, etc.)
        # MUST propagate — silently routing them to `failed[]` masked refactor
        # regressions per vdd-multi critic-logic C-1 + critic-security M-3.
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = upsert_main(argv)
        except (OSError, ValueError, KeyError, RuntimeError) as e:
            failed.append({"path": rel,
                           "envelope": {"error": type(e).__name__,
                                        "message": str(e)}})
            continue
        try:
            envelope = json.loads(buf.getvalue())
        except json.JSONDecodeError:
            # M-1 (vdd-multi 2026-05-28): the v3.1 envelope CWE-117
            # invariant (tested by 003-v3-17) forbids `raw` / `content`
            # / `value` / `received` keys in error envelopes — they
            # surface arbitrary downstream output (potentially including
            # sensitive vault content) into the final emitted payload.
            # Replace with a structured `reason` that emits only the
            # output LENGTH, not the bytes themselves. Operators can
            # find the full output in the application log if needed.
            raw_len = len(buf.getvalue())
            envelope = {
                "error": "BAD_UPSERT_OUTPUT",
                "reason": (f"wiki-index-upsert emitted non-JSON stdout "
                           f"({raw_len} bytes); see application log "
                           "for the raw output"),
            }
        if rc != 0 or "error" in envelope:
            failed.append({"path": rel, "envelope": envelope})
        else:
            upserted.append({"path": rel, "action": envelope.get("action", "?")})

    log_event_id: int | None = None
    log_event = manifest.get("log_event")
    if log_event and not failed:
        repo = make_repo({
            "vault_id": vault_id,
            **({"db_path": db_path} if db_path else {}),
        })
        try:
            ev_ts_raw = log_event.get("event_ts")
            ev_ts = (datetime.fromisoformat(ev_ts_raw) if ev_ts_raw
                     else datetime.now())
            log_event_id = repo.append_log_event(LogEvent(
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
            repo.close()

    return {
        "upserted": upserted,
        "failed": failed,
        "log_event_id": log_event_id,
    }
