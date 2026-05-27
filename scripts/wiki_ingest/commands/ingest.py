"""`ingest` orchestrator subcommand — Phase 1 skeleton (TASK 017 bead 017-05).

Phase 1 ships the argparse contract, vault-discovery, vault_id routing,
source-hash idempotency short-circuit, and well-formed manifest emission
with EMPTY `written[]`. Phase 2 (bead 017-06) replaces the empty stub
with the real `_dispatch`-mediated pipeline composition.

Anti-leak rule (`docs/tasks/task-017-05-ingest-skeleton.md` §5):
Phase 1 emits `summary_path: null` — NOT a placeholder path that does
not resolve on disk. A non-null `summary_path` in the manifest is a
written-file commitment; Phase 2 fills it in.

The vault discovery treats the operator's `--vault` as one of three
shapes:

- two-tier vault root (`schema_version: 2.0`): `course` resolves to
  `null` (the operator did not pin a specific course; downstream
  beads will surface course-required scenarios as needed);
- two-tier course root (`schema_version: 1.x` with a 2.0 root above):
  `course` is the course directory basename;
- single-course vault (`schema_version: 1.x` only): `course` is null.

The skill does NOT recurse via `_dispatch` in Phase 1.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from wiki_ingest import _dispatch, _safety, _vault
from wiki_ingest._frontmatter import split_frontmatter


_MANIFEST_VERSION = "1.1"
_SOURCE_HASH_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_READ_HASH_CHUNK = 1 << 20  # 1 MiB — bounded read, matches MAX_*_BYTES discipline


def register(sub: argparse._SubParsersAction) -> None:
    """Wire the `ingest` subparser. Called once from `wiki_ops.py`."""
    p = sub.add_parser(
        "ingest",
        help="v1.1 orchestrator: register source, upsert pages, update "
             "index, append log, emit manifest (Phase 1 stub).",
    )
    p.add_argument("--source", required=True,
                   help="absolute path to the raw input (transcript / "
                        "article / pre-made summary).")
    p.add_argument("--vault", required=True,
                   help="absolute path to the vault root OR a course root.")
    p.add_argument("--output-format", choices=("human", "json"),
                   default="human",
                   help="`json` emits the v1.1 manifest to stdout; "
                        "`human` emits a short summary (suppressed by "
                        "--quiet or when stdout is piped).")
    p.add_argument("--vault-id", default=None, metavar="SLUG",
                   help="strict-mode validator (TASK 017 R3 / UC-3); "
                        "see references/exit_codes.md exits 23/24/25.")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--known-concepts-file", default=None, metavar="PATH",
                   help="(decorative in v1.1 summary-passthrough scope; "
                        "consumed when the synthesizer-subagent integration "
                        "lands — see SKILL.md §Install on PATH).")
    g.add_argument("--known-concepts-stdin", action="store_true",
                   help="(decorative — see --known-concepts-file).")
    p.add_argument("--source-hash", default=None, metavar="HEX",
                   help="sha256-hex of the source bytes (TASK 017 R9 / "
                        "UC-4 short-circuit). Recorded into "
                        "`_sources/<slug>.md` after first ingest; second "
                        "call with the same hex short-circuits.")
    p.add_argument("--config", default=None, metavar="PATH",
                   help="(decorative — see --known-concepts-file).")
    p.add_argument("--timeout-seconds", type=int, default=600,
                   help="(decorative — no subprocess to bound in the "
                        "summary-passthrough scope).")
    p.add_argument("--quiet", action="store_true",
                   help="force-quiet decorative stdout regardless of TTY.")
    p.set_defaults(func=execute)


def execute(args: argparse.Namespace) -> int:
    """Phase 1 orchestrator entry point. Phase 2 (017-06) extends below."""
    # 1. Source path validation
    source = Path(args.source).resolve()
    if not source.is_file():
        _safety.die(f"source not found: {source}", code=_safety.EXIT_GENERIC)

    # 2. Vault discovery + 2.0/1.x disambiguation
    course_root, vault_root = _resolve_vault_layout(Path(args.vault).resolve())

    # 3. vault_id resolution + strict-mode routing (UC-3 → exit 23/24/25)
    effective_vault_id = _resolve_vault_id(
        vault_root_path=vault_root if vault_root else course_root,
        flag=args.vault_id,
    )

    # 4. Source-hash format validation + idempotency short-circuit (UC-4)
    effective_hash = _resolve_source_hash(args.source_hash, source)
    course_for_writes = course_root or vault_root
    if course_for_writes is not None:
        slug = _safety.slugify(source.stem)
        recorded = _read_source_footer_hash(slug, course_for_writes)
        if recorded is not None and recorded == effective_hash:
            return _emit_short_circuit(
                args, source, slug, effective_hash,
                effective_vault_id, course_root, vault_root,
            )

    # 5. Phase-2 — summary-passthrough orchestration (TASK 017 bead 017-06)
    head = _build_common_manifest_head(
        args, source, effective_hash, effective_vault_id, course_root, vault_root,
    )
    course_for_writes = course_root or vault_root
    if course_for_writes is None:
        _safety.die(
            "no course root to write into; pass --vault pointing to a "
            "course-local schema root (1.x), not the vault root (2.0)",
            code=_safety.EXIT_USAGE,
        )

    # 5a. Summary-passthrough detection (synthesis-via-subagent is FUTURE,
    # see references for the `claude -p --skill summarizing-meetings` pattern).
    src_fm, _ = split_frontmatter(_safety.read_text(source))
    src_type = src_fm.get("type") if isinstance(src_fm, dict) else None
    if src_type not in {"summary", "lesson-summary", "meeting-summary"}:
        _safety.die(
            _json_error_envelope({
                "status": "error",
                "phase": "needs-pre-summarization",
                "code": "SOURCE_NEEDS_SUMMARIZATION",
                "source_type": src_type,
                "hint": (
                    "wiki-ingest v1.1 supports summary-passthrough only. "
                    "Pre-summarise the source via the `summarizing-meetings` "
                    "skill (operator-side: `claude -p` headless, or the "
                    "/wiki-enrich bridge's pre-summarise pass), then re-invoke "
                    "with --source pointing at the resulting summary file."
                ),
            }),
            code=_safety.EXIT_SUBPROCESS,
        )

    # 5b. Pipeline dispatch loop. Per-step rollback (Q-1): each atomic op
    # commits independently; mid-pipeline failure leaves `written_so_far[]`
    # populated and routes to exit 20 via _emit_partial.
    try:
        written, log_event = _run_pipeline(
            args, source, src_fm, course_for_writes, course_root, vault_root,
            effective_hash,
        )
    except _PartialFailure as exc:
        return _emit_partial(head, exc)

    # 5c. Full success manifest
    slug = _safety.slugify(source.stem)
    sources_path = course_for_writes / "_sources" / f"{slug}.md"
    manifest = {
        **head,
        "status": "ok",
        "written": written,
        "created": [w["path"] for w in written if w["action"] == "created"],
        "touched": [w["path"] for w in written if w["action"] == "updated"],
        "contradictions": 0,
        "summary_path": str(sources_path.relative_to(course_for_writes)),
        "log_event": log_event,
        "llm_tokens_used": {"input": 0, "output": 0, "model": None},
    }
    return _emit(args, manifest, human_summary_lines=[
        f"Ingested: {source}",
        f"Wrote {len(written)} files into {course_for_writes}.",
    ])


# --------------------------------------------------------------------- #
# Vault-layout disambiguation                                           #
# --------------------------------------------------------------------- #

def _resolve_vault_layout(start: Path) -> tuple[Path | None, Path | None]:
    """Map operator-supplied `--vault <path>` to `(course_root, vault_root)`.

    `find_vault_root` returns `(first_schema_dir, outer_2.0_schema_dir|None)`
    but does NOT distinguish whether `start` is itself a 2.0 vault root vs
    a 1.x course root. We peek the schema version here to label correctly.
    """
    first, outer = _vault.find_vault_root(start)
    schema_version = _vault._peek_schema_version(first / _vault.SCHEMA_FILE)
    if schema_version == "2.0":
        # operator passed the vault root directly; no specific course pinned
        return None, first
    # 1.x course root; outer is either the 2.0 vault root or None
    return first, outer


# --------------------------------------------------------------------- #
# vault_id resolution + UC-3 routing                                    #
# --------------------------------------------------------------------- #

def _resolve_vault_id(vault_root_path: Path | None, flag: str | None) -> str | None:
    """Read frontmatter `vault_id`, validate pattern when present, route 23/24/25."""
    fm_value = None
    if vault_root_path is not None:
        fm_value = _vault.read_vault_id(vault_root_path)
    # Frontmatter-side pattern check fires regardless of whether the flag was passed.
    if fm_value is not None:
        _vault.validate_vault_id_pattern(fm_value)
    if flag is not None:
        # Caller-supplied slug must also satisfy the pattern (exits 24 on its own).
        _vault.validate_vault_id_pattern(flag)
        if fm_value is None:
            _safety.die(
                _json_error_envelope({
                    "status": "error",
                    "code": "MISSING_VAULT_ID",
                    "wiki_schema_path": str(vault_root_path / _vault.SCHEMA_FILE) if vault_root_path else None,
                    "from_flag": flag,
                }),
                code=_safety.EXIT_MISSING_VAULT_ID,
            )
        if fm_value != flag:
            _safety.die(
                _json_error_envelope({
                    "status": "error",
                    "code": "VAULT_ID_FLAG_MISMATCH",
                    "in_frontmatter": fm_value,
                    "from_flag": flag,
                }),
                code=_safety.EXIT_VAULT_ID_MISMATCH,
            )
    return fm_value


# --------------------------------------------------------------------- #
# Source-hash handling                                                  #
# --------------------------------------------------------------------- #

def _resolve_source_hash(flag: str | None, source: Path) -> str:
    """`--source-hash <hex>` overrides recompute (R9.1); else sha256 the bytes."""
    if flag is not None:
        if not _SOURCE_HASH_RE.fullmatch(flag):
            _safety.die(
                _json_error_envelope({
                    "status": "error",
                    "code": "INVALID_SOURCE_HASH",
                    "received": flag,
                    "pattern": _SOURCE_HASH_RE.pattern,
                }),
                code=_safety.EXIT_USAGE,
            )
        return flag.lower()
    h = hashlib.sha256()
    with open(source, "rb") as f:
        while True:
            chunk = f.read(_READ_HASH_CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _read_source_footer_hash(slug: str, course_root: Path) -> str | None:
    """Look up `source_hash` in an existing `_sources/<slug>.md` frontmatter.

    Returns the recorded hex (lowercased) on hit; `None` on miss. NEVER
    raises — absent file / unreadable / missing field all return `None`.
    Phase 2 (017-06) will WRITE this field via `register-summary`; Phase 1
    only reads when present.
    """
    candidate = course_root / "_sources" / f"{slug}.md"
    if not candidate.is_file():
        return None
    try:
        text = _safety.read_text(candidate)
    except (OSError, SystemExit):
        # SystemExit guards against `read_text`'s `die()` on size cap or
        # symlink-refusal; a defective recorded hash is "no hit, run full
        # pipeline" — never a backdoor for vault-escape (writes still go
        # through _atomic_write_text containment).
        return None
    try:
        fm, _ = split_frontmatter(text)
    except (ValueError, UnicodeError, KeyError):
        return None
    value = fm.get("source_hash") if isinstance(fm, dict) else None
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    return value if _SOURCE_HASH_RE.fullmatch(value) else None


# --------------------------------------------------------------------- #
# Manifest emission                                                     #
# --------------------------------------------------------------------- #

def _build_common_manifest_head(
    args, source, effective_hash, effective_vault_id, course_root, vault_root,
) -> dict:
    """Top-level manifest fields shared by full / short-circuit / Phase-1."""
    effective_vault_root = vault_root if vault_root is not None else course_root
    if course_root is not None and vault_root is not None:
        course_label = course_root.relative_to(vault_root).name
    else:
        course_label = None  # Q-5: single-course vault OR operator-passed root
    return {
        "manifest_version": _MANIFEST_VERSION,
        "vault_id": effective_vault_id,
        "vault_root": str(effective_vault_root) if effective_vault_root else None,
        "course": course_label,
        "source": {
            "path": str(source),
            "slug": _safety.slugify(source.stem),
            "hash": effective_hash,
        },
    }


def _dispatch_silent(cmd_name: str, ns: argparse.Namespace) -> int:
    """Dispatch an atomic op; swallow its stdout AND convert `die()`
    `SystemExit` into a non-zero return code.

    Each atomic op (register-summary / upsert-page / update-index /
    append-log / log-event) writes a per-op JSON report to stdout in
    TASK 015 style; suppressed here so it doesn't corrupt the final
    manifest. AND: every atomic op uses `_safety.die(code=N)` which
    `sys.exit`s on error — the SystemExit would otherwise bypass the
    orchestrator's per-step rollback (TASK 017 Q-1). Catch + convert
    so `_run_pipeline` can route to `_PartialFailure` cleanly.

    Stderr is NOT suppressed: the atomic op's error envelope still
    surfaces to the operator. The orchestrator's partial envelope on
    stdout complements (not replaces) the stderr diagnostic.
    """
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            return _dispatch.dispatch(cmd_name, ns)
        except SystemExit as exc:
            code = exc.code
            return int(code) if isinstance(code, int) else 1


class _PartialFailure(Exception):
    """Mid-pipeline failure (TASK 017 Q-1 / R5.3). Carries `written_so_far[]`
    + `phase` discriminator so the orchestrator can emit the §1.3 partial
    envelope and exit 20 (`EXIT_PARTIAL`). Also carries the original
    `child_exit_code` from the dispatched atomic op so security-class
    failures (S-M1 inbox containment exit 8, MAX_PAGE_BYTES exit 6, etc.)
    can be surfaced in the envelope rather than collapsed into "partial"
    (logic+security critics 2026-05-27 vdd-multi)."""

    def __init__(self, phase: str, written_so_far: list[dict],
                 cleanup_advice: str, child_exit_code: int = 0):
        super().__init__(f"partial failure at phase {phase!r}")
        self.phase = phase
        self.written_so_far = written_so_far
        self.cleanup_advice = cleanup_advice
        self.child_exit_code = child_exit_code


_FM_OPEN_RE = re.compile(r"^---\r?\n")
_FM_CLOSE_RE = re.compile(r"\r?\n---\r?\n")


def _record_source_hash_footer(sources_path: Path, hex_hash: str) -> None:
    """Inject `source_hash: <hex>` into `_sources/<slug>.md` frontmatter
    AFTER register-summary writes the file.

    Orchestrator-side post-process — keeps `register-summary`'s public
    surface untouched (no new flag) while enabling UC-4 idempotency
    short-circuits on re-runs. CRLF-aware (both `---\\n` and `---\\r\\n`
    fences are accepted). The write goes through `_safety.write_text`
    so it inherits the symlink-overwrite refusal + atomic-rename + size
    cap defenses — NOT a raw `Path.write_text` (which would bypass the
    F1 hardening register-summary itself uses). Best-effort: failure
    leaves the vault otherwise consistent and a re-run just runs the
    full pipeline again (slower, not broken).
    """
    try:
        text = sources_path.read_text(encoding="utf-8")
    except OSError:
        return
    if not _FM_OPEN_RE.match(text):
        return
    close_match = _FM_CLOSE_RE.search(text, 4)
    if close_match is None:
        return
    close_idx = close_match.start()
    if "\nsource_hash:" in text[:close_idx]:
        return
    new_text = text[:close_idx] + f"\nsource_hash: {hex_hash}" + text[close_idx:]
    try:
        # Route through F1 hardening (symlink-overwrite refusal + atomic
        # rename); failure ⇒ SystemExit, caught and silenced so the
        # vault stays consistent.
        _safety.write_text(sources_path, new_text, dry_run=False)
    except (OSError, SystemExit):
        pass


_TITLE_FORBIDDEN_RE = re.compile(r"[\n\r|]|^\s*## \[")


def _prevalidate_pipeline_inputs(title: str) -> None:
    """Reject inputs that would fail mid-pipeline AFTER state-mutating writes.

    `append-log` rejects titles containing `|`, newlines, or a `## [`
    prefix (log-heading spoof). `update-index` and `upsert-page` accept
    these. Without this pre-check, a malformed title would let the
    orchestrator write `_sources/<slug>.md` (+ the source_hash footer,
    which then short-circuits forever via UC-4) + N concept pages + an
    index row BEFORE dying at append-log → exit 20 with partial state.

    Fire BEFORE any dispatch so the operator gets exit 2 + a clear
    envelope and zero vault mutation.
    """
    if not isinstance(title, str) or not title.strip():
        _safety.die(
            _json_error_envelope({
                "status": "error",
                "code": "INVALID_TITLE",
                "received": title,
                "hint": "frontmatter `title:` (or `name:`) must be a non-empty string",
            }),
            code=_safety.EXIT_USAGE,
        )
    if _TITLE_FORBIDDEN_RE.search(title):
        _safety.die(
            _json_error_envelope({
                "status": "error",
                "code": "INVALID_TITLE",
                "received": title,
                "hint": ("title contains `|`, a newline, or a `## [` "
                         "log-heading prefix — `append-log` would reject "
                         "this mid-pipeline. Clean the summary's "
                         "frontmatter before ingest."),
            }),
            code=_safety.EXIT_USAGE,
        )


def _run_pipeline(
    args, source, src_fm, course_for_writes, course_root, vault_root,
    effective_hash,
) -> tuple[list[dict], dict]:
    """Compose register-summary → upsert-page × N → update-index → append-log
    → log-event via `_dispatch.dispatch`. Each step commits independently;
    a non-zero dispatch return raises `_PartialFailure` so the caller can
    emit the partial envelope and exit 20.
    """
    cwriter = str(course_for_writes)
    slug = _safety.slugify(source.stem)
    title = _scalar(src_fm.get("title")) or _scalar(src_fm.get("name")) or source.stem
    date = _scalar(src_fm.get("date")) or datetime.today().strftime("%Y-%m-%d")
    # HIGH-2 (logic-critic 2026-05-27): pre-validate title BEFORE any
    # state-mutating dispatch. `append-log` rejects pipe / newline /
    # log-heading-spoof in title; without this guard, a bad title would
    # corrupt the vault halfway through the pipeline.
    _prevalidate_pipeline_inputs(title)
    written: list[dict] = []

    # (d) register-summary — pin BOTH slug and title so downstream
    # ops (upsert-page, update-index, append-log, log-event) and the
    # source-hash short-circuit on re-run agree on the same `_sources/
    # <slug>.md` filename. Without the explicit pin, register-summary
    # would derive its own slug from frontmatter `title:` and the
    # orchestrator's `slugify(source.stem)` would disagree.
    sources_path = course_for_writes / "_sources" / f"{slug}.md"
    existed = sources_path.is_file()
    rc = _dispatch_silent("register-summary", argparse.Namespace(
        vault=cwriter, summary_path=str(source),
        slug=slug, title=title, force=False, inbox_root=None,
        dry_run=False, cmd="register-summary",
    ))
    if rc != 0:
        raise _PartialFailure(
            "register-summary", written,
            "register-summary failed; check stderr for inbox / symlink / size violation.",
            child_exit_code=rc,
        )
    written.append(_wentry(sources_path, course_for_writes, course_root, vault_root,
                           action=("updated" if existed else "created"), kind="source"))
    # TASK 017 R9 footer write (017.07 scope): record the source hash in
    # the just-registered _sources/<slug>.md so future ingests can short-
    # circuit via --source-hash matching the recorded footer.
    _record_source_hash_footer(sources_path, effective_hash)

    # (e) upsert-page × N — concepts + entities from the now-written summary's frontmatter
    sm_fm, _ = split_frontmatter(_safety.read_text(sources_path))
    concepts = _normalise_list(sm_fm.get("concepts") if isinstance(sm_fm, dict) else None)
    entities = _normalise_list(sm_fm.get("related") if isinstance(sm_fm, dict) else None)
    new_concepts, touched_concepts, new_entities, touched_entities = [], [], [], []
    for kind, names, new_list, touched_list in (
        ("concept", concepts, new_concepts, touched_concepts),
        ("entity",  entities, new_entities, touched_entities),
    ):
        for name in names:
            target = course_for_writes / f"_{kind}s" / f"{name}.md"
            was = target.is_file()
            rc = _dispatch_silent("upsert-page", argparse.Namespace(
                vault=cwriter, kind=kind, name=name,
                source_slug=slug, source_title=title, source_date=date,
                definition=None, fact=None, contradicts=None,
                force=False, dry_run=False, cmd="upsert-page",
            ))
            if rc != 0:
                raise _PartialFailure(
                    "upsert-page", written,
                    f"upsert-page failed for {kind}={name!r}; existing pages "
                    f"already written are preserved. Inspect, then rerun or "
                    f"`wiki-ingest lint --fix`.",
                    child_exit_code=rc,
                )
            written.append(_wentry(target, course_for_writes, course_root, vault_root,
                                   action=("updated" if was else "created"), kind=kind))
            (touched_list if was else new_list).append(name)

    # (f) update-index
    summary_oneliner = (_scalar(sm_fm.get("summary"))
                        or _scalar(sm_fm.get("description")) or title)[:200] or title
    index_path = course_for_writes / "index.md"
    rc = _dispatch_silent("update-index", argparse.Namespace(
        vault=cwriter, source_slug=slug,
        source_title=title, source_date=date,
        summary=summary_oneliner,
        new_concepts=None, new_entities=None,
        new_concept=new_concepts, new_entity=new_entities,
        dry_run=False, cmd="update-index",
    ))
    if rc != 0:
        raise _PartialFailure(
            "update-index", written,
            "update-index failed; rerun after inspecting index.md.",
            child_exit_code=rc,
        )
    written.append(_wentry(index_path, course_for_writes, course_root, vault_root,
                           action="updated", kind="index"))

    # (g) append-log + capture log_md_byte_offset
    log_path = course_for_writes / "log.md"
    size_before = log_path.stat().st_size if log_path.is_file() else 0
    rc = _dispatch_silent("append-log", argparse.Namespace(
        vault=cwriter, title=title, slug=slug, source_path=str(source),
        touched=None, created=None,
        touch_name=touched_concepts + touched_entities,
        create_name=new_concepts + new_entities,
        contradictions=0, date=date,
        force_log=False, dry_run=False, cmd="append-log",
    ))
    if rc != 0:
        raise _PartialFailure(
            "append-log", written,
            "append-log failed; vault content is consistent up to this step.",
            child_exit_code=rc,
        )
    written.append(_wentry(log_path, course_for_writes, course_root, vault_root,
                           action="appended", kind="log"))
    log_md_byte_offset = _find_appended_heading_offset(log_path, size_before, date, title)

    # (g') log-event
    rc = _dispatch_silent("log-event", argparse.Namespace(
        vault=cwriter, event="ingest", title=title,
        detail=[f"source_slug={slug}"],
        date=date, dry_run=False, cmd="log-event",
    ))
    if rc != 0:
        raise _PartialFailure(
            "log-event", written,
            "log-event failed; log.md already has the human-readable entry.",
            child_exit_code=rc,
        )

    log_event = {
        "event_ts": datetime.now(timezone.utc).isoformat(),
        "event_type": "ingest",
        "subject": title,
        "log_md_byte_offset": log_md_byte_offset,
    }
    return written, log_event


def _emit_partial(head: dict, exc: _PartialFailure) -> int:
    """Q-1 partial-success envelope (exit 20).

    `child_exit_code` carries the dispatched atomic op's original exit
    code (e.g., `register-summary`'s 6=oversized, 7=symlink-overwrite,
    8=inbox-containment). Consumers (the bridge / operator CI) can
    distinguish security-class refusals from generic mid-pipeline
    failures via this field, even though the orchestrator's outer
    exit code is always 20 (`EXIT_PARTIAL`).
    """
    envelope = {
        **head,
        "status": "error",
        "phase": exc.phase,
        "code": "PARTIAL_INDEX_FAILURE",
        "child_exit_code": exc.child_exit_code,
        "written_so_far": exc.written_so_far,
        "cleanup_advice": exc.cleanup_advice,
    }
    json.dump(_safety._safe_for_json(envelope), sys.stdout)
    sys.stdout.write("\n")
    return _safety.EXIT_PARTIAL


# --- pipeline helpers --------------------------------------------------- #

def _scalar(value) -> str | None:
    """Return `value` only if it's a non-empty string; else None."""
    return value.strip() if isinstance(value, str) and value.strip() else None


