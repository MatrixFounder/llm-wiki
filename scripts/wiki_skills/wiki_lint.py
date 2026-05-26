"""`wiki-lint` CLI — real impl per task-001-29."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout import GLOBAL_VAULT_SENTINEL
from scripts.wiki_index.lint import (
    render_json_sidecar,
    render_markdown_report,
    run_all_checks,
)
from scripts.wiki_skills._common import emit


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wiki-lint")
    p.add_argument("--vault", default=None)
    p.add_argument("--report", default=None)
    p.add_argument("--json-sidecar", default=None)
    p.add_argument("--strict", action="store_true")
    p.add_argument("--db-path", default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    vaults_list = None if args.vault is None else [args.vault]
    factory_vault = args.vault or GLOBAL_VAULT_SENTINEL
    config: dict[str, str] = {"vault_id": factory_vault}
    if args.db_path:
        config["db_path"] = args.db_path
    repo = make_repo(config)
    try:
        issues = run_all_checks(repo, vaults=vaults_list, strict=args.strict)
        if args.report:
            Path(args.report).write_text(render_markdown_report(issues))
        if args.json_sidecar:
            Path(args.json_sidecar).write_text(render_json_sidecar(issues))
        counts: dict[str, int] = {}
        for i in issues:
            counts[i.category] = counts.get(i.category, 0) + 1
        return emit({
            "action": "linted",
            "vault": args.vault,
            "total_issues": len(issues),
            "by_category": counts,
        })
    finally:
        repo.close()


if __name__ == "__main__":
    sys.exit(main())
