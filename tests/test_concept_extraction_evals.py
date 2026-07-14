"""TASK 064 — the `concept-extraction` eval set, GRADED and TRI-LAYOUT.

★ AN EVAL WHOSE OWN EXPECTED OUTPUT THE RAIL WOULD REFUSE IS WORSE THAN NO EVAL: it teaches
the model a shape the code rejects, and it looks like coverage. So every `expected.json` is
fed through the REAL validators — the same `_validate_candidates_schema` /
`check_in_batch_collisions` / `check_slugs_derived_from_names` / `check_near_duplicate_slugs`
that `apply` runs, in the ORDER `apply` runs them.

★★ AND VALIDATING IS NOT ENOUGH — HERE MORE THAN ON ANY OTHER RAIL. The three rules that
matter most on this rail have **NO MECHANISM BEHIND THEM AT ALL**:

  * that a concept is WORTH a permanent page (`тултип`, `coalesce`, `block_number` pass every
    mechanical gate — and are real pages in the operator's live vault);
  * that a definition SAYS something (a confident tautology is schema-valid, lint-green,
    FTS-indexed, and gets cited by `wiki-query` as knowledge);
  * that the extraction did not DROP the concept that mattered (nothing counts absences).

So a validator-only eval on this rail would be **green over a source that produced seven junk
pages.** Every fixture therefore carries a CENSUS (`expect`) and a `forbidden` list, and the
counterexamples that no code can refuse are graded by census — with `graded_by_census_only`
saying so out loud. A fixture that pretended a mechanism existed would be worse than none.

★ THE FIXTURE POPULATION IS GLOBBED, NEVER HARDCODED. A `range(1, 12)` here is how fixture
#12 gets silently skipped.

★★ TRI-LAYOUT, AND THE THIRD LAYOUT IS NOT DECORATION. `identity` (karpathy) is the branch a
naive implementation breaks on: `_apply_slug_strategy("Проскальзывание", "identity")` returns
the NAME, verbatim — which `_is_valid_slug` REFUSES (uppercase, space). A runner that "derives
the slug from the name per layout" therefore cannot do so on karpathy at all, and a G8 that
asserted `slug == derived` there would refuse EVERY karpathy candidate ever written. The rail
returns `None` from `derive_concept_slug` under `identity` and skips the gate; this runner
mirrors that, and `test_the_THREE_SLUG_STRATEGIES_are_the_ones_that_SHIP` pins it.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from scripts.wiki_index.layout_config import (
    LayoutConfig,
    _apply_slug_strategy,
    load_layout_config,
)
from scripts.wiki_skills.wiki_extract_concepts._errors import ExtractionParseError
from scripts.wiki_skills.wiki_extract_concepts._gates import (
    build_dup_keys,
    check_slugs_derived_from_names,
    concepts_dir_for_source,
    derive_concept_slug,
    layout_indexes_concepts,
    near_duplicate_warnings,
)
from scripts.wiki_skills.wiki_extract_concepts._validation import (
    _preflight_sanitize,
    _validate_candidates_schema,
    check_in_batch_collisions,
    classify_candidates,
)

SKILL_DIR = Path(__file__).resolve().parents[1] / "skills" / "concept-extraction"
EVALS = SKILL_DIR / "evals"
VAULT_ID = "eval-vault"

# ★ GLOBBED. A fixture added later is graded automatically.
FIXTURES = sorted(d for d in EVALS.iterdir() if d.is_dir() and (d / "input.md").is_file())

# ★ THE THREE SLUG STRATEGIES THAT ACTUALLY SHIP — and all three can host a concept page.
#   karpathy          → identity           (the byte-identity anchor; imposes NO derivation)
#   cybos             → transliterate      (COLLAPSES ё/е → the in-batch-collision fixture)
#   obsidian-personal → preserve-unicode   (★ THE OPERATOR'S LIVE VAULT)
LAYOUTS = ("karpathy", "cybos", "obsidian-personal")

# ★ WHERE THE SOURCE NOTE LIVES — and it is NOT the same place on every layout, which is the
# whole reason G10 exists.
#
# `cybos` has NO root glob: all eighteen of its read globs are TYPED FOLDERS (`decisions/**`,
# `facts/**`, …). A concept page filed at `<root>/_concepts/` there is written, never
# discovered by `iter_pages`, never indexed, never linted — an INVISIBLE page. Under `facts/`
# its `_concepts/` sibling is caught by `facts/**/*.md` and everything works. Getting this
# wrong is not a test detail: it is exactly the defect G10 refuses, and the first version of
# this runner walked straight into it (G10 caught it, which is the point of having G10).
_SOURCE_DIR = {
    "karpathy": "_sources",          # write.source_subdir — concepts hang off parent.parent
    "cybos": "facts",                # ★ see above: a typed folder, or the page is invisible
    "obsidian-personal": "",         # the vault root — TASK-037's root-anchored `_concepts/**`
}

# A definition that merely restates its own name says NOTHING — and no validator can see it.
# The stop-list must carry `это` / `когда` / `есть`: NLTK's Russian list does NOT, and with an
# exact-token check the tautology counterexample would slip through and grade nothing.
_STOPWORDS = {
    "это", "этот", "эта", "эти", "то", "тот", "та", "что", "чтобы", "когда", "где",
    "есть", "быть", "который", "которая", "которое", "которые", "и", "или", "а", "но",
    "не", "ни", "как", "так", "такой", "такая", "же", "бы", "ли", "в", "во", "на", "с",
    "со", "по", "из", "для", "о", "об", "при", "за", "до", "от", "у", "к", "над", "под",
    "про", "между", "если", "потому", "значит", "просто", "всегда", "всё", "все", "оно",
    "он", "она", "они", "мы", "вы", "я", "нас", "нам", "его", "её", "их", "себя",
}
_STEM = 5  # a light Russian stem: `исходящий`/`исходящего` share a 5-char prefix


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower(), flags=re.UNICODE)


def _is_tautology(name: str, definition: str) -> bool:
    """Does this definition add NOTHING beyond restating its own name?

    ★ THIS IS THE ONLY GRADER FOR THE OPERATOR'S LITERAL ASK — *"definitions that COMPLEMENT
    the source"*. The rail's `DEFINITION_IS_QUOTE` catches a definition copied from the quote;
    NOTHING catches «Синергия — это когда есть синергия», which is schema-valid, ≥40 chars,
    plain prose, and utterly empty. The page ships, `wiki-search` retrieves it, `wiki-query`
    cites it.
    """
    name_stems = {w[:_STEM] for w in _words(name)}
    content = {w[:_STEM] for w in _words(definition) if w not in _STOPWORDS}
    return bool(content) and content <= name_stems


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


def _grading(fixture: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (fixture / "grading.json").read_text(encoding="utf-8"))
    return data


def _payload(fixture: Path, which: str) -> list[dict[str, Any]]:
    p = fixture / f"{which}.json"
    if not p.is_file():
        return []
    items: list[dict[str, Any]] = json.loads(p.read_text(encoding="utf-8"))
    return items


def _seed_slugs(fixture: Path) -> list[str]:
    """The concept pages that must ALREADY be in the vault for this fixture to mean anything.

    Declared by `reuse_slug` in `expected.json` — the fixture says "re-link this existing
    concept", so the runner has to put it there. (Fixture 05: the vault owns
    `бессрочный-фьючерс`; the source says «бессрочные фьючерсы».)
    """
    return [str(c["reuse_slug"]) for c in _payload(fixture, "expected") if "reuse_slug" in c]


def _slug_for(item: dict[str, Any], config: LayoutConfig) -> str:
    """The slug this candidate gets — DERIVED, exactly as the REASON step derives it from
    `prepare`'s `slug_strategy`.

    ★ Three cases, and the order matters:
      1. `reuse_slug` → VERBATIM. This is a `mention` of an existing page; its slug is the
         vault's, not the model's, and slugifying it again would be wrong.
      2. an explicit `slug` (counterexamples only) → VERBATIM, so the fixture can FORCE a
         layout-dependent violation (`slippage` on a preserve-unicode vault).
      3. otherwise → the layout's own derivation. Under `identity` the layout declares NO
         name→slug function (`derive_concept_slug` returns None), so the model is free to
         choose; we pick the transliterated form, which is what a model actually does on
         karpathy and which `_is_valid_slug` accepts.
    """
    if "reuse_slug" in item:
        return str(item["reuse_slug"])
    if "slug" in item:
        return str(item["slug"])
    derived = derive_concept_slug(str(item["name"]), config.slug_strategy)
    return derived if derived is not None else _apply_slug_strategy(
        str(item["name"]), "transliterate")


def _candidates(items: list[dict[str, Any]], config: LayoutConfig) -> list[dict[str, Any]]:
    """A fixture item → the 6-key payload `apply` actually validates."""
    out = []
    for item in items:
        out.append({
            "slug": _slug_for(item, config),
            "name": str(item["name"]),
            "definition": str(item["definition"]),
            "source_quote": str(item["source_quote"]),
            "source_span": str(item["source_span"]),
            "entity_type": str(item["entity_type"]),
        })
    return out


def _vault(root: Path, layout: str, fixture: Path) -> tuple[LayoutConfig, Path, set[str]]:
    """A vault on `layout`, carrying the fixture's source note and its seeded concepts."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "WIKI_SCHEMA.md").write_text(
        f"---\nvault_id: {VAULT_ID}\nlanguage: ru\nlayout: {layout}\n---\n",
        encoding="utf-8")
    config = load_layout_config(root, {"layout": layout})

    sub = _SOURCE_DIR[layout]
    src_dir = root / sub if sub else root
    src_dir.mkdir(parents=True, exist_ok=True)
    source_path = src_dir / "input.md"
    source_path.write_text(
        (fixture / "input.md").read_text(encoding="utf-8"), encoding="utf-8")

    concepts_dir = concepts_dir_for_source(source_path, root, config)
    known: set[str] = set()
    for slug in _seed_slugs(fixture):
        concepts_dir.mkdir(parents=True, exist_ok=True)
        (concepts_dir / f"{slug}.md").write_text(
            f"---\ntype: concept\nslug: {slug}\nname: {slug}\n---\n# {slug}\n",
            encoding="utf-8")
        known.add(unicodedata.normalize("NFC", slug))
    return config, source_path, known


