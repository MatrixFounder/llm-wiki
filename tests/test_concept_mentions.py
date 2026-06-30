"""TASK 047 P1 — the derived "Mentions across sources" ledger (an in-page AUTO block).

A concept page carries a `<!-- BEGIN-AUTO:mentions -->## Mentions across sources …
<!-- END-AUTO:mentions -->` block listing the SOURCE pages that reference it
(`ref_type='mentioned'`), regenerated from `page_entity_refs` by `wiki-index-render
--concept-mentions`. LINKS ONLY (no quote/span — not rebuild-stable). The block is Class B:
re-indexing on render keeps `pages.file_hash` in sync (no spurious drift); everything OUTSIDE
the markers is byte-preserved.

R-1 lists all `mentioned` sources, excludes typed-edge backlinks · R-2 idempotent (+1 ref → +1
entry) · R-3 preserve-rest · R-4 renders after confirm (is_candidate:false) · R-9 no drift after
render. Harness builds the post-import DB+disk state directly (hermetic — no LLM).
"""
from __future__ import annotations

import io
import json
import sys
from datetime import date, datetime
from pathlib import Path

import frontmatter
import pytest

from scripts.wiki_index.models import Page, PageRef, Vault
from scripts.wiki_index.rendering import apply_auto_block, render_concept_mentions_body
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills._common import format_concept_mentions_body, wrap_auto_block
from scripts.wiki_skills.wiki_index_render import main as render_main

_VAULT = "cm-test"


def _schema_md() -> str:
    return "---\nvault_id: cm-test\nlayout: obsidian-personal\nlanguage: en\n---\n"


@pytest.fixture
def vault(tmp_path):
    """A registered vault with WIKI_SCHEMA.md (so the render's re-index step resolves a layout)."""
    root = tmp_path / "vault"
    (root / "_concepts").mkdir(parents=True)
    (root / "_sources").mkdir(parents=True)
    (root / "WIKI_SCHEMA.md").write_text(_schema_md(), encoding="utf-8")
    db = tmp_path / "g.db"
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(vault_id=_VAULT, name=_VAULT, root_path=root,
                             schema_version="7.0", registered_at=datetime(2026, 7, 1)))
    repo.close()
    return root, db


def _write_concept(root: Path, slug: str, *, seeded_source: str | None = None,
                   extra_body: str = "", is_candidate: bool = True) -> None:
    """Write a concept page on disk like `write_concept_page` does (seeded AUTO block + extras)."""
    block = wrap_auto_block(
        "mentions", format_concept_mentions_body([seeded_source] if seeded_source else []))
    body = f"# {slug.title()}\n\nA definition of {slug}.\n\n{block}\n{extra_body}"
    post = frontmatter.Post(body, **{
        "type": "concept", "vault_id": _VAULT, "slug": slug, "name": slug.title(),
        "date": "2026-07-01", "tags": ["concept", "candidate"],
        "is_candidate": is_candidate, "source_page": seeded_source or "", "trust_level": "medium"})
    (root / "_concepts" / f"{slug}.md").write_text(frontmatter.dumps(post), encoding="utf-8")


def _write_source(root: Path, slug: str, mentions: list[str]) -> None:
    """A source summary note whose `## Entities` footer wiki-links the mentioned concepts."""
    footer = "\n".join(f"- [[{m}]]" for m in mentions)
    body = (f"---\ntype: meeting-summary\nvault_id: {_VAULT}\nslug: {slug}\n"
            f"title: {slug.title()}\ndate: 2026-07-01\ntags: [meeting-summary]\n---\n"
            f"# {slug.title()}\n\nBody discussing things.\n\n## Entities\n\n{footer}\n")
    (root / "_sources" / f"{slug}.md").write_text(body, encoding="utf-8")


def _index_dir(root: Path, db: Path, subdir: str) -> None:
    """Index every `.md` under <root>/<subdir> via the real single-file upsert path (so the
    `## Entities` footer links become real `ref_type='mentioned'` page_entity_refs)."""
    from scripts.wiki_skills.wiki_index_upsert import upsert_one
    repo = SQLiteRepository(db)
    try:
        for md in sorted((root / subdir).glob("*.md")):
            upsert_one(_VAULT, md, root, repo)
    finally:
        repo.close()


def _render(db: Path, root: Path) -> dict:
    buf, old = io.StringIO(), sys.stdout
    sys.stdout = buf
    try:
        code = render_main(["--vault", _VAULT, "--vault-root", str(root),
                            "--db-path", str(db), "--concept-mentions"])
    finally:
        sys.stdout = old
    out = json.loads(buf.getvalue())
    assert code == 0, out
    return out


