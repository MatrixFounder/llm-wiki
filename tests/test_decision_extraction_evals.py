"""TASK 063-16 — the `decision-extraction` eval set.

★ AN EVAL WHOSE OWN EXPECTED OUTPUT THE RAIL WOULD REFUSE IS WORSE THAN NO EVAL. It
teaches the model a shape the code rejects, and it looks like coverage. So every
fixture's `expected.json` is fed through the REAL validators — the same
`validate_candidates_schema` / `validate_ontology` / `validate_refs` that `apply` runs.

★ THE FIXTURE POPULATION IS GLOBBED, NEVER HARDCODED. A `range(1, 5)` here is how
fixture #5 gets silently skipped — a denominator maintained by hand, which is this
project's signature failure mode.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout_config import load_layout_config
from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills.wiki_extract_decisions import _ontology_contract, main
from scripts.wiki_skills.wiki_extract_decisions._errors import ExtractionParseError
from scripts.wiki_skills.wiki_extract_decisions._pages import render_page
from scripts.wiki_skills.wiki_extract_decisions._validation import (
    derive_slugs,
    validate_candidates_schema,
    validate_ontology,
    validate_refs,
)

SKILL_DIR = Path(__file__).resolve().parents[1] / "skills" / "decision-extraction"
EVALS = SKILL_DIR / "evals"
ROSTER = ("decision", "requirement", "risk")
VAULT_ID = "eval-vault"

# ★ GLOBBED. A fixture added later is exercised automatically.
FIXTURES = sorted(d for d in EVALS.iterdir() if d.is_dir())


def test_the_eval_set_is_not_empty() -> None:
    """The census, asserted. A glob that matched nothing would make every
    parametrised test below vacuously green — a suite of zero tests reports as a pass."""
    assert len(FIXTURES) >= 4, f"the eval glob found {[f.name for f in FIXTURES]}"
    assert any(f.name.startswith("02-") for f in FIXTURES), (
        "the NEGATIVE fixture is missing — without it, CANDIDATE_COUNT_MIN = 0 is a "
        "constant no eval ever exercises")


def _cybos_vault(root: Path, db: Path) -> Path:
    """A cybos vault carrying the slugs the fixtures link to."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "WIKI_SCHEMA.md").write_text(
        f"---\nvault_id: {VAULT_ID}\nlanguage: ru\nlayout: cybos\n---\n",
        encoding="utf-8")
    (root / "decisions").mkdir(exist_ok=True)
    (root / "decisions" / "dec-ocheredi.md").write_text(
        "---\ntype: decision\nslug: dec-ocheredi\nstatus: accepted\n"
        "title: Использовать очереди\n---\n# Очереди\n", encoding="utf-8")
    r = SQLiteRepository(db)
    r.apply_schema()
    r.register_vault(Vault(vault_id=VAULT_ID, name=VAULT_ID, root_path=root,
                           schema_version="7.0", registered_at=datetime(2026, 7, 14)))
    r.close()
    repo = make_repo({"vault_id": VAULT_ID, "db_path": str(db),
                      "vault_root": str(root)})
    try:
        reindex_full(repo, VAULT_ID)
    finally:
        repo.close()
    return root


def _validate(
    candidates: list[dict[str, Any]], fixture: Path, vault: Path, db: Path
) -> int:
    """Run the REAL validators — the ones `apply` runs. Returns `links_checked`."""
    config = load_layout_config(vault, {"layout": "cybos"})
    body = (fixture / "input.md").read_text(encoding="utf-8")

    kept = validate_candidates_schema(candidates, source_body=body, roster=ROSTER)
    if not kept:
        return 0
    slugs = derive_slugs(kept, config)

    repo = make_repo({"vault_id": VAULT_ID, "db_path": str(db),
                      "vault_root": str(vault)})
    try:
        from scripts.wiki_skills.wiki_extract_decisions._db import (
            load_resolvable_targets,
            resolve_target_classes,
        )
        targets = sorted({t for c in kept
                          for ts in (c.get("edges") or {}).values() for t in ts})
        db_classes = resolve_target_classes(repo, VAULT_ID, targets)
        resolvable = load_resolvable_targets(repo, VAULT_ID) | set(slugs)
    finally:
        repo.close()

    validate_ontology(
        kept, ontology=_ontology_contract(config, ROSTER),
        batch_classes={s: str(c["class"]) for c, s in zip(kept, slugs)},
        db_classes=db_classes)

    rendered = [
        render_page(c, slug=s, vault_id=VAULT_ID, source_slug="input",
                    today=date(2026, 7, 14), source_indexable=False)
        for c, s in zip(kept, slugs)
    ]
    return validate_refs(rendered, config=config, resolvable=resolvable)


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f.name)
def test_every_eval_expected_output_PASSES_apply_validation(
    fixture: Path, tmp_path: Path
) -> None:
    """★ An eval whose own expected output `apply` would REFUSE is worse than no eval:
    it teaches the model a shape the code rejects, while looking like coverage.

    So every `expected.json` goes through the real validators — schema,
    anti-fabrication (including the verbatim-quote check against the fixture's OWN
    `input.md`), G1 ontology, and G2 refs.
    """
    v = _cybos_vault(tmp_path / "v", tmp_path / "x.db")
    candidates = json.loads((fixture / "expected.json").read_text(encoding="utf-8"))
    _validate(candidates, fixture, v, tmp_path / "x.db")     # raises ⇒ the eval is wrong


