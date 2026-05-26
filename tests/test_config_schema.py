"""
JSON Schema validation tests for config/wiki-config.schema.yaml (task-001-02).

Covers TC-E2E-01, TC-UNIT-01, TC-UNIT-02 from task-001-02:
- Valid root config passes validation.
- Missing vault_id rejected.
- Malformed vault_id (multiple cases) rejected.

Schema is JSON Schema 2020-12 (ADR-002 §D1.1 — vault_id REQUIRED, no fallback).

The `VaultId` pattern MUST round-trip with the SQLite CHECK constraint in
sql/wiki-index-v2.sql — that invariant is verified indirectly here (same
malformed values must be rejected by both layers; the SQLite side is covered
by tests/test_schema_smoke.py::test_unit_02_vault_id_check_rejects_malformed).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator, ValidationError

SCHEMA_PATH = Path(__file__).parent.parent / "config" / "wiki-config.schema.yaml"
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "configs"


@pytest.fixture(scope="module")
def schema():
    """Load and return the parsed YAML schema."""
    return yaml.safe_load(SCHEMA_PATH.read_text())


@pytest.fixture(scope="module")
def validator(schema):
    """Construct a Draft 2020-12 validator over the WikiRootConfig $def.

    The schema document is a library of $defs (no top-level oneOf — that would
    silently accept root configs missing vault_id by routing them to the
    override branch). config_loader (task-001-13) will pick the right $defs
    entry based on file scope; tests do the same.
    """
    Draft202012Validator.check_schema(schema)  # AC: schema doc itself is valid
    root_schema = {**schema, "$ref": "#/$defs/WikiRootConfig"}
    return Draft202012Validator(root_schema)


@pytest.fixture(scope="module")
def override_validator(schema):
    """Validator for WikiProjectOverride (`.wiki.yaml`) scope."""
    override_schema = {**schema, "$ref": "#/$defs/WikiProjectOverride"}
    return Draft202012Validator(override_schema)


@pytest.fixture
def valid_root_config():
    """Load the valid root config fixture."""
    return yaml.safe_load((FIXTURES_DIR / "valid-root-config.yaml").read_text())


# =============================================================================
# AC: jsonschema.Draft202012Validator.check_schema does not raise
# =============================================================================


def test_schema_itself_is_valid_2020_12(schema):
    """The schema document itself is well-formed JSON Schema 2020-12."""
    Draft202012Validator.check_schema(schema)  # raises if not


# =============================================================================
# TC-E2E-01 — fixture passes validation
# =============================================================================


def test_e2e_01_valid_root_config_passes(validator, valid_root_config):
    """A well-formed root config (vault_id + language + layout + paths) passes."""
    errors = sorted(validator.iter_errors(valid_root_config), key=lambda e: e.path)
    assert errors == [], "valid fixture should pass; got errors: " + "; ".join(
        f"{list(e.path)}: {e.message}" for e in errors
    )


# =============================================================================
# TC-UNIT-01 — vault_id REQUIRED (missing → rejected)
# =============================================================================


def test_unit_01_missing_vault_id_rejected(validator, valid_root_config):
    """vault_id REQUIRED per ADR-002 §D1.1; absence → ValidationError."""
    cfg = dict(valid_root_config)
    cfg.pop("vault_id")
    errors = list(validator.iter_errors(cfg))
    assert errors, "expected ValidationError when vault_id is missing"
    # At least one error must mention vault_id (oneOf branches both fail —
    # WikiRootConfig requires vault_id; WikiProjectOverride forbids it but the
    # config still doesn't match the override schema because it's not at that
    # scope. The composite error must reference vault_id somewhere.)
    messages = " ".join(e.message for e in errors)
    assert "vault_id" in messages, (
        f"error message should mention vault_id; got: {messages}"
    )


# =============================================================================
# TC-UNIT-02 — malformed vault_id rejected (must mirror SQLite CHECK)
# =============================================================================


@pytest.mark.parametrize(
    "bad_vault_id, reason",
    [
        ("ab", "too short (2 chars)"),
        ("1bad", "leading digit"),
        ("AB", "uppercase + too short"),
        ("Trade-Agents", "uppercase letter"),
        ("foo--bar", "double hyphen"),
        ("trade-agents-", "trailing hyphen"),
        ("-trade-agents", "leading hyphen"),
        ("a" * 33, "exceeds 32-char length cap"),
    ],
)
def test_unit_02_malformed_vault_id_rejected(validator, valid_root_config, bad_vault_id, reason):
    """Each malformed vault_id raises ValidationError (round-trip with SQLite CHECK)."""
    cfg = dict(valid_root_config)
    cfg["vault_id"] = bad_vault_id
    errors = list(validator.iter_errors(cfg))
    assert errors, (
        f"expected ValidationError for vault_id={bad_vault_id!r} ({reason})"
    )


@pytest.mark.parametrize(
    "good_vault_id",
    ["_global_", "trade-agents", "abc", "a1b", "a-b-c", "obsidian-llm-wiki", "x-y-z"],
)
def test_unit_02b_valid_vault_id_accepted(validator, valid_root_config, good_vault_id):
    """Valid vault_ids (incl. _global_ sentinel) pass — mirrors SQLite CHECK accepts."""
    cfg = dict(valid_root_config)
    cfg["vault_id"] = good_vault_id
    errors = list(validator.iter_errors(cfg))
    assert errors == [], (
        f"expected vault_id={good_vault_id!r} to validate; got: "
        + "; ".join(e.message for e in errors)
    )


# =============================================================================
# Project override: vault_id NOT allowed at .wiki.yaml scope
# =============================================================================


def test_project_override_rejects_vault_id(override_validator):
    """An .wiki.yaml override scope must not carry vault_id (`not.required`)."""
    cfg = {"vault_id": "trade-agents", "language": "en"}
    errors = list(override_validator.iter_errors(cfg))
    assert errors, "override scope must not allow vault_id (vault identity belongs to root)"


def test_project_override_accepts_no_vault_id(override_validator):
    """An override config WITHOUT vault_id passes the override scope."""
    cfg = {"language": "en", "paths": {"sources": "_sources/"}}
    errors = list(override_validator.iter_errors(cfg))
    assert errors == [], (
        "override config without vault_id should pass; got: "
        + "; ".join(e.message for e in errors)
    )


# =============================================================================
# Layout enum + Language enum sanity
# =============================================================================


def test_layout_enum_rejects_unknown(validator, valid_root_config):
    """layout must be 'flat' or 'per-project'; anything else rejected."""
    cfg = dict(valid_root_config)
    cfg["layout"] = "hierarchical"  # not in enum
    errors = list(validator.iter_errors(cfg))
    assert errors, "unknown layout value should be rejected"


def test_language_enum_rejects_unknown(validator, valid_root_config):
    """language must be in the supported set."""
    cfg = dict(valid_root_config)
    cfg["language"] = "klingon"
    errors = list(validator.iter_errors(cfg))
    assert errors, "unknown language code should be rejected"