def _validate(
    candidates: list[dict[str, Any]], fixture: Path, root: Path, config: LayoutConfig,
    source_path: Path, known: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Run the REAL validators, in the REAL order `apply` runs them.

    G10 (layout preflight) → schema → in-batch collision → sanitize pre-flight → classify →
    **G8 on the CREATE list only** → the near-duplicate ADVISORY.

    ★ THE ORDER IS THE CONTRACT, AND TWO PARTS OF IT ARE TASK-064 FIX-LOOP REPAIRS:
      * G8 runs AFTER `classify_candidates`, over the CREATE list, and skips any slug the
        vault already has. Running it over EVERY candidate (as the first cut did) judged
        `mention`s of pages that ALREADY EXIST — making every acronym page (`amm`, `dex`)
        permanently unmentionable, and its prescribed repair minted a SECOND page for the
        same concept.
      * the near-duplicate check RETURNS WARNINGS AND RAISES NOTHING. Its metric is
        anti-correlated with meaning (`централизация`/`децентрализация` = 0.941, HARDER
        than the real live duplicate it was built for at 0.927), and its refusal used to
        instruct the model to file a DIFFERENT concept as a MENTION of the near-match —
        writing a falsified provenance receipt at exit 0.

    Returns ``(create_list, mention_list, warnings)``.
    """
    body = source_path.read_text(encoding="utf-8")
    concepts_dir = concepts_dir_for_source(source_path, root, config)

    assert layout_indexes_concepts(config, root, concepts_dir), (
        f"{config.layout} cannot index a concept page — the whole tri-layout run over it "
        f"would be theatre (G10 would refuse every apply)")

    _validate_candidates_schema(candidates, source_body=body)
    if not candidates:
        return [], [], []
    check_in_batch_collisions(candidates)
    _preflight_sanitize(candidates)

    create_list, mention_list = classify_candidates(candidates, known)
    check_slugs_derived_from_names(
        [c for c in create_list
         if unicodedata.normalize("NFC", str(c["slug"])) not in known],
        config)
    warnings = near_duplicate_warnings(create_list, build_dup_keys(known))
    return create_list, mention_list, warnings


# --------------------------------------------------------------------------- #
# the census — a glob that matched nothing reports as a pass
# --------------------------------------------------------------------------- #


def test_the_eval_set_is_COMPLETE_and_every_fixture_is_GRADED() -> None:
    """A suite of zero tests reports green, so the population is asserted first."""
    assert len(FIXTURES) >= 11, f"the eval glob found {[f.name for f in FIXTURES]}"
    for f in FIXTURES:
        assert (f / "expected.json").is_file(), f"{f.name}: no expected.json"
        assert (f / "grading.json").is_file(), (
            f"{f.name}: NO grading.json — an ungraded fixture validates the shape and misses "
            f"the census, which is exactly how a half-dropped extraction stays green")
        g = _grading(f)
        assert len(g.get("why", "")) > 80, (
            f"{f.name}: `why` must state the FAILURE MODE this fixture guards, and whether a "
            f"mechanism backs it. A fixture whose reason is not recorded gets deleted.")

    names = {f.name for f in FIXTURES}
    assert any("nothing-to-define" in n for n in names), (
        "★ the EMPTY fixture is missing — it is the ONLY thing that exercises "
        "_CANDIDATE_COUNT_MIN = 0, the constant this whole task turns on")
    assert any("chrome" in n or "primitives" in n for n in names), (
        "the JUNK-CLASS fixture is missing — the highest-volume garbage class in the live "
        "corpus has no eval")
    assert any("participants" in n for n in names)
    assert any("collision" in n or "one-file" in n for n in names)


def test_the_THREE_SLUG_STRATEGIES_are_the_ones_that_SHIP(tmp_path: Path) -> None:
    """★ Pinned so the tri-layout run cannot silently become theatre.

    And `identity` is pinned for a second reason: it is the branch a naive G8 breaks on.
    `_apply_slug_strategy(name, "identity")` returns the NAME — not a slug — so a rail that
    asserted `slug == derived` under identity would refuse every karpathy candidate. The rail
    returns None and skips; if that ever changes, this test is where it surfaces.
    """
    strategies = {
        layout: load_layout_config(tmp_path, {"layout": layout}).slug_strategy
        for layout in LAYOUTS
    }
    assert strategies == {
        "karpathy": "identity",
        "cybos": "transliterate",
        "obsidian-personal": "preserve-unicode",
    }, strategies

    assert derive_concept_slug("Проскальзывание", "identity") is None, (
        "identity now claims a name→slug derivation — G8 would refuse every karpathy "
        "candidate, and this runner's slug fallback is wrong")
    assert derive_concept_slug("Проскальзывание", "preserve-unicode") == "проскальзывание"
    assert derive_concept_slug("Проскальзывание", "transliterate") == "proskalzyvanie"


# --------------------------------------------------------------------------- #
# ★ the graded run — every fixture, every layout
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("layout", LAYOUTS)
@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f.name)
def test_expected_output_PASSES_and_MATCHES_ITS_GRADING(
    fixture: Path, layout: str, tmp_path: Path
) -> None:
    """The expected extraction must (a) survive the real validators and (b) match the census
    `grading.json` declares.

    (b) is the half that matters. Validation alone stays green while an extraction silently
    drops half the source's concepts — every page it DID write is perfectly valid.
    """
    grading = _grading(fixture)
    if layout not in grading.get("layouts", list(LAYOUTS)):
        pytest.skip(f"{fixture.name} declares it does not apply to {layout}")

    root = tmp_path / "v"
    config, source_path, known = _vault(root, layout, fixture)
    items = _payload(fixture, "expected")
    candidates = _candidates(items, config)

    create_list, mention_list, _warnings = _validate(
        candidates, fixture, root, config, source_path, known)

    if grading.get("empty_is_success"):
        assert items == [], f"{fixture.name} is the NEGATIVE fixture; expected []"
        assert (create_list, mention_list) == ([], [])
        return

    census: dict[str, int] = {}
    for c in candidates:
        census[c["entity_type"]] = census.get(c["entity_type"], 0) + 1
    assert census == grading["expect"], (
        f"{fixture.name}: census {census} != graded {grading['expect']}")

    assert len(mention_list) == grading.get("expect_mentions", 0), (
        f"{fixture.name}: {len(mention_list)} mentions, graded "
        f"{grading.get('expect_mentions', 0)} — a near-duplicate that mints a NEW page "
        f"instead of re-linking the existing one is the #1 live garbage class")


@pytest.mark.parametrize("layout", LAYOUTS)
@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f.name)
def test_no_expected_candidate_is_FORBIDDEN_and_none_is_a_TAUTOLOGY(
    fixture: Path, layout: str, tmp_path: Path
) -> None:
    """★ THE HALF NO VALIDATOR CAN SEE — and therefore the half that must be graded here.

    `forbidden` is the junk the source dangles: UI chrome, SQL builtins, schema columns,
    attendees, the injected concept. Every one of them passes the schema. The census is the
    only gate, and this is it.
    """
    grading = _grading(fixture)
    if layout not in grading.get("layouts", list(LAYOUTS)):
        pytest.skip(f"{fixture.name} declares it does not apply to {layout}")

    config = load_layout_config(tmp_path, {"layout": layout})
    forbidden = {_norm(t) for t in grading.get("forbidden", [])}

    for item in _payload(fixture, "expected"):
        name, slug = _norm(str(item["name"])), _norm(_slug_for(item, config))
        assert name not in forbidden and slug not in forbidden, (
            f"{fixture.name}: the EXPECTED extraction contains {item['name']!r}, which the "
            f"grading forbids — the fixture is grading itself as garbage")
        assert not _is_tautology(str(item["name"]), str(item["definition"])), (
            f"{fixture.name}: expected definition for {item['name']!r} merely restates its "
            f"own name. That page's information content is ZERO, and NOTHING in the rail "
            f"would refuse it — which is exactly why the eval has to.")


# --------------------------------------------------------------------------- #
# ★ the counterexamples — a SKILL rule with no failing case is a SKILL rule that rots
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("layout", LAYOUTS)
@pytest.mark.parametrize(
    "fixture", [f for f in FIXTURES if (f / "counterexample.json").is_file()],
    ids=lambda f: f.name)
def test_the_COUNTEREXAMPLE_is_REFUSED_with_the_GRADED_code(
    fixture: Path, layout: str, tmp_path: Path
) -> None:
    """★ Each counterexample is the WRONG extraction, and `grading.json` names the exact code
    the rail must refuse it with. `refused_with` is ASSERTED — not merely "it raised": a
    counterexample refused for the WRONG reason would pass a laxer test while proving nothing
    about the rule it is supposed to demonstrate.

    ★★ AND SOME COUNTEREXAMPLES ARE NOT REFUSED AT ALL. `graded_by_census_only` marks the ones
    the code ACCEPTS — the padded meeting, the UI chrome, the obeyed injection, the tautology,
    and (since the TASK-064 fix-loop) THE NEAR-DUPLICATE. For those the assertion INVERTS: the
    rail must accept them (proving the mechanism gap is real, not imagined) and the `forbidden`
    census must catch them (proving the SKILL is the only thing that can). A fixture that
    claimed a refusal it does not get would be a lie in the direction of comfort.

    ★ `warns_with` is the THIRD grade, and it is what a DEMOTED mechanism looks like. The
    near-duplicate check no longer refuses — it ADVISES — so fixture 05 asserts the advisory
    FIRES (the mechanism still sees the duplicate) while the code still ACCEPTS the page (the
    mechanism no longer decides). Grading it as a refusal would now be a lie; grading it as
    census-only alone would silently drop the one thing the mechanism still does.
    """
    grading = _grading(fixture)
    if layout not in grading.get("layouts", list(LAYOUTS)):
        pytest.skip(f"{fixture.name} declares it does not apply to {layout}")

    spec = grading.get("counterexample", {})
    root = tmp_path / "v"
    config, source_path, known = _vault(root, layout, fixture)
    bad = _candidates(_payload(fixture, "counterexample"), config)

    census_only = spec.get("graded_by_census_only", False)
    accepted_here = layout in spec.get("accepted_on", [])

    if census_only or accepted_here:
        # It must ACTUALLY be accepted — asserting only the refusal half would let a rail that
        # refuses EVERYTHING pass this suite.
        _create, _mention, warnings = _validate(
            bad, fixture, root, config, source_path, known)

        # A DEMOTED mechanism: it must still SEE the violation, even though it no longer
        # decides. Without this, "we made it advisory" is indistinguishable from "we deleted
        # it" — and the fixture would go green over a check that stopped running.
        warns_with = spec.get("warns_with")
        if warns_with:
            codes = {str(w.get("code")) for w in warnings}
            assert warns_with in codes, (
                f"{fixture.name} on {layout}: the {warns_with} ADVISORY did not fire. The "
                f"mechanism was demoted from a refusal to a warning, not deleted — if it no "
                f"longer even SEES the duplicate, nothing does.")

        if census_only:
            forbidden = {_norm(t) for t in grading.get("forbidden", [])}
            assert forbidden, (
                f"{fixture.name}: graded_by_census_only with an EMPTY forbidden list — this "
                f"fixture grades NOTHING. The code accepts the counterexample and no census "
                f"catches it.")
            hits = {
                _norm(str(c["name"])) for c in _payload(fixture, "counterexample")
            } | {_norm(c["slug"]) for c in bad}
            assert hits & forbidden, (
                f"{fixture.name}: the counterexample is accepted by the code AND clean of "
                f"every forbidden term — so nothing, anywhere, grades it. Either the "
                f"counterexample or the forbidden list is wrong.")
        return

    if layout not in spec.get("on_layouts", list(LAYOUTS)):
        pytest.skip(f"{fixture.name} counterexample not graded for {layout}")

    with pytest.raises(ExtractionParseError) as exc:
        _validate(bad, fixture, root, config, source_path, known)
    assert exc.value.error == spec["refused_with"], (
        f"{fixture.name} on {layout}: refused with {exc.value.error}, graded "
        f"{spec['refused_with']} — a counterexample refused for the WRONG reason proves "
        f"nothing about the rule it demonstrates")


# --------------------------------------------------------------------------- #
# the SKILL's rules, each gated against the code that enforces them
# --------------------------------------------------------------------------- #


def test_SKILL_md_documents_the_rules_the_fixtures_demonstrate() -> None:
    """Doc and fixture must agree. A rule taught but never demonstrated rots; a rule
    demonstrated but never taught is a trap the model walks into every time.

    Whitespace-collapsed before matching: the SKILL is PROSE and its sentences wrap. A test
    that breaks when a paragraph is re-flowed trains the next author to stop re-flowing.
    """
    raw = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    text = re.sub(r"\s+", " ", raw)

    assert "Zero is a correct extraction" in text                      # 02
    assert "no minimum and no target" in text                          # the quota is DEAD
    assert "3-10" in text, (
        "the SKILL must name the quota it killed — a reader who does not know the old rule "
        "will restore it")
    assert "DEFINITION_IS_QUOTE" in text                               # 06
    assert "ENTITY_TYPE_NOT_ALLOWED" in text                           # 04
    assert "NEAR_DUPLICATE_SLUG" in text                               # 05
    assert "IN_BATCH_SLUG_COLLISION" in text                           # 09
    assert "SLUG_NOT_DERIVED_FROM_NAME" in text                        # 08
    assert "SOURCE_SPAN_OUT_OF_RANGE" in text                          # 10
    assert "BEGIN-SOURCE" in text and "UNTRUSTED DATA" in text         # 11 (H-6 armor)

    # ★ THE HONESTY LEDGER. The three rules with no mechanism must be NAMED as such — the
    # repo's own bar: a rule is worthless unless a mechanism refuses violations, OR the doc
    # is honest that none does.
    assert "What NOTHING refuses" in text
    assert "the ONLY gate" in text

    # ★ THE ESCAPE HATCH IS GONE, AND THE DOC MUST NOT RESURRECT IT. The old SKILL documented
    # `WIKI_EXTRACT_NO_QUOTE_CHECK` as a supported bypass of the one anti-fabrication check.
    assert "WIKI_EXTRACT_NO_QUOTE_CHECK" not in text
    assert "no escape hatch" in text.lower()

    assert "anthropic" not in text.lower()      # a CONTRACT, not a call (Decision-17)


def test_the_SKILLs_QUOTA_is_DEAD_in_the_CODE_too() -> None:
    """★ THE PUMP, GATED. The SKILL now says "zero is a correct extraction" — and that
    sentence is a LIE unless the validator agrees.

    Until TASK 064 `_CANDIDATE_COUNT_MIN` was 1: an honest `[]` was exit 4, so the model's
    cheapest green run was to INVENT a concept. A later "parity" commit that restores the 1
    would make every anti-fabrication word in the SKILL unfollowable, and every other gate in
    this file would still be green. This is the tripwire.
    """
    from scripts.wiki_skills.wiki_extract_concepts import _validation as v
    assert v._CANDIDATE_COUNT_MIN == 0, (
        "an empty extraction is a SUCCESS on this rail — restoring the floor of 1 hands the "
        "model a reason to fabricate, which is the defect this whole task exists to remove")


def test_no_refusal_reason_ANYWHERE_teaches_a_BYPASS() -> None:
    """★ THE FABRICATION TUTORIAL IN THE FAILURE PATH.

    The old `FIELD_QUOTE_NOT_IN_BODY` reason ended with *"(set WIKI_EXTRACT_NO_QUOTE_CHECK=1
    to skip)"* — the model read that string at the exact moment it was stuck on the one
    anti-fabrication check on the rail, and it named the way through. The env read is deleted;
    so must be every mention of it in an operator-facing string.

    ★ AND IT IS CHECKED WITH AN AST, NOT A GREP. `WIKI_EXTRACT_NO_QUOTE_CHECK` still appears
    in this package — inside the COMMENTS recording why it was deleted, which is exactly where
    it belongs. A substring test would either fail on that history or bully someone into
    erasing it; only a parse can tell a LIVE `os.environ.get(...)` from a comment about one.
    """
    import ast

    import scripts.wiki_skills.wiki_extract_concepts as pkg

    for py in sorted(Path(pkg.__file__).parent.glob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            # `os.environ` in ANY position — `.get(...)`, `[...]`, or bare — plus `os.getenv`.
            if not isinstance(node, ast.Attribute):
                continue
            if node.attr in {"environ", "getenv"} and isinstance(node.value, ast.Name) \
                    and node.value.id == "os":
                pytest.fail(
                    f"{py.name}:{node.lineno} reads the environment. An escape hatch on an "
                    f"anti-fabrication check IS the fabrication path, and it gets reached "
                    f"exactly when someone is in a hurry.")
