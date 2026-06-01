"""`wiki-extract-concepts` CLI (v3.1) — deterministic concept-extraction skill.

Two subcommands:

* ``prepare`` — read the source summary page, compute its sha256, query
  ``source_state`` for ``is_unchanged``, load the vault's known concepts,
  sweep for disk/DB drift, emit a JSON recon envelope. NO LLM call.
* ``apply``   — consume the orchestrator-synthesised candidates JSON
  (``--candidates-file`` or ``--candidates-stdin``), hash-check against
  ``--source-hash`` from prepare, validate the schema (strict), write
  ``_concepts/<slug>.md`` pages (atomic + content-hash skip + symlink
  refuse + markdown sanitization), upsert entity rows + refs, emit a
  wiki-ingest v1.1-compatible manifest, optionally dispatch the manifest
  in-process to ``index_from_manifest`` from the neutral
  ``_manifest_consumer`` module (Decision-15 + Decision-16 — no
  subprocess, no cross-skill coupling).

Synthesis lives outside this skill (TASK 003 v3.1 / Decision-17). The
orchestrator runs ``prepare``, loads the ``concept-extraction`` skill
into its own context, reads the source body, generates candidates JSON,
and pipes them into ``apply``. This module makes ZERO model-provider
SDK calls (the v2 LLM-call code path was deleted in bead 003-v3-06).

Module-top import of the three neutral-consumer symbols is intentional
(stable ``unittest.mock.patch`` target — see PLAN R-1 patch-target lock).

Exit codes (R-42 v3.1 + vdd-multi 2026-05-28 hardening):
    0 — success (manifest or {extraction, index} envelope)
    1 — argparse / usage error
    2 — input-validation failure: SOURCE_NOT_FOUND | INVALID_SOURCE_PATH
        | INVALID_SOURCE_SLUG | SOURCE_TOO_LARGE |
        SOURCE_CHANGED_DURING_EXTRACTION | INVALID_CANDIDATES_PATH |
        INVALID_SOURCE_HASH (new in vdd-multi-fix C-1; library-caller
        defense — argparse already gates the CLI path)
    4 — candidates payload error: EXTRACTION_PARSE_ERROR |
        CANDIDATES_TOO_LARGE | CANDIDATE_COUNT_OUT_OF_BOUNDS |
        FIELD_TOO_LONG | UNKNOWN_FIELD | FIELD_QUOTE_NOT_IN_BODY |
        INVALID_NAME_FORMAT | INVALID_SOURCE_SPAN
    5 — PARTIAL_INDEX_FAILURE (with --ingest; source_state NOT updated
        per C-1 invariant so a retry is safe) OR
        IDEMPOTENCY_UPDATE_FAILED (new in vdd-multi-fix H-3; pages /
        entities / refs committed but source_state UPSERT raised
        OperationalError — next run will safely re-extract)
    6 — MANIFEST_INVALID (with --ingest)

(The v2 exit-3 envelope for upstream-API failures is retired in v3.1.)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout import (
    CONCEPTS_SUBDIR,
)
from scripts.wiki_skills._common import emit
from scripts.wiki_skills._common import (  # noqa: F401 — facade re-export for wec._sanitize_markdown_text
    sanitize_markdown_text as _sanitize_markdown_text,
)
# TASK 003 I-7.0 + I-7.11 (Decisions 15+16): module-top import locks the
# patch target as `scripts.wiki_skills.wiki_extract_concepts.<symbol>`.
from scripts.wiki_skills._manifest_consumer import (
    WikiIngestError,
    index_from_manifest,
    validate_manifest,
)


# ============================================================================
# Stub-only exception classes (real raises land in 003-04)
# ============================================================================


# TASK 016: error types extracted to the `_errors` leaf (the dependency sink).
# Imported here so `wec.ExtractionParseError` / `wec._envelope_from_parse_error`
# stay resolvable on the facade.
from ._errors import ExtractionParseError, _envelope_from_parse_error  # noqa: E402
# TASK 016 bead 016-03: validation/sanitization leaf re-export.
# Every moved symbol is re-exported here so `wec.<name>` stays resolvable
# and external tests / the facade's own call-sites resolve via the facade.
from ._validation import (  # noqa: E402
    _SOURCE_SPAN_RE,
    _SLUG_RE,
    _ALLOWED_ENTITY_TYPES,
    _SOURCE_HASH_RE,
    _ORCHESTRATOR_ID_RE,
    _REQUIRED_CANDIDATE_KEYS,
    _CANDIDATE_COUNT_MIN,
    _CANDIDATE_COUNT_MAX,
    _FIELD_CAPS,
    _NAME_ALLOWLIST,
    _SPAN_REGEX,
    _path_is_absolute,
    _validate_source_hash,
    _validate_orchestrator_id,
    _validate_candidates_schema,
    classify_candidates,
    _sanitize_name,
    _sanitize_definition,
    _parse_source_span,
    _preflight_sanitize,
)
# TASK 016 bead 016-04: source-IO / path-resolution leaf re-export.
from ._sourcing import (  # noqa: E402
    _MAX_SOURCE_BODY_BYTES,
    _MAX_CANDIDATES_BYTES,
    _FileTooLargeError,
    _read_file_bounded,
    _resolve_source_inside_sources,
    _all_concepts_dirs,
    _derive_source_project,
    _load_candidates,
)


# TASK 016 bead 016-06: DB / entity / manifest leaf re-export.
# CARVE-OUT (R-016-2): `load_known_entities` + `update_idempotency_state` are
# monkeypatched at the facade; importing them here makes them facade globals,
# and the facade callers (_load_known_and_drift / _apply_write / apply call
# load_known_entities; _try_update_idempotency_state calls
# update_idempotency_state) reference them as bare names → `mock.patch(wec.<n>)`
# intercepts. `_SOURCE_KIND` relocated here (its only consumers are below).
from ._db import (  # noqa: E402
    _SOURCE_KIND,
    load_known_entities,
    _lookup_entity_row,
    upsert_extracted_entity,
    upsert_entity_refs,
    check_idempotency,
    update_idempotency_state,
    build_manifest,
)
# TASK 016 bead 016-05: concept-page writing leaf re-export.
from ._pages import write_concept_page, _format_source_quote_block  # noqa: E402


def dispatch_to_indexer(
    manifest_dict: dict[str, Any],
    vault_id: str,
    vault_root: Path,
    db_path: str | None,
    repo: Any = None,
) -> dict[str, Any]:
    """In-process dispatch to the neutral manifest consumer (Decision-15).

    Calls ``validate_manifest`` then ``index_from_manifest`` from
    ``_manifest_consumer`` — both bound at module top of this file
    (003-01 patch-target lock; tests patch
    ``scripts.wiki_skills.wiki_extract_concepts.<symbol>``, NOT the
    source-of-truth module). Raises ``WikiIngestError`` on contract
    violation (caller maps to exit 6).

    TASK 015 / R-015-2: when ``repo`` is provided the caller's already-open
    connection is reused (no second open/PRAGMA-sweep cycle); the caller
    retains lifecycle ownership. When None, ``index_from_manifest`` opens
    and closes its own.
    """
    validate_manifest(manifest_dict, vault_id, vault_root)
    return index_from_manifest(
        manifest_dict,
        vault_id,
        vault_root,
        db_path=db_path,
        repo=repo,
    )


# ============================================================================
# argparse + main
# ============================================================================


def _build_parser_v3() -> argparse.ArgumentParser:
    """v3.1 argparse surface (Decision-17): two subcommands, calling-agent
    drives synthesis. `prepare` does deterministic recon + idempotency check;
    `apply` consumes operator-synthesized candidates JSON and writes pages +
    entities + manifest. Legacy single-command invocation now fails at
    argparse with a `prepare`/`apply` hint (H-4 BREAKING CHANGE).
    """
    p = argparse.ArgumentParser(
        prog="wiki-extract-concepts",
        description=(
            "Deterministic concept-extraction skill (v3.1). "
            "Calling agent runs `prepare` (recon), synthesises candidates "
            "JSON in its own context, then runs `apply` to write pages + "
            "entities + manifest. BREAKING CHANGE vs v2: legacy single-"
            "command shape is no longer accepted."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True,
                           metavar="{prepare,apply}")

    # ---- prepare subparser ----
    pp = sub.add_parser("prepare",
                        help="Recon + idempotency check; emits JSON envelope.")
    pp.add_argument("--vault", required=True,
                    help="Vault ID (must be registered in vaults table)")
    pp.add_argument("--vault-root", required=True, type=Path,
                    help="Absolute path to vault root directory")
    # R-015-4: single-page (--source-page) XOR batch (--batch slugs.json).
    pp_src = pp.add_mutually_exclusive_group(required=True)
    pp_src.add_argument(
        "--source-page",
        help="Source page slug or relative path within vault "
             "(mutex with --batch)",
    )
    pp_src.add_argument(
        "--batch",
        metavar="SLUGS_JSON",
        help="Path to a JSON file containing a list of source-page slugs "
             "(mutex with --source-page). One batch prepare invocation; "
             "known_concepts + concept-file drift swept ONCE and shared "
             "across all entries.",
    )
    pp.add_argument("--db-path", default=None,
                    help="Override global DB path (default: standard XDG location)")
    pp.add_argument(
        "--known-concepts-format",
        choices=["full", "slugs-only"],
        default="full",
        dest="known_concepts_format",
        help="Format of the known_concepts field: 'full' (default) = "
             "[{slug,name,type,aliases},…]; 'slugs-only' = [slug,…]. "
             "Use slugs-only to reduce payload size at scale.",
    )

    # ---- apply subparser ----
    pa = sub.add_parser("apply",
                        help="Consume candidates JSON, write pages + manifest.")
    pa.add_argument("--vault", required=True,
                    help="Vault ID (must be registered in vaults table)")
    pa.add_argument("--vault-root", required=True, type=Path,
                    help="Absolute path to vault root directory")
    # R-015-5: --source-page / --source-hash are required for single-page
    # apply but NOT for --batch-candidates (each batch entry carries its own
    # source_slug + source_hash). argparse can't express "required-unless",
    # so they are optional here and apply() enforces presence on the
    # single-page path (REQUIRED_FOR_SINGLE_PAGE guard).
    pa.add_argument("--source-page", default=None,
                    help="Source page slug or relative path within vault "
                         "(required for single-page apply; omit with "
                         "--batch-candidates)")
    pa.add_argument("--db-path", default=None,
                    help="Override global DB path (default: standard XDG location)")
    pa.add_argument("--source-hash", default=None,
                    type=_validate_source_hash,
                    help="sha256 hex (64 lowercase hex chars) of the source "
                         "body, as emitted by `prepare`; mismatch → "
                         "SOURCE_CHANGED_DURING_EXTRACTION (Q5). Case-"
                         "normalized to lowercase at argparse time (C-1). "
                         "Required for single-page apply; omit with "
                         "--batch-candidates (per-entry hash instead).")
    pa.add_argument("--ingest", action="store_true",
                    help="In-process indexer dispatch (Decision-15) — "
                         "call index_from_manifest after manifest emit")
    pa.add_argument("--orchestrator-id",
                    type=_validate_orchestrator_id,
                    default="orchestrator",
                    help="Free-form orchestrator identifier "
                         "(e.g., 'claude-opus-4-7'). Populates "
                         "entities.canonicalized_by. Regex: "
                         f"{_ORCHESTRATOR_ID_RE.pattern}. "
                         "Default: literal 'orchestrator' (Q9-v3.1).")
    cand_group = pa.add_mutually_exclusive_group(required=True)
    cand_group.add_argument("--candidates-file", type=Path, default=None,
                            help="Path to JSON file inside the vault with candidates "
                                 "array (mutex with --candidates-stdin).")
    cand_group.add_argument("--candidates-stdin", action="store_true",
                            help="Read candidates JSON from stdin "
                                 "(mutex with --candidates-file).")
    cand_group.add_argument(
        "--batch-candidates",
        metavar="COMBINED_JSON",
        type=Path,
        default=None,
        help="Path to a combined batch-candidates JSON file (mutex with "
             "--candidates-file/--candidates-stdin). Schema: "
             "[{source_slug, source_hash, candidates:[…]}, …]. One repo "
             "is reused across all entries (R-015-5).",
    )
    return p


def prepare(args: argparse.Namespace) -> int:
    """`wiki-extract-concepts prepare` subcommand (v3.1).

    Deterministic recon + idempotency check. Reads the source page, computes
    sha256, queries source_state for is_unchanged, loads known entities, and
    builds a missing_concept_files drift list. Emits a JSON envelope the
    calling orchestrator consumes to decide whether to short-circuit (UC-09
    v3.1 is_unchanged path) or proceed to LLM-driven synthesis + `apply`.

    No LLM call in this path — Decision-17.
    """
    # R-015-4: batch dispatch (mutex with --source-page at argparse).
    if getattr(args, "batch", None):
        return _batch_prepare(args)

    vault_root = args.vault_root.resolve(strict=True)
    repo = make_repo({
        "vault_id": args.vault,
        **({"db_path": args.db_path} if args.db_path else {}),
    })
    try:
        known_out, missing_concept_files = _load_known_and_drift(
            repo, args.vault, vault_root,
            getattr(args, "known_concepts_format", "full"),
        )
        result = _recon_single(
            args.source_page, vault_root, args.vault, repo,
            known_out, missing_concept_files,
        )
        if "error" in result:
            return emit(result, exit_code=2)
        return emit(result)
    finally:
        repo.close()


def _load_known_and_drift(
    repo: Any,
    vault_id: str,
    vault_root: Path,
    known_concepts_format: str,
) -> tuple[list[dict[str, Any]] | list[str], list[str]]:
    """Load known_concepts (in the requested envelope format) and the
    concept-file drift list. Both are SOURCE-PAGE-INDEPENDENT, so a batch
    invocation computes them ONCE and shares them across every entry
    (R-015-4 / P-7: known_concepts loaded once; drift swept once).

    Returns ``(known_out, missing_concept_files)`` where ``known_out`` is a
    list of dicts (``full``) or a list of slug strings (``slugs-only``).
    """
    known = load_known_entities(repo, vault_id)
    known_slugs = [e["slug"] for e in known]
    if known_concepts_format == "slugs-only":
        # R-015-3 / slugs-only: reuse the already-built known_slugs
        # (avoid a redundant O(n) second pass over `known`).
        known_out: list[dict[str, Any]] | list[str] = known_slugs
    else:
        known_out = known

    # M-7: one os.scandir per `_concepts/` dir found in the vault.
    # Course-tier layout (Karpathy / Lessons pattern) puts concept
    # pages under `Lessons/<Course>/_concepts/` — sweep BOTH tiers
    # so the drift report is correct on any layout.
    present_concept_files: set[str] = set()
    for concepts_dir in _all_concepts_dirs(vault_root):
        for entry in os.scandir(concepts_dir):
            if entry.is_file() and entry.name.endswith(".md"):
                present_concept_files.add(entry.name[:-3])  # strip .md
    missing_concept_files = sorted(
        slug for slug in known_slugs if slug not in present_concept_files
    )
    return known_out, missing_concept_files


def _recon_single(
    source_page_arg: str,
    vault_root: Path,
    vault_id: str,
    repo: Any,
    known_out: list[dict[str, Any]] | list[str],
    missing_concept_files: list[str],
    include_known: bool = True,
) -> dict[str, Any]:
    """Per-source-page deterministic recon. PURE: no ``emit()``, no
    ``repo.close()`` — the caller owns I/O and the repo lifecycle.

    Returns the recon envelope dict on success, or an error dict
    (``{source_slug, error, message|reason}``) on failure. ``prepare()``
    maps an error dict to ``emit(err, exit_code=2)``; ``_batch_prepare()``
    appends it as a non-fatal per-entry result (R-015-4d isolation).

    ``known_out`` + ``missing_concept_files`` are pre-loaded ONCE by the
    caller and shared across batch entries (both are source-independent).
    ``include_known`` (R-015-4 / P-6 perf): single-page embeds them inline in
    the envelope; the batch path sets it False and emits them ONCE at the
    batch top level — otherwise json.dumps would re-serialize the full
    known_concepts list per entry → O(N·|known|) stdout, re-inflating the
    very payload P-6 set out to shrink.
    """
    # H-1: absolute --source-page → INVALID_SOURCE_PATH (distinct from
    # SOURCE_NOT_FOUND). Fire BEFORE any other resolution work.
    if _path_is_absolute(source_page_arg):
        return {
            "source_slug": source_page_arg,
            "error": "INVALID_SOURCE_PATH",
            "message": (f"--source-page must be a vault-relative slug or "
                        f"path, not absolute ({source_page_arg!r}). Pass "
                        "the page slug (e.g., 'self-improving-agent') or a "
                        "relative path inside --vault-root."),
        }

    resolved = _resolve_source_inside_sources(source_page_arg, vault_root)
    if isinstance(resolved, dict):  # error envelope
        return {**resolved, "source_slug": source_page_arg}
    source_path, source_slug = resolved

    # M-3 + M-5: stat-check size BEFORE read AND read via O_NOFOLLOW so
    # a symlink swap between resolve and read can't redirect to a file
    # outside the vault. ELOOP/race → SOURCE_NOT_FOUND envelope.
    try:
        source_body_bytes = _read_file_bounded(
            source_path, _MAX_SOURCE_BODY_BYTES,
        )
    except _FileTooLargeError:
        return {
            "source_slug": source_slug,
            "error": "SOURCE_TOO_LARGE",
            "reason": (f"source-page exceeds the {_MAX_SOURCE_BODY_BYTES}-byte "
                       "cap (10 MiB); refuse to read into memory."),
        }
    except OSError:
        return {
            "source_slug": source_slug,
            "error": "SOURCE_NOT_FOUND",
            "reason": (f"source-page {source_page_arg!r} could not be opened "
                       "(symlink swap race or transient I/O error)"),
        }
    source_hash = hashlib.sha256(source_body_bytes).hexdigest()
    is_unchanged = check_idempotency(repo, vault_id, source_slug, source_hash)

    # M-2: emit RELATIVE source_path instead of absolute. CWE-209: stop
    # leaking operator home directory / vault location into logs.
    try:
        source_path_rel = str(source_path.relative_to(vault_root))
    except ValueError:
        source_path_rel = str(source_path)  # defensive (shouldn't happen)

    entry: dict[str, Any] = {
        "vault_id": vault_id,
        "source_slug": source_slug,
        "source_path": source_path_rel,
        "source_hash": source_hash,
        "is_unchanged": is_unchanged,
    }
    if include_known:
        # Single-page: embed inline (backward-compatible envelope). Batch
        # omits these — they are emitted ONCE at the batch top level.
        entry["known_concepts"] = known_out
        entry["missing_concept_files"] = missing_concept_files
    return entry


def _batch_prepare(args: argparse.Namespace) -> int:
    """`prepare --batch <slugs.json>` (R-015-4 / P-7).

    Reads a JSON array of source-page slugs, loads known_concepts + concept
    drift ONCE, then runs per-slug recon with per-entry error isolation
    (one bad slug never aborts the batch). ``known_concepts`` +
    ``missing_concept_files`` are emitted ONCE at the top level (NOT per
    entry — avoids O(N·|known|) stdout, P-6); each entry carries only its
    own ``{source_slug, source_path, source_hash, is_unchanged}`` (or error).
    Emits ``{"known_concepts": […], "missing_concept_files": […],
    "batch": [entry, …]}``.
    """
    batch_path = Path(args.batch)
    try:
        raw = _read_file_bounded(batch_path, _MAX_SOURCE_BODY_BYTES)
    except _FileTooLargeError:
        return emit({"error": "INVALID_BATCH_FILE",
                     "reason": (f"batch file exceeds the "
                                f"{_MAX_SOURCE_BODY_BYTES}-byte cap")},
                    exit_code=2)
    except OSError:
        return emit({"error": "INVALID_BATCH_FILE",
                     "reason": "batch file could not be opened"},
                    exit_code=2)
    try:
        slugs = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return emit({"error": "INVALID_BATCH_FILE",
                     "reason": "batch file is not valid UTF-8 JSON"},
                    exit_code=2)
    if (not isinstance(slugs, list) or not slugs
            or not all(isinstance(s, str) for s in slugs)):
        return emit({"error": "INVALID_BATCH_FILE",
                     "reason": "must be a non-empty JSON array of strings"},
                    exit_code=2)

    vault_root = args.vault_root.resolve(strict=True)
    repo = make_repo({
        "vault_id": args.vault,
        **({"db_path": args.db_path} if args.db_path else {}),
    })
    try:
        known_out, missing_concept_files = _load_known_and_drift(
            repo, args.vault, vault_root,
            getattr(args, "known_concepts_format", "full"),
        )
        entries = [
            _recon_single(slug, vault_root, args.vault, repo,
                          known_out, missing_concept_files,
                          include_known=False)
            for slug in slugs
        ]
    finally:
        repo.close()
    return emit({
        "known_concepts": known_out,
        "missing_concept_files": missing_concept_files,
        "batch": entries,
    })


def apply(args: argparse.Namespace) -> int:
    """`wiki-extract-concepts apply` subcommand (v3.1).

    Consumes operator-synthesised candidates JSON and writes pages +
    entities + manifest. Hash-checks the source body against the
    `--source-hash` emitted by `prepare` so an edit-during-extraction
    race surfaces as a clean exit 2 SOURCE_CHANGED_DURING_EXTRACTION
    envelope (H-1, Q5) instead of corrupting the manifest.

    Exit codes (R-42):
      0 — success (manifest or {extraction, index} envelope)
      2 — input validation (INVALID_SOURCE_PATH, SOURCE_NOT_FOUND,
          INVALID_SOURCE_SLUG, SOURCE_TOO_LARGE,
          SOURCE_CHANGED_DURING_EXTRACTION, INVALID_CANDIDATES_PATH)
      4 — candidates payload errors (CANDIDATES_TOO_LARGE,
          EXTRACTION_PARSE_ERROR, UNKNOWN_FIELD, FIELD_TOO_LONG,
          CANDIDATE_COUNT_OUT_OF_BOUNDS, FIELD_QUOTE_NOT_IN_BODY)
      5 — PARTIAL_INDEX_FAILURE (some concept pages written, indexer
          rejected at least one; source_state NOT updated so a retry is
          safe — C-1 invariant carried forward from v2);
          IDEMPOTENCY_UPDATE_FAILED (H-3 DB-lock graceful path);
          DB_WRITE_FAILED (a `sqlite3.Error` — e.g. a FOREIGN KEY failure
          when the source page isn't indexed yet — caught as a clean
          envelope instead of a traceback; source_state NOT updated → retry
          safe; parity with the batch path's per-entry sqlite3.Error catch)
      6 — MANIFEST_INVALID
    """
    # R-015-5: batch dispatch (mutex with --candidates-file/stdin at
    # argparse). `getattr` guards library/test callers that build a
    # Namespace directly without the batch attribute.
    if getattr(args, "batch_candidates", None) is not None:
        return _batch_apply(args)

    vault_root = args.vault_root.resolve(strict=True)

    # R-015-5: --source-page / --source-hash are optional at argparse so
    # --batch-candidates can omit them; the single-page path requires both.
    if args.source_page is None or args.source_hash is None:
        return emit({
            "error": "MISSING_REQUIRED_ARG",
            "reason": ("single-page apply requires --source-page and "
                       "--source-hash; use --batch-candidates for the "
                       "batch path (per-entry slug + hash)."),
        }, exit_code=2)

    # Step 1 — load candidates (cap + path-validate + parse).
    try:
        candidates = _load_candidates(args, vault_root)
    except ExtractionParseError as e:
        envelope = _envelope_from_parse_error(e)
        exit_code = 2 if envelope["error"] == "INVALID_CANDIDATES_PATH" else 4
        return emit(envelope, exit_code=exit_code)

    orchestrator_id_val = getattr(args, "orchestrator_id", "orchestrator")

    # Validate source/hash/schema BEFORE opening the DB: input-validation
    # errors must not touch the repo (preserves the pre-R-015-5 ordering
    # contract exercised by the CWE-117 canary tests, and lets the batch
    # path reuse the same validator).
    validated = _apply_validate(
        args.source_page, args.source_hash, vault_root, candidates,
    )
    v_exit = validated.pop("_exit_code", 0)
    if v_exit != 0:
        return emit(validated, exit_code=v_exit)

    today = date.today()
    repo = make_repo({
        "vault_id": args.vault,
        **({"db_path": args.db_path} if args.db_path else {}),
    })
    try:
        # Step 5 (write) on the open repo; R-015-5d shares this with batch.
        result = _apply_write(
            validated, args.vault, vault_root, candidates,
            orchestrator_id_val, today, repo,
        )
        exit_code = result.pop("_exit_code", 0)
        if exit_code != 0:
            return emit(result, exit_code=exit_code)
        manifest = result["_manifest"]
        source_slug = result["source_slug"]
        current_hash = result["source_hash"]

        if args.ingest:
            try:
                # R-015-2: reuse apply's already-open repo so the upsert
                # loop + log_event append run on one connection (no second
                # PRAGMA/WAL setup cycle). apply owns repo.close() (its finally).
                summary = dispatch_to_indexer(
                    manifest, args.vault, vault_root, args.db_path,
                    repo=repo,
                )
            except WikiIngestError as e:
                return emit({"error": "MANIFEST_INVALID",
                             "reason": str(e)}, exit_code=6)
            if summary.get("failed"):
                # C-1 invariant: do NOT update_idempotency_state on
                # partial failure so the next run retries.
                return emit({
                    "action": "partial",
                    "error": "PARTIAL_INDEX_FAILURE",
                    "extraction": manifest,
                    "index": summary,
                }, exit_code=5)
            if not _try_update_idempotency_state(
                repo, args.vault, source_slug, current_hash, manifest,
            ):
                return emit({
                    "action": "partial",
                    "error": "IDEMPOTENCY_UPDATE_FAILED",
                    "extraction": manifest,
                    "index": summary,
                    "reason": ("pages/entities/indexer all committed, "
                               "but source_state update failed; next "
                               "run will safely re-extract"),
                }, exit_code=5)
            return emit({"extraction": manifest, "index": summary})

        if not _try_update_idempotency_state(
            repo, args.vault, source_slug, current_hash, manifest,
        ):
            # Pages + entities + refs committed; only source_state row
            # update failed. Treat as PARTIAL (exit 5) so the operator
            # knows retry-safety is degraded.
            return emit({
                "action": "partial",
                "error": "IDEMPOTENCY_UPDATE_FAILED",
                "extraction": manifest,
                "reason": ("pages/entities/refs committed, but "
                           "source_state update failed; next run will "
                           "safely re-extract"),
            }, exit_code=5)
        return emit(manifest)
    except sqlite3.Error as e:
        # A DB-layer fault during the entity/ref write (`_apply_write`) or the
        # `--ingest` dispatch — most commonly a FOREIGN KEY failure because the
        # source page is not yet in `pages` (run `wiki-reindex` first), or a
        # transient lock / disk-full. Return a clean envelope instead of an
        # uncaught traceback — parity with the batch path's per-entry
        # `sqlite3.Error` isolation. Concept pages/entities may be partially
        # written and `source_state` is NOT updated → exit 5, retry is safe.
        # sqlite3 messages carry no bound-parameter values (CWE-209 safe).
        return emit({
            "action": "partial",
            "error": "DB_WRITE_FAILED",
            "reason": (f"database write failed ({type(e).__name__}: {e}). "
                       "If this is a FOREIGN KEY failure, the source page is "
                       "likely not indexed yet — run `wiki-reindex` first."),
        }, exit_code=5)
    finally:
        repo.close()


def _apply_validate(
    source_page_arg: str,
    source_hash_expected: str | None,
    vault_root: Path,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Steps 2–4 of ``apply()`` — pure input validation, NO repo, NO writes.

    Returns ``{"source_path", "source_slug", "current_hash", "_exit_code": 0}``
    on success, or an error envelope ``{"error", "reason"|…, "_exit_code"}``.
    Kept separate from the write so the single-page path can validate BEFORE
    opening the DB (input errors must not touch the repo — the pre-R-015-5
    ordering contract guarded by the CWE-117 canary tests).

      2. resolve + bounded-read the source page (O_NOFOLLOW, M-3/M-5)
      3. recompute sha256 + hash-check vs ``source_hash_expected`` (Q5/C-1)
      4. strict candidates-schema validation + sanitization pre-flight (M-4)
    """
    # Step 2 — resolve + read source (H-1 / M-6 gating, same as prepare()).
    if _path_is_absolute(source_page_arg):
        return {
            "error": "INVALID_SOURCE_PATH",
            "reason": (f"--source-page must be a vault-relative slug or "
                       f"path, not absolute ({source_page_arg!r})."),
            "_exit_code": 2,
        }
    resolved = _resolve_source_inside_sources(source_page_arg, vault_root)
    if isinstance(resolved, dict):
        return {**resolved, "_exit_code": 2}
    source_path, source_slug = resolved
    try:
        source_body_bytes = _read_file_bounded(
            source_path, _MAX_SOURCE_BODY_BYTES,
        )
    except _FileTooLargeError:
        return {
            "error": "SOURCE_TOO_LARGE",
            "reason": (f"source-page exceeds the {_MAX_SOURCE_BODY_BYTES}-byte "
                       "cap (10 MiB); refuse to read into memory."),
            "_exit_code": 2,
        }
    except OSError:
        return {
            "error": "SOURCE_NOT_FOUND",
            "reason": (f"source-page {source_page_arg!r} could not be opened "
                       "(symlink swap race or transient I/O error)"),
            "_exit_code": 2,
        }
    source_body = source_body_bytes.decode("utf-8")
    current_hash = hashlib.sha256(source_body_bytes).hexdigest()

    # Step 3 — hash check (H-1, Q5 + C-1). Belt-and-braces re-validation of
    # the supplied hash (batch entries bypass argparse's _validate_source_hash;
    # so do library/test callers). Truncated prefixes only — never the full
    # body or supplied hash.
    supplied_hash = str(source_hash_expected).lower()
    if not _SOURCE_HASH_RE.match(supplied_hash):
        return {
            "error": "INVALID_SOURCE_HASH",
            "reason": ("--source-hash must be exactly 64 lowercase hex "
                       "chars (sha256 hex digest from `prepare`)"),
            "_exit_code": 2,
        }
    if current_hash != supplied_hash:
        return {
            "error": "SOURCE_CHANGED_DURING_EXTRACTION",
            "reason": (f"expected={supplied_hash[:16]}, "
                       f"got={current_hash[:16]} "
                       "(source body changed between prepare and apply; "
                       "re-run prepare to refresh)"),
            "_exit_code": 2,
        }

    # Step 4 — strict schema validation + sanitization pre-flight (M-4).
    try:
        _validate_candidates_schema(candidates, source_body=source_body)
        _preflight_sanitize(candidates)
    except ExtractionParseError as e:
        env = _envelope_from_parse_error(e)
        env["_exit_code"] = 4
        return env

    return {
        "source_path": source_path,
        "source_slug": source_slug,
        "current_hash": current_hash,
        "_exit_code": 0,
    }


def _apply_write(
    validated: dict[str, Any],
    vault_id: str,
    vault_root: Path,
    candidates: list[dict[str, Any]],
    orchestrator_id: str,
    today: date,
    repo: Any,
    known_slugs: set[str] | None = None,
) -> dict[str, Any]:
    """Step 5 of ``apply()`` — write pages + entities + refs + manifest on an
    ALREADY-OPEN repo (caller owns lifecycle: does NOT close it, does NOT
    emit, does NOT dispatch to the indexer, does NOT update idempotency).

    ``validated`` is the success dict from :func:`_apply_validate`. Returns
    ``{"_manifest", "source_slug", "source_hash", "_exit_code": 0}`` on
    success, or an exit-4 error envelope if a downstream parser raises.

    ``known_slugs`` (R-015-5 / P-7 perf): when None (single-page), the known
    entity slugs are loaded fresh here. When a set is passed (batch), the
    caller has loaded them ONCE; this function reuses it and MUTATES it in
    place — each newly-created entity slug is added so the NEXT batch entry
    dedups against it WITHOUT re-scanning the entities table (O(E) once
    instead of O(N·E)).
    """
    source_path: Path = validated["source_path"]
    source_slug: str = validated["source_slug"]
    current_hash: str = validated["current_hash"]

    # M-9: warn when --orchestrator-id omitted (opaque provenance). Fires
    # only once validation has passed and we are about to write — same
    # position relative to the write as the former monolithic apply().
    if orchestrator_id == "orchestrator":
        logger.warning(
            "apply: --orchestrator-id not supplied; entity provenance "
            "will record opaque literal 'orchestrator'. Pass "
            "--orchestrator-id <model-id> for an auditable canonicalized_by."
        )

    # Symmetric to the source-side H-1 layout invariant: concept pages land
    # in the `_concepts/` sibling of the source page's `_sources/`.
    # `pages.project` is derived from the source path so the page_entity_refs
    # FK matches the indexer's recorded value.
    target_concepts_dir = source_path.parent.parent / CONCEPTS_SUBDIR
    source_project = _derive_source_project(source_path, vault_root)
    try:
        if known_slugs is None:
            known = load_known_entities(repo, vault_id)
            known_slugs = {e["slug"] for e in known}
        create_list, mention_list = classify_candidates(candidates, known_slugs)

        for cand in create_list:
            _target, file_action = write_concept_page(
                vault_root, cand, source_slug, today, vault_id=vault_id,
                concepts_dir=target_concepts_dir,
            )
            cand["file_write_action"] = file_action
            cand["entity_action"] = upsert_extracted_entity(
                repo, vault_id, cand, source_slug, today,
                orchestrator_id=orchestrator_id,
            )
            # Augment the shared set so a later batch entry mentioning this
            # just-created concept classifies it as `mention`, not a dup
            # `create` — exactly what a fresh load_known_entities would show.
            known_slugs.add(cand["slug"])

        upsert_entity_refs(
            repo, vault_id, source_slug, source_project,
            create_list + mention_list,
        )

        log_event = {
            "event_ts": today.isoformat() + "T00:00:00",
            "event_type": "ingest",
            "subject": source_slug,
        }
        manifest = build_manifest(
            vault_id, source_slug, current_hash,
            create_list, mention_list, log_event, vault_root,
        )
    except ExtractionParseError as e:
        # v2 parity: downstream raises (e.g. _parse_source_span on an
        # inverted L10-L5 range that the regex validator passed) map to
        # exit 4 with the structured envelope.
        env = _envelope_from_parse_error(e)
        env["_exit_code"] = 4
        return env

    return {
        "_manifest": manifest,
        "source_slug": source_slug,
        "source_hash": current_hash,
        "_exit_code": 0,
    }


def _apply_candidates_to_db(
    source_page_arg: str,
    source_hash_expected: str | None,
    vault_id: str,
    vault_root: Path,
    candidates: list[dict[str, Any]],
    orchestrator_id: str,
    today: date,
    repo: Any,
    known_slugs: set[str] | None = None,
) -> dict[str, Any]:
    """Validate + write ONE source page's candidates on an already-open repo
    (R-015-5d). Thin combiner over :func:`_apply_validate` +
    :func:`_apply_write` used by the batch path, where the shared repo is
    legitimately open for every entry. Returns the same envelope shape as
    ``_apply_write`` (or the validation error envelope, with ``_exit_code``).

    ``known_slugs`` is threaded to :func:`_apply_write` so a batch caller can
    load known entities ONCE and have the set grow in place across entries.
    """
    validated = _apply_validate(
        source_page_arg, source_hash_expected, vault_root, candidates,
    )
    if validated.get("_exit_code", 0) != 0:
        return validated
    return _apply_write(
        validated, vault_id, vault_root, candidates,
        orchestrator_id, today, repo, known_slugs=known_slugs,
    )


def _batch_apply(args: argparse.Namespace) -> int:
    """`apply --batch-candidates <combined.json>` (R-015-5 / P-7).

    Schema: ``[{source_slug, source_hash, candidates:[…]}, …]`` — one entry
    per source page. Opens ONE repo reused across every entry (R-015-5d).
    Per-entry isolation: a failed entry records an error and the batch
    continues. When ``--ingest`` is set, ``index_from_manifest`` is dispatched
    once per entry on the shared repo (R-015-5f). Emits
    ``{"batch": [{source_slug, action, manifest} | {source_slug, error, message}, …]}``.
    """
    combined_path = args.batch_candidates
    # The combined file aggregates candidates for MANY source pages, so the
    # single-page 1 MiB candidates cap is too small here — use the 10 MiB
    # source-body cap (still O_NOFOLLOW + fstat-bounded → no OOM).
    try:
        raw = _read_file_bounded(combined_path, _MAX_SOURCE_BODY_BYTES)
    except _FileTooLargeError:
        return emit({"error": "INVALID_BATCH_FILE",
                     "reason": (f"batch-candidates file exceeds the "
                                f"{_MAX_SOURCE_BODY_BYTES}-byte cap")},
                    exit_code=2)
    except OSError:
        return emit({"error": "INVALID_BATCH_FILE",
                     "reason": "batch-candidates file could not be opened"},
                    exit_code=2)
    try:
        entries = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return emit({"error": "INVALID_BATCH_FILE",
                     "reason": "batch-candidates file is not valid UTF-8 JSON"},
                    exit_code=2)
    if not isinstance(entries, list) or not entries:
        return emit({"error": "INVALID_BATCH_FILE",
                     "reason": "must be a non-empty JSON array of entries"},
                    exit_code=2)

    vault_root = args.vault_root.resolve(strict=True)
    orchestrator_id_val = getattr(args, "orchestrator_id", "orchestrator")
    today = date.today()
    repo = make_repo({
        "vault_id": args.vault,
        **({"db_path": args.db_path} if args.db_path else {}),
    })
    batch_results: list[dict[str, Any]] = []
    try:
        # P-7: load known entities ONCE for the whole batch; `_apply_write`
        # grows this set in place as entries create new concepts, so we never
        # re-scan the entities table per entry (O(E) once, not O(N·E)).
        known = load_known_entities(repo, args.vault)
        known_slugs = {e["slug"] for e in known}
        for entry in entries:
            # Per-entry shape validation (non-fatal — isolates one bad entry).
            if (not isinstance(entry, dict)
                    or not isinstance(entry.get("source_slug"), str)
                    or not isinstance(entry.get("source_hash"), str)
                    or not isinstance(entry.get("candidates"), list)):
                batch_results.append({
                    "source_slug": (entry.get("source_slug")
                                    if isinstance(entry, dict) else None),
                    "error": "INVALID_BATCH_ENTRY",
                    "message": ("each entry must be "
                                "{source_slug:str, source_hash:str, "
                                "candidates:list}"),
                })
                continue
            source_slug = entry["source_slug"]
            try:
                result = _apply_candidates_to_db(
                    source_slug, entry["source_hash"], args.vault, vault_root,
                    entry["candidates"], orchestrator_id_val, today, repo,
                    known_slugs=known_slugs,
                )
            # Per-entry isolation: expected FS/parse/DB faults route to this
            # entry's error envelope and the batch continues. `sqlite3.Error`
            # (locked DB, disk-full, IntegrityError) is included — without it a
            # transient DB fault on one entry would crash the whole batch and
            # discard every accumulated result. Programming errors
            # (AttributeError, MemoryError, …) still propagate by design.
            except (OSError, ValueError, KeyError, RuntimeError,
                    sqlite3.Error) as e:
                batch_results.append({"source_slug": source_slug,
                                      "error": type(e).__name__,
                                      "message": str(e)})
                continue
            exit_code = result.pop("_exit_code", 0)
            if exit_code != 0:
                batch_results.append({"source_slug": source_slug, **result})
                continue
            manifest = result["_manifest"]
            current_hash = result["source_hash"]
            if args.ingest:
                try:
                    summary = dispatch_to_indexer(
                        manifest, args.vault, vault_root, args.db_path,
                        repo=repo,
                    )
                except WikiIngestError as e:
                    batch_results.append({"source_slug": source_slug,
                                          "error": "MANIFEST_INVALID",
                                          "message": str(e)})
                    continue
                except sqlite3.Error as e:
                    # A DB fault during the indexer dispatch isolates to this
                    # entry too (symmetry with the write-phase catch above) —
                    # never crash the batch / lose accumulated results.
                    batch_results.append({"source_slug": source_slug,
                                          "error": "DB_WRITE_FAILED",
                                          "message": str(e)})
                    continue
                if summary.get("failed"):
                    # C-1: do NOT update idempotency on partial failure.
                    batch_results.append({"source_slug": source_slug,
                                          "action": "partial",
                                          "error": "PARTIAL_INDEX_FAILURE",
                                          "manifest": manifest,
                                          "index": summary})
                    continue
            # Parity with single-page apply(): a failed source_state update
            # means the body hash wasn't recorded → report `partial` (retry
            # re-extracts) instead of a false `applied`.
            if not _try_update_idempotency_state(
                repo, args.vault, source_slug, current_hash, manifest,
            ):
                batch_results.append({"source_slug": source_slug,
                                      "action": "partial",
                                      "error": "IDEMPOTENCY_UPDATE_FAILED",
                                      "manifest": manifest})
                continue
            batch_results.append({"source_slug": source_slug,
                                  "action": "applied",
                                  "manifest": manifest})
    finally:
        repo.close()
    return emit({"batch": batch_results})


def _try_update_idempotency_state(
    repo: Any, vault_id: str, source_slug: str, current_hash: str,
    manifest: dict[str, Any],
) -> bool:
    """H-3: wrap `update_idempotency_state` in defensive try/except.

    Returns True on success, False if the DB UPDATE failed (caller maps
    to IDEMPOTENCY_UPDATE_FAILED envelope). Without this wrap, an
    OperationalError ("database locked", "disk full") after pages /
    entities / refs are committed leaves the caller with a Python
    traceback on stderr + a successfully-built manifest on stdout =
    split-brain. Treating the failure as PARTIAL keeps the envelope
    contract intact and signals "retry is safe" to the operator.
    """
    try:
        update_idempotency_state(repo, vault_id, source_slug, current_hash)
        return True
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
        logger.warning(
            "apply: update_idempotency_state failed for "
            "(vault=%s, source_slug=%s): %s — emitting "
            "IDEMPOTENCY_UPDATE_FAILED envelope, manifest preserved",
            vault_id, source_slug, type(e).__name__,
        )
        return False


def main(argv: list[str] | None = None) -> int:
    """CLI entry-point (v3.1). Dispatches to `prepare` or `apply` subcommand.

    BREAKING CHANGE vs v2: legacy single-command shape (no subcommand) is
    rejected at argparse with a usage error pointing at `{prepare,apply}`.
    See 003-v3-11a (deletion of legacy-shape main() tests) + this bead's
    dispatch shim.
    """
    args = _build_parser_v3().parse_args(argv)
    if args.cmd == "prepare":
        return prepare(args)
    if args.cmd == "apply":
        return apply(args)
    # argparse(required=True) makes this unreachable, but mypy-strict
    # likes the safety net.
    return 1


if __name__ == "__main__":
    sys.exit(main())
