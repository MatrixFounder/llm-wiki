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


@dataclass(frozen=True)
class LintReport:
    """TASK 061 / R-061-2 — the issues PLUS what **each config-driven check** examined.

    CHECK census — `wiki-lint` runs FOUR `check_*` functions
    (``grep -n "^def check_" scripts/wiki_index/lint.py`` → 4); **two** are config-driven
    with a rule POPULATION, and both gate `--strict` (the CI rail) — so both report a
    denominator. The boundary is STATED, not merely true (a `0` from a check that examined
    nothing is the bug this task exists to kill, and an unenumerated surface is how it
    recurs):

      - ``lifecycle-drift``    ✅ — config-driven (`drift_rules`), rule population, `--strict`
      - ``ontology-violation`` ✅ — config-driven (`ontology:`), rule population, `--strict`
      - ``auto-generated-drift`` ❌ — a render HASH comparison; there is no rule population,
        hence no denominator to state
      - ``classification-*``     ❌ — R-16 policy, gated on a `policy:` block that TASK 061
        §5 deliberately leaves declared-but-OFF

    **SINK census (061 FIX-LOOP, vdd-multi H1) — the census the first cut FORGOT.** We
    enumerated the four CHECKS above and never the OUTPUT SINKS, so the denominators
    reached exactly one of the three (``grep -n "emit(\\|write_text(" scripts/wiki_skills/
    wiki_lint.py`` → 3 sinks). ``wiki-lint --report out.md`` on the LIVE vault therefore
    still wrote a literal ``✅ Healthy. No issues found.`` from a run in which
    `ontology-violation` examined **0 of 8836 refs** — the task's own false green,
    unqualified, in the HUMAN-FACING artifact, while the JSON envelope beside it told the
    truth. All three sinks now take the REPORT:

      - **stdout JSON envelope** (`wiki_lint.emit`)         ✅ ``denominators`` (bead 061-03)
      - **`--report <path.md>`** (`render_markdown_report`)  ✅ a qualified verdict line +
        a "what was examined" table (H1)
      - **`--json-sidecar <path.json>`** (`render_json_sidecar`) ✅ ``denominators`` +
        a derived ``vacuous_checks`` list (H1)

    ``denominators`` is keyed ``{vault_id: {check_category: payload}}`` — **per-CHECK**, so
    the ``pages_examined`` noun (drift's population = ⋃ ``drift_rules[].class``) can never
    collide with the ontology check's edge/property populations inside one envelope.
    Coverage (`wiki-health`) owns the SAME noun for a THIRD population (⋃
    ``coverage_rules[].class``); that is safe only because the two never share an envelope.
    **Any future surface that flattens these payloads MUST re-qualify the noun** —
    collapsing them reruns the two-populations-one-denominator bug on a new surface
    (PLAN 061 P-061-D).

    A check whose no-op fires (no `drift_rules` / no `ontology:` block ⇒ **no DAL call**)
    contributes NO payload, and a vault with neither contributes no key at all — an absent
    key means "this check does not apply to this layout", which is different from
    "examined 0".
    """

    issues: list[LintIssue]
    denominators: dict[str, dict[str, Any]]


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

    Back-compat wrapper over `run_all_checks_report` (TASK 061) — signature and return
    type UNCHANGED for the pre-061 callers (`scripts/benchmark.py:217`, the lint test
    modules). New callers that want the denominators call the report form."""
    return run_all_checks_report(
        repo, vaults=vaults, strict=strict, mtime_skip=mtime_skip).issues


def run_all_checks_report(
    repo: "IndexRepository", *, vaults: list[str] | None = None,
    strict: bool = False, mtime_skip: bool = False,
) -> LintReport:
    """Run SQL-level lint checks across the given vaults (or all if None), returning the
    issues AND what each config-driven check examined (TASK 061 / R-061-2 — see
    `LintReport`).
    `mtime_skip` (the `wiki-lint --mtime-skip` opt-in, TASK 017 / P-3) is forwarded
    to `check_drift` — skips the re-hash for mtime-unchanged files (integrity-relaxed;
    default off → always full-hash)."""
    issues: list[LintIssue] = []
    denominators: dict[str, dict[str, Any]] = {}
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
        # TASK 061 (R-061-2): BOTH config-driven semantic checks report what they examined
        # — they are the two that gate `--strict` (the CI rail), and giving a denominator
        # to only one would leave the other printing `0` with no way to tell an inert check
        # from a healthy vault. Payload is per-CHECK-keyed (see `LintReport`).
        per_vault: dict[str, Any] = {}
        drift_issues, drift_denom = check_lifecycle_drift_report(
            repo, vid, v.root_path, strict=strict, config=config)
        issues.extend(drift_issues)
        if drift_denom is not None:
            per_vault["lifecycle-drift"] = drift_denom
        # TASK 054 (R-19): ontology-violation — config-driven (`ontology:` block; cybos ships
        # one, others none ⇒ no-op). A contradiction ⇒ advisory, gates `--strict` (ADR-006).
        ont_issues, ont_denom = check_ontology_violations_report(
            repo, vid, v.root_path, strict=strict, config=config)
        issues.extend(ont_issues)
        if ont_denom is not None:
            per_vault["ontology-violation"] = ont_denom
        if per_vault:
            # No key at all when NEITHER check applies to this layout — "does not apply"
            # is not "examined 0", and conflating them would be this task's own bug.
            denominators[vid] = per_vault
        # TASK 049 (R-6): classification-leak + invalid-classification — gated
        # on the vault actually declaring a `policy:` block (no block ⇒ no DAL
        # call, no output — the R-15 no-op precedent). NO denominator: policy is
        # declared-but-OFF by decision (TASK 061 §5), so it has no live rule population
        # here (`LintReport` states this boundary).
        issues.extend(
            check_classification_policy(repo, vid, v.root_path, strict=strict))

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
    return LintReport(issues=issues, denominators=denominators)


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
    event-graph state. Back-compat wrapper (signature UNCHANGED) over
    `check_lifecycle_drift_report` — see there for the full contract."""
    return check_lifecycle_drift_report(
        repo, vault_id, vault_root, strict=strict, config=config)[0]


