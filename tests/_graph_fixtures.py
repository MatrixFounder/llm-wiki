"""TASK 032 — ONE shared event-graph fixture (plan-review 🟡-2), reused by the
DAL (032-03), wiki-graph CLI (032-04), and graph-RAG (032-05) tests.

A cybos vault with a supersession chain (dec-2→dec-1→dec-0), implements/caused-by
edges around dec-1, an orphan-target edge (dec-3→ghost), and a relates_to CYCLE
(f1↔f2). After reindex_full the inverse rows are derived for real targets only.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository

_FILES = {
    "requirements/req-1.md": "---\ntype: requirement\ntitle: Req 1\n---\nbody\n",
    "decisions/dec-0.md": "---\ntype: decision\ntitle: Dec 0\n---\nbody\n",
    "decisions/dec-1.md": "---\ntype: decision\ntitle: Dec 1\nimplements: [[req-1]]\nsupersedes: [[dec-0]]\n---\nbody\n",
    "decisions/dec-2.md": "---\ntype: decision\ntitle: Dec 2\nsupersedes: [[dec-1]]\n---\nbody\n",
    "tasks/task-1.md": "---\ntype: task\ntitle: Task 1\nimplements: [[dec-1]]\n---\nbody\n",
    "incidents/inc-1.md": "---\ntype: incident\ntitle: Inc 1\ncaused_by: [[dec-1]]\n---\nbody\n",
    "decisions/dec-3.md": "---\ntype: decision\ntitle: Dec 3\nimplements: [[ghost]]\n---\nbody\n",
    "facts/f1.md": "---\ntype: fact\ntitle: F1\nrelates_to: [[f2]]\n---\nbody\n",
    "facts/f2.md": "---\ntype: fact\ntitle: F2\nrelates_to: [[f1]]\n---\nbody\n",
}


def build_graph_vault(tmp_path: Path) -> tuple[SQLiteRepository, Path]:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "WIKI_SCHEMA.md").write_text(
        '---\nvault_id: gvault\nschema_version: "2.0"\nlanguage: en\nlayout: cybos\n---\n',
        encoding="utf-8")
    for rel, content in _FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    repo.register_vault(Vault(vault_id="gvault", name="gvault", root_path=root,
                              schema_version="2.0", registered_at=datetime(2026, 6, 15)))
    assert reindex_full(repo, "gvault")["skipped"] == []
    return repo, root
