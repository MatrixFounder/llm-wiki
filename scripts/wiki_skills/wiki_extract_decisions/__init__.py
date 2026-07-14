"""`wiki-extract-decisions` CLI (TASK 063 / RFC-004) — the typed-knowledge
extraction rail.

Turns a summarised source note (a meeting protocol, a lesson, an article) into
typed `decision` / `requirement` / `risk` pages plus the typed edges between
them — the pages TASK 062 proved a human can write by hand, and proved are worth
having (they produced the vault's first EARNED ontology green).

Two subcommands, the proven Decision-17 split:

* ``prepare`` — read the source page, hash it, resolve the layout + the
  per-folder `extract_decisions` policy, PREFLIGHT that the layout can actually
  hold typed pages (G4), and emit the ONTOLOGY CONTRACT the reasoning step must
  obey (the class roster, each edge's domain/range, each class's `status` enum),
  the known typed pages, the existing slugs, and the `--source-hash` handshake.
  **NO LLM CALL.**
* ``apply``   — consume the orchestrator-synthesised candidates JSON, re-check
  the hash, validate every candidate against the ontology BEFORE any write
  (G1/G2), derive slugs with the LAYOUT'S OWN strategy, write the typed pages
  where the layout's READ GLOBS can see them (G4), reconcile supersede targets
  per the layout's OWN drift rules (G3), and emit a manifest.
  **NO LLM CALL.**

The REASON step lives OUTSIDE this skill (Decision-17). The orchestrator runs
`prepare`, loads the `decision-extraction` skill into its own context, reads the
source body, synthesises candidates JSON, and pipes it into `apply`. This package
makes ZERO model-provider SDK calls — gated at runtime over the whole package by
`tests/test_extract_decisions_cli.py::test_no_anthropic_import_in_package`, which
globs the package directory rather than a hand-typed file list, so a file added by
a later bead is covered without anyone remembering to add it.

★ ANTI-FABRICATION IS A MECHANISM, NOT A PROMPT (R-063-7). `CANDIDATE_COUNT_MIN`
is **0**, and the asymmetry with the precedent is deliberate:
`wiki_extract_concepts._validation` sets it to **1**. Cloning that 1 would make
*"this note contains no decisions"* an exit-4 FAILURE — and the model's cheapest
path to a green run would then be to INVENT one. An empty candidate set is
SUCCESS (`action: no_candidates`, exit 0). Do not "restore parity" with the
precedent here; the difference is the safety property.

Exit codes — THE CONTRACT (a change here is a breaking change):

    0 — success. Includes `action: no_candidates` (an empty candidate set is a
        SUCCESS, not a failure — see above) and `action: unchanged` (idempotent
        re-run of an unchanged source).
    1 — argparse / usage error.
    2 — input validation: SOURCE_NOT_FOUND | INVALID_SOURCE_PATH |
        SOURCE_TOO_LARGE | SOURCE_CHANGED_DURING_EXTRACTION |
        INVALID_SOURCE_HASH | INVALID_CANDIDATES_PATH |
        LAYOUT_CANNOT_INDEX_CLASSES (the prepare preflight: this layout maps no
        typed classes) | TYPED_DIR_NOT_COVERED_BY_LAYOUT (the G4 gate: the
        configured folder is invisible to the layout's read globs — the SAME
        refusal `wiki-config validate` renders, from the SAME helper).
    4 — CONTRACT VIOLATION ⇒ **ZERO files written**: EXTRACTION_PARSE_ERROR |
        CANDIDATES_TOO_LARGE | FIELD_TOO_LONG | UNKNOWN_FIELD |
        FIELD_QUOTE_NOT_IN_BODY | ONTOLOGY_VIOLATION | UNRESOLVED_REF |
        IN_BATCH_SLUG_COLLISION | DROPPED_CANDIDATE_STILL_REFERENCED |
        REQUIRES_STATUS_RECONCILIATION.
    5 — PARTIAL_INDEX_FAILURE | DB_WRITE_FAILED | IDEMPOTENCY_UPDATE_FAILED.
        `source_state` is NOT updated ⇒ the retry is safe.
    6 — MANIFEST_INVALID.

BEAD 063-04 (STUB): the package, the argparse surface, the exit-code table and
the `anthropic` gate — all landing BEFORE any logic exists that could violate
them. `prepare`/`apply` emit hardcoded stub envelopes; every other function
raises `NotImplementedError`. Beads 063-05…063-14 replace stub with logic, one
guarantee at a time.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sqlite3
import sys
from datetime import date
from pathlib import Path
from typing import Any

import frontmatter

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout_config import (
    LayoutConfig,
    glob_covers,
    resolve_layout_config,
    resolve_typed_write_dir,
    typed_write_refusal,
)
from scripts.wiki_index.security import PathTraversalError, validate_inside_vault
from scripts.wiki_index.sync_config import (
    _EXTRACT_DECISIONS_DIR_FIELDS,
    ExtractDecisionsDirs,
)
from scripts.wiki_skills._common import build_repo_config, emit
from scripts.wiki_skills._manifest_consumer import (
    WikiIngestError,
    index_from_manifest,
    validate_manifest,
)
from scripts.wiki_skills._resummarize import resolve_extract_decisions

from ._db import (
    check_idempotency,
    count_open_commitments,
    load_page_paths,
    load_target_statuses,
    load_existing_page_slugs,
    load_own_page_slugs,
    load_resolvable_targets,
    load_typed_pages,
    resolve_target_classes,
    update_idempotency_state,
)
from ._errors import ExtractionParseError, envelope_from_parse_error
from ._pages import backup_page, patch_frontmatter_scalar, render_page, write_page
from ._validation import (
    CANDIDATES_MAX_BYTES,
    check_in_batch_collisions,
    derive_slugs,
    page_refs,
    plan_reconciliation,
    validate_candidates_schema,
    validate_ontology,
    validate_refs,
)

logger = logging.getLogger("wiki_extract_decisions")

# The v1 roster — read from the CONFIG dataclass, never restated. `dirs` and the
# roster are the same three classes by construction, so they cannot drift apart.
ROSTER: tuple[str, ...] = _EXTRACT_DECISIONS_DIR_FIELDS

# 10 MiB, the house cap (`wiki_extract_concepts._sourcing`). Refuse, never truncate.
MAX_SOURCE_BODY_BYTES = 10 * 1024 * 1024

# ★ ZERO, and it is a safety property — see the module docstring. The precedent
# (`wiki_extract_concepts._validation._CANDIDATE_COUNT_MIN`) is 1; cloning it here
# would make "no decisions in this note" an exit-4 failure and hand the model a
# reason to fabricate one. 063-06 enforces it; the constant lives here, with its
# reason attached, so that no later bead can "restore parity" without reading why.
CANDIDATE_COUNT_MIN = 0


def _build_parser() -> argparse.ArgumentParser:
    """The CLI surface (Decision-17): `prepare` recon → orchestrator REASON →
    `apply` write. There is no single-command shape; the reasoning step is not
    ours to run."""
    p = argparse.ArgumentParser(
        prog="wiki-extract-decisions",
        description=(
            "Deterministic typed-knowledge extraction (TASK 063 / RFC-004). "
            "The calling agent runs `prepare` (recon + the ontology contract), "
            "synthesises candidates JSON in its own context, then runs `apply` "
            "to validate and write the typed pages + edges. This CLI never "
            "calls an LLM."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True, metavar="{prepare,apply}")

    pp = sub.add_parser(
        "prepare",
        help="Recon + the ontology contract + the --source-hash handshake.")
    pp.add_argument("--vault", required=True,
                    help="Vault ID (must be registered in the vaults table)")
    pp.add_argument("--vault-root", required=True, type=Path,
                    help="Absolute path to the vault root directory")
    pp.add_argument("--source-page", required=True,
                    help="Vault-relative path of the summarised source note")
    pp.add_argument("--db-path", default=None,
                    help="Override the index DB path (else: identity config → global)")

    pa = sub.add_parser(
        "apply",
        help="Validate candidates against the ontology, then write typed pages.")
    pa.add_argument("--vault", required=True,
                    help="Vault ID (must be registered in the vaults table)")
    pa.add_argument("--vault-root", required=True, type=Path,
                    help="Absolute path to the vault root directory")
    pa.add_argument("--source-page", required=True,
                    help="Vault-relative path of the summarised source note")
    pa.add_argument("--source-hash", required=True,
                    help="The sha256 `prepare` emitted. A mismatch is "
                         "SOURCE_CHANGED_DURING_EXTRACTION (exit 2) — the "
                         "candidates describe a body that no longer exists.")
    pa.add_argument("--db-path", default=None,
                    help="Override the index DB path")
    pa.add_argument("--ingest", action="store_true",
                    help="Index the written pages in-process from the manifest")
    pa.add_argument("--no-reconcile", action="store_true",
                    help="Refuse the batch rather than patch a supersede target's "
                         "status (G3). The batch is refused WHOLE — a partial "
                         "write would leave the graph asserting two live decisions.")
    pa.add_argument("--prune", action="store_true",
                    help="Report pages from a previous extraction that this batch "
                         "no longer produces. They are REPORTED, never auto-deleted "
                         "(Class A is the operator's — R-063-9).")
    pa.add_argument("--force", action="store_true",
                    help="Re-extract even when the source is unchanged")
    pa.add_argument("--orchestrator-id", default=None,
                    help="Opaque ID of the calling agent, recorded in the manifest")

    cand = pa.add_mutually_exclusive_group(required=True)
    cand.add_argument("--candidates-file", type=Path, default=None,
                      help="Path to the candidates JSON")
    cand.add_argument("--candidates-stdin", action="store_true",
                      help="Read the candidates JSON from stdin")
    return p


def _read_source_bounded(path: Path) -> bytes:
    """O_NOFOLLOW + fstat-then-bounded-read (the house pattern,
    `wiki_extract_concepts._sourcing._read_file_bounded`).

    Two things at once: it closes the TOCTOU between `stat().st_size` and a later
    `read_bytes()`, and O_NOFOLLOW makes a symlink swapped in AFTER the containment
    check raise ELOOP instead of redirecting the read outside the vault. Raises
    `ValueError` on the size cap, `OSError` on ELOOP/ENOENT."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        if os.fstat(fd).st_size > MAX_SOURCE_BODY_BYTES:
            raise ValueError("source too large")
        data = os.read(fd, MAX_SOURCE_BODY_BYTES + 1)
    finally:
        os.close(fd)
    if len(data) > MAX_SOURCE_BODY_BYTES:
        raise ValueError("source too large")
    return data


