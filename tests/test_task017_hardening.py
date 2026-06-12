"""TASK 017 — perf + security hardening (P-2, P-3, R-X1-REDOS-RT).

Stub-First test surface, populated bead-by-bead (017-00…13). Phase 1 (the SEV-2
ReDoS runtime deadline) follows skill-tdd-strict: AC-017-1 is a strict regression
(the catastrophic-pattern test must hang/timeout with the guard removed).
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import pytest

# A pattern catastrophic *under the `regex` engine* (verified: ~2.8 s at n=24).
# Used both to prove the runtime deadline fires and that the load-gate rejects it.
_CATASTROPHIC = r"(a|a)*$"
_LONG_LINE = "a" * 100_000 + "!"          # the 100 KB single-line threat model


def test_smoke_imports() -> None:
    """017-00 anchor: the new dependency and the touched module both import."""
    import regex  # noqa: F401 — the PyPI linear-deadline engine (R-X1-REDOS-RT)

    import scripts.wiki_index.layout_config  # noqa: F401


# --------------------------------------------------------------------------- #
# 017-01 / 017-03 — the guard helper
# --------------------------------------------------------------------------- #


def test_guarded_finditer_timeout() -> None:
    """operator=True → catastrophic pattern on a 100 KB line raises builtin
    TimeoutError within ~the budget (NOT regex.TimeoutError — verified)."""
    from scripts.wiki_index.layout_config import guarded_finditer

    t0 = time.monotonic()
    with pytest.raises(TimeoutError):
        list(guarded_finditer(_CATASTROPHIC, _LONG_LINE, operator=True,
                              deadline=time.monotonic() + 0.5))
    assert time.monotonic() - t0 < 3.0, "deadline did not bound the search"


def test_guarded_builtin_uses_re() -> None:
    """operator=False → byte-identical to stdlib re.finditer output."""
    from scripts.wiki_index.layout_config import guarded_finditer

    pat = r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]"
    body = "see [[Foo]] and [[Bar|baz]] end"
    got = [m.group(1) for m in guarded_finditer(pat, body, operator=False, deadline=None)]
    exp = [m.group(1) for m in re.compile(pat).finditer(body)]
    assert got == exp == ["Foo", "Bar"]


# --------------------------------------------------------------------------- #
# 017-02 — provenance flags in the loader
# --------------------------------------------------------------------------- #


def test_provenance_false_builtin(tmp_path: Path) -> None:
    """A vault with no override → both provenance flags False (built-ins pay zero)."""
    from scripts.wiki_index.layout_config import resolve_layout_config

    cfg = resolve_layout_config(tmp_path)            # no WIKI_SCHEMA → karpathy default
    assert cfg.ref_extraction_operator_supplied is False
    assert cfg.paths_operator_supplied is False


def test_provenance_flags_on_override(tmp_path: Path) -> None:
    """A `.wiki/layout.yaml` override that SUPPLIES ref_extraction → flag True."""
    from scripts.wiki_index.layout_config import resolve_layout_config

    wiki = tmp_path / ".wiki"
    wiki.mkdir()
    # safe (linear) override pattern → passes the load-gate; only `ref_extraction` set.
    (wiki / "layout.yaml").write_text(
        "ref_extraction:\n"
        "  - kind: wiki-link\n"
        "    regex: '\\[\\[([^\\]|]+)(?:\\|[^\\]]+)?\\]\\]'\n"
        "    target_group: 1\n",
        encoding="utf-8",
    )
    cfg = resolve_layout_config(tmp_path)
    assert cfg.ref_extraction_operator_supplied is True
    assert cfg.paths_operator_supplied is False


# --------------------------------------------------------------------------- #
# 017-04 — extract_refs wiring
# --------------------------------------------------------------------------- #


def test_extract_refs_operator_timeout_skips() -> None:
    """UC-1: operator-custom catastrophic rule on a 100 KB line → [] + WARN, no hang."""
    from scripts.wiki_index.layout_config import RefRule
    from scripts.wiki_source.parsing import extract_refs

    rule = RefRule(kind="wikilink", regex=_CATASTROPHIC, target_group=0, transform=None)
    t0 = time.monotonic()
    out = extract_refs(_LONG_LINE, [rule], operator_supplied=True, budget_s=0.5)
    assert out == []
    assert time.monotonic() - t0 < 3.0, "extract_refs did not bound the catastrophic scan"


def test_extract_refs_builtin_byte_identical() -> None:
    """UC-2: built-in path (operator_supplied=False) unchanged behaviour."""
    from scripts.wiki_index.layout_config import RefRule
    from scripts.wiki_source.parsing import extract_refs

    rule = RefRule(kind="wikilink", regex=r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]",
                   target_group=1, transform=None)
    body = "line one [[Alpha]]\nline two [[Beta|b]] and [[Gamma]]"
    out = extract_refs(body, [rule])          # default operator_supplied=False
    assert [t for t, _, _ in out] == ["Alpha", "Beta", "Gamma"]
    assert [ln for _, ln, _ in out] == [1, 2, 2]


# --------------------------------------------------------------------------- #
# 017-05 — _derive_project wiring
# --------------------------------------------------------------------------- #


def test_derive_project_operator_timeout_unmatched() -> None:
    """Operator catastrophic project_pattern on a long rel-path → UNMATCHED_PROJECT."""
    from scripts.wiki_index.layout_config import (
        UNMATCHED_PROJECT,
        PathEntry,
        _derive_project,
    )

    entry = PathEntry(
        glob="**/*.md", type=None, project=None,
        project_pattern=_CATASTROPHIC, project_template="${g}",
        project_slug_strategy=None, default_tags=(), extra_tags=(),
    )
    # the non-matching `!` tail forces catastrophic backtracking (an all-`a` input
    # would simply match and return fast — no backtracking, no timeout).
    t0 = time.monotonic()
    got = _derive_project(_LONG_LINE, entry, operator_supplied=True)
    assert got == UNMATCHED_PROJECT
    assert time.monotonic() - t0 < 3.0


# --------------------------------------------------------------------------- #
# 017-06 — load-gate aligned to the regex engine
# --------------------------------------------------------------------------- #


def test_redos_gate_rejects_operator_regex_under_regex_engine() -> None:
    """An operator-supplied regex catastrophic under the `regex` engine is rejected
    at load (exit-6 → LayoutConfigError), proving the gate probes under `regex`."""
    from scripts.wiki_index.layout_config import (
        LayoutConfigError,
        RefRule,
        _redos_budget_check,
        resolve_layout_config,
    )

    base = resolve_layout_config(Path("/nonexistent-vault-defaults-karpathy"))
    import dataclasses

    cfg = dataclasses.replace(
        base,
        ref_extraction=(RefRule(kind="wikilink", regex=_CATASTROPHIC,
                                target_group=0, transform=None),),
        ref_extraction_operator_supplied=True,
    )
    with pytest.raises(LayoutConfigError):
        _redos_budget_check(cfg)


def test_operator_pattern_regex_only_syntax_loads(tmp_path: Path) -> None:
    """LOW-A: an operator `project_pattern` using a regex-only construct (`\\p{L}`,
    which stdlib `re` rejects with `bad escape`) now loads — both the load-gate AND
    `_validate_path_patterns` compile operator patterns under the `regex` engine
    (the one that runs them). Under the pre-fix code this raised at load."""
    import re as _re

    import regex as _regex

    # sanity: the construct is genuinely re-invalid but regex-valid
    with pytest.raises(_re.error):
        _re.compile(r"\p{L}+")
    _regex.compile(r"\p{L}+")  # no raise

    from scripts.wiki_index.layout_config import resolve_layout_config

    wiki = tmp_path / ".wiki"
    wiki.mkdir()
    (wiki / "layout.yaml").write_text(
        "paths:\n"
        "  - glob: '**/*.md'\n"
        "    project_pattern: '(?P<name>\\p{L}+)'\n"
        "    project_template: '${name}'\n",
        encoding="utf-8",
    )
    cfg = resolve_layout_config(tmp_path)  # must NOT raise
    assert cfg.paths_operator_supplied is True


# --------------------------------------------------------------------------- #
# 017-07 / 017-08 — P-2 single-stat walk
# --------------------------------------------------------------------------- #


def test_iter_pages_populates_mtime(tmp_path: Path) -> None:
    """017-07: iter_pages carries each file's mtime (one stat, reused downstream)."""
    import os

    from scripts.wiki_index.layout_config import iter_pages, resolve_layout_config

    (tmp_path / "_sources").mkdir()
    f = tmp_path / "_sources" / "alpha.md"
    f.write_text("---\ntype: summary\n---\n# A\n", encoding="utf-8")
    cfg = resolve_layout_config(tmp_path)
    pages = iter_pages(tmp_path, cfg)
    assert pages, "no pages discovered"
    dp = next(p for p in pages if p.path == f)
    assert dp.mtime is not None
    assert abs(dp.mtime - os.stat(f).st_mtime) < 1.0


