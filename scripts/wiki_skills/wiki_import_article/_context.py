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

from scripts.wiki_index.layout import CONCEPTS_SUBDIR
from scripts.wiki_index.layout_config import _apply_slug_strategy


def known_concepts(
    repo: Any, vault_id: str, vault_root: Path, *, fmt: str = "full",
) -> list[dict[str, str]] | list[str]:
    """Existing concept names for the vault — a single indexed query.

    Uses `load_known_entities` (one SQL read) rather than the drift-computing
    `_load_known_and_drift(..., "full")`, which walks the ENTIRE vault on disk only to
    discard the drift result here — needless O(vault) work on every `prepare`.

    `fmt` (P-6 residual — mirrors `wiki-extract-concepts` R-015-3) selects the envelope payload
    shape: ``"full"`` (default, backward-compatible) → ``[{slug, name}, …]`` (~N×200 B);
    ``"slugs-only"`` → ``[slug, …]`` (~N×30 B), for a large vault where the full known-concepts
    list dominates the `prepare` envelope. The orchestrator still matches entities against these
    in-context; with slugs-only it resolves the full record via SKILL.md prompt / a targeted probe
    only on a suspected collision."""
    from scripts.wiki_skills.wiki_extract_concepts._db import load_known_entities

    entities = load_known_entities(repo, vault_id)
    if fmt == "slugs-only":
        slugs: list[str] = []
        for k in entities:
            slug = str(k.get("slug") or "") if isinstance(k, dict) else str(k)
            if slug:
                slugs.append(slug)
        return slugs

    out: list[dict[str, str]] = []
    for k in entities:
        if isinstance(k, dict):
            slug = str(k.get("slug") or "")
            out.append({"slug": slug, "name": str(k.get("name") or slug)})
        else:  # "slugs-only" upstream shape → normalize to a {slug, name} pair
            out.append({"slug": str(k), "name": str(k)})
    return out


def existing_page_slugs(
    db_path: str | None,
    vault_id: str,
    project: str,
    target_folder: Path,
    *,
    slug_strategy: str = "preserve-unicode",
    source_subdir: str = "",
) -> list[str]:
    """The collision-guard slug set for `project`: indexed page slugs ∪ on-disk stems.

    `source_subdir` mirrors the layout's write-grammar so the on-disk `_concepts/` scan
    matches where `wiki_extract_concepts._apply_write` actually files concept pages: for a
    source_subdir layout (karpathy: note in `…/_sources/`) the concepts live in the SIBLING
    `…/_concepts/` (`target_folder.parent`), not `target_folder/_concepts/`. Empty (PARA) →
    concepts are a sibling of the note, i.e. `target_folder/_concepts/` (unchanged)."""
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
        # layout-aware concepts dir: source_subdir layouts file concepts in the SIBLING
        # _concepts/ (parent), not target_folder/_concepts/ (matches _apply_write). Use the
        # canonical CONCEPTS_SUBDIR constant — never a literal — so a rename can't silently
        # desync this scan from where _apply_write actually files concept pages.
        cdir = (folder.parent if source_subdir and folder.name == source_subdir
                else folder) / CONCEPTS_SUBDIR
        if cdir.is_dir():
            for md in cdir.glob("*.md"):
                slugs.add(_apply_slug_strategy(md.stem, slug_strategy))

    return sorted(slugs)
