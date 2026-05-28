"""Tests for `scripts.wiki_skills.wiki_extract_concepts`.

Bead 003-01 lands the argparse surface + 9 helper stubs.
Bead 003-03 lands `load_known_entities` (raw SQL on `repo._connect()`).
Downstream beads (003-04..003-11) add the real test surface as each
helper's body fills in.
"""
from __future__ import annotations

import argparse
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable
from unittest import mock

import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.repository import IndexRepository
import scripts.wiki_skills.wiki_extract_concepts as wec


# ============================================================================
# Argparse surface (R-30 / R-31 / R-42)
# ============================================================================


def test_argparse_no_args_returns_exit_2() -> None:
    """`main([])` → argparse SystemExit(2). Under v3.1 the cause is
    "missing required subcommand" (was "missing required --vault" in v2);
    the mechanical assertion is unchanged.
    """
    with pytest.raises(SystemExit) as ei:
        wec.main([])
    assert ei.value.code == 2


def test_argparse_no_subcommand_returns_helpful_error(
    capsys: pytest.CaptureFixture,
) -> None:
    """H-4 BREAKING CHANGE smoke: invoking without `prepare` / `apply`
    fails at argparse with stderr that names both subcommand choices, so
    the operator can see the migration path.
    """
    with pytest.raises(SystemExit) as ei:
        wec._build_parser_v3().parse_args([])
    assert ei.value.code == 2
    err = capsys.readouterr().err
    assert "prepare" in err
    assert "apply" in err


def test_argparse_prepare_subparser_exists() -> None:
    """`prepare` subparser accepts the recon flags and rejects v2-only ones."""
    args = wec._build_parser_v3().parse_args([
        "prepare",
        "--vault", "X",
        "--vault-root", "/tmp",
        "--source-page", "sample-doc",
    ])
    assert args.cmd == "prepare"
    assert args.vault == "X"
    assert args.source_page == "sample-doc"


_VALID_HASH = "deadbeef" * 8  # 64 lowercase hex chars (C-1 normalized form)
_VALID_HASH_UPPER = _VALID_HASH.upper()


def test_argparse_apply_subparser_exists() -> None:
    """`apply` subparser accepts the write-path flags including --source-hash
    (REQUIRED, validated as 64-lowercase-hex per C-1) and the candidates
    mutex group.
    """
    args = wec._build_parser_v3().parse_args([
        "apply",
        "--vault", "X",
        "--vault-root", "/tmp",
        "--source-page", "sample-doc",
        "--source-hash", _VALID_HASH,
        "--candidates-stdin",
    ])
    assert args.cmd == "apply"
    assert args.source_hash == _VALID_HASH
    assert args.candidates_stdin is True
    assert args.candidates_file is None


def test_argparse_apply_source_hash_case_normalized_C1() -> None:
    """C-1: --source-hash DEADBEEF... (uppercased by PowerShell `toupper`
    or similar pipeline) is accepted and normalized to lowercase, not
    misrouted to SOURCE_CHANGED_DURING_EXTRACTION."""
    args = wec._build_parser_v3().parse_args([
        "apply",
        "--vault", "X",
        "--vault-root", "/tmp",
        "--source-page", "sample-doc",
        "--source-hash", _VALID_HASH_UPPER,
        "--candidates-stdin",
    ])
    assert args.source_hash == _VALID_HASH  # normalized to lowercase


def test_argparse_apply_source_hash_rejects_short_value_C1(
    capsys: pytest.CaptureFixture,
) -> None:
    """C-1: --source-hash with < 64 chars (e.g., 'deadbeef') is rejected
    at argparse with SystemExit(2). Without this gate, the value would
    silently misroute and could land unescaped in CWE-117 log injection
    vector via the envelope reason field."""
    with pytest.raises(SystemExit) as ei:
        wec._build_parser_v3().parse_args([
            "apply",
            "--vault", "X",
            "--vault-root", "/tmp",
            "--source-page", "sample-doc",
            "--source-hash", "deadbeef",  # only 8 chars
            "--candidates-stdin",
        ])
    assert ei.value.code == 2
    err = capsys.readouterr().err
    assert "64 lowercase hex chars" in err


def test_argparse_apply_source_hash_rejects_non_hex_chars_C1(
    capsys: pytest.CaptureFixture,
) -> None:
    """C-1: --source-hash with non-hex chars (e.g., embedded ANSI escape
    or JSON-breaking sequence) is rejected at argparse, closing the
    CWE-117 log-injection vector through the envelope reason field."""
    evil = "z" * 64  # 64 chars but not hex
    with pytest.raises(SystemExit) as ei:
        wec._build_parser_v3().parse_args([
            "apply",
            "--vault", "X",
            "--vault-root", "/tmp",
            "--source-page", "sample-doc",
            "--source-hash", evil,
            "--candidates-stdin",
        ])
    assert ei.value.code == 2


# test_main_dispatches_to_prepare_stub REMOVED in 003-v3-01:
# the prepare() stub was replaced with the real implementation, so the
# NotImplementedError assertion no longer holds. Real prepare-surface tests
# live below (test_prepare_*).


# test_main_dispatches_to_apply_stub REMOVED in 003-v3-03:
# the apply() stub was replaced with the real implementation, so the
# NotImplementedError assertion no longer holds. Real apply-surface tests
# live in the "003-v3-03: apply subcommand" section below.


def test_argparse_top_level_help_shows_subcommands(
    capsys: pytest.CaptureFixture,
) -> None:
    """Replacement for the 003-v3-11a-deleted `test_argparse_help_text_contains_ingest_flag`.
    Top-level --help now lists the {prepare,apply} subcommand choices instead of
    the v2 monolithic flag set (--ingest, --vault, --source-page lived at the
    top-level in v2; under v3.1 they live under `apply`).
    """
    with pytest.raises(SystemExit) as ei:
        wec.main(["--help"])
    assert ei.value.code == 0
    out = capsys.readouterr().out
    # Both subcommands must be visible in the usage line / choices.
    assert "prepare" in out
    assert "apply" in out


# ============================================================================
# 003-v3-01: prepare subcommand (R-31, R-32, R-39, R-42)
# ============================================================================


def _make_prepare_args(
    vault: str, vault_root: Path, source_page: str,
    db_path: str | None = None,
) -> argparse.Namespace:
    """Build an argparse.Namespace matching the `prepare` subparser surface."""
    return argparse.Namespace(
        cmd="prepare",
        vault=vault, vault_root=vault_root,
        source_page=source_page, db_path=db_path,
    )


