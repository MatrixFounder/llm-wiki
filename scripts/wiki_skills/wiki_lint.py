"""`wiki-lint` CLI — real impl per task-001-29.

TASK 061 / R-061-2 — the envelope carries an additive `denominators` key: what EACH of
the two config-driven semantic checks actually examined (`lifecycle-drift` and
`ontology-violation` — the two that gate `--strict`, i.e. the CI rail). Without it,
`by_category` silently omitting a category is indistinguishable from a check that ran
against an EMPTY population (on the LIVE vault, `ontology-violation` examined 0 of 8836
refs — every one was a `mentioned` wikilink, not a declared edge). Denominators never
gate and never become issues: `total_issues`, `by_category` and the exit-code policy are
unchanged. See `lint.LintReport` for why the payload is per-CHECK-keyed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout import GLOBAL_VAULT_SENTINEL
from scripts.wiki_index.lint import (
    render_json_sidecar,
    render_markdown_report,
    run_all_checks_report,
)
from scripts.wiki_skills._common import build_repo_config, emit, resolve_vault_root_for_cli


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wiki-lint")
    p.add_argument("--vault", default=None)
    p.add_argument("--report", default=None)
    p.add_argument("--json-sidecar", default=None)
    p.add_argument("--strict", action="store_true")
    p.add_argument("--mtime-skip", action="store_true",
                   help="skip drift re-hash when stored mtime matches disk "
                        "(faster, integrity-relaxed; default off → always full-hash)")
    p.add_argument("--vault-root", default=None,
                   help="Vault root (resolve a local index_db); walks up from CWD when omitted.")
    p.add_argument("--db-path", default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    vaults_list = None if args.vault is None else [args.vault]
    factory_vault = args.vault or GLOBAL_VAULT_SENTINEL
    config = build_repo_config(  # TASK 022
        factory_vault, vault_root=resolve_vault_root_for_cli(args),
        db_path_flag=args.db_path)
    repo = make_repo(config)
    try:
        report = run_all_checks_report(repo, vaults=vaults_list, strict=args.strict,
                                       mtime_skip=args.mtime_skip)
        issues = report.issues
        if args.report:
            Path(args.report).write_text(render_markdown_report(issues))
        if args.json_sidecar:
            Path(args.json_sidecar).write_text(render_json_sidecar(issues))
        counts: dict[str, int] = {}
        for i in issues:
            counts[i.category] = counts.get(i.category, 0) + 1
        # R-5.6(d): --strict raises a non-zero advisory exit when issues exist;
        # default mode reports only (exit 0). No prior test relied on a strict
        # exit, so this establishes the gating policy.
        exit_code = 1 if (args.strict and issues) else 0
        return emit({
            "action": "linted",
            "vault": args.vault,
            "total_issues": len(issues),
            "by_category": counts,
            # TASK 061 (additive): {vault_id: {check_category: {denominator, by_rule}}}.
            # An absent check key = "this check does not apply to this layout" (its no-op
            # fired; no DAL call) — which is NOT the same as "examined 0", and the two must
            # not be conflated.
            "denominators": report.denominators,
        }, exit_code)
    finally:
        repo.close()


if __name__ == "__main__":
    sys.exit(main())
