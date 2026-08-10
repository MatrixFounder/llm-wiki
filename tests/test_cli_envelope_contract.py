"""TASK 074 — the CLI *envelope* contract is a MECHANISM, not a sentence in `CLAUDE.md`.

WHY THIS FILE EXISTS. `tests/test_exit_code_doc_truth.py` (TASK 072 bead 072-03d) mechanised the
exit *codes* and stated, in its own docstring, what it deliberately could NOT do:

    CANNOT · free-prose semantics ("... never echoes the offending value", "one JSON envelope
             per invocation"). Those are English, not data.

The 2026-08-07 census then measured two of those prose claims FALSE and filed them as DF-072-3
and DF-072-5. This file closes the half of each that IS data:

  * **DF-072-3** — «Every CLI emits one JSON envelope + a stable exit code» is false on the usage
    path: argparse writes usage to *stderr* and exits 2 **before** any `emit()` runs, so stdout is
    EMPTY. A caller written against the universal claim does `json.loads(stdout)` and crashes (or
    silently swallows) instead of surfacing the argparse message. Gate A measures the real shape.
  * **DF-072-5** — `wiki-init` emitted a `received` key echoing the offending `vault_id`: the one
    key `docs/architectures/functional/components.md:291` names as forbidden (CWE-117). It went
    unseen for 14 months because the three runtime canary suites enumerate their CLIs by HAND, and
    the hand-list was derived from the instances already known. `wiki_init` is imported by nine
    test files and by none of the canaries. Gate B derives its roster from `bin/`.

>>> A census predicate derived from the instances you already found is not a census. <<<

So, exactly as in the sibling file: every roster here is DISCOVERED AT RUNTIME. A CLI added
tomorrow is in scope without editing this file; excluding one requires an explicit entry with a
stated reason.

WHAT THIS FILE CAN AND CANNOT DO — stated precisely, because an overclaiming gate is the failure
being fixed. The first cut of this docstring *was* an instance of it: a `/vdd-multi` pass found
that it claimed a complete blind-spot census while measuring only a degenerate case, and claimed
to scan "every source file of every CLI" while `_common.py` — the shared emitter every `wiki-*`
CLI calls — was outside every scan set. Both are corrected below and both are now pinned.

  CAN  · what each `bin/` CLI ACTUALLY writes to stdout, and exits, on an unrecognised flag
         (a real process, real bytes);
       · the literal keys of every **error-bearing dict literal** passed to an `*emit(...)` call,
         in every source file of every `bin/` CLI **and** in every other `emit`-calling file under
         `scripts/` (the shared-emitter population, computed as the set difference — see
         `test_no_shared_emitter_carries_a_forbidden_key`);
       · how many emit sites are structurally invisible to that scan, per CLI, pinned as a number
         so the blind spot cannot grow silently;
       · that `wiki-lint --strict`'s non-zero exit carries a *parseable success envelope* — the
         discrimination a `rc == 1`-only assertion structurally cannot make (DF-072-4).

  CANNOT · **values.** This is a check on four forbidden KEY NAMES, not on whether a value is
         operator-supplied. `{"error": …, "offending": v}` passes. The runtime canary suites
         (`test_wiki_query_envelope_safety.py` et al.) check values on the CLIs they cover; this
         checks keys over the complete roster. Neither is redundant, and neither alone is
         "no envelope echoes the offending value".
       · **any emit payload that is not a dict literal at the call site.** Measured shapes in this
         tree: a bare variable (`emit(envelope, …)`), a call result (`emit(reindex_full(...))`), a
         `dict(...)` constructor, a keyword payload (`emit(payload=…)`), `{**base, …}` where
         `base` is a Name, non-`ast.Constant` keys, and a literal that is MUTATED after
         construction (`env["k"] = v`). Also invisible: envelopes carried by a raised domain
         exception (`ImportArticleError(...).envelope()`) and any emitter helper whose name does
         not end in `emit`. `_NON_LITERAL_EMIT_SITES` counts the first family per CLI and pins it.
       · the two deliberate non-JSON *success* modes (`wiki-search --format markdown`,
         `wiki-sync scan --dry-run`) and `wiki-config serve`'s stderr banner. Those are features,
         documented in prose at each site; asserting them here would pin behaviour this task
         explicitly does not change (TASK 074 §4 Non-Goals). ⚠️ Anything claiming this file gates
         them is wrong — see the Decision-17 paragraph, which was corrected for exactly that.
"""

