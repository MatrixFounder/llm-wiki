"""`scan` subcommand — dump vault state as JSON.

Read-only: walks the vault, counts pages per subdir, samples the last
5 log entries via `tail_log`. Output is deterministic (sorted keys at
every list-emit boundary) so the R11 byte-identity gate stays green.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from wiki_ingest._safety import die
from wiki_ingest._vault import (
    DEFAULT_SUBDIRS,
    INDEX_FILE,
    LOG_FILE,
    SCHEMA_FILE,
    load_vault_pages,
    tail_log,
)


def register(sub: argparse._SubParsersAction) -> None:
    """Attach the `scan` subparser. Called once at CLI startup."""
    p = sub.add_parser("scan", help="dump vault state as JSON")
    p.add_argument("vault")
    p.set_defaults(func=execute)


def execute(args: argparse.Namespace) -> int:
    """Print the vault's JSON state report; return 0 on success."""
    vault = Path(args.vault).resolve()
    if not vault.is_dir():
        die(f"vault not a directory: {vault}")

    pages = load_vault_pages(vault)
    state = {
        "vault": str(vault),
        "schema_present": (vault / SCHEMA_FILE).exists(),
        "index_present": (vault / INDEX_FILE).exists(),
        "log_present": (vault / LOG_FILE).exists(),
        "subdirs_present": {sd: (vault / sd).is_dir() for sd in DEFAULT_SUBDIRS},
        "concepts": sorted(pages["concepts"].keys()),
        "entities": sorted(pages["entities"].keys()),
        "sources": sorted(pages["sources"].keys()),
        "counts": {
            "concepts": len(pages["concepts"]),
            "entities": len(pages["entities"]),
            "sources": len(pages["sources"]),
        },
        "last_log_entries": tail_log(vault, 5),
    }
    print(json.dumps(state, indent=2, ensure_ascii=False))
    return 0
