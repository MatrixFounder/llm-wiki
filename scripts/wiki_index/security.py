"""Path-traversal guard utility (R-26 / task-001-12).

Two functions:
  - `validate_inside_vault(candidate, vault_root)` — bread-and-butter check for
    operator-supplied paths. Resolves to absolute, then verifies the candidate
    is rooted inside the vault.
  - `assert_no_symlink_escape(p)` — stricter; walks parents looking for
    symlinks that point outside the filesystem root. Used by reindex.

Adapters and skills MUST call `validate_inside_vault` first thing on any
operator-supplied path. The R-26 contract: never index outside-vault paths,
never read/write filesystems outside the declared vault root.
"""

from __future__ import annotations

from pathlib import Path


class PathTraversalError(ValueError):
    """Raised when an operator-supplied path lies outside the declared vault
    root. The adapter wrapper (task-001-24) translates this exception into
    the `{"error": "PATH_OUTSIDE_VAULT"}` JSON envelope per R-26."""


def validate_inside_vault(candidate: Path, vault_root: Path) -> Path:
    """Return the resolved absolute path if `candidate` is strictly inside
    (or equal to) `vault_root`. Otherwise raise `PathTraversalError`.

    `strict=True` on `.resolve()` is intentional — prevents TOCTOU races where
    the candidate path is created/destroyed between resolution and use.

    Args:
        candidate: operator- or adapter-supplied path.
        vault_root: the registered vault root (from `vaults.root_path`).

    Returns:
        The resolved absolute path (same shape as `candidate.resolve()`).

    Raises:
        FileNotFoundError: if `candidate` or `vault_root` does not exist on
            disk (propagated from `resolve(strict=True)`).
        PathTraversalError: if the resolved `candidate` is not equal to or
            beneath the resolved `vault_root`.
    """
    abs_candidate = candidate.resolve(strict=True)
    abs_root = vault_root.resolve(strict=True)
    if not abs_candidate.is_relative_to(abs_root):
        raise PathTraversalError(
            f"{candidate} is outside vault root {vault_root}"
        )
    return abs_candidate


def assert_no_symlink_escape(p: Path) -> None:
    """Walk parents of `p` and ensure no ancestor is a symlink resolving
    outside its own parent. Used by sensitive operations (reindex) that walk
    the vault filesystem — protects against an operator dropping a symlinked
    directory that, on traversal, ends up reading `/etc` or similar.

    Args:
        p: absolute path to inspect (typically the vault root).

    Raises:
        PathTraversalError: if any ancestor is a symlink whose target points
            outside the filesystem path tree rooted at `p.anchor`.
    """
    if not p.is_absolute():
        raise PathTraversalError(f"{p} must be absolute for symlink check")
    seen: set[Path] = set()
    current = p
    while current != current.parent:
        if current.is_symlink():
            target = current.resolve(strict=False)
            # Symlink that escapes to a different anchor (e.g. macOS /private
            # mapping aside) is suspect.
            if not target.is_relative_to(Path(p.anchor)):
                raise PathTraversalError(
                    f"symlink {current} → {target} escapes filesystem anchor "
                    f"{p.anchor}"
                )
        if current in seen:
            raise PathTraversalError(f"symlink loop detected at {current}")
        seen.add(current)
        current = current.parent
