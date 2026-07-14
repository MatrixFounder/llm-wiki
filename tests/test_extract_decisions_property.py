"""TASK 063-15 — ★ THE PROPERTY: `(delta-clean) AND (G6)`.

    THE DELTA PROPERTY CATCHES **HARM**. G6 CATCHES **SILENCE**.

A rail that writes glob-invisible files — or that writes NOTHING AT ALL — passes the
delta property perfectly. That is why the acceptance criterion is a CONJUNCTION, and
why this module's most important test is the one that PROVES the delta half alone is
satisfiable by doing nothing.

★ G6 IS ANCHORED ON THE SUBMITTED CANDIDATE BATCH — the only EXTERNAL ground truth in
this file. An earlier draft anchored it on `pages_written == pages_indexed`: two
numbers THE RAIL REPORTS ABOUT ITSELF. Under a no-op `apply` that is `0 == 0` and G6
PASSES — so the half that exists to catch silence was itself satisfiable by silence.
A self-consistency check between two of the rail's own outputs is not a measurement.

★ THE VAULT IS BUILT IN `tmp_path`, never in `samples/` — `samples/` is gitignored, and
on a clean checkout an acceptance gate anchored there would SKIP, joining the
baseline's "5 skipped" in silence. A check that examined nothing, reporting green, in
this task's own acceptance criteria.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout_config import _apply_slug_strategy
from scripts.wiki_index.lint import run_all_checks
from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills.wiki_extract_decisions import main

VAULT_ID = "test-vault"

SOURCE = """# Протокол встречи с SetlTech

Мы решили отказаться от Kafka в MVP.
Заказчик требует latency < 200ms.
Риск: клиент может уйти к конкуренту.
Старое решение про очереди больше не действует.
"""


def _slug(title: str) -> str:
    return _apply_slug_strategy(title, "transliterate")


# ★ THE SUBMITTED BATCH — the EXTERNAL ground truth every G6 clause is anchored on.
# Realistic: three classes, a forward edge, and a supersede that triggers G3.
BATCH: list[dict[str, Any]] = [
    {
        "class": "requirement",
        "title": "Latency под 200ms",
        "status": "draft",
        "body": "Клиент требует ответ быстрее 200 миллисекунд.",
        "source_quote": "Заказчик требует latency < 200ms.",
    },
    {
        "class": "decision",
        "title": "Отказаться от Kafka в MVP",
        "status": "accepted",
        "body": "Kafka избыточна: очередь заменяется на прямой вызов.",
        "source_quote": "Мы решили отказаться от Kafka в MVP.",
        "edges": {
            "implements": [_slug("Latency под 200ms")],
            "supersedes": ["dec-ocheredi"],
        },
    },
    {
        "class": "risk",
        "title": "Клиент может уйти к конкуренту",
        "status": "open",
        "body": "Если latency не будет достигнута, клиент уйдёт.",
        "source_quote": "Риск: клиент может уйти к конкуренту.",
    },
]


def _build_vault(root: Path, db: Path, layout: str = "cybos") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "WIKI_SCHEMA.md").write_text(
        f"---\nvault_id: {VAULT_ID}\nlanguage: ru\nlayout: {layout}\n---\n",
        encoding="utf-8")
    (root / "meetings").mkdir(exist_ok=True)
    (root / "meetings" / "m1.md").write_text(SOURCE, encoding="utf-8")

    # the supersede target — a pre-existing, LIVE decision
    (root / "decisions").mkdir(exist_ok=True)
    (root / "decisions" / "dec-ocheredi.md").write_text(
        "---\ntype: decision\nslug: dec-ocheredi\nstatus: accepted\n"
        "title: Использовать очереди\n---\n# Очереди\n\nСтарое решение.\n",
        encoding="utf-8")

    r = SQLiteRepository(db)
    r.apply_schema()
    r.register_vault(Vault(vault_id=VAULT_ID, name=VAULT_ID, root_path=root,
                           schema_version="7.0",
                           registered_at=datetime(2026, 7, 14)))
    r.close()
    _reindex_full(root, db)
    return root


def _reindex_full(vault: Path, db: Path) -> None:
    """★ `--full`, NEVER `--delta`. Drift reads the AUTO-DERIVED INVERSE edges, and
    `--delta` leaves them transiently stale on one side of a bidirectionally-authored
    edge (`lint.py:298`, verbatim: "`--strict` drift gating assumes a recent `--full`").
    A `--delta` acceptance test can report `lint_before == lint_after` WHILE THE VAULT
    IS ACTUALLY DRIFTED — a check that examined nothing, reporting green, inside this
    task's own acceptance criteria."""
    repo = make_repo({"vault_id": VAULT_ID, "db_path": str(db),
                      "vault_root": str(vault)})
    try:
        reindex_full(repo, VAULT_ID)
    finally:
        repo.close()