def _block_of(root: Path, slug: str) -> str:
    md = (root / "_concepts" / f"{slug}.md").read_text(encoding="utf-8")
    import re
    m = re.search(r"<!--\s*BEGIN-AUTO:mentions\s*-->.*?<!--\s*END-AUTO:mentions\s*-->", md, re.DOTALL)
    assert m, f"no AUTO block in {slug}.md:\n{md}"
    return m.group(0)


# --- R-1: lists all mentioned sources; excludes typed-edge backlinks --------

def test_concept_mentions_lists_all_sources(vault):
    root, db = vault
    _write_concept(root, "defi", seeded_source="src-a")
    _write_source(root, "src-a", ["defi"])
    _write_source(root, "src-b", ["defi"])
    _index_dir(root, db, "_concepts")
    _index_dir(root, db, "_sources")
    _render(db, root)
    block = _block_of(root, "defi")
    assert "- [[src-a]]" in block and "- [[src-b]]" in block
    assert block.index("- [[src-a]]") < block.index("- [[src-b]]")   # sorted
    assert "## Mentions across sources" in block


def test_concept_mentions_excludes_typed_edges(vault):
    root, db = vault
    _write_concept(root, "defi", seeded_source="src-a")
    _write_source(root, "src-a", ["defi"])
    _index_dir(root, db, "_concepts")
    _index_dir(root, db, "_sources")
    # a typed-edge inbound ref (NOT 'mentioned') from another page must NOT appear
    repo = SQLiteRepository(db)
    repo.upsert_page(Page(vault_id=_VAULT, slug="risk-x", project="_vault_", type="summary",
                          title="Risk X", file_path="_sources/risk-x.md", date=date(2026, 7, 1),
                          last_modified=datetime(2026, 7, 1), file_hash="rx",
                          frontmatter_json={"tags": []}, body_excerpt="x", tags=[]))
    repo.upsert_refs([PageRef(vault_id=_VAULT, page_slug="risk-x", page_project="_vault_",
                              entity_slug="defi", ref_type="caused-by", trust_level="medium")])
    repo.close()
    _render(db, root)
    block = _block_of(root, "defi")
    assert "- [[src-a]]" in block
    assert "risk-x" not in block               # typed-edge (caused-by) excluded — mentioned-only


# --- R-2: idempotent; +1 ref → +1 entry -------------------------------------

def test_concept_mentions_render_idempotent(vault):
    root, db = vault
    _write_concept(root, "defi", seeded_source="src-a")
    _write_source(root, "src-a", ["defi"])
    _index_dir(root, db, "_concepts")
    _index_dir(root, db, "_sources")
    out1 = _render(db, root)
    snap = (root / "_concepts" / "defi.md").read_text(encoding="utf-8")
    out2 = _render(db, root)                     # no new refs
    assert out2["updated"] == []                 # nothing rewritten
    assert (root / "_concepts" / "defi.md").read_text(encoding="utf-8") == snap   # byte-identical
    # add a 2nd source → +1 entry on the next render
    _write_source(root, "src-b", ["defi"])
    _index_dir(root, db, "_sources")
    _render(db, root)
    block = _block_of(root, "defi")
    assert block.count("- [[") == 2
    assert "<!-- GENERATED-AT:" not in block      # no volatile stamp (would break byte-identity)


# --- R-3: preserve-rest (only the AUTO region changes) ----------------------

def test_concept_mentions_preserves_rest(vault):
    root, db = vault
    custom = "\n<!-- BEGIN-CUSTOM:notes -->\nOperator note: keep me.\n<!-- END-CUSTOM:notes -->\n"
    _write_concept(root, "defi", seeded_source="src-a",
                   extra_body="\nA hand-written paragraph the operator added.\n" + custom)
    _write_source(root, "src-a", ["defi"])
    _write_source(root, "src-b", ["defi"])
    _index_dir(root, db, "_concepts")
    _index_dir(root, db, "_sources")
    before = (root / "_concepts" / "defi.md").read_text(encoding="utf-8")
    _render(db, root)
    after = (root / "_concepts" / "defi.md").read_text(encoding="utf-8")
    # everything OUTSIDE the AUTO block is byte-preserved
    import re
    rx = re.compile(r"<!--\s*BEGIN-AUTO:mentions\s*-->.*?<!--\s*END-AUTO:mentions\s*-->", re.DOTALL)
    assert rx.sub("X", before) == rx.sub("X", after)
    assert "A hand-written paragraph the operator added." in after
    assert "<!-- BEGIN-CUSTOM:notes -->" in after and "Operator note: keep me." in after
    assert "- [[src-b]]" in _block_of(root, "defi")    # the block DID update


