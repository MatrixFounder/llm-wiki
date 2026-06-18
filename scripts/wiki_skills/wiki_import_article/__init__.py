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
    (dispatch to the html2md / pdf skills) and emit an envelope with the target
    project's ``known_concepts`` + ``existing_page_slugs`` so the orchestrator's
    translation/summary reuses existing concept names (the known-concepts
    discipline — the core fix vs. ad-hoc imports).
  * ``apply`` — take the orchestrator's structured note, assemble the PARA note
    (per-mode), sanitize entity names, guarantee verbatim quotes, run the
    collision guard, file concept pages via ``wiki-extract-concepts apply``, index
    the note, and emit a combined manifest.

Composition, not reinvention (NF-2): fetch via the external ``html2md``/``pdf``
skill binaries (shell-out); concept filing + indexing via the existing
``wiki-extract-concepts`` / ``wiki-index-upsert`` surfaces.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout_config import (
    _apply_slug_strategy,
    derive_project_for_path,
    resolve_alias,
    resolve_layout_config,
)
from scripts.wiki_index.security import PathTraversalError, validate_inside_vault
from scripts.wiki_skills._common import atomic_write_text, build_repo_config, emit
from scripts.wiki_skills.wiki_extract_concepts._validation import _is_valid_slug

from . import _context
from ._authoring import (
    assemble_note,
    derive_candidates,
    name_is_filable,
    sanitize_name,
)
from ._detect import KINDS, detect_kind, harness_for
from ._errors import EXIT_BAD_ARG, EXIT_DEP_MISSING, EXIT_FETCH_FAILED, ImportArticleError
from ._fetch import _parse_frontmatter, dispatch_fetch

# kind → preferred note `type:`; layout-safe fallback to "summary" (mapped by every layout)
_KIND_NOTE_TYPE = {
    "meeting": "meeting-summary", "article": "article-summary",
    "paper": "article-summary", "thread": "article-summary", "summary": "summary",
}

__version__ = "1.0"

_DEFAULT_HTML2MD = "~/.claude/skills/html2md/scripts/html2md.py"
_DEFAULT_PDF_EXTRACT = "~/.claude/skills/pdf/scripts/pdf_extract.py"
_EXT_RE = re.compile(r"\.(md|markdown|txt|html?|pdf|aspx?)$", re.IGNORECASE)
# MINTING strategy for NEW slugs (the _raw filename + concept candidates): always a valid
# lowercase-kebab slug, decoupled from the vault's layout `slug_strategy` (karpathy's
# `identity` preserves source-FILENAME case — it is NOT for minting new concept slugs).
# Round-trips under both layouts: the concept file is named `<slug>.md`, so identity reads
# back the lowercase stem unchanged and preserve-unicode lowercases an already-lowercase stem.
_MINT_SLUG = "preserve-unicode"


def _derive_slug(title: str | None, source: str, slug_strategy: str) -> str:
    base = (title or "").strip()
    if not base:
        base = source.rstrip("/").rsplit("/", 1)[-1].split("?", 1)[0]
    base = _EXT_RE.sub("", base)
    return _apply_slug_strategy(base, slug_strategy)


# --------------------------------------------------------------------------- prepare

def prepare(args: argparse.Namespace) -> int:
    vault_root = args.vault_root.resolve(strict=True)
    cfg = build_repo_config(args.vault, vault_root=vault_root, db_path_flag=args.db_path)
    db_path = cfg.get("db_path")
    layout = resolve_layout_config(vault_root)
    slug_strategy = layout.slug_strategy

    try:
        folder_abs = validate_inside_vault(vault_root / args.folder, vault_root)
    except PathTraversalError:
        return emit({"error": "INVALID_FOLDER",
                     "message": f"--folder {args.folder!r} escapes the vault root"},
                    exit_code=EXIT_BAD_ARG)

    # 1. deterministic fetch (NO raw written on failure — R-3)
    try:
        result = dispatch_fetch(
            args.source,
            html2md_bin=args.html2md_bin,
            pdf_extract_bin=args.pdf_extract_bin,
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

    # 2. slug + raw path (containment + slug validity — R-26). Mint via _MINT_SLUG so a
    # capitalized title under karpathy's `identity` strategy still yields a valid slug.
    slug = args.slug or _derive_slug(result.title, args.source, _MINT_SLUG)
    if not _is_valid_slug(slug, max_len=None):
        return emit({"error": "INVALID_SLUG",
                     "message": f"derived slug {slug!r} is not a valid page slug; pass --slug",
                     "source": args.source}, exit_code=EXIT_BAD_ARG)
    # _is_valid_slug already forbids separators / leading dot, so `<slug>.md` cannot
    # traverse; we still route the (now-existing) _raw dir through R-26 for defense.
    raw_dir = folder_abs / "_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    try:
        raw_dir = validate_inside_vault(raw_dir, vault_root)
    except PathTraversalError:
        return emit({"error": "INVALID_FOLDER",
                     "message": f"_raw under {args.folder!r} resolves outside the vault"},
                    exit_code=EXIT_BAD_ARG)

    raw_path = raw_dir / f"{slug}.md"
    if raw_path.is_symlink():  # refuse a swapped-in symlink target (R-26 write posture)
        return emit({"error": "REFUSED_SYMLINK",
                     "message": f"_raw/{slug}.md is a symlink; refusing to write through it"},
                    exit_code=EXIT_BAD_ARG)
    raw_bytes = result.raw_text.encode("utf-8")
    raw_path.write_bytes(raw_bytes)
    source_hash = hashlib.sha256(raw_bytes).hexdigest()  # _raw hash → import idempotency ONLY

    # 3. project + context (known_concepts + existing_page_slugs)
    project = derive_project_for_path(folder_abs / f"{slug}.md", vault_root)
    repo = make_repo(cfg)
    try:
        known = _context.known_concepts(repo, args.vault, vault_root)
    finally:
        repo.close()
    existing = _context.existing_page_slugs(
        db_path, args.vault, project, folder_abs, slug_strategy=slug_strategy)

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
        "kind": kind,
        "reason_harness": harness_for(kind),
        "kind_confidence": kind_conf,
        "title": result.title,
        "author": result.author,
        "date": result.date,
        "engine": result.engine,
        "source_hash": source_hash,
        "known_concepts": known,
        "existing_page_slugs": existing,
    })