def check_lifecycle_drift_report(
    repo: "IndexRepository", vault_id: str, vault_root: "Path", *, strict: bool,
    config: "LayoutConfig | None" = None,
) -> tuple[list[LintIssue], dict[str, Any] | None]:
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
    `--full`. `config` is reused from `run_all_checks` when provided (else resolved here).

    TASK 061 / R-061-2 — returns `(issues, denominators)`. `denominators` is `None` (NOT
    an empty dict) when the layout ships **no** `drift_rules`: the pre-061 no-op is
    preserved VERBATIM — no DAL call, and the caller emits no payload, because "this check
    does not apply to this layout" is a different statement from "examined 0 pages". All
    counting happens in the DAL (`find_lifecycle_drift_report`); this function adds none."""
    if config is None:
        from scripts.wiki_index.layout_config import resolve_layout_config
        config = resolve_layout_config(vault_root)
    if not config.drift_rules:
        return [], None
    sev: Severity = "error" if strict else "warning"
    out: list[LintIssue] = []
    report = repo.find_lifecycle_drift_report(vault_id, list(config.drift_rules))
    for hit in report.hits:
        out.append(LintIssue(
            category="lifecycle-drift", severity=sev, vault_id=vault_id,
            page_slug=hit.page_slug,
            details={"project": hit.page_project, "class": hit.page_class,
                     "edge": hit.edge, "status": hit.status,
                     "expected": hit.expected},
        ))
    # `pages_examined` = pages whose $.type ∈ ⋃ drift_rules[].class; per-rule `matched` =
    # the rule's PRECONDITION ($.type = class AND the page CARRIES the edge). Both, because
    # `matched: 0` alone cannot distinguish "no decision pages at all" from "50 decisions,
    # none carrying a superseded-by edge" (R-061-2's E2 correction).
    return out, {"pages_examined": report.pages_examined,
                 "by_rule": [s.to_json() for s in report.rule_stats]}


def check_ontology_violations(
    repo: "IndexRepository", vault_id: str, vault_root: "Path", *, strict: bool,
    config: "LayoutConfig | None" = None,
) -> list[LintIssue]:
    """TASK 054 / R-19 — flag pages that CONTRADICT the declared ontology contract.
    Back-compat wrapper (signature UNCHANGED) over `check_ontology_violations_report` —
    see there for the full contract."""
    return check_ontology_violations_report(
        repo, vault_id, vault_root, strict=strict, config=config)[0]


def check_ontology_violations_report(
    repo: "IndexRepository", vault_id: str, vault_root: "Path", *, strict: bool,
    config: "LayoutConfig | None" = None,
) -> tuple[list[LintIssue], dict[str, Any] | None]:
    """TASK 054 / R-19 — flag pages that CONTRADICT the declared ontology contract: an edge
    whose source/target class is out of the declared `from`/`to` (domain/range), or a
    `status`-style property value out of its enum. Config-driven (`ontology:` block; the
    `cybos` layout ships one, other layouts none → no-op, no DAL call). An ontology violation
    is a genuine CONTRADICTION (like lifecycle-drift), so it rides `wiki-lint` and gates ONLY
    `--strict` (ADR-006 D-036-2, the same rail); the sibling `wiki-health ontology` is the
    always-exit-0 report view. (`closed_types` is enforced at index time — an out-of-roster
    `$.type` is a reindex SKIP — so it produces no read-side finding here; see Q-054.)
    `config` is reused from `run_all_checks` when provided (else resolved here).

    TASK 061 / R-061-2 — returns `(issues, denominators)` with the TWO denominators this
    ONE check needs, because it spans TWO disjoint populations: `edges_examined` (refs whose
    ref_type is in the declared edge vocabulary — a `mentioned` wikilink is NOT one; on the
    LIVE vault this reads 0 despite 8836 refs) and `property_pages_examined` (pages whose
    $.type ∈ ⋃ properties[].class). `None` when the layout declares no `ontology:` block —
    the pre-061 no-op preserved VERBATIM (no DAL call). All counting happens in the DAL
    (`find_ontology_violations_report`); this function adds none."""
    if config is None:
        from scripts.wiki_index.layout_config import resolve_layout_config
        config = resolve_layout_config(vault_root)
    if config.ontology is None:
        return [], None
    sev: Severity = "error" if strict else "warning"
    out: list[LintIssue] = []
    report = repo.find_ontology_violations_report(vault_id, config.ontology)
    for v in report.violations:
        out.append(LintIssue(
            category="ontology-violation", severity=sev, vault_id=vault_id,
            page_slug=v.page_slug,
            details={"project": v.page_project, "class": v.page_class,
                     "kind": v.kind, "ref": v.ref, "detail": v.detail,
                     "target": v.target_slug},
        ))
    return out, {"edges_examined": report.edges_examined,
                 "property_pages_examined": report.property_pages_examined,
                 "by_rule": [s.to_json() for s in report.rule_stats]}


def check_classification_policy(
    repo: "IndexRepository", vault_id: str, vault_root: "Path", *, strict: bool,
) -> list[LintIssue]:
    """TASK 049 (R-6): two categories over the vault's declared `policy:` block.

    - ``classification-leak`` — a page's ``cited``/``verifies`` ref targets a
      page of a HIGHER level (a filed answer/verdict republishing restricted
      content). A genuine contradiction ⇒ warning, **error under --strict**
      (ADR-006 D-036-2 rail, like lifecycle-drift).
    - ``invalid-classification`` — an authored value outside the declared
      ladder (or non-string): the page fails closed out of every scoped
      retrieval. An authoring slip, not a graph contradiction ⇒ warning, never
      strict-gated. The offending VALUE is never echoed (CWE-209/NFR-4).
    - ``invalid-policy`` — the block itself is malformed (warning; the scoped
      CLIs fail loud on it with INVALID_POLICY, lint just surfaces it).

    A vault with NO ``policy:`` block (or no readable ``WIKI_SCHEMA.md``) is a
    silent no-op — no DAL call (the R-15 empty-rules precedent)."""
    from scripts.wiki_index.policy import PolicyError, load_vault_policy

    try:
        block = load_vault_policy(vault_root)
    except PolicyError:
        return [LintIssue(
            category="invalid-policy", severity="warning", vault_id=vault_id,
            details={"hint": "the vault's policy: block is malformed; scoped "
                             "CLIs will refuse it (INVALID_POLICY)"},
        )]
    if block is None:
        return []
    levels, default_level, _audience = block
    out: list[LintIssue] = []
    sev: Severity = "error" if strict else "warning"
    for leak in repo.find_classification_leaks(
            vault_id, list(levels), default_level):
        out.append(LintIssue(
            category="classification-leak", severity=sev, vault_id=vault_id,
            page_slug=leak.page_slug,
            details={"project": leak.page_project,
                     "page_level": leak.page_level,
                     "target": leak.target_slug,
                     "target_level": leak.target_level,
                     "ref_type": leak.ref_type,
                     "hint": "a lower-classified page cites/verifies a "
                             "higher-classified one — the filed artifact "
                             "republishes restricted content"},
        ))
    for bad in repo.find_invalid_classifications(vault_id, list(levels)):
        out.append(LintIssue(
            category="invalid-classification", severity="warning",
            vault_id=vault_id, page_slug=bad.page_slug,
            details={"project": bad.page_project,
                     "hint": "authored classification is not one of the "
                             "vault's policy.levels (value withheld); the "
                             "page fails closed out of scoped retrieval"},
        ))
    return out


def _split(report: "LintReport | list[LintIssue]") -> tuple[
        list[LintIssue], dict[str, dict[str, Any]] | None]:
    """Normalize either renderer input. A bare ``list[LintIssue]`` (the pre-061
    back-compat form) yields ``None`` — *denominators UNKNOWN* — which is deliberately
    NOT the same as a `LintReport` carrying ``{}`` (*no config-driven check applies to
    any of these vaults*: an honest green). Collapsing the two would re-run this task's
    own bug one level up, in the very function written to fix it."""
    if isinstance(report, LintReport):
        return report.issues, report.denominators
    return report, None


def _denominator_rows(
    denominators: dict[str, dict[str, Any]],
) -> list[tuple[str, str, str, int]]:
    """``[(vault_id, check, population, examined)]`` — one row per (check, DENOMINATOR).

    DERIVED, never enumerated: a check payload is ``{<population noun>: int, …,
    "by_rule": [...]}``, so every INT-valued key IS a population count (``by_rule`` is a
    list and drops out). A future denominator noun (TASK 062 adds rules; a new population
    may follow) therefore renders in both sinks with **zero renderer code** — the
    schema-driven discipline TASK 058 set for the config UI. Hard-coding the three known
    nouns here (`pages_examined`/`edges_examined`/`property_pages_examined`) would be
    exactly the fractal's next recurrence: a mechanism asserting it covers a surface it
    never enumerated."""
    rows: list[tuple[str, str, str, int]] = []
    for vault_id in sorted(denominators):
        for check in sorted(denominators[vault_id]):
            payload = denominators[vault_id][check]
            for key in sorted(payload):
                val = payload[key]
                if isinstance(val, int) and not isinstance(val, bool):
                    rows.append((vault_id, check, key, val))
    return rows


def render_markdown_report(report: "LintReport | list[LintIssue]") -> str:
    """Render a lint run as a markdown report (the `--report <path.md>` sink).

    TASK 061 FIX-LOOP (H1) — the unconditional ``✅ Healthy. No issues found.`` was THE
    false green this task exists to kill, left alive in the one artifact a human actually
    reads: on the LIVE vault it was written by a run whose `ontology-violation` check
    examined **0 of 8836 refs**. A green is now printed ONLY when every config-driven
    check that ran examined a NON-EMPTY population; otherwise the report says, in the same
    breath, which population was empty. A "what was examined" table follows the issues.

    Accepts a bare ``list[LintIssue]`` (pre-061 signature, byte-identical output) — but a
    list carries NO denominators, so that form CANNOT qualify its green and prints the
    pre-061 body verbatim. The CLI always passes the `LintReport`."""
    issues, denominators = _split(report)
    rows = _denominator_rows(denominators) if denominators else []
    vacuous = [r for r in rows if r[3] == 0]
    lines = ["# Wiki Lint Report", ""]
    if vacuous:
        lines.append(
            f"⚠️ **NOT a clean bill of health** — {len(vacuous)} of {len(rows)} "
            f"config-driven check population(s) examined **nothing**:")
        lines.append("")
        for vault_id, check, population, _n in vacuous:
            lines.append(
                f"- ⚠ `{check}` examined **0** (`{population}`) in vault `{vault_id}` — "
                f"a `0` finding count for this check carries NO information.")
        lines.append("")
    if not issues:
        lines.append("No issues found — but see the warning above: a check that examined "
                     "nothing cannot certify health."
                     if vacuous else "✅ Healthy. No issues found.")
        lines.append("")
    else:
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
    if rows:
        # The denominator table — the positive half of the same honesty: what a check
        # DID examine is as load-bearing as what it found. Absent entirely when no
        # config-driven check applies to any vault (karpathy et al: nothing to state).
        lines.append("## What was examined")
        lines.append("")
        lines.append("| vault | check | population | examined |")
        lines.append("|---|---|---|---|")
        for vault_id, check, population, n in rows:
            flag = " ⚠" if n == 0 else ""
            lines.append(f"| {vault_id} | {check} | `{population}` | {n}{flag} |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_json_sidecar(report: "LintReport | list[LintIssue]") -> str:
    """Render a lint run as the `--json-sidecar <path.json>` detail artifact.

    TASK 061 FIX-LOOP (H1) — **SHAPE CHANGE, stated not smuggled.** Given a `LintReport`
    (what the CLI now passes) this emits an OBJECT:

        {"issues": [<the pre-061 array, VERBATIM>],
         "denominators": {<vault>: {<check>: {...}}},     # same payload as stdout
         "vacuous_checks": [{"vault", "check", "population"}]}   # derived; [] = all good

    The pre-061 sidecar was a BARE ARRAY, and a bare array is structurally incapable of
    carrying a denominator — so an empty one was indistinguishable from "the checks
    examined nothing", the same false green as the markdown sink, in a file that travels
    ALONE (a CI artifact, read without the stdout envelope beside it). Emitting the
    vacuity as a synthetic *issue* instead is forbidden by the spec (TASK 061: denominators
    "never gate and never become issues" — it would desync the array's length from the
    envelope's `total_issues`), so the wrapper object is the only honest shape.

    Passing a bare ``list[LintIssue]`` still returns the pre-061 BARE ARRAY byte-for-byte
    (library back-compat; a list has no denominators to render)."""
    import json
    issues, denominators = _split(report)
    payload = [
        {
            "category": i.category,
            "severity": i.severity,
            "vault_id": i.vault_id,
            "page_slug": i.page_slug,
            "details": i.details,
        }
        for i in issues
    ]
    if denominators is None:
        return json.dumps(payload, ensure_ascii=False, indent=2)
    rows = _denominator_rows(denominators)
    return json.dumps({
        "issues": payload,
        "denominators": denominators,
        "vacuous_checks": [
            {"vault": vault_id, "check": check, "population": population}
            for vault_id, check, population, n in rows if n == 0
        ],
    }, ensure_ascii=False, indent=2)