def _lint_issues(vault: Path, db: Path) -> list[tuple[str, str]]:
    """The FULL sorted issue list — every category, never a filtered subset.

    `--strict` gates 13 categories, most of which the rail never touches. Comparing a
    SUBSET would be the same lie in a smaller font: it would hide a category the rail
    newly breaks simply because the test did not look at it."""
    repo = make_repo({"vault_id": VAULT_ID, "db_path": str(db),
                      "vault_root": str(vault)})
    try:
        issues = run_all_checks(repo, vaults=[VAULT_ID], strict=True)
    finally:
        repo.close()
    return sorted(
        (str(i.kind), str(getattr(i, "slug", "") or getattr(i, "detail", "")))
        for i in issues
    )


def _run_rail(vault: Path, db: Path, batch: list[dict[str, Any]],
              capsys: pytest.CaptureFixture[str], *, ingest: bool = True,
              ) -> dict[str, Any]:
    code = main(["prepare", "--vault", VAULT_ID, "--vault-root", str(vault),
                 "--source-page", "meetings/m1.md", "--db-path", str(db)])
    prep = json.loads(capsys.readouterr().out.strip())
    assert code == 0, prep

    cand_file = vault.parent / "batch.json"
    cand_file.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")
    code = main(["apply", "--vault", VAULT_ID, "--vault-root", str(vault),
                 "--source-page", "meetings/m1.md",
                 "--source-hash", prep["source_hash"],
                 "--candidates-file", str(cand_file), "--db-path", str(db),
                 *(["--ingest"] if ingest else [])])
    env: dict[str, Any] = json.loads(capsys.readouterr().out.strip())
    assert code == 0, env
    return env


# --------------------------------------------------------------------------- #
# ★ G6 — every clause anchored on the SUBMITTED BATCH, read back from the REPO
# --------------------------------------------------------------------------- #


