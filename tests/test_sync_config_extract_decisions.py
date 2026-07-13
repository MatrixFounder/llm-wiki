"""TASK 063-00 — the `extract_decisions:` cascading block (loader half).

The block lives in `config/sync-config.schema.yaml` (NOT in `layouts/*.yaml`) for
one concrete reason, and it is the operator requirement this bead exists to meet:
`wiki-config`'s `set`/`unset` **and its web editor** render ONLY from the sync
schema (`_uimodel.py`, `_server.py`). A folder-name knob in the layout grammar
would never appear in the config editor at all.

This file pins the LOADER contract. The RENDERED surfaces — the thing the
operator actually sees — are pinned in
`tests/test_wiki_config_extract_decisions_surfaces.py`, because asserting the UI
*model* instead of the *rendered output* is precisely the TASK-061 bug shape
(`FieldSpec.description` lived in the model and rendered in `serve` alone).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import scripts.wiki_skills._resummarize as _resummarize
from scripts.wiki_index.sync_config import (
    ExtractDecisionsDirs,
    SyncConfigError,
    load_extract_decisions_raw,
    load_sync_config,
)
from scripts.wiki_skills._resummarize import resolve_extract_decisions


def _sync_yaml(root: Path, text: str) -> None:
    (root / ".wiki").mkdir(parents=True, exist_ok=True)
    (root / ".wiki" / "sync.yaml").write_text(text, encoding="utf-8")


def test_absent_block_is_none(tmp_path: Path) -> None:
    """No `extract_decisions:` anywhere ⇒ `None`, NOT a defaulted-and-disabled
    config. The distinction is load-bearing: `None` means "this vault never opted
    in", which is what every existing vault is — back-compat by byte-identity."""
    _sync_yaml(tmp_path, "tag_namespace: wiki\n")
    assert load_sync_config(tmp_path).extract_decisions is None
    assert load_extract_decisions_raw(tmp_path) is None


def test_defaults_are_the_cybos_names(tmp_path: Path) -> None:
    """`{enabled: true}` with NO `dirs:` block ⇒ the cybos names. A vault on a
    layout whose read globs already cover `decisions/**` works with a one-line
    config."""
    _sync_yaml(tmp_path, "extract_decisions:\n  enabled: true\n")
    cfg = load_sync_config(tmp_path).extract_decisions
    assert cfg is not None
    assert cfg.enabled is True
    assert cfg.dirs == ExtractDecisionsDirs(
        decision="decisions", requirement="requirements", risk="risks"
    )


def test_enabled_is_off_by_default(tmp_path: Path) -> None:
    """A `dirs:`-only block does NOT switch the rail on. Naming the folders is
    not consenting to auto-dispatch (R-063-3′(c))."""
    _sync_yaml(tmp_path, "extract_decisions:\n  dirs:\n    risk: Риски\n")
    cfg = load_sync_config(tmp_path).extract_decisions
    assert cfg is not None
    assert cfg.enabled is False


def test_partial_dirs_override_keeps_the_other_defaults(tmp_path: Path) -> None:
    """Overriding ONE class does not blank the other two — the dataclass defaults
    fill them. (The per-FOLDER cascade is 063-01; this is the single-level case.)
    Cyrillic is a first-class folder name: the operator's live vault is Russian."""
    _sync_yaml(
        tmp_path,
        "extract_decisions:\n  enabled: true\n  dirs:\n    decision: 'Решения'\n",
    )
    cfg = load_sync_config(tmp_path).extract_decisions
    assert cfg is not None
    assert cfg.dirs.decision == "Решения"
    assert (cfg.dirs.requirement, cfg.dirs.risk) == ("requirements", "risks")


def test_unknown_class_key_is_exit_6(tmp_path: Path) -> None:
    """A class the v1 roster does not carry (`incident`) — or a typo — is
    INVALID_SYNC_CONFIG (exit 6), never a silently-ignored key that leaves pages
    filed in a folder the operator did not choose.

    MUT: flip `additionalProperties` to `true` on `$defs/ExtractDecisionsDirs`
    ⇒ this test goes RED (the load succeeds and the key is dropped in silence).
    """
    _sync_yaml(tmp_path, "extract_decisions:\n  dirs:\n    incident: inc\n")
    with pytest.raises(SyncConfigError) as exc:
        load_sync_config(tmp_path)
    assert exc.value.code == "INVALID_SYNC_CONFIG"
    assert exc.value.reason == "SCHEMA"


