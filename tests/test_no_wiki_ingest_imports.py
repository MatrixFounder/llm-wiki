"""TASK 047 P2 (R-6) — the retired `wiki_ingest` / `wiki-enrich` stay retired.

The vendored `scripts/wiki_ingest/` tree and the `wiki-enrich` bridge were deleted; the concept
compounding they used to own is now a derived Class-B render (TASK 047 P1). This guard fails loudly
if any host code re-imports `scripts.wiki_ingest` or re-adds the `wiki_enrich` module — so the
6.4k-LOC vendored surface + its vendoring policy can never quietly creep back.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
# Runtime code trees (NOT tests — a test may still *name* the retired modules in a comment).
_CODE_DIRS = ("scripts", "bin")
_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+(?:scripts\.)?wiki_ingest[\w.]*\s+import\b"
    r"|import\s+(?:scripts\.)?wiki_ingest\b"
    r"|from\s+scripts\.wiki_skills\.wiki_enrich\s+import\b"
    r"|import\s+scripts\.wiki_skills\.wiki_enrich\b)",
    re.MULTILINE,
)


def _py_files() -> list[Path]:
    out: list[Path] = []
    for d in _CODE_DIRS:
        out += [p for p in (_REPO / d).rglob("*.py") if "__pycache__" not in p.parts]
    return out


def test_no_runtime_wiki_ingest_or_enrich_imports() -> None:
    offenders = [str(p.relative_to(_REPO)) for p in _py_files()
                 if _IMPORT_RE.search(p.read_text(encoding="utf-8"))]
    assert not offenders, (
        "TASK 047 retired wiki_ingest + wiki-enrich; these files import them again: "
        + ", ".join(offenders))


def test_vendored_tree_and_enrich_module_absent() -> None:
    assert not (_REPO / "scripts" / "wiki_ingest").exists(), "scripts/wiki_ingest/ must be gone"
    assert not (_REPO / "scripts" / "wiki_skills" / "wiki_enrich.py").exists(), \
        "scripts/wiki_skills/wiki_enrich.py must be gone"
    for retired in ("bin/wiki-enrich", "skills/wiki-enrich", "workflows/wiki-enrich.md",
                    "commands/wiki-enrich.md", "scripts/sync_wiki_ingest.sh",
                    ".claude/skills/wiki-enrich", ".claude/commands/wiki-enrich.md",
                    ".agent/skills/wiki-enrich", ".agent/workflows/wiki-enrich.md"):
        p = _REPO / retired
        # `exists()` follows a symlink → False for a dangling mirror link (target deleted);
        # also assert it isn't even a lingering (broken) symlink entry.
        assert not p.exists() and not p.is_symlink(), f"{retired} must be gone (no orphan mirror)"


@pytest.mark.parametrize("cli", ["wiki-import", "wiki-sync", "wiki-extract-concepts",
                                 "wiki-search", "wiki-index-upsert"])
def test_surviving_clis_still_present(cli: str) -> None:
    # sanity: retiring wiki-enrich didn't take a live CLI with it.
    assert (_REPO / "bin" / cli).exists(), f"{cli} must still exist"