from __future__ import annotations

import ast
import functools
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills._common import _REPO_ROOT
from tests.test_exit_code_doc_truth import CLIS, _module_paths

_BOGUS_FLAG = "--definitely-not-a-real-flag-0723"

#: `docs/architectures/functional/components.md:291` — the universal envelope invariant
#: (CWE-117 / CWE-209). Kept in sync with `tests/test_wiki_extract_concepts.py`'s runtime
#: canary; this is the STATIC half, and the half whose population is complete.
_FORBIDDEN_ENVELOPE_KEYS = frozenset({"content", "value", "raw", "received"})

#: Roots swept for the shared-emitter population (everything `emit`-calling that no CLI's own
#: scan set reaches). Computed as a set difference, never listed — `_common.py` was invisible to
#: every CLI while holding two live error envelopes, and no control could see that.
_EMIT_SWEEP_ROOTS = ("scripts",)

#: CLIs with **zero** error-bearing dict literals — the scan finds nothing to check in them.
#: Distinct from `_NON_LITERAL_EMIT_SITES` below: this is "nothing to see", that is "something
#: we cannot see". Both are pinned; conflating them is what made the first cut overclaim.
#: ★ It SHRANK, which is the direction that matters. `wiki-lint` and `wiki-reindex` left this
#: set when DF-074-4 gave each an explicit `VAULT_NOT_FOUND` literal — the pin's failure message
#: says "FIRST consider restoring a dict-literal payload (that is coverage)", and that is what
#: happened: the fix for a silent-green defect also moved two CLIs out of the blind spot.
_NO_LITERAL_ERROR_ENVELOPE = {
    "obsidian-active-note": "`_emit(res, fmt)` — every payload is a variable built by the resolver",
    "obsidian-context": "`_emit(envelope, fmt)` — payload is a variable",
    "obsidian-selection": "`_emit(envelope, fmt)` — payload is a variable",
}

#: Emit sites whose payload is NOT a dict literal, per CLI — the real blind spot, counted.
#: ⚠️ This is the pin that matters. `_NO_LITERAL_ERROR_ENVELOPE` only catches a CLI dropping to
#: ZERO literals; a CLI keeping one literal could add unlimited invisible envelopes beside it and
#: nothing went red. That is DF-072-5's own failure mode reproduced inside its fix, and it is what
#: this dict closes: the number can go DOWN freely, and up only by a deliberate edit here.
_NON_LITERAL_EMIT_SITES = {
    "obsidian-active-note": 5,
    "obsidian-context": 1,
    "obsidian-selection": 1,
    "wiki-config": 7,
    "wiki-extract-concepts": 6,
    "wiki-extract-decisions": 5,
    "wiki-health": 3,
    "wiki-import": 4,
    "wiki-index-upsert": 1,
    "wiki-query": 1,
    "wiki-reindex": 3,
    "wiki-search": 1,
    "wiki-sync": 2,
    "wiki-verify-multi": 1,
}


# --------------------------------------------------------------------------------------------
# Discovery — computed, never transcribed. Lazy: pytest imports every test module at collection,
# so doing the AST work at import time taxes `pytest -k something-else` too (measured +0.21s on
# a 0.33s collect). `lru_cache` keeps exactly one parse per file for a full run.
# --------------------------------------------------------------------------------------------

def _cli_sources(wrapper: Path) -> list[Path]:
    """Every `.py` file a `bin/` wrapper execs. Read the wrapper; never guess from its name.

    Two shapes live in `bin/`, and an earlier cut handled only the first — which silently dropped
    the three `obsidian-*` CLIs. That is the same exclusion-by-omission this file exists to
    prevent, so both are resolved:

      * `exec python -m scripts.wiki_skills.wiki_query "$@"`      (the wiki-* family)
      * `exec python3 "$REPO/skills/obsidian-cli/scripts/x.py"`   (the stdlib-only obsidian trio)

    Anchored to the `exec` line, not searched free-form: a commented-out `# was: python -m
    scripts.wiki_skills.old_module` would otherwise resolve the wrapper to the WRONG module, and
    every control here would stay green while Gate B scanned the wrong files.
    """
    text = wrapper.read_text(encoding="utf-8")
    m = re.search(r"^\s*exec\s+python3?\s+-m\s+([\w.]+)", text, re.M)
    if m:
        return _module_paths(m.group(1))
    m = re.search(r'^\s*exec\s+python3?\s+"\$REPO/([^"]+\.py)"', text, re.M)
    if m:
        candidate = _REPO_ROOT / m.group(1)
        return [candidate] if candidate.is_file() else []
    return []


