"""TASK 064 — the ANTI-GARBAGE GATES for `wiki-extract-concepts` (G0…G10).

The operator's ask, in his words: *"definitions for the KEY concepts, which COMPLEMENT
the source page, WITHOUT GARBAGE DATA"* — and the rail must hold on WEAK models, which
obey quotas far more literally than strong ones.

Every test here pins a MECHANISM, not prompt wording. The prompt is advice; a validator
is not. Each gate is named after the live garbage class it kills in the operator's
720-page vault:

  G0  an EMPTY extraction is a SUCCESS      — the pump behind every other class: with a
                                              floor of 1, invention was the only green path
  G1  the definition must COMPLEMENT        — `definition: ""` and `definition == quote` passed
  G2  the quote receipt is LOAD-BEARING     — `source_quote: "и"` grounded against any body
  G3  NO env bypass, and NO mention of one  — the refusal used to TEACH the bypass
  G4  a person is not a concept             — `уоррен-баффет`, `гарри-марковиц` are live
  G5  NEAR_DUPLICATE_SLUG                   — 5 permanent graph splits, the #1 verified class
  G6  IN_BATCH_SLUG_COLLISION               — silent overwrite, ZERO lint issues
  G7  never overwrite an existing page      — data loss reported as success
  G8  the slug is the LAYOUT's to derive    — an ASCII page in a Cyrillic vault links to nothing
  G9  the source_span is VERIFIED           — `L9999-L9999` was exit 0, straight into the index
  G10 refuse pages the layout cannot SEE    — invisible pages; TASK 063's G4 lesson

Plus the four cross-cutting invariants the contract requires:
  * ZERO-FILE on refusal (and, for the pre-DB gates, the DB is NEVER OPENED);
  * the G5 cutoff is RE-MEASURED here on the operator's real pairs, never hardcoded;
  * `[]` ⇒ exit 0 end-to-end through `main()`, with `upsert_entity_refs` NOT called;
  * the CWE-117/209 canary: no source-body content in any refusal envelope, walked
    RECURSIVELY so a nested `violations[]` cannot smuggle it out.
"""
from __future__ import annotations

import re

import argparse
import difflib
import hashlib
import io
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills import wiki_extract_concepts as wec
from scripts.wiki_skills.wiki_extract_concepts._errors import ExtractionParseError
from scripts.wiki_skills.wiki_extract_concepts._gates import (
    NEAR_DUP_CUTOFF,
    _dup_key,
    build_dup_keys,
    near_duplicate_warnings,
)
from scripts.wiki_skills.wiki_extract_concepts import _name_differs
from scripts.wiki_skills.wiki_extract_concepts._validation import (
    derive_source_span,
    _validate_candidates_schema,
)

# --------------------------------------------------------------------------- #
# The seeded source. ★ THE LINE NUMBERS ARE THE POINT (G9).
#
# `source_body` is the WHOLE FILE as read — frontmatter included — because that is the
# string the quote check grounds against. So **L1 is the file's first line: the opening
# `---`.** That was UNDEFINED before TASK 064, which is exactly why the repo's canonical
# apply fixture carried `L3-L3` for a quote that lives on line 4 and nobody ever noticed:
# the span was shape-validated three times and verified against the body zero times.
# --------------------------------------------------------------------------- #
_BODY = (
    "---\n"                                                                  # L1
    "type: summary\n"                                                        # L2
    "title: Sample Doc\n"                                                    # L3
    "---\n"                                                                  # L4
    "\n"                                                                     # L5
    "# Sample Doc\n"                                                         # L6
    "\n"                                                                     # L7
    "The Sharpe Ratio measures excess return per unit of volatility.\n"      # L8
    "\n"                                                                     # L9
    "A perpetual future is a derivative contract with no expiry date.\n"     # L10
)
_PARA_NOTE = "05 - Материалы/Тема/sample-doc.md"
_PARA_RU_NOTE = "05 - Материалы/Тема/Заметка.md"
_QUOTE = "The Sharpe Ratio measures excess return per unit of volatility."
_SPAN = "L8-L8"
_DEFINITION = (
    "A risk-adjusted return measure: excess return divided by the volatility "
    "that produced it."
)


def _cand(**over: Any) -> dict[str, Any]:
    """A candidate that passes EVERY gate — the baseline each test perturbs by one field."""
    base: dict[str, Any] = {
        "slug": "sharpe-ratio",
        "name": "Sharpe Ratio",
        "definition": _DEFINITION,
        "source_quote": _QUOTE,
        "source_span": _SPAN,
        "entity_type": "concept",
    }
    base.update(over)
    return base


def _schema(root: Path, vault_id: str, layout: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "WIKI_SCHEMA.md").write_text(
        f'---\nvault_id: {vault_id}\nschema_version: "2.0"\nlanguage: en\n'
        f'layout: {layout}\n---\n', encoding="utf-8")


def _seed(
    tmp_path: Path,
    *,
    layout: str = "karpathy",
    vault_id: str = "kvault",
    body: str = _BODY,
    note_rel: str | None = None,
    index: bool = True,
) -> tuple[Path, Path, str, str]:
    """Spin up a vault + source note + registered DB.

    Returns (vault_root, db_path, source_hash, source_page_arg).
    """
    root = tmp_path / "vault"
    _schema(root, vault_id, layout)
    if note_rel is None:
        note_rel = ("_sources/sample-doc.md" if layout == "karpathy"
                    else "notes/sample-doc.md")
    note = root / note_rel
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(body, encoding="utf-8")

    db = tmp_path / "index.db"
    if index:
        repo = SQLiteRepository(db)
        repo.apply_schema()
        repo.register_vault(Vault(
            vault_id=vault_id, name=vault_id, root_path=root,
            schema_version="2.0", registered_at=datetime(2026, 7, 14)))
        reindex_full(repo, vault_id)
        repo.close()

    source_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    # karpathy resolves by slug; the PARA-family layouts by vault-relative path.
    src_arg = "sample-doc" if layout == "karpathy" else note_rel
    return root, db, source_hash, src_arg


def _args(
    *, root: Path, db: Path | None, src: str, source_hash: str,
    vault: str = "kvault", ingest: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        cmd="apply", vault=vault, vault_root=root, source_page=src,
        db_path=str(db) if db else None, source_hash=source_hash, ingest=ingest,
        candidates_file=None, candidates_stdin=True,
    )


def _stdin(monkeypatch: pytest.MonkeyPatch, candidates: list[dict[str, Any]]) -> None:
    payload = json.dumps(candidates).encode("utf-8")
    monkeypatch.setattr(
        "sys.stdin", type("FakeStdin", (), {"buffer": io.BytesIO(payload)})())


def _apply(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    candidates: list[dict[str, Any]], **kw: Any,
) -> tuple[int, dict[str, Any]]:
    """Run `apply` in-process; return (exit_code, envelope)."""
    _stdin(monkeypatch, candidates)
    rc = wec.apply(_args(**kw))
    env = json.loads(capsys.readouterr().out)
    assert isinstance(env, dict)
    return rc, env


def _concept_files(root: Path) -> list[Path]:
    return sorted(root.rglob("_concepts/*.md"))


# =========================================================================== #
# G0 — ★ AN EMPTY EXTRACTION IS A SUCCESS (the pump)
# =========================================================================== #

def test_g0_empty_candidates_is_success_end_to_end_through_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """★ THE most important test in this file. `[]` → exit 0 + `action: no_candidates`,
    driven END-TO-END THROUGH `main()` (argv → envelope), not through the internal
    `apply()` seam — because the thing that used to be broken was the OPERATOR-VISIBLE
    contract, and a test that skips the CLI cannot pin it.

    `_CANDIDATE_COUNT_MIN` was 1: an honest "this source has no concepts" was an exit-4
    FAILURE, so the model's only green path was to INVENT one. That is the pump behind
    every garbage class in the operator's vault.
    """
    root, db, source_hash, src = _seed(tmp_path)
    _stdin(monkeypatch, [])
    rc = wec.main([
        "apply", "--vault", "kvault", "--vault-root", str(root),
        "--source-page", src, "--source-hash", source_hash,
        "--db-path", str(db), "--candidates-stdin",
    ])
    env = json.loads(capsys.readouterr().out)
    assert rc == 0, f"an empty extraction must be a SUCCESS, got exit {rc}: {env}"
    assert env["action"] == "no_candidates"
    assert env["written"] == [] and env["mentioned"] == []
    assert _concept_files(root) == [], "an empty extraction must write NO pages"