def _ontology_contract(config: LayoutConfig, roster: tuple[str, ...]) -> dict[str, Any]:
    """The layout's ontology, projected into the contract the REASON step obeys.

    Scoped to the roster: an edge whose domain AND range both fall outside the three
    classes this rail extracts is not a rule the reasoning step can violate, and
    shipping it would just be noise in the prompt. `closed_types` is carried through
    verbatim — it is the layout's statement about whether an unknown class is an
    error, and that is not ours to soften."""
    onto = config.ontology
    if onto is None:
        return {}
    rset = set(roster)
    return {
        "closed_types": onto.closed_types,
        "edges": [
            {"edge": e.edge, "from": list(e.frm), "to": list(e.to)}
            for e in onto.edges
            if rset & set(e.frm) or rset & set(e.to)
        ],
        "properties": [
            {"class": p.page_class, "field": p.field, "enum": list(p.enum)}
            for p in onto.properties
            if p.page_class in rset
        ],
    }


class _Refused(Exception):
    """A preflight refusal, carrying its envelope + exit code.

    An exception rather than an `int` return so the SAME preflight can serve BOTH
    `prepare` and `apply` without either of them re-deciding what a refusal looks
    like. Two copies of the G4 gate is the exact failure this task exists to
    prevent — it would let `apply` write into a folder `prepare` had refused."""

    def __init__(self, envelope: dict[str, Any], exit_code: int = 2) -> None:
        super().__init__(envelope.get("error", "REFUSED"))
        self.envelope = envelope
        self.exit_code = exit_code


