"""TASK 058 — the `wiki-config validate`/`doctor` finding taxonomy + renderers.

One registry row per stable machine code: severity (error | warning | info) ×
fix tier (safe | confirm | manual). Value-free posture throughout (CWE-209/117):
messages carry JSON pointers, file paths (our own walk labels), and SCHEMA
constants — never an operator-typed value or regex pattern. Operator KEY NAMES
pass through `safe_key` (printable subset, capped).

Renderers mirror the wiki-lint output split: stdout = histogram envelope only;
`--json-sidecar` = the full findings array; `--report` = grouped markdown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SEV_ERROR = "error"
SEV_WARNING = "warning"
SEV_INFO = "info"

TIER_SAFE = "safe"
TIER_CONFIRM = "confirm"
TIER_MANUAL = "manual"


@dataclass(frozen=True)
class FindingKind:
    code: str
    severity: str
    tier: str


# The canonical taxonomy (TASK 058 design table). Codes are API — stable.
_KINDS: tuple[FindingKind, ...] = (
    # --- hard gates (loader-refused files) --------------------------------- #
    FindingKind("SYMLINK", SEV_ERROR, TIER_MANUAL),
    FindingKind("OUTSIDE_VAULT", SEV_ERROR, TIER_MANUAL),
    FindingKind("UNRESOLVABLE", SEV_ERROR, TIER_MANUAL),
    FindingKind("SIZE_CAP", SEV_ERROR, TIER_MANUAL),
    FindingKind("YAML_ALIAS_BANNED", SEV_ERROR, TIER_CONFIRM),
    FindingKind("YAML_ANCHOR_BANNED", SEV_ERROR, TIER_CONFIRM),
    FindingKind("PARSE_ERROR", SEV_ERROR, TIER_MANUAL),
    FindingKind("NOT_A_MAPPING", SEV_ERROR, TIER_MANUAL),
    FindingKind("UNREADABLE", SEV_ERROR, TIER_MANUAL),
    # --- schema violations (enumerated, not fail-fast) --------------------- #
    FindingKind("SCHEMA_VIOLATION_TYPE", SEV_ERROR, TIER_MANUAL),
    FindingKind("SCHEMA_VIOLATION_ENUM", SEV_ERROR, TIER_CONFIRM),
    FindingKind("SCHEMA_VIOLATION_PATTERN", SEV_ERROR, TIER_MANUAL),
    FindingKind("SCHEMA_VIOLATION", SEV_ERROR, TIER_MANUAL),
    FindingKind("UNKNOWN_KEY", SEV_ERROR, TIER_CONFIRM),
    FindingKind("UNKNOWN_KEY_TYPO", SEV_ERROR, TIER_CONFIRM),
    # --- per-file advisory -------------------------------------------------- #
    FindingKind("EMPTY_FILE", SEV_INFO, TIER_CONFIRM),
    FindingKind("NON_CASCADING_KEY_IN_SUBFOLDER", SEV_WARNING, TIER_CONFIRM),
    FindingKind("INVALID_REGEX", SEV_ERROR, TIER_MANUAL),
    FindingKind("REDOS_UNSAFE_REGEX", SEV_ERROR, TIER_MANUAL),
    FindingKind("GROUP_KEY_NO_CAPTURE", SEV_WARNING, TIER_SAFE),
    FindingKind("MIRROR_REGEX_DOUBLE_ESCAPE", SEV_WARNING, TIER_CONFIRM),
    FindingKind("MIRROR_EXT_NO_DOT", SEV_ERROR, TIER_SAFE),
    FindingKind("DUPLICATE_LIST_ITEM", SEV_INFO, TIER_SAFE),
    FindingKind("ZONE_GLOB_NO_MATCH", SEV_INFO, TIER_MANUAL),
    FindingKind("EXCLUDE_GLOB_NO_MATCH", SEV_INFO, TIER_MANUAL),
    FindingKind("ORPHAN_WIKI_DIR", SEV_INFO, TIER_CONFIRM),
    # --- cross-level (cascade) ---------------------------------------------- #
    FindingKind("REDUNDANT_OVERRIDE", SEV_INFO, TIER_CONFIRM),
    FindingKind("LIST_REPLACE_SHADOW", SEV_INFO, TIER_MANUAL),
    FindingKind("GROUP_KEY_SHADOWED_BY_KEY", SEV_WARNING, TIER_MANUAL),
    FindingKind("CONFLICTING_MIRROR_LEVELS", SEV_INFO, TIER_MANUAL),
    FindingKind("MIRROR_TEMPLATE_GROUP_MISSING", SEV_ERROR, TIER_MANUAL),
    FindingKind("MIRROR_DIR_OUTSIDE_VAULT", SEV_WARNING, TIER_MANUAL),
    FindingKind("MIRROR_SCOPE_MISSING", SEV_INFO, TIER_MANUAL),
    FindingKind("MIRROR_KEYS_NOTHING", SEV_INFO, TIER_MANUAL),
    FindingKind("UNSAFE_TARGET_SUBDIR", SEV_ERROR, TIER_MANUAL),
    FindingKind("SHADOWED_CONFIG", SEV_WARNING, TIER_MANUAL),
    # --- sibling config systems --------------------------------------------- #
    FindingKind("LAYOUT_CONFIG_INVALID", SEV_ERROR, TIER_MANUAL),
    FindingKind("IDENTITY_CONFIG_INVALID", SEV_ERROR, TIER_MANUAL),
    FindingKind("PROJECT_OVERRIDE_INVALID", SEV_ERROR, TIER_MANUAL),
    # --- templates (detection lands with the templates subsystem, Phase 4) --- #
    FindingKind("TEMPLATE_DRIFT", SEV_INFO, TIER_MANUAL),
    FindingKind("SCHEMA_MODELINE_MISSING", SEV_INFO, TIER_SAFE),
    FindingKind("SCHEMA_MODELINE_STALE", SEV_INFO, TIER_SAFE),
)

TAXONOMY: dict[str, FindingKind] = {k.code: k for k in _KINDS}


def safe_key(name: str, *, cap: int = 64) -> str:
    """Operator-typed key name → printable subset, capped (CWE-209/117 posture
    mirror of `wiki_index.lint._safe_surface`)."""
    return "".join(ch for ch in name if ch.isprintable())[:cap]


@dataclass(frozen=True)
class ConfigFinding:
    """One validate/doctor finding. `file` is a vault-relative path from our own
    walk; `pointer` a JSON pointer ('' when file-level); `data` carries ONLY
    value-free extras (sanitized key names, schema-constant suggestions)."""

    code: str
    system: str  # sync | layout | identity
    file: str
    pointer: str = ""
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    file_hash: str | None = None

    @property
    def kind(self) -> FindingKind:
        return TAXONOMY[self.code]

    def to_json(self) -> dict[str, Any]:
        kind = self.kind
        out: dict[str, Any] = {
            "code": self.code,
            "severity": kind.severity,
            "tier": kind.tier,
            "system": self.system,
            "file": self.file,
            "pointer": self.pointer,
            "message": self.message,
        }
        if self.data:
            out["data"] = dict(self.data)
        if self.file_hash:
            out["file_hash"] = self.file_hash
        return out


def sort_findings(findings: list[ConfigFinding]) -> list[ConfigFinding]:
    """Deterministic output order: file, then pointer, then code."""
    return sorted(findings, key=lambda f: (f.file, f.pointer, f.code))


def histogram(findings: list[ConfigFinding]) -> dict[str, Any]:
    by_code: dict[str, int] = {}
    by_severity = {SEV_ERROR: 0, SEV_WARNING: 0, SEV_INFO: 0}
    fixable = {TIER_SAFE: 0, TIER_CONFIRM: 0, TIER_MANUAL: 0}
    for finding in findings:
        by_code[finding.code] = by_code.get(finding.code, 0) + 1
        by_severity[finding.kind.severity] += 1
        fixable[finding.kind.tier] += 1
    return {
        "total_findings": len(findings),
        "by_code": dict(sorted(by_code.items())),
        "by_severity": by_severity,
        "fixable": fixable,
    }


def render_findings_report(
    findings: list[ConfigFinding], vault_root_label: str
) -> str:
    lines: list[str] = [
        "# wiki-config validate",
        "",
        f"Vault: `{vault_root_label}` — {len(findings)} finding(s)",
        "",
    ]
    current_file = None
    for finding in sort_findings(findings):
        if finding.file != current_file:
            current_file = finding.file
            lines += [f"## `{finding.file}`", ""]
        kind = finding.kind
        pointer = f" `{finding.pointer}`" if finding.pointer else ""
        lines.append(
            f"- **{finding.code}** ({kind.severity}, fix: {kind.tier}){pointer} — "
            f"{finding.message}"
        )
    if not findings:
        lines.append("No findings — all config files are clean.")
    return "\n".join(lines) + "\n"
