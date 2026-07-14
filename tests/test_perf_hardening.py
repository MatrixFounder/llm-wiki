"""TASK 015 perf-hardening test suite.

Bead 015-00: smoke import anchor — confirms the module is importable before
any code changes land. Subsequent beads add tests here (RED first, then GREEN).
"""
import argparse
import contextlib
import hashlib
import io
import json
import pytest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import scripts.wiki_skills.wiki_extract_concepts as wec
from scripts.wiki_skills._manifest_consumer import index_from_manifest
from scripts.wiki_skills.wiki_index_upsert import main, upsert_one  # noqa: F401


def _build_manifest(vault_id: str, vault_root: Path,
                    written: list[str]) -> dict[str, Any]:
    return {
        "status": "ok",
        "vault_id": vault_id,
        "vault_root": str(vault_root),
        "source": {"slug": "test-source", "hash": "deadbeef"},
        "written": [
            {"path": p, "action": "created", "kind": "concept", "scope": "vault"}
            for p in written
        ],
        "created": written,
        "touched": [],
        "contradictions": 0,
        "log_event": {
            "event_ts": "2026-05-27T12:00:00",
            "event_type": "ingest",
            "subject": "Perf-hardening test",
            "log_md_byte_offset": 0,
        },
    }


def test_smoke_import() -> None:
    assert callable(main)


def test_upsert_one_returns_envelope(tmp_path: Path) -> None:
    """upsert_one returns a dict with an 'action' key."""
    repo = MagicMock()
    repo.upsert_page.return_value = "created"
    repo.replace_refs.return_value = None
    src = tmp_path / "test.md"
    src.write_text("---\ntitle: Test\ntype: concept\n---\nBody.\n")
    result = upsert_one("test-vault", src, tmp_path, repo)
    assert isinstance(result, dict)
    assert "action" in result


def test_upsert_one_no_argparse(tmp_path: Path) -> None:
    """upsert_one must NOT invoke argparse."""
    repo = MagicMock()
    repo.upsert_page.return_value = "created"
    repo.replace_refs.return_value = None
    src = tmp_path / "test.md"
    src.write_text("---\ntitle: Test\ntype: concept\n---\nBody.\n")
    with patch("scripts.wiki_skills.wiki_index_upsert._build_parser") as mock_p:
        result = upsert_one("test-vault", src, tmp_path, repo)
    mock_p.assert_not_called()
    assert "action" in result


def test_index_from_manifest_single_connection(minimal_vault: Path) -> None:
    """make_repo called exactly once when repo=None (AC-015-1)."""
    manifest = _build_manifest("minimal-test", minimal_vault,
                               ["_sources/alpha.md"])
    mock_repo = MagicMock()
    mock_repo.upsert_page.return_value = "created"
    mock_repo.replace_refs.return_value = None
    mock_repo.append_log_event.return_value = 1
    with patch("scripts.wiki_skills._manifest_consumer.make_repo",
               return_value=mock_repo) as mr:
        index_from_manifest(manifest, "minimal-test", minimal_vault)
    assert mr.call_count == 1


def test_index_from_manifest_caller_owned_repo_not_closed(
    minimal_vault: Path,
) -> None:
    """When repo= is passed, index_from_manifest must NOT open a new repo
    and must NOT close the caller's repo (R-015-2g: caller owns lifecycle)."""
    manifest = _build_manifest("minimal-test", minimal_vault,
                               ["_sources/alpha.md"])
    caller_repo = MagicMock()
    caller_repo.upsert_page.return_value = "created"
    caller_repo.replace_refs.return_value = None
    caller_repo.append_log_event.return_value = 1
    with patch("scripts.wiki_skills._manifest_consumer.make_repo") as mr:
        index_from_manifest(manifest, "minimal-test", minimal_vault,
                            repo=caller_repo)
    mr.assert_not_called()           # no second connection opened
    caller_repo.close.assert_not_called()  # caller's connection left open


