"""Config-driven knowledge-health analyses of the SQLite DAL (TASK 056).

Methods relocated verbatim from the pre-056 monolith: find_lifecycle_drift,
find_coverage_gaps (R-15 / TASK 036, ADR-006), find_ontology_violations
(R-19 / TASK 054). All three read declared LayoutConfig rule objects
(DriftRule / CoverageRule / OntologyConfig) — new R-15-family rules belong
here; rule-free structural scans belong in `_health_scan`.

**TASK 061 (R-061-1) — honest denominators.** The three finders above are now
THIN WRAPPERS over `find_*_report()` (ONE code path — `tests/
test_health_denominators.py` TC-00-2/TC-01-5 pin `wrapper.<findings> ==
report.<findings>`, so the two can never drift apart). `find_coverage_gaps_report`
/ `find_ontology_violations_report` additionally compute a POSITIVELY-DEFINED
population denominator (how many pages/refs the check's rules actually bind
to) alongside the findings, so `{"total_gaps": 0}` can no longer be mistaken
for "0 typed pages were ever examined" (the LIVE-vault bug this task fixes).
`find_lifecycle_drift_report`'s OWN `pages_examined` is **R-061-2** (bead 061-03,
`wiki-lint`'s ontology+drift denominators) — it stays a stub `0` here.

dialect: SQLite-leaning — heavy `json_extract`/`json_type` over
`frontmatter_json` (Postgres: `jsonb` `->`/`->>`/`jsonb_typeof`); the
NOT-EXISTS / LEFT-JOIN shapes themselves are portable.
"""

from __future__ import annotations

from typing import Any

from scripts.wiki_index.models import (
    CoverageGap,
    CoverageReport,
    CoverageRule,
    DriftHit,
    DriftRule,
    LifecycleDriftReport,
    OntologyConfig,
    OntologyReport,
    OntologyViolation,
    RuleStat,
)
from scripts.wiki_index.repository import validate_filter_field
from scripts.wiki_index.sqlite_repository._base import SQLiteRepositoryBase