# --- R-4: renders after confirm (is_candidate:false) ------------------------

def test_concept_mentions_renders_after_confirm(vault):
    root, db = vault
    _write_concept(root, "defi", seeded_source="src-a", is_candidate=False)  # confirmed
    _write_source(root, "src-a", ["defi"])
    _write_source(root, "src-b", ["defi"])
    _index_dir(root, db, "_concepts")
    _index_dir(root, db, "_sources")
    _render(db, root)
    block = _block_of(root, "defi")
    assert "- [[src-a]]" in block and "- [[src-b]]" in block   # confirm is a lifecycle flag, not ownership


# --- R-9: no hash-mismatch drift after render -------------------------------

def test_concept_mentions_no_drift_after_render(vault):
    root, db = vault
    _write_concept(root, "defi", seeded_source="src-a")
    _write_source(root, "src-a", ["defi"])
    _write_source(root, "src-b", ["defi"])
    _index_dir(root, db, "_concepts")
    _index_dir(root, db, "_sources")
    _render(db, root)
    # The render rewrote defi.md (added src-b) AND re-indexed it. So a FRESH single-file index
    # of the same on-disk page must see NO change → `unchanged`. If the render forgot to
    # re-index, the DB file_hash would be stale and this would come back `updated` (drift).
    from scripts.wiki_skills.wiki_index_upsert import upsert_one
    repo = SQLiteRepository(db)
    try:
        res = upsert_one(_VAULT, root / "_concepts" / "defi.md", root, repo)
    finally:
        repo.close()
    assert res["action"] == "unchanged", res


def test_apply_auto_block_inserts_when_absent():
    # a pre-047 page (no AUTO markers) → the block is appended, body preserved.
    md = "# Defi\n\nDefinition.\n"
    out = apply_auto_block(md, "mentions", format_concept_mentions_body(["s1"]))
    assert out.startswith("# Defi\n\nDefinition.\n")
    assert "<!-- BEGIN-AUTO:mentions -->" in out and "- [[s1]]" in out


def test_apply_auto_block_absent_inserts_before_custom_island():
    # roast L2: a pre-047 page that ALREADY carries an operator BEGIN-CUSTOM island → the derived
    # AUTO block is spliced BEFORE the custom prose (Class-B above operator-owned), not at EOF.
    md = ("# Defi\n\nDefinition.\n\n"
          "<!-- BEGIN-CUSTOM:notes -->\noperator prose, keep verbatim\n<!-- END-CUSTOM:notes -->\n")
    out = apply_auto_block(md, "mentions", format_concept_mentions_body(["s1"]))
    assert out.index("<!-- BEGIN-AUTO:mentions -->") < out.index("<!-- BEGIN-CUSTOM:notes -->")
    assert "operator prose, keep verbatim" in out
    # name-anchored (roast L1): the AUTO replace targets `mentions` only — a different-named AUTO
    # block earlier in the doc is NOT clobbered.
    md2 = ("<!-- BEGIN-AUTO:other -->\nX\n<!-- END-AUTO:other -->\n"
           "<!-- BEGIN-AUTO:mentions -->\n## Mentions across sources\n\n- [[old]]\n<!-- END-AUTO:mentions -->\n")
    out2 = apply_auto_block(md2, "mentions", format_concept_mentions_body(["new"]))
    assert "<!-- BEGIN-AUTO:other -->\nX\n<!-- END-AUTO:other -->" in out2   # untouched
    assert "- [[new]]" in out2 and "- [[old]]" not in out2


def test_mentioning_source_pages_excludes_derived_pages(vault):
    # roast L4: the ledger lists CONTENT sources (summary/brief/research), not the derived
    # index/query/verification pages — even when those carry a `mentioned` ref to the concept.
    root, db = vault
    repo = SQLiteRepository(db)
    for slug, typ in [("src-a", "summary"), ("brief-1", "brief"),
                      ("q-1", "query"), ("v-1", "verification")]:
        repo.upsert_page(Page(vault_id=_VAULT, slug=slug, project="_vault_", type=typ,
                              title=slug, file_path=f"_x/{slug}.md", date=date(2026, 7, 1),
                              last_modified=datetime(2026, 7, 1), file_hash=slug,
                              frontmatter_json={"tags": []}, body_excerpt="x", tags=[]))
        repo.upsert_refs([PageRef(vault_id=_VAULT, page_slug=slug, page_project="_vault_",
                                  entity_slug="defi", ref_type="mentioned", trust_level="high")])
    got = repo.mentioning_source_pages(_VAULT, "defi")
    repo.close()
    assert got == ["brief-1", "src-a"]      # summary + brief kept; query + verification excluded