def _assert_g6(vault: Path, db: Path, batch: list[dict[str, Any]]) -> None:
    """★ THE POSITIVE HALF. LHS = the batch the TEST submitted. RHS = the REPO.

    Never the rail's envelope: lint is STRUCTURALLY INCAPABLE of seeing a
    glob-invisible page (`find_pages_missing_in_index` walks via `discover_pages`, so
    an unglobbed file is never even DISCOVERED), and the rail's own report of what it
    wrote would happily agree with itself about a page the index does not have.
    """
    repo = make_repo({"vault_id": VAULT_ID, "db_path": str(db),
                      "vault_root": str(vault)})
    try:
        conn = repo._connect()

        # G6a — EVERY candidate has a `pages` row, with the right class.
        for cand in batch:
            slug = _slug(str(cand["title"]))
            row = conn.execute(
                "SELECT json_extract(frontmatter_json, '$.type') AS cls "
                "FROM pages WHERE vault_id = ? AND slug = ?",
                (VAULT_ID, slug)).fetchone()
            assert row is not None, f"G6a: no `pages` row for submitted candidate {slug!r}"
            assert row["cls"] == cand["class"], (
                f"G6a: {slug!r} indexed as {row['cls']!r}, batch says {cand['class']!r}")

        # G6b — EVERY authored forward edge is a ref row, AND its inverse is derived.
        inverses = {"implements": "implemented-by", "supersedes": "superseded-by"}
        for cand in batch:
            src = _slug(str(cand["title"]))
            for edge, targets in (cand.get("edges") or {}).items():
                for target in targets:
                    fwd = conn.execute(
                        "SELECT 1 FROM page_entity_refs WHERE vault_id = ? "
                        "AND page_slug = ? AND entity_slug = ? AND ref_type = ?",
                        (VAULT_ID, src, target, edge)).fetchone()
                    assert fwd is not None, f"G6b: forward edge {edge} {src}→{target} missing"
                    inv = inverses[edge]
                    back = conn.execute(
                        "SELECT 1 FROM page_entity_refs WHERE vault_id = ? "
                        "AND page_slug = ? AND entity_slug = ? AND ref_type = ?",
                        (VAULT_ID, target, src, inv)).fetchone()
                    assert back is not None, (
                        f"G6b: the INVERSE {inv} {target}→{src} was not auto-derived "
                        f"(M-1 broken, or the reindex was --delta)")

        # G6d — the COUNTS, from the repo, compared against the BATCH.
        indexed = conn.execute(
            "SELECT COUNT(*) AS n FROM pages WHERE vault_id = ? "
            "AND json_extract(frontmatter_json, '$.extracted_from') = 'm1'",
            (VAULT_ID,)).fetchone()["n"]
        assert indexed == len(batch), (
            f"G6d: {len(batch)} candidates submitted, {indexed} indexed. "
            f"A rail that writes nothing reports 0 == 0 and passes a self-check; "
            f"this compares against the BATCH.")

        authored = sum(len(t) for c in batch
                       for t in (c.get("edges") or {}).values())
        edge_types = tuple(inverses) + tuple(inverses.values())
        placeholders = ",".join("?" * len(edge_types))
        edges_indexed = conn.execute(
            f"SELECT COUNT(*) AS n FROM page_entity_refs "
            f"WHERE vault_id = ? AND ref_type IN ({placeholders})",
            (VAULT_ID, *edge_types)).fetchone()["n"]
        assert edges_indexed == authored * 2, (
            f"G6d: {authored} forward edges authored ⇒ {authored * 2} rows expected "
            f"(forward + auto-derived inverse); found {edges_indexed}")
    finally:
        repo.close()


# --------------------------------------------------------------------------- #
# THE TESTS
# --------------------------------------------------------------------------- #


