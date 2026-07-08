"""`wiki-sync scan` CLI — the deterministic, plan-only front of the format-aware,
tag-routed ingest dispatcher (TASK 018 / R-11).

Decision-17: this module is pure Python plumbing — it walks a zone, classifies
each file, and emits a strict **plan JSON**. It performs NO LLM call, NO network,
and NO filesystem mutation (it only reads). The plan is executed by the
orchestrator recipe `workflows/wiki-sync.md` (convert / de-timestamp / H-6-fence
/ summarise / enrich / extract / upsert / skip). It carries no LLM-client
import (Decision-17; grep-guarded).

`scan <zone>`:
  walk (`_sync.iter_sync_candidates`) → classify (`_sync.classify_file`) →
  `source_hash = sha256(bytes)` → `is_unchanged` via the `wiki-sync`-owned
  `source_state` partition (`get_source_state(vault_id,'sync',rel,'source_hash')`)
  → strict plan `{vault_id, zone, generated_by, entries[], summary{}}` with
  `entries[]` sorted by vault-relative POSIX path (determinism, AC-10).

Exit codes: `0` ok · `2` precondition (zone missing / outside vault / no vault
root) · `6` config-invalid (`.wiki/sync.yaml`). Error envelopes never echo
untrusted content (CWE-209/CWE-117).

Bead 12 (STUB): the CLI shell + precondition wiring emits a HARDCODED EMPTY plan.
Bead 13 (LOGIC) wires the walk/classify/hash/idempotency.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
import sys
from pathlib import Path, PurePosixPath
from typing import Any

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout_config import resolve_layout_config
from scripts.wiki_index.repository import IndexRepository
from scripts.wiki_index.security import PathTraversalError, validate_inside_vault
from scripts.wiki_index.sync_config import SyncConfig, SyncConfigError, load_sync_config
from scripts.wiki_skills._sync import (
    Decision,
    classify_file,
    iter_sync_candidates,
    transcript_variant_skips,
)
from scripts.wiki_skills._resummarize import (
    ACTIONABLE,
    Caches,
    apply_policy,
    resolve_policy,
    resolve_summarize,
)
from scripts.wiki_skills._common import (
    build_repo_config,
    emit,
    resolve_vault_root_for_cli,
)

GENERATED_BY = "wiki-sync/scan"
_HASH_CHUNK = 65536
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _is_clean_rel(rel: str) -> bool:
    """A canonical, non-empty vault-relative POSIX path: no absolute root, no
    `..`/`.` segment, no NUL/control char, no backslash, no trailing slash. The
    scope key must round-trip exactly with a `scan`-produced `rel` or the
    idempotency marker silently never matches (critic-security LOW)."""
    if not rel or rel.startswith("/") or rel.endswith("/"):
        return False
    if "\\" in rel or any(ord(c) < 32 for c in rel):  # backslash + NUL/control
        return False
    pp = PurePosixPath(rel)
    if not pp.parts:          # "." / "" normalise to no parts → not a real file
        return False
    if pp.is_absolute() or ".." in pp.parts or "." in pp.parts:
        return False
    # canonical: re-serialising the parts must reproduce the input exactly.
    return pp.as_posix() == rel


def _empty_summary() -> dict[str, int]:
    return {"total": 0, "convert+ingest": 0, "ingest": 0,
            "upsert": 0, "skip": 0, "unchanged": 0}


def scan(args: argparse.Namespace) -> int:
    # TASK 022: resolve vault_root (flag → cwd walk-up) BEFORE make_repo so a
    # vault-local index_db is honoured; the chain is --db-path > index_db > global.
    vault_root = resolve_vault_root_for_cli(args)
    config = build_repo_config(args.vault, vault_root=vault_root, db_path_flag=args.db_path)
    try:
        repo = make_repo(config)
    except ValueError:
        # bad/missing vault_id format — never echo the value (CWE-209).
        return emit({"error": "INVALID_VAULT", "field": "vault",
                     "reason": "vault_id missing or malformed"}, 2)

    try:
        if vault_root is None:
            # global vault addressed by id from outside → derive root from the DB.
            v = repo.get_vault(args.vault)
            vault_root = Path(v.root_path) if v is not None else None
        if vault_root is None:
            return emit({"error": "INVALID_VAULT_ROOT", "field": "vault-root",
                         "reason": "vault not registered; pass --vault-root"}, 2)
        vault_root = vault_root.resolve()
        if not vault_root.is_dir():
            return emit({"error": "INVALID_VAULT_ROOT", "field": "vault-root",
                         "reason": "vault root is not a directory"}, 2)

        # Resolve the zone: a relative zone is joined to the vault root.
        zone_arg = Path(args.zone)
        zone = (zone_arg if zone_arg.is_absolute() else (vault_root / zone_arg)).resolve()
        # Existence check FIRST — `validate_inside_vault` uses `resolve(strict=True)`
        # and would raise FileNotFoundError (not PathTraversalError) on a missing zone.
        if not zone.is_dir():
            return emit({"error": "ZONE_NOT_FOUND", "field": "zone",
                         "reason": "zone does not exist or is not a directory"}, 2)
        try:
            zone = validate_inside_vault(zone, vault_root)
        except PathTraversalError:
            return emit({"error": "ZONE_OUTSIDE_VAULT", "field": "zone",
                         "reason": "zone resolves outside the vault root"}, 2)

        # `.wiki/sync.yaml` (optional) — INVALID_SYNC_CONFIG → exit 6.
        # `.wiki/sync.yaml` (optional) AND any per-folder `resummarize:` override
        # the cascade resolver reads inside `_build_entries` (TASK 019) — BOTH map
        # an invalid config to exit 6, never a traceback/CWE-209 leak.
        try:
            config_obj = load_sync_config(vault_root)
            layout = resolve_layout_config(vault_root)
            entries = _build_entries(
                repo, args.vault, zone, vault_root, config_obj, layout,
                force=args.force)
        except SyncConfigError as exc:
            return emit({"error": exc.code, "field": "sync-config",
                         "reason": exc.detail}, 6)
        plan: dict[str, Any] = {
            "vault_id": args.vault,
            "zone": _safe_zone_rel(zone, vault_root),
            "generated_by": GENERATED_BY,
            "entries": entries,
            "summary": _summarize(entries),
        }
        if args.dry_run:
            return _emit_dry_run(plan)
        return emit(plan, 0)
    finally:
        repo.close()


def _build_entries(
    repo: IndexRepository, vault_id: str, zone: Path, vault_root: Path,
    config: SyncConfig, layout: Any, force: bool = False,
) -> list[dict[str, Any]]:
    """Walk → classify → **re-summarization gate** (TASK 019) → hash (actionable
    only) → idempotency. Deterministic: NO timestamp; `entries[]` sorted by
    vault-relative POSIX path (AC-10). The gate (`apply_policy`) is monotone — it
    can only turn an `ingest`/`convert+ingest` into a `skip`; `policy=None` (no
    `resummarize:` block at any level) is a no-op (back-compat / AC-7). The policy
    is resolved per file via the per-folder cascade, memoized per directory."""
    entries: list[dict[str, Any]] = []
    caches = Caches()  # per-scan memo: resolved policy / D2a citation set / D2b key index
    cands = list(iter_sync_candidates(zone, vault_root=vault_root, config=config))
    # TASK 023 — transcript FORMAT dedup (opt-in): demote redundant caption/transcript
    # variants (e.g. ID.ru.vtt / ID.ru-orig.vtt when ID.ru.txt exists) to skip BEFORE
    # the re-summarization gate, so only the preferred format is ever ingested. A lone
    # caption with no higher-preference sibling is untouched (still ingested). `--force`
    # re-arms only the PREFERRED format (a variant skip is not ACTIONABLE → unaffected).
    dedup = config.transcript_dedup
    variant_skips = (
        transcript_variant_skips(
            cands, prefer_ext=dedup.prefer_ext, identity_mode=dedup.identity)
        if dedup is not None and dedup.enabled else {}
    )
    for cand in cands:
        d: Decision = classify_file(
            cand.path, vault_root=vault_root, config=config, layout=layout,
            in_raw=cand.in_raw, in_exclude_zone=cand.in_exclude_zone,
        )
        if cand.rel in variant_skips and d.action in ACTIONABLE:
            d = Decision(
                action="skip",
                reason=f"transcript-variant:{variant_skips[cand.rel]}",
            )
        policy = resolve_policy(cand.path, vault_root=vault_root, caches=caches)
        # TASK 051 (R-18 / Q-051-1): HOIST the file hash for ACTIONABLE candidates
        # AHEAD of the gate so `apply_policy`'s `if-changed` mode can compare it
        # against the recorded `source_state` marker — and REUSE the single value
        # for the executor `is_unchanged`/`source_hash` record below (no double
        # read). Scoped to `if-changed` (the ONLY mode that reads `current_hash`):
        # under `if-missing`/`always`/`never` a gated-to-skip ACTIONABLE raw must
        # NOT incur a pre-gate read it avoided pre-051 — those paths hash lazily in
        # the record block (fallback), byte-identically to before. `upsert`/`skip`
        # are non-ACTIONABLE → also lazy. `None` (unreadable/vanished) flows through
        # unchanged (gate and record both treat it as "not unchanged").
        source_hash: str | None = None
        if d.action in ACTIONABLE and policy is not None \
                and policy.mode == "if-changed":
            source_hash = _hash_file(cand.path)
        d = apply_policy(
            d, path=cand.path, rel=cand.rel, vault_root=vault_root,
            repo=repo, vault_id=vault_id, policy=policy, force=force, caches=caches,
            current_hash=source_hash,
        )
        entry: dict[str, Any] = {
            "path": cand.rel, "action": d.action, "reason": d.reason,
            "converter": d.converter, "staged_target": d.staged_target,
            "normalize": d.normalize,
        }
        # TASK 046 P2: the distil actions (ingest / convert+ingest) are DELEGATED to wiki-import —
        # the single per-source engine that owns convert + REASON + file + index. The executor
        # runs wiki-import per `delegate` instead of inline summarise/enrich/extract (R-9); the
        # classifier's converter/normalize stay only as the DETECTED-format hint (wiki-import
        # prepare re-detects). The kind/diagrams/concepts knobs DEFAULT here (back-compat:
        # auto-detect kind, no diagrams, concepts ON) and are populated from the per-folder
        # `.wiki/sync.yaml` `summarize:` block in P3.
        if d.action in ACTIONABLE:
            sm = resolve_summarize(cand.path, vault_root=vault_root, caches=caches)
            folder = _delegate_folder(cand.rel)
            if sm.target_subdir:
                folder = sm.target_subdir if folder == "." else f"{folder}/{sm.target_subdir}"
            entry["delegate"] = {
                "tool": "wiki-import",
                "source": cand.rel,
                "folder": folder,
                "kind": sm.profile,            # profile == wiki-import --kind (auto/meeting/lesson/article)
                "diagrams": sm.diagrams,
                "concepts": sm.extract_concepts,
            }
        if d.action != "skip":
            # Reuse the hoisted hash for ACTIONABLE; a non-ACTIONABLE non-skip
            # (`upsert`/ready-note) was NOT hoisted, so hash it once here (TASK 051
            # fallback — plan 051-03; never a double read).
            if source_hash is None:
                source_hash = _hash_file(cand.path)
            entry["source_hash"] = source_hash
            # A `None` hash (file vanished / unreadable between walk and hash —
            # TOCTOU) must NEVER read as `is_unchanged`: `None == None` would
            # otherwise mark a never-synced, failed-to-hash file as a no-op and
            # the executor would silently skip actionable content (critic-logic
            # MED). Require a real hash that matches the recorded marker.
            entry["is_unchanged"] = (
                source_hash is not None
                and repo.get_source_state(vault_id, "sync", cand.rel, "source_hash")
                == source_hash
            )
        else:
            entry["source_hash"] = None
            entry["is_unchanged"] = False
        entries.append(entry)
    entries.sort(key=lambda e: str(e["path"]))
    return entries


# Raw/source-machinery dir names trimmed when resolving a delegate's topic folder. Covers the
# `mirror.raw_dirs` defaults (`_raw`, `_transcripts`) + the `_raw/.staging` scratch dir — so a
# source under ANY of them files its summary in the TOPIC folder, not inside the raw tree.
_RAW_DIR_NAMES = frozenset({"_raw", ".staging", "_transcripts"})


def _delegate_folder(rel: str) -> str:
    """Target topic folder for a delegated wiki-import (TASK 046 P2): the topic folder ABOVE all
    raw/source machinery — so the summary note (and wiki-import's own `_raw/<slug>.md` capture)
    land in the topic folder, never INSIDE a `_raw/`/`_transcripts/` tree. We trim from the FIRST
    raw-machinery segment onward (not just the immediate parent): a source nested under a grouping
    subdir like `<topic>/_raw/<group>/x.vtt` (or `<topic>/_transcripts/x.txt`) still resolves to
    `<topic>`, else its capture lands in the raw tree and the next scan re-ingests it (re-ingest
    loop, P2 review) / the summary is mis-filed (TASK 046 P3 dogfood). A vault-root source → `.`."""
    segs: list[str] = []
    for seg in PurePosixPath(rel).parent.parts:
        if seg in _RAW_DIR_NAMES:
            break
        segs.append(seg)
    return PurePosixPath(*segs).as_posix() if segs else "."


def _hash_file(path: Path) -> str | None:
    """sha256 of the file's *bytes* (the original binary, for `convert+ingest`).
    Streamed in chunks — bounded read (zones scoped; binaries pruned pre-walk)."""
    h = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(_HASH_CHUNK), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def _summarize(entries: list[dict[str, Any]]) -> dict[str, int]:
    summary = _empty_summary()
    summary["total"] = len(entries)
    for e in entries:
        action = str(e["action"])
        summary[action] = summary.get(action, 0) + 1
        if e.get("is_unchanged"):
            summary["unchanged"] += 1
    return summary


def _safe_zone_rel(zone: Path, vault_root: Path) -> str:
    try:
        rel = zone.relative_to(vault_root).as_posix()
    except ValueError:
        return zone.name
    return rel or "."


def _emit_dry_run(plan: dict[str, Any]) -> int:
    """Human-readable report (writes nothing). Lists EVERY entry (incl. every
    skip + its reason — AC-13) then the summary counts."""
    lines = [f"wiki-sync scan (dry-run) — vault={plan['vault_id']} zone={plan['zone']}"]
    for e in plan["entries"]:
        flag = " [unchanged]" if e.get("is_unchanged") else ""
        # TASK 046 P2: a delegated distil entry shows where wiki-import files it (delegate.folder),
        # NOT the classifier's staged_target (a `_raw/.staging/...` path that is no longer written —
        # conversion moved into wiki-import prepare). Non-delegated entries keep the old arrow.
        deleg = e.get("delegate")
        if deleg:
            extra = f" -> wiki-import:{deleg.get('folder', '.')}"
        elif e.get("staged_target"):
            extra = f" -> {e['staged_target']}"
        else:
            extra = ""
        lines.append(f"  {e['action']:<14} {e['path']}  — {e['reason']}{flag}{extra}")
    summary = plan["summary"]
    lines.append(
        "summary: "
        + " ".join(f"{k}={summary[k]}" for k in
                   ("total", "convert+ingest", "ingest", "upsert", "skip", "unchanged"))
    )
    print("\n".join(lines), file=sys.stdout)
    return 0


def record(args: argparse.Namespace) -> int:
    """The executor's post-success **commit marker** (bead 14). Writes the
    `wiki-sync` `source_state` row (`source_kind='sync'`, scope=vault-rel path,
    key='source_hash') so the next `scan` short-circuits the file as
    `is_unchanged`. Called by `workflows/wiki-sync.md` ONLY after a *full*
    per-file ingest/upsert succeeds — a partial failure records nothing, so the
    file is re-planned next run (Q-018-8). No raw SQL in the orchestrator: this
    is the DAL access path (NFR-2)."""
    if not _HEX64.match(args.source_hash or ""):
        return emit({"error": "INVALID_HASH", "field": "source-hash",
                     "reason": "expected a 64-char lowercase sha256"}, 2)
    rel = (args.path or "").strip()
    if not _is_clean_rel(rel):
        return emit({"error": "INVALID_PATH", "field": "path",
                     "reason": "expected a clean vault-relative path"}, 2)
    config = build_repo_config(
        args.vault, vault_root=resolve_vault_root_for_cli(args), db_path_flag=args.db_path)
    try:
        repo = make_repo(config)
    except ValueError:
        return emit({"error": "INVALID_VAULT", "field": "vault",
                     "reason": "vault_id missing or malformed"}, 2)
    try:
        try:
            repo.set_source_state(args.vault, "sync", rel, "source_hash", args.source_hash)
        except sqlite3.IntegrityError:
            return emit({"error": "VAULT_NOT_REGISTERED", "field": "vault",
                         "reason": "vault not registered (FK)"}, 2)
        return emit({"status": "recorded", "path": rel}, 0)
    finally:
        repo.close()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wiki-sync")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser(
        "scan", help="Deterministic plan-only walk → classify → plan JSON.")
    sp.add_argument("zone", help="Zone to scan (vault-relative or absolute, inside the vault).")
    sp.add_argument("--vault", required=True)
    sp.add_argument("--vault-root", default=None,
                    help="Vault root. Derived from the registered vault when omitted.")
    sp.add_argument("--dry-run", action="store_true",
                    help="Print a human report of the plan; write nothing.")
    sp.add_argument("--force", action="store_true",
                    help="Re-summarise raw sources even if a summary exists "
                         "(bypass the resummarize policy + detectors).")
    sp.add_argument("--db-path", default=None)
    sp.set_defaults(func=scan)

    rp = sub.add_parser(
        "record", help="Executor commit-marker: record a successful per-file sync.")
    rp.add_argument("path", help="Vault-relative POSIX path of the synced source.")
    rp.add_argument("--source-hash", required=True, help="sha256 of the source bytes (from the plan).")
    rp.add_argument("--vault", required=True)
    rp.add_argument("--vault-root", default=None,
                    help="Vault root (resolve a local index_db). Walks up from CWD when omitted.")
    rp.add_argument("--db-path", default=None)
    rp.set_defaults(func=record)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    func = args.func
    return int(func(args))


if __name__ == "__main__":
    sys.exit(main())
