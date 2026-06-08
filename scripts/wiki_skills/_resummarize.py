"""TASK 019 — the `wiki-sync` re-summarization policy: resolver + detectors + gate.

A **monotone** gate: it can only turn an `ingest`/`convert+ingest` `Decision` into a
`skip` — never the reverse, never touching `upsert`/`skip` (Q-019-1). Three pieces:

  * `resolve_policy` — the per-folder **Option-A cascade** (Q-019-3): merge the
    vault-root + every `<ancestor>/.wiki/sync.yaml` `resummarize:` block
    **deepest-wins**, on the RAW dicts (so a partial folder override that sets only
    `mode` correctly INHERITS the parent's `detect`), then parse once.
  * `summary_exists` — "summary exists" = D1 (`source_state`) ∪ D2a (provenance) ∪
    D2b (mirror) (Q-019-4), cheapest-first short-circuit.
  * `apply_policy` — the gate: `mode` (if-missing/always/never) + `--force`.

A per-scan `Caches` (built in `wiki_sync._build_entries`) hoists the expensive work
out of the per-file loop (vdd-multi PERF): the resolved policy is memoized per parent
dir; the D2a citation set per `(fields, match)`; the D2b summary-key index per scope.
Operator mirror regexes are ReDoS-gated at first use (`_assert_mirror_regexes`, reusing
`layout_config.is_pattern_redos_safe`) AND under a per-call `regex` deadline.

Acyclic: imports `Decision` from `_sync`; `_sync` does NOT import this module.
"""

from __future__ import annotations

import logging
import string
import time
import unicodedata
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any

import scripts.wiki_index.layout_config as _lc
from scripts.wiki_index.config_loader import deep_merge
from scripts.wiki_index.layout_config import guarded_search
from scripts.wiki_index.repository import IndexRepository
from scripts.wiki_index.security import PathTraversalError, validate_inside_vault
from scripts.wiki_index.sync_config import (
    MirrorConfig,
    ResummarizeConfig,
    SyncConfigError,
    _parse_resummarize,
    load_resummarize_raw,
)
from scripts.wiki_skills._sync import Decision

_LOG = logging.getLogger("wiki_sync.resummarize")

# Only these actions are gated — the monotonicity invariant (Q-019-1).
ACTIONABLE = frozenset({"ingest", "convert+ingest"})

# D2b default group-key: the leading integer (lesson/module number / date prefix).
_DEFAULT_GROUP_KEY = r"^(\d+)"


@dataclass
class Caches:
    """Per-scan memo (vdd-multi PERF): one instance threaded through a whole
    `_build_entries` run so the gate's expensive work runs once, not per file.
      * `raw` — per-dir RAW `resummarize` block read (cascade input).
      * `resolved` — the parsed `ResummarizeConfig` per parent dir (cascade output).
      * `cited` — the D2a citation set per `(fields, match)`.
      * `mirror` — the D2b summary-key index (`key → representative summary filename`)
        per `(scope, summ_pat, template, ext)`.
    """

    raw: dict[Path, dict[str, Any] | None] = field(default_factory=dict)
    resolved: dict[Path, ResummarizeConfig | None] = field(default_factory=dict)
    cited: dict[tuple[tuple[str, ...], str], frozenset[str]] = field(default_factory=dict)
    mirror: dict[tuple[str, str, str | None, str], dict[str, str]] = field(default_factory=dict)


def _ancestor_dirs(path: Path, vault_root: Path) -> list[Path]:
    """Dirs from `vault_root` → `path.parent` inclusive, **shallowest first**, so a
    deeper folder's `resummarize` overrides a shallower one in the deep-merge.
    A `path` outside `vault_root` degrades to `[vault_root]`."""
    dirs = [vault_root]
    try:
        rel = path.parent.relative_to(vault_root)
    except ValueError:
        return dirs
    cur = vault_root
    for part in rel.parts:
        cur = cur / part
        dirs.append(cur)
    return dirs


