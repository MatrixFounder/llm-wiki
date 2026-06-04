"""The `wiki-sync` routing brain (TASK 018 / R-11).

`classify_file` is the deterministic classifier: given a discovered file it
returns a `Decision` (one of `convert+ingest` / `ingest` / `upsert` / `skip`)
with a stable, human-readable `reason`. NO LLM, network, or filesystem mutation
happens here — `wiki-sync scan` (the CLI) is pure planning; the orchestrator
workflow (`workflows/wiki-sync.md`) executes the plan.

Routing layers (locked — functional-architecture.md *Sync Dispatcher*):
  1. extension front-stage (bead 06) — case-folded suffix → convert/text/md/skip,
     compound `.excalidraw.md` / `.canvas` / `.base` handled before generic `.md`;
  2. `.md` content-tag layer (bead 07) — `#<ns>/{raw,skip,keep}` + `<ns>:` field,
     precedence **skip > raw > keep > default**; `_raw/` ≡ implicit raw; `#wiki/keep`
     rescues a `.md` from an `exclude:` zone;
  3. generated-view sidecar detection + only-a-view guard (bead 08) — DB Folder /
     Bases / Dataview / folder-note → skip ONLY when the note is essentially a view
     (a note that *embeds* a view block alongside prose is content → upsert);
  4. unmappable-`type:` predictor (bead 09) — a no-tag `.md` upserts ONLY when the
     resolved layout's `normalize_frontmatter` accepts it (layout-general, W-1),
     else `skip:unmappable-type`; degenerate inputs (empty / unparseable) never raise.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat as stat_mod
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any, Literal

import frontmatter
from slugify import slugify

from scripts.wiki_index.layout import SYSTEM_FILES
from scripts.wiki_index.layout_config import LayoutConfig
from scripts.wiki_index.normalization import UnmappedTypeError, normalize_frontmatter
from scripts.wiki_index.sync_config import SyncConfig

SyncAction = Literal["convert+ingest", "ingest", "upsert", "skip"]

# --- extension routing sets (bead 06; config `extensions` overrides EXTEND them) ---
_CONVERT_EXTS = frozenset({".docx", ".xlsx", ".pptx", ".pdf"})
_TEXT_EXTS = frozenset({".txt", ".vtt", ".srt"})
_DETIMESTAMP_EXTS = frozenset({".vtt", ".srt"})
# Obsidian Canvas / Bases definition files are navigation artifacts, not knowledge.
_VIEW_ARTIFACT_EXTS = frozenset({".canvas", ".base"})
_BINARY_EXTS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".ico", ".tiff",
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".mp3", ".wav", ".m4a", ".flac", ".ogg",
    ".zip", ".gz", ".tar", ".7z", ".rar", ".bin", ".exe", ".dll", ".so", ".dylib",
})
# Fenced-block info-strings that mark a generated view (bead 08).
_VIEW_INFO = {"yaml:dbfolder": "dbfolder", "base": "base",
              "dataview": "dataview", "dataviewjs": "dataviewjs"}

# Upper bound on a `.md` we will slurp+inspect for content routing. A markdown
# note over this is pathological; reading it whole (`read_text` + the line-split
# passes) is the one unbounded-RAM lever in scan, so an oversize `.md` is skipped
# rather than read (critic-security MED — makes security.md §7.5 "bounded" true).
WIKI_SYNC_MD_MAX_BYTES = 8 * 1024 * 1024  # 8 MiB


@lru_cache(maxsize=8)
def _ext_route_sets(
    config: SyncConfig,
) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    """`(convert, text, skip)` extension sets — built-ins extended by the
    operator overrides. Memoised on the (frozen, hashable) config so the per-file
    `classify_file` doesn't rebuild three sets on every call (critic-performance
    LOW — free win in the hot loop)."""
    convert = _CONVERT_EXTS | frozenset(e.lower() for e in config.extensions_convert)
    text = _TEXT_EXTS | frozenset(e.lower() for e in config.extensions_text)
    skip = frozenset(e.lower() for e in config.extensions_skip)
    return convert, text, skip


@dataclass(frozen=True)
class Decision:
    """The classifier's verdict for one file.

    `converter` (docx|xlsx|pptx|pdf), `staged_target`
    (`_raw/.staging/<slug(stem)>-<ext>.md`), and `normalize` (`vtt-detimestamp`)
    are populated only for the routes that need them; `reason` is always set and
    is stable enough to assert on / surface in a `--dry-run` report.
    """

    action: SyncAction
    reason: str
    converter: str | None = None
    staged_target: str | None = None
    normalize: str | None = None


# Directories never descended into (system / config / wiki-sync working dirs).
# Any dot-segment dir (`.git`, `.obsidian`, `.wiki`, `_raw/.staging`, `_raw/.locks`)
# plus the non-dot `_raw/failed` quarantine.
_EXPLICIT_PRUNE_RELDIRS = frozenset({"_raw/.staging", "_raw/.locks", "_raw/failed"})


@dataclass(frozen=True)
class Candidate:
    """One discovered file the scanner will classify.

    `rel` is the vault-relative POSIX path (the `source_state` scope + the plan
    entry path); `mtime` is the walk's single `stat()`; `in_raw`/`in_exclude_zone`
    are the precomputed routing flags `classify_file` consumes."""

    path: Path
    rel: str
    mtime: float
    in_raw: bool
    in_exclude_zone: bool


def _walk_extensions(config: SyncConfig) -> set[str]:
    """The case-folded extension set the walk yields (convert ∪ text ∪ `.md`,
    plus operator overrides, minus operator skips). Anything else is pruned
    pre-stat — images/binaries/unknown cost no `stat()` or read (W-2)."""
    exts = set(_CONVERT_EXTS) | set(_TEXT_EXTS) | {".md"}
    exts |= {e.lower() for e in config.extensions_convert}
    exts |= {e.lower() for e in config.extensions_text}
    exts -= {e.lower() for e in config.extensions_skip}
    return exts


def _is_pruned_dir(rel_dir: str) -> bool:
    """A directory never descended into: any dot-segment dir (`.git`, `.obsidian`,
    `.wiki`, `_raw/.staging`, `_raw/.locks`) plus the explicit `_raw/failed`."""
    if rel_dir in ("", "."):
        return False
    if any(seg.startswith(".") for seg in rel_dir.split("/")):
        return True
    return rel_dir in _EXPLICIT_PRUNE_RELDIRS or any(
        rel_dir == p or rel_dir.startswith(p + "/") for p in _EXPLICIT_PRUNE_RELDIRS
    )


def _matches_exclude(rel: str, globs: tuple[str, ...]) -> bool:
    pp = PurePosixPath(rel)
    for g in globs:
        try:
            if pp.full_match(g):
                return True
        except ValueError:
            continue
    return False


def iter_sync_candidates(
    zone: Path, *, vault_root: Path, config: SyncConfig
) -> list[Candidate]:
    """The wiki-sync-OWN discovery walk (NOT `iter_pages`, which is `.md`-only).

    Mirrors `iter_pages`' discipline — free string/glob filters first → ONE
    `lstat()` per surviving candidate → case-folded extension prune *before* any
    read. `exclude:`-matched non-`.md` are pruned immediately; `exclude:`-matched
    `.md` are still yielded (so `#wiki/keep` can rescue them) with
    `in_exclude_zone=True`. Symlinked dirs are not descended and symlinked target
    files are refused (`O_NOFOLLOW` posture). Output is sorted by vault-relative
    POSIX path (determinism, AC-10)."""
    walk_exts = _walk_extensions(config)
    exclude_globs = tuple(config.exclude)
    out: list[Candidate] = []

    for dirpath, dirnames, filenames in os.walk(zone, followlinks=False):
        dpath = Path(dirpath)
        # Prune dirs in place: symlinked dirs + system/working dirs.
        dirnames[:] = [
            d for d in dirnames
            if not (dpath / d).is_symlink()
            and not _is_pruned_dir(_safe_rel(dpath / d, vault_root))
        ]
        for fn in filenames:
            p = dpath / fn
            # Cheap string filters FIRST — no syscall for pruned extensions.
            if p.suffix.lower() not in walk_exts:
                continue
            rel = _safe_rel(p, vault_root)
            in_exclude = _matches_exclude(rel, exclude_globs)
            if in_exclude and p.suffix.lower() != ".md":
                continue  # non-.md in an exclude zone → prune (no keep-rescue)
            try:
                st = p.lstat()  # ONE stat per surviving candidate
            except OSError:
                continue
            if stat_mod.S_ISLNK(st.st_mode):
                continue  # symlinked target file refused
            if not stat_mod.S_ISREG(st.st_mode):
                continue
            out.append(Candidate(
                path=p, rel=rel, mtime=st.st_mtime,
                in_raw=rel == "_raw" or rel.startswith("_raw/"),
                in_exclude_zone=in_exclude,
            ))

    out.sort(key=lambda c: c.rel)
    return out


def classify_file(
    path: Path,
    *,
    vault_root: Path,
    config: SyncConfig,
    layout: LayoutConfig,
    in_raw: bool,
    in_exclude_zone: bool,
) -> Decision:
    """Classify a single discovered file into a `Decision`."""
    # Vault system files (per-vendor agent instructions CLAUDE.md/GEMINI.md,
    # WIKI_SCHEMA.md, index.md, log.md) are operating instructions / projections,
    # NOT knowledge — skip them, consistent with the indexer's `iter_pages`
    # (so a `wiki-sync scan .` over the vault root never upserts them).
    if path.name in SYSTEM_FILES:
        return Decision("skip", "system-file")
    name_lower = path.name.lower()
    ext = path.suffix.lower()
    convert_exts, text_exts, skip_exts = _ext_route_sets(config)

    # --- definitive non-`.md` skips (checked before the generic `.md` branch) ---
    if ext in skip_exts:
        return Decision("skip", "config-skip")
    if name_lower.endswith(".excalidraw.md") or name_lower.endswith(".excalidraw"):
        return Decision("skip", "excalidraw")
    if ext in _VIEW_ARTIFACT_EXTS:
        return Decision("skip", "canvas" if ext == ".canvas" else "bases-definition")

    # --- degenerate: a zero-byte file never ingests/converts/upserts (AC-11) ---
    try:
        size = path.stat().st_size
    except OSError:
        return Decision("skip", "stat-error")
    if size == 0:
        return Decision("skip", "empty-source")

    # --- extension front-stage (bead 06) ---
    if ext in convert_exts:
        converter = ext.lstrip(".")
        return Decision(
            "convert+ingest", f"convert:{converter}",
            converter=converter, staged_target=_staged_target(path, vault_root, ext),
        )
    if ext in text_exts:
        normalize = "vtt-detimestamp" if ext in _DETIMESTAMP_EXTS else None
        return Decision("ingest", "text-source", normalize=normalize)
    if ext == ".md":
        if size > WIKI_SYNC_MD_MAX_BYTES:
            return Decision("skip", "oversize-source")
        return _classify_md(
            path, vault_root=vault_root, config=config, layout=layout,
            in_raw=in_raw, in_exclude_zone=in_exclude_zone,
        )
    if ext in _BINARY_EXTS:
        return Decision("skip", "binary")
    return Decision("skip", "unknown-ext")


def _classify_md(
    path: Path,
    *,
    vault_root: Path,
    config: SyncConfig,
    layout: LayoutConfig,
    in_raw: bool,
    in_exclude_zone: bool,
) -> Decision:
    """The `.md` content path: tag precedence → view-sidecar → unmappable-type."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return Decision("skip", "read-error")
    fm, body, fm_unparseable = _parse_frontmatter(text)
    suffix = " (frontmatter-unparseable)" if fm_unparseable else ""
    tags = _routing_tags(fm, body, config.tag_namespace)

    # --- tag precedence: skip > raw > keep > default (bead 07) ---
    if "skip" in tags:
        return Decision("skip", "wiki/skip")
    if in_exclude_zone and "keep" not in tags:
        # only `#wiki/keep` rescues a `.md` from an excluded zone.
        return Decision("skip", "excluded-zone")
    if not body.strip():
        return Decision("skip", "empty-source")
    if in_raw or "raw" in tags:
        return Decision("ingest", "raw" + suffix)

    # --- generated-view sidecar (bead 08) ---
    view = _detect_view(fm, body, path)
    if view is not None:
        return Decision("skip", f"view:{view}")

    # --- unmappable-type predictor (layout-general, W-1; bead 09) ---
    glob_type = _matched_glob_type(_safe_rel(path, vault_root), layout)
    try:
        normalize_frontmatter(
            dict(fm), source_path=path,
            type_mapping=layout.type_mapping,
            path_type_fallback=layout.path_type_fallback,
            glob_type=glob_type,
        )
    except (UnmappedTypeError, TypeError, ValueError):
        # The classifier predicts whether `wiki-index-upsert` would accept the
        # note — ANY predictor fault means it would NOT, so skip rather than
        # raise (AC-11). A malformed `type:` (a YAML list/map → unhashable `in`
        # test) or a non-iterable `tags:` would otherwise crash the whole scan
        # with an uncaught TypeError (critic-logic HIGH).
        return Decision("skip", "unmappable-type" + suffix)
    return Decision("upsert", "ready-note" + suffix)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _staged_target(path: Path, vault_root: Path, ext: str) -> str:
    """`_raw/.staging/<slug(stem)>-<ext>.md` — the (non-walked) convert target.

    Distinct ext keeps same-stem `report.docx`/`report.pdf` from colliding
    (AC-12). An empty slug (pure-symbol/non-transliterable stem) falls back to a
    path-hash (SEC-N1) so the target is always a valid, deterministic name."""
    stem_slug = slugify(path.stem)
    if not stem_slug:
        rel = _safe_rel(path, vault_root)
        stem_slug = "sync-" + hashlib.sha256(rel.encode("utf-8")).hexdigest()[:8]
    return f"_raw/.staging/{stem_slug}-{ext.lstrip('.')}.md"


