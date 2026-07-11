"""TASK 058 — doctor/fix: finding → mechanical repair plan → tiered application.

Tier semantics (from the taxonomy): SAFE plans apply on bare `fix`; CONFIRM
plans need `--yes` (bare `fix` applies SAFE, lists CONFIRM, exits 7); MANUAL is
never applied by machine. Every text mutation goes through the `_edit.rewrite_text`
sandwich — a verification failure DOWNGRADES the file's plans to manual and
writes nothing (`fix_downgraded`). Every mutation of an existing file takes a
`.wiki/backups/` backup first and is TOCTOU-guarded (sha256 pinned at plan/read
time, re-checked immediately before the atomic replace).

Envelopes are value-free (CWE-209/117): diffs and removed content appear ONLY
in the `--report` markdown sidecar, never on stdout.
"""

from __future__ import annotations

import difflib
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from scripts.wiki_index.sync_config import SyncConfigError, _load_validated_raw

from ._backups import WikiDirSymlinkError, ensure_wiki_writable, write_backup
from ._edit import (
    EditDowngrade,
    PointerEdit,
    gate_text,
    parse_text_no_schema,
    rewrite_text,
)
from ._findings import TIER_CONFIRM, TIER_SAFE, ConfigFinding
from scripts.wiki_skills._common import atomic_write_text

# Anchor/alias expansion bounds (a billion-laughs file must never be "fixed").
_EXPAND_MAX_BYTES = 8 * 1024
_EXPAND_MAX_MARKS = 32


@dataclass(frozen=True)
class FixPlan:
    plan_id: str
    finding: ConfigFinding
    kind: str  # edit | delete-file | rmdir | expand-anchors
    edits: tuple[PointerEdit, ...] = ()
    description: str = ""
    comments_lost: bool = False

    @property
    def tier(self) -> str:
        return self.finding.kind.tier

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.plan_id,
            "code": self.finding.code,
            "file": self.finding.file,
            "pointer": self.finding.pointer,
            "tier": self.tier,
            "fix": self.kind if self.kind != "edit" else self.edits[0].op,
            "description": self.description,
            "comments_lost": self.comments_lost,
        }


@dataclass
class FileResult:
    file: str
    status: str = "ok"  # ok | confirm-required | drifted | failed | manual | dry-run
    applied: list[dict[str, Any]] = field(default_factory=list)
    proposed: list[dict[str, Any]] = field(default_factory=list)
    manual: list[str] = field(default_factory=list)
    backup: str | None = None
    result_hash: str | None = None
    fix_downgraded: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "file": self.file, "status": self.status,
            "applied": self.applied, "proposed": self.proposed,
            "manual": self.manual, "backup": self.backup,
            "result_hash": self.result_hash,
            "fix_downgraded": self.fix_downgraded,
        }


def _sync_path(vault_root: Path, file_rel: str) -> Path:
    return vault_root / file_rel


def _folder_of_sync_file(vault_root: Path, file_rel: str) -> Path:
    # "<label>/.wiki/sync.yaml" → vault_root/<label>
    return (vault_root / file_rel).parent.parent


def _raw_of(vault_root: Path, file_rel: str) -> dict[str, Any] | None:
    try:
        return parse_text_no_schema(
            _sync_path(vault_root, file_rel).read_text(encoding="utf-8"))
    except (OSError, SyncConfigError):
        return None


