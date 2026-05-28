"""Integration tests for `wiki-extract-concepts` (TASK 003 v2 / I-7.13).

Exercises the full extraction pipeline end-to-end against a fixture source
page. The Anthropic LLM call is mocked with a deterministic JSON response
(loaded from `tests/fixtures/source_extract/llm-response.json`) so re-runs
are byte-identical.

Scenarios:
  1. First extraction (no prior source_state): manifest contains expected
     concepts; concept pages written; entity rows + refs in DB.
  2. Re-extraction on unchanged body: action="unchanged", exit 0, ZERO LLM
     calls (idempotency short-circuit per UC-09 Scenario A).
  3. --ingest end-to-end: combined {"extraction":..., "index":...} JSON;
     index summary reports upserted concept pages.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Callable
from unittest import mock

import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.repository import IndexRepository
import scripts.wiki_skills.wiki_extract_concepts as wec


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "source_extract"
SOURCE_FIXTURE = FIXTURE_DIR / "source-page.md"
LLM_RESPONSE_FIXTURE = FIXTURE_DIR / "llm-response.json"


# ============================================================================
# Fixtures
# ============================================================================


def _llm_mock_response() -> mock.Mock:
    block = mock.Mock()
    block.text = LLM_RESPONSE_FIXTURE.read_text(encoding="utf-8")
    resp = mock.Mock()
    resp.content = [block]
    return resp


def _setup_vault_and_db(
    tmp_path: Path,
    repo_factory: Callable[[], IndexRepository],
    vault_id: str = "test-vault",
    source_slug: str = "trading-agent-demo",
) -> tuple[Path, str]:
    """Build a registered vault + indexed source page; return (vault_root, db_path)."""
    vault_root = tmp_path / "vault"
    sources_dir = vault_root / "_sources"
    sources_dir.mkdir(parents=True)
    shutil.copy(SOURCE_FIXTURE, sources_dir / f"{source_slug}.md")

    db_path = str(tmp_path / "wiki.db")
    bootstrap = repo_factory()
    bootstrap.apply_schema()  # type: ignore[attr-defined]
    bootstrap.register_vault(Vault(
        vault_id=vault_id, name="Integration test vault",
        root_path=vault_root, schema_version="2.0",
        registered_at=datetime(2026, 5, 27),
    ))
    # Pre-register the source page so page_entity_refs FK succeeds.
    bootstrap._connect().execute(  # type: ignore[attr-defined]
        "INSERT INTO pages(vault_id, slug, project, type, title, file_path, "
        "date, last_modified, file_hash, frontmatter_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (vault_id, source_slug, "_vault_", "summary",
         "Self-Improving Trading Agent on Hermes",
         f"_sources/{source_slug}.md",
         "2026-05-27", "2026-05-27T12:00:00", "abc", "{}"),
    )
    bootstrap._connect().commit()  # type: ignore[attr-defined]
    bootstrap.close()
    # Promote into the explicit --db-path location.
    src_db = list(tmp_path.glob("wiki-*.db"))[0]
    shutil.copy(src_db, db_path)
    return vault_root, db_path


# ============================================================================
# Scenario 1: first extraction
# ============================================================================


@pytest.mark.skip(
    reason="BREAKING CHANGE (003-v3-00): legacy `main([--vault, ...])` no "
           "longer accepted; integration tests rewritten in 003-v3-12 to use "
           "subprocess prepare + apply against canned candidates fixture."
)
def test_integration_first_extraction_writes_concept_pages(
    tmp_path: Path, repo_factory: Callable[[], IndexRepository],
    capsys: pytest.CaptureFixture,
) -> None:
    """End-to-end: fresh extraction produces 3 concept pages + 3 entity rows
    + 3 page_entity_refs rows. Manifest validates against _manifest_consumer."""
    vault_root, db_path = _setup_vault_and_db(tmp_path, repo_factory)
    with mock.patch("anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = _llm_mock_response()
        rc = wec.main([
            "--vault", "test-vault",
            "--vault-root", str(vault_root),
            "--source-page", "trading-agent-demo",
            "--db-path", db_path,
        ])
    assert rc == 0, f"main returned {rc}, captured: {capsys.readouterr().out}"

    # Manifest emitted to stdout
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["vault_id"] == "test-vault"
    assert len(payload["written"]) == 3
    written_slugs = {w["slug"] for w in payload["written"]}
    assert written_slugs == {"hermes-api", "backtesting", "reinforcement-learning"}

    # Concept files on disk
    concepts_dir = vault_root / "_concepts"
    for slug in written_slugs:
        assert (concepts_dir / f"{slug}.md").is_file(), f"missing {slug}.md"

    # Entity rows + refs in DB
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        ent_rows = conn.execute(
            "SELECT slug FROM entities WHERE vault_id=? AND is_candidate=1",
            ("test-vault",),
        ).fetchall()
        assert {r["slug"] for r in ent_rows} == written_slugs

        ref_rows = conn.execute(
            "SELECT entity_slug, trust_level, source_quote, line_start, line_end "
            "FROM page_entity_refs WHERE vault_id=? AND page_slug=?",
            ("test-vault", "trading-agent-demo"),
        ).fetchall()
        assert len(ref_rows) == 3
        for r in ref_rows:
            assert r["trust_level"] == "medium"
            assert r["source_quote"] and len(r["source_quote"].split()) >= 5
            assert r["line_start"] is not None
            assert r["line_end"] is not None
            assert r["line_end"] >= r["line_start"]
    finally:
        conn.close()


# ============================================================================
# Scenario 2: re-extraction on unchanged body (UC-09 Scenario A)
# ============================================================================


@pytest.mark.skip(
    reason="BREAKING CHANGE (003-v3-00): legacy `main([--vault, ...])` no "
           "longer accepted; integration tests rewritten in 003-v3-12 to use "
           "subprocess prepare + apply against canned candidates fixture."
)
def test_integration_reextraction_unchanged_short_circuits(
    tmp_path: Path, repo_factory: Callable[[], IndexRepository],
    capsys: pytest.CaptureFixture,
) -> None:
    """R-39 / UC-09 Scenario A: re-run on unchanged body → action='unchanged',
    exit 0, ZERO LLM API calls (idempotency)."""
    vault_root, db_path = _setup_vault_and_db(tmp_path, repo_factory)
    with mock.patch("anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = _llm_mock_response()
        # First run — should LLM-call once.
        rc1 = wec.main([
            "--vault", "test-vault",
            "--vault-root", str(vault_root),
            "--source-page", "trading-agent-demo",
            "--db-path", db_path,
        ])
        assert rc1 == 0
        first_call_count = MockClient.return_value.messages.create.call_count
        assert first_call_count == 1
        capsys.readouterr()  # drain stdout

        # Second run — same source body — must short-circuit, NO LLM call.
        rc2 = wec.main([
            "--vault", "test-vault",
            "--vault-root", str(vault_root),
            "--source-page", "trading-agent-demo",
            "--db-path", db_path,
        ])
        assert rc2 == 0
        # call_count unchanged from first run → idempotency held
        assert MockClient.return_value.messages.create.call_count == first_call_count

    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "unchanged"
    assert payload["manifest"] is None


# ============================================================================
# Scenario 3: --ingest end-to-end with in-process indexer dispatch
# ============================================================================


@pytest.mark.skip(
    reason="BREAKING CHANGE (003-v3-00): legacy `main([--vault, ...])` no "
           "longer accepted; integration tests rewritten in 003-v3-12 to use "
           "subprocess prepare + apply against canned candidates fixture."
)
def test_integration_with_ingest_flag_emits_combined_payload(
    tmp_path: Path, repo_factory: Callable[[], IndexRepository],
    capsys: pytest.CaptureFixture,
) -> None:
    """--ingest: full Decision-15 path — extraction + in-process
    index_from_manifest. Combined {"extraction":..., "index":...} on stdout."""
    vault_root, db_path = _setup_vault_and_db(tmp_path, repo_factory)
    with mock.patch("anthropic.Anthropic") as MockClient, mock.patch(
        "scripts.wiki_skills.wiki_extract_concepts.dispatch_to_indexer",
        return_value={"upserted": [{"path": "_concepts/hermes-api.md",
                                     "action": "inserted"}],
                       "failed": [], "log_event_id": 42},
    ) as mock_dispatch:
        MockClient.return_value.messages.create.return_value = _llm_mock_response()
        rc = wec.main([
            "--vault", "test-vault",
            "--vault-root", str(vault_root),
            "--source-page", "trading-agent-demo",
            "--db-path", db_path,
            "--ingest",
        ])
    assert rc == 0
    mock_dispatch.assert_called_once()

    payload = json.loads(capsys.readouterr().out)
    assert "extraction" in payload
    assert "index" in payload
    assert payload["extraction"]["status"] == "ok"
    assert payload["index"]["log_event_id"] == 42