def _safe_rel(path: Path, vault_root: Path) -> str:
    try:
        return path.relative_to(vault_root).as_posix()
    except ValueError:
        return path.name


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str, bool]:
    """`(frontmatter_dict, body, unparseable)` — never raises (bead 09). A file
    with malformed frontmatter is treated as no-frontmatter (route by path)."""
    # Strip a leading UTF-8 BOM (Windows/office editors prepend it) so the `---`
    # frontmatter delimiter is recognised — mirrors the indexer's read path
    # (`wiki_ingest._frontmatter`); without it a valid note is mis-skipped as
    # `unmappable-type` (critic-logic MED, W-1 fidelity).
    if text.startswith("﻿"):
        text = text[1:]
    try:
        post = frontmatter.loads(text)
    except Exception:  # noqa: BLE001 — untrusted content; YAML/parse errors must not raise
        return {}, text, True
    md = post.metadata if isinstance(post.metadata, dict) else {}
    return md, post.content or "", False


def _routing_tags(fm: dict[str, Any], body: str, ns: str) -> set[str]:
    """The `{raw,skip,keep}` routing intents declared by frontmatter `tags:`
    (`<ns>/x` or `#<ns>/x`), the `<ns>:` field, or inline `#<ns>/x` body tags."""
    found: set[str] = set()
    vocab = {"raw", "skip", "keep"}

    raw_tags = fm.get("tags")
    if isinstance(raw_tags, str):
        raw_tags = [raw_tags]
    if isinstance(raw_tags, list):
        for t in raw_tags:
            if isinstance(t, str):
                v = t.lstrip("#")
                if v.startswith(ns + "/") and v[len(ns) + 1:] in vocab:
                    found.add(v[len(ns) + 1:])

    field_val = fm.get(ns)
    if isinstance(field_val, str) and field_val in vocab:
        found.add(field_val)

    # Inline `#<ns>/x` body tags — but NOT inside a fenced code block, so a
    # how-to doc that *documents* the tag (```\n#wiki/skip\n```) is not wrongly
    # routed (critic-logic LOW — over-flag / data-loss).
    for m in re.finditer(rf"(?<![\w/])#{re.escape(ns)}/(raw|skip|keep)\b",
                         _strip_fenced_blocks(body)):
        found.add(m.group(1))
    return found