# --------------------------------------------------------------------------- apply

_INVEST_HINTS = ("инвест", "финанс", "invest", "financ")


def _folder_kind(folder: str) -> str:
    low = folder.lower()
    return "invest" if any(h in low for h in _INVEST_HINTS) else "crypto"


def _note_type(kind: str, layout: Any) -> str:
    """Per-kind note `type:`, layout-safe: fall back to `summary` (mapped by every
    layout) when the preferred type isn't in this layout's type_mapping (e.g. karpathy
    has no `article-summary`)."""
    pref = _KIND_NOTE_TYPE.get(kind, "article-summary")
    return pref if pref in layout.type_mapping else "summary"


def _note_dir(layout: Any, vault_root: Path, folder_abs: Path) -> Path:
    """Layout-aware note target: Karpathy files sources under `_sources/`; every other
    (PARA-family) layout files the note in its topic folder. One code path, config-driven."""
    if resolve_alias(layout.layout) == "karpathy":
        d = vault_root / "_sources"
        d.mkdir(parents=True, exist_ok=True)
        return validate_inside_vault(d, vault_root)
    return folder_abs


def _load_note_json(args: argparse.Namespace) -> dict[str, Any]:
    if args.note_stdin:
        raw = sys.stdin.read()
    elif args.note_file:
        raw = Path(args.note_file).read_text(encoding="utf-8")
    else:
        raise ImportArticleError(
            "MISSING_NOTE", "pass --note-file or --note-stdin", exit_code=EXIT_BAD_ARG)
    try:
        note = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ImportArticleError("BAD_NOTE_JSON", f"note JSON is invalid: {e}",
                                 exit_code=EXIT_BAD_ARG) from e
    if (not isinstance(note, dict)
            or not isinstance(note.get("title_ru"), str) or not note["title_ru"].strip()
            or not isinstance(note.get("entities"), list)):
        raise ImportArticleError(
            "BAD_NOTE_JSON",
            "note must be an object with a non-empty string title_ru + a list entities",
            exit_code=EXIT_BAD_ARG)
    return note


