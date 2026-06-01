"""TASK 012-06 (PW-F) — frontmatter synthesis (H1∥stem title) + glob-type inference.

Karpathy keeps `enabled: false` → a type-less file with no path fallback still
raises UnmappedTypeError (byte-identical). A layout with synthesis enabled +
glob-typed paths indexes frontmatter-less notes, titled from the first H1 (else
the filename stem).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import _synthesize_fm, reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_source.parsing import first_h1


def _register(repo: SQLiteRepository, vault_id: str, root: Path) -> None:
    repo.register_vault(Vault(
        vault_id=vault_id, name=vault_id, root_path=root,
        schema_version="2.0", registered_at=datetime(2026, 5, 26)))


# --------------------------------------------------------------------------- #
# Unit
# --------------------------------------------------------------------------- #


def test_first_h1() -> None:
    assert first_h1("intro\n# My Heading\nmore") == "My Heading"
    assert first_h1("## h2 only\nno h1") is None
    assert first_h1("no heading at all") is None


def test_synthesize_fm_injects_h1_only_when_enabled() -> None:
    body = "# Title From Body\n\ntext"
    assert _synthesize_fm({}, body, {"enabled": True}) == {"title": "Title From Body"}
    assert _synthesize_fm({}, body, {"enabled": False}) == {}          # disabled → no-op
    assert _synthesize_fm({"title": "kept"}, body, {"enabled": True}) == {"title": "kept"}
    assert _synthesize_fm({}, "no h1 here", {"enabled": True}) == {}   # no H1 → no title


# --------------------------------------------------------------------------- #
# Karpathy byte-identity: type-less _sources file (no path fallback) still raises
# --------------------------------------------------------------------------- #


def test_karpathy_typeless_source_skipped(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    (vault / "_sources").mkdir(parents=True)
    (vault / "_sources" / "no-type.md").write_text("just a body, no frontmatter\n", encoding="utf-8")
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    _register(repo, "kv-vault", vault)
    try:
        result = reindex_full(repo, "kv-vault")  # karpathy default (no WIKI_SCHEMA)
        # No type, _sources not in path_type_fallback, synthesis off → UnmappedTypeError → skipped.
        assert result["pages"] == 0
        assert any("no-type.md" in s["path"] for s in result["skipped"])
    finally:
        repo.close()


# --------------------------------------------------------------------------- #
# Synthesis enabled: frontmatter-less notes index with H1∥stem title
# --------------------------------------------------------------------------- #

_OVERRIDE = (
    "schema_version: '2.0'\nlayout: obsidian\nslug_strategy: identity\n"
    "file_extensions: ['.md']\n"
    "frontmatter_synthesis: {enabled: true}\n"
    "type_mapping:\n  note: {db_type: summary, tag: null}\n"
    "paths:\n  - {glob: 'notes/**/*.md', type: note, project: '_notes_'}\n"
)


def _obsidian_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "ov"
    (vault / "notes").mkdir(parents=True)
    (vault / "WIKI_SCHEMA.md").write_text(
        '---\nvault_id: ov-vault\nschema_version: "2.0"\nlanguage: en\n'
        'layout: karpathy\n---\n', encoding="utf-8")
    (vault / ".wiki").mkdir()
    (vault / ".wiki" / "layout.yaml").write_text(_OVERRIDE, encoding="utf-8")
    (vault / "notes" / "has-h1.md").write_text("# My Heading\n\nbody\n", encoding="utf-8")
    (vault / "notes" / "no-h1.md").write_text("just body, no heading\n", encoding="utf-8")
    return vault


def test_frontmatterless_notes_index_with_synthesized_title(tmp_path: Path) -> None:
    vault = _obsidian_vault(tmp_path)
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    _register(repo, "ov-vault", vault)
    try:
        result = reindex_full(repo, "ov-vault")
        assert result["pages"] == 2  # both frontmatter-less notes indexed (glob_type=note)
        rows = {r["slug"]: (r["type"], r["title"]) for r in repo._connect().execute(
            "SELECT slug, type, title FROM pages WHERE vault_id='ov-vault'").fetchall()}
        assert rows["has-h1"] == ("summary", "My Heading")  # title from first H1
        assert rows["no-h1"] == ("summary", "no-h1")        # fallback to filename stem
    finally:
        repo.close()