def test_g0_empty_candidates_does_not_call_upsert_entity_refs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """★ THE SUBTLE HALF, and the one that would have silently eaten data.

    `upsert_entity_refs` is an atomic DELETE+INSERT keyed on the source page: called
    with an empty list it CLEARS the source's existing refs. On the empty path that
    would drop this source out of EVERY concept's `BEGIN-AUTO:mentions` ledger —
    turning "I found no concepts" into "I deleted the ones you had". An empty
    extraction must mutate NOTHING but `source_state`.
    """
    root, db, source_hash, src = _seed(tmp_path)

    called: list[Any] = []

    def _boom(*a: Any, **k: Any) -> None:
        called.append(a)
        raise AssertionError(
            "upsert_entity_refs was called on the EMPTY path — it would CLEAR the "
            "source's existing mentions ledger")

    monkeypatch.setattr(wec, "upsert_entity_refs", _boom)
    rc, env = _apply(monkeypatch, capsys, [], root=root, db=db, src=src,
                     source_hash=source_hash)
    assert rc == 0 and env["action"] == "no_candidates"
    assert not called


def test_g0_empty_candidates_updates_source_state_so_rerun_short_circuits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The empty path still records the hash — otherwise every re-run would re-ask the
    model to extract nothing from the same unchanged source, forever."""
    root, db, source_hash, src = _seed(tmp_path)
    rc, _ = _apply(monkeypatch, capsys, [], root=root, db=db, src=src,
                   source_hash=source_hash)
    assert rc == 0

    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            "SELECT value FROM source_state WHERE vault_id='kvault'").fetchone()
    finally:
        conn.close()
    assert row is not None, "the empty path must still update source_state"
    assert row[0] == source_hash


def test_g0_validator_accepts_empty_list() -> None:
    """The floor is 0, at the leaf. (The old value, 1, is the single line this whole
    task hangs off.)"""
    _validate_candidates_schema([], source_body=_BODY)  # must not raise
    assert wec._CANDIDATE_COUNT_MIN == 0


# =========================================================================== #
# G1 — the definition must COMPLEMENT the source
# =========================================================================== #

@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("definition", ""),                       # the empty definition — was ACCEPTED
        ("definition", "A measure."),             # 10 chars — says nothing
        ("source_quote", "и"),                    # the forgeable receipt — was ACCEPTED
        ("source_quote", "The Sharpe Ratio"),     # a fragment, not a sentence
        ("name", "X"),                            # 1 char
    ],
)
def test_g1_field_too_short(field: str, value: str) -> None:
    """`definition: ""` was ACCEPTED — only the CAPS were ever checked, never the
    FLOORS. The definition IS the page body, so an empty one files a page that says
    nothing; a one-token `source_quote` "grounds" against any body at all."""
    with pytest.raises(ExtractionParseError) as ei:
        _validate_candidates_schema([_cand(**{field: value})], source_body=_BODY)
    assert ei.value.error == "FIELD_TOO_SHORT"
    assert ei.value.field == field


def test_g1_definition_is_quote_refused() -> None:
    """A definition that is a byte-for-byte copy of the quote adds NOTHING: the quote is
    ALREADY stored as provenance in `page_entity_refs`. The page would just restate the
    sentence the source already says. Zero false positives — nobody wants a page whose
    body is its own citation."""
    with pytest.raises(ExtractionParseError) as ei:
        _validate_candidates_schema(
            [_cand(definition=_QUOTE)], source_body=_BODY)
    assert ei.value.error == "DEFINITION_IS_QUOTE"


def test_g1_definition_is_quote_normalised_not_byte_exact() -> None:
    """The compare is `_norm`'d (NFC + collapse-whitespace + casefold), so re-wrapping
    the quote and changing its case does not launder it into a "definition"."""
    laundered = "  the sharpe   ratio MEASURES excess return per unit of volatility.  "
    with pytest.raises(ExtractionParseError) as ei:
        _validate_candidates_schema(
            [_cand(definition=laundered)], source_body=_BODY)
    assert ei.value.error == "DEFINITION_IS_QUOTE"


@pytest.mark.parametrize(
    "definition",
    [
        "A measure of risk.\nWith a second line that makes it not one sentence.",
        "A risk measure. See [[write-ahead-log]] for the related storage concept.",
        "A risk measure computed as `excess_return / stddev` over the sample window.",
        "- A risk-adjusted return measure, rendered here as a markdown list item.",
        "# A risk-adjusted return measure written as a markdown heading, not prose.",
        "> A risk-adjusted return measure written as a markdown blockquote, not prose.",
    ],
)
def test_g1_definition_not_prose_refused(definition: str) -> None:
    """★ REFUSING BEATS MANGLING.

    `sanitize_markdown_text` SILENTLY ESCAPES these into the filed page as visible
    backslash litter — `See \\[\\[write-ahead-log\\]\\]` — and nobody is told. The vault
    gets permanently scarred to spare the model a round-trip. Refuse instead: the model
    is told and re-emits one clean sentence; the operator's page never carries the scar.
    """
    with pytest.raises(ExtractionParseError) as ei:
        _validate_candidates_schema(
            [_cand(definition=definition)], source_body=_BODY)
    assert ei.value.error == "DEFINITION_NOT_PROSE"
    assert ei.value.field == "definition"


def test_g1_ordinary_prose_definition_passes() -> None:
    """The gate must not fire on the thing it exists to protect: a plain sentence with
    ordinary punctuation (colon, comma, hyphen, parens) is fine."""
    _validate_candidates_schema(
        [_cand(definition="A risk-adjusted return measure (Sharpe, 1966): excess "
                          "return divided by volatility, per unit of risk taken.")],
        source_body=_BODY)


# =========================================================================== #
# G2 — the quote receipt is LOAD-BEARING
# =========================================================================== #

def test_g2_fabricated_quote_refused() -> None:
    """The receipt is what makes the whole rail non-fabricable. A paraphrase is not a
    quote."""
    with pytest.raises(ExtractionParseError) as ei:
        _validate_candidates_schema(
            [_cand(source_quote="The Sharpe Ratio is a wonderful measure of risk "
                                "that this source never actually says.")],
            source_body=_BODY)
    assert ei.value.error == "FIELD_QUOTE_NOT_IN_BODY"


def test_g2_line_wrapped_quote_still_grounds() -> None:
    """★ A gate that fires on INNOCENT input is a gate the operator learns to route
    around. A quote copied out of a hard-wrapped source differs from the body only in
    whitespace; the normalised compare grounds it instead of failing it for a reason
    that has nothing to do with grounding."""
    wrapped = "The Sharpe Ratio measures excess\n   return per unit of volatility."
    _validate_candidates_schema(
        [_cand(source_quote=wrapped)], source_body=_BODY)  # must not raise


def test_g2_single_token_quote_cannot_forge_grounding() -> None:
    """The pre-064 check was a bare `in` substring test with NO minimum length, so
    `source_quote: "и"` grounded against any Russian body ever written. The floor is
    what makes the substring test mean something."""
    with pytest.raises(ExtractionParseError) as ei:
        _validate_candidates_schema(
            [_cand(source_quote="The")], source_body=_BODY)
    assert ei.value.error == "FIELD_TOO_SHORT"  # caught by the floor, not the substring


# =========================================================================== #
# G3 — ★ NO ESCAPE HATCH, AND NO TUTORIAL FOR ONE
# =========================================================================== #

@pytest.mark.parametrize("value", ["1", "0", "false", "", "yes"])
def test_g3_no_quote_check_env_var_does_not_bypass(
    monkeypatch: pytest.MonkeyPatch, value: str,
) -> None:
    """★ THE BYPASS IS DELETED — at EVERY truthiness value, including the ones that used
    to "disable" it by accident.

    The old code was a bare `os.environ.get(...)` truthiness test, so `=0` and `=false`
    ALSO disabled the check (verified: a fabricated quote was accepted with `=0`). The
    env read is gone; setting the variable to anything now does nothing at all.
    """
    monkeypatch.setenv("WIKI_EXTRACT_NO_QUOTE_CHECK", value)
    with pytest.raises(ExtractionParseError) as ei:
        _validate_candidates_schema(
            [_cand(source_quote="A sentence this source does not contain anywhere.")],
            source_body=_BODY)
    assert ei.value.error == "FIELD_QUOTE_NOT_IN_BODY"


def test_g3_no_refusal_reason_ever_names_an_env_var() -> None:
    """★★ WORSE THAN THE FLAG WAS THE ERROR MESSAGE THAT TAUGHT IT.

    The old refusal put *"(set WIKI_EXTRACT_NO_QUOTE_CHECK=1 to skip)"* inside the
    envelope the model reads AT THE EXACT MOMENT IT IS STUCK AND LOOKING FOR A WAY
    THROUGH. That is a fabrication tutorial in the failure path.

    This sweeps EVERY refusal this rail can raise from the validation leaf and asserts
    no reason string mentions an env var — so a future gate cannot quietly reintroduce
    the pattern. Sibling precedent (`wiki_extract_decisions._validation`): *"an escape
    hatch on an anti-fabrication check IS the fabrication path, and it gets reached
    exactly when someone is in a hurry."*
    """
    perturbations: list[dict[str, Any]] = [
        _cand(definition=""),
        _cand(source_quote="и"),
        _cand(definition=_QUOTE),
        _cand(definition="See [[x]] for more about this risk-adjusted return measure."),
        _cand(entity_type="person"),
        _cand(entity_type="banana"),
        _cand(slug="block_number"),
        _cand(source_quote="A sentence this source does not contain at all, ever."),
        # ⚠️ the two span perturbations that used to live here no longer REFUSE — the span is
        # DERIVED (TASK 066), so they are corrected, not rejected. A MALFORMED span still
        # refuses, and that is the surface that must stay swept.
        _cand(source_span="line 8"),
    ]
    reasons: list[str] = []
    for cand in perturbations:
        with pytest.raises(ExtractionParseError) as ei:
            _validate_candidates_schema([cand], source_body=_BODY)
        reasons.append(ei.value.reason or "")
    assert len(reasons) == len(perturbations)

    banned = ("WIKI_EXTRACT", "env var", "environment variable", "=1 to skip",
              "NO_QUOTE_CHECK", "os.environ")
    for reason in reasons:
        for token in banned:
            assert token.lower() not in reason.lower(), (
                f"a refusal reason names an escape hatch — that is a fabrication "
                f"tutorial delivered exactly when the model is stuck: {reason!r}")


# =========================================================================== #
# G4 — a person is not a concept
# =========================================================================== #

def test_g4_person_entity_type_refused_with_a_teaching_reason() -> None:
    """The operator's standing rule: an attendee belongs in `participants:` frontmatter,
    a cited author in the note body — NEVER as a `_concepts/` page. `person` was in the
    allowed set AND offered on the prompt's menu; 12+ person pages are live in his vault.

    It gets its OWN code, not the generic parse error — because "not in [company,
    concept, ...]" is true, useless, and invites the model to retry as `group`.
    """
    with pytest.raises(ExtractionParseError) as ei:
        _validate_candidates_schema(
            [_cand(slug="warren-buffett", name="Warren Buffett",
                   entity_type="person")],
            source_body=_BODY)
    assert ei.value.error == "ENTITY_TYPE_NOT_ALLOWED"
    assert ei.value.field == "entity_type"
    reason = (ei.value.reason or "").lower()
    assert "participants" in reason, "the reason must TEACH the fix, not just refuse"
    assert "person" not in wec._ALLOWED_ENTITY_TYPES


def test_g4_unknown_entity_type_stays_a_parse_error() -> None:
    """An unknown type is a SCHEMA problem, not a policy one — it keeps the generic
    code. Only `person` is a refusal with a rule behind it."""
    with pytest.raises(ExtractionParseError) as ei:
        _validate_candidates_schema(
            [_cand(entity_type="banana")], source_body=_BODY)
    assert ei.value.error == "EXTRACTION_PARSE_ERROR"


# =========================================================================== #
# G5 — NEAR_DUPLICATE_SLUG (the #1 VERIFIED live garbage class)
# =========================================================================== #

# The operator's REAL live splits (true positives) and the REAL narrower concepts that
# must survive (false-positive probes). These are not hypotheticals: the left column is
# a list of pages that exist in his vault twice.
_TRUE_POSITIVES = [
    ("бессрочный-фьючерс", "бессрочные-фьючерсы"),   # plural
    ("сатоши-накамото", "сатоси-накамото"),          # transliteration variant
    ("виталик-бутерин", "vitalik-buterin"),          # script split
    ("cppi-constant-proportion-portfolio-insurance",
     "cppi-constant-proportion-portfolio-insurance-strategy"),  # long/short
]
_FALSE_POSITIVE_PROBES = [
    ("хеджирование", "хеджирование-дельтой"),        # a real, NARROWER concept
    ("backtesting", "backtesting-engine"),
    ("риск", "риск-ликвидности"),
]


def test_g5_cutoff_is_re_measured_on_the_real_pairs_not_hardcoded() -> None:
    """★ RE-MEASURE, DO NOT TRUST THE NUMBER.

    A similarity cutoff nobody re-derives is a magic constant, and a magic constant is
    how a gate silently stops working. This asserts the cutoff still SEES the operator's
    REAL duplicate pairs (it is what makes the advisory worth emitting at all) and still
    stays quiet on his REAL narrower concepts.

    Transliteration in `_dup_key` is the whole trick: `виталик-бутерин` and
    `vitalik-buterin` are 100% dissimilar as raw strings — no character-ratio metric
    will EVER relate them — but they are the SAME KEY once transliterated.
    """
    def ratio(a: str, b: str) -> float:
        return difflib.SequenceMatcher(None, _dup_key(a), _dup_key(b)).ratio()

    for a, b in _TRUE_POSITIVES:
        assert ratio(a, b) >= NEAR_DUP_CUTOFF, (
            f"the advisory stopped SEEING a real live duplicate: {a} / {b} scored "
            f"{ratio(a, b):.3f} < {NEAR_DUP_CUTOFF}")
    for a, b in _FALSE_POSITIVE_PROBES:
        assert ratio(a, b) < NEAR_DUP_CUTOFF, (
            f"{a} / {b} scored {ratio(a, b):.3f} >= {NEAR_DUP_CUTOFF} — the advisory "
            f"would nag about a legitimately narrower concept")

    # The script split is the expensive one: transliteration must make it EXACT.
    assert _dup_key("виталик-бутерин") == _dup_key("vitalik-buterin")


# ★★★ THE MEASUREMENT THAT DEMOTED THE GATE (F2). Every pair below is a pair of DIFFERENT
# concepts, and every one scores AT OR ABOVE the cutoff. The bands do not merely overlap —
# they are INVERTED: `type-i-error`/`type-ii-error` (0.960) outscores the real live
# duplicate the gate was BUILT for (`бессрочный-фьючерс`/`бессрочные-фьючерсы`, 0.927).
#
# Structural law: a 2-char negating prefix (`de`/`не`) on any base ≥ 8 chars crosses 0.88.
# The metric is therefore ANTI-CORRELATED WITH MEANING — it rates ANTONYMS as duplicates.
_FALSELY_REFUSED = [
    ("type-i-error", "type-ii-error"),
    ("supervised-learning", "unsupervised-learning"),
    ("централизация", "децентрализация"),
    ("precision", "recision"),
    ("serialization", "deserialization"),
    ("micro-service", "macro-service"),
    ("шифрование", "дешифрование"),
    ("ликвидность", "неликвидность"),
    ("uniswap-v2", "uniswap-v3"),
    ("llama-3-1", "llama-3-2"),
]


def test_g5_NO_SCALAR_CUTOFF_EXISTS_which_is_why_the_gate_is_ADVISORY() -> None:
    """★★★ THE TEST THAT KILLED THE REFUSAL. **DO NOT "FIX" THIS BY NUDGING THE CUTOFF.**

    Each pair below is a pair of DIFFERENT concepts that the metric scores AT OR ABOVE
    0.88. They are not edge cases — they are the ordinary vocabulary of the operator's
    domains. Under the first cut of TASK 064 every one of them was REFUSED, and the
    refusal was BATCH-FATAL: three good new concepts, all lost, zero pages written.

    And the true/false bands are INVERTED, which is the finding that settles it: the
    tightest false positive (0.960) is HIGHER than the real live duplicate the gate exists
    for (0.927). No scalar can separate them, at any value. A better constant is not
    available; a better KEY would be a different task.

    So the mechanism ADVISES. `near_duplicate_warnings` returns warnings and RAISES
    NOTHING — that is asserted directly here, because a future author "restoring" the
    refusal would otherwise only be caught by the operator's vault.
    """
    def ratio(a: str, b: str) -> float:
        return difflib.SequenceMatcher(None, _dup_key(a), _dup_key(b)).ratio()

    for a, b in _FALSELY_REFUSED:
        assert ratio(a, b) >= NEAR_DUP_CUTOFF, (
            f"{a}/{b} scored {ratio(a, b):.3f} — if this pair is now BELOW the cutoff the "
            f"key changed; re-derive the whole table before touching the gate's severity")

    worst_false_positive = max(ratio(a, b) for a, b in _FALSELY_REFUSED)
    real_duplicate = ratio("бессрочный-фьючерс", "бессрочные-фьючерсы")
    assert worst_false_positive > real_duplicate, (
        "the bands have separated — but do NOT re-promote the gate to a refusal on that "
        "basis alone: re-run the FULL false-positive census first (negating prefixes, "
        "version suffixes, inverse operations), because this list is a sample, not a "
        "population")

    # ★ THE MECHANISM, PINNED: it RETURNS, it does not RAISE. A refusal here would (a)
    # block correct work and (b) — far worse — instruct a compliant model to file a
    # DIFFERENT concept as a MENTION of the near-match, writing a FALSIFIED provenance
    # receipt into `page_entity_refs` at exit 0.
    warnings = near_duplicate_warnings(
        [_cand(slug="децентрализация", name="Децентрализация")],
        build_dup_keys({"централизация"}))
    assert warnings and warnings[0]["code"] == "NEAR_DUPLICATE_SLUG"
    assert "централизация" in warnings[0]["nearest"]


def test_g5_no_advisory_text_anywhere_instructs_a_merge() -> None:
    """★★ THE ADVISORY MUST NOT SAY WHAT THE REFUSAL SAID.

    The old refusal reason told the model its candidate *"will be filed as a MENTION of
    the page that is already there, which is what you want"*. A compliant model reading
    that about `decentralized-exchange` vs `centralized-exchange` DOES IT — and writes a
    provenance receipt claiming the source discussed a concept it never mentioned. **The
    anti-duplicate gate manufactured false knowledge.** The advisory must state BOTH
    branches and command NEITHER.
    """
    warnings = near_duplicate_warnings(
        [_cand(slug="serialization", name="Serialization")],
        build_dup_keys({"deserialization"}))
    advice = warnings[0]["advice"].lower()
    assert "if yours is the same concept" in advice
    assert "if it is a different concept" in advice
    for banned in ("which is what you want", "do not mint", "re-emit the candidate with "
                   "the exact existing slug"):
        assert banned not in advice, (
            f"the advisory COMMANDS a merge ({banned!r}) — that is the refusal's text, and "
            f"obeying it on an antonym pair writes a falsified provenance receipt")


def test_g5_near_duplicate_WARNS_at_exit_0_and_still_files_the_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """★ ADVISORY, END TO END: exit 0, the page IS written, and `warnings[]` names the slug
    to reuse if — and only if — the model judges it the same concept.

    The `nearest[]` payload is the actionable half: a model that agrees re-emits with the
    existing slug, `classify_candidates` files a `mention`, and the existing page gains a
    source in its `BEGIN-AUTO:mentions` ledger. A model that disagrees (an inverse, a
    negation, a different version) ignores it and loses nothing.
    """
    root, db, source_hash, src = _seed(tmp_path)
    (root / "_concepts").mkdir(parents=True, exist_ok=True)
    (root / "_concepts/бессрочный-фьючерс.md").write_text(
        "---\ntype: concept\n---\n# Бессрочный фьючерс\n", encoding="utf-8")

    rc, env = _apply(
        monkeypatch, capsys,
        [_cand(slug="бессрочные-фьючерсы", name="Бессрочные фьючерсы")],
        root=root, db=db, src=src, source_hash=source_hash)

    assert rc == 0, f"the near-duplicate check must ADVISE, never refuse: {env}"
    warn = env["warnings"][0]
    assert warn["code"] == "NEAR_DUPLICATE_SLUG"
    assert warn["slug"] == "бессрочные-фьючерсы"
    assert "бессрочный-фьючерс" in warn["nearest"], (
        "the advisory must hand back the EXACT slug to reuse — that is the whole payload")
    # The page IS filed. Refusing it would have destroyed correct work.
    assert (root / "_concepts/бессрочные-фьючерсы.md").is_file()


def test_g5_a_clean_run_carries_no_empty_warnings_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The overwhelmingly common run has nothing to advise. `warnings: []` on every clean
    envelope is noise that trains the reader to skip the key."""
    root, db, source_hash, src = _seed(tmp_path)
    rc, env = _apply(monkeypatch, capsys, [_cand()],
                     root=root, db=db, src=src, source_hash=source_hash)
    assert rc == 0 and "warnings" not in env


