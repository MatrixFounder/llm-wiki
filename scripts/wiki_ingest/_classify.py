"""F3-helper · Folder-classification helpers for `classify-folder`.

Per-file role assignment (text-candidate / derived-output / link / merge
/ metadata / skip), grouping pattern detection (prefix / sibling / flat),
and `_pick_primary` segment-aware filename-hint scoring + log-size + prose
bonus. The `_UNGROUPED_SENTINEL` is a distinct in-memory object so a
literal regex capture cannot collide with the fallback bucket.

Pure stdlib — no F1/F2 imports needed. Tested by
`../tests/test__classify.py`.
"""
from __future__ import annotations

import functools
import math
import re
from pathlib import Path


# File extensions and their default classification roles
_OFFICE_EXTS = {".docx", ".pptx", ".xlsx", ".pdf"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp"}
_METADATA_EXTS = {".json", ".yaml", ".yml", ".toml"}
_TEXT_EXTS = {".txt", ".md", ".markdown", ".rst"}
_SKIP_EXTS = {".lock", ".swp", ".pyc", ".pyo"}
_SKIP_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}

# Filename hints for primary-vs-non-primary tie-breaking within a group
_PRIMARY_HINTS = (
    "transcript", "main", "content", "intro", "lesson",
    "phase", "recording", "talk", "session",
)
_NON_PRIMARY_HINTS = (
    "slides", "notes", "template", "appendix", "specification", "spec",
    "ricef", "glossary", "cheatsheet", "outline", "agenda",
    "description", "metadata",
)

# Default grouping regex: "01 - ", "02-", "1.2.", etc.
_PREFIX_REGEX = re.compile(r"^(\d+(?:\.\d+)*)[\s\-_.]+")

# Distinct in-memory sentinel for the "did not match the grouping regex"
# bucket, so a literal regex capture of e.g. `"_ungrouped"` cannot collide
# with the fallback bucket. The JSON-facing label uses angle brackets so it
# cannot equal any regex capture (regex captures never contain `<` or `>`).
_UNGROUPED_SENTINEL = object()
_UNGROUPED_LABEL = "<ungrouped>"

# Extensionless filenames that ARE text and should be treated as text-readable
_EXTENSIONLESS_TEXT_NAMES = {
    "Makefile", "README", "LICENSE", "AUTHORS", "CONTRIBUTORS",
    "CHANGELOG", "TODO", "NOTES", "Dockerfile", "Procfile",
    ".envrc", ".gitignore", ".dockerignore",
}


def _is_text_readable(ext: str) -> bool:
    return ext.lower() in _TEXT_EXTS


@functools.lru_cache(maxsize=512)
def _count_md_structure(path: Path) -> tuple[int, int, int, bool]:
    """Return (size_bytes, h2_count, fence_count, is_prose).

    `is_prose` is heuristic: file is text-readable AND not just lists/JSON-like.
    Rejects binary masquerade (L-M8): a file with significant UTF-8 decode
    errors or NUL bytes in the first 8 KiB is treated as non-prose so it
    can't win `_pick_primary` over a real markdown file.

    **P-L5 cache**: `lru_cache(512)` memoises results per-Path within a
    single CLI invocation. `_pick_primary` and `cmd_classify_folder` both
    call this on the same paths; previously the file was read twice. Cache
    lives for the process lifetime (CLI exits after one command, so no
    staleness risk).
    """
    try:
        size = path.stat().st_size
        # Peek at raw bytes first to filter binaries cheaply — `errors="replace"`
        # was masking U+FFFD substitutions that made binaries look text-y.
        with path.open("rb") as f:
            head = f.read(8192)
        if b"\x00" in head:
            return (size, 0, 0, False)
        sample_decoded = head.decode("utf-8", errors="replace")
        replacement_ratio = (sample_decoded.count("�")
                             / max(len(sample_decoded), 1))
        if replacement_ratio > 0.05:  # >5% undecodable → treat as binary
            return (size, 0, 0, False)
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return (0, 0, 0, False)
    h2_count = sum(1 for line in text.splitlines() if line.startswith("## "))
    fence_count = text.count("```")  # raw fence-line count; pairs of 2 = 1 block
    # rough prose check: has at least one full sentence-like line
    has_prose = any(len(line) > 60 and line.rstrip()[-1:] in ".!?»\"'"
                    for line in text.splitlines())
    return (size, h2_count, fence_count, has_prose)


