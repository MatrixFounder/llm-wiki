"""wiki-lint orchestration: run all SQL-level checks, return issues."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.wiki_index.repository import IndexRepository

Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class LintIssue:
    category: str
    severity: Severity
    vault_id: str
    page_slug: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


def _safe_surface(s: str) -> str:
    """CWE-117 (F5, vdd-multi): strip control chars + cap an untrusted alias
    surface before it enters an operator-facing lint report (markdown / JSON
    sidecar). The surface originates from `_raw/`-derived frontmatter and is
    only edge-stripped at ingest."""
    return "".join(c for c in s if ord(c) >= 32)[:200]


def run_all_checks(
    repo: "IndexRepository", *, vaults: list[str] | None = None,
    strict: bool = False,
) -> list[LintIssue]:
    """Run SQL-level lint checks across the given vaults (or all if None)."""
    issues: list[LintIssue] = []
    target_vaults: list[str]
    if vaults is None:
        target_vaults = [v.vault_id for v in repo.list_vaults()]
    else:
        target_vaults = vaults

    for vid in target_vaults:
        v = repo.get_vault(vid)
        if v is None:
            continue
        # Orphan links
        for orph in repo.find_orphan_links(vid):
            issues.append(LintIssue(
                category="orphan-link",
                severity="warning" if not strict else "error",
                vault_id=vid,
                page_slug=orph.source_page_slug,
                details={"target": orph.target_slug,
                         "project": orph.source_page_project,
                         "line": orph.line_start},
            ))
        # Drift
        drift = repo.check_drift(vid)
        for f in drift.missing_in_db:
            issues.append(LintIssue(
                category="missing-in-db", severity="warning",
                vault_id=vid, details={"file": str(f)},
            ))
        for slug, project in drift.missing_on_disk:
            issues.append(LintIssue(
                category="missing-on-disk", severity="error",
                vault_id=vid, page_slug=slug,
                details={"project": project},
            ))
        for slug, project in drift.hash_mismatch:
            issues.append(LintIssue(
                category="hash-mismatch", severity="warning",
                vault_id=vid, page_slug=slug,
                details={"project": project},
            ))
        for slug, project, file_type, db_type in drift.type_mismatch:
            issues.append(LintIssue(
                category="type-mismatch", severity="warning",
                vault_id=vid, page_slug=slug,
                details={"project": project,
                         "file_type": file_type, "db_type": db_type},
            ))
        # Alias collisions (R-5.6). `find_alias_collisions` returns all kinds —
        # in_table (legacy), cross_slug / cross_name (alias == another entity's
        # slug/name), and **frontmatter** (P-10, TASK 006: ≥2 entity pages claim
        # the same `aliases:` surface, read from pages.frontmatter_json in the DB
        # — no per-file YAML re-parse; the old file-scan helper was removed).
        sev: Severity = "error" if strict else "warning"
        for col in repo.find_alias_collisions(vid):
            issues.append(LintIssue(
                category="alias-collision", severity=sev, vault_id=vid,
                details={"alias": _safe_surface(col.alias), "slugs": col.slugs,
                         "kind": col.kind},
            ))

    # Cross-vault duplicates (R-29)
    for slug, vault_ids in repo.find_cross_vault_concept_duplicates():
        issues.append(LintIssue(
            category="cross-vault-duplicate",
            severity="info",
            vault_id=",".join(vault_ids),
            page_slug=slug,
            details={"vaults": vault_ids,
                     "hint": "Consider promotion via wiki-ingest promote"},
        ))
    return issues


def render_markdown_report(issues: list[LintIssue]) -> str:
    """Render lint issues as a markdown report."""
    lines = ["# Wiki Lint Report", ""]
    if not issues:
        lines.append("✅ Healthy. No issues found.")
        return "\n".join(lines) + "\n"
    by_cat: dict[str, list[LintIssue]] = {}
    for i in issues:
        by_cat.setdefault(i.category, []).append(i)
    lines.append(f"**{len(issues)} issue(s)** across {len(by_cat)} categories.")
    lines.append("")
    for cat in sorted(by_cat):
        cat_issues = by_cat[cat]
        lines.append(f"## {cat} ({len(cat_issues)})")
        for i in cat_issues:
            page = f"`{i.page_slug}`" if i.page_slug else ""
            lines.append(f"- [{i.severity}] vault={i.vault_id} {page} {i.details}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_json_sidecar(issues: list[LintIssue]) -> str:
    """Render lint issues as JSON array."""
    import json
    return json.dumps([
        {
            "category": i.category,
            "severity": i.severity,
            "vault_id": i.vault_id,
            "page_slug": i.page_slug,
            "details": i.details,
        }
        for i in issues
    ], ensure_ascii=False, indent=2)
