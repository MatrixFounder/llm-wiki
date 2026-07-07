"""Tests for scripts/wiki_index/policy.py (TASK 049 / R-1).

Precedence matrix (Q-049-1), ladder validation, CWE-209 message shape,
effective_level null/absent semantics.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.wiki_index.policy import (
    BUILTIN_LEVELS,
    PolicyError,
    PolicyProfile,
    allowed_levels,
    effective_level,
    load_vault_policy,
    parse_policy_block,
    resolve_policy,
)


def _vault(tmp_path: Path, policy_yaml: str | None) -> Path:
    """Minimal vault: WIKI_SCHEMA.md with an optional policy: block."""
    root = tmp_path / "vault"
    root.mkdir()
    fm = ("---\nname: WIKI_SCHEMA\nvault_id: policy-test\n"
          "schema_version: '2.0'\nlanguage: en\nlayout: flat\n")
    if policy_yaml is not None:
        fm += policy_yaml
    fm += "---\n\n# schema\n"
    (root / "WIKI_SCHEMA.md").write_text(fm)
    return root


_BLOCK = ("policy:\n  levels: [public, internal, restricted]\n"
          "  default_level: public\n")


# =============================================================================
# parse_policy_block
# =============================================================================

def test_parse_minimal_block():
    levels, default, audience = parse_policy_block(
        {"levels": ["low", "high"]})
    assert levels == ("low", "high")
    assert default == "low"          # derived: lowest level
    assert audience is None


def test_parse_full_block():
    levels, default, audience = parse_policy_block(
        {"levels": ["a", "b", "c"], "default_level": "b",
         "default_audience": "c"})
    assert (levels, default, audience) == (("a", "b", "c"), "b", "c")


@pytest.mark.parametrize("raw", [
    "not-a-dict",
    {"levels": []},
    {"levels": "public"},
    {"levels": ["public"] * 17},
    {"levels": ["public", "public"]},
    {"levels": ["Public"]},                      # uppercase
    {"levels": ["public"], "default_level": "internal"},
    {"levels": ["public"], "default_audience": "internal"},
    {"levels": ["public"], "unknown_key": 1},
    {"levels": [None]},
    {"levels": ["x" * 17]},                      # over the 16-char cap
])
def test_parse_rejects_malformed(raw):
    with pytest.raises(PolicyError):
        parse_policy_block(raw)


def test_error_messages_never_echo_values():
    """CWE-209/117: the offending VALUE must not appear in the message."""
    secret = "s3cr3t_LEVEL_value"
    with pytest.raises(PolicyError) as exc:
        parse_policy_block({"levels": [secret.upper()]})
    assert secret.upper() not in str(exc.value)
    with pytest.raises(PolicyError) as exc:
        resolve_policy(None, secret.upper())
    assert secret.upper() not in str(exc.value)


# =============================================================================
# resolve_policy — the Q-049-1 precedence matrix
# =============================================================================

def test_off_no_flag_no_block(tmp_path):
    root = _vault(tmp_path, None)
    assert resolve_policy(root, None) is None


def test_off_block_without_default_audience(tmp_path):
    root = _vault(tmp_path, _BLOCK)
    assert resolve_policy(root, None) is None


def test_active_declared_default_audience(tmp_path):
    root = _vault(tmp_path, _BLOCK + "  default_audience: internal\n")
    p = resolve_policy(root, None)
    assert p == PolicyProfile(("public", "internal", "restricted"),
                              "public", "internal")


def test_active_declared_default_audience_at_highest_level(tmp_path):
    """Q-049-1: a declared audience ALWAYS activates — no max-level=OFF case."""
    root = _vault(tmp_path, _BLOCK + "  default_audience: restricted\n")
    p = resolve_policy(root, None)
    assert p is not None and p.audience == "restricted"


def test_flag_beats_default_audience(tmp_path):
    root = _vault(tmp_path, _BLOCK + "  default_audience: restricted\n")
    p = resolve_policy(root, "public")
    assert p is not None and p.audience == "public"


def test_flag_without_block_uses_builtin_ladder(tmp_path):
    root = _vault(tmp_path, None)
    p = resolve_policy(root, "internal")
    assert p == PolicyProfile(BUILTIN_LEVELS, "public", "internal")


def test_flag_without_vault_root_uses_builtin_ladder():
    p = resolve_policy(None, "restricted")
    assert p == PolicyProfile(BUILTIN_LEVELS, "public", "restricted")


def test_flag_not_in_vault_ladder_rejected(tmp_path):
    root = _vault(tmp_path, "policy:\n  levels: [lo, hi]\n")
    with pytest.raises(PolicyError) as exc:
        resolve_policy(root, "internal")
    assert exc.value.field == "audience"


def test_flag_bad_shape_rejected():
    with pytest.raises(PolicyError) as exc:
        resolve_policy(None, "NOT-A-LEVEL!")
    assert exc.value.field == "audience"


def test_malformed_block_raises_never_silent_off(tmp_path):
    root = _vault(tmp_path, "policy:\n  levels: [public, public]\n")
    with pytest.raises(PolicyError):
        resolve_policy(root, None)
    with pytest.raises(PolicyError):
        resolve_policy(root, "public")


def test_unreadable_vault_means_no_block(tmp_path):
    """Outside any vault (no WIKI_SCHEMA.md) → block=None → flag uses builtin."""
    empty = tmp_path / "not-a-vault"
    empty.mkdir()
    assert load_vault_policy(empty) is None
    assert resolve_policy(empty, None) is None
    p = resolve_policy(empty, "public")
    assert p is not None and p.levels == BUILTIN_LEVELS


# =============================================================================
# allowed_levels / effective_level
# =============================================================================

def test_allowed_levels_prefix():
    p = PolicyProfile(("a", "b", "c"), "a", "b")
    assert allowed_levels(p) == ["a", "b"]
    assert allowed_levels(PolicyProfile(("a", "b", "c"), "a", "c")) == ["a", "b", "c"]
    assert allowed_levels(PolicyProfile(("a", "b", "c"), "a", "a")) == ["a"]


@pytest.mark.parametrize("fm,expected", [
    (None, "public"),
    ({}, "public"),
    ({"classification": None}, "public"),          # null ≡ absent
    ({"classification": "restricted"}, "restricted"),
    ({"classification": "not-in-any-ladder"}, "not-in-any-ladder"),  # fail-closed downstream
])
def test_effective_level(fm, expected):
    assert effective_level(fm, "public") == expected


@pytest.mark.parametrize("val", ["", 7, True, ["restricted"], {"x": 1}])
def test_effective_level_non_null_non_ladder_fails_closed(val):
    """Aligned with the SQL predicate: an empty string or a non-string value
    must NOT fall back to the default (that would let a `classification: 3`
    page leak through the Python get_page gates while the SQL path excludes
    it). It resolves to a value that can never be in a ladder."""
    lvl = effective_level({"classification": val}, "public")
    assert lvl != "public"
    assert lvl not in ("public", "internal", "restricted")