def test_property_conjunction_on_a_clean_vault(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """★ THE ACCEPTANCE GATE — both halves, on a clean cybos vault.

    The delta is `before == after`, NEVER `after == []`: `--strict` gates 13 categories
    including pre-existing vault state the rail never touched, and an `== []` assertion
    tests the FIXTURE, not the RAIL.
    """
    v = _build_vault(tmp_path / "v", tmp_path / "x.db")
    db = tmp_path / "x.db"

    before = _lint_issues(v, db)
    assert before == [], (
        "the fixture must be lint-clean BEFORE the run — the property's PREMISE has to "
        "be exercised, or the delta is trivially true")

    env = _run_rail(v, db, BATCH, capsys)
    _reindex_full(v, db)
    after = _lint_issues(v, db)

    # Half 1 — HARM.
    assert before == after, f"the rail introduced lint issues: {set(after) - set(before)}"

    # Half 2 — SILENCE.
    _assert_g6(v, db, BATCH)

    # ...and G3 did its job: the superseded target was reconciled (else the vault's own
    # drift rule would have fired and `after` would not equal `before`).
    assert len(env["reconciled"]) == 1
    assert env["reconciled"][0]["to"] == "superseded"


def test_the_DELTA_HALF_ALONE_IS_SATISFIABLE_BY_SILENCE(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★★ THE META-TEST THAT JUSTIFIES THE CONJUNCTION.

    Make `apply` write NOTHING. Then:
      * the DELTA half PASSES — perfectly, because nothing changed;
      * G6 FAILS — because the batch was submitted and the pages are not there.

    This is the test that proves our acceptance criterion is NOT satisfiable by doing
    nothing. An earlier draft of G6 anchored on `pages_written == pages_indexed` —
    two numbers the RAIL reports about ITSELF — which under this very no-op is `0 == 0`
    and PASSES. The half that exists to catch silence was itself satisfiable by silence,
    and this meta-test would have been decorative.

    MUT (real, not decorative): re-anchor G6d on the rail's own `written` count ⇒ G6
    passes under the no-op ⇒ this test goes RED. If G6 ever passes a no-op apply, G6 is
    not a gate.
    """
    import scripts.wiki_skills.wiki_extract_decisions._pages as pages_mod

    v = _build_vault(tmp_path / "v", tmp_path / "x.db")
    db = tmp_path / "x.db"
    before = _lint_issues(v, db)
    assert before == []

    # the no-op: the rail runs, validates, reports — and writes nothing.
    monkeypatch.setattr(
        pages_mod, "write_page",
        lambda vault_root, typed_dir, slug, payload: (
            Path(vault_root) / typed_dir / f"{slug}.md", "unchanged"))
    import scripts.wiki_skills.wiki_extract_decisions as wed
    monkeypatch.setattr(wed, "write_page", pages_mod.write_page)

    # NOTE: no `--ingest`. With it, `validate_manifest`'s containment check catches the
    # missing file on its own (exit 6) — a genuinely good property, and one worth
    # knowing, but NOT the one under test. The scenario here is the dangerous one: a
    # rail that reports SUCCESS having written nothing. That is what the delta half
    # cannot see and G6 must.
    _run_rail(v, db, BATCH, capsys, ingest=False)
    _reindex_full(v, db)
    after = _lint_issues(v, db)

    # ★ The delta half PASSES. This is the point of the test, so it is ASSERTED.
    assert before == after, (
        "the no-op must pass the delta half — if it did not, this meta-test would be "
        "proving something else")

    # ★ ...and G6 CATCHES IT.
    with pytest.raises(AssertionError, match="G6"):
        _assert_g6(v, db, BATCH)


def test_a_GLOB_INVISIBLE_page_is_caught_by_G6_and_NOT_by_lint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★ THE EMPIRICAL PROOF OF THE SPEC'S CENTRAL CLAIM.

    Without this test, "lint cannot see a glob-invisible page" is an ASSERTION. With
    it, it is a MEASUREMENT.

    Force one page outside the layout's globs (bypassing the 063-02 load gate, which is
    what normally makes this unreachable). Then:
      * the lint delta is CLEAN — proving lint's STRUCTURAL blindness:
        `find_pages_missing_in_index` walks via `discover_pages`, so an unglobbed file
        is never even DISCOVERED, and a check that never discovers a file cannot report
        it;
      * G6 FAILS — 3 submitted, 2 indexed.

    This is exactly the loss the G4 gate exists to prevent, and exactly why the
    acceptance criterion cannot be the delta alone.
    """
    import scripts.wiki_skills.wiki_extract_decisions as wed
    import scripts.wiki_skills.wiki_extract_decisions._pages as pages_mod

    v = _build_vault(tmp_path / "v", tmp_path / "x.db")
    db = tmp_path / "x.db"
    before = _lint_issues(v, db)
    assert before == []

    real_write = pages_mod.write_page
    invisible_slug = _slug("Клиент может уйти к конкуренту")

    def _sabotage(vault_root: Path, typed_dir: str, slug: str, payload: str) -> Any:
        # `_scratch/` matches no cybos glob — the walker will never see it.
        if slug == invisible_slug:
            return real_write(vault_root, "_scratch", slug, payload)
        return real_write(vault_root, typed_dir, slug, payload)

    monkeypatch.setattr(wed, "write_page", _sabotage)

    _run_rail(v, db, BATCH, capsys)
    _reindex_full(v, db)
    after = _lint_issues(v, db)

    # ★ THE PAGE IS ON DISK...
    assert (v / "_scratch" / f"{invisible_slug}.md").is_file()

    # ★ ...AND LINT IS PERFECTLY CLEAN ABOUT IT. Measured, not claimed.
    assert before == after, (
        "if lint DID see this, the whole G4 apparatus would be unnecessary — and the "
        "spec's central claim would be false")

    # ★ ...AND G6 CATCHES IT: 3 submitted, 2 indexed.
    with pytest.raises(AssertionError, match="G6"):
        _assert_g6(v, db, BATCH)


def test_dev_project_property_holds_VACUOUSLY_and_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`dev-project` maps the typed classes but declares NO `ontology:` block. The
    property still HOLDS — and the envelope says `vacuous_validation: true`, so the
    green is HONEST about what it validated rather than looking like a full pass.

    ⚠️ REACHABLE ONLY BECAUSE 063-02 ADDED dev-project's three `paths[]` globs. Before
    that, `prepare` REFUSED the layout and this test could never have passed — the
    plan-review C-2 finding, as a live dependency rather than a footnote.
    """
    v = _build_vault(tmp_path / "v", tmp_path / "x.db", layout="dev-project")
    db = tmp_path / "x.db"
    before = _lint_issues(v, db)

    # no ontology ⇒ no drift rules ⇒ no supersede reconciliation; drop that edge
    batch = [dict(c) for c in BATCH]
    batch[1] = {**batch[1], "edges": {"implements": [_slug("Latency под 200ms")]}}

    env = _run_rail(v, db, batch, capsys)
    _reindex_full(v, db)

    assert before == _lint_issues(v, db)
    _assert_g6(v, db, batch)
    assert env["vacuous_validation"] is True
    assert env["validation"]["edges_checked"] == 0
    assert env["validation"]["properties_checked"] == 0


def test_the_acceptance_module_uses_FULL_reindex_never_delta() -> None:
    """A comment saying "use --full" is not a gate. This is.

    `--delta` leaves the auto-derived INVERSE edges transiently stale, so a `--delta`
    acceptance test can report `lint_before == lint_after` while the vault is ACTUALLY
    DRIFTED — a check that examined nothing, reporting green, inside the acceptance
    criteria themselves.

    ⚠️ MEASURED ON THE COMPILED CODE, NOT THE SOURCE TEXT — and the first draft of THIS
    GATE was itself the disease, for the fifth time in this task. It grepped the module
    for the string `--delta` and matched its OWN PROSE (the paragraphs explaining why
    delta is wrong) and its OWN SOURCE LINE. A gate that fails on the explanation of
    why it exists would force the explanation out to stay green.

    `co_names` holds the globals a function actually calls. The one reindex helper in
    this module must call `reindex_full`, and nothing here may call a delta path.
    """
    import inspect
    import sys

    mod = sys.modules[__name__]
    reindexers = [
        (name, fn) for name, fn in vars(mod).items()
        if inspect.isfunction(fn) and fn.__module__ == __name__
        and name.startswith("_") and "reindex" in name
    ]
    assert [n for n, _ in reindexers] == ["_reindex_full"], (
        f"a second reindex helper appeared: {[n for n, _ in reindexers]} — every one "
        f"of them must be gated, not just the one this test remembers")
    for name, fn in reindexers:
        names = fn.__code__.co_names
        assert "reindex_full" in names, f"{name} does not call reindex_full"
        assert not any("delta" in n for n in names), (
            f"{name} calls a delta path: {sorted(n for n in names if 'delta' in n)}")
