"""W2 (TASK 057) — vendor-independent folder inference for `wiki-import prepare`.

When `--folder` is omitted, `prepare` proposes a target folder instead of letting the
operator/model guess (the 004-import mis-filing). Signals, in order (ARCH §2.3.5):

1. **Series-stem inference (primary)** — derive a conservative series stem from the
   detected title, FTS-query the vault's own index for same-series sibling notes, and
   propose their (single) containing folder. Index + filesystem only: no running app,
   no vendor, no network (Decision-17; derive-don't-author).
2. **Active-note hint (secondary)** — `obsidian-active-note folder` when available;
   an OPTIONAL signal that degrades silently (ANY non-zero exit / absent binary /
   outside-vault → skipped), never a contract.
3. **Ask (fallback)** — the caller emits a typed `FOLDER_UNRESOLVED` with the ranked
   candidates instead of silently guessing.

This module never writes; the caller guarantees nothing lands in the vault before the
folder is confirmed (staging lives OUTSIDE the vault — Q-057-3).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from scripts.wiki_index.repository import IndexRepository

# How many FTS hits to consider as potential series siblings (bounded, cheap).
_SIBLING_SEARCH_LIMIT = 10
# Evidence cap in the proposal envelope (top sibling paths).
_EVIDENCE_MAX = 3
# Ranked-candidates cap on the unresolved path.
_CANDIDATES_MAX = 5
# Conservative stem floor (over-merge guard, spec Risk 1): a residual stem must keep
# BOTH ≥ this many characters AND ≥ 2 whitespace-separated words to be trusted.
_STEM_MIN_CHARS = 8
_STEM_MIN_WORDS = 2

# ONE trailing episode/index marker, with surrounding dash/colon/dot separators:
#   "… [004]" · "… (4)" · "… #4" · "… Episode 12" / "Part 3" / "выпуск 7" / "урок 2"
#   · a trailing bare number "… 003".
_EPISODE_MARKER_RE = re.compile(
    r"""[\s\-–—:.]*
        (?:
            \[\s*\d{1,4}\s*\]
          | \(\s*\d{1,4}\s*\)
          | \#\d{1,4}
          | (?:ep(?:isode)?|part|выпуск|серия|урок|занятие)\.?\s*№?\s*\d{1,4}
          | \d{1,4}
        )
        [\s\-–—:.]*$""",
    re.IGNORECASE | re.VERBOSE)

_INDEX_DIR = "00-Vault-Index"


@dataclass
class FolderInference:
    """Outcome of the inference chain — a proposal or a ranked ask."""

    folder: str | None = None
    """`--folder`-form vault-relative folder; None = unresolved."""

    basis: str | None = None
    """"series-sibling" | "active-note" | None."""

    confidence: str | None = None
    """"high" (series sibling) | "medium" (active-note hint) | None."""

    evidence: list[str] = field(default_factory=list)
    """Vault-relative sibling file_paths backing the proposal (top few)."""

    candidates: list[str] = field(default_factory=list)
    """Ranked distinct folders (ambiguous/unresolved path; may be empty)."""


def _norm(s: str) -> str:
    """Casefolded, whitespace-collapsed comparison key (Cyrillic-safe)."""
    return re.sub(r"\s+", " ", s).casefold().strip()


def series_stem(title: str | None) -> str | None:
    """Conservative series stem of `title`, or None when inference must not run.

    Strips ONE trailing episode/index marker; the residual (or the whole title when no
    marker matched) must clear the floor (≥ ``_STEM_MIN_CHARS`` chars AND ≥
    ``_STEM_MIN_WORDS`` words) — else None (over-merge guard: "Урок 12" or "Standup #42"
    must never seed a vault-wide match).
    """
    if not title or not title.strip():
        return None
    stem = _EPISODE_MARKER_RE.sub("", title.strip(), count=1).strip()
    if len(stem) < _STEM_MIN_CHARS or len(stem.split()) < _STEM_MIN_WORDS:
        return None
    return stem


def folder_for_hit(file_path: str, source_subdir: str) -> str | None:
    """Map a sibling hit's vault-relative ``file_path`` to its `--folder`-form folder.

    Strips ONE trailing ``source_subdir`` segment (karpathy course-tier
    ``Lessons/X/_sources/`` → ``Lessons/X``); a stripped-to-empty path yields the
    subdir itself (vault-tier ``--folder _sources``). Machinery paths — any segment
    starting with ``_`` (other than that one trailing source_subdir) or the
    ``00-Vault-Index`` tree — return None (a `_concepts/` page is not a sibling).
    """
    parts = list(PurePosixPath(file_path).parent.parts)
    for i, seg in enumerate(parts):
        is_trailing_subdir = bool(source_subdir) and i == len(parts) - 1 and seg == source_subdir
        if (seg.startswith("_") or seg == _INDEX_DIR) and not is_trailing_subdir:
            return None
    if source_subdir and parts and parts[-1] == source_subdir:
        parts = parts[:-1]
        if not parts:
            return source_subdir          # vault-tier karpathy: --folder _sources
    if not parts:
        return None                       # root-level note: no folder to propose
    return "/".join(parts)


def infer_folder(repo: IndexRepository, vault_id: str, title: str | None,
                 *, source_subdir: str) -> FolderInference:
    """Primary signal: series-sibling folder inference over the vault's own index.

    Read-only DAL consumer: FTS5-quotes the stem into
    ``repo.search_pages(query, vaults=[vault_id], limit=_SIBLING_SEARCH_LIMIT)``
    (hits are ``PageHit``; the page is at ``hit.page``, rank at ``hit.bm25_score``),
    keeps hits whose title OR filename stem starts with the stem, maps them through
    :func:`folder_for_hit`, and decides: exactly one distinct folder → high-confidence
    proposal with evidence; several → unresolved with ranked candidates; none/no stem →
    unresolved with empty candidates. Never raises on an FTS/DAL error — unresolved.
    """
    stem = series_stem(title)
    if stem is None:
        return FolderInference()
    fts_query = '"' + stem.replace('"', '""') + '"'   # FTS5 phrase, quote-doubled
    try:
        hits = repo.search_pages(fts_query, vaults=[vault_id],
                                 limit=_SIBLING_SEARCH_LIMIT)
    except Exception:  # noqa: BLE001 — inference is a best-effort guard: any FTS/DAL
        return FolderInference()  # fault degrades to "ask", never crashes prepare
    stem_n = _norm(stem)
    # sibling = (folder, file_path, bm25) — title OR filename stem startswith the stem
    siblings: list[tuple[str, str, float]] = []
    for hit in hits:
        page = hit.page
        if not (_norm(page.title or "").startswith(stem_n)
                or _norm(PurePosixPath(page.file_path).stem).startswith(stem_n)):
            continue
        folder = folder_for_hit(page.file_path, source_subdir)
        if folder is not None:
            siblings.append((folder, page.file_path, hit.bm25_score))
    if not siblings:
        return FolderInference()
    # rank folders: sibling count desc, then best (lowest) bm25
    by_folder: dict[str, list[tuple[str, float]]] = {}
    for folder, fp, score in siblings:
        by_folder.setdefault(folder, []).append((fp, score))
    ranked = sorted(by_folder,
                    key=lambda f: (-len(by_folder[f]), min(s for _, s in by_folder[f])))
    if len(ranked) == 1:
        folder = ranked[0]
        evidence = [fp for fp, _ in sorted(by_folder[folder], key=lambda e: e[1])]
        return FolderInference(folder=folder, basis="series-sibling", confidence="high",
                               evidence=evidence[:_EVIDENCE_MAX], candidates=[folder])
    return FolderInference(candidates=ranked[:_CANDIDATES_MAX])


def active_note_folder(vault_root: Path, *, timeout_s: int = 10) -> str | None:
    """Secondary hint: the focused Obsidian note's containing folder, or None.

    Shells out to ``obsidian-active-note folder --format json`` when the resolver is
    on PATH. OPTIONAL by construction: absent binary, ANY non-zero exit (3/4/5 are
    merely the illustrative unavailable family — no per-code allowlist), timeout,
    unparsable output, or a folder that does not resolve INSIDE ``vault_root`` all
    return None silently. Local subprocess only — never the network (H-6).
    """
    resolver = shutil.which("obsidian-active-note")
    if resolver is None:
        return None
    try:
        proc = subprocess.run([resolver, "folder", "--format", "json"],
                              capture_output=True, text=True, timeout=timeout_s)
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None
    if proc.returncode != 0:
        return None
    try:
        payload = json.loads(proc.stdout.strip() or "null")
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    # folder mode: `abs` = absolute folder, `path` = vault-relative ("" = vault root)
    folder_abs = str(payload.get("abs") or "")
    if not folder_abs:
        return None
    try:
        resolved = Path(folder_abs).resolve(strict=True)
        root = vault_root.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if resolved == root or not resolved.is_relative_to(root):
        return None      # a root folder is a whole-vault blast radius — never a silent hint
    if not resolved.is_dir():
        return None
    return resolved.relative_to(root).as_posix()
