"""tmp2/ migration — flat → `_sources/<file>.md` layout (task-001-32).

Idempotent one-shot migration helper: moves every top-level .md file under
`<vault_path>/<target_subdir>/` (default `_sources`). System files (WIKI_SCHEMA,
CLAUDE, log, index) are preserved at the vault root.

Usage:
    python -m scripts.wiki_migrate_flat_to_folders <vault_path> [--dry-run]
                                                   [--target-subdir _sources]

After this script, operator typically runs:
    python -m scripts.wiki_skills.wiki_init --register-existing --vault <path>
    python -m scripts.wiki_skills.wiki_reindex --full --vault <vault_id>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from scripts.wiki_index.layout import SOURCES_SUBDIR, SYSTEM_FILES
from scripts.wiki_index.security import (
    PathTraversalError,
    validate_inside_vault,
)


def _hash_file(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def migrate_flat_to_folders(
    vault_path: Path,
    target_subdir: str = SOURCES_SUBDIR,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Move flat top-level .md files into <vault>/<target_subdir>/.

    Returns summary dict: {"moved": N, "skipped": K, "errors": [...]}.
    Raises PathTraversalError if `target_subdir` would escape the vault.
    """
    vault_path = vault_path.resolve(strict=True)
    # Reject obviously hostile target_subdir values; second-pass resolved
    # containment check below is the authoritative guard.
    if (not target_subdir or target_subdir.startswith("/")
            or ".." in Path(target_subdir).parts):
        raise PathTraversalError(
            f"target_subdir must be a single relative segment inside the "
            f"vault root; got {target_subdir!r}"
        )
    target_dir = (vault_path / target_subdir).resolve()
    if not target_dir.is_relative_to(vault_path):
        raise PathTraversalError(
            f"target_subdir {target_subdir!r} escapes vault {vault_path}"
        )
    moved = 0
    skipped = 0
    errors: list[dict[str, str]] = []

    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)

    for entry in sorted(vault_path.iterdir()):
        if not entry.is_file() or entry.suffix != ".md":
            continue
        if entry.name in SYSTEM_FILES:
            skipped += 1
            continue
        try:
            validate_inside_vault(entry, vault_path)
        except PathTraversalError as e:
            errors.append({"file": entry.name, "error": str(e)})
            continue
        target = target_dir / entry.name
        if target.exists():
            try:
                if _hash_file(entry) == _hash_file(target):
                    skipped += 1
                    continue
                errors.append({
                    "file": entry.name,
                    "error": "target exists with different hash; manual resolve",
                })
                continue
            except OSError as e:
                errors.append({"file": entry.name, "error": str(e)})
                continue
        if dry_run:
            moved += 1
            continue
        try:
            shutil.move(str(entry), str(target))
            moved += 1
        except OSError as e:
            errors.append({"file": entry.name, "error": str(e)})

    return {"moved": moved, "skipped": skipped, "errors": errors,
            "dry_run": dry_run, "target_subdir": target_subdir}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Migrate flat tmp2/*.md → tmp2/_sources/*.md"
    )
    p.add_argument("vault_path", type=Path)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--target-subdir", default=SOURCES_SUBDIR)
    args = p.parse_args(argv)

    if not args.vault_path.is_dir():
        print(json.dumps({"error": f"not a directory: {args.vault_path}"}),
              file=sys.stderr)
        return 2

    result = migrate_flat_to_folders(
        args.vault_path,
        target_subdir=args.target_subdir,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2))
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
