"""TASK 072 bead 072-03d — exit-code doc-truth is a MECHANISM, not a doc-review pass.

WHY THIS FILE EXISTS. Bead 072-03c ran a hand doc-currency pass over `wiki-query`'s exit-code
roster and declared the class closed. Three adversarial roast rounds then found *the same two
falsehoods on one more file each time*, and the loop bound (3) was exhausted and escalated. The
mechanism of the non-convergence is the finding:

    Each round proved eradication by grepping for the literal string the PREVIOUS round had
    found. That grep returns 0 *precisely because* the auditor already fixed every place that
    string occurs. `skills/wiki-extract-concepts/SKILL.md` carried the identical falsehood
    worded `| 1 | argparse / usage error | - |` and was invisible to it.

    >>> A census predicate derived from the instances you already found is not a census. <<<

So every roster here is DISCOVERED AT RUNTIME — `bin/` is walked, `skills/*/SKILL.md` is parsed,
the modules are AST-scanned, and the CLIs are actually EXECUTED. A CLI added tomorrow is in scope
without editing this file. Excluding one, by contrast, requires an explicit entry with a reason
below: automatic inclusion, explicit exclusion.

WHAT THIS FILE CAN AND CANNOT DO — stated, because an overclaiming gate is the failure being fixed:

  CAN  · the (exit code, error token) pairs a table documents vs. the ones the module can emit,
         in BOTH directions (a phantom is as wrong as a blind spot), including codes the CLI
         INHERITS rather than raises (`build_repo_config` -> 6/INVALID_INDEX_DB was missed by two
         separate roast rounds);
       · what a CLI ACTUALLY exits on an unrecognised flag vs. what its usage row claims.

  CANNOT · free-prose semantics ("the verdict page IS still filed", "never echoes the offending
         value", "one JSON envelope per invocation"). Those are English, not data. The 2026-08-07
         census measured several of them FALSE across the repo; they are tracked as issues and
         reviewed by humans, NOT asserted here. Do not add a regex that pretends otherwise.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

from scripts.wiki_skills._common import _REPO_ROOT

BIN = _REPO_ROOT / "bin"
SKILLS = _REPO_ROOT / "skills"

# --------------------------------------------------------------------------------------------
# Stated exclusions. Every entry is a DECISION with a reason. An unlisted CLI is always in scope.
# --------------------------------------------------------------------------------------------

#: `bin/` entries that are not CLIs under this contract at all.
_NOT_A_CLI = {
    "install-globally.sh": "installer shell script, not a wiki-* CLI",
    "install-project-symlinks.sh": "installer shell script",
    "link-command.sh": "installer shell script",
    "link-skill.sh": "installer shell script",
    "link-workflow.sh": "installer shell script",
}

#: CLIs whose exit contract is real but lives outside `skills/<cli-name>/SKILL.md`, so the
#: name-based table lookup cannot reach it. Each is a genuine doc gap, tracked, not asserted here.
_NO_NAME_MATCHED_SKILL = {
    "wiki-extract-decisions": (
        "doc surface is skills/decision-extraction/ + commands/ + workflows/ under a DIFFERENT "
        "name; the only wiki-* CLI with no skills/<name>/ dir"
    ),
    "obsidian-active-note": "documented inside skills/obsidian-cli/SKILL.md (prose, no table)",
    "obsidian-context": "documented inside skills/obsidian-cli/SKILL.md (prose, no table)",
    "obsidian-selection": "documented inside skills/obsidian-cli/SKILL.md (prose, no table)",
}

#: Tables that do NOT claim to enumerate every reachable code. A table may be incomplete — what it
#: may not be is silently incomplete. Anything not listed here is held to completeness.
#: (`wiki-query`'s roster deliberately absent: it DECLARES normativity, so it is held to it.)
_DOES_NOT_CLAIM_COMPLETENESS = {
    "wiki-alias", "wiki-append-log", "wiki-confirm", "wiki-extract-concepts", "wiki-import",
    "wiki-index-render", "wiki-index-upsert", "wiki-init", "wiki-merge", "wiki-search",
}

#: CLIs whose exit table documents no argparse/usage row at all. This is a real doc GAP, not a
#: falsehood, so it is recorded rather than asserted away — and pinned, so deleting a usage row
#: from a table that HAS one is caught. Closing the gap is follow-on work, not this bead's scope.
_NO_USAGE_ROW_DOCUMENTED = {
    "wiki-alias", "wiki-append-log", "wiki-confirm", "wiki-import", "wiki-index-render",
    "wiki-index-upsert", "wiki-init", "wiki-search",
}

#: Error tokens a CLI inherits from a shared emitter rather than raising itself. Keyed by the
#: helper's name as it appears in the module's imports; value = the pairs it can produce.
#: DERIVED, not hand-listed per CLI: membership is decided by scanning each module for the call.
_INHERITED = {
    "build_repo_config": {(6, "INVALID_INDEX_DB")},
    "emit_prepare_with_integrity": {(2, "SKILL_INTEGRITY_DRIFT")},
}

_BOGUS_FLAG = "--definitely-not-a-real-flag-0723"

#: Cells in a table's *cause* column that mark the row as the argparse/usage row.
_USAGE_ROW = re.compile(r"argparse|usage|unrecognized|unrecognised|missing (required )?flag", re.I)

_TOKEN = re.compile(r"\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)\b")


# --------------------------------------------------------------------------------------------
# Discovery — every roster below is computed, never transcribed.
# --------------------------------------------------------------------------------------------

def _discover_clis() -> dict[str, Path]:
    """Every executable in bin/ that is a CLI under this contract -> its wrapper path.

    A symlinked launcher (`wiki-import-article` -> `wiki-import`) is the SAME program with the
    same doc surface, so it resolves to its target's name rather than becoming a phantom CLI with
    no SKILL.md. Detected via `is_symlink`, not by name.
    """
    out = {}
    for p in sorted(BIN.iterdir()):
        if not p.is_file() or p.name in _NOT_A_CLI:
            continue
        if p.is_symlink():
            target = (p.parent / p.readlink()).resolve()
            if target.parent == BIN:
                continue  # same program, already enumerated under its real name
        out[p.name] = p
    return out


def _module_for(wrapper: Path) -> str | None:
    """Resolve a bin/ wrapper to the dotted python module it execs (read it; never guess)."""
    m = re.search(r"python3?\s+-m\s+([\w.]+)", wrapper.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def _module_paths(dotted: str) -> list[Path]:
    """Every .py file that makes up a module or package."""
    base = _REPO_ROOT / Path(*dotted.split("."))
    if base.with_suffix(".py").is_file():
        return [base.with_suffix(".py")]
    if base.is_dir():
        return sorted(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)
    return []


def _exit_table_rows(skill_md: Path) -> list[tuple[int, str, str]]:
    """(code, error-cell, rest-of-row) for every markdown table row whose first cell is an int.

    Deliberately NOT anchored to `^|` — the census found a real exit table indented three spaces
    inside a task body, which an anchored pattern silently skips.
    """
    rows = []
    for line in skill_md.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 2:
            continue
        head = cells[0].strip("`* ")
        if not head.isdigit():
            continue
        rows.append((int(head), cells[1], " | ".join(cells[2:])))
    return rows


def _documented_pairs(skill_md: Path) -> set[tuple[int, str]]:
    """(code, TOKEN) pairs a table asserts. A cell may carry several tokens separated by `/`."""
    return {
        (code, tok)
        for code, err, _rest in _exit_table_rows(skill_md)
        for tok in _TOKEN.findall(err)
    }


def _reachable_pairs(dotted: str) -> set[tuple[int, str]]:
    """(code, TOKEN) pairs the module can actually emit, by AST.

    Handles every shape found in the live tree. Each bullet after the first was added because the
    naive version produced a FALSE POSITIVE against real code — a scanner that reports a phantom
    where none exists is as useless as one that misses a real defect, and it trains the reader to
    add exclusions instead of fixing docs:
      * `emit({"error": "LITERAL", ...}, N)`                    — the easy case
      * `emit({"error": err, ...}, N)` with `err` a ternary over two string literals
        (wiki_query, wiki_verify_multi and wiki_search all use it for AUDIENCE/POLICY)
      * `emit({"warning": "LITERAL", ...}, N)` — wiki-init's exit 7 is a warning envelope, and
        its table's column is "Envelope keys", so it legitimately documents a non-error token
      * `raise ImportArticleError("TOKEN", ..., exit_code=EXIT_CONST)` — wiki-import raises a
        domain exception whose `.envelope()` becomes the payload; it has no `emit(...)` call at
        all, so the naive scanner declared its whole table phantom
      * codes inherited from a shared emitter the module calls (see `_INHERITED`)
    """
    pairs: set[tuple[int, str]] = set()
    ternaries: dict[str, set[str]] = {}
    int_consts: dict[str, int] = {}
    called: set[str] = set()
    paths = _module_paths(dotted)
    trees = [(p, ast.parse(p.read_text(encoding="utf-8"), filename=str(p))) for p in paths]

    # Pass 1 — module-level int constants (EXIT_FETCH_FAILED = 10) and string/ternary bindings.
    for _path, tree in trees:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            tgt = node.targets[0]
            if not isinstance(tgt, ast.Name):
                continue
            val = node.value
            if isinstance(val, ast.Constant) and isinstance(val.value, int) \
                    and not isinstance(val.value, bool):
                int_consts[tgt.id] = val.value
                continue
            lits: set[str] = set()
            if isinstance(val, ast.IfExp):
                for branch in (val.body, val.orelse):
                    if isinstance(branch, ast.Constant) and isinstance(branch.value, str):
                        lits.add(branch.value)
            elif isinstance(val, ast.Constant) and isinstance(val.value, str):
                lits.add(val.value)
            if lits:
                ternaries.setdefault(tgt.id, set()).update(lits)

    def _int_of(node: ast.AST | None) -> int | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, int) \
                and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.Name):
            return int_consts.get(node.id)
        return None

    # Pass 2 — emit(...) calls, domain-error raises, and the shared emitters this module invokes.
    for _path, tree in trees:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fname = (
                node.func.id if isinstance(node.func, ast.Name)
                else node.func.attr if isinstance(node.func, ast.Attribute)
                else None
            )
            if fname is None:
                continue
            called.add(fname)

            if fname.endswith("Error") and node.args:
                # A domain exception carrying (code, message, *, exit_code=CONST).
                tok = node.args[0]
                if not (isinstance(tok, ast.Constant) and isinstance(tok.value, str)):
                    continue
                code = next(
                    (_int_of(kw.value) for kw in node.keywords if kw.arg == "exit_code"), None)
                if code is None:
                    code = int_consts.get("EXIT_USAGE")  # the class default
                if code is not None:
                    pairs.add((code, tok.value))
                continue

            if not fname.endswith("emit"):
                continue
            code = _int_of(node.args[1]) if len(node.args) >= 2 else None
            for kw in node.keywords:
                if kw.arg in ("exit_code", "code"):
                    code = _int_of(kw.value) if _int_of(kw.value) is not None else code
            if code is None:
                continue
            payload = node.args[0] if node.args else None
            if not isinstance(payload, ast.Dict):
                continue
            for k, v in zip(payload.keys, payload.values):
                if not (isinstance(k, ast.Constant) and k.value in ("error", "warning")):
                    continue
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    pairs.add((code, v.value))
                elif isinstance(v, ast.Name):
                    for lit in ternaries.get(v.id, ()):
                        pairs.add((code, lit))

    for helper, inherited in _INHERITED.items():
        if helper in called:
            pairs |= inherited
    return pairs


CLIS = _discover_clis()
#: name -> (wrapper, dotted module, SKILL.md-or-None, exit-table-rows)
RESOLVED = {
    name: (
        wrapper,
        _module_for(wrapper),
        (SKILLS / name / "SKILL.md") if (SKILLS / name / "SKILL.md").is_file() else None,
    )
    for name, wrapper in CLIS.items()
}
#: Partition A — a CLI whose own SKILL.md carries an exit table. Computed, not listed.
WITH_TABLE = sorted(
    n for n, (_w, _m, s) in RESOLVED.items() if s is not None and _exit_table_rows(s)
)


# --------------------------------------------------------------------------------------------
# Controls — this gate must be able to FAIL. A check that examines nothing is not a check.
# --------------------------------------------------------------------------------------------

def test_the_discovered_population_is_not_empty() -> None:
    """Non-vacuity. If discovery silently returns nothing, every assertion below passes trivially."""
    assert len(CLIS) >= 15, f"bin/ walk found only {len(CLIS)} CLIs — discovery is broken"
    assert len(WITH_TABLE) >= 10, f"only {len(WITH_TABLE)} CLIs have an exit table — parser broken"
    for name in WITH_TABLE:
        rows = _exit_table_rows(RESOLVED[name][2])
        assert rows, f"{name}: classified as having a table, but the parser returns no rows"


def test_every_cli_lands_in_exactly_one_declared_partition() -> None:
    """A new CLI cannot join a silent third bucket — it must be classified or refused."""
    unclassified = []
    for name, (_w, _m, skill) in RESOLVED.items():
        if name in WITH_TABLE:
            continue
        if name in _NO_NAME_MATCHED_SKILL:
            continue
        if skill is not None:  # partition B: has a SKILL.md, no exit table
            continue
        unclassified.append(name)
    assert not unclassified, (
        f"{unclassified} have neither an exit table, a SKILL.md, nor a stated exclusion. "
        "Add an exit table, or add an entry to _NO_NAME_MATCHED_SKILL WITH A REASON."
    )


def test_the_table_parser_can_actually_fire() -> None:
    """Mutation control: feed the parser a table that IS wrong and prove the checkers see it."""
    bad = _REPO_ROOT / "tests" / "_mutation_probe_exit_table.md"
    bad.write_text(
        "| Code | `error` | Cause |\n|---|---|---|\n"
        "| 1 | — | argparse / usage error |\n"
        "| 4 | `TOTALLY_MADE_UP_TOKEN` | phantom |\n",
        encoding="utf-8",
    )
    try:
        rows = _exit_table_rows(bad)
        assert [r[0] for r in rows] == [1, 4], f"parser lost rows: {rows}"
        assert _USAGE_ROW.search(rows[0][2]), "usage-row detector missed an argparse row"
        assert (4, "TOTALLY_MADE_UP_TOKEN") in _documented_pairs(bad)
    finally:
        bad.unlink()


def test_the_ast_scanner_can_actually_fire() -> None:
    """Mutation control for the reachability side, including the ternary shape."""
    pairs = _reachable_pairs("scripts.wiki_skills.wiki_query")
    assert pairs, "AST scan of wiki_query returned nothing — the scanner is broken"
    assert (4, "NO_CITATIONS") in pairs, "scanner missed a literal-token emit site"
    assert (2, "INVALID_AUDIENCE") in pairs, "scanner missed the ternary-assigned token shape"
    assert (6, "INVALID_INDEX_DB") in pairs, "scanner missed an INHERITED pair"
    assert (4, "NO_SUCH_TOKEN_ANYWHERE") not in pairs


# --------------------------------------------------------------------------------------------
# The assertions.
# --------------------------------------------------------------------------------------------

def test_which_tables_document_a_usage_row_is_pinned() -> None:
    """The skip list of the executed test is DECLARED, so it cannot quietly grow.

    Nine of twelve tables document no argparse row; that gap is recorded above. What this pins is
    the complement: if someone deletes the usage row from a table that has one, the executed
    assertion would start skipping instead of failing — a gate silently switching itself off.
    """
    without = {n for n in WITH_TABLE
               if not any(_USAGE_ROW.search(f"{e} {r}") for _c, e, r in
                          _exit_table_rows(RESOLVED[n][2]))}
    assert without == _NO_USAGE_ROW_DOCUMENTED, (
        f"usage-row coverage changed: newly undocumented={sorted(without - _NO_USAGE_ROW_DOCUMENTED)}, "
        f"newly documented={sorted(_NO_USAGE_ROW_DOCUMENTED - without)}. Update the roster deliberately."
    )
    assert len(WITH_TABLE) - len(without) >= 2, "no table documents a usage row — nothing to check"


@pytest.mark.parametrize("name", WITH_TABLE)
def test_documented_usage_code_matches_what_the_cli_actually_exits(name: str) -> None:
    """EXECUTED. The row that says "argparse/usage" must name the status argparse really returns.

    This is the assertion the three roast rounds could not make, and the one that catches the
    same falsehood however it is WORDED — which a literal grep structurally cannot.
    """
    rows = _exit_table_rows(RESOLVED[name][2])
    # Search the WHOLE row, not just the cause column. The first version of this test searched
    # only the last cell and silently skipped 10 of 12 CLIs — including the one it was written
    # to catch, whose row reads `| 1 | argparse / usage error | — |` with the text in column 2.
    # A gate that skips the case it exists for is the vacuous green this bead is about.
    usage_rows = [(code, f"{err} {rest}") for code, err, rest in rows
                  if _USAGE_ROW.search(f"{err} {rest}")]
    if not usage_rows:
        pytest.skip(f"{name}: table documents no argparse/usage row")
    observed = subprocess.run(
        [str(RESOLVED[name][0]), _BOGUS_FLAG],
        capture_output=True, cwd=_REPO_ROOT, timeout=60,
    ).returncode
    documented = {code for code, _rest in usage_rows}
    assert observed in documented, (
        f"{name}: `{name} {_BOGUS_FLAG}` exits {observed}, but its SKILL.md usage row(s) "
        f"claim {sorted(documented)}. argparse's own status is 2, always."
    )


@pytest.mark.parametrize("name", WITH_TABLE)
def test_no_documented_error_token_is_a_phantom(name: str) -> None:
    """Direction 1 — documented ⊆ reachable. A token no code can emit is a lie to the caller."""
    dotted = RESOLVED[name][1]
    assert dotted, f"{name}: could not resolve the bin/ wrapper to a module"
    documented = _documented_pairs(RESOLVED[name][2])
    reachable = _reachable_pairs(dotted)
    assert reachable, f"{name}: AST scan found no emit sites — non-vacuity guard"
    phantom = {(c, t) for c, t in documented if t not in {tok for _c, tok in reachable}}
    assert not phantom, (
        f"{name}: SKILL.md documents error token(s) that exist nowhere in {dotted}: "
        f"{sorted(phantom)}"
    )


@pytest.mark.parametrize("name", sorted(set(WITH_TABLE) - _DOES_NOT_CLAIM_COMPLETENESS))
def test_a_table_claiming_completeness_is_complete(name: str) -> None:
    """Direction 2 — reachable ⊆ documented, for tables that claim to enumerate everything.

    A table may be incomplete. What it may not be is *silently* incomplete: opt out by adding the
    CLI to _DOES_NOT_CLAIM_COMPLETENESS (and say so in the SKILL.md), or list every code.
    Inherited pairs count — 6/INVALID_INDEX_DB was missed by two separate roast rounds precisely
    because nobody thinks of the code their CLI did not write.
    """
    dotted = RESOLVED[name][1]
    documented = {tok for _c, tok in _documented_pairs(RESOLVED[name][2])}
    reachable = _reachable_pairs(dotted)
    missing = sorted({(c, t) for c, t in reachable if t not in documented})
    assert not missing, (
        f"{name}: its exit table claims completeness but omits {missing}. "
        f"Add the rows, or add {name!r} to _DOES_NOT_CLAIM_COMPLETENESS with a reason."
    )