class _Context:
    """Everything both subcommands resolve identically: the source, the layout, the
    roster, and the walker-verified typed dirs."""

    def __init__(
        self, *, vault_root: Path, source_page: str, source_path: Path,
        body: bytes, source_hash: str, source_slug: str, config: LayoutConfig,
        roster: tuple[str, ...], typed_dirs: dict[str, str],
    ) -> None:
        self.vault_root = vault_root
        self.source_page = source_page
        self.source_path = source_path
        self.body = body
        self.source_hash = source_hash
        self.source_slug = source_slug
        self.config = config
        self.roster = roster
        self.typed_dirs = typed_dirs
        self.ontology = _ontology_contract(config, roster)
        # ★ Can the walker SEE the source note itself? If not, a `[[backlink]]` to it
        # would be an ORPHAN LINK of our own manufacture — the exact defect the rail
        # exists to prevent. Found by G2 refusing our own output.
        self.source_indexable = glob_covers(config, source_page)


def _resolve_context(args: argparse.Namespace) -> _Context:
    """The shared preflight. Raises `_Refused` (exit 2) rather than returning an
    error, so a caller CANNOT proceed past a refusal by forgetting to check.

    ★ THE G4 PREFLIGHT — refuse EARLY, refuse LOUDLY:

      LAYOUT_CANNOT_INDEX_CLASSES     the `type_mapping` routes NONE of the roster
                                      (karpathy, stock obsidian-personal) — a typed
                                      page here would be indexed under no class
      TYPED_DIR_NOT_COVERED_BY_LAYOUT the folder is invisible to the read globs —
                                      the SAME code, from the SAME helper, that
                                      `wiki-config validate` renders

    Refusing costs the operator one message. Not refusing costs them a decision page
    that is written, never indexed, and raises no lint issue — because a
    glob-invisible page is never discovered by the walk, so nothing downstream can
    report it.
    """
    vault_root = args.vault_root.resolve()
    source_page = str(args.source_page)

    if Path(source_page).is_absolute():
        raise _Refused({
            "action": "refused", "error": "INVALID_SOURCE_PATH",
            "message": "--source-page must be vault-relative, not absolute"})

    source_path = vault_root / source_page

    # ORDER, deliberately: existence FIRST (so a plain typo gets SOURCE_NOT_FOUND,
    # not the alarming INVALID_SOURCE_PATH — different diagnoses, different operator
    # actions), then CONTAINMENT, and only then the read. Nothing is read before
    # containment: `is_file()` is a stat, and a traversal or an outward symlink still
    # stats True and is refused on the next line.
    if not source_path.is_file():
        raise _Refused({
            "action": "refused", "error": "SOURCE_NOT_FOUND",
            "message": f"source page not found: {source_page}"})
    try:
        validate_inside_vault(source_path, vault_root)
    except (PathTraversalError, OSError):
        raise _Refused({
            "action": "refused", "error": "INVALID_SOURCE_PATH",
            "message": "--source-page resolves outside the vault"}) from None

    config = resolve_layout_config(vault_root)

    # ---- G4, conjunct 1: does the layout ROUTE the typed classes? ----
    roster = tuple(c for c in ROSTER if c in config.type_mapping)
    if not roster:
        raise _Refused({
            "action": "refused", "error": "LAYOUT_CANNOT_INDEX_CLASSES",
            "layout": config.layout, "missing_classes": list(ROSTER),
            "message": (
                f"layout '{config.layout}' maps NONE of {list(ROSTER)} in its "
                f"`type_mapping`, so a typed page written here would be indexed "
                f"under no class at all. Add them to `type_mapping` in "
                f".wiki/layout.yaml, or use a layout that has them "
                f"(cybos, dev-project).")})

    # ---- the per-folder policy (cascading) → the folder names ----
    # No `extract_decisions` block ⇒ `None`, and that is NOT a refusal: an explicit
    # invocation is consent. `None` means "never AUTO-dispatched" (the 063-17
    # marker), so the defaults apply here.
    policy = resolve_extract_decisions(source_path, vault_root=vault_root)
    dirs_cfg = policy.dirs if policy is not None else ExtractDecisionsDirs()

    # ---- G4, conjunct 2: can the WALKER SEE the write dirs? ----
    # ONE authority decides (`resolve_typed_write_dir`); the other only EXPLAINS
    # (`typed_write_refusal`). An earlier draft asked the explainer first and then
    # `assert`ed the decider agreed — turning any disagreement between them into a
    # crash the operator can do nothing with.
    typed_dirs: dict[str, str] = {}
    for cls in roster:
        dir_name = str(getattr(dirs_cfg, cls))
        write_dir = resolve_typed_write_dir(
            config, dir_name=dir_name, source_rel=source_page)
        if write_dir is None:
            refusal = typed_write_refusal(
                config, dir_name=dir_name, source_rel=source_page) or "unmatched"
            raise _Refused({
                "action": "refused", "error": "TYPED_DIR_NOT_COVERED_BY_LAYOUT",
                "layout": config.layout, "page_class": cls,
                "dir_name": dir_name, "reason": refusal,
                "message": (
                    f"the folder configured for `{cls}` is not visible to the "
                    f"walker of layout '{config.layout}' (reason: {refusal}). A "
                    f"page written there would never be indexed and would raise no "
                    f"lint issue. `wiki-config validate` reports the same finding.")})
        typed_dirs[cls] = write_dir

    try:
        body = _read_source_bounded(source_path)
    except ValueError:
        raise _Refused({
            "action": "refused", "error": "SOURCE_TOO_LARGE",
            "message": f"source page exceeds the {MAX_SOURCE_BODY_BYTES}-byte cap",
        }) from None
    except OSError:
        raise _Refused({
            "action": "refused", "error": "SOURCE_NOT_FOUND",
            "message": "source page could not be opened (symlink swap or I/O error)",
        }) from None

    return _Context(
        vault_root=vault_root, source_page=source_page, source_path=source_path,
        body=body, source_hash=hashlib.sha256(body).hexdigest(),
        source_slug=Path(source_page).stem, config=config, roster=roster,
        typed_dirs=typed_dirs,
    )


