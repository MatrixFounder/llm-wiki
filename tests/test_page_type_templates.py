"""TASK 031 / R-031-4 — per-type page templates are valid; TASK 034 — refreshed to
type-appropriate, LIVE event-graph edges (the original "reserved-but-inert Phase-1
block" is superseded: edges ship since TASK 032, and each template now carries only the
edges natural to its class). Invariants checked here:
  * the template's `type:` matches the file and is a cybos-mapped raw type,
  * every frontmatter key that is an event-graph edge is a VALID authorable key
    (in `reindex._EDGE_KEY_TO_REF_TYPE`) — no typos / dead keys,
  * every template carries the universal `relates_to` edge.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest

from scripts.wiki_index.layout_config import load_layout_config
from scripts.wiki_index.reindex import _EDGE_KEY_TO_REF_TYPE

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "page-types"
# 7 knowledge classes (TASK 031) + 6 agent-memory classes (TASK 034)
_KNOWLEDGE = ["decision", "requirement", "risk", "incident", "hypothesis", "fact", "event"]
_AGENT_MEMORY = ["agent", "tool", "workflow", "capability", "execution", "pattern"]
_TYPES = _KNOWLEDGE + _AGENT_MEMORY
_AUTHORABLE_EDGES = set(_EDGE_KEY_TO_REF_TYPE)


@pytest.mark.parametrize("name", _TYPES)
def test_page_type_template_valid(tmp_path: Path, name: str) -> None:
    path = _TEMPLATES_DIR / f"{name}.md"
    assert path.is_file(), f"missing template {path}"
    post = frontmatter.loads(path.read_text(encoding="utf-8"))
    # the template's `type:` matches the file and is a cybos-mapped raw type
    assert post["type"] == name
    cfg = load_layout_config(tmp_path, {"layout": "cybos"})
    assert name in cfg.type_mapping, f"{name} not in cybos type_mapping"
    # every edge key the template authors must be a REAL authorable edge (no typos/dead keys)
    edge_keys = {k for k in post.keys() if k in _AUTHORABLE_EDGES}
    bogus = {k for k in post.keys()
             if (k.endswith(("_by", "_to")) or k in {"uses", "owns", "implements",
                 "supersedes", "causes", "invalidates", "activates"})
             and k not in _AUTHORABLE_EDGES}
    assert not bogus, f"{name} template has non-authorable edge keys: {bogus}"
    # the universal symmetric edge is always offered
    assert "relates_to" in post.keys(), f"{name} template missing relates_to"
    assert edge_keys, f"{name} template authors no event-graph edges"


def test_all_templates_exist() -> None:
    found = {p.stem for p in _TEMPLATES_DIR.glob("*.md")}
    assert set(_TYPES) <= found, f"missing templates: {set(_TYPES) - found}"
    assert len(found) == len(_TYPES), f"unexpected extra templates: {found - set(_TYPES)}"