@functools.lru_cache(maxsize=None)
def _sources_for(name: str) -> tuple[Path, ...]:
    return tuple(_cli_sources(CLIS[name]))


@functools.lru_cache(maxsize=None)
def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _emit_calls(paths: tuple[Path, ...] | list[Path]) -> list[tuple[Path, int, ast.expr | None]]:
    """(file, lineno, payload-arg-or-None) for every `*emit(...)` call in these files."""
    out: list[tuple[Path, int, ast.expr | None]] = []
    for path in paths:
        for node in ast.walk(_parse(path)):
            if not isinstance(node, ast.Call):
                continue
            fname = (
                node.func.id if isinstance(node.func, ast.Name)
                else node.func.attr if isinstance(node.func, ast.Attribute)
                else None
            )
            if fname is None or not fname.endswith("emit"):
                continue
            out.append((path, node.lineno, node.args[0] if node.args else None))
    return out


def _payload_dicts(node: ast.expr) -> list[ast.Dict]:
    """Every dict literal belonging to the PAYLOAD, reached through container literals only.

    Descends through dict values, list/tuple/set elements and ternary branches — and stops at a
    `Call` or `Lambda`. A blanket `ast.walk` would also reach dicts inside call arguments nested
    in the payload, so a legitimate `emit({"error": …, "counts": summarise({"raw": n})}, 4)`
    would false-positive on `raw`. The cheapest response to a false positive is to rename a good
    key or add an exclusion — the exact reflex this suite is built against — so the recursion is
    scoped instead. Nesting through containers IS followed: TASK 064 made the runtime canary walk
    `violations[]` recursively, and a static mirror narrower than the thing it mirrors is useless.
    """
    found: list[ast.Dict] = []
    if isinstance(node, ast.Dict):
        found.append(node)
        for value in node.values:
            if value is not None:
                found.extend(_payload_dicts(value))
    elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        for elt in node.elts:
            found.extend(_payload_dicts(elt))
    elif isinstance(node, ast.IfExp):
        found.extend(_payload_dicts(node.body))
        found.extend(_payload_dicts(node.orelse))
    return found


def _literal_keys(node: ast.expr) -> set[str]:
    return {
        k.value
        for d in _payload_dicts(node)
        for k in d.keys
        if isinstance(k, ast.Constant) and isinstance(k.value, str)
    }


def _is_error_bearing(node: ast.expr) -> bool:
    """True if ANY dict in the payload carries a literal `error` key — at any depth.

    Top-level-only classification was a hole this task's own DF-072-4 evidence predicts: the
    codebase has success envelopes carrying per-item error records (`skipped[]`, `violations[]`,
    per-file results). A leak inside one of those was outside the gate entirely.
    """
    return any(
        isinstance(k, ast.Constant) and k.value == "error"
        for d in _payload_dicts(node) for k in d.keys
    )


@functools.lru_cache(maxsize=None)
def _error_envelopes(name: str) -> tuple[tuple[Path, int, ast.expr], ...]:
    return tuple(
        (p, ln, pl) for p, ln, pl in _emit_calls(_sources_for(name))
        if pl is not None and _is_error_bearing(pl)
    )


@functools.lru_cache(maxsize=None)
def _non_literal_sites(name: str) -> tuple[tuple[Path, int], ...]:
    return tuple(
        (p, ln) for p, ln, pl in _emit_calls(_sources_for(name))
        if not isinstance(pl, ast.Dict)
    )