def test_dispatch_to_indexer_forwards_repo(minimal_vault: Path) -> None:
    """R-015-2 (CRITICAL vdd-multi finding): dispatch_to_indexer must forward
    the caller-owned repo through to index_from_manifest, so apply --ingest
    reuses ONE connection instead of opening a second.
    """
    sentinel_repo = MagicMock()
    with patch.object(wec, "validate_manifest"), \
         patch.object(wec, "index_from_manifest",
                      return_value={"upserted": [], "failed": [],
                                    "log_event_id": None}) as ifm:
        wec.dispatch_to_indexer({"written": []}, "minimal-test",
                                minimal_vault, None, repo=sentinel_repo)
    # index_from_manifest received the exact repo apply passed down.
    assert ifm.call_args.kwargs.get("repo") is sentinel_repo


# ---------------------------------------------------------------------------
# Helpers for prepare / batch tests (beads 015-04..015-07)
# ---------------------------------------------------------------------------

def _run_prepare_raw(
    vault_root: Path,
    source_page: str,
    db_path: str,
    known_concepts_format: str = "full",
) -> dict[str, Any]:
    """Call wec.prepare() with a direct Namespace; return parsed JSON envelope."""
    ns = argparse.Namespace(
        cmd="prepare",
        vault="minimal-test",
        vault_root=vault_root,
        source_page=source_page,
        db_path=db_path,
        known_concepts_format=known_concepts_format,
    )
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        wec.prepare(ns)
    return json.loads(buf.getvalue())


def _setup_minimal_db(vault_root: Path, tmp_path: Path,
                      entities: list[str] | None = None) -> str:
    """Bootstrap a minimal SQLite DB for minimal-test vault; return db_path."""
    from scripts.wiki_index.models import Vault
    from scripts.wiki_index.sqlite_repository import SQLiteRepository
    db_path = str(tmp_path / "test.db")
    db: Any = SQLiteRepository(tmp_path / "test.db")
    db.apply_schema()  # type: ignore[attr-defined]
    db.register_vault(Vault(
        vault_id="minimal-test",
        name="minimal-test test vault",
        root_path=vault_root,
        schema_version="2.0",
        registered_at=datetime.now(timezone.utc),
    ))
    if entities:
        conn = db._connect()  # type: ignore[attr-defined]
        now = datetime.now(timezone.utc).isoformat()
        for slug in entities:
            conn.execute(
                "INSERT INTO entities(vault_id, slug, type, name, first_seen, "
                "last_updated, file_path) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("minimal-test", slug, "concept", slug.replace("-", " ").title(),
                 now, now, f"_entities/{slug}.md"),
            )
        conn.commit()
    db.close()
    return db_path


# ---------------------------------------------------------------------------
# Bead 015-04: RED test for --known-concepts-format slugs-only
# ---------------------------------------------------------------------------

def test_prepare_slugs_only_format(
    minimal_vault: Path, tmp_path: Path,
) -> None:
    """prepare --known-concepts-format slugs-only emits strings (RED until 015-05)."""
    db_path = _setup_minimal_db(minimal_vault, tmp_path,
                                entities=["test-concept"])
    result = _run_prepare_raw(minimal_vault, "alpha", db_path,
                              known_concepts_format="slugs-only")
    known = result["known_concepts"]
    assert isinstance(known, list)
    assert len(known) >= 1, "need ≥1 entity so the slugs-only check is non-vacuous"
    assert all(isinstance(item, str) for item in known), (
        "slugs-only should emit strings, not dicts"
    )


def test_prepare_full_default(
    minimal_vault: Path, tmp_path: Path,
) -> None:
    """prepare without format flag emits full entity dicts (AC-015-4, backward-compat)."""
    db_path = _setup_minimal_db(minimal_vault, tmp_path,
                                entities=["test-concept"])
    result = _run_prepare_raw(minimal_vault, "alpha", db_path)
    known = result["known_concepts"]
    assert isinstance(known, list)
    if known:
        assert isinstance(known[0], dict)
        assert "slug" in known[0]
        assert "name" in known[0]
        assert "type" in known[0]
        assert "aliases" in known[0]


# ---------------------------------------------------------------------------
# Beads 015-06 / 015-07: prepare --batch
# ---------------------------------------------------------------------------