def test_g5_advice_is_surfaced_by_PREPARE_where_it_is_actionable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """★ THE ADVICE IS ONLY ACTIONABLE **BEFORE** AUTHORING.

    Told at `apply` time that your slug resembles an existing one, the cheapest fix is a
    round-trip. Told at `prepare` time, you simply reuse the existing slug and the vault
    COMPOUNDS instead of splitting. `dup_key` is the part a model cannot derive for itself:
    `виталик-бутерин` and `vitalik-buterin` are 100% dissimilar as strings and IDENTICAL as
    keys — the operator's most expensive live split.
    """
    root, db, _h, src = _seed(tmp_path, layout="obsidian-personal", vault_id="pvault",
                              note_rel=_PARA_NOTE)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO entities(vault_id, slug, name, type, is_candidate, "
            "first_seen, last_updated, file_path) VALUES (?,?,?,?,?,?,?,?)",
            ("pvault", "виталик-бутерин", "Виталик Бутерин", "person", 1, "2026-07-14",
             "2026-07-14", "_concepts/виталик-бутерин.md"))
        conn.commit()
    finally:
        conn.close()

    rc = wec.main([
        "prepare", "--vault", "pvault", "--vault-root", str(root),
        "--source-page", src, "--db-path", str(db),
    ])
    env = json.loads(capsys.readouterr().out)
    assert rc == 0, env
    assert "near_duplicate_advice" in env
    assert "will not refuse" in env["near_duplicate_advice"], (
        "prepare must tell the model the check is ADVISORY — a model that believes apply "
        "will catch its duplicates stops checking `known_concepts` itself, and apply won't")
    known = {e["slug"]: e for e in env["known_concepts"]}
    assert known["виталик-бутерин"]["dup_key"] == "vitalik-buterin", (
        "the transliterated key is the ONE thing a model cannot compute for itself")


