"""Source-IO / path-resolution leaf for wiki-extract-concepts (TASK 016).

Dependency rule: imports ONLY stdlib + `._errors` + `._validation`
(for `_path_is_absolute` and `_is_valid_slug`) + `scripts.wiki_index.layout` +
`scripts.wiki_index.security`. No import from the facade (`__init__`) or
any other leaf. (TASK 037 adds a LAZY import of `scripts.wiki_index.layout_config`
inside the PARA branch, mirroring `_derive_source_project` — no new module-load dep.)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from scripts.wiki_index.layout import (
    CONCEPTS_SUBDIR,
    COURSE_TIER_DIR,
    ENTITIES_SUBDIR,
    QUERIES_SUBDIR,
    SOURCES_SUBDIR,
    VERIFICATIONS_SUBDIR,
)
from scripts.wiki_index.security import (
    PathTraversalError,
    validate_inside_vault,
)
from ._errors import ExtractionParseError
from ._validation import _path_is_absolute, _is_valid_slug


# TASK 037 (vdd-multi perf SEV-2 / R-26): dirs the `_all_concepts_dirs` sweep
# never descends — VCS/editor/trash + the reserved scratch dirs (`_raw`/`.staging`,
# matching obsidian-personal.yaml's ignore). None can hold a real `_concepts/`;
# pruning them bounds the walk on a large vault and skips untrusted/irrelevant trees.
_WALK_PRUNE_DIRS = frozenset({".git", ".obsidian", ".trash", "_raw", ".staging"})

# M-3 (TASK 003 v3.1): DoS protection on prepare's sha256+read pipeline.
# Stat-checks st_size BEFORE read_text to bound memory. 10 MiB matches the
# existing validate_manifest body cap pattern.
_MAX_SOURCE_BODY_BYTES = 10_485_760  # 10 MiB

# H-5 / H-6 (TASK 003 v3.1 / 003-v3-03): DoS protection on candidates input
# (file or stdin). Capped BEFORE any JSON parse so a 5 GB payload cannot
# OOM the interpreter. Risk R-6 mitigation: stdin read uses cap+1 bytes
# so we never accumulate beyond the limit even if the producer streams.
_MAX_CANDIDATES_BYTES = 1_048_576  # 1 MiB


class _FileTooLargeError(OSError):
    """Raised by `_read_file_bounded` when fstat shows size > cap."""


def _read_file_bounded(path: Path, cap_bytes: int) -> bytes:
    """Open `path` with O_NOFOLLOW, fstat-check size, read up to cap+1 bytes.

    M-3 / M-5: closes the TOCTOU between `Path.stat().st_size` and a
    subsequent `Path.read_bytes()` AND defends against symlink-swap
    races (O_NOFOLLOW → ELOOP if the path became a symlink after the
    earlier resolve). The fstat-then-bounded-read pattern guarantees
    we never accumulate more than `cap_bytes + 1` bytes from the FD.
    Raises:
      - _FileTooLargeError if fstat shows size > cap OR the read
        produced more than cap bytes.
      - OSError on ELOOP / ENOENT / EACCES (caller maps to envelope).
    """
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        if st.st_size > cap_bytes:
            raise _FileTooLargeError(
                f"file size {st.st_size} > cap {cap_bytes}"
            )
        data = os.read(fd, cap_bytes + 1)
        if len(data) > cap_bytes:
            raise _FileTooLargeError(
                f"read returned > cap {cap_bytes} bytes (TOCTOU growth)"
            )
        return data
    finally:
        os.close(fd)


def _derive_source_project(source_path: Path, vault_root: Path) -> str:
    """Derive the `pages.project` column value for `source_path`.

    TASK 012 / architecture-review C1: delegates to the shared, config-driven
    `layout_config.derive_project_for_path` so the apply-side project matches what
    the reindexer (`iter_pages`) records — the `page_entity_refs` FK on
    `(vault_id, page_slug, page_project) → pages(vault_id, slug, project)`
    requires the two paths to agree. For a Karpathy vault this yields the same
    two-tier result as before (vault-tier → `VAULT_TIER_PROJECT`; course-tier →
    slugified course); for dev/obsidian layouts it follows the layout config
    (previously this hardcoded the Karpathy two-tier walk and would have drifted).
    """
    from scripts.wiki_index.layout_config import derive_project_for_path

    return derive_project_for_path(source_path, vault_root)


def _all_concepts_dirs(vault_root: Path) -> list[Path]:
    """Enumerate every `_concepts/` directory present in `vault_root`.

    TASK 037: generalised from the Karpathy vault-/course-tier scan to a full
    recursive sweep, so PARA layouts (obsidian-personal) — where each thematic
    folder owns a `<folder>/_concepts/` sibling, at arbitrary depth — are covered
    too. Matches only directories named exactly ``CONCEPTS_SUBDIR``; the previous
    vault-tier + `Lessons/<Course>/_concepts/` set is a strict subset.

    Uses ``os.walk(followlinks=False)`` (NOT ``Path.rglob``, which descends
    symlinked dirs) and skips a `_concepts` that is itself a symlink — so a
    symlink loop cannot hang `prepare` and a symlink pointing outside the vault is
    never scanned (R-26). PRUNES system/scratch dirs in-place (`dirnames[:]`) so
    the sweep does not descend `.git`/`.obsidian`/`.trash`/`_raw`/`.staging` — they
    never hold a real `_concepts/`, and skipping them both bounds the walk cost on
    a large vault (vdd-multi perf SEV-2) and avoids reading irrelevant/untrusted
    trees (R-26). Returns existing real dirs, sorted for deterministic
    `set[slug]` construction by callers.
    """
    found: list[Path] = []
    for dirpath, dirnames, _files in os.walk(vault_root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in _WALK_PRUNE_DIRS]
        if CONCEPTS_SUBDIR in dirnames:
            candidate = Path(dirpath) / CONCEPTS_SUBDIR
            if not candidate.is_symlink():
                found.append(candidate)
    return sorted(found)


def _resolve_source_inside_sources(
    src_page: str, vault_root: Path,
) -> dict[str, Any] | tuple[Path, str]:
    """Resolve `--source-page` to a real path inside SOME `_sources/`.

    Returns either an error envelope `dict` (caller emits at exit 2) or
    a `(resolved_path, source_slug)` tuple on success.

    Supports both layouts:
    - vault-tier:  `<vault_root>/_sources/<slug>.md`
    - course-tier: `<vault_root>/Lessons/<Course>/_sources/<slug>.md`
      (per `layout.py::COURSE_TIER_DIR` — the Karpathy pattern; real
      operator vaults like `trade-agents` use this exclusively).

    Slug-form lookup tries vault-tier first, then globs course-tier.
    Ambiguous matches (same slug under two different `_sources/`) yield
    `AMBIGUOUS_SOURCE_SLUG` so the operator passes the full path instead.

    TASK 037 — two layout families:
    - Karpathy (`_sources/`-nesting): the resolved file lives directly under a
      `_sources/` dir; slug = file stem (byte-identical to pre-037).
    - PARA (obsidian-personal, etc.): the content note lives in its own folder.
      It is accepted, BUT (H-1 anti-loop) NEVER from a generated dir
      (`_concepts/_entities/_queries/_verifications/`) — extraction must not feed
      its own output back in — and its slug is derived via the vault's LAYOUT
      slug_strategy (so it equals `pages.slug`, which the `page_entity_refs` FK
      and inbound `[[Wikilink]]` ref-targets both key on).
    """
    # Slug-form search: try every `_sources/<slug>.md` under the vault.
    # Vault-tier first (deterministic), course-tier glob second.
    candidate_path: Path | None = None
    vault_tier = vault_root / SOURCES_SUBDIR / f"{src_page}.md"
    if vault_tier.is_file():
        candidate_path = vault_tier
    else:
        course_tier_root = vault_root / COURSE_TIER_DIR
        if course_tier_root.is_dir():
            course_matches = sorted(
                course_tier_root.glob(f"*/{SOURCES_SUBDIR}/{src_page}.md")
            )
            course_matches = [p for p in course_matches if p.is_file()]
            if len(course_matches) > 1:
                rels = [str(p.relative_to(vault_root)) for p in course_matches]
                return {
                    "error": "AMBIGUOUS_SOURCE_SLUG",
                    "reason": (f"slug {src_page!r} matches multiple "
                               f"_sources/ entries: {rels}. Pass the full "
                               "vault-relative path instead of the slug."),
                }
            if course_matches:
                candidate_path = course_matches[0]
    # Fall back to treating `src_page` as a vault-relative path verbatim.
    if candidate_path is None:
        candidate_path = vault_root / src_page

    try:
        source_path = candidate_path.resolve(strict=True)
        validate_inside_vault(source_path, vault_root)
    except (FileNotFoundError, PathTraversalError):
        # M-2 / CWE-209: do NOT interpolate the exception — both
        # FileNotFoundError and PathTraversalError stringify the ABSOLUTE
        # resolved path / vault root, leaking the operator's filesystem
        # layout into the envelope (reachable from batch entries too). Echo
        # only the operator-supplied slug.
        return {
            "error": "SOURCE_NOT_FOUND",
            "reason": (f"source-page {src_page!r} not found inside the "
                       "vault's _sources/ (missing, or resolves outside "
                       "the vault root)"),
        }

    # Karpathy (and any `_sources/`-nesting layout): unchanged contract — the
    # resolved file lives directly under a `_sources/` dir; slug = file stem,
    # validated lowercase kebab (now Unicode-aware via `_is_valid_slug`).
    # Byte-identical to pre-TASK-037 for ASCII stems.
    if source_path.parent.name == SOURCES_SUBDIR:
        source_slug = source_path.stem
        # max_len=None: the source page already exists on disk; its slug length
        # is the indexer's business, not a reason to refuse extraction.
        if not _is_valid_slug(source_slug, max_len=None):
            return {
                "error": "INVALID_SOURCE_SLUG",
                "reason": (f"source-page filename {source_slug!r} does not "
                           "yield a valid slug (lowercase Unicode word-chars "
                           "+ hyphens, no dots/seps). Rename the file or pass "
                           "--source-page with the canonical slug."),
            }
        return source_path, source_slug

    # TASK 037 — PARA / non-`_sources/` layouts (e.g. obsidian-personal).
    # (1) H-1 anti-loop: REFUSE generated pages (`_concepts/_entities/`
    #     `_queries/_verifications/`) — replaces the old blanket
    #     `parent != _sources` reject, which also (over-broadly) blocked PARA.
    # casefold both sides: macOS (APFS) / Windows are case-insensitive, so a
    # `_Concepts/` dir is the same dir as `_concepts/` to the OS — the anti-loop
    # guard must not be defeated by non-canonical casing.
    rel_parts = {p.casefold() for p in source_path.relative_to(vault_root).parts}
    _generated = {s.casefold() for s in (CONCEPTS_SUBDIR, ENTITIES_SUBDIR,
                                         QUERIES_SUBDIR, VERIFICATIONS_SUBDIR)}
    if _generated.intersection(rel_parts):
        return {
            "error": "INVALID_SOURCE_PATH",
            "reason": (f"source-page {src_page!r} resolves inside a generated "
                       "directory (_concepts/_entities/_queries/"
                       "_verifications); extraction refuses to run on its own "
                       "output (H-1 anti-loop guard)."),
        }
    # (2) layout-derived slug (lazy import mirrors `_derive_source_project`),
    #     so it equals `pages.slug` → page_entity_refs FK + inbound wikilink
    #     ref-targets resolve.
    from scripts.wiki_index.layout_config import (
        derive_discovered_page,
        resolve_layout_config,
    )
    disc = derive_discovered_page(
        source_path, vault_root, resolve_layout_config(vault_root),
    )
    if disc is None:
        return {
            "error": "INVALID_SOURCE_PATH",
            "reason": (f"source-page {src_page!r} is not an indexable page "
                       "under the vault's layout (matched no path rule)."),
        }
    source_slug = disc.slug
    # max_len=None: `disc.slug` IS the indexed `pages.slug` (slug_strategy output,
    # uncapped) — accept whatever the indexer would record so a long-titled PARA
    # note stays extractable (it must equal pages.slug for the refs FK).
    if not _is_valid_slug(source_slug, max_len=None):
        return {
            "error": "INVALID_SOURCE_SLUG",
            "reason": (f"layout-derived slug {source_slug!r} is not a valid "
                       "slug (lowercase Unicode word-chars + hyphens)."),
        }
    return source_path, source_slug


def _load_candidates(
    args: argparse.Namespace, vault_root: Path,
) -> list[Any]:
    """Load + cap + path-validate + parse the candidates JSON payload.

    Encapsulates the four `apply()` failure modes that fire BEFORE any
    schema validation:

      - `CANDIDATES_TOO_LARGE` (exit 4, H-6 / R-6) — stdin or file payload
        exceeds `_MAX_CANDIDATES_BYTES`. For stdin we read cap+1 bytes via
        `sys.stdin.buffer.read(...)` so the cap holds even under streaming.
      - `INVALID_CANDIDATES_PATH` (exit 2, H-5) — `--candidates-file` does
        not exist OR resolves to a location outside the vault root. Envelope
        emits the operator-supplied path STRING (never the file contents).
      - `EXTRACTION_PARSE_ERROR` (exit 4) — JSON decode error. Envelope
        emits the SDK-style `at line N column M` locator, never the
        offending byte stream (CWE-117 invariant).

    All three are raised as `ExtractionParseError` with `.error` populated
    so the apply() caller can map straight into a JSON envelope.
    """
    if args.candidates_stdin:
        # Risk R-6 mitigation: bound the read so a malicious producer
        # streaming one byte at a time cannot drive memory growth past
        # the cap. cap+1 bytes lets us detect overflow with one check.
        data = sys.stdin.buffer.read(_MAX_CANDIDATES_BYTES + 1)
        if len(data) > _MAX_CANDIDATES_BYTES:
            raise ExtractionParseError(
                "candidates stdin payload exceeds size cap",
                error="CANDIDATES_TOO_LARGE",
                field=None,
                reason=(f"stdin payload > {_MAX_CANDIDATES_BYTES} bytes "
                        "(1 MiB cap)"),
            )
    else:
        candidates_file = args.candidates_file
        # H-5 / M-6 (cross-platform): path-validate BEFORE any read. Both
        # FileNotFoundError and PathTraversalError map to
        # INVALID_CANDIDATES_PATH so the envelope never discloses on-disk
        # existence outside the vault. If the operator passed a relative
        # path, resolve it against vault_root (instead of CWD which would
        # produce inconsistent envelopes across operator shells).
        if not _path_is_absolute(candidates_file):
            candidates_file = vault_root / candidates_file
        try:
            resolved = validate_inside_vault(candidates_file, vault_root)
        except (FileNotFoundError, PathTraversalError):
            raise ExtractionParseError(
                "candidates file is not inside vault root",
                error="INVALID_CANDIDATES_PATH",
                field=None,
                reason=(f"--candidates-file {str(candidates_file)!r} is "
                        "missing or outside --vault-root"),
            ) from None
        # H-2: FIFO/device/socket bypasses stat-cap (st_size=0 for
        # FIFOs/char devices); reject anything that isn't a regular file.
        # M-3/M-5: open the file with O_NOFOLLOW + read at most cap+1
        # bytes from THAT FD so a TOCTOU swap between stat and read
        # cannot exceed the cap. The fstat-then-bounded-read pattern
        # closes both the FIFO bypass and the swap race.
        if not resolved.is_file():
            raise ExtractionParseError(
                "candidates file is not a regular file",
                error="INVALID_CANDIDATES_PATH",
                field=None,
                reason=(f"--candidates-file {str(candidates_file)!r} is "
                        "not a regular file (FIFOs/devices/sockets "
                        "rejected; H-2 bypass guard)"),
            )
        try:
            fd = os.open(resolved, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError:
            # ELOOP if target became a symlink between is_file() and open;
            # EACCES / ENOENT on race. All map to INVALID_CANDIDATES_PATH.
            raise ExtractionParseError(
                "candidates file open failed",
                error="INVALID_CANDIDATES_PATH",
                field=None,
                reason=(f"--candidates-file {str(candidates_file)!r} "
                        "could not be opened (possible symlink-swap race)"),
            ) from None
        try:
            data = os.read(fd, _MAX_CANDIDATES_BYTES + 1)
            if len(data) > _MAX_CANDIDATES_BYTES:
                raise ExtractionParseError(
                    "candidates file exceeds size cap",
                    error="CANDIDATES_TOO_LARGE",
                    field=None,
                    reason=(f"--candidates-file size > "
                            f"{_MAX_CANDIDATES_BYTES} bytes (1 MiB cap)"),
                )
        finally:
            os.close(fd)

    try:
        parsed = json.loads(data.decode("utf-8"))
    except json.JSONDecodeError as e:
        # CWE-117: never echo the raw payload — only the SDK locator.
        raise ExtractionParseError(
            "candidates payload is not valid JSON",
            error="EXTRACTION_PARSE_ERROR",
            field=None,
            reason=f"JSON decode failed at line {e.lineno} column {e.colno}",
        ) from None
    except UnicodeDecodeError:
        raise ExtractionParseError(
            "candidates payload is not valid UTF-8",
            error="EXTRACTION_PARSE_ERROR",
            field=None,
            reason="payload bytes are not decodable as UTF-8",
        ) from None
    if not isinstance(parsed, list):
        raise ExtractionParseError(
            "candidates payload top-level shape is not a JSON array",
            error="EXTRACTION_PARSE_ERROR",
            field=None,
            reason=(f"top-level JSON is {type(parsed).__name__}, "
                    "expected array"),
        )
    return parsed
