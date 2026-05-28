"""Integration tests for `wiki-extract-concepts` v3.1 — TASK 003 v3.1 / I-V3.7.

Exercises the full prepare → apply round-trip end-to-end against a fixture
source page. The orchestrator-side LLM synthesis step is simulated by
piping a canned candidates JSON array (`tests/fixtures/source_extract/
candidates.json`) into `apply --candidates-stdin`. The subprocess pattern
mirrors operator reality (no in-process import shortcuts).

Scenarios (003-v3-12 rewrite of v2's mock-LLM integration tests):
  1. First extraction: prepare emits source_hash + is_unchanged=false;
     apply writes 3 concept pages + entity rows + refs.
  2. Re-extraction on unchanged body: prepare emits is_unchanged=true so
     the orchestrator short-circuits BEFORE apply (UC-09 v3.1).
  3. Full --ingest: apply + in-process index_from_manifest produces the
     combined `{extraction, index}` envelope.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.repository import IndexRepository


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "source_extract"
SOURCE_FIXTURE = FIXTURE_DIR / "source-page.md"
CANDIDATES_FIXTURE = FIXTURE_DIR / "candidates.json"


# ============================================================================
# Fixtures
# ============================================================================


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


def _run_skill_subprocess(
    *args: str, stdin_payload: bytes | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke `python -m scripts.wiki_skills.wiki_extract_concepts <args>`."""
    return subprocess.run(
        [sys.executable, "-m", "scripts.wiki_skills.wiki_extract_concepts", *args],
        input=stdin_payload,
        capture_output=True,
        check=False,
    )


# ============================================================================
# Scenario 1: first extraction (prepare + apply round-trip)
# ============================================================================


def test_integration_first_extraction(
    tmp_path: Path, repo_factory: Callable[[], IndexRepository],
) -> None:
    """End-to-end: prepare emits source_hash; apply consumes canned
    candidates fixture via stdin and produces 3 concept pages + entity
    rows + 3 page_entity_refs rows."""
    vault_root, db_path = _setup_vault_and_db(tmp_path, repo_factory)

    # Step 1 — prepare
    prep = _run_skill_subprocess(
        "prepare",
        "--vault", "test-vault",
        "--vault-root", str(vault_root),
        "--source-page", "trading-agent-demo",
        "--db-path", db_path,
    )
    assert prep.returncode == 0, (
        f"prepare exit {prep.returncode}; stderr={prep.stderr!r}; "
        f"stdout={prep.stdout!r}"
    )
    prepare_env = json.loads(prep.stdout)
    assert prepare_env["is_unchanged"] is False
    source_hash = prepare_env["source_hash"]
    assert len(source_hash) == 64  # sha256 hex

    # Step 2 — orchestrator "synthesises" candidates (we substitute the fixture)
    candidates_bytes = CANDIDATES_FIXTURE.read_bytes()

    # Step 3 — apply
    app = _run_skill_subprocess(
        "apply",
        "--vault", "test-vault",
        "--vault-root", str(vault_root),
        "--source-page", "trading-agent-demo",
        "--source-hash", source_hash,
        "--db-path", db_path,
        "--candidates-stdin",
        stdin_payload=candidates_bytes,
    )
    assert app.returncode == 0, (
        f"apply exit {app.returncode}; stderr={app.stderr!r}; "
        f"stdout={app.stdout!r}"
    )
    payload = json.loads(app.stdout)
    assert payload["status"] == "ok"
    assert payload["vault_id"] == "test-vault"
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
            # v3.1: quotes are operator-synthesised verbatim substrings of
            # the source body (variable length). The min word-count check
            # from v2 was prompt-shape-specific and no longer applies.
            assert r["source_quote"]
            assert r["line_start"] is not None
            assert r["line_end"] is not None
            assert r["line_end"] >= r["line_start"]
    finally:
        conn.close()


# ============================================================================
# Scenario 2: re-extraction on unchanged body — UC-09 v3.1 short-circuit
# ============================================================================


