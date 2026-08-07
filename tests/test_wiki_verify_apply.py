"""TASK 008 / bead 008-06 — `wiki-verify-multi apply` write-side (R-8.3/8.7/8.8).

strict-TDD. The load-bearing properties: the grounding gate
(FINDING_SOURCE_NOT_EXAMINED), the ANSWER_CHANGED TOCTOU, the FAIL→exit-6 signal,
and the **no-mutate-the-answer** invariant (D-008-3 — the `_queries/<slug>.md`
file is byte-identical before/after a FAIL apply). DB indexing is 008-07.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from datetime import datetime
from pathlib import Path

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills import wiki_verify_multi

VAULT_ID = "test-vault"
QSLUG = "how-hermes-routes"


def _write(vault: Path, rel: str, fm: str, body: str) -> None:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{fm}\n---\n\n{body}\n", encoding="utf-8")


def _run(argv: list[str]) -> tuple[int, dict]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = wiki_verify_multi.main(argv)
    return code, json.loads(buf.getvalue())


def _seed(tmp_path: Path) -> tuple[Path, Path]:
    vault, db = tmp_path / "vault", tmp_path / "g.db"
    _write(vault, "_sources/foo.md",
           "type: summary\ntitle: Foo\ndate: 2026-05-29\ntags: [t]",
           "# Foo\n\nHermes routes via the bus.")
    _write(vault, f"_queries/{QSLUG}.md",
           "type: query\ntitle: Q\ndate: 2026-05-29\ntags: [query]\n"
           "question: How does Hermes route?\ncites: ['_vault_/foo']",
           "# Answer\n\nHermes routes via the bus.")
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(vault_id=VAULT_ID, name="v", root_path=vault,
                              schema_version="5.0",
                              registered_at=datetime(2026, 5, 29)))
    reindex_full(repo, VAULT_ID)
    repo.close()
    return vault, db


def _prepare(vault: Path, db: Path) -> dict:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        wiki_verify_multi.main(["prepare", QSLUG, "--vault", VAULT_ID,
                                "--vault-root", str(vault), "--db-path", str(db)])
    return json.loads(buf.getvalue())


def _apply(vault: Path, db: Path, prep: dict, verdict: dict,
           *extra: str) -> tuple[int, dict]:
    (vault / "verdict.json").write_text(json.dumps(verdict), encoding="utf-8")
    return _run(["apply", "--vault", VAULT_ID, "--vault-root", str(vault),
                 "--db-path", str(db),
                 "--verification-slug", prep["verification_slug"],
                 "--query-slug", QSLUG, "--answer-hash", prep["answer_hash"],
                 "--verdict-file", str(vault / "verdict.json"), *extra])


_PASS = {"verdict": "pass", "critics": ["factual"],
         "findings": [{"lens": "factual", "severity": "low",
                       "claim": "ok", "source": "_vault_/foo", "note": "supported"}]}
_FAIL = {"verdict": "fail", "critics": ["factual"],
         "findings": [{"lens": "factual", "severity": "high",
                       "claim": "unsupported claim", "source": "_vault_/foo",
                       "note": "not in the source"}]}


def test_pass_writes_verdict_page(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    code, env = _apply(vault, db, _prepare(vault, db), _PASS)
    assert code == 0
    page = vault / "_verifications" / f"verify-{QSLUG}.md"
    assert page.exists()
    text = page.read_text(encoding="utf-8")
    assert "type: verification" in text and "verdict: pass" in text
    assert f"verifies: _vault_/{QSLUG}" in text


def test_fail_returns_exit_6(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    code, _env = _apply(vault, db, _prepare(vault, db), _FAIL)
    assert code == 6  # VERDICT_FAIL (page still filed)
    assert (vault / "_verifications" / f"verify-{QSLUG}.md").exists()
    assert "verdict: fail" in (vault / "_verifications" / f"verify-{QSLUG}.md").read_text()


def test_fail_does_not_mutate_the_answer(tmp_path: Path) -> None:
    """D-008-3 (the load-bearing invariant): the Class-A answer is byte-identical
    before and after a FAIL apply."""
    vault, db = _seed(tmp_path)
    answer_path = vault / "_queries" / f"{QSLUG}.md"
    before = hashlib.sha256(answer_path.read_bytes()).hexdigest()
    _apply(vault, db, _prepare(vault, db), _FAIL)
    after = hashlib.sha256(answer_path.read_bytes()).hexdigest()
    assert before == after, "FAIL apply mutated the Class-A answer (D-008-3 violation)"


def test_fail_on_none_exits_zero(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    code, _env = _apply(vault, db, _prepare(vault, db), _FAIL, "--fail-on", "none")
    assert code == 0
    assert "verdict: pass" in (vault / "_verifications" / f"verify-{QSLUG}.md").read_text()


def test_answer_changed_toctou(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    prep = _prepare(vault, db)
    # edit the answer body after prepare → recomputed answer_hash differs
    (vault / "_queries" / f"{QSLUG}.md").write_text(
        "---\ntype: query\ntitle: Q\ndate: 2026-05-29\ntags: [query]\n"
        "question: How does Hermes route?\ncites: ['_vault_/foo']\n---\n\n# Answer\n\nEDITED.\n",
        encoding="utf-8")
    code, env = _apply(vault, db, prep, _PASS)
    assert code == 2 and env["error"] == "ANSWER_CHANGED"
    assert not (vault / "_verifications" / f"verify-{QSLUG}.md").exists()


def test_finding_source_not_examined(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    prep = _prepare(vault, db)
    bad = {"verdict": "pass", "critics": ["factual"],
           "findings": [{"lens": "factual", "severity": "low", "claim": "x",
                         "source": "_vault_/not-cited", "note": "n"}]}
    code, env = _apply(vault, db, prep, bad)
    assert code == 4 and env["error"] == "FINDING_SOURCE_NOT_EXAMINED"
    assert not (vault / "_verifications" / f"verify-{QSLUG}.md").exists()


def test_python_rule_overrides_optimistic_llm_verdict(tmp_path: Path) -> None:
    """Safety property: the LLM self-reports verdict:'pass' but emits a high
    `factual` finding → the Python rule derives FAIL (exit 6) + writes
    `verdict: fail`. A buggy/optimistic LLM cannot bypass the grounding rule."""
    vault, db = _seed(tmp_path)
    optimistic = {"verdict": "pass", "critics": ["factual"],
                  "findings": [{"lens": "factual", "severity": "high",
                                "claim": "overclaim", "source": "_vault_/foo",
                                "note": "not supported"}]}
    code, _env = _apply(vault, db, _prepare(vault, db), optimistic)
    assert code == 6
    assert "verdict: fail" in (vault / "_verifications" / f"verify-{QSLUG}.md").read_text()


def test_severity_case_insensitive_fail(tmp_path: Path) -> None:
    """vdd-multi L-1: a critic that emits `severity:"High"` (title-case — common
    LLM drift) on a factual finding STILL derives FAIL (exit 6). A case-sensitive
    rule would have silently passed it, defeating the Python-overrides-LLM rule."""
    vault, db = _seed(tmp_path)
    mixed = {"verdict": "pass", "critics": ["factual"],
             "findings": [{"lens": "Factual", "severity": "High",
                           "claim": "overclaim", "source": "_vault_/foo", "note": "n"}]}
    code, _env = _apply(vault, db, _prepare(vault, db), mixed)
    assert code == 6
    assert "verdict: fail" in (vault / "_verifications" / f"verify-{QSLUG}.md").read_text()


def test_invalid_severity_rejected(tmp_path: Path) -> None:
    """vdd-multi L-1: an out-of-vocab severity is rejected (not silently
    downgraded to non-failing)."""
    vault, db = _seed(tmp_path)
    bad = {"verdict": "fail", "critics": ["factual"],
           "findings": [{"lens": "factual", "severity": "catastrophic",
                         "claim": "x", "source": "_vault_/foo", "note": "n"}]}
    code, env = _apply(vault, db, _prepare(vault, db), bad)
    assert code == 4 and env["error"] == "INVALID_VERDICT"


def test_invalid_lens_rejected(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    bad = {"verdict": "pass", "critics": [],
           "findings": [{"lens": "vibes", "severity": "low", "claim": "x", "note": "n"}]}
    code, env = _apply(vault, db, _prepare(vault, db), bad)
    assert code == 4 and env["error"] == "INVALID_VERDICT"


def test_invalid_verdict_enum(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    code, env = _apply(vault, db, _prepare(vault, db),
                       {"verdict": "maybe", "critics": [], "findings": []})
    assert code == 4 and env["error"] == "INVALID_VERDICT"


def test_verdict_parse_error(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    prep = _prepare(vault, db)
    (vault / "verdict.json").write_text("{not json", encoding="utf-8")
    code, env = _run(["apply", "--vault", VAULT_ID, "--vault-root", str(vault),
                      "--db-path", str(db), "--verification-slug", prep["verification_slug"],
                      "--query-slug", QSLUG, "--answer-hash", prep["answer_hash"],
                      "--verdict-file", str(vault / "verdict.json")])
    assert code == 4 and env["error"] == "VERDICT_PARSE_ERROR"


def test_idempotent_skip_and_force(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    prep = _prepare(vault, db)
    _c1, e1 = _apply(vault, db, prep, _PASS)
    assert e1["action"] == "filed"
    _c2, e2 = _apply(vault, db, prep, _PASS)
    assert e2["action"] == "unchanged"  # content-hash skip
    _c3, e3 = _apply(vault, db, prep, _PASS, "--force")
    assert e3["action"] == "filed"


def test_mkdir_on_migrated_vault_no_predir(tmp_path: Path) -> None:
    """CMP-4: a vault with NO pre-existing _verifications/ dir — apply must create
    it (mkdir parents), not crash with FileNotFoundError."""
    vault, db = _seed(tmp_path)
    assert not (vault / "_verifications").exists()  # reindex doesn't scaffold it
    code, _env = _apply(vault, db, _prepare(vault, db), _PASS)
    assert code == 0
    assert (vault / "_verifications" / f"verify-{QSLUG}.md").exists()


# ---------------------------------------------------------------------------
# DF-072-1 — the two grounding FLOORS `prepare` carries must also hold in
# `apply`. `--verify-hash` is optional (back-compat), so `apply` is reachable
# WITHOUT the `prepare` that would have refused: without these floors a query
# page citing nothing (or citing only unresolvable slugs) yielded a filed,
# self-indexed `verdict: pass` at exit 0 — a PASS certified over ZERO examined
# sources. Exit 2, matching `prepare` and the sibling context-class refusals
# (ANSWER_CHANGED / VERIFY_CONTEXT_CHANGED) in this same block: `cites:` comes
# from the query page on disk, not from the supplied verdict payload, so
# re-synthesising the verdict (the exit-4 class) cannot fix it — STOP is the
# only correct action.
# ---------------------------------------------------------------------------

def _seed_cites(tmp_path: Path, cites: str) -> tuple[Path, Path]:
    """`_seed` with an operator-chosen `cites:` — `prepare` refuses these, so the
    answer_hash is computed here directly (exactly the un-prepared invocation
    that DF-072-1 reported)."""
    vault, db = tmp_path / "vault", tmp_path / "g.db"
    _write(vault, "_sources/foo.md",
           "type: summary\ntitle: Foo\ndate: 2026-05-29\ntags: [t]",
           "# Foo\n\nHermes routes via the bus.")
    _write(vault, f"_queries/{QSLUG}.md",
           "type: query\ntitle: Q\ndate: 2026-05-29\ntags: [query]\n"
           f"question: How does Hermes route?\ncites: {cites}",
           "# Answer\n\nHermes routes via the bus.")
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(vault_id=VAULT_ID, name="v", root_path=vault,
                              schema_version="5.0",
                              registered_at=datetime(2026, 5, 29)))
    reindex_full(repo, VAULT_ID)
    repo.close()
    return vault, db


def _self_answer_hash(vault: Path) -> str:
    """The answer_hash `prepare` would have emitted, computed without it."""
    import frontmatter  # local: only these helpers need the body split
    page = wiki_verify_multi._read_page_text(  # noqa: SLF001 — the same read apply does
        vault, str(vault / "_queries" / f"{QSLUG}.md"))
    return wiki_verify_multi._answer_hash(frontmatter.loads(page).content.strip())


def _apply_unprepared(vault: Path, db: Path, verdict: dict,
                      *extra: str) -> tuple[int, dict]:
    """Invoke `apply` with a self-computed answer_hash — no `prepare` run."""
    (vault / "verdict.json").write_text(json.dumps(verdict), encoding="utf-8")
    return _run(["apply", "--vault", VAULT_ID, "--vault-root", str(vault),
                 "--db-path", str(db), "--verification-slug", f"verify-{QSLUG}",
                 "--query-slug", QSLUG,
                 "--answer-hash", _self_answer_hash(vault),
                 "--verdict-file", str(vault / "verdict.json"), *extra])


_VACUOUS_PASS = {"verdict": "pass", "critics": ["factual"], "findings": []}


def test_apply_refuses_empty_cites(tmp_path: Path) -> None:
    """DF-072-1 scenario 1: `cites: []` → NO_SOURCES, nothing filed, nothing indexed."""
    vault, db = _seed_cites(tmp_path, "[]")
    code, env = _apply_unprepared(vault, db, _VACUOUS_PASS)
    assert code == 2, "a PASS was filed over zero cited sources"
    assert env["error"] == "NO_SOURCES" and env["field"] == "cites"
    # Pin FLOOR #1 specifically. Floor #2 (empty examined set) SUBSUMES this case
    # — `_gather_examined([])` is empty — so `error`/exit alone cannot tell the
    # two apart and would stay green with floor #1 deleted. The operator-facing
    # `reason` is the only observable that distinguishes "you cited nothing" from
    # "your cites are all broken", which are different fixes.
    assert "cites nothing" in env["reason"]
    assert not (vault / "_verifications" / f"verify-{QSLUG}.md").exists()
    repo = SQLiteRepository(db)
    assert repo.get_page(VAULT_ID, f"verify-{QSLUG}", "_vault_") is None
    repo.close()


def test_apply_refuses_when_every_cite_is_unresolvable(tmp_path: Path) -> None:
    """DF-072-1 scenario 3: `cites:` non-empty but NO entry resolves → the examined
    set is empty → NO_SOURCES. The control that this is not vacuous: the same seed
    with a resolvable cite reaches exit 0 (`test_apply_floors_do_not_fire_on_a_grounded_verdict`)."""
    vault, db = _seed_cites(tmp_path, '["_vault_/ghost1", "_vault_/ghost2"]')
    code, env = _apply_unprepared(vault, db, _VACUOUS_PASS)
    assert code == 2, "a PASS was filed over an empty examined set"
    assert env["error"] == "NO_SOURCES" and env["field"] == "cites"
    assert "none are indexed/readable" in env["reason"]  # floor #2, not floor #1
    assert "ghost" not in json.dumps(env)  # CWE-209: never echo the offending cites
    assert not (vault / "_verifications" / f"verify-{QSLUG}.md").exists()


def test_apply_refuses_empty_cites_even_with_a_self_computed_verify_hash(
        tmp_path: Path) -> None:
    """DF-072-1 scenario 2: passing a CORRECTLY self-computed `--verify-hash` (over
    the empty examined set, so VERIFY_CONTEXT_CHANGED genuinely does not fire) must
    not buy a pass — the floor, not the symmetry gate, is what refuses here."""
    vault, db = _seed_cites(tmp_path, "[]")
    v_hash = wiki_verify_multi._verify_hash(
        _self_answer_hash(vault), [], audience=None)
    code, env = _apply_unprepared(vault, db, _VACUOUS_PASS, "--verify-hash", v_hash)
    assert code == 2 and env["error"] == "NO_SOURCES"
    assert not (vault / "_verifications" / f"verify-{QSLUG}.md").exists()


def test_apply_floors_do_not_fire_on_a_grounded_verdict(tmp_path: Path) -> None:
    """Non-vacuity control: the SAME un-prepared invocation with one resolvable
    cite still files at exit 0 — the floors refuse zero sources, not all sources."""
    vault, db = _seed_cites(tmp_path, "['_vault_/foo']")
    code, env = _apply_unprepared(vault, db, _VACUOUS_PASS)
    assert code == 0 and env["action"] == "filed"
    assert (vault / "_verifications" / f"verify-{QSLUG}.md").exists()