def test_g5_exact_match_is_not_a_near_duplicate_ghost_row_self_heal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """★ TASK 053 / R3 — THE SELF-HEAL MUST SURVIVE G5 AND G7.

    Ghost row = the entity row is in the DB but its `_concepts/<slug>.md` was DELETED on
    disk. The rail is supposed to RE-CREATE the page. Two ways TASK 064 could have
    broken that, both closed here:

      * G5 comparing the candidate against ITSELF would score 1.000 and refuse the very
        repair the classifier just asked for. (Hence the `k != slug` skip: an EXACT
        match is not a NEAR-duplicate.)
      * G7 keys `mention` off PRESENCE ON DISK — and the ghost's page is NOT present, so
        it still classifies `create`. The intersection was never what made R3 work;
        PRESENCE was.
    """
    root, db, source_hash, src = _seed(tmp_path)
    # A known entity row whose page does NOT exist on disk (the ghost).
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO entities(vault_id, slug, name, type, is_candidate, "
            "first_seen, last_updated, file_path) VALUES (?,?,?,?,?,?,?,?)",
            ("kvault", "sharpe-ratio", "Sharpe Ratio", "concept", 1, "2026-07-14",
             "2026-07-14", "_concepts/sharpe-ratio.md"))
        conn.commit()
    finally:
        conn.close()
    assert not (root / "_concepts/sharpe-ratio.md").exists()

    rc, env = _apply(monkeypatch, capsys, [_cand()],
                     root=root, db=db, src=src, source_hash=source_hash)
    assert rc == 0, f"the ghost-row self-heal regressed: {env}"
    assert [w["slug"] for w in env["written"]] == ["sharpe-ratio"], (
        "a known slug whose page is GONE must reclassify `create` and self-heal")
    assert (root / "_concepts/sharpe-ratio.md").is_file()


# =========================================================================== #
# G6 — IN_BATCH_SLUG_COLLISION
# =========================================================================== #

def test_g6_in_batch_slug_collision_refused() -> None:
    """`classify_candidates` dedups only against the KNOWN set, so two candidates sharing
    a slug BOTH classify `create`; the second `write_concept_page` sees different bytes
    and silently overwrites the first.

    ★ One file, one row, one concept gone — and **ZERO lint issues, because the count is
    right.** "Last one wins" does not show up in lint. That is precisely why it needs its
    own gate. Zero false positives: two candidates with the same slug are never both
    wanted.
    """
    with pytest.raises(ExtractionParseError) as ei:
        wec.check_in_batch_collisions([
            _cand(),
            _cand(name="Sharpe Ratio (annualised)",
                  definition=_DEFINITION + " Annualised."),
        ])
    assert ei.value.error == "IN_BATCH_SLUG_COLLISION"
    assert ei.value.violations is not None
    assert ei.value.violations[0]["slug"] == "sharpe-ratio"
    assert ei.value.violations[0]["indices"] == [0, 1]