def resolve_policy(
    path: Path,
    *,
    vault_root: Path,
    caches: Caches | None = None,
) -> ResummarizeConfig | None:
    """Resolve the effective re-summarization policy for `path` (Q-019-3).

    Reads each ancestor dir's RAW `resummarize` block (hardened via
    `load_resummarize_raw` — size-cap + anchor-ban + symlink-refuse + strict schema
    at EVERY level), deep-merges them deepest-wins, and parses once. The
    RAW-then-parse order makes a partial override (`mode:` only) inherit the
    parent's `detect`. Both the per-dir RAW read AND the parsed result are memoized
    on `caches` (resolution is a function of `path.parent`), so N files in one dir
    resolve once (perf + AC-10 order-independence). Returns `None` when NO level
    configures a policy (≡ TASK 018 / AC-7).
    """
    c = caches or Caches()
    parent = path.parent
    if parent in c.resolved:
        return c.resolved[parent]
    merged: dict[str, Any] = {}
    found = False
    for d in _ancestor_dirs(path, vault_root):
        if d not in c.raw:
            c.raw[d] = load_resummarize_raw(d)
        block = c.raw[d]
        if block is not None:
            found = True
            merged = deep_merge(merged, block)
    result = _parse_resummarize(merged) if found else None
    c.resolved[parent] = result
    return result


def summary_exists(
    path: Path,
    *,
    rel: str,
    vault_root: Path,
    repo: IndexRepository,
    vault_id: str,
    policy: ResummarizeConfig,
    caches: Caches | None = None,
) -> str | None:
    """Return which detector proves a summary exists (`source_state` | `provenance`
    | `mirror`), else `None`. Union with **cheapest-first short-circuit**:
    D1 (`source_state` marker presence) → D2a (provenance citation set) → D2b
    (filesystem mirror). Each detector is individually toggleable (Q-019-4)."""
    c = caches or Caches()
    det = policy.detect
    # D1 — wiki-sync has summarised this exact source path before (marker present,
    # any version → a summary exists; the operator rule "re-summarise only on
    # --force or if absent" means a stale-but-present summary still counts).
    if det.source_state and repo.get_source_state(
        vault_id, "sync", rel, "source_hash"
    ) is not None:
        return "source_state"
    # D2a — an indexed page cites this raw file. The citation SET is hoisted once
    # per (fields, match) (PERF-HIGH); `match` chooses vault-rel-path vs basename
    # equality (the previously-orphaned config knob — vdd-multi logic MED-1).
    pr = det.provenance_ref
    if pr.enabled:
        ckey = (pr.fields, pr.match)
        if ckey not in c.cited:
            cited = repo.all_cited_sources(vault_id, pr.fields)
            if pr.match == "basename":
                cited = {PurePosixPath(x).name for x in cited}
            # TASK 024 / R-4 (dogfood #3 finding): NFC-normalise the citation set.
            # A frontmatter `sources:` value is typically NFC, but `rel` comes from
            # the filesystem walk, which on macOS (HFS+/APFS) yields **NFD** for
            # decomposable Cyrillic (`й`=и+◌̆, `ё`) etc. Without normalising both
            # sides, a Cyrillic-named raw (`Кейс Ярли …pptx`) NEVER matches its
            # summary's provenance and re-converts on EVERY scan. ASCII paths are
            # unaffected (NFC≡NFD). D1 source_state stays NFD-on-both-sides
            # (self-consistent); D2b mirror is FS-vs-FS (consistent) — only D2a
            # crosses the FS↔frontmatter boundary, so the fix is localised here.
            c.cited[ckey] = frozenset(
                unicodedata.normalize("NFC", x) for x in cited)
        target = PurePosixPath(rel).name if pr.match == "basename" else rel
        if unicodedata.normalize("NFC", target) in c.cited[ckey]:
            return "provenance"
    # D2b — filesystem mirror. Reaching here means D1/D2a did NOT prove a summary, so a
    # group-key (N:1) hit is the uncited-same-key merge/split moment (TASK 021 / HIGH-1):
    # warn iff provenance is enabled (else the operator opted into pure-key grouping and a
    # per-file warn would be noise). The skip itself is unchanged.
    if det.mirror.enabled and _mirror_match(
        path, vault_root=vault_root, mirror=det.mirror, caches=c,
        warn_uncited=pr.enabled,
    ):
        return "mirror"
    return None


