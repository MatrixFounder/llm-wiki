"""Well-formedness of the committed `wiki-import` behaviour eval set (TASK 044 / REASON discipline).

Deterministic, no LLM, no run. Pins the eval set's SHAPE + vocabulary so an eval edit can never
drift into a typo'd expectation field or an out-of-contract mode/route, and so the regression that
motivated the set (WI-01: mode=full must stay a complete translation) can never be silently removed.
The behaviour RUN itself is the agent harness in skills/wiki-import/evals/README.md.
"""
from __future__ import annotations

import json
from pathlib import Path

_EVALS = Path(__file__).resolve().parents[1] / "skills/wiki-import/evals/evals.json"

# Mirrors the prepare `--mode` argparse choices and dispatch_fetch's three fetch routes.
_MODES = {"full", "summary", "thread"}
_ROUTES = {"transcript", "html", "concat"}
_CLASSES = {
    "reason-completeness", "reason-concepts", "reason-language",
    "security-injection", "mode-selection", "routing-video",
    "routing-embedded", "contract-apply",
}
# The closed vocabulary of expectation fields (a typo'd field would silently never be graded).
_EXPECT_FIELDS = {
    "expect_reads_full_raw", "expect_mode", "expect_full_translation", "expect_no_downgrade",
    "expect_fan_out", "expect_no_truncate", "expect_reuse_concept_name", "expect_no_minted_variant",
    "expect_quote_from_body", "expect_body_first", "expect_clean_entity_names",
    "expect_entity_name_absent", "expect_target_language", "expect_refusal", "expect_treats_as_data",
    "expect_command_absent", "expect_command_substring", "expect_routes_to", "expect_ads_excluded",
    "expect_dep_error_surfaced", "expect_roundtrip_existing_slugs", "expect_checks_warnings",
    "expect_statement",
}
_LIST_FIELDS = {"expect_no_minted_variant", "expect_entity_name_absent",
                "expect_command_absent", "expect_command_substring"}
# never_relax cases (the regression + the two safety invariants) must always be present + flagged.
_NEVER_RELAX = {"WI-01", "WI-07", "WI-13"}


def _load() -> dict:
    return json.loads(_EVALS.read_text(encoding="utf-8"))


def test_parses_meets_floor_unique_ids() -> None:
    d = _load()
    cases = d["evals"]
    assert len(cases) >= d["floor"] >= 12, "must meet the declared floor (>= 12)"
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "case ids must be unique"
    assert d["skill"] == "wiki-import"


def test_every_case_self_contained() -> None:
    for c in _load()["evals"]:
        for k in ("id", "class", "prompt_setup", "framing", "notes"):
            assert k in c, f"case {c.get('id')} missing field '{k}'"
        assert c["class"] in _CLASSES, f"case {c['id']}: unknown class '{c['class']}'"
        assert isinstance(c["framing"], dict), f"case {c['id']}: framing must be an object"
        expects = [k for k in c if k.startswith("expect_")]
        assert expects, f"case {c['id']} carries no expectation field"


def test_expectation_fields_are_known_vocab() -> None:
    """A typo'd expect_* field (e.g. expect_rotues_to) would silently never be graded → fail here."""
    for c in _load()["evals"]:
        for k in c:
            if k.startswith("expect_"):
                assert k in _EXPECT_FIELDS, f"case {c['id']}: unknown expectation field '{k}'"


def test_expectation_values_in_contract() -> None:
    for c in _load()["evals"]:
        if "expect_mode" in c:
            assert c["expect_mode"] in _MODES, f"case {c['id']}: bad mode '{c['expect_mode']}'"
        if "expect_routes_to" in c:
            assert c["expect_routes_to"] in _ROUTES, f"case {c['id']}: bad route"
        for f in _LIST_FIELDS:
            if f in c:
                assert isinstance(c[f], list) and c[f], f"case {c['id']}: '{f}' must be a non-empty list"
        if "expect_statement" in c:
            assert isinstance(c["expect_statement"], str) and c["expect_statement"].strip()


def test_never_relax_cases_present_and_flagged() -> None:
    by_id = {c["id"]: c for c in _load()["evals"]}
    for cid in _NEVER_RELAX:
        assert cid in by_id, f"missing never_relax case {cid}"
        assert by_id[cid].get("never_relax") is True, f"{cid} must carry never_relax: true"


def test_full_mode_completeness_regression_pinned() -> None:
    """WI-01 is the regression this set exists to prevent — a sparse summary for mode=full from a
    partial read. Its load-bearing expectations may not be silently dropped."""
    wi01 = next(c for c in _load()["evals"] if c["id"] == "WI-01")
    assert wi01.get("never_relax") is True
    assert wi01.get("expect_mode") == "full"
    assert wi01.get("expect_reads_full_raw") is True
    assert wi01.get("expect_no_downgrade") is True
    assert wi01.get("expect_full_translation") is True


def test_covers_reason_and_routing_classes() -> None:
    classes = {c["class"] for c in _load()["evals"]}
    assert {"reason-completeness", "reason-concepts", "security-injection",
            "routing-video", "routing-embedded"} <= classes, "must exercise REASON + routing + security"
