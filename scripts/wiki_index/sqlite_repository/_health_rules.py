"""Config-driven knowledge-health analyses of the SQLite DAL (TASK 056).

Methods relocated verbatim from the pre-056 monolith: find_lifecycle_drift,
find_coverage_gaps (R-15 / TASK 036, ADR-006), find_ontology_violations
(R-19 / TASK 054). All three read declared LayoutConfig rule objects
(DriftRule / CoverageRule / OntologyConfig) — new R-15-family rules belong
here; rule-free structural scans belong in `_health_scan`.

**TASK 061 (R-061-1) — honest denominators.** The three finders above are now
THIN WRAPPERS over `find_*_report()` (ONE code path — `tests/
test_health_denominators.py` TC-00-2/TC-01-5 pin `wrapper.<findings> ==
report.<findings>`, so the two can never drift apart). Each `*_report` method
additionally computes a POSITIVELY-DEFINED population denominator (how many
pages/refs the check's rules actually bind to) alongside the findings, so
`{"total_gaps": 0}` can no longer be mistaken for "0 typed pages were ever
examined" (the LIVE-vault bug this task fixes). FOUR denominators over FOUR
populations — one per (check, population) pair, never one noun shared across two:

  - `find_coverage_gaps_report`      → `pages_examined`  (⋃ coverage_rules[].class)
  - `find_lifecycle_drift_report`    → `pages_examined`  (⋃ drift_rules[].class) — a
    DIFFERENT population under the same noun; safe ONLY because the two never share
    an envelope (`wiki-health` vs `wiki-lint`) and lint's payload is per-check-keyed
    (P-061-D). R-061-2, bead 061-03.
  - `find_ontology_violations_report` → `edges_examined` (⋃ ontology.edges[].edge) AND
    `property_pages_examined` (⋃ ontology.properties[].class) — ONE call, TWO disjoint
    populations, hence two denominators (C6).

**061 FIX-LOOP (vdd-multi).** Three corrections, all of them the SAME disease one level
further in — a number that is reported without the population it was measured against:

  - **M1 (perf).** Every denominator was 1 COUNT *per rule* on top of the finder query
    that already loops per rule (+17 statements / +16 `pages` scans per lint run on
    cybos's 24 rules). Now ONE grouped histogram per FAMILY — see the helper block below.
  - **M3.** The ontology EDGE `matched` counted rows the check CANNOT JUDGE (`domain`
    needs a typed SOURCE, `range` a resolved+typed TARGET). `RuleStat.matched_by_kind`
    now mirrors `findings` key-for-key, so every numerator has its OWN denominator.
  - **M4.** A degenerate property rule (empty `enum`) was `continue`d with NO `RuleStat`
    while its class still counted in `property_pages_examined` — a declared rule missing
    from `by_rule`. It now emits its stat first, in verbatim parity with drift.

**TASK 072 / P2 — `forbid_values`.** `CoverageRule` gained an optional `forbid_values`
modifier on `requires_field` (gap = absent/empty **OR** value ∈ the sentinel list).
⚠️ **STUB STATE (bead 072-08): `find_coverage_gaps_report` below still IGNORES it** —
the key parses and is load-gated, nothing more. Bead 072-09 adds the third disjunct.

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
    # TASK 061 (R-061-1) — shared population-count helpers.
    #
    # P-061-C: every denominator is a COUNT over an `IN (...)` set that MAY be
    # empty (a layout with no rules, or an ontology with no edges/properties
    # declared). NEVER compose a degenerate `IN ()` — return an EMPTY result
    # before touching SQL (mirrors the pre-existing hand-built-rule precedent in
    # this module: skip, never crash, never inject).
    #
    # 061 FIX-LOOP (vdd-multi critic-performance MED / M1) — these are HISTOGRAMS,
    # one grouped statement per FAMILY, not one COUNT per RULE. The first cut of
    # TASK 061 computed `matched` with a fresh `pages` scan per rule ON TOP of the
    # finder query that already loops per rule: on cybos's 24 declared rules that
    # was +17 statements (21→38) and +16 full `pages` scans (14→30) per lint run —
    # a >2× regression of `wiki-health coverage` (3→7 statements). The EDGE family
    # already did it right (`matched = len(rows)`, free off the fetchall it had to
    # run anyway); the other three now match that discipline. Zero DDL, NO new
    # index (P-5) — the fix is query SHAPE (1+N → 1), not a new access path.
    #
    # Statement census, per lint run on cybos (3 drift + 7 edge + 11 property rules):
    #   pre-061  21 statements / 14 `pages` scans
    #   061 v1   38 statements / 30 `pages` scans   ← the regression
    #   NOW      25 statements / 16 `pages` scans   (+4 / +2 over the pre-061 baseline:
    #            one grouped histogram per family, never one COUNT per rule)
    # =========================================================================

    def _page_class_histogram(self, vault_id: str, classes: set[str]) -> dict[str, int]:
        """``{page_class: COUNT(*)}`` over `pages` whose AUTHORED ``$.type`` is in
        ``classes`` — ONE grouped scan for the whole family (the family denominator is
        ``sum(...)``; a rule's ``matched`` is ``.get(cls, 0)``). A class with no pages is
        ABSENT from the dict, so callers MUST use ``.get(cls, 0)`` — an absent key means
        `0`, and rendering it as `0` is exactly what this task is for. Returns ``{}`` —
        **no query executed** — when ``classes`` is empty (P-061-C)."""
        if not classes:
            return {}
        conn = self._connect()
        clause, vals = self._in_clause(
            "json_extract(p.frontmatter_json, '$.type')", sorted(classes))
        rows = conn.execute(
            "SELECT json_extract(p.frontmatter_json, '$.type') AS t, COUNT(*) AS n "
            f"FROM pages p WHERE p.vault_id = ? AND {clause} GROUP BY t",
            [vault_id, *vals]).fetchall()
        return {str(r["t"]): int(r["n"]) for r in rows}

    def _count_refs_of_types(self, vault_id: str, ref_types: set[str]) -> int:
        """COUNT(*) of `page_entity_refs` rows whose `ref_type` is in
        `ref_types`. Returns `0` — no query executed — when `ref_types` is
        empty. ONE statement for the whole edge family (rides `idx_refs_type`;
        never a `pages` scan), so it is left as a plain COUNT: the edge rules'
        per-rule `matched` already comes free off their own `fetchall()`.

        NOT derived as `Σ len(rows)` over the edge rules, deliberately: those rows
        are INNER-JOINed to the owning `pages` row, so an orphaned ref (schema
        permits one only if the FK is unenforced) would silently shrink the
        denominator — a denominator that hides rows is the bug this task fixes."""
        if not ref_types:
            return 0
        conn = self._connect()
        clause, vals = self._in_clause("ref_type", sorted(ref_types))
        row = conn.execute(
            f"SELECT COUNT(*) FROM page_entity_refs WHERE vault_id = ? AND {clause}",
            [vault_id, *vals]).fetchone()
        return int(row[0])

    def _pages_with_edge_histogram(
        self, vault_id: str, classes: set[str], edges: set[str]
    ) -> dict[tuple[str, str], int]:
        """``{(page_class, ref_type): COUNT(DISTINCT page)}`` — pages of that class which
        CARRY that ref_type: a DRIFT rule's PRECONDITION (the `$.type = ? AND
        EXISTS(ref_type = ?)` head of `find_lifecycle_drift_report`'s query), for the WHOLE
        drift family in ONE grouped probe (M1: was one `pages` scan per rule).

        ``COUNT(DISTINCT p.id)`` reproduces the EXISTS semantics exactly — a page carrying
        the same edge to two targets is ONE matched page, not two (`pages.id` is the
        INTEGER PRIMARY KEY, so it is a per-page identity, and the join is driven off
        `idx_refs_type` + the `pages(vault_id, slug, project)` UNIQUE index).

        The `json_type($.status) = 'text'` scalar filter is part of the drift CONDITION,
        NOT the precondition, so it is deliberately absent here — otherwise a page whose
        status is absent/list-valued would vanish from the denominator it is legitimately
        measured against. Returns ``{}`` — no query executed — when either set is empty
        (P-061-C)."""
        if not classes or not edges:
            return {}
        conn = self._connect()
        cls_clause, cls_vals = self._in_clause(
            "json_extract(p.frontmatter_json, '$.type')", sorted(classes))
        ref_clause, ref_vals = self._in_clause("r.ref_type", sorted(edges))
        rows = conn.execute(
            "SELECT json_extract(p.frontmatter_json, '$.type') AS t, r.ref_type AS rt, "
            "COUNT(DISTINCT p.id) AS n "
            "FROM pages p "
            "JOIN page_entity_refs r ON r.vault_id = p.vault_id "
            "                       AND r.page_slug = p.slug "
            "                       AND r.page_project = p.project "
            f"WHERE p.vault_id = ? AND {cls_clause} AND {ref_clause} "
            "GROUP BY t, rt",
            [vault_id, *cls_vals, *ref_vals]).fetchall()
        return {(str(r["t"]), str(r["rt"])): int(r["n"]) for r in rows}

    def _property_scalar_histogram(
        self, vault_id: str, classes: set[str], fields: set[str]
    ) -> tuple[int, dict[tuple[str, str], int]]:
        """``(property_pages_examined, {(page_class, field): n})`` in ONE grouped scan
        (M1: was 1 + one `pages` scan per property rule — 12 statements on cybos).

        ``property_pages_examined`` = pages whose ``$.type`` ∈ ``classes`` (the family
        denominator). ``n`` = pages of that class whose ``$.<field>`` is a PRESENT scalar
        (``json_type(...) = 'text'``) — the population an ontology property rule can
        actually JUDGE; an ABSENT value is a coverage concern, not a contradiction
        (mirrors the property-violation finder's own filter, and the R-15 drift
        scalar-only rule).

        One conditional SUM per DISTINCT field (cybos declares 11 property rules over
        **one** field, `status` → one SUM). Every field is `validate_filter_field`-checked
        THEN BOUND as a `$.<field>` path — never string-composed; the only composed part is
        the placeholder COUNT. Returns ``(0, {})`` — no query executed — when ``classes``
        is empty (P-061-C)."""
        if not classes:
            return 0, {}
        ordered_fields = sorted({validate_filter_field(f) for f in fields})
        conn = self._connect()
        clause, vals = self._in_clause(
            "json_extract(p.frontmatter_json, '$.type')", sorted(classes))
        sums = "".join(
            f", SUM(CASE WHEN json_type(p.frontmatter_json, ?) = 'text' THEN 1 ELSE 0 END) "
            f"AS f{i}" for i in range(len(ordered_fields)))
        # Param ORDER follows SQL TEXT order: the SELECT-list `?` (one per field) precede
        # the WHERE-clause `?`s.
        params: list[Any] = [f"$.{f}" for f in ordered_fields]
        params += [vault_id, *vals]
        rows = conn.execute(
            f"SELECT json_extract(p.frontmatter_json, '$.type') AS t, COUNT(*) AS n{sums} "
            f"FROM pages p WHERE p.vault_id = ? AND {clause} GROUP BY t",
            params).fetchall()
        examined = 0
        hist: dict[tuple[str, str], int] = {}
        for r in rows:
            page_class = str(r["t"])
            examined += int(r["n"])
            for i, fld in enumerate(ordered_fields):
                hist[(page_class, fld)] = int(r[f"f{i}"])
        return examined, hist

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
        # TASK 061 (R-061-2 / bead 061-03) — DRIFT'S OWN DENOMINATOR. `pages_examined` =
        # pages whose AUTHORED $.type is in the UNION of drift_rules[].class (P-061-C: 0
        # rules ⇒ 0, no SQL). Per-rule `matched` = the rule's PRECONDITION ($.type = class
        # AND EXISTS(ref_type = edge)) — NOT the same population, and that is the whole
        # point: `matched` counts only pages that ALREADY CARRY the edge, so a bare
        # `matched: 0` cannot distinguish "no `decision` pages at all" (today's LIVE state)
        # from "50 decisions, none carrying a `superseded-by` edge" (the post-TASK-062
        # state). Both denominators are needed; neither substitutes for the other.
        #
        # 061 FIX-LOOP (M1): both numbers come from TWO grouped statements for the WHOLE
        # family (a class histogram + a (class, ref_type) probe), not from 1 + one scan
        # per rule.
        classes = {r.page_class for r in rules}
        class_hist = self._page_class_histogram(vault_id, classes)
        pages_examined = sum(class_hist.values())
        edge_hist = self._pages_with_edge_histogram(
            vault_id, classes, {r.edge for r in rules})
        conn = self._connect()
        out: list[DriftHit] = []
        rule_stats: list[RuleStat] = []
        for rule in rules:
            # Read BEFORE the expect/forbid branch, so the degenerate-rule `continue`
            # below still reports an honest `matched` (bead 061-03).
            matched = edge_hist.get((rule.page_class, rule.edge), 0)
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
                # Defensive (critic-security LOW-1): a hand-built rule (bypassing the
                # config-load gate) with NEITHER `expect_status` nor `forbid_status` would
                # otherwise build a degenerate `IN ()`. Skip it — never crash, never inject.
                #
                # 061 FIX-LOOP (critic-logic LOW): this used to claim "parity with
                # find_coverage_gaps". It is NOT parity — the three finders have THREE
                # degenerate behaviours, and the honest statement is the enumeration:
                #   • drift (here)          — a rule with no status branch: SKIP + a RuleStat
                #     (an examined-but-unjudgeable rule is still reported, never dropped).
                #   • coverage              — a rule with neither `requires_edge` nor
                #     `requires_field` does NOT skip: it reaches `validate_filter_field("")`
                #     and RAISES ValueError (fail-loud; the load-gate makes it unreachable).
                #   • ontology property     — an empty `enum`: SKIP + a RuleStat (fix-loop M4;
                #     it used to `continue` with NO RuleStat, silently omitting a declared
                #     rule from `by_rule` while its class still counted in the denominator).
                #
                # TASK 061 (bead 061-03): the skipped rule STILL gets a RuleStat. Its
                # PRECONDITION is well-defined (so `matched` is real), only its drift
                # CONDITION is degenerate — and "this rule examined N pages and found
                # nothing because the RULE is broken" is precisely the state this task
                # refuses to render as a silent green. Hence `∀ declared rule` in the
                # invariant test is a REAL quantifier: no rule is missing from `rule_stats`.
                rule_stats.append(RuleStat(
                    page_class=rule.page_class, kind="drift", ref=rule.edge,
                    matched=matched, matched_by_kind={"drift": matched},
                    findings={"drift": 0},
                ))
                continue
            sql += "ORDER BY p.project, p.slug"
            rows = conn.execute(sql, params).fetchall()
            for r in rows:
                out.append(DriftHit(
                    vault_id=vault_id, page_slug=r["slug"], page_project=r["project"],
                    page_class=rule.page_class, edge=rule.edge,
                    status=r["status"], expected=expected,
                ))
            rule_stats.append(RuleStat(
                page_class=rule.page_class, kind="drift", ref=rule.edge,
                matched=matched, matched_by_kind={"drift": matched},
                findings={"drift": len(rows)},
            ))
        return LifecycleDriftReport(
            hits=out, pages_examined=pages_examined, rule_stats=rule_stats)

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
        # empty-field predicate below is the GAP condition, not the precondition).
        #
        # 061 FIX-LOOP (M1): ONE grouped histogram gives BOTH — `pages_examined` is its
        # sum, `matched_r` is `.get(class)`. The first cut ran a fresh COUNT scan per rule
        # ON TOP of the union COUNT (3 rules → 4 scans where 1 suffices; `wiki-health
        # coverage` went 3 → 7 statements, a >2× regression of the whole command).
        classes = {r.page_class for r in rules}
        class_hist = self._page_class_histogram(vault_id, classes)
        pages_examined = sum(class_hist.values())
        conn = self._connect()
        out: list[CoverageGap] = []
        rule_stats: list[RuleStat] = []
        for rule in rules:
            matched = class_hist.get(rule.page_class, 0)
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
                matched=matched, matched_by_kind={"gaps": matched},
                findings={"gaps": len(rows)},
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
            #
            # 061 FIX-LOOP (critic-logic MED / M3) — `matched` alone COUNTS ROWS THE CHECK
            # CANNOT JUDGE. `domain` fires only when src_type IS NOT NULL; `range` only when
            # tgt_type IS NOT NULL (NULL for a dangling/entity/ambiguous target). So a vault
            # with 500 `uses` refs all pointing at `[[ghost]]` reported
            # `{matched: 500, findings: {domain: 0, range: 0}}` — which READS as "500
            # examined, all clean" while `range` examined ZERO. That is `{"total_gaps": 0}`
            # one level down, INSIDE the numbers this task added. We split the NUMERATOR
            # per kind (P-061-A) but not the DENOMINATOR. `matched_by_kind` closes it —
            # both counts are FREE off the same fetchall(). `matched` STAYS the row total
            # (the rule's examined population), so `matched_by_kind[k] <= matched` and the
            # pinned `domain + range > matched` fixture assertion both keep holding.
            rows = conn.execute(sql, (vault_id, edge.edge)).fetchall()
            domain_count = 0
            range_count = 0
            # `domain` is a PER-PAGE finding (de-duped below), so its denominator is the
            # DISTINCT judgeable pages; `range` is per-instance, so its denominator is rows.
            domain_judgeable: set[tuple[str, str]] = set()
            range_judgeable = 0
            for row in rows:
                src_type = row["src_type"]
                tgt_type = row["tgt_type"]
                if src_type is not None:
                    domain_judgeable.add((row["page_slug"], row["page_project"]))
                if tgt_type is not None:
                    range_judgeable += 1
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
            # a range violation). `matched_by_kind` mirrors it EXACTLY (same key set), so
            # the honest invariant is `findings[k] ≤ matched_by_kind[k] ≤ matched`.
            rule_stats.append(RuleStat(
                page_class="", kind="edge", ref=edge.edge, matched=len(rows),
                matched_by_kind={"domain": len(domain_judgeable),
                                 "range": range_judgeable},
                findings={"domain": domain_count, "range": range_count},
            ))

        # (b) property enum — a PRESENT scalar `$.<field>` not in the enum. `json_type ==
        # 'text'` excludes absent/null/list/object (an absence is a coverage concern, not a
        # contradiction — mirrors the drift scalar-only rule). Field re-validated
        # (library-caller defense) + bound as a `$.<field>` path; enum values bound.
        #
        # `property_pages_examined` — TASK 061: pages whose $.type is in ⋃
        # ontology.properties[].class (P-061-C: 0 properties ⇒ 0, no SQL).
        #
        # 061 FIX-LOOP (M1): ONE grouped scan yields the family denominator AND every
        # rule's `matched` (one conditional SUM per DISTINCT field — cybos's 11 property
        # rules all key on `status`, so: one SUM). The first cut ran 1 + 11 scans.
        prop_classes = {p.page_class for p in ontology.properties}
        property_pages_examined, prop_hist = self._property_scalar_histogram(
            vault_id, prop_classes, {p.field for p in ontology.properties})
        for prop in ontology.properties:
            field = validate_filter_field(prop.field)
            # TASK 061: `matched_p` = pages of this class carrying a PRESENT scalar for the
            # field (the rule's PRECONDITION) — NOT the violation count below (which further
            # filters NOT IN enum).
            matched = prop_hist.get((prop.page_class, field), 0)
            if not prop.enum:
                # Defensive: a hand-built rule bypassing the load-gate → skip (never a
                # degenerate `IN ()`).
                #
                # 061 FIX-LOOP (critic-logic MED / M4) — it used to `continue` with **no
                # RuleStat**, while its class STILL contributed to
                # `property_pages_examined`: a declared rule silently ABSENT from `by_rule`,
                # so the `∀ declared rule` quantifier in the invariant test held only
                # because the config load-gate rejects an empty enum — enforced by CONFIG,
                # not by CODE. Drift's degenerate branch got belt-and-braces; ontology got a
                # single point of failure. Now they are verbatim parity: emit the RuleStat,
                # THEN skip.
                rule_stats.append(RuleStat(
                    page_class=prop.page_class, kind="property", ref=field,
                    matched=matched, matched_by_kind={"property": matched},
                    findings={"property": 0},
                ))
                continue
            json_path = f"$.{field}"
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
                matched=matched, matched_by_kind={"property": matched},
                findings={"property": len(rows)},
            ))
        return OntologyReport(
            violations=out, edges_examined=edges_examined,
            property_pages_examined=property_pages_examined, rule_stats=rule_stats,
        )
