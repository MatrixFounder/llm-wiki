"""Layout-grammar config layer (TASK 012 / R-X1, PW-A).

A SEPARATE config system from the per-vault identity config
(`config_loader.py` / `config/wiki-config.schema.yaml`). This layer answers
"how do I PARSE this kind of vault?" — globs → (type, project), ref-extraction
patterns, type-mapping, slug strategy. The grammar ships ONCE with the engine as
built-in `layouts/{karpathy,dev-project,obsidian-personal}.yaml`; a vault's
`WIKI_SCHEMA.md` merely NAMES its layout. An operator may override per-vault via
a `WIKI_SCHEMA.md` frontmatter `layout_config:` pointer or a conventional
`<vault>/.wiki/layout.yaml` (frontmatter pointer wins), deep-merged over the
built-in base and validated against `config/layout-config.schema.yaml`.

Design (D-012-2): kept parallel to `config_loader` because the per-vault
`deep_merge` REPLACES lists — correct here for `paths[]`/`ref_extraction[]`
(operator-supplied list replaces the built-in) but the dict-recurse keeps
`type_mapping` mergeable. `flat`/`per-project` alias to `karpathy` (the legacy
`layout:` values never gated the two-tier walk).

Byte-identity: `karpathy.yaml` is a validated projection of `layout.py` +
`normalization.TYPE_MAPPING`/`_PATH_TYPE_FALLBACK`; the invariant is pinned by
`tests/test_layout_config.py::test_karpathy_config_matches_layout_constants`.

NOTE: the PW-D ReDoS load-gate (validate `ref_extraction[].regex` against an
adversarial payload) lands in bead 012-04 with the ref-extraction consumer; this
module (PW-A) validates the config SCHEMA only.
"""

from __future__ import annotations

import logging
import os
import re
import stat
import string
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple

import regex  # PyPI linear-deadline engine — operator-pattern ReDoS guard (R-X1-REDOS-RT)
import yaml
from jsonschema import Draft202012Validator
from slugify import slugify

from scripts.wiki_index.config_loader import (
    ConfigValidationError,
    VaultRootNotFoundError,
    deep_merge,
    load_root_config,
)
from scripts.wiki_index.layout import SCHEMA_FILE, SYSTEM_FILES, VAULT_TIER_PROJECT
from scripts.wiki_index.security import (
    PathTraversalError,
    assert_no_symlink_escape,
    validate_inside_vault,
)

_LOG = logging.getLogger(__name__)

# PW-J: a glob matched a file but its project_pattern did not — the file is still
# indexed (no silent drop) under this sentinel so the operator sees it and can fix
# the config. Distinct from VAULT_TIER_PROJECT.
UNMATCHED_PROJECT = "_unmatched_"

# --- PW-D ReDoS load-time budget gate (D-012-3, stdlib `re` — no `regex` dep) ---
# Every operator-supplied regex (`ref_extraction[].regex` AND `paths[].project_pattern`)
# is run against a deterministic adversarial payload at config-load; if the median of
# N runs exceeds the ceiling the config is rejected (exit 6) BEFORE any file is read.
# The payload is small (a short ambiguous run) so a catastrophic-backtracking pattern
# is bounded to ~sub-second per run (the gate itself can't be DoS'd) while built-in
# patterns finish in microseconds. Constants are explicit (not one-shot timing —
# plan-review m2 / architecture-review m2).
_REDOS_N = 5
_REDOS_CEILING_S = 0.05
# A small battery of STRUCTURALLY-DIVERSE adversarial payloads (critic-security
# HIGH-2): different char classes + a no-final-match tail, so the gate catches
# more than one backtracker SHAPE (the old single `"a"*22+"!"` only stressed
# nested-quantifier-over-`a`; a pattern like `(.*a){50}` slipped past it). Each
# payload is short so even a catastrophic pattern completes in ~sub-second (the
# gate itself can't be DoS'd; safe patterns finish in ~1µs → no flaky verdicts).
# RESIDUAL (deferred → KNOWN_ISSUES R-X1-REDOS-RUNTIME): a pattern that is linear
# on these short payloads but catastrophic only on LONG real file content is NOT
# caught at load — that needs a per-file runtime regex deadline at the
# `extract_refs`/`_derive_project` consumer (stdlib `re` has no timeout). Built-in
# layout patterns are pre-vetted; this gate guards operator-custom configs.
_REDOS_PAYLOADS = (
    "a" * 24 + "!",                # nested quantifier over one char
    "1" * 24 + "x",                # digit run
    " " * 24 + "x",                # whitespace run
    ("ab" * 12) + "!",             # alternation/group over a 2-char cycle
    ("a" * 12 + "b" * 12) + "!",   # two runs + non-matching tail (defeats `(.*a){…}`)
)