def _strip_fenced_blocks(body: str) -> str:
    """Drop fenced code-block CONTENT (keep non-fence lines) so a tag mentioned
    inside a code example is not treated as a routing directive."""
    out: list[str] = []
    in_fence = False
    for line in body.split("\n"):
        if _FENCE_RE.match(line.lstrip()):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return "\n".join(out)


def _detect_view(fm: dict[str, Any], body: str, path: Path) -> str | None:
    """A generated-view sidecar kind, or None. RC-5 decision: we do NOT reuse the
    vendored `wiki_ingest._classify._count_md_structure` — it is `lru_cache`-keyed
    by `Path` (process-lifetime), which would return stale structure for a file
    re-written within one process (e.g. across test/scan re-runs), and it counts
    structure for primary-picking, not view-shape. A small local matcher is used.
    """
    if isinstance(fm, dict) and "database-plugin" in fm:
        return "dbfolder"  # DB Folder config sidecar — definitive
    kind = _only_a_view(body)
    if kind is not None:
        return kind
    # folder-note (stem == parent dir) with no material prose → navigation, skip.
    if path.stem == path.parent.name and not _has_material_prose(body):
        return "folder-note"
    return None


_FENCE_RE = re.compile(r"^(`{3,}|~{3,})(.*)$")


def _only_a_view(body: str) -> str | None:
    """Return the view-kind iff `body` is *essentially one fenced view block*
    (RC-4 / AC-2b): after dropping leading blanks + an optional single leading
    heading line, the remaining non-blank content is exactly one fenced block
    whose info-string ∈ {yaml:dbfolder, base, dataview, dataviewjs} with nothing
    material after it. A note that embeds such a block alongside prose → None
    (content, not a view)."""
    lines = body.split("\n")
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and lines[i].lstrip().startswith("#"):
        i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
    if i >= len(lines):
        return None
    m = _FENCE_RE.match(lines[i].lstrip())
    if not m:
        return None
    fence_marker = m.group(1)[0] * 3
    info = m.group(2).strip().lower()
    # find the closing fence
    j = i + 1
    while j < len(lines):
        ls = lines[j].lstrip()
        if ls.startswith(fence_marker) and set(ls.strip()) <= {m.group(1)[0]}:
            break
        j += 1
    else:
        return None  # unterminated fence → not a clean single view block
    for k in range(j + 1, len(lines)):
        if lines[k].strip():
            return None  # material content after the block → embedded, not only-a-view
    return _VIEW_INFO.get(info)


