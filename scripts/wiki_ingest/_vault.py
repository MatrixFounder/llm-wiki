"""F3-helper · Vault layout + two-tier discovery (TASK 015 + TASK 016).

`_peek_schema_version` + `find_vault_root` + `discover_courses` are the
TASK 016 additions; they skip symlinks (OVERLAP-5) and `find_vault_root`
refuses cross-filesystem traversal. Tested by `../tests/test__vault.py`.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from wiki_ingest._frontmatter import split_frontmatter
from wiki_ingest._markdown import _mask_code_fences
from wiki_ingest._safety import (
    EXIT_INVALID_VAULT_ID,
    _skip_symlink,
    die,
    read_text,
)


# Folder names use the Obsidian system-folder convention: a leading underscore
# sorts them at the top of the file tree and signals "vault meta-content,
# not user notes." Display labels in index.md stay human-readable
# (Sources / Concepts / Entities) — see SUBDIR_TO_DISPLAY below.
DEFAULT_SUBDIRS = ("_sources", "_concepts", "_entities")
SUBDIR_TO_KIND = {"_sources": "source", "_concepts": "concept", "_entities": "entity"}
SUBDIR_TO_DISPLAY = {"_sources": "Sources", "_concepts": "Concepts", "_entities": "Entities"}
SCHEMA_FILE = "WIKI_SCHEMA.md"
INDEX_FILE = "index.md"
LOG_FILE = "log.md"

# ASSETS_DIR resolves to `skills/wiki-ingest/assets/`. This file lives at
# `skills/wiki-ingest/scripts/wiki_ingest/_vault.py`, so we walk three
# parents up (`_vault.py` → `wiki_ingest/` → `scripts/` → `wiki-ingest/`).
ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"


def _walk_pages(vault: Path):
    """Yield every `.md` page in the vault, EXCLUDING symlinks.

    Symlinks are skipped to refuse exfiltration via a malicious vault entry
    like `_concepts/secrets.md -> /etc/passwd` or `_sources/x.md -> ~/.aws/credentials`.
    """
    for sub in DEFAULT_SUBDIRS:
        d = vault / sub
        if not d.is_dir():
            continue
        for md in sorted(d.glob("*.md")):
            if _skip_symlink(md):
                continue
            yield md
    for md in sorted(vault.glob("*.md")):
        if md.name in (INDEX_FILE, LOG_FILE, SCHEMA_FILE):
            continue
        if _skip_symlink(md):
            continue
        yield md


def load_vault_pages(vault: Path) -> dict:
    """Walk the vault and collect frontmatter from every .md page.

    Pages are keyed by filename stem (which IS unique on a case-sensitive
    filesystem), not by `title:` — two files with the same `title:` should
    both surface in `scan`/known-concepts. The displayed name carries the
    title separately so callers can render it.

    Skips symlinks — a malicious vault could contain
    `_concepts/secrets.md -> /etc/passwd`; following it would surface
    arbitrary user files in the agent's view of the wiki.
    """
    pages = {"concepts": {}, "entities": {}, "sources": {}, "other": []}
    for kind, subdir, bucket in (
        ("concept", "_concepts", "concepts"),
        ("entity", "_entities", "entities"),
        ("source", "_sources", "sources"),
    ):
        d = vault / subdir
        if not d.exists():
            continue
        for md in d.glob("*.md"):
            if _skip_symlink(md):
                continue
            fm, _ = split_frontmatter(read_text(md))
            title = fm.get("title") or md.stem
            pages[bucket][md.stem] = {
                "path": str(md.relative_to(vault)),
                "title": title,
                "frontmatter": fm,
            }
    # also scan root-level pages that aren't index/log/schema
    for md in vault.glob("*.md"):
        if md.name in (INDEX_FILE, LOG_FILE, SCHEMA_FILE):
            continue
        if _skip_symlink(md):
            continue
        fm, _ = split_frontmatter(read_text(md))
        pages["other"].append({
            "path": str(md.relative_to(vault)),
            "title": fm.get("title") or md.stem,
        })
    return pages


def ensure_schema(vault: Path) -> None:
    """Refuse to run mutating commands on a vault that lacks `WIKI_SCHEMA.md`.

    Exits with code 2 (the documented "missing schema" exit code) so callers
    can distinguish this from other failures.
    """
    if not (vault / SCHEMA_FILE).exists():
        die(f"{SCHEMA_FILE} not found in {vault}. Run `wiki_ops.py init {vault}` first.", code=2)


def load_asset(name: str) -> str:
    """Load a packaged template asset from `skills/wiki-ingest/assets/`.

    Fails closed via `die()` if the asset is missing — every bundled asset
    is required for the skill to function (e.g., `WIKI_SCHEMA.template.md`).
    """
    path = ASSETS_DIR / name
    if not path.exists():
        die(f"missing bundled asset: {path}")
    return path.read_text(encoding="utf-8")


_SCHEMA_PEEK_BYTES = 8192  # frontmatter rarely exceeds 200 bytes, but template
                            # comments / extended descriptions can push past 1 KiB.
                            # Logic-critic 2026-05-27 (TASK 017 vdd-multi):
                            # a 1024-byte cap could misclassify a 2.0 vault root
                            # as 1.x when frontmatter is long. 8 KiB is safely
                            # above any realistic frontmatter while staying tiny.


def _peek_schema_version(schema_path: Path) -> str | None:
    """`schema_version` from a `WIKI_SCHEMA.md` frontmatter, or None on any failure."""
    try:
        with open(schema_path, "rb") as f:
            head = f.read(_SCHEMA_PEEK_BYTES)
    except OSError:
        return None
    try:
        fm, _ = split_frontmatter(head.decode("utf-8", errors="replace"))
    except (ValueError, UnicodeError, KeyError):
        return None
    sv = fm.get("schema_version") if isinstance(fm, dict) else None
    return None if sv is None else str(sv).strip()


_VAULT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}[a-z0-9]$")


def read_vault_id(vault_root: Path) -> str | None:
    """`vault_id` slug from `vault_root/WIKI_SCHEMA.md` frontmatter (TASK 017 R3).

    "Emit, don't enforce" per architecture §2.4: returns the raw value
    when present, `None` when absent (schema-file missing, frontmatter
    has no `vault_id:` line, or read fails). Does NOT validate the
    pattern — caller chooses when to call `validate_vault_id_pattern`.

    Standalone wiki-ingest users see no behavioural change: they neither
    set the field nor demand strict mode, and the consumer-side index
    layer (`obsidian-llm-wiki`) is the only audience that requires it.
    """
    schema_path = vault_root / SCHEMA_FILE
    if not schema_path.is_file():
        return None
    try:
        content = read_text(schema_path)
    except (OSError, SystemExit):
        # SystemExit guards against `read_text` deciding to die() on a
        # symlinked schema. Absent / unreadable schema = "no vault_id".
        return None
    try:
        fm, _ = split_frontmatter(content)
    except (ValueError, UnicodeError, KeyError):
        return None
    value = fm.get("vault_id") if isinstance(fm, dict) else None
    if not isinstance(value, str):
        return None
    return value.strip()


def validate_vault_id_pattern(slug: str) -> None:
    """`die(code=EXIT_INVALID_VAULT_ID)` on a malformed `vault_id` (TASK 017 R3.3).

    Pattern (architecture §2.4): `^[a-z][a-z0-9-]{1,30}[a-z0-9]$`
    (length 3..32, lowercase ASCII, kebab-case, no leading/trailing
    dash). The `--` substring is rejected separately so the error
    message can be specific.

    A malformed slug would poison downstream consumers (filesystem,
    SQLite PRIMARY KEY, URL fragments), so this check fires whether
    the value came from frontmatter or from `--vault-id <slug>`.
    Returns `None` on valid input.
    """
    if not _VAULT_ID_RE.fullmatch(slug):
        die(f"INVALID_VAULT_ID: {slug!r} does not match {_VAULT_ID_RE.pattern}",
            code=EXIT_INVALID_VAULT_ID)
    if "--" in slug:
        die(f"INVALID_VAULT_ID: {slug!r} contains '--'",
            code=EXIT_INVALID_VAULT_ID)


def _walk_up_for_schema(ancestors: list[Path], start_idx: int,
                        start_dev: int) -> int:
    """Next ancestor with `WIKI_SCHEMA.md` from `start_idx`, or -1.

    Stops at filesystem boundary or symlinked ancestor (both = unreachable).
    """
    for i in range(start_idx, len(ancestors)):
        anc = ancestors[i]
        try:
            if os.stat(anc).st_dev != start_dev:
                return -1
        except OSError:
            return -1
        if _skip_symlink(anc):
            return -1
        if (anc / SCHEMA_FILE).is_file():
            return i
    return -1


def find_vault_root(start: Path) -> tuple[Path, Path | None]:
    """Walk UP from `start` to find `(course_root, vault_root_or_None)`.

    First schema-bearing ancestor = course root. Outer schema declaring
    `schema_version: 2.0` = vault root; anything else → `None` (single-
    course mode, R1.2 / R9.3). Refuses symlinked / cross-fs ancestors.
    `die(..., code=2)` if no schema found.

    Symlink discipline: walks the **un-resolved** absolute path; if an
    ancestor encountered BEFORE reaching the course root is a symlink,
    aborts. System-level symlinks above the course root (e.g. macOS
    `/var → /private/var`) are never inspected because the walk stops
    at the first schema match.

    Caller contract: `start` MUST be free of literal `..` segments.
    `start.absolute()` does NOT normalise `..`, and the parent-walk
    would produce nonsense paths. All in-tree callers pass either
    `Path(args.vault).resolve()` or a path produced by `discover_courses`
    (already resolved by `os.walk`), so this is the documented contract.
    """
    try:
        start_abs = start.absolute()
        start_dev = os.stat(start_abs).st_dev
    except OSError:
        die(f"vault not found from {start}", code=2)
        return Path(), None  # unreachable; satisfies type checker
    ancestors: list[Path] = []
    cur = start_abs if start_abs.is_dir() else start_abs.parent
    while True:
        ancestors.append(cur)
        if cur.parent == cur:
            break
        cur = cur.parent
    course_idx = _walk_up_for_schema(ancestors, 0, start_dev)
    if course_idx < 0:
        die(f"vault not found from {start}", code=2)
        return Path(), None  # unreachable
    course_root = ancestors[course_idx]
    outer_idx = _walk_up_for_schema(ancestors, course_idx + 1, start_dev)
    vault_root: Path | None = None
    if outer_idx >= 0:
        outer = ancestors[outer_idx]
        if _peek_schema_version(outer / SCHEMA_FILE) == "2.0":
            vault_root = outer
    return course_root, vault_root


def discover_courses(vault_root: Path) -> list[Path]:
    """Walk DOWN from `vault_root`, return descendant course roots (sorted).

    Course root = any dir with `WIKI_SCHEMA.md` declaring `schema_version: 1.x`.
    Vault root itself (`2.0`) excluded. Descends INTO matched dirs so nested
    courses (e.g. `Lessons/2026/Spring/Hermes/`) are also captured (A-M-4).
    `followlinks=False` + per-dir symlink filter enforce OVERLAP-5.
    `die(..., code=2)` if `vault_root` is not a v2.0 root.
    """
    root_schema = vault_root / SCHEMA_FILE
    if not root_schema.is_file():
        die(f"not a vault root: {vault_root} (no {SCHEMA_FILE})", code=2)
    if _peek_schema_version(root_schema) != "2.0":
        die(f"not a vault root: {vault_root} (schema_version != 2.0)", code=2)
    vault_root_resolved = vault_root.resolve()
    result: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(vault_root, followlinks=False):
        dirnames[:] = [d for d in dirnames
                       if not _skip_symlink(Path(dirpath) / d)]
        if SCHEMA_FILE not in filenames:
            continue
        cur = Path(dirpath)
        try:
            if cur.resolve() == vault_root_resolved:
                continue
        except OSError:
            continue
        sv = _peek_schema_version(cur / SCHEMA_FILE)
        if sv is not None and sv.startswith("1."):
            result.append(cur)
    result.sort(key=lambda p: str(p))
    return result


_TAIL_LOG_RE = re.compile(r"^## \[\d{4}-\d{2}-\d{2}\][^\n]*$", re.M | re.A)

# Read this much from the END of log.md to find recent entries. 64 KiB is
# generous: even an obnoxiously long event entry with hundreds of detail
# lines won't exceed ~4 KiB. 5 entries × 4 KiB = 20 KiB; pad to 64 for
# safety. The full-file fallback below kicks in if the regex finds <n
# entries in the tail window (P-L2).
_TAIL_LOG_WINDOW_BYTES = 64 * 1024


def tail_log(vault: Path, n: int) -> list[str]:
    """Return the last `n` `## [YYYY-MM-DD] …` heading lines from `log.md`.

    Code-fence aware: a `## [date]` heading inside a fenced example
    block is NOT surfaced as a real log entry (L-M6). The `[^\\n]`
    upper-bound on the line tail keeps the regex linear. ASCII-anchored
    `\\d{4}-\\d{2}-\\d{2}` rejects Unicode-digit `[date]` strings that
    would otherwise pass the bare `\\[` literal (S-L2).

    **P-L2 fast path**: for files larger than `_TAIL_LOG_WINDOW_BYTES`,
    seek to the last 64 KiB and search there first. If we find ≥ n entries
    in the tail window, return them without ever reading the full file
    (5 MB log → 64 KiB read instead of full 5 MB). Falls back to full-file
    read for short logs or when the window doesn't contain enough entries.
    """
    log = vault / LOG_FILE
    if not log.exists():
        return []

    # Fast path: seek to last 64 KiB on large logs.
    try:
        size = log.stat().st_size
    except OSError:
        size = 0
    if size > _TAIL_LOG_WINDOW_BYTES:
        try:
            with log.open("rb") as f:
                f.seek(-_TAIL_LOG_WINDOW_BYTES, 2)
                tail_bytes = f.read()
            # Truncate up to the first `\n` so we don't start mid-line and
            # accidentally splice a half-heading.
            nl_idx = tail_bytes.find(b"\n")
            if nl_idx >= 0:
                tail_bytes = tail_bytes[nl_idx + 1:]
            tail_text = tail_bytes.decode("utf-8", errors="replace")
            masked = _mask_code_fences(tail_text)
            matches = list(_TAIL_LOG_RE.finditer(masked))
            if len(matches) >= n:
                return [tail_text[m.start():m.end()] for m in matches][-n:]
            # else: window didn't have enough entries → fall through to full read
        except OSError:
            pass

    raw = read_text(log)
    masked = _mask_code_fences(raw)
    entries: list[str] = []
    for m in _TAIL_LOG_RE.finditer(masked):
        # use the ORIGINAL content's slice (offsets are preserved by masking)
        entries.append(raw[m.start():m.end()])
    return entries[-n:]
