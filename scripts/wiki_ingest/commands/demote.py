"""`demote` subcommand — move a root page back into one course.

TASK 016 bead 016-07. Reverse of `promote`. Refuses if any non-target
course's `_sources/` cites the page being demoted (R5.2 cross-course
citation guard). Footnote rewrite reverses A-M-2: vault-relative
form `[[<course_rel>/_sources/<slug>]]` → short form `[[<slug>]]`.
`promoted_from:` frontmatter field is removed via the
`_splice_frontmatter_fields(.., {"promoted_from": None})` path.

Dry-run NOT default per Q-2b (demote is reversible; cheaper to undo).
Imports F1+F2+F3-helper only — never another command (R12.5).
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from wiki_ingest._frontmatter import (
    _serialize_yaml_list_field,
    _splice_frontmatter_fields,
    split_frontmatter,
)
from wiki_ingest._markdown import (
    _existing_lines,
    get_section_body,
    insert_section_before,
    replace_section_body,
)
from wiki_ingest._safety import (
    _atomic_write_text,
    _safe_for_json,
    _safe_name,
    die,
    read_text,
)
from wiki_ingest._vault import (
    SCHEMA_FILE,
    _peek_schema_version,
    discover_courses,
)

_KIND_TO_SUBDIR = {"concept": "_concepts", "entity": "_entities"}


def register(sub: argparse._SubParsersAction) -> None:
    """Attach the `demote` subparser. Dry-run NOT default (Q-2b)."""
    p = sub.add_parser(
        "demote",
        help="move a root-level concept/entity page back into one course; "
             "refuses if any other course cites it",
    )
    p.add_argument("name", help="canonical filename without .md")
    p.add_argument("--vault", required=True,
                   help="path to the vault root (schema_version: 2.0)")
    p.add_argument("--to", dest="to_course", required=True,
                   help="target course name (matches `discover_courses` "
                        "result by last path segment)")
    p.add_argument("--dry-run", action="store_true",
                   help="emit DemotionPlan JSON; do not write")
    p.set_defaults(func=execute)


def execute(args: argparse.Namespace) -> int:
    vault = Path(args.vault).resolve()
    if not vault.is_dir():
        die(f"vault not a directory: {vault}", code=2)
    root_schema = vault / SCHEMA_FILE
    if not root_schema.is_file():
        die("vault root WIKI_SCHEMA.md absent; run init --root first", code=2)
    if _peek_schema_version(root_schema) != "2.0":
        die("vault root schema must declare schema_version: 2.0", code=2)

    safe_name = _safe_name(args.name, kind="page")
    # Sec M-3 fix: `--to` is a course directory basename, not free prose.
    # Apply `_safe_name` discipline (rejects `/`, `\`, `..`, control bytes,
    # bracket metacharacters, etc.) — defence-in-depth even though the
    # subsequent `c.name == target_arg` match would fail on traversal
    # attempts today.
    target_arg = _safe_name(args.to_course, kind="to")
    courses = discover_courses(vault)
    target = next(
        (c for c in courses if c.name == target_arg),
        None,
    )
    if target is None:
        die(f"target course not found: {target_arg}", code=1)

    # Locate the root page
    root_page: Path | None = None
    kind: str = ""
    for k, sub in _KIND_TO_SUBDIR.items():
        candidate = vault / sub / f"{safe_name}.md"
        try:
            if candidate.is_file() and not candidate.is_symlink():
                root_page = candidate
                kind = k
                break
        except OSError:
            continue
    if root_page is None:
        die("page is not at root; nothing to demote", code=1)

    text = read_text(root_page)
    fm, body = split_frontmatter(text)

    # Cross-course citation scan (R5.2 / A1).
    # H2 fix: track ALL courses that own each slug, not just the last one
    # seen. If two courses share the same source-slug filename (spec §6.2
    # cross-vault collision hazard), the guard must refuse when ANY of
    # them is outside the target.
    target_rel = str(target.relative_to(vault))
    slug_to_courses: dict[str, list[str]] = {}
    for c in courses:
        sdir = c / "_sources"
        if not sdir.is_dir():
            continue
        crel = str(c.relative_to(vault))
        for src in sdir.glob("*.md"):
            try:
                if src.is_symlink():
                    continue
            except OSError:
                continue
            slug_to_courses.setdefault(src.stem, []).append(crel)
    fn_re = re.compile(
        r"^\[\^src-(?P<slug>[^\]]+)\]:\s*\[\[(?P<target>[^\]]+)\]\][^\n]*$",
        re.M,
    )
    conflicting: list[tuple[str, str]] = []
    for m in fn_re.finditer(body):
        slug = m.group("slug").strip()
        owners = slug_to_courses.get(slug)
        if not owners:
            continue  # unknown slug; non-blocking
        # Refuse if any owner is OUTSIDE the target course (and if the
        # target itself is among them, that's fine — but a sibling owner
        # is still a guard hit because the demoted page's short-form
        # `[[slug]]` reference becomes ambiguous between the two `_sources/`).
        for owner in owners:
            if owner != target_rel:
                conflicting.append((owner, slug))
    if conflicting:
        listing = ", ".join(f"{c}/_sources/{s}" for c, s in conflicting)
        die(
            f"refused: page is cited by sources outside {target_arg}: "
            f"[{listing}]",
            code=1,
        )

    # Compute target path; refuse to clobber an existing course-local copy
    target_path = target / _KIND_TO_SUBDIR[kind] / f"{safe_name}.md"
    if target_path.is_file():
        die("target already has a course-local copy; demote would clobber",
            code=1)

    # Rewrite footnotes back to short form (R5.3)
    new_body = _rewrite_footnotes_short_form(body)

    # Remove promoted_from (R5.4) via splice helper
    new_text_with_fm = _splice_frontmatter_fields(
        _serialise(fm, new_body), ["promoted_from"],
        {"promoted_from": None},
    )

    today = datetime.today().strftime("%Y-%m-%d")

    plan = {
        "applied": not args.dry_run,
        "name": safe_name,
        "kind": kind,
        "moved_from": str(root_page.relative_to(vault)),
        "moved_to": str(target_path.relative_to(vault)),
    }
    if args.dry_run:
        print(json.dumps(_safe_for_json(plan), indent=2, ensure_ascii=False))
        return 0

    # --- write path ---
    target_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(target_path, new_text_with_fm)
    try:
        root_page.unlink()
    except OSError:
        pass

    # Update root index: remove row
    _root_index_remove(vault, safe_name, kind)
    # Update target course index: remove from "Shared * referenced", add to v1 section
    _course_index_on_demote(target, safe_name, kind)
    # Append target course log
    _append_demote_log(target, safe_name, kind, today, vault)

    print(json.dumps(plan, indent=2, ensure_ascii=False))
    return 0


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


_FN_REWRITE_SHORT_RE = re.compile(
    # H4 fix: separator accepts em/en/hyphen/minus.
    r"^(\[\^src-)([^\]]+)(\]:\s*\[\[)([^\]]+)(\]\]\s*[—–\-−]\s*.+)$",
    re.M,
)


def _rewrite_footnotes_short_form(body: str) -> str:
    """`[[<course_rel>/_sources/<slug>]]` → `[[<slug>]]` (re.M anchored).

    H5 fix: handles aliased wikilinks `[[<target>|<alias>]]` — the alias
    is preserved and the target is stripped to the bare slug.
    """
    def _sub(m: re.Match) -> str:
        target = m.group(4)
        slug = m.group(2)
        # Split off an alias if present (`[[target|alias]]` form).
        target_only, sep, alias = target.partition("|")
        suffix = f"/_sources/{slug}"
        if target_only.endswith(suffix):
            new_target = f"{slug}{sep}{alias}" if sep else slug
            return f"{m.group(1)}{slug}{m.group(3)}{new_target}{m.group(5)}"
        return m.group(0)

    return _FN_REWRITE_SHORT_RE.sub(_sub, body)


def _serialise_scalar(v) -> str:
    """Scalar with proper YAML escape (H-1 sec fix — mirrors `_scalar`
    in `_frontmatter._serialize_yaml_list_field`)."""
    if not isinstance(v, str):
        return str(v)
    needs_quote = (
        not v
        or v[0] in "&*!@`%>|#?,[]{}\"'-"
        or any(ch in v for ch in (":", "#"))
        or v.strip() != v
    )
    if needs_quote:
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return v


def _serialise(fm: dict, body: str) -> str:
    """Re-serialise fm + body. H-1 sec fix: routes list fields through
    the F2 helper so list[dict] / list[str] serialisation uses the
    properly-escaping `_scalar` from `_frontmatter`."""
    if not fm:
        return body
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            lines.append(_serialize_yaml_list_field(k, v))
        else:
            lines.append(f"{k}: {_serialise_scalar(v)}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines) + body.lstrip("\n")


def _row_matches_name(row: str, name: str) -> bool:
    """Same exact-wikilink helper as promote.py (C1 fix). Inline-duplicated
    to avoid cross-command imports per R12.5 import-graph invariant."""
    return bool(re.search(
        rf"\[\[{re.escape(name)}(?:\][\]]|[|#])",
        row,
    ))


def _root_index_remove(vault: Path, name: str, kind: str) -> None:
    idx_path = vault / "index.md"
    if not idx_path.is_file():
        return
    text = read_text(idx_path)
    section = "Concepts" if kind == "concept" else "Entities"
    body = get_section_body(text, section)
    if body is None:
        return
    rows = [r for r in _existing_lines(body) if not _row_matches_name(r, name)]
    text = replace_section_body(text, section, "\n".join(rows))
    _atomic_write_text(idx_path, text)


def _course_index_on_demote(course_root: Path, name: str, kind: str) -> None:
    """Remove from `## Shared * referenced`; add back to v1 section."""
    idx_path = course_root / "index.md"
    if not idx_path.is_file():
        return
    text = read_text(idx_path)
    shared_section = (
        "Shared concepts referenced" if kind == "concept"
        else "Shared entities referenced"
    )
    section_v1 = "Concepts" if kind == "concept" else "Entities"
    row = f"- [[{name}]]"
    # Remove from shared (C1 fix: exact-wikilink match)
    body_shared = get_section_body(text, shared_section)
    if body_shared:
        rows = [r for r in _existing_lines(body_shared) if not _row_matches_name(r, name)]
        text = replace_section_body(text, shared_section, "\n".join(rows))
    # Add to v1 section (create if missing)
    body_v1 = get_section_body(text, section_v1)
    if body_v1 is None:
        new_section = f"## {section_v1}\n\n{row}\n"
        text = text.rstrip() + "\n\n" + new_section
    else:
        rows = _existing_lines(body_v1)
        if not any(_row_matches_name(r, name) for r in rows):
            rows.append(row)
        text = replace_section_body(text, section_v1, "\n".join(sorted(rows)))
    _atomic_write_text(idx_path, text)


def _append_demote_log(course_root: Path, name: str, kind: str,
                       today: str, vault: Path) -> None:
    """L7 fix: use `_KIND_TO_SUBDIR[kind]` so entities render as
    `_entities/` (not `_entitys/`)."""
    log_path = course_root / "log.md"
    if not log_path.is_file():
        return
    subdir = _KIND_TO_SUBDIR[kind]
    block = (
        f"\n## [{today}] demote | {name}\n"
        f"- Source: {subdir}/{name}.md (vault root)\n"
        f"- Destination: {course_root.relative_to(vault)}/{subdir}/{name}.md\n"
        f"- Citation guard: passed\n"
    )
    text = read_text(log_path)
    _atomic_write_text(log_path, text.rstrip() + "\n" + block)