def _run_prepare_batch(
    vault_root: Path,
    batch_file: str,
    db_path: str,
    known_concepts_format: str = "full",
) -> tuple[int, dict[str, Any]]:
    """Call wec.prepare() in batch mode; return (exit_code, parsed envelope)."""
    ns = argparse.Namespace(
        cmd="prepare",
        vault="minimal-test",
        vault_root=vault_root,
        source_page=None,
        batch=batch_file,
        db_path=db_path,
        known_concepts_format=known_concepts_format,
    )
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = wec.prepare(ns)
    return rc, json.loads(buf.getvalue())


def _write_source(vault_root: Path, slug: str, body: str = "Body.\n") -> None:
    (vault_root / "_sources" / f"{slug}.md").write_text(
        f"---\ntitle: {slug}\ntype: summary\n---\n\n# {slug}\n\n{body}"
    )


def test_prepare_batch_multi_page(
    minimal_vault: Path, tmp_path: Path,
) -> None:
    """prepare --batch over 3 slugs → 3 entries, each with source_slug+source_hash (AC-015-5)."""
    db_path = _setup_minimal_db(minimal_vault, tmp_path,
                                entities=["test-concept"])
    _write_source(minimal_vault, "gamma")  # alpha+beta exist in fixture
    slugs_file = tmp_path / "slugs.json"
    slugs_file.write_text('["alpha", "beta", "gamma"]')
    rc, result = _run_prepare_batch(minimal_vault, str(slugs_file), db_path)
    assert rc == 0
    assert "batch" in result
    assert len(result["batch"]) == 3
    for entry in result["batch"]:
        assert "source_slug" in entry
        assert "source_hash" in entry
        assert "error" not in entry


def test_prepare_batch_partial_failure(
    minimal_vault: Path, tmp_path: Path,
) -> None:
    """2 valid + 1 missing slug → 3 entries (2 ok, 1 error), exit 0 (AC-015-6)."""
    db_path = _setup_minimal_db(minimal_vault, tmp_path,
                                entities=["test-concept"])
    slugs_file = tmp_path / "slugs.json"
    slugs_file.write_text('["alpha", "does-not-exist", "beta"]')
    rc, result = _run_prepare_batch(minimal_vault, str(slugs_file), db_path)
    assert rc == 0, "per-entry failure must NOT abort the batch"
    assert len(result["batch"]) == 3
    errors = [e for e in result["batch"] if "error" in e]
    oks = [e for e in result["batch"] if "error" not in e]
    assert len(oks) == 2 and len(errors) == 1
    assert errors[0]["source_slug"] == "does-not-exist"
    assert errors[0]["error"] == "SOURCE_NOT_FOUND"


def test_prepare_batch_known_concepts_once(
    minimal_vault: Path, tmp_path: Path,
) -> None:
    """known_concepts loaded exactly once for the whole batch (R-015-4f / P-7)."""
    db_path = _setup_minimal_db(minimal_vault, tmp_path,
                                entities=["test-concept"])
    _write_source(minimal_vault, "gamma")
    slugs_file = tmp_path / "slugs.json"
    slugs_file.write_text('["alpha", "beta", "gamma"]')
    real_load = wec.load_known_entities
    with patch.object(wec, "load_known_entities",
                      side_effect=real_load) as lk:
        _run_prepare_batch(minimal_vault, str(slugs_file), db_path)
    assert lk.call_count == 1


def test_prepare_batch_slugs_only(
    minimal_vault: Path, tmp_path: Path,
) -> None:
    """--known-concepts-format slugs-only applies batch-wide (R-015-4f).
    known_concepts is emitted ONCE at the top level, not per entry (P-6)."""
    db_path = _setup_minimal_db(minimal_vault, tmp_path,
                                entities=["test-concept"])
    slugs_file = tmp_path / "slugs.json"
    slugs_file.write_text('["alpha", "beta"]')
    _, result = _run_prepare_batch(minimal_vault, str(slugs_file), db_path,
                                   known_concepts_format="slugs-only")
    # Top-level, once — strings in slugs-only mode.
    known = result["known_concepts"]
    assert all(isinstance(k, str) for k in known)
    assert "missing_concept_files" in result


