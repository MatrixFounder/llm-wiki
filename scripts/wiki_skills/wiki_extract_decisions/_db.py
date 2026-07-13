"""DB reads for the extraction rail (TASK 063) — `source_state` + typed pages.

Read-mostly and ZERO-DDL: `user_version` stays 7. Everything here rides existing
columns + `frontmatter_json`. The rail adds no table, no index (P-5).

BEAD 063-04 (STUB): signatures only. 063-05 fills them.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def load_known_typed_pages(
    db_path: Path, *, vault_id: str, roster: tuple[str, ...]
) -> list[dict[str, Any]]:
    """STUB (063-04) → LOGIC (063-05). The vault's existing typed pages (slug,
    class, status, title) — what `prepare` hands the REASON step so it can LINK to
    prior knowledge instead of duplicating it."""
    raise NotImplementedError("063-05")


def resolve_target_classes(
    db_path: Path, *, vault_id: str, slugs: list[str]
) -> dict[str, str]:
    """STUB (063-04) → LOGIC (063-08). slug → typed class, for edge targets that
    live OUTSIDE the batch. Without this, G1's RANGE check could only see targets
    inside the batch — and an edge into the EXISTING graph is precisely where a
    range error hides."""
    raise NotImplementedError("063-08")