def apply_policy(
    decision: Decision,
    *,
    path: Path,
    rel: str,
    vault_root: Path,
    repo: IndexRepository,
    vault_id: str,
    policy: ResummarizeConfig | None,
    force: bool,
    caches: Caches | None = None,
) -> Decision:
    """The **monotone** re-summarization gate (Q-019-1/4/6).

    Only `ingest`/`convert+ingest` are gated — `upsert`/`skip` pass through
    unchanged (the safety invariant). Otherwise: `--force` re-arms a raw the policy
    would skip (reason `forced`, set **uniformly** across `never` and `if-missing` —
    vdd-multi logic MED-2); `mode: never` → `skip:resummarize-never`; `mode: always`
    → unchanged; `mode: if-missing` → `skip:summary-exists:<which>` when a detector
    matches, else unchanged."""
    if policy is None or decision.action not in ACTIONABLE:
        return decision
    if policy.mode == "never":
        return replace(decision, reason="forced") if force \
            else Decision("skip", "resummarize-never")
    if policy.mode == "always":
        return decision
    # if-missing
    which = summary_exists(
        path, rel=rel, vault_root=vault_root, repo=repo,
        vault_id=vault_id, policy=policy, caches=caches,
    )
    if which is None:
        return decision
    # A summary exists → skip, unless the operator forces a re-summarisation.
    return replace(decision, reason="forced") if force \
        else Decision("skip", f"summary-exists:{which}")


# --------------------------------------------------------------------------- #
# D2b — filesystem mirror (Q-019-5)
# --------------------------------------------------------------------------- #


def _nearest_anchor(path: Path, raw_dirs: frozenset[str]) -> Path | None:
    """The nearest ancestor directory of `path` whose name ∈ `raw_dirs`, else None."""
    for parent in path.parents:
        if parent.name in raw_dirs:
            return parent
    return None


def _norm(value: str) -> str:
    """Normalise a key component: a pure **ASCII**-digit run loses leading zeros (so
    a raw `02-…` and a summary `02 - …` both key to `2`); other text is verbatim.
    The `isascii()` guard avoids `int()` raising on Unicode-numeric-but-not-decimal
    codepoints that `str.isdigit()` accepts (e.g. `²`) — vdd-multi logic LOW-2."""
    return str(int(value)) if value.isascii() and value.isdigit() else value


def _compose_key(stem: str, pattern: str, template: str | None, *, deadline: float) -> str | None:
    """Derive a comparable key from a filename `stem` via an operator regex
    (Q-019-5). ReDoS-guarded: the regex runs under the `regex` engine with a
    per-call deadline (`guarded_search`); a timeout → `None`. With named groups + a
    `template` the key is composed (`${module}-${lesson}`); otherwise it is group(1)
    (or the whole match). An **empty** composed key → `None` (no-match), so a
    permissive regex matching the empty string can't cause false N:1 collisions
    (vdd-multi logic LOW-1)."""
    try:
        m = guarded_search(pattern, stem, operator=True, deadline=deadline)
    except TimeoutError:
        _LOG.warning("[resummarize-redos] mirror key regex exceeded the budget "
                     "on stem %r — treating as no-match", stem)
        return None
    if m is None:
        return None
    if template:
        groups = {k: _norm(v) for k, v in (m.groupdict() or {}).items() if v is not None}
        try:
            key = string.Template(template).substitute(groups)
        except (KeyError, ValueError):
            return None
        return key or None
    val = m.group(1) if m.lastindex else m.group(0)
    if val is None:
        return None
    return _norm(val) or None