def test_prepare_batch_known_concepts_hoisted_not_per_entry(
    minimal_vault: Path, tmp_path: Path,
) -> None:
    """P-6/perf: known_concepts + missing_concept_files live ONCE at the batch
    top level; per-entry dicts must NOT re-embed them (O(N·|known|) blowup)."""
    db_path = _setup_minimal_db(minimal_vault, tmp_path,
                                entities=["test-concept"])
    _write_source(minimal_vault, "gamma")
    slugs_file = tmp_path / "slugs.json"
    slugs_file.write_text('["alpha", "beta", "gamma"]')
    _, result = _run_prepare_batch(minimal_vault, str(slugs_file), db_path)
    assert "known_concepts" in result and "missing_concept_files" in result
    for entry in result["batch"]:
        assert "known_concepts" not in entry, "must not re-embed per entry"
        assert "missing_concept_files" not in entry
        # per-entry payload is just the source-specific recon
        assert {"source_slug", "source_hash", "is_unchanged"} <= set(entry)


def test_prepare_batch_malformed_file(
    minimal_vault: Path, tmp_path: Path,
) -> None:
    """A JSON array of non-strings → INVALID_BATCH_FILE, exit 2."""
    db_path = _setup_minimal_db(minimal_vault, tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text("[1, 2, 3]")
    rc, result = _run_prepare_batch(minimal_vault, str(bad), db_path)
    assert rc == 2
    assert result["error"] == "INVALID_BATCH_FILE"


def test_prepare_batch_not_json(
    minimal_vault: Path, tmp_path: Path,
) -> None:
    """Non-JSON batch file → INVALID_BATCH_FILE, exit 2."""
    db_path = _setup_minimal_db(minimal_vault, tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text("not json at all {[")
    rc, result = _run_prepare_batch(minimal_vault, str(bad), db_path)
    assert rc == 2
    assert result["error"] == "INVALID_BATCH_FILE"


# ---------------------------------------------------------------------------
# Beads 015-08 / 015-09: apply --batch-candidates
# ---------------------------------------------------------------------------

# Body + candidate pairing mirrors test_wiki_extract_concepts._APPLY_DEMO_*
# (source_quote is a verbatim substring of the body, on line 4).
_BATCH_BODY = ("---\ntype: summary\n---\n"
               "The Sharpe Ratio measures excess return.\n")

# ★ TASK 064 — THREE fixture bugs, and the third one is the gate catching a REAL defect
# in the fixture rather than the fixture catching a bug in the gate:
#
#   1. `definition: "A test concept."` (15 chars) is below G1's floor of 40.
#   2. `source_span: "L3-L3"` was WRONG — line 3 of `_BATCH_BODY` is the closing `---`;
#      the quote is on line 4. Nobody noticed for two tasks, because nothing checked.
#   3. ★ the slugs were `concept-a` and `concept-b` — which are **0.889 similar**, over
#      G5's 0.88 near-duplicate cutoff. On the BATCH path (where the known-slug set grows
#      in place across entries, exactly so a later entry dedups against an earlier one's
#      new concept) entry B would be refused as a near-duplicate of entry A. That is the
#      gate WORKING: two slugs one character apart are precisely the plural/variant split
#      it exists to stop. The fixture, not the gate, was wrong — `concept-a` was never a
#      concept. Distinct concepts now.
_CONCEPT_FIXTURES = {
    "a": ("sharpe-ratio", "Sharpe Ratio"),
    "b": ("drawdown", "Drawdown"),
    "x": ("volatility", "Volatility"),
}


def _cand(suffix: str) -> dict[str, Any]:
    slug, name = _CONCEPT_FIXTURES[suffix]
    return {
        "slug": slug,
        "name": name,
        "definition": f"{name} is a risk statistic used to compare strategies "
                      f"on a common footing.",
        "source_quote": "The Sharpe Ratio measures excess return.",
        "source_span": "L4-L4",
        "entity_type": "concept",
    }


def _setup_apply_batch_vault(tmp_path: Path) -> tuple[Path, str, str, list[str]]:
    """Real vault + DB with 2 source pages registered. Returns
    (vault_root, db_path, source_hash, slugs)."""
    from scripts.wiki_index.models import Vault
    from scripts.wiki_index.sqlite_repository import SQLiteRepository
    vault_root = tmp_path / "bvault"
    (vault_root / "_sources").mkdir(parents=True)
    (vault_root / "_concepts").mkdir(parents=True)
    src_hash = hashlib.sha256(_BATCH_BODY.encode("utf-8")).hexdigest()
    slugs = ["src-a", "src-b"]
    db_path = str(tmp_path / "b.db")
    db: Any = SQLiteRepository(tmp_path / "b.db")
    db.apply_schema()  # type: ignore[attr-defined]
    db.register_vault(Vault(
        vault_id="batch-test", name="batch test vault", root_path=vault_root,
        schema_version="2.0", registered_at=datetime.now(timezone.utc),
    ))
    conn = db._connect()  # type: ignore[attr-defined]
    for s in slugs:
        (vault_root / "_sources" / f"{s}.md").write_text(
            _BATCH_BODY, encoding="utf-8")
        conn.execute(
            "INSERT INTO pages(vault_id, slug, project, type, title, "
            "file_path, date, last_modified, file_hash, frontmatter_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("batch-test", s, "_vault_", "summary", s,
             f"_sources/{s}.md", "2026-05-28", "2026-05-28T00:00:00",
             "seed", "{}"),
        )
    conn.commit()
    db.close()
    return vault_root, db_path, src_hash, slugs


def _run_apply_batch(
    vault_root: Path, combined_file: str, db_path: str, ingest: bool = False,
) -> tuple[int, dict[str, Any]]:
    ns = argparse.Namespace(
        cmd="apply", vault="batch-test", vault_root=vault_root,
        source_page=None, source_hash=None, db_path=db_path, ingest=ingest,
        orchestrator_id="claude-test",
        candidates_file=None, candidates_stdin=False,
        batch_candidates=Path(combined_file),
    )
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = wec.apply(ns)
    return rc, json.loads(buf.getvalue())


def test_apply_batch_candidates(tmp_path: Path) -> None:
    """apply --batch-candidates over 2 pages → make_repo ONCE, 2 applied
    entries (AC-015-7). Counting wrapper delegates to the real repo so the
    full write path runs."""
    vault_root, db_path, src_hash, slugs = _setup_apply_batch_vault(tmp_path)
    combined = [
        {"source_slug": slugs[0], "source_hash": src_hash,
         "candidates": [_cand("a")]},
        {"source_slug": slugs[1], "source_hash": src_hash,
         "candidates": [_cand("b")]},
    ]
    cf = tmp_path / "combined.json"
    cf.write_text(json.dumps(combined))

    real_make_repo = wec.make_repo
    calls: list[Any] = []

    def counting(cfg: Any) -> Any:
        calls.append(cfg)
        return real_make_repo(cfg)

    with patch.object(wec, "make_repo", side_effect=counting):
        rc, result = _run_apply_batch(vault_root, str(cf), db_path)
    assert rc == 0
    assert len(calls) == 1, "one repo reused across all batch entries"
    assert len(result["batch"]) == 2
    assert all(e.get("action") == "applied" for e in result["batch"]), \
        result["batch"]


def test_apply_batch_with_ingest(tmp_path: Path) -> None:
    """apply --batch-candidates --ingest → make_repo ONCE; index_from_manifest
    called once per entry, each with the shared repo (AC-015-8)."""
    vault_root, db_path, src_hash, slugs = _setup_apply_batch_vault(tmp_path)
    combined = [
        {"source_slug": slugs[0], "source_hash": src_hash,
         "candidates": [_cand("a")]},
        {"source_slug": slugs[1], "source_hash": src_hash,
         "candidates": [_cand("b")]},
    ]
    cf = tmp_path / "combined.json"
    cf.write_text(json.dumps(combined))

    real_make_repo = wec.make_repo
    calls: list[Any] = []
    shared: dict[str, Any] = {}

    def counting(cfg: Any) -> Any:
        calls.append(cfg)
        r = real_make_repo(cfg)
        shared["repo"] = r
        return r

    seen_repos: list[Any] = []

    def fake_ifm(manifest: Any, vault_id: str, vault_root: Path,
                 db_path: Any = None, repo: Any = None) -> dict[str, Any]:
        seen_repos.append(repo)
        return {"upserted": [], "failed": [], "log_event_id": 1}

    with patch.object(wec, "make_repo", side_effect=counting), \
         patch.object(wec, "index_from_manifest", side_effect=fake_ifm):
        rc, result = _run_apply_batch(vault_root, str(cf), db_path, ingest=True)
    assert rc == 0
    assert len(calls) == 1, "AC-015-8: one repo for the whole invocation"
    assert len(seen_repos) == 2, "index_from_manifest once per source entry"
    assert all(r is shared["repo"] for r in seen_repos), \
        "each dispatch reuses the shared repo"


def test_apply_batch_partial_failure(tmp_path: Path) -> None:
    """One entry with a stale hash → that entry errors, the other applies;
    exit 0 (per-entry isolation, R-015-5)."""
    vault_root, db_path, src_hash, slugs = _setup_apply_batch_vault(tmp_path)
    combined = [
        {"source_slug": slugs[0], "source_hash": src_hash,
         "candidates": [_cand("a")]},
        {"source_slug": slugs[1], "source_hash": "f" * 64,  # stale → SOURCE_CHANGED
         "candidates": [_cand("b")]},
    ]
    cf = tmp_path / "combined.json"
    cf.write_text(json.dumps(combined))
    rc, result = _run_apply_batch(vault_root, str(cf), db_path)
    assert rc == 0
    assert len(result["batch"]) == 2
    applied = [e for e in result["batch"] if e.get("action") == "applied"]
    errored = [e for e in result["batch"] if "error" in e]
    assert len(applied) == 1 and len(errored) == 1
    assert errored[0]["error"] == "SOURCE_CHANGED_DURING_EXTRACTION"


def test_apply_batch_invalid_entry_shape(tmp_path: Path) -> None:
    """An entry missing required keys → INVALID_BATCH_ENTRY, batch continues."""
    vault_root, db_path, src_hash, slugs = _setup_apply_batch_vault(tmp_path)
    combined = [
        {"source_slug": slugs[0], "source_hash": src_hash,
         "candidates": [_cand("a")]},
        {"source_slug": slugs[1]},  # missing source_hash + candidates
    ]
    cf = tmp_path / "combined.json"
    cf.write_text(json.dumps(combined))
    rc, result = _run_apply_batch(vault_root, str(cf), db_path)
    assert rc == 0
    bad = [e for e in result["batch"] if e.get("error") == "INVALID_BATCH_ENTRY"]
    assert len(bad) == 1


def test_apply_batch_malformed_file(tmp_path: Path) -> None:
    """Non-list combined.json → INVALID_BATCH_FILE, exit 2."""
    vault_root, db_path, src_hash, slugs = _setup_apply_batch_vault(tmp_path)
    cf = tmp_path / "combined.json"
    cf.write_text('{"not": "a list"}')
    rc, result = _run_apply_batch(vault_root, str(cf), db_path)
    assert rc == 2
    assert result["error"] == "INVALID_BATCH_FILE"


# --- vdd-multi iteration-1 fixes (batch surfaces) ---------------------------

def test_apply_batch_db_error_isolated(tmp_path: Path) -> None:
    """vdd-multi HIGH: a sqlite3.Error on ONE entry must NOT crash the batch —
    it is recorded as that entry's error and the batch still emits."""
    vault_root, db_path, src_hash, slugs = _setup_apply_batch_vault(tmp_path)
    combined = [
        {"source_slug": slugs[0], "source_hash": src_hash,
         "candidates": [_cand("a")]},
        {"source_slug": slugs[1], "source_hash": src_hash,
         "candidates": [_cand("b")]},
    ]
    cf = tmp_path / "combined.json"
    cf.write_text(json.dumps(combined))

    import sqlite3
    real_fn = wec._apply_candidates_to_db
    n = {"calls": 0}

    def flaky(*a: Any, **k: Any) -> dict[str, Any]:
        n["calls"] += 1
        if n["calls"] == 2:
            raise sqlite3.OperationalError("database is locked")
        return real_fn(*a, **k)

    with patch.object(wec, "_apply_candidates_to_db", side_effect=flaky):
        rc, result = _run_apply_batch(vault_root, str(cf), db_path)
    assert rc == 0, "DB fault on one entry must not abort the batch"
    assert len(result["batch"]) == 2
    assert result["batch"][0].get("action") == "applied"
    assert result["batch"][1].get("error") == "OperationalError"


def test_apply_batch_known_loaded_once(tmp_path: Path) -> None:
    """vdd-multi MED: batch apply loads known entities ONCE (not per entry)."""
    vault_root, db_path, src_hash, slugs = _setup_apply_batch_vault(tmp_path)
    combined = [
        {"source_slug": slugs[0], "source_hash": src_hash,
         "candidates": [_cand("a")]},
        {"source_slug": slugs[1], "source_hash": src_hash,
         "candidates": [_cand("b")]},
    ]
    cf = tmp_path / "combined.json"
    cf.write_text(json.dumps(combined))
    real_load = wec.load_known_entities
    with patch.object(wec, "load_known_entities", side_effect=real_load) as lk:
        rc, result = _run_apply_batch(vault_root, str(cf), db_path)
    assert rc == 0
    assert lk.call_count == 1, "known entities must be loaded once per batch"


def test_apply_batch_idempotency_failure_reports_partial(tmp_path: Path) -> None:
    """vdd-multi MED: a failed source_state update → entry 'partial' /
    IDEMPOTENCY_UPDATE_FAILED (parity with single-page), not a false 'applied'."""
    vault_root, db_path, src_hash, slugs = _setup_apply_batch_vault(tmp_path)
    combined = [
        {"source_slug": slugs[0], "source_hash": src_hash,
         "candidates": [_cand("a")]},
    ]
    cf = tmp_path / "combined.json"
    cf.write_text(json.dumps(combined))
    with patch.object(wec, "_try_update_idempotency_state",
                      return_value=False):
        rc, result = _run_apply_batch(vault_root, str(cf), db_path)
    assert rc == 0
    assert result["batch"][0]["action"] == "partial"
    assert result["batch"][0]["error"] == "IDEMPOTENCY_UPDATE_FAILED"


def test_apply_batch_accepts_file_over_1mib(tmp_path: Path) -> None:
    """vdd-multi LOW: a combined.json > 1 MiB (single-page cap) but < 10 MiB
    must be accepted — the batch aggregates many pages."""
    vault_root, db_path, src_hash, slugs = _setup_apply_batch_vault(tmp_path)
    combined = [
        {"source_slug": slugs[0], "source_hash": src_hash,
         "candidates": [_cand("a")],
         # extra ignored key padding the file past the 1 MiB single-page cap
         "_pad": "x" * 1_400_000},
    ]
    cf = tmp_path / "combined.json"
    cf.write_text(json.dumps(combined))
    assert cf.stat().st_size > 1_048_576
    rc, result = _run_apply_batch(vault_root, str(cf), db_path)
    assert rc == 0, "1 MiB < file < 10 MiB must not be rejected for size"
    assert result["batch"][0]["action"] == "applied"


def _setup_unindexed_vault(tmp_path: Path) -> tuple[Path, str, str]:
    """Vault + DB registered, source file on disk, but the source page is NOT
    in `pages` (no reindex) — so a ref write hits the page_entity_refs FK."""
    from scripts.wiki_index.models import Vault
    from scripts.wiki_index.sqlite_repository import SQLiteRepository
    vault_root = tmp_path / "uvault"
    (vault_root / "_sources").mkdir(parents=True)
    (vault_root / "_concepts").mkdir(parents=True)
    src_hash = hashlib.sha256(_BATCH_BODY.encode("utf-8")).hexdigest()
    (vault_root / "_sources" / "src-x.md").write_text(_BATCH_BODY,
                                                      encoding="utf-8")
    # candidates file inside the vault (single-page apply path)
    (vault_root / "cand.json").write_text(json.dumps([_cand("x")]))
    db_path = str(tmp_path / "u.db")
    db: Any = SQLiteRepository(tmp_path / "u.db")
    db.apply_schema()  # type: ignore[attr-defined]
    db.register_vault(Vault(
        vault_id="unindexed-test", name="u", root_path=vault_root,
        schema_version="2.0", registered_at=datetime.now(timezone.utc),
    ))
    db.close()  # deliberately NO pages row + NO reindex
    return vault_root, db_path, src_hash


def test_single_page_apply_unindexed_source_clean_envelope(
    tmp_path: Path,
) -> None:
    """F1: single-page apply on an UNINDEXED source returns a clean
    DB_WRITE_FAILED envelope (exit 5), NOT an uncaught sqlite3 traceback —
    parity with the hardened batch path."""
    vault_root, db_path, src_hash = _setup_unindexed_vault(tmp_path)
    ns = argparse.Namespace(
        cmd="apply", vault="unindexed-test", vault_root=vault_root,
        source_page="src-x", source_hash=src_hash, db_path=db_path,
        ingest=False, orchestrator_id="claude-test",
        candidates_file=vault_root / "cand.json", candidates_stdin=False,
        batch_candidates=None,
    )
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = wec.apply(ns)  # must NOT raise sqlite3.IntegrityError
    result = json.loads(buf.getvalue())
    assert rc == 5, "DB fault → exit 5 (retry-safe partial), not a crash"
    assert result["error"] == "DB_WRITE_FAILED"
    assert "wiki-reindex" in result["reason"], "actionable remediation hint"


def test_apply_batch_dispatch_db_error_isolated(tmp_path: Path) -> None:
    """A sqlite3.Error from the --ingest dispatch isolates to one entry
    (DB_WRITE_FAILED) and does NOT crash the batch (dispatch-phase parity
    with the write-phase per-entry catch)."""
    import sqlite3
    vault_root, db_path, src_hash, slugs = _setup_apply_batch_vault(tmp_path)
    combined = [
        {"source_slug": slugs[0], "source_hash": src_hash,
         "candidates": [_cand("a")]},
        {"source_slug": slugs[1], "source_hash": src_hash,
         "candidates": [_cand("b")]},
    ]
    cf = tmp_path / "combined.json"
    cf.write_text(json.dumps(combined))

    real_dispatch = wec.dispatch_to_indexer
    n = {"calls": 0}

    def flaky_dispatch(*a: Any, **k: Any) -> dict[str, Any]:
        n["calls"] += 1
        if n["calls"] == 2:
            raise sqlite3.OperationalError("disk I/O error")
        return real_dispatch(*a, **k)

    with patch.object(wec, "dispatch_to_indexer", side_effect=flaky_dispatch):
        rc, result = _run_apply_batch(vault_root, str(cf), db_path, ingest=True)
    assert rc == 0, "dispatch DB fault on one entry must not abort the batch"
    assert len(result["batch"]) == 2
    assert result["batch"][1].get("error") == "DB_WRITE_FAILED"


def test_apply_batch_traversal_slug_no_abspath_leak(tmp_path: Path) -> None:
    """vdd-multi LOW (M-2/CWE-209): a traversal slug is rejected AND the
    error reason must not leak the absolute vault path."""
    vault_root, db_path, src_hash, slugs = _setup_apply_batch_vault(tmp_path)
    combined = [
        {"source_slug": "../../../../etc/passwd", "source_hash": src_hash,
         "candidates": [_cand("a")]},
    ]
    cf = tmp_path / "combined.json"
    cf.write_text(json.dumps(combined))
    rc, result = _run_apply_batch(vault_root, str(cf), db_path)
    assert rc == 0
    entry = result["batch"][0]
    assert "error" in entry
    blob = json.dumps(entry)
    assert str(vault_root) not in blob, "absolute vault path must not leak"
