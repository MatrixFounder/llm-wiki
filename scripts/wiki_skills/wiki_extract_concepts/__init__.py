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
import re
import sqlite3
import sys
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout import (
    CONCEPTS_SUBDIR,
)
from scripts.wiki_skills._common import build_repo_config, emit
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
    _is_valid_slug,
    _ALLOWED_ENTITY_TYPES,
    _REFUSED_ENTITY_TYPES,
    _SOURCE_HASH_RE,
    _ORCHESTRATOR_ID_RE,
    _REQUIRED_CANDIDATE_KEYS,
    _CANDIDATE_COUNT_MIN,
    _CANDIDATE_COUNT_MAX,
    _FIELD_CAPS,
    _FIELD_MIN_WORDS,
    _NAME_MIN_CHARS,
    _NAME_ALLOWLIST,
    _SPAN_REGEX,
    _norm,
    _path_is_absolute,
    _validate_source_hash,
    _validate_orchestrator_id,
    _validate_candidates_schema,
    check_in_batch_collisions,
    classify_candidates,
    _sanitize_name,
    _sanitize_definition,
    _parse_source_span,
    _preflight_sanitize,
)
# TASK 064: the LAYOUT-AWARE gates (G5 near-duplicate / G8 slug-derivation / G10
# the write-dir-must-be-indexable preflight). A separate leaf because `_validation`
# is a PURE stdlib-only leaf and that purity is what makes "a refusal writes zero
# files" true by construction rather than by care.
from ._gates import (  # noqa: E402
    NEAR_DUP_CUTOFF,
    _dup_key,
    build_dup_keys,
    check_slugs_derived_from_names,
    concepts_dir_for_source,
    derive_concept_slug,
    layout_indexes_concepts,
    near_duplicate_warnings,
)
# TASK 016 bead 016-04: source-IO / path-resolution leaf re-export.
from ._sourcing import (  # noqa: E402
    _MAX_SOURCE_BODY_BYTES,
    _MAX_CANDIDATES_BYTES,
    _FileTooLargeError,
    _read_file_bounded,
    _resolve_source_inside_sources,
    _all_concepts_dirs,
    _present_concept_slugs,
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
    check_page_slug_collisions,
    upsert_extracted_entity,
    upsert_entity_refs,
    check_idempotency,
    update_idempotency_state,
    build_manifest,
)
# TASK 016 bead 016-05: concept-page writing leaf re-export.
from ._pages import write_concept_page  # noqa: E402


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
    repo = make_repo(build_repo_config(  # TASK 022: vault_root already resolved above
        args.vault, vault_root=vault_root, db_path_flag=args.db_path))
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


def _name_map(known: list[dict[str, Any]]) -> dict[str, str]:
    """slug (NFC) → the page's authored name. Built ONCE per batch, beside `known_slugs`."""
    return {unicodedata.normalize("NFC", str(e["slug"])): str(e.get("name") or "")
            for e in known}


def _name_differs(a: str, b: str) -> bool:
    """Two concept names that landed on ONE slug — the SAME concept written twice, or TWO
    concepts the slug strategy collapsed?

    NFC + casefold + whitespace-collapse, exactly as every other content comparison on this rail
    (`_validation._norm`). What is left is a real difference: «Падёж скота» vs «Грамматический
    падеж» differ; «Идемпотентность» vs «идемпотентность » do not.
    """
    def _n(s: str) -> str:
        return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s)).strip().casefold()
    return bool(a) and bool(b) and _n(a) != _n(b)


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

    # M-7: one os.scandir per `_concepts/` dir found in the vault (course-tier
    # Karpathy `Lessons/<Course>/_concepts/` AND PARA `<folder>/_concepts/`).
    # Shared with `_apply_write`'s ghost-row self-heal (TASK 053 / R3) via the
    # `_present_concept_slugs` helper — one source of truth for on-disk concepts.
    present_concept_files = _present_concept_slugs(vault_root)
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
        # omits these — they are emitted ONCE at the batch top level (they are
        # SOURCE-INDEPENDENT, and re-serialising them per entry is the O(N·|known|)
        # stdout blow-up P-6 exists to prevent). `slug_strategy` joins them for the
        # same reason: one vault, one answer.
        entry["known_concepts"] = _annotate_dup_keys(known_out)
        entry["missing_concept_files"] = missing_concept_files
        entry.update(_layout_contract(vault_root))
    return entry


