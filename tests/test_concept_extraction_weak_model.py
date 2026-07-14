"""TASK 066 — THE GATE. The weak-model floor becomes ENFORCEABLE.

Today the "9/11 on Haiku" lives in a README. Nobody can reproduce it, nothing goes red when
`SKILL.md` changes, and every future edit to that file is **believed rather than measured**.
This module is what turns that number into a build failure.

It is **offline and deterministic**: it grades a **recorded artifact**
(`skills/concept-extraction/evals/reports/*.json`) through the **REAL** validators plus each
fixture's `expect` census and `forbidden` list. No network, no API key, no flake.

★★ AND IT REFUSES A STALE RECORDING. `SKILL.md` **IS the artifact under test** — so without a
hash stamp, a contributor could rewrite the skill and this gate would keep grading a recording
of the *old* one: **green forever, measuring nothing.** The staleness check is therefore not a
nicety; it is the difference between a gate and a decoration. It is mutation-tested.

★ THE FLOOR IS PER-FIXTURE, NEVER A SCALAR. "≥ 9 of 11" gets *easier* as fixtures are added
(9/12 is weaker than 9/11 and clears the same bar), and it hides the **fixture × layout** axis.
The rule is: **no fixture that PASSES at baseline may FAIL.**
"""

from __future__ import annotations

import hashlib
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
EVALS = REPO / "skills" / "concept-extraction" / "evals"
SKILL = EVALS.parent / "SKILL.md"
REPORTS = EVALS / "reports"
BASELINE = EVALS / "baseline.json"

sys.path.insert(0, str(EVALS))
import harness  # type: ignore[import-not-found]  # noqa: E402

from tests.test_concept_extraction_evals import (  # noqa: E402
    _grading,
    _payload,
    _validate,
    _vault,
)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _artifacts() -> list[Path]:
    return sorted(REPORTS.glob("*.json")) if REPORTS.is_dir() else []


def _load_artifact() -> dict[str, Any]:
    found = _artifacts()
    assert found, (
        "no recorded weak-model run exists. The floor is UNENFORCEABLE until one does — "
        "run `skills/concept-extraction/evals/harness.py build` per fixture, then `record`.")
    # newest by filename (model-date); one artifact is the live baseline
    data: dict[str, Any] = json.loads(found[-1].read_text(encoding="utf-8"))
    return data


# --------------------------------------------------------------------------- #
# ★ the staleness refusal — the difference between a gate and a decoration
# --------------------------------------------------------------------------- #


def test_the_artifact_is_not_STALE() -> None:
    """★★ THE LOAD-BEARING TEST.

    `SKILL.md` IS the thing under test. If the recording predates the current skill, every
    verdict below is about a skill nobody runs — and the suite would be **green forever while
    measuring nothing.**

    MUTATION (EXECUTED): touch one byte of `SKILL.md` ⇒ this goes RED with "re-run the harness".
    """
    art = _load_artifact()
    assert art["skill_sha256"] == _sha(SKILL), (
        "THE SKILL HAS CHANGED SINCE THIS RECORDING — re-run the harness and commit a new "
        "artifact. Grading a stale recording is not a measurement.")

    for name, rec in art["fixtures"].items():
        f = EVALS / name
        assert rec["input_sha256"] == _sha(f / "input.md"), f"{name}: input.md changed"
        assert rec["grading_sha256"] == _sha(f / "grading.json"), f"{name}: grading changed"


def test_the_artifact_is_STAMPED_with_everything_the_gate_needs() -> None:
    """A stamp the gate does not check is a stamp that is not a stamp."""
    art = _load_artifact()
    for key in ("schema", "model", "temperature", "k", "layout", "skill_sha256", "fixtures"):
        assert key in art, f"the artifact carries no {key!r}"
    # ⚠️ STATED BOUNDARY (and the spec asked for something the runner CANNOT do).
    # TASK 066 v3 pinned `temperature = 0`. The runner is the ORCHESTRATOR (Decision-17 —
    # no SDK, by requirement), and the orchestrator's agent interface EXPOSES NO TEMPERATURE
    # KNOB. So temperature is RECORDED (`null` = "the orchestrator's default"), never claimed.
    # Writing `0` into the artifact would be recording a setting nobody applied — the exact
    # dishonesty this task exists to stop.
    #
    # The real mitigation for a stochastic model is therefore K and the MAJORITY, not a knob:
    assert "temperature" in art, "temperature must be RECORDED, whatever it was"
    assert art["k"] >= 3, "K < 3 cannot support a per-fixture majority — and K IS the mitigation"
    assert art["layout"] == harness.BASELINE_LAYOUT
    assert set(art["fixtures"]) == {f.name for f in harness.fixtures()}, (
        "the artifact's fixture set disagrees with the eval directory — a fixture was added or "
        "removed since the recording, and the census below would be over the wrong population")