def _run_module(module: str, argv: list[str], *, stdin: str | None = None,
                ) -> tuple[int, dict[str, Any]]:
    """Invoke a sibling wiki-* CLI in-repo and capture its JSON envelope."""
    proc = subprocess.run(
        [sys.executable, "-m", module, *argv],
        capture_output=True, text=True, input=stdin, timeout=300)
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
    vault_root = args.vault_root.resolve(strict=True)
    cfg = build_repo_config(args.vault, vault_root=vault_root, db_path_flag=args.db_path)
    db_path = cfg.get("db_path")
    layout = resolve_layout_config(vault_root)
    slug_strategy = layout.slug_strategy

    try:
        folder_abs = validate_inside_vault(vault_root / args.folder, vault_root)
    except PathTraversalError:
        return emit({"error": "INVALID_FOLDER",
                     "message": f"--folder {args.folder!r} escapes the vault root"},
                    exit_code=EXIT_BAD_ARG)

    note = _load_note_json(args)
    today = args.today or datetime.date.today().isoformat()
    note_type = _note_type(args.kind, layout)
    raw_rel = args.raw_rel  # required (see parser) — always prepare's real raw_path, never re-slugified
    san_names = [n for n in (sanitize_name(e.get("name", "")) for e in note["entities"])
                 if name_is_filable(n)]

    # karpathy: filename == slug (identity strategy) → file as <minted-slug>.md, not the human
    # title; the minted slug MUST be valid (a title that slugifies to "" would yield ".md").
    is_karpathy = resolve_alias(layout.layout) == "karpathy"
    karp_fname = None
    if is_karpathy:
        karp_slug = _apply_slug_strategy(note["title_ru"], _MINT_SLUG)
        if not _is_valid_slug(karp_slug, max_len=None):
            return emit({"error": "INVALID_SLUG",
                         "message": f"title {note['title_ru']!r} does not slugify to a valid "
                                    "karpathy source filename; rename it or use a PARA layout"},
                        exit_code=EXIT_BAD_ARG)
        karp_fname = f"{karp_slug}.md"

    fname, note_text = assemble_note(
        note, mode=args.mode, raw_rel_basename=raw_rel,
        source_url=args.source_url or str(note.get("URL", "")),
        source_lang=args.source_lang, today=today, note_type=note_type,
        folder_kind=_folder_kind(args.folder), san_names=san_names, fname=karp_fname)

    note_path = _note_dir(layout, vault_root, folder_abs) / fname
    if note_path.is_symlink():  # refuse writing through a symlinked target (R-26)
        return emit({"error": "REFUSED_SYMLINK",
                     "message": f"{fname!r} is a symlink; refusing to write through it"},
                    exit_code=EXIT_BAD_ARG)
    atomic_write_text(note_path, note_text)  # os.replace → does not follow a symlink
    note_path = validate_inside_vault(note_path, vault_root)
    note_rel = str(note_path.relative_to(vault_root))
    # minted slug (lowercase-kebab) — used only for the self-collision check + manifest;
    # extract-concepts gets the note's REL PATH as --source-page, so the indexed page slug
    # (layout strategy) is resolved downstream, not here.
    note_slug = _apply_slug_strategy(note_path.stem, _MINT_SLUG)
    # hash the ON-DISK bytes so the two-hash contract is newline-translation-proof
    note_hash = hashlib.sha256(note_path.read_bytes()).hexdigest()

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
        project = derive_project_for_path(folder_abs / f"{note_slug}.md", vault_root)
        existing = _context.existing_page_slugs(
            db_path, args.vault, project, folder_abs, slug_strategy=slug_strategy)

    candidates, skipped = derive_candidates(
        note["entities"], note_text, slug_strategy=_MINT_SLUG,
        note_slug=note_slug, existing_page_slugs=existing)

    # the source note must be indexed BEFORE concept refs can attach to it
    idx_rc, idx_env = _index_note(args.vault, vault_root, db_path, note_path)
    cc_rc, cc_env = (0, {"created": 0, "note": "no candidates"})
    if candidates:
        # --source-hash = FRESH hash of the just-written note body (NOT prepare's _raw hash)
        cc_rc, cc_env = _file_concepts(
            args.vault, vault_root, db_path, note_rel, note_hash, candidates)

    ok = idx_rc == 0 and cc_rc == 0
    return emit({
        "action": "imported" if ok else "partial",
        "vault_id": args.vault,
        "note": note_rel,
        "slug": note_slug,
        "mode": args.mode,
        "note_hash": note_hash,
        "candidates": len(candidates),
        "skipped": skipped,
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
                    help="Target PARA folder, vault-relative (e.g. '05 - Материалы/Криптовалюты')")
    pp.add_argument("--mode", choices=("full", "summary", "thread"), default="full")
    pp.add_argument("--kind", choices=KINDS, default="auto",
                    help="content-type → REASON harness (auto-detected; reported in the envelope)")
    pp.add_argument("--slug", default=None, help="Override the _raw/<slug>.md filename slug")
    pp.add_argument("--html2md-bin", default=_DEFAULT_HTML2MD)
    pp.add_argument("--pdf-extract-bin", default=_DEFAULT_PDF_EXTRACT)
    pp.set_defaults(func=prepare)

    ap = sub.add_parser("apply", help="Author the PARA note + file concepts + index.")
    _add_common(ap)
    ap.add_argument("--folder", required=True, help="Target PARA folder (as in prepare)")
    ap.add_argument("--mode", choices=("full", "summary", "thread"), default="full")
    ap.add_argument("--kind", choices=[k for k in KINDS if k != "auto"], default="article",
                    help="content-type from prepare; sets the note `type:` (layout-safe)")
    ap.add_argument("--note-file", default=None,
                    help="Path to the orchestrator's note JSON (mutex with --note-stdin)")
    ap.add_argument("--note-stdin", action="store_true",
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


if __name__ == "__main__":
    sys.exit(main())