def _layout_contract(vault_root: Path) -> dict[str, Any]:
    """★ TASK 064 / G8 — the LAYOUT half of the contract the REASON step must obey.

    Before this, `prepare`'s envelope carried 7 keys and NOT ONE WORD about the layout,
    so the model had to GUESS how this vault turns a concept NAME into a SLUG — and the
    SKILL told it to guess ASCII (`^[a-z0-9][a-z0-9-]{0,62}$`), which is simply false
    for the operator's `preserve-unicode` Cyrillic vault. A model obeying the doc emits
    `vitalik-buterin`; every `[[Виталик Бутерин]]` in that vault resolves to
    `виталик-бутерин`; the page is filed and NOTHING CAN EVER LINK TO IT. Both slugs are
    live in his vault today.

    A contract that omits the rule the caller is judged against is not a contract.
    Mirrors `wiki_extract_decisions.prepare`, which emits `slug_strategy` for exactly
    this reason. Additive keys — no existing consumer breaks.

    ★ AND IT CARRIES THE NEAR-DUPLICATE ADVICE (F2, TASK 064 FIX-LOOP). The advice is
    ONLY actionable BEFORE authoring: told at `apply` time that your slug resembles an
    existing one, the cheapest fix is to re-send — told at `prepare` time, you simply
    reuse the existing slug and the vault compounds instead of splitting. The `dup_key`
    is the part a model cannot derive for itself: `виталик-бутерин` and `vitalik-buterin`
    are 100% dissimilar as strings and IDENTICAL as keys, which is exactly the operator's
    most expensive live split.
    """
    from scripts.wiki_index.layout_config import resolve_layout_config as _rlc
    config = _rlc(vault_root)
    return {
        "layout": config.layout,
        "slug_strategy": config.slug_strategy,
        "near_duplicate_advice": (
            "Before you invent a slug, check `known_concepts`: if the vault ALREADY has "
            "this concept under any spelling — a plural, a transliteration, a word-order "
            "variant — reuse its EXACT slug so your candidate files as a mention instead "
            "of minting a second page. Compare against `dup_key` (the transliterated "
            "form), not just the slug: «Виталик Бутерин» and `vitalik-buterin` look "
            "nothing alike and are the same person. `apply` will WARN about near "
            "matches, but it will not refuse them — string similarity cannot tell "
            "`serialization` from `deserialization`, and you can."),
    }