def prepare(args: argparse.Namespace) -> int:
    """Deterministic recon + the ontology contract + the `--source-hash` handshake.

    NO LLM CALL (Decision-17). The orchestrator takes this envelope, reads the source
    body, and synthesises candidates in its OWN context.

    ★ `vacuous_validation` — TASK 061's lesson, applied to ourselves before the first
    line of logic. `dev-project` maps the typed classes but declares NO `ontology:`
    block, so G1 there degrades to a roster-only check and G3 is moot. The delta
    property still holds (both sides vacuous) — so this is not a lie. But a green
    `apply` there means "validated almost nothing", and that must be ANNOUNCED, not
    inferred from a zero:

        a validator that examined nothing must not look green.
    """
    try:
        ctx = _resolve_context(args)
    except _Refused as r:
        return emit(r.envelope, exit_code=r.exit_code)

    repo = make_repo(build_repo_config(
        args.vault, vault_root=ctx.vault_root, db_path_flag=args.db_path))
    try:
        is_unchanged = check_idempotency(
            repo, args.vault, ctx.source_slug, ctx.source_hash)
        known = load_typed_pages(repo, args.vault, ctx.roster)
        existing_slugs = load_existing_page_slugs(repo, args.vault)
        open_commitments = count_open_commitments(repo, args.vault)
    finally:
        repo.close()

    config, roster, ontology = ctx.config, ctx.roster, ctx.ontology
    typed_dirs, source_slug = ctx.typed_dirs, ctx.source_slug
    source_hash, source_page = ctx.source_hash, ctx.source_page
    drift = [
        {"class": r.page_class, "edge": r.edge,
         "expect_status": r.expect_status,
         "forbid_status": list(r.forbid_status or ())}
        for r in config.drift_rules if r.page_class in roster
    ]

    return emit({
        "action": "prepared",
        "vault_id": args.vault,
        "source_slug": source_slug,
        "source_path": source_page,          # RELATIVE — CWE-209, never the abs path
        "source_hash": source_hash,
        "is_unchanged": is_unchanged,
        "layout": config.layout,
        "roster": list(roster),
        "ontology": ontology,
        "drift_rules": drift,
        "typed_dirs": typed_dirs,
        "known_typed_pages": known,
        "existing_page_slugs": existing_slugs,
        "open_commitments": open_commitments,   # DATA, never a defect (Q-063-4)
        # ★ The house-standard denominators. `roster_size` is what G1 CAN check;
        # the other three are what the ONTOLOGY gives it to check WITH. Zeros here
        # with a green apply mean "validated almost nothing" — which is why the
        # marker below exists rather than leaving the reader to infer it.
        "validation": {
            "roster_size": len(roster),
            "edges_checked": len(ontology.get("edges", [])),
            "properties_checked": len(ontology.get("properties", [])),
            "links_checked": len(existing_slugs),
        },
        "vacuous_validation": not ontology,
    })



