"""TASK 036 / R-15 — shared fixture for derived-knowledge-health tests
(lifecycle-drift + coverage). A cybos vault exercising EVERY drift/coverage rule
shipped in layouts/cybos.yaml, plus the NON-drift / NON-gap controls.

Drift (4 expected): dec-stale (forward-authored superseded-by), dec-old2 (INVERSE
superseded-by derived from dec-new's `supersedes`), dec-voided (invalidated-by +
still-live status), wf-stale (workflow superseded-by). Controls (never drift):
dec-new, dec-correct (status superseded), dec-nostatus (NULL status), dec-voided-ok
(terminal `rejected`), dec-plain (no edge), wf-new.

Coverage (4 expected): req-uncovered + cap-orphan (no implemented-by), fact-nosrc
(empty source) + fact-missing (absent source). Controls (never a gap): req-covered
(forward implemented-by), fact-withsrc.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository

_FILES = {
    # --- drift: decisions ---
    "decisions/dec-stale.md": "---\ntype: decision\ntitle: Dec Stale\nstatus: accepted\nsuperseded_by: [[dec-new]]\n---\nbody\n",
    "decisions/dec-new.md": "---\ntype: decision\ntitle: Dec New\nstatus: accepted\nsupersedes: [[dec-old2]]\n---\nbody\n",
    "decisions/dec-old2.md": "---\ntype: decision\ntitle: Dec Old2\nstatus: accepted\n---\nbody\n",
    "decisions/dec-correct.md": "---\ntype: decision\ntitle: Dec Correct\nstatus: superseded\nsuperseded_by: [[dec-new]]\n---\nbody\n",
    "decisions/dec-nostatus.md": "---\ntype: decision\ntitle: Dec NoStatus\nsuperseded_by: [[dec-new]]\n---\nbody\n",
    "decisions/dec-voided.md": "---\ntype: decision\ntitle: Dec Voided\nstatus: accepted\ninvalidated_by: [[inc-1]]\n---\nbody\n",
    "decisions/dec-voided-ok.md": "---\ntype: decision\ntitle: Dec Voided OK\nstatus: rejected\ninvalidated_by: [[inc-1]]\n---\nbody\n",
    "decisions/dec-plain.md": "---\ntype: decision\ntitle: Dec Plain\nstatus: accepted\n---\nbody\n",
    "incidents/inc-1.md": "---\ntype: incident\ntitle: Inc 1\nstatus: resolved\n---\nbody\n",
    # --- drift: workflows ---
    "workflows/wf-stale.md": "---\ntype: workflow\ntitle: WF Stale\nstatus: active\nsuperseded_by: [[wf-new]]\n---\nbody\n",
    "workflows/wf-new.md": "---\ntype: workflow\ntitle: WF New\nstatus: active\n---\nbody\n",
    # --- coverage: requirements / capabilities / facts ---
    "requirements/req-uncovered.md": "---\ntype: requirement\ntitle: Req Uncovered\nstatus: draft\n---\nbody\n",
    "requirements/req-covered.md": "---\ntype: requirement\ntitle: Req Covered\nstatus: draft\nimplemented_by: [[dec-new]]\n---\nbody\n",
    "capabilities/cap-orphan.md": "---\ntype: capability\ntitle: Cap Orphan\nstatus: active\n---\nbody\n",
    "facts/fact-nosrc.md": "---\ntype: fact\ntitle: Fact NoSrc\nsource: \"\"\n---\nbody\n",
    "facts/fact-withsrc.md": "---\ntype: fact\ntitle: Fact WithSrc\nsource: \"https://example.com\"\n---\nbody\n",
    "facts/fact-missing.md": "---\ntype: fact\ntitle: Fact Missing\n---\nbody\n",
}


def build_health_vault(tmp_path: Path) -> tuple[SQLiteRepository, Path]:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "WIKI_SCHEMA.md").write_text(
        '---\nvault_id: hvault\nschema_version: "2.0"\nlanguage: en\nlayout: cybos\n---\n',
        encoding="utf-8")
    for rel, content in _FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    repo = SQLiteRepository(tmp_path / "h.db")
    repo.apply_schema()
    repo.register_vault(Vault(vault_id="hvault", name="hvault", root_path=root,
                              schema_version="2.0", registered_at=datetime(2026, 6, 16)))
    assert reindex_full(repo, "hvault")["skipped"] == []
    return repo, root


def build_cybos_vault(
    tmp_path: Path, files: dict[str, str], *, vault_id: str = "mini",
) -> tuple[SQLiteRepository, Path]:
    """Build + reindex an arbitrary cybos vault from ``{rel_path: content}`` — for
    focused edge-case tests that must not perturb the shared `build_health_vault`
    counts. DB lives at ``tmp_path/<vault_id>.db``."""
    root = tmp_path / vault_id
    root.mkdir()
    (root / "WIKI_SCHEMA.md").write_text(
        f'---\nvault_id: {vault_id}\nschema_version: "2.0"\nlanguage: en\nlayout: cybos\n---\n',
        encoding="utf-8")
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    repo = SQLiteRepository(tmp_path / f"{vault_id}.db")
    repo.apply_schema()
    repo.register_vault(Vault(vault_id=vault_id, name=vault_id, root_path=root,
                              schema_version="2.0", registered_at=datetime(2026, 6, 16)))
    assert reindex_full(repo, vault_id)["skipped"] == []
    return repo, root