class _HealthRulesMixin(SQLiteRepositoryBase):
    """Declared-rules analyses: lifecycle drift, coverage gaps, ontology."""

    # =========================================================================
    # TASK 061 (R-061-1) — shared population-count helpers. P-061-C: every
    # denominator is a COUNT over an `IN (...)` set that MAY be empty (a layout
    # with no rules, or an ontology with no edges/properties declared). NEVER
    # compose a degenerate `IN ()` — return 0 before touching SQL (mirrors the
    # pre-existing hand-built-rule precedent in this module: skip, never crash,
    # never inject).
    # =========================================================================

    def _count_pages_of_classes(self, vault_id: str, classes: set[str]) -> int:
        """COUNT(*) of `pages` whose AUTHORED `$.type` is in `classes`. Returns
        `0` — no query executed — when `classes` is empty."""
        if not classes:
            return 0
        conn = self._connect()
        clause, vals = self._in_clause(
            "json_extract(p.frontmatter_json, '$.type')", sorted(classes))
        row = conn.execute(
            f"SELECT COUNT(*) FROM pages p WHERE p.vault_id = ? AND {clause}",
            [vault_id, *vals]).fetchone()
        return int(row[0])

    def _count_refs_of_types(self, vault_id: str, ref_types: set[str]) -> int:
        """COUNT(*) of `page_entity_refs` rows whose `ref_type` is in
        `ref_types`. Returns `0` — no query executed — when `ref_types` is
        empty."""
        if not ref_types:
            return 0
        conn = self._connect()
        clause, vals = self._in_clause("ref_type", sorted(ref_types))
        row = conn.execute(
            f"SELECT COUNT(*) FROM page_entity_refs WHERE vault_id = ? AND {clause}",
            [vault_id, *vals]).fetchone()
        return int(row[0])

    def _count_pages_with_scalar(self, vault_id: str, page_class: str, field: str) -> int:
        """COUNT(*) of `pages` of `page_class` whose `$.<field>` is a PRESENT
        scalar (`json_type(...) = 'text'`) — a value an ontology property rule
        can actually judge; an ABSENT value is a coverage concern, not a
        contradiction (mirrors the property-violation finder's own filter, and
        the R-15 drift scalar-only rule). `field` is `validate_filter_field`-
        checked THEN bound as a `$.<field>` path (never string-composed).
        `page_class` is always a single bound scalar (never an IN-list), so no
        degenerate-SQL guard applies here (P-061-C is an `IN (...)` concern)."""
        field = validate_filter_field(field)
        json_path = f"$.{field}"
        conn = self._connect()
        row = conn.execute(
            "SELECT COUNT(*) FROM pages p WHERE p.vault_id = ? "
            "AND json_extract(p.frontmatter_json, '$.type') = ? "
            "AND json_type(p.frontmatter_json, ?) = 'text'",
            [vault_id, page_class, json_path]).fetchone()
        return int(row[0])

    # =========================================================================
    # Legacy list-returning methods — public API (lint.py, wiki_health.py, 4
    # test modules). Each is a THIN WRAPPER over its `*_report()` sibling below
    # (TASK 061 collapse — one code path, TC-00-2/TC-01-5 pin the equivalence).
    # =========================================================================

    def find_lifecycle_drift(
        self, vault_id: str, rules: list[DriftRule]
    ) -> list[DriftHit]:
        """TASK 036 / R-15 (Slice A1) — pages whose AUTHORED ``status``
        frontmatter contradicts their event-graph state. See
        `find_lifecycle_drift_report` (TASK 061) for the implementation — this
        is a thin wrapper over its `.hits`."""
        return self.find_lifecycle_drift_report(vault_id, rules).hits

    def find_coverage_gaps(
        self, vault_id: str, rules: list[CoverageRule]
    ) -> list[CoverageGap]:
        """TASK 036 / R-15 (Slice A2) — pages MISSING an expected relation. See
        `find_coverage_gaps_report` (TASK 061) for the implementation — this is
        a thin wrapper over its `.gaps`."""
        return self.find_coverage_gaps_report(vault_id, rules).gaps

    def find_ontology_violations(
        self, vault_id: str, ontology: OntologyConfig
    ) -> list[OntologyViolation]:
        """TASK 054 / R-19 — pages that CONTRADICT the declared ontology
        contract. See `find_ontology_violations_report` (TASK 061) for the
        implementation — this is a thin wrapper over its `.violations`."""
        return self.find_ontology_violations_report(vault_id, ontology).violations

    # =========================================================================
    # Report methods — TASK 061 (R-061-1): findings + a positively-defined
    # denominator. The legacy methods above delegate here; a concrete backend
    # implements THESE, never the reverse.
    # =========================================================================

    def find_lifecycle_drift_report(
        self, vault_id: str, rules: list[DriftRule]
    ) -> LifecycleDriftReport:
        # TASK 036 / R-15 (Slice A1) — a page whose AUTHORED `$.status` contradicts its
        # event-graph state. Keyed on frontmatter `$.type` (the RAW class, NOT pages.type
        # which is the db-bucket) + an EXISTS over page_entity_refs where page_slug IS this
        # page (the auto-derived INVERSE edge, e.g. superseded-by — unambiguous on the page
        # side, so no cross-project COUNT guard is needed: the inverse was only derived when
        # the forward target resolved uniquely). page_class/edge/status values are BOUND
        # params; the `$.type`/`$.status` JSON paths are FIXED literals (no user field name).
        # Read-only; zero DDL.
        #
        # NOTE (vdd-multi): the inverse-edge reliance means drift can UNDER-report right
        # after a `wiki-reindex --delta` that re-walked only ONE side of a bidirectionally-
        # authored edge — the inverse on the un-walked page is restored on the next `--full`
        # (see reindex.py). So `wiki-lint --strict` drift gating assumes a recent `--full`.
        # COST: one scan of `pages` PER rule (O(N·rules); `$.type` is unindexed by design,
        # P-5) — fine for the small typed vaults; revisit a single CASE/CTE pass only if a
        # typed partition grows large.
        #
        # TASK 061 (R-061-2 / bead 061-03): `pages_examined` (= pages whose $.type is in
        # UNION of drift_rules[].class) is `wiki-lint`'s OWN denominator, computed there —
        # NOT this bead's scope (R-061-1 is coverage + ontology only). Stays `0` here.
        conn = self._connect()
        out: list[DriftHit] = []
        for rule in rules:
            sql = (
                "SELECT p.slug, p.project, "
                "CAST(json_extract(p.frontmatter_json, '$.status') AS TEXT) AS status "
                "FROM pages p "
                "WHERE p.vault_id = ? "
                "AND json_extract(p.frontmatter_json, '$.type') = ? "
                "AND EXISTS (SELECT 1 FROM page_entity_refs r "
                "            WHERE r.vault_id = p.vault_id "
                "              AND r.page_slug = p.slug "
                "              AND r.page_project = p.project "
                "              AND r.ref_type = ?) "
            )
            params: list[Any] = [vault_id, rule.page_class, rule.edge]
            # Only a SCALAR text status is a clean contradiction. `json_type(...) = 'text'`
            # excludes BOTH an absent status (path missing → NULL → not 'text') AND a
            # NON-scalar status (a YAML list `status: [superseded]` json_extract's to the
            # text `["superseded"]`, which would otherwise phantom-match `<> expected`;
            # vdd-multi critic-logic MED). So NULL/list/object statuses are never drift.
            sql += "AND json_type(p.frontmatter_json, '$.status') = 'text' "
            if rule.expect_status is not None:
                # Drift = scalar status present and != expected.
                sql += "AND CAST(json_extract(p.frontmatter_json, '$.status') AS TEXT) <> ? "
                params.append(rule.expect_status)
                expected = f"status == {rule.expect_status}"
            elif rule.forbid_status:
                # Drift = scalar status IN the forbidden set.
                placeholders = ",".join("?" * len(rule.forbid_status))
                sql += (f"AND CAST(json_extract(p.frontmatter_json, '$.status') AS TEXT) "
                        f"IN ({placeholders}) ")
                params.extend(rule.forbid_status)
                expected = "status not in {" + ", ".join(rule.forbid_status) + "}"
            else:
                # Defensive (critic-security LOW-1, parity with find_coverage_gaps): a
                # hand-built rule (bypassing the config-load gate) with NEITHER branch would
                # otherwise build a degenerate `IN ()`. Skip it — never crash, never inject.
                continue
            sql += "ORDER BY p.project, p.slug"
            for r in conn.execute(sql, params).fetchall():
                out.append(DriftHit(
                    vault_id=vault_id, page_slug=r["slug"], page_project=r["project"],
                    page_class=rule.page_class, edge=rule.edge,
                    status=r["status"], expected=expected,
                ))
        return LifecycleDriftReport(hits=out, pages_examined=0, rule_stats=[])

    def find_coverage_gaps_report(
        self, vault_id: str, rules: list[CoverageRule]
    ) -> CoverageReport:
        # TASK 036 / R-15 (Slice A2) — a page MISSING an expected relation. Keyed on
        # frontmatter `$.type`. `requires_edge` → NOT EXISTS a page_entity_refs row
        # (page_slug IS this page) of that ref_type. `requires_field` → the frontmatter
        # scalar `$.<field>` is absent OR empty (''). Field names are re-validated
        # (library-caller defense; the config-load gate already validated built-ins) and
        # the JSON path is bound as a param. Read-only; zero DDL.
        #
        # TASK 061 (R-061-1): `pages_examined` = pages whose AUTHORED $.type is in the
        # UNION of every rule's class (P-061-C: 0 rules ⇒ 0, no SQL). Per-rule `matched`
        # = pages of THAT rule's class ALONE — the rule's PRECONDITION (the NOT EXISTS /
        # empty-field predicate below is the GAP condition, not the precondition). One
        # extra COUNT scan per rule ($.type unindexed by design, P-5) — fine for the
        # small typed partitions this ships against.
        classes = {r.page_class for r in rules}
        pages_examined = self._count_pages_of_classes(vault_id, classes)
        conn = self._connect()
        out: list[CoverageGap] = []
        rule_stats: list[RuleStat] = []
        for rule in rules:
            matched = self._count_pages_of_classes(vault_id, {rule.page_class})
            params: list[Any] = [vault_id, rule.page_class]
            if rule.requires_edge is not None:
                sql = (
                    "SELECT p.slug, p.project FROM pages p "
                    "WHERE p.vault_id = ? "
                    "AND json_extract(p.frontmatter_json, '$.type') = ? "
                    "AND NOT EXISTS (SELECT 1 FROM page_entity_refs r "
                    "                WHERE r.vault_id = p.vault_id "
                    "                  AND r.page_slug = p.slug "
                    "                  AND r.page_project = p.project "
                    "                  AND r.ref_type = ?) "
                    "ORDER BY p.project, p.slug"
                )
                params.append(rule.requires_edge)
                kind, detail = "edge", rule.requires_edge
            else:
                field = validate_filter_field(rule.requires_field or "")
                json_path = f"$.{field}"
                # Gap = the scalar is absent (NULL), an empty string, or an EMPTY container
                # (`source: []` / `{}` — "no value", json_extract's to the text '[]'/'{}';
                # vdd-multi critic-logic MED). A non-empty scalar OR a non-empty list/object
                # counts as covered. The IN-list is a fixed literal (no params).
                sql = (
                    "SELECT p.slug, p.project FROM pages p "
                    "WHERE p.vault_id = ? "
                    "AND json_extract(p.frontmatter_json, '$.type') = ? "
                    "AND (json_extract(p.frontmatter_json, ?) IS NULL "
                    "     OR CAST(json_extract(p.frontmatter_json, ?) AS TEXT) IN ('', '[]', '{}')) "
                    "ORDER BY p.project, p.slug"
                )
                params.extend([json_path, json_path])
                kind, detail = "field", field
            # TASK 061: count off the SAME fetchall() that builds the CoverageGap
            # objects below — never a second scan of the result (bead-01 spec).
            rows = conn.execute(sql, params).fetchall()
            for r in rows:
                out.append(CoverageGap(
                    vault_id=vault_id, page_slug=r["slug"], page_project=r["project"],
                    page_class=rule.page_class, kind=kind, detail=detail,
                ))
            rule_stats.append(RuleStat(
                page_class=rule.page_class, kind=kind, ref=detail,
                matched=matched, findings={"gaps": len(rows)},
            ))
        return CoverageReport(gaps=out, pages_examined=pages_examined, rule_stats=rule_stats)

    def find_ontology_violations_report(
        self, vault_id: str, ontology: OntologyConfig
    ) -> OntologyReport:
        # TASK 054 / R-19 — pages that CONTRADICT the declared ontology contract. Two
        # read-side families (edge domain/range + property enum). All values are BOUND
        # params; the only string-composed parts are placeholder COUNTS (never values), the
        # FIXED `$.type` JSON-path literal, and a `$.<field>` path that is
        # `validate_filter_field`-checked THEN bound. Keyed on frontmatter `$.type` (the
        # AUTHORED raw class, NOT pages.type the db-bucket) — the R-15 drift/coverage
        # precedent. Read-only; zero DDL; NOT a write gate.
        #
        # `closed_types` is NOT re-checked here: reindex resolves a typed page's class FROM
        # its frontmatter `$.type` and SKIPS any page whose `$.type` ∉ type_mapping (reported
        # in `wiki-reindex --full`'s `skipped[]`), so an out-of-roster type can never be
        # indexed — a read-side sweep would be a guaranteed no-op. The closed-world stance is
        # thus enforced at INDEX time (a type is a hard classification failure) while edge/
        # property contradictions are soft (the page still indexes) → advisory here. Q-054.
        #
        # COVERAGE SCOPE (Q-054, vdd-multi critic-logic MAJOR): the checks key on frontmatter
        # `$.type` — the R-15 drift/coverage precedent. A note filed under a typed folder with
        # NO authored `type:` (a quick-capture; cybos routes its db-class from the path glob but
        # never injects `$.type`) has a NULL `$.type` and so escapes these checks. The
        # page-type TEMPLATES all author `type:`, so template-created notes ARE checked; the
        # gap is untyped quick-captures. Fixing it uniformly (key off the derived class tag, or
        # inject the glob-resolved `$.type` at reindex) belongs to a machinery-wide change
        # across R-15+R-19, deferred (not silently narrowed).
        #
        # DELTA CAVEAT (mirrors find_lifecycle_drift): the forward edge a page carries can be an
        # AUTO-DERIVED inverse; a `wiki-reindex --delta` that re-walks only one side of a
        # bidirectionally-authored edge can leave it transiently missing until the next
        # `--full`, so `wiki-lint --strict` ontology gating assumes a recent `--full`.
        #
        # TASK 061 (R-061-1, C6): this SINGLE call spans TWO disjoint populations — edges
        # (domain/range, section a) and pages (property, section b) — so it needs TWO
        # denominators, each bound to `OntologyViolation.kind`. `edges_examined` counts refs
        # whose ref_type is in the DECLARED edge vocabulary (⋃ ontology.edges[].edge — NOT
        # every ref_type; an undeclared edge like `verifies` is UNDECLARABLE, not merely
        # absent from the sum — `_validate_ontology` rejects it at load). `property_pages_
        # examined` counts pages whose $.type is in ⋃ ontology.properties[].class — a
        # DIFFERENT population, hence a DIFFERENT noun (`CoverageReport.pages_examined`
        # already owns "pages_examined" for coverage's population, RTM constraint 4).
        conn = self._connect()
        out: list[OntologyViolation] = []
        # A `domain` violation is about the PAGE's class carrying an edge type — the specific
        # target is irrelevant — so a page with N same-type edges (`implements: [[A]], [[B]]`)
        # is ONE domain finding, not N (critic-logic 1d: else `total_violations`/`by_kind`
        # inflate by target cardinality). Range/property stay per-instance (each a distinct fact).
        domain_seen: set[tuple[str, str, str]] = set()
        rule_stats: list[RuleStat] = []

        # (a) edge domain/range — per (forward) ref_type. A **LEFT JOIN** to the resolved
        # target (guarded by the COUNT=1 same-slug check IN THE ON-CLAUSE, verbatim from
        # find_classification_leaks) collapses the target to exactly one row OR all-NULL when
        # the slug is an orphan / entity / cross-project-ambiguous. Consequence (critic-logic
        # MAJOR fix): the **domain** check fires off the src join alone — INDEPENDENT of whether
        # the target resolves (a `risk` that `implements` a dangling `[[ghost]]` is still a
        # domain error) — while the **range** check fires only when the target resolves
        # uniquely (tgt_type non-NULL), so it never phantom-hits an ambiguous slug.
        #
        # `edges_examined` — TASK 061: the declared edge vocabulary is ⋃ ontology.edges[].edge;
        # `_validate_ontology` rejects a duplicate `edge:` name at load, so this set has exactly
        # one member per rule below (no double-count risk).
        edge_types = {e.edge for e in ontology.edges}
        edges_examined = self._count_refs_of_types(vault_id, edge_types)
        for edge in ontology.edges:
            frm = set(edge.frm)
            to = set(edge.to)
            sql = (
                "SELECT r.page_slug, r.page_project, "
                "CAST(json_extract(src.frontmatter_json, '$.type') AS TEXT) AS src_type, "
                "t.slug AS tgt_slug, "
                "CAST(json_extract(t.frontmatter_json, '$.type') AS TEXT) AS tgt_type "
                "FROM page_entity_refs r "
                "JOIN pages src ON src.vault_id = r.vault_id "
                "               AND src.slug = r.page_slug "
                "               AND src.project = r.page_project "
                "LEFT JOIN pages t ON t.vault_id = r.vault_id AND t.slug = r.entity_slug "
                "     AND (SELECT COUNT(*) FROM pages tc WHERE tc.vault_id = r.vault_id "
                "          AND tc.slug = r.entity_slug) = 1 "
                "WHERE r.vault_id = ? AND r.ref_type = ? "
                "ORDER BY r.page_project, r.page_slug, r.entity_slug"
            )
            # TASK 061: `matched_e` = the rows THIS rule's own query already fetched — free,
            # no extra query (bead-01 spec).
            rows = conn.execute(sql, (vault_id, edge.edge)).fetchall()
            domain_count = 0
            range_count = 0
            for row in rows:
                src_type = row["src_type"]
                tgt_type = row["tgt_type"]
                # Only an EXPLICIT (present, scalar) class is a contradiction — a page with
                # no authored `$.type` has an unknown class, never a domain/range violation.
                if src_type is not None and src_type not in frm:
                    key = (row["page_slug"], row["page_project"], edge.edge)
                    if key not in domain_seen:
                        domain_seen.add(key)
                        domain_count += 1
                        out.append(OntologyViolation(
                            vault_id=vault_id, page_slug=row["page_slug"],
                            page_project=row["page_project"], page_class=src_type,
                            kind="domain", ref=edge.edge,
                            detail=f"source class {src_type!r} not in from {sorted(frm)}",
                            target_slug=None,  # domain is about the source class, not any target
                        ))
                if tgt_type is not None and tgt_type not in to:
                    range_count += 1
                    out.append(OntologyViolation(
                        vault_id=vault_id, page_slug=row["page_slug"],
                        page_project=row["page_project"],
                        # the offending page's class; fall back to the target class when the
                        # source is an untyped quick-capture (never an empty string — critic NIT).
                        page_class=(src_type if src_type is not None else tgt_type),
                        kind="range", ref=edge.edge,
                        detail=f"target class {tgt_type!r} not in to {sorted(to)}",
                        target_slug=row["tgt_slug"],
                    ))
            # TASK 061 (P-061-A): `findings` is a DICT — domain_e ≤ matched_e AND
            # range_e ≤ matched_e hold independently; summing them into one int would make
            # `violations_e ≤ matched_e` false (one examined row can be BOTH a domain AND
            # a range violation).
            rule_stats.append(RuleStat(
                page_class="", kind="edge", ref=edge.edge, matched=len(rows),
                findings={"domain": domain_count, "range": range_count},
            ))

        # (b) property enum — a PRESENT scalar `$.<field>` not in the enum. `json_type ==
        # 'text'` excludes absent/null/list/object (an absence is a coverage concern, not a
        # contradiction — mirrors the drift scalar-only rule). Field re-validated
        # (library-caller defense) + bound as a `$.<field>` path; enum values bound.
        #
        # `property_pages_examined` — TASK 061: pages whose $.type is in ⋃
        # ontology.properties[].class (P-061-C: 0 properties ⇒ 0, no SQL).
        prop_classes = {p.page_class for p in ontology.properties}
        property_pages_examined = self._count_pages_of_classes(vault_id, prop_classes)
        for prop in ontology.properties:
            if not prop.enum:
                continue  # defensive: a hand-built rule bypassing the load-gate → skip (no `IN ()`)
            field = validate_filter_field(prop.field)
            json_path = f"$.{field}"
            # TASK 061: `matched_p` = pages of this class carrying a PRESENT scalar for the
            # field (the rule's precondition) — a SEPARATE count from the violation query
            # below (which further filters NOT IN enum).
            matched = self._count_pages_with_scalar(vault_id, prop.page_class, field)
            placeholders = ",".join("?" * len(prop.enum))
            sql = (
                "SELECT p.slug, p.project, "
                "CAST(json_extract(p.frontmatter_json, ?) AS TEXT) AS val "
                "FROM pages p "
                "WHERE p.vault_id = ? "
                "AND json_extract(p.frontmatter_json, '$.type') = ? "
                "AND json_type(p.frontmatter_json, ?) = 'text' "
                f"AND CAST(json_extract(p.frontmatter_json, ?) AS TEXT) NOT IN ({placeholders}) "
                "ORDER BY p.project, p.slug"
            )
            params: list[Any] = [json_path, vault_id, prop.page_class, json_path,
                                  json_path, *prop.enum]
            rows = conn.execute(sql, params).fetchall()
            for row in rows:
                # The offending value is UNTRUSTED frontmatter (H-6). `!r` escapes control
                # chars (CWE-117) and every sink re-escapes (json.dumps / dict-repr); a length
                # cap bounds an adversarial value in the operator-facing report (critic NIT,
                # parity with lint._safe_surface's 200-char cap).
                raw_val = row["val"]
                shown = raw_val if len(raw_val) <= 200 else raw_val[:200] + "…"
                out.append(OntologyViolation(
                    vault_id=vault_id, page_slug=row["slug"], page_project=row["project"],
                    page_class=prop.page_class, kind="property", ref=field,
                    detail=f"{field}={shown!r} not in {list(prop.enum)}",
                ))
            rule_stats.append(RuleStat(
                page_class=prop.page_class, kind="property", ref=field,
                matched=matched, findings={"property": len(rows)},
            ))
        return OntologyReport(
            violations=out, edges_examined=edges_examined,
            property_pages_examined=property_pages_examined, rule_stats=rule_stats,
        )
