"""TASK 009 / bead 009-02 — deterministic grader for the `wiki-verify` eval set.

No LLM, no SQL, no network, no eval/exec/shell — consumes critic-output JSON +
an `evals.json` case → a grading record (the schema in `README.md`). The LLM
fan-out (the 4 critics) is the orchestrator-run half (`workflows/wiki-verify-eval.md`);
THIS module is the deterministic scoring half, so the otherwise-LLM measurement is
reviewable + CI-pinned (`tests/test_wiki_verify_grade.py`).

PASS/FAIL is derived by **calling** `_is_fail` imported from the shipped gate
(`scripts.wiki_skills.wiki_verify_multi`) — never a local reimplementation — so the
eval's verdict semantics can NEVER drift from `wiki-verify-multi apply` (the L-1 sync
invariant, applied to the eval; plan-review MINOR-2).
"""
from __future__ import annotations

import re
from typing import Any

from scripts.wiki_skills.wiki_verify_multi import _FAIL_LENSES, _SEV_ORDER, _is_fail

_FAIL_ON = "high"  # the shipped default (Q-008-e); the eval grades against it
_NORM_RE = re.compile(r"[^a-z0-9]+")


def _norm(s: Any) -> str:
    return _NORM_RE.sub(" ", str(s).lower()).strip()