def test_prepare_happy_path(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """prepare emits the canonical recon envelope on a fresh vault."""
    vault_root = tmp_path / "vault"
    sources_dir = vault_root / "_sources"
    sources_dir.mkdir(parents=True)
    src = sources_dir / "sample-doc.md"
    src.write_text("---\ntype: summary\n---\nbody.", encoding="utf-8")

    db_path = str(tmp_path / "test.db")
    bootstrap = repo_factory()
    bootstrap.apply_schema()  # type: ignore[attr-defined]
    _register_vault(bootstrap, "trade-agents", tmp_path)
    bootstrap.close()
    import shutil as _sh
    src_db = list(tmp_path.glob("wiki-*.db"))[0]
    _sh.copy(src_db, db_path)

    args = _make_prepare_args("trade-agents", vault_root, "sample-doc", db_path)
    rc = wec.prepare(args)
    assert rc == 0
    import json as _json
    payload = _json.loads(capsys.readouterr().out)
    assert payload["vault_id"] == "trade-agents"
    assert payload["source_slug"] == "sample-doc"
    assert payload["is_unchanged"] is False
    assert len(payload["source_hash"]) == 64  # sha256 hex
    assert payload["known_concepts"] == []
    assert payload["missing_concept_files"] == []


def test_prepare_source_not_found(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """SOURCE_NOT_FOUND when the file doesn't exist."""
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    args = _make_prepare_args("trade-agents", vault_root, "missing-page")
    rc = wec.prepare(args)
    assert rc == 2
    import json as _json
    payload = _json.loads(capsys.readouterr().out)
    assert payload["error"] == "SOURCE_NOT_FOUND"


def test_prepare_invalid_slug(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """H-3 regression migration from 003-v3-11a: source-page with dots in
    stem → INVALID_SOURCE_SLUG BEFORE any concept page write."""
    vault_root = tmp_path / "vault"
    sources_dir = vault_root / "_sources"
    sources_dir.mkdir(parents=True)
    bad = sources_dir / "Foo.Bar.md"
    bad.write_text("---\ntype: summary\n---\nbody.", encoding="utf-8")

    args = _make_prepare_args("trade-agents", vault_root, "Foo.Bar")
    rc = wec.prepare(args)
    assert rc == 2
    import json as _json
    payload = _json.loads(capsys.readouterr().out)
    assert payload["error"] == "INVALID_SOURCE_SLUG"
    # Critically: no concept pages got written before the error
    concepts = vault_root / "_concepts"
    if concepts.exists():
        assert list(concepts.glob("*.md")) == []


def test_prepare_invalid_source_path_absolute(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """H-1 regression migration from 003-v3-11a: absolute --source-page →
    INVALID_SOURCE_PATH (distinct envelope from SOURCE_NOT_FOUND)."""
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    args = _make_prepare_args("trade-agents", vault_root, "/etc/passwd")
    rc = wec.prepare(args)
    assert rc == 2
    import json as _json
    payload = _json.loads(capsys.readouterr().out)
    assert payload["error"] == "INVALID_SOURCE_PATH"
    # No concept pages written
    concepts = vault_root / "_concepts"
    if concepts.exists():
        assert list(concepts.glob("*.md")) == []


def test_prepare_idempotency_match_returns_unchanged_true(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """is_unchanged=true when source_state.source_hash matches the recomputed hash."""
    import hashlib as _hashlib
    vault_root = tmp_path / "vault"
    sources_dir = vault_root / "_sources"
    sources_dir.mkdir(parents=True)
    src = sources_dir / "sample-doc.md"
    body = "---\ntype: summary\n---\nidempotent body."
    src.write_text(body, encoding="utf-8")
    expected_hash = _hashlib.sha256(body.encode("utf-8")).hexdigest()

    db_path = str(tmp_path / "test.db")
    bootstrap = repo_factory()
    bootstrap.apply_schema()  # type: ignore[attr-defined]
    _register_vault(bootstrap, "trade-agents", tmp_path)
    # Pre-insert source_state row matching the body hash (key/value schema)
    bootstrap._connect().execute(  # type: ignore[attr-defined]
        "INSERT INTO source_state(vault_id, source_kind, scope, key, value, "
        "updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("trade-agents", "extract-concepts", "sample-doc",
         "source_hash", expected_hash,
         datetime.now(timezone.utc).isoformat()),
    )
    bootstrap._connect().commit()  # type: ignore[attr-defined]
    bootstrap.close()
    import shutil as _sh
    src_db = list(tmp_path.glob("wiki-*.db"))[0]
    _sh.copy(src_db, db_path)

    args = _make_prepare_args("trade-agents", vault_root, "sample-doc", db_path)
    rc = wec.prepare(args)
    assert rc == 0
    import json as _json
    payload = _json.loads(capsys.readouterr().out)
    assert payload["is_unchanged"] is True
    assert payload["source_hash"] == expected_hash


def test_prepare_source_too_large_M3(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """M-3: file st_size > _MAX_SOURCE_BODY_BYTES → SOURCE_TOO_LARGE BEFORE
    read_text. Envelope must NOT echo file content (CWE-117 guard)."""
    vault_root = tmp_path / "vault"
    sources_dir = vault_root / "_sources"
    sources_dir.mkdir(parents=True)
    big = sources_dir / "huge-doc.md"
    # Write 10 MiB + 1 byte; content irrelevant — only size matters for the cap.
    big.write_bytes(b"\x00" * (wec._MAX_SOURCE_BODY_BYTES + 1))

    db_path = str(tmp_path / "test.db")
    bootstrap = repo_factory()
    bootstrap.apply_schema()  # type: ignore[attr-defined]
    _register_vault(bootstrap, "trade-agents", tmp_path)
    bootstrap.close()
    import shutil as _sh
    src_db = list(tmp_path.glob("wiki-*.db"))[0]
    _sh.copy(src_db, db_path)

    args = _make_prepare_args("trade-agents", vault_root, "huge-doc", db_path)
    rc = wec.prepare(args)
    assert rc == 2
    import json as _json
    payload = _json.loads(capsys.readouterr().out)
    assert payload["error"] == "SOURCE_TOO_LARGE"
    # CWE-117: no content echo
    assert "content" not in payload
    assert "value" not in payload
    assert "raw" not in payload


def test_prepare_missing_concept_files_warns(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """M-1 / Q16: prepare lists known-entity slugs whose `_concepts/<slug>.md`
    is missing on disk. Eager O(N) sweep in v3.1 (P-9 deferred)."""
    vault_root = tmp_path / "vault"
    sources_dir = vault_root / "_sources"
    sources_dir.mkdir(parents=True)
    src = sources_dir / "sample-doc.md"
    src.write_text("---\ntype: summary\n---\nbody.", encoding="utf-8")
    concepts_dir = vault_root / "_concepts"
    concepts_dir.mkdir()
    # On-disk pages for 2 of 3 known entities; the 3rd is "missing".
    (concepts_dir / "alpha.md").write_text("# Alpha\n", encoding="utf-8")
    (concepts_dir / "beta.md").write_text("# Beta\n", encoding="utf-8")

    db_path = str(tmp_path / "test.db")
    bootstrap = repo_factory()
    bootstrap.apply_schema()  # type: ignore[attr-defined]
    _register_vault(bootstrap, "trade-agents", tmp_path)
    for slug, name in [("alpha", "Alpha"), ("beta", "Beta"), ("gamma", "Gamma")]:
        _insert_entity(bootstrap, "trade-agents", slug, name)
    bootstrap.close()
    import shutil as _sh
    src_db = list(tmp_path.glob("wiki-*.db"))[0]
    _sh.copy(src_db, db_path)

    args = _make_prepare_args("trade-agents", vault_root, "sample-doc", db_path)
    rc = wec.prepare(args)
    assert rc == 0
    import json as _json
    payload = _json.loads(capsys.readouterr().out)
    assert sorted(payload["missing_concept_files"]) == ["gamma"]
    assert sorted(e["slug"] for e in payload["known_concepts"]) == ["alpha", "beta", "gamma"]


# ============================================================================
# Module-top import lock (I-7.12 patch-target note)
# ============================================================================


def test_module_imports_neutral_manifest_consumer() -> None:
    """The three symbols from `_manifest_consumer` are bound at module top.

    This locks the `unittest.mock.patch` target as
    `scripts.wiki_skills.wiki_extract_concepts.<symbol>` (the importer's
    binding), NOT `scripts.wiki_skills._manifest_consumer.<symbol>`
    (the source-of-truth definition). If a future refactor demotes any of
    these to a lazy import inside `dispatch_to_indexer`, all patch sites
    break — this test guards against that drift.
    """
    assert wec.validate_manifest is not None
    assert wec.index_from_manifest is not None
    assert wec.WikiIngestError is not None
    # Sanity: they are the same objects as in the neutral module.
    from scripts.wiki_skills._manifest_consumer import (
        WikiIngestError as src_err,
        index_from_manifest as src_index,
        validate_manifest as src_validate,
    )
    assert wec.validate_manifest is src_validate
    assert wec.index_from_manifest is src_index
    assert wec.WikiIngestError is src_err


# ============================================================================
# Helper stubs raise NotImplementedError (the 9 staging targets)
# ============================================================================


def test_helpers_raise_not_implemented(tmp_path: Path) -> None:
    """Phase-1 stubs that remain to be filled by downstream beads. As each
    bead lands, the corresponding assertion is removed. All 003-NN helpers
    have landed (and the v2 LLM-call helpers are retired in 003-v3-11)."""
    # All 003-NN helpers landed; this test is now an empty contract — keep
    # the function as a regression placeholder so future stubs can
    # re-populate it if more helpers are added.
    assert True


# ============================================================================
# 003-03: load_known_entities (R-32)
# ============================================================================


def _register_vault(repo: IndexRepository, vault_id: str, tmp_path: Path) -> None:
    """Helper: minimal vault registration so entity FK insertions succeed."""
    repo.register_vault(Vault(
        vault_id=vault_id,
        name=f"{vault_id} test vault",
        root_path=tmp_path / vault_id,
        schema_version="2.0",
        registered_at=datetime.now(timezone.utc),
    ))


def _insert_entity(
    repo: IndexRepository, vault_id: str, slug: str, name: str,
    type_: str = "concept",
) -> None:
    """Helper: raw insert into entities table (bypasses upsert_entity which
    is the subject of bead 003-07a and doesn't exist yet)."""
    conn = repo._connect()  # type: ignore[attr-defined]
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO entities(vault_id, slug, type, name, first_seen, "
        "last_updated, file_path) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (vault_id, slug, type_, name, now, now, f"_entities/{slug}.md"),
    )
    conn.commit()


def _insert_alias(
    repo: IndexRepository, vault_id: str, entity_slug: str, alias: str,
    alias_type: str = "spelling_variant",
) -> None:
    conn = repo._connect()  # type: ignore[attr-defined]
    conn.execute(
        "INSERT INTO entity_aliases(vault_id, alias, entity_slug, alias_type) "
        "VALUES (?, ?, ?, ?)",
        (vault_id, alias, entity_slug, alias_type),
    )
    conn.commit()


def test_load_known_entities_empty_vault(
    repo_factory: Callable[[], IndexRepository],
    tmp_path: Path,
) -> None:
    """R-32(c): empty vault → [] (no exception)."""
    repo = repo_factory()
    repo.apply_schema()  # type: ignore[attr-defined]
    _register_vault(repo, "empty-vault", tmp_path)
    try:
        result = wec.load_known_entities(repo, "empty-vault")
    finally:
        repo.close()
    assert result == []


def test_load_known_entities_returns_aggregated_aliases(
    repo_factory: Callable[[], IndexRepository],
    tmp_path: Path,
) -> None:
    """R-32(b): entity rows + aliases serialised as
    [{"slug": ..., "name": ..., "type": ..., "aliases": [...]}]."""
    repo = repo_factory()
    repo.apply_schema()  # type: ignore[attr-defined]
    _register_vault(repo, "test-vault", tmp_path)
    try:
        _insert_entity(repo, "test-vault", "sharpe-ratio", "Sharpe Ratio")
        _insert_entity(repo, "test-vault", "hermes", "Hermes Agent",
                       type_="product")
        _insert_alias(repo, "test-vault", "sharpe-ratio", "Sharpe Score")
        _insert_alias(repo, "test-vault", "sharpe-ratio", "Sharpe Index")
        _insert_alias(repo, "test-vault", "hermes", "Hermes Framework")

        result = wec.load_known_entities(repo, "test-vault")
    finally:
        repo.close()

    assert len(result) == 2
    by_slug = {e["slug"]: e for e in result}
    assert by_slug["sharpe-ratio"]["name"] == "Sharpe Ratio"
    assert by_slug["sharpe-ratio"]["type"] == "concept"
    assert sorted(by_slug["sharpe-ratio"]["aliases"]) == ["Sharpe Index", "Sharpe Score"]
    assert by_slug["hermes"]["name"] == "Hermes Agent"
    assert by_slug["hermes"]["type"] == "product"
    assert by_slug["hermes"]["aliases"] == ["Hermes Framework"]


def test_load_known_entities_filters_by_vault(
    repo_factory: Callable[[], IndexRepository],
    tmp_path: Path,
) -> None:
    """ADR-002 §D1.1: multi-vault isolation — no cross-vault leakage."""
    repo = repo_factory()
    repo.apply_schema()  # type: ignore[attr-defined]
    _register_vault(repo, "vault-a", tmp_path)
    _register_vault(repo, "vault-b", tmp_path)
    try:
        _insert_entity(repo, "vault-a", "alpha", "Alpha (in A)")
        _insert_entity(repo, "vault-b", "beta", "Beta (in B)")

        a_result = wec.load_known_entities(repo, "vault-a")
        b_result = wec.load_known_entities(repo, "vault-b")
    finally:
        repo.close()

    assert {e["slug"] for e in a_result} == {"alpha"}
    assert {e["slug"] for e in b_result} == {"beta"}


# 003-v3-11: the prior v2 LLM-side test block (9 SDK-mock tests, 1
# prompt-construction test, 2 helpers) was removed in lockstep with the
# v3.1 Decision-17 refactor. The deleted surface tested the in-skill LLM
# call + prompt builder; all three (function, prompt helper, SDK import)
# are deleted in bead 003-v3-06. Regression intent for the v3.1 surface
# (synthesis is now orchestrator-side) is covered by:
#   - the strict validator tests (003-v3-02)
#   - the apply subcommand tests (003-v3-03)
#   - the envelope-shape parametrized test (003-v3-17)
#   - the integration test refactor (003-v3-12)


# ============================================================================
# 003-05: classify_candidates (R-34)
# ============================================================================


def test_classify_candidates_splits_known_and_novel() -> None:
    """R-34(b,c): known-slug → mention; novel slug → create."""
    llm_results = [
        {"slug": "alpha", "name": "Alpha"},
        {"slug": "gamma", "name": "Gamma"},
        {"slug": "beta", "name": "Beta"},
        {"slug": "delta", "name": "Delta"},
    ]
    create_list, mention_list = wec.classify_candidates(
        llm_results, {"alpha", "beta"},
    )
    assert {c["slug"] for c in create_list} == {"gamma", "delta"}
    assert {m["slug"] for m in mention_list} == {"alpha", "beta"}
    # R-34(d): action annotation present
    assert all(c["action"] == "create" for c in create_list)
    assert all(m["action"] == "mention" for m in mention_list)


def test_classify_candidates_empty_input() -> None:
    """Empty LLM results → ([], []) regardless of known_slugs."""
    create_list, mention_list = wec.classify_candidates([], {"alpha"})
    assert create_list == []
    assert mention_list == []


def test_classify_candidates_all_known() -> None:
    """All items match known_slugs → empty create_list."""
    llm_results = [
        {"slug": "alpha", "name": "Alpha"},
        {"slug": "beta", "name": "Beta"},
    ]
    create_list, mention_list = wec.classify_candidates(
        llm_results, {"alpha", "beta", "gamma"},
    )
    assert create_list == []
    assert len(mention_list) == 2


def test_classify_candidates_defensive_copy() -> None:
    """Annotated dicts are copies — caller's LLM output is not mutated."""
    original = {"slug": "novel", "name": "Novel"}
    create_list, _ = wec.classify_candidates([original], set())
    assert "action" not in original  # original untouched
    assert create_list[0]["action"] == "create"


# ============================================================================
# 003-v3-02: strict-validator (R-33′, R-42)
# ============================================================================


def _valid_candidate(**overrides: Any) -> dict[str, Any]:
    """Helper: build a canonical candidate with optional field overrides."""
    base = {
        "slug": "sharpe-ratio",
        "name": "Sharpe Ratio",
        "definition": "A risk-adjusted return measure.",
        "source_quote": "this exact quote",
        "source_span": "L1-L1",
        "entity_type": "concept",
    }
    base.update(overrides)
    return base


def test_validator_unknown_field_raises_H9() -> None:
    """H-9: strict-equality on keys rejects extras with UNKNOWN_FIELD;
    envelope identifies the field name but NEVER echoes its value."""
    item = _valid_candidate()
    item["evil"] = "leak-me-please"
    with pytest.raises(wec.ExtractionParseError) as ei:
        wec._validate_candidates_schema([item])
    assert ei.value.error == "UNKNOWN_FIELD"
    assert ei.value.field == "evil"
    # CWE-117: offending value MUST NOT appear in any envelope attr.
    assert "leak-me-please" not in (ei.value.reason or "")
    assert "leak-me-please" not in str(ei.value)


def test_validator_count_bound_empty_raises_H2() -> None:
    """H-2: count < 1 → CANDIDATE_COUNT_OUT_OF_BOUNDS."""
    with pytest.raises(wec.ExtractionParseError) as ei:
        wec._validate_candidates_schema([])
    assert ei.value.error == "CANDIDATE_COUNT_OUT_OF_BOUNDS"


def test_validator_count_bound_oversize_raises_H2() -> None:
    """H-2: count > 25 → CANDIDATE_COUNT_OUT_OF_BOUNDS."""
    items = [_valid_candidate(slug=f"slug-{i}") for i in range(26)]
    with pytest.raises(wec.ExtractionParseError) as ei:
        wec._validate_candidates_schema(items)
    assert ei.value.error == "CANDIDATE_COUNT_OUT_OF_BOUNDS"


def test_validator_field_too_long_definition_raises_H6() -> None:
    """H-6: definition > 2000 chars → FIELD_TOO_LONG, no content echo."""
    item = _valid_candidate(definition="x" * 2001)
    with pytest.raises(wec.ExtractionParseError) as ei:
        wec._validate_candidates_schema([item])
    assert ei.value.error == "FIELD_TOO_LONG"
    assert ei.value.field == "definition"
    # CWE-117: the long string must not appear in the envelope.
    assert "x" * 2001 not in (ei.value.reason or "")
    assert "x" * 2001 not in str(ei.value)


def test_validator_field_too_long_name_raises_H6() -> None:
    """H-6: name > 200 chars → FIELD_TOO_LONG, field='name'."""
    item = _valid_candidate(name="N" * 201)
    with pytest.raises(wec.ExtractionParseError) as ei:
        wec._validate_candidates_schema([item])
    assert ei.value.error == "FIELD_TOO_LONG"
    assert ei.value.field == "name"


def test_validator_field_too_long_source_quote_raises_H6() -> None:
    """H-6: source_quote > 500 chars → FIELD_TOO_LONG, field='source_quote'."""
    item = _valid_candidate(source_quote="Q" * 501)
    with pytest.raises(wec.ExtractionParseError) as ei:
        wec._validate_candidates_schema([item])
    assert ei.value.error == "FIELD_TOO_LONG"
    assert ei.value.field == "source_quote"


def test_validator_quote_in_body_optional_M5() -> None:
    """M-5: optional quote-in-body check (when source_body is provided AND
    WIKI_EXTRACT_NO_QUOTE_CHECK is NOT set). Match → pass; mismatch → raise."""
    item = _valid_candidate(source_quote="this exact quote")
    body_match = "preamble ... this exact quote ... epilogue"
    body_miss = "completely different content"
    # Match → no raise.
    wec._validate_candidates_schema([item], source_body=body_match)
    # Mismatch → FIELD_QUOTE_NOT_IN_BODY.
    with pytest.raises(wec.ExtractionParseError) as ei:
        wec._validate_candidates_schema([item], source_body=body_miss)
    assert ei.value.error == "FIELD_QUOTE_NOT_IN_BODY"
    assert ei.value.field == "source_quote"


def test_validator_quote_in_body_bypass_env_var_M5(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M-5: WIKI_EXTRACT_NO_QUOTE_CHECK=1 bypasses the quote-in-body check
    even when source_body is provided."""
    monkeypatch.setenv("WIKI_EXTRACT_NO_QUOTE_CHECK", "1")
    item = _valid_candidate(source_quote="not present in body at all")
    # Would otherwise raise FIELD_QUOTE_NOT_IN_BODY; the env var bypasses.
    wec._validate_candidates_schema([item], source_body="just preamble")


# ============================================================================
# 003-06: write_concept_page (R-36, R-40)
# ============================================================================


_DEMO_CANDIDATE = {
    "slug": "sharpe-ratio",
    "name": "Sharpe Ratio",
    "definition": "A measure of risk-adjusted return.",
    "source_quote": "The Sharpe ratio measures excess return per unit of volatility.",
    "source_span": "L12-L14",
    "entity_type": "concept",
}


def test_write_concept_page_returns_correct_path(tmp_path: Path) -> None:
    """R-36(a): target path = `<vault_root>/_concepts/<slug>.md`.
    H-2 fix: returns (path, action) tuple."""
    path, action = wec.write_concept_page(
        tmp_path, _DEMO_CANDIDATE, "src", date(2026, 5, 27),
        vault_id="test-vault",
    )
    assert path == tmp_path / "_concepts" / "sharpe-ratio.md"
    assert path.is_file()
    assert action == "created"


def test_write_concept_page_writes_file_with_frontmatter(tmp_path: Path) -> None:
    """R-36(b,c): frontmatter contains the 9 required fields; body has
    `# <name>`, definition, `## Mentions`, provenance line."""
    target, _action = wec.write_concept_page(
        tmp_path, _DEMO_CANDIDATE, "self-improving-agent",
        date(2026, 5, 27), vault_id="trade-agents",
    )
    import frontmatter as _fm
    post = _fm.load(target)
    fm = post.metadata
    assert fm["type"] == "concept"
    assert fm["vault_id"] == "trade-agents"
    assert fm["slug"] == "sharpe-ratio"
    assert fm["name"] == "Sharpe Ratio"
    assert fm["date"] == "2026-05-27"
    assert sorted(fm["tags"]) == ["candidate", "concept"]
    assert fm["is_candidate"] is True
    assert fm["source_page"] == "self-improving-agent"
    assert fm["trust_level"] == "medium"
    body = post.content
    assert body.startswith("# Sharpe Ratio")
    assert "A measure of risk-adjusted return." in body
    assert "## Mentions" in body
    assert "[[self-improving-agent]]" in body
    assert "L12-L14" in body


# test_write_concept_page_skips_existing_file DELETED in 003-v3-04:
# v2's "skip-on-exists regardless of content" semantic is replaced by
# content-hash skip (C-1). The replacement coverage lives in
# test_write_concept_page_content_hash_skip_unchanged_C1 (same-content
# path) and test_write_concept_page_content_hash_diff_triggers_rewrite_C1
# (different-content path), both below.


def test_write_concept_page_creates_concepts_dir_if_missing(tmp_path: Path) -> None:
    """R-36 step 4 / UC-08 A4: `_concepts/` is created on demand."""
    assert not (tmp_path / "_concepts").exists()
    wec.write_concept_page(
        tmp_path, _DEMO_CANDIDATE, "src", date(2026, 5, 27),
        vault_id="test-vault",
    )
    assert (tmp_path / "_concepts").is_dir()


def test_write_concept_page_rejects_path_outside_vault(tmp_path: Path) -> None:
    """R-40(d): path-traversal slug → exception (PathTraversalError)."""
    from scripts.wiki_index.security import PathTraversalError
    malicious = {**_DEMO_CANDIDATE, "slug": "../escape"}
    with pytest.raises((PathTraversalError, OSError, ValueError)):
        wec.write_concept_page(
            tmp_path, malicious, "src", date(2026, 5, 27),
            vault_id="test-vault",
        )


# ============================================================================
# 003-v3-04: write_concept_page reshape — symlink refuse + content-hash skip
#            + markdown sanitization (R-36, R-40, Q13, Q15, H-7, C-1)
# ============================================================================


def test_write_concept_page_symlink_target_raises_PathTraversal_Q15(
    tmp_path: Path,
) -> None:
    """Q15 / NEW-2: pre-existing `_concepts/<slug>.md` symlink → refuse
    BEFORE any read or hash-compute."""
    from scripts.wiki_index.security import PathTraversalError
    concepts_dir = tmp_path / "_concepts"
    concepts_dir.mkdir(parents=True)
    elsewhere = tmp_path / "decoy.md"
    elsewhere.write_text("decoy\n", encoding="utf-8")
    target = concepts_dir / "sharpe-ratio.md"
    target.symlink_to(elsewhere)
    with pytest.raises(PathTraversalError, match="symlink"):
        wec.write_concept_page(
            tmp_path, _DEMO_CANDIDATE, "src", date(2026, 5, 27),
            vault_id="test-vault",
        )


def test_write_concept_page_content_hash_skip_unchanged_C1(
    tmp_path: Path,
) -> None:
    """C-1: identical inputs run twice → second call returns
    `(target, "unchanged")` and the on-disk file is byte-identical."""
    path1, action1 = wec.write_concept_page(
        tmp_path, _DEMO_CANDIDATE, "src", date(2026, 5, 27),
        vault_id="test-vault",
    )
    assert action1 == "created"
    bytes_after_first = path1.read_bytes()
    path2, action2 = wec.write_concept_page(
        tmp_path, _DEMO_CANDIDATE, "src", date(2026, 5, 27),
        vault_id="test-vault",
    )
    assert path2 == path1
    assert action2 == "unchanged"
    assert path2.read_bytes() == bytes_after_first


def test_write_concept_page_content_hash_diff_triggers_rewrite_C1(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """C-1: same target, different `definition` → atomic rewrite +
    `(target, "updated")` + `logger.warning` emitted."""
    path, _action = wec.write_concept_page(
        tmp_path, _DEMO_CANDIDATE, "src", date(2026, 5, 27),
        vault_id="test-vault",
    )
    mutated = {**_DEMO_CANDIDATE,
               "definition": "Updated definition — different content."}
    caplog.set_level("WARNING", logger="scripts.wiki_skills.wiki_extract_concepts")
    path2, action2 = wec.write_concept_page(
        tmp_path, mutated, "src", date(2026, 5, 27),
        vault_id="test-vault",
    )
    assert path2 == path
    assert action2 == "updated"
    assert "Updated definition" in path2.read_text(encoding="utf-8")
    assert any("rewriting" in rec.message for rec in caplog.records), (
        "logger.warning must fire on content rewrite (C-1 observability)"
    )


def test_write_concept_page_creates_new_returns_created(tmp_path: Path) -> None:
    """New target file → action='created' (preserved from v2 happy path)."""
    path, action = wec.write_concept_page(
        tmp_path, _DEMO_CANDIDATE, "src", date(2026, 5, 27),
        vault_id="test-vault",
    )
    assert path.is_file()
    assert action == "created"


def test_write_concept_page_sanitize_name_strips_leading_hash_H7(
    tmp_path: Path,
) -> None:
    """H-7: `name='## Backdoor'` → leading `##` stripped; body has
    `# Backdoor` H1 and NO smuggled `## Backdoor` line."""
    cand = {**_DEMO_CANDIDATE, "name": "## Backdoor"}
    path, _action = wec.write_concept_page(
        tmp_path, cand, "src", date(2026, 5, 27), vault_id="test-vault",
    )
    text = path.read_text(encoding="utf-8")
    import frontmatter as _fm
    post = _fm.loads(text)
    assert post.metadata["name"] == "Backdoor"
    assert "# Backdoor" in post.content
    assert "## Backdoor" not in post.content


def test_write_concept_page_sanitize_name_strips_leading_yaml_delimiter_H7(
    tmp_path: Path,
) -> None:
    """H-7: `name='--- evil'` → leading `---` stripped to `'evil'`; body
    does NOT contain a stray `---` outside the frontmatter block."""
    cand = {**_DEMO_CANDIDATE, "name": "--- evil"}
    path, _action = wec.write_concept_page(
        tmp_path, cand, "src", date(2026, 5, 27), vault_id="test-vault",
    )
    text = path.read_text(encoding="utf-8")
    import frontmatter as _fm
    post = _fm.loads(text)
    assert post.metadata["name"] == "evil"
    # Body must not contain `---` (only the frontmatter delimiters do).
    assert "---" not in post.content


def test_write_concept_page_sanitize_name_accepts_cyrillic_N5(
    tmp_path: Path,
) -> None:
    """Iteration-2 N-5: Cyrillic name `'Свидетель'` passes the
    allowlist (re.UNICODE flag) without raising."""
    cand = {**_DEMO_CANDIDATE, "slug": "svidetel", "name": "Свидетель"}
    path, action = wec.write_concept_page(
        tmp_path, cand, "src", date(2026, 5, 27), vault_id="test-vault",
    )
    assert action == "created"
    import frontmatter as _fm
    post = _fm.loads(path.read_text(encoding="utf-8"))
    assert post.metadata["name"] == "Свидетель"


def test_write_concept_page_sanitize_definition_escapes_newline_header_H7(
    tmp_path: Path,
) -> None:
    """H-7: `definition='text\\n## Backdoor'` → escaped to `\\n\\## ` so
    Obsidian does not render a new H2 mid-body."""
    cand = {**_DEMO_CANDIDATE, "definition": "text\n## Backdoor"}
    path, _action = wec.write_concept_page(
        tmp_path, cand, "src", date(2026, 5, 27), vault_id="test-vault",
    )
    import frontmatter as _fm
    post = _fm.loads(path.read_text(encoding="utf-8"))
    # The escaped backslash sequence must appear; the bare `## Backdoor`
    # must NOT appear at start-of-line.
    assert "\\## Backdoor" in post.content
    assert "\n## Backdoor" not in post.content


def test_write_concept_page_sanitize_definition_escapes_html_tag_H7(
    tmp_path: Path,
) -> None:
    """H-7: `definition='<script>alert(1)</script>'` → HTML entities
    escaped so Obsidian does not render the tag."""
    cand = {**_DEMO_CANDIDATE, "definition": "<script>alert(1)</script>"}
    path, _action = wec.write_concept_page(
        tmp_path, cand, "src", date(2026, 5, 27), vault_id="test-vault",
    )
    import frontmatter as _fm
    post = _fm.loads(path.read_text(encoding="utf-8"))
    assert "&lt;script&gt;" in post.content
    assert "&lt;/script&gt;" in post.content
    assert "<script>" not in post.content


def test_write_concept_page_source_quote_wrapped_in_blockquote_H7(
    tmp_path: Path,
) -> None:
    """NEW-1: source_quote rendered as ``> ...`` blockquote with a
    provenance footer line, eliminating inline-quote ambiguity and the
    `]]` wikilink-escape attack vector."""
    cand = {**_DEMO_CANDIDATE,
            "source_quote": 'said something "smart" today'}
    path, _action = wec.write_concept_page(
        tmp_path, cand, "self-improving-agent",
        date(2026, 5, 27), vault_id="test-vault",
    )
    text = path.read_text(encoding="utf-8")
    assert '> said something "smart" today' in text
    assert "> — [[self-improving-agent]] (L12-L14)" in text
    # v2 inline ``- [[slug]] — "quote"`` format must be gone.
    assert '- [[self-improving-agent]] — "said something' not in text


def test_write_concept_page_invalid_source_span_raises_H7(
    tmp_path: Path,
) -> None:
    """Defense-in-depth: body construction asserts source_span regex
    BEFORE embedding, even if a caller bypassed the upstream validator.
    `source_span='L1-L2)]] [[evil'` → ExtractionParseError(error='INVALID_SOURCE_SPAN')."""
    cand = {**_DEMO_CANDIDATE, "source_span": "L1-L2)]] [[evil"}
    with pytest.raises(wec.ExtractionParseError) as ei:
        wec.write_concept_page(
            tmp_path, cand, "src", date(2026, 5, 27), vault_id="test-vault",
        )
    assert ei.value.error == "INVALID_SOURCE_SPAN"
    assert ei.value.field == "source_span"


def test_write_concept_page_yaml_safety_name_with_yaml_key_H7(
    tmp_path: Path,
) -> None:
    """H-7: `name='key: value'` round-trips through frontmatter without
    YAML injection — the `name` field equals the literal string
    `'key: value'` after re-parsing."""
    cand = {**_DEMO_CANDIDATE, "name": "key: value"}
    path, _action = wec.write_concept_page(
        tmp_path, cand, "src", date(2026, 5, 27), vault_id="test-vault",
    )
    import frontmatter as _fm
    post = _fm.loads(path.read_text(encoding="utf-8"))
    assert post.metadata["name"] == "key: value"


def test_write_concept_page_broken_symlink_target_also_refused_Q15(
    tmp_path: Path,
) -> None:
    """Q15 defense-in-depth: a symlink pointing to a non-existent target
    is ALSO refused. `target.is_symlink()` returns True regardless of
    whether the symlink resolves; the pre-check fires before any
    `target.exists()` follow-through."""
    from scripts.wiki_index.security import PathTraversalError
    concepts_dir = tmp_path / "_concepts"
    concepts_dir.mkdir(parents=True)
    nowhere = tmp_path / "nowhere.md"  # intentionally not created
    target = concepts_dir / "sharpe-ratio.md"
    target.symlink_to(nowhere)
    assert target.is_symlink()
    assert not target.exists()  # broken symlink
    with pytest.raises(PathTraversalError, match="symlink"):
        wec.write_concept_page(
            tmp_path, _DEMO_CANDIDATE, "src", date(2026, 5, 27),
            vault_id="test-vault",
        )


# ============================================================================
# vdd-multi 2026-05-27 regression tests (fixes for CRITICAL + HIGH + MEDIUM)
# ============================================================================


# H-1 / H-3 migrations from 003-v3-11a landed in 003-v3-01 as
# `test_prepare_invalid_source_path_absolute` and `test_prepare_invalid_slug`
# (see top of file). The placeholder TODO markers were removed in 003-v3-01.


# C-1 regression migration landed in 003-v3-03 as
# `test_apply_with_ingest_partial_failure_exits_5_C1` (below).


def test_validate_candidates_schema_rejects_malformed_slug() -> None:
    """M-2: candidate slug with disallowed chars → ExtractionParseError at
    the validation boundary (exit 4) rather than propagating to
    write_concept_page where it would raise PathTraversalError uncaught.

    Renamed in 003-v3-11 to match the validator's v3.1 name
    `_validate_candidates_schema` (was the v2-era name in 003-v3-02)."""
    bad_items = [{"slug": "Hello World",  # space → not kebab
                  "name": "X", "definition": "d",
                  "source_quote": "q", "source_span": "L1-L1",
                  "entity_type": "concept"}]
    with pytest.raises(wec.ExtractionParseError, match="kebab-case"):
        wec._validate_candidates_schema(bad_items)


# Three additional SDK-mock tests REMOVED in 003-v3-11 (M-1 input cap,
# M-1 follow-up BadRequest wrap, L-V3.3 SDK chain-suppression). All three
# exercised the v2 in-skill LLM call which is deleted in bead 003-v3-06.
# The invariants are moot post-v3.1 because there is no LLM call inside
# the Python skill (Decision-17).


def test_check_idempotency_handles_null_row_value(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
) -> None:
    """L-V3.2: defensive NULL check on row["value"]. Even though schema
    declares value TEXT NOT NULL, the gate must not silently match if
    corruption / future schema-change presents a NULL row."""
    # We can't actually INSERT a NULL value due to the NOT NULL constraint,
    # so simulate by mocking the underlying cursor.fetchone() return.
    fake_row = {"value": None}
    fake_conn = mock.MagicMock()
    fake_conn.execute.return_value.fetchone.return_value = fake_row
    fake_repo = mock.MagicMock()
    fake_repo._connect.return_value = fake_conn
    assert wec.check_idempotency(fake_repo, "v", "src", "hash-abc") is False


# ============================================================================
# 003-07b: upsert_extracted_entity (R-37)
# ============================================================================


def test_upsert_extracted_entity_returns_created_for_new_row(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
) -> None:
    """R-37(a): novel slug → 'created' return, row inserted with is_candidate=1."""
    repo = repo_factory()
    repo.apply_schema()  # type: ignore[attr-defined]
    _register_vault(repo, "trade-agents", tmp_path)
    try:
        result = wec.upsert_extracted_entity(
            repo, "trade-agents", _DEMO_CANDIDATE, "src", date(2026, 5, 27),
        )
        assert result == "created"
        row = wec._lookup_entity_row(repo, "trade-agents", "sharpe-ratio")
        assert row is not None
        assert row["is_candidate"] == 1
    finally:
        repo.close()


def test_upsert_extracted_entity_returns_updated_for_existing_candidate(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
) -> None:
    """Re-extraction on existing candidate row → 'updated'."""
    repo = repo_factory()
    repo.apply_schema()  # type: ignore[attr-defined]
    _register_vault(repo, "trade-agents", tmp_path)
    try:
        wec.upsert_extracted_entity(
            repo, "trade-agents", _DEMO_CANDIDATE, "src", date(2026, 5, 26),
        )
        result = wec.upsert_extracted_entity(
            repo, "trade-agents", _DEMO_CANDIDATE, "src", date(2026, 5, 27),
        )
        assert result == "updated"
    finally:
        repo.close()


def test_upsert_extracted_entity_skips_confirmed(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
) -> None:
    """R-37(b) defense-in-depth: existing is_candidate=0 → 'confirmed' return,
    no DB write at the call layer (the SQL guard in 003-07a is the primary)."""
    repo = repo_factory()
    repo.apply_schema()  # type: ignore[attr-defined]
    _register_vault(repo, "trade-agents", tmp_path)
    try:
        # Seed a confirmed entity directly (bypass upsert_extracted_entity).
        repo.upsert_entity(  # type: ignore[attr-defined]
            vault_id="trade-agents", slug="sharpe-ratio", name="Sharpe Ratio",
            type="concept", is_candidate=0,
            canonicalized_by="operator", first_seen="2026-05-01T00:00:00",
            last_updated="2026-05-01T00:00:00",
            file_path="_entities/sharpe-ratio.md",
        )
        # Pre-check: write goes through upsert_entity (now we'll watch it
        # NOT be called by patching).
        with mock.patch.object(repo, "upsert_entity") as mock_upsert:
            result = wec.upsert_extracted_entity(
                repo, "trade-agents", _DEMO_CANDIDATE, "src", date(2026, 5, 27),
            )
        assert result == "confirmed"
        mock_upsert.assert_not_called()
    finally:
        repo.close()


def test_upsert_extracted_entity_canonicalized_by_format(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
) -> None:
    """R-37(c) v3.1: canonicalized_by = 'llm:<orchestrator_id>@<date>'.
    With explicit orchestrator_id='claude-sonnet-4-6' to match the v2
    semantic shape; the new default is 'orchestrator' (Q9-v3.1)."""
    repo = repo_factory()
    repo.apply_schema()  # type: ignore[attr-defined]
    _register_vault(repo, "trade-agents", tmp_path)
    try:
        wec.upsert_extracted_entity(
            repo, "trade-agents", _DEMO_CANDIDATE, "src",
            date(2026, 5, 27), orchestrator_id="claude-sonnet-4-6",
        )
        row = repo._connect().execute(  # type: ignore[attr-defined]
            "SELECT canonicalized_by FROM entities WHERE vault_id=? AND slug=?",
            ("trade-agents", "sharpe-ratio"),
        ).fetchone()
        assert row["canonicalized_by"] == "llm:claude-sonnet-4-6@2026-05-27"
    finally:
        repo.close()


# ============================================================================
# 003-08: upsert_entity_refs + _parse_source_span (R-38, Decision-10)
# ============================================================================


def test_parse_source_span_valid() -> None:
    assert wec._parse_source_span("L12-L18") == (12, 18)
    assert wec._parse_source_span("L5-L5") == (5, 5)
    assert wec._parse_source_span("L1-L9999") == (1, 9999)


def test_parse_source_span_malformed_raises() -> None:
    """Decision-10: format MUST be 'Lstart-Lend' — anything else raises."""
    for bad in ["lines 12-18", "L12 - L18", "12-18", "L12-18", "L-L5"]:
        with pytest.raises(wec.ExtractionParseError, match="source_span"):
            wec._parse_source_span(bad)


def test_parse_source_span_inverted_range_raises() -> None:
    with pytest.raises(wec.ExtractionParseError, match="end before start"):
        wec._parse_source_span("L18-L12")


def test_upsert_entity_refs_parses_line_spans_and_calls_replace_refs() -> None:
    """R-38(a,d,f): both create+mention candidates → refs with parsed spans →
    repo.replace_refs called once with the full list."""
    repo = mock.MagicMock()
    candidates = [
        {"slug": "alpha", "source_quote": "alpha mentioned in text",
         "source_span": "L12-L18", "action": "create"},
        {"slug": "beta", "source_quote": "beta also appears here",
         "source_span": "L5-L5", "action": "mention"},
    ]
    wec.upsert_entity_refs(repo, "trade-agents", "src-page", "_vault_",
                           candidates)
    assert repo.replace_refs.call_count == 1
    kwargs = repo.replace_refs.call_args.kwargs
    assert kwargs["vault_id"] == "trade-agents"
    assert kwargs["page_slug"] == "src-page"
    assert kwargs["page_project"] == "_vault_"
    refs = kwargs["refs"]
    assert len(refs) == 2
    by_slug = {r.entity_slug: r for r in refs}
    assert by_slug["alpha"].line_start == 12
    assert by_slug["alpha"].line_end == 18
    assert by_slug["beta"].line_start == 5
    assert by_slug["beta"].line_end == 5
    # R-38(b,c,e)
    assert all(r.trust_level == "medium" for r in refs)
    assert all(r.ref_type == "mentioned" for r in refs)
    assert all(r.source_quote for r in refs)


def test_upsert_entity_refs_rejects_malformed_span() -> None:
    repo = mock.MagicMock()
    bad = [{"slug": "x", "source_quote": "q", "source_span": "12-18",
            "action": "create"}]
    with pytest.raises(wec.ExtractionParseError):
        wec.upsert_entity_refs(repo, "v", "src", "_vault_", bad)
    repo.replace_refs.assert_not_called()


def test_upsert_entity_refs_empty_list_still_calls_replace_refs() -> None:
    """Empty candidates list still triggers replace_refs (atomic clearing —
    UC-09 Scenario B: a re-extraction with zero candidates wipes stale refs)."""
    repo = mock.MagicMock()
    wec.upsert_entity_refs(repo, "v", "src", "_vault_", [])
    repo.replace_refs.assert_called_once()
    assert repo.replace_refs.call_args.kwargs["refs"] == []


# ============================================================================
# 003-09: check_idempotency + update_idempotency_state (R-39)
# ============================================================================


def _seed_source_state(repo: IndexRepository, vault_id: str, source_kind: str,
                       scope: str, value: str, key: str = "source_hash") -> None:
    conn = repo._connect()  # type: ignore[attr-defined]
    conn.execute(
        "INSERT INTO source_state(vault_id, source_kind, scope, key, value, "
        "updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (vault_id, source_kind, scope, key, value, "2026-05-27T00:00:00"),
    )
    conn.commit()


def test_check_idempotency_no_prior_record(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
) -> None:
    """Empty source_state → False (proceed with extraction)."""
    repo = repo_factory()
    repo.apply_schema()  # type: ignore[attr-defined]
    _register_vault(repo, "trade-agents", tmp_path)
    try:
        assert wec.check_idempotency(repo, "trade-agents", "src", "hash-abc") is False
    finally:
        repo.close()


def test_check_idempotency_hash_match(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
) -> None:
    """R-39(b): recorded hash == current → True (short-circuit)."""
    repo = repo_factory()
    repo.apply_schema()  # type: ignore[attr-defined]
    _register_vault(repo, "trade-agents", tmp_path)
    try:
        _seed_source_state(repo, "trade-agents", "extract-concepts",
                           "src", "hash-abc")
        assert wec.check_idempotency(repo, "trade-agents", "src", "hash-abc") is True
    finally:
        repo.close()


def test_check_idempotency_hash_mismatch(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
) -> None:
    """Body changed → recorded != current → False."""
    repo = repo_factory()
    repo.apply_schema()  # type: ignore[attr-defined]
    _register_vault(repo, "trade-agents", tmp_path)
    try:
        _seed_source_state(repo, "trade-agents", "extract-concepts",
                           "src", "hash-old")
        assert wec.check_idempotency(repo, "trade-agents", "src", "hash-new") is False
    finally:
        repo.close()


def test_check_idempotency_filters_by_source_kind(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
) -> None:
    """Risk R-6: a different source_kind ('enrich') for the same scope must
    NOT match — source_state PK includes source_kind."""
    repo = repo_factory()
    repo.apply_schema()  # type: ignore[attr-defined]
    _register_vault(repo, "trade-agents", tmp_path)
    try:
        _seed_source_state(repo, "trade-agents", "enrich",
                           "src", "hash-abc")
        assert wec.check_idempotency(repo, "trade-agents", "src", "hash-abc") is False
    finally:
        repo.close()


def test_check_idempotency_filters_by_vault_id(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
) -> None:
    """ADR-002 §D1.1: cross-vault hash collision must not short-circuit."""
    repo = repo_factory()
    repo.apply_schema()  # type: ignore[attr-defined]
    _register_vault(repo, "vault-a", tmp_path)
    _register_vault(repo, "vault-b", tmp_path)
    try:
        _seed_source_state(repo, "vault-a", "extract-concepts",
                           "src", "hash-abc")
        # Same hash, different vault → must not match
        assert wec.check_idempotency(repo, "vault-b", "src", "hash-abc") is False
    finally:
        repo.close()


def test_update_idempotency_state_inserts_then_upserts(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
) -> None:
    """First call inserts; subsequent call with new hash UPDATEs the row."""
    repo = repo_factory()
    repo.apply_schema()  # type: ignore[attr-defined]
    _register_vault(repo, "trade-agents", tmp_path)
    try:
        wec.update_idempotency_state(repo, "trade-agents", "src", "hash-v1")
        assert wec.check_idempotency(repo, "trade-agents", "src", "hash-v1") is True

        wec.update_idempotency_state(repo, "trade-agents", "src", "hash-v2")
        assert wec.check_idempotency(repo, "trade-agents", "src", "hash-v2") is True
        # Old hash no longer matches
        assert wec.check_idempotency(repo, "trade-agents", "src", "hash-v1") is False

        # Exactly one row exists for this (vault, kind, scope, key)
        rows = repo._connect().execute(  # type: ignore[attr-defined]
            "SELECT count(*) AS n FROM source_state "
            "WHERE vault_id=? AND source_kind=? AND scope=?",
            ("trade-agents", "extract-concepts", "src"),
        ).fetchone()
        assert rows["n"] == 1
    finally:
        repo.close()


# ============================================================================
# 003-10: build_manifest (R-35)
# ============================================================================


def test_build_manifest_minimal_shape() -> None:
    """R-35(a-e): empty lists still produce a valid v1.1 envelope."""
    m = wec.build_manifest(
        vault_id="vid", source_slug="src", source_hash="abc",
        create_list=[], mention_list=[],
        log_event={"event_type": "ingest", "subject": "S"},
        vault_root=Path("/v"),
    )
    assert m["status"] == "ok"
    assert m["vault_id"] == "vid"
    assert m["source"] == {"slug": "src", "hash": "abc"}
    assert m["written"] == []
    assert m["mentioned"] == []
    assert m["log_event"] == {"event_type": "ingest", "subject": "S"}
    assert m["extraction_summary"]["create_count"] == 0
    assert m["extraction_summary"]["mention_count"] == 0


def test_build_manifest_includes_create_items_as_written() -> None:
    """R-35(c): create_list items → written[] entries with kind='concept'."""
    create = [
        {"slug": "alpha", "name": "Alpha", "file_write_action": "created",
         "entity_action": "created"},
        {"slug": "beta", "name": "Beta", "file_write_action": "unchanged",
         "entity_action": "updated"},
    ]
    m = wec.build_manifest("vid", "src", "abc", create, [], {}, Path("/v"))
    by_slug = {w["slug"]: w for w in m["written"]}
    assert set(by_slug) == {"alpha", "beta"}
    assert by_slug["alpha"]["kind"] == "concept"
    assert by_slug["alpha"]["path"] == "_concepts/alpha.md"
    assert by_slug["alpha"]["action"] == "created"
    assert by_slug["beta"]["action"] == "unchanged"


def test_build_manifest_includes_mentions_for_both_create_and_mention_lists() -> None:
    """create items get entity_action from 007b; mention items get 'mentioned'."""
    create = [{"slug": "alpha", "entity_action": "created",
               "file_write_action": "created"}]
    mention = [{"slug": "bar"}]
    m = wec.build_manifest("vid", "src", "abc", create, mention, {}, Path("/v"))
    by_slug = {x["slug"]: x for x in m["mentioned"]}
    assert by_slug["alpha"]["action"] == "created"
    assert by_slug["bar"]["action"] == "mentioned"


# ============================================================================
# 003-11: dispatch_to_indexer (R-41, Decision-15 + patch-target lock R-2)
# ============================================================================


def test_dispatch_to_indexer_calls_validate_then_index() -> None:
    """R-41(b): validate_manifest called first; index_from_manifest second
    with the SAME manifest dict."""
    fake_summary = {"upserted": [{"path": "x"}], "failed": [],
                    "log_event_id": 1}
    manifest = {"status": "ok", "vault_id": "vid", "written": []}
    with mock.patch(
        "scripts.wiki_skills.wiki_extract_concepts.validate_manifest"
    ) as mv, mock.patch(
        "scripts.wiki_skills.wiki_extract_concepts.index_from_manifest",
        return_value=fake_summary,
    ) as mi:
        result = wec.dispatch_to_indexer(manifest, "vid", Path("/v"), None)
    mv.assert_called_once_with(manifest, "vid", Path("/v"))
    mi.assert_called_once_with(manifest, "vid", Path("/v"), db_path=None)
    assert result is fake_summary


def test_dispatch_to_indexer_propagates_wiki_ingest_error() -> None:
    """R-41(f): validate raises → no index call; WikiIngestError propagates."""
    with mock.patch(
        "scripts.wiki_skills.wiki_extract_concepts.validate_manifest",
        side_effect=wec.WikiIngestError("bad manifest"),
    ), mock.patch(
        "scripts.wiki_skills.wiki_extract_concepts.index_from_manifest"
    ) as mi:
        with pytest.raises(wec.WikiIngestError, match="bad manifest"):
            wec.dispatch_to_indexer({}, "vid", Path("/v"), None)
        mi.assert_not_called()


def test_dispatch_to_indexer_returns_summary_dict() -> None:
    """Summary dict is returned verbatim; no rewrapping."""
    summary = {"upserted": [], "failed": [], "log_event_id": None}
    with mock.patch(
        "scripts.wiki_skills.wiki_extract_concepts.validate_manifest"
    ), mock.patch(
        "scripts.wiki_skills.wiki_extract_concepts.index_from_manifest",
        return_value=summary,
    ):
        result = wec.dispatch_to_indexer({}, "vid", Path("/v"), "db.sqlite")
    assert result == summary


def test_patch_target_lock_at_skill_module() -> None:
    """Risk R-2: prove patching the SKILL module (not the source module)
    intercepts the call inside dispatch_to_indexer."""
    with mock.patch(
        "scripts.wiki_skills.wiki_extract_concepts.index_from_manifest",
        return_value={"upserted": [], "failed": []},
    ) as patched, mock.patch(
        "scripts.wiki_skills.wiki_extract_concepts.validate_manifest"
    ):
        wec.dispatch_to_indexer({}, "vid", Path("/v"), None)
    assert patched.called, (
        "Patching at 'scripts.wiki_skills.wiki_extract_concepts.index_from_manifest' "
        "MUST intercept dispatch_to_indexer's call — otherwise the module-top "
        "import has been demoted to lazy in-function and the patch target lock "
        "is broken (PLAN.md Risk R-2)."
    )


# ============================================================================
# 003-12: main() integration — `--ingest` end-to-end mock
# ============================================================================


# End-to-end --ingest regression migration landed in 003-v3-03 as
# `test_apply_with_ingest_end_to_end_mocked_dispatch` and
# `test_apply_without_ingest_emits_manifest_only` (see "003-v3-03: apply
# subcommand" section).


def test_build_manifest_passes_validate_manifest(tmp_path: Path) -> None:
    """R-35(h) CRITICAL: the manifest this skill emits MUST be consumable
    by `_manifest_consumer.validate_manifest` — proves the Decision-15
    in-process dispatch contract holds end-to-end."""
    # Pre-create the concept page so validate_manifest's R-26 guard finds it.
    concepts_dir = tmp_path / "_concepts"
    concepts_dir.mkdir()
    (concepts_dir / "alpha.md").write_text("# Alpha\n", encoding="utf-8")

    create = [{"slug": "alpha", "name": "Alpha",
               "file_write_action": "created", "entity_action": "created"}]
    m = wec.build_manifest("trade-agents", "src-page", "deadbeef",
                           create, [],
                           {"event_type": "ingest", "subject": "Src Page"},
                           tmp_path)
    from scripts.wiki_skills._manifest_consumer import validate_manifest
    validate_manifest(m, "trade-agents", tmp_path)


# ============================================================================
# 003-v3-03: apply subcommand (R-31, R-33′, R-35, R-37, R-38, R-39, R-41, R-42)
# ============================================================================


def _seed_apply_vault(
    repo_factory: Callable[[], IndexRepository],
    tmp_path: Path,
    source_body: str = "---\ntype: summary\n---\nThe Sharpe Ratio measures excess return.\n",
    vault_id: str = "trade-agents",
) -> tuple[Path, str, str]:
    """Helper: spin up a vault with a single source page + registered DB row.

    Returns (vault_root, db_path, source_hash) for the seeded source body.
    """
    import hashlib as _hashlib
    import shutil as _sh

    vault_root = tmp_path / "vault"
    sources_dir = vault_root / "_sources"
    sources_dir.mkdir(parents=True)
    src = sources_dir / "sample-doc.md"
    src.write_text(source_body, encoding="utf-8")
    source_hash = _hashlib.sha256(source_body.encode("utf-8")).hexdigest()

    db_path = str(tmp_path / "test.db")
    bootstrap = repo_factory()
    bootstrap.apply_schema()  # type: ignore[attr-defined]
    _register_vault(bootstrap, vault_id, tmp_path)
    # Pre-register the source page so the page_entity_refs FK succeeds when
    # apply() upserts refs keyed on (vault_id, source_slug, '_vault_').
    bootstrap._connect().execute(  # type: ignore[attr-defined]
        "INSERT INTO pages(vault_id, slug, project, type, title, file_path, "
        "date, last_modified, file_hash, frontmatter_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (vault_id, "sample-doc", "_vault_", "summary",
         "Sample Doc", "_sources/sample-doc.md",
         "2026-05-28", "2026-05-28T00:00:00", "seed", "{}"),
    )
    bootstrap._connect().commit()  # type: ignore[attr-defined]
    bootstrap.close()
    src_db = list(tmp_path.glob("wiki-*.db"))[0]
    _sh.copy(src_db, db_path)
    return vault_root, db_path, source_hash


def _make_apply_args(
    *,
    vault: str,
    vault_root: Path,
    source_page: str,
    source_hash: str,
    db_path: str | None = None,
    ingest: bool = False,
    candidates_file: Path | None = None,
    candidates_stdin: bool = False,
) -> argparse.Namespace:
    """Build an argparse.Namespace matching the `apply` subparser surface."""
    return argparse.Namespace(
        cmd="apply",
        vault=vault, vault_root=vault_root,
        source_page=source_page, db_path=db_path,
        source_hash=source_hash, ingest=ingest,
        candidates_file=candidates_file,
        candidates_stdin=candidates_stdin,
    )


_APPLY_DEMO_CANDIDATE = {
    "slug": "sharpe-ratio",
    "name": "Sharpe Ratio",
    "definition": "Risk-adjusted return measure.",
    "source_quote": "The Sharpe Ratio measures excess return.",
    "source_span": "L3-L3",
    "entity_type": "concept",
}


def test_apply_canned_json_happy(
    repo_factory: Callable[[], IndexRepository],
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Canned 1-candidate JSON on stdin → exit 0, concept page written,
    manifest envelope emitted."""
    import io
    import json as _json
    vault_root, db_path, source_hash = _seed_apply_vault(repo_factory, tmp_path)

    payload = _json.dumps([_APPLY_DEMO_CANDIDATE]).encode("utf-8")
    monkeypatch.setattr(
        "sys.stdin",
        type("FakeStdin", (), {"buffer": io.BytesIO(payload)})(),
    )

    args = _make_apply_args(
        vault="trade-agents", vault_root=vault_root,
        source_page="sample-doc", source_hash=source_hash,
        db_path=db_path, candidates_stdin=True,
    )
    rc = wec.apply(args)
    assert rc == 0
    manifest = _json.loads(capsys.readouterr().out)
    assert manifest["status"] == "ok"
    assert manifest["vault_id"] == "trade-agents"
    assert (vault_root / "_concepts" / "sharpe-ratio.md").is_file()


def test_apply_stdin_vs_file_mutex(
    tmp_path: Path,
) -> None:
    """Passing BOTH --candidates-stdin AND --candidates-file fires the
    argparse mutex group → SystemExit(2)."""
    cf = tmp_path / "cands.json"
    cf.write_text("[]", encoding="utf-8")
    with pytest.raises(SystemExit) as ei:
        wec._build_parser_v3().parse_args([
            "apply",
            "--vault", "X",
            "--vault-root", str(tmp_path),
            "--source-page", "sample-doc",
            "--source-hash", _VALID_HASH,
            "--candidates-stdin",
            "--candidates-file", str(cf),
        ])
    assert ei.value.code == 2


def test_apply_source_hash_mismatch_exits_2_SOURCE_CHANGED_H1(
    repo_factory: Callable[[], IndexRepository],
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H-1, Q5: source edited between prepare and apply → exit 2
    SOURCE_CHANGED_DURING_EXTRACTION. Envelope must NOT echo the new
    source body content (CWE-117 guard)."""
    import io
    import json as _json
    vault_root, db_path, original_hash = _seed_apply_vault(
        repo_factory, tmp_path,
        source_body="---\ntype: summary\n---\noriginal body\n",
    )
    # Mutate source on disk so apply's recomputed hash differs.
    src = vault_root / "_sources" / "sample-doc.md"
    NEW_SOURCE_MARKER = "EDITED_AFTER_PREPARE_SECRET_TOKEN"
    src.write_text(
        f"---\ntype: summary\n---\nedited body {NEW_SOURCE_MARKER}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "sys.stdin",
        type("FakeStdin", (), {
            "buffer": io.BytesIO(_json.dumps([_APPLY_DEMO_CANDIDATE]).encode("utf-8"))
        })(),
    )

    args = _make_apply_args(
        vault="trade-agents", vault_root=vault_root,
        source_page="sample-doc", source_hash=original_hash,
        db_path=db_path, candidates_stdin=True,
    )
    rc = wec.apply(args)
    assert rc == 2
    payload = _json.loads(capsys.readouterr().out)
    assert payload["error"] == "SOURCE_CHANGED_DURING_EXTRACTION"
    # CWE-117 invariant: the new source content marker MUST NOT appear in
    # any envelope field.
    for v in payload.values():
        assert NEW_SOURCE_MARKER not in str(v), (
            f"CWE-117 leak: new source content surfaced in envelope: {payload!r}"
        )


def test_apply_candidates_file_outside_vault_exits_2_INVALID_CANDIDATES_PATH_H5(
    repo_factory: Callable[[], IndexRepository],
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """H-5: --candidates-file resolving outside the vault → exit 2
    INVALID_CANDIDATES_PATH. Envelope emits the path string but NEVER the
    file content (CWE-117 guard)."""
    import json as _json
    vault_root, db_path, source_hash = _seed_apply_vault(repo_factory, tmp_path)
    # Candidates file outside the vault: peer of vault_root under tmp_path.
    outside = tmp_path / "outside-the-vault.json"
    OUTSIDE_MARKER = "SECRET_FROM_OUTSIDE_FILE_CONTENT"
    outside.write_text(_json.dumps([{"x": OUTSIDE_MARKER}]), encoding="utf-8")

    args = _make_apply_args(
        vault="trade-agents", vault_root=vault_root,
        source_page="sample-doc", source_hash=source_hash,
        db_path=db_path, candidates_file=outside,
    )
    rc = wec.apply(args)
    assert rc == 2
    payload = _json.loads(capsys.readouterr().out)
    assert payload["error"] == "INVALID_CANDIDATES_PATH"
    # CWE-117 invariant: file content MUST NOT be in the envelope.
    for v in payload.values():
        assert OUTSIDE_MARKER not in str(v), (
            f"CWE-117 leak: outside-vault file content surfaced: {payload!r}"
        )


def test_apply_candidates_file_too_large_exits_4_H6(
    repo_factory: Callable[[], IndexRepository],
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """H-6: candidates file > _MAX_CANDIDATES_BYTES (1 MiB) → exit 4
    CANDIDATES_TOO_LARGE BEFORE any read or parse."""
    import json as _json
    vault_root, db_path, source_hash = _seed_apply_vault(repo_factory, tmp_path)
    # Write a file inside the vault that exceeds the cap by 1 byte.
    big = vault_root / "_sources" / "huge-candidates.json"
    big.write_bytes(b"x" * (wec._MAX_CANDIDATES_BYTES + 1))

    args = _make_apply_args(
        vault="trade-agents", vault_root=vault_root,
        source_page="sample-doc", source_hash=source_hash,
        db_path=db_path, candidates_file=big,
    )
    rc = wec.apply(args)
    assert rc == 4
    payload = _json.loads(capsys.readouterr().out)
    assert payload["error"] == "CANDIDATES_TOO_LARGE"


def test_apply_with_ingest_end_to_end_mocked_dispatch(
    repo_factory: Callable[[], IndexRepository],
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression migration from 003-v3-11a (originally
    test_main_with_ingest_calls_dispatch_and_emits_combined).

    --ingest path: dispatch returns `{"failed": [], ...}` → envelope is
    `{extraction, index}` shape; dispatch called once with vault_id."""
    import io
    import json as _json
    vault_root, db_path, source_hash = _seed_apply_vault(repo_factory, tmp_path)
    fake_summary = {"upserted": [{"path": "_concepts/sharpe-ratio.md"}],
                    "failed": [], "log_event_id": 42}

    monkeypatch.setattr(
        "sys.stdin",
        type("FakeStdin", (), {
            "buffer": io.BytesIO(_json.dumps([_APPLY_DEMO_CANDIDATE]).encode("utf-8"))
        })(),
    )

    with mock.patch(
        "scripts.wiki_skills.wiki_extract_concepts.dispatch_to_indexer",
        return_value=fake_summary,
    ) as mock_dispatch:
        args = _make_apply_args(
            vault="trade-agents", vault_root=vault_root,
            source_page="sample-doc", source_hash=source_hash,
            db_path=db_path, candidates_stdin=True, ingest=True,
        )
        rc = wec.apply(args)

    assert rc == 0
    envelope = _json.loads(capsys.readouterr().out)
    assert set(envelope.keys()) == {"extraction", "index"}, (
        f"--ingest envelope must wrap as {{extraction, index}}; got {envelope!r}"
    )
    assert envelope["index"] is fake_summary or envelope["index"] == fake_summary
    mock_dispatch.assert_called_once()


def test_apply_without_ingest_emits_manifest_only(
    repo_factory: Callable[[], IndexRepository],
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression migration from 003-v3-11a (originally
    test_main_without_ingest_emits_manifest_only).

    Without --ingest: envelope is the bare manifest (NOT wrapped in
    {extraction, index}); dispatch_to_indexer was NOT called."""
    import io
    import json as _json
    vault_root, db_path, source_hash = _seed_apply_vault(repo_factory, tmp_path)

    monkeypatch.setattr(
        "sys.stdin",
        type("FakeStdin", (), {
            "buffer": io.BytesIO(_json.dumps([_APPLY_DEMO_CANDIDATE]).encode("utf-8"))
        })(),
    )

    with mock.patch(
        "scripts.wiki_skills.wiki_extract_concepts.dispatch_to_indexer",
    ) as mock_dispatch:
        args = _make_apply_args(
            vault="trade-agents", vault_root=vault_root,
            source_page="sample-doc", source_hash=source_hash,
            db_path=db_path, candidates_stdin=True, ingest=False,
        )
        rc = wec.apply(args)

    assert rc == 0
    envelope = _json.loads(capsys.readouterr().out)
    # Bare manifest, not wrapped in extraction/index.
    assert envelope.get("status") == "ok"
    assert "extraction" not in envelope
    assert "index" not in envelope
    mock_dispatch.assert_not_called()


def test_apply_with_ingest_partial_failure_exits_5_C1(
    repo_factory: Callable[[], IndexRepository],
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C-1 regression migration from 003-v3-11a (originally
    test_main_ingest_partial_failure_does_not_update_source_state).

    On --ingest partial failure (summary['failed'] non-empty): exit 5
    PARTIAL_INDEX_FAILURE, and update_idempotency_state MUST NOT be
    called so the next run retries."""
    import io
    import json as _json
    vault_root, db_path, source_hash = _seed_apply_vault(repo_factory, tmp_path)
    failing_summary = {"upserted": [], "failed": ["sample-concept"],
                       "log_event_id": None}

    monkeypatch.setattr(
        "sys.stdin",
        type("FakeStdin", (), {
            "buffer": io.BytesIO(_json.dumps([_APPLY_DEMO_CANDIDATE]).encode("utf-8"))
        })(),
    )

    with mock.patch(
        "scripts.wiki_skills.wiki_extract_concepts.dispatch_to_indexer",
        return_value=failing_summary,
    ), mock.patch(
        "scripts.wiki_skills.wiki_extract_concepts.update_idempotency_state",
    ) as mock_update_state:
        args = _make_apply_args(
            vault="trade-agents", vault_root=vault_root,
            source_page="sample-doc", source_hash=source_hash,
            db_path=db_path, candidates_stdin=True, ingest=True,
        )
        rc = wec.apply(args)

    assert rc == 5
    envelope = _json.loads(capsys.readouterr().out)
    assert envelope["error"] == "PARTIAL_INDEX_FAILURE"
    assert envelope["action"] == "partial"
    # C-1 invariant: source_state MUST NOT have been touched.
    mock_update_state.assert_not_called()


def _read_canonicalized_by(db_path: str, vault_id: str, slug: str) -> str | None:
    """Helper for orchestrator-id tests: read entities.canonicalized_by
    via a fresh sqlite3 connection (the apply call already closed its repo)."""
    import sqlite3 as _sqlite3
    conn = _sqlite3.connect(db_path)
    conn.row_factory = _sqlite3.Row
    try:
        row = conn.execute(
            "SELECT canonicalized_by FROM entities "
            "WHERE vault_id=? AND slug=?",
            (vault_id, slug),
        ).fetchone()
        return row["canonicalized_by"] if row else None
    finally:
        conn.close()


def test_apply_orchestrator_id_valid_populates_canonicalized_by_H8(
    repo_factory: Callable[[], IndexRepository],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H-8: --orchestrator-id 'claude-opus-4-7' → entities.canonicalized_by
    = 'llm:claude-opus-4-7@<today>'."""
    import io
    import json as _json
    from datetime import date as _date
    vault_root, db_path, source_hash = _seed_apply_vault(repo_factory, tmp_path)

    monkeypatch.setattr(
        "sys.stdin",
        type("FakeStdin", (), {
            "buffer": io.BytesIO(_json.dumps([_APPLY_DEMO_CANDIDATE]).encode("utf-8"))
        })(),
    )

    args = _make_apply_args(
        vault="trade-agents", vault_root=vault_root,
        source_page="sample-doc", source_hash=source_hash,
        db_path=db_path, candidates_stdin=True,
    )
    args.orchestrator_id = "claude-opus-4-7"
    rc = wec.apply(args)
    assert rc == 0
    canonicalized = _read_canonicalized_by(db_path, "trade-agents", "sharpe-ratio")
    assert canonicalized == f"llm:claude-opus-4-7@{_date.today().isoformat()}"


def test_apply_orchestrator_id_invalid_regex_argparse_error_H8(
    tmp_path: Path,
) -> None:
    """H-8: --orchestrator-id 'with spaces' fails the argparse-level regex
    → SystemExit(2) (NOT exit 4 EXTRACTION_PARSE_ERROR)."""
    with pytest.raises(SystemExit) as ei:
        wec._build_parser_v3().parse_args([
            "apply",
            "--vault", "X",
            "--vault-root", str(tmp_path),
            "--source-page", "sample-doc",
            "--source-hash", _VALID_HASH,
            "--candidates-stdin",
            "--orchestrator-id", "with spaces",
        ])
    assert ei.value.code == 2


def test_apply_orchestrator_id_default_is_orchestrator_H8(
    repo_factory: Callable[[], IndexRepository],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H-8 / Q9-v3.1: omitting --orchestrator-id yields the literal
    'orchestrator' default (honest unknown beats hallucinated specific)."""
    import io
    import json as _json
    from datetime import date as _date
    vault_root, db_path, source_hash = _seed_apply_vault(repo_factory, tmp_path)

    monkeypatch.setattr(
        "sys.stdin",
        type("FakeStdin", (), {
            "buffer": io.BytesIO(_json.dumps([_APPLY_DEMO_CANDIDATE]).encode("utf-8"))
        })(),
    )

    args = _make_apply_args(
        vault="trade-agents", vault_root=vault_root,
        source_page="sample-doc", source_hash=source_hash,
        db_path=db_path, candidates_stdin=True,
    )
    # No orchestrator_id set on args → apply uses getattr default.
    rc = wec.apply(args)
    assert rc == 0
    canonicalized = _read_canonicalized_by(db_path, "trade-agents", "sharpe-ratio")
    assert canonicalized == f"llm:orchestrator@{_date.today().isoformat()}"


# ============================================================================
# 003-v3-17: adversarial envelope-shape parametrized test
#            (CWE-117 / CWE-209 regression guard for every R-42 sub-envelope)
# ============================================================================


_CANARY = "SECRET_LEAK_CANARY_xyzzy_777"
_FORBIDDEN_ENVELOPE_KEYS = frozenset({"content", "value", "raw", "received"})


def _stdin_with_payload(payload_bytes: bytes) -> Any:
    """Build a FakeStdin object exposing `.buffer` for monkeypatching."""
    import io
    return type("FakeStdin", (), {"buffer": io.BytesIO(payload_bytes)})()


def _capture_apply(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
    args: argparse.Namespace,
) -> tuple[int, dict[str, Any]]:
    """Invoke wec.apply(args) and return (rc, parsed-stdout-envelope)."""
    import json as _json
    rc = wec.apply(args)
    payload = _json.loads(capsys.readouterr().out)
    assert isinstance(payload, dict)
    return rc, payload


def _trigger_source_not_found(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> tuple[int, dict[str, Any]]:
    """SOURCE_NOT_FOUND: candidates JSON carries canary in a definition; the
    apply call fails at source resolution BEFORE schema validation, so the
    canary must never reach the envelope."""
    import json as _json
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    cand = {**_APPLY_DEMO_CANDIDATE, "definition": _CANARY}
    monkeypatch.setattr("sys.stdin",
                        _stdin_with_payload(_json.dumps([cand]).encode("utf-8")))
    args = _make_apply_args(
        vault="v", vault_root=vault_root,
        source_page="missing-doc", source_hash=_VALID_HASH,
        candidates_stdin=True,
    )
    return _capture_apply(monkeypatch, capsys, args)


def _trigger_invalid_source_path(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> tuple[int, dict[str, Any]]:
    """INVALID_SOURCE_PATH: absolute --source-page. Canary in candidates."""
    import json as _json
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    cand = {**_APPLY_DEMO_CANDIDATE, "definition": _CANARY}
    monkeypatch.setattr("sys.stdin",
                        _stdin_with_payload(_json.dumps([cand]).encode("utf-8")))
    args = _make_apply_args(
        vault="v", vault_root=vault_root,
        source_page="/etc/somewhere", source_hash=_VALID_HASH,
        candidates_stdin=True,
    )
    return _capture_apply(monkeypatch, capsys, args)


def _trigger_invalid_source_slug(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> tuple[int, dict[str, Any]]:
    """INVALID_SOURCE_SLUG: dotted filename. Canary in candidates."""
    import json as _json
    vault_root = tmp_path / "vault"
    sources_dir = vault_root / "_sources"
    sources_dir.mkdir(parents=True)
    bad = sources_dir / "Foo.Bar.md"
    bad.write_text("body", encoding="utf-8")
    cand = {**_APPLY_DEMO_CANDIDATE, "definition": _CANARY}
    monkeypatch.setattr("sys.stdin",
                        _stdin_with_payload(_json.dumps([cand]).encode("utf-8")))
    args = _make_apply_args(
        vault="v", vault_root=vault_root,
        source_page="Foo.Bar", source_hash=_VALID_HASH,
        candidates_stdin=True,
    )
    return _capture_apply(monkeypatch, capsys, args)


def _trigger_source_too_large(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> tuple[int, dict[str, Any]]:
    """SOURCE_TOO_LARGE: 10MiB+ source body containing canary."""
    import json as _json
    vault_root = tmp_path / "vault"
    sources_dir = vault_root / "_sources"
    sources_dir.mkdir(parents=True)
    big = sources_dir / "huge-doc.md"
    # Write canary at the start, then pad to exceed cap.
    pad = b"x" * (wec._MAX_SOURCE_BODY_BYTES + 1 - len(_CANARY.encode("utf-8")))
    big.write_bytes(_CANARY.encode("utf-8") + pad)
    cand = {**_APPLY_DEMO_CANDIDATE}
    monkeypatch.setattr("sys.stdin",
                        _stdin_with_payload(_json.dumps([cand]).encode("utf-8")))
    args = _make_apply_args(
        vault="v", vault_root=vault_root,
        source_page="huge-doc", source_hash=_VALID_HASH,
        candidates_stdin=True,
    )
    return _capture_apply(monkeypatch, capsys, args)


def _trigger_source_changed(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> tuple[int, dict[str, Any]]:
    """SOURCE_CHANGED_DURING_EXTRACTION: mutate body to include canary."""
    import json as _json
    vault_root, db_path, original_hash = _seed_apply_vault(
        repo_factory, tmp_path,
        source_body="---\ntype: summary\n---\noriginal\n",
    )
    src = vault_root / "_sources" / "sample-doc.md"
    src.write_text(
        f"---\ntype: summary\n---\nmutated with {_CANARY}\n",
        encoding="utf-8",
    )
    cand = {**_APPLY_DEMO_CANDIDATE}
    monkeypatch.setattr("sys.stdin",
                        _stdin_with_payload(_json.dumps([cand]).encode("utf-8")))
    args = _make_apply_args(
        vault="trade-agents", vault_root=vault_root,
        source_page="sample-doc", source_hash=original_hash,
        db_path=db_path, candidates_stdin=True,
    )
    return _capture_apply(monkeypatch, capsys, args)


def _trigger_invalid_candidates_path(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> tuple[int, dict[str, Any]]:
    """INVALID_CANDIDATES_PATH: candidates file outside vault, canary in body."""
    import json as _json
    vault_root, db_path, source_hash = _seed_apply_vault(repo_factory, tmp_path)
    outside = tmp_path / "outside-the-vault.json"
    outside.write_text(_json.dumps([{"sensitive": _CANARY}]), encoding="utf-8")
    args = _make_apply_args(
        vault="trade-agents", vault_root=vault_root,
        source_page="sample-doc", source_hash=source_hash,
        db_path=db_path, candidates_file=outside,
    )
    return _capture_apply(monkeypatch, capsys, args)


def _trigger_candidates_too_large(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> tuple[int, dict[str, Any]]:
    """CANDIDATES_TOO_LARGE: >1 MiB candidates file containing canary."""
    vault_root, db_path, source_hash = _seed_apply_vault(repo_factory, tmp_path)
    big = vault_root / "_sources" / "huge-candidates.json"
    payload = _CANARY.encode("utf-8") + b"x" * (
        wec._MAX_CANDIDATES_BYTES + 1 - len(_CANARY.encode("utf-8")))
    big.write_bytes(payload)
    args = _make_apply_args(
        vault="trade-agents", vault_root=vault_root,
        source_page="sample-doc", source_hash=source_hash,
        db_path=db_path, candidates_file=big,
    )
    return _capture_apply(monkeypatch, capsys, args)


def _trigger_extraction_parse_error(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> tuple[int, dict[str, Any]]:
    """EXTRACTION_PARSE_ERROR: malformed JSON containing canary."""
    vault_root, db_path, source_hash = _seed_apply_vault(repo_factory, tmp_path)
    malformed = f"[{{ this is {_CANARY} not valid json".encode("utf-8")
    monkeypatch.setattr("sys.stdin", _stdin_with_payload(malformed))
    args = _make_apply_args(
        vault="trade-agents", vault_root=vault_root,
        source_page="sample-doc", source_hash=source_hash,
        db_path=db_path, candidates_stdin=True,
    )
    return _capture_apply(monkeypatch, capsys, args)


def _trigger_count_oob(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> tuple[int, dict[str, Any]]:
    """CANDIDATE_COUNT_OUT_OF_BOUNDS: 26 candidates, one carries canary."""
    import json as _json
    vault_root, db_path, source_hash = _seed_apply_vault(repo_factory, tmp_path)
    cands = []
    for i in range(26):
        slug = f"cand-{i}"
        defn = _CANARY if i == 0 else f"definition {i}"
        cands.append({**_APPLY_DEMO_CANDIDATE, "slug": slug, "definition": defn})
    monkeypatch.setattr("sys.stdin",
                        _stdin_with_payload(_json.dumps(cands).encode("utf-8")))
    args = _make_apply_args(
        vault="trade-agents", vault_root=vault_root,
        source_page="sample-doc", source_hash=source_hash,
        db_path=db_path, candidates_stdin=True,
    )
    return _capture_apply(monkeypatch, capsys, args)


def _trigger_field_too_long(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> tuple[int, dict[str, Any]]:
    """FIELD_TOO_LONG: 3000-char definition starting with canary."""
    import json as _json
    vault_root, db_path, source_hash = _seed_apply_vault(repo_factory, tmp_path)
    huge_def = _CANARY + "x" * (3000 - len(_CANARY))
    cand = {**_APPLY_DEMO_CANDIDATE, "definition": huge_def}
    monkeypatch.setattr("sys.stdin",
                        _stdin_with_payload(_json.dumps([cand]).encode("utf-8")))
    args = _make_apply_args(
        vault="trade-agents", vault_root=vault_root,
        source_page="sample-doc", source_hash=source_hash,
        db_path=db_path, candidates_stdin=True,
    )
    return _capture_apply(monkeypatch, capsys, args)


def _trigger_unknown_field(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> tuple[int, dict[str, Any]]:
    """UNKNOWN_FIELD: extra key with canary as VALUE (key name is benign)."""
    import json as _json
    vault_root, db_path, source_hash = _seed_apply_vault(repo_factory, tmp_path)
    cand = {**_APPLY_DEMO_CANDIDATE, "extra": _CANARY}
    monkeypatch.setattr("sys.stdin",
                        _stdin_with_payload(_json.dumps([cand]).encode("utf-8")))
    args = _make_apply_args(
        vault="trade-agents", vault_root=vault_root,
        source_page="sample-doc", source_hash=source_hash,
        db_path=db_path, candidates_stdin=True,
    )
    return _capture_apply(monkeypatch, capsys, args)


def _trigger_quote_not_in_body(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> tuple[int, dict[str, Any]]:
    """FIELD_QUOTE_NOT_IN_BODY: source_quote contains canary, not in body."""
    import json as _json
    vault_root, db_path, source_hash = _seed_apply_vault(repo_factory, tmp_path)
    cand = {**_APPLY_DEMO_CANDIDATE,
            "source_quote": f"hallucinated phrase {_CANARY}"}
    monkeypatch.setattr("sys.stdin",
                        _stdin_with_payload(_json.dumps([cand]).encode("utf-8")))
    args = _make_apply_args(
        vault="trade-agents", vault_root=vault_root,
        source_page="sample-doc", source_hash=source_hash,
        db_path=db_path, candidates_stdin=True,
    )
    return _capture_apply(monkeypatch, capsys, args)


_ENVELOPE_TRIGGERS: list[tuple[str, int, Any]] = [
    ("SOURCE_NOT_FOUND", 2, _trigger_source_not_found),
    ("INVALID_SOURCE_PATH", 2, _trigger_invalid_source_path),
    ("INVALID_SOURCE_SLUG", 2, _trigger_invalid_source_slug),
    ("SOURCE_TOO_LARGE", 2, _trigger_source_too_large),
    ("SOURCE_CHANGED_DURING_EXTRACTION", 2, _trigger_source_changed),
    ("INVALID_CANDIDATES_PATH", 2, _trigger_invalid_candidates_path),
    ("CANDIDATES_TOO_LARGE", 4, _trigger_candidates_too_large),
    ("EXTRACTION_PARSE_ERROR", 4, _trigger_extraction_parse_error),
    ("CANDIDATE_COUNT_OUT_OF_BOUNDS", 4, _trigger_count_oob),
    ("FIELD_TOO_LONG", 4, _trigger_field_too_long),
    ("UNKNOWN_FIELD", 4, _trigger_unknown_field),
    ("FIELD_QUOTE_NOT_IN_BODY", 4, _trigger_quote_not_in_body),
]


@pytest.mark.parametrize("envelope_code,expected_exit,trigger", _ENVELOPE_TRIGGERS)
def test_apply_error_envelopes_never_echo_content(
    envelope_code: str,
    expected_exit: int,
    trigger: Any,
    repo_factory: Callable[[], IndexRepository],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """R-42 / CWE-117 / CWE-209 regression guard: every error sub-envelope
    from R-42(c) + R-42(d) v3.1 (a) emits the documented exit code,
    (b) contains NONE of the forbidden keys `{content, value, raw,
    received}`, and (c) does NOT echo the canary OFFENDING string in
    any field value.

    Future regressions where a developer accidentally adds `value` or
    `raw` to an envelope (or starts echoing the offending payload back)
    are caught here BEFORE reaching production.
    """
    rc, env = trigger(repo_factory, tmp_path, monkeypatch, capsys)
    assert rc == expected_exit, (
        f"{envelope_code} expected exit {expected_exit}, got {rc} "
        f"with envelope {env!r}"
    )
    assert env.get("error") == envelope_code, (
        f"{envelope_code} envelope did not match: {env!r}"
    )
    leaked_keys = _FORBIDDEN_ENVELOPE_KEYS & set(env.keys())
    assert not leaked_keys, (
        f"{envelope_code} envelope contains forbidden keys {leaked_keys}: "
        f"{env!r}"
    )
    for k, v in env.items():
        if isinstance(v, str):
            assert _CANARY not in v, (
                f"CWE-117 leak: {envelope_code} envelope echoes canary "
                f"in field {k!r}: {v!r}"
            )


def test_prepare_source_page_escape_blocked_by_H1_layout_invariant(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """H-1 (vdd-multi 2026-05-28): `--source-page _sources/../_concepts/foo.md`
    used to resolve inside the vault and silently honor any `.md` file.
    The new `_sources/` layout invariant rejects it with
    INVALID_SOURCE_PATH instead."""
    import json as _json
    vault_root = tmp_path / "vault"
    sources_dir = vault_root / "_sources"
    concepts_dir = vault_root / "_concepts"
    sources_dir.mkdir(parents=True)
    concepts_dir.mkdir()
    # Seed a concept page (the file the attacker is trying to read).
    (concepts_dir / "sharpe-ratio.md").write_text("# Sharpe Ratio\n",
                                                  encoding="utf-8")
    args = _make_prepare_args(
        "trade-agents", vault_root, "_sources/../_concepts/sharpe-ratio.md",
    )
    rc = wec.prepare(args)
    assert rc == 2
    payload = _json.loads(capsys.readouterr().out)
    assert payload["error"] == "INVALID_SOURCE_PATH"


def test_apply_candidates_file_fifo_rejected_H2(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """H-2 (vdd-multi 2026-05-28): a FIFO/named-pipe at the
    --candidates-file path has stat().st_size==0 (bypassing the cap)
    and would let `read_bytes()` accumulate unbounded data. The new
    `is_file()` guard rejects non-regular files with
    INVALID_CANDIDATES_PATH BEFORE any read."""
    import json as _json
    vault_root, db_path, source_hash = _seed_apply_vault(repo_factory, tmp_path)
    fifo = vault_root / "_sources" / "evil.fifo"
    os.mkfifo(fifo)
    assert not fifo.is_file()
    args = _make_apply_args(
        vault="trade-agents", vault_root=vault_root,
        source_page="sample-doc", source_hash=source_hash,
        db_path=db_path, candidates_file=fifo,
    )
    rc = wec.apply(args)
    assert rc == 2
    payload = _json.loads(capsys.readouterr().out)
    assert payload["error"] == "INVALID_CANDIDATES_PATH"
    assert "not a regular file" in payload.get("reason", "")


def test_apply_update_idempotency_state_failure_emits_partial_H3(
    repo_factory: Callable[[], IndexRepository], tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H-3 (vdd-multi 2026-05-28): if `update_idempotency_state` raises
    a sqlite OperationalError (DB locked, disk full) AFTER pages/entities
    are committed, the operator gets a clean IDEMPOTENCY_UPDATE_FAILED
    envelope at exit 5 instead of an uncaught traceback that produces
    split-brain (success on stdout, traceback on stderr, exit 1)."""
    import io
    import json as _json
    import sqlite3
    vault_root, db_path, source_hash = _seed_apply_vault(repo_factory, tmp_path)
    monkeypatch.setattr(
        "sys.stdin",
        type("FakeStdin", (), {
            "buffer": io.BytesIO(_json.dumps([_APPLY_DEMO_CANDIDATE]).encode("utf-8"))
        })(),
    )

    def _boom(*a: Any, **kw: Any) -> None:
        raise sqlite3.OperationalError("simulated database is locked")

    with mock.patch(
        "scripts.wiki_skills.wiki_extract_concepts.update_idempotency_state",
        side_effect=_boom,
    ):
        args = _make_apply_args(
            vault="trade-agents", vault_root=vault_root,
            source_page="sample-doc", source_hash=source_hash,
            db_path=db_path, candidates_stdin=True, ingest=False,
        )
        rc = wec.apply(args)
    assert rc == 5
    payload = _json.loads(capsys.readouterr().out)
    assert payload["error"] == "IDEMPOTENCY_UPDATE_FAILED"
    assert payload["action"] == "partial"
    # Pages SHOULD still be on disk (commit happened before the failure)
    assert (vault_root / "_concepts" / "sharpe-ratio.md").is_file()


def test_sanitize_definition_blocks_javascript_link_injection_H4(
    tmp_path: Path,
) -> None:
    """H-4 (vdd-multi 2026-05-28): the previous denylist sanitizer let
    `[click](javascript:alert(1))` through. The new text-only allowlist
    backslash-escapes `[` and `]` so markdown does not render the link
    at all (rendered output: literal `[click](javascript:alert(1))`)."""
    cand = {**_DEMO_CANDIDATE,
            "definition": "Click here: [click](javascript:alert(1))"}
    path, _action = wec.write_concept_page(
        tmp_path, cand, "src", date(2026, 5, 27), vault_id="test-vault",
    )
    text = path.read_text(encoding="utf-8")
    # The brackets must be escaped (markdown literal); the URL must NOT
    # form an active link.
    assert "\\[click\\]" in text
    # And the original unescaped `[click](javascript:` MUST NOT appear.
    assert "[click](javascript:" not in text


def test_sanitize_definition_blocks_html_entity_smuggling_H4(
    tmp_path: Path,
) -> None:
    """H-4: HTML entity smuggling `&#x3C;script&#x3E;` previously
    bypassed the `<tag>` regex; the new sanitizer escapes `&` first
    so the entity itself renders as literal `&#x3C;`."""
    cand = {**_DEMO_CANDIDATE,
            "definition": "Smuggled: &#x3C;script&#x3E;alert(1)&#x3C;/script&#x3E;"}
    path, _action = wec.write_concept_page(
        tmp_path, cand, "src", date(2026, 5, 27), vault_id="test-vault",
    )
    text = path.read_text(encoding="utf-8")
    # The `&` got HTML-escaped to `&amp;` so the entity renders as
    # literal `&#x3C;`, not as `<`.
    assert "&amp;#x3C;" in text
    # And the active form `<script>` must NOT have been reconstructed.
    assert "<script>" not in text


def test_sanitize_definition_blocks_obsidian_wikilink_injection_H4(
    tmp_path: Path,
) -> None:
    """H-4: hostile `[[evil-target]]` in definition would otherwise
    render as an active Obsidian wikilink; the new sanitizer escapes
    `[` and `]` so it renders as literal text."""
    cand = {**_DEMO_CANDIDATE,
            "definition": "See [[evil-target]] for malicious context."}
    path, _action = wec.write_concept_page(
        tmp_path, cand, "src", date(2026, 5, 27), vault_id="test-vault",
    )
    text = path.read_text(encoding="utf-8")
    assert "\\[\\[evil-target\\]\\]" in text
    assert "[[evil-target]]" not in text


def test_sanitize_definition_blocks_code_span_injection_H4(
    tmp_path: Path,
) -> None:
    """H-4: `` `dataview LIST FROM \"\"` `` would otherwise execute as
    an Obsidian dataview block; backtick escape neutralizes it."""
    cand = {**_DEMO_CANDIDATE,
            "definition": "Try `dataview LIST FROM \"\"` to enumerate."}
    path, _action = wec.write_concept_page(
        tmp_path, cand, "src", date(2026, 5, 27), vault_id="test-vault",
    )
    text = path.read_text(encoding="utf-8")
    assert "\\`dataview" in text


def test_sanitize_source_quote_blocks_html_injection_H4(
    tmp_path: Path,
) -> None:
    """H-4: source_quote was previously embedded verbatim in the
    blockquote (only the `>` prefix protected against block-level
    markdown). HTML and wikilink injection slipped through. New
    sanitizer covers source_quote via the shared text helper."""
    cand = {**_DEMO_CANDIDATE,
            "source_quote": "The Sharpe Ratio measures excess return."}
    # Mutate to include an HTML injection attempt — the upstream M-5
    # quote-in-body check is bypassed in write_concept_page so we test
    # the sanitizer in isolation via the helper.
    sanitized = wec._sanitize_markdown_text(
        "Hostile <img src=x onerror=alert(1)> quote with [[wikilink]]"
    )
    assert "&lt;img" in sanitized
    assert "<img" not in sanitized
    assert "\\[\\[wikilink\\]\\]" in sanitized


def test_validate_candidates_schema_rejects_non_list_L1() -> None:
    """L-1 (vdd-multi 2026-05-28): top-level type-guard. If a future
    caller bypasses `_load_candidates` and passes a dict directly,
    the validator now emits a clear EXTRACTION_PARSE_ERROR envelope
    saying 'payload is not a list' rather than per-item confusion."""
    with pytest.raises(wec.ExtractionParseError) as ei:
        wec._validate_candidates_schema({"oops": "I'm a dict"})  # type: ignore[arg-type]
    assert ei.value.error == "EXTRACTION_PARSE_ERROR"
    assert ei.value.reason is not None
    assert "expected JSON array" in ei.value.reason


def test_validate_candidates_schema_rejects_null_slug_L1() -> None:
    """L-1: a `null` slug used to fall through to `re.match("None")`
    yielding a misleading 'kebab-case regex' envelope. The new type-
    check loop emits 'slug is not a string' first."""
    bad = [{"slug": None, "name": "X", "definition": "d",
            "source_quote": "q", "source_span": "L1-L1",
            "entity_type": "concept"}]
    with pytest.raises(wec.ExtractionParseError) as ei:
        wec._validate_candidates_schema(bad)  # type: ignore[list-item]
    assert ei.value.field == "slug"
    assert ei.value.reason is not None
    assert "is NoneType" in ei.value.reason


def test_validate_candidates_schema_rejects_unicode_digits_in_span_L2() -> None:
    """L-2 (vdd-multi 2026-05-28): `\\d` with re.ASCII rejects Arabic-
    Indic digits like `L١-L٢` that would otherwise pass and (per
    `int()` Unicode-digit coercion) produce confusing line numbers."""
    bad = [{"slug": "x", "name": "X", "definition": "d",
            "source_quote": "q", "source_span": "L١-L٢",
            "entity_type": "concept"}]
    with pytest.raises(wec.ExtractionParseError) as ei:
        wec._validate_candidates_schema(bad)
    assert ei.value.field == "source_span"


def test_apply_invalid_source_hash_library_caller_defense_C1(
    repo_factory: Callable[[], IndexRepository],
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C-1 belt-and-braces: library/test callers that construct args
    directly (bypassing argparse) still get INVALID_SOURCE_HASH instead
    of a misleading SOURCE_CHANGED_DURING_EXTRACTION when they pass a
    short/non-hex value. Closes the bypass that the argparse `type=`
    validator would otherwise leave open for non-CLI consumers."""
    import io
    import json as _json
    vault_root, db_path, _ = _seed_apply_vault(repo_factory, tmp_path)
    monkeypatch.setattr(
        "sys.stdin",
        type("FakeStdin", (), {
            "buffer": io.BytesIO(_json.dumps([_APPLY_DEMO_CANDIDATE]).encode("utf-8"))
        })(),
    )
    args = _make_apply_args(
        vault="trade-agents", vault_root=vault_root,
        source_page="sample-doc",
        source_hash="not-a-real-hash",  # would-be argparse-rejected
        db_path=db_path, candidates_stdin=True,
    )
    rc = wec.apply(args)
    assert rc == 2
    payload = _json.loads(capsys.readouterr().out)
    assert payload["error"] == "INVALID_SOURCE_HASH"


def test_apply_validator_unknown_field_exits_4_with_structured_envelope(
    repo_factory: Callable[[], IndexRepository],
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H-9: candidates carrying an extra key → exit 4 UNKNOWN_FIELD with
    structured `{error, field, reason}` envelope. The offending value
    MUST NOT appear anywhere in the envelope (CWE-117 guard)."""
    import io
    import json as _json
    vault_root, db_path, source_hash = _seed_apply_vault(repo_factory, tmp_path)
    LEAK_MARKER = "if_this_leaks_we_have_a_cwe117"
    evil_cand = {**_APPLY_DEMO_CANDIDATE, "evil": LEAK_MARKER}

    monkeypatch.setattr(
        "sys.stdin",
        type("FakeStdin", (), {
            "buffer": io.BytesIO(_json.dumps([evil_cand]).encode("utf-8"))
        })(),
    )

    args = _make_apply_args(
        vault="trade-agents", vault_root=vault_root,
        source_page="sample-doc", source_hash=source_hash,
        db_path=db_path, candidates_stdin=True,
    )
    rc = wec.apply(args)
    assert rc == 4
    payload = _json.loads(capsys.readouterr().out)
    assert payload["error"] == "UNKNOWN_FIELD"
    assert payload["field"] == "evil"
    # CWE-117: the offending VALUE must never appear.
    for v in payload.values():
        assert LEAK_MARKER not in str(v), (
            f"CWE-117 leak: offending value surfaced in envelope: {payload!r}"
        )
