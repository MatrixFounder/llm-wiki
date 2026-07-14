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
import os
import re
import shutil
import subprocess
import sys
import tempfile
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
from scripts.wiki_skills._resummarize import resolve_extract_decisions
from scripts.wiki_skills._common import atomic_write_text, build_repo_config, emit
from scripts.wiki_skills.wiki_extract_concepts._validation import _is_valid_slug

from . import _context, _folder
from ._authoring import (
    _MAX_CANDIDATES,
    assemble_note,
    derive_candidates,
    finalize_candidates,
    name_is_filable,
    sanitize_name,
)
from ._detect import KINDS, detect_kind, harness_for
from ._errors import EXIT_BAD_ARG, EXIT_DEP_MISSING, EXIT_FETCH_FAILED, ImportArticleError
from ._fetch import (
    _parse_frontmatter,
    dispatch_fetch,
    ensure_source_frontmatter,
    inject_classification,
    resolve_skill_bin,
    stamp_metadata_frontmatter,
)

# TASK 049 (R-7): --classification value shape — same ≤16 cap as a policy
# level (policy._LEVEL_RE). argparse.ArgumentTypeError keeps the offending
# VALUE out of the error text (CWE-209).
_CLASSIFICATION_RE = re.compile(r"[a-z][a-z0-9_-]{0,15}")


def _classification_arg(value: str) -> str:
    if not _CLASSIFICATION_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "must be a level name matching [a-z][a-z0-9_-]{0,15}")
    return value


def _bounded_int(hi: int) -> Any:
    """argparse type factory for the W1 transcript knobs — 1 ≤ n ≤ hi (Phase-4 security
    F3: an unbounded concurrency would be forwarded verbatim and could FD/memory-exhaust
    the child). Offending value kept out of the error text (CWE-209, mirrors
    _classification_arg)."""
    def _parse(value: str) -> int:
        try:
            n = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"must be an integer in [1, {hi}]") from None
        if not 1 <= n <= hi:
            raise argparse.ArgumentTypeError(f"must be an integer in [1, {hi}]")
        return n
    return _parse


_TRANSCRIPT_CONCURRENCY_MAX = 64        # parallel HLS fragment downloads (child-side sanity)
_TRANSCRIPT_MEDIA_TIMEOUT_MAX = 86400   # 24 h — beyond any real media budget


# kind → preferred note `type:`; layout-safe fallback to "summary" (mapped by every layout)
_KIND_NOTE_TYPE = {
    "meeting": "meeting-summary", "lesson": "lesson-summary",
    "article": "article-summary",
    "paper": "article-summary", "thread": "article-summary", "summary": "summary",
}

# kinds whose REASON-authored note is the rich `summarizing-meetings` PYRAMID (TASK 046):
# `apply` files the body verbatim WITHOUT the article wrappers. The rest use the article grammar.
_PYRAMID_KINDS = frozenset({"meeting", "lesson"})

# `skipped` reasons that mean a concept page the orchestrator INTENDED was lost and is
# RECOVERABLE (vs benign dedup/collision/layout skips). Surfaced LOUDLY in the apply
# envelope's `warnings` — one entry PER reason, each with reason-specific recovery advice —
# so a paraphrased/mis-sourced quote (or an over-cap tail) can't hide behind
# action="imported"/exit 0 (the TASK 042 silent-drop fix). Keys mirror the LOSSY `skipped`
# reasons in `_authoring.derive_candidates` — INTENTIONAL skips (dedup / self-collision /
# `participant-not-concept`, TASK 052) are deliberately absent: reported in `skipped[]`, never warned.
_LOSSY_DROP_HINTS = {
    "no-verbatim-quote": "each entity `quote` MUST be an exact substring of the authored "
                         "`body` — copy quotes FROM the body you write, not the raw source. "
                         "Re-run apply with corrected quotes to file them.",
    "max-candidates": f"the per-note concept cap ({_MAX_CANDIDATES}) was reached, so the tail "
                      "was dropped — re-running with the same entities drops the same tail; "
                      "trim the entity list or split the import to file them.",
    # TASK 064 / F1 — the RAIL's own refusals, arriving as per-candidate SKIPS instead of a
    # batch kill (see `_authoring._SKIP_REASON_BY_CODE`). All RECOVERABLE: the orchestrator
    # fixes the entity and re-runs. `participant-not-concept` is deliberately absent — it is
    # INTENTIONAL (the operator's standing rule), reported in `skipped[]`, never warned.
    "definition-too-short": "the entity `definition` was empty or a fragment. A concept page "
                            "whose body says nothing is the garbage this rail exists to "
                            "prevent — write what the concept IS (terse is fine; empty is "
                            "not) and re-run apply to file it.",
    "definition-is-quote": "the entity `definition` merely restates its `quote`. The quote is "
                           "already stored as provenance; the definition is what the reader "
                           "LEARNS. Write it in your own words and re-run apply.",
    "definition-not-prose": "the entity `definition` carries markdown (a newline, a "
                            "`[[wikilink]]`, a backtick, or a leading list/heading marker) — "
                            "it is written into the page body verbatim, where those become "
                            "visible backslash litter. Send one plain sentence and re-run.",
    "field-too-long": "the entity `definition` (>2000 chars) or `quote` (>500) exceeds the "
                      "concept-page cap. Trim it and re-run apply to file it.",
    "rejected-by-concept-rail": "`wiki-extract-concepts` refused this candidate (see `code`). "
                                "The note IS filed and every other concept WAS written — only "
                                "this entity was dropped. Fix it and re-run apply.",
}
_LOSSY_SKIP_REASONS = frozenset(_LOSSY_DROP_HINTS)

