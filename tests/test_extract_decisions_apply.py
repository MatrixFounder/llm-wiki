"""TASK 063-06…063-12 — `apply`: validation, the normative ordering, and the write.

These beads are ONE FUNCTION. Splitting their tests would ship VACUOUS GATES: a
"zero files written" assertion against a rail that cannot write yet passes for the
wrong reason, and a vacuous gate is this task's own disease.

The three anti-fabrication mechanisms, the four G1 checks, G2, the ordering, and the
write are each pinned here with a mutation that takes them RED.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.wiki_index.layout_config import _apply_slug_strategy, resolve_layout_config
from scripts.wiki_skills.wiki_extract_decisions import main

BODY = (
    "# Протокол встречи\n\n"
    "Мы решили отказаться от Kafka в MVP.\n"
    "Заказчик требует latency < 200ms.\n"
    "Риск: клиент может уйти к конкуренту.\n"
)


def _vault(root: Path, layout: str = "cybos", *, override: dict[str, Any] | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "WIKI_SCHEMA.md").write_text(
        f"---\nvault_id: test-vault\nlanguage: ru\nlayout: {layout}\n"
        + ("layout_config: .wiki/layout.yaml\n" if override else "")
        + "---\n", encoding="utf-8")
    if override:
        (root / ".wiki").mkdir(exist_ok=True)
        (root / ".wiki" / "layout.yaml").write_text(
            yaml.safe_dump(override, allow_unicode=True), encoding="utf-8")
    src = root / "meetings" / "m1.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(BODY, encoding="utf-8")
    return root


def _prepared(capsys: pytest.CaptureFixture[str], vault: Path, db: Path) -> dict[str, Any]:
    _register(vault, db)
    code = main(["prepare", "--vault", "test-vault", "--vault-root", str(vault),
                 "--source-page", "meetings/m1.md", "--db-path", str(db)])
    env: dict[str, Any] = json.loads(capsys.readouterr().out.strip())
    assert code == 0, env
    return env


def _apply(
    capsys: pytest.CaptureFixture[str], vault: Path, db: Path,
    candidates: Any, source_hash: str, *, extra: list[str] | None = None,
) -> tuple[int, dict[str, Any]]:
    cand_file = vault.parent / "cands.json"
    cand_file.write_text(json.dumps(candidates, ensure_ascii=False), encoding="utf-8")
    code = main([
        "apply", "--vault", "test-vault", "--vault-root", str(vault),
        "--source-page", "meetings/m1.md", "--source-hash", source_hash,
        "--candidates-file", str(cand_file), "--db-path", str(db),
        *(extra or []),
    ])
    return code, json.loads(capsys.readouterr().out.strip())


def _cand(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "class": "decision",
        "title": "Отказаться от Kafka в MVP",
        "status": "accepted",
        "body": "Kafka избыточна для MVP.",
        "source_quote": "Мы решили отказаться от Kafka в MVP.",
    }
    base.update(kw)
    return base


def _register(vault: Path, db: Path) -> None:
    """Register the vault. `vault_id` is a FOREIGN KEY (ADR-002 §D1.1), so an
    unregistered vault is a REAL refusal, not a test artefact — the rail is right to
    fail on one."""
    from datetime import datetime

    from scripts.wiki_index.models import Vault
    from scripts.wiki_index.sqlite_repository import SQLiteRepository

    r = SQLiteRepository(db)
    r.apply_schema()
    if not r.get_vault("test-vault"):          # idempotent — callers may register twice
        r.register_vault(Vault(
            vault_id="test-vault", name="test-vault", root_path=vault,
            schema_version="7.0", registered_at=datetime(2026, 7, 14)))
    r.close()


def _reindex(vault: Path, db: Path) -> None:
    """Full reindex on the vault — `--full`, never `--delta`: inverse-edge derivation
    is exactly what `--delta` leaves transiently stale (`lint.py:298`)."""
    from scripts.wiki_index.factory import make_repo
    from scripts.wiki_index.reindex import reindex_full
    _register(vault, db)
    repo = make_repo({"vault_id": "test-vault", "db_path": str(db),
                      "vault_root": str(vault)})
    try:
        reindex_full(repo, "test-vault")
    finally:
        repo.close()


def _written(vault: Path) -> list[Path]:
    return sorted(p for d in ("decisions", "requirements", "risks")
                  for p in (vault / d).glob("*.md"))


# --------------------------------------------------------------------------- #
# ★ Anti-fabrication — the three MECHANISMS
# --------------------------------------------------------------------------- #


def test_empty_candidates_is_SUCCESS_exit_0(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """★ THE SINGLE MOST IMPORTANT TEST IN THE RAIL.

    A note with no decisions in it is a NORMAL NOTE. If an empty set were a failure,
    the model's cheapest path to a green run would be to INVENT a decision — so the
    check that looks like a formality is in fact the whole anti-fabrication posture.

    MUT: set `CANDIDATE_COUNT_MIN = 1` ⇒ RED (and in production: fabricated knowledge
    written into the operator's vault, grounded in a quote it had to invent too).
    """
    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"
    p = _prepared(capsys, v, db)
    code, env = _apply(capsys, v, db, [], p["source_hash"])

    assert code == 0
    assert env["action"] == "no_candidates"
    assert env["written"] == []
    assert _written(v) == []


def test_quote_not_in_body_REFUSES(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Mechanism 2: verbatim grounding. A decision the source does not contain has no
    quote to point at — which is what makes fabrication mechanically expensive rather
    than merely discouraged."""
    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"
    p = _prepared(capsys, v, db)
    code, env = _apply(capsys, v, db,
                       [_cand(source_quote="Мы решили использовать Kafka везде.")],
                       p["source_hash"])
    assert code == 4
    assert env["error"] == "FIELD_QUOTE_NOT_IN_BODY"
    assert env["written"] == []
    assert _written(v) == []


def test_the_NO_QUOTE_CHECK_env_escape_is_NOT_honoured(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★ Mechanism 3. The PRECEDENT honours `WIKI_EXTRACT_NO_QUOTE_CHECK`. This rail
    does not — an escape hatch on an anti-fabrication check IS the fabrication path,
    and it gets reached exactly when someone is in a hurry.

    Asserted as BEHAVIOUR, not merely as an absent grep: the env var is set, and the
    refusal still happens.
    """
    monkeypatch.setenv("WIKI_EXTRACT_NO_QUOTE_CHECK", "1")
    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"
    p = _prepared(capsys, v, db)
    code, env = _apply(capsys, v, db, [_cand(source_quote="fabricated")],
                       p["source_hash"])
    assert code == 4
    assert env["error"] == "FIELD_QUOTE_NOT_IN_BODY"


def test_the_rail_READS_NO_ENVIRONMENT_VARIABLE_AT_ALL() -> None:
    """"We do not honour the escape" and "the escape is not reachable" are different
    claims, and only the second survives a refactor. So this asserts the STRONGER,
    structural one: the package reads NO environment variable whatsoever.

    ⚠️ Measured on the COMPILED CODE, not the source text — for the third time in this
    task, a text grep proved unable to tell a MENTION from a USE. A
    `grep NO_QUOTE_CHECK` gate fails on the shipped code because the module docstring
    EXPLAINS why the escape is not honoured: the gate would force the explanation out
    to stay green — deleting the knowledge it exists to protect.

    `co_names` holds the globals a function actually references. No `getenv`, no
    `environ`, anywhere in the package ⇒ no env var can turn any mechanism off, and
    no future one can be added without this test noticing.
    """
    import inspect

    from scripts.wiki_skills import wiki_extract_decisions as wed

    pkg_dir = Path(wed.__file__).resolve().parent
    offenders: list[str] = []
    for path in sorted(pkg_dir.rglob("*.py")):
        module_name = f"scripts.wiki_skills.wiki_extract_decisions" + (
            "" if path.name == "__init__.py" else f".{path.stem}")
        try:
            mod = __import__(module_name, fromlist=["_"])
        except ImportError:
            continue
        for name, fn in vars(mod).items():
            if not inspect.isfunction(fn) or fn.__module__ != module_name:
                continue
            if {"getenv", "environ"} & set(fn.__code__.co_names):
                offenders.append(f"{path.name}::{name}")
    assert offenders == [], (
        f"the rail reads an environment variable: {offenders}. No mechanism here may "
        f"have an off switch — an escape hatch on an anti-fabrication check IS the "
        f"fabrication path.")


def test_missing_source_quote_key_refuses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The key is REQUIRED. Absence is not "no grounding needed"."""
    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"
    p = _prepared(capsys, v, db)
    bad = _cand()
    del bad["source_quote"]
    code, env = _apply(capsys, v, db, [bad], p["source_hash"])
    assert code == 4
    assert _written(v) == []


def test_unknown_field_refuses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A misspelled `sorce_quote` must NOT silently disable grounding — which is what
    a lenient schema would do: the required key would be "missing", the typo ignored,
    and the operator would see a confusing error instead of the real one."""
    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"
    p = _prepared(capsys, v, db)
    code, env = _apply(capsys, v, db, [_cand(sorce_quote="x")], p["source_hash"])
    assert code == 4
    assert env["error"] == "UNKNOWN_FIELD"


def test_class_outside_the_roster_refuses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Q-063-3 — THE ROSTER IS WHAT KEEPS MEETING PARTICIPANTS OUT OF THE GRAPH.
    `class: person` is refused HERE; the `wiki-import` pyramid guard does not cover
    this rail, so the operator's rule (attendees go in `participants:`, not into the
    knowledge graph) has no other enforcement point on this path."""
    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"
    p = _prepared(capsys, v, db)
    code, env = _apply(capsys, v, db, [_cand(**{"class": "person"})], p["source_hash"])
    assert code == 4
    assert env["error"] == "ONTOLOGY_VIOLATION"
    assert _written(v) == []


def test_validation_failure_touches_NO_DB(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★ "A contract violation writes ZERO files" is true BY CONSTRUCTION, not by
    care: the schema pass runs before the repo is ever opened. Proven by making
    `make_repo` EXPLODE — a schema-invalid payload must still exit 4, which is only
    possible if the DB was never reached."""
    import scripts.wiki_skills.wiki_extract_decisions as wed

    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"
    p = _prepared(capsys, v, db)

    def _boom(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("the DB was opened before validation finished")

    monkeypatch.setattr(wed, "make_repo", _boom)
    code, env = _apply(capsys, v, db, [_cand(source_quote="nope")], p["source_hash"])
    assert code == 4


# --------------------------------------------------------------------------- #
# ★ Slugs + collisions — two DIFFERENT rules
# --------------------------------------------------------------------------- #


def test_in_batch_transliterate_collision_REFUSES_the_batch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """★ THE SILENT-LOSS CASE, and the reason this needs its own gate.

    cybos declares `slug_strategy: transliterate`; the protocols are RUSSIAN. Two
    titles that transliterate to the SAME slug would see the second silently
    OVERWRITE the first: one file, one DB row, one decision GONE, and ZERO lint
    issues — because the file that exists is perfectly valid.

    Invisible to the delta property AND to a written-page count, because the count is
    RIGHT. "Last one wins" does not show up in lint.

    MUT: drop the uniqueness check ⇒ ONE file appears where this demands ZERO ⇒ RED.
    Asserted on the FILESYSTEM, not on the envelope: "refused" in JSON is not evidence
    that nothing was written.
    """
    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"
    p = _prepared(capsys, v, db)
    title = "Отказаться от Kafka в MVP"
    code, env = _apply(capsys, v, db, [
        _cand(title=title),
        _cand(title=title, body="дубль"),
    ], p["source_hash"])

    assert code == 4
    assert env["error"] == "IN_BATCH_SLUG_COLLISION"
    assert _written(v) == []                     # ← the filesystem, not the envelope
    assert env["violations"][0]["slug"] == _apply_slug_strategy(title, "transliterate")


def test_slug_uses_the_LAYOUT_strategy_not_a_kebab(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The slug is compared against the ENGINE's own function, never against a
    hardcoded string — a literal here would be a second source of truth and would
    drift from `iter_pages`, indexing the page under a slug nothing links to."""
    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"
    p = _prepared(capsys, v, db)
    title = "Отказаться от Kafka в MVP"
    code, env = _apply(capsys, v, db, [_cand(title=title)], p["source_hash"])

    assert code == 0, env
    cfg = resolve_layout_config(v)
    expected = _apply_slug_strategy(title, cfg.slug_strategy)
    assert env["written"][0]["slug"] == expected
    assert (v / "decisions" / f"{expected}.md").is_file()


# --------------------------------------------------------------------------- #
# ★ G1 — the four checks, and the RANGE one is the one that is easy to fake
# --------------------------------------------------------------------------- #


def test_bad_status_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"
    p = _prepared(capsys, v, db)
    code, env = _apply(capsys, v, db, [_cand(status="done")], p["source_hash"])
    assert code == 4
    assert env["error"] == "ONTOLOGY_VIOLATION"
    assert env["violations"][0]["kind"] == "status"
    assert _written(v) == []


def test_bad_domain_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """cybos: `implements.from` = [decision, task, agent, tool]. A `risk` may not
    author it."""
    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"
    p = _prepared(capsys, v, db)
    code, env = _apply(capsys, v, db, [
        _cand(**{"class": "requirement", "title": "Latency под 200ms",
                 "status": "draft",
                 "source_quote": "Заказчик требует latency < 200ms."}),
        _cand(**{"class": "risk", "title": "Клиент уйдёт", "status": "open",
                 "source_quote": "Риск: клиент может уйти к конкуренту.",
                 "edges": {"implements": ["latency-pod-200ms"]}}),
    ], p["source_hash"])
    assert code == 4
    kinds = {vv["kind"] for vv in env["violations"]}
    assert "domain" in kinds
    assert _written(v) == []


def test_all_violations_listed_AT_ONCE(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A validator that stops at the first error makes the caller iterate BLIND — it
    repairs one thing, re-runs, meets the next — and a model repairing blind starts
    GUESSING what else might be wrong. One repair round, not N.

    MUT: return on the first violation ⇒ RED.
    """
    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"
    p = _prepared(capsys, v, db)
    code, env = _apply(capsys, v, db, [
        _cand(status="done"),                                    # status
        _cand(**{"class": "risk", "title": "Клиент уйдёт", "status": "invalid",
                 "source_quote": "Риск: клиент может уйти к конкуренту."}),  # status
    ], p["source_hash"])
    assert code == 4
    assert len(env["violations"]) == 2


# --------------------------------------------------------------------------- #
# ★ G2 — PROSE CREATES REFS
# --------------------------------------------------------------------------- #


def test_a_bare_ID_in_PROSE_is_a_ref_and_must_resolve(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """★ THE TEST THIS WHOLE SURFACE EXISTS FOR.

    cybos ships an `id-ref` rule, so "это отменяет DEC-004" IN BODY TEXT is a ref —
    and `find_orphan_links` scans `page_entity_refs` with NO `ref_type` filter, so
    there is nowhere for it to hide at lint time.

    A validator that only looked at `[[wikilinks]]` (the v2 assumption) would ACCEPT
    this page, and `wiki-lint` would then REJECT it: the delta property broken by our
    own hand. The operator would experience it as "the rail is flaky".

    MUT: validate only wikilinks ⇒ RED.
    """
    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"
    p = _prepared(capsys, v, db)
    code, env = _apply(capsys, v, db,
                       [_cand(body="Это отменяет DEC-004.")], p["source_hash"])
    assert code == 4
    assert env["error"] == "UNRESOLVED_REF"
    assert env["violations"][0]["target"] == "dec-004"
    assert _written(v) == []


def test_in_batch_wikilink_resolves(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A decision implementing a requirement that is IN THE SAME BATCH resolves — the
    batch's own slugs are part of the resolvable set."""
    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"
    p = _prepared(capsys, v, db)
    req_slug = _apply_slug_strategy("Latency под 200ms", "transliterate")
    code, env = _apply(capsys, v, db, [
        _cand(**{"class": "requirement", "title": "Latency под 200ms",
                 "status": "draft",
                 "source_quote": "Заказчик требует latency < 200ms."}),
        _cand(edges={"implements": [req_slug]}),
    ], p["source_hash"])

    assert code == 0, env
    assert len(env["written"]) == 2
    assert env["validation"]["links_checked"] >= 1


def test_frontmatter_edges_are_ALSO_scanned(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The rules run over the FULL RENDERED PAGE — frontmatter included. An
    unresolvable slug in `edges.supersedes` is refused even though it never appears
    in the body."""
    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"
    p = _prepared(capsys, v, db)
    code, env = _apply(capsys, v, db,
                       [_cand(edges={"supersedes": ["dec-ghost"]})], p["source_hash"])
    assert code == 4
    assert env["error"] == "UNRESOLVED_REF"
    assert env["violations"][0]["target"] == "dec-ghost"


# --------------------------------------------------------------------------- #
# ★ H-6
# --------------------------------------------------------------------------- #


def test_traversal_in_an_edge_target_is_REFUSED_not_normalised(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A candidate is model output about untrusted text — two layers of untrust.
    Normalising a traversal is how you end up writing outside the vault while
    believing you sanitised it."""
    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"
    p = _prepared(capsys, v, db)
    code, env = _apply(capsys, v, db,
                       [_cand(edges={"supersedes": ["../../etc/passwd"]})],
                       p["source_hash"])
    assert code == 4
    assert _written(v) == []


def test_frontmatter_breakout_is_REFUSED(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `status:` containing a bare `---` line CLOSES the frontmatter block early —
    everything after it is injected markdown. Reachable by saying the right sentence
    in a meeting.

    Two claims, both asserted: the PAYLOAD is refused, AND no file on disk carries it.
    MUT: remove the YAML-delimiter guard ⇒ RED.
    """
    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"
    p = _prepared(capsys, v, db)
    code, env = _apply(capsys, v, db,
                       [_cand(status="accepted\n---\nmalicious: true")],
                       p["source_hash"])
    assert code == 4
    assert _written(v) == []
    assert "malicious" not in json.dumps(env)      # CWE-117: never echo the payload


def test_apply_NEVER_authors_an_aliases_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Closes the `alias-collision` lint category BY CONSTRUCTION: a category you
    cannot enter needs no guard. Checked on EVERY page of a multi-candidate batch,
    not just the first."""
    import frontmatter

    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"
    p = _prepared(capsys, v, db)
    code, _ = _apply(capsys, v, db, [
        _cand(),
        _cand(**{"class": "risk", "title": "Клиент уйдёт", "status": "open",
                 "source_quote": "Риск: клиент может уйти к конкуренту."}),
    ], p["source_hash"])
    assert code == 0
    pages = _written(v)
    assert len(pages) == 2
    for page in pages:
        assert "aliases" not in frontmatter.loads(
            page.read_text(encoding="utf-8")).metadata


def test_classification_is_INHERITED_from_the_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """★ NO DECLASSIFICATION PUMP (R-063-10(b)).

    Honest: this behaviour is INERT today — policy is declared-but-off, and
    `classification-leak` fires only on `cited`/`verifies` refs, which typed pages do
    not carry. The test exists anyway, because an inert guard with NO TEST is a guard
    that silently disappears in the refactor before R-16 lands — and then a decision
    extracted from a `confidential` transcript quietly picks up the vault default and
    the rail becomes a declassification pump, via a config flip somewhere else.

    MUT: drop the inheritance ⇒ RED.
    """
    import frontmatter

    v = _vault(tmp_path / "v")
    (v / "meetings" / "m1.md").write_text(
        "---\nclassification: confidential\n---\n" + BODY, encoding="utf-8")
    db = tmp_path / "x.db"
    p = _prepared(capsys, v, db)
    code, _ = _apply(capsys, v, db, [_cand()], p["source_hash"])
    assert code == 0
    page = _written(v)[0]
    assert frontmatter.loads(
        page.read_text(encoding="utf-8")).metadata["classification"] == "confidential"


# --------------------------------------------------------------------------- #
# ★ The write + the manifest + idempotency
# --------------------------------------------------------------------------- #


def test_writes_to_the_LAYOUT_DERIVED_dir(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Same candidate, two layouts, two placements — because placement is a property
    of the LAYOUT'S read grammar, not of the rail's preference.

    MUT: hardcode the sibling ⇒ the cybos assertion RED (and the page would be
    glob-invisible: written, never indexed, zero lint issues).
    """
    v = _vault(tmp_path / "cy")
    db = tmp_path / "a.db"
    p = _prepared(capsys, v, db)
    code, env = _apply(capsys, v, db, [_cand()], p["source_hash"])
    assert code == 0
    assert env["written"][0]["path"].startswith("decisions/")   # ROOT on cybos

    para = _vault(tmp_path / "pa", "obsidian-personal", override={
        "type_mapping": {
            "decision": {"db_type": "research", "tag": "decision"},
            "requirement": {"db_type": "brief", "tag": "requirement"},
            "risk": {"db_type": "research", "tag": "risk"},
        }})
    (para / "meetings").rename(para / "06 - BD")
    db2 = tmp_path / "b.db"
    code = main(["prepare", "--vault", "test-vault", "--vault-root", str(para),
                 "--source-page", "06 - BD/m1.md", "--db-path", str(db2)])
    p2 = json.loads(capsys.readouterr().out.strip())
    assert code == 0, p2
    assert p2["typed_dirs"]["decision"] == "06 - BD/decisions"   # SIBLING on PARA


def test_forward_edges_ONLY_on_disk(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """★ M-1 INTACT (R-063-4). We author `implements:`; we NEVER author
    `implemented-by:` — the inverse is auto-derived at `wiki-reindex --full`.
    Authoring both sides would make the graph's halves independently editable, and a
    page could then assert an edge whose inverse contradicts it.

    MUT: author the inverse ⇒ RED.
    """
    import frontmatter

    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"
    p = _prepared(capsys, v, db)
    req_slug = _apply_slug_strategy("Latency под 200ms", "transliterate")
    code, _ = _apply(capsys, v, db, [
        _cand(**{"class": "requirement", "title": "Latency под 200ms",
                 "status": "draft",
                 "source_quote": "Заказчик требует latency < 200ms."}),
        _cand(edges={"implements": [req_slug]}),
    ], p["source_hash"])
    assert code == 0

    dec = frontmatter.loads(
        (v / "decisions" / f"{_apply_slug_strategy('Отказаться от Kafka в MVP', 'transliterate')}.md")
        .read_text(encoding="utf-8")).metadata
    assert "implements" in dec
    assert "implemented-by" not in dec and "implemented_by" not in dec


def test_every_page_we_touched_is_in_the_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """★ G5, as a SET EQUALITY computed from the filesystem — never a spot-check.

    `<=` would pass a manifest listing pages we never wrote; `>=` would pass one that
    misses a page we did. Only EQUALITY is the claim: every page we touch is indexed,
    and nothing else is.
    """
    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"
    p = _prepared(capsys, v, db)
    code, env = _apply(capsys, v, db, [
        _cand(),
        _cand(**{"class": "risk", "title": "Клиент уйдёт", "status": "open",
                 "source_quote": "Риск: клиент может уйти к конкуренту."}),
    ], p["source_hash"])
    assert code == 0

    touched = {pp.relative_to(v).as_posix() for pp in _written(v)}
    manifested = {e["path"] for e in env["manifest"]["written"]}
    assert touched == manifested

    # ...and every written page landed in the dir `prepare`'s preflight VERIFIED.
    for entry in env["manifest"]["written"]:
        assert str(Path(entry["path"]).parent) in env["typed_dirs"].values()


def test_unchanged_source_is_a_NOOP(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """R-063-5. The second run writes nothing — and `--force` bypasses it."""
    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"
    p = _prepared(capsys, v, db)
    code, _ = _apply(capsys, v, db, [_cand()], p["source_hash"], extra=["--ingest"])
    assert code == 0

    code, env = _apply(capsys, v, db, [_cand()], p["source_hash"])
    assert code == 0
    assert env["action"] == "unchanged"
    assert env["written"] == []

    code, env = _apply(capsys, v, db, [_cand()], p["source_hash"],
                       extra=["--force"])
    assert code == 0
    assert env["action"] == "applied"
    assert env["written"][0]["action"] == "unchanged"   # content-hash skip


# --------------------------------------------------------------------------- #
# ★★ THE NORMATIVE ORDERING (063-09) — the 7th surface
# --------------------------------------------------------------------------- #


def test_a_survivor_referencing_a_DROPPED_candidate_REFUSES_the_batch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """★★ THE BUG THE ORDERING EXISTS FOR — and BOTH halves of the acceptance
    property are blind to it.

    Submit `{D, R}` where `D.implements: [[r-slug]]`. G1's range check passes against
    the IN-BATCH R. Then R is DROPPED (its slug already exists — someone else owns
    that page). If D is written anyway, D's edge now resolves to the PRE-EXISTING
    page of that slug — whose class is `summary`, which is NOT in `implements.to`.

    We would have AUTHORED an ontology violation. And:
      * the counts still reconcile (the dropped candidate was never written) ⇒ G6 passes;
      * G1/G2 already passed — against a batch that NO LONGER EXISTS.

    A validation computed against a hypothetical batch is not a validation of what got
    written. A benign drop is benign only when nothing depends on it.

    MUT: validate the PRE-drop batch ⇒ D is written, the vault gains an
    ontology-violation, and the assertion that the decisions dir is EMPTY goes RED.
    """
    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"

    # ★ THE SEED IS A **VALID-CLASS** PAGE — and that is the whole point.
    #
    # The ordering bug has TWO manifestations, and only ONE of them G1 can see:
    #   (a) the pre-existing page's class is OUT of range (e.g. a `fact`) ⇒ G1's RANGE
    #       check catches it once it runs on the post-drop batch. Real, but the loud one.
    #   (b) the pre-existing page's class is IN range (another `requirement`, owned by
    #       a different source) ⇒ G1 PASSES. G2 passes (the slug resolves — to someone
    #       else's page). The counts reconcile. And the decision now silently
    #       `implements` A REQUIREMENT IT NEVER MEANT. Nothing anywhere reports it.
    #
    # (b) is the dangerous one, so (b) is the fixture. A test seeded with (a) would
    # pass for the WRONG REASON — G1 would catch it and the 7th-surface gate would
    # never be exercised. (First draft of this test did exactly that.)
    req_slug = _apply_slug_strategy("Latency под 200ms", "transliterate")
    (v / "requirements").mkdir(exist_ok=True)
    (v / "requirements" / f"{req_slug}.md").write_text(
        f"---\ntype: requirement\nslug: {req_slug}\nstatus: approved\n"
        f"title: Чужой requirement\n---\n# Latency\n",
        encoding="utf-8")
    _reindex(v, db)

    p = _prepared(capsys, v, db)
    code, env = _apply(capsys, v, db, [
        _cand(**{"class": "requirement", "title": "Latency под 200ms",
                 "status": "draft",
                 "source_quote": "Заказчик требует latency < 200ms."}),
        _cand(edges={"implements": [req_slug]}),
    ], p["source_hash"])

    assert code == 4
    assert env["error"] == "DROPPED_CANDIDATE_STILL_REFERENCED"
    # ZERO writes BY US. Measured on the filesystem, not read off the envelope —
    # "refused" in JSON is not evidence that nothing was written. The seeded
    # requirement (someone else's page) is subtracted, so the assertion is about what
    # THIS run produced.
    assert list((v / "decisions").glob("*.md")) == []
    assert {pp.name for pp in (v / "requirements").glob("*.md")} == {f"{req_slug}.md"}


def test_a_drop_with_NO_dependents_is_still_benign(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The escalation must not swallow the benign case. A dropped candidate nobody
    references ⇒ exit 0, the survivors ARE written, and the drop is reported."""
    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"

    req_slug = _apply_slug_strategy("Latency под 200ms", "transliterate")
    (v / "facts").mkdir(exist_ok=True)
    (v / "facts" / f"{req_slug}.md").write_text(
        f"---\ntype: fact\nslug: {req_slug}\ntitle: Latency\n---\n# Latency\n",
        encoding="utf-8")
    _reindex(v, db)

    p = _prepared(capsys, v, db)
    code, env = _apply(capsys, v, db, [
        _cand(**{"class": "requirement", "title": "Latency под 200ms",
                 "status": "draft",
                 "source_quote": "Заказчик требует latency < 200ms."}),
        _cand(),                                    # references NOTHING
    ], p["source_hash"])

    assert code == 0, env
    assert len(env["dropped"]) == 1
    assert env["dropped"][0]["reason"] == "existing-page-collision"
    assert len(env["written"]) == 1
    assert len(_written(v)) == 1


def test_re_extraction_UPDATES_OUR_page_but_never_someone_elses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """★ THE OWNERSHIP LINE (R-063-9) — found by the idempotency test, not by review.

    After `--ingest`, the rail's OWN pages are in the index. The very next `--force`
    run then saw their slugs in `existing` and DROPPED them as foreign — which would
    make the rail a ONE-SHOT: able to create knowledge, never to correct it.

    The distinction is `extracted_from`. A page carrying OUR source slug is OURS to
    update. A page that does not is someone else's — hand-authored, or from another
    source — and Class A is the operator's: we drop the candidate rather than
    overwrite their page.

    MUT: drop the `slug not in ours` clause ⇒ the re-extraction drops its own output
    and `written` is empty ⇒ RED.
    """
    import frontmatter

    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"
    p = _prepared(capsys, v, db)

    code, _ = _apply(capsys, v, db, [_cand()], p["source_hash"], extra=["--ingest"])
    assert code == 0
    page = _written(v)[0]
    assert frontmatter.loads(page.read_text(encoding="utf-8")).metadata["status"] == "accepted"

    # the operator corrects the decision — re-extract with a NEW status
    code, env = _apply(capsys, v, db, [_cand(status="superseded")],
                       p["source_hash"], extra=["--force", "--ingest"])
    assert code == 0, env
    assert env["dropped"] == []                       # ← OUR page, not a foreign one
    assert len(env["written"]) == 1
    assert env["written"][0]["action"] == "updated"
    assert frontmatter.loads(
        page.read_text(encoding="utf-8")).metadata["status"] == "superseded"

    # ...and a page we do NOT own is still protected.
    other = _apply_slug_strategy("Клиент уйдёт", "transliterate")
    (v / "risks").mkdir(exist_ok=True)
    (v / "risks" / f"{other}.md").write_text(
        f"---\ntype: risk\nslug: {other}\nstatus: open\ntitle: Ручная страница\n---\n"
        f"# Написано человеком\n", encoding="utf-8")
    _reindex(v, db)

    code, env = _apply(capsys, v, db, [
        _cand(**{"class": "risk", "title": "Клиент уйдёт", "status": "open",
                 "source_quote": "Риск: клиент может уйти к конкуренту."}),
    ], p["source_hash"], extra=["--force"])
    assert code == 0, env
    assert len(env["dropped"]) == 1
    assert env["dropped"][0]["reason"] == "existing-page-collision"
    assert "Написано человеком" in (v / "risks" / f"{other}.md").read_text(encoding="utf-8")


def test_bad_RANGE_refused_via_a_DB_LOOKUP(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """★ THE RANGE CHECK IS THE ONE THAT IS EASY TO FAKE — and this test exists
    because a MUTATION found it missing, not because a review did.

    A range check that only inspects targets INSIDE the batch is a range check that
    DOES NOT EXIST: an edge into the EXISTING graph (`implements: [[some-fact]]`) is
    precisely where a range error hides, because that is where the model is reasoning
    about a page it never read.

    Here the target is a `fact` that already exists in the vault. cybos declares
    `implements.to = [requirement, capability]`, so this must be refused — and the ONLY
    way to know the target's class is to ask the DB.

    MUT (the one that exposed the gap): `target_class = batch_classes.get(target)` —
    i.e. drop the `or db_classes.get(target)` — ⇒ the edge is silently accepted and the
    page ships. RED.
    """
    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"

    (v / "facts").mkdir(exist_ok=True)
    (v / "facts" / "latency-fakt.md").write_text(
        "---\ntype: fact\nslug: latency-fakt\ntitle: Latency факт\n---\n# Факт\n",
        encoding="utf-8")
    _reindex(v, db)

    p = _prepared(capsys, v, db)
    code, env = _apply(capsys, v, db,
                       [_cand(edges={"implements": ["latency-fakt"]})],
                       p["source_hash"])

    assert code == 4
    assert env["error"] == "ONTOLOGY_VIOLATION"
    kinds = {vv["kind"] for vv in env["violations"]}
    assert "range" in kinds, (
        "the target resolves only through the DB — a batch-only range check would "
        "have accepted this edge")
    assert list((v / "decisions").glob("*.md")) == []


# --------------------------------------------------------------------------- #
# ★ G3 — supersede reconciliation, DRIFT-RULE-DRIVEN
# --------------------------------------------------------------------------- #


def _seed_typed(v: Path, db: Path, subdir: str, slug: str, cls: str, status: str) -> None:
    (v / subdir).mkdir(exist_ok=True)
    (v / subdir / f"{slug}.md").write_text(
        f"---\ntype: {cls}\nslug: {slug}\nstatus: {status}\n"
        f"title: Старое решение\n---\n# Старое\n\nТекст.\n", encoding="utf-8")
    _reindex(v, db)


def test_supersedes_RECONCILES_the_target_status_from_the_DRIFT_RULE(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """★ G3, and it is GUARANTEED to be needed, not hypothetical: without the patch,
    cybos's own rule `{class: decision, edge: superseded-by, expect_status: superseded}`
    fires and the vault is no longer `--strict`-clean.

    The value comes from the RULE (`expect_status`), never from a literal — v2
    hardcoded `superseded` and thereby authored a G1 violation on a `requirement`,
    whose enum has no such member.
    """
    import frontmatter

    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"
    _seed_typed(v, db, "decisions", "dec-staroe", "decision", "accepted")

    p = _prepared(capsys, v, db)
    code, env = _apply(capsys, v, db,
                       [_cand(edges={"supersedes": ["dec-staroe"]})],
                       p["source_hash"], extra=["--ingest"])
    assert code == 0, env

    assert len(env["reconciled"]) == 1
    row = env["reconciled"][0]
    assert (row["slug"], row["from"], row["to"]) == ("dec-staroe", "accepted", "superseded")

    patched = frontmatter.loads(
        (v / "decisions" / "dec-staroe.md").read_text(encoding="utf-8"))
    assert patched.metadata["status"] == "superseded"
    # the body is re-attached BYTE-IDENTICALLY — we edited one scalar, not the page
    assert "# Старое\n\nТекст." in patched.content
    assert patched.metadata["title"] == "Старое решение"

    # ★ G5: the PATCHED page is in the manifest. A mutated file whose DB row keeps the
    # old hash is a `hash-mismatch` — a lint issue we would have CREATED.
    assert "decisions/dec-staroe.md" in {e["path"] for e in env["manifest"]["written"]}

    # ...and a BACKUP exists: an escalation that cannot be undone is not safe.
    assert (v / row["backup"]).is_file()


def test_a_forbid_status_shaped_rule_patches_NOTHING(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """★ M-9 — the shape NEITHER v2 NOR v3 caught, and it is reachable from CONFIG.

    `DriftRule` carries exactly one of `expect_status` / `forbid_status`. An operator
    may legitimately declare the FORBID shape for `(decision, superseded-by)`. Then
    `expect_status is None` and THERE IS NO VALUE TO PATCH TO — `forbid_status` says
    what a status must NOT be, which does not determine what it SHOULD be.

    Same branch as "no rule at all": patch nothing, and do not invent a value.
    """
    import frontmatter

    v = _vault(tmp_path / "v", override={
        "drift_rules": [
            {"class": "decision", "edge": "superseded-by",
             "forbid_status": ["proposed", "accepted"]},
        ]})
    db = tmp_path / "x.db"
    _seed_typed(v, db, "decisions", "dec-staroe", "decision", "accepted")

    p = _prepared(capsys, v, db)
    code, env = _apply(capsys, v, db,
                       [_cand(edges={"supersedes": ["dec-staroe"]})],
                       p["source_hash"])
    assert code == 0, env
    assert env["reconciled"] == []
    assert frontmatter.loads(
        (v / "decisions" / "dec-staroe.md").read_text(encoding="utf-8")
    ).metadata["status"] == "accepted"        # untouched


def test_a_PROTECTED_status_REFUSES_the_batch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """★ Superseding a REJECTED decision is a semantic contradiction the OPERATOR must
    resolve — overwriting `rejected` with `superseded` would DESTROY that fact.

    And the protected set is DERIVED FROM CONFIG, not hardcoded (hardcoding `rejected`
    would be v2's disease a third time): a class's `forbid_status` rules enumerate the
    statuses the vault still treats as LIVE (cybos: `invalidated-by` forbids
    [proposed, accepted]). A status OUTSIDE that live set is one the operator already
    resolved.

    A SKIP would be wrong too: it leaves the `lifecycle-drift` finding standing and
    BREAKS the property. Refuse — exit 4, zero writes.
    """
    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"
    _seed_typed(v, db, "decisions", "dec-staroe", "decision", "rejected")

    p = _prepared(capsys, v, db)
    code, env = _apply(capsys, v, db,
                       [_cand(edges={"supersedes": ["dec-staroe"]})],
                       p["source_hash"])
    assert code == 4
    assert env["error"] == "REQUIRES_STATUS_RECONCILIATION"
    assert env["violations"][0]["status"] == "rejected"
    assert list((v / "decisions").glob("*.md")) == [v / "decisions" / "dec-staroe.md"]


def test_no_reconcile_REFUSES_THE_WHOLE_BATCH(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--no-reconcile` is the OPT-OUT, and it refuses the batch WHOLE.

    Writing the pages WITHOUT the patch would silently break G3 — the target keeps a
    status its own vault's drift rule contradicts — and turn the opt-out into a
    footgun that leaves the vault non-strict-clean. An opt-out that quietly damages the
    invariant is worse than no opt-out.
    """
    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"
    _seed_typed(v, db, "decisions", "dec-staroe", "decision", "accepted")

    p = _prepared(capsys, v, db)
    code, env = _apply(capsys, v, db,
                       [_cand(edges={"supersedes": ["dec-staroe"]})],
                       p["source_hash"], extra=["--no-reconcile"])
    assert code == 4
    assert env["error"] == "REQUIRES_STATUS_RECONCILIATION"
    assert list((v / "decisions").glob("*.md")) == [v / "decisions" / "dec-staroe.md"]


def test_an_already_reconciled_target_is_a_NOOP(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Idempotent: a target already at `expect_status` is not re-patched, and no
    gratuitous Class-A edit is made to a page that was never drifting."""
    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"
    _seed_typed(v, db, "decisions", "dec-staroe", "decision", "superseded")

    before = (v / "decisions" / "dec-staroe.md").read_bytes()
    p = _prepared(capsys, v, db)
    code, env = _apply(capsys, v, db,
                       [_cand(edges={"supersedes": ["dec-staroe"]})],
                       p["source_hash"])
    assert code == 0, env
    assert env["reconciled"] == []
    assert (v / "decisions" / "dec-staroe.md").read_bytes() == before   # byte-identical


def test_the_PRECONDITION_is_the_rules_own_firing_condition_not_a_decision_set(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """★ v3's BUG, PINNED — and this test exists because a MUTATION found it missing.

    v3 fixed the reconciliation VALUE (read it from `expect_status`) but left the
    PRECONDITION hardcoded as `{proposed, accepted}` — a DECISION-specific set. cybos
    also declares `{class: workflow, edge: superseded-by, expect_status: superseded}`,
    and `workflow`'s enum is [draft, active, deprecated, superseded]. An `active`
    workflow is not in `{proposed, accepted}`, so v3 would NEVER PATCH IT and the drift
    rule would fire anyway. v2's bug, one field to the left.

    The precondition is the drift rule's OWN firing condition (`_health_rules.py`):
    a scalar text status that differs from `expect_status`. Nothing about decisions in
    it.

    A `decision` may supersede a `workflow` — cybos's `supersedes.to` includes it — so
    this is reachable, not contrived.

    MUT: `if status not in {"proposed", "accepted"}: continue` ⇒ RED. (Run: it was
    GREEN against every other test in this file, which is how the gap was found.)
    """
    import frontmatter

    v = _vault(tmp_path / "v")
    db = tmp_path / "x.db"
    _seed_typed(v, db, "workflows", "wf-staryi", "workflow", "active")

    p = _prepared(capsys, v, db)
    code, env = _apply(capsys, v, db,
                       [_cand(edges={"supersedes": ["wf-staryi"]})],
                       p["source_hash"])
    assert code == 0, env
    assert len(env["reconciled"]) == 1
    row = env["reconciled"][0]
    assert (row["page_class"], row["from"], row["to"]) == (
        "workflow", "active", "superseded")
    assert frontmatter.loads(
        (v / "workflows" / "wf-staryi.md").read_text(encoding="utf-8")
    ).metadata["status"] == "superseded"
