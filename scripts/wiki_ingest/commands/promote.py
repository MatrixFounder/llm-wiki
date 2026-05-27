"""`promote` subcommand — merge cross-course duplicates into the vault root.

TASK 016 beads 016-05 (skeleton + dry-run) + 016-06 (write path).

Dry-run by default per Q-2 / R4.1. Footnote rewrite uses
`course_root.relative_to(vault_root)` per A-M-2 (not literal `Lessons/`).
Contradiction detection is literal-line-diff per Q-10.

Imports F1 (`_safety`) + F2 (`_markdown`, `_frontmatter`, `_page_merge`) +
F3-helper (`_vault`). Per R12.5, does NOT import any other `commands/*`.
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
    _mask_code_fences,
    get_section_body,
    insert_section_before,
    replace_section_body,
)
from wiki_ingest._page_merge import (
    append_contradiction,
    append_fact,
    upsert_footnote,
    upsert_source_row,
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

_CONCEPT_KIND = "concept"
_ENTITY_KIND = "entity"
_KIND_TO_SUBDIR = {_CONCEPT_KIND: "_concepts", _ENTITY_KIND: "_entities"}
_SUBDIR_TO_KIND = {v: k for k, v in _KIND_TO_SUBDIR.items()}


def register(sub: argparse._SubParsersAction) -> None:
    """Attach the `promote` subparser. Dry-run is the default (Q-2 / R4.1)."""
    p = sub.add_parser(
        "promote",
        help="merge cross-course duplicates of a concept/entity into the "
             "vault root (dry-run by default; --apply to commit)",
    )
    p.add_argument("name",
                   help="canonical filename without .md (e.g. \"Sharpe Score\")")
    p.add_argument("--vault", required=True,
                   help="path to the vault root (schema_version: 2.0)")
    p.add_argument("--kind", choices=[_CONCEPT_KIND, _ENTITY_KIND],
                   default=None,
                   help="explicit kind; auto-inferred when duplicates agree")
    p.add_argument("--apply", action="store_true",
                   help="commit the merge (default is dry-run plan JSON)")
    p.set_defaults(func=execute)


def execute(args: argparse.Namespace) -> int:
    """Compute the promotion plan; emit dry-run JSON or stub `--apply`.

    Steps (all run on every invocation, even dry-run):
    1. Vault validation (R9.1 / R9.2 — schema_version peek).
    2. Name sanitisation (`_safe_name`).
    3. Discover courses; collect course-local + root-level copies.
    4. Pre-conditions:
       - R3.1 strict: ≥2 course copies & no root copy → first_promote
       - R3.7 relaxed: ≥1 course copy + existing root copy → merge_into_root
       - Else: refuse.
    5. R3.2: kind auto-infer (refuse on mismatch).
    6. Emit `PromotionPlan` JSON (R4.2 envelope).
    """
    vault = Path(args.vault).resolve()
    if not vault.is_dir():
        die(f"vault not a directory: {vault}", code=2)
    root_schema = vault / SCHEMA_FILE
    if not root_schema.is_file():
        die(f"vault root WIKI_SCHEMA.md absent; run init --root first",
            code=2)
    sv = _peek_schema_version(root_schema)
    if sv != "2.0":
        die(f"vault root schema must declare schema_version: 2.0 (got: {sv})",
            code=2)

    safe_name = _safe_name(args.name, kind="page")
    course_roots = discover_courses(vault)

    # Collect course-local copies + root-level copy. `course_hits` maps
    # course_root → (kind, path); `root_hit` is (kind, path) or None.
    course_hits: dict[Path, tuple[str, Path]] = {}
    for c in course_roots:
        for sub, kind in _SUBDIR_TO_KIND.items():
            p = c / sub / f"{safe_name}.md"
            try:
                if p.is_file() and not p.is_symlink():
                    course_hits[c] = (kind, p)
                    break
            except OSError:
                continue

    root_hit: tuple[str, Path] | None = None
    for sub, kind in _SUBDIR_TO_KIND.items():
        rp = vault / sub / f"{safe_name}.md"
        try:
            if rp.is_file() and not rp.is_symlink():
                root_hit = (kind, rp)
                break
        except OSError:
            continue

    # Pre-conditions (R3.1, R3.7)
    if root_hit is None and len(course_hits) == 0:
        die(f"no duplicates found; nothing to promote", code=1)
    if root_hit is None and len(course_hits) == 1:
        die(f"only one course-local copy of '{safe_name}'; need ≥2 OR an "
            f"existing root version", code=1)

    mode = "merge_into_root" if root_hit is not None else "first_promote"

    # Kind resolution (R3.2)
    seen_kinds = {k for k, _ in course_hits.values()}
    if root_hit is not None:
        seen_kinds.add(root_hit[0])
    if args.kind is not None:
        kind = args.kind
        if seen_kinds and seen_kinds != {kind}:
            die(f"kind mismatch: --kind={args.kind} but disk has "
                f"{sorted(seen_kinds)}", code=1)
    elif len(seen_kinds) > 1:
        die(f"kind mismatch: courses disagree on kind for '{safe_name}': "
            f"{sorted(seen_kinds)}; reconcile manually before promoting",
            code=1)
    else:
        kind = next(iter(seen_kinds))

    # Compute paths for the plan
    target_subdir = _KIND_TO_SUBDIR[kind]
    merge_to = vault / target_subdir / f"{safe_name}.md"

    merge_from_paths = sorted(
        str(p.relative_to(vault)) for _, p in course_hits.values()
    )
    delete_paths = list(merge_from_paths)  # the course-local copies

    # `index_updates`: high-level per-course/-root rendition (concrete
    # row mutation lands in 016-06).
    index_updates: list[dict] = []
    for c in sorted(course_hits.keys(), key=lambda p: str(p)):
        index_updates.append({
            "course": str(c.relative_to(vault)),
            "op": "move_to_shared_referenced",
        })
    if root_hit is None:
        index_updates.append({"layer": "root", "op": "create_or_add_row"})
    else:
        index_updates.append({"layer": "root", "op": "row_already_present"})

    log_appends: list[dict] = []
    for c in sorted(course_hits.keys(), key=lambda p: str(p)):
        log_appends.append({
            "course": str(c.relative_to(vault)),
            "block": f"## [YYYY-MM-DD] promote | {safe_name}",
        })

    plan = {
        "applied": False,
        "mode": mode,
        "name": safe_name,
        "kind": kind,
        "merge_from": merge_from_paths,
        "merge_to": str(merge_to.relative_to(vault)),
        "delete": delete_paths,
        "index_updates": index_updates,
        "log_appends": log_appends,
        "contradictions_raised": 0,  # real computation in 016-06
    }

    if not args.apply:
        print(json.dumps(_safe_for_json(plan), indent=2, ensure_ascii=False))
        return 0

    # === bead 016-06 — --apply write path ===
    return _apply_promotion(
        vault=vault,
        safe_name=safe_name,
        kind=kind,
        target_subdir=target_subdir,
        mode=mode,
        course_hits=course_hits,
        root_hit=root_hit,
        merge_to=merge_to,
    )


def _apply_promotion(*, vault: Path, safe_name: str, kind: str,
                     target_subdir: str, mode: str,
                     course_hits: dict, root_hit, merge_to: Path) -> int:
    """The state-mutating write path. Idempotent: re-runs after a clean
    apply are a no-op (R4.3).

    Crash-safety honest scope: a mid-apply failure between writing the
    root page and deleting course copies leaves an `invariant_violation`
    state that 016-04's lint net detects. Operator re-runs `--apply`;
    the re-run is idempotent.
    """
    # R4.3 — no-op when nothing to do (page already at root, no course
    # copies left to fold in)
    if not course_hits and root_hit is not None:
        print(json.dumps(_safe_for_json({
            "applied": True, "noop": True,
            "name": safe_name, "kind": kind,
            "merge_to": str(merge_to.relative_to(vault)),
        }), indent=2, ensure_ascii=False))
        return 0

    today = datetime.today().strftime("%Y-%m-%d")

    # 1. Read all course copies (and root copy if present)
    sources: list[tuple[Path, Path, str, dict, str]] = []
    # (course_root, page_path, raw_text, fm, body)
    for course_root, (_, p) in course_hits.items():
        text = read_text(p)
        fm, body = split_frontmatter(text)
        sources.append((course_root, p, text, fm, body))

    root_fm: dict = {}
    root_body = ""
    if root_hit is not None:
        _, rp = root_hit
        root_text = read_text(rp)
        root_fm, root_body = split_frontmatter(root_text)

    # 2. Union frontmatter
    merged_fm = _union_frontmatter(
        root_fm=root_fm, source_fms=[s[3] for s in sources],
        source_courses=[s[0].name for s in sources],
        kind=kind, today=today,
    )

    # 3. Build the merged body: start from the root copy (if any) +
    #    each course's body folded in via _page_merge primitives.
    merged_body = root_body if root_hit is not None else ""
    # Sort sources by course path for deterministic merge order.
    sources_sorted = sorted(sources, key=lambda s: str(s[0]))

    contradictions_raised = 0
    if root_hit is None:
        # Initialise from the first course's body so the merge has a
        # base. The subsequent loop folds the rest in.
        merged_body = sources_sorted[0][4]
        # Source-record + footnote already present in the first course's
        # body. We do NOT need to upsert them again.
        rest = sources_sorted[1:]
    else:
        rest = sources_sorted

    # Fold each course into merged_body.
    # Mask-once optimisation (Perf-H1): compute `merged_mask` once per
    # course-fold; pass into each primitive so the inner get_section_body
    # / replace_section_body calls don't re-mask. Re-mask only when the
    # body length actually changes (a mutation happened).
    merged_mask = _mask_code_fences(merged_body)
    # Running set of (slug, fact_text) pairs already in merged_body —
    # avoids the quadratic re-parse of the Facts section per new fact
    # (Perf-H2). Initialise from merged_body once.
    existing_facts: set[tuple[str, str]] = set()
    _facts_body0 = get_section_body(merged_body, "Facts", masked=merged_mask)
    if _facts_body0:
        for _el in _existing_lines(_facts_body0):
            _em = re.match(r"^-\s+(.*?)\s+\[\^src-([^\]]+)\]\s*$", _el)
            if _em:
                existing_facts.add((_em.group(2), _em.group(1)))

    for course_root, p, _text, fm, body in rest:
        # Each course's _sources/ may include multiple slugs; extract them
        # from footnote definitions the body carries.
        slugs_titles = _extract_slugs_and_titles(body)
        sdate_default = today
        if isinstance(fm.get("created"), str):
            sdate_default = fm["created"]
        for slug, title in slugs_titles:
            old_len = len(merged_body)
            merged_body = upsert_source_row(
                merged_body, slug, title, sdate_default, masked=merged_mask)
            if len(merged_body) != old_len:
                merged_mask = _mask_code_fences(merged_body)
            old_len = len(merged_body)
            merged_body = upsert_footnote(
                merged_body, slug, title, masked=merged_mask)
            if len(merged_body) != old_len:
                merged_mask = _mask_code_fences(merged_body)

        # Fold facts line-by-line so dedupe + literal-line-diff
        # contradiction detection (Q-10) works.
        facts_body = get_section_body(body, "Facts")
        if not facts_body:
            continue
        for line in _existing_lines(facts_body):
            m = re.match(r"^-\s+(.*?)\s+\[\^src-([^\]]+)\]\s*$", line)
            if not m:
                continue
            fact_text, slug = m.group(1), m.group(2)
            # Look for a contradiction: same predicate-prefix, different
            # remainder, against any existing fact (Q-10 heuristic).
            differs = False
            for (e_slug, ef) in existing_facts:
                if ef == fact_text:
                    continue
                if _facts_similar_predicate(ef, fact_text):
                    old_len = len(merged_body)
                    merged_body = append_contradiction(
                        merged_body, f"{ef} [^src-{e_slug}]",
                        fact_text, slug, masked=merged_mask)
                    if len(merged_body) != old_len:
                        merged_mask = _mask_code_fences(merged_body)
                        contradictions_raised += 1
                    differs = True
                    break
            if not differs:
                old_len = len(merged_body)
                merged_body = append_fact(
                    merged_body, fact_text, slug, masked=merged_mask)
                if len(merged_body) != old_len:
                    merged_mask = _mask_code_fences(merged_body)
                    existing_facts.add((slug, fact_text))

    # 4. Rewrite footnotes to vault-relative form (A-M-2 / R3.5).
    # Map across ALL discovered courses, not just those participating in
    # this merge — covers the M2 case where root_hit's body cites a slug
    # from a course that didn't have a course-local copy of this page.
    merged_body = _rewrite_footnotes_vault_relative(
        merged_body,
        course_roots_for_slug=_slug_to_course_map(
            discover_courses(vault), vault),
        vault_root=vault,
    )

    # 5. Reserialise frontmatter + write root page atomically
    final_text = _serialise(merged_fm, merged_body)
    merge_to.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(merge_to, final_text)

    # 6. Delete course-local copies (one-page-one-place invariant).
    # Sec M-4 fix: track unlink failures so a partial state is visible to
    # the operator instead of silently violating the invariant.
    residual_course_copies: list[str] = []
    for course_root, p, *_ in sources_sorted:
        try:
            p.unlink()
        except OSError:
            residual_course_copies.append(str(p.relative_to(vault)))

    # 7. Update each affected course's index.md + log.md
    for course_root, p, *_ in sources_sorted:
        _update_course_index_on_promote(course_root, safe_name, kind)
        _append_course_log_promote(
            course_root, safe_name, kind, sources_sorted, contradictions_raised,
            today, vault,
        )

    # 8. Update root index.md (create if missing; idempotent)
    _update_root_index_on_promote(vault, safe_name, kind)

    result_payload = {
        "applied": True, "noop": False,
        "mode": mode,
        "name": safe_name, "kind": kind,
        "merge_to": str(merge_to.relative_to(vault)),
        "merged_from": sorted(str(s[1].relative_to(vault))
                              for s in sources_sorted),
        "contradictions_raised": contradictions_raised,
    }
    # Sec M-4: surface partial-unlink-failure so operator knows to fix
    # the invariant_violation state. Exit non-zero in that case.
    if residual_course_copies:
        result_payload["partial"] = True
        result_payload["residual_course_copies"] = sorted(residual_course_copies)
        print(json.dumps(_safe_for_json(result_payload),
                         indent=2, ensure_ascii=False))
        return 1
    print(json.dumps(_safe_for_json(result_payload),
                     indent=2, ensure_ascii=False))
    return 0


# ----------------------------------------------------------------------
# helpers (016-06)
# ----------------------------------------------------------------------


def _union_frontmatter(*, root_fm: dict, source_fms: list[dict],
                       source_courses: list[str], kind: str,
                       today: str) -> dict:
    """Merge frontmatter: earliest `created`, longest `description` (Q-6),
    union `promoted_from:` (list[dict])."""
    merged: dict = dict(root_fm) if root_fm else {}
    merged["kind"] = kind
    # name preserved from first non-empty fm
    for fm in [merged] + source_fms:
        if fm.get("name"):
            merged["name"] = fm["name"]
            break
    # created: earliest
    candidates = [fm.get("created") for fm in [root_fm] + source_fms
                  if isinstance(fm.get("created"), str)]
    if candidates:
        merged["created"] = min(candidates)
    # description: longest (Q-6)
    descs = [fm.get("description") for fm in [root_fm] + source_fms
             if isinstance(fm.get("description"), str)]
    if descs:
        merged["description"] = max(descs, key=len)
    # promoted_from: list of dicts; merge with existing root list (if any)
    existing = root_fm.get("promoted_from") if isinstance(
        root_fm.get("promoted_from"), list) else []
    pf: list[dict] = list(existing)
    for course_name in source_courses:
        entry = {"course": course_name, "date": today}
        # dedupe by (course, date)
        if not any(
            isinstance(e, dict)
            and e.get("course") == course_name
            and e.get("date") == today
            for e in pf
        ):
            pf.append(entry)
    merged["promoted_from"] = pf
    return merged


_FOOTNOTE_DEF_PATTERN = re.compile(
    # `[^src-<slug>]: [[<target>]] <sep> <title>` — separator accepts
    # em-dash (U+2014), en-dash (U+2013), ASCII hyphen, or unicode minus
    # so hand-edited / third-party-tool footnotes round-trip cleanly
    # (H4 fix).
    r"^\[\^src-([^\]]+)\]:\s*\[\[[^\]]+\]\]\s*[—–\-−]\s*(.+?)\s*$",
    re.M,
)


def _extract_slugs_and_titles(body: str) -> list[tuple[str, str]]:
    """Parse `[^src-<slug>]: [[<target>]] <sep> <title>` definitions in `body`.

    Accepts em-dash, en-dash, ASCII hyphen, or unicode minus as separator.
    """
    out: list[tuple[str, str]] = []
    for m in _FOOTNOTE_DEF_PATTERN.finditer(body):
        out.append((m.group(1).strip(), m.group(2).strip()))
    return out


def _facts_similar_predicate(a: str, b: str) -> bool:
    """Q-10 literal-line-diff: treat two facts as a contradiction if they
    share a common token prefix of ≥2 words AND differ in the remainder.
    Heuristic — operator-reviewable. False = treat as independent facts.
    """
    aw = a.split()
    bw = b.split()
    if len(aw) < 3 or len(bw) < 3:
        return False
    return aw[:2] == bw[:2] and aw != bw


def _slug_to_course_map(course_roots: list[Path],
                        vault: Path) -> dict[str, Path]:
    """For each `_sources/<slug>.md` under each course, map slug → course_root."""
    out: dict[str, Path] = {}
    for c in course_roots:
        sdir = c / "_sources"
        if not sdir.is_dir():
            continue
        for src in sdir.glob("*.md"):
            try:
                if src.is_symlink():
                    continue
            except OSError:
                continue
            out[src.stem] = c
    return out


_FN_REWRITE_VAULT_RE = re.compile(
    # Captures: \1 = `[^src-`, \2 = slug, \3 = `]: [[`, \4 = target,
    # \5 = `]]<sep>title…`. Separator accepts em/en/hyphen/minus (H4).
    r"^(\[\^src-)([^\]]+)(\]:\s*\[\[)([^\]]+)(\]\]\s*[—–\-−]\s*.+)$",
    re.M,
)


def _rewrite_footnotes_vault_relative(body: str,
                                      course_roots_for_slug: dict[str, Path],
                                      vault_root: Path) -> str:
    """Rewrite footnote definitions to `[[<course_rel>/_sources/<slug>]] — title`.

    Regex anchored to `^` + `re.M` (T16-S3 — no second-definition smuggling).
    Footnotes whose slug doesn't map to a known course are left unchanged
    (they may belong to the root-already-cited set).
    """
    def _sub(m: re.Match) -> str:
        slug = m.group(2)
        course = course_roots_for_slug.get(slug)
        if course is None:
            return m.group(0)
        course_rel = course.relative_to(vault_root)
        new_target = f"{course_rel}/_sources/{slug}"
        return f"{m.group(1)}{slug}{m.group(3)}{new_target}{m.group(5)}"

    return _FN_REWRITE_VAULT_RE.sub(_sub, body)


def _serialise_scalar(v) -> str:
    """Render a scalar with proper YAML escaping (H-1 sec fix).

    Mirrors `_frontmatter._serialize_yaml_list_field._scalar` so that
    operator-supplied / vault-supplied strings containing `"`, `\\`,
    newlines, etc. cannot smuggle forged top-level fields into the
    frontmatter.
    """
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
    """Render frontmatter dict + body back to markdown.

    H-1 sec fix: uses `_serialise_scalar` (with proper `\\` and `"`
    escape) instead of naive `f'"{v}"'` wrapping. Routes list fields
    through the F2 helper `_serialize_yaml_list_field` so list[dict]
    serialisation stays consistent with the rest of the codebase.
    """
    if not fm:
        return body
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            # Delegate to the F2 helper for both list[str] and list[dict].
            lines.append(_serialize_yaml_list_field(k, v))
        else:
            lines.append(f"{k}: {_serialise_scalar(v)}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines) + body.lstrip("\n")


def _index_row(name: str) -> str:
    return f"- [[{name}]]"


def _row_matches_name(row: str, name: str) -> bool:
    """True when `row` contains an exact `[[<name>]]` wikilink (no substring trap).

    Fixes C1: substring match would erroneously delete `[[<name> Bar]]`
    when promoting `<name>`. Use a regex that anchors `[[` and `]]` around
    the exact name; aliases `[[<name>|alias]]` and anchors `[[<name>#X]]`
    DO match (same canonical target).
    """
    return bool(re.search(
        rf"\[\[{re.escape(name)}(?:\][\]]|[|#])",
        row,
    ))


def _update_course_index_on_promote(course_root: Path, name: str,
                                    kind: str) -> None:
    """Move row from `## Concepts`/`## Entities` to `## Shared * referenced`."""
    idx_path = course_root / "index.md"
    if not idx_path.is_file():
        return
    text = read_text(idx_path)
    section_orig = "Concepts" if kind == "concept" else "Entities"
    shared_section = (
        "Shared concepts referenced" if kind == "concept"
        else "Shared entities referenced"
    )
    row = _index_row(name)
    # Remove from original section — exact-wikilink match (C1 fix)
    body = get_section_body(text, section_orig)
    if body:
        rows = [r for r in _existing_lines(body) if not _row_matches_name(r, name)]
        text = replace_section_body(text, section_orig, "\n".join(rows))
    # Add to shared section (create if missing)
    shared_body = get_section_body(text, shared_section)
    if shared_body is None:
        new_section = f"## {shared_section}\n\n{row}\n"
        # Insert before Footnotes/end
        for anchor in ("Footnotes",):
            if get_section_body(text, anchor) is not None:
                text = insert_section_before(text, anchor, new_section)
                break
        else:
            text = text.rstrip() + "\n\n" + new_section
    else:
        rows = _existing_lines(shared_body)
        if not any(_row_matches_name(r, name) for r in rows):
            rows.append(row)
        text = replace_section_body(text, shared_section, "\n".join(rows))
    _atomic_write_text(idx_path, text)


def _update_root_index_on_promote(vault: Path, name: str, kind: str) -> None:
    """Add `<name>` row to root `index.md` under the right section. Idempotent."""
    idx_path = vault / "index.md"
    section = "Concepts" if kind == "concept" else "Entities"
    row = _index_row(name)
    if not idx_path.is_file():
        # Create minimal root index
        text = "# Vault Root Index\n\n## Concepts\n\n## Entities\n"
    else:
        text = read_text(idx_path)
        if get_section_body(text, "Concepts") is None:
            text = text.rstrip() + "\n\n## Concepts\n\n"
        if get_section_body(text, "Entities") is None:
            text = text.rstrip() + "\n\n## Entities\n\n"
    body = get_section_body(text, section) or ""
    rows = _existing_lines(body)
    if not any(_row_matches_name(r, name) for r in rows):
        rows.append(row)
    text = replace_section_body(text, section, "\n".join(sorted(rows)))
    _atomic_write_text(idx_path, text)


def _append_course_log_promote(course_root: Path, name: str, kind: str,
                               sources_sorted: list,
                               contradictions: int,
                               today: str, vault: Path) -> None:
    """Append the promote log block. M4 fix: destination subdir is keyed
    on `kind` (was hardcoded `_concepts/` — wrong for entities)."""
    log_path = course_root / "log.md"
    if not log_path.is_file():
        return
    merged_paths = ", ".join(
        str(p.relative_to(vault)) for _, p, *_ in sources_sorted)
    dest_subdir = _KIND_TO_SUBDIR[kind]
    block = (
        f"\n## [{today}] promote | {name}\n"
        f"- Merged from: {merged_paths}\n"
        f"- Destination: {dest_subdir}/{name}.md (vault root)\n"
        f"- Contradictions raised: {contradictions}\n"
    )
    text = read_text(log_path)
    _atomic_write_text(log_path, text.rstrip() + "\n" + block)