__version__ = "1.0"

# TASK 048: the acquire-skill bin defaults resolve VENDOR-AGNOSTICALLY (env var → harness-dir
# scan → legacy ~/.claude fallback) via resolve_skill_bin — so a pi/codex/hermes-only operator
# (no ~/.claude, and whose html skill is named `html2md`) works out of the box. A `--*-bin` flag
# still overrides. Single source of truth in _fetch.py (no per-file hardcode duplication).
_DEFAULT_HTML = resolve_skill_bin("html")            # `html` skill; html2md.py is the URL→md command
_DEFAULT_PDF_EXTRACT = resolve_skill_bin("pdf_extract")
_DEFAULT_SOFFICE_WRAPPER = resolve_skill_bin("soffice_wrapper")  # office→text (docx/pptx/xlsx)
_DEFAULT_TRANSCRIPT = resolve_skill_bin("transcript")  # TASK 044 (Q-044-1); absent → exit 6
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


_SLUG_MAX_BYTES = 180  # filesystem-safe: `<slug>.md` stays well under NAME_MAX (255 bytes/component)


def _derive_slug(title: str | None, source: str, slug_strategy: str) -> str:
    base = (title or "").strip()
    if not base:
        base = source.rstrip("/").rsplit("/", 1)[-1].split("?", 1)[0]
    base = _EXT_RE.sub("", base)
    slug = _apply_slug_strategy(base, slug_strategy)
    # Cap the slug to a filesystem-safe byte length: a titleless source (e.g. an x.com tweet whose
    # whole body becomes the og:title) yields a >255-byte filename → `OSError [Errno 63] File name
    # too long` at write_bytes. Truncate byte-safe (UTF-8/Cyrillic-aware), then back off to a hyphen
    # boundary and strip trailing separators so the slug stays valid.
    if len(slug.encode("utf-8")) > _SLUG_MAX_BYTES:
        slug = slug.encode("utf-8")[:_SLUG_MAX_BYTES].decode("utf-8", errors="ignore")
        cut = slug.rfind("-")
        if cut >= 20:
            slug = slug[:cut]
        slug = slug.strip("-")
    return slug


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


_STAGED_GC_AGE_S = 48 * 3600  # staged captures older than this are abandoned proposals


def _gc_staged_captures() -> None:
    """Age-based sweep of `wiki-import-staged-*.md` tempfiles (Phase-4 F1: the staged
    capture is deliberately NOT deleted on consume — the fetch-free re-run contract —
    and an abandoned proposal never gets a consume at all, so without a sweep every
    no-folder `prepare` leaks one file). Runs at the start of each staging; age-based
    so a proposal confirmed within the window still finds its staged file. Best-effort:
    never raises into prepare (correctness over reclamation, mirrors `_gc_attachments`)."""
    cutoff = datetime.datetime.now().timestamp() - _STAGED_GC_AGE_S
    try:
        for f in Path(tempfile.gettempdir()).glob("wiki-import-staged-*.md"):
            try:
                if f.is_file() and not f.is_symlink() and f.stat().st_mtime < cutoff:
                    f.unlink(missing_ok=True)
            except OSError:
                continue
    except OSError:
        pass


def _stage_capture(args: argparse.Namespace, result: Any) -> Path:
    """TASK 057 (W2-4, Q-057-3): persist the converted capture to a tempfile OUTSIDE the
    vault so the confirmed re-run (`prepare --folder <F> --source <staged_path>`) is
    fetch-free — a 70-min broadcast is never transcribed twice. Frontmatter carries
    `source:` + the detected title/author/date (each `_fm_safe`-guarded — H-6) so the
    local-md re-read keeps slug + provenance; an operator `--classification` stamp is
    applied now too, so the quarantine survives even if the flag is dropped at re-run."""
    _gc_staged_captures()   # bound accumulation before adding one more (Phase-4 F1)
    md = ensure_source_frontmatter(result.raw_text or "", args.source)
    md = stamp_metadata_frontmatter(md, title=result.title, author=result.author,
                                    date=result.date)
    if getattr(args, "classification", None):
        md = inject_classification(md, args.classification)
    fd, name = tempfile.mkstemp(prefix="wiki-import-staged-", suffix=".md")
    # write THROUGH the mkstemp fd (0600) — a close-then-reopen-by-name would open a
    # narrow symlink-swap window on a shared sticky /tmp (Phase-4 security F2)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(md)
    return Path(name)


