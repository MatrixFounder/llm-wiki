"""TASK 034 / R-1 — `wiki-search --as-of DATE` temporal filter.

"Active as of DATE" is graph-derived (zero required new fields):
  effective_from = COALESCE(authored valid_from, pages.date)
  effective_to   = authored valid_to  ELSE  the date of the earliest page that
                   SUPERSEDES/INVALIDATES it (TASK 032/034 graph)  ELSE +inf
A page is active iff effective_from <= DATE < effective_to. `valid_from`/`valid_to`
survive only as OPTIONAL overrides; a page with neither valid_from nor a `date` is
excluded. Covers DAL semantics (over real reindexed edges) + CLI validation/threading.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills import wiki_search

VAULT_ID = "tvault"

# A temporal vault: a supersession chain, an invalidation, and two override cases.
_FILES = {
    # supersession chain dec-0(01-01) <- dec-1(03-01) <- dec-2(05-01)
    "decisions/dec-0.md": "---\ntype: decision\ntitle: Dec 0\ndate: 2026-01-01\n---\nb\n",
    "decisions/dec-1.md": "---\ntype: decision\ntitle: Dec 1\ndate: 2026-03-01\nsupersedes: [[dec-0]]\n---\nb\n",
    "decisions/dec-2.md": "---\ntype: decision\ntitle: Dec 2\ndate: 2026-05-01\nsupersedes: [[dec-1]]\n---\nb\n",
    # invalidation: dec-x(03-01) invalidated_by inc-1(04-10)
    "decisions/dec-x.md": "---\ntype: decision\ntitle: Dec X\ndate: 2026-03-01\ninvalidated_by: [[inc-1]]\n---\nb\n",
    "incidents/inc-1.md": "---\ntype: incident\ntitle: Inc 1\ndate: 2026-04-10\n---\nb\n",
    # override: future-effective (valid_from in the future, despite an early `date`)
    "decisions/dec-future.md": "---\ntype: decision\ntitle: Dec Future\ndate: 2026-01-01\nvalid_from: 2026-06-01\n---\nb\n",
    # override: known sunset (valid_to, no successor edge)
    "decisions/dec-sunset.md": "---\ntype: decision\ntitle: Dec Sunset\ndate: 2026-01-01\nvalid_to: 2026-04-01\n---\nb\n",
    # override WINS over the graph: explicit valid_to retires it at 02-01 even though
    # its successor dec-vt-succ is dated far in the future (09-01).
    "decisions/dec-vt.md": "---\ntype: decision\ntitle: Dec VT\ndate: 2026-01-01\nvalid_to: 2026-02-01\nsuperseded_by: [[dec-vt-succ]]\n---\nb\n",
    "decisions/dec-vt-succ.md": "---\ntype: decision\ntitle: Dec VT Succ\ndate: 2026-09-01\nsupersedes: [[dec-vt]]\n---\nb\n",
    # a page with NO date and no valid_from → never in an --as-of result
    "facts/f-nodate.md": "---\ntype: fact\ntitle: F NoDate\n---\nb\n",
}


def _build(tmp_path: Path) -> tuple[SQLiteRepository, Path, Path]:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "WIKI_SCHEMA.md").write_text(
        f'---\nvault_id: {VAULT_ID}\nschema_version: "2.0"\nlanguage: en\nlayout: cybos\n---\n',
        encoding="utf-8")
    for rel, content in _FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    db = tmp_path / "g.db"
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(vault_id=VAULT_ID, name=VAULT_ID, root_path=root,
                              schema_version="2.0", registered_at=datetime(2026, 6, 15)))
    assert reindex_full(repo, VAULT_ID)["skipped"] == []
    return repo, root, db


def _active(repo: SQLiteRepository, as_of: str) -> set[str]:
    return {h.page.slug for h in repo.search_pages(None, vaults=[VAULT_ID], as_of=as_of, limit=100)}


@pytest.mark.parametrize("as_of,expected", [
    ("2026-01-15", {"dec-0", "dec-sunset", "dec-vt"}),
    ("2026-02-15", {"dec-0", "dec-sunset"}),
    ("2026-05-15", {"dec-2", "inc-1"}),
    ("2026-09-15", {"dec-2", "inc-1", "dec-future", "dec-vt-succ"}),
])
def test_as_of_active_set(tmp_path: Path, as_of: str, expected: set[str]) -> None:
    repo, _root, _db = _build(tmp_path)
    try:
        assert _active(repo, as_of) == expected
    finally:
        repo.close()


def test_no_date_page_never_matches(tmp_path: Path) -> None:
    repo, _root, _db = _build(tmp_path)
    try:
        for d in ("2026-01-01", "2026-06-01", "2027-01-01"):
            assert "f-nodate" not in _active(repo, d)
    finally:
        repo.close()


def test_supersession_flip_boundary(tmp_path: Path) -> None:
    """Half-open [from, to): on the successor's own date the predecessor is already out."""
    repo, _root, _db = _build(tmp_path)
    try:
        # dec-1 superseded by dec-2 dated 2026-05-01
        assert "dec-1" in _active(repo, "2026-04-30")
        assert "dec-1" not in _active(repo, "2026-05-01")   # boundary: successor takes over
        assert "dec-2" in _active(repo, "2026-05-01")
    finally:
        repo.close()


