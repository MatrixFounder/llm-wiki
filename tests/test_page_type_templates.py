"""TASK 031 / R-031-4 / AC-4.1 — per-type page templates are valid + the reserved
Phase-2 edge keys are present (authored-but-inert)."""

from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest

from scripts.wiki_index.layout_config import load_layout_config

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "page-types"
_TYPES = ["decision", "requirement", "risk", "incident", "hypothesis", "fact", "event"]
_RESERVED = {"implements", "supersedes", "superseded_by", "caused_by", "relates_to"}


@pytest.mark.parametrize("name", _TYPES)
def test_page_type_template_valid(tmp_path: Path, name: str) -> None:
    path = _TEMPLATES_DIR / f"{name}.md"
    assert path.is_file(), f"missing template {path}"
    post = frontmatter.loads(path.read_text(encoding="utf-8"))
    # the template's `type:` matches the file and is a cybos-mapped raw type
    assert post["type"] == name
    cfg = load_layout_config(tmp_path, {"layout": "cybos"})
    assert name in cfg.type_mapping, f"{name} not in cybos type_mapping"
    # reserved Phase-2 edge keys present (authored-but-inert in Phase 1)
    missing = _RESERVED - set(post.keys())
    assert not missing, f"{name} template missing reserved edge keys: {missing}"


def test_all_seven_templates_exist() -> None:
    found = {p.stem for p in _TEMPLATES_DIR.glob("*.md")}
    assert set(_TYPES) <= found, f"missing templates: {set(_TYPES) - found}"