@functools.lru_cache(maxsize=None)
def _shared_emitter_files() -> tuple[Path, ...]:
    """Every `emit`-calling file under `scripts/` that NO CLI's own scan set reaches.

    Computed as a set difference. `_common.py` — which holds `SKILL_INTEGRITY_DRIFT` and the
    `INVALID_INDEX_DB` envelope inherited by every `wiki-*` CLI, the highest-blast-radius error
    envelope in the repo — sat here, invisible to all 22 per-CLI scans, while the issue text
    claimed the scan covered "every source file of every CLI".
    """
    covered = {p.resolve() for name in CLIS for p in _sources_for(name)}
    out: list[Path] = []
    for root in _EMIT_SWEEP_ROOTS:
        for path in sorted((_REPO_ROOT / root).rglob("*.py")):
            if "__pycache__" in path.parts or path.resolve() in covered:
                continue
            if any(True for _p, _ln, _pl in _emit_calls([path])):
                out.append(path)
    return tuple(out)


# --------------------------------------------------------------------------------------------
# Controls — this gate must be able to FAIL. A check that examines nothing is not a check.
# --------------------------------------------------------------------------------------------

def test_the_discovered_population_is_not_empty() -> None:
    """Non-vacuity. If discovery returns nothing, every parametrised assertion passes trivially."""
    assert len(CLIS) >= 15, f"bin/ walk found only {len(CLIS)} CLIs — discovery is broken"
    unresolved = sorted(n for n in CLIS if not _sources_for(n))
    assert not unresolved, (
        f"{unresolved}: could not resolve the bin/ wrapper to any source file. A CLI whose "
        "sources cannot be found is invisible to Gate B — extend `_cli_sources`, do not skip it."
    )
    total = sum(len(_error_envelopes(n)) for n in CLIS)
    assert total >= 150, (
        f"only {total} error-bearing literals found across {len(CLIS)} CLIs — the AST scan is "
        "broken, and Gate B would be a vacuous green"
    )
    assert _shared_emitter_files(), (
        "the shared-emitter sweep found no files — it must at minimum reach "
        "scripts/wiki_skills/_common.py, which emits INVALID_INDEX_DB for every wiki-* CLI"
    )


def test_the_zero_literal_clis_are_pinned() -> None:
    """Which CLIs have NOTHING for the scan to check, pinned so the set cannot grow quietly."""
    measured = {n for n in CLIS if not _error_envelopes(n)}
    declared = set(_NO_LITERAL_ERROR_ENVELOPE)
    assert measured == declared, (
        f"zero-literal set changed: newly empty={sorted(measured - declared)}, "
        f"newly non-empty={sorted(declared - measured)}.\n"
        "FIRST consider restoring a dict-literal payload at the emit site (that is coverage). "
        "If the CLI genuinely has none, update `_NO_LITERAL_ERROR_ENVELOPE` WITH A REASON. "
        "If its sources failed to resolve at all, fix `_cli_sources` — do NOT add an entry."
    )


def test_the_invisible_emit_sites_are_counted_and_pinned() -> None:
    """★ The pin that actually bounds the blind spot.

    `_NO_LITERAL_ERROR_ENVELOPE` catches only a CLI falling to ZERO literals. A CLI that keeps one
    literal envelope can add any number of non-literal ones beside it, and that check stays green
    — so "the blind spot cannot grow by omission" was FALSE as first written. Measured at the time
    of writing: 41 invisible sites across 14 CLIs, 10 of them in CLIs the old pin counted as fully
    covered. Counting them per CLI makes the number go DOWN freely and UP only by editing this
    dict, which is a reviewable diff.
    """
    measured = {n: len(_non_literal_sites(n)) for n in CLIS if _non_literal_sites(n)}
    assert measured == _NON_LITERAL_EMIT_SITES, (
        "the count of emit sites INVISIBLE to Gate B changed.\n"
        f"  measured: {dict(sorted(measured.items()))}\n"
        f"  declared: {dict(sorted(_NON_LITERAL_EMIT_SITES.items()))}\n"
        "A rise means new envelope surface the static scan cannot see. Prefer a dict literal at "
        "the emit site; if the payload genuinely must be built elsewhere, raise the number here "
        "deliberately and make sure a runtime canary covers that CLI."
    )