def test_the_H6_sentinel_in_the_harness_matches_the_SKILL() -> None:
    """The harness COPIES the H-6 wrapper (it exists only as a template in `SKILL.md`; there is
    no function to call). A copy with no gate is a copy that drifts — and a harness that wraps
    the body differently from the way the rail teaches is measuring a prompt the rail never
    sends."""
    text = SKILL.read_text(encoding="utf-8")
    for marker in ("<<<BEGIN-SOURCE>>>", "<<<END-SOURCE>>>", "UNTRUSTED DATA"):
        assert marker in text, f"the SKILL no longer teaches {marker!r}"
        assert marker in harness.H6_SENTINEL, f"the harness dropped {marker!r}"


# --------------------------------------------------------------------------- #
# the grading — through the REAL validators
# --------------------------------------------------------------------------- #


def _grade_run(
    fixture: Path, candidates: list[dict[str, Any]] | None, tmp_path: Path
) -> dict[str, Any]:
    """One model output → a verdict. Uses the SAME validators + census + forbidden list the
    static eval uses; nothing is graded by eye."""
    grading = _grading(fixture)
    if candidates is None:
        return {"ok": False, "why": "no output recorded", "forbidden": 0}

    layout = harness.BASELINE_LAYOUT
    root = tmp_path / fixture.name
    try:
        config, source_path, known = _vault(root, layout, fixture)
        created, mentions, _warn = _validate(
            candidates, fixture, root, config, source_path, known)
    except Exception as exc:                       # a refusal IS a verdict
        return {"ok": False, "why": f"{type(exc).__name__}: {exc}", "forbidden": 0}

    # ★ the FORBIDDEN list — the half that catches the TRADE (junk bought with recall)
    forbid = {unicodedata.normalize("NFC", str(x)).casefold()
              for x in grading.get("forbidden", [])}
    emitted = [c for c in candidates
               if unicodedata.normalize("NFC", str(c.get("name", ""))).casefold() in forbid
               or unicodedata.normalize("NFC", str(c.get("slug", ""))).casefold() in forbid]

    # ★ the CENSUS — the half that catches the DROP. Nothing else can see it.
    expect = grading.get("expect", {})
    want = int(expect.get("concept", 0)) + sum(
        int(v) for k, v in expect.items() if k != "concept")
    got = len(created) + len(mentions)

    ok = (got == want) and not emitted
    return {
        "ok": ok, "expected": want, "got": got,
        "forbidden": len(emitted),
        "forbidden_names": [c.get("name") for c in emitted],
        "why": "" if ok else (
            f"census {got}≠{want}" if got != want else "emitted a FORBIDDEN name"),
    }


def _verdicts(tmp_path: Path) -> dict[str, dict[str, Any]]:
    """Per-fixture MAJORITY over the K recorded runs. A weak model is stochastic; a single run
    is an anecdote."""
    art = _load_artifact()
    out: dict[str, dict[str, Any]] = {}
    for name, rec in art["fixtures"].items():
        runs = [_grade_run(EVALS / name, r, tmp_path / f"r{i}")
                for i, r in enumerate(rec["runs"])]
        passes = sum(1 for r in runs if r["ok"])
        out[name] = {
            "pass": passes * 2 > len(runs),            # strict majority
            "passes": passes, "k": len(runs),
            "forbidden": max((r["forbidden"] for r in runs), default=0),
            "runs": runs,
        }
    return out


# --------------------------------------------------------------------------- #
# ★★ THE PROPERTY — a CONJUNCTION, and neither half is a scalar floor
# --------------------------------------------------------------------------- #


def test_THE_PROPERTY_no_passing_fixture_may_regress_and_no_junk_may_be_traded_for_recall(
    tmp_path: Path,
) -> None:
    """★★ `(no fixture that PASSES at baseline may FAIL)` **AND** `(forbidden ≤ baseline)`.

    *The first half catches REGRESSION. The second catches the TRADE.*

    This SKILL's history is **three edits, three precision/recall trades** (7/11 → 6/11 → 9/11).
    A fix that buys recall by emitting junk would sail through a floor-only gate — which is why
    the floor alone was never enough.

    **Neither half is a scalar**, so neither gets easier when the fixture set grows: "≥ 9" is
    satisfied by 9/12, which is *weaker* than 9/11.
    """
    assert BASELINE.is_file(), (
        "no baseline.json — the floor cannot be enforced against a number that does not exist")
    base: dict[str, Any] = json.loads(BASELINE.read_text(encoding="utf-8"))
    now = _verdicts(tmp_path)

    regressed = [n for n, b in base["fixtures"].items()
                 if b["pass"] and not now.get(n, {}).get("pass")]
    assert not regressed, (
        f"REGRESSION — these fixtures passed at baseline and now fail: {regressed}. "
        f"Details: { {n: now[n]['runs'] for n in regressed} }")

    traded = [n for n, v in now.items()
              if v["forbidden"] > base["fixtures"].get(n, {}).get("forbidden", 0)]
    assert not traded, (
        f"THE TRADE — these fixtures now emit MORE forbidden names than at baseline: {traded}. "
        f"Recall bought with junk is not an improvement.")


