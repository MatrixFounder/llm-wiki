"""`classify-folder` subcommand — Phase 0 of folder-ingest.

Detects grouping pattern (prefix / sibling / flat) + classifies each file
into a role (primary / metadata / merge / link / derived-output / skip).
Refuses to run on a vault root unless `--force` (MED-4). Uses
`_UNGROUPED_SENTINEL` (a process-unique object) so a literal regex
capture cannot collide with the fallback bucket.

All heavy lifting lives in `wiki_ingest._classify`; this module is just
the CLI orchestration + JSON emit.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from wiki_ingest._classify import (
    _UNGROUPED_LABEL,
    _UNGROUPED_SENTINEL,
    _classify_one_file,
    _count_md_structure,
    _detect_grouping,
    _group_files,
    _pick_primary,
)
from wiki_ingest._safety import die
from wiki_ingest._vault import SCHEMA_FILE


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "classify-folder",
        help="Phase 0 of folder-ingest: detect grouping pattern + classify "
             "each file into primary/metadata/merge/link/derived-output; "
             "emit a plan JSON",
    )
    p.add_argument("folder",
                   help="path to a folder containing one-or-more sources to ingest")
    p.add_argument("--group-by",
                   help="optional regex with EXACTLY ONE capture group to "
                        "override grouping pattern "
                        "(e.g. '^(\\d+)\\s*-\\s*' for 'NN - name.ext' files)")
    p.add_argument("--force", action="store_true",
                   help="bypass vault-root check (refuses if WIKI_SCHEMA.md is present in target)")
    p.set_defaults(func=execute)


def execute(args: argparse.Namespace) -> int:
    folder = Path(args.folder).resolve()
    if not folder.is_dir():
        die(f"folder not a directory: {folder}")

    # MED-4: refuse running on a vault root unless --force.
    # A vault root has WIKI_SCHEMA.md at top level — classify-folder would
    # otherwise mis-treat schema/index/log as source files.
    if (folder / SCHEMA_FILE).exists() and not args.force:
        die(f"refusing to classify-folder on a vault root ({folder} contains "
            f"{SCHEMA_FILE}) — pass --force if you really mean it, or point at "
            f"a raw-source folder instead", code=2)

    all_entries = sorted(folder.iterdir(), key=lambda p: p.name)
    all_files = [e.name for e in all_entries if e.is_file()]
    subdirs = [e.name for e in all_entries
               if e.is_dir() and not e.name.startswith(".")]

    # MED-2: warn about subdirectories that classify-folder won't recurse into
    top_warnings: list[str] = []
    if subdirs:
        top_warnings.append(
            f"found {len(subdirs)} subdirectory(ies) in this folder — "
            f"classify-folder does NOT recurse. Run separately on each: "
            f"{subdirs[:5]}{'...' if len(subdirs) > 5 else ''}"
        )

    if args.group_by:
        # LOW-2: validate the user regex has exactly one capture group
        try:
            user_regex = re.compile(args.group_by)
        except re.error as e:
            die(f"invalid --group-by regex: {e}")
        if user_regex.groups != 1:
            die(f"--group-by regex must contain exactly one capture group, "
                f"got {user_regex.groups} in {args.group_by!r}")
        pattern_name = "prefix"
        pattern_info = {"regex": args.group_by, "source": "operator-override"}
        groups: dict = {}
        for f in all_files:
            m = user_regex.match(f)
            # Use sentinel object so a literal capture of `__ungrouped__` cannot
            # collide with the fallback bucket.
            key = m.group(1) if m else _UNGROUPED_SENTINEL
            groups.setdefault(key, []).append(f)
    else:
        pattern_name, pattern_info = _detect_grouping(all_files)
        groups = _group_files(all_files, pattern_name)

    # Sort: real string keys alphabetically, sentinel always last.
    str_keys = sorted(k for k in groups if isinstance(k, str))
    sorted_keys = str_keys + ([_UNGROUPED_SENTINEL] if _UNGROUPED_SENTINEL in groups else [])
    output_groups = []
    for key in sorted_keys:
        group_files = groups[key]
        # Emit the sentinel as a stable bracketed label that's distinguishable
        # from any regex capture (rejected by _safe_name due to `__` prefix
        # heuristic? no — but no regex capture can produce a Python object).
        emit_key: str = _UNGROUPED_LABEL if key is _UNGROUPED_SENTINEL else key
        roles: dict[str, list[str]] = {
            "primary": [], "metadata": [], "merge": [], "link": [],
            "derived_output": [], "skip": [],
        }
        rationales: dict[str, str] = {}
        text_candidates = []
        for f in group_files:
            role, rat = _classify_one_file(folder / f)
            rationales[f] = rat
            if role == "text-candidate":
                text_candidates.append(f)
            elif role == "derived-output":
                roles["derived_output"].append(f)
            elif role == "skip":
                roles["skip"].append(f)
            else:
                roles[role].append(f)

        # PHASE 2b — pick primary from text candidates
        warnings: list[str] = []
        if not text_candidates:
            warnings.append(
                "no text-readable primary in this group — manual review needed "
                "(consider running an extraction skill on a binary file first)"
            )
        elif len(text_candidates) == 1:
            f = text_candidates[0]
            roles["primary"].append(f)
            rationales[f] = "primary — only text-readable file in group"
        else:
            # multiple candidates: score + pick
            primary_file, primary_rat = _pick_primary(folder, text_candidates)
            if primary_file:
                roles["primary"].append(primary_file)
                rationales[primary_file] = f"primary — {primary_rat}"
                # Remaining text-candidates: classify as link or merge by structure
                for f in text_candidates:
                    if f == primary_file:
                        continue
                    p = folder / f
                    size, h2, fences, _ = _count_md_structure(p)
                    if size >= 2048 and h2 >= 3 and fences >= 2:
                        roles["link"].append(f)
                        rationales[f] = (f"unchosen primary → link "
                                         f"(standalone: {size}B, {h2} headings, "
                                         f"{fences} fence-lines)")
                    elif size < 5120 and h2 < 2:
                        roles["merge"].append(f)
                        rationales[f] = (f"unchosen primary → merge "
                                         f"(small/flat: {size}B, {h2} headings)")
                    else:
                        roles["link"].append(f)
                        rationales[f] = (f"unchosen primary → link "
                                         f"(default for unchosen: {size}B)")

        output_groups.append({
            "group_key": emit_key,
            "files": {k: v for k, v in roles.items()
                      if v and k not in ("skip", "derived_output")},
            "derived_outputs": roles["derived_output"],
            "skipped": roles["skip"],
            "rationale": rationales,
            "warnings": warnings,
        })

    plan = {
        "source_folder": str(folder),
        "grouping": {"pattern": pattern_name, "info": pattern_info},
        "warnings": top_warnings,
        "subdirs": subdirs,
        "groups": output_groups,
    }
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    return 0