def test_gate_b_scanner_can_actually_fire(tmp_path: Path) -> None:
    """Mutation control: plant forbidden keys and prove the scanner sees them — at depth, inside
    a success payload, and NOT in the two places it must stay quiet. All four halves matter: a
    scanner that flags every dict is as useless as one that flags none, because it gets muted."""
    probe = tmp_path / "probe_module.py"
    probe.write_text(
        "def f():\n"
        "    emit({'error': 'X', 'received': value}, 2)\n"                    # 2: depth 0
        "    emit({'error': 'Y', 'violations': [{'raw': v}]}, 4)\n"           # 3: nested in a list
        "    emit({'action': 'ok', 'skipped': [{'error': e, 'value': v}]})\n"  # 4: error nested in
        "    emit({'error': 'Z', 'field': 'ok'}, 2)\n"                        # 5: clean
        "    emit({'error': 'W', 'n': count({'raw': v})}, 2)\n"               # 6: inside a Call
        "    rows = {'value': 1}\n"                                           # 7: not a payload
        "    return rows\n",
        encoding="utf-8",
    )
    calls = _emit_calls([probe])
    assert len(calls) == 5, f"scanner lost emit sites: {calls}"
    errored = [(ln, pl) for _p, ln, pl in calls if pl is not None and _is_error_bearing(pl)]
    assert sorted(ln for ln, _ in errored) == [2, 3, 4, 5, 6], (
        f"error-bearing classification wrong (line 4 is the nested-in-success case): {errored}"
    )
    hits = sorted(ln for ln, pl in errored if _literal_keys(pl) & _FORBIDDEN_ENVELOPE_KEYS)
    assert hits == [2, 3, 4], (
        "expected the depth-0 leak, the list-nested leak and the leak nested inside a SUCCESS "
        f"payload — and NOT line 6 (inside a Call) or line 7 (not a payload); got {hits}"
    )


def test_gate_a_probe_can_actually_fire(tmp_path: Path) -> None:
    """Mutation control for the argparse-shape gate: a program that prints to stdout and exits 2
    must be REJECTED by the same predicate the real assertion uses."""
    fake = tmp_path / "fake-cli"
    fake.write_text('#!/bin/sh\necho \'{"error":"X"}\'\nexit 2\n', encoding="utf-8")
    fake.chmod(0o755)
    proc = subprocess.run([str(fake), _BOGUS_FLAG], capture_output=True, timeout=20)
    assert proc.returncode == 2 and proc.stdout != b"", (
        "the probe itself is broken — it must reproduce the shape the gate rejects"
    )


# --------------------------------------------------------------------------------------------
# Gate A (DF-072-3) — what a usage refusal ACTUALLY looks like.
# --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(CLIS))
def test_argparse_refusal_emits_no_envelope(name: str) -> None:
    """EXECUTED, over the whole `bin/` roster.

    This is the measurement that makes the corrected Decision-17 sentence true rather than
    reviewed: an argparse refusal PRECEDES the envelope contract. Usage goes to stderr, the
    status is argparse's own 2, and stdout is **empty** — so `json.loads(stdout)` on this path
    is a caller bug, not a CLI bug, and the docs now say which is which.

    If a CLI ever wants to answer a usage error WITH an envelope, that is a legitimate design
    change — but it is a *contract* change, and it must be made deliberately here and in the
    Decision-17 paragraph, not discovered by a caller in production.

    Timeout is 20s, not 60s: the measured worst case is 0.12s, so 20s is a ~150x margin for a
    cold shared runner while bounding a whole-roster hang at ~7 min instead of ~22.
    """
    proc = subprocess.run(
        [str(CLIS[name]), _BOGUS_FLAG], capture_output=True, cwd=_REPO_ROOT, timeout=20,
    )
    assert proc.returncode == 2, (
        f"{name} {_BOGUS_FLAG}: exit {proc.returncode}, expected argparse's own status 2"
    )
    assert proc.stdout == b"", (
        f"{name} {_BOGUS_FLAG}: wrote {len(proc.stdout)} byte(s) to stdout "
        f"({proc.stdout[:120]!r}). The Decision-17 contract says the usage path emits NO "
        "envelope; update the contract in CLAUDE.md/AGENTS.md if that changed on purpose."
    )


# --------------------------------------------------------------------------------------------
# Gate B (DF-072-5) — no error envelope carries one of the four forbidden KEY NAMES.
# (Not "echoes the offending value" — see the CANNOT block. `{"error": …, "offending": v}` passes.)
# --------------------------------------------------------------------------------------------