def _key_specs(mirror: MirrorConfig) -> tuple[str, str, str | None, tuple[str, ...]]:
    """(raw_pattern, summary_pattern, template, flags) for the group-key match.
    `key` (extended, separate per side) wins; `group_key` is the same-both-sides
    shorthand; default `^(\\d+)`. A side missing its own regex falls back to the
    other side's, then `group_key`, then the default."""
    k = mirror.key
    gk = mirror.group_key
    if k is not None:
        raw = k.raw_regex or k.summary_regex or gk or _DEFAULT_GROUP_KEY
        summ = k.summary_regex or k.raw_regex or gk or _DEFAULT_GROUP_KEY
        return raw, summ, k.template, k.flags
    pat = gk or _DEFAULT_GROUP_KEY
    return pat, pat, None, ()


def _with_flags(pattern: str, flags: tuple[str, ...]) -> str:
    """Fold `ignorecase` into the pattern as an inline flag (the `regex` engine is
    unicode-by-default, so `unicode` is a no-op)."""
    return "(?i)" + pattern if "ignorecase" in flags else pattern


@lru_cache(maxsize=256)
def _mirror_regex_ok(pattern: str) -> bool:
    """Cached ReDoS load-gate verdict for a single mirror pattern (per process)."""
    return _lc.is_pattern_redos_safe(pattern, operator=True)


def _assert_mirror_regexes(*patterns: str) -> None:
    """Load-gate: reject (→ `INVALID_SYNC_CONFIG`, exit 6) a mirror key regex that is
    uncompilable or catastrophic, BEFORE it runs on any file — closes the per-scan
    ReDoS amplification the per-call deadline alone leaves open (vdd-multi security
    MED). The error NEVER echoes the pattern (CWE-209). Cached per pattern."""
    for pat in patterns:
        if not _mirror_regex_ok(pat):
            raise SyncConfigError(
                "INVALID_SYNC_CONFIG",
                "mirror key regex is uncompilable or exceeds the ReDoS budget",
            )


def _scope_key_index(
    scope: Path, summ_pat: str, template: str | None, ext: str, caches: Caches,
) -> dict[str, str]:
    """Mapping `key → representative summary filename` for `scope`, computed **once per
    scope** and memoized (vdd-multi PERF-HIGH — was O(R×S), now O(S) + R lookups). The
    value (lexicographically-smallest filename sharing the key, deterministic) names the
    colliding summary in the TASK 021 merge/split WARN; membership (`key in index`) and
    falsiness (the dead-detector guard) are unchanged from the former set. A SINGLE
    shared deadline bounds the whole scope build's regex cost (vdd-multi security MED —
    the S-side aggregate is one budget, not S budgets)."""
    ck = (str(scope), summ_pat, template, ext)
    cached = caches.mirror.get(ck)
    if cached is not None:
        return cached
    keys: dict[str, str] = {}
    n_files = 0
    deadline = time.monotonic() + _lc.WIKI_REDOS_BUDGET_S
    # `recurse_symlinks=False` (explicit, not relying on the 3.13+ default) keeps the
    # mirror walk aligned with wiki-sync's O_NOFOLLOW discipline (vdd-multi security
    # DiD) — a symlinked subdir under `scope` is never descended into.
    for summ in scope.rglob("*" + ext, recurse_symlinks=False):
        n_files += 1
        k = _compose_key(summ.stem, summ_pat, template, deadline=deadline)
        if k is not None and (k not in keys or summ.name < keys[k]):
            keys[k] = summ.name
    # Dead-detector guard (TASK 019 dogfood finding): mirror is enabled and the scope
    # has summary files, yet the operator regex keyed NONE of them — almost always a
    # misconfigured `group_key`/`key` (e.g. a YAML double-backslash `^(\\d+)` that
    # compiles to "literal-backslash + d"). Without this the detector is SILENTLY inert
    # and the gate quietly leans on D1/D2a alone. WARN once per scope (the index is
    # memoized, so this fires at most once per (scope, pattern)).
    if n_files and not keys:
        _LOG.warning(
            "[resummarize] mirror match=%s keyed 0 of %d summaries in %s — the "
            "group_key/key regex matched nothing (likely a misconfigured pattern, e.g. "
            "a YAML double-backslash); D2b mirror is inert for this scope.",
            "group-key", n_files, scope,
        )
    caches.mirror[ck] = keys
    return keys


