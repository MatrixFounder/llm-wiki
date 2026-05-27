"""`reindex` subcommand — rebuild index.md from disk.

Parses + masks each page exactly once (P-H4). Preserves custom sections
from the existing index. Inline-construct masking on the existing index
defeats L-H6 ghost headers.

**TASK 016 bead 016-08 — two-tier extensions**:

- Mode detection via `_peek_schema_version` (M-4 resolution).
- Course mode (`schema_version: 1.x`): existing v1 behaviour PLUS
  cross-layer pass that adds `## Shared concepts referenced` /
  `## Shared entities referenced` rows for root pages cited by this
  course's `_sources/`.
- Root mode (`schema_version: 2.0`): rebuild root `index.md` from disk
  (Concepts + Entities only — no Sources at root per spec §2.5).
- `--cascade` flag: in root mode, also reindex every discovered course.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from wiki_ingest._frontmatter import split_frontmatter
from wiki_ingest._markdown import (
    _H2_HEADER_RE,
    _HTML_COMMENT_RE,
    _ensure_masked,
    _first_sentence,
    _mask_code_fences,
    _mask_inline_constructs,
    get_all_section_bodies,
    get_section_body,
    insert_section_before,
    replace_section_body,
)
from wiki_ingest._safety import read_text, write_text
from wiki_ingest._vault import (
    DEFAULT_SUBDIRS,
    INDEX_FILE,
    SCHEMA_FILE,
    SUBDIR_TO_DISPLAY,
    SUBDIR_TO_KIND,
    _peek_schema_version,
    _walk_pages,
    discover_courses,
    ensure_schema,
    find_vault_root,
    load_asset,
)


def _page_one_line(text: str, fm: dict, kind: str,
                   body: str | None = None,
                   masked: str | None = None) -> str:
    """One-line page summary for the index. Reuses pre-parsed body/masked view.

    `body` and `masked` are optional pre-extracted artifacts from the caller
    (P-H4: avoid re-parsing frontmatter and re-masking the page).
    """
    masked = _ensure_masked(text, masked)
    # Sources: prefer summary frontmatter, else first sentence of TL;DR / Executive Summary / first paragraph
    if kind == "source":
        for key in ("summary", "tldr", "description"):
            v = fm.get(key)
            if v:
                return str(v).strip().replace("\n", " ")
        if body is None:
            body = split_frontmatter(text)[1]
        # try TL;DR section, then Executive Summary (common summarizing-meetings output)
        for section in ("TL;DR", "Executive Summary"):
            body_text = get_section_body(text, section, masked=masked)
            if body_text and body_text.strip():
                cleaned = _first_sentence(body_text)
                if cleaned:
                    return cleaned
        # fall back to first non-empty paragraph that isn't a header/comment/separator
        for para in body.split("\n\n"):
            para = _HTML_COMMENT_RE.sub("", para).strip()
            if not para or para.startswith("#") or para.startswith("---"):
                continue
            cleaned = _first_sentence(para)
            if cleaned:
                return cleaned
        return ""
    # concept/entity pages: first sentence of Definition section
    defn = get_section_body(text, "Definition", masked=masked)
    if defn:
        return _first_sentence(defn.strip())
    return ""


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("reindex",
                       help="rebuild index.md from disk (preserves Notes section)")
    p.add_argument("vault")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--cascade", action="store_true",
                   help="in root mode, also reindex every discovered course")
    p.set_defaults(func=execute)


def execute(args: argparse.Namespace) -> int:
    vault = Path(args.vault).resolve()
    # M-4 mode detection: peek schema_version
    sv = _peek_schema_version(vault / SCHEMA_FILE)
    if sv == "2.0":
        return _execute_root(args, vault)
    # Course mode (v1 behaviour + 016 shared-referenced extension)
    return _execute_course(args, vault)


def _execute_course(args: argparse.Namespace, vault: Path) -> int:
    ensure_schema(vault)

    # Bucket pages by the on-disk subdir (with underscore prefix), then map
    # to user-facing display section labels when rendering the index.
    # Parse frontmatter + mask each page exactly ONCE — pass `body` and
    # `masked` through to `_page_one_line` (P-H4).
    rows_by_subdir: dict[str, list[str]] = {sd: [] for sd in DEFAULT_SUBDIRS}
    for md in _walk_pages(vault):
        try:
            text = read_text(md)
        except OSError:
            continue
        fm, body = split_frontmatter(text)
        subdir = md.parent.name
        if subdir not in rows_by_subdir:
            continue
        masked = _mask_inline_constructs(_mask_code_fences(text))
        kind = fm.get("kind") or SUBDIR_TO_KIND.get(subdir, "unknown")
        title = fm.get("title") or fm.get("name") or md.stem
        date = fm.get("date") or fm.get("created") or ""
        one_line = _page_one_line(text, fm, kind, body=body, masked=masked)
        slug = md.stem
        if kind == "source":
            row = f"- [[{slug}]]"
            if date:
                row += f" — {date}"
            row += f" — {title}"
            if one_line:
                row += f" — {one_line}"
        else:
            row = f"- [[{slug}]]"
            if one_line:
                row += f" — {one_line}"
        rows_by_subdir[subdir].append(row)

    # Build new index from template; each on-disk subdir maps to a display
    # section label ("_sources" → "Sources", etc.) in index.md.
    display_section_names = set(SUBDIR_TO_DISPLAY.values())
    new_content = load_asset("index.template.md")
    for subdir, rows in rows_by_subdir.items():
        display = SUBDIR_TO_DISPLAY[subdir]
        body = "\n".join(rows) if rows else ""
        new_content = replace_section_body(new_content, display, body)

    # Preserve ALL custom sections from the existing index — anything outside
    # the default display sections (Sources/Concepts/Entities) the operator
    # added gets carried through. Duplicate header names get their bodies
    # MERGED (separated by a markdown HR) into one section, and a warning is
    # emitted so the operator can rename one of them if that wasn't intended.
    existing = read_text(vault / INDEX_FILE)
    preserved_sections: list[str] = []
    merge_warnings: list[str] = []
    if existing:
        # Mask existing once for the entire preserve-loop — and ALSO mask
        # inline constructs so `## Foo` inside an inline backtick or HTML
        # comment is not mis-treated as a real header (L-H6 mitigation).
        existing_masked = _mask_inline_constructs(_mask_code_fences(existing))
        # Walk header occurrences in document order; track which non-default
        # names we've already handled so each unique name is processed once
        # and ALL its occurrences are collected.
        handled: set[str] = set()
        for m in _H2_HEADER_RE.finditer(existing_masked):
            header_text = m.group(1).strip()
            if header_text in display_section_names:
                continue
            if header_text in handled:
                continue
            handled.add(header_text)

            bodies = [b.strip("\n") for b in
                      get_all_section_bodies(existing, header_text,
                                             masked=existing_masked)]
            bodies = [b for b in bodies if b]  # drop empty
            if not bodies:
                continue
            if len(bodies) == 1:
                merged_body = bodies[0]
            else:
                # Merge duplicates with a horizontal-rule separator
                merged_body = "\n\n---\n\n".join(bodies)
                merge_warnings.append(
                    f"merged {len(bodies)} duplicate `## {header_text}` "
                    f"sections from existing index — consider renaming one "
                    f"if the duplication was unintended"
                )

            # Insert (or replace) in new_content
            if get_section_body(new_content, header_text) is not None:
                new_content = replace_section_body(new_content, header_text, merged_body)
            else:
                new_content = (new_content.rstrip()
                               + f"\n\n## {header_text}\n\n{merged_body}\n")
            preserved_sections.append(header_text)

    # TASK 016 R7.1: when this course lives under a vault root with a
    # shared layer, scan its `_sources/` for slugs cited by root pages
    # and emit `## Shared concepts referenced` / `## Shared entities
    # referenced` sections.
    shared_referenced = _build_shared_referenced(vault)
    if shared_referenced["concepts"]:
        section = "Shared concepts referenced"
        rows = "\n".join(f"- [[{n}]] — (shared)"
                         for n in shared_referenced["concepts"])
        if get_section_body(new_content, section) is not None:
            new_content = replace_section_body(new_content, section, rows)
        else:
            new_content = (new_content.rstrip() +
                           f"\n\n## {section}\n\n{rows}\n")
    if shared_referenced["entities"]:
        section = "Shared entities referenced"
        rows = "\n".join(f"- [[{n}]] — (shared)"
                         for n in shared_referenced["entities"])
        if get_section_body(new_content, section) is not None:
            new_content = replace_section_body(new_content, section, rows)
        else:
            new_content = (new_content.rstrip() +
                           f"\n\n## {section}\n\n{rows}\n")

    write_text(vault / INDEX_FILE, new_content, args.dry_run)
    result = {
        "index": INDEX_FILE,
        "rebuilt": True,
        "mode": "course",
        "counts": {SUBDIR_TO_DISPLAY[k]: len(v) for k, v in rows_by_subdir.items()},
        "preserved_sections": preserved_sections,
        "shared_referenced": shared_referenced,
    }
    if merge_warnings:
        result["warnings"] = merge_warnings
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


# =============================================================================
# TASK 016 bead 016-08 helpers
# =============================================================================


_FN_DEF_RE = re.compile(
    r"^\[\^src-(?P<slug>[^\]]+)\]:\s*\[\[(?P<target>[^\]]+)\]\][^\n]*$",
    re.M,
)


def _build_shared_referenced(course_root: Path) -> dict:
    """For each root concept/entity page, check if any of its footnote
    targets references a `_sources/<slug>.md` file owned by THIS course.

    Returns `{"concepts": [name, ...], "entities": [name, ...]}` (sorted).
    Returns empty lists when the course is not under a v2.0 vault root.

    M5/M-1 fix: vault-root discovery is delegated to `find_vault_root`,
    which enforces the same symlink-skip + cross-fs guards as the rest
    of the codebase (was: hand-rolled walk-up that silently followed
    symlinked ancestors and crossed mount boundaries).
    M6 fix: only `<course_rel>/_sources/<slug>` form counts as
    "referenced". Short-form `[[<slug>]]` on a root page is a lint
    warning, not a green light to claim cross-course reference.
    """
    try:
        _, vault_root = find_vault_root(course_root)
    except SystemExit:
        return {"concepts": [], "entities": []}
    if vault_root is None:
        return {"concepts": [], "entities": []}

    # Collect this course's source slugs
    course_slugs: set[str] = set()
    sdir = course_root / "_sources"
    if sdir.is_dir():
        for src in sdir.glob("*.md"):
            try:
                if src.is_symlink():
                    continue
            except OSError:
                continue
            course_slugs.add(src.stem)
    if not course_slugs:
        return {"concepts": [], "entities": []}

    course_rel = str(course_root.relative_to(vault_root))
    expected_prefix = f"{course_rel}/_sources/"
    referenced: dict = {"concepts": [], "entities": []}
    for sub, bucket in (("_concepts", "concepts"), ("_entities", "entities")):
        d = vault_root / sub
        if not d.is_dir():
            continue
        for rp in sorted(d.glob("*.md")):
            try:
                if rp.is_symlink():
                    continue
            except OSError:
                continue
            text = read_text(rp)
            cites_course = False
            for m in _FN_DEF_RE.finditer(text):
                slug = m.group("slug").strip()
                target = m.group("target").strip().split("|", 1)[0]
                # M6 fix: require the vault-relative prefix; bare slug
                # is a lint warning, not "referenced".
                if slug in course_slugs and target.startswith(expected_prefix):
                    cites_course = True
                    break
            if cites_course:
                referenced[bucket].append(rp.stem)
    referenced["concepts"].sort()
    referenced["entities"].sort()
    return referenced


def _execute_root(args: argparse.Namespace, vault_root: Path) -> int:
    """Root-mode reindex: rebuild root index.md (Concepts + Entities only).

    C2 fix: preserve custom H2 sections (operator-added `## Notes`,
    `## Maintainers`, etc.) by splicing their bodies into the rebuilt
    index, not just enumerating their names.
    C3 fix: in cascade mode, suppress per-course JSON via stdout
    redirection so the caller receives a single valid JSON document.
    """
    # Walk root layer's _concepts/ + _entities/
    concept_names: list[str] = []
    entity_names: list[str] = []
    for sub, bucket in (("_concepts", concept_names),
                        ("_entities", entity_names)):
        d = vault_root / sub
        if not d.is_dir():
            continue
        for md in sorted(d.glob("*.md")):
            try:
                if md.is_symlink():
                    continue
            except OSError:
                continue
            bucket.append(md.stem)

    idx = vault_root / INDEX_FILE
    existing_text = read_text(idx) if idx.is_file() else ""

    # Build the rebuilt body from a minimal template
    text = "# Vault Root Index\n\n## Concepts\n\n## Entities\n"

    text = replace_section_body(
        text, "Concepts",
        "\n".join(f"- [[{n}]]" for n in concept_names))
    text = replace_section_body(
        text, "Entities",
        "\n".join(f"- [[{n}]]" for n in entity_names))

    # C2 fix: preserve operator-added custom sections by SPLICING their
    # bodies into the rebuilt index — not just listing their names.
    preserved: list[str] = []
    if existing_text:
        existing_masked = _mask_inline_constructs(_mask_code_fences(existing_text))
        for m in _H2_HEADER_RE.finditer(existing_masked):
            h = m.group(1).strip()
            if h in ("Concepts", "Entities"):
                continue
            if h in preserved:
                continue
            body = get_section_body(existing_text, h, masked=existing_masked)
            if body is None:
                continue
            preserved.append(h)
            # Append after the rebuilt Concepts/Entities
            text = text.rstrip() + f"\n\n## {h}\n\n{body.strip()}\n"

    write_text(idx, text, args.dry_run)

    # Cascade: reindex every course. C3 fix — suppress per-course JSON
    # so the outer cascade emits a SINGLE valid JSON document.
    cascaded: list[str] = []
    if args.cascade:
        from contextlib import redirect_stdout
        import io as _io
        for c in discover_courses(vault_root):
            sub_args = argparse.Namespace(
                vault=str(c), dry_run=args.dry_run, cascade=False,
                cmd="reindex",
            )
            with redirect_stdout(_io.StringIO()):
                _execute_course(sub_args, c)
            cascaded.append(str(c.relative_to(vault_root)))

    result = {
        "index": INDEX_FILE,
        "rebuilt": True,
        "mode": "root",
        "concepts": len(concept_names),
        "entities": len(entity_names),
        "preserved_sections": preserved,
        "cascaded": cascaded,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0
