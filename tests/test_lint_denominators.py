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
import inspect
import json
from datetime import datetime
from pathlib import Path

from scripts.wiki_index.layout_config import resolve_layout_config
from scripts.wiki_index.lint import (
    LintIssue,
    LintReport,
    check_lifecycle_drift,
    check_lifecycle_drift_report,
    check_ontology_violations,
    check_ontology_violations_report,
    render_json_sidecar,
    render_markdown_report,
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

def test_h1_sink_census_is_complete(tmp_path: Path) -> None:
    """THE CENSUS THE FIRST CUT FORGOT — grepped, not believed. `wiki-lint` has THREE
    output sinks; TASK 061 fed the denominators to exactly one of them, so `--report`
    kept writing `✅ Healthy. No issues found.` from a run that examined nothing.

    This pins the census itself: if a FOURTH sink is ever added to `wiki_lint.main`, this
    test fails and forces the author to decide whether it, too, must carry the
    denominators — rather than letting the next false green ship silently.

    ★ IT FIRED, and here is the decision it forced. DF-074-4 added a fourth sink: the
    `VAULT_NOT_FOUND` refusal (`--vault <typo>` used to report `{"total_issues": 0}` at exit 0
    — a clean bill of health for a vault that does not exist, on the CI-gate surface).
    **It deliberately carries NO denominators**, and that is the opposite of a false green:
    nothing was examined *and the envelope says so with an `error` key*, which is precisely
    what a denominator exists to prevent you from having to infer. Same stance `wiki-health`
    documents for its three error envelopes. So the census now has two classes, asserted
    separately — REPORT sinks must carry the payload, refusal sinks must not pretend to."""
    src = Path("scripts/wiki_skills/wiki_lint.py").read_text(encoding="utf-8")
    sinks = [ln.strip() for ln in src.splitlines()
             if ".write_text(" in ln or ln.strip().startswith("return emit(")]
    refusals = [s for s in sinks if '"error"' in s]
    reports = [s for s in sinks if s not in refusals]
    assert len(sinks) == 4, sinks       # 3 report sinks + 1 refusal
    assert len(reports) == 3, reports   # stdout envelope · --report · --json-sidecar
    assert len(refusals) == 1, refusals  # VAULT_NOT_FOUND (DF-074-4)
    # ...and all three REPORT sinks are fed the REPORT (or its `.denominators`), never the bare list.
    assert "render_markdown_report(report)" in src
    assert "render_json_sidecar(report)" in src
    assert '"denominators": report.denominators' in src
    # The refusal must NOT fake a report shape — no denominators, no total_issues.
    assert "VAULT_NOT_FOUND" in refusals[0] and "denominators" not in refusals[0]


def test_h1_the_sidecar_READER_contract_is_not_stale() -> None:
    """THE CENSUS THE H1 FIX ITSELF FORGOT — the fractal, one turn deeper.

    H1 censused the three output SINKS and changed the sidecar's SHAPE (array → object),
    but never censused the sidecar's **READERS**. `grep -rn "json_sidecar"` found five:
    two test modules, and — the one that matters — `skills/wiki-lint/SKILL.md`, which told
    every orchestrator the sidecar is "a **bare JSON array** (NOT wrapped in any object)".
    An agent following that doc would `json.loads(...)` and iterate a dict's KEYS. The code
    was honest and the CONTRACT was a lie: exactly this task's disease (a mechanism
    asserting it covers a surface it never enumerated), relocated from the numbers to the
    docs. Enumerating a shape's sinks is not enumerating its readers.

    Pins the LLM-facing contract against re-drift, since it is the surface no test would
    otherwise touch and no type-checker can see."""
    skill = Path("skills/wiki-lint/SKILL.md").read_text(encoding="utf-8")
    # the stale claim, dead — in any spacing/emphasis (it read: "a **bare JSON array**").
    assert "bare JSON array" not in skill
    assert "ONLY in the `--json-sidecar` array" not in skill
    # ...and the keys an orchestrator must now parse are all DOCUMENTED, by name.
    for key in ("issues", "denominators", "vacuous_checks", "vacuous_kinds"):
        assert f"`{key}`" in skill or f'"{key}"' in skill, key
    # the migration is stated (one key), not left for the reader to discover at runtime.
    assert 'data["issues"]' in skill


def test_m3_the_new_KEY_has_readers_in_BOTH_llm_facing_contracts() -> None:
    """M-3 (061 FIX-LOOP iteration-2) — THE THESIS RECURRING INSIDE THE FIX FOR THE THESIS.

    The H1 loop wrote `test_h1_the_sidecar_READER_contract_is_not_stale` ABOVE, on the
    lesson that *enumerating a shape's SINKS is not enumerating its READERS* — and then, in
    the same loop, M3 added `matched_by_kind` to FOUR envelopes and `grep -rn
    "matched_by_kind" skills/` returned **ZERO**. `skills/wiki-health/SKILL.md` still
    documented the pre-M3 `by_rule` shape AND the SUPERSEDED, weaker invariant
    `findings[k] <= matched <= <denominator>` — so an orchestrator following the shipped
    contract computed health from `matched`, **the number M3 had just PROVEN is not
    judgeable**, and reconstructed the false green from a correct envelope.

    A key with no reader is not a fix; it is a number the machine emits into a void. This
    test is the census that was missing: every key the vacuity CONTRACT depends on must be
    named in the docs an LLM actually reads.

    MUTATION BAR: delete `matched_by_kind` from either SKILL.md and this fails."""
    lint_skill = Path("skills/wiki-lint/SKILL.md").read_text(encoding="utf-8")
    health_skill = Path("skills/wiki-health/SKILL.md").read_text(encoding="utf-8")

    for name, doc in (("wiki-lint", lint_skill), ("wiki-health", health_skill)):
        assert "matched_by_kind" in doc, f"{name}: the judgeable-population key has NO READER"
        assert "vacuous_kinds" in doc, f"{name}: the vacuity verdict has NO READER"
        # the SUPERSEDED invariant must be GONE — it is the one that rebuilds the false green
        assert "findings[k] ≤ matched ≤" not in doc, f"{name}: superseded invariant still shipped"
        assert "findings[k] <= matched <=" not in doc, name
        # ...and the honest one, which threads matched_by_kind, must be stated.
        assert "findings[k] ≤ matched_by_kind[k] ≤ matched" in doc, name

    # wiki-health's own envelope keys are documented by name (its `note`/`vacuous_*` contract
    # is what M-2 fixed; a reader that never learns the key cannot honour it).
    assert "vacuous_populations" in health_skill


def test_h1_markdown_report_qualifies_a_vacuous_green(tmp_path: Path, capsys) -> None:
    """H1 — the literal false green, in the HUMAN-FACING artifact. On the LIVE vault
    `wiki-lint --report out.md` wrote `# Wiki Lint Report` + `✅ Healthy. No issues found.`
    from a run whose `ontology-violation` check examined **0 of 8836 refs**. The markdown
    sink took `issues` only, so it could not have known better."""
    files = {f"facts/_concepts/c{i}.md":
             f"---\ntype: concept\ntitle: C{i}\n---\nSee [[c{(i + 1) % 5}]].\n"
             for i in range(5)}
    repo, _root = build_cybos_vault(tmp_path, files, vault_id="vacuousmd")
    # ANTI-VACUITY GUARD (an earlier bead shipped a vacuity test that was itself vacuous,
    # asserting over an EMPTY table): the pages ARE indexed, and lint finds ZERO issues —
    # so the pre-fix report really would have said "Healthy".
    assert repo._connect().execute(
        "SELECT COUNT(*) FROM pages WHERE vault_id='vacuousmd'").fetchone()[0] == 5
    assert run_all_checks(repo, vaults=["vacuousmd"]) == []
    repo.close()

    out = tmp_path / "report.md"
    rc, _env = _run_lint(capsys, ["--vault", "vacuousmd", "--report", str(out),
                                  "--db-path", str(tmp_path / "vacuousmd.db")])
    text = out.read_text()
    assert rc == 0                                   # advisory, as ever — no gating change
    assert "✅ Healthy" not in text                   # THE false green, killed at the source
    assert "NOT a clean bill of health" in text
    # every zero-denominator population is NAMED (3 of them: drift pages, ontology edges,
    # ontology property pages) — not a vague "some checks were inert".
    for population in ("pages_examined", "edges_examined", "property_pages_examined"):
        assert f"`{population}`" in text
    assert "ontology-violation" in text and "lifecycle-drift" in text
    assert "## What was examined" in text            # the positive half of the same honesty


def test_h1_markdown_healthy_only_when_something_was_examined(tmp_path: Path, capsys) -> None:
    """The green must survive where it is EARNED — otherwise the fix is just a new
    dishonesty (crying wolf on a real clean bill of health). A cybos vault with typed
    pages, a real declared edge, in-enum statuses and no lint issues: every denominator is
    NON-zero, so `✅ Healthy` is printed — and the table states what backs it."""
    repo, _root = build_cybos_vault(tmp_path, {
        "decisions/d-new.md":
            "---\ntype: decision\ntitle: D New\nstatus: accepted\n---\nbody\n",
        "decisions/d-old.md":
            "---\ntype: decision\ntitle: D Old\nstatus: superseded\n"
            "superseded_by: [[d-new]]\n---\nbody\n",
    }, vault_id="cleanv")
    assert run_all_checks(repo, vaults=["cleanv"]) == []      # a genuinely clean vault
    repo.close()

    out = tmp_path / "clean.md"
    _rc, env = _run_lint(capsys, ["--vault", "cleanv", "--report", str(out),
                                  "--db-path", str(tmp_path / "cleanv.db")])
    denoms = env["denominators"]["cleanv"]
    # the guard: this vault really did examine things (else the assertion below is vacuous)
    assert denoms["lifecycle-drift"]["pages_examined"] == 2
    assert denoms["ontology-violation"]["edges_examined"] == 1      # the derived `supersedes`
    assert denoms["ontology-violation"]["property_pages_examined"] == 2
    text = out.read_text()
    assert "✅ Healthy. No issues found." in text
    assert "NOT a clean bill of health" not in text
    assert "| cleanv | ontology-violation | `edges_examined` | 1 |" in text


def test_h1_json_sidecar_carries_the_denominators(tmp_path: Path, capsys) -> None:
    """The sidecar travels ALONE (a CI artifact, read without the stdout envelope beside
    it), so a bare `[]` there is the same false green. SHAPE CHANGE, stated: the sidecar is
    now an OBJECT whose `issues` key holds the pre-061 array VERBATIM — a bare array is
    structurally incapable of carrying a denominator, and emitting the vacuity as a
    synthetic ISSUE is forbidden by the spec (denominators "never become issues")."""
    repo, _root = build_health_vault(tmp_path)
    repo.close()
    side = tmp_path / "issues.json"
    _rc, env = _run_lint(capsys, ["--vault", "hvault", "--json-sidecar", str(side),
                                  "--db-path", str(tmp_path / "h.db")])
    data = json.loads(side.read_text())
    assert set(data) == {"issues", "denominators", "vacuous_checks", "vacuous_kinds"}
    # `issues` IS the pre-061 array of LintIssue dicts — the DAL's own `run_all_checks`
    # (still list-returning; `benchmark.py` depends on it) is the oracle for its contents.
    repo2 = SQLiteRepository(tmp_path / "h.db")
    oracle = run_all_checks(repo2, vaults=["hvault"])
    repo2.close()
    assert [i["category"] for i in data["issues"]] == [i.category for i in oracle]
    assert len(data["issues"]) == env["total_issues"] > 0
    assert data["denominators"] == env["denominators"]    # same payload as the stdout envelope
    assert data["vacuous_checks"] == []          # this vault examined a real population
    # ...and the STDOUT envelope announces the same two verdicts (M-1: the sink that
    # carried the numbers used to announce nothing at all).
    assert env["vacuous_checks"] == data["vacuous_checks"]
    assert env["vacuous_kinds"] == data["vacuous_kinds"]


def test_h1_json_sidecar_vacuous_checks_are_machine_visible(tmp_path: Path, capsys) -> None:
    repo, _root = build_cybos_vault(tmp_path, {
        "facts/_concepts/c.md": "---\ntype: concept\ntitle: C\n---\nb\n",
    }, vault_id="vacuousjs")
    assert run_all_checks(repo, vaults=["vacuousjs"]) == []    # zero issues → `[]` pre-fix
    repo.close()
    side = tmp_path / "s.json"
    _run_lint(capsys, ["--vault", "vacuousjs", "--json-sidecar", str(side),
                       "--db-path", str(tmp_path / "vacuousjs.db")])
    data = json.loads(side.read_text())
    assert data["issues"] == []                  # ...and `[]` is ALL the pre-061 file said
    assert {(v["check"], v["population"]) for v in data["vacuous_checks"]} == {
        ("lifecycle-drift", "pages_examined"),
        ("ontology-violation", "edges_examined"),
        ("ontology-violation", "property_pages_examined"),
    }
    assert all(v["vault"] == "vacuousjs" for v in data["vacuous_checks"])


def test_l1_the_list_taking_renderer_overload_is_GONE(tmp_path: Path) -> None:
    """L-1 (061 FIX-LOOP iteration-2) — the `list[LintIssue]` overload was a LOADED GUN.

    It survived H1 as "library back-compat", with ZERO production callers — and a list is
    structurally incapable of carrying a denominator, so that form printed the EXACT
    pre-fix false green (`✅ Healthy. No issues found.` over a run that examined nothing).
    Any new sink in any module could have picked it up with **mypy silent and no test
    failing**: H1's own sink census only greps `wiki_lint.py` for `.write_text(`/`return
    emit(`, so a sink routed through a helper is invisible to it.

    Both renderers now take `LintReport` ONLY. The false green is UNREPRESENTABLE rather
    than merely unreached — the M6 precedent, applied to the module M6 was written for.
    A bare `{}` denominators map still renders an HONEST green: it means *no config-driven
    check applies to any of these vaults*, which is exactly what `_split`'s docstring
    insisted must never be collapsed with "unknown" (L-4) — and now cannot be, because the
    "unknown" state no longer exists."""
    from scripts.wiki_index.lint import render_json_sidecar, render_markdown_report

    issue = LintIssue(category="orphan-link", severity="warning", vault_id="v",
                      page_slug="p", details={"target": "t"})
    # The disease, at the type level: a bare list no longer type-checks...
    sig = inspect.signature(render_markdown_report).parameters["report"].annotation
    assert "list" not in str(sig) and "LintReport" in str(sig)
    sig_s = inspect.signature(render_json_sidecar).parameters["report"].annotation
    assert "list" not in str(sig_s) and "LintReport" in str(sig_s)
    src = Path("scripts/wiki_index/lint.py").read_text(encoding="utf-8")
    assert "def _split(" not in src          # the None-vs-{} normalizer has no reason to exist
    # ...and `{}` (no config-driven check applies) is still an honest, UNqualified green.
    honest = LintReport(issues=[], denominators={})
    assert render_markdown_report(honest) == (
        "# Wiki Lint Report\n\n✅ Healthy. No issues found.\n")
    assert json.loads(render_json_sidecar(honest)) == {
        "issues": [], "denominators": {}, "vacuous_checks": [], "vacuous_kinds": []}
    # ...and the issue body is unchanged for the report form.
    md = render_markdown_report(LintReport(issues=[issue], denominators={}))
    assert "**1 issue(s)** across 1 categories." in md and "## orphan-link (1)" in md
    assert json.loads(render_json_sidecar(
        LintReport(issues=[issue], denominators={})))["issues"] == [
        {"category": "orphan-link", "severity": "warning", "vault_id": "v",
         "page_slug": "p", "details": {"target": "t"}}]


def test_h1_denominator_rows_are_derived_not_enumerated(tmp_path: Path) -> None:
    """The renderer must NOT hard-code the three known denominator nouns: TASK 062 adds
    rules and may add a population, and a renderer that enumerates its nouns is this task's
    fractal, one surface over. `_denominator_rows` derives them (every int-valued key in a
    check payload IS a population), so a NEW noun renders with zero renderer code."""
    from scripts.wiki_index.lint import (
        LintReport,
        _denominator_rows,
        render_json_sidecar,
        render_markdown_report,
    )
    denoms: dict = {"v": {"future-check": {
        "brand_new_noun_examined": 0, "another_noun_examined": 7,
        # L-3 (061 FIX-LOOP iteration-2): a NON-population int in the same payload. TASK 062
        # "adds rules" — the moment a check reports `{"rules": 0}` (a count of RULES, not of
        # examined rows), the old "every int is a population" heuristic FABRICATED a "NOT a
        # clean bill of health" alarm out of a fully-examined vault. A false RED is not the
        # safe direction of this bug; it is the one that gets the alarm ignored. The
        # population contract is now the `_examined` SUFFIX — still derived, never
        # enumerated, but no longer credulous.
        "rules": 0,
        "by_rule": [{"matched": 1}]}}}
    assert _denominator_rows(denoms) == [    # `by_rule` (list) and `rules` (not a population)
        ("v", "future-check", "another_noun_examined", 7),   # both drop out
        ("v", "future-check", "brand_new_noun_examined", 0)]
    # ...and BOTH sinks render the never-before-seen noun with zero renderer code:
    md = render_markdown_report(LintReport(issues=[], denominators=denoms))
    assert "`brand_new_noun_examined`" in md and "NOT a clean bill of health" in md
    assert "| v | future-check | `another_noun_examined` | 7 |" in md
    assert "`rules`" not in md                   # the non-population never became an alarm
    side = json.loads(render_json_sidecar(LintReport(issues=[], denominators=denoms)))
    assert side["vacuous_checks"] == [
        {"vault": "v", "check": "future-check", "population": "brand_new_noun_examined"}]
    assert side["vacuous_kinds"] == []          # `matched: 1` with no `matched_by_kind`


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


# =============================================================================
# 061 FIX-LOOP iteration-2 — M-1: H1 and M3 were never COMPOSED
# =============================================================================

# The rule that MATCHES rows it cannot JUDGE, with **zero lint issues** beside it. `uses`
# from a `workflow` is in the declared domain, and the target RESOLVES (so no orphan-link
# fires — that is the whole point: the ghost-link fixture in test_health_denominators can
# NEVER reach the green, because a dangling link IS an issue) but the target is UNTYPED, so
# `tgt_type` is NULL and the RANGE half can judge NOT ONE of these rows.
#
# Pre-fix this vault printed `✅ Healthy. No issues found.` and shipped `"vacuous_checks":
# []`, while `by_rule` — the list that holds `matched_by_kind`, the number M3 added
# precisely to IDENTIFY this state — was dropped by `_denominator_rows` (a LIST, not an
# int) and rendered on NO surface at all. The number that identifies a false green was not
# read by the mechanism that announces false greens.
_UNJUDGEABLE_FILES = {
    "workflows/wf-a.md":
        "---\ntype: workflow\ntitle: WF A\nstatus: active\nuses: [[tool-x]]\n---\nb\n",
    # an INDEXED page (so the link resolves) with NO `type:` in frontmatter and a path that
    # implies none — the range check's target type is NULL.
    "tools/tool-x.md": "---\ntitle: Tool X\n---\nno type field at all\n",
}


def _unjudgeable_report(tmp_path: Path):
    repo, _root = build_cybos_vault(tmp_path, _UNJUDGEABLE_FILES, vault_id="unjudge")
    report = run_all_checks_report(repo, vaults=["unjudge"])
    repo.close()
    return report


def test_m1_the_anti_vacuity_guard_this_fixture_is_the_state_it_claims(
        tmp_path: Path) -> None:
    """THE ANTI-VACUITY GUARD — the fixture must actually BE the state, or every assertion
    below is itself a vacuous check (this task's disease, in its own test file)."""
    report = _unjudgeable_report(tmp_path)
    ont = report.denominators["unjudge"]["ontology-violation"]
    uses = next(r for r in ont["by_rule"] if r["ref"] == "uses")
    assert uses["matched"] == 1                        # a row WAS examined by the rule...
    assert uses["matched_by_kind"] == {"domain": 1, "range": 0}   # ...`range` judged NONE
    assert uses["findings"] == {"domain": 0, "range": 0}          # ...and "found" nothing
    assert ont["edges_examined"] == 1 and ont["property_pages_examined"] >= 1  # NOT vacuous
    assert report.issues == []          # ...and NOTHING else flags this vault. Green, pre-fix.


def test_m1_matched_by_kind_is_READ_by_the_mechanism_that_announces_false_greens(
        tmp_path: Path) -> None:
    """M-1 — the composition H1 and M3 never made. MUTATION BAR: revert either
    `derive_vacuous_kinds` or its use in the renderer and this test fails, because the
    report goes back to printing the unqualified green over `range: 0`."""
    report = _unjudgeable_report(tmp_path)
    md = render_markdown_report(report)
    assert "✅ Healthy. No issues found." not in md          # THE false green, dead
    assert "NOT a clean bill of health" in md
    assert "`range`" in md and "could judge **0**" in md     # ...and it names WHICH half
    side = json.loads(render_json_sidecar(report))
    assert side["issues"] == [] and side["vacuous_checks"] == []   # both empty, pre-fix...
    assert side["vacuous_kinds"] == [{                             # ...and THIS is the tell
        "vault": "unjudge", "check": "ontology-violation",
        "class": "", "kind": "edge", "ref": "uses", "finding_kind": "range"}]


def test_m1_by_rule_is_RENDERED_in_the_markdown_report(tmp_path: Path) -> None:
    """M-1's other half: the markdown report is the ONLY surface a human reads, and it
    showed not a single per-rule number — `by_rule` dropped out of `_denominator_rows`
    because it is a LIST. A rule's judgeable population is now a column."""
    report = _unjudgeable_report(tmp_path)
    md = render_markdown_report(report)
    assert "## What each rule could judge" in md
    assert "| vault | check | rule | kind | matched | judgeable | found |" in md
    # the lying row, with its judgeable population flagged:
    assert "| unjudge | ontology-violation | `edge:uses` | range | 1 | 0 ⚠ | 0 |" in md
    assert "| unjudge | ontology-violation | `edge:uses` | domain | 1 | 1 | 0 |" in md


def test_m1_openly_empty_rules_are_DISCLOSED_but_do_not_cry_wolf(tmp_path: Path) -> None:
    """THE STATED BOUNDARY (a boundary that is stated is honest; one that is merely true is
    the disease). A rule with `matched == 0` matched NOTHING — its `0` findings are
    uninformative, but OPENLY so. cybos declares 18 rules and a healthy vault exercises two
    or three, so alarming on every unused rule would fire the headline on EVERY vault: a
    permanent RED is exactly as uninformative as the permanent green this task exists to
    kill, and it is the one that trains the operator to ignore the alarm.

    So: openly-empty (`matched == 0`) → DISCLOSED in the table, no alarm.
        hidden-empty (`matched > 0`, kind judges 0) → ALARMED. That is `vacuous_rule_kinds`."""
    repo, _root = build_cybos_vault(tmp_path, {
        "agents/ag-1.md": "---\ntype: agent\ntitle: Ag\nstatus: active\nowns: [[wf-1]]\n---\nb\n",
        "workflows/wf-1.md": "---\ntype: workflow\ntitle: WF\nstatus: active\n---\nb\n",
    }, vault_id="cleanv")
    report = run_all_checks_report(repo, vaults=["cleanv"])
    repo.close()
    ont = report.denominators["cleanv"]["ontology-violation"]
    unused = [r for r in ont["by_rule"] if r["matched"] == 0]
    assert len(unused) >= 10          # census: most of cybos's 18 rules are unused here...
    md = render_markdown_report(report)
    assert render_json_sidecar(report) and "✅ Healthy. No issues found." in md  # ...still green
    assert "NOT a clean bill of health" not in md
    # ...but every unused rule is VISIBLE, flagged, in the table — never silently absent.
    assert "| cleanv | ontology-violation | `edge:implements` | domain | 0 | 0 ⚠ | 0 |" in md
