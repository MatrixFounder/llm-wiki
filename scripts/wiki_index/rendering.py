"""`wiki-index-render` rendering primitives.

Generates `<vault>/index.md` from the `index_meta` VIEW. Preserves
`<!-- BEGIN-CUSTOM:name -->...<!-- END-CUSTOM:name -->` blocks across
re-renders (ADR-002 §D8 — operator-owned prose inside Class B file).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scripts.wiki_index.layout import VAULT_TIER_PROJECT
from scripts.wiki_index.security import PathTraversalError
# Neutral repo-wide egress sanitiser (Decision-16) — escapes wikilink/markdown/
# HTML actives so untrusted frontmatter `title`/`tldr`/`id` can't inject into a
# Class-B rendered page (graph-poisoning / custom-block-hijack / header-spoof).
from scripts.wiki_skills._common import (
    format_concept_mentions_body,
    sanitize_markdown_text,
    wrap_auto_block,
)

if TYPE_CHECKING:
    from scripts.wiki_index.layout_config import LayoutConfig
    from scripts.wiki_index.repository import IndexRepository

_GENERATED_AT_PREFIX = "<!-- GENERATED-AT:"

_CUSTOM_BLOCK_RE = re.compile(
    r"<!--\s*BEGIN-CUSTOM:([a-z0-9-]+)\s*-->(.*?)<!--\s*END-CUSTOM:\1\s*-->",
    re.DOTALL,
)


def extract_custom_sections(existing_md: str) -> dict[str, str]:
    """Find `<!-- BEGIN-CUSTOM:name -->...<!-- END-CUSTOM:name -->` blocks.

    Returns `{name: full_block_text}` where full_block_text includes both markers.
    """
    out: dict[str, str] = {}
    for m in _CUSTOM_BLOCK_RE.finditer(existing_md):
        name = m.group(1)
        out[name] = m.group(0)
    return out


# =============================================================================
# TASK 047 — derived "Mentions across sources" ledger (an in-page AUTO block).
#
# A concept page carries a managed `<!-- BEGIN-AUTO:mentions -->…<!-- END-AUTO:mentions -->`
# block listing the SOURCE pages that reference the concept (`ref_type='mentioned'`),
# regenerated from `page_entity_refs` (Class B). LINKS ONLY — no quote/span (those are not a
# pure function of Class A: extract-time stores the LLM quote/span, `reindex --full` rebuilds
# from the source footer wikilink; only the *set of linking sources* agrees across both, so
# only it is rebuild-stable). NO `GENERATED-AT` line (it must stay byte-identical across
# no-op re-renders). The AUTO markers are DISTINCT from BEGIN-CUSTOM (operator-owned).
# =============================================================================

class MalformedAutoBlockError(ValueError):
    """A page carries an unbalanced / duplicate / out-of-order `BEGIN-AUTO:<name>` …
    `END-AUTO:<name>` marker set (a merge conflict, a truncated prior write, or an
    operator-typed literal sentinel above the real block). Rewriting it blindly would
    either APPEND a second block (dangling `BEGIN`, no `END`) or SWALLOW the operator's
    prose between a stray `BEGIN` and the real `END` — so `apply_auto_block` refuses.
    The sweep records the page and skips it, never committing a mangled Class-A file."""


def apply_auto_block(existing_md: str, name: str, body: str) -> str:
    """Replace the `BEGIN-AUTO:<name>` region of `existing_md` with `wrap_auto_block(name, body)`,
    preserving everything else byte-for-byte. The pattern is anchored on `<name>` (non-greedy) →
    it matches ONLY the block of that name and can never swallow the definition, a different-named
    AUTO block, or a `BEGIN-CUSTOM` island. If the named block is ABSENT (a pre-047 page or a
    fresh non-seeded one) it is inserted BEFORE the first operator `BEGIN-CUSTOM` island (so the
    derived Class-B block sits above operator-owned prose), else appended at the end.

    Raises `MalformedAutoBlockError` when the markers of `<name>` are NOT exactly zero or a single
    well-formed `BEGIN`→`END` pair (unbalanced counts, duplicates, or `END` before `BEGIN`). This
    is a defensive refusal: append-a-duplicate or swallow-prose on a malformed page would commit a
    mangled Class-A file (that then gets its hash indexed), so the caller skips + surfaces it."""
    new_block = wrap_auto_block(name, body)
    n_begin = len(re.findall(rf"<!--\s*BEGIN-AUTO:{re.escape(name)}\s*-->", existing_md))
    n_end = len(re.findall(rf"<!--\s*END-AUTO:{re.escape(name)}\s*-->", existing_md))
    pat = re.compile(
        rf"<!--\s*BEGIN-AUTO:{re.escape(name)}\s*-->.*?<!--\s*END-AUTO:{re.escape(name)}\s*-->",
        re.DOTALL,
    )
    # Exactly one well-formed, ordered pair → replace in place (rest byte-preserved).
    if n_begin == 1 and n_end == 1 and pat.search(existing_md):
        return pat.sub(lambda _m: new_block, existing_md, count=1)
    # Any stray/unbalanced/out-of-order marker → refuse (never append-dup or swallow prose).
    # (n_begin == n_end == 1 but no ordered pair means END precedes BEGIN — still malformed.)
    if n_begin or n_end:
        raise MalformedAutoBlockError(
            f"page has {n_begin} BEGIN-AUTO:{name} and {n_end} END-AUTO:{name} marker(s) "
            "(expected none, or a single well-formed BEGIN…END pair)"
        )
    custom = _CUSTOM_BLOCK_RE.search(existing_md)
    if custom:
        return existing_md[:custom.start()].rstrip() + "\n\n" + new_block + "\n\n" + existing_md[custom.start():]
    return existing_md.rstrip() + "\n\n" + new_block + "\n"


def render_concept_mentions_body(repo: "IndexRepository", vault_id: str, entity_slug: str) -> str:
    """The mentions AUTO-block BODY for one concept — a pure function of the DB
    (`mentioning_source_pages`). Deterministic (sorted, deduped, links only)."""
    from scripts.wiki_index.sqlite_repository import SQLiteRepository
    if not isinstance(repo, SQLiteRepository):
        raise NotImplementedError("render_concept_mentions supports SQLiteRepository only")
    return format_concept_mentions_body(repo.mentioning_source_pages(vault_id, entity_slug))


def render_index(
    repo: "IndexRepository",
    vault_id: str,
    *,
    preserve_custom: dict[str, str] | None = None,
) -> str:
    """Render `index.md` content from the `index_meta` VIEW for one vault.

    `preserve_custom`: blocks to inject at the end (after auto-generated
    sections). Order preserved by insertion order.
    """
    # Access connection directly via SQLite repo (defined in subclass);
    # use the search-style approach.
    from scripts.wiki_index.sqlite_repository import SQLiteRepository
    if not isinstance(repo, SQLiteRepository):
        raise NotImplementedError("render_index supports SQLiteRepository only")

    rows = repo._connect().execute(
        "SELECT slug, project, kind, title, tldr "
        "FROM index_meta WHERE vault_id = ? "
        "ORDER BY project, kind, slug",
        (vault_id,),
    ).fetchall()

    lines: list[str] = [
        f"# Index — {vault_id}",
        "",
        "<!-- AUTO-GENERATED by wiki-index-render. Custom sections marked "
        "with BEGIN-CUSTOM/END-CUSTOM are preserved across re-renders. -->",
        "",
    ]

    # Group by (project, kind)
    by_project: dict[str, dict[str, list[tuple[str, str, str | None]]]] = {}
    for r in rows:
        proj = r["project"] or VAULT_TIER_PROJECT
        by_project.setdefault(proj, {}).setdefault(r["kind"], []).append(
            (r["slug"], r["title"], r["tldr"])
        )

    for proj in sorted(by_project):
        lines.append(f"## Project: `{proj}`")
        lines.append("")
        for kind in sorted(by_project[proj]):
            entries = by_project[proj][kind]
            lines.append(f"### {kind.capitalize()}s ({len(entries)})")
            lines.append("")
            for slug, title, tldr in entries:
                # MED-1 (security-critic): title/tldr are untrusted frontmatter —
                # sanitise on egress (the dev/obsidian layouts index arbitrary trees).
                tldr_part = f" — {sanitize_markdown_text(tldr)}" if tldr else ""
                lines.append(f"- [[{slug}|{sanitize_markdown_text(title)}]]{tldr_part}")
            lines.append("")

    if preserve_custom:
        lines.append("---")
        lines.append("")
        for name in preserve_custom:
            lines.append(preserve_custom[name])
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def atomic_write(path: Path, content: str) -> None:
    """Write `content` to `path` atomically (tempfile + os.rename).

    `os.rename` is atomic on POSIX within the same filesystem; macOS APFS
    preserves the guarantee within one volume.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # tempfile in same dir → same filesystem → rename is atomic
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.rename(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def auto_shard(content: str, max_pages: int = 200) -> dict[str, str]:
    """Stub for shard logic. Phase 3a returns a single file; sharding triggers
    in task-001-33 when benchmark vaults exceed `max_pages`."""
    _ = max_pages  # accepted for forward-compat
    return {"index.md": content}


# =============================================================================
# PW-H (TASK 012-09) — auto_indexes[] rebuildable-markdown rendering.
#
# Renders a config `auto_indexes[]` target (e.g. docs/KNOWN_ISSUES.md) from the
# indexed Class-A source-type pages (e.g. type-tagged `known-issue`). The body is
# a PURE deterministic function of those pages' content; the ONLY volatile value
# is the single GENERATED-AT header line. A sha256 of the header-stripped body is
# pinned in <vault>/.wiki/state.json so the PW-Q lint guard (012-10) can detect a
# manual edit. See ADR-002 §D8 TASK-012 amendment (Class-B rebuildable markdown).
# =============================================================================


def _fetch_tagged_pages(
    repo: "IndexRepository", vault_id: str, source_type: str,
) -> list[dict[str, str]]:
    """Indexed pages whose tag-route type is `source_type` (e.g. known-issue),
    projected to the per-issue fields the ledger renders. Reads the per-issue
    Class-A frontmatter from `pages.frontmatter_json` (the DB mirror)."""
    from scripts.wiki_index.sqlite_repository import SQLiteRepository
    if not isinstance(repo, SQLiteRepository):
        raise NotImplementedError("render_auto_index supports SQLiteRepository only")
    out: list[dict[str, str]] = []
    for r in repo._connect().execute(
        "SELECT slug, title, frontmatter_json FROM pages WHERE vault_id = ?",
        (vault_id,),
    ).fetchall():
        fm = json.loads(r["frontmatter_json"])
        if source_type not in (fm.get("tags") or []):
            continue
        out.append({
            "slug": str(r["slug"]),
            "title": str(r["title"]),
            "id": str(fm.get("id", "")),
            "category": str(fm.get("category", "")),
            "severity": str(fm.get("severity", "")),
            "status": str(fm.get("status", "")),
            "opened_at": str(fm.get("opened_at", "")),
        })
    return out


def _issue_sort_key(issue: dict[str, str], sort_fields: list[str]) -> tuple[str, ...]:
    """Stable total order: the configured sort_within_group fields, then a final
    `id` tiebreaker (architecture-review M2) so equal (severity, opened_at) rows
    never reorder across machines/clones."""
    return tuple(str(issue.get(f, "")) for f in sort_fields) + (str(issue.get("id", "")),)


def _render_issue_line(issue: dict[str, str]) -> str:
    # Every field originates in UNTRUSTED per-issue frontmatter → sanitise on
    # egress (security-critic HIGH-1): a raw `title` could otherwise inject a
    # `]]`-breakout wikilink, a `<!-- BEGIN-CUSTOM -->` marker, or a
    # `<!-- GENERATED-AT: -->` line that fools the drift hash.
    sev = sanitize_markdown_text(issue["severity"])
    status = sanitize_markdown_text(issue["status"])
    opened = sanitize_markdown_text(issue["opened_at"])
    bits = []
    if issue["severity"]:
        bits.append(f"severity `{sev}`")
    if issue["status"]:
        bits.append(f"status `{status}`")
    if issue["opened_at"]:
        bits.append(f"opened {opened}")
    meta = (" — " + ", ".join(bits)) if bits else ""
    id_part = f"**{sanitize_markdown_text(issue['id'])}** " if issue["id"] else ""
    # slug is the link TARGET (engine/slugify-derived); title is the display text.
    return f"- {id_part}[[{issue['slug']}|{sanitize_markdown_text(issue['title'])}]]{meta}"


def render_auto_index(
    repo: "IndexRepository",
    vault_id: str,
    auto_index: dict[str, Any],
    *,
    generated_at: str,
    preserve_custom: dict[str, str] | None = None,
) -> str:
    """Render one `auto_indexes[]` target's content. Pure function of the indexed
    source-type pages + `generated_at` (the only volatile input — the header line)."""
    source_type = str(auto_index["source_type"])
    group_by = auto_index.get("group_by")
    sort_fields = list(auto_index.get("sort_within_group") or [])
    issues = _fetch_tagged_pages(repo, vault_id, source_type)

    groups: dict[str, list[dict[str, str]]] = {}
    for issue in issues:
        gval = str(issue.get(group_by, "")) if group_by else ""
        groups.setdefault(gval, []).append(issue)

    lines: list[str] = [
        f"{_GENERATED_AT_PREFIX} {generated_at} by wiki-index-render --auto-indexes -->",
        f"# Known Issues — {vault_id}",
        "",
    ]
    for gval in sorted(groups):
        # gval is the group_by value (default `category`) from untrusted
        # frontmatter — sanitise on egress too (critic-security LOW: the one
        # untrusted field on this path left raw, same class as the title sink).
        lines.append(f"## {sanitize_markdown_text(gval) if gval else 'uncategorized'}")
        lines.append("")
        for issue in sorted(groups[gval], key=lambda i: _issue_sort_key(i, sort_fields)):
            lines.append(_render_issue_line(issue))
        lines.append("")

    if preserve_custom:
        lines.append("---")
        lines.append("")
        for name in preserve_custom:
            lines.append(preserve_custom[name])
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def auto_index_body_sha(content: str) -> str:
    """sha256 of the rendered body with the volatile GENERATED-AT header line
    stripped — the rebuildability/drift anchor (ADR-002 §D8 amendment / PW-Q)."""
    body = "\n".join(
        ln for ln in content.splitlines() if not ln.startswith(_GENERATED_AT_PREFIX)
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _safe_output_path(vault_root: Path, output_rel: str) -> Path:
    """Containment check for an operator-config `auto_indexes[].output` (which may
    not exist yet, so `validate_inside_vault`'s strict resolve can't be used)."""
    abs_root = vault_root.resolve()
    candidate = (vault_root / output_rel).resolve()
    if candidate != abs_root and abs_root not in candidate.parents:
        raise PathTraversalError(
            f"auto_indexes output {output_rel!r} escapes vault root {vault_root}"
        )
    return candidate


def update_render_state(vault_root: Path, output_rel: str, content: str) -> None:
    """Pin the header-stripped sha256 of a rendered auto-index in
    <vault>/.wiki/state.json (consumed by the PW-Q lint guard)."""
    state_path = vault_root / ".wiki" / "state.json"
    state: dict[str, Any] = {}
    if state_path.is_file():
        loaded = json.loads(state_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            state = loaded
    state.setdefault("auto_indexes", {})[output_rel] = auto_index_body_sha(content)
    atomic_write(state_path, json.dumps(state, indent=2, sort_keys=True) + "\n")


def render_and_write_auto_indexes(
    repo: "IndexRepository",
    vault_id: str,
    vault_root: Path,
    config: "LayoutConfig",
    *,
    generated_at: str,
) -> list[str]:
    """Render every `config.auto_indexes[]` target, preserve its BEGIN-CUSTOM
    blocks, atomic-write it (path-guarded), and pin its sha256 in state.json.
    Returns the list of output paths written (empty when the layout has no
    auto_indexes — e.g. Karpathy → no-op, byte-identical)."""
    written: list[str] = []
    for auto_index in config.auto_indexes:
        output_rel = str(auto_index["output"])
        out_path = _safe_output_path(vault_root, output_rel)
        existing = out_path.read_text(encoding="utf-8") if out_path.is_file() else ""
        content = render_auto_index(
            repo, vault_id, auto_index, generated_at=generated_at,
            preserve_custom=extract_custom_sections(existing),
        )
        atomic_write(out_path, content)
        update_render_state(vault_root, output_rel, content)
        written.append(output_rel)
    return written
