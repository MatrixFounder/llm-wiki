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
import os
import sys
from pathlib import Path
from typing import Any

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout_config import (
    LayoutConfig,
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
from scripts.wiki_skills._resummarize import resolve_extract_decisions

from ._db import (
    check_idempotency,
    count_open_commitments,
    load_existing_page_slugs,
    load_typed_pages,
)

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


def prepare(args: argparse.Namespace) -> int:
    """Deterministic recon + the ontology contract + the `--source-hash` handshake.

    NO LLM CALL (Decision-17). The orchestrator takes this envelope, reads the
    source body, and synthesises candidates in its OWN context.

    ★ THE G4 PREFLIGHT — refuse EARLY, refuse LOUDLY. Two refusals, both exit 2,
    both raised before any reasoning is requested:

      LAYOUT_CANNOT_INDEX_CLASSES     the layout's `type_mapping` maps NONE of the
                                      roster (karpathy, stock obsidian-personal)
      TYPED_DIR_NOT_COVERED_BY_LAYOUT the configured folder is invisible to the
                                      layout's read globs — the SAME helper, and the
                                      SAME code, `wiki-config validate` renders

    Refusing costs the operator one message. NOT refusing costs them a decision page
    that is written, never indexed, and raises no lint issue — because a
    glob-invisible page is never discovered by the walk, so nothing downstream can
    report it. That is why the gate is here and not after the write.

    ★ `vacuous_validation` — TASK 061's lesson, applied to ourselves before the
    first line of logic. `dev-project` maps the typed classes but declares NO
    `ontology:` block, so G1 there degrades to a roster-only check and G3 is moot.
    The delta property still holds (both sides vacuous) — this is not a lie. But a
    green `apply` there means "validated almost nothing", and that must be
    ANNOUNCED, not inferred. Hence the denominators AND the explicit marker:

        a validator that examined nothing must not look green.
    """
    vault_root = args.vault_root.resolve()
    source_page = str(args.source_page)

    if Path(source_page).is_absolute():
        return emit({
            "action": "refused", "error": "INVALID_SOURCE_PATH",
            "message": "--source-page must be vault-relative, not absolute",
        }, exit_code=2)

    source_path = vault_root / source_page

    # ORDER, deliberately: existence FIRST (so a plain typo gets SOURCE_NOT_FOUND,
    # not the alarming INVALID_SOURCE_PATH — they are different diagnoses and the
    # operator acts differently on each), then CONTAINMENT, and only then the read.
    # Nothing is read before containment: `is_file()` is a stat, and a traversal or
    # a symlink pointing outside still stats True and is refused on the next line.
    if not source_path.is_file():
        return emit({
            "action": "refused", "error": "SOURCE_NOT_FOUND",
            "message": f"source page not found: {source_page}",
        }, exit_code=2)
    try:
        validate_inside_vault(source_path, vault_root)
    except (PathTraversalError, OSError):
        return emit({
            "action": "refused", "error": "INVALID_SOURCE_PATH",
            "message": "--source-page resolves outside the vault",
        }, exit_code=2)

    config = resolve_layout_config(vault_root)

    # ---- G4 preflight, conjunct 1: does the layout ROUTE the typed classes? ----
    roster = tuple(c for c in ROSTER if c in config.type_mapping)
    if not roster:
        return emit({
            "action": "refused", "error": "LAYOUT_CANNOT_INDEX_CLASSES",
            "layout": config.layout,
            "missing_classes": list(ROSTER),
            "message": (
                f"layout '{config.layout}' maps NONE of {list(ROSTER)} in its "
                f"`type_mapping`, so a typed page written here would be indexed "
                f"under no class at all. Add them to `type_mapping` in "
                f".wiki/layout.yaml, or use a layout that has them "
                f"(cybos, dev-project)."),
        }, exit_code=2)

    # ---- the per-folder policy (cascading) → the folder names ----
    # A vault with NO `extract_decisions` block resolves to `None`, and that is not
    # a refusal: an explicit `prepare` invocation is consent. What `None` means is
    # "never AUTO-dispatched" (the 063-17 marker), so the defaults apply here.
    policy = resolve_extract_decisions(source_path, vault_root=vault_root)
    dirs_cfg = policy.dirs if policy is not None else ExtractDecisionsDirs()
    dirs = {cls: str(getattr(dirs_cfg, cls)) for cls in roster}

    # ---- G4 preflight, conjunct 2: can the WALKER SEE the write dirs? ----
    # ONE helper, TWO callers: `wiki-config validate` (063-03) calls the same
    # `typed_write_refusal`, so the two can never disagree about the same vault.
    # ONE authority decides (`resolve_typed_write_dir`); the other only EXPLAINS
    # (`typed_write_refusal`). An earlier draft asked the explainer first and then
    # `assert`ed the decider agreed — which turns any disagreement between them
    # into a crash instead of an envelope, and hides the disagreement behind an
    # assertion the operator can do nothing with.
    typed_dirs: dict[str, str] = {}
    for cls, dir_name in dirs.items():
        write_dir = resolve_typed_write_dir(
            config, dir_name=dir_name, source_rel=source_page)
        if write_dir is None:
            refusal = typed_write_refusal(
                config, dir_name=dir_name, source_rel=source_page) or "unmatched"
            return emit({
                "action": "refused", "error": "TYPED_DIR_NOT_COVERED_BY_LAYOUT",
                "layout": config.layout, "page_class": cls,
                "dir_name": dir_name, "reason": refusal,
                "message": (
                    f"the folder configured for `{cls}` is not visible to the "
                    f"walker of layout '{config.layout}' (reason: {refusal}). A "
                    f"page written there would never be indexed and would raise no "
                    f"lint issue. `wiki-config validate` reports the same finding."),
            }, exit_code=2)
        typed_dirs[cls] = write_dir

    # ---- the source: bounded read + hash + idempotency ----
    try:
        body_bytes = _read_source_bounded(source_path)
    except ValueError:
        return emit({
            "action": "refused", "error": "SOURCE_TOO_LARGE",
            "message": f"source page exceeds the {MAX_SOURCE_BODY_BYTES}-byte cap",
        }, exit_code=2)
    except OSError:
        return emit({
            "action": "refused", "error": "SOURCE_NOT_FOUND",
            "message": "source page could not be opened (symlink swap or I/O error)",
        }, exit_code=2)

    source_hash = hashlib.sha256(body_bytes).hexdigest()
    source_slug = Path(source_page).stem

    repo = make_repo(build_repo_config(
        args.vault, vault_root=vault_root, db_path_flag=args.db_path))
    try:
        is_unchanged = check_idempotency(repo, args.vault, source_slug, source_hash)
        known = load_typed_pages(repo, args.vault, roster)
        existing_slugs = load_existing_page_slugs(repo, args.vault)
        open_commitments = count_open_commitments(repo, args.vault)
    finally:
        repo.close()

    ontology = _ontology_contract(config, roster)
    drift = [
        {"class": r.page_class, "edge": r.edge,
         "expect_status": r.expect_status, "forbid_status": list(r.forbid_status or ())}
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



def apply(args: argparse.Namespace) -> int:
    """STUB (063-04) → LOGIC (063-06 … 063-14).

    Will, IN THIS ORDER (the ordering is normative — 063-09):
      1. re-check `--source-hash` against the body on disk;
      2. parse + strict-validate the candidates schema (063-06), including the
         mandatory verbatim `source_quote` — a quote that is not IN the body is
         a contract violation, which is what makes fabrication mechanically
         expensive rather than merely discouraged;
      3. derive slugs with the LAYOUT'S OWN `slug_strategy`; an in-batch slug
         collision REFUSES the batch (063-07) — two Russian titles collapsing to
         one transliterated slug would otherwise silently lose a decision, with
         zero lint issues;
      4. drop benign-skip candidates, THEN validate the POST-DROP batch (I-8) —
         a validation computed against a batch that is not the one being written
         is not a validation;
      5. G1: every candidate against the ontology — class ∈ roster, edge domain,
         edge RANGE (an out-of-batch target's class resolved FROM THE DB),
         `status` ∈ that class's enum. ALL violations listed at once;
      6. G2: every ref resolves (063-10);
      7. G3: supersede reconciliation, DRIVEN BY THE LAYOUT'S `drift_rules` —
         never a hardcoded `status: superseded` (063-13);
      8. write (063-12), atomically, only then;
      9. emit the manifest; `--ingest` indexes it in-process.

    ANY contract violation ⇒ exit 4 and ZERO files written. A partially written
    typed batch is worse than none: the graph would assert edges to pages that
    do not exist.
    """
    return emit({
        "action": "stub",
        "source_page": args.source_page,
        "written": [],
        "reconciled": [],
        "stale": [],
        "edges": [],
        "manifest": None,
    })


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.cmd == "prepare":
        return prepare(args)
    if args.cmd == "apply":
        return apply(args)
    return 1  # unreachable (subparser is required); mypy-strict likes the net


if __name__ == "__main__":
    sys.exit(main())