def _has_material_prose(body: str) -> bool:
    """Heuristic: any non-blank line OUTSIDE a fenced block, that is not a
    heading/list/quote/table row, and carries > 40 chars of real text (links
    stripped). Used to keep a prose-bearing folder-note from being over-flagged."""
    in_fence = False
    for line in body.split("\n"):
        s = line.strip()
        if not s:
            continue
        if _FENCE_RE.match(s):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if s[0] in "#>-*+|":
            continue
        stripped = re.sub(r"\[\[[^\]]*\]\]|\[[^\]]*\]\([^)]*\)|`[^`]*`", "", s).strip()
        # Conservative threshold (critic-logic LOW): over-flagging a real note is
        # data loss, so err toward DETECTING prose — a short-but-real sentence in
        # a terse folder-note keeps it out of the skip set.
        if len(stripped) > 25:
            return True
    return False


def _matched_glob_type(rel_posix: str, layout: LayoutConfig) -> str | None:
    """The literal `type` of the first `layout.paths[]` glob the file matches —
    the same `glob_type` `iter_pages`/the indexer feed `normalize_frontmatter`."""
    pp = PurePosixPath(rel_posix)
    for entry in layout.paths:
        try:
            if pp.full_match(entry.glob):
                return entry.type
        except ValueError:
            continue
    return None
