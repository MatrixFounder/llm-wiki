"""TASK 058 — the `wiki-config validate` engine: whole-tree, all-findings lint
over the three vault config systems.

Layering (the no-duplication rule): the LOADERS stay the single authority for
the load/refuse verdict — pass 1 CALLS `_load_validated_raw` (sync),
`resolve_layout_config` (layout), `load_root_config` (identity) and merely
catches their exceptions instead of dying. The linter owns only (a) the
enumeration a fail-fast loader cannot express (all schema violations, via the
SAME validator singleton's `iter_errors`), and (b) advisory findings the strict
schema cannot see (regex health, ignored keys, cross-level cascade analysis).

Four passes:
  0. discovery walk (configured dirs, orphan `.wiki` dirs, `.wiki.yaml` overrides)
  1. hard gates per file (loader verdict → finding code via `SyncConfigError.reason`)
  2. per-file advisory (regex/glob/list checks — regex FIELDS come from the schema's
     `x-wiki-format` annotations via the UI model, never a hardcoded key list)
  3. cross-level cascade analysis (redundant override, list-replace shadow,
     key-supersedes-group_key, merged-mirror health, bounded dead-detector probe)

Value-free posture (CWE-209/117): findings carry pointers/labels/schema
constants; operator values and regex patterns are never echoed.
"""

from __future__ import annotations

import difflib
import hashlib
import os
import string
import time
from pathlib import Path
from typing import Any, Callable, Iterator

import regex as regex_mod
import yaml

import scripts.wiki_index.layout_config as _lc
from scripts.wiki_index.config_loader import (
    ConfigValidationError,
    load_config,
    load_project_override,
)
from scripts.wiki_index.layout_config import LayoutConfigError, resolve_layout_config
from scripts.wiki_index.sync_config import (
    SyncConfigError,
    _get_validator,
    _load_validated_raw,
    _parse_resummarize,
    _parse_summarize,
)
from scripts.wiki_skills._resummarize import _compose_key, _key_specs, _with_flags

from ._findings import ConfigFinding, safe_key
from ._provenance import _PRUNE_DIRS, _rel_label, ROOT_LABEL
from ._uimodel import (
    SCOPE_CASCADING,
    FieldSpec,
    build_ui_model,
    top_level_keys,
)

# Bounded filesystem probes (info-severity checks must not scan a huge vault).
_PROBE_DIR_CAP = 500
_PROBE_FILE_CAP = 500
_PROBE_SCOPE_CAP = 3

_REASON_TO_CODE = {
    "SYMLINK": "SYMLINK",
    "OUTSIDE_VAULT": "OUTSIDE_VAULT",
    "UNRESOLVABLE": "UNRESOLVABLE",
    "SIZE_CAP": "SIZE_CAP",
    "ALIAS": "YAML_ALIAS_BANNED",
    "ANCHOR": "YAML_ANCHOR_BANNED",
    "PARSE": "PARSE_ERROR",
    "NOT_MAPPING": "NOT_A_MAPPING",
    "UNSAFE_SUBDIR": "UNSAFE_TARGET_SUBDIR",
}

_WIKI_DIR_ARTIFACTS = frozenset({
    "sync.yaml", "layout.yaml", "backups", "templates", "page-types",
    "config-report.html",
})


def _sync_rel(label: str) -> str:
    return (".wiki/sync.yaml" if label == "." else f"{label}/.wiki/sync.yaml")


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _get_by_pointer(raw: dict[str, Any], pointer: str) -> Any:
    cur: Any = raw
    for part in pointer.lstrip("/").split("/"):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _iter_lists(node: Any, pointer: str) -> Iterator[tuple[str, list[Any]]]:
    if isinstance(node, dict):
        for key, child in node.items():
            yield from _iter_lists(child, f"{pointer}/{key}")
    elif isinstance(node, list):
        yield pointer, node


def _iter_leaves(node: Any, pointer: str) -> Iterator[tuple[str, Any]]:
    if isinstance(node, dict):
        for key, child in node.items():
            yield from _iter_leaves(child, f"{pointer}/{key}")
    else:
        yield pointer, node


def _glob_matches_label(pattern: str, label: str) -> bool:
    """Does a root `exclude:` glob cover the folder `label`? Pragmatic superset
    of the walk-prune semantics: a `<prefix>/**` pattern covers the prefix dir
    and everything below; otherwise fnmatch on the label itself."""
    import fnmatch

    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return label == prefix or label.startswith(prefix + "/")
    return fnmatch.fnmatch(label, pattern)


