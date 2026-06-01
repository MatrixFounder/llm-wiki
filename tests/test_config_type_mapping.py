"""TASK 012-03 (PW-C/E) — config-driven type inference + type_mapping.

`normalize_frontmatter` consumes a layout-config `type_mapping` / `path_type_fallback`
(default = the Karpathy module constants — back-compat). Karpathy byte-identity is
guarded by the golden anchor; this module pins the dev-project tag-route + the
config-fallback path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.wiki_index.normalization import (
    TYPE_MAPPING,
    UnmappedTypeError,
    normalize_frontmatter,
)

# A dev-project tag-route (subset) — task/plan→brief, adr/review→research + tag.
_DEV_TM: dict[str, tuple[str, str | None]] = {
    "task": ("brief", "task"),
    "plan": ("brief", "plan"),
    "adr": ("research", "adr"),
    "review": ("research", "review"),
}
_DEV_FALLBACK = {"issues": "known-issue"}
# known-issue must be mappable for the fallback test:
_DEV_TM_FULL = {**_DEV_TM, "known-issue": ("research", "known-issue")}


def test_default_path_is_module_type_mapping() -> None:
    """Passing neither map == today's Karpathy behaviour (the byte-identity contract)."""
    fm, db_type = normalize_frontmatter({"type": "concept", "title": "X"})
    assert db_type == "concept"
    # external → concept + tag external (a TYPE_MAPPING entry)
    fm2, db2 = normalize_frontmatter({"type": "external", "title": "Y"})
    assert db2 == "concept" and "external" in fm2["tags"]
    assert "external" in TYPE_MAPPING  # sanity: still the module default


def test_dev_type_mapping_tag_route() -> None:
    fm, db_type = normalize_frontmatter({"type": "task", "title": "T"}, type_mapping=_DEV_TM)
    assert db_type == "brief"
    assert "task" in fm["tags"]
    fm2, db2 = normalize_frontmatter({"type": "adr", "title": "A"}, type_mapping=_DEV_TM)
    assert db2 == "research" and "adr" in fm2["tags"]


def test_unmapped_type_raises_against_supplied_map() -> None:
    # `concept` is valid for Karpathy but NOT in the dev map → UnmappedTypeError.
    with pytest.raises(UnmappedTypeError, match="not in type_mapping"):
        normalize_frontmatter({"type": "concept"}, type_mapping=_DEV_TM)


def test_config_path_type_fallback() -> None:
    """A type-less file under a config-declared fallback subdir infers its type
    from the supplied path_type_fallback (not the Karpathy default)."""
    fm, db_type = normalize_frontmatter(
        {"title": "no type"},
        source_path=Path("docs/issues/p-1-foo.md"),
        type_mapping=_DEV_TM_FULL,
        path_type_fallback=_DEV_FALLBACK,
    )
    assert db_type == "research" and "known-issue" in fm["tags"]


def test_supplied_fallback_does_not_leak_karpathy() -> None:
    # Under the dev fallback, a `_concepts/` path does NOT infer `concept`
    # (that's the Karpathy default, not the supplied map) → unmapped.
    with pytest.raises(UnmappedTypeError):
        normalize_frontmatter(
            {"title": "x"},
            source_path=Path("_concepts/x.md"),
            type_mapping=_DEV_TM_FULL,
            path_type_fallback=_DEV_FALLBACK,
        )
