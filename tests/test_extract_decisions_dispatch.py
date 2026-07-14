"""TASK 063-17 — the config-driven DISPATCH MARKER.

The operator requirement: the rail must be invocable FROM CONFIG, like its sibling
`extract_concepts`.

★ AND DECISION-17 SURVIVES IT. `wiki-sync` / `wiki-import` do NOT call the rail — they
emit a MARKER, and the ORCHESTRATOR runs it as a second step. That is exactly how
`wiki-sync` already delegates to `wiki-import`: the CLIs stay deterministic plumbing on
both sides of the REASON step.

★ THE MARKER IS ABSENT, NOT `false`. A marker that is always present invites an
orchestrator to act on it — `{"enabled": false}` reads, to a model skimming an
envelope, like a thing it could switch on. Omission cannot be misread.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest

import scripts.wiki_skills.wiki_import_article as wia
import scripts.wiki_skills.wiki_sync as wsync
from scripts.wiki_skills._resummarize import Caches


def _vault(root: Path, sync: str | None = None, *, at: str = ".") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "WIKI_SCHEMA.md").write_text(
        "---\nvault_id: test-vault\nlanguage: ru\nlayout: cybos\n---\n",
        encoding="utf-8")
    if sync is not None:
        d = root if at == "." else root / at
        (d / ".wiki").mkdir(parents=True, exist_ok=True)
        (d / ".wiki" / "sync.yaml").write_text(sync, encoding="utf-8")
    return root


def test_marker_is_ABSENT_when_not_configured(tmp_path: Path) -> None:
    """BACK-COMPAT: a vault with no `extract_decisions:` block gets a byte-identical
    envelope. The key is not there at all.

    MUT: always emit the marker ⇒ every existing wiki-import/wiki-sync envelope test
    goes RED — which is the correct, LOUD way to learn you changed a contract.
    """
    v = _vault(tmp_path / "v")
    (v / "note.md").write_text("# n\n", encoding="utf-8")
    assert wia._extract_decisions_marker(v, "note.md") is None


def test_marker_is_OMITTED_not_FALSE(tmp_path: Path) -> None:
    """`enabled: false` ⇒ the key is ABSENT, not `false`. Naming the folders is not
    consenting to auto-dispatch, and a present-but-false marker is an invitation."""
    v = _vault(tmp_path / "v",
               "extract_decisions:\n  enabled: false\n  dirs:\n    risk: Риски\n")
    (v / "note.md").write_text("# n\n", encoding="utf-8")
    assert wia._extract_decisions_marker(v, "note.md") is None


def test_marker_is_PRESENT_when_enabled_and_carries_the_RESOLVED_dirs(
    tmp_path: Path,
) -> None:
    v = _vault(tmp_path / "v",
               "extract_decisions:\n  enabled: true\n  dirs:\n    decision: 'Решения'\n")
    (v / "note.md").write_text("# n\n", encoding="utf-8")
    marker = wia._extract_decisions_marker(v, "note.md")
    assert marker == {
        "tool": "wiki-extract-decisions",
        "source": "note.md",
        "dirs": {"decision": "Решения", "requirement": "requirements",
                 "risk": "risks"},
    }


def test_the_marker_respects_the_PER_ZONE_CASCADE(tmp_path: Path) -> None:
    """★ R-063-3′(d), end-to-end: two zones in ONE vault, two folder grammars, two
    different markers. This is the operator requirement in its literal form — two
    engagements cannot be forced to share a folder vocabulary."""
    v = _vault(tmp_path / "v", "extract_decisions:\n  enabled: true\n")
    for zone, dec in (("Zone A", "decisions"), ("Zone B", "Решения")):
        (v / zone).mkdir()
        (v / zone / ".wiki").mkdir()
        (v / zone / ".wiki" / "sync.yaml").write_text(
            f"extract_decisions:\n  dirs:\n    decision: '{dec}'\n", encoding="utf-8")
        (v / zone / "n.md").write_text("# n\n", encoding="utf-8")

    a = wia._extract_decisions_marker(v, "Zone A/n.md")
    b = wia._extract_decisions_marker(v, "Zone B/n.md")
    assert a is not None and b is not None
    assert (a["dirs"]["decision"], b["dirs"]["decision"]) == ("decisions", "Решения")


def test_sync_delegate_carries_the_marker(tmp_path: Path) -> None:
    """`wiki-sync scan`'s per-entry `delegate` block gains the flag, resolved through
    the SAME cascade `summarize:` uses — one cascade, not a second one that could
    disagree with it."""
    v = _vault(tmp_path / "v", "extract_decisions:\n  enabled: true\n")
    src = inspect.getsource(wsync)
    assert "resolve_extract_decisions(" in src, (
        "wiki-sync must resolve the policy through the SHARED cascade")
    assert '"extract_decisions"] = True' in src.replace("entry[\"delegate\"][", "")


# --------------------------------------------------------------------------- #
# ★ DECISION-17 — the denominator claim, over ALL the LLM-shaped skills
# --------------------------------------------------------------------------- #


def test_NO_LLM_CALL_in_ANY_deterministic_skill() -> None:
    """★ "The CLIs never call an LLM" is a DENOMINATOR CLAIM, so it is asserted over the
    WHOLE population — not just the two modules this bead happened to touch.

    The population is enumerated from CLAUDE.md's Decision-17 clause: the LLM-shaped
    skills are `wiki-query`, `wiki-verify-multi`, `wiki-extract-concepts`, `wiki-sync` —
    and now `wiki-extract-decisions` and `wiki-import`, both of which this bead gave a
    dispatch marker. A gate that checked only the files in this diff would go green
    while a sibling regressed.

    BOTH import forms (the house precedent asserts both): `from anthropic import X`
    slips straight through a gate that greps only `import anthropic`.
    """
    import re

    root = Path(__file__).resolve().parents[1] / "scripts" / "wiki_skills"
    targets = [
        "wiki_query.py", "wiki_verify_multi.py", "wiki_sync.py",
        "wiki_extract_concepts", "wiki_extract_decisions", "wiki_import_article",
    ]
    files: list[Path] = []
    for name in targets:
        path = root / name
        assert path.exists(), f"the Decision-17 population names {name}, which is gone"
        files.extend(sorted(path.rglob("*.py")) if path.is_dir() else [path])
    assert len(files) >= 10, f"the population glob found only {len(files)} files"

    offenders = [
        f.name for f in files
        if re.search(r"^\s*(import anthropic|from anthropic)",
                     f.read_text(encoding="utf-8"), re.MULTILINE)
    ]
    assert offenders == [], (
        f"Decision-17 broken — an LLM-client import reached a deterministic skill: "
        f"{offenders}")
