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
import sys
from pathlib import Path

from scripts.wiki_skills._common import emit

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


def prepare(args: argparse.Namespace) -> int:
    """STUB (063-04) → LOGIC (063-05).

    Will: resolve the layout + the cascading `extract_decisions` policy for the
    source note's folder; PREFLIGHT G4 (the layout maps the typed classes AND
    `resolve_typed_write_dir` finds a walker-visible folder for each — refusing
    with LAYOUT_CANNOT_INDEX_CLASSES / TYPED_DIR_NOT_COVERED_BY_LAYOUT rather
    than writing a page nothing will ever index); hash the source body; check
    `source_state` for `is_unchanged`; load the known typed pages and existing
    slugs; and emit the ONTOLOGY CONTRACT the REASON step must obey — the class
    roster, every edge's domain/range, every class's `status` enum — plus the
    house-standard denominators (`validation: {roster_size, edges_checked,
    properties_checked, links_checked}`) and a `vacuous_validation: true` marker
    when the layout declares no `ontology:` block at all.

    That marker is TASK 061's lesson, applied before the first line of logic: a
    validator that examined NOTHING must not look green.
    """
    return emit({
        "action": "stub",
        "source_page": args.source_page,
        "source_slug": "",
        "source_hash": "",
        "is_unchanged": False,
        "ontology": {},
        "known_typed_pages": [],
        "existing_page_slugs": [],
        "typed_dirs": {},
        "validation": {
            "roster_size": 0,
            "edges_checked": 0,
            "properties_checked": 0,
            "links_checked": 0,
        },
        "vacuous_validation": True,
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