def _propose_folder(args: argparse.Namespace, cfg: dict[str, Any], vault_root: Path,
                    layout: Any, result: Any) -> int:
    """TASK 057 (W2): the no-`--folder` outcome — stage the capture, run the inference
    chain (series-sibling → active-note hint → ask), emit `folder_proposed` (exit 0) or
    `FOLDER_UNRESOLVED` (exit 2 — Q-057-1), and write NOTHING inside the vault."""
    staged = _stage_capture(args, result)
    try:
        return _propose_folder_staged(args, cfg, vault_root, layout, result, staged)
    except BaseException:
        # Phase-4 logic F5: a post-stage fault (make_repo, inference) surfaces as
        # INTERNAL_ERROR with no staged_path in the envelope — don't strand the file.
        staged.unlink(missing_ok=True)
        raise


def _propose_folder_staged(args: argparse.Namespace, cfg: dict[str, Any],
                           vault_root: Path, layout: Any, result: Any,
                           staged: Path) -> int:
    if args.kind == "auto":
        fm = _parse_frontmatter(result.raw_text or "")
        kind, kind_conf = detect_kind(result.raw_text, args.source, fm)
    else:
        kind, kind_conf = args.kind, "explicit"
    repo = make_repo(cfg)
    try:
        inf = _folder.infer_folder(repo, args.vault, result.title,
                                   source_subdir=layout.write.source_subdir)
    finally:
        repo.close()
    if inf.folder is None:
        hint_folder = _folder.active_note_folder(vault_root)   # optional signal, may be None
        # Phase-4 logic F10: the hint never OVERRIDES evidence-backed series candidates —
        # with an ambiguous candidate set it may only PICK one of them; with no candidates
        # at all it may propose its own folder. An unrelated focused note stays a bystander.
        if hint_folder is not None and (not inf.candidates or hint_folder in inf.candidates):
            inf = _folder.FolderInference(
                folder=hint_folder, basis="active-note", confidence="medium",
                evidence=[], candidates=inf.candidates or [hint_folder])
    if inf.folder is not None:
        return emit({
            "action": "folder_proposed",
            "vault_id": args.vault,
            "source": args.source,
            "title": result.title,
            "kind": kind,
            "kind_confidence": kind_conf,
            "folder_inferred": inf.folder,
            "basis": inf.basis,
            "confidence": inf.confidence,
            "evidence": inf.evidence,
            "candidates": inf.candidates,
            "staged_path": str(staged),
            "hint": "confirm or override the folder, then re-run prepare "
                    "--folder <F> --source <staged_path> (fetch-free) or "
                    "--source <original URL> (re-downloads images).",
        }, exit_code=0)
    return emit({
        "error": "FOLDER_UNRESOLVED",
        "message": "no --folder given and neither a same-series sibling nor an "
                   "active-note hint resolved one — ask the operator, then re-run "
                   "prepare --folder <F> --source <staged_path>.",
        "vault_id": args.vault,
        "source": args.source,
        "title": result.title,
        "kind": kind,
        "candidates": inf.candidates,
        "staged_path": str(staged),
    }, exit_code=EXIT_BAD_ARG)