def test_explicit_valid_to_overrides_graph(tmp_path: Path) -> None:
    """dec-vt has valid_to 02-01 AND a future successor (09-01). The override wins:
    it is retired at 02-01, NOT kept alive until the successor's date."""
    repo, _root, _db = _build(tmp_path)
    try:
        assert "dec-vt" in _active(repo, "2026-01-15")     # within [01-01, 02-01)
        assert "dec-vt" not in _active(repo, "2026-05-15")  # past valid_to, despite succ@09-01
    finally:
        repo.close()


def test_as_of_back_compat_no_temporal_filter(tmp_path: Path) -> None:
    """Without as_of, no temporal filtering: every decision-tagged page is listed."""
    repo, _root, _db = _build(tmp_path)
    try:
        all_dec = {h.page.slug for h in repo.search_pages(
            None, vaults=[VAULT_ID], where_fields=[("tags", "decision")], limit=100)}
        assert all_dec == {"dec-0", "dec-1", "dec-2", "dec-x", "dec-future",
                           "dec-sunset", "dec-vt", "dec-vt-succ"}
    finally:
        repo.close()


def test_as_of_composes_with_fts(tmp_path: Path) -> None:
    """--as-of AND an FTS query: the temporal predicate intersects the BM25 hits."""
    repo, _root, _db = _build(tmp_path)
    try:
        hits = repo.search_pages("Dec", vaults=[VAULT_ID], as_of="2026-05-15", limit=100)
        slugs = {h.page.slug for h in hits}
        assert "dec-2" in slugs and "dec-0" not in slugs and "inc-1" not in slugs
    finally:
        repo.close()


# --------------------------------------------------------------------------- #
# CLI (Delta 1 / R-1a)
# --------------------------------------------------------------------------- #

def test_cli_bad_date_rejected_no_echo(capsys) -> None:
    """A non-ISO --as-of → INVALID_FILTER exit 2, WITHOUT echoing the value (CWE-209/117)."""
    rc = wiki_search.main(["--as-of", "TOTALLY-BOGUS-7777", "--vaults", VAULT_ID])
    out = capsys.readouterr().out
    assert rc == 2
    payload = json.loads(out)
    assert payload["error"] == "INVALID_FILTER"
    assert "TOTALLY-BOGUS-7777" not in out          # value never echoed