def test_g6_collision_gate_is_wired_into_apply_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The leaf raising is not enough — it has to be WIRED, and it has to be wired BEFORE
    the write loop."""
    root, db, source_hash, src = _seed(tmp_path)
    rc, env = _apply(
        monkeypatch, capsys,
        [_cand(), _cand(name="Sharpe Ratio Two",
                        definition=_DEFINITION + " A second, different definition.")],
        root=root, db=db, src=src, source_hash=source_hash)
    assert rc == 4 and env["error"] == "IN_BATCH_SLUG_COLLISION"
    assert _concept_files(root) == []


# =========================================================================== #
# G7 — NEVER overwrite an existing concept page
# =========================================================================== #

def test_g7_existing_page_without_entity_row_is_a_mention_not_an_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """★★ DATA LOSS REPORTED AS SUCCESS — the bug this gate exists for.

    `effective_known` was `known_entity_rows ∩ present_concept_files`. The INVERSE case —
    page ON DISK, entity row ABSENT (a hand-authored page; a rebuilt DB; a stale index) —
    fell OUTSIDE the intersection, classified `create`, and `write_concept_page`
    OVERWROTE THE HUMAN'S PAGE with the model's definition: `logger.warning`, exit 0.

    A page on disk is now ALWAYS a `mention`. The operator's bytes survive verbatim.
    """
    root, db, source_hash, src = _seed(tmp_path)
    concepts = root / "_concepts"
    concepts.mkdir(parents=True, exist_ok=True)
    hand_authored = concepts / "sharpe-ratio.md"
    original = (
        "---\ntype: concept\n---\n# Sharpe Ratio\n\n"
        "MY OWN careful definition, written by a human, with nuance the model lacks.\n"
    )
    hand_authored.write_text(original, encoding="utf-8")

    rc, env = _apply(monkeypatch, capsys, [_cand()],
                     root=root, db=db, src=src, source_hash=source_hash)

    assert rc == 0, env
    assert hand_authored.read_text(encoding="utf-8") == original, (
        "the model's definition OVERWROTE a hand-authored concept page")
    assert [m["slug"] for m in env["mentioned"]] == ["sharpe-ratio"]
    assert env["written"] == []


def test_g7_existing_page_missing_entity_row_is_healed_in_the_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The other half of G7: classifying the page a `mention` must not leave it INVISIBLE.

    With no `entities` row, the concept is unreachable from `wiki-search`/`wiki-graph`
    until someone runs a full reindex. So the row is HEALED from the candidate.

    (Verified against `sql/wiki-index-v2.sql`: `page_entity_refs` FKs to **`pages`**, NOT
    to `entities` — so this heal is CORRECTNESS, not crash-avoidance. The contract said
    to check the FK direction before writing it; the check says the heal is optional and
    right, not mandatory.)
    """
    root, db, source_hash, src = _seed(tmp_path)
    concepts = root / "_concepts"
    concepts.mkdir(parents=True, exist_ok=True)
    (concepts / "sharpe-ratio.md").write_text(
        "---\ntype: concept\n---\n# Sharpe Ratio\n\nHand-authored.\n", encoding="utf-8")

    conn = sqlite3.connect(db)
    try:
        assert conn.execute(
            "SELECT count(*) FROM entities WHERE vault_id='kvault' AND slug='sharpe-ratio'"
        ).fetchone()[0] == 0
    finally:
        conn.close()

    rc, _env = _apply(monkeypatch, capsys, [_cand()],
                      root=root, db=db, src=src, source_hash=source_hash)
    assert rc == 0

    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            "SELECT slug, file_path FROM entities WHERE vault_id='kvault' AND "
            "slug='sharpe-ratio'").fetchone()
    finally:
        conn.close()
    assert row is not None, (
        "the missing entities row was not healed — the concept stays invisible to "
        "wiki-search until a full reindex")
    assert row[1] == "_concepts/sharpe-ratio.md"


def test_g7_write_concept_page_refuses_to_clobber_a_differing_page(
    tmp_path: Path,
) -> None:
    """The BELT. The caller now classifies any on-disk page a `mention`, so this should
    never fire — but "should never fire" is not an argument for silently destroying a
    file when it does. `write_concept_page` used to return `"updated"` here (atomic
    rewrite + a log line). It now REFUSES.

    ★ This test REPLACES the old `"updated"` unit test, which asserted the overwrite was
    correct behaviour. Precedent: `wiki-import` already refuses this
    (`_authoring.py` `collides-existing-page`).
    """
    root = tmp_path / "vault"
    (root / "_concepts").mkdir(parents=True)
    target = root / "_concepts/sharpe-ratio.md"
    target.write_text("---\ntype: concept\n---\n# Sharpe Ratio\n\nDifferent.\n",
                      encoding="utf-8")
    before = target.read_bytes()

    with pytest.raises(ExtractionParseError) as ei:
        wec.write_concept_page(
            root, _cand(), "sample-doc", datetime(2026, 7, 14).date(), vault_id="kvault")
    assert ei.value.error == "CONCEPT_PAGE_EXISTS"
    assert target.read_bytes() == before, "the refusal still clobbered the file"
    # CWE-209: the envelope names the model's own slug, never the operator's abs path.
    assert str(root) not in (ei.value.reason or "")


def test_g7_identical_content_is_still_unchanged_not_a_refusal(tmp_path: Path) -> None:
    """The idempotency path must survive: byte-identical content → `unchanged`, NOT
    `CONCEPT_PAGE_EXISTS`. A gate that refuses a no-op re-run would break every retry."""
    root = tmp_path / "vault"
    (root / "_sources").mkdir(parents=True)
    _target, action = wec.write_concept_page(
        root, _cand(), "sample-doc", datetime(2026, 7, 14).date(), vault_id="kvault")
    assert action == "created"
    _target2, action2 = wec.write_concept_page(
        root, _cand(), "sample-doc", datetime(2026, 7, 14).date(), vault_id="kvault")
    assert action2 == "unchanged"


# =========================================================================== #
# G8 — the slug is DERIVED from the name BY THE LAYOUT
# =========================================================================== #