def _filename_hint_score(stem_lower: str) -> int:
    """Segment-aware hint score. Right-most segment is most discriminative.

    Splits stem on common separators (./-/_/whitespace), then EACH SEGMENT
    must EXACTLY match a hint word — no substring matching. Substring caused
    false positives like `speculation` matching `spec`.
    """
    segments = re.split(r"[\s\-_.]+", stem_lower)
    segments = [s for s in segments if s]
    if not segments:
        return 0
    score = 0
    for i, seg in enumerate(reversed(segments)):
        weight = 3 if i == 0 else 1
        if seg in _PRIMARY_HINTS:
            score += 2 * weight
        if seg in _NON_PRIMARY_HINTS:
            score -= 2 * weight
    return score


def _looks_like_wiki_summary(path: Path) -> bool:
    """Read the file's first ~1KB and check for wiki-summary frontmatter.

    Streams just the first kilobyte — `read_text()[:1024]` would slurp the
    entire file into memory before slicing, which is wasteful on multi-MB
    inputs (P-L6).
    """
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            head = f.read(1024)
    except OSError:
        return False
    return ("type: lesson-summary" in head
            or "type: meeting-summary" in head
            or "kind: source" in head)


def _classify_one_file(path: Path) -> tuple[str, str]:
    """Per-file independent classification.

    Returns (role, rationale) — role in {text-candidate, derived-output, merge,
    link, metadata, skip}. Note: text-candidate is provisional — the per-group
    pass (PHASE 2b) decides which text-candidate becomes primary vs link vs merge.
    """
    name = path.name
    ext = path.suffix.lower()
    stem_lower = path.stem.lower()

    if name in _SKIP_NAMES or name.startswith("."):
        # extensionless dotfiles that are nonetheless text (.envrc, .gitignore)
        if name in _EXTENSIONLESS_TEXT_NAMES:
            pass  # fall through to text-readable handling
        else:
            return ("skip", "hidden/system file")
    if ext in _SKIP_EXTS:
        return ("skip", f"skip-extension {ext}")
    if ext in _OFFICE_EXTS:
        return ("link", f"binary office file ({ext}) — cannot inline, link only")
    if ext in _IMAGE_EXTS:
        return ("link", f"image asset ({ext})")
    if ext in _METADATA_EXTS:
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        if size < 4096:
            return ("metadata", f"structured-data file ({ext}, {size}B) → frontmatter")
        return ("link", f"large structured-data file ({ext}, {size}B) → link")

    # Extensionless text whitelist (Makefile, README, LICENSE, etc.)
    is_text = _is_text_readable(ext) or name in _EXTENSIONLESS_TEXT_NAMES
    if not is_text:
        return ("link", f"non-text-readable extension ({ext}) → link by default")

    size, h2, fences, prose = _count_md_structure(path)
    if size == 0:
        return ("skip", "empty file")

    # Derived-output detection: content-first (filename is a hint, not a gate).
    # ATTACK-19 fix: if a previously-generated summary is renamed to a
    # non-pattern filename, it must STILL be detected as derived via content.
    if _looks_like_wiki_summary(path):
        return ("derived-output",
                f"previously-generated wiki summary "
                f"(frontmatter has type: lesson-summary / kind: source)")

    # All other text-readable files become candidates; per-group pass picks primary
    return ("text-candidate",
            f"text-readable ({size}B, {h2} ## headings, fences={fences}, prose={prose})")


