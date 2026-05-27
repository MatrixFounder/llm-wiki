"""`wiki-enrich` CLI — bridge: wiki-ingest (file synthesis) → SQLite index.

ADR-001 Option I: wiki-ingest owns the file layer (LLM-driven additive merge
of concept/entity pages, log.md append). After each successful ingest it
emits a JSON manifest (WIKI-INGEST-V1.1-CONTRACT §1). This CLI consumes the
manifest and mirrors every written file into our SQLite index plus inserts
the structured log_event row.

Flow:
    1. Verify ``wiki-ingest --version`` >= 1.1 (fail-fast otherwise).
    2. Run ``wiki-ingest ingest --output-format json ...``; capture manifest.
    3. For each manifest.written[].path → call wiki_index_upsert.main([...]).
    4. INSERT manifest.log_event into log_events via wiki_append_log.
    5. Emit combined JSON ``{"ingest": <manifest>, "index": {...}}``.

Exit codes:
    0 — success
    1 — usage / arg error
    6 — wiki-ingest version too old, manifest schema invalid, vault mismatch,
        path-traversal, partial-index failure
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
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
from scripts.wiki_skills._common import emit

# ARCHITECTURE.md §1.5.2 path decision branch (TASK 004 R-47/R-48 / bead 004-05):
# Try to import the vendored `wiki_ingest` Python module. When import succeeds
# AND `WIKI_ENRICH_NO_VENDORED=1` is NOT set, `main()` calls `ingest()`
# in-process (PRIMARY path — no subprocess, no `check_wiki_ingest_version()`
# call, no PATH dependency). Otherwise falls back to the legacy subprocess
# path via `wiki-ingest` CLI (preserves R-56: standalone wiki-ingest users
# can keep using this script without installing the vendored copy).
import os
try:
    from scripts.wiki_ingest.commands.ingest import (
        IngestError as _VendoredIngestError,
        ingest as _vendored_ingest,
    )
    _VENDORED_AVAILABLE = True
except ImportError:
    _vendored_ingest = None  # type: ignore[assignment]
    _VendoredIngestError = None  # type: ignore[assignment,misc]
    _VENDORED_AVAILABLE = False

MIN_WIKI_INGEST_VERSION = (1, 1)


class WikiIngestError(Exception):
    """Raised on any wiki-ingest subprocess problem (missing, old, failed)."""


def _parse_semver(text: str) -> tuple[int, ...]:
    """Parse a string like ``wiki-ingest 1.1.2`` → ``(1, 1, 2)``.

    Accepts leading ``v`` and any trailing ``-rc1`` etc. (stripped).
    """
    digits: list[int] = []
    parts = text.strip().split()
    candidate = parts[-1] if parts else text.strip()
    candidate = candidate.lstrip("v")
    candidate = candidate.split("-", 1)[0]
    for chunk in candidate.split("."):
        try:
            digits.append(int(chunk))
        except ValueError:
            break
    return tuple(digits) if digits else (0,)


def check_wiki_ingest_version(
    binary: str = "wiki-ingest",
    minimum: tuple[int, ...] = MIN_WIKI_INGEST_VERSION,
) -> tuple[int, ...]:
    """Return parsed version tuple if `binary --version` >= minimum. Raise
    ``WikiIngestError`` on missing binary, parse failure, or too-old version."""
    if shutil.which(binary) is None:
        raise WikiIngestError(
            f"{binary} not found on PATH; install wiki-ingest v1.1+"
        )
    try:
        out = subprocess.run(
            [binary, "--version"],
            capture_output=True, text=True, check=False, timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        raise WikiIngestError(f"could not run {binary} --version: {e}") from e
    if out.returncode != 0:
        raise WikiIngestError(
            f"{binary} --version exit {out.returncode}: {out.stderr!r}"
        )
    version = _parse_semver(out.stdout)
    if version < minimum:
        raise WikiIngestError(
            f"{binary} version {version} < required {minimum}; "
            f"upgrade per docs/WIKI-INGEST-V1.1-CONTRACT.md"
        )
    return version


def run_wiki_ingest(
    binary: str, source: Path, vault_root: Path,
    extra_args: list[str] | None = None,
    timeout_seconds: int = 600,
) -> dict[str, Any]:
    """Invoke wiki-ingest ingest with JSON output. Returns parsed manifest."""
    argv = [
        binary, "ingest",
        "--source", str(source),
        "--vault", str(vault_root),
        "--output-format", "json",
    ]
    if extra_args:
        argv.extend(extra_args)
    try:
        out = subprocess.run(
            argv, capture_output=True, text=True, check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as e:
        raise WikiIngestError(f"wiki-ingest timed out after {timeout_seconds}s") from e
    if out.returncode != 0:
        raise WikiIngestError(
            f"wiki-ingest ingest exit {out.returncode}: {out.stderr!r}"
        )
    try:
        manifest: dict[str, Any] = json.loads(out.stdout)
    except json.JSONDecodeError as e:
        raise WikiIngestError(
            f"wiki-ingest stdout is not valid JSON: {e}; "
            f"first 200 chars: {out.stdout[:200]!r}"
        ) from e
    return manifest


def _validate_manifest(manifest: dict[str, Any], expected_vault_id: str,
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
    for entry in manifest["written"]:
        rel = entry.get("path")
        if not rel or not isinstance(rel, str):
            raise WikiIngestError(f"manifest written entry missing path: {entry}")
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
        # at the upsert boundary (_validate_manifest should have caught them,
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
        import io
        import contextlib

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
            envelope = {"error": "BAD_UPSERT_OUTPUT", "raw": buf.getvalue()}
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


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="wiki-enrich",
        description="Bridge wiki-ingest (file synthesis) → SQLite index",
    )
    p.add_argument("--vault", required=True, help="vault_id (must be registered)")
    p.add_argument("--vault-root", required=True, type=Path,
                   help="Absolute vault root path")
    p.add_argument("--source", required=True, type=Path,
                   help="Path to the raw source file")
    p.add_argument("--db-path", default=None,
                   help="Override default DB path (testing)")
    p.add_argument("--wiki-ingest-bin", default="wiki-ingest",
                   help="wiki-ingest binary name or path (default: wiki-ingest)")
    p.add_argument("--timeout-seconds", type=int, default=600)
    p.add_argument("--ingest-arg", action="append", default=[],
                   help="Extra argv passed through to wiki-ingest "
                        "(repeatable; e.g. --ingest-arg=--course=ZeroOne)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    vault_root = args.vault_root.resolve(strict=True)
    source = args.source.resolve(strict=True)

    # WIKI_ENRICH_NO_VENDORED accepts a truthy set (case-insensitive, stripped)
    # rather than exact-match "1" — operators following standard env-var
    # conventions ("true", "yes", "on") would otherwise silently get the
    # in-process path despite explicit downgrade intent. vdd-multi
    # critic-logic H-3 + critic-security M-2 (force-downgrade defense).
    _no_vendored_env = os.environ.get("WIKI_ENRICH_NO_VENDORED", "").strip().lower()
    _force_subprocess = _no_vendored_env in {"1", "true", "yes", "on"}
    use_vendored = _VENDORED_AVAILABLE and not _force_subprocess

    try:
        if use_vendored:
            # PRIMARY PATH (post-TASK-004): in-process call into vendored
            # ingest(). No subprocess. No check_wiki_ingest_version(). No
            # PATH dependency on `wiki-ingest`.
            assert _vendored_ingest is not None  # mypy: _VENDORED_AVAILABLE guard
            try:
                manifest = _vendored_ingest(
                    source=source,
                    vault=vault_root,
                    vault_id=args.vault,
                    source_hash=None,
                    known_concepts=None,
                    dry_run=False,
                    timeout_seconds=args.timeout_seconds,
                    quiet=True,
                )
            except Exception as e:
                # Vendored `IngestError` is a content-level failure (not a
                # transport failure); DO NOT fall back to subprocess. Emit
                # structured error envelope and exit 6.
                if (_VendoredIngestError is not None
                        and isinstance(e, _VendoredIngestError)):
                    # PARTIAL_INDEX_FAILURE carries `manifest_head` +
                    # `cleanup_advice` as dynamic attrs (set by vendored
                    # `ingest()`'s _PartialFailure catch block). Emit the
                    # FULL envelope shape (incl. manifest_version, vault_id,
                    # vault_root, course, source fields) to preserve R-56
                    # byte-identical contract on the primary path. Pre-fix
                    # this was truncated to {error, code, phase, written_so_far}
                    # — vdd-multi critic-logic H-1.
                    if getattr(e, "code", None) == "PARTIAL_INDEX_FAILURE":
                        head = getattr(e, "manifest_head", {}) or {}
                        return emit({
                            **head,
                            "status": "error",
                            "phase": getattr(e, "phase", None),
                            "code": "PARTIAL_INDEX_FAILURE",
                            "child_exit_code": getattr(e, "child_exit_code", 0),
                            "written_so_far": getattr(e, "written_so_far", []),
                            "cleanup_advice": getattr(e, "cleanup_advice", str(e)),
                        }, exit_code=6)
                    return emit({
                        "error": "WIKI_INGEST_FAILED",
                        "code": getattr(e, "code", "UNKNOWN"),
                        "phase": getattr(e, "phase", None),
                        "written_so_far": getattr(e, "written_so_far", []),
                        "message": str(e),
                    }, exit_code=6)
                raise
        else:
            # FALLBACK PATH: subprocess via `wiki-ingest` CLI on PATH.
            # Used when (a) vendored import failed, OR (b)
            # WIKI_ENRICH_NO_VENDORED=1 is set (escape hatch for debugging).
            # Pre-TASK-004 behavior preserved byte-for-byte.
            if shutil.which(args.wiki_ingest_bin) is None:
                return emit({
                    "error": "WIKI_INGEST_UNAVAILABLE",
                    "hint": ("vendored module not importable AND "
                             "wiki-ingest binary not on PATH. Install "
                             "wiki-ingest or unset WIKI_ENRICH_NO_VENDORED."),
                }, exit_code=6)
            check_wiki_ingest_version(args.wiki_ingest_bin)
            manifest = run_wiki_ingest(
                args.wiki_ingest_bin, source, vault_root,
                extra_args=list(args.ingest_arg),
                timeout_seconds=args.timeout_seconds,
            )
        _validate_manifest(manifest, args.vault, vault_root)
    except WikiIngestError as e:
        return emit({"error": "WIKI_INGEST_FAILED", "message": str(e)},
                    exit_code=6)

    summary = index_from_manifest(
        manifest, args.vault, vault_root, db_path=args.db_path,
    )
    if summary["failed"]:
        return emit({
            "action": "partial",
            "error": "PARTIAL_INDEX_FAILURE",
            "ingest": manifest,
            "index": summary,
        }, exit_code=6)
    return emit({
        "action": "enriched",
        "vault_id": args.vault,
        "ingest": manifest,
        "index": summary,
    })


if __name__ == "__main__":
    sys.exit(main())
