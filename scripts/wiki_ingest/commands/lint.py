"""`lint` subcommand — health check: orphans, dangling, contradictions, missing.

One-pass enrichment (OVERLAP-2 + P-H2): each page read once, masked once,
parsed once, wikilinks extracted once. Subsequent passes consume cached
data. O(1) in-memory `known_names` set replaces the pre-fix stat-storm
(P-H3). Concept aggregation is case-insensitive (L-L7). Dangling reports
surface anchor info (L-L4). Output sanitised via `_safe_for_json` (S-M6).

**TASK 016 bead 016-04 — two-tier extensions** (A-M-1 invariant net):

When `args.vault` is a vault ROOT (`schema_version: 2.0`), lint switches
to two-tier mode. It discovers every course via `discover_courses` and
adds four new finding categories to the JSON:

- `cross_course_duplicate` — same filename in ≥2 courses' `_concepts/`/`_entities/`.
- `invariant_violation` — filename present at root AND in some course
  (HARD failure: non-zero exit code; the one-page-one-place invariant).
- Cross-layer dangling refinement (R6.3) — a course-local `[[Foo]]`
  where `Foo` exists at root is NOT dangling. Cross-course-only
  references gain a `hint` field suggesting promotion.
- `root_footnote_format_warning` (R6.4) — root-page footnote definitions
  whose target is NOT `<course_rel>/_sources/<slug>` form. Warning only;
  exit code unaffected.

Sort discipline: every list is sorted alphabetically by `name`/`target`/`page`
so JSON output is byte-stable (m-5 / determinism gate).

`--limit N` caps findings per category and adds a `truncated: true` marker
(TASK §8 risk 3 mitigation, R6.6).
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from wiki_ingest._frontmatter import split_frontmatter
from wiki_ingest._markdown import (
    _extract_wikilinks_with_anchors,
    _mask_code_fences,
    _mask_inline_constructs,
    get_section_body,
)
from wiki_ingest._safety import _safe_for_json, die, read_text
from wiki_ingest._vault import (
    SCHEMA_FILE,
    SUBDIR_TO_KIND,
    _peek_schema_version,
    _walk_pages,
    discover_courses,
)


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("lint",
                       help="health check: orphans, dangling links, "
                            "contradictions, missing pages")
    p.add_argument("vault")
    p.add_argument("--threshold", type=int, default=2,
                   help="min sources mentioning a concept to flag missing-page (default: 2)")
    p.add_argument("--limit", type=int, default=None,
                   help="cap findings per category (default: no cap); "
                        "categories that hit the cap gain `truncated: true`")
    p.set_defaults(func=execute)


def execute(args: argparse.Namespace) -> int:
    vault = Path(args.vault).resolve()
    if not vault.is_dir():
        die(f"vault not a directory: {vault}")

    # Mode detection: vault root has schema_version 2.0 → two-tier mode.
    sv = _peek_schema_version(vault / SCHEMA_FILE)
    if sv == "2.0":
        return _execute_two_tier(args, vault)
    return _execute_single(args, vault)


def _execute_single(args: argparse.Namespace, vault: Path) -> int:
    """v1 single-course lint (TASK 015 baseline). Byte-identical to pre-016."""

    pages: dict[str, dict] = {}   # name → {path, raw, fm, kind, masked, wikilinks}
    inbound: dict[str, set[str]] = {}
    contradictions: list[dict] = []
    # L-L7: aggregate concept mentions case-insensitively so
    # "Hermes Agent" vs "hermes agent" don't fragment the missing-page
    # heuristic. Store both the canonical display form and the sources.
    concept_freq: dict[str, dict] = {}  # lc_name → {display, sources: set}

    # ONE-PASS enrichment: read each page once, mask once, parse fm once,
    # extract wikilinks once, run contradictions check using the cached
    # masked view. Subsequent passes consume cached data — no re-mask,
    # no re-parse (OVERLAP-2 + P-H2).
    for md in _walk_pages(vault):
        try:
            text = read_text(md)
        except OSError:
            continue
        fm, body = split_frontmatter(text)
        masked_full = _mask_inline_constructs(_mask_code_fences(text))
        wikilinks_with_anchors = _extract_wikilinks_with_anchors(text,
                                                                 masked=masked_full)
        wikilinks = set(wikilinks_with_anchors.keys())
        name = md.stem
        pages[name] = {
            "path": str(md.relative_to(vault)),
            "raw": text,
            "fm": fm,
            "masked": masked_full,
            "wikilinks": wikilinks,
            # {target: {anchor, ...}} — anchors used for L-L4 dangling display
            "wikilinks_anchors": wikilinks_with_anchors,
            "kind": fm.get("kind") or SUBDIR_TO_KIND.get(md.parent.name, "unknown"),
        }
        # contradictions detection — reuse the cached masked view
        contra_body = get_section_body(text, "Contradictions", masked=masked_full)
        if contra_body and contra_body.strip():
            count = contra_body.count("⚠️")
            contradictions.append({
                "page": str(md.relative_to(vault)),
                "count": count or 1,
            })
        # collect concept mentions from source-page frontmatter — keyed by
        # lowercase form (L-L7) so casing variants aggregate together.
        if SUBDIR_TO_KIND.get(md.parent.name) == "source":
            for c in (fm.get("concepts") or []):
                if not isinstance(c, str):
                    continue
                c = c.strip()
                if not c:
                    continue
                lc = c.lower()
                entry = concept_freq.setdefault(lc, {"display": c, "sources": set()})
                entry["sources"].add(name)

    # In-memory page-name set for O(1) existence checks — replaces the
    # stat-storming `_page_exists_anywhere` (P-H3).
    known_names: set[str] = set(pages.keys())

    # inbound link counts — reuse cached wikilinks + frontmatter
    # AND treat frontmatter `concepts:` / `related:` entries as implicit
    # inbound links, since they declare "this source is about X" even when
    # the body doesn't bracket the name as [[X]].
    for name, info in pages.items():
        targets = set(info["wikilinks"])
        fm = info["fm"]
        for entry in (fm.get("concepts") or []):
            if not isinstance(entry, str):
                continue
            e = entry.strip()
            if e:
                targets.add(e)
        for entry in (fm.get("related") or []):
            if not isinstance(entry, str):
                continue
            m = re.match(r"^\[\[([^\]|#]+?)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]$",
                         entry.strip())
            t = (m.group(1) if m else entry).strip()
            if t:
                targets.add(t)
        for t in targets:
            if not t or t == name:
                continue  # self-reference doesn't count as inbound
            inbound.setdefault(t, set()).add(name)

    # orphans: pages with no inbound link (excluding source pages, which are root-of-truth)
    orphans = []
    for name, info in pages.items():
        if info["kind"] == "source":
            continue  # source pages don't need inbound links
        if not inbound.get(name):
            orphans.append({"page": info["path"], "kind": info["kind"]})

    # dangling: link targets that have no corresponding page (O(1) membership
    # check via known_names, no filesystem stat needed). For each broken
    # target we also surface any anchors that were referenced (L-L4) so the
    # operator sees `Foo#API` instead of bare `Foo`.
    dangling: dict[str, dict] = {}
    for name, info in pages.items():
        for target, anchors in info["wikilinks_anchors"].items():
            if target in known_names:
                continue
            entry = dangling.setdefault(target, {"referenced_by": set(),
                                                 "anchors": set()})
            entry["referenced_by"].add(info["path"])
            entry["anchors"].update(a for a in anchors if a)

    # missing concept pages: concepts mentioned in ≥threshold sources without
    # a page. Case-insensitive aggregation (L-L7) — entries are keyed by
    # lowercase form, but we surface the first-seen display casing.
    threshold = args.threshold
    known_lc = {n.lower() for n in known_names}
    missing_concept_pages = []
    for lc, entry in concept_freq.items():
        if lc in known_lc:
            continue
        sources = sorted(entry["sources"])
        if len(sources) >= threshold:
            missing_concept_pages.append({
                "name": entry["display"],
                "mentioned_in": sources,
                "count": len(sources),
            })

    report = {
        "vault": str(vault),
        "totals": {
            "pages": len(pages),
            "orphans": len(orphans),
            "dangling_link_targets": len(dangling),
            "pages_with_open_contradictions": len(contradictions),
            "missing_concept_pages": len(missing_concept_pages),
        },
        "orphans": sorted(orphans, key=lambda x: x["page"]),
        "dangling_links": [
            {"target": t,
             "referenced_by": sorted(d["referenced_by"]),
             # Surface specific anchors so the operator sees Foo#API (L-L4)
             "anchors": sorted(d["anchors"]) if d["anchors"] else []}
            for t, d in sorted(dangling.items())
        ],
        "open_contradictions": sorted(contradictions, key=lambda x: x["page"]),
        "missing_concept_pages": sorted(missing_concept_pages, key=lambda x: -x["count"]),
    }
    print(json.dumps(_safe_for_json(report), indent=2, ensure_ascii=False))
    return 0


# =============================================================================
# TASK 016 bead 016-04 — two-tier mode (invariant net)
# =============================================================================

# Footnote-definition pattern. Anchored to line-start with re.M so a single
# `[^src-slug]` key matches once per line (T16-S3 — no second-definition
# smuggling).
_FOOTNOTE_DEF_RE = re.compile(
    r"^\[\^src-(?P<slug>[^\]]+)\]:\s*\[\[(?P<target>[^\]]+)\]\][^\n]*$",
    re.M,
)


def _collect_layer_filenames(layer_root: Path, subdirs: tuple[str, ...]
                             ) -> dict[str, tuple[str, Path]]:
    """name → (kind, full_path) for `.md` files under `layer_root / sub`.

    `kind` is `"concept"` or `"entity"` (per subdir). Symlinked files are
    skipped (OVERLAP-5). Used by the cross-course-duplicate + invariant
    scans below.
    """
    out: dict[str, tuple[str, Path]] = {}
    for sub in subdirs:
        d = layer_root / sub
        if not d.is_dir():
            continue
        for md in d.glob("*.md"):
            try:
                if md.is_symlink():
                    continue
            except OSError:
                continue
            kind = "concept" if sub == "_concepts" else "entity"
            out[md.stem] = (kind, md)
    return out


def _apply_limit(items: list, limit: int | None) -> tuple[list, bool]:
    """Cap `items` to `limit`; returns (capped_list, truncated_flag)."""
    if limit is None or len(items) <= limit:
        return items, False
    return items[:limit], True


def _execute_two_tier(args: argparse.Namespace, vault_root: Path) -> int:
    """Two-tier vault lint with cross-course + invariant checks (R6 / A-M-1).

    Aggregates findings across the root layer + every course layer:
    - Existing v1 categories (orphans/dangling/contradictions/missing-pages)
      are computed PER LAYER and merged.
    - Cross-layer dangling refinement (R6.3): a course-local `[[Foo]]` where
      `Foo` exists at root is NOT dangling.
    - New categories: `cross_course_duplicate`, `invariant_violation`,
      `root_footnote_format_warning`.
    """
    course_roots = discover_courses(vault_root)

    # Per-layer page maps: keyed by layer label, then by name.
    # Layer label: "_root_" or relative-path of course root.
    layer_pages: dict[str, dict[str, dict]] = {}
    # Across-layer name → set of (layer_label, path) — for dangling refinement
    # and cross-course duplicate detection.
    name_to_layers: dict[str, set[str]] = {}

    # 1. Root layer pages (no _sources/ at root per spec §2.5)
    root_label = "_root_"
    layer_pages[root_label] = _enrich_layer(vault_root, has_sources=False)
    for nm in layer_pages[root_label]:
        name_to_layers.setdefault(nm, set()).add(root_label)

    # 2. Course layers
    for c in course_roots:
        label = str(c.relative_to(vault_root))
        layer_pages[label] = _enrich_layer(c, has_sources=True)
        for nm in layer_pages[label]:
            name_to_layers.setdefault(nm, set()).add(label)

    # 3. Per-layer findings (existing v1 categories), aggregated
    all_orphans: list[dict] = []
    all_dangling: dict[str, dict] = {}
    all_contradictions: list[dict] = []
    all_missing: list[dict] = []
    # known_names across all layers (cross-layer membership for dangling
    # refinement, R6.3): a course-local link to a root page is NOT dangling.
    known_global: set[str] = set(name_to_layers.keys())

    for label, pages in layer_pages.items():
        orphans, dangling, contras, missing = _layer_findings(
            pages, known_global, args.threshold, label,
        )
        all_orphans.extend(orphans)
        for tgt, dat in dangling.items():
            entry = all_dangling.setdefault(
                tgt, {"referenced_by": set(), "anchors": set()},
            )
            entry["referenced_by"].update(dat["referenced_by"])
            entry["anchors"].update(dat["anchors"])
        all_contradictions.extend(contras)
        all_missing.extend(missing)

    # 4. Cross-course duplicates: same filename in ≥2 courses
    cross_dup: list[dict] = []
    for name, layers in sorted(name_to_layers.items()):
        course_layers = [l for l in layers if l != root_label]
        if len(course_layers) < 2:
            continue
        paths = []
        kind = "concept"
        for lbl in sorted(course_layers):
            k, p = next(iter(layer_pages[lbl][name]["_files"]))
            paths.append(str(p.relative_to(vault_root)))
            kind = k
        cross_dup.append({
            "name": name,
            "kind": kind,
            "courses": sorted(paths),
            "suggest": f'wiki-ingest promote "{name}"',
        })

    # 5. Invariant violations: filename at root AND in some course
    invariant: list[dict] = []
    for name, layers in sorted(name_to_layers.items()):
        if root_label in layers and len(layers) > 1:
            course_paths = []
            for lbl in sorted(l for l in layers if l != root_label):
                _, p = next(iter(layer_pages[lbl][name]["_files"]))
                course_paths.append(str(p.relative_to(vault_root)))
            _, rp = next(iter(layer_pages[root_label][name]["_files"]))
            invariant.append({
                "name": name,
                "kind": layer_pages[root_label][name]["kind"],
                "root_path": str(rp.relative_to(vault_root)),
                "course_paths": course_paths,
                "suggest": f'wiki-ingest promote "{name}" or demote it',
            })

    # 6. Root-page footnote-format warnings (R6.4)
    valid_course_rels = {str(c.relative_to(vault_root)) for c in course_roots}
    fn_warnings = _root_footnote_warnings(layer_pages[root_label],
                                          valid_course_rels, vault_root)

    # Apply sort discipline + --limit
    limit = args.limit
    orphans_out, orph_trunc = _apply_limit(
        sorted(all_orphans, key=lambda x: x["page"]), limit)
    dangling_out_full = [
        {"target": t,
         "referenced_by": sorted(d["referenced_by"]),
         "anchors": sorted(d["anchors"]) if d["anchors"] else []}
        for t, d in sorted(all_dangling.items())
    ]
    dangling_out, dang_trunc = _apply_limit(dangling_out_full, limit)
    contras_out, contra_trunc = _apply_limit(
        sorted(all_contradictions, key=lambda x: x["page"]), limit)
    missing_out, miss_trunc = _apply_limit(
        sorted(all_missing, key=lambda x: -x["count"]), limit)
    cross_dup_out, cd_trunc = _apply_limit(cross_dup, limit)
    invariant_out, inv_trunc = _apply_limit(invariant, limit)
    fn_warnings_out, fn_trunc = _apply_limit(fn_warnings, limit)

    report = {
        "vault": str(vault_root),
        "mode": "two-tier",
        "totals": {
            "courses": len(course_roots),
            "root_pages": len(layer_pages[root_label]),
            "orphans": len(all_orphans),
            "dangling_link_targets": len(all_dangling),
            "pages_with_open_contradictions": len(all_contradictions),
            "missing_concept_pages": len(all_missing),
            "cross_course_duplicate": len(cross_dup),
            "invariant_violation": len(invariant),
            "root_footnote_format_warning": len(fn_warnings),
        },
        "orphans": orphans_out,
        "dangling_links": dangling_out,
        "open_contradictions": contras_out,
        "missing_concept_pages": missing_out,
        "cross_course_duplicate": cross_dup_out,
        "invariant_violation": invariant_out,
        "root_footnote_format_warning": fn_warnings_out,
    }
    # Truncation markers (only when --limit kicked in)
    truncated = {
        k: True for k, v in (
            ("orphans", orph_trunc),
            ("dangling_links", dang_trunc),
            ("open_contradictions", contra_trunc),
            ("missing_concept_pages", miss_trunc),
            ("cross_course_duplicate", cd_trunc),
            ("invariant_violation", inv_trunc),
            ("root_footnote_format_warning", fn_trunc),
        ) if v
    }
    if truncated:
        report["truncated"] = truncated
    print(json.dumps(_safe_for_json(report), indent=2, ensure_ascii=False))
    # R6.2: invariant_violation is a HARD failure
    return 1 if invariant else 0


def _enrich_layer(layer_root: Path, *, has_sources: bool) -> dict[str, dict]:
    """Walk a single layer (root or course), return name → enriched-page dict.

    `has_sources=False` for the vault root (no `_sources/` per spec §2.5).
    Each returned page dict carries: path, fm, kind, wikilinks_anchors,
    contradiction-count, source-concept-frequency, plus `_files` (a
    one-element list of `(kind, Path)` so the cross-layer pass can recover
    the full path without re-stat).
    """
    subdirs = ("_sources", "_concepts", "_entities") if has_sources \
        else ("_concepts", "_entities")
    pages: dict[str, dict] = {}
    for sub in subdirs:
        d = layer_root / sub
        if not d.is_dir():
            continue
        for md in d.glob("*.md"):
            try:
                if md.is_symlink():
                    continue
            except OSError:
                continue
            try:
                text = read_text(md)
            except OSError:
                continue
            fm, _ = split_frontmatter(text)
            masked = _mask_inline_constructs(_mask_code_fences(text))
            wikilinks_anchors = _extract_wikilinks_with_anchors(
                text, masked=masked)
            kind = fm.get("kind") or SUBDIR_TO_KIND.get(sub, "unknown")
            contra_body = get_section_body(text, "Contradictions", masked=masked)
            contra_count = (contra_body.count("⚠️") or 1) \
                if contra_body and contra_body.strip() else 0
            concepts = []
            if SUBDIR_TO_KIND.get(sub) == "source":
                for c in (fm.get("concepts") or []):
                    if isinstance(c, str) and c.strip():
                        concepts.append(c.strip())
            pages[md.stem] = {
                "_files": [(kind, md)],
                "raw": text,
                "fm": fm,
                "kind": kind,
                "wikilinks_anchors": wikilinks_anchors,
                "wikilinks": set(wikilinks_anchors.keys()),
                "contradiction_count": contra_count,
                "concepts_from_source": concepts,
                "_sub": sub,
            }
    return pages


def _layer_findings(pages: dict[str, dict], known_global: set[str],
                    threshold: int, layer_label: str
                    ) -> tuple[list, dict, list, list]:
    """Compute v1 findings for one layer; dangling uses `known_global`
    so cross-layer references resolve (R6.3 refinement).

    Returns (orphans, dangling, contradictions, missing_concept_pages).
    Each finding includes the layer label for cross-layer disambiguation.
    """
    inbound: dict[str, set[str]] = {}
    concept_freq: dict[str, dict] = {}
    for name, info in pages.items():
        targets = set(info["wikilinks"])
        for entry in info["fm"].get("concepts") or []:
            if isinstance(entry, str) and entry.strip():
                targets.add(entry.strip())
        for entry in info["fm"].get("related") or []:
            if not isinstance(entry, str):
                continue
            m = re.match(r"^\[\[([^\]|#]+?)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]$",
                         entry.strip())
            t = (m.group(1) if m else entry).strip()
            if t:
                targets.add(t)
        for t in targets:
            if not t or t == name:
                continue
            inbound.setdefault(t, set()).add(name)
        # source-page concept frequency
        for c in info["concepts_from_source"]:
            lc = c.lower()
            entry = concept_freq.setdefault(lc, {"display": c, "sources": set()})
            entry["sources"].add(name)

    orphans = []
    for name, info in pages.items():
        if info["kind"] == "source":
            continue
        if not inbound.get(name):
            _, p = info["_files"][0]
            orphans.append({"page": str(p), "kind": info["kind"],
                            "layer": layer_label})
    # dangling: use known_global for cross-layer awareness (R6.3)
    dangling: dict[str, dict] = {}
    for name, info in pages.items():
        for target, anchors in info["wikilinks_anchors"].items():
            if target in known_global:
                continue
            entry = dangling.setdefault(target, {"referenced_by": set(),
                                                 "anchors": set()})
            _, p = info["_files"][0]
            entry["referenced_by"].add(str(p))
            entry["anchors"].update(a for a in anchors if a)
    contradictions = []
    for name, info in pages.items():
        if info["contradiction_count"] > 0:
            _, p = info["_files"][0]
            contradictions.append({"page": str(p),
                                   "count": info["contradiction_count"],
                                   "layer": layer_label})
    # missing concept pages: only meaningful per-course (concept_freq comes
    # from source pages, which don't exist at root). Aggregation across
    # layers happens in the caller — here just emit raw entries.
    known_lc = {n.lower() for n in pages}
    missing = []
    for lc, entry in concept_freq.items():
        if lc in known_lc:
            continue
        sources = sorted(entry["sources"])
        if len(sources) >= threshold:
            missing.append({
                "name": entry["display"],
                "mentioned_in": sources,
                "count": len(sources),
                "layer": layer_label,
            })
    return orphans, dangling, contradictions, missing


def _root_footnote_warnings(root_pages: dict[str, dict],
                            valid_course_rels: set[str],
                            vault_root: Path) -> list[dict]:
    """R6.4: root-page footnote-format check.

    Every `[^src-<slug>]: [[<target>]]` definition on a root page should
    have `<target>` shaped as `<course_rel>/_sources/<slug>` for some
    `course_rel in valid_course_rels`. Bare `<slug>` (no prefix) emits
    a warning. The check is regex-anchored to line-start (T16-S3) so a
    single `[^src-key]` definition is processed once per line.
    """
    out: list[dict] = []
    for name, info in root_pages.items():
        _, p = info["_files"][0]
        for m in _FOOTNOTE_DEF_RE.finditer(info["raw"]):
            target = m.group("target").strip()
            slug = m.group("slug").strip()
            # Strip alias `[[target|alias]]` for the check (H5 robustness)
            target_only = target.split("|", 1)[0]
            # Vault-relative form check: target must start with one of
            # the discovered course-relative prefixes + `/_sources/`.
            # H6 fix: removed the prior `or target.endswith(<slug-suffix>)`
            # fallback which permitted unknown-course prefixes
            # (e.g. `evil/_sources/foo`) to pass silently.
            is_vault_relative = any(
                target_only.startswith(f"{rel}/_sources/")
                for rel in valid_course_rels
            )
            if is_vault_relative:
                continue
            # Anchor-only / fragment-style refs aren't footnote-format issues.
            if target_only.startswith("#"):
                continue
            out.append({
                "page": str(p.relative_to(vault_root)),
                "footnote": f"[^src-{slug}]",
                "current_target": f"[[{target}]]",
                "expected_pattern": "<course_rel>/_sources/<slug>",
                "severity": "warning",
            })
    out.sort(key=lambda x: (x["page"], x["footnote"]))
    return out
