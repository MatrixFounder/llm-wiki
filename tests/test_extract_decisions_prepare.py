"""TASK 063-05 — `prepare`: the ontology contract, the G4 preflight, the handshake.

Fixtures come from the PLAN §1 ROSTER. No test here invents its own layout fixture:
"which layouts are supported" is a denominator claim, and the spec got it wrong in
v1, then the PLAN got it wrong AGAIN inside the very gate written to stop it — both
times by measuring ONE of G4's two conjuncts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.wiki_index.layout_config import resolve_layout_config
from scripts.wiki_skills.wiki_extract_decisions import main

_PARA_TYPED: dict[str, Any] = {
    "type_mapping": {
        "decision": {"db_type": "research", "tag": "decision"},
        "requirement": {"db_type": "brief", "tag": "requirement"},
        "risk": {"db_type": "research", "tag": "risk"},
    },
}


def _vault(
    root: Path, layout: str, *, override: dict[str, Any] | None = None,
    sync: str | None = None, sync_at: str = ".",
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "WIKI_SCHEMA.md").write_text(
        f"---\nvault_id: test-vault\nlanguage: en\nlayout: {layout}\n"
        + ("layout_config: .wiki/layout.yaml\n" if override else "")
        + "---\n", encoding="utf-8")
    if override:
        (root / ".wiki").mkdir(exist_ok=True)
        (root / ".wiki" / "layout.yaml").write_text(
            yaml.safe_dump(override, allow_unicode=True), encoding="utf-8")
    if sync is not None:
        d = root if sync_at == "." else root / sync_at
        (d / ".wiki").mkdir(parents=True, exist_ok=True)
        (d / ".wiki" / "sync.yaml").write_text(sync, encoding="utf-8")
    return root


def _source(vault: Path, rel: str, body: str = "# Protocol\n\nWe decided X.\n") -> str:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return rel


def _prepare(
    capsys: pytest.CaptureFixture[str], vault: Path, source: str, db: Path,
) -> tuple[int, dict[str, Any]]:
    code = main([
        "prepare", "--vault", "test-vault", "--vault-root", str(vault),
        "--source-page", source, "--db-path", str(db),
    ])
    payload = json.loads(capsys.readouterr().out.strip())
    assert isinstance(payload, dict)
    return code, payload


# --------------------------------------------------------------------------- #
# ★ The ontology contract
# --------------------------------------------------------------------------- #


def test_prepare_emits_the_ontology_contract(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The contract is asserted AGAINST THE LAYOUT YAML, never against a literal
    copy of it. A literal copy in a test is a second source of truth, and the whole
    point of the contract is that there is one.
    """
    v = _vault(tmp_path / "v", "cybos")
    src = _source(v, "meetings/m1.md")
    code, env = _prepare(capsys, v, src, tmp_path / "x.db")
    assert code == 0
    assert env["action"] == "prepared"

    cfg = resolve_layout_config(v)
    assert cfg.ontology is not None
    supersedes = next(e for e in cfg.ontology.edges if e.edge == "supersedes")
    emitted = next(e for e in env["ontology"]["edges"] if e["edge"] == "supersedes")
    assert emitted["from"] == list(supersedes.frm)
    assert emitted["to"] == list(supersedes.to)

    dec_status = next(p for p in cfg.ontology.properties
                      if p.page_class == "decision" and p.field == "status")
    emitted_p = next(p for p in env["ontology"]["properties"]
                     if p["class"] == "decision")
    assert emitted_p["enum"] == list(dec_status.enum)
    assert env["ontology"]["closed_types"] is cfg.ontology.closed_types

    assert env["vacuous_validation"] is False
    assert env["validation"]["roster_size"] == 3
    assert env["validation"]["properties_checked"] >= 3


def test_dev_project_is_vacuous_and_SAYS_SO(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """★ THE MOST IMPORTANT TEST IN THIS BEAD.

    `dev-project` maps the typed classes but declares NO `ontology:` block and NO
    `drift_rules`. There, G1 degrades to a roster-only check and G3 is moot. The
    delta property still HOLDS (both sides vacuous), so a green `apply` there is not
    a lie — but it means "validated ALMOST NOTHING", and per TASK 061 that must be
    ANNOUNCED, not inferred from a zero.

    A zero that means "examined nothing" and a zero that means "examined everything
    and found nothing" are different facts. This marker is the difference.

    MUT: drop `vacuous_validation` from the envelope ⇒ RED.
    """
    v = _vault(tmp_path / "v", "dev-project")
    src = _source(v, "tasks/t1.md")
    code, env = _prepare(capsys, v, src, tmp_path / "x.db")

    assert code == 0
    assert env["vacuous_validation"] is True
    assert env["ontology"] == {}
    assert env["validation"]["edges_checked"] == 0
    assert env["validation"]["properties_checked"] == 0
    # ...and yet the rail IS usable here: the roster is full, so G1 still checks
    # the class membership. "Vacuous" is a statement about the ONTOLOGY, not about
    # the run — and saying which is which is the entire point.
    assert env["validation"]["roster_size"] == 3
    assert env["roster"] == ["decision", "requirement", "risk"]
    assert env["drift_rules"] == []


# --------------------------------------------------------------------------- #
# ★ The G4 preflight — both conjuncts, both exit 2
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("layout", ["karpathy", "obsidian-personal"])
def test_zero_typed_class_layout_REFUSES(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], layout: str
) -> None:
    """BOTH zero-typed-class layouts (PLAN §1). They fail G4's FIRST conjunct: the
    `type_mapping` routes none of the roster, so a typed page written here would be
    indexed under no class at all.

    MUT: delete the preflight ⇒ RED (and in production: pages indexed as nothing).
    """
    v = _vault(tmp_path / "v", layout)
    src = _source(v, "_sources/s.md" if layout == "karpathy" else "06 - BD/n.md")
    code, env = _prepare(capsys, v, src, tmp_path / "x.db")

    assert code == 2
    assert env["error"] == "LAYOUT_CANNOT_INDEX_CLASSES"
    assert env["layout"] == layout
    assert "type_mapping" in env["message"]