def test_the_NEGATIVE_fixture_is_a_SUCCESS(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """★ Fixture 02 — the transcript that explicitly DEFERS («отложили», «вернёмся к
    этому»). Correct extraction: `[]`. Correct outcome: exit 0, `no_candidates`.

    This fixture IS the anti-fabrication mechanism in fixture form. Without it,
    `CANDIDATE_COUNT_MIN = 0` is a constant nothing exercises, and the posture rests on
    a value no eval proves is reachable.

    MUT: `CANDIDATE_COUNT_MIN = 1` ⇒ RED.
    """
    fixture = EVALS / "02-deferred-no-decisions"
    assert json.loads((fixture / "expected.json").read_text(encoding="utf-8")) == []

    v = _cybos_vault(tmp_path / "v", tmp_path / "x.db")
    (v / "meetings").mkdir(exist_ok=True)
    (v / "meetings" / "m1.md").write_text(
        (fixture / "input.md").read_text(encoding="utf-8"), encoding="utf-8")

    db = tmp_path / "x.db"
    code = main(["prepare", "--vault", VAULT_ID, "--vault-root", str(v),
                 "--source-page", "meetings/m1.md", "--db-path", str(db)])
    prep = json.loads(capsys.readouterr().out.strip())
    assert code == 0

    cands = tmp_path / "c.json"
    cands.write_text("[]", encoding="utf-8")
    code = main(["apply", "--vault", VAULT_ID, "--vault-root", str(v),
                 "--source-page", "meetings/m1.md",
                 "--source-hash", prep["source_hash"],
                 "--candidates-file", str(cands), "--db-path", str(db)])
    env = json.loads(capsys.readouterr().out.strip())
    assert code == 0
    assert env["action"] == "no_candidates"


def test_the_BARE_ID_counterexample_is_REFUSED(tmp_path: Path) -> None:
    """★ THE SKILL'S RULE, DEMONSTRATED BY A FAILING CASE.

    Fixture 04 ships two payloads, byte-identical except for one line of prose:
      expected.json      body: "Это отменяет [[dec-ocheredi]]."   → accepted
      counterexample.json body: "Это отменяет DEC-004."            → UNRESOLVED_REF

    On cybos the bare ID matches the layout's `id-ref` regex, so it CREATES A REF. A
    doc rule with no failing case is a doc rule that rots; this is the failing case.
    """
    fixture = EVALS / "04-bare-id-in-prose"
    v = _cybos_vault(tmp_path / "v", tmp_path / "x.db")
    db = tmp_path / "x.db"

    # the CORRECT form validates
    good = json.loads((fixture / "expected.json").read_text(encoding="utf-8"))
    _validate(good, fixture, v, db)

    # ...and the bare-ID form is refused, on exactly the ref surface
    bad = json.loads((fixture / "counterexample.json").read_text(encoding="utf-8"))
    with pytest.raises(ExtractionParseError) as exc:
        _validate(bad, fixture, v, db)
    assert exc.value.error == "UNRESOLVED_REF"
    assert exc.value.violations[0]["target"] == "dec-004"


def test_SKILL_md_documents_the_id_ref_hazard_and_the_empty_success() -> None:
    """A doc rule with no test rots. These two rules are the ones whose absence makes
    the rail feel BROKEN to an operator:

      * the id-ref hazard — without it, correct prose bounces the batch on G2 and the
        rail is experienced as "flaky" (a correct gate producing an unusable product);
      * the empty-is-success rule — without it, the model's cheapest green run is to
        invent a decision.
    """
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "BARE IDs IN PROSE ARE REFS" in text
    assert "DEC-004" in text                     # the hazard, shown concretely
    assert "AN EMPTY EXTRACTION IS A SUCCESS" in text
    assert "no_candidates" in text
    assert "OPEN COMMITMENT IS DATA" in text     # do not invent a closing decision

    # ...and the SKILL is a CONTRACT, not a call: the orchestrator owns REASON.
    assert "import anthropic" not in text
    assert "anthropic" not in text.lower()