def test_cli_as_of_only_is_valid_search(tmp_path: Path, capsys) -> None:
    """--as-of alone (no query / no --where) is a valid search (relaxed guard)."""
    repo, root, db = _build(tmp_path)
    repo.close()
    rc = wiki_search.main(["--as-of", "2026-05-15", "--vaults", VAULT_ID,
                           "--vault-root", str(root), "--db-path", str(db),
                           "--format", "json", "--limit", "100"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    slugs = {h["slug"] for h in payload["hits"]}
    assert slugs == {"dec-2", "inc-1"}


def test_cli_basic_date_form_normalized(tmp_path: Path, capsys) -> None:
    """A valid ISO basic form (e.g. 20260515) is accepted + normalized, not rejected."""
    repo, root, db = _build(tmp_path)
    repo.close()
    rc = wiki_search.main(["--as-of", "20260515", "--vaults", VAULT_ID,
                           "--vault-root", str(root), "--db-path", str(db),
                           "--format", "json", "--limit", "100"])
    out = capsys.readouterr().out
    assert rc == 0
    assert {h["slug"] for h in json.loads(out)["hits"]} == {"dec-2", "inc-1"}


def test_invalidation_boundary(tmp_path: Path) -> None:
    """The invalidated-by walk is half-open too: dec-x (invalidated_by inc-1 @ 04-10)
    is active the day before and out on the invalidation date itself."""
    repo, _root, _db = _build(tmp_path)
    try:
        assert "dec-x" in _active(repo, "2026-04-09")
        assert "dec-x" not in _active(repo, "2026-04-10")   # boundary: inc-1's own date
    finally:
        repo.close()


# --------------------------------------------------------------------------- #
# vdd-multi logic fixes — direct-DB cases the reindex (single-project, bare-date)
# vault cannot reach. MED-1 (cross-project successor ambiguity) + MED-2 (datetime
# override boundary).
# --------------------------------------------------------------------------- #

def _direct_repo(tmp_path: Path) -> SQLiteRepository:
    repo = SQLiteRepository(tmp_path / "d.db")
    repo.apply_schema()
    repo.register_vault(Vault(vault_id=VAULT_ID, name=VAULT_ID, root_path=tmp_path,
                              schema_version="2.0", registered_at=datetime(2026, 6, 15)))
    return repo


def _insert(repo: SQLiteRepository, slug: str, project: str, date: str,
            fm: dict | None = None) -> None:
    repo._connect().execute(
        "INSERT INTO pages (vault_id, slug, project, type, title, file_path, date, "
        "last_modified, file_hash, frontmatter_json) VALUES (?,?,?,'research',?,?,?,"
        "'2026-06-15','h',?)",
        (VAULT_ID, slug, project, slug, f"{project}/{slug}.md", date,
         json.dumps(fm or {})))
    repo._connect().commit()


def _add_ref(repo: SQLiteRepository, slug: str, project: str, target: str, rt: str) -> None:
    repo._connect().execute(
        "INSERT INTO page_entity_refs (vault_id, page_slug, page_project, entity_slug, "
        "ref_type) VALUES (?,?,?,?,?)", (VAULT_ID, slug, project, target, rt))
    repo._connect().commit()


def test_cross_project_ambiguous_successor_does_not_retire(tmp_path: Path) -> None:
    """MED-1: a successor slug that resolves to >1 page (here `succ` in p1 AND p2)
    cannot disambiguate, so it must NOT retire P. The unrelated p2 namesake (dated
    02-01) would wrongly retire `dec` at 05-01; the COUNT=1 guard keeps it active."""
    repo = _direct_repo(tmp_path)
    try:
        _insert(repo, "dec", "p1", "2026-01-01")
        _insert(repo, "succ", "p1", "2026-09-01")     # the real (future) successor
        _insert(repo, "succ", "p2", "2026-02-01")     # unrelated same-slug, in the past
        _add_ref(repo, "dec", "p1", "succ", "superseded-by")
        assert "dec" in _active(repo, "2026-05-01")   # ambiguous → stays active
    finally:
        repo.close()


def test_unique_successor_does_retire(tmp_path: Path) -> None:
    """Control for MED-1: a UNIQUE successor slug DOES retire its predecessor."""
    repo = _direct_repo(tmp_path)
    try:
        _insert(repo, "dec2", "p1", "2026-01-01")
        _insert(repo, "usucc", "p1", "2026-02-01")
        _add_ref(repo, "dec2", "p1", "usucc", "superseded-by")
        assert "dec2" not in _active(repo, "2026-05-01")
        assert "dec2" in _active(repo, "2026-01-15")   # active before the successor's date
    finally:
        repo.close()


def test_datetime_valued_valid_to_keeps_day_boundary(tmp_path: Path) -> None:
    """MED-2: a datetime-valued valid_to (`...T14:30:00`) must retire on its DATE,
    not be kept alive one extra day by the trailing time component sorting after."""
    repo = _direct_repo(tmp_path)
    try:
        _insert(repo, "dt", "_vault_", "2026-01-01",
                fm={"valid_to": "2026-02-01T14:30:00"})
        assert "dt" in _active(repo, "2026-01-15")        # within [01-01, 02-01)
        assert "dt" not in _active(repo, "2026-02-01")    # half-open: out on the date itself
    finally:
        repo.close()