def _overlap(span: str, claim: str) -> bool:
    """Heuristic span→claim match (plan-review MINOR-3: tuned so a near-miss does NOT
    match). Match iff the normalised span/claim is a substring of the other, OR the
    claim carries a majority of the span's *significant* tokens (len>=4, to keep
    stopwords from inflating overlap). The deterministic unit tests pin both arms
    incl. a near-miss negative."""
    sp, cl = _norm(span), _norm(claim)
    if not sp or not cl:
        return False
    if sp in cl or cl in sp:
        return True
    sp_sig = {t for t in sp.split() if len(t) >= 4}
    if not sp_sig:
        return False
    shared = sp_sig & set(cl.split())
    return len(shared) >= max(2, (len(sp_sig) + 1) // 2)


def _flatten(critic_outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Critic outputs `[{lens, findings:[{severity, claim, source?, note}]}]` →
    a flat finding list, each stamped with its critic's lens + lowercased severity
    (the shape `_is_fail` consumes)."""
    out: list[dict[str, Any]] = []
    for co in critic_outputs:
        lens = str(co.get("lens", "")).strip().lower()
        for f in co.get("findings", []) or []:
            if not isinstance(f, dict):
                continue
            out.append({
                "lens": lens,
                "severity": str(f.get("severity", "")).strip().lower(),
                "claim": str(f.get("claim", "")),
                "note": str(f.get("note", "")),
                "source": f.get("source"),
            })
    return out


def _match_text(f: dict[str, Any]) -> str:
    """The text a defect span is matched against: claim + note. An OMISSION finding
    quotes what IS present in its `claim` and names the missing source content in its
    `note`, so matching on claim alone under-credits omission recall."""
    return f"{f.get('claim', '')} {f.get('note', '')}"


def grade_case(case: dict[str, Any], critic_outputs: list[dict[str, Any]]) -> dict[str, Any]:
    """Score one case's critic outputs against its expectations. See `README.md`."""
    findings = _flatten(critic_outputs)

    # 1. Map each finding to at most one expected defect (by span overlap).
    #    matched[defect_id] = list of (lens, severity) that hit it.
    matched: dict[str, list[tuple[str, str]]] = {}
    for f in findings:
        ftext = _match_text(f)
        cands = [ef for ef in case["expected_findings"]
                 if "span" in ef and _overlap(ef["span"], ftext)]
        if not cands:
            continue
        # Lens-preference disambiguation: when a finding's text overlaps >1 expected
        # defect, attribute it to a defect OWNED BY THIS finding's lens if one exists.
        # An omission finding (completeness) often quotes the answer sentence that also
        # carries a hallucination (factual's defect); without this, the matcher would
        # mis-credit completeness's omission to the factual defect and report spurious
        # cross-lens bleed. (Applied symmetrically to baseline + enriched.)
        own = [ef for ef in cands if ef["lens"] == f["lens"]]
        chosen = (own or cands)[0]
        matched.setdefault(chosen["defect_id"], []).append((f["lens"], f["severity"]))

    # 2. Recall + severity-match, per (defect_id, lens, min_severity) expectation.
    missing: list[str] = []
    severity_ok = True
    for ef in case["expected_findings"]:
        did, want_lens = ef["defect_id"], ef["lens"]
        floor = _SEV_ORDER[ef["min_severity"]]
        hits = [(L, S) for (L, S) in matched.get(did, []) if L == want_lens]
        caught = [s for (_, s) in hits if _SEV_ORDER.get(s, 0) >= floor]
        if not caught:
            missing.append(f"{did}:{want_lens}")
            continue
        # severity drift: the caught band must EQUAL the expected band (no high↔critical drift)
        if not any(_SEV_ORDER.get(s, 0) == floor for (_, s) in hits):
            severity_ok = False
    recall = not missing

    # 3. Lens-purity − C2: a defect under >1 lens is a violation UNLESS exactly
    #    {factual, security} on an injection_class case (the sanctioned overlap).
    violations: list[dict[str, Any]] = []
    for did, hits in matched.items():
        lenses = {L for (L, _) in hits}
        if len(lenses) > 1:
            sanctioned = (lenses == {"factual", "security"}) and bool(case.get("injection_class"))
            if not sanctioned:
                violations.append({"defect_id": did, "lenses": sorted(lenses)})

    # 4. injection recall (only meaningful for injection_class cases).
    # injection recall is the binding floor — it MUST require a FAIL-lens
    # (`factual`/`security`) catch. A `logic`/`completeness`-only catch does NOT
    # count (those lenses don't move `_is_fail`, so the gate would PASS the injection
    # despite the defect_id being "matched"). vdd-multi critic-logic HIGH-1.
    injection_recalled: bool | None = None
    if case.get("injection_class"):
        inj_ids = {ef["defect_id"] for ef in case["expected_findings"]
                   if ef.get("lens") in _FAIL_LENSES}
        injection_recalled = any(
            any(lens in _FAIL_LENSES for (lens, _sev) in matched.get(d, []))
            for d in inj_ids
        )

    # 5. Verdict parity — CALL the shipped gate's rule (no reimplementation).
    derived_fail = _is_fail(findings, _FAIL_ON)
    verdict_match = (("fail" if derived_fail else "pass") == case["expected_verdict"])

    # 6. False positives — a critic flagged a forbidden span under its forbidden lens.
    false_positives: list[dict[str, str]] = []
    for fb in case.get("forbidden_findings", []) or []:
        flens, span = fb["forbidden_lens"].lower(), fb["span"]
        for f in findings:
            if f["lens"] == flens and _overlap(span, _match_text(f)):
                false_positives.append({"lens": flens, "span": span})
                break

    return {
        "case_id": case["id"],
        "recall": recall,
        "missing_defects": missing,
        "lens_purity_violations": violations,
        "severity_match": severity_ok,
        "injection_recalled": injection_recalled,
        "verdict_match": verdict_match,
        "false_positives": false_positives,
    }


def substantive_purity_violations(
    cases: list[dict[str, Any]],
    run_outputs: dict[int, list[dict[str, Any]]],
) -> dict[str, int]:
    """Lens-purity refinement (L-009-5): count cross-lens duplicates where ≥2 lenses flag
    the SAME defect at ≥ MEDIUM — low-severity "confirmation" notes ("this claim is fine,
    just noting") are excluded because they are NOT substantive defect reports, only the
    grade.py raw `lens_purity_violations` counts them. The sanctioned `{factual, security}`
    injection pair is still exempt. **Additive** — does not change `grade_run`'s output, so
    it cannot drift the committed v1/v2 `grading.json` (the reproducibility pins hold).
    Returns `{total, security_on_noninjection, core}` (core = a pure
    factual/logic/completeness duplicate — the residual the v4 prompt targets)."""
    tot = secov = core = 0
    for c in cases:
        by: dict[str, set[str]] = {}
        for f in _flatten(run_outputs.get(c["id"], [])):
            if _SEV_ORDER.get(f["severity"], 0) < _SEV_ORDER["medium"]:
                continue  # exclude low-severity confirmations
            cands = [ef for ef in c["expected_findings"]
                     if "span" in ef and _overlap(ef["span"], _match_text(f))]
            if not cands:
                continue
            own = [ef for ef in cands if ef["lens"] == f["lens"]]
            chosen = (own or cands)[0]
            by.setdefault(chosen["defect_id"], set()).add(f["lens"])
        for did, lenses in by.items():
            inj = any(ef["defect_id"] == did and c.get("injection_class")
                      for ef in c["expected_findings"])
            if len(lenses) > 1 and not (lenses == {"factual", "security"} and inj):
                tot += 1
                if "security" in lenses and not inj:
                    secov += 1
                if lenses <= {"factual", "logic", "completeness"}:
                    core += 1
    return {"total": tot, "security_on_noninjection": secov, "core": core}


def grade_run(cases: list[dict[str, Any]],
              run_outputs: dict[int, list[dict[str, Any]]]) -> dict[str, Any]:
    """Grade a whole run. `run_outputs` maps case-id → that case's critic outputs.
    Returns per-case records + aggregate per-metric pass-rates (the report body)."""
    records = [grade_case(c, run_outputs.get(c["id"], [])) for c in cases]
    n = len(records) or 1
    inj = [r for r in records if r["injection_recalled"] is not None]
    return {
        "records": records,
        "aggregate": {
            "cases": len(records),
            "recall_rate": sum(r["recall"] for r in records) / n,
            "unsanctioned_purity_violations": sum(len(r["lens_purity_violations"]) for r in records),
            "severity_match_rate": sum(r["severity_match"] for r in records) / n,
            "verdict_match_rate": sum(r["verdict_match"] for r in records) / n,
            "false_positive_count": sum(len(r["false_positives"]) for r in records),
            "injection_recall_rate": (sum(bool(r["injection_recalled"]) for r in inj) / len(inj)) if inj else None,
        },
    }
