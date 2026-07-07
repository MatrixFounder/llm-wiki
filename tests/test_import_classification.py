"""TASK 049 (R-7) — `wiki-import --classification`: the H-6 quarantine stamp.

The `_raw` capture gets a DEDICATED frontmatter injection (not riding
`ensure_source_frontmatter`'s already-cites-source early-return — plan-review
F3); the authored note's frontmatter carries the same key via `assemble_note`;
omitted flag ⇒ byte-identical output (NFR-1).
"""

from __future__ import annotations

import pytest

from scripts.wiki_skills.wiki_import_article import _classification_arg
from scripts.wiki_skills.wiki_import_article._authoring import assemble_note
from scripts.wiki_skills.wiki_import_article._fetch import (
    ensure_source_frontmatter,
    inject_classification,
)


# =============================================================================
# inject_classification (the _raw stamp)
# =============================================================================

def test_inject_into_existing_frontmatter():
    raw = '---\ntitle: "T"\nsource: "https://x.test/a"\n---\n\nBody.\n'
    out = inject_classification(raw, "restricted")
    assert out.startswith("---\nclassification: restricted\n")
    assert 'source: "https://x.test/a"' in out and out.endswith("Body.\n")


def test_inject_creates_frontmatter_when_absent():
    out = inject_classification("Just a text dump.", "internal")
    assert out.startswith("---\nclassification: internal\n---\n\n")
    assert out.endswith("Just a text dump.")


def test_inject_survives_ensure_source_early_return():
    """Plan-review F3: a capture ALREADY citing its source takes
    ensure_source_frontmatter's untouched branch — the stamp must still land."""
    raw = '---\nsource: "https://x.test/a"\n---\n\nBody.\n'
    assert ensure_source_frontmatter(raw, "https://x.test/a") == raw
    out = inject_classification(
        ensure_source_frontmatter(raw, "https://x.test/a"), "restricted")
    assert "classification: restricted" in out


def test_inject_idempotent_existing_key_untouched():
    raw = "---\nclassification: public\nsource: \"s\"\n---\n\nB.\n"
    assert inject_classification(raw, "restricted") == raw


def test_omitted_is_noop_nfr1():
    raw = '---\nsource: "s"\n---\n\nB.\n'
    # the caller only invokes inject_classification when the flag is set;
    # assert the un-stamped path leaves bytes untouched end-to-end.
    assert ensure_source_frontmatter(raw, "s") == raw


# =============================================================================
# assemble_note (the authored-note stamp)
# =============================================================================

_NOTE = {"title": "Demo", "tldr": "t", "summary_bullets": ["a"],
         "body": "Body text.", "tags": ["article"]}


def _assemble(**kw) -> str:
    _, text = assemble_note(
        _NOTE, mode="full", raw_rel_basename="_raw/demo.md",
        source_url="https://x.test/a", source_lang="en",
        today="2026-07-07", san_names=[], **kw)
    return text


def test_note_frontmatter_carries_stamp():
    text = _assemble(classification="restricted")
    fm = text.split("---")[1]
    assert "\nclassification: restricted\n" in fm


def test_note_without_flag_byte_identical():
    assert _assemble() == _assemble(classification=None)
    assert "classification" not in _assemble().split("---")[1]


# =============================================================================
# flag shape validation (CWE-209: value not echoed)
# =============================================================================

@pytest.mark.parametrize("bad", ["UPPER", "1leading", "x" * 17, "has space", ""])
def test_bad_shape_rejected_without_echo(bad):
    import argparse
    with pytest.raises(argparse.ArgumentTypeError) as exc:
        _classification_arg(bad)
    if bad:  # '' is a substring of everything — containment check meaningless
        assert bad not in str(exc.value)


def test_good_shapes_accepted():
    for ok in ("public", "internal", "restricted", "sev-1_tier"):
        assert _classification_arg(ok) == ok