def _annotate_dup_keys(
    known_out: list[dict[str, Any]] | list[str],
) -> list[dict[str, Any]] | list[str]:
    """Add `dup_key` to each `known_concepts` entry whose transliterated key DIFFERS from
    its slug — the cross-script information a model cannot compute itself.

    Only when it differs: for an ASCII vault every key equals its slug and the annotation
    would be 720 lines of pure noise (P-6). `slugs-only` format is left untouched (it is a
    list of bare strings by contract).
    """
    if not known_out or not isinstance(known_out[0], dict):
        return known_out
    for e in known_out:
        assert isinstance(e, dict)
        key = _dup_key(str(e["slug"]))
        if key != e["slug"]:
            e["dup_key"] = key
    return known_out


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
    repo = make_repo(build_repo_config(  # TASK 022: vault_root already resolved above
        args.vault, vault_root=vault_root, db_path_flag=args.db_path))
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
        "known_concepts": _annotate_dup_keys(known_out),
        "missing_concept_files": missing_concept_files,
        # TASK 064 / G8 + the F2 near-duplicate advice: source-INDEPENDENT, so both ride
        # at the top level next to `known_concepts` — not repeated per entry (P-6).
        **_layout_contract(vault_root),
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
    repo = make_repo(build_repo_config(  # TASK 022: vault_root already resolved above
        args.vault, vault_root=vault_root, db_path_flag=args.db_path))
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

        # ★ G0 — the empty extraction. Record the hash (so a re-run short-circuits) and
        # report SUCCESS. No pages, no entities, no refs, no indexer dispatch — and,
        # critically, NO `upsert_entity_refs`, which would have cleared this source's
        # existing mentions (see `_apply_write`).
        if result.get("_no_candidates"):
            if not _try_update_idempotency_state(
                repo, args.vault, source_slug, current_hash, {},
            ):
                return emit({
                    "action": "partial",
                    "error": "IDEMPOTENCY_UPDATE_FAILED",
                    "source_slug": source_slug,
                    "reason": ("no candidates to write, but the source_state update "
                               "failed; the next run will safely re-extract"),
                }, exit_code=5)
            return emit({
                "action": "no_candidates",
                "source_slug": source_slug,
                "written": [],
                "mentioned": [],
                "message": ("no extractable concepts in this source — this is a "
                            "SUCCESS, not a failure. Nothing was written and the "
                            "source's existing concept mentions are untouched."),
            })

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
            # G5's near-duplicate advisory rides TOP-LEVEL here too — `manifest` is nested
            # under `extraction` on this branch, and advice the caller has to go digging
            # for is advice the caller does not read.
            ingest_env: dict[str, Any] = {"extraction": manifest, "index": summary}
            if result.get("_warnings"):
                ingest_env["warnings"] = result["_warnings"]
            return emit(ingest_env)

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

    # ★ Step 3b (TASK 064 / G10) — CAN THIS LAYOUT EVEN SEE A CONCEPT PAGE?
    #
    # `apply` writes to a hardcoded `_concepts` dir on EVERY layout — including
    # `dev-project`, which maps no `concept` type and whose read globs (`tasks/*.md`)
    # never reach a `_concepts/` sibling. The pages were written, never discovered by
    # `iter_pages`, never indexed, and never linted: a page the walker cannot SEE is a
    # page `wiki-lint` is *structurally incapable* of reporting. This is TASK 063's G4
    # lesson, which this rail never learned.
    #
    # Refuse BEFORE the schema pass so the operator's answer is about the LAYOUT (which
    # is what they must fix) and not about candidate #7's quote.
    from scripts.wiki_index.layout_config import resolve_layout_config as _rlc
    config = _rlc(vault_root)
    concepts_dir = concepts_dir_for_source(source_path, vault_root, config)
    if not layout_indexes_concepts(config, vault_root, concepts_dir):
        return {
            "error": "LAYOUT_CANNOT_INDEX_CONCEPTS",
            "layout": config.layout,
            "reason": (
                f"layout {config.layout!r} cannot index a concept page filed for this "
                f"source: either it maps no `concept` type (→ UnmappedTypeError, the "
                f"page is silently DROPPED at reindex) or its read globs never reach "
                f"the `_concepts/` dir we would write to. The pages would exist on "
                f"disk, index nowhere, and raise no lint issue — invisible. Add a "
                f"`concept` type_mapping + a `_concepts/**/*.md` path glob to the "
                f"layout, or extract into a concept-capable layout (karpathy, "
                f"obsidian-personal, cybos)."),
            "_exit_code": 4,
        }

    # Step 4 — strict schema validation + sanitization pre-flight (M-4), then the one
    # remaining pure gate. ALL of this is pre-DB and pre-write, so a violation is a
    # guaranteed ZERO-FILE, DB-never-opened no-op — by CONSTRUCTION, not by care.
    #
    # ★ G8 IS NOT HERE (F3, TASK 064 FIX-LOOP). It used to be — and judging candidates
    # BEFORE `classify_candidates` meant judging the ones that are MENTIONS of pages that
    # ALREADY EXIST. Any existing page whose slug is not exactly `slugify(name)` — every
    # ACRONYM page (`amm`, `wal`, `pos`, `nft`, `dex`), every hand-authored page, every
    # page written before TASK 064 — could never be mentioned again, and the prescribed
    # repair MANUFACTURED a second page for the same concept. G8 now runs in
    # `_apply_write`, on the CREATE list only. It still writes zero files.
    try:
        _validate_candidates_schema(candidates, source_body=source_body)
        # ★ G6 — two candidates, one slug: the second `write_concept_page` would see
        #   different bytes and silently OVERWRITE the first. Zero lint issues, because
        #   the count is right. (Ported from `wiki_extract_decisions`.)
        check_in_batch_collisions(candidates)
        _preflight_sanitize(candidates)
    except ExtractionParseError as e:
        env = _envelope_from_parse_error(e)
        env["_exit_code"] = 4
        return env

    return {
        "source_path": source_path,
        "source_slug": source_slug,
        "current_hash": current_hash,
        "config": config,
        "concepts_dir": concepts_dir,
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
    known_names: dict[str, str] | None = None,
    present_concept_files: set[str] | None = None,
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

    ``present_concept_files`` (TASK 053 / R3, DF-8): the set of concept slugs
    whose `_concepts/<slug>.md` exists on disk. None (single-page) → scanned
    fresh; a set (batch) is loaded ONCE and grown in place alongside
    ``known_slugs``. A candidate dedups to `mention` ONLY when it is BOTH a
    known entity AND present on disk; a known-but-missing slug (a GHOST row,
    file deleted without a reindex) reclassifies `create` so the page
    self-heals instead of silently vanishing.
    """
    source_path: Path = validated["source_path"]
    source_slug: str = validated["source_slug"]
    current_hash: str = validated["current_hash"]

    # ★★ G0 (TASK 064) — AN EMPTY EXTRACTION IS A SUCCESS, AND IT MUTATES NOTHING.
    #
    # `_CANDIDATE_COUNT_MIN` is now 0, so `[]` reaches here instead of dying at exit 4.
    # It must touch NOTHING but `source_state` — and in particular it must NOT fall
    # through to the write path, because `upsert_entity_refs` does an atomic
    # DELETE+INSERT keyed on the source page: called with an empty list it **CLEARS the
    # source's existing refs** (an existing test pins that clearing behaviour, and it is
    # correct for a re-extraction that legitimately found nothing NEW to link). On the
    # empty path it would silently drop this source out of every concept's
    # `BEGIN-AUTO:mentions` ledger — turning "I found no concepts" into "I deleted the
    # ones you had". Mirrors `wiki_extract_decisions.apply`.
    #
    # The caller updates `source_state` (so a re-run short-circuits) and emits
    # `action: no_candidates` at exit 0.
    if not candidates:
        logger.info(
            "apply: no candidates for %r — this is a SUCCESS, not a failure; "
            "nothing written, existing refs preserved", source_slug,
        )
        return {
            "_no_candidates": True,
            "_manifest": None,
            "source_slug": source_slug,
            "source_hash": current_hash,
            "_exit_code": 0,
        }

    # M-9: warn when --orchestrator-id omitted (opaque provenance). Fires
    # only once validation has passed and we are about to write — same
    # position relative to the write as the former monolithic apply().
    if orchestrator_id == "orchestrator":
        logger.warning(
            "apply: --orchestrator-id not supplied; entity provenance "
            "will record opaque literal 'orchestrator'. Pass "
            "--orchestrator-id <model-id> for an auditable canonicalized_by."
        )

    # TASK 037 — layout-aware concepts dir. Karpathy nests the source under
    # `_sources/`, so its `_concepts/` sibling is `parent.parent/_concepts`
    # (byte-identical to pre-037). PARA layouts (obsidian-personal) keep the
    # source note in its own folder, so concepts live in `<folder>/_concepts/`.
    # `concepts_rel` (vault-relative POSIX) is threaded into the entity row
    # `file_path` + manifest so they point at the REAL on-disk page (R-5).
    # `pages.project` is derived from the source path so the page_entity_refs
    # FK matches the indexer's recorded value (unchanged).
    # TASK 040 / ADR-007: concepts-anchor is config (the source-nesting subdir), not a fork.
    # source_subdir non-empty (karpathy "_sources") → concepts at the container `<parent.parent>/`;
    # "" (PARA) → sibling `<parent>/`. karpathy value == SOURCES_SUBDIR → byte-identical.
    # TASK 064: ONE definition of that dir (`concepts_dir_for_source`), reused by the G10
    # preflight in `_apply_validate` — a preflight that checked a different directory than
    # the writer uses would not be a preflight. `_apply_validate` already resolved both;
    # a library caller that skipped it gets them resolved here.
    from scripts.wiki_index.layout_config import resolve_layout_config as _rlc
    config = validated.get("config") or _rlc(vault_root)
    target_concepts_dir: Path = (
        validated.get("concepts_dir")
        or concepts_dir_for_source(source_path, vault_root, config)
    )
    concepts_rel = target_concepts_dir.relative_to(vault_root).as_posix()
    source_project = _derive_source_project(source_path, vault_root)
    try:
        if known_slugs is None:
            known = load_known_entities(repo, vault_id)
            known_slugs = {e["slug"] for e in known}
            known_names = _name_map(known)
        if present_concept_files is None:
            present_concept_files = _present_concept_slugs(vault_root)
        # ★★ G7 (TASK 064) — **A PAGE ON DISK IS ALWAYS A `mention`.**
        #
        # This was `known_entity_rows ∩ present_concept_files`, and the INVERSE case is
        # the bug: page ON DISK, entity row ABSENT (a hand-authored page; a rebuilt DB;
        # a stale index) fell OUTSIDE the intersection, classified `create`, and
        # `write_concept_page` **OVERWROTE THE HUMAN'S PAGE** with the model's
        # definition — `logger.warning`, exit 0. Data loss reported as success.
        #
        # Dropping the `known ∩` conjunct fixes it without costing the TASK-053/R3
        # ghost-row self-heal: that case is `known row + file GONE`, which is still
        # NOT present ⇒ still `create` ⇒ still self-heals. The intersection was never
        # what made R3 work; PRESENCE was. (Its test stays green, and stays.)
        #
        # NFC on both sides (R3 fix-up): `present_concept_files` is normalised at its FS
        # source (macOS/iCloud store NFD), candidate slugs arrive NFC.
        effective_known = set(present_concept_files)
        create_list, mention_list = classify_candidates(candidates, effective_known)
        known_nfc = {unicodedata.normalize("NFC", s) for s in known_slugs}

        # ★ THE CROSS-SOURCE `mention` HAZARD — a WARNING, and deliberately NOT a refusal.
        #
        # `classify_candidates` files a candidate as a `mention` on SLUG ALONE, never on name —
        # and a mention DISCARDS the candidate's definition. So «Падеж» (grammatical case),
        # extracted from a later note into a vault that already owns `padezh` («Падёж» — mass
        # death of livestock), would be filed as A MENTION OF THE LIVESTOCK PAGE: a falsified
        # provenance receipt, written at exit 0, with a correct-looking count.
        #
        # ⚠️ IT IS A WARNING BECAUSE THE POPULATION WAS MEASURED, AND IT IS **ZERO**. Across the
        # operator's 685 live entities, the number of name-pairs that collapse to one slug is 0
        # under `preserve-unicode` AND 0 under `transliterate`. A REFUSAL here would be a gate
        # that fires on nothing — and a refusal on a currently-exit-0 path is EXACTLY how the
        # 0.88 near-duplicate gate came to block correct work and had to be demoted. The lesson
        # is one page away in this rail's own SKILL; we are not learning it twice.
        #
        # So it SURFACES (where the operator can act) and refuses nothing.
        # ★ P-7: the name map is THREADED, never re-queried. The first cut called
        # `load_known_entities` here — inside the per-entry path — and
        # `test_apply_batch_known_loaded_once` caught the N+1 on the first run. A warning is
        # not worth a query per candidate.
        mention_name_warnings: list[dict[str, Any]] = []
        name_by_slug = known_names or {}
        for m in mention_list:
            slug_n = unicodedata.normalize("NFC", str(m["slug"]))
            owner = name_by_slug.get(slug_n)
            mine = str(m.get("name") or "")
            if owner and _name_differs(owner, mine):
                mention_name_warnings.append({
                    "warning": "MENTION_NAME_DIFFERS",
                    "slug": slug_n,
                    "reason": (
                        f"this candidate is being filed as a MENTION of an existing page "
                        f"because it derived the same slug — but the page's name differs. "
                        f"Its definition will be DISCARDED. If these are two DIFFERENT "
                        f"concepts, give this one a name that stands alone."),
                })

        # ★ G8 (F3, TASK 064 FIX-LOOP) — ON THE **CREATE LIST**, AND ONLY ON SLUGS THE
        # VAULT DOES NOT ALREADY HAVE.
        #
        # Judging a slug the vault ALREADY OWNS is not a contract check, it is a demand to
        # rename someone else's page — and every ACRONYM page in the vault (`amm`, `wal`,
        # `pos`, `nft`, `dex`) has a slug that is not `slugify(name)`. Under the first cut
        # they became permanently UNMENTIONABLE, and the prescribed repair ("re-emit `amm`
        # as `автоматический-маркет-мейкер`") minted a SECOND page for AMM. The gate is
        # only meaningful for a slug that does not exist yet.
        check_slugs_derived_from_names(
            [c for c in create_list
             if unicodedata.normalize("NFC", str(c["slug"])) not in known_nfc
             and unicodedata.normalize("NFC", str(c["slug"])) not in present_concept_files],
            config,
        )

        # ★★ F6 (TASK 064 FIX-LOOP) — A CONCEPT CAN **EVICT THE SOURCE NOTE FROM THE
        # INDEX**, AT EXIT 0.
        #
        # `pages` is UNIQUE(vault_id, slug, project). A candidate whose slug equals an
        # existing page's slug — the SOURCE NOTE'S OWN being the easy case: extract
        # `backtesting` from `_sources/backtesting.md` — makes `upsert_page` silently
        # REPLACE that row's type + file_path. Reproduced: rc=0, and `pages` afterwards
        # holds ('backtesting', 'concept', '_concepts/backtesting.md'). The source note is
        # GONE from the index and unfindable by `wiki-search`, with no error, no warning
        # and no lint issue.
        #
        # The other gates compare candidates against ENTITY rows and on-disk `_concepts/`
        # pages — never against `pages`. `wiki-import`'s `derive_candidates` has carried
        # `self-collision` + `collides-existing-page` guards for a year (`_authoring.py`);
        # they were simply never ported to this rail. Ported now, pre-write, zero-file.
        check_page_slug_collisions(
            repo, vault_id, create_list, vault_root, target_concepts_dir, source_slug,
        )

        # ★ F7 (TASK 064 FIX-LOOP) — G7's REFUSAL IS NOW **ATOMIC**.
        #
        # `CONCEPT_PAGE_EXISTS` is raised from inside `write_concept_page`, i.e. on
        # iteration k — AFTER k-1 pages are already on disk and their entity rows
        # committed. That contradicts this rail's own zero-file invariant. Check every
        # target BEFORE the loop starts. (The belt inside `write_concept_page` stays; this
        # makes it unreachable in practice, which is what a belt should be. Note this
        # cannot fire on an idempotent re-run: a page on disk classifies `mention` above,
        # so it is not in `create_list` at all.)
        # ★ `lexists`, NOT `exists`. `Path.exists()` FOLLOWS the symlink, so a DANGLING one
        # at `_concepts/<slug>.md` reports False here, sails past this guard, and then trips
        # `write_concept_page`'s symlink refusal — a `PathTraversalError`, which is a
        # ValueError, NOT an ExtractionParseError. Nothing catches it: the process dies inside
        # the write loop with a traceback, no JSON envelope, a non-zero exit that is not one of
        # the contract's codes — and the pages written on iterations 0..k-1 still on disk with
        # their entity rows committed. Both invariants (zero-file refusal, one envelope + a
        # stable exit code) break on a single broken symlink.
        collisions = [
            {"slug": str(c["slug"])} for c in create_list
            if os.path.lexists(target_concepts_dir / f"{c['slug']}.md")
        ]
        if collisions:
            raise ExtractionParseError(
                f"{len(collisions)} concept page(s) already exist on disk",
                error="CONCEPT_PAGE_EXISTS",
                field="slug",
                reason=("a `_concepts/<slug>.md` for this candidate already exists on "
                        "disk and this rail does not overwrite a page it did not just "
                        "create — it may be hand-authored. Re-emit the candidate with "
                        "the existing slug so it files as a mention, or rename the "
                        "concept."),
                violations=collisions,
            )

        # ★ G5 — the NEAR-DUPLICATE **ADVISORY**. It does NOT refuse (see
        # `_gates.NEAR_DUP_CUTOFF`: the metric rates `централизация`/`децентрализация` at
        # 0.941, HARDER than the real live duplicate it was built for) and it does NOT
        # instruct a merge (a compliant model told to file `decentralized-exchange` as a
        # mention of `centralized-exchange` writes a FALSIFIED provenance receipt into
        # `page_entity_refs`, at exit 0 — an anti-duplicate gate that manufactures false
        # knowledge). It hands the model the similar slugs and lets it judge.
        warnings = mention_name_warnings + near_duplicate_warnings(
            create_list, build_dup_keys(known_nfc | set(present_concept_files)),
        )

        # ★ G7 (part 2) — HEAL THE DB, don't clobber the disk. A page present in the
        # target dir whose `entities` row is missing is now a `mention`, so nothing
        # would ever create that row and the concept would stay invisible to
        # `wiki-search`/`wiki-graph` until someone ran a full reindex. Upsert it from
        # the candidate.
        # SCOPED DELIBERATELY to a page in the dir WE would have written to:
        # `present_concept_files` spans EVERY `_concepts/` in the vault, and writing an
        # entity row whose `file_path` points at OUR dir for a page that actually lives
        # in another course's `_concepts/` would manufacture the exact `missing-on-disk`
        # lint issue this rail is supposed to prevent.
        # (`page_entity_refs` has NO FK to `entities` — checked, `sql/wiki-index-v2.sql`
        # — so this heal is CORRECTNESS, not a crash-avoidance necessity.)
        for cand in mention_list:
            slug_nfc = unicodedata.normalize("NFC", str(cand["slug"]))
            if (slug_nfc not in known_nfc
                    and (target_concepts_dir / f"{cand['slug']}.md").is_file()):
                logger.warning(
                    "apply: concept page for %r exists on disk but has no entities "
                    "row (stale index / hand-authored page) — healing the row instead "
                    "of overwriting the page", cand["slug"],
                )
                cand["entity_action"] = upsert_extracted_entity(
                    repo, vault_id, cand, source_slug, today,
                    orchestrator_id=orchestrator_id,
                    concepts_rel=concepts_rel,
                )
                known_slugs.add(str(cand["slug"]))

        for cand in create_list:
            _target, file_action = write_concept_page(
                vault_root, cand, source_slug, today, vault_id=vault_id,
                concepts_dir=target_concepts_dir,
            )
            cand["file_write_action"] = file_action
            cand["entity_action"] = upsert_extracted_entity(
                repo, vault_id, cand, source_slug, today,
                orchestrator_id=orchestrator_id,
                concepts_rel=concepts_rel,
            )
            # Augment the shared sets so a later batch entry mentioning this
            # just-created concept classifies it as `mention`, not a dup
            # `create` — exactly what a fresh load_known_entities + on-disk scan
            # would show. Both must grow: `known_slugs` (entity row now exists)
            # AND `present_concept_files` (the page was just written above), so
            # the R3 `known & present` intersection sees it (else the next entry
            # would re-`create` the same slug — a double-create).
            known_slugs.add(cand["slug"])
            present_concept_files.add(unicodedata.normalize("NFC", cand["slug"]))

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
            concepts_rel=concepts_rel,
        )
        # ★ G5's advisory rides the SUCCESS envelope (exit 0) — it is advice, not a
        # refusal. Omitted entirely when there is nothing to say (no empty `warnings: []`
        # noise on the overwhelmingly common clean run).
        if warnings:
            manifest["warnings"] = warnings
    except ExtractionParseError as e:
        # v2 parity: downstream raises (e.g. _parse_source_span on an
        # inverted L10-L5 range that the regex validator passed) map to
        # exit 4 with the structured envelope.
        env = _envelope_from_parse_error(e)
        env["_exit_code"] = 4
        return env

    return {
        "_manifest": manifest,
        "_warnings": warnings,
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
    known_names: dict[str, str] | None = None,
    present_concept_files: set[str] | None = None,
) -> dict[str, Any]:
    """Validate + write ONE source page's candidates on an already-open repo
    (R-015-5d). Thin combiner over :func:`_apply_validate` +
    :func:`_apply_write` used by the batch path, where the shared repo is
    legitimately open for every entry. Returns the same envelope shape as
    ``_apply_write`` (or the validation error envelope, with ``_exit_code``).

    ``known_slugs`` / ``present_concept_files`` are threaded to
    :func:`_apply_write` so a batch caller can load known entities + scan
    on-disk concepts ONCE and have both sets grow in place across entries
    (P-7; R3 ghost-row self-heal).
    """
    validated = _apply_validate(
        source_page_arg, source_hash_expected, vault_root, candidates,
    )
    if validated.get("_exit_code", 0) != 0:
        return validated
    return _apply_write(
        validated, vault_id, vault_root, candidates,
        orchestrator_id, today, repo, known_slugs=known_slugs,
        known_names=known_names,
        present_concept_files=present_concept_files,
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
    repo = make_repo(build_repo_config(  # TASK 022: vault_root already resolved above
        args.vault, vault_root=vault_root, db_path_flag=args.db_path))
    batch_results: list[dict[str, Any]] = []
    try:
        # P-7: load known entities ONCE for the whole batch; `_apply_write`
        # grows this set in place as entries create new concepts, so we never
        # re-scan the entities table per entry (O(E) once, not O(N·E)).
        known = load_known_entities(repo, args.vault)
        known_slugs = {e["slug"] for e in known}
        known_names_map = _name_map(known)
        # TASK 053 / R3 (DF-8): scan on-disk concept slugs ONCE too and thread
        # the shared set (grown in place per create) so the ghost-row self-heal
        # does not reintroduce an O(N·walk) `_all_concepts_dirs` sweep per entry.
        present_concept_files = _present_concept_slugs(vault_root)
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
                    known_names=known_names_map,
                    present_concept_files=present_concept_files,
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
            # ★ G0 parity with the single-page path: an empty entry is a SUCCESS that
            # writes nothing and clears nothing. Without this branch the batch path
            # would fall through to `--ingest` with a `None` manifest.
            if result.get("_no_candidates"):
                _try_update_idempotency_state(
                    repo, args.vault, source_slug, current_hash, {},
                )
                batch_results.append({"source_slug": source_slug,
                                      "action": "no_candidates",
                                      "written": [], "mentioned": []})
                continue
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
            entry_result: dict[str, Any] = {"source_slug": source_slug,
                                            "action": "applied",
                                            "manifest": manifest}
            # G5's advisory, lifted next to `action` — same reason as the single-page
            # `--ingest` branch: advice buried inside a nested manifest is advice nobody
            # reads. Omitted when empty.
            if result.get("_warnings"):
                entry_result["warnings"] = result["_warnings"]
            batch_results.append(entry_result)
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
