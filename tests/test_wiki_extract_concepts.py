"""Tests for `scripts.wiki_skills.wiki_extract_concepts`.

Bead 003-01 lands the argparse surface + 9 helper stubs.
Bead 003-03 lands `load_known_entities` (raw SQL on `repo._connect()`).
Downstream beads (003-04..003-11) add the real test surface as each
helper's body fills in.
"""
from __future__ import annotations

import argparse
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


def test_argparse_apply_subparser_exists() -> None:
    """`apply` subparser accepts the write-path flags including --source-hash
    (REQUIRED) and the candidates mutex group.
    """
    args = wec._build_parser_v3().parse_args([
        "apply",
        "--vault", "X",
        "--vault-root", "/tmp",
        "--source-page", "sample-doc",
        "--source-hash", "deadbeef",
        "--candidates-stdin",
    ])
    assert args.cmd == "apply"
    assert args.source_hash == "deadbeef"
    assert args.candidates_stdin is True
    assert args.candidates_file is None


# test_main_dispatches_to_prepare_stub REMOVED in 003-v3-01:
# the prepare() stub was replaced with the real implementation, so the
# NotImplementedError assertion no longer holds. Real prepare-surface tests
# live below (test_prepare_*).


def test_main_dispatches_to_apply_stub() -> None:
    """`main(["apply", ...])` reaches the apply() stub which raises
    NotImplementedError naming the bead that fills it in (003-v3-03).
    """
    with pytest.raises(NotImplementedError, match="task-003-v3-03"):
        wec.main([
            "apply",
            "--vault", "X",
            "--vault-root", "/tmp",
            "--source-page", "sample-doc",
            "--source-hash", "deadbeef",
            "--candidates-stdin",
        ])


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
    bead lands, the corresponding assertion is removed. 003-03 (load_known_entities)
    and 003-04 (extract_concepts_llm) already landed."""
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


# ============================================================================
# 003-04: extract_concepts_llm (R-33, R-34)
# ============================================================================


def _llm_response(text: str) -> mock.Mock:
    """Build a mock anthropic.Messages.create() response with .content[0].text."""
    block = mock.Mock()
    block.text = text
    resp = mock.Mock()
    resp.content = [block]
    return resp


_VALID_LLM_JSON = (
    '['
    '{"slug":"sharpe-ratio","name":"Sharpe Ratio","definition":"Risk-adjusted return.",'
    '"source_quote":"The Sharpe ratio measures excess return per unit of volatility.",'
    '"source_span":"L12-L14","entity_type":"concept"},'
    '{"slug":"hermes","name":"Hermes Agent","definition":"Self-improving trading framework.",'
    '"source_quote":"Hermes is the self-improving trading agent we built on the framework.",'
    '"source_span":"L20-L22","entity_type":"product"}'
    ']'
)


def test_build_prompt_includes_known_concepts() -> None:
    """R-34(a): known-concepts JSON embedded in the LLM prompt."""
    known = [{"slug": "alpha", "name": "Alpha", "type": "concept",
              "aliases": ["A1"]}]
    prompt = wec._build_extraction_prompt("Source body here.", known)
    assert '"slug": "alpha"' in prompt
    assert '"name": "Alpha"' in prompt
    assert "Source body here." in prompt
    assert "ONLY a JSON array" in prompt


def test_extract_concepts_llm_parses_valid_json() -> None:
    """R-33(d): valid JSON parses into a list of dicts with all required fields."""
    fake_response = _llm_response(_VALID_LLM_JSON)
    with mock.patch("anthropic.Anthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create.return_value = fake_response

        result = wec.extract_concepts_llm(
            "body", [], model="claude-sonnet-4-6", max_tokens=4096,
        )

    assert len(result) == 2
    assert result[0]["slug"] == "sharpe-ratio"
    assert result[1]["entity_type"] == "product"


def test_extract_concepts_llm_raises_on_malformed_json() -> None:
    """R-33(e): malformed JSON → ExtractionParseError → exit 4."""
    fake_response = _llm_response("not json {")
    with mock.patch("anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = fake_response
        with pytest.raises(wec.ExtractionParseError, match="non-JSON"):
            wec.extract_concepts_llm("body", [])


def test_extract_concepts_llm_raises_on_schema_violation() -> None:
    """Decision-10: source_span must match Lstart-Lend; otherwise ExtractionParseError."""
    bad = (
        '[{"slug":"x","name":"X","definition":"d",'
        '"source_quote":"q","source_span":"lines 12-14","entity_type":"concept"}]'
    )
    with mock.patch("anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = _llm_response(bad)
        with pytest.raises(wec.ExtractionParseError, match="source_span"):
            wec.extract_concepts_llm("body", [])


def test_extract_concepts_llm_raises_on_api_error() -> None:
    """R-42(c): anthropic.APIConnectionError → LLMUnavailableError → exit 3."""
    import anthropic
    with mock.patch("anthropic.Anthropic") as MockClient:
        # APIConnectionError requires a request object — use a Mock to satisfy it.
        MockClient.return_value.messages.create.side_effect = (
            anthropic.APIConnectionError(request=mock.Mock())
        )
        with pytest.raises(wec.LLMUnavailableError):
            wec.extract_concepts_llm("body", [])


def test_extract_concepts_llm_uses_temperature_zero() -> None:
    """R-33(b): every API call passes temperature=0."""
    fake_response = _llm_response(_VALID_LLM_JSON)
    with mock.patch("anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = fake_response
        wec.extract_concepts_llm("body", [], model="claude-sonnet-4-6", max_tokens=2048)

    call_kwargs = MockClient.return_value.messages.create.call_args.kwargs
    assert call_kwargs["temperature"] == 0
    assert call_kwargs["model"] == "claude-sonnet-4-6"
    assert call_kwargs["max_tokens"] == 2048


def test_extract_concepts_llm_caps_max_tokens_at_4096() -> None:
    """R-33(c): max_tokens > 4096 is clamped."""
    fake_response = _llm_response(_VALID_LLM_JSON)
    with mock.patch("anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = fake_response
        wec.extract_concepts_llm("body", [], max_tokens=8192)
    assert MockClient.return_value.messages.create.call_args.kwargs["max_tokens"] == 4096


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


def test_write_concept_page_skips_existing_file(tmp_path: Path) -> None:
    """R-36(e): existing file is NOT overwritten; H-2 fix: action='unchanged'."""
    concepts_dir = tmp_path / "_concepts"
    concepts_dir.mkdir(parents=True)
    target = concepts_dir / "sharpe-ratio.md"
    target.write_text("OPERATOR_MARKER\n", encoding="utf-8")
    returned_path, returned_action = wec.write_concept_page(
        tmp_path, _DEMO_CANDIDATE, "src", date(2026, 5, 27),
        vault_id="test-vault",
    )
    assert returned_path == target
    assert returned_action == "unchanged"
    assert target.read_text(encoding="utf-8") == "OPERATOR_MARKER\n"


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
# vdd-multi 2026-05-27 regression tests (fixes for CRITICAL + HIGH + MEDIUM)
# ============================================================================


# H-1 / H-3 migrations from 003-v3-11a landed in 003-v3-01 as
# `test_prepare_invalid_source_path_absolute` and `test_prepare_invalid_slug`
# (see top of file). The placeholder TODO markers were removed in 003-v3-01.


# DELETED in 003-v3-11a (Option A green-throughout invariant).
# Regression intent: C-1 CRITICAL — --ingest dispatch partial failure must NOT
# update source_state so operator can retry without hash-short-circuit.
# Migrated to: 003-v3-03 `test_apply_with_ingest_partial_failure_exits_5_C1`.


def test_extract_concepts_llm_rejects_oversized_input() -> None:
    """M-1: source body exceeding _MAX_SOURCE_BODY_CHARS → ExtractionParseError
    BEFORE the SDK is called."""
    big_body = "x" * (wec._MAX_SOURCE_BODY_CHARS + 1)
    with mock.patch("anthropic.Anthropic") as MockClient:
        with pytest.raises(wec.ExtractionParseError, match="too large"):
            wec.extract_concepts_llm(big_body, [], max_tokens=4096)
    # SDK MUST NOT be instantiated when the input is rejected
    MockClient.assert_not_called()


def test_validate_extraction_schema_rejects_malformed_slug() -> None:
    """M-2: LLM-returned slug with disallowed chars → ExtractionParseError at
    the extraction boundary (exit 4) rather than propagating to
    write_concept_page where it would raise PathTraversalError uncaught."""
    bad_items = [{"slug": "Hello World",  # space → not kebab
                  "name": "X", "definition": "d",
                  "source_quote": "q", "source_span": "L1-L1",
                  "entity_type": "concept"}]
    with pytest.raises(wec.ExtractionParseError, match="kebab-case"):
        wec._validate_extraction_schema(bad_items)


def test_extract_concepts_llm_wraps_bad_request_error() -> None:
    """M-1 follow-up: anthropic.BadRequestError → LLMUnavailableError (exit 3),
    not an uncaught crash."""
    import anthropic
    with mock.patch("anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.side_effect = (
            anthropic.BadRequestError(
                message="prompt too long", response=mock.Mock(status_code=400),
                body={},
            )
        )
        with pytest.raises(wec.LLMUnavailableError, match="BadRequestError"):
            wec.extract_concepts_llm("body", [], max_tokens=4096)


def test_extract_concepts_llm_suppresses_sdk_exception_chain() -> None:
    """L-V3.3 (CWE-209): LLMUnavailableError MUST NOT propagate the SDK
    exception via __cause__ — `raise ... from None` strips the chain so
    request_id / partial headers from the SDK can never surface to a
    future __cause__ consumer."""
    import anthropic
    with mock.patch("anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.side_effect = (
            anthropic.APIConnectionError(request=mock.Mock())
        )
        try:
            wec.extract_concepts_llm("body", [])
        except wec.LLMUnavailableError as raised:
            assert raised.__cause__ is None, (
                "L-V3.3 broken: SDK exception chain leaked via __cause__"
            )
            assert raised.__context__ is not None, (
                "Python sets __context__ implicitly inside except blocks; "
                "this is benign — but __cause__ being None confirms `from None`"
            )


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
    """R-37(c): canonicalized_by = 'llm:<model>@<date>' format."""
    repo = repo_factory()
    repo.apply_schema()  # type: ignore[attr-defined]
    _register_vault(repo, "trade-agents", tmp_path)
    try:
        cand = {**_DEMO_CANDIDATE, "model": "claude-sonnet-4-6"}
        wec.upsert_extracted_entity(
            repo, "trade-agents", cand, "src", date(2026, 5, 27),
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


# DELETED in 003-v3-11a (Option A green-throughout invariant).
# Regression intent: end-to-end via main([--ingest]) — mock LLM + dispatch,
# exercise real argparse + source-page resolution + idempotency + try/except,
# verify {extraction, index} envelope shape and log_event_id wiring.
# Migrated to: 003-v3-03 `test_apply_with_ingest_end_to_end_mocked_dispatch`.

# DELETED in 003-v3-11a (Option A green-throughout invariant).
# Regression intent: end-to-end via main() WITHOUT --ingest — mock LLM,
# verify bare manifest shape (NOT {extraction, index} wrapper),
# verify dispatch_to_indexer NOT called.
# Migrated to: 003-v3-03 `test_apply_without_ingest_emits_manifest_only`.


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
