"""`wiki-import` — the unified construct path (TASK 039; generalizes TASK 038's
`wiki-import-article`, kept as a back-compat alias).

A Decision-17 CLI (no `import anthropic`; the orchestrator owns the REASON step) that
imports an external article / paper / thread / meeting transcript / finished summary
into ANY layout's vault, along two orthogonal axes: **content-type → which REASON harness**
(`prepare` detects `--kind` → the universal `summarizing-meetings` harness, or none) and
**layout (config) → where it files** (Karpathy `_sources/`+root `_concepts/` vs PARA
topic-folder+sibling `_concepts/`, via `resolve_layout_config` — one code path).

Two subcommands:
  * ``prepare`` — deterministically fetch+convert a source to ``_raw/<slug>.md``
    (dispatch to the html / pdf skills) and emit an envelope with the target
    project's ``known_concepts`` + ``existing_page_slugs`` so the orchestrator's
    translation/summary reuses existing concept names (the known-concepts
    discipline — the core fix vs. ad-hoc imports).
  * ``apply`` — take the orchestrator's structured note, assemble the PARA note
    (per-mode), sanitize entity names, guarantee verbatim quotes, run the
    collision guard, file concept pages via ``wiki-extract-concepts apply``, index
    the note, and emit a combined manifest.

Composition, not reinvention (NF-2): fetch via the external ``html``/``pdf``
skill binaries (shell-out); concept filing + indexing via the existing
``wiki-extract-concepts`` / ``wiki-index-upsert`` surfaces.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.wiki_index.config_loader import (
    ConfigValidationError,
    VaultRootNotFoundError,
    load_root_config,
)
from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout_config import (
    _apply_slug_strategy,
    derive_project_for_path,
    resolve_layout_config,
)
from scripts.wiki_index.security import PathTraversalError, validate_inside_vault
from scripts.wiki_skills._common import atomic_write_text, build_repo_config, emit
from scripts.wiki_skills.wiki_extract_concepts._validation import _is_valid_slug

from . import _context
from ._authoring import (
    _MAX_CANDIDATES,
    assemble_note,
    derive_candidates,
    name_is_filable,
    sanitize_name,
)
from ._detect import KINDS, detect_kind, harness_for
from ._errors import EXIT_BAD_ARG, EXIT_DEP_MISSING, EXIT_FETCH_FAILED, ImportArticleError
from ._fetch import _parse_frontmatter, dispatch_fetch, ensure_source_frontmatter

# kind → preferred note `type:`; layout-safe fallback to "summary" (mapped by every layout)
_KIND_NOTE_TYPE = {
    "meeting": "meeting-summary", "article": "article-summary",
    "paper": "article-summary", "thread": "article-summary", "summary": "summary",
}

# `skipped` reasons that mean a concept page the orchestrator INTENDED was lost and is
# RECOVERABLE (vs benign dedup/collision/layout skips). Surfaced LOUDLY in the apply
# envelope's `warnings` — one entry PER reason, each with reason-specific recovery advice —
# so a paraphrased/mis-sourced quote (or an over-cap tail) can't hide behind
# action="imported"/exit 0 (the TASK 042 silent-drop fix). Keys mirror the `skipped` reasons
# in `_authoring.derive_candidates` (keep in sync).
_LOSSY_DROP_HINTS = {
    "no-verbatim-quote": "each entity `quote` MUST be an exact substring of the authored "
                         "`body` — copy quotes FROM the body you write, not the raw source. "
                         "Re-run apply with corrected quotes to file them.",
    "max-candidates": f"the per-note concept cap ({_MAX_CANDIDATES}) was reached, so the tail "
                      "was dropped — re-running with the same entities drops the same tail; "
                      "trim the entity list or split the import to file them.",
}
_LOSSY_SKIP_REASONS = frozenset(_LOSSY_DROP_HINTS)

__version__ = "1.0"

_DEFAULT_HTML = "~/.claude/skills/html/scripts/html2md.py"  # `html` skill; html2md.py is the combined URL→md command
_DEFAULT_PDF_EXTRACT = "~/.claude/skills/pdf/scripts/pdf_extract.py"
_EXT_RE = re.compile(r"\.(md|markdown|txt|html?|pdf|aspx?)$", re.IGNORECASE)
# MINTING strategy for NEW slugs (the _raw filename + concept candidates): always a valid
# lowercase-kebab slug, decoupled from the vault's layout `slug_strategy` (karpathy's
# `identity` preserves source-FILENAME case — it is NOT for minting new concept slugs).
# Round-trips under both layouts: the concept file is named `<slug>.md`, so identity reads
# back the lowercase stem unchanged and preserve-unicode lowercases an already-lowercase stem.
_MINT_SLUG = "preserve-unicode"


def _mint_strategy(slug_strategy: str) -> str:
    """The keyspace to mint NEW slugs / re-slugify FS stems in for the collision guard.

    It MUST equal the indexer's keyspace (the layout's own `slug_strategy`) for every strategy
    that yields a valid lowercase-kebab slug (`transliterate`, `preserve-unicode`, `ascii-only`,
    + any future lowercase strategy) — else the guard compares a minted slug against a
    differently-keyed `pages.slug` and misses a real owner-page collision (eviction at reindex).
    Only `identity` preserves source-FILENAME case and so is NOT mint-valid; mint via `_MINT_SLUG`
    (preserve-unicode), which round-trips the already-lowercase `<slug>.md` stems wiki-import
    writes (karpathy byte-identity). A FUTURE case-preserving strategy must be added here too."""
    return _MINT_SLUG if slug_strategy == "identity" else slug_strategy


def _derive_slug(title: str | None, source: str, slug_strategy: str) -> str:
    base = (title or "").strip()
    if not base:
        base = source.rstrip("/").rsplit("/", 1)[-1].split("?", 1)[0]
    base = _EXT_RE.sub("", base)
    return _apply_slug_strategy(base, slug_strategy)


# --------------------------------------------------------------------------- prepare

def _resolve_vault_root(args: argparse.Namespace) -> Path:
    """Resolve --vault-root, emitting a clean INVALID_VAULT_ROOT envelope (via main's handler)
    instead of a raw `resolve(strict=True)` FileNotFoundError traceback (Decision-17)."""
    try:
        return Path(args.vault_root).resolve(strict=True)
    except FileNotFoundError:
        raise ImportArticleError(
            "INVALID_VAULT_ROOT",
            f"--vault-root {str(args.vault_root)!r} does not exist",
            exit_code=EXIT_BAD_ARG) from None


def _vault_language(vault_root: Path) -> str:
    """The rendered note language (WIKI_SCHEMA `language`), 'en' fallback. Guarded the SAME way
    resolve_layout_config is: a SCHEMALESS vault (pre-R-X1 / byte-identity karpathy, which
    resolve_layout_config supports by defaulting to karpathy) must NOT crash here — load_root_config
    raises VaultRootNotFoundError when WIKI_SCHEMA.md is absent, so fall back to 'en'."""
    try:
        return str(load_root_config(vault_root).get("language") or "en").lower()
    except (VaultRootNotFoundError, ConfigValidationError):
        return "en"


def prepare(args: argparse.Namespace) -> int:
    vault_root = _resolve_vault_root(args)
    cfg = build_repo_config(args.vault, vault_root=vault_root, db_path_flag=args.db_path)
    db_path = cfg.get("db_path")
    layout = resolve_layout_config(vault_root)
    slug_strategy = layout.slug_strategy
    # the REASON step must summarise INTO the vault's language (international — not hardcoded
    # RU); emitted in the envelope so the orchestrator knows the target language. en fallback.
    note_lang = _vault_language(vault_root)

    try:
        folder_abs = validate_inside_vault(vault_root / args.folder, vault_root)
    except PathTraversalError:
        return emit({"error": "INVALID_FOLDER",
                     "message": f"--folder {args.folder!r} escapes the vault root"},
                    exit_code=EXIT_BAD_ARG)
    except FileNotFoundError:
        # validate_inside_vault resolve(strict=True) → FileNotFoundError for a missing folder.
        # Refuse with a clean envelope (Decision-17), never a raw traceback. We auto-create our
        # OWN machinery subdirs (_raw/_sources/_concepts) but not the operator's topic folder —
        # so a typo can't silently spawn junk folders in a curated vault.
        return emit({"error": "INVALID_FOLDER",
                     "message": f"--folder {args.folder!r} does not exist in the vault; "
                                "create the target topic folder first"},
                    exit_code=EXIT_BAD_ARG)

    # 1. deterministic fetch (NO raw written on failure — R-3)
    try:
        result = dispatch_fetch(
            args.source,
            html_bin=args.html_bin,
            pdf_extract_bin=args.pdf_extract_bin,
            download_images=layout.import_images,   # config-driven, default ON
        )
    except ImportArticleError as e:
        return emit(e.envelope(), exit_code=e.exit_code)

    if not result.ok or not result.raw_text:
        return emit({
            "action": "fetch-failed",
            "error": "FETCH_FAILED",
            "source": args.source,
            "engine": result.engine,
            "upstream": result.error or {},
            "hint": "source unreachable/empty — file a needs-manual stub by hand.",
        }, exit_code=EXIT_FETCH_FAILED)

    # A successful image-bearing fetch leaves the html skill's temp dir alive (its `_attachments/`
    # is filed below); reclaim it on EVERY exit path, including the validation early-returns.
    _imgtmp = result.attachments_dir.parent if result.attachments_dir else None

    def _bad(env: dict[str, Any], code: int) -> int:
        if _imgtmp:
            shutil.rmtree(_imgtmp, ignore_errors=True)
        return emit(env, exit_code=code)

    # 2. slug + raw path (containment + slug validity — R-26). Mint via _MINT_SLUG so a
    # capitalized title under karpathy's `identity` strategy still yields a valid slug.
    slug = args.slug or _derive_slug(result.title, args.source, _MINT_SLUG)
    if not _is_valid_slug(slug, max_len=None):
        return _bad({"error": "INVALID_SLUG",
                     "message": f"derived slug {slug!r} is not a valid page slug; pass --slug",
                     "source": args.source}, EXIT_BAD_ARG)
    # _raw lives under the source-subdir tier for source_subdir layouts (course-tier karpathy
    # → Lessons/<Course>/_sources/_raw, matching where `apply` files the note); PARA → folder.
    try:
        note_dir = _note_dir(layout, vault_root, folder_abs)
        raw_dir = note_dir / "_raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_dir = validate_inside_vault(raw_dir, vault_root)
    except PathTraversalError:
        return _bad({"error": "INVALID_FOLDER",
                     "message": f"_raw under {args.folder!r} resolves outside the vault"},
                    EXIT_BAD_ARG)

    raw_path = raw_dir / f"{slug}.md"
    if raw_path.is_symlink():  # refuse a swapped-in symlink target (R-26 write posture)
        return _bad({"error": "REFUSED_SYMLINK",
                     "message": f"_raw/{slug}.md is a symlink; refusing to write through it"},
                    EXIT_BAD_ARG)
    # R-26: refuse a swapped-in `_attachments` DIR symlink BEFORE writing the raw, so a refused
    # import leaves NO partial artifact on disk; this guard covers both the image copy and the
    # GC below (either of which would otherwise write/unlink THROUGH the symlink).
    att_dst = raw_dir / "_attachments"
    if att_dst.is_symlink():
        return _bad({"error": "REFUSED_SYMLINK",
                     "message": "_raw/_attachments is a symlink; refusing to write through it"},
                    EXIT_BAD_ARG)
    # Guarantee the _raw carries a link to the original (PDFs/text dumps lack a frontmatter;
    # some captures lack `source:`) — inject `source:` from the import source if missing.
    raw_md = ensure_source_frontmatter(result.raw_text, args.source)
    raw_bytes = raw_md.encode("utf-8")
    source_hash = hashlib.sha256(raw_bytes).hexdigest()  # _raw hash → import idempotency ONLY
    n_images = 0
    # The html skill temp dir (`_imgtmp`) is reclaimed in the `finally` — the SINGLE owner for both
    # the success path AND any OSError from write_bytes/mkdir/copy2 (read-only vault, ENOSPC,
    # ENAMETOOLONG), which would otherwise propagate to main()'s catch-all and orphan it.
    try:
        raw_path.write_bytes(raw_bytes)
        # File downloaded images (image-import ON) into _raw/_attachments/ so the md's relative
        # `_attachments/<sha>` links resolve.
        if result.attachments_dir and result.attachments_dir.is_dir():
            att_dst.mkdir(exist_ok=True)
            for img in result.attachments_dir.iterdir():
                if img.is_file() and not (att_dst / img.name).is_symlink():
                    shutil.copy2(img, att_dst / img.name)
                    n_images += 1
        # Reclaim re-import orphans (folder-wide; safe) whenever the dir exists — including a
        # no-image re-import (import_images:false / no images this run) that must still GC stale
        # files left by a PRIOR image-bearing import.
        if att_dst.is_dir():
            _gc_attachments(raw_dir, att_dst)
    finally:
        if _imgtmp and _imgtmp.exists():
            shutil.rmtree(_imgtmp, ignore_errors=True)

    # 3. project + context (known_concepts + existing_page_slugs) — keyed to the dir the note
    # actually writes to (note_dir) and the candidate keyspace (mint), matching apply's guard.
    mint = _mint_strategy(slug_strategy)
    project = derive_project_for_path(note_dir / f"{slug}.md", vault_root)
    repo = make_repo(cfg)
    try:
        known = _context.known_concepts(repo, args.vault, vault_root)
    finally:
        repo.close()
    existing = _context.existing_page_slugs(
        db_path, args.vault, project, note_dir, slug_strategy=mint,
        source_subdir=layout.write.source_subdir)

    # content-type → REASON harness (R-2). `auto` detects; an explicit --kind overrides.
    if args.kind == "auto":
        fm = _parse_frontmatter(result.raw_text or "")
        kind, kind_conf = detect_kind(result.raw_text, args.source, fm)
    else:
        kind, kind_conf = args.kind, "explicit"

    return emit({
        "action": "prepared",
        "vault_id": args.vault,
        "raw_path": str(raw_path.relative_to(vault_root)),
        "folder": args.folder,
        "slug": slug,
        "project": project,
        "mode": args.mode,
        "language": note_lang,   # target language for the REASON summary (vault `language`)
        "kind": kind,
        "reason_harness": harness_for(kind),
        "kind_confidence": kind_conf,
        "title": result.title,
        "author": result.author,
        "date": result.date,
        "engine": result.engine,
        "source_hash": source_hash,
        "images": n_images,
        "known_concepts": known,
        "existing_page_slugs": existing,
    })


# --------------------------------------------------------------------------- apply



def _note_type(kind: str, layout: Any) -> str:
    """Per-kind note `type:`, layout-safe: fall back to `summary` when the preferred type
    isn't in this layout's type_mapping (e.g. karpathy has no `article-summary`). All FOUR
    built-in layouts map `summary` → db_type summary, so import lands cleanly on each; a
    CUSTOM layout that maps neither the preferred type nor `summary` yields a loud `partial`
    at index time (UnmappedTypeError → exit 6), never a silent mis-tag."""
    pref = _KIND_NOTE_TYPE.get(kind, "article-summary")
    return pref if pref in layout.type_mapping else "summary"


def _note_dir(layout: Any, vault_root: Path, folder_abs: Path) -> Path:
    """Layout-aware note target — config-driven (TASK 040 / ADR-007), no layout-name fork.
    `write.source_subdir` non-empty (karpathy `_sources`) → file under `<vault>/<source_subdir>/`;
    empty (PARA) → file in the given topic folder."""
    sub = layout.write.source_subdir
    if sub:
        # Nest `source_subdir` UNDER the operator's --folder so course-tier karpathy
        # (`Lessons/<Course>/_sources/`) is addressable — but when --folder already IS that
        # subdir (vault tier: `--folder _sources`) don't double it (`_sources/_sources`).
        # Byte-identity for vault-tier karpathy is preserved (folder_abs == vault_root/_sources).
        d = folder_abs if folder_abs.name == sub else folder_abs / sub
        # Containment check BEFORE mkdir (defense-in-depth: `write.source_subdir` is operator
        # config, already load-gated to a safe single segment — but never mkdir outside the
        # vault even if that gate were bypassed). resolve() normalizes `..` without needing
        # the dir to exist; validate_inside_vault (strict resolve) re-checks post-mkdir.
        if not d.resolve().is_relative_to(vault_root.resolve()):
            raise PathTraversalError(f"write.source_subdir {sub!r} escapes the vault root")
        d.mkdir(parents=True, exist_ok=True)
        return validate_inside_vault(d, vault_root)
    return folder_abs


def _layout_indexes_concepts(layout: Any, vault_root: Path, note_dir: Path) -> bool:
    """True iff a `_concepts/<slug>.md` page filed for a note in `note_dir` would be INDEXED
    (discovered by a path glob AND type-mappable) by this layout.

    The construct path files concept pages via wiki-extract-concepts; if the resolved layout
    can't index them, `wiki-reindex --full` can't rebuild that Class-A markdown (a Class A/B
    invariant breach → orphaned pages + dangling footer wikilinks). So a layout whose globs
    don't reach the sibling `_concepts/` (e.g. dev-project's single-level `tasks/*.md`) or that
    lacks a `concept` type_mapping (→ UnmappedTypeError, silently dropped at reindex) returns
    False here, and the caller files the summary note WITHOUT concept pages. Concept-capable
    layouts (karpathy, obsidian-personal, cybos) return True. Robust to future drop-in YAMLs."""
    from scripts.wiki_index.layout import CONCEPTS_SUBDIR
    from scripts.wiki_index.layout_config import derive_discovered_page
    if "concept" not in layout.type_mapping:
        return False
    sub = layout.write.source_subdir  # concepts dir mirrors wiki_extract_concepts._apply_write
    concepts_dir = (note_dir.parent if sub and note_dir.name == sub else note_dir) / CONCEPTS_SUBDIR
    probe = concepts_dir / "concept-probe.md"   # hypothetical (never written) — glob check only
    return derive_discovered_page(probe, vault_root, layout) is not None


_GC_MD_MAX_BYTES = 64 * 1024 * 1024  # per-_raw read ceiling (matches the fetch size cap)


def _gc_attachments(raw_dir: Path, att_dst: Path) -> None:
    """Drop `_attachments/` images referenced by NO `_raw/*.md` in this folder.

    `_attachments/` is shared per `_raw/` dir, so a re-import (changed/removed images) leaves
    orphans that grow unbounded. GC is FOLDER-WIDE (scan every `_raw/*.md`, not just the note
    just written) so a sibling note's referenced images are preserved. Same reference regex as
    `_fetch`'s prune (`_attachments/<basename>`). Best-effort: never raises into the caller.

    Memory is bounded — files are read ONE at a time (peak = one file), and a `_raw/*.md` over
    `_GC_MD_MAX_BYTES` ABORTS the GC entirely (we'd rather keep orphans than delete an image a
    too-large note might reference but we never fully read — correctness over reclamation)."""
    try:
        referenced: set[str] = set()
        for md in raw_dir.glob("*.md"):
            if md.is_file() and not md.is_symlink():
                if md.stat().st_size > _GC_MD_MAX_BYTES:
                    return  # can't safely reason about references → keep everything
                referenced.update(re.findall(r"_attachments/([^\s)\]]+)",
                                             md.read_text(encoding="utf-8", errors="replace")))
        for f in att_dst.iterdir():
            if f.is_file() and not f.is_symlink() and f.name not in referenced:
                f.unlink()
    except OSError:
        pass


_MAX_NOTE_BYTES = 32 * 1024 * 1024  # bounded read (a full translation > the 1 MiB candidates cap)


def _load_note_json(args: argparse.Namespace) -> dict[str, Any]:
    if args.note_stdin:
        data = sys.stdin.buffer.read(_MAX_NOTE_BYTES + 1)  # bounded — don't slurp unboundedly
        if len(data) > _MAX_NOTE_BYTES:
            raise ImportArticleError("NOTE_TOO_LARGE",
                f"note JSON exceeds {_MAX_NOTE_BYTES >> 20} MiB", exit_code=EXIT_BAD_ARG)
        raw = data.decode("utf-8", errors="replace")
    elif args.note_file:
        nf = Path(args.note_file)
        if nf.is_file() and nf.stat().st_size > _MAX_NOTE_BYTES:
            raise ImportArticleError("NOTE_TOO_LARGE",
                f"note file exceeds {_MAX_NOTE_BYTES >> 20} MiB", exit_code=EXIT_BAD_ARG)
        raw = nf.read_text(encoding="utf-8")
    else:
        raise ImportArticleError(
            "MISSING_NOTE", "pass --note-file or --note-stdin", exit_code=EXIT_BAD_ARG)
    try:
        note = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ImportArticleError("BAD_NOTE_JSON", f"note JSON is invalid: {e}",
                                 exit_code=EXIT_BAD_ARG) from e
    ents = note.get("entities") if isinstance(note, dict) else None
    bullets = note.get("summary_bullets") if isinstance(note, dict) else None
    # neutral field names (international): `title`/`body`; `title_ru`/`ru_body` accepted as
    # legacy back-compat (prefer the neutral name when both are present).
    _title = note.get("title") or note.get("title_ru") if isinstance(note, dict) else None
    _body = (note.get("body") if (isinstance(note, dict) and note.get("body") is not None)
             else (note.get("ru_body") if isinstance(note, dict) else None))
    if (not isinstance(note, dict)
            or not isinstance(_title, str) or not _title.strip()
            or not isinstance(ents, list)
            or not all(isinstance(e, dict) for e in ents)
            # consumed scalar/list field TYPES (else assemble/sanitize/strip crash with a raw
            # traceback, bypassing the one-JSON-envelope contract — Decision-17):
            or not all(isinstance(e.get("name", ""), str) for e in ents)
            or not all(e.get("quote") is None or isinstance(e.get("quote"), str) for e in ents)
            or (_body is not None and not isinstance(_body, str))
            or not isinstance(note.get("tldr", ""), str)
            or (bullets is not None
                and (not isinstance(bullets, list)
                     or not all(isinstance(b, str) for b in bullets)))
            # `tags` (also consumed by assemble_note) — a bare string would iterate per-CHAR
            # into garbage `tags: [c, r, y, p, t, o]`; require a list of strings:
            or (note.get("tags") is not None
                and (not isinstance(note.get("tags"), list)
                     or not all(isinstance(t, str) for t in note["tags"])))):
        raise ImportArticleError(
            "BAD_NOTE_JSON",
            "note needs a non-empty string title (or legacy title_ru), a list of object "
            "entities with string names + string-or-null quotes, string body/tldr (or legacy "
            "ru_body), string summary_bullets items, and a list-of-strings tags",
            exit_code=EXIT_BAD_ARG)
    return note


def _run_module(module: str, argv: list[str], *, stdin: str | None = None,
                ) -> tuple[int, dict[str, Any]]:
    """Invoke a sibling wiki-* CLI in-repo and capture its JSON envelope."""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", module, *argv],
            capture_output=True, text=True, input=stdin, timeout=300)
    except subprocess.TimeoutExpired:
        # a hung child must NOT crash apply() with a raw traceback — surface a clean
        # non-zero rc so the caller reports a `partial` JSON envelope (Decision-17).
        return 6, {"error": "SUBPROCESS_TIMEOUT", "module": module}
    env: dict[str, Any] = {}
    if proc.stdout.strip():
        try:
            env = json.loads(proc.stdout)
        except json.JSONDecodeError:
            env = {"_stdout": proc.stdout[:400], "_stderr": proc.stderr[:400]}
    elif proc.stderr.strip():
        env = {"_stderr": proc.stderr[:400]}
    return proc.returncode, env


def _index_note(vault: str, vault_root: Path, db_path: str | None,
                note_path: Path) -> tuple[int, dict[str, Any]]:
    argv = ["--vault", vault, "--vault-root", str(vault_root), "--source", str(note_path)]
    if db_path:
        argv += ["--db-path", db_path]
    return _run_module("scripts.wiki_skills.wiki_index_upsert", argv)


def _file_concepts(vault: str, vault_root: Path, db_path: str | None, source_page: str,
                   source_hash: str, candidates: list[dict[str, Any]],
                   ) -> tuple[int, dict[str, Any]]:
    argv = ["apply", "--vault", vault, "--vault-root", str(vault_root),
            "--source-page", source_page, "--source-hash", source_hash,
            "--candidates-stdin", "--ingest", "--orchestrator-id", "wiki-import"]
    if db_path:
        argv += ["--db-path", db_path]
    return _run_module("scripts.wiki_skills.wiki_extract_concepts", argv,
                       stdin=json.dumps(candidates, ensure_ascii=False))


def apply(args: argparse.Namespace) -> int:
    vault_root = _resolve_vault_root(args)
    cfg = build_repo_config(args.vault, vault_root=vault_root, db_path_flag=args.db_path)
    db_path = cfg.get("db_path")
    layout = resolve_layout_config(vault_root)
    slug_strategy = layout.slug_strategy
    # rendered note language = the vault's `language` (WIKI_SCHEMA), English fallback — the
    # project is international, so section headings/labels are NOT hardcoded to one locale.
    note_lang = _vault_language(vault_root)
    # Mint slugs in the SAME keyspace the indexer will record from the filename, so the
    # collision guards (self-collision / collides-existing-page) compare like-for-like.
    # mint in the layout's OWN keyspace (see _mint_strategy): a `transliterate`/`ascii-only`
    # layout MUST NOT mint preserve-unicode, else the guard compares the wrong keyspace and
    # evicts an owner page at reindex.
    mint = _mint_strategy(slug_strategy)

    try:
        folder_abs = validate_inside_vault(vault_root / args.folder, vault_root)
    except PathTraversalError:
        return emit({"error": "INVALID_FOLDER",
                     "message": f"--folder {args.folder!r} escapes the vault root"},
                    exit_code=EXIT_BAD_ARG)
    except FileNotFoundError:  # missing folder → clean envelope, never a raw traceback (D-17)
        return emit({"error": "INVALID_FOLDER",
                     "message": f"--folder {args.folder!r} does not exist in the vault; "
                                "run prepare first / create the target topic folder"},
                    exit_code=EXIT_BAD_ARG)

    note = _load_note_json(args)
    today = args.today or datetime.date.today().isoformat()
    note_type = _note_type(args.kind, layout)
    raw_rel = args.raw_rel  # required (see parser) — always prepare's real raw_path, never re-slugified
    # dedup (order-preserving): two entities with the same name must not double the footer link
    san_names = list(dict.fromkeys(
        n for n in (sanitize_name(e.get("name", "")) for e in note["entities"])
        if name_is_filable(n)))

    # Resolve the note's target dir ONCE (source_subdir layouts file under the subdir tier;
    # course-tier karpathy → Lessons/<Course>/_sources) — drives the collision-guard project +
    # FS scan AND the write path together, so they can never query a different partition.
    try:
        note_dir = _note_dir(layout, vault_root, folder_abs)
    except PathTraversalError:
        return emit({"error": "INVALID_FOLDER",
                     "message": "the layout's write.source_subdir escapes the vault root"},
                    exit_code=EXIT_BAD_ARG)

    # config-driven filename (TASK 040): `source_filename: slug` (karpathy `identity` → filename ==
    # the page slug) files as <minted-slug>.md (the minted slug MUST be valid — a title that
    # slugifies to "" would yield ".md"); `title` (PARA) → assemble_note derives from the title.
    slug_fname = None
    if layout.write.source_filename == "slug":
        # neutral-or-legacy title (same resolution as _load_note_json/assemble_note) — a
        # contract-conformant {title} note has NO title_ru, so a bare note["title_ru"] would
        # KeyError on karpathy (the only source_filename:slug layout). Already validated non-empty.
        _title = note.get("title") or note.get("title_ru") or ""
        _s = _apply_slug_strategy(_title, mint)
        if not _is_valid_slug(_s, max_len=None):
            return emit({"error": "INVALID_SLUG",
                         "message": f"title {_title!r} does not slugify to a valid "
                                    "slug-filename for this layout; rename it"},
                        exit_code=EXIT_BAD_ARG)
        slug_fname = f"{_s}.md"

    def _assemble(names: list[str]) -> tuple[str, str]:
        return assemble_note(
            note, mode=args.mode, raw_rel_basename=raw_rel,
            source_url=args.source_url or str(note.get("URL", "")),
            source_lang=args.source_lang, today=today, note_type=note_type,
            san_names=names, fname=slug_fname, mint_strategy=mint, lang=note_lang)

    # Build the note once (footer = every filable entity), then reconcile that footer
    # with what concept-filing will actually materialize (below).
    fname, note_text = _assemble(san_names)
    # minted slug (lowercase-kebab) — self-collision check + manifest; extract-concepts gets
    # the note's REL PATH as --source-page, so the indexed page slug is resolved downstream.
    # Stable across re-assembly: the filename derives from the title, not the entity set.
    note_slug = _apply_slug_strategy(Path(fname).stem, mint)

    # collision-guard input: round-tripped from prepare, else re-derived (always fresh)
    if args.existing_page_slugs:
        try:
            parsed = json.loads(args.existing_page_slugs)
        except json.JSONDecodeError:
            parsed = None
        # accept ONLY a JSON array of strings (a scalar would mis-build the guard set)
        existing = ([s for s in parsed if isinstance(s, str)]
                    if isinstance(parsed, list) else [])
    else:
        # query the partition the note ACTUALLY writes to (note_dir), in the candidate keyspace
        project = derive_project_for_path(note_dir / f"{note_slug}.md", vault_root)
        existing = _context.existing_page_slugs(
            db_path, args.vault, project, note_dir, slug_strategy=mint,
            source_subdir=layout.write.source_subdir)

    # Concept-filing GATE: only extract concept pages on a layout that can actually INDEX a
    # `_concepts/<slug>.md` page (else wiki-reindex --full can't rebuild them → orphaned pages
    # + dangling footer wikilinks, a Class A/B breach). A structured-doc layout like dev-project
    # files the summary note WITHOUT concepts; concept-graph layouts (karpathy/obsidian/cybos) do.
    concepts_indexable = _layout_indexes_concepts(layout, vault_root, note_dir)
    if concepts_indexable:
        candidates, skipped = derive_candidates(
            note["entities"], note_text, slug_strategy=mint,
            note_slug=note_slug, existing_page_slugs=existing)
    else:
        candidates = []
        skipped = [{"name": str(e.get("name", "")), "reason": "layout-no-concepts"}
                   for e in note["entities"] if isinstance(e, dict)]

    # Footer reconciliation (P3-8): the entity-index section must list ONLY entities
    # that resolve to a page — those filed now (candidates) plus those whose slug collides
    # with an EXISTING page (the link still resolves). Drop the rest (no-verbatim-quote / dup /
    # self-collision / over-cap) so the footer never carries a dangling `[[wikilink]]`. Rebuild
    # + re-derive only when the set actually shrank (clean notes stay byte-identical).
    # `candidates`/`skipped` from the derive above are AUTHORITATIVE — only the displayed
    # footer is rebuilt (NOT re-derived): re-deriving against the shrunk note_text would be
    # circular (an entity whose only support was the footer wikilink line would then drop).
    resolvable = {c["name"] for c in candidates} | {
        s["name"] for s in skipped if s.get("reason") == "collides-existing-page"}
    footer_names = [n for n in san_names if n in resolvable]
    if footer_names != san_names:
        fname, note_text = _assemble(footer_names)

    note_path = note_dir / fname   # note_dir resolved + validated above
    if note_path.is_symlink():  # refuse writing through a symlinked target (R-26)
        return emit({"error": "REFUSED_SYMLINK",
                     "message": f"{fname!r} is a symlink; refusing to write through it"},
                    exit_code=EXIT_BAD_ARG)
    atomic_write_text(note_path, note_text)  # os.replace → does not follow a symlink
    note_path = validate_inside_vault(note_path, vault_root)
    note_rel = str(note_path.relative_to(vault_root))
    # hash the ON-DISK bytes so the two-hash contract is newline-translation-proof
    note_hash = hashlib.sha256(note_path.read_bytes()).hexdigest()

    # the source note must be indexed BEFORE concept refs can attach to it
    idx_rc, idx_env = _index_note(args.vault, vault_root, db_path, note_path)
    cc_rc, cc_env = (0, {"created": 0, "note": "no candidates"})
    if candidates and idx_rc == 0:
        # --source-hash = FRESH hash of the just-written note body (NOT prepare's _raw hash)
        cc_rc, cc_env = _file_concepts(
            args.vault, vault_root, db_path, note_rel, note_hash, candidates)
    elif candidates:
        # indexing failed → the source note has no pages row, so concept refs can't
        # attach. Skip filing (avoid orphan _concepts/ pages) and report partial.
        cc_env = {"created": 0, "note": "skipped: source note indexing failed"}
    elif not concepts_indexable and note["entities"]:
        # intentional (not a failure): this layout can't index _concepts pages → note only.
        cc_env = {"created": 0, "note": "skipped: layout does not index _concepts pages"}

    ok = idx_rc == 0 and cc_rc == 0
    # Surface RECOVERABLE concept losses loudly (the note still imported, so exit stays 0 —
    # non-fatal-metadata precedent: wiki_merge `aliases_skipped` + wiki_init `hint`). A benign
    # dedup/collision skip stays quiet; only the _LOSSY_SKIP_REASONS warn — one entry PER reason
    # (homogeneous names + reason-specific recovery advice), so the hint never misdirects.
    warnings: list[dict[str, Any]] = []
    for reason in sorted({s["reason"] for s in skipped if s.get("reason") in _LOSSY_SKIP_REASONS}):
        warnings.append({
            "code": "CONCEPTS_DROPPED",
            "reason": reason,
            "names": [s["name"] for s in skipped if s.get("reason") == reason],
            "hint": f"Concept pages were NOT written ({reason}): {_LOSSY_DROP_HINTS[reason]}",
        })
    return emit({
        "action": "imported" if ok else "partial",
        "vault_id": args.vault,
        "note": note_rel,
        "slug": note_slug,
        "mode": args.mode,
        "note_hash": note_hash,
        "candidates": len(candidates),
        "skipped": skipped,
        "warnings": warnings,
        "index": idx_env,
        "concepts": cc_env,
    }, exit_code=0 if ok else EXIT_DEP_MISSING)


# --------------------------------------------------------------------------- CLI

def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--vault", required=True, help="Vault ID (registered in vaults table)")
    p.add_argument("--vault-root", required=True, type=Path,
                   help="Absolute path to the vault root")
    p.add_argument("--db-path", default=None, help="Override the index DB path")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wiki-import",
        description="Unified construct path: fetch+convert (prepare) → REASON → author+file (apply); content-type + layout from config.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("prepare", help="Fetch+convert a source; emit known_concepts context.")
    _add_common(pp)
    pp.add_argument("--source", required=True, help="A http(s) URL or a local file path")
    pp.add_argument("--folder", required=True,
                    help="Target folder, vault-relative (e.g. '05 - Materials/Crypto')")
    pp.add_argument("--mode", choices=("full", "summary", "thread"), default="full")
    pp.add_argument("--kind", choices=KINDS, default="auto",
                    help="content-type → REASON harness (auto-detected; reported in the envelope)")
    pp.add_argument("--slug", default=None, help="Override the _raw/<slug>.md filename slug")
    pp.add_argument("--html-bin", dest="html_bin", default=_DEFAULT_HTML,
                    help="path to the `html` skill combined command (default: the deployed symlink)")
    pp.add_argument("--pdf-extract-bin", default=_DEFAULT_PDF_EXTRACT)
    pp.set_defaults(func=prepare)

    ap = sub.add_parser("apply", help="Author the PARA note + file concepts + index.")
    _add_common(ap)
    ap.add_argument("--folder", required=True, help="Target PARA folder (as in prepare)")
    ap.add_argument("--mode", choices=("full", "summary", "thread"), default="full")
    ap.add_argument("--kind", choices=[k for k in KINDS if k != "auto"], default="article",
                    help="content-type from prepare; sets the note `type:` (layout-safe)")
    note_src = ap.add_mutually_exclusive_group()  # enforce the documented mutex
    note_src.add_argument("--note-file", default=None,
                          help="Path to the orchestrator's note JSON (mutex with --note-stdin)")
    note_src.add_argument("--note-stdin", action="store_true",
                          help="Read the orchestrator's note JSON from stdin")
    ap.add_argument("--existing-page-slugs", default=None,
                    help="JSON array of existing slugs (from prepare) for the collision guard")
    ap.add_argument("--source-url", default=None, help="Original source URL (for provenance)")
    ap.add_argument("--raw-rel", required=True,
                    help="Vault-rel path of the _raw original (use prepare's raw_path verbatim)")
    ap.add_argument("--source-lang", default="en")
    ap.add_argument("--today", default=None, help="ISO date stamp (default: today)")
    ap.set_defaults(func=apply)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except ImportArticleError as e:
        return emit(e.envelope(), exit_code=e.exit_code)
    except Exception as e:  # noqa: BLE001 — Decision-17 backstop: every CLI emits ONE JSON
        # envelope + a stable exit code, NEVER a raw traceback (e.g. make_repo on a malformed
        # --vault, or any unforeseen deep fault). Emit only the exception TYPE — never str(e),
        # which can leak resolved filesystem paths (CWE-209).
        return emit({"error": "INTERNAL_ERROR", "type": type(e).__name__,
                     "message": "unexpected internal error — check --vault / --vault-root / "
                                "--folder / --source"}, exit_code=EXIT_BAD_ARG)


if __name__ == "__main__":
    sys.exit(main())