def _leaks(sites: tuple[tuple[Path, int, ast.expr], ...]) -> list[str]:
    return [
        f"{path.relative_to(_REPO_ROOT)}:{lineno} -> "
        f"{sorted(_literal_keys(pl) & _FORBIDDEN_ENVELOPE_KEYS)}"
        for path, lineno, pl in sites
        if _literal_keys(pl) & _FORBIDDEN_ENVELOPE_KEYS
    ]


@pytest.mark.parametrize("name", sorted(CLIS))
def test_no_error_envelope_carries_a_forbidden_key(name: str) -> None:
    """`{error, field?, reason, violations?}` — with NO `content`/`value`/`raw`/`received` key.

    The invariant is `docs/architectures/functional/components.md:291`. `wiki-init` violated it at
    three sites for 14 months; a one-token grep would have found it at any point. What kept it
    hidden was not the difficulty of the check but the **population** of the checks — hand-listed
    from the CLIs the invariant was written for. Here the population is `bin/`.
    """
    if name in _NO_LITERAL_ERROR_ENVELOPE:
        pytest.skip(f"{name}: {_NO_LITERAL_ERROR_ENVELOPE[name]}")
    sites = _error_envelopes(name)
    assert sites, f"{name}: classified as having literal error envelopes, but the scan found none"
    leaks = _leaks(sites)
    assert not leaks, (
        f"{name}: error envelope(s) carry a forbidden key (CWE-117):\n  " + "\n  ".join(leaks)
        + "\nName the input with `field` and the expectation with `pattern`/`reason` instead."
    )


def test_no_shared_emitter_carries_a_forbidden_key() -> None:
    """The population no per-CLI scan reaches — computed, not listed.

    `scripts/wiki_skills/_common.py` emits `SKILL_INTEGRITY_DRIFT` (exit 2) and `INVALID_INDEX_DB`
    (exit 6). The latter is inherited by every `wiki-*` CLI, so a forbidden key added there would
    surface in all of them at once — and it was outside all 22 per-CLI scan sets. Found by a
    `/vdd-multi` pass on TASK 074 itself, which is the point: the fix for an unenumerated surface
    had its own unenumerated surface.
    """
    files = _shared_emitter_files()
    sites = tuple(
        (p, ln, pl) for p, ln, pl in _emit_calls(files)
        if pl is not None and _is_error_bearing(pl)
    )
    assert sites, (
        f"no error-bearing literal found in the shared-emitter sweep ({[str(f) for f in files]}) "
        "— non-vacuity guard; _common.py has at least two"
    )
    leaks = _leaks(sites)
    assert not leaks, (
        "shared emitter(s) carry a forbidden key (CWE-117) — blast radius is EVERY CLI that "
        "calls them:\n  " + "\n  ".join(leaks)
    )


# --------------------------------------------------------------------------------------------
# DF-072-4 — `wiki-lint --strict` exits non-zero with a SUCCESS envelope.
# --------------------------------------------------------------------------------------------

def _gating_vault(tmp_path: Path) -> tuple[Path, Path]:
    """A vault with exactly one, genuinely GATING lint issue (`missing-on-disk`)."""
    root = tmp_path / "vault"
    (root / "_concepts").mkdir(parents=True)
    (root / "WIKI_SCHEMA.md").write_text(
        '---\nvault_id: gatev\nschema_version: "2.0"\nlanguage: en\nlayout: karpathy\n---\n',
        encoding="utf-8")
    (root / "_concepts" / "alpha.md").write_text(
        "---\ntype: concept\nname: alpha\n---\n\n# alpha\n", encoding="utf-8")
    db = tmp_path / "d.db"
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(vault_id="gatev", name="gatev", root_path=root,
                              schema_version="2.0", registered_at=datetime(2026, 8, 10)))
    assert reindex_full(repo, "gatev")["skipped"] == []
    repo.close()
    (root / "_concepts" / "alpha.md").unlink()   # DB row survives -> missing-on-disk, gating
    return root, db


