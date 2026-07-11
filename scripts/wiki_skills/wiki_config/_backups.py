"""TASK 058 — backups for operator-authored config files (`.wiki/backups/`).

Why an editor tool backs up where the indexer tools don't: the repo's
"atomic write, no .bak" convention protects DERIVED, regenerable artifacts
(ADR-002 §D8 — the DB rebuilds from markdown). `sync.yaml` is the opposite:
irreplaceable operator intent (comments included), in vaults that are usually
NOT git repos. Atomic replace guards torn writes; a backup is the undo for a
semantically-wrong write. They compose: backup → edit → verify → atomic write.

Scheme: `<folder>/.wiki/backups/<name>.<UTC basic ISO, colon-free>.bak`,
newest 10 kept (pruned at write time). `restore` re-backs-up the CURRENT file
first, so restore is itself reversible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from scripts.wiki_skills._common import atomic_write_text

BACKUP_DIR = "backups"
KEEP = 10


@dataclass(frozen=True)
class BackupEntry:
    name: str
    size: int
    mtime: str


class WikiDirSymlinkError(Exception):
    """`<folder>/.wiki` (or its `sync.yaml` leaf) is a symlink, or the leaf's
    resolved target escapes the vault — refused before any mutation touches
    the path (CWE-59). Fixed, value-free detail; never echoes the resolved
    target."""

    code = "WIKI_DIR_SYMLINK"

    def __init__(self) -> None:
        super().__init__("`.wiki` path is a symlink or escapes the vault")


def ensure_wiki_writable(folder: Path, vault_root: Path, *, name: str = "sync.yaml") -> None:
    """The ONE choke-point guard for every MUTATING path onto
    `<folder>/.wiki/<name>` (write / delete / backup / restore — CLI and serve
    alike). A pre-planted `.wiki -> outside-dir` symlink redirects writes,
    deletes and backups outside the vault; the READ path already refuses this
    (`sync_config._load_validated_raw` step 0b resolves the full leaf path and
    re-validates containment) but every WRITE path used to check only the
    LEAF, missing a symlinked `.wiki` directory itself. The `backups/` leg is
    guarded too: `write_backup`/`prune_backups`/`restore_backup` all write,
    delete or read through `<folder>/.wiki/backups/`, so a symlink THERE is
    the same escape one level down (vdd-multi iteration-2 finding). Raises
    `WikiDirSymlinkError` when: `.wiki`, the `<name>` leaf, or `backups/` is a
    symlink; or (when the parent exists) the RESOLVED leaf/backups path falls
    outside `vault_root.resolve()`."""
    wiki_dir = folder / ".wiki"
    target = wiki_dir / name
    backups_dir = wiki_dir / BACKUP_DIR
    if wiki_dir.is_symlink() or target.is_symlink() or backups_dir.is_symlink():
        raise WikiDirSymlinkError()
    root = vault_root.resolve()
    if wiki_dir.exists() and not target.resolve().is_relative_to(root):
        raise WikiDirSymlinkError()
    if backups_dir.exists() and not backups_dir.resolve().is_relative_to(root):
        raise WikiDirSymlinkError()


def _backups_dir(folder: Path) -> Path:
    return folder / ".wiki" / BACKUP_DIR


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")


def write_backup(folder: Path, *, name: str = "sync.yaml",
                 suffix: str = ".bak") -> str | None:
    """Copy the current `<folder>/.wiki/<name>` (byte-exact) into backups/.
    Returns the vault-visible relative name, or None when there is nothing to
    back up. Prunes to the newest KEEP afterwards."""
    source = folder / ".wiki" / name
    if not source.is_file() or source.is_symlink():
        return None
    dest_dir = _backups_dir(folder)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{name}.{_timestamp()}{suffix}"
    atomic_write_text(dest, source.read_text(encoding="utf-8"))
    prune_backups(folder, name=name)
    return f".wiki/{BACKUP_DIR}/{dest.name}"


def list_backups(folder: Path, *, name: str = "sync.yaml") -> list[BackupEntry]:
    dest_dir = _backups_dir(folder)
    if not dest_dir.is_dir():
        return []
    out: list[BackupEntry] = []
    for p in sorted(dest_dir.iterdir(), reverse=True):
        if not p.name.startswith(name + ".") or p.is_symlink() or not p.is_file():
            continue
        stat = p.stat()
        out.append(BackupEntry(
            name=p.name, size=stat.st_size,
            mtime=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        ))
    return out


def prune_backups(folder: Path, *, name: str = "sync.yaml", keep: int = KEEP) -> int:
    entries = list_backups(folder, name=name)
    pruned = 0
    for entry in entries[keep:]:
        try:
            (_backups_dir(folder) / entry.name).unlink()
            pruned += 1
        except OSError:
            pass
    return pruned


def restore_backup(
    folder: Path, backup_name: str, *, name: str = "sync.yaml"
) -> tuple[str, str | None]:
    """Replace `<folder>/.wiki/<name>` with the named backup (byte-exact).
    The CURRENT file is backed up first (restore is reversible). Returns
    (restored_from, backup_of_current). Raises FileNotFoundError on an unknown
    backup name; ValueError on a name outside the scheme."""
    if "/" in backup_name or not backup_name.startswith(name + "."):
        raise ValueError("backup name outside the scheme")
    source = _backups_dir(folder) / backup_name
    if not source.is_file() or source.is_symlink():
        raise FileNotFoundError(backup_name)
    # Read BEFORE backing up the current file: a full KEEP set means the
    # backup-of-current write below prunes the OLDEST entry, which is exactly
    # `source` when restoring the oldest backup — reading first avoids losing
    # the very content being restored.
    restored_text = source.read_text(encoding="utf-8")
    pre = write_backup(folder, name=name)
    atomic_write_text(folder / ".wiki" / name, restored_text)
    return backup_name, pre