def test_uncovered_dir_refuses_in_prepare_TOO(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """★ ONE GATE, TWO CALLERS. cybos + a Cyrillic folder name: `prepare` refuses
    with the SAME code `wiki-config validate` emits, from the SAME helper
    (`typed_write_refusal`). Two implementations would drift, and a gate that
    disagrees with the rail it gates is a second opinion."""
    v = _vault(tmp_path / "v", "cybos",
               sync="extract_decisions:\n  dirs:\n    decision: 'решения'\n")
    src = _source(v, "meetings/m1.md")
    code, env = _prepare(capsys, v, src, tmp_path / "x.db")

    assert code == 2
    assert env["error"] == "TYPED_DIR_NOT_COVERED_BY_LAYOUT"
    assert env["page_class"] == "decision"
    assert env["reason"] == "unmatched"


def test_ignored_dir_refuses_in_prepare(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The C-3 case at the RAIL's surface: `_raw` matches a PARA glob and is killed
    by `ignore`. A `paths[]`-only preflight would let this through, and every page
    written would be invisible to the index with zero lint issues."""
    v = _vault(tmp_path / "v", "obsidian-personal", override=_PARA_TYPED,
               sync="extract_decisions:\n  dirs:\n    decision: '_raw'\n")
    src = _source(v, "06 - BD/Acme/note.md")
    code, env = _prepare(capsys, v, src, tmp_path / "x.db")

    assert code == 2
    assert env["error"] == "TYPED_DIR_NOT_COVERED_BY_LAYOUT"
    assert env["reason"] == "ignored"


# --------------------------------------------------------------------------- #
# placement, the handshake, idempotency, and the numbers
# --------------------------------------------------------------------------- #


def test_typed_dirs_are_DERIVED_per_layout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same rail, two layouts, two placements — because placement is a property
    of the LAYOUT'S read grammar, not of the rail's preference. cybos: root. PARA:
    sibling of the source note, with the operator's own Cyrillic folder names."""
    cy = _vault(tmp_path / "cy", "cybos")
    _, env = _prepare(capsys, cy, _source(cy, "meetings/m1.md"), tmp_path / "a.db")
    assert env["typed_dirs"]["decision"] == "decisions"

    pa = _vault(
        tmp_path / "pa", "obsidian-personal", override=_PARA_TYPED,
        sync="extract_decisions:\n  enabled: true\n  dirs:\n"
             "    decision: 'Решения'\n    risk: 'Риски'\n",
        sync_at="06 - BD")
    (pa / "06 - BD" / "Acme").mkdir(parents=True, exist_ok=True)
    _, env = _prepare(capsys, pa, _source(pa, "06 - BD/Acme/note.md"), tmp_path / "b.db")
    assert env["typed_dirs"] == {
        "decision": "06 - BD/Acme/Решения",
        "requirement": "06 - BD/Acme/requirements",
        "risk": "06 - BD/Acme/Риски",
    }


def test_source_path_is_RELATIVE(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CWE-209: the envelope goes into agent logs. It must not leak the operator's
    home directory or the vault's location on disk."""
    v = _vault(tmp_path / "v", "cybos")
    _, env = _prepare(capsys, v, _source(v, "meetings/m1.md"), tmp_path / "x.db")
    assert env["source_path"] == "meetings/m1.md"
    assert str(tmp_path) not in json.dumps(env)


def test_absolute_source_page_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    v = _vault(tmp_path / "v", "cybos")
    _source(v, "meetings/m1.md")
    code = main(["prepare", "--vault", "test-vault", "--vault-root", str(v),
                 "--source-page", str(v / "meetings" / "m1.md"),
                 "--db-path", str(tmp_path / "x.db")])
    env = json.loads(capsys.readouterr().out.strip())
    assert code == 2
    assert env["error"] == "INVALID_SOURCE_PATH"


def test_missing_source_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    v = _vault(tmp_path / "v", "cybos")
    code, env = _prepare(capsys, v, "meetings/nope.md", tmp_path / "x.db")
    assert code == 2
    assert env["error"] == "SOURCE_NOT_FOUND"


def test_hash_is_the_handshake_and_changes_with_the_body(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--source-hash` is what makes `apply` refuse candidates that describe a body
    which no longer exists. It must actually track the body."""
    v = _vault(tmp_path / "v", "cybos")
    src = _source(v, "meetings/m1.md", "# A\n")
    _, first = _prepare(capsys, v, src, tmp_path / "x.db")
    (v / src).write_text("# B\n", encoding="utf-8")
    _, second = _prepare(capsys, v, src, tmp_path / "x.db")
    assert first["source_hash"] != second["source_hash"]
    assert len(first["source_hash"]) == 64


def test_is_unchanged_is_false_on_a_fresh_vault(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """R-063-5. The `source_state` round-trip (unchanged → True) lands with `apply`
    in 063-12, which is what WRITES the marker; `prepare` can only read it, and a
    fresh vault has none. Stated rather than left as a silently missing assertion."""
    v = _vault(tmp_path / "v", "cybos")
    _, env = _prepare(capsys, v, _source(v, "meetings/m1.md"), tmp_path / "x.db")
    assert env["is_unchanged"] is False


def test_open_commitments_is_DATA_not_a_defect(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """★ Q-063-4. An open commitment is a FACT about the engagement, reported at
    exit 0 — never something the run should have closed.

    If it read as a defect, the model's cheapest path to a clean report would be to
    INVENT a decision that closes it. TASK 062 surfaced three real open commitments
    from the operator's own protocols; every one was a genuine open question with a
    real client, and inventing a closure for any of them would have been a lie
    written into the knowledge base."""
    v = _vault(tmp_path / "v", "cybos")
    code, env = _prepare(capsys, v, _source(v, "meetings/m1.md"), tmp_path / "x.db")
    assert code == 0                       # ← the whole point
    assert env["open_commitments"] == 0    # empty vault; the count is live in 063-12


def test_traversal_source_is_refused_and_nothing_is_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """H-6: a `..` path that RESOLVES to a real file outside the vault must be
    refused as INVALID_SOURCE_PATH — the containment check runs before any read.

    Pinned as a test because the existence check now runs FIRST (so a typo gets the
    honest SOURCE_NOT_FOUND), and "existence first" is exactly the reordering that
    could quietly become "read first" in a later edit. `is_file()` is a stat; the
    bytes are still gated by containment."""
    outside = tmp_path / "secret.md"
    outside.write_text("# not yours\n", encoding="utf-8")
    v = _vault(tmp_path / "v", "cybos")
    code, env = _prepare(capsys, v, "../secret.md", tmp_path / "x.db")
    assert code == 2
    assert env["error"] == "INVALID_SOURCE_PATH"
    assert "not yours" not in json.dumps(env)


def test_the_SUPPORTED_SET_is_what_prepare_ACTUALLY_ACCEPTS(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """★ THE CONJUNCTION, MEASURED THROUGH THE RAIL ITSELF — not through the helper.

    063-02 already gates `maps ∧ sees` against `layout_choices()`. That gate is about
    the HELPER. This one runs the actual `prepare` CLI over every built-in layout and
    asserts the exit codes match the roster — because the helper being right and the
    rail USING it are two different claims, and the plan-review's C-2 finding was
    precisely that the gate agreed with itself while the rail refused `dev-project`.

    So: the population is the registry, the measurement is the CLI's exit code, and
    SUPPORTED is the claim. A new built-in layout that maps the classes and can see
    them fails this test until someone updates SUPPORTED deliberately — which is the
    entire point of a denominator you cannot edit by accident.
    """
    from scripts.wiki_index.layout_config import layout_choices

    SUPPORTED = {"cybos", "dev-project"}
    # flat / per-project are ALIASES of karpathy (layout_config.resolve_alias), so
    # they inherit its zero typed classes. Stated, because "6 names, 4 grammars" is
    # exactly the kind of thing a denominator claim gets wrong.
    accepted: set[str] = set()
    for name in layout_choices():
        v = _vault(tmp_path / name, name)
        src = _source(v, "notes/n.md")
        code, env = _prepare(capsys, v, src, tmp_path / f"{name}.db")
        assert code in (0, 2), f"{name}: unexpected exit {code}"
        if code == 0:
            accepted.add(name)
        else:
            assert env["error"] in {
                "LAYOUT_CANNOT_INDEX_CLASSES", "TYPED_DIR_NOT_COVERED_BY_LAYOUT",
            }, f"{name}: refused for an unexpected reason: {env['error']}"

    assert accepted == SUPPORTED, (
        f"the rail accepts {sorted(accepted)}, the roster says {sorted(SUPPORTED)}. "
        f"Support is a CONJUNCTION (type_mapping ∧ the read globs); a layout with "
        f"only one half is not supported, it is a trap.")
