"""TASK 014 / R-X1-REF-SLUGIFY — body ref targets are slugified via the layout's
`slug_strategy` so a `[[Title Case]]` / `[[Идеи]]` wikilink resolves to its
(slugified) target page instead of being flagged a false `orphan-link`.

Layout matrix: `identity` (karpathy) is a verbatim no-op (byte-identity); the
non-`identity` strategies normalise the target the same way page slugs are
derived from their stems.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts.wiki_index.layout_config import RefRule
from scripts.wiki_index.reindex import _body_refs

# The karpathy/obsidian wiki-link rule.
_WIKILINK = RefRule(
    kind="wiki-link",
    regex=r"\[\[([^\]|#]+)(?:#[^|\]]*)?(?:\|[^\]]+)?\]\]",
    target_group=1,
)


def _out(body: str) -> SimpleNamespace:
    return SimpleNamespace(page_slug="src", project="_vault_", body_text=body)


def _targets(body: str, strategy: str) -> list[str]:
    return [r.entity_slug for r in
            _body_refs(_out(body), (_WIKILINK,), "v", strategy)]


def test_identity_is_verbatim_noop() -> None:
    # Karpathy: slug_strategy=identity → target unchanged (byte-identity anchor).
    assert _targets("see [[Some Page]] and [[Идеи]]", "identity") == \
        ["Some Page", "Идеи"]


def test_transliterate_slugifies_target() -> None:
    # dev-project: [[Some Page]] → 'some-page' matches the page's transliterated slug.
    assert _targets("[[Some Page]]", "transliterate") == ["some-page"]


def test_preserve_unicode_slugifies_target() -> None:
    # obsidian-personal: [[Идеи]] → 'идеи' (lowercased, unicode kept) — the dogfood bug.
    assert _targets("[[Идеи]]", "preserve-unicode") == ["идеи"]
    # spaces → hyphen (the common Obsidian-link shape).
    assert _targets("[[draft idea]]", "preserve-unicode") == ["draft-idea"]


def test_default_strategy_is_identity() -> None:
    # Defensive: the param defaults to identity (verbatim) when a caller omits it.
    assert _targets("[[Keep Case]]", "identity") == ["Keep Case"]


@pytest.mark.parametrize("strategy,link,expected", [
    ("transliterate", "[[Roadmap]]", "roadmap"),
    ("preserve-unicode", "[[Квартиры]]", "квартиры"),
    ("ascii-only", "[[Café Notes]]", "cafe-notes"),
])
def test_matrix(strategy: str, link: str, expected: str) -> None:
    assert _targets(link, strategy) == [expected]