def _normalise_list(value) -> list[str]:
    """Accept `concepts: foo` (str), `concepts: [a, b]` (list), or absent (None)."""
    if isinstance(value, list):
        out = [str(v).strip() for v in value if isinstance(v, (str, int, float))]
        return [v for v in out if v]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _wentry(target: Path, course_for_writes: Path, course_root, vault_root,
            *, action: str, kind: str) -> dict:
    """Build a WrittenEntry (Architecture §4.5.5) with the correct `scope`."""
    rel = target.relative_to(course_for_writes).as_posix()
    return {
        "path": rel,
        "action": action,
        "kind": kind,
        "scope": _derive_scope(target, course_root, vault_root),
    }


def _derive_scope(target: Path, course_root, vault_root) -> str:
    """`vault` when the write lands at the two-tier root layer; else `course`."""
    if vault_root is None or course_root is None or course_root == vault_root:
        return "course"
    try:
        target.relative_to(course_root)
        return "course"
    except ValueError:
        try:
            target.relative_to(vault_root)
            return "vault"
        except ValueError:
            return "course"


def _find_appended_heading_offset(log_path: Path, size_before: int,
                                  date: str, title: str) -> int:
    """Locate the byte offset of the `## [date] ingest | <title>` heading
    that `append-log` just wrote. Reads ONLY the appended chunk
    (perf-critic LOW-1 2026-05-27 — drops worst-case from O(file) to
    O(appended-chunk)). Prefers the heading whose title also matches
    (multi-ingest-per-day safety)."""
    if not log_path.is_file():
        return 0
    try:
        with log_path.open("rb") as fh:
            fh.seek(size_before)
            tail = fh.read()
    except OSError:
        return size_before
    titled = f"## [{date}] ingest | {title}".encode("utf-8")
    idx = tail.find(titled)
    if idx >= 0:
        return size_before + idx
    prefix = f"## [{date}] ingest | ".encode("utf-8")
    idx = tail.find(prefix)
    return size_before + idx if idx >= 0 else size_before