def _mirror_match(
    path: Path, *, vault_root: Path, mirror: MirrorConfig, caches: Caches,
    warn_uncited: bool = False,
) -> bool:
    """D2b filesystem mirror (Q-019-5), index-independent.

    anchor = nearest `raw_dirs` ancestor of `path`; scope = the raw file's own
    folder when `summary_dir == "."`, else the sibling `<anchor.parent>/<summary_dir>/`.
    The scope is contained inside the vault (an operator `summary_dir: "../.."` can
    NOT redirect the probe out — vdd-multi security LOW). `stem-relpath` (1:1) checks
    the structure-preserving sibling; `group-key` (N:1) folds many raw onto one
    summary sharing a composed key, via a once-per-scope key index.

    TASK 021 / HIGH-1 (Option A): when `warn_uncited` and a **group-key** (N:1) match
    causes the skip, emit ONE merge/split WARN. Reaching D2b means D1/D2a did NOT match
    (the raw is genuinely uncited), so an N:1 key hit is the merge-vs-split moment — the
    skip stays (behaviour-preserving), but the coarse-key ambiguity is surfaced.
    `stem-relpath` (1:1, exact) never warns.
    """
    anchor = _nearest_anchor(path, frozenset(mirror.raw_dirs))
    if anchor is None:
        return False
    scope = path.parent if mirror.summary_dir == "." else anchor.parent / mirror.summary_dir
    if not scope.is_dir():
        return False
    try:
        validate_inside_vault(scope, vault_root)  # operator summary_dir containment
    except PathTraversalError:
        return False

    if mirror.match == "stem-relpath":
        if mirror.summary_dir == ".":
            target = path.parent / (path.stem + mirror.summary_ext)
        else:
            try:
                rel = path.relative_to(anchor)
            except ValueError:
                return False
            target = (scope / rel).with_suffix(mirror.summary_ext)
        return target.is_file()

    # group-key (N:1)
    raw_pat, summ_pat, template, flags = _key_specs(mirror)
    raw_pat = _with_flags(raw_pat, flags)
    summ_pat = _with_flags(summ_pat, flags)
    _assert_mirror_regexes(raw_pat, summ_pat)  # load-gate (cached) → exit 6 on catastrophic
    # Build the (memoized) summary-key index FIRST so the dead-detector WARN in
    # `_scope_key_index` fires even when the raw stem itself yields no key — the exact
    # symptom of a misconfigured regex that matches NEITHER side (dogfood finding).
    summary_keys = _scope_key_index(scope, summ_pat, template, mirror.summary_ext, caches)
    rkey = _compose_key(path.stem, raw_pat, template,
                        deadline=time.monotonic() + _lc.WIKI_REDOS_BUDGET_S)
    if rkey is None:
        return False
    matched = rkey in summary_keys
    if matched and warn_uncited:
        _LOG.warning(
            "[resummarize] mirror: %r shares key %r with already-summarised %r but is "
            "NOT cited by it — skipped. MERGE: re-run with --force to fold it into that "
            "summary (the orchestrator rewrites its sources:); SPLIT: give it a distinct "
            "key (finer group_key / own scope) or author a separate summary citing it.",
            path.name, rkey, summary_keys[rkey],
        )
    return matched
