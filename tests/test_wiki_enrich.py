"""Tests for scripts/wiki_skills/wiki_enrich.py (bridge: wiki-ingest → SQLite).

Mock-based: real wiki-ingest may not be installed in CI. We exercise the
parsing / validation / index-from-manifest path with hand-built manifests.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest import mock

import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills.wiki_enrich import (
    WikiIngestError,
    _parse_semver,
    _validate_manifest,
    check_wiki_ingest_version,
    index_from_manifest,
)


# =============================================================================
# Unit: semver parsing
# =============================================================================


def test_parse_semver_basic():
    assert _parse_semver("wiki-ingest 1.1.0") == (1, 1, 0)
    assert _parse_semver("1.2") == (1, 2)
    assert _parse_semver("v0.9.1") == (0, 9, 1)
    assert _parse_semver("1.1.0-rc1") == (1, 1, 0)


def test_parse_semver_garbage_returns_zero():
    assert _parse_semver("not a version") == (0,)


# =============================================================================
# Unit: version check
# =============================================================================


def test_version_check_missing_binary_raises(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    with pytest.raises(WikiIngestError, match=r"not found on PATH"):
        check_wiki_ingest_version("wiki-ingest-fake")


def test_version_check_too_old_raises(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/fake")
    fake = mock.Mock(returncode=0, stdout="wiki-ingest 1.0.5", stderr="")
    with mock.patch("subprocess.run", return_value=fake):
        with pytest.raises(WikiIngestError, match=r"< required"):
            check_wiki_ingest_version("wiki-ingest")


def test_version_check_ok(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/fake")
    fake = mock.Mock(returncode=0, stdout="wiki-ingest 1.1.0", stderr="")
    with mock.patch("subprocess.run", return_value=fake):
        v = check_wiki_ingest_version("wiki-ingest")
    assert v == (1, 1, 0)


# =============================================================================
# Unit: manifest validation
# =============================================================================


def _build_manifest(vault_id: str, vault_root: Path, written: list[str]):
    return {
        "status": "ok",
        "vault_id": vault_id,
        "vault_root": str(vault_root),
        "source": {"slug": "test-source", "hash": "deadbeef"},
        "written": [{"path": p, "action": "created", "kind": "source",
                     "scope": "vault"} for p in written],
        "created": written,
        "touched": [],
        "contradictions": 0,
        "log_event": {
            "event_ts": "2026-05-26T14:32:11",
            "event_type": "ingest",
            "subject": "Test Source",
            "log_md_byte_offset": 0,
        },
    }


def test_validate_manifest_status_not_ok(tmp_path):
    bad = {"status": "error"}
    with pytest.raises(WikiIngestError, match=r"status != 'ok'"):
        _validate_manifest(bad, "test-vault", tmp_path)


def test_validate_manifest_vault_id_mismatch(tmp_path):
    m = _build_manifest("wrong-vault", tmp_path, [])
    with pytest.raises(WikiIngestError, match=r"vault_id"):
        _validate_manifest(m, "test-vault", tmp_path)


def test_validate_manifest_path_traversal_rejected(tmp_path, minimal_vault):
    """A manifest claiming `../../etc/passwd` is rejected by R-26 gate."""
    m = _build_manifest("minimal-test", minimal_vault,
                        ["../../etc/passwd"])
    with pytest.raises(WikiIngestError, match=r"vault containment"):
        _validate_manifest(m, "minimal-test", minimal_vault)


def test_validate_manifest_happy(minimal_vault):
    m = _build_manifest("minimal-test", minimal_vault,
                        ["_sources/alpha.md"])
    # No exception — alpha.md exists in the fixture vault.
    _validate_manifest(m, "minimal-test", minimal_vault)


# =============================================================================
# Integration: full index_from_manifest against a registered vault
# =============================================================================


@pytest.fixture
def registered_vault(minimal_vault, tmp_path):
    db = tmp_path / "g.db"
    r = SQLiteRepository(db)
    r.apply_schema()
    r.register_vault(Vault(
        vault_id="minimal-test", name="t", root_path=minimal_vault,
        schema_version="2.0", registered_at=datetime(2026, 5, 26),
    ))
    r.close()
    return minimal_vault, db


def test_index_from_manifest_upserts_existing_files(registered_vault):
    """index_from_manifest loops written[], calls wiki_index_upsert per path,
    and inserts the log_event row."""
    vault_root, db = registered_vault
    m = _build_manifest("minimal-test", vault_root,
                        ["_sources/alpha.md"])
    summary = index_from_manifest(m, "minimal-test", vault_root,
                                  db_path=str(db))
    assert summary["failed"] == []
    assert len(summary["upserted"]) == 1
    assert summary["upserted"][0]["path"] == "_sources/alpha.md"
    assert summary["log_event_id"] is not None and summary["log_event_id"] > 0

    # Verify DB has the row
    r = SQLiteRepository(db)
    p = r.get_page("minimal-test", "alpha", "_vault_")
    assert p is not None
    # log_events has the ingest row
    rows = r._connect().execute(
        "SELECT event_type, subject FROM log_events WHERE vault_id='minimal-test'"
    ).fetchall()
    assert any(row["event_type"] == "ingest"
               and row["subject"] == "Test Source" for row in rows)
    r.close()


def test_index_from_manifest_partial_failure_skips_log_event(registered_vault):
    """If any upsert fails, log_event is NOT mirrored (recovery-friendly)."""
    vault_root, db = registered_vault
    # Manifest claims a file that doesn't exist on disk; upsert will fail
    m = _build_manifest("minimal-test", vault_root,
                        ["_sources/nonexistent.md"])
    # Skip _validate_manifest (would reject earlier); call index directly.
    summary = index_from_manifest(m, "minimal-test", vault_root,
                                  db_path=str(db))
    assert len(summary["failed"]) == 1
    assert summary["log_event_id"] is None


def test_index_from_manifest_skips_top_level_system_files(registered_vault):
    """Top-level index.md/log.md/WIKI_SCHEMA.md/CLAUDE.md MUST be skipped —
    they are Class B/C (ADR-002 §D8), mirrored via other paths. The bridge
    must NOT route them through page-upsert (would fail on missing `type:`)."""
    vault_root, db = registered_vault
    m = _build_manifest("minimal-test", vault_root, ["_sources/alpha.md"])
    # Inject system-file entries that wiki-ingest emits in its written[].
    m["written"].extend([
        {"path": "index.md", "action": "updated", "kind": "index",
         "scope": "vault"},
        {"path": "log.md", "action": "appended", "kind": "log",
         "scope": "vault"},
        {"path": "WIKI_SCHEMA.md", "action": "updated", "kind": "schema",
         "scope": "vault"},
    ])
    summary = index_from_manifest(m, "minimal-test", vault_root,
                                  db_path=str(db))
    assert summary["failed"] == []
    # Only the content page was indexed; system files were silently skipped.
    assert len(summary["upserted"]) == 1
    assert summary["upserted"][0]["path"] == "_sources/alpha.md"
    # log_event still mirrored (failed is empty).
    assert summary["log_event_id"] is not None and summary["log_event_id"] > 0


# =============================================================================
# Bead 004-07 / R-51: path-decision branch coverage (TASK 004)
# In-process primary path + 3 subprocess fallback scenarios + content failure.
# =============================================================================


def _make_vendoring_vault(tmp_path: Path) -> tuple[Path, Path, str]:
    """Build a minimal registered vault + source file for wiki-enrich main().
    Returns (vault_root, source_path, db_path)."""
    from scripts.wiki_index.sqlite_repository import SQLiteRepository

    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    (vault_root / "_sources").mkdir()
    (vault_root / "WIKI_SCHEMA.md").write_text(
        "---\nschema_version: '1.0'\nvault_id: vendor-test\n---\n",
        encoding="utf-8",
    )
    src = tmp_path / "src.md"
    src.write_text(
        "---\ntype: summary\ntitle: Vendor Test\n---\nBody.\n",
        encoding="utf-8",
    )
    db = tmp_path / "g.db"
    r = SQLiteRepository(db)
    r.apply_schema()
    r.register_vault(Vault(
        vault_id="vendor-test", name="vt", root_path=vault_root,
        schema_version="2.0", registered_at=datetime(2026, 5, 27),
    ))
    r.close()
    return vault_root, src, str(db)


def _canned_manifest(vault_root: Path, source: Path, vault_id: str) -> dict:
    return {
        "manifest_version": "1.1",
        "status": "ok",
        "vault_id": vault_id,
        "vault_root": str(vault_root),
        "source": {"path": str(source), "slug": "src", "hash": "deadbeef"},
        "written": [],
        "created": [],
        "touched": [],
        "log_event": None,
    }


def test_in_process_no_subprocess(monkeypatch, tmp_path):
    """R-47(a): primary path does NOT spawn `wiki-ingest` subprocess."""
    from scripts.wiki_skills import wiki_enrich

    vault_root, src, db = _make_vendoring_vault(tmp_path)
    canned = _canned_manifest(vault_root, src, "vendor-test")

    monkeypatch.setattr(wiki_enrich, "_VENDORED_AVAILABLE", True)
    monkeypatch.setattr(
        wiki_enrich, "_vendored_ingest",
        lambda **_: canned,
    )
    subprocess_mock = mock.MagicMock()
    monkeypatch.setattr(wiki_enrich.subprocess, "run", subprocess_mock)
    monkeypatch.delenv("WIKI_ENRICH_NO_VENDORED", raising=False)

    exit_code = wiki_enrich.main([
        "--vault", "vendor-test",
        "--vault-root", str(vault_root),
        "--source", str(src),
        "--db-path", db,
    ])
    assert exit_code == 0
    assert subprocess_mock.call_count == 0, "primary path must not spawn subprocess"


def test_no_vendored_env_forces_subprocess(monkeypatch, tmp_path):
    """R-48(a): WIKI_ENRICH_NO_VENDORED=1 routes to subprocess fallback path."""
    from scripts.wiki_skills import wiki_enrich

    vault_root, src, db = _make_vendoring_vault(tmp_path)
    canned = _canned_manifest(vault_root, src, "vendor-test")

    monkeypatch.setenv("WIKI_ENRICH_NO_VENDORED", "1")
    monkeypatch.setattr(wiki_enrich.shutil, "which",
                        lambda _: "/fake/bin/wiki-ingest")
    monkeypatch.setattr(wiki_enrich, "check_wiki_ingest_version",
                        mock.MagicMock())
    vendored_mock = mock.MagicMock()
    monkeypatch.setattr(wiki_enrich, "_vendored_ingest", vendored_mock)

    fake_proc = mock.MagicMock(returncode=0, stdout=json.dumps(canned),
                               stderr="")
    monkeypatch.setattr(wiki_enrich.subprocess, "run",
                        mock.MagicMock(return_value=fake_proc))

    exit_code = wiki_enrich.main([
        "--vault", "vendor-test",
        "--vault-root", str(vault_root),
        "--source", str(src),
        "--db-path", db,
    ])
    assert exit_code == 0
    assert vendored_mock.call_count == 0, (
        "env var override must not call vendored ingest()"
    )


def test_import_error_with_binary_falls_back_to_subprocess(monkeypatch, tmp_path):
    """R-48(b): vendored import failed + wiki-ingest on PATH → subprocess."""
    from scripts.wiki_skills import wiki_enrich

    vault_root, src, db = _make_vendoring_vault(tmp_path)
    canned = _canned_manifest(vault_root, src, "vendor-test")

    monkeypatch.setattr(wiki_enrich, "_VENDORED_AVAILABLE", False)
    monkeypatch.delenv("WIKI_ENRICH_NO_VENDORED", raising=False)
    monkeypatch.setattr(wiki_enrich.shutil, "which",
                        lambda _: "/fake/bin/wiki-ingest")
    monkeypatch.setattr(wiki_enrich, "check_wiki_ingest_version",
                        mock.MagicMock())

    fake_proc = mock.MagicMock(returncode=0, stdout=json.dumps(canned),
                               stderr="")
    subprocess_mock = mock.MagicMock(return_value=fake_proc)
    monkeypatch.setattr(wiki_enrich.subprocess, "run", subprocess_mock)

    exit_code = wiki_enrich.main([
        "--vault", "vendor-test",
        "--vault-root", str(vault_root),
        "--source", str(src),
        "--db-path", db,
    ])
    assert exit_code == 0
    assert subprocess_mock.call_count == 1


def test_import_error_without_binary_emits_unavailable_error(monkeypatch, tmp_path, capsys):
    """R-48(c): vendored ImportError + wiki-ingest absent → exit 6,
    `WIKI_INGEST_UNAVAILABLE` error envelope on stdout."""
    from scripts.wiki_skills import wiki_enrich

    vault_root, src, db = _make_vendoring_vault(tmp_path)

    monkeypatch.setattr(wiki_enrich, "_VENDORED_AVAILABLE", False)
    monkeypatch.delenv("WIKI_ENRICH_NO_VENDORED", raising=False)
    monkeypatch.setattr(wiki_enrich.shutil, "which", lambda _: None)

    exit_code = wiki_enrich.main([
        "--vault", "vendor-test",
        "--vault-root", str(vault_root),
        "--source", str(src),
        "--db-path", db,
    ])
    assert exit_code == 6
    captured = capsys.readouterr().out
    payload = json.loads(captured)
    assert payload["error"] == "WIKI_INGEST_UNAVAILABLE"


@pytest.mark.parametrize("env_value,should_force_subprocess", [
    ("1", True),
    ("true", True),
    ("TRUE", True),
    ("yes", True),
    ("on", True),
    (" true ", True),       # whitespace-stripped
    ("0", False),
    ("false", False),
    ("no", False),
    ("", False),
])
def test_no_vendored_env_truthy_parsing(monkeypatch, tmp_path, env_value, should_force_subprocess):
    """vdd-multi critic-logic H-3 / critic-security M-2 regression guard:
    WIKI_ENRICH_NO_VENDORED accepts case-insensitive truthy set, not only "1"."""
    from scripts.wiki_skills import wiki_enrich

    vault_root, src, db = _make_vendoring_vault(tmp_path)
    canned = _canned_manifest(vault_root, src, "vendor-test")

    monkeypatch.setattr(wiki_enrich, "_VENDORED_AVAILABLE", True)
    monkeypatch.setattr(wiki_enrich, "_vendored_ingest", lambda **_: canned)
    subprocess_mock = mock.MagicMock(
        return_value=mock.MagicMock(returncode=0, stdout=json.dumps(canned), stderr=""))
    monkeypatch.setattr(wiki_enrich.subprocess, "run", subprocess_mock)
    monkeypatch.setattr(wiki_enrich.shutil, "which",
                        lambda _: "/fake/bin/wiki-ingest")
    monkeypatch.setattr(wiki_enrich, "check_wiki_ingest_version", mock.MagicMock())
    monkeypatch.setenv("WIKI_ENRICH_NO_VENDORED", env_value)

    exit_code = wiki_enrich.main([
        "--vault", "vendor-test",
        "--vault-root", str(vault_root),
        "--source", str(src),
        "--db-path", db,
    ])
    assert exit_code == 0
    if should_force_subprocess:
        assert subprocess_mock.call_count == 1, (
            f"env_value={env_value!r} should force subprocess fallback"
        )
    else:
        assert subprocess_mock.call_count == 0, (
            f"env_value={env_value!r} should NOT force subprocess"
        )


def test_partial_index_failure_envelope_carries_head_on_primary(monkeypatch, tmp_path, capsys):
    """vdd-multi critic-logic H-1 regression guard: PARTIAL_INDEX_FAILURE
    on the primary (in-process) path emits the FULL envelope (manifest_head
    + cleanup_advice + written_so_far), byte-shape-identical to the
    subprocess path. Pre-fix the primary-path envelope was truncated."""
    from scripts.wiki_skills import wiki_enrich
    from scripts.wiki_ingest.commands.ingest import IngestError

    vault_root, src, db = _make_vendoring_vault(tmp_path)

    err = IngestError(
        "partial failure at phase 'upsert-page': cleanup-hint",
        code="PARTIAL_INDEX_FAILURE",
        phase="upsert-page",
        written_so_far=[{"path": "_concepts/x.md", "action": "created"}],
        child_exit_code=2,
    )
    err.manifest_head = {  # type: ignore[attr-defined]
        "manifest_version": "1.1",
        "vault_id": "vendor-test",
        "vault_root": str(vault_root),
        "course": None,
        "source": {"path": str(src), "slug": "src", "hash": "deadbeef"},
    }
    err.cleanup_advice = "cleanup-hint"  # type: ignore[attr-defined]

    monkeypatch.setattr(wiki_enrich, "_VENDORED_AVAILABLE", True)
    monkeypatch.setattr(wiki_enrich, "_VendoredIngestError", IngestError)

    def raise_partial(**_):
        raise err

    monkeypatch.setattr(wiki_enrich, "_vendored_ingest", raise_partial)
    monkeypatch.delenv("WIKI_ENRICH_NO_VENDORED", raising=False)

    exit_code = wiki_enrich.main([
        "--vault", "vendor-test",
        "--vault-root", str(vault_root),
        "--source", str(src),
        "--db-path", db,
    ])
    assert exit_code == 6
    payload = json.loads(capsys.readouterr().out)
    # R-56 byte-identical contract — full envelope shape, not truncated.
    assert payload["manifest_version"] == "1.1"
    assert payload["vault_id"] == "vendor-test"
    assert payload["status"] == "error"
    assert payload["code"] == "PARTIAL_INDEX_FAILURE"
    assert payload["phase"] == "upsert-page"
    assert payload["child_exit_code"] == 2
    assert payload["written_so_far"] == [{"path": "_concepts/x.md", "action": "created"}]
    assert payload["cleanup_advice"] == "cleanup-hint"


def test_index_from_manifest_rejects_absolute_path(registered_vault):
    """vdd-multi critic-logic M-1 regression guard: absolute path in
    manifest.written[] must be rejected (defense-in-depth — _validate_manifest
    should catch first, but the upsert loop has its own guard)."""
    from scripts.wiki_skills.wiki_enrich import index_from_manifest

    vault_root, db = registered_vault
    manifest = _build_manifest("minimal-test", vault_root, [])
    manifest["written"] = [{
        "path": "/abs/escape/index.md",  # absolute — must be rejected
        "action": "created", "kind": "source", "scope": "vault",
    }]
    summary = index_from_manifest(manifest, "minimal-test", vault_root,
                                  db_path=str(db))
    assert summary["upserted"] == []
    assert len(summary["failed"]) == 1
    assert summary["failed"][0]["envelope"]["error"] == "ABSOLUTE_PATH_IN_MANIFEST"


def test_ingest_error_emits_failed_envelope(monkeypatch, tmp_path, capsys):
    """Decision-14 semantic: vendored `IngestError` is a content failure,
    not a transport failure — must NOT fall back to subprocess."""
    from scripts.wiki_skills import wiki_enrich
    from scripts.wiki_ingest.commands.ingest import IngestError

    vault_root, src, db = _make_vendoring_vault(tmp_path)

    monkeypatch.setattr(wiki_enrich, "_VENDORED_AVAILABLE", True)
    monkeypatch.setattr(wiki_enrich, "_VendoredIngestError", IngestError)

    def raise_ingest_error(**_):
        raise IngestError(
            "source type=note not allowed",
            code="SOURCE_NEEDS_SUMMARIZATION",
            phase="needs-pre-summarization",
        )

    monkeypatch.setattr(wiki_enrich, "_vendored_ingest", raise_ingest_error)
    subprocess_mock = mock.MagicMock()
    monkeypatch.setattr(wiki_enrich.subprocess, "run", subprocess_mock)
    monkeypatch.delenv("WIKI_ENRICH_NO_VENDORED", raising=False)

    exit_code = wiki_enrich.main([
        "--vault", "vendor-test",
        "--vault-root", str(vault_root),
        "--source", str(src),
        "--db-path", db,
    ])
    assert exit_code == 6
    assert subprocess_mock.call_count == 0, (
        "IngestError must NOT trigger subprocess fallback"
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "WIKI_INGEST_FAILED"
    assert payload["code"] == "SOURCE_NEEDS_SUMMARIZATION"


def test_index_from_manifest_does_not_skip_subdir_namesakes(registered_vault):
    """False-positive guard: a concept page whose basename happens to match
    a SYSTEM_FILES entry (e.g. ``_concepts/index.md``) MUST still be indexed.
    The skip filter must be top-level-only."""
    vault_root, db = registered_vault
    # Create the subdir namesakes on disk so upsert can read them.
    concept_index = vault_root / "_concepts" / "index.md"
    concept_index.write_text(
        "---\ntype: concept\ntitle: Index (a concept)\n"
        "date: 2026-05-27\ntags: [test]\n---\nBody.\n",
        encoding="utf-8",
    )
    concept_log = vault_root / "_concepts" / "log.md"
    concept_log.write_text(
        "---\ntype: concept\ntitle: Log (a concept)\n"
        "date: 2026-05-27\ntags: [test]\n---\nBody.\n",
        encoding="utf-8",
    )
    m = _build_manifest("minimal-test", vault_root, [])
    m["written"] = [
        {"path": "_concepts/index.md", "action": "created", "kind": "concept",
         "scope": "vault"},
        {"path": "_concepts/log.md", "action": "created", "kind": "concept",
         "scope": "vault"},
    ]
    summary = index_from_manifest(m, "minimal-test", vault_root,
                                  db_path=str(db))
    assert summary["failed"] == [], summary["failed"]
    assert len(summary["upserted"]) == 2
    paths = {row["path"] for row in summary["upserted"]}
    assert paths == {"_concepts/index.md", "_concepts/log.md"}