@pytest.mark.parametrize(
    "value",
    ["'../../etc'", "'/etc/passwd'", "'a\\b'", "'ok/../../up'"],
)
def test_unsafe_dir_is_refused_and_the_value_is_not_echoed(
    tmp_path: Path, value: str
) -> None:
    """H-6 / CWE-209: a traversal, absolute or backslash folder name is refused at
    LOAD time (exit 6) — not surfaced later as a write error — and the offending
    value NEVER appears in the message.

    MUT: drop the `_is_safe_subdir` call in `_parse_extract_decisions`
    ⇒ RED (the config loads and a `..` folder name reaches the writer).
    """
    _sync_yaml(tmp_path, f"extract_decisions:\n  dirs:\n    decision: {value}\n")
    with pytest.raises(SyncConfigError) as exc:
        load_sync_config(tmp_path)
    assert exc.value.reason == "UNSAFE_SUBDIR"
    assert value.strip("'") not in str(exc.value)
    assert "decision" in str(exc.value)  # names the KEY, never the value


@pytest.mark.parametrize("value", ['""', "'   '", "'/'"])
def test_empty_dir_is_refused(tmp_path: Path, value: str) -> None:
    """An EMPTY folder name is refused — a STATED boundary, not a merely-true one.
    `dirs.decision: ""` would file typed pages into the source note's own folder:
    exactly the flat clutter the per-class folders exist to prevent. The literal
    `""` is caught by the schema's `minLength: 1`; `"   "` and `"/"` normalise to
    empty and are caught by the parser — so BOTH halves are pinned here."""
    _sync_yaml(tmp_path, f"extract_decisions:\n  dirs:\n    decision: {value}\n")
    with pytest.raises(SyncConfigError) as exc:
        load_sync_config(tmp_path)
    assert exc.value.reason in {"SCHEMA", "UNSAFE_SUBDIR"}


def test_raw_loader_returns_the_unparsed_block(tmp_path: Path) -> None:
    """`load_extract_decisions_raw` is what the 063-01 cascade deep-merges: it must
    return the RAW dict (defaults NOT injected), or a partial folder override would
    inherit its parent's `enabled` only by accident. Mirrors `load_summarize_raw`."""
    _sync_yaml(tmp_path, "extract_decisions:\n  dirs:\n    risk: Риски\n")
    assert load_extract_decisions_raw(tmp_path) == {"dirs": {"risk": "Риски"}}


# --------------------------------------------------------------------------- #
# 063-01 — the per-folder Option-A cascade (R-063-3′(d))
# --------------------------------------------------------------------------- #


def test_absent_at_every_level_is_none(tmp_path: Path) -> None:
    """No block anywhere in the chain ⇒ `None`. NOT a defaulted-and-disabled config:
    "never configured" and "configured, off" are different facts, and only the first
    means the rail must never be auto-dispatched."""
    zone = tmp_path / "Zone"
    zone.mkdir()
    assert resolve_extract_decisions(
        zone / "note.md", vault_root=tmp_path
    ) is None


def test_partial_override_inherits_parent(tmp_path: Path) -> None:
    """★ The RAW-then-parse order, which is the whole reason the cascade merges raw
    dicts instead of parsed dataclasses.

    Root: `{enabled: true, dirs: {decision: decisions}}`. Zone overrides ONE key.
    The zone must inherit `enabled: true` and the root's `decision`.

    MUT: parse-then-merge (parse each level, then overwrite field-by-field) ⇒ the
    zone's parsed block carries its INJECTED DEFAULT `enabled=False`, which
    overwrites the root's `true` — the override silently switches the rail OFF.
    That is a real failure mode, not a hypothetical: it is what a reader "cleaning
    up" the resolver into `replace(parent, **child_fields)` would ship.
    """
    _sync_yaml(
        tmp_path,
        "extract_decisions:\n  enabled: true\n  dirs:\n    decision: decisions\n",
    )
    zone = tmp_path / "Zone"
    zone.mkdir()
    _sync_yaml(zone, "extract_decisions:\n  dirs:\n    risk: 'риски'\n")

    cfg = resolve_extract_decisions(zone / "note.md", vault_root=tmp_path)
    assert cfg is not None
    assert cfg.enabled is True            # inherited — the MUT breaks exactly this
    assert cfg.dirs.decision == "decisions"    # inherited
    assert cfg.dirs.risk == "риски"            # overridden
    assert cfg.dirs.requirement == "requirements"  # neither level set it → default