def _value_at(raw: dict[str, Any], pointer: str) -> Any:
    cur: Any = raw
    for part in [p for p in pointer.split("/") if p]:
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def build_plans(
    findings: list[ConfigFinding], vault_root: Path
) -> tuple[list[FixPlan], list[ConfigFinding]]:
    """Map fixable findings to mechanical plans; the rest stay manual."""
    plans: list[FixPlan] = []
    manual: list[ConfigFinding] = []
    raw_cache: dict[str, dict[str, Any] | None] = {}

    def raw_for(file_rel: str) -> dict[str, Any] | None:
        if file_rel not in raw_cache:
            raw_cache[file_rel] = _raw_of(vault_root, file_rel)
        return raw_cache[file_rel]

    for finding in findings:
        # Stable across runs while the finding itself persists — the serve UI
        # round-trips these ids into POST /api/fix.
        plan_id = f"{finding.code}:{finding.file}:{finding.pointer}"
        code = finding.code
        if finding.kind.tier == "manual" or finding.system != "sync":
            manual.append(finding)
            continue
        if code == "MIRROR_EXT_NO_DOT":
            raw = raw_for(finding.file)
            value = _value_at(raw or {}, finding.pointer)
            if not isinstance(value, str):
                manual.append(finding)
                continue
            plans.append(FixPlan(plan_id, finding, "edit",
                                 (PointerEdit("set", finding.pointer, "." + value),),
                                 "prepend the missing '.' to summary_ext"))
        elif code == "DUPLICATE_LIST_ITEM":
            plans.append(FixPlan(plan_id, finding, "edit",
                                 (PointerEdit("dedupe-list", finding.pointer),),
                                 "drop duplicate list entries (first occurrence kept)"))
        elif code == "GROUP_KEY_NO_CAPTURE":
            raw = raw_for(finding.file)
            value = _value_at(raw or {}, finding.pointer)
            if not isinstance(value, str):
                manual.append(finding)
                continue
            plans.append(FixPlan(plan_id, finding, "edit",
                                 (PointerEdit("set", finding.pointer, f"({value})"),),
                                 "wrap the pattern in (...) — behavior-identical"))
        elif code == "MIRROR_REGEX_DOUBLE_ESCAPE":
            raw = raw_for(finding.file)
            value = _value_at(raw or {}, finding.pointer)
            if not isinstance(value, str):
                manual.append(finding)
                continue
            plans.append(FixPlan(plan_id, finding, "edit",
                                 (PointerEdit("set", finding.pointer,
                                              value.replace("\\\\", "\\")),),
                                 "collapse the doubled backslash to the intended "
                                 "character class"))
        elif code == "UNKNOWN_KEY_TYPO":
            suggestion = finding.data.get("suggestion")
            if not isinstance(suggestion, str):
                manual.append(finding)
                continue
            plans.append(FixPlan(plan_id, finding, "edit",
                                 (PointerEdit("rename-key", finding.pointer,
                                              new_key=suggestion),),
                                 f"rename the key to '{suggestion}' "
                                 "(value subtree preserved verbatim)"))
        elif code == "UNKNOWN_KEY":
            plans.append(FixPlan(plan_id, finding, "edit",
                                 (PointerEdit("unset", finding.pointer),),
                                 "delete the unknown key (backup keeps the original)"))
        elif code == "SCHEMA_VIOLATION_ENUM":
            suggestion = finding.data.get("suggestion")
            if not isinstance(suggestion, str):
                manual.append(finding)
                continue
            plans.append(FixPlan(plan_id, finding, "edit",
                                 (PointerEdit("set", finding.pointer, suggestion),),
                                 f"replace the value with '{suggestion}'"))
        elif code == "NON_CASCADING_KEY_IN_SUBFOLDER":
            keys = finding.data.get("keys") or []
            edits = tuple(PointerEdit("unset", f"/{k}") for k in keys)
            if not edits:
                manual.append(finding)
                continue
            plans.append(FixPlan(plan_id, finding, "edit", edits,
                                 "delete the ignored root-only key(s) from this "
                                 "subfolder file (re-add at the vault root "
                                 "deliberately if wanted; backup keeps them)",
                                 comments_lost=True))
        elif code == "REDUNDANT_OVERRIDE":
            plans.append(FixPlan(plan_id, finding, "edit",
                                 (PointerEdit("unset", finding.pointer),),
                                 "remove the override that is identical to the "
                                 "inherited value (un-pins the folder from future "
                                 "parent edits — hence confirm)"))
        elif code == "EMPTY_FILE":
            plans.append(FixPlan(plan_id, finding, "delete-file", (),
                                 "delete the empty config file (≡ absent)"))
        elif code == "ORPHAN_WIKI_DIR":
            plans.append(FixPlan(plan_id, finding, "rmdir", (),
                                 "remove the vestigial empty .wiki directory"))
        elif code in ("YAML_ALIAS_BANNED", "YAML_ANCHOR_BANNED"):
            plans.append(FixPlan(plan_id, finding, "expand-anchors", (),
                                 "inline-expand the anchors/aliases (bounded; "
                                 "comments are NOT preserved — backup keeps the "
                                 "original)", comments_lost=True))
        elif code in ("SCHEMA_MODELINE_MISSING", "SCHEMA_MODELINE_STALE"):
            plans.append(FixPlan(plan_id, finding, "modeline", (),
                                 "insert/refresh the yaml-language-server "
                                 "modeline (line 1 only; content untouched)"))
        else:
            manual.append(finding)
    return plans, manual


