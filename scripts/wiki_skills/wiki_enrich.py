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
from pathlib import Path
from typing import Any

from scripts.wiki_skills._common import build_repo_config, emit
# TASK 003 I-7.0 (Decision-16): manifest-consumer surface lives in the
# neutral sub-layer module `_manifest_consumer`. The three symbols below
# are re-exported here so existing test imports keep working for one
# release cycle (back-compat hatch — exercised by tests, NOT dead code).
from scripts.wiki_skills._manifest_consumer import (
    WikiIngestError,
    index_from_manifest,
    validate_manifest,
)

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

# Back-compat alias for one release cycle (TASK 003 I-7.0 acceptance bullet c).
# Existing tests in tests/test_wiki_enrich.py (lines 21, 98, 104, 112, 467)
# import `_validate_manifest` from this module — those imports stay pointed
# here so the alias is exercised by the test suite, not dead code. A
# follow-up bead (post-release) will deprecate it with DeprecationWarning
# and migrate the tests to import from `_manifest_consumer` directly.
_validate_manifest = validate_manifest


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
    # TASK 022 (M-2): resolve a vault-local index_db and thread it into the ingest so
    # wiki-enrich writes into the SAME DB as the rest of the vault (no split-brain).
    _db_path = build_repo_config(
        args.vault, vault_root=vault_root, db_path_flag=args.db_path).get("db_path")
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
        validate_manifest(manifest, args.vault, vault_root)
    except WikiIngestError as e:
        return emit({"error": "WIKI_INGEST_FAILED", "message": str(e)},
                    exit_code=6)

    summary = index_from_manifest(
        manifest, args.vault, vault_root, db_path=_db_path,
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
