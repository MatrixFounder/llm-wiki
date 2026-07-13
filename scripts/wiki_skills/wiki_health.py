"""`wiki-health` CLI (TASK 036 / R-15, Slice A2, ADR-006; TASK 054 / R-19) — READ-ONLY
derived knowledge-health report over the event graph + frontmatter. Two subcommands:

  wiki-health coverage --vault <vid> [--class C]   # pages missing an expected relation
  wiki-health ontology --vault <vid> [--class C]   # pages contradicting the ontology contract

Rules are layout-config-driven (`coverage_rules` / the `ontology:` block; the `cybos`
layout ships them, other layouts default to none → an empty report). A gap / violation
report from THIS CLI is DATA, not a failure, so it ALWAYS exits 0 on success — contrast
`wiki-lint`, where the sibling lifecycle-drift and ontology-violation checks are
*contradictions* and gate `--strict`.

Decision-17: deterministic plumbing (SQL + config; no `import anthropic`); one JSON
envelope + a stable exit code; the slug/edge/field values are BOUND DAL params, never
string-composed (injection-safe — TASK 013 posture). Read-only — no DB writes.

Exit codes: 0 ok (incl. gaps/violations found) · 2 INVALID_CLASS · 6 VAULT_NOT_FOUND.

TASK 061 (R-061-1) — HONEST DENOMINATORS. `{"total_gaps": 0}` used to be
indistinguishable from "0 typed pages were ever examined" (the LIVE-vault state: 713
`concept` pages, zero pages in any rule's class). Every REPORT envelope now carries its
family's POSITIVELY-DEFINED denominator + per-rule `matched`, and says so out loud via a
`note` when the denominator is 0. Keys are ADDITIVE — no pre-061 key renamed or removed.

**The `emit(` census (enumerate the surfaces; do not assume there is one):** this module
has SIX `emit(` sites — `main` VAULT_NOT_FOUND(6); `_run_coverage` INVALID_CLASS(2) +
report(0); `_run_ontology` `ontology is None` early-return(0) + INVALID_CLASS(2) +
report(0). **All THREE exit-0 REPORT paths carry the new keys** (including the
`ontology is None` early return — a consumer must never see a key go missing depending on
config). The THREE `error` envelopes deliberately do NOT: they carry an `"error"` key +
a non-zero exit and are not reports. Emitting `pages_examined: 0` there would assert
"examined nothing" where in fact nothing was ATTEMPTED — a fresh instance of the very
confusion this task exists to kill. Boundary STATED, not merely true.

`--class` semantics (stated because it scopes the denominators): `coverage` filters the
RULES *before* the DAL call ⇒ its denominators describe the FILTERED run. `ontology`
filters the VIOLATIONS *after* the call ⇒ its denominators describe the WHOLE run (what
the DAL actually examined), while `violations[]` is the filtered view — the ontology
envelope's additive `class_filter` key makes that mixed scoping machine-visible (061
fix-loop). Both are honest, and the per-rule invariant holds in both — `by_rule` is always
the DAL's own accounting.

The two `--class` VALIDITY rosters are deliberately different (061 fix-loop / M5):
`coverage` validates against its RULES' classes (correct by construction — it can report
no other class), `ontology` against the layout's CLOSED type roster (`type_mapping` keys —
the roster its own load-gate already uses). A `domain` violation's class is BY DEFINITION
outside the edge's declared `from`, so validating ontology against the declared classes
rejected exactly the classes the envelope had just reported in `by_class`.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout_config import resolve_layout_config
from scripts.wiki_skills._common import (
    build_repo_config,
    emit,
    resolve_vault_root_for_cli,
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="wiki-health",
        description="Read-only derived knowledge-health report (TASK 036 / R-15).")
    sub = p.add_subparsers(dest="cmd", required=True)
    cov = sub.add_parser("coverage", help="pages missing an expected edge/field")
    cov.add_argument("--vault", required=True, help="vault_id to analyze.")
    cov.add_argument("--class", dest="page_class", default=None,
                     help="restrict the report to ONE page class (e.g. requirement).")
    cov.add_argument("--db-path", default=None)
    cov.add_argument("--vault-root", default=None)
    ont = sub.add_parser("ontology", help="pages contradicting the ontology contract (R-19)")
    ont.add_argument("--vault", required=True, help="vault_id to analyze.")
    ont.add_argument("--class", dest="page_class", default=None,
                     help="restrict the report to ONE offending page class.")
    ont.add_argument("--db-path", default=None)
    ont.add_argument("--vault-root", default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    config = build_repo_config(
        args.vault, vault_root=resolve_vault_root_for_cli(args),
        db_path_flag=args.db_path)
    repo = make_repo(config)
    try:
        vault = repo.get_vault(args.vault)
        if vault is None:
            return emit({"error": "VAULT_NOT_FOUND", "vault": args.vault}, 6)
        # Rules ride the vault's LAYOUT grammar — resolve from the REGISTERED root_path
        # (not a CWD walk), so the report works from any directory.
        layout = resolve_layout_config(vault.root_path)
        if args.cmd == "ontology":
            return _run_ontology(repo, args, layout)
        return _run_coverage(repo, args, layout)
    finally:
        repo.close()


NOTE_NO_COVERAGE_RULES = "no coverage rules configured for this layout"
NOTE_NO_ONTOLOGY = "no ontology contract configured for this layout"
NOTE_COVERAGE_VACUOUS = (
    "coverage rules are configured, but NO page carries an authored $.type in those "
    "classes — nothing was examined (this is not a clean bill of health)"
)
# 061 FIX-LOOP (vdd-multi critic-logic LOW): an `ontology: {closed_types: true}` block with
# NO `edges` and NO `properties` is SCHEMA-VALID (both default to `[]` —
# `config/layout-config.schema.yaml` §Ontology), and it used to fall through to
# NOTE_ONTOLOGY_VACUOUS, which blames the VAULT'S DATA ("no page carries…") when the truth
# is "you declared no rules". Coverage already distinguishes the two precisely
# (NOTE_NO_COVERAGE_RULES vs NOTE_COVERAGE_VACUOUS); ontology now mirrors it. Misdirecting
# the operator about WHY a check found nothing is the same disease as not telling him at all.
NOTE_NO_ONTOLOGY_RULES = (
    "an ontology block is configured, but it declares NO edges and NO properties — there "
    "are no rules to examine (this is not a clean bill of health)"
)
NOTE_ONTOLOGY_VACUOUS = (
    "an ontology contract is configured, but NO page_entity_refs row carries a declared "
    "edge type AND no page carries an authored $.type in the property classes — nothing "
    "was examined (this is not a clean bill of health)"
)


def _run_coverage(repo: Any, args: argparse.Namespace, layout: Any) -> int:
    rules = list(layout.coverage_rules)
    if args.page_class is not None:
        classes = sorted({r.page_class for r in rules})
        if args.page_class not in classes:
            # No echo of the offending value beyond the valid set (CWE-209 posture,
            # mirrors wiki-graph's INVALID_KIND). An ERROR envelope — no denominators
            # (see the module docstring's emit-census: nothing was ATTEMPTED here).
            return emit({"error": "INVALID_CLASS", "valid": classes}, 2)
        rules = [r for r in rules if r.page_class == args.page_class]
    # TASK 061: the report method carries `gaps` AND the denominator; `find_coverage_gaps`
    # is now a thin wrapper over `.gaps`, so this is the SAME query, not a second one.
    report = repo.find_coverage_gaps_report(args.vault, rules)
    gaps = report.gaps
    by_class: dict[str, int] = {}
    for g in gaps:
        by_class[g.page_class] = by_class.get(g.page_class, 0) + 1
    envelope: dict[str, Any] = {
        "action": "coverage",
        "vault": args.vault,
        "rules": len(rules),
        "total_gaps": len(gaps),
        # TASK 061 (R-061-1) — the denominator. Pages whose AUTHORED `$.type` is in the
        # UNION of the (possibly --class-filtered) rules' classes. Do NOT read
        # `total_gaps <= pages_examined` as an invariant: two rules may target one class,
        # so one page can gap twice. The per-rule form in `by_rule` is the true one.
        "pages_examined": report.pages_examined,
        "by_rule": [s.to_json() for s in report.rule_stats],
        "by_class": by_class,
        "gaps": [
            {"slug": g.page_slug, "project": g.page_project,
             "class": g.page_class, "kind": g.kind, "missing": g.detail}
            for g in gaps
        ],
    }
    if not rules:
        # vdd-multi critic-logic LOW: a layout with NO coverage rules (a non-cybos
        # vault, or a cybos vault whose root_path moved → resolve defaults to karpathy)
        # yields an empty report — say it was not analyzable rather than implying
        # "0 gaps = healthy".
        envelope["note"] = NOTE_NO_COVERAGE_RULES
    elif report.pages_examined == 0:
        # TASK 061 — THE POINT OF THE TASK. Rules exist and ran, but their population is
        # EMPTY: `total_gaps: 0` here means "examined nothing", not "healthy". A distinct,
        # already-honest condition from the no-rules note above.
        envelope["note"] = NOTE_COVERAGE_VACUOUS
    return emit(envelope)


def _run_ontology(repo: Any, args: argparse.Namespace, layout: Any) -> int:
    # TASK 054 / R-19 — read-only ontology-contract report. A violation is a CONTRADICTION,
    # but THIS surface is the report view (the `--strict`-gating rail is `wiki-lint`), so it
    # ALWAYS exits 0 (like `coverage`). No ontology block ⇒ empty report + a note.
    if layout.ontology is None:
        # TASK 061: this early return is one of the module's THREE report exit paths — it
        # emits the SAME key set as the report below (all zero). A consumer must never see
        # a key appear/disappear depending on the vault's config (`class_filter` included —
        # 061 fix-loop NIT; pinned by test_tc_02_3_ontology_none_early_return_same_keys).
        return emit({
            "action": "ontology", "vault": args.vault, "total_violations": 0,
            "class_filter": args.page_class,
            "edges_examined": 0, "property_pages_examined": 0, "by_rule": [],
            "by_kind": {}, "by_class": {}, "violations": [],
            "note": NOTE_NO_ONTOLOGY,
        })
    # TASK 061 (R-061-1, C6): ONE call, TWO populations — edges (domain/range) and pages
    # (property enums) — hence TWO denominators. `find_ontology_violations` is now a thin
    # wrapper over `.violations`, so this is the same query, not a second one.
    report = repo.find_ontology_violations_report(args.vault, layout.ontology)
    violations = report.violations
    if args.page_class is not None:
        # 061 FIX-LOOP (vdd-multi critic-logic MED / M5) — THE GATE REJECTED THE CLASSES
        # MOST LIKELY TO OFFEND. It used to build the valid set from the DECLARED classes
        # (⋃(edge.frm ∪ edge.to) ∪ {p.page_class}) — but a `domain` violation's `page_class`
        # is BY DEFINITION a class NOT in that edge's `from`. TASK 061's own fixture proves
        # it: `fact-badcauses` (`type: fact`, `causes: [[wf-target]]`) is a domain violation
        # with `page_class="fact"`, and `fact` appears in no from/to/property list in
        # cybos.yaml — so the CLI reported `by_class: {"fact": 1}` and then answered
        # `--class fact` with INVALID_CLASS + exit 2, rejecting a class it had named ONE
        # LINE EARLIER IN THE SAME ENVELOPE.
        #
        # The right roster is the layout's CLOSED type roster — `type_mapping`'s keys — which
        # is ALREADY the ontology's own load-gate roster (`layout_config._validate_ontology`:
        # every from/to/class must be a `type_mapping` key; "no second roster,
        # derive-don't-author"). It is a strict SUPERSET of the declared classes, so no class
        # that was accepted before is rejected now.
        #
        # `coverage`'s gate stays as-is and is correct BY CONSTRUCTION: it filters the RULES
        # before the DAL call, so the only classes it can ever report are its rules' classes.
        classes = sorted(layout.type_mapping)
        if args.page_class not in classes:
            # No echo of the offending value beyond the valid set (CWE-209 posture). An
            # ERROR envelope — no denominators (module-docstring emit-census).
            return emit({"error": "INVALID_CLASS", "valid": classes}, 2)
        violations = [v for v in violations if v.page_class == args.page_class]
    by_kind: dict[str, int] = {}
    by_class: dict[str, int] = {}
    for v in violations:
        by_kind[v.kind] = by_kind.get(v.kind, 0) + 1
        by_class[v.page_class] = by_class.get(v.page_class, 0) + 1
    envelope: dict[str, Any] = {
        "action": "ontology",
        "vault": args.vault,
        "total_violations": len(violations),
        # 061 FIX-LOOP (NIT): the `--class` scoping is MIXED on this subcommand and now says
        # so machine-visibly — `total_violations`/`by_kind`/`by_class`/`violations` describe
        # the FILTERED view, while `edges_examined`/`property_pages_examined`/`by_rule`
        # describe the WHOLE DAL run (ontology filters violations AFTER the call). `null`
        # ⇒ unfiltered ⇒ the two scopes coincide. Coverage needs no such key: it filters the
        # RULES before the call, so its whole envelope is one scope.
        "class_filter": args.page_class,
        # TASK 061 — TWO denominators, because the check spans TWO populations. `by_rule`
        # binds each rule's `matched` + per-kind findings to its OWN family denominator
        # (edge rules → `edges_examined`; property rules → `property_pages_examined`).
        # Deliberately NOT named `pages_examined`: coverage owns that noun for a DIFFERENT
        # population (RTM constraint 4 / Q-061-1). `by_rule` describes the WHOLE DAL run,
        # unaffected by the post-hoc `--class` filter on `violations[]` above.
        "edges_examined": report.edges_examined,
        "property_pages_examined": report.property_pages_examined,
        "by_rule": [s.to_json() for s in report.rule_stats],
        "by_kind": by_kind,
        "by_class": by_class,
        "violations": [
            {"slug": v.page_slug, "project": v.page_project, "class": v.page_class,
             "kind": v.kind, "ref": v.ref, "detail": v.detail, "target": v.target_slug}
            for v in violations
        ],
    }
    if not layout.ontology.edges and not layout.ontology.properties:
        # 061 FIX-LOOP (LOW): a declared-but-RULE-LESS ontology block. Distinct from the
        # vacuous case below — and it must not be described as it, or the operator goes
        # hunting for missing typed pages when the fix is to declare a rule. Same shape as
        # coverage's `if not rules: … elif pages_examined == 0: …`.
        envelope["note"] = NOTE_NO_ONTOLOGY_RULES
    elif report.edges_examined == 0 and report.property_pages_examined == 0:
        # TASK 061 — the LIVE 8836-`mentioned`-ref trap: a contract IS declared, but NOTHING
        # it binds to exists. `total_violations: 0` here means "examined nothing".
        envelope["note"] = NOTE_ONTOLOGY_VACUOUS
    return emit(envelope)


if __name__ == "__main__":
    sys.exit(main())