def prepare(args: argparse.Namespace) -> int:
    vault_root = _resolve_vault_root(args)
    cfg = build_repo_config(args.vault, vault_root=vault_root, db_path_flag=args.db_path)
    db_path = cfg.get("db_path")
    layout = resolve_layout_config(vault_root)
    slug_strategy = layout.slug_strategy
    # the REASON step must summarise INTO the vault's language (international — not hardcoded
    # RU); emitted in the envelope so the orchestrator knows the target language. en fallback.
    note_lang = _vault_language(vault_root)

    # TASK 057 (W2-1): --folder is optional — omitted → the folder-inference path below
    # (fetch runs as today, then propose/ask; NOTHING is written into the vault). Given →
    # byte-identical legacy behaviour, validated up front as before.
    folder_abs: Path | None = None
    if args.folder is not None:
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
            soffice_wrapper=args.soffice_wrapper,    # TASK 046: office→text (docx/pptx/xlsx)
            download_images=layout.import_images,   # config-driven, default ON
            transcript_bin=args.transcript_bin,     # TASK 044: video sources
            video=args.video,
            embedded_videos=args.embedded_videos,
            embedded_videos_max=args.embedded_videos_max,
            lang=note_lang,                         # ALWAYS forward the vault language (C-3)
            max_duration_min=args.max_duration_min,
            cookies_from_browser=args.cookies_from_browser,
            cookies_file=args.cookies_file,
            concurrent_fragments=args.transcript_concurrency,    # TASK 057 W1: skill knobs
            media_timeout_sec=args.transcript_media_timeout,     # (None → skill defaults)
        )
    except ImportArticleError as e:
        return emit(e.envelope(), exit_code=e.exit_code)

    # TASK 057 (W3): announcement-of-a-Broadcast tweet → benign stop BEFORE slug/_raw/kind —
    # nothing filed, exit 0, and the orchestrator gets the broadcast URL + route hint.
    _err_details = (result.error or {}).get("details", {}) or {}
    if _err_details.get("kind") == "announcement_only":
        return emit({
            "action": "announcement_only",
            "source": args.source,
            "broadcast_url": _err_details.get("broadcast_url"),
            "hint": "the tweet only announces a Broadcast/Space — re-run prepare on the "
                    "broadcast URL, or pass --video to concatenate tweet + transcript.",
        }, exit_code=0)

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

    # TASK 057 (W2): no --folder → stage + infer + propose/ask; the vault stays untouched
    # (attachments are not staged — Q-057-3 — so the html temp dir is reclaimed here too).
    if args.folder is None:
        try:
            return _propose_folder(args, cfg, vault_root, layout, result)
        finally:
            if _imgtmp:
                shutil.rmtree(_imgtmp, ignore_errors=True)
    if folder_abs is None:  # unreachable (set whenever args.folder is given) — but a
        # plain guard survives `python -O`, an assert would not (Phase-4 logic I-1)
        return _bad({"error": "INTERNAL_ERROR", "type": "FolderStateError",
                     "message": "folder resolution state inconsistent"}, EXIT_BAD_ARG)

    # 2. slug + raw path (containment + slug validity — R-26). Mint via _MINT_SLUG so a
    # capitalized title under karpathy's `identity` strategy still yields a valid slug.
    # Phase-4 logic F3: a TITLELESS staged capture must not slugify to the tempfile stem
    # (`wiki-import-staged-xxxx`) — derive from the staged frontmatter's original `source:`
    # instead, so the re-run mints the same slug a direct folder-given run would have.
    _slug_source = args.source
    if not result.title and Path(args.source).name.startswith("wiki-import-staged-"):
        _orig = _parse_frontmatter(result.raw_text or "").get("source")
        if _orig:
            _slug_source = _orig
    slug = args.slug or _derive_slug(result.title, _slug_source, _MINT_SLUG)
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
    # TASK 053 / R5 (DF-JUNK): adopt-in-place. A clean markdown source that
    # ALREADY lives under a `_raw/` dir inside the vault (a re-dropped `.md`, a
    # re-run, or a direct `/wiki-import <…>/_raw/x.md`) is ITSELF a valid
    # raw-of-record — minting a second `_raw/<slug>.md` beside it is pure junk.
    # Adopt the source path as the capture; the symlink guard (below) + the
    # `is_unchanged` short-circuit then make this a no-op (byte-identical) or an
    # in-place `source:` stamp (SAME path → no dup). Scoped to clean markdown
    # already under `_raw/`: a `.txt/.vtt`/office original genuinely needs
    # conversion+relocation into `_raw/`, so it is NOT adopted (its leftover inbox
    # original is handled by the wiki-sync workflow — see workflows/wiki-sync.md).
    # A URL / out-of-vault / symlinked source naturally fails these guards and
    # falls through to the normal mint (R-26 posture preserved).
    try:
        _src = Path(args.source).expanduser()
        _src_real = _src.resolve()
        _src_rel = _src_real.relative_to(vault_root.resolve())
        if (_src_real.suffix.lower() in (".md", ".markdown")
                and "_raw" in _src_rel.parts
                and not _src.is_symlink()
                and _src_real.is_file()):
            raw_path = _src_real
    except (ValueError, OSError):
        pass  # not an in-vault local file (URL / outside vault / unresolvable)
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
    # TASK 049 (R-7): opt-in classification stamp — a DEDICATED injection (not
    # riding ensure_source_frontmatter's already-cites-source early-return) so
    # a capture that already carries `source:` still gets the stamp. This is
    # the H-6 "_raw/ second-class" quarantine: a hostile capture classified
    # `restricted` never enters a lower-audience retrieval envelope.
    if getattr(args, "classification", None):
        raw_md = inject_classification(raw_md, args.classification)
    raw_bytes = raw_md.encode("utf-8")
    source_hash = hashlib.sha256(raw_bytes).hexdigest()  # _raw hash → import idempotency ONLY
    # TASK 051 (R-18): `is_unchanged` short-circuit — a re-poll of a source that
    # converts to byte-identical `_raw` skips the REASON pass entirely. Placed AFTER
    # the symlink guards (raw_path L276 / att_dst L284) so we never hash THROUGH a
    # swapped-in symlink (H-6 write posture), and BEFORE the write so nothing on disk
    # changes. `--force` bypasses (regenerate after a REASON-harness change or a
    # corrupt prior summary). A read failure falls through to a normal (over)write.
    if not args.force and raw_path.is_file():
        try:
            existing_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        except OSError:
            existing_hash = None
        if existing_hash == source_hash:
            if _imgtmp and _imgtmp.exists():
                shutil.rmtree(_imgtmp, ignore_errors=True)
            return emit({
                "action": "unchanged",
                "is_unchanged": True,
                "vault_id": args.vault,
                "raw_path": str(raw_path.relative_to(vault_root)),
                "folder": args.folder,
                "slug": slug,
                "source_hash": source_hash,
            }, exit_code=0)
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
        known = _context.known_concepts(
            repo, args.vault, vault_root,
            fmt=getattr(args, "known_concepts_format", "full"))
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
        # TASK 044: a non-null quality_flag (e.g. english_auto_translation) MUST be surfaced to the
        # operator BEFORE the REASON harness runs (R-8c); the embedded log records every discovered
        # embed + WHY it was skipped (ad-denylist/ad-context/cap/… — R-13f, no silent drops).
        "quality_flag": result.quality_flag,
        "embedded": result.embed_log,
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
        # TASK 053 / R4 (DF-9): DELIBERATELY no `validate_inside_vault` containment
        # check here (contrast wiki-extract-concepts `--candidates-file`, which
        # refuses an out-of-vault path with INVALID_CANDIDATES_PATH). The note JSON
        # is ephemeral orchestrator scaffolding — the documented primary channel is
        # `--note-stdin`, and `--note-file` routinely points at a scratchpad tmpfile
        # OUTSIDE the vault; a containment check would break that flow. We DO keep
        # the R-26 posture: refuse to read THROUGH a swapped-in symlink.
        if nf.is_symlink():
            raise ImportArticleError("REFUSED_SYMLINK",
                "note file is a symlink; refusing to read through it",
                exit_code=EXIT_BAD_ARG)
        # R4 deliberately drops containment (a scratchpad path is fine), so
        # --note-file may be ANY path — require a REGULAR file so a FIFO / char
        # device can't bypass the size bound with an unbounded read_text() (the
        # st_size guard is meaningless for a non-regular file). Covers missing /
        # FIFO / device / dir uniformly.
        if not nf.is_file():
            raise ImportArticleError("NOTE_NOT_FILE",
                "note file is not a regular file (missing, FIFO, device, or directory)",
                exit_code=EXIT_BAD_ARG)
        if nf.stat().st_size > _MAX_NOTE_BYTES:
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
                     or not all(isinstance(t, str) for t in note["tags"])))
            # `participants` (TASK 052; consumed by assemble_note for pyramid kinds) — same
            # per-CHAR hazard as tags; require a list of strings when present:
            or (note.get("participants") is not None
                and (not isinstance(note.get("participants"), list)
                     or not all(isinstance(p, str) for p in note["participants"])))):
        raise ImportArticleError(
            "BAD_NOTE_JSON",
            "note needs a non-empty string title (or legacy title_ru), a list of object "
            "entities with string names + string-or-null quotes, string body/tldr (or legacy "
            "ru_body), string summary_bullets items, and list-of-strings tags/participants",
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
    # WI-3: a month-precision source date (arXiv `2025-10`, ECB/working-paper `YYYY-MM`) has no
    # valid YYYY-MM-DD form, so the REASON note commonly leaves `published` null. Fall back to
    # prepare's already-extracted `date` (round-tripped via --published) so the publication date
    # isn't lost. Only fills a null/blank — a note that DID author `published` (any precision) wins.
    if not str(note.get("published") or "").strip() and getattr(args, "published", None):
        note["published"] = args.published
    today = args.today or datetime.date.today().isoformat()
    note_type = _note_type(args.kind, layout)
    # TASK 046: meeting/lesson → the REASON-authored PYRAMID is filed verbatim (no article
    # wrappers); everything else keeps the per-mode article grammar.
    grammar = "pyramid" if args.kind in _PYRAMID_KINDS else "article"
    # The pyramid body IS the entire deliverable (no Саммари/bullets wrapper to fall back on),
    # so an empty body would file a content-less note as action=imported (silent). Refuse it
    # (L-1 / vdd-multi) — author the pyramid digest in `body` before apply.
    if grammar == "pyramid" and not (note.get("body") or note.get("ru_body") or "").strip():
        return emit({"error": "EMPTY_PYRAMID_BODY",
                     "message": f"--kind {args.kind} files a pyramid whose `body` IS the "
                                "deliverable, but the note body is empty; author the pyramid "
                                "digest (TL;DR + sections) in `body` before apply"},
                    exit_code=EXIT_BAD_ARG)
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
            san_names=names, fname=slug_fname, mint_strategy=mint, lang=note_lang,
            grammar=grammar,
            classification=getattr(args, "classification", None))

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
    if not args.concepts:
        # TASK 046 --no-concepts: defer concept filing to a separate /wiki-extract-concepts run.
        # NOT a lossy skip (no per-entity warning noise) — the entities are intact in the body;
        # the footer is dropped (footer_names → [] below) so no wikilink dangles.
        candidates: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
    elif concepts_indexable:
        candidates, skipped = derive_candidates(
            note["entities"], note_text, slug_strategy=mint,
            note_slug=note_slug, existing_page_slugs=existing, grammar=grammar)
    else:
        candidates = []
        skipped = [{"name": str(e.get("name", "")), "reason": "layout-no-concepts"}
                   for e in note["entities"] if isinstance(e, dict)]

    # Footer reconciliation (P3-8): the entity-index section must list ONLY entities
    # that resolve to a page — those filed now (candidates) plus those whose slug collides
    # with an EXISTING page (the link still resolves). Drop the rest (no-verbatim-quote / dup /
    # self-collision / over-cap) so the footer never carries a dangling `[[wikilink]]`. Rebuild
    # only when the set actually shrank (clean notes stay byte-identical).
    # `candidates`/`skipped` from the derive above are AUTHORITATIVE — only the displayed
    # footer is rebuilt (NOT re-derived): re-deriving against the shrunk note_text would be
    # circular (an entity whose only support was the footer wikilink line would then drop).
    #
    # ★★ F1 (TASK 064) — AND THEN THE CANDIDATES ARE **FINALISED AGAINST THE BYTES THAT
    # REACH DISK**. `wiki-import` has no concept writer: `_file_concepts` SHELLS OUT to
    # `wiki-extract-concepts apply`, whose gates now VERIFY the span against the note it
    # reads from disk. Two consequences the first cut of TASK 064 missed, both fatal:
    #
    #   1. the entity footer sits in the MIDDLE of a `full`/`summary`/`thread` note, so
    #      reconciling it SHIFTS every line below it — a span derived before the rebuild is
    #      wrong for the bytes actually written (`SOURCE_SPAN_QUOTE_MISMATCH`);
    #   2. a candidate the rail refuses (empty definition, one-token quote, a `person`)
    #      killed the ENTIRE batch at exit 6 — destroying every legitimate concept beside it
    #      and leaving the filed note's footer wikilinks dangling.
    #
    # `finalize_candidates` re-derives the span against the final text and judges each
    # candidate with the RAIL'S OWN validators, DROPPING the failures into `skipped[]`
    # instead of failing. A drop shrinks the footer, which shifts the lines again — hence
    # the fixed point. It terminates: every iteration that does not break STRICTLY shrinks
    # `candidates`.
    for _ in range(len(candidates) + 1):
        resolvable = {c["name"] for c in candidates} | {
            s["name"] for s in skipped if s.get("reason") == "collides-existing-page"}
        footer_names = [n for n in san_names if n in resolvable]
        fname, note_text = _assemble(footer_names)
        candidates, rail_dropped = finalize_candidates(candidates, note_text, layout)
        if not rail_dropped:
            break
        skipped.extend(rail_dropped)

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
    elif not args.concepts and note["entities"]:
        # TASK 046 --no-concepts: intentional deferral, not a failure.
        cc_env = {"created": 0, "note": "deferred (--no-concepts); run /wiki-extract-concepts"}
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
    envelope: dict[str, Any] = {
        "action": "imported" if ok else "partial",
        "vault_id": args.vault,
        "note": note_rel,
        "slug": note_slug,
        "mode": args.mode,
        "grammar": grammar,                       # TASK 046: pyramid (meeting/lesson) | article
        "diagrams": bool(args.diagrams),          # TASK 046: --diagrams recorded for the recipe
        "concepts_deferred": not args.concepts,   # TASK 046: --no-concepts → filed separately
        "note_hash": note_hash,
        "candidates": len(candidates),
        "skipped": skipped,
        "warnings": warnings,
        "index": idx_env,
        "concepts": cc_env,
    }
    marker = _extract_decisions_marker(vault_root, note_rel)
    if marker is not None:
        envelope["extract_decisions"] = marker
    return emit(envelope, exit_code=0 if ok else EXIT_DEP_MISSING)


