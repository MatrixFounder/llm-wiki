"""Tests for the programmatic `ingest()` + `IngestError` API in the
vendored `scripts/wiki_ingest/commands/ingest.py`.

Bead 004-03 / I-V.3 / R-46. Phase 1 covers the stub contract (import,
NotImplementedError, IngestError attributes). Phase 2 (next iteration
in this bead) extends with happy-path manifest, SOURCE_NEEDS_SUMMARIZATION,
and `execute()` wrapper-around-ingest tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest


# ============================================================== #
# Phase 1 — Stub contract                                        #
# ============================================================== #


def test_ingest_importable() -> None:
    """R-46(a): `ingest` and `IngestError` are public symbols of the
    vendored package."""
    from scripts.wiki_ingest.commands.ingest import IngestError, ingest
    assert callable(ingest)
    assert issubclass(IngestError, Exception)


def test_ingest_raises_on_source_not_found(tmp_path: Path) -> None:
    """Phase 2: missing source → IngestError(code='SOURCE_NOT_FOUND').
    Was Phase 1's `test_ingest_stub_raises_not_implemented`; replaced once
    `ingest()` got a real body. Source-not-found is the cheapest error path
    to test (no vault fixture needed)."""
    from scripts.wiki_ingest.commands.ingest import IngestError, ingest
    with pytest.raises(IngestError) as excinfo:
        ingest(source=tmp_path / "nonexistent.md", vault=tmp_path)
    assert excinfo.value.code == "SOURCE_NOT_FOUND"
    assert excinfo.value.phase is None
    assert "source not found" in str(excinfo.value)


# ============================================================== #
# Phase 2 — Logic tests                                          #
# ============================================================== #


def _make_minimal_vault(tmp_path: Path) -> Path:
    """Build a 1.x course-root vault sufficient for `ingest()` to reach
    the summary-passthrough check (which is what most Phase 2 error-path
    tests need). Pipeline dispatch (`_run_pipeline`) is NOT exercised
    here — that's I-V.7 integration territory."""
    vault = tmp_path / "vault"
    (vault / "_sources").mkdir(parents=True)
    (vault / "_concepts").mkdir()
    (vault / "_entities").mkdir()
    (vault / "WIKI_SCHEMA.md").write_text(
        "---\nschema_version: '1.0'\n---\n# Course Schema\n",
        encoding="utf-8",
    )
    return vault


def test_ingest_raises_on_source_not_summary(tmp_path: Path) -> None:
    """R-46(c): non-summary source → IngestError(code='SOURCE_NEEDS_SUMMARIZATION').
    Proves the `_safety.die(...)` call inside the orchestrator's
    summary-passthrough check was correctly replaced by `raise IngestError`."""
    from scripts.wiki_ingest.commands.ingest import IngestError, ingest

    vault = _make_minimal_vault(tmp_path)
    source = tmp_path / "note.md"
    source.write_text(
        "---\ntype: note\ntitle: Just a note\n---\nBody.\n",
        encoding="utf-8",
    )

    with pytest.raises(IngestError) as excinfo:
        ingest(source=source, vault=vault)
    assert excinfo.value.code == "SOURCE_NEEDS_SUMMARIZATION"
    assert excinfo.value.phase == "needs-pre-summarization"


def test_execute_wraps_ingest_for_cli(tmp_path: Path, monkeypatch) -> None:
    """R-46(e): `execute(args)` calls `ingest()` internally and converts
    `IngestError` back to `_safety.die()`. Mocks `_safety.die` so we can
    verify it's called with the mapped int exit code without actually
    exiting the test runner."""
    import argparse
    from scripts.wiki_ingest import _safety
    from scripts.wiki_ingest.commands.ingest import execute

    captured: dict = {}

    def fake_die(msg: str, code: int = 1) -> None:
        captured["msg"] = msg
        captured["code"] = code
        raise SystemExit(code)

    monkeypatch.setattr(_safety, "die", fake_die)

    args = argparse.Namespace(
        source=str(tmp_path / "nonexistent.md"),  # triggers SOURCE_NOT_FOUND
        vault=str(tmp_path),
        vault_id=None,
        source_hash=None,
        output_format="json",
        quiet=True,
    )

    with pytest.raises(SystemExit) as excinfo:
        execute(args)
    # SOURCE_NOT_FOUND maps to EXIT_GENERIC=1.
    assert excinfo.value.code == _safety.EXIT_GENERIC
    assert captured["code"] == _safety.EXIT_GENERIC
    assert "source not found" in captured["msg"]


def test_ingest_no_sys_exit_in_call_graph() -> None:
    """R-46(c) literal acceptance: grep `ingest()` function body for
    `sys.exit` / `_safety.die` — should find ZERO non-comment matches.

    Uses AST inspection rather than text grep so a code-fenced example
    or a docstring mentioning `sys.exit` does not produce a false
    positive. Walks the body of the `ingest` FunctionDef and asserts no
    `Call` node references `sys.exit` or `_safety.die`.
    """
    import ast
    from pathlib import Path

    src = Path(
        "scripts/wiki_ingest/commands/ingest.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(src)
    ingest_fn = next(
        (node for node in tree.body
         if isinstance(node, ast.FunctionDef) and node.name == "ingest"),
        None,
    )
    assert ingest_fn is not None, "ingest() function must be defined"

    forbidden_calls: list[str] = []
    for node in ast.walk(ingest_fn):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        # `sys.exit(...)`
        if (isinstance(callee, ast.Attribute)
                and isinstance(callee.value, ast.Name)
                and callee.value.id == "sys"
                and callee.attr == "exit"):
            forbidden_calls.append(f"sys.exit at line {node.lineno}")
        # `_safety.die(...)`
        if (isinstance(callee, ast.Attribute)
                and isinstance(callee.value, ast.Name)
                and callee.value.id == "_safety"
                and callee.attr == "die"):
            forbidden_calls.append(f"_safety.die at line {node.lineno}")

    assert forbidden_calls == [], (
        "ingest() body must not call sys.exit() or _safety.die() — "
        f"found: {forbidden_calls}"
    )


def test_ingest_error_attributes() -> None:
    """R-46(d): IngestError carries `code`, `phase`, `written_so_far`,
    `child_exit_code` attributes; `str(err) == message`."""
    from scripts.wiki_ingest.commands.ingest import IngestError
    err = IngestError(
        "test failure",
        code="SOURCE_NEEDS_SUMMARIZATION",
        phase="needs-pre-summarization",
        written_so_far=[{"path": "a.md", "action": "created"}],
        child_exit_code=3,
    )
    assert str(err) == "test failure"
    assert err.code == "SOURCE_NEEDS_SUMMARIZATION"
    assert err.phase == "needs-pre-summarization"
    assert err.written_so_far == [{"path": "a.md", "action": "created"}]
    assert err.child_exit_code == 3


def test_ingest_error_defaults_sensible() -> None:
    """Defaults: phase=None, written_so_far=[], child_exit_code=0.
    Guards against a future refactor accidentally requiring all 5 args."""
    from scripts.wiki_ingest.commands.ingest import IngestError
    err = IngestError("only required args", code="GENERIC")
    assert err.code == "GENERIC"
    assert err.phase is None
    assert err.written_so_far == []
    assert err.child_exit_code == 0
