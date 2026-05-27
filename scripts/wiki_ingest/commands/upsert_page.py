"""`upsert-page` subcommand — create or additively update a concept/entity page.

Mid-complexity command: builds (or extends) one markdown page per call.
The four additive-merge primitives (`upsert_source_row`, `append_fact`,
`append_contradiction`, `upsert_footnote`) live in F2 helper
`wiki_ingest._page_merge` since TASK 016 bead 016-01 (so `promote.py`
can reuse them without crossing the command-import boundary). The
local helper `render_stub_page` stays here — it consumes the F3-helper
`load_asset` and has no other caller.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from wiki_ingest._page_merge import (
    append_contradiction,
    append_fact,
    upsert_footnote,
    upsert_source_row,
)
from wiki_ingest._safety import (
    _check_case_collision,
    _is_relative_to,
    _safe_inline,
    _safe_name,
    die,
    read_text,
    write_text,
)
from wiki_ingest._vault import ensure_schema, find_vault_root, load_asset

CONCEPT_KIND, ENTITY_KIND = "concept", "entity"
KIND_TO_SUBDIR = {CONCEPT_KIND: "_concepts", ENTITY_KIND: "_entities"}


def render_stub_page(kind: str, name: str, definition: str | None,
                     source_slug: str, source_title: str, source_date: str) -> str:
    tpl_name = "concept_page.template.md" if kind == CONCEPT_KIND else "entity_page.template.md"
    tpl = load_asset(tpl_name)
    today = datetime.today().strftime("%Y-%m-%d")
    def_section = ""
    if definition:
        def_section = f"{definition.strip()} [^src-{source_slug}]"
    else:
        def_section = "_Definition pending — first ingest did not extract a one-sentence summary._"

    # Single-pass placeholder substitution: previous chained .replace() calls
    # would substitute into a prior value's text if it contained '{{KIND}}'
    # etc. _safe_name now blocks that for names, but use a regex-based
    # single-pass lookup for defense-in-depth.
    subs = {
        "NAME": name,
        "KIND": kind,
        "CREATED_DATE": today,
        "DEFINITION": def_section,
        "FIRST_SOURCE_ROW": f"- [[{source_slug}]] — {source_date} — {source_title}",
        "FIRST_FOOTNOTE": f"[^src-{source_slug}]: [[{source_slug}]] — {source_title}",
    }
    return re.sub(r"\{\{([A-Z_]+)\}\}",
                  lambda m: subs.get(m.group(1), m.group(0)), tpl)


def register(sub: argparse._SubParsersAction) -> None:
    """Attach the `upsert-page` subparser."""
    p = sub.add_parser("upsert-page",
                       help="create or additively update a concept/entity page")
    p.add_argument("vault")
    p.add_argument("--kind", required=True, choices=[CONCEPT_KIND, ENTITY_KIND])
    p.add_argument("--name", required=True)
    p.add_argument("--source-slug", required=True)
    p.add_argument("--source-title", required=True)
    p.add_argument("--source-date", required=True)
    p.add_argument("--definition", help="one-sentence definition (for stub creation)")
    p.add_argument("--fact", help="new fact to append under ## Facts")
    p.add_argument("--contradicts", help="existing claim that disagrees with --fact")
    p.add_argument("--force", action="store_true",
                   help="bypass safety checks: case-collision, --contradicts-not-found")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=execute)


def execute(args: argparse.Namespace) -> int:
    """Create or additively update the named concept / entity page."""
    vault = Path(args.vault).resolve()
    ensure_schema(vault)
    if args.kind not in (CONCEPT_KIND, ENTITY_KIND):
        die(f"--kind must be 'concept' or 'entity', got {args.kind!r}")

    safe_name = _safe_name(args.name, kind="name")
    # also sanitize source_slug since it's embedded into paths/links
    safe_slug = _safe_name(args.source_slug, kind="source-slug")
    # Reject newlines / structural-markup in user-supplied prose fields —
    # otherwise an attacker can spoof fake section headers or separators
    # via crafted --definition / --fact / --contradicts / --source-title.
    safe_title = _safe_inline(args.source_title, "source-title")
    safe_date = _safe_inline(args.source_date, "source-date")
    safe_definition = _safe_inline(args.definition, "definition") if args.definition else None
    safe_fact = _safe_inline(args.fact, "fact") if args.fact else None
    safe_contradicts = _safe_inline(args.contradicts, "contradicts") if args.contradicts else None

    # TASK 016 R8.1 — root-aware lookup: if `vault` is inside a two-tier
    # vault, check the ROOT layer first. If a page with the canonical
    # name exists at root, target it (vault-relative footnote). Else
    # fall back to course-local (v1 behaviour). On single-course vaults
    # (no root schema), `find_vault_root` returns vault_root=None and
    # behaviour is byte-identical to v1.
    course_root, vault_root = find_vault_root(vault)
    target_is_shared = False
    target_dir = vault / KIND_TO_SUBDIR[args.kind]
    target: Path

    if vault_root is not None:
        # Look at root layer first
        for sub in ("_concepts", "_entities"):
            candidate = vault_root / sub / f"{safe_name}.md"
            try:
                if candidate.is_file() and not candidate.is_symlink():
                    target = candidate
                    target_dir = vault_root / sub
                    target_is_shared = True
                    break
            except OSError:
                continue

    if not target_is_shared:
        collision = _check_case_collision(target_dir, safe_name)
        if collision:
            die(f"case-collision: '{safe_name}.md' would collide with existing "
                f"'{collision}' on a case-insensitive filesystem; rename one or "
                f"pass --force to override", code=4)
        target = target_dir / f"{safe_name}.md"
        # final containment check after resolving symlinks etc. — use
        # is_relative_to so a sibling like `_concepts_evil/` cannot match
        # via string-prefix confusion (S-H1).
        if not _is_relative_to(target, target_dir):
            die(f"refusing to write outside {target_dir}: {target}")

    created = not target.exists()

    # H1 fix: guard against the race window where target_is_shared=True
    # was decided based on a directory listing, but the root page was
    # deleted/renamed between the lookup and now (concurrent operator
    # action, mid-promote crash recovery, etc.). The "create stub at
    # root" path is forbidden: shared pages must only be created via
    # `promote` (R8.5 honest-scope).
    if target_is_shared and created:
        die(
            f"shared target expected at {target.relative_to(vault_root)} "
            f"but is missing — re-run `promote --apply` to recreate it, "
            f"or remove the operator-added reference. wiki-ingest never "
            f"auto-creates shared pages (R8.5).",
            code=2,
        )

    # verify --contradicts text actually appears on the page (unless creating)
    contradiction_warning = None
    if safe_contradicts and not created:
        page_text = read_text(target)
        if safe_contradicts not in page_text:
            if not args.force:
                die(f"--contradicts text {safe_contradicts!r} not found on "
                    f"{target.relative_to(vault)}; pass --force to record anyway",
                    code=5)
            contradiction_warning = "contradicted text not found on page; recorded anyway via --force"

    if created:
        # When creating a shared (root) page on first ingest of an
        # already-existing slug, we don't take that path here — R8.5
        # honest-scope: shared pages are only created via `promote`.
        # So this branch is reachable only when target_is_shared is False.
        content = render_stub_page(
            kind=args.kind, name=safe_name, definition=safe_definition,
            source_slug=safe_slug, source_title=safe_title,
            source_date=safe_date,
        )
    else:
        content = read_text(target)
        content = upsert_source_row(
            content, safe_slug, safe_title, safe_date
        )
        content = upsert_footnote(content, safe_slug, safe_title)
        # R8.2: when target is a SHARED root page, footnotes on it should
        # use the vault-relative form `[[<course_rel>/_sources/<slug>]]`.
        # Rewrite the just-added footnote definition to that form.
        if target_is_shared and vault_root is not None:
            course_rel = course_root.relative_to(vault_root)
            new_target = f"{course_rel}/_sources/{safe_slug}"
            content = _rewrite_one_footnote(
                content, safe_slug, new_target, safe_title,
            )

    if safe_fact:
        content = append_fact(content, safe_fact, safe_slug)

    if safe_contradicts:
        if not safe_fact:
            die("--contradicts requires --fact (the new claim that disagrees)")
        content = append_contradiction(content, safe_contradicts, safe_fact, safe_slug)

    write_text(target, content, args.dry_run)
    rel_target = str(target.relative_to(
        vault_root if target_is_shared and vault_root is not None else vault))
    result = {
        "page": rel_target,
        "created": created,
        "added_fact": bool(args.fact),
        "contradiction_flagged": bool(args.contradicts),
        "target_is_shared": target_is_shared,
    }
    if contradiction_warning:
        result["warning"] = contradiction_warning
    print(json.dumps(result, indent=2))
    return 0


def _rewrite_one_footnote(content: str, slug: str, new_target: str,
                          title: str) -> str:
    """Replace `[^src-<slug>]: [[<anything>]] <sep> <title>` with the
    vault-relative form. Regex anchored to line start with `re.M`
    (T16-S3 — no second-definition smuggling).

    Sec L-2 fix: pass a **function** to `pattern.sub` instead of a
    template string so user-supplied `title` cannot inject `\\g<N>`
    back-references and leak earlier capture groups.
    H4 fix: separator class accepts em-dash, en-dash, ASCII hyphen,
    unicode minus.
    """
    pattern = re.compile(
        rf"^(\[\^src-{re.escape(slug)}\]:\s*\[\[)([^\]]+)(\]\]\s*[—–\-−]\s*)(.+)$",
        re.M,
    )

    def _sub(m: re.Match) -> str:
        return f"{m.group(1)}{new_target}{m.group(3)}{title}"

    return pattern.sub(_sub, content)
