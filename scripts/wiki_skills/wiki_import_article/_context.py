"""S2 — project context for the orchestrator + collision guard (R-2).

Two read-only artifacts, both sourced from EXISTING machinery (NF-2):
  * ``known_concepts`` — the vault's existing concept names, via
    ``wiki_extract_concepts._load_known_and_drift`` (the same loader ``prepare``
    uses). The orchestrator is fed these so its proposed entity names reuse
    existing concept names instead of minting dangling/colliding variants
    (the known-concepts discipline — R-6).
  * ``existing_page_slugs`` — the slug set the collision guard (R-5) checks
    against: every ``pages.slug`` in the target project (notes + concept pages)
    ∪ on-disk note/``_concepts`` stems in the target folder. A generic candidate
    name (``defi``) that collides with an owner note (``Defi.md``) is thereby
    skipped at apply-time, never evicting the owner page at reindex.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from scripts.wiki_index.layout_config import _apply_slug_strategy


def known_concepts(repo: Any, vault_id: str, vault_root: Path) -> list[dict[str, str]]:
    """Existing concept {slug, name} pairs for the vault (reuses extract-concepts)."""
    from scripts.wiki_skills.wiki_extract_concepts import _load_known_and_drift

    known_out, _missing = _load_known_and_drift(repo, vault_id, vault_root, "full")
    out: list[dict[str, str]] = []
    for k in known_out:
        if isinstance(k, dict):
            slug = str(k.get("slug") or "")
            out.append({"slug": slug, "name": str(k.get("name") or slug)})
        else:  # "slugs-only" fallback shape
            out.append({"slug": str(k), "name": str(k)})
    return out


def existing_page_slugs(
    db_path: str | None,
    vault_id: str,
    project: str,
    target_folder: Path,
    *,
    slug_strategy: str = "preserve-unicode",
) -> list[str]:
    """The collision-guard slug set for `project`: indexed page slugs ∪ on-disk stems."""
    slugs: set[str] = set()

    if db_path and Path(db_path).exists():
        # read-only connection to the same DB — no new DAL surface, no writes
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            for (slug,) in conn.execute(
                "SELECT slug FROM pages WHERE vault_id = ? AND project = ?",
                (vault_id, project),
            ):
                if slug:
                    slugs.add(str(slug))
        except sqlite3.OperationalError:
            pass  # DB without a pages table yet (fresh vault) — FS scan still applies
        finally:
            conn.close()

    folder = Path(target_folder)
    if folder.is_dir():
        for md in folder.glob("*.md"):
            slugs.add(_apply_slug_strategy(md.stem, slug_strategy))
        cdir = folder / "_concepts"
        if cdir.is_dir():
            for md in cdir.glob("*.md"):
                slugs.add(_apply_slug_strategy(md.stem, slug_strategy))

    return sorted(slugs)