def test_integration_unchanged_on_rerun(
    tmp_path: Path, repo_factory: Callable[[], IndexRepository],
) -> None:
    """R-39 / UC-09 v3.1: first prepare+apply records the source hash;
    second prepare on the unchanged body emits `is_unchanged=true` so
    the orchestrator short-circuits BEFORE invoking apply."""
    vault_root, db_path = _setup_vault_and_db(tmp_path, repo_factory)
    candidates_bytes = CANDIDATES_FIXTURE.read_bytes()

    # First prepare + apply (must succeed end-to-end to record source_state).
    prep1 = _run_skill_subprocess(
        "prepare",
        "--vault", "test-vault",
        "--vault-root", str(vault_root),
        "--source-page", "trading-agent-demo",
        "--db-path", db_path,
    )
    assert prep1.returncode == 0, (
        f"first prepare exit {prep1.returncode}; stderr={prep1.stderr!r}"
    )
    hash1 = json.loads(prep1.stdout)["source_hash"]

    app1 = _run_skill_subprocess(
        "apply",
        "--vault", "test-vault",
        "--vault-root", str(vault_root),
        "--source-page", "trading-agent-demo",
        "--source-hash", hash1,
        "--db-path", db_path,
        "--candidates-stdin",
        stdin_payload=candidates_bytes,
    )
    assert app1.returncode == 0, (
        f"first apply exit {app1.returncode}; stderr={app1.stderr!r}"
    )

    # Second prepare on the unchanged body — must report is_unchanged.
    prep2 = _run_skill_subprocess(
        "prepare",
        "--vault", "test-vault",
        "--vault-root", str(vault_root),
        "--source-page", "trading-agent-demo",
        "--db-path", db_path,
    )
    assert prep2.returncode == 0
    env2 = json.loads(prep2.stdout)
    assert env2["is_unchanged"] is True, (
        f"UC-09 v3.1 short-circuit broken: prepare did not report "
        f"is_unchanged=true after a successful apply; env={env2!r}"
    )
    assert env2["source_hash"] == hash1


# ============================================================================
# Scenario 3: --ingest end-to-end with in-process indexer dispatch
# ============================================================================


def test_integration_with_ingest(
    tmp_path: Path, repo_factory: Callable[[], IndexRepository],
) -> None:
    """Full Decision-15 path: apply --ingest dispatches manifest to
    `_manifest_consumer.index_from_manifest` in-process; stdout carries
    the combined `{extraction, index}` envelope."""
    vault_root, db_path = _setup_vault_and_db(tmp_path, repo_factory)
    candidates_bytes = CANDIDATES_FIXTURE.read_bytes()

    prep = _run_skill_subprocess(
        "prepare",
        "--vault", "test-vault",
        "--vault-root", str(vault_root),
        "--source-page", "trading-agent-demo",
        "--db-path", db_path,
    )
    assert prep.returncode == 0
    source_hash = json.loads(prep.stdout)["source_hash"]

    app = _run_skill_subprocess(
        "apply",
        "--vault", "test-vault",
        "--vault-root", str(vault_root),
        "--source-page", "trading-agent-demo",
        "--source-hash", source_hash,
        "--db-path", db_path,
        "--candidates-stdin",
        "--ingest",
        stdin_payload=candidates_bytes,
    )
    assert app.returncode == 0, (
        f"apply --ingest exit {app.returncode}; stderr={app.stderr!r}; "
        f"stdout={app.stdout!r}"
    )
    payload = json.loads(app.stdout)
    assert set(payload.keys()) == {"extraction", "index"}, (
        f"--ingest envelope must wrap as {{extraction, index}}; got {payload!r}"
    )
    assert payload["extraction"]["status"] == "ok"
    # The indexer summary should report at least one upserted page; exact
    # shape depends on _manifest_consumer's response contract.
    assert payload["index"].get("failed") in (None, []), (
        f"in-process indexer reported failures: {payload['index']!r}"
    )
