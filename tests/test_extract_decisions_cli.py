"""TASK 063-04 — the `wiki-extract-decisions` CLI surface (STUB-FIRST).

The interface, the exit-code contract and the Decision-17 gate land HERE, before
any logic exists that could violate them. These E2E tests pass ON THE STUBS; the
later beads REWRITE their assertions to real values rather than deleting them.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.wiki_skills import wiki_extract_decisions as wed
from scripts.wiki_skills.wiki_extract_decisions import main

_PKG_DIR = Path(wed.__file__).resolve().parent


def _run(capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, dict[str, object]]:
    code = main(argv)
    payload = json.loads(capsys.readouterr().out.strip())
    assert isinstance(payload, dict)
    return code, payload


def test_help_lists_both_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "prepare" in out and "apply" in out


def test_no_subcommand_is_a_usage_error() -> None:
    """There is no single-command shape. The reasoning step is not ours to run
    (Decision-17), so an invocation that implies we would run it is a usage error."""
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2  # argparse's own usage exit


def test_prepare_on_a_bare_vault_refuses_rather_than_stubbing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """STUB-FIRST STEP 4: this test was `test_prepare_stub_envelope` in 063-04 and is
    REWRITTEN to assert real behaviour, not deleted — the E2E shape survives, its
    expectations become true.

    A bare `tmp_path` has no `WIKI_SCHEMA.md`, so `resolve_layout_config` defaults to
    **karpathy** (its documented back-compat fallback), which maps ZERO typed classes.
    The real rail therefore REFUSES with exit 2 where the stub happily emitted an
    envelope — and that difference IS the bead: the preflight fires before any
    reasoning is requested, on the most default vault there is.

    The envelope is checked for the operator-facing essentials: which layout, and
    what to do about it.

    (The source file is created because `prepare` checks the SOURCE before the
    layout: the path you passed is the most immediate thing that can be wrong, and a
    typo deserves SOURCE_NOT_FOUND rather than a lecture about `type_mapping`.)
    """
    src = tmp_path / "meetings" / "m1.md"
    src.parent.mkdir(parents=True)
    src.write_text("# Protocol\n", encoding="utf-8")

    code, env = _run(capsys, [
        "prepare", "--vault", "v", "--vault-root", str(tmp_path),
        "--source-page", "meetings/m1.md",
    ])
    assert code == 2
    assert env["error"] == "LAYOUT_CANNOT_INDEX_CLASSES"
    assert env["layout"] == "karpathy"
    assert "type_mapping" in env["message"]
    assert "cybos" in env["message"]        # names a layout that WOULD work


def test_apply_on_a_bare_vault_refuses_at_the_SAME_preflight_as_prepare(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """STUB-FIRST STEP 4: was `test_apply_stub_envelope`; REWRITTEN, not deleted.

    ★ The point of the rewrite is the shared preflight. `apply` refuses a bare vault
    with the EXACT code and message `prepare` does, because both call
    `_resolve_context` — one G4 gate, two callers. Two copies of that gate would let
    `apply` write into a folder `prepare` had refused, which is the whole failure this
    task exists to prevent.

    It refuses BEFORE the `--source-hash` mismatch is even considered: a vault that
    cannot hold typed pages is a more fundamental fact than a stale hash.
    """
    src = tmp_path / "meetings" / "m1.md"
    src.parent.mkdir(parents=True)
    src.write_text("# Protocol\n", encoding="utf-8")
    cands = tmp_path / "c.json"
    cands.write_text("[]", encoding="utf-8")

    code, env = _run(capsys, [
        "apply", "--vault", "v", "--vault-root", str(tmp_path),
        "--source-page", "meetings/m1.md", "--source-hash", "deadbeef",
        "--candidates-file", str(cands),
    ])
    assert code == 2
    assert env["error"] == "LAYOUT_CANNOT_INDEX_CLASSES"   # ← identical to prepare's
    assert env["layout"] == "karpathy"


def test_apply_requires_a_candidates_source(tmp_path: Path) -> None:
    """`--candidates-file` XOR `--candidates-stdin`, required. `apply` with no
    candidates at all is a usage error, not an empty run — the empty-SET case is
    `[]`, which is a legitimate SUCCESS, and the two must not be confusable."""
    with pytest.raises(SystemExit):
        main(["apply", "--vault", "v", "--vault-root", str(tmp_path),
              "--source-page", "m.md", "--source-hash", "h"])


def test_candidate_count_min_is_ZERO_not_one() -> None:
    """★ THE ANTI-FABRICATION MECHANISM (R-063-7), pinned as a CONSTANT.

    The precedent — `wiki_extract_concepts._validation._CANDIDATE_COUNT_MIN` — is
    **1**. Cloning it would make "this note contains no decisions" an exit-4
    FAILURE, and the model's cheapest path to a green run would then be to INVENT
    one. An empty candidate set must be SUCCESS.

    This test exists because the pull toward "parity with the precedent" is real:
    a later reader sees 0 next to the precedent's 1 and reads it as an oversight.
    It is the safety property. MUT: set it to 1 ⇒ RED.
    """
    assert wed.CANDIDATE_COUNT_MIN == 0
    other = (
        Path(wed.__file__).resolve().parents[1]
        / "wiki_extract_concepts" / "_validation.py"
    ).read_text(encoding="utf-8")
    assert "_CANDIDATE_COUNT_MIN = 1" in other, (
        "the precedent changed — re-read WHY this skill deliberately differs "
        "before syncing it")


def test_no_anthropic_import_in_package() -> None:
    """★ DECISION-17, over the WHOLE PACKAGE, globbed at RUNTIME.

    Two things this gate gets right that its first draft did not:

    1. **BOTH import forms.** The house precedent
       (`tests/test_wiki_sync.py::test_scan_module_has_no_anthropic_import`)
       asserts `"import anthropic"` AND `"from anthropic"`. A gate checking only
       the first lets `from anthropic import Anthropic` walk straight through —
       *a gate narrower than the precedent it clones is a gate with a documented
       hole.*
    2. **The population is GLOBBED, not typed.** A hand-written file list would
       cover exactly the files that existed the day it was written, and beads
       063-05…063-14 add more. A denominator maintained by hand is this project's
       signature failure mode; `rglob` cannot forget.
    """
    files = sorted(_PKG_DIR.rglob("*.py"))
    assert len(files) >= 5, f"the package glob found only {files} — is the path right?"

    offenders = [
        f.name for f in files
        if re.search(r"^\s*(import anthropic|from anthropic)",
                     f.read_text(encoding="utf-8"), re.MULTILINE)
    ]
    assert offenders == [], (
        f"Decision-17: the deterministic rail must carry NO LLM-client import. "
        f"Offenders: {offenders}")


def test_exit_code_table_is_documented() -> None:
    """Every error string the rail can emit appears in the module docstring's
    exit-code table. Cheap, and it stops the contract rotting: a code that is
    raised but undocumented is a code the orchestrator cannot branch on."""
    doc = wed.__doc__ or ""
    for code in (
        # exit 2 — input validation
        "SOURCE_NOT_FOUND", "INVALID_SOURCE_PATH", "SOURCE_TOO_LARGE",
        "SOURCE_CHANGED_DURING_EXTRACTION", "INVALID_SOURCE_HASH",
        "INVALID_CANDIDATES_PATH", "LAYOUT_CANNOT_INDEX_CLASSES",
        "TYPED_DIR_NOT_COVERED_BY_LAYOUT",
        # exit 4 — contract violation, ZERO writes
        "EXTRACTION_PARSE_ERROR", "CANDIDATES_TOO_LARGE", "FIELD_TOO_LONG",
        "UNKNOWN_FIELD", "FIELD_QUOTE_NOT_IN_BODY", "ONTOLOGY_VIOLATION",
        "UNRESOLVED_REF", "IN_BATCH_SLUG_COLLISION",
        "DROPPED_CANDIDATE_STILL_REFERENCED", "REQUIRES_STATUS_RECONCILIATION",
        # exit 5 / 6
        "PARTIAL_INDEX_FAILURE", "DB_WRITE_FAILED", "IDEMPOTENCY_UPDATE_FAILED",
        "MANIFEST_INVALID",
        # the two success actions that are NOT failures
        "no_candidates", "unchanged",
    ):
        assert code in doc, f"{code} is raiseable but absent from the exit-code table"