def test_reindex_delta_reuses_walk_mtime_no_double_stat(
    minimal_vault: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-017-4 (P-2): a no-op delta stats each discovered file at most ONCE (the
    discovery walk) — the per-file loop reuses DiscoveredPage.mtime instead of a
    second `path.stat()`. Per-path counting → overhead-independent (works at N=3).

    RE-ARMED for TASK 030 (Sarcasmotron 030-05 HIGH — sanctioned edit): the
    single-pass walk stats via `os.DirEntry.stat()`, INVISIBLE to this
    `pathlib.Path.stat` spy, so the old `<= 1` bound became vacuous (a
    reintroduced `path.stat()` in the delta loop would count 1 and PASS).
    The honest post-030 pin is `== 0` detector-visible `Path.stat` calls on
    discovered files (the walk contributes zero; ANY per-file `path.stat()`
    regression now counts ≥1 and FAILS — strictly stronger than before).
    The walk-side exactly-once guarantee is pinned separately by
    `tests/test_task030_single_pass_walk.py::test_walk_stats_each_file_exactly_once`
    via a DirEntry proxy."""
    import pathlib
    from collections import Counter
    from datetime import datetime

    from scripts.wiki_index.models import Vault
    from scripts.wiki_index.reindex import discover_pages, reindex_delta, reindex_full
    from scripts.wiki_index.sqlite_repository import SQLiteRepository

    r = SQLiteRepository(tmp_path / "g.db")
    r.apply_schema()
    r.register_vault(Vault(vault_id="minimal-test", name="m", root_path=minimal_vault,
                           schema_version="2.0", registered_at=datetime(2026, 5, 26)))
    reindex_full(r, "minimal-test")
    # discover_pages yields (path, slug, project) tuples
    discovered = {str(t[0]) for t in discover_pages(minimal_vault)}
    assert discovered

    counts: Counter[str] = Counter()
    orig_stat = pathlib.Path.stat

    def counting(self: Path, *a: object, **k: object) -> object:
        counts[str(self)] += 1
        return orig_stat(self, *a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(pathlib.Path, "stat", counting)
    result = reindex_delta(r, "minimal-test")
    monkeypatch.undo()
    r.close()

    assert result["touched"] == 0, "expected a genuine no-op delta"
    statted = {p: c for p, c in counts.items() if p in discovered and c > 0}
    assert not statted, (
        f"discovered files hit Path.stat during delta — the walk uses "
        f"DirEntry.stat, so ANY visible call is a reintroduced per-file "
        f"double-stat (P-2 regression): {statted}")


# --------------------------------------------------------------------------- #
# 017-09 — `type:` regex fast-path ≡ PyYAML
# --------------------------------------------------------------------------- #


def _pyyaml_type_oracle(body: str) -> str | None:
    """The pre-TASK-017 always-PyYAML behaviour, as an equivalence oracle."""
    if not body.startswith("---\n"):
        return None
    parts = body.split("---\n", 2)
    if len(parts) < 3:
        return None
    import yaml

    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return None
    if isinstance(fm, dict):
        v = fm.get("type")
        return v if isinstance(v, str) else None
    return None


@pytest.mark.parametrize("fm", [
    "type: concept",                       # bare slug → fast path
    "type: lesson-summary",                # hyphen
    'type: "summary"',                     # double-quoted → fallback
    "type: 'query'",                       # single-quoted → fallback
    "title: T\ntype: source\ntags: [a, b]",  # not first key
    "type: verification  # inline comment",  # inline comment → fallback (not 'x # c')
    "title: only-title",                   # no type → None
    "type: 123",                           # numeric → PyYAML int → None
    "type:",                               # empty → None
    "type: Two Words",                     # space → fallback (full scalar)
    "type:nospace",                        # no space → YAML plain scalar (not mapping) → None
])
def test_extract_type_regex_equals_pyyaml(fm: str) -> None:
    from scripts.wiki_index.sqlite_repository import SQLiteRepository

    body = f"---\n{fm}\n---\nbody text\n"
    assert SQLiteRepository._extract_frontmatter_type(body) == _pyyaml_type_oracle(body)


def test_extract_type_no_frontmatter() -> None:
    from scripts.wiki_index.sqlite_repository import SQLiteRepository

    assert SQLiteRepository._extract_frontmatter_type("plain body, no fm") is None


# NB: a *duplicate* top-level `type:` (invalid YAML) diverges by design — the regex
# fast-path takes the first, PyYAML the last. Out-of-corpus malformed input; not asserted.


def test_builtin_layout_does_not_invoke_regex_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NF2 / AC-017-2: a built-in (operator_supplied=False) extract_refs must touch
    ONLY stdlib `re`, never the `regex` engine — built-ins pay zero overhead."""
    import regex as _regex

    from scripts.wiki_index.layout_config import RefRule
    from scripts.wiki_source.parsing import extract_refs

    calls = {"n": 0}
    orig = _regex.compile

    def spy(*a: object, **k: object) -> object:
        calls["n"] += 1
        return orig(*a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(_regex, "compile", spy)
    rule = RefRule(kind="wiki-link", regex=r"\[\[([^\]|]+)\]\]", target_group=1, transform=None)
    out = extract_refs("see [[Foo]] and [[Bar]]", [rule])  # operator_supplied=False
    assert [t for t, _, _ in out] == ["Foo", "Bar"]
    assert calls["n"] == 0, "built-in layout must not invoke the regex engine"


def test_is_intentional_mapping_layout_aware() -> None:
    """DF-017-1: `check_drift` type-mismatch consults the config-driven layout
    `type_mapping` (not just the 3 hardcoded karpathy mappings), so dev-project
    `known-issue→research` etc. are intentional, not drift — while the marker tag
    still disambiguates raw types that share a db_type (task/plan → brief)."""
    from scripts.wiki_index.sqlite_repository import SQLiteRepository

    f = SQLiteRepository._is_intentional_mapping
    tm = {"known-issue": ("research", "known-issue"),
          "task": ("brief", "task"), "plan": ("brief", "plan")}

    # layout-mapped + marker tag present → NOT drift (the DF-017-1 false positive)
    assert f("known-issue", "research", '{"tags": ["known-issue"]}', tm) is True
    # marker tag missing → still flagged (can't confirm intentional)
    assert f("known-issue", "research", '{"tags": []}', tm) is False
    # same db_type, WRONG marker → genuine raw-type drift still caught
    assert f("task", "brief", '{"tags": ["task"]}', tm) is True
    assert f("task", "brief", '{"tags": ["plan"]}', tm) is False
    # null-marker mapping → db_type match alone suffices
    assert f("raw", "mapped", "{}", {"raw": ("mapped", None)}) is True
    # back-compat: no layout mapping → only the hardcoded karpathy 3 (old behavior)
    assert f("lesson-summary", "summary", '{"tags": ["lesson-summary"]}') is True
    assert f("known-issue", "research", '{"tags": ["known-issue"]}') is False


def test_derive_project_for_path_operator_guarded(tmp_path: Path) -> None:
    """vdd-multi HIGH: `derive_project_for_path` threads operator provenance, so an
    operator `project_pattern` runs under the `regex` engine — NOT unguarded stdlib
    `re`. A regex-only construct (`\\p{L}`) that the load-gate accepts would
    `re.error`-CRASH here pre-fix (only `TimeoutError` was caught)."""
    from scripts.wiki_index.layout_config import derive_project_for_path

    wiki = tmp_path / ".wiki"
    wiki.mkdir()
    (wiki / "layout.yaml").write_text(
        "paths:\n"
        "  - glob: '**/*.md'\n"
        "    project_pattern: '(?P<name>\\p{L}+)'\n"   # regex-only — re.compile would raise
        "    project_template: '${name}'\n",
        encoding="utf-8",
    )
    f = tmp_path / "Идеи.md"
    f.write_text("x", encoding="utf-8")
    proj = derive_project_for_path(f, tmp_path)   # must NOT raise re.error
    assert isinstance(proj, str) and proj


# --------------------------------------------------------------------------- #
# 017-10 / 017-11 — check_drift --mtime-skip (opt-in) vs always-hash (default)
# --------------------------------------------------------------------------- #

_FIXED_MTIME = 1_700_000_000.0  # integer-second → exact stat round-trip


def _drift_repo(minimal_vault: Path, db_path: Path) -> tuple[object, Path]:
    import os
    from datetime import datetime

    from scripts.wiki_index.models import Vault
    from scripts.wiki_index.reindex import reindex_full
    from scripts.wiki_index.sqlite_repository import SQLiteRepository

    target = minimal_vault / "_sources" / "alpha.md"
    os.utime(target, (_FIXED_MTIME, _FIXED_MTIME))  # pin mtime BEFORE indexing
    r = SQLiteRepository(db_path)
    r.apply_schema()
    r.register_vault(Vault(vault_id="minimal-test", name="m", root_path=minimal_vault,
                           schema_version="2.0", registered_at=datetime(2026, 5, 26)))
    reindex_full(r, "minimal-test")        # stores last_modified = fromtimestamp(_FIXED_MTIME)
    return r, target


def test_check_drift_mtime_skip_vs_default(minimal_vault: Path, tmp_path: Path) -> None:
    """D-017-B: --mtime-skip trusts a matching mtime (skips hash → tamper missed);
    the DEFAULT always full-hashes (preserved-mtime tamper IS detected — integrity)."""
    import os

    r, target = _drift_repo(minimal_vault, tmp_path / "g.db")
    # tamper content but RESTORE the exact mtime (a preserved-mtime tamper)
    target.write_text(target.read_text(encoding="utf-8") + "\nTAMPER\n", encoding="utf-8")
    os.utime(target, (_FIXED_MTIME, _FIXED_MTIME))
    key = ("alpha", "_vault_")
    try:
        # opt-in: mtime matches → skip re-hash → tamper NOT detected
        assert key not in r.check_drift("minimal-test", trust_mtime=True).hash_mismatch
        # default: always hash → tamper detected
        assert key in r.check_drift("minimal-test").hash_mismatch
    finally:
        r.close()  # type: ignore[attr-defined]


def test_check_drift_mtime_change_still_hashed(minimal_vault: Path, tmp_path: Path) -> None:
    """--mtime-skip still hashes (and detects) a file whose mtime changed."""
    import os

    r, target = _drift_repo(minimal_vault, tmp_path / "g.db")
    target.write_text(target.read_text(encoding="utf-8") + "\nTAMPER\n", encoding="utf-8")
    os.utime(target, (_FIXED_MTIME + 5000, _FIXED_MTIME + 5000))  # mtime CHANGED
    try:
        assert ("alpha", "_vault_") in r.check_drift(
            "minimal-test", trust_mtime=True).hash_mismatch
    finally:
        r.close()  # type: ignore[attr-defined]


def test_check_drift_mtime_skip_aware_datetime_no_crash(
    minimal_vault: Path, tmp_path: Path
) -> None:
    """The --mtime-skip comparison is crash-proof: an AWARE stored last_modified
    (vs the naive disk mtime) degrades to hashing, never raises TypeError. Locks
    the Phase-3 roast fix (latent today — reindex writes naive — but aware
    datetimes exist elsewhere in the codebase)."""
    r, _ = _drift_repo(minimal_vault, tmp_path / "g.db")
    conn = r._connect()  # type: ignore[attr-defined]
    conn.execute(
        "UPDATE pages SET last_modified = ? WHERE vault_id = ? AND slug = ?",
        ("2023-11-14T22:13:20+00:00", "minimal-test", "alpha"),
    )
    conn.commit()
    try:
        report = r.check_drift("minimal-test", trust_mtime=True)  # must NOT raise
        assert report is not None
    finally:
        r.close()  # type: ignore[attr-defined]
