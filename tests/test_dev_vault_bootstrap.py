"""TASK 012-14/15 (R-X2 Phases A-B) — dev-vault bootstrap + cross-project search.

End-to-end acceptance on fixtures (temp DB): the full bootstrap flow
(`wiki-init --register-existing --layout dev-project` → reindex → search) indexes
a project's docs/, renders the Class-B ledger, and cross-project search spans two
dev-vaults. (The LIVE bootstrap of this repo + a peer repo is an operator step —
see the R-X2 docs — because it needs a committed dev-vault declaration + the
operator's environment.)
"""

from __future__ import annotations

from pathlib import Path

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills.wiki_init import main as init_main


def _dev_vault(root: Path, vault_id: str, *, with_issue: bool = True) -> None:
    """A dev-project vault: WIKI_SCHEMA at the root, content under docs/."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "WIKI_SCHEMA.md").write_text(
        f'---\nvault_id: {vault_id}\nschema_version: "2.0"\nlanguage: en\n'
        f'layout: dev-project\n---\n', encoding="utf-8")
    (root / "adr").mkdir(parents=True)
    (root / "adr" / "adr-002-layering.md").write_text(
        "# ADR-002: Data Layering\n\nThe M-4 contract lives here.\n", encoding="utf-8")
    if with_issue:
        (root / "issues").mkdir(parents=True)
        (root / "issues" / "p-1-perf.md").write_text(
            "---\nid: P-1\ntype: known-issue\nstatus: open\ncategory: performance\n"
            "severity: SEV-1\nopened_at: 2026-01-01\n---\n\n# Perf One\n\nbody\n",
            encoding="utf-8")


def test_phase_a_bootstrap_index_and_search(tmp_path: Path) -> None:
    vault = tmp_path / "obsidian-llm-wiki"
    db = tmp_path / "g.db"
    _dev_vault(vault, "obsidian-llm-wiki")

    # the R-X2.1 CLI bootstrap path: register the existing dev-vault
    rc = init_main(["--register-existing", "--vault", str(vault), "--db-path", str(db)])
    assert rc == 0

    repo = make_repo({"vault_id": "obsidian-llm-wiki", "db_path": str(db)})
    assert isinstance(repo, SQLiteRepository)
    try:
        result = reindex_full(repo, "obsidian-llm-wiki")
        # the ADR + the per-issue page both indexed (tag-route, zero DDL)
        rows = {r["slug"]: r["type"] for r in repo._connect().execute(
            "SELECT slug, type FROM pages WHERE vault_id='obsidian-llm-wiki'").fetchall()}
        assert rows["adr-002-layering"] == "research"
        assert rows["p-1-perf"] == "research"      # known-issue → research + tag
        # Phase-A acceptance: search returns the ADR with a snippet
        hits = repo.search_pages("Layering", vaults=["obsidian-llm-wiki"])
        assert any(h.page.slug == "adr-002-layering" for h in hits)
        # the Class-B ledger was rendered from the per-issue file…
        assert "KNOWN_ISSUES.md" in result["auto_rendered"]
        assert (vault / "KNOWN_ISSUES.md").is_file()
        # …and is NOT itself re-indexed as a page (auto-output implicit-ignore, m1)
        assert "KNOWN_ISSUES" not in rows
    finally:
        repo.close()


def test_phase_b_cross_project_search(tmp_path: Path) -> None:
    db = tmp_path / "g.db"
    a = tmp_path / "obsidian-llm-wiki"
    b = tmp_path / "peer-project"
    _dev_vault(a, "obsidian-llm-wiki", with_issue=False)
    _dev_vault(b, "peer-project", with_issue=False)
    for vid, root in [("obsidian-llm-wiki", a), ("peer-project", b)]:
        assert init_main(["--register-existing", "--vault", str(root), "--db-path", str(db)]) == 0

    repo = make_repo({"vault_id": "obsidian-llm-wiki", "db_path": str(db)})
    assert isinstance(repo, SQLiteRepository)
    try:
        reindex_full(repo, "obsidian-llm-wiki")
        reindex_full(repo, "peer-project")
        # cross-project: "contract" (the M-4 contract, in both ADRs) spans BOTH
        # vaults (a non-hyphenated term — FTS5 parses the hyphen in "M-4" as an
        # operator; query-escaping for bare id-refs is a wiki-search concern).
        hits = repo.search_pages("contract", vaults=["obsidian-llm-wiki", "peer-project"])
        vault_ids = {h.page.vault_id for h in hits}
        assert vault_ids == {"obsidian-llm-wiki", "peer-project"}
    finally:
        repo.close()