def test_g8_prepare_emits_the_layout_contract(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """`prepare`'s envelope carried 7 keys and NOT ONE WORD about the layout — so the
    REASON step had to GUESS how this vault turns a NAME into a SLUG, and the SKILL told
    it to guess ASCII. A contract that omits the rule the caller is judged against is not
    a contract."""
    root, db, _h, src = _seed(tmp_path, layout="obsidian-personal", vault_id="pvault",
                              note_rel=_PARA_NOTE)
    rc = wec.main([
        "prepare", "--vault", "pvault", "--vault-root", str(root),
        "--source-page", src, "--db-path", str(db),
    ])
    env = json.loads(capsys.readouterr().out)
    assert rc == 0, env
    assert env["slug_strategy"] == "preserve-unicode"
    assert env["layout"] == "obsidian-personal"


def test_g8_ascii_slug_for_a_cyrillic_name_is_refused_on_a_unicode_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """★ THE LIVE `виталик-бутерин` / `vitalik-buterin` SPLIT, REPRODUCED.

    On the operator's `obsidian-personal` (preserve-unicode, Russian) vault, a model
    obeying the SKILL's ASCII slug regex emits `vitalik-buterin` for «Виталик Бутерин» —
    while every inbound `[[Виталик Бутерин]]` in the vault resolves, through the SAME
    slug_strategy, to `виталик-бутерин`. The page is written and NOTHING EVER LINKS TO
    IT. Both slugs are live in his vault today.

    The refusal carries the DERIVED slug so the model can just re-send it.
    """
    body = (
        "---\ntype: summary\ntitle: Заметка\n---\n\n"
        "Виталик Бутерин — сооснователь Эфириума и автор его первоначальной "
        "спецификации.\n"
    )
    root, db, source_hash, src = _seed(
        tmp_path, layout="obsidian-personal", vault_id="pvault", body=body,
        note_rel=_PARA_RU_NOTE)
    quote = ("Виталик Бутерин — сооснователь Эфириума и автор его первоначальной "
             "спецификации.")
    cand = _cand(
        slug="vitalik-buterin",  # what a model obeying the (false) ASCII doc emits
        name="Виталик Бутерин",
        definition="Сооснователь Эфириума, автор его первоначальной спецификации и "
                   "один из авторов концепции смарт-контрактов.",
        source_quote=quote, source_span="L6-L6",
    )
    rc, env = _apply(monkeypatch, capsys, [cand], root=root, db=db, src=src,
                     source_hash=source_hash, vault="pvault")
    assert rc == 4
    assert env["error"] == "SLUG_NOT_DERIVED_FROM_NAME"
    assert env["violations"][0]["derived_slug"] == "виталик-бутерин"
    assert _concept_files(root) == []


def test_g8_the_derived_slug_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The repair loop closes: re-emit with `derived_slug` → the page files, in Cyrillic,
    where the vault's wikilinks will actually find it."""
    body = (
        "---\ntype: summary\ntitle: Заметка\n---\n\n"
        "Виталик Бутерин — сооснователь Эфириума и автор его первоначальной "
        "спецификации.\n"
    )
    root, db, source_hash, src = _seed(
        tmp_path, layout="obsidian-personal", vault_id="pvault", body=body,
        note_rel=_PARA_RU_NOTE)
    cand = _cand(
        slug="виталик-бутерин", name="Виталик Бутерин",
        definition="Сооснователь Эфириума, автор его первоначальной спецификации и "
                   "один из авторов концепции смарт-контрактов.",
        source_quote=("Виталик Бутерин — сооснователь Эфириума и автор его "
                      "первоначальной спецификации."),
        source_span="L6-L6",
    )
    rc, env = _apply(monkeypatch, capsys, [cand], root=root, db=db, src=src,
                     source_hash=source_hash, vault="pvault")
    assert rc == 0, env
    assert (root / "05 - Материалы/Тема/_concepts/виталик-бутерин.md").is_file()


def test_g8_karpathy_identity_layout_skips_the_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """★ THE `identity` CARVE-OUT, AND WHY IT IS NOT A HOLE.

    Under karpathy, `slug_strategy: identity` means the FILE STEM *is* the slug. There is
    no name→slug function to check against: `_apply_slug_strategy("Sharpe Ratio",
    "identity")` returns `"Sharpe Ratio"`, which is not a slug at all — asserting
    `slug == that` would refuse EVERY karpathy candidate ever written.

    The bug G8 kills is a WIKILINK-RESOLUTION bug on the SLUGIFYING layouts. On karpathy
    links to concepts are written AS the slug, so the failure mode does not arise; and
    the residual risk (a slug that renders its name poorly) is caught by G5 the moment a
    second variant shows up.
    """
    root, db, source_hash, src = _seed(tmp_path)  # karpathy
    rc, env = _apply(monkeypatch, capsys, [_cand()], root=root, db=db, src=src,
                     source_hash=source_hash)
    assert rc == 0, env
    assert (root / "_concepts/sharpe-ratio.md").is_file()


@pytest.mark.parametrize(
    "slug", ["block_number", "row_number", "erc20_ethereum-evt_transfer"])
def test_g8_underscore_slug_refused(slug: str) -> None:
    """`_SLUG_RE`'s `[\\w-]` tail ADMITS `_`, and `preserve-unicode`'s slugify regex
    (`[^\\w\\-]`) KEEPS an underscore that is already there — so NEITHER gate stopped it.
    That is how `block_number`, `row_number` and `erc20_ethereum-evt_transfer` became
    "concepts" in the operator's vault: they are SCHEMA COLUMNS and CODE SYMBOLS, and the
    underscore is the tell. No layout slug-strategy emits `_`."""
    with pytest.raises(ExtractionParseError) as ei:
        _validate_candidates_schema([_cand(slug=slug)], source_body=_BODY)
    assert ei.value.error == "INVALID_SLUG_CHARSET"
    assert ei.value.field == "slug"


# =========================================================================== #
# G9 — the source_span is **DERIVED**, not verified (TASK 066)
#
# ★★ THE CONTRACT CHANGED, AND A MEASUREMENT CHANGED IT.
#
# G9 used to REFUSE a bad span. It now DERIVES the right one and ignores what the model
# said. The reason is in `skills/concept-extraction/evals/baseline.json`: 33 fresh Haiku
# contexts, 56 candidates —
#
#     source_quote VERBATIM in the body     56/56  (100%)   ← the anti-fabrication gate WORKS
#     the model's source_span is CORRECT    40/56  ( 71%)   ← it is COUNTING LINES, and failing
#     the span is DERIVABLE from the quote  56/56  (100%)
#
# NINE of thirteen failing runs were a bad span — the largest failure class, hitting 8 of 11
# fixtures. We were asking a LANGUAGE MODEL to do ARITHMETIC ON LINE NUMBERS, and then
# refusing the WHOLE BATCH when it got the arithmetic wrong. The concepts were right. The
# quotes were right. The counting was not.
#
# ★ DERIVATION IS STRICTLY STRONGER THAN THE CHECK IT REPLACES. G9 existed because the span
# was an honour system — `L9999-L9999` on a 3-line body was written into `page_entity_refs`
# AS IF IT WERE PROVENANCE. A DERIVED span cannot be fabricated: it is computed from a quote
# that is itself proven verbatim. **The attack is not detected — it is UNREACHABLE.**
#
# Every property the old tests protected is asserted below, against the new mechanism.
# =========================================================================== #

def test_g9_an_out_of_range_span_is_CORRECTED_never_written() -> None:
    """★ THE OLD BUG (`L9999-L9999` into `page_entity_refs` as provenance) is now
    UNREACHABLE — and the fix costs the operator NOTHING, where the old gate cost them the
    entire batch.

    The fabricated span does not reach the DB, and the candidate is not refused: it is
    written with the TRUE span. Both halves are asserted — a fix that silently dropped the
    candidate would pass the first half alone.
    """
    batch = [_cand(source_span="L9999-L9999")]
    _validate_candidates_schema(batch, source_body=_BODY)
    out = batch
    assert out[0]["source_span"] == "L8-L8", (
        "the fabricated span must be REPLACED by the derived one, not merely rejected")


def test_g9_a_span_that_misses_the_quote_is_CORRECTED() -> None:
    """The span must point AT the quote — and now it does BY CONSTRUCTION. L2 is
    `type: summary`; the quote is on L8. The model's L2 is discarded."""
    batch = [_cand(source_span="L2-L2")]
    _validate_candidates_schema(batch, source_body=_BODY)
    out = batch
    assert out[0]["source_span"] == "L8-L8"


def test_g9_the_span_is_OPTIONAL_and_the_model_need_not_count_at_all() -> None:
    """★★ THE POINT OF THE WHOLE CHANGE. A candidate with NO `source_span` is valid — the
    model is no longer asked to count lines, which is the thing it cannot do."""
    cand = _cand()
    del cand["source_span"]
    batch = [cand]
    _validate_candidates_schema(batch, source_body=_BODY)
    out = batch
    assert out[0]["source_span"] == "L8-L8"


def test_g9_line_one_is_the_files_first_line_including_frontmatter() -> None:
    """★ THE LINE ORIGIN, STILL PINNED — the derivation must produce the SAME semantics the
    old gate enforced, or every span in the vault silently shifts by the frontmatter's height.

    `source_body` is the WHOLE FILE as read, so **L1 is the opening `---`.** The prose quote
    is on **L8**, not L4 (where it would be if the origin were the first line of prose).
    """
    assert len(_BODY.splitlines()) == 10
    cand = _cand()
    del cand["source_span"]
    batch = [cand]
    _validate_candidates_schema(batch, source_body=_BODY)
    out = batch
    assert out[0]["source_span"] == "L8-L8", (
        "the line origin shifted — every span in the vault would move with it")

    # ...and the LAST line of the file derives correctly too (an off-by-one at the tail is
    # the classic way a line-origin fix breaks the far end).
    tail = _cand(
        slug="perpetual-future", name="Perpetual Future",
        definition="A derivative contract that never expires, held open "
                   "indefinitely via a periodic funding payment.",
        source_quote="A perpetual future is a derivative contract with no expiry date.",
    )
    del tail["source_span"]
    batch = [tail]
    _validate_candidates_schema(batch, source_body=_BODY)
    out = batch
    assert out[0]["source_span"] == "L10-L10"


# --------------------------------------------------------------------------- #
# ★★ F5 — THE FORM FEED. `split("\n")`, NEVER `splitlines()`.
# --------------------------------------------------------------------------- #

# A PDF→markdown source: `\x0c` (FORM FEED) is the page break, and it is a ROUTINE
# artifact of that conversion. `wiki-import` IS this repo's PDF on-ramp, so this is not a
# hypothetical body — it is the shape of the sources this rail is actually fed.
_FF_BODY = ("---\ntitle: Дюна\n---\n\n"
            "Первая страница PDF заканчивается здесь.\n"
            "\x0cСтавка финансирования удерживает цену контракта у спота.\n")

_FF_QUOTE = "Ставка финансирования удерживает цену контракта у спота."


def test_g9_form_feed_the_DERIVED_span_counts_lines_the_way_every_tool_counts_them() -> None:
    """★★ F5 SURVIVES THE REWRITE — and it matters MORE now, not less.

    `str.splitlines()` breaks on `\x0b \x0c \x1c \x1d \x1e \x85 U+2028 U+2029`. EVERY tool a
    human or a model counts lines with — the Read tool, `cat -n`, an editor, `wc -l` — breaks
    on `\n` and nothing else. On `_FF_BODY` the two disagree:

        split("\n")   → the quote is on **L6**   ← what the operator SEES in their editor
        splitlines()  → the quote is on **L7**

    Under the OLD gate a `splitlines()` bug REFUSED the correct span. Under the NEW one it
    would WRITE THE WRONG SPAN INTO THE VAULT, silently, on every PDF-derived source — and
    nobody would ever be refused, so nobody would ever look. **The regression got quieter,
    so the test got more important.**
    """
    # the two splitters genuinely disagree on this body — the premise, asserted
    assert _FF_BODY.split("\n").index("\x0c" + _FF_QUOTE) + 1 == 6
    assert _FF_BODY.splitlines().index(_FF_QUOTE) + 1 == 7

    ff_cand = _cand(
        slug="ставка-финансирования", name="Ставка финансирования",
        definition="периодический платёж между лонгами и шортами.",
        source_quote=_FF_QUOTE,
    )
    del ff_cand["source_span"]

    batch = [ff_cand]
    _validate_candidates_schema(batch, source_body=_FF_BODY)
    out = batch
    assert out[0]["source_span"] == "L6-L6", (
        "the derived span used splitlines() — on every PDF-derived source the vault would "
        "now carry a span that disagrees with `cat -n`, and NOTHING would refuse it")


def test_g9_a_supplied_span_is_only_a_HINT_and_never_overrides_the_truth() -> None:
    """A supplied span cannot make the rail write a lie. It disambiguates a repeated quote;
    it does not get to be wrong.

    (The old `SOURCE_SPAN_OUT_OF_RANGE` case — a span past the end of a form-feed body —
    is simply overwritten. There is no range left to be out of.)
    """
    ff_cand = _cand(
        slug="ставка-финансирования", name="Ставка финансирования",
        definition="периодический платёж между лонгами и шортами.",
        source_quote=_FF_QUOTE, source_span="L8-L8",   # past the end of the body
    )
    batch = [ff_cand]
    _validate_candidates_schema(batch, source_body=_FF_BODY)
    out = batch
    assert out[0]["source_span"] == "L6-L6"


def test_g9_the_HINT_picks_between_TWO_occurrences_of_the_same_quote() -> None:
    """★ The one job a supplied span still has. The same sentence appears twice; the hint
    says which one. With no hint the FIRST occurrence wins — still true provenance, because
    the quote really is there."""
    quote = "Ставка финансирования удерживает цену контракта у спота."
    body = ("---\ntitle: t\n---\n"          # L1-L3
            f"{quote}\n"                     # L4  ← first occurrence
            "Между ними другой текст.\n"      # L5
            f"{quote}\n")                    # L6  ← second
    cand = _cand(
        slug="ставка-финансирования", name="Ставка финансирования",
        definition="периодический платёж между лонгами и шортами.",
        source_quote=quote,
    )
    del cand["source_span"]

    # no hint → the first occurrence
    b1 = [dict(cand)]
    _validate_candidates_schema(b1, source_body=body)
    assert b1[0]["source_span"] == "L4-L4"

    # a hint pointing at the second → the second
    b2 = [{**cand, "source_span": "L6-L6"}]
    _validate_candidates_schema(b2, source_body=body)
    assert b2[0]["source_span"] == "L6-L6"


# =========================================================================== #
# G10 — refuse to write concepts a layout cannot SEE
# =========================================================================== #

def test_g10_layout_that_cannot_index_concepts_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """★ INVISIBLE PAGES — TASK 063's G4 lesson, unrepaired on this rail until now.

    `apply` wrote to a hardcoded `_concepts` dir on EVERY layout — including
    `dev-project`, which maps no `concept` type and whose read globs never reach a
    `_concepts/` sibling. The pages were written, never discovered by `iter_pages`, never
    indexed, and never linted.

    ★ A PAGE THE WALKER CANNOT SEE IS A PAGE `wiki-lint` IS *STRUCTURALLY INCAPABLE* OF
    REPORTING. Refusing costs the operator one message; not refusing costs them a
    directory of files they will never find again.
    """
    root, db, source_hash, src = _seed(
        tmp_path, layout="dev-project", vault_id="dvault", index=False,
        note_rel="tasks/sample-doc.md")
    rc, env = _apply(monkeypatch, capsys, [_cand()], root=root, db=db, src=src,
                     source_hash=source_hash, vault="dvault")
    assert rc == 4
    assert env["error"] == "LAYOUT_CANNOT_INDEX_CONCEPTS"
    assert env["layout"] == "dev-project"
    assert _concept_files(root) == [], "invisible pages were written anyway"


def test_g10_concept_capable_layout_passes_the_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The gate must not fire on a layout that CAN index concepts — obsidian-personal
    maps a `concept` type and globs `_concepts/**/*.md`."""
    root, db, source_hash, src = _seed(
        tmp_path, layout="obsidian-personal", vault_id="pvault",
        note_rel=_PARA_NOTE)
    rc, env = _apply(monkeypatch, capsys, [_cand()], root=root, db=db, src=src,
                     source_hash=source_hash, vault="pvault")
    assert rc == 0, env
    assert (root / "05 - Материалы/Тема/_concepts/sharpe-ratio.md").is_file()


# =========================================================================== #
# ★ THE ZERO-FILE INVARIANT — a refusal writes NOTHING, and the pre-DB gates
#   never even OPEN the database
# =========================================================================== #

# Every pre-DB refusal: it must be impossible to reach `make_repo`.
_PRE_DB_REFUSALS: list[tuple[str, dict[str, Any]]] = [
    ("FIELD_TOO_SHORT", _cand(definition="")),
    ("DEFINITION_IS_QUOTE", _cand(definition=_QUOTE)),
    ("DEFINITION_NOT_PROSE",
     _cand(definition="A risk measure. See [[write-ahead-log]] for the storage "
                      "concept it is related to.")),
    ("FIELD_QUOTE_NOT_IN_BODY",
     _cand(source_quote="Never appears in this body at all, not even once.")),
    ("ENTITY_TYPE_NOT_ALLOWED", _cand(entity_type="person")),
    ("INVALID_SLUG_CHARSET", _cand(slug="block_number")),
    # ⚠️ `SOURCE_SPAN_OUT_OF_RANGE` and `SOURCE_SPAN_QUOTE_MISMATCH` were HERE until TASK 066.
    # They are now UNREACHABLE FROM CANDIDATE INPUT — the span is DERIVED, so there is no
    # candidate a caller can write that makes the rail refuse on one.
    #
    # ★ Removing a row from a refusal roster is EXACTLY how a gate silently shrinks. So the
    # removal is not silent: `test_the_SPAN_REFUSALS_are_UNREACHABLE_not_merely_untested`
    # below PROVES the two codes cannot be provoked, rather than leaving them merely absent.
]


def test_the_SPAN_REFUSALS_are_UNREACHABLE_not_merely_untested() -> None:
    """★ THE ROSTER SHRANK BY TWO, AND THIS IS THE PROOF THAT IT WAS SAFE.

    A row quietly deleted from a refusal roster is a gate quietly deleted. So the two span
    refusals are not merely *removed* — they are shown to be **unprovokable**: the span is
    DERIVED, so the worst input a caller can write is CORRECTED, not refused.

    The old attack — `L9999-L9999` on a 10-line body, written into `page_entity_refs` as if
    it were provenance — is not *caught* here. It is **impossible**.

    ⚠️ What IS still reachable, and must stay so: a supplied span that is not `Lx-Ly` at all.
    A malformed hint is a caller bug, and silently ignoring it would be the fail-open this
    repo keeps having to close.
    """
    for span in ("L9999-L9999", "L2-L2", "L1-L1"):
        batch = [_cand(source_span=span)]
        _validate_candidates_schema(batch, source_body=_BODY)      # no raise
        assert batch[0]["source_span"] == "L8-L8", (
            f"a candidate carrying {span!r} must be CORRECTED to the truth")

    # a MALFORMED hint is still refused — the fail-open stays closed
    with pytest.raises(ExtractionParseError) as ei:
        _validate_candidates_schema(
            [_cand(source_span="line 8")], source_body=_BODY)
    assert ei.value.field == "source_span"


@pytest.mark.parametrize(
    ("code", "cand"), _PRE_DB_REFUSALS, ids=[c for c, _ in _PRE_DB_REFUSALS])
def test_zero_file_and_db_never_opened_on_a_pre_db_refusal(
    code: str, cand: dict[str, Any], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """★ ZERO-FILE, BY CONSTRUCTION — NOT BY CARE.

    `_apply_validate` runs BEFORE `make_repo`, so every one of these refusals is a
    guaranteed zero-file, DB-never-opened no-op. This asserts the STRUCTURE, not just the
    outcome: `make_repo` is replaced with a landmine. If a future gate is placed after
    the DB opens, this fails loudly rather than eroding the property quietly.
    """
    root, db, source_hash, src = _seed(tmp_path)

    def _landmine(*a: Any, **k: Any) -> Any:
        raise AssertionError(
            f"{code} opened the DB — a contract violation must be a DB-never-opened "
            f"no-op (the gate belongs before `make_repo`)")

    monkeypatch.setattr(wec, "make_repo", _landmine)
    rc, env = _apply(monkeypatch, capsys, [cand], root=root, db=db, src=src,
                     source_hash=source_hash)
    assert rc == 4
    assert env["error"] == code
    assert _concept_files(root) == []


@pytest.mark.parametrize(
    ("code", "seed"),
    [
        # F6 — the candidate takes the SOURCE NOTE's own slug and would EVICT it from
        # `pages` (UNIQUE(vault_id, slug, project)). Needs the DB, so it cannot be a
        # pre-DB gate; it must still be zero-file.
        ("SLUG_COLLIDES_WITH_PAGE", "sample-doc"),
    ],
)
def test_zero_file_on_the_post_db_gates(
    code: str, seed: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The DB-dependent gates CANNOT live in the pre-DB validator — they need what the
    vault already knows. They run in `_apply_write`, but still BEFORE the write loop, so
    they are still ZERO-FILE. `write_concept_page` is a landmine: it proves the raise
    unwinds before a single byte is written, rather than merely asserting the outcome.

    (G5 is NOT in this list any more — it no longer refuses at all. See
    `test_g5_NO_SCALAR_CUTOFF_EXISTS_which_is_why_the_gate_is_ADVISORY`.)
    """
    root, db, source_hash, src = _seed(tmp_path)

    def _landmine(*a: Any, **k: Any) -> Any:
        raise AssertionError(
            f"{code} reached the write loop — the refusal must unwind first")

    monkeypatch.setattr(wec, "write_concept_page", _landmine)
    rc, env = _apply(
        monkeypatch, capsys,
        [_cand(slug=seed, name="Sample Doc")],
        root=root, db=db, src=src, source_hash=source_hash)
    assert rc == 4 and env["error"] == code
    assert _concept_files(root) == []


# =========================================================================== #
# ★ CWE-117 / CWE-209 — the canary, walked RECURSIVELY
# =========================================================================== #

_CANARY = "SECRET_LEAK_CANARY_xyzzy_777"


def _walk(node: Any) -> list[str]:
    """Flatten every string in an arbitrarily nested envelope. `violations[]` is a LIST
    OF DICTS — a top-level `in json.dumps(...)` check would pass over a leak nested
    inside it, so the canary walk has to recurse or it is theatre."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for v in node.values() for s in _walk(v)]
    if isinstance(node, list):
        return [s for v in node for s in _walk(v)]
    return []


@pytest.mark.parametrize(
    ("code", "cand"), _PRE_DB_REFUSALS, ids=[c for c, _ in _PRE_DB_REFUSALS])
def test_canary_no_source_body_content_in_any_refusal_envelope(
    code: str, cand: dict[str, Any], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """CWE-117 / CWE-209: a refusal envelope NEVER echoes SOURCE-CONTENT values.

    The canary is planted in the SOURCE BODY (not in the candidate) — model-authored
    values (the candidate's own slug/name, the derived slug, the `nearest` list) ARE safe
    to echo and are deliberately echoed, because the repair loop needs them. Body content
    is not.

    Extends the existing matrix (`tests/test_wiki_extract_concepts.py`) with every code
    TASK 064 adds.
    """
    body = _BODY.replace("# Sample Doc", f"# Sample Doc {_CANARY}")
    root, db, source_hash, src = _seed(tmp_path, body=body)
    rc, env = _apply(monkeypatch, capsys, [cand], root=root, db=db, src=src,
                     source_hash=source_hash)
    assert rc == 4 and env["error"] == code
    for s in _walk(env):
        assert _CANARY not in s, f"{code} leaked source-body content: {s!r}"


def test_canary_near_duplicate_echoes_slugs_but_not_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """G5's `warnings[].nearest` is the one place this rail deliberately echoes
    vault-derived values — and it now does so in a SUCCESS envelope, which is exactly the
    envelope nobody thinks to audit. Pin BOTH halves: the slugs come back (the advice
    depends on it) and the body does not."""
    body = _BODY.replace("# Sample Doc", f"# Sample Doc {_CANARY}")
    root, db, source_hash, src = _seed(tmp_path, body=body)
    (root / "_concepts").mkdir(parents=True, exist_ok=True)
    (root / "_concepts/бессрочный-фьючерс.md").write_text(
        "---\ntype: concept\n---\n# X\n", encoding="utf-8")

    rc, env = _apply(
        monkeypatch, capsys,
        [_cand(slug="бессрочные-фьючерсы", name="Бессрочные фьючерсы")],
        root=root, db=db, src=src, source_hash=source_hash)
    assert rc == 0
    strings = _walk(env)
    assert any("бессрочный-фьючерс" in s for s in strings)   # the actionable advice
    for s in strings:
        assert _CANARY not in s                              # the CWE line


def test_canary_the_page_collision_refusal_leaks_no_absolute_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """F6's refusal names the VAULT-RELATIVE path of the page it would have evicted (the
    same shape the success envelope already emits in `written[].path`) — never the
    operator's absolute vault location (CWE-209), and never a byte of file content."""
    body = _BODY.replace("# Sample Doc", f"# Sample Doc {_CANARY}")
    root, db, source_hash, src = _seed(tmp_path, body=body)
    rc, env = _apply(monkeypatch, capsys, [_cand(slug="sample-doc", name="Sample Doc")],
                     root=root, db=db, src=src, source_hash=source_hash)
    assert rc == 4 and env["error"] == "SLUG_COLLIDES_WITH_PAGE"
    assert env["violations"][0]["occupied_by"] == "_sources/sample-doc.md"
    for s in _walk(env):
        assert str(root) not in s
        assert _CANARY not in s


def test_the_DERIVED_span_ALWAYS_contains_its_own_quote() -> None:
    """★★ THE UNIVERSAL INVARIANT — and it replaces a property that used to belong to ONE
    fixture's counterexample.

    Since TASK 066 the span is COMPUTED from the quote, so the guarantee is no longer
    *"a fabricated span is refused"* but the stronger *"no span can be fabricated at all."*
    That deserves to be asserted **everywhere**, not in one place:

        for EVERY fixture, for EVERY candidate (expected AND counterexample):
            the DERIVED span points AT the quote it was derived from.

    A fixture-specific gate protects a fixture. This protects the rail. And it fires on any
    future body shape — a form feed, a CRLF file, a quote spanning three lines — without
    anybody remembering to add a case.
    """
    import json
    import unicodedata

    evals = (Path(__file__).resolve().parents[1]
             / "skills" / "concept-extraction" / "evals")
    checked = 0
    for fixture in sorted(p for p in evals.iterdir() if (p / "input.md").is_file()):
        body = (fixture / "input.md").read_text(encoding="utf-8")
        for which in ("expected", "counterexample"):
            f = fixture / f"{which}.json"
            if not f.is_file():
                continue
            for item in json.loads(f.read_text(encoding="utf-8")):
                quote = item.get("source_quote")
                if not quote:
                    continue
                norm = lambda s: re.sub(                       # noqa: E731
                    r"\s+", " ", unicodedata.normalize("NFC", s)).strip().casefold()
                if norm(quote) not in norm(body):
                    continue                                   # a deliberately-bad quote
                span = derive_source_span(body, quote)
                start, end = (int(x[1:]) for x in span.split("-"))
                lines = body.split("\n")                       # NEVER splitlines() — F5
                assert 1 <= start <= end <= len(lines), (
                    f"{fixture.name}/{which}: derived {span} is outside a "
                    f"{len(lines)}-line body")
                assert norm(quote) in norm("\n".join(lines[start - 1:end])), (
                    f"{fixture.name}/{which}: the DERIVED span {span} does not contain the "
                    f"quote it was derived FROM — the derivation is broken")
                checked += 1

    assert checked >= 20, (
        f"the invariant examined only {checked} candidates — a sweep over an empty population "
        f"reports green, which is this project's signature failure mode")


def test_a_slug_match_with_a_DIFFERENT_name_WARNS_and_never_refuses() -> None:
    """★ THE CROSS-SOURCE `mention` HAZARD (DF-064-4 / M-1) — surfaced, never refused.

    `classify_candidates` files a candidate as a `mention` on **SLUG ALONE**, never on name — and
    a mention **DISCARDS the definition**. So «Падеж» (grammatical case), extracted from a LATER
    note into a vault that already owns `padezh` («Падёж» — mass death of livestock), is filed as
    **a mention of the livestock page**: a falsified provenance receipt, at exit 0, with a
    correct-looking count.

    ⚠️ IT IS A WARNING, NOT A REFUSAL — AND THE POPULATION IS WHY.

    Across the operator's **685 live entities**, the number of name-pairs that collapse onto one
    slug is **ZERO** under `preserve-unicode` AND **ZERO** under `transliterate`. A refusal here
    would be a gate that fires on nothing. And a refusal on a currently-exit-0 path is *exactly*
    how the 0.88 near-duplicate gate came to **block correct work** and had to be demoted — the
    lesson is one page away in this rail's own SKILL, and we are not learning it twice.

    MUT: delete the `_name_differs` branch ⇒ RED.
    """
    assert _name_differs("Падёж скота", "Грамматический падеж")
    # ...and it does NOT fire on the SAME name written differently — a warning that cried wolf
    # on every mention would be noise, and noise gets muted.
    assert not _name_differs("Идемпотентность", " идемпотентность ")
    assert not _name_differs("Slippage", "slippage")
    assert not _name_differs("", "Anything")            # an unnamed page cannot disagree