def _extract_decisions_marker(
    vault_root: Path, note_rel: str
) -> dict[str, Any] | None:
    """TASK 063 / R-063-3′(a) — the DISPATCH MARKER, and Decision-17 survives it.

    `wiki-import` does NOT call the extraction rail. It emits a marker; the
    ORCHESTRATOR runs `wiki-extract-decisions` as a second step — exactly how
    `wiki-sync` already delegates to `wiki-import`. The CLI stays deterministic
    plumbing on both sides of the REASON step.

    ★ ABSENT, NOT `false`. When the config does not enable the rail, the key is OMITTED
    from the envelope entirely. A marker that is ALWAYS PRESENT invites an orchestrator
    to act on it — and `"extract_decisions": {"enabled": false}` reads, to a model
    skimming an envelope, like a thing it could switch on. Omission cannot be misread.
    """
    policy = resolve_extract_decisions(vault_root / note_rel, vault_root=vault_root)
    if policy is None or not policy.enabled:
        return None
    return {
        "tool": "wiki-extract-decisions",
        "source": note_rel,
        "dirs": {
            "decision": policy.dirs.decision,
            "requirement": policy.dirs.requirement,
            "risk": policy.dirs.risk,
        },
    }


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
    pp.add_argument("--folder", required=False, default=None,
                    help="Target folder, vault-relative (e.g. '05 - Materials/Crypto'). "
                         "TASK 057 (W2): omitted → prepare runs folder INFERENCE (same-series "
                         "sibling via the index, then an optional active-note hint), emits "
                         "folder_proposed / FOLDER_UNRESOLVED with a staged capture, and "
                         "writes NOTHING into the vault until a --folder re-run confirms.")
    pp.add_argument("--mode", choices=("full", "summary", "thread"), default="full")
    pp.add_argument("--kind", choices=KINDS, default="auto",
                    help="content-type → REASON harness (auto-detected; reported in the envelope)")
    pp.add_argument("--slug", default=None, help="Override the _raw/<slug>.md filename slug")
    pp.add_argument("--known-concepts-format", choices=["full", "slugs-only"], default="full",
                    dest="known_concepts_format",
                    help="P-6 (mirrors wiki-extract-concepts R-015-3): shape of the envelope's "
                         "`known_concepts` field. 'full' (default) = [{slug,name}, …] "
                         "(backward-compatible); 'slugs-only' = [slug, …] (~N×30 B vs ~N×200 B) "
                         "— pass it on a LARGE vault to keep the prepare envelope small.")
    pp.add_argument("--force", action="store_true",
                    help="TASK 051 (R-18): bypass the `is_unchanged` short-circuit — "
                         "always rewrite _raw and emit a full envelope even when a "
                         "re-poll produced byte-identical content (regenerate after a "
                         "REASON-harness change or a corrupt prior summary).")
    pp.add_argument("--classification", type=_classification_arg, default=None,
                    metavar="LEVEL",
                    help="TASK 049 (ADR-009): stamp `classification: <level>` into the "
                         "_raw capture's frontmatter (the H-6 quarantine for hostile "
                         "external content). Pass the SAME value to `apply` so the "
                         "authored note is stamped too.")
    pp.add_argument("--html-bin", dest="html_bin", default=_DEFAULT_HTML,
                    help=f"path to the `html` skill's combined URL→md command, run via python3 "
                         f"(default: {_DEFAULT_HTML})")
    pp.add_argument("--pdf-extract-bin", default=_DEFAULT_PDF_EXTRACT)
    pp.add_argument("--soffice-wrapper", dest="soffice_wrapper", default=_DEFAULT_SOFFICE_WRAPPER,
                    help="Path to the office skills' soffice wrapper (office→text for docx/pptx/xlsx)")
    # TASK 044 — video sources via the transcript-fetcher skill.
    pp.add_argument("--transcript-bin", dest="transcript_bin", default=_DEFAULT_TRANSCRIPT,
                    help="transcript-fetcher fetch.py (absent → exit 6 when a video URL is hit)")
    # --video (force transcript for an ambiguous x-status) and --embedded-videos (discover + append
    # non-ad embeds on a not_video page) are mutually exclusive — argparse rejects both with exit 2.
    _vid = pp.add_mutually_exclusive_group()
    _vid.add_argument("--video", action="store_true",
                      help="force the transcript path for an ambiguous x.com/status URL (concat text+video)")
    _vid.add_argument("--embedded-videos", dest="embedded_videos", action="store_true",
                      help="on a non-video html page, discover + transcribe NON-AD video embeds (ads always excluded)")
    pp.add_argument("--embedded-videos-max", dest="embedded_videos_max", type=int, default=5,
                    help="cap on embedded videos transcribed (default 5); overflow logged, never silently dropped")
    pp.add_argument("--max-duration-min", dest="max_duration_min", type=float, default=None,
                    help="passthrough: transcribe only the first N minutes (long Broadcasts/Spaces)")
    # TASK 057 (W1): forward the skill's X-media robustness knobs. Omitted (None) → the flag
    # is NOT passed, so the skill's own env/.env/duration-derived defaults rule.
    pp.add_argument("--transcript-concurrency", dest="transcript_concurrency",
                    type=_bounded_int(_TRANSCRIPT_CONCURRENCY_MAX), default=None, metavar="N",
                    help="passthrough → transcript-fetcher --concurrent-fragments (parallel HLS "
                         "fragment downloads for X media; omitted → skill default/env; max "
                         f"{_TRANSCRIPT_CONCURRENCY_MAX})")
    pp.add_argument("--transcript-media-timeout", dest="transcript_media_timeout",
                    type=_bounded_int(_TRANSCRIPT_MEDIA_TIMEOUT_MAX), default=None, metavar="SEC",
                    help="passthrough → transcript-fetcher --media-timeout-sec (X media download "
                         "budget; omitted → skill duration-derived default/env; raises the "
                         "subprocess wall-clock when larger than it)")
    pp.add_argument("--cookies-from-browser", dest="cookies_from_browser", default=None,
                    help="passthrough: load cookies from a local browser (login-walled video)")
    pp.add_argument("--cookies-file", dest="cookies_file", default=None,
                    help="passthrough: Netscape cookies.txt path (login-walled video)")
    pp.set_defaults(func=prepare)

    ap = sub.add_parser("apply", help="Author the PARA note + file concepts + index.")
    _add_common(ap)
    ap.add_argument("--folder", required=True, help="Target PARA folder (as in prepare)")
    ap.add_argument("--mode", choices=("full", "summary", "thread"), default="full")
    ap.add_argument("--kind", choices=[k for k in KINDS if k != "auto"], default="article",
                    help="content-type from prepare; sets the note `type:` (layout-safe)")
    note_src = ap.add_mutually_exclusive_group()  # enforce the documented mutex
    note_src.add_argument("--note-file", default=None,
                          help="Path to the orchestrator's note JSON (mutex with --note-stdin). "
                               "By design this MAY live outside --vault-root (ephemeral "
                               "orchestrator scratch, e.g. a scratchpad tmpfile — NOT vault "
                               "content), so unlike wiki-extract-concepts' --candidates-file it "
                               "is NOT containment-checked; a swapped-in symlink is still "
                               "refused (TASK 053 / R4, DF-9).")
    note_src.add_argument("--note-stdin", action="store_true",
                          help="Read the orchestrator's note JSON from stdin")
    ap.add_argument("--existing-page-slugs", default=None,
                    help="JSON array of existing slugs (from prepare) for the collision guard")
    ap.add_argument("--source-url", default=None, help="Original source URL (for provenance)")
    ap.add_argument("--raw-rel", required=True,
                    help="Vault-rel path of the _raw original (use prepare's raw_path verbatim)")
    ap.add_argument("--source-lang", default="en")
    ap.add_argument("--published", default=None,
                    help="WI-3: prepare's extracted source `date` (may be month-precision "
                         "YYYY-MM or year-only YYYY, e.g. arXiv `2025-10`). Used as a FALLBACK "
                         "for the note's `published` when the REASON note leaves it null — so a "
                         "publication date with no valid YYYY-MM-DD form isn't silently dropped. "
                         "A `published` authored in the note JSON (any precision) wins.")
    ap.add_argument("--classification", type=_classification_arg, default=None,
                    metavar="LEVEL",
                    help="TASK 049: stamp `classification: <level>` into the authored "
                         "note's frontmatter (pass the same value given to `prepare`).")
    ap.add_argument("--today", default=None, help="ISO date stamp (default: today)")
    # TASK 046: orthogonal generation modifiers. --diagrams signals the REASON harness to
    # include selective mermaid (the body already carries it on the CLI side; recorded in the
    # manifest). --concepts/--no-concepts gates concept filing (default ON = back-compat;
    # --no-concepts defers to a separate /wiki-extract-concepts run).
    ap.add_argument("--diagrams", action="store_true",
                    help="REASON includes selective mermaid diagrams (recorded in the manifest)")
    concepts_grp = ap.add_mutually_exclusive_group()
    concepts_grp.add_argument("--concepts", dest="concepts", action="store_true", default=True,
                              help="File concept pages (default)")
    concepts_grp.add_argument("--no-concepts", dest="concepts", action="store_false",
                              help="Defer concept filing to a separate /wiki-extract-concepts run")
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