def _load_candidates(args: argparse.Namespace) -> Any:
    """Read the candidates payload. Overflow REFUSES, never truncates (R-063-11) —
    a silently truncated batch loses its last decisions without a word."""
    if args.candidates_stdin:
        raw = sys.stdin.read(CANDIDATES_MAX_BYTES + 1)
    else:
        path = Path(args.candidates_file)
        if not path.is_file():
            raise _Refused({
                "action": "refused", "error": "INVALID_CANDIDATES_PATH",
                "message": "--candidates-file not found"})
        raw = path.read_text(encoding="utf-8")
    if len(raw.encode("utf-8")) > CANDIDATES_MAX_BYTES:
        raise ExtractionParseError(
            f"candidates payload exceeds the {CANDIDATES_MAX_BYTES}-byte cap",
            error="CANDIDATES_TOO_LARGE")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExtractionParseError(
            "candidates payload is not valid JSON",
            error="EXTRACTION_PARSE_ERROR", reason="JSON_DECODE") from exc


def apply(args: argparse.Namespace) -> int:
    """Validate every guarantee, THEN write. NO LLM CALL (Decision-17).

    ★★ THE ORDERING IS NORMATIVE (063-09), AND IT IS A REAL BUG, NOT BOOKKEEPING.

        1. re-check `--source-hash`               (the candidates describe THIS body)
        2. schema + anti-fabrication              (063-06)
        3. slugs, via the LAYOUT'S strategy       (063-07)
        4. IN-BATCH collision  → refuse           (063-07)
        5. EXISTING-PAGE collision → DROP         (benign; someone else owns that page)
        6. ★ G1 + G2 over the POST-DROP batch     (063-08, 063-10)
        7. ★ a SURVIVOR referencing a DROPPED one → REFUSE
        8. write                                  (063-12)

    Why step 7 exists, and why step 6 must come AFTER step 5:

    Validate `{D, R}` where `D.implements: [[r-slug]]`. The range check passes against
    the IN-BATCH R. Then R is dropped on a slug collision. Then D is written anyway —
    and D's edge now resolves to the PRE-EXISTING page of that slug, whose class
    (`summary`) is not in `implements.to`. We have just AUTHORED an ontology violation.

    And BOTH halves of the acceptance property are blind to it: the counts still
    reconcile (the dropped candidate was never written), so G6 passes; and G1/G2
    already passed — against a batch that no longer exists.

        A VALIDATION COMPUTED AGAINST A HYPOTHETICAL BATCH IS NOT A VALIDATION OF
        WHAT GOT WRITTEN. A benign drop is benign only when nothing depends on it.

    So the post-drop list is the ONLY list G1/G2 can see — not "called in the right
    order", but structurally the only list in scope. And `referenced_dropped` is
    computed over THE SAME extracted-ref set G2 uses (`page_refs` over the RENDERED
    page), never over an ad-hoc peek at `edges` — otherwise a bare ID in prose
    ("заменяет DEC-004") referencing a dropped candidate slips past this gate while
    G2 catches only its unresolved cousin: two ref populations, one of them wrong.

    ANY contract violation ⇒ exit 4 and ZERO files written. A partially written typed
    batch is worse than none: the graph would assert edges to pages that do not exist.
    """
    try:
        ctx = _resolve_context(args)
    except _Refused as r:
        return emit(r.envelope, exit_code=r.exit_code)

    # 1. the handshake. The candidates describe a body; if that body changed, they
    #    describe something that no longer exists.
    if args.source_hash != ctx.source_hash:
        return emit({
            "action": "refused", "error": "SOURCE_CHANGED_DURING_EXTRACTION",
            "message": "the source body changed between prepare and apply; "
                       "re-run prepare (the candidates describe the old body)",
        }, exit_code=2)

    # 2-4. PURE VALIDATION — no repo is open yet, so "a contract violation writes
    #      ZERO files" is true BY CONSTRUCTION, not by care.
    try:
        payload = _load_candidates(args)
        candidates = validate_candidates_schema(
            payload, source_body=ctx.body.decode("utf-8", "replace"),
            roster=ctx.roster)
        if not candidates:
            # ★ AN EMPTY SET IS SUCCESS (R-063-7). A note with no decisions in it is
            # a normal note. If this were a failure, the cheapest green run would be
            # to invent one.
            return emit({
                "action": "no_candidates", "written": [], "dropped": [],
                "source_slug": ctx.source_slug,
                "message": "no typed knowledge in this source — this is a SUCCESS, "
                           "not a failure",
            })
        slugs = derive_slugs(candidates, ctx.config)
        check_in_batch_collisions(candidates, slugs)
    except _Refused as r:
        return emit(r.envelope, exit_code=r.exit_code)
    except ExtractionParseError as exc:
        return emit(envelope_from_parse_error(exc), exit_code=4)

    repo = make_repo(build_repo_config(
        args.vault, vault_root=ctx.vault_root, db_path_flag=args.db_path))
    try:
        if check_idempotency(repo, args.vault, ctx.source_slug, ctx.source_hash) \
                and not args.force:
            return emit({
                "action": "unchanged", "written": [], "dropped": [],
                "source_slug": ctx.source_slug,
                "message": "source unchanged since the last extraction; "
                           "pass --force to re-extract",
            })

        # 5. EXISTING-PAGE collision → DROP. The `prepare` snapshot is a HINT for the
        #    orchestrator; the gate is this RE-CHECK against the open repo. A slug can
        #    appear between prepare and apply — the orchestrator's reasoning takes real
        #    time — and a slug collision does not error, it OVERWRITES.
        # ★ OURS vs SOMEONE ELSE'S (R-063-9). The drop protects a page we do not own.
        # A page carrying `extracted_from: <our source>` IS ours — re-extracting must
        # UPDATE it, not drop it. Without this line the rail is a one-shot: it can
        # create knowledge and never correct it, because the second run drops
        # everything the first one wrote.
        existing = set(load_existing_page_slugs(repo, args.vault))
        ours = load_own_page_slugs(repo, args.vault, ctx.source_slug)
        kept: list[dict[str, Any]] = []
        kept_slugs: list[str] = []
        dropped: list[dict[str, Any]] = []
        for cand, slug in zip(candidates, slugs):
            if slug in existing and slug not in ours:
                logger.warning(
                    "dropping candidate: slug %r already exists in the vault "
                    "(another source owns that page)", slug)
                dropped.append({"slug": slug, "reason": "existing-page-collision"})
            else:
                kept.append(cand)
                kept_slugs.append(slug)

        # 6. ★ G1 + G2 over the POST-DROP batch — `kept` is the ONLY list from here on.
        batch_classes = {s: str(c["class"]) for c, s in zip(kept, kept_slugs)}
        edge_targets = sorted({
            t for c in kept for targets in (c.get("edges") or {}).values()
            for t in targets})
        db_classes = resolve_target_classes(repo, args.vault, edge_targets)
        rendered = [
            render_page(cand, slug=slug, vault_id=args.vault,
                        source_slug=ctx.source_slug, today=date.today(),
                        classification=_source_classification(ctx),
                        source_indexable=ctx.source_indexable)
            for cand, slug in zip(kept, kept_slugs)
        ]
        try:
            validate_ontology(
                kept, ontology=ctx.ontology, batch_classes=batch_classes,
                db_classes=db_classes)
            # The batch's own slugs resolve, and so does the SOURCE — but only when
            # the walker can see it. If it can see it, the next `--full` indexes it,
            # so the backlink resolves even against a stale DB; if it cannot, we did
            # not author a link to it at all (see `render_page`).
            resolvable = load_resolvable_targets(repo, args.vault) | set(kept_slugs)
            if ctx.source_indexable:
                resolvable.add(ctx.source_slug)
            links_checked = validate_refs(
                rendered, config=ctx.config, resolvable=resolvable)

            # 7. ★ A SURVIVOR REFERENCING A DROPPED CANDIDATE. Computed over the SAME
            #    ref set G2 uses — the rendered page — so a bare ID in prose counts.
            #    G2 could never catch this: the dropped slug RESOLVES (to someone
            #    else's page). That is the whole bug.
            dropped_slugs = {d["slug"] for d in dropped}
            still_referenced = [
                {"survivor": kept_slugs[i], "dropped_target": target}
                for i, text in enumerate(rendered)
                for target in page_refs(text, ctx.config)
                if target in dropped_slugs
            ]
            if still_referenced:
                raise ExtractionParseError(
                    "a surviving candidate references a DROPPED one — its edge would "
                    "silently re-point at the pre-existing page of that slug",
                    error="DROPPED_CANDIDATE_STILL_REFERENCED",
                    violations=still_referenced)

            # ★ G3 — supersede reconciliation. NOT FLAG-GATED: by authoring
            # `supersedes: [[D1]]` the operator has ALREADY asserted D1 is superseded,
            # and leaving its status untouched would fire the vault's own drift rule.
            # An opt-in flag would make the headline invariant conditional on a flag.
            #
            # `--no-reconcile` is the OPT-OUT, and it refuses the WHOLE BATCH: writing
            # the pages WITHOUT the patch would silently break G3 and turn the opt-out
            # into a footgun that leaves the vault non-strict-clean.
            supersede_targets = sorted({
                t for c in kept
                for t in (c.get("edges") or {}).get("supersedes", [])})
            if supersede_targets and args.no_reconcile:
                raise ExtractionParseError(
                    "the batch supersedes existing pages; --no-reconcile refuses it "
                    "WHOLE rather than writing pages whose targets keep a status the "
                    "vault's drift rule contradicts",
                    error="REQUIRES_STATUS_RECONCILIATION",
                    violations=[{"target": t} for t in supersede_targets])
            reconcile_plan = plan_reconciliation(
                kept, config=ctx.config,
                target_status=load_target_statuses(
                    repo, args.vault, supersede_targets),
                target_class=db_classes)

            # G1 SELF-CHECK ON OUR OWN WRITE: the value we are about to patch in must
            # be in the target class's enum. The v2 bug (`status: superseded` on a
            # `requirement`) would be caught HERE even if it slipped past the config.
            enums = {p["class"]: p["enum"]
                     for p in ctx.ontology.get("properties", [])
                     if p["field"] == "status"}
            for row in reconcile_plan:
                enum = enums.get(row["page_class"])
                if enum is not None and row["to"] not in enum:
                    raise ExtractionParseError(
                        f"the reconciliation would author a status outside the class "
                        f"enum — the drift rule and the ontology disagree",
                        error="ONTOLOGY_VIOLATION",
                        violations=[{"kind": "status", "class": row["page_class"],
                                     "detail": f"`{row['to']}` not in {enum}"}])
        except ExtractionParseError as exc:
            return emit(envelope_from_parse_error(exc), exit_code=4)

        # 8. Only now: write.
        written: list[dict[str, Any]] = []
        for cand, slug, text in zip(kept, kept_slugs, rendered):
            typed_dir = ctx.typed_dirs[str(cand["class"])]
            try:
                path, action = write_page(ctx.vault_root, typed_dir, slug, text)
            except PathTraversalError as exc:
                return emit({
                    "action": "refused", "error": "INVALID_SOURCE_PATH",
                    "message": str(exc), "written": [w["path"] for w in written],
                }, exit_code=4)
            written.append({
                "kind": str(cand["class"]),
                "path": path.relative_to(ctx.vault_root).as_posix(),
                "action": action, "scope": "vault", "slug": slug,
            })

        # The reconciliation patches — AFTER the new pages exist, so a failure here
        # never leaves a target marked superseded by a page that does not exist.
        #
        # ★ The candidate count is FROZEN before the patched pages join `written`.
        # `written` is the MANIFEST list (everything we touched, G5), and a patched page
        # is something we touched but did NOT extract. Counting it as a written
        # CANDIDATE would report `submitted: 2, written: 3` — a denominator that lies,
        # and in the one envelope whose whole job is honest denominators.
        candidates_written = len(written)
        reconciled: list[dict[str, Any]] = []
        page_paths = load_page_paths(
            repo, args.vault, [r["slug"] for r in reconcile_plan])
        for row in reconcile_plan:
            rel = page_paths.get(row["slug"])
            if rel is None:
                continue
            target_path = ctx.vault_root / rel
            backup = backup_page(ctx.vault_root, target_path)
            old_value, new_value = patch_frontmatter_scalar(
                target_path, "status", str(row["to"]))
            reconciled.append({**row, "from": old_value, "path": rel,
                               "backup": backup})
            # ★ G5: the PATCHED page goes into the manifest too. A mutated file whose
            # DB row still carries the old hash is a `hash-mismatch` — a lint issue we
            # would have CREATED while fixing another one.
            written.append({
                "kind": row["page_class"], "path": rel, "action": "updated",
                "scope": "vault", "slug": row["slug"],
            })

        manifest = {
            "status": "ok",
            "vault_id": args.vault,
            "source": {"slug": ctx.source_slug, "hash": ctx.source_hash},
            "written": written,
            "mentioned": [],
            "log_event": {
                # `ingest` — an ALLOWED value. `log_events.event_type` carries a CHECK
                # constraint, and ZERO-DDL (I-1) means the rail does not get to invent
                # a new enum member for itself: `user_version` stays 7. The rail is
                # identified by `source_kind` in `source_state` instead, which is a
                # free-text partition key.
                "event_type": "ingest",
                "source_slug": ctx.source_slug,
                "orchestrator_id": args.orchestrator_id,
            },
        }

        index_result: dict[str, Any] | None = None
        if args.ingest:
            try:
                validate_manifest(manifest, args.vault, ctx.vault_root)
            except WikiIngestError as exc:
                return emit({
                    "action": "refused", "error": "MANIFEST_INVALID",
                    "message": str(exc)}, exit_code=6)
            index_result = index_from_manifest(
                manifest, args.vault, ctx.vault_root, repo=repo)
            if index_result.get("failed"):
                # ★ `source_state` is NOT updated ⇒ THE RETRY IS SAFE (the C-1
                # invariant). Marking the source "done" before the index succeeded
                # would make the retry a silent no-op and the pages would never index.
                return emit({
                    "action": "partial", "error": "PARTIAL_INDEX_FAILURE",
                    "written": [w["path"] for w in written],
                    "failed": index_result["failed"],
                    "message": "pages written but not all indexed; source_state left "
                               "UNSET so a retry re-indexes them",
                }, exit_code=5)

        try:
            update_idempotency_state(
                repo, args.vault, ctx.source_slug, ctx.source_hash)
        except sqlite3.OperationalError:
            return emit({
                "action": "partial", "error": "IDEMPOTENCY_UPDATE_FAILED",
                "written": [w["path"] for w in written],
                "message": "pages written + indexed, but source_state was not "
                           "recorded; the next run will safely re-extract",
            }, exit_code=5)
    finally:
        repo.close()

    return emit({
        "action": "applied",
        "vault_id": args.vault,
        "source_slug": ctx.source_slug,
        "layout": ctx.config.layout,
        "typed_dirs": ctx.typed_dirs,
        "written": written,
        "dropped": dropped,
        "reconciled": reconciled,
        "indexed": index_result,
        "manifest": manifest,
        "validation": {
            "roster_size": len(ctx.roster),
            "edges_checked": len(ctx.ontology.get("edges", [])),
            "properties_checked": len(ctx.ontology.get("properties", [])),
            "links_checked": links_checked,
            "candidates_submitted": len(candidates),
            "candidates_written": candidates_written,
            "candidates_dropped": len(dropped),
        },
        "vacuous_validation": not ctx.ontology,
    })


def _source_classification(ctx: _Context) -> str | None:
    """The SOURCE page's `classification:`, inherited by every page we generate from
    it (R-063-10(b)) — never the vault default.

    Honest statement of what this does TODAY: nothing observable. Policy is
    declared-but-off, and `classification-leak` fires only on `cited`/`verifies` refs,
    which typed pages do not carry. It is here because the moment R-16 is switched on,
    a decision extracted from a `confidential` transcript that silently picked up the
    vault's `default_level` turns this rail into a DECLASSIFICATION PUMP — a security
    regression created by a config flip somewhere else, in a rail nobody re-audits."""
    try:
        post = frontmatter.loads(ctx.body.decode("utf-8", "replace"))
    except Exception:
        return None
    value = post.metadata.get("classification")
    return str(value) if isinstance(value, str) and value.strip() else None


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.cmd == "prepare":
        return prepare(args)
    if args.cmd == "apply":
        return apply(args)
    return 1  # unreachable (subparser is required); mypy-strict likes the net


if __name__ == "__main__":
    sys.exit(main())