def _run_lint(root: Path, db: Path, *strict: str) -> tuple[int, dict[str, object]]:
    """Run the real `bin/wiki-lint` and return (rc, envelope).

    Asserts stdout is EXACTLY one line — the sibling clause of the same contract this file pins
    ("Output is exactly one line of JSON on stdout"). Taking `splitlines()[-1]` would silently
    tolerate a stray `print()` that breaks `json.loads(stdout)` for every real caller.
    """
    proc = subprocess.run(
        [str(_REPO_ROOT / "bin" / "wiki-lint"), "--vault", "gatev",
         "--vault-root", str(root), "--db-path", str(db), *strict],
        capture_output=True, cwd=_REPO_ROOT, timeout=45,
    )
    assert proc.stdout, (
        f"empty stdout means a crash, not a verdict; stderr={proc.stderr[-400:]!r}")
    lines = proc.stdout.decode("utf-8").strip().splitlines()
    assert len(lines) == 1, f"stdout must be exactly one JSON line, got {len(lines)}: {lines}"
    return proc.returncode, json.loads(lines[0])


def test_wiki_lint_strict_gate_is_a_success_envelope_at_exit_1(tmp_path: Path) -> None:
    """★ DF-072-4, and the assertion the issue's own ⚠️ demands.

    `wiki-lint --strict` exits **1** on a tripped gate while printing a NORMAL SUCCESS payload —
    a second instance of the "non-zero exit carrying a success envelope" divergence the repo had
    documented as unique to `wiki-verify-multi`'s exit 6. It stays at 1 by decision (TASK 074
    D-074-2: the issue's proposed move "to the family's 6" would land on `wiki-lint`'s INHERITED
    `INVALID_INDEX_DB`, reproducing the very ambiguity it meant to remove), and the collision is
    fenced in `skills/wiki-lint/SKILL.md` instead.

    What makes the fence usable is that the two meanings of 1 ARE discriminable, and this test is
    what pins that: a crash writes **nothing** to stdout, a tripped gate writes a parseable
    envelope with no `error` key. `rc == 1` alone cannot tell them apart — which is exactly how a
    caller applying the family's "1 = unhandled exception" convention misreads a working gate.
    """
    root, db = _gating_vault(tmp_path)
    rc, env = _run_lint(root, db, "--strict")
    assert rc == 1, f"expected the --strict gate to trip, got {rc}: {env}"
    assert "error" not in env, f"the --strict gate envelope must be a SUCCESS payload: {env}"
    assert env["action"] == "linted", env
    # The fixture promises ONE gating issue of a KNOWN category. Asserting only `> 0` would let
    # the pin survive `missing-on-disk` ceasing to gate, so long as anything else fired.
    assert env["by_category"] == {"missing-on-disk": 1}, (
        f"the fixture must trip exactly the issue it seeds: {env['by_category']}")
    assert env["total_issues"] == 1, env


def test_wiki_lint_without_strict_reports_the_same_issues_at_exit_0(tmp_path: Path) -> None:
    """The other half of the fence: the gate is `--strict`, not the finding.

    Without it the identical issues are reported and the exit is 0 — so a caller that reads
    `total_issues` rather than `$?` gets the same information either way, which is what the
    corrected SKILL.md tells it to do. `strict` IS threaded into `run_all_checks_report`, where it
    changes severity, so "identical" is asserted on the actual payload rather than assumed.
    """
    root, db = _gating_vault(tmp_path)
    rc_plain, plain = _run_lint(root, db)
    assert rc_plain == 0, f"the finding must not gate without --strict: {plain}"
    assert "error" not in plain, plain

    root2, db2 = _gating_vault(tmp_path / "strict")
    _rc, strict = _run_lint(root2, db2, "--strict")
    assert plain["by_category"] == strict["by_category"], (
        f"--strict changed WHAT is reported, not just the exit code: "
        f"{plain['by_category']} vs {strict['by_category']}")
    assert plain["total_issues"] == strict["total_issues"], (plain, strict)


# --------------------------------------------------------------------------------------------
# DF-074-4 — a NAMED vault must exist before its emptiness can mean anything.
# --------------------------------------------------------------------------------------------

def _empty_registered_vault(tmp_path: Path) -> tuple[Path, Path]:
    """A real, registered, CLEAN vault — so "0 issues" is earned rather than vacuous."""
    root = tmp_path / "vault"
    (root / "_concepts").mkdir(parents=True)
    (root / "WIKI_SCHEMA.md").write_text(
        '---\nvault_id: realv\nschema_version: "2.0"\nlanguage: en\nlayout: karpathy\n---\n',
        encoding="utf-8")
    db = tmp_path / "d.db"
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(vault_id="realv", name="realv", root_path=root,
                              schema_version="2.0", registered_at=datetime(2026, 8, 10)))
    repo.close()
    return root, db


