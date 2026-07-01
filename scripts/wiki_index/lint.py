"""wiki-lint orchestration: run all SQL-level checks, return issues."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from scripts.wiki_index.layout_config import LayoutConfig
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
    strict: bool = False, mtime_skip: bool = False,
) -> list[LintIssue]:
    """Run SQL-level lint checks across the given vaults (or all if None).
    `mtime_skip` (the `wiki-lint --mtime-skip` opt-in, TASK 017 / P-3) is forwarded
    to `check_drift` — skips the re-hash for mtime-unchanged files (integrity-relaxed;
    default off → always full-hash)."""
    issues: list[LintIssue] = []
    # Resolve each vault's layout grammar ONCE and share it across the config-driven checks
    # below (vdd-multi perf LOW: it was resolved independently per check). Lazy import keeps
    # lint→layout_config off the module import graph (cycle-safe).
    from scripts.wiki_index.layout_config import resolve_layout_config
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
        drift = repo.check_drift(vid, trust_mtime=mtime_skip)
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
        # PW-Q (TASK 012) ledger drift + R-15 (A1) lifecycle-drift: both config-driven —
        # resolve the layout grammar ONCE and share it.
        config = resolve_layout_config(v.root_path)
        issues.extend(check_auto_generated_unchanged(repo, vid, v.root_path, config=config))
        issues.extend(
            check_lifecycle_drift(repo, vid, v.root_path, strict=strict, config=config))

    # Cross-vault duplicates (R-29)
    for slug, vault_ids in repo.find_cross_vault_concept_duplicates():
        issues.append(LintIssue(
            category="cross-vault-duplicate",
            severity="info",
            vault_id=",".join(vault_ids),
            page_slug=slug,
            details={"vaults": vault_ids,
                     "hint": "Consider promoting to the shared root tier "
                             "(relocate the page + wiki-reindex --delta; see WIKI_SCHEMA.md)"},
        ))
    return issues


def check_auto_generated_unchanged(
    repo: "IndexRepository", vault_id: str, vault_root: "Path",
    *, config: "LayoutConfig | None" = None,
) -> list[LintIssue]:
    """PW-Q (TASK 012): for each `auto_indexes[].output` (e.g. docs/KNOWN_ISSUES.md),
    re-render from the index and compare the header-stripped body sha256 against the
    on-disk file. A mismatch = a manual edit (or a stale render) of a Class-B
    rebuildable-markdown file → flag with a remediation hint (don't overwrite).
    Operator BEGIN-CUSTOM blocks are preserved in the re-render, so editing those
    is NOT flagged — only edits to the generated body. No-op for layouts without
    `auto_indexes[]` (Karpathy/obsidian-personal). `config` is reused from
    `run_all_checks` when provided, else resolved here (direct callers)."""
    from scripts.wiki_index.rendering import (
        auto_index_body_sha,
        extract_custom_sections,
        render_auto_index,
    )
    from scripts.wiki_index.sqlite_repository import SQLiteRepository

    if not isinstance(repo, SQLiteRepository):
        return []
    out: list[LintIssue] = []
    if config is None:
        from scripts.wiki_index.layout_config import resolve_layout_config
        config = resolve_layout_config(vault_root)
    for auto_index in config.auto_indexes:
        output_rel = str(auto_index["output"])
        out_path = vault_root / output_rel
        if not out_path.is_file():
            continue  # never rendered yet — not a drift (other checks cover absence)
        on_disk = out_path.read_text(encoding="utf-8")
        rerender = render_auto_index(
            repo, vault_id, auto_index, generated_at="lint",
            preserve_custom=extract_custom_sections(on_disk),
        )
        if auto_index_body_sha(on_disk) != auto_index_body_sha(rerender):
            out.append(LintIssue(
                category="auto-generated-drift", severity="warning",
                vault_id=vault_id,
                details={
                    "path": output_rel,
                    "hint": (f"manual edit detected at {output_rel!r}; run "
                             "`wiki-index-render --auto-indexes` to regenerate, or "
                             "move your edit into the per-issue file"),
                },
            ))
    return out


def check_lifecycle_drift(
    repo: "IndexRepository", vault_id: str, vault_root: "Path", *, strict: bool,
    config: "LayoutConfig | None" = None,
) -> list[LintIssue]:
    """TASK 036 / R-15 (Slice A1): flag pages whose AUTHORED `status` contradicts their
    event-graph state (e.g. a decision carrying a `superseded-by` edge but still
    `status: accepted`). Rules are layout-config-driven (`drift_rules`; the `cybos`
    layout ships them), so a layout without them (Karpathy/dev-project/obsidian-personal)
    is a no-op — and no DAL call is made. Severity rides the existing lint policy
    (warning → error under `--strict`): drift surfaces in the report by default and gates
    ONLY `wiki-lint --strict` (D-036 — drift is a genuine contradiction, so it is the one
    SEMANTIC check that belongs on lint's `--strict` rail; coverage GAPS, which are
    expected, live in the always-exit-0 `wiki-health` CLI instead).

    CAVEAT (vdd-multi): drift reads the auto-derived INVERSE edges, which a
    `wiki-reindex --delta` can leave transiently stale on one side of a bidirectionally-
    authored edge until the next `--full` — so `--strict` drift gating assumes a recent
    `--full`. `config` is reused from `run_all_checks` when provided (else resolved here)."""
    if config is None:
        from scripts.wiki_index.layout_config import resolve_layout_config
        config = resolve_layout_config(vault_root)
    if not config.drift_rules:
        return []
    sev: Severity = "error" if strict else "warning"
    out: list[LintIssue] = []
    for hit in repo.find_lifecycle_drift(vault_id, list(config.drift_rules)):
        out.append(LintIssue(
            category="lifecycle-drift", severity=sev, vault_id=vault_id,
            page_slug=hit.page_slug,
            details={"project": hit.page_project, "class": hit.page_class,
                     "edge": hit.edge, "status": hit.status,
                     "expected": hit.expected},
        ))
    return out


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
