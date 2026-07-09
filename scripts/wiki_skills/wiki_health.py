"""`wiki-health` CLI (TASK 036 / R-15, Slice A2, ADR-006; TASK 054 / R-19) — READ-ONLY
derived knowledge-health report over the event graph + frontmatter. Two subcommands:

  wiki-health coverage --vault <vid> [--class C]   # pages missing an expected relation
  wiki-health ontology --vault <vid> [--class C]   # pages contradicting the ontology contract

Rules are layout-config-driven (`coverage_rules` / the `ontology:` block; the `cybos`
layout ships them, other layouts default to none → an empty report). A gap / violation
report from THIS CLI is DATA, not a failure, so it ALWAYS exits 0 on success — contrast
`wiki-lint`, where the sibling lifecycle-drift and ontology-violation checks are
*contradictions* and gate `--strict`.

Decision-17: deterministic plumbing (SQL + config; no `import anthropic`); one JSON
envelope + a stable exit code; the slug/edge/field values are BOUND DAL params, never
string-composed (injection-safe — TASK 013 posture). Read-only — no DB writes.

Exit codes: 0 ok (incl. gaps/violations found) · 2 INVALID_CLASS · 6 VAULT_NOT_FOUND.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout_config import resolve_layout_config
from scripts.wiki_skills._common import (
    build_repo_config,
    emit,
    resolve_vault_root_for_cli,
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="wiki-health",
        description="Read-only derived knowledge-health report (TASK 036 / R-15).")
    sub = p.add_subparsers(dest="cmd", required=True)
    cov = sub.add_parser("coverage", help="pages missing an expected edge/field")
    cov.add_argument("--vault", required=True, help="vault_id to analyze.")
    cov.add_argument("--class", dest="page_class", default=None,
                     help="restrict the report to ONE page class (e.g. requirement).")
    cov.add_argument("--db-path", default=None)
    cov.add_argument("--vault-root", default=None)
    ont = sub.add_parser("ontology", help="pages contradicting the ontology contract (R-19)")
    ont.add_argument("--vault", required=True, help="vault_id to analyze.")
    ont.add_argument("--class", dest="page_class", default=None,
                     help="restrict the report to ONE offending page class.")
    ont.add_argument("--db-path", default=None)
    ont.add_argument("--vault-root", default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    config = build_repo_config(
        args.vault, vault_root=resolve_vault_root_for_cli(args),
        db_path_flag=args.db_path)
    repo = make_repo(config)
    try:
        vault = repo.get_vault(args.vault)
        if vault is None:
            return emit({"error": "VAULT_NOT_FOUND", "vault": args.vault}, 6)
        # Rules ride the vault's LAYOUT grammar — resolve from the REGISTERED root_path
        # (not a CWD walk), so the report works from any directory.
        layout = resolve_layout_config(vault.root_path)
        if args.cmd == "ontology":
            return _run_ontology(repo, args, layout)
        return _run_coverage(repo, args, layout)
    finally:
        repo.close()


def _run_coverage(repo: Any, args: argparse.Namespace, layout: Any) -> int:
    rules = list(layout.coverage_rules)
    if args.page_class is not None:
        classes = sorted({r.page_class for r in rules})
        if args.page_class not in classes:
            # No echo of the offending value beyond the valid set (CWE-209 posture,
            # mirrors wiki-graph's INVALID_KIND).
            return emit({"error": "INVALID_CLASS", "valid": classes}, 2)
        rules = [r for r in rules if r.page_class == args.page_class]
    gaps = repo.find_coverage_gaps(args.vault, rules)
    by_class: dict[str, int] = {}
    for g in gaps:
        by_class[g.page_class] = by_class.get(g.page_class, 0) + 1
    envelope: dict[str, Any] = {
        "action": "coverage",
        "vault": args.vault,
        "rules": len(rules),
        "total_gaps": len(gaps),
        "by_class": by_class,
        "gaps": [
            {"slug": g.page_slug, "project": g.page_project,
             "class": g.page_class, "kind": g.kind, "missing": g.detail}
            for g in gaps
        ],
    }
    if not rules:
        # vdd-multi critic-logic LOW: a layout with NO coverage rules (a non-cybos
        # vault, or a cybos vault whose root_path moved → resolve defaults to karpathy)
        # yields an empty report — say it was not analyzable rather than implying
        # "0 gaps = healthy".
        envelope["note"] = "no coverage rules configured for this layout"
    return emit(envelope)


def _run_ontology(repo: Any, args: argparse.Namespace, layout: Any) -> int:
    # TASK 054 / R-19 — read-only ontology-contract report. A violation is a CONTRADICTION,
    # but THIS surface is the report view (the `--strict`-gating rail is `wiki-lint`), so it
    # ALWAYS exits 0 (like `coverage`). No ontology block ⇒ empty report + a note.
    if layout.ontology is None:
        return emit({
            "action": "ontology", "vault": args.vault, "total_violations": 0,
            "by_kind": {}, "by_class": {}, "violations": [],
            "note": "no ontology contract configured for this layout",
        })
    violations = repo.find_ontology_violations(args.vault, layout.ontology)
    if args.page_class is not None:
        # the offending page classes that CAN appear = edge `from`/`to` ∪ property classes.
        classes = sorted(
            {c for e in layout.ontology.edges for c in (*e.frm, *e.to)}
            | {p.page_class for p in layout.ontology.properties})
        if args.page_class not in classes:
            # No echo of the offending value beyond the valid set (CWE-209 posture).
            return emit({"error": "INVALID_CLASS", "valid": classes}, 2)
        violations = [v for v in violations if v.page_class == args.page_class]
    by_kind: dict[str, int] = {}
    by_class: dict[str, int] = {}
    for v in violations:
        by_kind[v.kind] = by_kind.get(v.kind, 0) + 1
        by_class[v.page_class] = by_class.get(v.page_class, 0) + 1
    return emit({
        "action": "ontology",
        "vault": args.vault,
        "total_violations": len(violations),
        "by_kind": by_kind,
        "by_class": by_class,
        "violations": [
            {"slug": v.page_slug, "project": v.page_project, "class": v.page_class,
             "kind": v.kind, "ref": v.ref, "detail": v.detail, "target": v.target_slug}
            for v in violations
        ],
    })


if __name__ == "__main__":
    sys.exit(main())
