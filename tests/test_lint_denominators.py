"""TASK 061 / R-061-2 (bead 061-03) — `wiki-lint` reports what BOTH of its
config-driven semantic checks examined.

`wiki-lint` runs FOUR `check_*` functions; **two** are config-driven with a rule
population, and **both gate `--strict`** — the CI rail:

    $ grep -n "issues.extend(\\|def check_" scripts/wiki_index/lint.py
    def check_auto_generated_unchanged   — hash drift, NO rule population  → no denominator
    def check_lifecycle_drift            — drift_rules,  gates --strict    → denominator ✅
    def check_ontology_violations        — ontology:,    gates --strict    → denominator ✅
    def check_classification_policy      — policy:, declared-but-OFF (§5)  → no denominator

Wiring only the first of the two (as PLAN v1 did) would have left `wiki-lint` printing
`ontology-violation: 0` with NO denominator on the one surface that gates CI — the 7th
recurrence of this task's own fractal, and the exact thing TC-03-5 pins.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime
from pathlib import Path

from scripts.wiki_index.layout_config import resolve_layout_config
from scripts.wiki_index.lint import (
    LintIssue,
    check_lifecycle_drift,
    check_lifecycle_drift_report,
    check_ontology_violations,
    check_ontology_violations_report,
    run_all_checks,
    run_all_checks_report,
)
from scripts.wiki_index.models import DriftRule, Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills.wiki_lint import main as lint_main
from tests._health_fixtures import _FILES, build_cybos_vault, build_health_vault
from tests.test_health_denominators import _type_counts


def _run_lint(capsys, argv: list[str]) -> tuple[int, dict]:
    rc = lint_main(argv)
    out = capsys.readouterr().out.strip().splitlines()[-1]
    return rc, json.loads(out)


# --- TC-03-1: drift, typed pages AND the edges ⇒ matched > 0 -----------------

def test_tc_03_1_drift_typed_with_edges(tmp_path: Path) -> None:
    # build_health_vault carries typed pages AND the inverse edges (dec-old2 gets the
    # derived `superseded-by` from dec-new's `supersedes`) — RTM constraint 5: a
    # typed-pages-ONLY fixture would leave `matched` at 0 and "prove" non-vacuity while
    # proving nothing.
    repo, _root = build_health_vault(tmp_path)
    report = run_all_checks_report(repo, vaults=["hvault"])
    drift = report.denominators["hvault"]["lifecycle-drift"]
    counts = _type_counts(_FILES)
    assert drift["pages_examined"] == counts["decision"] + counts["workflow"] == 10
    assert any(s["matched"] > 0 for s in drift["by_rule"])
    for stat in drift["by_rule"]:
        assert stat["findings"]["drift"] <= stat["matched"] <= drift["pages_examined"]
    repo.close()


# --- TC-03-2: drift, typed pages, NO edges — the E2 distinction --------------

def test_tc_03_2_drift_typed_but_no_edges(tmp_path: Path) -> None:
    """THE state a bare `matched: 0` cannot distinguish from "no decision pages at all":
    a vault WITH `decision` pages, none of which carries a lifecycle edge (the
    post-TASK-062 state). `pages_examined > 0` while every `matched == 0` is exactly the
    signal — and it is why drift needs `pages_examined` ON TOP OF `matched`."""
    repo, _root = build_cybos_vault(tmp_path, {
        "decisions/d1.md": "---\ntype: decision\ntitle: D1\nstatus: accepted\n---\nb\n",
        "decisions/d2.md": "---\ntype: decision\ntitle: D2\nstatus: accepted\n---\nb\n",
    }, vault_id="noedges")
    report = run_all_checks_report(repo, vaults=["noedges"])
    drift = report.denominators["noedges"]["lifecycle-drift"]
    assert drift["pages_examined"] == 2                       # the pages ARE there...
    assert all(s["matched"] == 0 for s in drift["by_rule"])   # ...none carries the edge
    assert all(s["findings"]["drift"] == 0 for s in drift["by_rule"])
    assert [i for i in report.issues if i.category == "lifecycle-drift"] == []
    repo.close()


# --- TC-03-3: untyped vault ⇒ every denominator 0 ---------------------------

def test_tc_03_3_untyped_vault_all_zero(tmp_path: Path) -> None:
    # A cybos vault (⇒ BOTH checks are configured and DO run) whose pages carry no
    # rule-bound `$.type`. `concept` is a real class, but no drift/ontology rule binds
    # to it — the LIVE state (713 concepts, 0 examined) inside CI.
    # NOTE (grepped, not believed): cybos's `paths:` globs do NOT include `_concepts/**`,
    # so a top-level `_concepts/x.md` is never INDEXED — it would make this fixture pass
    # vacuously (the page isn't in `pages` at all). Nesting it under a globbed folder
    # (`facts/**/*.md` is RECURSIVE) is what actually indexes it with `$.type = concept`.
    repo, _root = build_cybos_vault(tmp_path, {
        "facts/_concepts/c.md": "---\ntype: concept\ntitle: C\n---\nb\n",
    }, vault_id="untypedv")
    assert repo._connect().execute(
        "SELECT COUNT(*) FROM pages WHERE vault_id='untypedv' "
        "AND json_extract(frontmatter_json,'$.type')='concept'").fetchone()[0] == 1
    denoms = run_all_checks_report(repo, vaults=["untypedv"]).denominators["untypedv"]
    assert denoms["lifecycle-drift"]["pages_examined"] == 0
    assert denoms["ontology-violation"]["edges_examined"] == 0
    assert denoms["ontology-violation"]["property_pages_examined"] == 0
    repo.close()


# --- TC-03-4: invariants, ∀ DECLARED rule (incl. the degenerate/skipped one) --

def test_tc_03_4_invariants_all_declared_rules(tmp_path: Path) -> None:
    repo, _root = build_health_vault(tmp_path)
    cfg = resolve_layout_config(_root)
    denoms = run_all_checks_report(repo, vaults=["hvault"]).denominators["hvault"]

    drift = denoms["lifecycle-drift"]
    assert len(drift["by_rule"]) == len(cfg.drift_rules)   # a REAL ∀: no rule is missing
    for stat in drift["by_rule"]:
        assert stat["findings"]["drift"] <= stat["matched"] <= drift["pages_examined"]

    ont = denoms["ontology-violation"]
    assert cfg.ontology is not None
    assert len(ont["by_rule"]) == len(cfg.ontology.edges) + len(cfg.ontology.properties)
    for stat in ont["by_rule"]:
        denom = (ont["edges_examined"] if stat["kind"] == "edge"
                 else ont["property_pages_examined"])
        # P-061-A: per (rule × KIND), never summed — ONE examined ref row can be BOTH a
        # domain and a range violation, so `domain + range` can exceed `matched` on
        # correct data. And never `total <= examined`: two rules may target one class.
        for count in stat["findings"].values():
            assert count <= stat["matched"], stat
        assert stat["matched"] <= denom, stat
    repo.close()


def test_tc_03_4_degenerate_rule_still_gets_a_rulestat(tmp_path: Path) -> None:
    """A hand-built drift rule with NEITHER `expect_status` nor `forbid_status` (bypassing
    the config load-gate) is `continue`d by the finder — but it STILL gets a RuleStat with
    a real `matched`. A rule that examined N pages and found nothing BECAUSE THE RULE IS
    DEGENERATE is precisely the state this task refuses to render as a silent green."""
    repo, root = build_health_vault(tmp_path)
    cfg = resolve_layout_config(root)
    degenerate = DriftRule(page_class="decision", edge="superseded-by",
                           expect_status=None, forbid_status=())
    cfg = dataclasses.replace(cfg, drift_rules=(degenerate,))
    issues, denom = check_lifecycle_drift_report(
        repo, "hvault", root, strict=False, config=cfg)
    assert issues == []                       # the rule can produce no finding...
    assert denom is not None
    assert denom["pages_examined"] == 8       # ...yet it examined the 8 decision pages
    assert len(denom["by_rule"]) == 1         # and it is PRESENT, not silently dropped
    stat = denom["by_rule"][0]
    # matched = decisions CARRYING `superseded-by`: dec-stale, dec-correct, dec-nostatus
    # (all three authored `superseded_by:`) + dec-old2, whose edge is the AUTO-DERIVED
    # INVERSE of dec-new's `supersedes` — the inverse is a real stored ref, so it counts.
    assert stat["matched"] == 4
    assert stat["findings"] == {"drift": 0}
    repo.close()


# --- TC-03-5: THE LIVE 8836-REF TRAP, pinned on the CI-GATING surface --------

def test_tc_03_5_mentioned_only_vault_on_the_ci_rail(tmp_path: Path, capsys) -> None:
    """The LIVE vault holds 8836 `page_entity_refs` rows — every one a `mentioned` body
    wikilink, none a declared ontology edge — and zero typed pages. `wiki-lint` reported
    `ontology-violation: 0`, which read as a clean bill of health on the surface that
    GATES CI. It examined nothing. Now it says so: `edges_examined == 0`."""
    # `concept` pages nested under a RECURSIVE cybos glob (`facts/**/*.md`) — the only way
    # a concept page is actually INDEXED under this layout (`paths:` has no `_concepts/**`
    # glob; a top-level one would leave `pages` empty and the fixture would prove nothing).
    files = {f"facts/_concepts/c{i}.md":
             f"---\ntype: concept\ntitle: C{i}\n---\nSee [[c{(i + 1) % 40}]] and "
             f"[[c{(i + 2) % 40}]] and [[c{(i + 3) % 40}]].\n"
             for i in range(40)}
    repo, _root = build_cybos_vault(tmp_path, files, vault_id="mentionsv")
    conn = repo._connect()
    ref_types = dict(conn.execute(
        "SELECT ref_type, COUNT(*) FROM page_entity_refs WHERE vault_id=? GROUP BY ref_type",
        ["mentionsv"]).fetchall())
    assert ref_types == {"mentioned": 120}     # the trap: 120 refs exist, ALL `mentioned`
    assert conn.execute("SELECT COUNT(*) FROM pages WHERE vault_id='mentionsv'"
                        ).fetchone()[0] == 40  # ...over 40 REAL indexed pages
    repo.close()

    db = str(tmp_path / "mentionsv.db")
    for argv in (["--vault", "mentionsv", "--db-path", db],
                 ["--vault", "mentionsv", "--strict", "--db-path", db]):
        _, env = _run_lint(capsys, argv)
        assert env["by_category"].get("ontology-violation", 0) == 0   # 0 issues, as before
        ont = env["denominators"]["mentionsv"]["ontology-violation"]
        assert ont["edges_examined"] == 0            # ...and NOW we know why: inert check
        assert ont["property_pages_examined"] == 0
        assert all(s["matched"] == 0 for s in ont["by_rule"])
        # the sibling on the same rail is equally inert, and equally honest about it
        assert env["denominators"]["mentionsv"]["lifecycle-drift"]["pages_examined"] == 0


# --- TC-03-6: BOTH no-ops preserved — no rules / no ontology ⇒ NO DAL call ---

def test_tc_03_6_no_ops_make_no_dal_call(tmp_path: Path, monkeypatch) -> None:
    # A karpathy vault ships NEITHER `drift_rules` NOR an `ontology:` block. Both checks
    # must short-circuit BEFORE touching the DAL (the pre-061 no-op contract), and the
    # envelope must carry NO key for the vault — "does not apply" ≠ "examined 0".
    root = tmp_path / "kvault"
    root.mkdir()  # no WIKI_SCHEMA.md → karpathy
    repo = SQLiteRepository(tmp_path / "kvault.db")
    repo.apply_schema()
    repo.register_vault(Vault(vault_id="kvault", name="kvault", root_path=root,
                              schema_version="2.0", registered_at=datetime(2026, 6, 16)))

    def _boom(*_a: object, **_k: object) -> None:
        raise AssertionError("DAL called for a check whose no-op should have fired")

    for name in ("find_lifecycle_drift", "find_lifecycle_drift_report",
                 "find_ontology_violations", "find_ontology_violations_report"):
        monkeypatch.setattr(SQLiteRepository, name, _boom)

    report = run_all_checks_report(repo, vaults=["kvault"])
    assert report.denominators == {}
    # the no-op holds at the check level too (direct callers bypass run_all_checks)
    assert check_lifecycle_drift_report(repo, "kvault", root, strict=True) == ([], None)
    assert check_ontology_violations_report(repo, "kvault", root, strict=True) == ([], None)
    assert check_lifecycle_drift(repo, "kvault", root, strict=True) == []
    assert check_ontology_violations(repo, "kvault", root, strict=True) == []
    repo.close()


# --- TC-03-7: back-compat — the pre-061 API is byte-identical ----------------

def test_tc_03_7_back_compat_list_returning_api(tmp_path: Path) -> None:
    repo, root = build_health_vault(tmp_path)
    cfg = resolve_layout_config(root)
    issues = run_all_checks(repo, vaults=["hvault"])          # signature UNCHANGED
    assert isinstance(issues, list)
    assert all(isinstance(i, LintIssue) for i in issues)
    assert issues == run_all_checks_report(repo, vaults=["hvault"]).issues
    # the two check wrappers keep their signatures AND their outputs
    assert check_lifecycle_drift(repo, "hvault", root, strict=False, config=cfg) == [
        i for i in issues if i.category == "lifecycle-drift"]
    assert check_ontology_violations(repo, "hvault", root, strict=False, config=cfg) == [
        i for i in issues if i.category == "ontology-violation"]
    repo.close()


def test_tc_03_7_benchmark_still_imports() -> None:
    # scripts/benchmark.py:217 calls run_all_checks(repo, vaults=[...]) — the one non-test,
    # non-CLI caller (`grep -rn "run_all_checks" scripts/`).
    import scripts.benchmark  # noqa: F401


# --- the CLI envelope: additive, non-gating ---------------------------------

def test_lint_envelope_additive_and_non_gating(tmp_path: Path, capsys) -> None:
    repo, _root = build_health_vault(tmp_path)
    repo.close()
    db = str(tmp_path / "h.db")
    rc, env = _run_lint(capsys, ["--vault", "hvault", "--db-path", db])
    # pre-061 keys still present and unchanged (additive-only contract)
    assert {"action", "vault", "total_issues", "by_category"} <= set(env)
    assert rc == 0 and env["by_category"]["lifecycle-drift"] == 4   # advisory → exit 0
    # ...and the denominators ride alongside, per-CHECK-keyed so the `pages_examined`
    # noun (drift's population) never collides with the ontology check's populations.
    denoms = env["denominators"]["hvault"]
    assert set(denoms) == {"lifecycle-drift", "ontology-violation"}
    assert "pages_examined" in denoms["lifecycle-drift"]
    assert "pages_examined" not in denoms["ontology-violation"]
    assert {"edges_examined", "property_pages_examined"} <= set(denoms["ontology-violation"])
    # denominators NEVER gate: --strict exit code still rides the ISSUES alone
    rc_strict, env_strict = _run_lint(capsys, ["--vault", "hvault", "--strict",
                                               "--db-path", db])
    assert rc_strict == 1
    assert env_strict["total_issues"] == env["total_issues"]
    assert env_strict["by_category"] == env["by_category"]