def _detect_grouping(filenames: list[str]) -> tuple[str, dict | None]:
    """Detect grouping pattern from a list of filenames.

    Returns (pattern_name, info_dict). pattern_name in {"prefix", "sibling", "flat"}.
    info_dict has metadata about the pattern (e.g., regex used, base-name mapping).
    """
    if not filenames:
        return ("flat", None)

    # 1. Try filename-prefix pattern (NN-, NN.M-, etc.)
    matched = [(f, _PREFIX_REGEX.match(f)) for f in filenames]
    prefix_hits = [(f, m.group(1)) for f, m in matched if m]
    if len(prefix_hits) >= max(2, len(filenames) // 2):
        return ("prefix", {"regex": _PREFIX_REGEX.pattern,
                           "matched": f"{len(prefix_hits)}/{len(filenames)}"})

    # 2. Try sibling-sidecar pattern: a shared base before the first '.'
    #    e.g. {lesson.txt, lesson.description.md, lesson.txt.stat.json} share base "lesson"
    bases: dict[str, list[str]] = {}
    for f in filenames:
        base = f.split(".", 1)[0]
        bases.setdefault(base, []).append(f)
    # if at least one base has ≥2 files AND it covers most filenames → sibling
    big_groups = [(b, fs) for b, fs in bases.items() if len(fs) >= 2]
    if big_groups:
        total_covered = sum(len(fs) for _, fs in big_groups)
        if total_covered >= max(2, len(filenames) // 2):
            return ("sibling", {"shared_bases": [b for b, _ in big_groups]})

    return ("flat", None)


def _group_files(filenames: list[str], pattern: str) -> dict:
    """Group filenames by detected pattern.

    Returns a dict whose keys are either str (regex capture) OR the
    `_UNGROUPED_SENTINEL` object for files that didn't match the regex.
    The sentinel cannot collide with any literal regex capture, so even
    `--group-by '^(__ungrouped__)'` won't merge real and fallback buckets.
    """
    if pattern == "prefix":
        groups: dict = {}
        for f in filenames:
            m = _PREFIX_REGEX.match(f)
            key = m.group(1) if m else _UNGROUPED_SENTINEL
            groups.setdefault(key, []).append(f)
        return groups
    elif pattern == "sibling":
        groups = {}
        for f in filenames:
            base = f.split(".", 1)[0]
            groups.setdefault(base, []).append(f)
        return groups
    else:  # flat
        return {"_all": list(filenames)}


def _pick_primary(folder: Path, candidates: list[str]) -> tuple[str | None, str]:
    """From multiple text-candidates, pick THE primary.

    Strategy:
    1. Score each by filename-hint (segment-aware).
    2. If pool has BOTH positive- and negative-hint files → only non-negative
       files compete (categorical discrimination, hint wins over size).
    3. Within the eligible pool, pick by log-size + prose bonus.

    Returns (chosen_file_or_None, rationale).
    """
    if not candidates:
        return (None, "no text-readable primary-candidate in group")
    if len(candidates) == 1:
        return (candidates[0], "only text-readable file in group")

    # Phase A: collect signals per file
    signals = []
    for f in candidates:
        size, h2, fences, prose = _count_md_structure(folder / f)
        hint = _filename_hint_score(Path(f).stem.lower())
        signals.append({"file": f, "size": size, "hint": hint, "prose": prose,
                        "h2": h2, "fences": fences})

    # Phase B: filter pool — if mixed-hint, only positive/neutral compete
    pos = [s for s in signals if s["hint"] > 0]
    neg = [s for s in signals if s["hint"] < 0]
    if pos and neg:
        pool = [s for s in signals if s["hint"] >= 0]
        pool_explain = (f"hint-pool: kept {len(pool)} non-negative files "
                        f"(dropped {len(neg)} with non-primary hints)")
    else:
        pool = signals
        pool_explain = "size-only ranking (no discriminating filename hints)"

    # Phase C: score within pool — size + hint + prose
    scored = []
    for s in pool:
        score = math.log10(max(s["size"], 1)) * 10 + s["hint"] + (5 if s["prose"] else 0)
        scored.append((score, s))
    scored.sort(reverse=True, key=lambda x: x[0])

    top = scored[0][1]
    top_score = scored[0][0]
    runner_up = scored[1] if len(scored) > 1 else None
    rationale = (f"{pool_explain}; top: {top['file']} "
                 f"({top['size']}B, hint={top['hint']:+d})")
    if runner_up and top_score - runner_up[0] < 5:
        rationale += (f"; close runner-up {runner_up[1]['file']} "
                      f"({runner_up[1]['size']}B) — review")
    return (top["file"], rationale)