def _emit_short_circuit(
    args, source, slug, effective_hash, effective_vault_id, course_root, vault_root,
) -> int:
    """UC-4 short-circuit — recorded footer hash matches; no LLM, no writes."""
    head = _build_common_manifest_head(
        args, source, effective_hash, effective_vault_id, course_root, vault_root,
    )
    head["source"]["slug"] = slug  # use the slug we already computed
    manifest = {
        **head,
        "status": "ok",
        "action": "unchanged",
        "written": [],
        "created": [],
        "touched": [],
        "contradictions": 0,
        "summary_path": str(
            (course_root or vault_root) / "_sources" / f"{slug}.md"
        ) if (course_root or vault_root) is not None else None,
        "log_event": None,
        "llm_tokens_used": {"input": 0, "output": 0, "model": None},
    }
    return _emit(args, manifest, human_summary_lines=[
        f"Source: {source}",
        f"Already ingested (source-hash matches). No writes.",
    ])


def _emit(args, manifest: dict, *, human_summary_lines: list[str]) -> int:
    """Dispatch to JSON vs human output; honour --quiet + TTY check."""
    quiet = _should_be_quiet(args)
    if args.output_format == "json":
        json.dump(_safety._safe_for_json(manifest), sys.stdout)
        sys.stdout.write("\n")
    elif not quiet:
        for line in human_summary_lines:
            print(line)
    return _safety.EXIT_OK


def _should_be_quiet(args) -> bool:
    """`--quiet` OR stdout not a TTY (subprocess piping) → suppress human chrome."""
    if args.quiet:
        return True
    try:
        return not os.isatty(sys.stdout.fileno())
    except (io.UnsupportedOperation, OSError, ValueError):
        # Captured streams (StringIO etc.) lack fileno → treat as piped.
        return True


def _json_error_envelope(payload: dict) -> str:
    """`die()`-compatible JSON envelope for exits 23/24/25 + INVALID_SOURCE_HASH."""
    return json.dumps(_safety._safe_for_json(payload), ensure_ascii=False)