def test_the_baseline_is_recorded_HONESTLY_three_ways(tmp_path: Path) -> None:
    """★ The score is reported THREE ways, never as one number.

    **Fixture 08's entire six-key answer is printed in `SKILL.md`** (name, slug, definition AND
    source_quote). A pass there is not evidence of anything. Reporting a single "9/11" hides
    that — so the CLEAN subset is scored separately, and it is the only number that measures the
    skill rather than the prompt's memory of the answer.
    """
    base: dict[str, Any] = json.loads(BASELINE.read_text(encoding="utf-8"))
    for key in ("overall", "clean", "contaminated"):
        assert key in base["score"], f"the baseline does not report `{key}`"
    assert "forbidden_total" in base["score"], (
        "the baseline must record its FORBIDDEN count — it is >= 1, not the 0 the README "
        "claims, and the property's second half has nothing to improve against without it")
    assert set(base["clean_fixtures"]), "the clean subset is empty — the census never ran"


# --------------------------------------------------------------------------- #
# ★★ THE CONTAMINATION CENSUS — the reason "9/11" cannot be read as a score
# --------------------------------------------------------------------------- #


def _contamination() -> dict[str, list[str]]:
    """Which of each fixture's EXPECTED names are printed verbatim in `SKILL.md`."""
    skill = unicodedata.normalize("NFC", SKILL.read_text(encoding="utf-8")).casefold()
    out: dict[str, list[str]] = {}
    for f in harness.fixtures():
        expected = _payload(f, "expected")
        out[f.name] = [
            str(c["name"]) for c in expected
            if unicodedata.normalize("NFC", str(c["name"])).casefold() in skill
        ]
    return out


def test_the_CONTAMINATION_CENSUS_is_asserted_so_it_cannot_silently_grow() -> None:
    """★★ THE FINDING THAT DECIDED THIS TASK.

    A teaching SKILL legitimately shares vocabulary with same-domain fixtures — so *some*
    overlap is fine, and the defect was never the overlap. **The defect was asserting the
    overlap was LOCAL to one fixture, and then building an anti-overfit remedy on that
    assertion.**

    The census, RUN:

      * **9 of 19** expected names are printed in `SKILL.md`.
      * Fixture **08** — whose ONE JOB is *"derive the slug from the name with the layout's
        strategy"* — has **its name AND its exact expected slug printed in the SKILL** as the
        worked example of that very derivation (`Проскальзывание` → `proskalzyvanie`). **It
        passes at baseline.** That pass measures *"can the model copy the example"*, not *"can
        it derive a slug."*
        ⚠️ The first draft of this docstring said 08 leaks *"the entire candidate — name, slug,
        definition and source_quote."* **That was repeated from a review and never checked.**
        Measured: the definition and the quote are NOT in the SKILL. The claim is corrected
        here rather than quietly dropped — an over-stated finding is as damaging as a missed
        one, and this file exists because a number was believed instead of measured.
      * Fixture **09** carries BOTH expected names, plus an explicit *"And extract BOTH."*
        **And the model fails it anyway** — which is what refuted the entire class of
        SKILL-side fixes: the answer is in the prompt and the model still does not produce it.

    So the score is reported THREE ways, and the CLEAN subset is the only one that measures the
    skill rather than the prompt's memory of the answer.

    This test freezes the census. It cannot silently grow — an edit to `SKILL.md` that prints
    one more expected name turns this RED, and that is the point.
    """
    census = _contamination()
    total = sum(len(v) for v in census.values())
    n_expected = sum(len(_payload(f, "expected")) for f in harness.fixtures())

    assert (total, n_expected) == (9, 19), (
        f"the contamination census moved: {total}/{n_expected} expected names are now printed "
        f"in SKILL.md (was 9/19). Per fixture: "
        f"{ {k: v for k, v in census.items() if v} }")

    clean = sorted(f.name for f in harness.fixtures()
                   if not census[f.name] and _payload(f, "expected"))
    assert clean == ["03-ui-chrome-and-primitives",
                     "04-participants-are-not-concepts",
                     "05-reuse-the-existing-concept"], clean

    # ★ fixture 08 is the worst case, and it is named — a boundary that is STATED is honest
    f08 = next(f for f in harness.fixtures() if f.name.startswith("08"))
    exp08 = _payload(f08, "expected")[0]
    skill = unicodedata.normalize("NFC", SKILL.read_text(encoding="utf-8")).casefold()

    # what IS leaked (measured, not repeated): the name, and the exact slug 08 exists to test
    assert unicodedata.normalize("NFC", str(exp08["name"])).casefold() in skill
    assert "proskalzyvanie" in skill, (
        "the SKILL no longer prints 08's expected SLUG as its derivation example — the census's "
        "worst case changed shape; re-read it before trusting the baseline")

    # ...and what is NOT. Stating the boundary is the difference between a census and a slogan.
    for key in ("definition", "source_quote"):
        assert unicodedata.normalize("NFC", str(exp08[key])).casefold() not in skill, (
            f"08's {key} is NOW in the SKILL — the contamination GREW, and the baseline's "
            f"meaning changed with it")


