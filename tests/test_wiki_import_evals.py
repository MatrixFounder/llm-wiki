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
    "reason-grammar",       # TASK 046: pyramid-vs-article grammar + diagrams discipline
    "acquire-degradation",  # TASK 046 P4: scanned-PDF graceful FETCH_FAILED + the OCR xfail tripwire
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
    # TASK 046 converged-discipline fields
    "expect_pyramid", "expect_no_fulltext_wrapper", "expect_sections", "expect_type",
    "expect_mermaid_selective", "expect_no_decorative_diagrams", "expect_states_concepts_deferred",
    # TASK 046 P4 acquire-degradation + xfail tripwire
    "expect_graceful_fetch_failed", "expect_no_fabricated_summary", "expect_produces_summary",
}
_LIST_FIELDS = {"expect_no_minted_variant", "expect_entity_name_absent",
                "expect_command_absent", "expect_command_substring", "expect_sections"}
# Closed vocab for the note `type:` — the OUTPUT values of wiki_import_article/__init__.py
# `_KIND_NOTE_TYPE` (article/paper/thread all map to `article-summary`), plus the layout-safe
# `summary` fallback. NOT the `--kind` keys (which would admit a fake type / reject the real one).
_TYPES = {"meeting-summary", "lesson-summary", "article-summary", "summary"}
# never_relax cases (the regression + safety invariants + TASK 046 grammar invariants) must
# always be present + flagged.
_NEVER_RELAX = {"WI-01", "WI-07", "WI-13", "WI-16", "WI-19", "WI-20"}


def _load() -> dict:
    return json.loads(_EVALS.read_text(encoding="utf-8"))


def test_parses_meets_floor_unique_ids() -> None:
    d = _load()
    cases = d["evals"]
    # floor is measured over expected_pass cases only — an xfail tripwire must not inflate it.
    expected_pass = [c for c in cases if not c.get("expected_fail")]
    assert len(expected_pass) >= d["floor"] >= 12, "expected_pass cases must meet the declared floor (>= 12)"
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "case ids must be unique"
    assert d["skill"] == "wiki-import"


def test_expected_fail_cases_are_tracked_and_not_never_relax() -> None:
    """An xfail tripwire (expected_fail: true) MUST cite a tracked known-issue (`tracks`) and may NOT
    be never_relax (a 'must always pass' that is 'expected to fail' is a contradiction). When the gap
    closes the case xPASSES → promote it (drop expected_fail)."""
    for c in _load()["evals"]:
        if c.get("expected_fail"):
            assert isinstance(c.get("tracks"), str) and c["tracks"].strip(), \
                f"case {c['id']}: expected_fail must carry a non-empty 'tracks' known-issue ref"
            assert c.get("never_relax") is not True, \
                f"case {c['id']}: an expected_fail case cannot also be never_relax"


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
        if "expect_type" in c:
            assert c["expect_type"] in _TYPES, f"case {c['id']}: bad note type '{c['expect_type']}'"
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
            "routing-video", "routing-embedded", "reason-grammar"} <= classes, \
        "must exercise REASON + routing + security + TASK-046 grammar"


def test_pyramid_grammar_regression_pinned() -> None:
    """TASK 046 P1: --kind meeting/lesson must produce a PYRAMID note, never the article full-text
    wrapper. WI-16 (meeting) + WI-19 (lesson) pin this; their load-bearing expectations may not be
    silently dropped (the lesson branch was mutation-survivable in P1 review)."""
    by_id = {c["id"]: c for c in _load()["evals"]}
    for cid, typ in (("WI-16", "meeting-summary"), ("WI-19", "lesson-summary")):
        c = by_id[cid]
        assert c.get("never_relax") is True, f"{cid} must be never_relax"
        assert c["class"] == "reason-grammar"
        assert c.get("expect_pyramid") is True, f"{cid} must assert the pyramid grammar"
        assert c.get("expect_no_fulltext_wrapper") is True, f"{cid} must forbid the article wrapper"
        assert c.get("expect_type") == typ, f"{cid} must pin type {typ}"
        assert isinstance(c.get("expect_sections"), list) and c["expect_sections"], \
            f"{cid} must list the pyramid sections"
