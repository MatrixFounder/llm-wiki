"""End-to-end test harness for Stage 1 stubs (task-001-11).

This file is modified — not deleted — in Stage 2. Each stub-asserting
assertion is replaced with a real-value assertion by the relevant Stage 2
task:
  - TC-E2E-01 wiki-init mode → replaced by task-001-21..23
  - TC-E2E-01 wiki-search query echo → replaced by task-001-28
  - TC-E2E-01 wiki-lint issues → replaced by task-001-29
  - TC-E2E-01 wiki-index-render pages_written → replaced by task-001-26
  - TC-E2E-01 wiki-append-log log_event_id → replaced by task-001-27
  - TC-E2E-01 wiki-index-upsert page_slug → replaced by task-001-25
  - TC-E2E-02 repo NotImplementedError → replaced by tasks 001-15..19
  - TC-E2E-03 manual adapter stub → replaced by task-001-24

When implementing a Stage 2 method, also update the corresponding assertion
here. This file is the Stage 1 → Stage 2 progression contract.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.repository import IndexRepository
from scripts.wiki_source.base import SourceItem
from scripts.wiki_source.manual import ManualSourceAdapter


def _run_skill(module: str, *args: str) -> dict:
    """Invoke a wiki_skills module via subprocess; return parsed JSON output."""
    result = subprocess.run(
        [sys.executable, "-m", f"scripts.wiki_skills.{module}", *args],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, (
        f"{module} exit {result.returncode}; stderr={result.stderr!r}"
    )
    return json.loads(result.stdout)


# =============================================================================
# TC-E2E-01 — All six scaffold CLIs return {"action": "stub", ...}
# =============================================================================


def test_e2e_01_full_pipeline_stub_chain(minimal_vault: Path):
    """Stage 1 contract: every CLI scaffold returns hardcoded stub JSON."""
    vault = str(minimal_vault)

    # 1. wiki-init — IMPLEMENTED in task-001-21..23: register existing vault
    init_out = _run_skill("wiki_init", "--register-existing", "--vault", vault,
                          "--db-path", str(Path(vault).parent / "stage1.db"))
    assert init_out["action"] in ("registered", "already-registered")
    assert init_out["vault_id"] == "minimal-test"

    # 2. wiki-index-upsert — IMPLEMENTED in task-001-25
    db_path = str(Path(vault).parent / "stage1.db")
    upsert_out = _run_skill(
        "wiki_index_upsert", "--vault", "minimal-test",
        "--source", f"{vault}/_sources/alpha.md",
        "--vault-root", vault, "--db-path", db_path,
    )
    assert upsert_out["action"] in ("inserted", "updated", "unchanged")
    assert upsert_out["slug"] == "alpha"

    # 3. wiki-append-log — IMPLEMENTED in task-001-27
    log_out = _run_skill("wiki_append_log", "--vault", "minimal-test",
                        "--event-type", "ingest", "--subject", "Alpha",
                        "--db-path", db_path)
    assert log_out["action"] == "logged"
    assert log_out["event_id"] > 0

    # 4. wiki-search — IMPLEMENTED in task-001-28
    search_out = _run_skill("wiki_search", "example", "--vaults", "minimal-test",
                            "--db-path", db_path)
    assert search_out["action"] == "searched"

    # 5. wiki-lint — IMPLEMENTED in task-001-29
    lint_out = _run_skill("wiki_lint", "--vault", "minimal-test",
                          "--db-path", db_path)
    assert lint_out["action"] == "linted"

    # 6. wiki-index-render — IMPLEMENTED in task-001-26
    render_out = _run_skill("wiki_index_render", "--vault", "minimal-test",
                           "--output", f"{vault}/index.md",
                           "--db-path", db_path)
    assert render_out["action"] == "rendered"

    # 7. wiki-reindex — IMPLEMENTED in task-001-30 (--full)
    reindex_out = _run_skill(
        "wiki_reindex", "--full", "--vault", "minimal-test",
        "--db-path", db_path,
    )
    assert reindex_out["action"] == "reindexed"


# =============================================================================
# TC-E2E-02 — Repository methods raise NotImplementedError with task pointers
# =============================================================================


def test_e2e_02_register_vault_real(repo_factory):
    """task-001-15 IMPLEMENTED: register_vault persists; get_vault returns row."""
    from datetime import datetime

    from scripts.wiki_index.sqlite_repository import SQLiteRepository

    repo = repo_factory()
    assert isinstance(repo, SQLiteRepository)
    repo.apply_schema()
    vault = Vault(
        vault_id="trade-agents",
        name="Trade Agents",
        root_path=Path("/tmp/trade-agents-stage1"),
        schema_version="2.0",
        registered_at=datetime(2026, 5, 26),
    )
    repo.register_vault(vault)
    got = repo.get_vault("trade-agents")
    assert got is not None
    assert got.vault_id == "trade-agents"


def test_e2e_02b_upsert_page_real(repo_factory):
    """task-001-16 IMPLEMENTED: upsert_page persists; get_page returns row."""
    from datetime import datetime

    from scripts.wiki_index.models import Page
    from scripts.wiki_index.sqlite_repository import SQLiteRepository

    repo = repo_factory()
    assert isinstance(repo, SQLiteRepository)
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id="test-vault", name="V", root_path=Path("/tmp/v-stage1"),
        schema_version="2.0", registered_at=datetime(2026, 5, 26),
    ))
    from datetime import date

    page = Page(
        vault_id="test-vault", slug="s", project="_vault_", type="summary",
        title="t", file_path="_sources/s.md", date=date(2026, 5, 26),
        last_modified=datetime(2026, 1, 1), file_hash="h",
        frontmatter_json={}, body_excerpt="", tags=[],
    )
    assert repo.upsert_page(page) == "inserted"
    assert repo.get_page("test-vault", "s", "_vault_") is not None


# =============================================================================
# TC-E2E-03 — Manual adapter returns documented hardcoded SourceOutput
# =============================================================================


def test_e2e_03_manual_adapter_stub(minimal_vault: Path):
    """task-001-24 IMPLEMENTED: real frontmatter parsing + ref extraction.
    Tests detailed in test_source_manual_impl.py."""
    adapter = ManualSourceAdapter()
    item = SourceItem(
        kind="manual",
        source_path=minimal_vault / "_sources" / "alpha.md",
        vault_root=minimal_vault,
        vault_id="minimal-test",
    )
    out = adapter.fetch(item)
    assert out.page_slug == "alpha"
    assert out.trust_level == "high"
    # alpha.md mentions example-concept + dangling-link
    assert len(out.refs) >= 2