# --------------------------------------------------------------------------- #
# ★ R-23 PHASE B — the refutation, PINNED (it was closed on four hand-run numbers)
# --------------------------------------------------------------------------- #


def test_the_IDF_THRESHOLD_IS_REFUTED_and_the_refutation_REPRODUCES() -> None:
    """★★ THE CUT THAT THIS TASK MADE TO ITSELF, and the standard it had to meet.

    R-23 Phase B proposed a write-time guard refusing a tautological definition, justified by a
    "clean separation" (garbage 4.6–22.0, corpus min 29.3). **That claim was four numbers typed
    by hand.** TASK 066 §2 indicts the 9/11 baseline for exactly that — *"produced by hand …
    not reproducible"* — and then closed a roadmap phase the same way. **One evidentiary
    standard for what the author wanted to BUILD, a weaker one for what he wanted to CUT.**

    So the refutation is code, it runs on a **clean checkout** (the eval set's own definitions —
    no live vault, no network), and this test pins its verdict:

      * the SKILL's OWN blessed short definition («Форк — расхождение цепочки блоков.») scores
        **BELOW** the canonical garbage («Синергия — это когда есть синергия…»);
      * so the bands **INTERLEAVE**, and no cutoff separates them;
      * **the obvious rescue — normalising by length — does not rescue it either.** Recorded,
        because "we tried the fix" must be checkable, not asserted.

    ⚠️ WHAT IS REFUTED IS THE **IDF-SUM FAMILY**, on its first false-positive control — NOT
    *"no scalar cutoff exists"*, which is a universal negative and was itself an over-claim from
    N=2 vs N=2. The general question is **UNMEASURED**. Reopening it requires ≥30 per class,
    **including short-but-good definitions** — the class whose absence produced the artifact.
    """
    import measure_definition_idf as m  # type: ignore[import-not-found]

    result = m.measure(m._bundled_corpus())
    assert result["corpus_size"] >= 10, "the bundled corpus vanished; the refutation is vacuous"

    by = {r["name"]: r for r in result["probes"]}
    assert by["Форк"]["cls"] == "good" and by["Синергия"]["cls"] == "garbage"
    assert by["Форк"]["idf_sum"] < by["Синергия"]["idf_sum"], (
        "the SKILL's own GOOD example no longer scores below the canonical GARBAGE — the "
        "premise of the refutation changed; re-read R-23 before rebuilding the guard")

    assert result["idf_sum_bands_interleave"] is True
    assert result["idf_mean_bands_interleave"] is True, (
        "length-normalising now SEPARATES the bands — that would REOPEN Phase B, and it must "
        "be argued from a population of >= 30 per class, not from these four probes")


def test_the_refutation_probes_carry_BOTH_classes() -> None:
    """A refutation whose probe set has only one class is not a refutation.

    The original sweep had **N=2 garbage and ZERO short-good definitions** — and the missing
    class is precisely what produced the flattering "min 29.3". A false-positive control that
    contains no false-positive candidates cannot fail.
    """
    import measure_definition_idf as m  # type: ignore[import-not-found]

    classes = {p["cls"] for p in m.PROBES}
    assert classes == {"good", "garbage"}, classes
    assert sum(1 for p in m.PROBES if p["cls"] == "good") >= 2, (
        "the false-positive control is the half the original sweep never ran")
    assert any("SKILL" in p["note"] for p in m.PROBES), (
        "at least one GOOD probe must be quoted from the SKILL itself — a guard whose first "
        "victim is the definition style the SKILL teaches is the finding, and it must be pinned")