def test_two_zones_resolve_different_names(tmp_path: Path) -> None:
    """R-063-3′(d), literally: two engagements in ONE vault, two folder grammars.
    This is the operator's requirement — a Russian-named zone and an English one
    cannot be forced to share a folder vocabulary."""
    _sync_yaml(tmp_path, "extract_decisions:\n  enabled: true\n")
    (tmp_path / "Zone A").mkdir()
    (tmp_path / "Zone B").mkdir()
    _sync_yaml(tmp_path / "Zone A", "extract_decisions:\n  dirs:\n    decision: decisions\n")
    _sync_yaml(tmp_path / "Zone B", "extract_decisions:\n  dirs:\n    decision: 'Решения'\n")

    a = resolve_extract_decisions(tmp_path / "Zone A" / "n.md", vault_root=tmp_path)
    b = resolve_extract_decisions(tmp_path / "Zone B" / "n.md", vault_root=tmp_path)
    assert a is not None and b is not None
    assert (a.dirs.decision, b.dirs.decision) == ("decisions", "Решения")
    assert a.enabled is b.enabled is True   # both inherit the root's opt-in


def test_caches_read_sync_yaml_once_per_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PERF-046-1 survives a THIRD cascade: `extract_decisions` sources its block
    from the shared `_validated_dir` memo, so N files in one dir read + parse +
    validate `.wiki/sync.yaml` ONCE — not once more per new cascade.

    MUT: drop the `c.extract_decisions` memo ⇒ 3 calls, RED.
    """
    _sync_yaml(tmp_path, "extract_decisions:\n  enabled: true\n")
    zone = tmp_path / "Zone"
    zone.mkdir()

    real = _resummarize._validated_dir
    calls: list[Path] = []

    def _counting(d: Path, c: _resummarize.Caches) -> dict[str, Any]:
        calls.append(d)
        return real(d, c)

    monkeypatch.setattr(_resummarize, "_validated_dir", _counting)

    caches = _resummarize.Caches()
    for name in ("a.md", "b.md", "c.md"):
        cfg = resolve_extract_decisions(zone / name, vault_root=tmp_path, caches=caches)
        assert cfg is not None and cfg.enabled is True
    # 2 dirs (root + Zone) × ONE read each — the second and third file hit the
    # `c.extract_decisions[parent]` memo and never reach `_validated_dir` at all.
    assert len(calls) == 2


def test_every_cascade_resolver_uses_the_SHARED_hardened_read() -> None:
    """The exit-criterion grep, promoted to a durable test — and MEASURED from the
    source rather than asserted in prose.

    A cascade resolver that opened its own `sync.yaml` read would be a SECOND,
    divergent hardening surface: the size cap, the anchor-ban, the symlink refusal
    and the strict schema all live in `_load_validated_raw`, and a resolver that
    skipped it would silently accept a config the others refuse. So: every resolver
    must use the same ancestor walk, the same memoized hardened read, and the same
    deep-merge.

    The POPULATION is enumerated here (three resolvers, named). A fourth cascade
    added without updating this list is the failure this test cannot catch — so the
    list is asserted against the module's own `resolve_*` surface, not hardcoded.
    """
    import inspect

    resolvers = sorted(
        name for name in dir(_resummarize)
        if name.startswith("resolve_") and callable(getattr(_resummarize, name))
    )
    assert resolvers == ["resolve_extract_decisions", "resolve_policy", "resolve_summarize"], (
        "a new cascade resolver appeared — add it to the shared-surface contract "
        "below, or explain why it may bypass the hardened read")

    for name in resolvers:
        src = inspect.getsource(getattr(_resummarize, name))
        assert "_ancestor_dirs(" in src, f"{name} does not use the shared ancestor walk"
        assert "_validated_dir(" in src, f"{name} bypasses the shared hardened read"
        assert "deep_merge(" in src, f"{name} does not deep-merge (RAW-then-parse)"