def _apply_modeline(text: str) -> str:
    """Insert or refresh the schema modeline as line 1; the parsed content must
    be untouched (comment-only change — verified by the caller)."""
    from ._templates import MODELINE_PREFIX, modeline

    lines = text.splitlines(keepends=True)
    new_line = modeline() + "\n"
    if lines and lines[0].startswith(MODELINE_PREFIX):
        lines[0] = new_line
    else:
        lines.insert(0, new_line)
    return "".join(lines)


def _unshare(value: Any) -> Any:
    """Rebuild containers WITHOUT shared identities: after `safe_load` an alias
    is the SAME object as its anchor, and `safe_dump` would re-emit `&id001`/
    `*id001` for it — defeating the expansion. Fresh containers per site."""
    if isinstance(value, dict):
        return {k: _unshare(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_unshare(v) for v in value]
    return value


def _expand_anchors_text(text: str) -> str:
    """Bounded anchor/alias expansion: refuse anything that could amplify."""
    if len(text.encode("utf-8")) > _EXPAND_MAX_BYTES:
        raise EditDowngrade("file too large for bounded anchor expansion")
    if text.count("&") + text.count("*") > _EXPAND_MAX_MARKS:
        raise EditDowngrade("too many anchor/alias marks for bounded expansion")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise EditDowngrade("cannot parse for anchor expansion") from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise EditDowngrade("top level must be a mapping")
    rendered = yaml.safe_dump(_unshare(data), sort_keys=False, allow_unicode=True,
                              default_flow_style=False)
    try:
        gate_text(rendered)  # must be fully valid once expanded
    except SyncConfigError as exc:
        raise EditDowngrade(
            f"expanded config fails the hardened gate ({exc.reason})") from exc
    return rendered


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def apply_plans(
    vault_root: Path,
    plans: list[FixPlan],
    *,
    yes: bool,
    dry_run: bool,
    no_backup: bool,
    expected_hashes: dict[str, str] | None = None,
) -> tuple[list[FileResult], list[tuple[str, str, str]], int]:
    """Apply SAFE (always) + CONFIRM (with `yes`) plans, grouped per file.

    Returns (per-file results, report diffs [(file, before, after)], exit code).
    `expected_hashes` (from a `--from-plan` sidecar) is an ALL-OR-NOTHING
    pre-check: any drift → exit 2, zero writes."""
    results: dict[str, FileResult] = {}
    diffs: list[tuple[str, str, str]] = []

    def result_for(file_rel: str) -> FileResult:
        if file_rel not in results:
            results[file_rel] = FileResult(file=file_rel)
        return results[file_rel]

    # --from-plan all-or-nothing drift pre-check, BEFORE any write.
    if expected_hashes:
        for file_rel, expected in expected_hashes.items():
            target = _sync_path(vault_root, file_rel)
            try:
                actual = _sha256_text(target.read_text(encoding="utf-8"))
            except OSError:
                actual = ""
            if actual != expected:
                res = result_for(file_rel)
                res.status = "drifted"
                return list(results.values()), diffs, 2

    by_file: dict[str, list[FixPlan]] = {}
    for plan in plans:
        by_file.setdefault(plan.finding.file, []).append(plan)

    any_failed = False
    any_proposed = False
    for file_rel, file_plans in sorted(by_file.items()):
        res = result_for(file_rel)
        applicable = [p for p in file_plans
                      if p.tier == TIER_SAFE or (yes and p.tier == TIER_CONFIRM)]
        deferred = [p for p in file_plans if p not in applicable]
        for plan in deferred:
            res.proposed.append(plan.to_json())
            any_proposed = True
        if not applicable:
            res.status = "confirm-required" if deferred else "manual"
            continue
        if dry_run:
            res.status = "dry-run"
            res.applied = [p.to_json() for p in applicable]
            continue

        kinds = {p.kind for p in applicable}
        if kinds == {"rmdir"}:
            try:
                (vault_root / file_rel).rmdir()
                res.applied = [p.to_json() for p in applicable]
            except OSError:
                res.status = "failed"
                any_failed = True
            continue
        if kinds == {"delete-file"}:
            folder = _folder_of_sync_file(vault_root, file_rel)
            try:
                ensure_wiki_writable(folder, vault_root)
            except WikiDirSymlinkError:
                res.status = "failed"
                any_failed = True
                continue
            if not no_backup:
                res.backup = write_backup(folder)
            try:
                _sync_path(vault_root, file_rel).unlink()
                res.applied = [p.to_json() for p in applicable]
            except OSError:
                res.status = "failed"
                any_failed = True
            continue

        target = _sync_path(vault_root, file_rel)
        try:
            before = target.read_text(encoding="utf-8")
        except OSError:
            res.status = "failed"
            any_failed = True
            continue
        try:
            if kinds == {"expand-anchors"}:
                after = _expand_anchors_text(before)
            else:
                work = before
                if any(p.kind == "modeline" for p in applicable):
                    work = _apply_modeline(work)
                    if parse_text_no_schema(work) != parse_text_no_schema(before):
                        raise EditDowngrade("modeline change altered the content")
                edits = [e for p in applicable if p.kind == "edit" for e in p.edits]
                if edits:
                    schema_broken = any(
                        p.finding.code in ("UNKNOWN_KEY", "UNKNOWN_KEY_TYPO",
                                           "SCHEMA_VIOLATION_ENUM",
                                           "NON_CASCADING_KEY_IN_SUBFOLDER")
                        for p in applicable)
                    after = rewrite_text(work, edits,
                                         require_schema_before=not schema_broken)
                else:
                    after = work
        except (EditDowngrade, SyncConfigError):
            res.status = "manual"
            res.fix_downgraded = True
            res.manual = [p.finding.code for p in applicable]
            continue

        folder = _folder_of_sync_file(vault_root, file_rel)
        try:
            ensure_wiki_writable(folder, vault_root)
        except WikiDirSymlinkError:
            res.status = "failed"
            any_failed = True
            continue
        # TOCTOU FIRST: the file must still be what we planned against — a
        # drift-aborted op must not consume a backup KEEP slot.
        try:
            if target.read_text(encoding="utf-8") != before:
                res.status = "drifted"
                continue
        except OSError:
            res.status = "failed"
            any_failed = True
            continue
        if not no_backup:
            res.backup = write_backup(folder)
        atomic_write_text(target, after)
        try:
            _load_validated_raw(folder)
        except SyncConfigError:
            # Post-write validation failed (should be impossible after the
            # sandwich): restore the just-taken backup, report failed.
            if res.backup:
                atomic_write_text(target, before)
            res.status = "failed"
            any_failed = True
            continue
        res.applied = [p.to_json() for p in applicable]
        res.result_hash = _sha256_text(after)
        diffs.append((file_rel, before, after))

    exit_code = 0
    if any_failed:
        exit_code = 5
    elif any_proposed and not yes:
        exit_code = 7
    elif any(r.status == "drifted" for r in results.values()):
        exit_code = 2
    return list(results.values()), diffs, exit_code


def render_fix_report(
    plans: list[FixPlan],
    manual: list[ConfigFinding],
    diffs: list[tuple[str, str, str]],
    vault_root_label: str,
) -> str:
    """The value-BEARING side: proposed/applied unified diffs live here only."""
    lines = [f"# wiki-config doctor — `{vault_root_label}`", ""]
    if plans:
        lines += ["## Fix plans", ""]
        for plan in plans:
            lines.append(f"- `{plan.plan_id}` **{plan.finding.code}** "
                         f"({plan.tier}) `{plan.finding.file}`"
                         f"{' `' + plan.finding.pointer + '`' if plan.finding.pointer else ''}"
                         f" — {plan.description}")
    if manual:
        lines += ["", "## Manual findings", ""]
        for finding in manual:
            lines.append(f"- **{finding.code}** `{finding.file}` — {finding.message}")
    for file_rel, before, after in diffs:
        lines += ["", f"## Diff — `{file_rel}`", "", "```diff"]
        lines += [line.rstrip("\n") for line in difflib.unified_diff(
            before.splitlines(keepends=True), after.splitlines(keepends=True),
            fromfile=f"a/{file_rel}", tofile=f"b/{file_rel}")]
        lines.append("```")
    return "\n".join(lines) + "\n"
