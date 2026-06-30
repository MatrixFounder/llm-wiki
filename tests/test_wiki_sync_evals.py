"""Well-formedness of the committed `wiki-sync` behaviour eval set (TASK 046 / converged driver).

Deterministic, no LLM, no run. Pins the eval set's SHAPE + vocabulary so an eval edit can never
drift into a typo'd expectation field or an out-of-contract kind, and so the converged-path
invariants (WS-01 delegation, WS-03 H-6 fence, WS-06 dual commit-marker / no re-ingest loop) can
never be silently removed. The behaviour RUN itself is the agent harness in
skills/wiki-sync/evals/README.md.
"""
from __future__ import annotations

import json
from pathlib import Path

_EVALS = Path(__file__).resolve().parents[1] / "skills/wiki-sync/evals/evals.json"

# Mirrors the wiki-import `--kind` choices (the delegate kind wiki-sync passes through).
_KINDS = {"auto", "meeting", "lesson", "article", "paper", "thread", "summary"}
_CLASSES = {"delegation", "profile", "h6-fence", "idempotency", "concepts-passthrough"}
# The closed vocabulary of expectation fields (a typo'd field would silently never be graded).
_EXPECT_FIELDS = {
    "expect_delegates_to_wiki_import", "expect_no_inline_summarise", "expect_kind",
    "expect_h6_fence_in_reason", "expect_treats_as_data", "expect_skip_summary_exists",
    "expect_no_redelegate", "expect_delegate_no_concepts", "expect_records_both_markers",
    "expect_no_reingest_loop", "expect_command_substring", "expect_command_absent",
    "expect_statement",
}
_LIST_FIELDS = {"expect_command_substring", "expect_command_absent"}
# never_relax cases (the converged-path invariants) must always be present + flagged.
_NEVER_RELAX = {"WS-01", "WS-03"}


def _load() -> dict:
    return json.loads(_EVALS.read_text(encoding="utf-8"))


def test_parses_meets_floor_unique_ids() -> None:
    d = _load()
    cases = d["evals"]
    assert len(cases) >= d["floor"] >= 5, "must meet the declared floor (>= 5)"
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "case ids must be unique"
    assert d["skill"] == "wiki-sync"


def test_every_case_self_contained() -> None:
    for c in _load()["evals"]:
        for k in ("id", "class", "prompt_setup", "framing", "notes"):
            assert k in c, f"case {c.get('id')} missing field '{k}'"
        assert c["class"] in _CLASSES, f"case {c['id']}: unknown class '{c['class']}'"
        assert isinstance(c["framing"], dict), f"case {c['id']}: framing must be an object"
        expects = [k for k in c if k.startswith("expect_")]
        assert expects, f"case {c['id']} carries no expectation field"


def test_expectation_fields_are_known_vocab() -> None:
    """A typo'd expect_* field would silently never be graded → fail here."""
    for c in _load()["evals"]:
        for k in c:
            if k.startswith("expect_"):
                assert k in _EXPECT_FIELDS, f"case {c['id']}: unknown expectation field '{k}'"


def test_expectation_values_in_contract() -> None:
    for c in _load()["evals"]:
        if "expect_kind" in c:
            assert c["expect_kind"] in _KINDS, f"case {c['id']}: bad kind '{c['expect_kind']}'"
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


def test_delegation_invariant_pinned() -> None:
    """WS-01 is the core converged-path invariant — every distil entry is delegated to wiki-import,
    never inlined. Its load-bearing expectations may not be silently dropped."""
    ws01 = next(c for c in _load()["evals"] if c["id"] == "WS-01")
    assert ws01.get("never_relax") is True
    assert ws01.get("expect_delegates_to_wiki_import") is True
    assert ws01.get("expect_no_inline_summarise") is True


def test_h6_fence_invariant_pinned() -> None:
    """WS-03 pins that the H-6 nonce fence rides the delegation (the distil is delegated, so the
    single shared fence is wiki-import's reason-contract Hard Rule #4)."""
    ws03 = next(c for c in _load()["evals"] if c["id"] == "WS-03")
    assert ws03.get("never_relax") is True
    assert ws03.get("expect_h6_fence_in_reason") is True
    assert ws03.get("expect_treats_as_data") is True


def test_covers_driver_discipline_classes() -> None:
    classes = {c["class"] for c in _load()["evals"]}
    assert {"delegation", "profile", "h6-fence", "idempotency", "concepts-passthrough"} <= classes, \
        "must exercise delegation + profile + H-6 + idempotency + concepts passthrough"