@pytest.mark.parametrize("extra", [[], ["--strict"]])
def test_wiki_lint_refuses_an_unregistered_vault_instead_of_reporting_it_clean(
    tmp_path: Path, extra: list[str],
) -> None:
    """★ DF-074-4. `--vault <typo>` used to return `{"total_issues": 0}` at exit 0 — a clean
    bill of health for a vault that does not exist, on the surface this project documents as
    its **CI gate**. A typo in a CI config turned the gate permanently green.

    ★★ And TASK 061's vacuity machinery structurally could not catch it: `denominators: {}`
    legitimately means "these config-driven checks do not apply to this layout", NOT
    "examined 0", so `vacuous_checks` stayed `[]` and the zero read as earned. The one signal
    built to detect a vacuous green was silent on the most vacuous input possible.

    Asserted on the ENVELOPE, not the code alone: `rc == 6` cannot tell `VAULT_NOT_FOUND` from
    the inherited `INVALID_INDEX_DB`, which is the exact trap this file exists for.
    """
    root, db = _empty_registered_vault(tmp_path)
    proc = subprocess.run(
        [str(_REPO_ROOT / "bin" / "wiki-lint"), "--vault", "no-such-vault-xyz",
         "--vault-root", str(root), "--db-path", str(db), *extra],
        capture_output=True, cwd=_REPO_ROOT, timeout=45,
    )
    assert proc.returncode == 6, f"expected VAULT_NOT_FOUND at 6; stderr={proc.stderr[-300:]!r}"
    env = json.loads(proc.stdout.decode("utf-8").strip())
    assert env["error"] == "VAULT_NOT_FOUND" and env["field"] == "vault", env
    assert "total_issues" not in env, f"a refusal must not look like a lint report: {env}"


def test_wiki_lint_still_reports_a_registered_but_clean_vault_as_clean(tmp_path: Path) -> None:
    """The other side of DF-074-4 — the fix must not turn an EARNED zero into a refusal.
    A registered vault with nothing wrong still exits 0 with a real report."""
    root, db = _empty_registered_vault(tmp_path)
    proc = subprocess.run(
        [str(_REPO_ROOT / "bin" / "wiki-lint"), "--vault", "realv",
         "--vault-root", str(root), "--db-path", str(db), "--strict"],
        capture_output=True, cwd=_REPO_ROOT, timeout=45,
    )
    assert proc.returncode == 0, f"a clean registered vault must pass: {proc.stdout!r}"
    env2 = json.loads(proc.stdout.decode("utf-8").strip())
    assert "error" not in env2 and env2["total_issues"] == 0, env2


@pytest.mark.parametrize("mode", ["--full", "--delta"])
def test_wiki_reindex_refuses_an_unregistered_vault_instead_of_crashing(
    tmp_path: Path, mode: str,
) -> None:
    """★ DF-074-4 family sweep. `reindex_full`/`reindex_delta` raise
    `ValueError("vault_id=… not registered")` and nothing caught it, so a typo'd `--vault`
    exited **1 with no envelope and a raw traceback that echoed the vault_id** — the family's
    "this is a bug in the CLI" signal, for plain user input.

    Found because DF-074-4's fix shape said to sweep the family rather than fix the one
    instance found. It was the second defect in a roster of eight.
    """
    root, db = _empty_registered_vault(tmp_path)
    proc = subprocess.run(
        [str(_REPO_ROOT / "bin" / "wiki-reindex"), mode, "--vault", "no-such-vault-xyz",
         "--vault-root", str(root), "--db-path", str(db)],
        capture_output=True, cwd=_REPO_ROOT, timeout=45,
    )
    assert proc.returncode == 6, f"expected VAULT_NOT_FOUND at 6, got {proc.returncode}"
    env = json.loads(proc.stdout.decode("utf-8").strip())
    assert env["error"] == "VAULT_NOT_FOUND" and env["field"] == "vault", env
    assert "no-such-vault-xyz" not in proc.stdout.decode("utf-8"), \
        "the refusal must not echo the operator's value (CWE-117)"
    assert b"Traceback" not in proc.stderr, "a typo must not produce a traceback"