class _Linter:
    def __init__(self, vault_root: Path, model: dict[str, FieldSpec] | None) -> None:
        self.vault_root = vault_root
        self.model = model if model is not None else build_ui_model()
        self.cascading = set(top_level_keys(self.model, SCOPE_CASCADING))
        self.findings: list[ConfigFinding] = []
        self.files_checked = 0
        # label → (raw dict | None on hard failure)
        self.raws: dict[str, dict[str, Any] | None] = {}
        self.hashes: dict[str, str | None] = {}

    def add(self, code: str, system: str, file: str, pointer: str = "",
            message: str = "", **data: Any) -> None:
        self.findings.append(ConfigFinding(
            code=code, system=system, file=file, pointer=pointer,
            message=message, data={k: v for k, v in data.items() if v is not None},
            file_hash=self.hashes.get(file),
        ))

    # ------------------------------------------------------------------ #
    # pass 0 — discovery
    # ------------------------------------------------------------------ #

    def discover(self) -> tuple[list[tuple[str, Path]], list[Path], list[Path]]:
        configured: list[tuple[str, Path]] = []
        wiki_yaml_overrides: list[Path] = []
        orphan_wiki_dirs: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(self.vault_root, followlinks=False):
            dirnames[:] = sorted(
                d for d in dirnames if d not in _PRUNE_DIRS and not d.startswith(".")
            )
            d = Path(dirpath)
            wiki = d / ".wiki"
            if wiki.is_dir():
                if (wiki / "sync.yaml").is_file():
                    label = _rel_label(d, self.vault_root)
                    configured.append(("." if label == ROOT_LABEL else label, d))
                elif not any((wiki / a).exists() for a in _WIKI_DIR_ARTIFACTS):
                    orphan_wiki_dirs.append(wiki)
            if ".wiki.yaml" in filenames:
                wiki_yaml_overrides.append(d)
        return configured, orphan_wiki_dirs, wiki_yaml_overrides

    # ------------------------------------------------------------------ #
    # pass 1 — hard gates (loader-owned verdicts)
    # ------------------------------------------------------------------ #

    def gate_sync_file(self, label: str, d: Path) -> None:
        rel = _sync_rel(label)
        self.files_checked += 1
        self.hashes[rel] = _sha256(d / ".wiki" / "sync.yaml")
        try:
            self.raws[label] = _load_validated_raw(d)
        except OSError:
            self.raws[label] = None
            self.add("UNREADABLE", "sync", rel,
                     message="config cannot be read (permissions or an iCloud "
                             "placeholder not downloaded locally)")
        except SyncConfigError as exc:
            self.raws[label] = None
            if exc.reason == "SCHEMA":
                self._enumerate_schema_errors(label, d, rel)
            else:
                code = _REASON_TO_CODE.get(exc.reason, "PARSE_ERROR")
                self.add(code, "sync", rel, message=exc.detail)

    def _enumerate_schema_errors(self, label: str, d: Path, rel: str) -> None:
        """Stages 0-2 passed (reason SCHEMA), so a re-parse with the SAME
        hardened loader is safe; enumerate ALL violations via the SAME
        validator singleton the loader uses."""
        from scripts.wiki_index.sync_config import _NoAliasSafeLoader

        try:
            raw = yaml.load((d / ".wiki" / "sync.yaml").read_text(encoding="utf-8"),
                            Loader=_NoAliasSafeLoader)
        except Exception:  # drifted between the two reads — report the verdict only
            self.add("PARSE_ERROR", "sync", rel, message="config changed during lint")
            return
        if not isinstance(raw, dict):
            self.add("NOT_A_MAPPING", "sync", rel,
                     message="top level must be a YAML mapping")
            return
        for err in _get_validator().iter_errors(raw):
            pointer = "/" + "/".join(str(p) for p in err.absolute_path)
            if err.validator == "additionalProperties":
                schema = err.schema if isinstance(err.schema, dict) else {}
                allowed = sorted((schema.get("properties") or {}).keys())
                instance = err.instance if isinstance(err.instance, dict) else {}
                for key in instance:
                    if key in allowed:
                        continue
                    shown = safe_key(str(key))
                    suggestion = difflib.get_close_matches(str(key), allowed, 1, 0.75)
                    if suggestion:
                        self.add("UNKNOWN_KEY_TYPO", "sync", rel,
                                 pointer=f"{pointer}/{shown}",
                                 message=f"unknown key '{shown}' — did you mean "
                                         f"'{suggestion[0]}'?",
                                 key=shown, suggestion=suggestion[0])
                    else:
                        self.add("UNKNOWN_KEY", "sync", rel,
                                 pointer=f"{pointer}/{shown}",
                                 message=f"unknown key '{shown}'", key=shown)
            elif err.validator == "enum":
                allowed_vals = [str(v) for v in err.validator_value] \
                    if isinstance(err.validator_value, list) else []
                suggestion = difflib.get_close_matches(
                    str(err.instance), allowed_vals, 1, 0.6)
                extra = f", did you mean '{suggestion[0]}'?" if suggestion else ""
                self.add("SCHEMA_VIOLATION_ENUM", "sync", rel, pointer=pointer,
                         message="not one of the allowed values "
                                 f"({', '.join(allowed_vals)}){extra}",
                         allowed=allowed_vals,
                         suggestion=suggestion[0] if suggestion else None)
            elif err.validator == "type":
                self.add("SCHEMA_VIOLATION_TYPE", "sync", rel, pointer=pointer,
                         message=f"wrong type (expected {err.validator_value})",
                         expected=str(err.validator_value))
            elif err.validator == "pattern":
                self.add("SCHEMA_VIOLATION_PATTERN", "sync", rel, pointer=pointer,
                         message="value fails the schema pattern "
                                 "(e.g. prefer_ext entries need a leading dot)")
            else:
                self.add("SCHEMA_VIOLATION", "sync", rel, pointer=pointer,
                         message=f"schema violation ({err.validator})",
                         validator=str(err.validator))

    # ------------------------------------------------------------------ #
    # pass 2 — per-file advisory
    # ------------------------------------------------------------------ #

    def advise_sync_file(self, label: str, raw: dict[str, Any]) -> None:
        rel = _sync_rel(label)
        is_root = label == "."
        if raw == {}:
            self.add("EMPTY_FILE", "sync", rel,
                     message="empty config — equivalent to absent")
            return
        non_cascading = [k for k in raw if k not in self.cascading]
        if not is_root and non_cascading:
            keys = ", ".join(f"'{safe_key(str(k))}'" for k in non_cascading)
            self.add("NON_CASCADING_KEY_IN_SUBFOLDER", "sync", rel,
                     message=f"{keys}: consumed ONLY from the vault-root sync.yaml "
                             "— silently ignored here",
                     keys=[safe_key(str(k)) for k in non_cascading])
        self._check_regex_fields(rel, raw)
        self._check_mirror_ext(rel, raw)
        for pointer, items in _iter_lists(raw, ""):
            scalars = [i for i in items if not isinstance(i, (dict, list))]
            if len(scalars) != len(set(map(str, scalars))):
                self.add("DUPLICATE_LIST_ITEM", "sync", rel, pointer=pointer,
                         message="duplicate list entry (first occurrence wins)")
        if is_root:
            self._check_globs(rel, raw)

    def _check_regex_fields(self, rel: str, raw: dict[str, Any]) -> None:
        """Regex health for every field the SCHEMA marks x-wiki-format: regex."""
        for pointer, spec in self.model.items():
            if spec.fmt != "regex":
                continue
            value = _get_by_pointer(raw, pointer)
            if not isinstance(value, str):
                continue
            if "\\\\" in value:
                self.add("MIRROR_REGEX_DOUBLE_ESCAPE", "sync", rel, pointer=pointer,
                         message="pattern contains a literal double backslash (the "
                                 "YAML single-quote trap): it matches a literal '\\' "
                                 "character, not the intended class")
            try:
                compiled = regex_mod.compile(value)
            except regex_mod.error:
                self.add("INVALID_REGEX", "sync", rel, pointer=pointer,
                         message="regex does not compile (pattern not echoed)")
                continue
            if not _lc.is_pattern_redos_safe(value, operator=True):
                self.add("REDOS_UNSAFE_REGEX", "sync", rel, pointer=pointer,
                         message="regex exceeds the ReDoS budget — rewrite it "
                                 "(pattern not echoed)")
                continue
            if compiled.groups == 0 and not self._has_sibling_template(raw, pointer):
                self.add("GROUP_KEY_NO_CAPTURE", "sync", rel, pointer=pointer,
                         message="no capture group — the WHOLE match becomes the key "
                                 "(group(0) fallback); wrapping the pattern in (...) "
                                 "is behavior-identical and explicit")

    @staticmethod
    def _has_sibling_template(raw: dict[str, Any], pointer: str) -> bool:
        parent = pointer.rsplit("/", 1)[0]
        block = _get_by_pointer(raw, parent) if parent else raw
        return isinstance(block, dict) and bool(block.get("template"))

    def _check_mirror_ext(self, rel: str, raw: dict[str, Any]) -> None:
        ext = _get_by_pointer(raw, "/resummarize/detect/mirror/summary_ext")
        if isinstance(ext, str) and ext and not ext.startswith("."):
            self.add("MIRROR_EXT_NO_DOT", "sync", rel,
                     pointer="/resummarize/detect/mirror/summary_ext",
                     message="summary_ext must start with '.' — the stem-relpath "
                             "mirror crashes on it at runtime")

    def _check_globs(self, rel: str, raw: dict[str, Any]) -> None:
        for key, code in (("zones", "ZONE_GLOB_NO_MATCH"),
                          ("exclude", "EXCLUDE_GLOB_NO_MATCH")):
            value = raw.get(key)
            if not isinstance(value, list):
                continue
            for i, pat in enumerate(value):
                if not isinstance(pat, str):
                    continue
                try:
                    hit = next(iter(self.vault_root.glob(pat)), None)
                except (ValueError, NotImplementedError, OSError):
                    continue
                if hit is None:
                    self.add(code, "sync", rel, pointer=f"/{key}/{i}",
                             message=f"{key}[{i}] matches nothing on disk")

    # ------------------------------------------------------------------ #
    # pass 3 — cross-level cascade analysis
    # ------------------------------------------------------------------ #

    def _configured_ancestors(self, label: str) -> list[str]:
        """Configured levels strictly ABOVE `label`, shallowest first ('.' first)."""
        out = [a for a in self.raws
               if a != label and self.raws[a] is not None
               and (a == "." or (label != "." and label.startswith(a + "/")))]
        return sorted(out, key=lambda a: 0 if a == "." else a.count("/") + 1)

    def cross_level(self, label: str, raw: dict[str, Any]) -> None:
        from scripts.wiki_index.config_loader import deep_merge

        rel = _sync_rel(label)
        for block_name in sorted(self.cascading):
            own = raw.get(block_name)
            inherited: dict[str, Any] = {}
            for ancestor in self._configured_ancestors(label):
                anc_raw = self.raws.get(ancestor)
                anc_block = (anc_raw or {}).get(block_name)
                if isinstance(anc_block, dict):
                    inherited = deep_merge(inherited, anc_block)
            if isinstance(own, dict) and inherited:
                for pointer, value in _iter_leaves(own, f"/{block_name}"):
                    inh = _get_by_pointer(inherited, pointer[len(block_name) + 1:])
                    if inh is None:
                        continue
                    if isinstance(value, list) and isinstance(inh, list):
                        if value == inh:
                            self.add("REDUNDANT_OVERRIDE", "sync", rel, pointer=pointer,
                                     message="identical to the inherited value — "
                                             "redundant today, but removing it un-pins "
                                             "the folder from future parent edits")
                        else:
                            self.add("LIST_REPLACE_SHADOW", "sync", rel, pointer=pointer,
                                     message=f"this list REPLACES the ancestor's "
                                             f"{len(inh)}-item list entirely (lists "
                                             "never extend in the cascade)")
                    elif not isinstance(value, (dict, list)) and value == inh:
                        self.add("REDUNDANT_OVERRIDE", "sync", rel, pointer=pointer,
                                 message="identical to the inherited value — redundant "
                                         "today, but removing it un-pins the folder "
                                         "from future parent edits")
            merged = inherited
            if isinstance(own, dict):
                merged = deep_merge(inherited, own)
            if block_name == "resummarize" and isinstance(own, dict):
                self._check_merged_mirror(label, rel, merged, own, inherited)
            if block_name == "summarize" and (isinstance(own, dict) or inherited):
                try:
                    _parse_summarize(merged)
                except SyncConfigError:
                    self.add("UNSAFE_TARGET_SUBDIR", "sync", rel,
                             pointer="/summarize/target_subdir",
                             message="target_subdir is not a safe relative path")

    def _check_merged_mirror(
        self, label: str, rel: str, merged: dict[str, Any],
        own: dict[str, Any], inherited: dict[str, Any],
    ) -> None:
        mirror = _get_by_pointer(merged, "/detect/mirror")
        if not isinstance(mirror, dict):
            return
        key_block = mirror.get("key")
        has_key_regex = isinstance(key_block, dict) and (
            key_block.get("raw_regex") or key_block.get("summary_regex"))
        if has_key_regex and mirror.get("group_key"):
            self.add("GROUP_KEY_SHADOWED_BY_KEY", "sync", rel,
                     pointer="/resummarize/detect/mirror/group_key",
                     message="'group_key' is superseded by the (possibly inherited) "
                             "'key' block — it has no effect")
        own_mirror = _get_by_pointer(own, "/detect/mirror")
        inh_mirror = _get_by_pointer(inherited, "/detect/mirror")
        if isinstance(own_mirror, dict) and isinstance(inh_mirror, dict) and inh_mirror:
            own_leaves = {p for p, _ in _iter_leaves(own_mirror, "")}
            inh_leaves = {p for p, _ in _iter_leaves(inh_mirror, "")}
            if own_leaves - inh_leaves and inh_leaves - own_leaves:
                self.add("CONFLICTING_MIRROR_LEVELS", "sync", rel,
                         pointer="/resummarize/detect/mirror",
                         message="the effective mirror config is assembled from "
                                 "multiple levels — verify the merged result "
                                 "(wiki-config show) is intended")
        if not mirror.get("enabled"):
            return
        try:
            parsed = _parse_resummarize(merged)
        except SyncConfigError:
            return
        if parsed is None:
            return
        mc = parsed.detect.mirror
        raw_pat, summ_pat, template, flags = _key_specs(mc)
        raw_pat, summ_pat = _with_flags(raw_pat, flags), _with_flags(summ_pat, flags)
        if template:
            self._check_template_groups(rel, raw_pat, summ_pat, template)
        parts = [p for p in str(mc.summary_dir).split("/") if p]
        if str(mc.summary_dir).startswith("/") or ".." in parts:
            self.add("MIRROR_DIR_OUTSIDE_VAULT", "sync", rel,
                     pointer="/resummarize/detect/mirror/summary_dir",
                     message="summary_dir escapes the vault — the mirror detector "
                             "silently disables itself at runtime")
            return
        if isinstance(own_mirror, dict):  # probe only where mirror is DEFINED
            self._probe_mirror_fs(label, rel, mc.raw_dirs, str(mc.summary_dir),
                                  str(mc.summary_ext), raw_pat, summ_pat, template)

    def _check_template_groups(
        self, rel: str, raw_pat: str, summ_pat: str, template: str
    ) -> None:
        try:
            wanted = set(string.Template(template).get_identifiers())
        except ValueError:
            wanted = set()
        for side, pat in (("raw", raw_pat), ("summary", summ_pat)):
            try:
                names = set(regex_mod.compile(pat).groupindex.keys())
            except regex_mod.error:
                continue  # INVALID_REGEX already reported in pass 2
            missing = sorted(wanted - names)
            if missing:
                self.add("MIRROR_TEMPLATE_GROUP_MISSING", "sync", rel,
                         pointer="/resummarize/detect/mirror/key/template",
                         message=f"template names group(s) {', '.join(missing)} absent "
                                 f"from the {side}-side regex — the mirror detector "
                                 "is silently inert",
                         side=side, missing=missing)

    def _probe_mirror_fs(
        self, label: str, rel: str, raw_dirs: tuple[str, ...], summary_dir: str,
        summary_ext: str, raw_pat: str, summ_pat: str, template: str | None,
    ) -> None:
        """Bounded dead-detector probe (info severity, capped walk)."""
        folder = self.vault_root if label == "." else self.vault_root / label
        anchors: list[Path] = []
        seen = 0
        for dirpath, dirnames, _files in os.walk(folder, followlinks=False):
            dirnames[:] = [d for d in dirnames
                           if d not in _PRUNE_DIRS and not d.startswith(".")]
            seen += 1
            if seen > _PROBE_DIR_CAP:
                return  # vault too big for an advisory probe — stay silent
            d = Path(dirpath)
            if d.name in raw_dirs:
                anchors.append(d)
        if not anchors:
            return
        scopes: list[Path] = []
        for anchor in anchors:
            scope = anchor if summary_dir == "." else anchor.parent / summary_dir
            if scope.is_dir():
                scopes.append(scope)
        if not scopes:
            self.add("MIRROR_SCOPE_MISSING", "sync", rel,
                     pointer="/resummarize/detect/mirror/summary_dir",
                     message="mirror raw_dirs anchors exist but no sibling "
                             "summary_dir does — the detector can never match")
            return
        deadline = time.monotonic() + _lc.WIKI_REDOS_BUDGET_S
        for scope in scopes[:_PROBE_SCOPE_CAP]:
            n_files = 0
            keyed = 0
            for summ in scope.rglob("*" + summary_ext, recurse_symlinks=False):
                n_files += 1
                if n_files > _PROBE_FILE_CAP:
                    break
                if _compose_key(summ.stem, summ_pat, template, deadline=deadline):
                    keyed += 1
            if n_files and not keyed:
                self.add("MIRROR_KEYS_NOTHING", "sync", rel,
                         pointer="/resummarize/detect/mirror",
                         message=f"the mirror regex keys 0 of {n_files} summaries in "
                                 "a scope — the detector is inert (misconfigured "
                                 "group_key/key, e.g. a YAML double-backslash?)")
                return

    def shadowed_configs(self) -> None:
        root_raw = self.raws.get(".")
        excludes = (root_raw or {}).get("exclude")
        if not isinstance(excludes, list):
            return
        patterns = [p for p in excludes if isinstance(p, str)]
        for label, raw in self.raws.items():
            if label == "." or raw is None:
                continue
            if any(_glob_matches_label(p, label) for p in patterns):
                self.add("SHADOWED_CONFIG", "sync", _sync_rel(label),
                         message="this folder is excluded at the vault root — its "
                                 "config is never consulted by scans")

    # ------------------------------------------------------------------ #
    # sibling config systems
    # ------------------------------------------------------------------ #

    def sibling_systems(self, wiki_yaml_dirs: list[Path]) -> None:
        """Verdicts only, via the owning loaders. Their exception texts may echo
        offending values, so findings carry a GENERIC message (CWE-209) and
        point the operator at the owning loader for detail."""
        layout_file = self.vault_root / ".wiki" / "layout.yaml"
        if layout_file.is_file():
            self.files_checked += 1
            self.hashes[".wiki/layout.yaml"] = _sha256(layout_file)
            try:
                resolve_layout_config(self.vault_root)
            except LayoutConfigError:
                self.add("LAYOUT_CONFIG_INVALID", "layout", ".wiki/layout.yaml",
                         message="layout override fails the layout-config loader "
                                 "(schema config/layout-config.schema.yaml); run "
                                 "wiki-reindex --delta for the full loader error")
        identity_file = self.vault_root / "WIKI_SCHEMA.md"
        if identity_file.is_file():
            self.files_checked += 1
            self.hashes["WIKI_SCHEMA.md"] = _sha256(identity_file)
            try:
                load_config(self.vault_root)  # base + overlay + nearest override
            except (ConfigValidationError, ValueError, yaml.YAMLError):
                self.add("IDENTITY_CONFIG_INVALID", "identity", "WIKI_SCHEMA.md",
                         message="vault identity config fails the config_loader "
                                 "validation (schema config/wiki-config.schema.yaml)")
        for d in wiki_yaml_dirs:
            label = _rel_label(d, self.vault_root)
            rel = (".wiki.yaml" if label == ROOT_LABEL else f"{label}/.wiki.yaml")
            self.files_checked += 1
            self.hashes[rel] = _sha256(d / ".wiki.yaml")
            try:
                load_project_override(d)
            except (ConfigValidationError, ValueError, yaml.YAMLError, OSError):
                self.add("PROJECT_OVERRIDE_INVALID", "identity", rel,
                         message="project override is not a valid YAML mapping")


def lint_vault(
    vault_root: Path,
    model: dict[str, FieldSpec] | None = None,
    extra_passes: tuple[Callable[["_Linter"], None], ...] = (),
) -> tuple[list[ConfigFinding], int]:
    """Run all passes; returns (findings, files_checked). Never raises on a bad
    config file — every failure class is a finding."""
    linter = _Linter(vault_root, model)
    configured, orphans, wiki_yaml_dirs = linter.discover()
    for label, d in configured:
        linter.gate_sync_file(label, d)
    for label, _d in configured:
        raw = linter.raws.get(label)
        if raw is not None:
            linter.advise_sync_file(label, raw)
    for label, _d in configured:
        raw = linter.raws.get(label)
        if raw is not None:
            linter.cross_level(label, raw)
    linter.shadowed_configs()
    for wiki in orphans:
        rel = wiki.relative_to(vault_root).as_posix()
        linter.add("ORPHAN_WIKI_DIR", "sync", rel,
                   message="vestigial .wiki directory with no known artifacts")
    linter.sibling_systems(wiki_yaml_dirs)
    for extra in extra_passes:  # Phase 4 hook (template drift / modeline checks)
        extra(linter)
    return linter.findings, linter.files_checked
