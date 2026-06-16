"""`wiki-health` CLI (TASK 036 / R-15, Slice A2, ADR-006) — READ-ONLY derived
knowledge-health report over the event graph + frontmatter. One subcommand:

  wiki-health coverage --vault <vid> [--class C]   # pages missing an expected relation

Coverage rules are layout-config-driven (`coverage_rules`; the `cybos` layout ships
them, other layouts default to none → an empty report). A gap is DATA, not a failure,
so the CLI ALWAYS exits 0 on success — contrast `wiki-lint`, where the sibling
lifecycle-drift check (Slice A1) is a *contradiction* and gates `--strict`.

Decision-17: deterministic plumbing (SQL + config; no `import anthropic`); one JSON
envelope + a stable exit code; the slug/edge/field values are BOUND DAL params, never
string-composed (injection-safe — TASK 013 posture). Read-only — no DB writes.

Exit codes: 0 ok (incl. gaps found) · 2 INVALID_CLASS · 6 VAULT_NOT_FOUND.
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
        # Coverage rules ride the vault's LAYOUT grammar — resolve from the REGISTERED
        # root_path (not a CWD walk), so the report works from any directory.
        layout = resolve_layout_config(vault.root_path)
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
    finally:
        repo.close()


if __name__ == "__main__":
    sys.exit(main())
