"""Shared active-note resolution (ADR-008 / TASK 057-06, extracted TASK 058).

The focused Obsidian note's containing folder, via the OPTIONAL
`obsidian-active-note` resolver on PATH. Lifted out of
`wiki_import_article._folder` into this neutral leaf so `wiki-config` can use
the same signal without a skill→skill import (Decision-16); `_folder`
re-exports it, so the wiki-import surface and its tests are unchanged.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def active_note_folder(vault_root: Path, *, timeout_s: int = 10) -> str | None:
    """Secondary hint: the focused Obsidian note's containing folder, or None.

    Shells out to ``obsidian-active-note folder --format json`` when the resolver is
    on PATH. OPTIONAL by construction: absent binary, ANY non-zero exit (3/4/5 are
    merely the illustrative unavailable family — no per-code allowlist), timeout,
    unparsable output, or a folder that does not resolve INSIDE ``vault_root`` all
    return None silently. Local subprocess only — never the network (H-6).
    """
    resolver = shutil.which("obsidian-active-note")
    if resolver is None:
        return None
    try:
        proc = subprocess.run([resolver, "folder", "--format", "json"],
                              capture_output=True, text=True, timeout=timeout_s)
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None
    if proc.returncode != 0:
        return None
    try:
        payload = json.loads(proc.stdout.strip() or "null")
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    # folder mode: `abs` = absolute folder, `path` = vault-relative ("" = vault root)
    folder_abs = str(payload.get("abs") or "")
    if not folder_abs:
        return None
    try:
        resolved = Path(folder_abs).resolve(strict=True)
        root = vault_root.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if resolved == root or not resolved.is_relative_to(root):
        return None      # a root folder is a whole-vault blast radius — never a silent hint
    if not resolved.is_dir():
        return None
    return resolved.relative_to(root).as_posix()