def is_pattern_redos_safe(pattern: str, *, operator: bool = True) -> bool:
    """Return False iff `pattern` fails to compile OR its median search time over
    the adversarial payloads exceeds the ceiling (catastrophic backtracking). The
    boolean, value-free sibling of `_redos_budget_check` — reused by TASK 019's
    mirror-regex load-gate, which must reject a catastrophic operator regex WITHOUT
    echoing it (CWE-209). `operator` picks the runtime engine (`regex` vs stdlib `re`)
    so the gate shares the dialect the pattern will actually run under."""
    try:
        compiled = regex.compile(pattern) if operator else re.compile(pattern)
    except (re.error, regex.error):
        return False
    for payload in _REDOS_PAYLOADS:
        times: list[float] = []
        for _ in range(_REDOS_N):
            t0 = time.perf_counter()
            compiled.search(payload)
            dt = time.perf_counter() - t0
            times.append(dt)
            if dt > _REDOS_CEILING_S:
                break
        if sorted(times)[len(times) // 2] > _REDOS_CEILING_S:
            return False
    return True


# --- R-X1-REDOS-RT runtime per-file deadline (TASK 017) ----------------------- #
# The load-gate above is a load-time heuristic; this is the sound backstop for a
# pattern catastrophic only on long real file content. A per-file wall-clock budget
# is enforced ONLY for operator-custom patterns, run under the PyPI `regex` engine —
# which checks the deadline INSIDE its backtracking loop and raises the builtin
# `TimeoutError` (stdlib `re` cannot be interrupted: a catastrophic match is one
# C-level call that holds the GIL). Built-in layout patterns stay on stdlib `re`
# (zero overhead, byte-identity). DIALECT: operator patterns are authored for stdlib
# `re`; `regex` V0 mode (the default) is an `re`-compatible near-superset.
def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# Clamp the operator budget to a sane ceiling (vdd-multi SEC-LOW): an operator env
# `WIKI_REDOS_BUDGET_S=999999` must not be able to silently DISABLE the guard. A
# tiny/negative value fails SAFE (immediate timeout), so only the ceiling is clamped.
_WIKI_REDOS_BUDGET_MAX_S = 60.0
WIKI_REDOS_BUDGET_S: float = min(_env_float("WIKI_REDOS_BUDGET_S", 2.0),
                                 _WIKI_REDOS_BUDGET_MAX_S)


def _operator_remaining(deadline: float | None) -> float:
    """Time left for an operator-pattern call. **Fails CLOSED** (vdd-multi SEC-LOW):
    a missing `deadline` defaults to a full `WIKI_REDOS_BUDGET_S` budget rather than
    `timeout=None` (which `regex` treats as NO limit → unbounded operator pattern)."""
    if deadline is None:
        deadline = time.monotonic() + WIKI_REDOS_BUDGET_S
    return max(0.0, deadline - time.monotonic())


def guarded_finditer(
    pattern: str, text: str, *, operator: bool, deadline: float | None
) -> Iterator[Any]:
    """Iterate regex matches of `pattern` over `text`.

    `operator=False` → verbatim stdlib `re.finditer` (byte-identity, zero overhead)
    for pre-vetted built-in layout patterns. `operator=True` → run under the `regex`
    engine with `timeout=remaining` (remaining = `deadline - monotonic()`), so a
    catastrophic operator pattern raises the builtin `TimeoutError` instead of
    hanging. The caller owns the per-file `deadline` and converts `TimeoutError`
    into a report-and-skip (never re-raise, never hang). An operator call with no
    deadline fails CLOSED (full budget), never `timeout=None`."""
    if not operator:
        yield from re.compile(pattern).finditer(text)
        return
    yield from regex.compile(pattern).finditer(text, timeout=_operator_remaining(deadline))


def guarded_search(
    pattern: str, text: str, *, operator: bool, deadline: float | None
) -> Any:
    """Single-shot counterpart of `guarded_finditer` (for `_derive_project`).
    Returns the match (or None); raises builtin `TimeoutError` past the deadline
    when `operator=True`. Fails CLOSED on a missing deadline (see `guarded_finditer`)."""
    if not operator:
        return re.compile(pattern).search(text)
    return regex.compile(pattern).search(text, timeout=_operator_remaining(deadline))


# Repo-root-relative paths (project root = parent of `scripts/`).
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LAYOUTS_DIR = _REPO_ROOT / "scripts" / "wiki_index" / "layouts"
_SCHEMA_PATH = _REPO_ROOT / "config" / "layout-config.schema.yaml"

# Legacy WIKI_SCHEMA `layout:` values map onto the Karpathy grammar (the field
# never gated the two-tier walk — see ADR-002 §D8 TASK-012 amendment).
_ALIAS: dict[str, str] = {"flat": "karpathy", "per-project": "karpathy"}

_OVERRIDE_CONVENTIONAL = ".wiki/layout.yaml"


class LayoutConfigError(ValueError):
    """Raised on an unknown layout name, a schema-invalid grammar, a regex that
    fails to compile / exceeds the ReDoS budget (bead 012-04), a template that
    references a missing named group, or an override that escapes the vault.
    The CLI caller surfaces this as exit code 6."""


@dataclass(frozen=True)
class PathEntry:
    """One glob → (type, project) rule (PW-B/J/N)."""

    glob: str
    type: str | None = None
    project: str | None = None
    project_pattern: str | None = None
    project_template: str | None = None
    project_slug_strategy: str | None = None
    default_tags: tuple[str, ...] = ()
    extra_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class RefRule:
    """One cross-reference extraction pattern (PW-D)."""

    kind: str
    regex: str
    target_group: int
    transform: str | None = None


class DiscoveredPage(NamedTuple):
    """One page found by `iter_pages` (PW-B/J/K/M/L/N): its path, derived slug
    (per `slug_strategy`), derived `pages.project`, the matched glob's
    `default_tags + extra_tags` (merged into the page's tags by reindex), and the
    matched glob's `type` (PW-C/F — the glob-inferred raw-type used when the file
    has no frontmatter `type:`; None for Karpathy, which infers from frontmatter /
    path_type_fallback), plus `mtime` — the `st_mtime` captured from the SINGLE
    `stat()` the walk already performs (TASK 017 / P-2), reused by `reindex_delta`
    and the `check_drift --mtime-skip` fast-path instead of a second stat."""

    path: Path
    slug: str
    project: str
    extra_tags: tuple[str, ...]
    raw_type: str | None = None
    mtime: float | None = None


@dataclass(frozen=True)
class LayoutConfig:
    """The merged, validated layout grammar the engine consumes."""

    schema_version: str
    layout: str
    slug_strategy: str
    paths: tuple[PathEntry, ...]
    type_mapping: dict[str, tuple[str, str | None]]
    path_type_fallback: dict[str, str] = field(default_factory=dict)
    ref_extraction: tuple[RefRule, ...] = ()
    ignore: tuple[str, ...] = ()
    file_extensions: tuple[str, ...] = (".md",)
    frontmatter_synthesis: dict[str, Any] = field(default_factory=dict)
    auto_indexes: tuple[dict[str, Any], ...] = ()
    # R-X1-REDOS-RT (TASK 017) provenance — True iff a per-vault override SUPPLIED
    # this list (Q-012-f merge REPLACES it wholesale). Drives the runtime ReDoS
    # guard: operator-supplied patterns run under `regex`+timeout; built-in patterns
    # stay on stdlib `re` (byte-identity). `resolve_layout_config`'s built-in-only
    # path leaves both False.
    ref_extraction_operator_supplied: bool = False
    paths_operator_supplied: bool = False


# --------------------------------------------------------------------------- #
# Schema validation
# --------------------------------------------------------------------------- #


def _load_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise LayoutConfigError(f"{path}: layout config must be a YAML mapping")
    return raw


_VALIDATOR: Draft202012Validator | None = None


def _get_validator() -> Draft202012Validator:
    """Module-level singleton (perf-critic H-1): the layout-config JSON Schema is
    static + ships with the engine, so read + `check_schema`-meta-validate + build
    the `Draft202012Validator` ONCE per process, not on every `_validate` call
    (which previously re-read the file + re-meta-validated the schema each time)."""
    global _VALIDATOR
    if _VALIDATOR is None:
        schema_doc = yaml.safe_load(_SCHEMA_PATH.read_text(encoding="utf-8"))
        if not isinstance(schema_doc, dict):
            raise LayoutConfigError(f"{_SCHEMA_PATH}: schema must be a YAML mapping")
        Draft202012Validator.check_schema(schema_doc)
        _VALIDATOR = Draft202012Validator({**schema_doc, "$ref": "#/$defs/LayoutConfig"})
    return _VALIDATOR


def _validate(merged: dict[str, Any]) -> None:
    """Validate `merged` against #/$defs/LayoutConfig. Raises LayoutConfigError
    with a JSON pointer to the offending field on failure."""
    errors = sorted(_get_validator().iter_errors(merged), key=lambda e: list(e.absolute_path))
    if errors:
        parts = []
        for err in errors:
            pointer = "/" + "/".join(str(p) for p in err.absolute_path) if err.absolute_path else "/"
            parts.append(f"  at {pointer}: {err.message}")
        raise LayoutConfigError("layout config validation failed:\n" + "\n".join(parts))


def _build(
    merged: dict[str, Any], *, paths_operator_supplied: bool = False,
    ref_extraction_operator_supplied: bool = False,
) -> LayoutConfig:
    """Convert a validated config dict into a frozen LayoutConfig, applying
    schema defaults (jsonschema does not mutate the instance with defaults).
    The two `*_operator_supplied` flags carry R-X1-REDOS-RT provenance (TASK 017)."""
    paths = tuple(
        PathEntry(
            glob=p["glob"],
            type=p.get("type"),
            project=p.get("project"),
            project_pattern=p.get("project_pattern"),
            project_template=p.get("project_template"),
            project_slug_strategy=p.get("project_slug_strategy"),
            default_tags=tuple(p.get("default_tags") or ()),
            extra_tags=tuple(p.get("extra_tags") or ()),
        )
        for p in merged["paths"]
    )
    type_mapping = {
        raw: (entry["db_type"], entry.get("tag"))
        for raw, entry in merged["type_mapping"].items()
    }
    ref_extraction = tuple(
        RefRule(
            kind=r["kind"],
            regex=r["regex"],
            target_group=r["target_group"],
            transform=r.get("transform"),
        )
        for r in (merged.get("ref_extraction") or ())
    )
    return LayoutConfig(
        schema_version=merged["schema_version"],
        layout=merged["layout"],
        slug_strategy=merged["slug_strategy"],
        paths=paths,
        type_mapping=type_mapping,
        path_type_fallback=dict(merged.get("path_type_fallback") or {}),
        ref_extraction=ref_extraction,
        ignore=tuple(merged.get("ignore") or ()),
        file_extensions=tuple(merged.get("file_extensions") or (".md",)),
        frontmatter_synthesis=dict(merged.get("frontmatter_synthesis") or {}),
        auto_indexes=tuple(merged.get("auto_indexes") or ()),
        ref_extraction_operator_supplied=ref_extraction_operator_supplied,
        paths_operator_supplied=paths_operator_supplied,
    )


# --------------------------------------------------------------------------- #
# Override resolution (path-guarded — architecture-review m3)
# --------------------------------------------------------------------------- #


def _resolve_override(vault_root: Path, root_config: dict[str, Any]) -> Path | None:
    """Return the override layout file to overlay, or None. An explicit
    `layout_config:` frontmatter pointer wins over the conventional
    `<vault>/.wiki/layout.yaml`. The file is read under validate_inside_vault +
    symlink-refuse (an operator override is Class-A but must not escape the
    vault root)."""
    pointer = root_config.get("layout_config")
    if pointer:
        candidate = vault_root / str(pointer)   # RAW — do NOT resolve yet
    else:
        candidate = vault_root / _OVERRIDE_CONVENTIONAL
        if not candidate.exists():
            return None

    # critic-security MED-2: check is_symlink on the RAW candidate, BEFORE any
    # resolve() (which would dereference the symlink and make this check a no-op).
    if candidate.is_symlink():
        raise LayoutConfigError(
            f"layout override is a symlink (refusing to follow): {candidate}"
        )
    try:
        validated = validate_inside_vault(candidate, vault_root)  # resolve+contain
        assert_no_symlink_escape(validated)                       # ancestor-symlink walk
    except PathTraversalError as exc:
        raise LayoutConfigError(str(exc)) from exc
    except FileNotFoundError as exc:
        raise LayoutConfigError(
            f"layout_config pointer does not exist: {candidate}"
        ) from exc
    return validated


def load_layout_config(vault_root: Path, root_config: dict[str, Any]) -> LayoutConfig:
    """Resolve + validate the layout grammar for `vault_root`.

    `root_config` is the per-vault config (from `config_loader.load_root_config`
    / `load_config`); only its `layout:` (required) and optional `layout_config:`
    keys are read here. Resolution:
      1. name = alias-map(root_config['layout']);
      2. load built-in `layouts/<name>.yaml` (base);
      3. overlay an optional per-vault override (deep-merge over base);
      4. validate the merged result against `layout-config.schema.yaml`;
      5. build + return the frozen LayoutConfig.
    """
    raw_name = root_config.get("layout")
    if not raw_name:
        raise LayoutConfigError("root config missing required `layout` field")
    name = _ALIAS.get(str(raw_name), str(raw_name))
    builtin = LAYOUTS_DIR / f"{name}.yaml"
    if not builtin.is_file():
        raise LayoutConfigError(
            f"unknown layout {raw_name!r} (no built-in {name}.yaml; "
            f"valid: {sorted(p.stem for p in LAYOUTS_DIR.glob('*.yaml'))})"
        )
    merged = _load_yaml(builtin)

    override_path = _resolve_override(vault_root, root_config)
    paths_op = refs_op = False
    if override_path is not None:
        override_dict = _load_yaml(override_path)
        # Q-012-f: an override REPLACES the whole list when it supplies the key, so
        # presence of the key is exact per-list provenance (R-X1-REDOS-RT).
        paths_op = "paths" in override_dict
        refs_op = "ref_extraction" in override_dict
        # `ignore` is the one ADDITIVE list (TASK 019 dogfood finding): a per-vault
        # override EXTENDS the base ignore set rather than discarding the built-in
        # `.obsidian/**`/`.trash/**`/`_templates/**`/`**/*.base` exclusions — which is
        # what the `wiki-init` CLAUDE.md/WIKI_SCHEMA templates already promise
        # ("extend `ignore`"). Captured BEFORE deep_merge (which would replace it) and
        # re-unioned after, base-first, deduped. (paths/ref_extraction stay REPLACE for
        # their ReDoS provenance contract.)
        base_ignore = list(merged.get("ignore") or [])
        merged = deep_merge(merged, override_dict)
        if "ignore" in override_dict:
            merged["ignore"] = list(
                dict.fromkeys(base_ignore + list(override_dict.get("ignore") or []))
            )

    _validate(merged)
    cfg = _build(merged, paths_operator_supplied=paths_op,
                 ref_extraction_operator_supplied=refs_op)
    _validate_path_patterns(cfg.paths, operator_supplied=cfg.paths_operator_supplied)
    _redos_budget_check(cfg)            # PW-D ReDoS gate (ref + project regexes)
    return cfg


def _redos_budget_check(config: LayoutConfig) -> None:
    """PW-D ReDoS gate (D-012-3): reject (exit 6) any operator-supplied regex
    whose median search time over the adversarial payload exceeds the ceiling —
    catastrophic backtracking caught at config-load, before any file is read.
    Covers BOTH `ref_extraction[].regex` and `paths[].project_pattern` (012-04
    Roast finding). Built-in layouts are pre-vetted (sub-ms). Bounded: the loop
    breaks after the first over-ceiling run, so a pathological pattern cannot DoS
    the gate itself (one catastrophic run, then reject)."""
    # (label, pattern, operator) — R-X1-REDOS-RT alignment (TASK 017): probe each
    # pattern under the SAME engine that runs it at runtime (operator-supplied →
    # `regex`, built-in → stdlib `re`), so load-gate and runtime share one dialect
    # and a regex-incompatible operator pattern is caught here (exit 6), not at
    # runtime inside `guarded_*`.
    patterns: list[tuple[str, str, bool]] = [
        (f"ref_extraction[{i}].regex", r.regex, config.ref_extraction_operator_supplied)
        for i, r in enumerate(config.ref_extraction)
    ]
    patterns += [
        (f"paths[{i}].project_pattern", p.project_pattern, config.paths_operator_supplied)
        for i, p in enumerate(config.paths)
        if p.project_pattern is not None
    ]
    for label, pat, operator in patterns:
        try:
            compiled = regex.compile(pat) if operator else re.compile(pat)
        except (re.error, regex.error) as exc:  # not compile-checked elsewhere
            raise LayoutConfigError(f"regex {label}={pat!r} failed to compile: {exc}") from exc
        for payload in _REDOS_PAYLOADS:
            times: list[float] = []
            for _ in range(_REDOS_N):
                t0 = time.perf_counter()
                compiled.search(payload)
                dt = time.perf_counter() - t0
                times.append(dt)
                if dt > _REDOS_CEILING_S:
                    break  # already over budget — stop (bounds catastrophic gate cost)
            median = sorted(times)[len(times) // 2]
            if median > _REDOS_CEILING_S:
                raise LayoutConfigError(
                    f"regex {label}={pat!r} exceeds the ReDoS budget "
                    f"({median * 1000:.1f}ms median > {_REDOS_CEILING_S * 1000:.0f}ms "
                    f"ceiling) on an adversarial payload — refusing to load "
                    f"(potential catastrophic backtracking)"
                )


# --------------------------------------------------------------------------- #
# PW-J: project derivation (regex + string.Template) with load-time error policy
# --------------------------------------------------------------------------- #


def _validate_path_patterns(
    paths: tuple[PathEntry, ...], *, operator_supplied: bool = False
) -> None:
    """PW-J error policy (a)+(c), enforced at config-load:
    (a) a `project_pattern` that fails to compile → LayoutConfigError (exit 6);
    (c) a `project_template` referencing a named group the pattern does not
        produce → LayoutConfigError (exit 6).

    NOTE (bead 012-04): the ReDoS budget gate folds in here — `project_pattern`
    is an operator-supplied regex run per-file in `_derive_project`, so it shares
    the same adversarial-payload budget check as `ref_extraction[].regex`.
    Built-in layouts are pre-vetted; the gate guards operator-custom configs.

    R-X1-REDOS-RT (TASK 017): operator-supplied patterns are compiled under the
    `regex` engine — the one that actually runs them in `_derive_project` — so the
    compile-check + named-group validation share the runtime dialect with the
    aligned `_redos_budget_check` (no engine split between load and runtime).
    Built-in patterns compile under stdlib `re`.
    """
    for entry in paths:
        if entry.project_pattern is None:
            continue
        try:
            compiled = (regex.compile(entry.project_pattern) if operator_supplied
                        else re.compile(entry.project_pattern))
        except (re.error, regex.error) as exc:
            raise LayoutConfigError(
                f"project_pattern {entry.project_pattern!r} (glob {entry.glob!r}) "
                f"failed to compile: {exc}"
            ) from exc
        if not entry.project_template:
            # critic-logic LOW: a pattern without a template → _derive_project
            # would substitute into "" → a degenerate empty project. Reject at load.
            raise LayoutConfigError(
                f"project_pattern {entry.project_pattern!r} (glob {entry.glob!r}) "
                f"requires a project_template"
            )
        if entry.project_template:
            ids = set(string.Template(entry.project_template).get_identifiers())
            missing = ids - set(compiled.groupindex)
            if missing:
                raise LayoutConfigError(
                    f"project_template {entry.project_template!r} (glob {entry.glob!r}) "
                    f"references group(s) {sorted(missing)} not produced by project_pattern"
                )


def _project_slug(value: str, strategy: str | None) -> str:
    """Slugify a derived project value per `project_slug_strategy`. `course-slug`
    is the loose-default slugify (byte-identical to today's course project). The
    PW-L strategies are implemented here too so the enum is complete."""
    if strategy in (None, "identity"):
        return value
    if strategy in ("course-slug", "transliterate"):
        return slugify(value, lowercase=True, separator="-")
    if strategy == "preserve-unicode":
        return slugify(value, lowercase=True, separator="-",
                       allow_unicode=True, regex_pattern=r"[^\w\-]")
    if strategy == "ascii-only":
        return slugify(value, lowercase=True, separator="-", regex_pattern=r"[^a-z0-9\-]")
    return value


def _derive_project(
    rel_posix: str, entry: PathEntry, *, operator_supplied: bool = False
) -> str:
    """PW-J: derive `pages.project` for a matched file. Literal `project` wins;
    else `project_pattern` + `project_template` (already validated at load); a
    pattern miss → UNMATCHED_PROJECT + a WARN (no silent drop).

    R-X1-REDOS-RT (TASK 017): when the pattern is operator-supplied it runs under
    the `regex` engine with a per-file deadline; a `TimeoutError` degrades to
    UNMATCHED_PROJECT + a WARN (exact parity with the pattern-miss branch), never
    hangs. The rel-path input is short, so a per-call budget suffices."""
    if entry.project_pattern is not None:
        try:
            match = guarded_search(
                entry.project_pattern, rel_posix, operator=operator_supplied,
                deadline=(time.monotonic() + WIKI_REDOS_BUDGET_S
                          if operator_supplied else None),
            )
        except TimeoutError:
            _LOG.warning("[redos-skip] project_pattern exceeded %.1fs budget for %s "
                         "(glob=%s)", WIKI_REDOS_BUDGET_S, rel_posix, entry.glob)
            return UNMATCHED_PROJECT
        if match is None:
            _LOG.warning("[unmatched-pattern] %s (glob=%s)", rel_posix, entry.glob)
            return UNMATCHED_PROJECT
        value = string.Template(entry.project_template or "").substitute(match.groupdict())
        return _project_slug(value, entry.project_slug_strategy)
    if entry.project is not None:
        return entry.project
    return VAULT_TIER_PROJECT


def _matches_ignore(rel_posix: str, ignore: tuple[str, ...]) -> bool:
    """PW-K: match a vault-relative POSIX path against an ignore glob. Uses
    `PurePosixPath.full_match` (Python 3.13+) for correct recursive `**` semantics
    (stdlib `PurePath.match` does NOT handle `**`)."""
    p = PurePosixPath(rel_posix)
    return any(p.full_match(spec) for spec in ignore)


def _apply_slug_strategy(stem: str, strategy: str) -> str:
    """PW-L: derive a page slug from its file stem per `slug_strategy`.
    `identity` = verbatim stem (Karpathy byte-identity); the others call
    python-slugify with strategy-specific settings (obsidian-personal)."""
    if strategy == "identity":
        return stem
    if strategy == "transliterate":
        return slugify(stem, lowercase=True, separator="-")
    if strategy == "preserve-unicode":
        return slugify(stem, lowercase=True, separator="-",
                       allow_unicode=True, regex_pattern=r"[^\w\-]")
    if strategy == "ascii-only":
        return slugify(stem, lowercase=True, separator="-", regex_pattern=r"[^a-z0-9\-]")
    return stem


def iter_pages(vault_root: Path, config: LayoutConfig) -> list[DiscoveredPage]:
    """Config-driven page discovery (PW-B/J/K/M/L/N). Yields a `DiscoveredPage`
    (path, slug, project, extra_tags) for every file matched by `config.paths[]`
    (first-match-wins, declared order), after applying `ignore[]` (PW-K) +
    `file_extensions` (PW-M) + the implicit ignore set (SYSTEM_FILES + every
    `auto_indexes[].output` — architecture-review m1). Slug = `slug_strategy`
    applied to the file stem (PW-L; `identity` = verbatim → Karpathy byte-identity).
    `extra_tags` = the matched entry's `default_tags + extra_tags` (PW-N). Output
    is stably sorted by vault-relative POSIX path (NFR-5, deterministic ≥ today).
    """
    exts = set(config.file_extensions)
    autoindex_outputs = {
        str(ai["output"]) for ai in config.auto_indexes if ai.get("output")
    }
    seen: set[Path] = set()
    out: list[DiscoveredPage] = []

    for entry in config.paths:
        entry_tags = tuple(entry.default_tags) + tuple(entry.extra_tags)
        for path in vault_root.glob(entry.glob):
            if path in seen:
                continue
            # Free string/glob filters FIRST — no syscall for non-.md / system /
            # ignored glob hits (vdd-multi PERF-LOW; matters for broad-glob operator
            # layouts; byte-identity-neutral — same files pass, sorted at the end).
            if path.suffix not in exts:
                continue
            if path.name in SYSTEM_FILES:
                continue
            rel_posix = path.relative_to(vault_root).as_posix()
            if rel_posix in autoindex_outputs or _matches_ignore(rel_posix, config.ignore):
                continue
            # P-2 (TASK 017): ONE stat per SURVIVING candidate — derive is-regular-file
            # AND mtime from it (was `path.is_file()` + a separate `path.stat()` in
            # reindex_delta). `is_file()` swallows OSError → False; mirror that.
            try:
                st = path.stat()
            except OSError:
                continue
            if not stat.S_ISREG(st.st_mode):
                continue
            seen.add(path)
            out.append(DiscoveredPage(
                path=path,
                slug=_apply_slug_strategy(path.stem, config.slug_strategy),
                project=_derive_project(rel_posix, entry,
                                        operator_supplied=config.paths_operator_supplied),
                extra_tags=entry_tags,
                raw_type=entry.type,
                mtime=st.st_mtime,
            ))

    out.sort(key=lambda d: d.path.relative_to(vault_root).as_posix())
    return out


def derive_project_for_path(path: Path, vault_root: Path) -> str:
    """Single-path project derivation — the shared helper that converges the
    ingest-side `wiki_extract_concepts._derive_source_project` onto the same
    config-driven logic `iter_pages` uses (architecture-review C1). Resolves the
    vault's layout config, finds the first matching `paths[]` entry, and derives
    its project. Returns `VAULT_TIER_PROJECT` if no entry matches (e.g. a path
    outside the configured globs). Called bounded times (not per-file in a large
    loop), so the per-call config resolve is acceptable."""
    try:
        rel_posix = path.relative_to(vault_root).as_posix()
    except ValueError:
        return VAULT_TIER_PROJECT
    config = resolve_layout_config(vault_root)
    for entry in config.paths:
        if PurePosixPath(rel_posix).full_match(entry.glob):
            # R-X1-REDOS-RT (TASK 017): thread provenance exactly as `iter_pages`
            # does — an operator `project_pattern` MUST run under the `regex` engine
            # (with the runtime deadline), never unguarded stdlib `re`. Without this
            # an operator pattern here both (a) escapes the ReDoS deadline and (b)
            # crashes with `re.error` on regex-only syntax the load-gate accepted.
            return _derive_project(rel_posix, entry,
                                   operator_supplied=config.paths_operator_supplied)
    return VAULT_TIER_PROJECT


# --------------------------------------------------------------------------- #
# Vault → LayoutConfig resolution (used by reindex.discover_pages)
# --------------------------------------------------------------------------- #


def resolve_layout_config(vault_root: Path) -> LayoutConfig:
    """Resolve the layout grammar for a vault root. Reads `WIKI_SCHEMA.md`
    frontmatter `layout:` (+ optional `layout_config:`) if present; **defaults to
    `karpathy` when the schema is absent or carries no layout** — so vaults built
    without a `WIKI_SCHEMA.md` (most test vaults, and any pre-R-X1 vault) keep
    walking exactly as before (byte-identity / back-compat)."""
    root_config: dict[str, Any] = {}
    if (vault_root / SCHEMA_FILE).is_file():
        try:
            root_config = load_root_config(vault_root)
        except (VaultRootNotFoundError, ConfigValidationError):
            root_config = {}
    if not root_config.get("layout"):
        root_config = {**root_config, "layout": "karpathy"}
    return load_layout_config(vault_root, root_config)
