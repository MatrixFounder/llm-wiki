"""Typed-page writer (TASK 063).

BEAD 063-04 (STUB): signatures only. 063-07 slugs, 063-11 H-6 hardening,
063-12 the write + manifest, 063-13 the supersede patch, 063-14 reconciliation.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def render_page(candidate: dict[str, Any], *, source_rel: str) -> str:
    """STUB (063-04) → LOGIC (063-12). Render one typed page (frontmatter + body).

    Frontmatter carries `type`, `status`, the typed edges (FORWARD ONLY — the
    inverses are auto-derived at `wiki-reindex --full`, never authored) and the
    provenance back to `source_rel`. `apply` NEVER authors an `aliases:` key
    (R-063-10): aliases are the entity-resolution layer's, and a rail that could
    mint them could silently merge two distinct entities.
    """
    raise NotImplementedError("063-12")


def write_pages(
    candidates: list[dict[str, Any]],
    *,
    vault_root: Path,
    typed_dirs: dict[str, str],
    source_rel: str,
) -> list[str]:
    """STUB (063-04) → LOGIC (063-12). Write the batch atomically and return the
    vault-relative paths written.

    Placement is DERIVED (`resolve_typed_write_dir`), never hardcoded — the same
    class name lands at the vault root on cybos and beside the source note on a
    PARA vault, because those are the folders each layout's read globs can see.
    Never clobbers a hand-edited page (R-063-9): Class A is the operator's.
    """
    raise NotImplementedError("063-12")
