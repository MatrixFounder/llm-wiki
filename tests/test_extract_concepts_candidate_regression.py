"""TASK 005-14 — extract-concepts Class A candidate-flag regression guard (R-4.6).

`wiki-extract-concepts apply` writes `is_candidate: true` into Class A
frontmatter; reindex reads it back (005-02). This guards both the pin (audit
grep, mirrors the v3.1 load-bearing-grep pattern) and the round-trip on a page
written in the exact shape `write_concept_page` produces.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository

_SRC = Path(__file__).resolve().parent.parent / "scripts" / "wiki_skills" / "wiki_extract_concepts.py"


def test_write_concept_page_pins_is_candidate() -> None:
    """The Class A pin must stay in write_concept_page (R-4.6 load-bearing)."""
    text = _SRC.read_text(encoding="utf-8")
    assert '"is_candidate": True' in text
    assert '"tags": ["concept", "candidate"]' in text


def test_extract_shaped_candidate_survives_reindex(tmp_path: Path) -> None:
    """A page in the exact frontmatter shape `apply` emits round-trips through
    `wiki-reindex --full` as a candidate (is_candidate=1)."""
    vault = tmp_path / "vault"
    (vault / "_concepts").mkdir(parents=True)
    # Mirror write_concept_page's frontmatter exactly.
    (vault / "_concepts" / "new-concept.md").write_text(
        "---\ntype: concept\nvault_id: test-vault\nslug: new-concept\n"
        "name: New Concept\ndate: 2026-05-29\ntags:\n- concept\n- candidate\n"
        "is_candidate: true\nsource_page: some-source\ntrust_level: medium\n---\n\n"
        "# New Concept\n\nA definition.\n", encoding="utf-8",
    )
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id="test-vault", name="v", root_path=vault,
        schema_version="3.0", registered_at=datetime(2026, 5, 29),
    ))
    reindex_full(repo, "test-vault")
    row = repo._connect().execute(
        "SELECT is_candidate FROM entities WHERE vault_id='test-vault' AND slug='new-concept'"
    ).fetchone()
    repo.close()
    assert row["is_candidate"] == 1
