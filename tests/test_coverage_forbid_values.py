"""TASK 072 / P2 — `forbid_values`: the coverage-rule modifier for *present, and a
non-answer*.

WHY THIS EXISTS. `wiki-health` examined all 20 elma-kb `hypothesis` pages and
pronounced them healthy: `proposed` is a legal status and `verified_on` is PRESENT —
it just carries a value MEANING unverified. Not a vacuous green (the denominator was
honest) but a blind spot the shipped rule vocabulary could not express: neither *field
absent/empty* nor *no typed edge*.

THE DISCRIMINATION CONTROL IS THE POINT (Rule 4 / the control whose absence killed
R-23 Phase B). One corpus, one field, one value — TWO rules that differ ONLY in the
modifier:

  - `{class: hypothesis, requires_field: verified_on, forbid_values: [...]}`  → FIRES
  - `{class: fact,       requires_field: verified_on}`                        → does NOT

and the `fact` rule is proved ALIVE by `fact-absent` (which it does report), so its
silence on the sentinel is a verdict rather than a broken rule. A rule that fires on
everything and a rule that fires on nothing both pass a one-sided test.

OFF-EQUIVALENCE (ADR-005-D2 style). With the key absent, the emitted SQL and the
`wiki-health coverage` envelope are BYTE-IDENTICAL to pre-072. Pinned as goldens,
captured from the pre-change tree — not re-derived from the post-change code, which
would only prove the change agrees with itself.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.wiki_index.layout_config import resolve_layout_config
from scripts.wiki_index.models import CoverageRule
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from tests._health_fixtures import build_cybos_vault

REPO_ROOT = Path(__file__).resolve().parents[1]

# The sentinel vocabulary is an AUTHORING CONVENTION and lives in the operator's
# `<vault>/.wiki/layout.yaml` — never in a built-in layout. Pinned here as the
# override text a real operator would write.
_OVERRIDE = (
    "coverage_rules:\n"
    "  - {class: hypothesis, requires_field: verified_on, "
    'forbid_values: ["не проверено", "n/a"]}\n'
    "  - {class: fact, requires_field: verified_on}\n"
)

_FILES = {
    # --- hypothesis: the class the modifier binds to ---
    "hypotheses/h-sentinel.md":
        '---\ntype: hypothesis\ntitle: H Sentinel\nstatus: proposed\n'
        'verified_on: "не проверено"\n---\nbody\n',
    "hypotheses/h-sentinel2.md":
        '---\ntype: hypothesis\ntitle: H Sentinel 2\nstatus: proposed\n'
        'verified_on: "n/a"\n---\nbody\n',
    # the control that must NEVER be a gap under either rule set
    "hypotheses/h-real.md":
        '---\ntype: hypothesis\ntitle: H Real\nstatus: confirmed\n'
        'verified_on: "2026-01-02"\n---\nbody\n',
    # the two PRE-072 gap shapes — must stay gaps, and stay kind `field`
    "hypotheses/h-absent.md":
        "---\ntype: hypothesis\ntitle: H Absent\nstatus: proposed\n---\nbody\n",
    "hypotheses/h-empty.md":
        '---\ntype: hypothesis\ntitle: H Empty\nstatus: proposed\n'
        'verified_on: ""\n---\nbody\n',
    # --- fact: SAME field, SAME value, a rule WITHOUT the modifier ---
    "facts/fact-sentinel.md":
        '---\ntype: fact\ntitle: Fact Sentinel\nsource: "https://example.com"\n'
        'verified_on: "не проверено"\n---\nbody\n',
    "facts/fact-absent.md":
        '---\ntype: fact\ntitle: Fact Absent\nsource: "https://example.com"\n---\nbody\n',
}


def _gaps(repo: SQLiteRepository, vault_id: str, rules: list[CoverageRule]
          ) -> set[tuple[str, str, str]]:
    """``{(slug, class, kind)}`` — the identity a gap is asserted on."""
    report = repo.find_coverage_gaps_report(vault_id, rules)
    return {(g.page_slug, g.page_class, g.kind) for g in report.gaps}


# =============================================================================
# The discrimination control — both halves, same corpus.
# =============================================================================


def test_the_modifier_fires_on_the_sentinel_class(tmp_path: Path) -> None:
    repo, root = build_cybos_vault(
        tmp_path, _FILES, vault_id="p2on", layout_override=_OVERRIDE)
    cfg = resolve_layout_config(root)
    rules = list(cfg.coverage_rules)
    assert [r.forbid_values for r in rules] == [("не проверено", "n/a"), ()]

    report = repo.find_coverage_gaps_report("p2on", rules)
    found = {(g.page_slug, g.page_class, g.kind) for g in report.gaps}
    assert found == {
        # PRESENT but a non-answer — the whole point of P2, and INEXPRESSIBLE before it
        ("h-sentinel", "hypothesis", "field-value"),
        ("h-sentinel2", "hypothesis", "field-value"),
        # the two pre-072 shapes, unchanged and still kind `field`
        ("h-absent", "hypothesis", "field"),
        ("h-empty", "hypothesis", "field"),
        # the forbid-LESS rule is ALIVE: it reports absence on its own class
        ("fact-absent", "fact", "field"),
    }
    repo.close()


def test_the_same_value_on_a_rule_without_the_modifier_is_not_a_gap(tmp_path: Path) -> None:
    """`fact-sentinel` carries the IDENTICAL field and the IDENTICAL value as
    `h-sentinel`, and is examined by a rule on that very field. It is NOT a gap. The
    only difference is the modifier — so the modifier, not the corpus, is what fires.

    Paired with `fact-absent` above (which the same rule DOES report), this separates
    "the rule judged it clean" from "the rule is broken/never runs"."""
    repo, root = build_cybos_vault(
        tmp_path, _FILES, vault_id="p2ctl", layout_override=_OVERRIDE)
    rules = list(resolve_layout_config(root).coverage_rules)
    found = _gaps(repo, "p2ctl", rules)
    assert ("fact-sentinel", "fact", "field") not in found
    assert ("fact-sentinel", "fact", "field-value") not in found
    assert ("fact-absent", "fact", "field") in found      # …and the rule is alive
    repo.close()


def test_a_real_value_is_never_a_gap_under_either_rule(tmp_path: Path) -> None:
    """The other one-sided failure: a modifier that widens the predicate into
    "any present value is a gap" would also pass every assertion above."""
    repo, root = build_cybos_vault(
        tmp_path, _FILES, vault_id="p2real", layout_override=_OVERRIDE)
    rules = list(resolve_layout_config(root).coverage_rules)
    found = _gaps(repo, "p2real", rules)
    assert not [f for f in found if f[0] == "h-real"]
    repo.close()


def test_the_rule_examined_a_non_zero_population(tmp_path: Path) -> None:
    """★ Rule 4 — the control asserts `matched > 0`, not merely `gaps == 0`. A rule
    binding to a class with no pages reports a clean, honest-looking zero."""
    repo, root = build_cybos_vault(
        tmp_path, _FILES, vault_id="p2den", layout_override=_OVERRIDE)
    rules = list(resolve_layout_config(root).coverage_rules)
    report = repo.find_coverage_gaps_report("p2den", rules)
    assert report.pages_examined == 7          # 5 hypotheses + 2 facts
    by_class = {s.page_class: s for s in report.rule_stats}
    assert by_class["hypothesis"].matched == 5 > 0
    assert by_class["fact"].matched == 2 > 0
    # per-rule findings, each against its OWN denominator
    assert by_class["hypothesis"].findings == {"gaps": 4}
    assert by_class["fact"].findings == {"gaps": 1}
    # the rule-level kind reports what the RULE can express (the per-ROW kind above
    # reports why THAT page is a gap) — so a reader of `by_rule` can tell a
    # forbid-carrying rule from a plain one without re-reading the layout.
    assert by_class["hypothesis"].kind == "field-value"
    assert by_class["fact"].kind == "field"
    repo.close()


# =============================================================================
# Off-equivalence — the key ABSENT must change nothing, byte for byte.
# =============================================================================

def _off_golden(vault_id: str) -> list[str]:
    """The two statements `find_coverage_gaps_report` emitted for a bare
    `requires_field` rule BEFORE TASK 072, captured from the pre-change tree via
    `sqlite3.set_trace_callback` (which expands bound parameters — so this also pins
    that every value is BOUND, never interpolated). Re-pin ONLY with a deliberate
    decision that the OFF path may change."""
    return [
        "SELECT json_extract(p.frontmatter_json, '$.type') AS t, COUNT(*) AS n "
        f"FROM pages p WHERE p.vault_id = '{vault_id}' AND "
        "json_extract(p.frontmatter_json, '$.type') IN ('hypothesis') GROUP BY t",
        "SELECT p.slug, p.project FROM pages p WHERE p.vault_id = "
        f"'{vault_id}' AND json_extract(p.frontmatter_json, '$.type') = 'hypothesis' "
        "AND (json_extract(p.frontmatter_json, '$.verified_on') IS NULL "
        "     OR CAST(json_extract(p.frontmatter_json, '$.verified_on') AS TEXT) "
        "IN ('', '[]', '{}')) ORDER BY p.project, p.slug",
    ]


def test_off_path_sql_is_byte_identical_to_pre_072(tmp_path: Path) -> None:
    repo, _root = build_cybos_vault(tmp_path, _FILES, vault_id="p2off")
    stmts: list[str] = []
    repo._connect().set_trace_callback(stmts.append)
    repo.find_coverage_gaps_report(
        "p2off", [CoverageRule(page_class="hypothesis", requires_field="verified_on")])
    repo._connect().set_trace_callback(None)
    assert stmts == _off_golden("p2off")
    repo.close()


def test_off_path_findings_are_unchanged(tmp_path: Path) -> None:
    """The same rule WITHOUT the modifier still reports exactly the two pre-072 shapes
    — and, critically, still does NOT report the sentinel pages. Off means off."""
    repo, _root = build_cybos_vault(tmp_path, _FILES, vault_id="p2off2")
    found = _gaps(repo, "p2off2",
                  [CoverageRule(page_class="hypothesis", requires_field="verified_on")])
    assert found == {("h-absent", "hypothesis", "field"),
                     ("h-empty", "hypothesis", "field")}
    repo.close()


def test_off_path_statement_count_is_unchanged(tmp_path: Path) -> None:
    """M1's 1+N→1 collapse must survive P2: ONE class histogram + one finder per rule,
    with or without the modifier. A modifier implemented as a second query would pass
    every behavioural test above and silently re-open the regression TASK 061 fixed."""
    repo, root = build_cybos_vault(
        tmp_path, _FILES, vault_id="p2stmt", layout_override=_OVERRIDE)
    rules = list(resolve_layout_config(root).coverage_rules)
    stmts: list[str] = []
    repo._connect().set_trace_callback(stmts.append)
    repo.find_coverage_gaps_report("p2stmt", rules)
    repo._connect().set_trace_callback(None)
    assert len(stmts) == 1 + len(rules) == 3, stmts
    repo.close()


def test_wiki_health_envelope_off_path_is_unchanged(tmp_path: Path) -> None:
    """End-to-end, through the CLI: a cybos vault with NO override emits the same
    coverage envelope it emitted pre-072. Pinned in full — a new key, a renamed key or
    a moved number all go RED."""
    repo, root = build_cybos_vault(tmp_path, _FILES, vault_id="p2env")
    repo.close()
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.wiki_skills.wiki_health", "coverage",
         "--vault", "p2env", "--db-path", str(tmp_path / "p2env.db")],
        capture_output=True, text=True, cwd=REPO_ROOT, check=False)
    assert proc.returncode == 0, proc.stderr
    env = json.loads(proc.stdout)
    # CAPTURED from the pre-change tree, not written by hand. The first hand-written
    # version of this pin was wrong in three places (invented an `ok` key, missed
    # `rules`, mis-stated `pages_examined`) — which is the argument for capturing.
    assert env == {
        "action": "coverage",
        "vault": "p2env",
        "rules": 3,
        "total_gaps": 0,
        "pages_examined": 2,
        "by_rule": [
            {"class": "requirement", "kind": "edge", "ref": "implemented-by",
             "matched": 0, "matched_by_kind": {"gaps": 0}, "findings": {"gaps": 0}},
            {"class": "capability", "kind": "edge", "ref": "implemented-by",
             "matched": 0, "matched_by_kind": {"gaps": 0}, "findings": {"gaps": 0}},
            {"class": "fact", "kind": "field", "ref": "source",
             "matched": 2, "matched_by_kind": {"gaps": 2}, "findings": {"gaps": 0}},
        ],
        "by_class": {},
        "gaps": [],
        "vacuous_populations": [],
        "vacuous_kinds": [],
    }, json.dumps(env, ensure_ascii=False, indent=2)
    # ⚠️ NOT A P2 DEFECT, recorded because this pin makes it visible: the `requirement`
    # and `capability` rules matched **0** pages and are flagged by NEITHER
    # `vacuous_populations` (a FAMILY-level number, and the family is non-empty at 2)
    # NOR `vacuous_kinds` (which only fires on a rule that matched rows it could not
    # judge). A rule that matched nothing at all falls between them. That is the
    # ADR-006 D-036-4 honest-denominator hole, which PREDATES P2 — `by_rule[].matched`
    # does carry the truth, so the envelope is not lying, only under-summarising.
    assert [r["matched"] for r in env["by_rule"]] == [0, 0, 2]


# =============================================================================
# The sentinel strings are an authoring convention — they never ship.
# =============================================================================


def test_no_builtin_layout_ships_forbid_values() -> None:
    """★ Mechanically enforced, not review-gated (the 072-03d lesson: a rule a human
    has to remember is a rule that gets forgotten). Shipping one importer's Russian
    authoring convention inside a built-in layout would make every cybos vault in the
    world inherit it. The population is GLOB-DISCOVERED, so a layout added tomorrow is
    covered without editing this test."""
    layouts = sorted((REPO_ROOT / "scripts/wiki_index/layouts").glob("*.yaml"))
    assert len(layouts) >= 4, layouts        # non-vacuity: the population is not empty
    offenders = [
        p.name for p in layouts
        if any(line.lstrip().startswith("forbid_values")
               or ", forbid_values:" in line or "{forbid_values:" in line
               for line in p.read_text(encoding="utf-8").splitlines()
               if not line.lstrip().startswith("#"))
    ]
    assert offenders == [], (
        f"{offenders} declare forbid_values — the sentinel vocabulary belongs in "
        f"<vault>/.wiki/layout.yaml, never in a shipped layout")
