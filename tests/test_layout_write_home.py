"""TASK 072 / bead 072-10b — THE TWO-CONJUNCT PROPERTY: a layout that MAPS a class must
also be able to SEE the directory that class is WRITTEN to.

THE TRAP (TASK 063's conjunction trap, third recurrence). Adding a class to
`type_mapping` looks like the whole job. It is half of it. The other half is a `paths[]`
glob that the WALKER can reach — and when it is missing, nothing complains:

  * the page is written and the CLI exits 0;
  * `wiki-reindex --full` reports it in NEITHER `indexed` NOR `skipped[]`, because
    `skipped[]` only reports files the walker actually SAW;
  * `wiki-lint` is *structurally incapable* of flagging it — a page absent from the
    index cannot fail an index check.

Measured on `main` before the fix: a cybos vault with `Articles/Some Paper.md`
(`type: article-summary`, well-formed) and `Articles/_concepts/topic.md` indexed
**neither**, with `skipped == []`.

WHY THIS IS A TEST AND NOT A COMMENT. Both layout files ALREADY carried a comment block
spelling this lesson out — twice (DF-049-1 for the RAG surfaces, then TASK 063 G4 for the
typed-knowledge surfaces). The classes added by TASK 046 landed anyway. A rule a human
must remember is a rule that gets forgotten; the population is walked here instead.

THE PROBE IS THE PRODUCTION CHAIN, NOT A GLOB MATCH. `cover_refusal` is the walker's own
five-conjunct filter (extension → system-file → autoindex-output → ignore → globs), the
single authority `wiki-config validate` and the `wiki-extract-decisions` G4 preflight both
call. A test that re-matched globs itself would be a SECOND implementation of the chain,
and a gate that disagrees with the code it gates is a second opinion.
"""

from __future__ import annotations

from pathlib import PurePosixPath

import pytest

from scripts.wiki_index.layout_config import (
    LAYOUTS_DIR,
    LayoutConfig,
    _build,
    _load_yaml,
    _validate,
    cover_refusal,
)

# The imported-source classes (TASK 046) and the concept/entity classes the construct
# path files beside a note. A layout declaring ANY of these claims to support that
# writer, and this module holds it to the claim.
_IMPORT_CLASSES = frozenset(
    {"summary", "article-summary", "meeting-summary", "lesson-summary"})
_CONCEPT_CLASSES = frozenset(
    {"concept", "external", "person", "company", "product", "group"})


def _layouts() -> dict[str, LayoutConfig]:
    """Every built-in layout, GLOB-DISCOVERED — a layout added tomorrow is covered
    without editing this module."""
    out: dict[str, LayoutConfig] = {}
    for path in sorted(LAYOUTS_DIR.glob("*.yaml")):
        merged = _load_yaml(path)
        _validate(merged)
        out[path.name] = _build(merged)
    return out


def _candidate_folders(config: LayoutConfig) -> list[str]:
    """`--folder` values worth probing, DERIVED from the layout's own `paths[]`: the
    literal prefix of each glob and every proper ancestor of it, plus the vault root.

    Derived, never hand-listed: a layout that renames its folders keeps being probed at
    the folders it actually has."""
    out = {""}
    for entry in config.paths:
        segs: list[str] = []
        for seg in PurePosixPath(entry.glob).parts:
            if any(ch in seg for ch in "*?["):
                break
            segs.append(seg)
        for i, seg in enumerate(segs):
            if not seg.endswith(".md"):
                out.add("/".join(segs[: i + 1]))
    return sorted(out)


def _covering_type(config: LayoutConfig, rel_posix: str) -> str | None | object:
    """The `type:` declared by the FIRST `paths[]` glob that matches `rel_posix`
    (first-match-wins, the engine's own order), or `_NO_COVER` when the walker refuses
    the path outright. `None` means the glob declares no type — the page's own
    frontmatter decides, which is exactly what an untyped container glob is for."""
    if cover_refusal(config, rel_posix) is not None:
        return _NO_COVER
    rel = PurePosixPath(rel_posix)
    for entry in config.paths:
        try:
            if rel.full_match(entry.glob):
                return entry.type
        except ValueError:
            continue
    return _NO_COVER


_NO_COVER = object()


def _visible_note_folders(config: LayoutConfig) -> list[str]:
    """Folders where `wiki-import` would file a note the walker can SEE **as a source
    note**. Mirrors `_note_dir`: a non-empty `write.source_subdir` (karpathy `_sources`)
    nests under the operator's folder; empty (PARA/cybos) files directly in it.

    ⚠️ THE COVERING GLOB'S TYPE IS PART OF THE PROPERTY, and leaving it out made the
    first cut of this module a VACUOUS GREEN: on the pre-fix cybos, `decisions/` is
    walker-visible, so "is there a visible folder?" answered YES and the headline test
    PASSED ON THE BUG. Filing an article into the decisions folder is not a home — it is
    another class's home. A valid import home is covered by a glob that declares an
    imported-source type or declares none at all."""
    sub = config.write.source_subdir
    out = []
    for folder in _candidate_folders(config):
        base = f"{folder}/{sub}".strip("/") if sub else folder
        got = _covering_type(config, f"{base}/Some Title.md".lstrip("/"))
        if got is None or got in _IMPORT_CLASSES:
            out.append(folder or "<root>")
    return out


def _visible_concept_folders(config: LayoutConfig) -> list[str]:
    """Folders whose sibling `_concepts/` page the walker can SEE, under the same
    type-aware rule. An imported-source glob counts: `_concepts/` legitimately rides the
    container glob of the note it was extracted from."""
    sub = config.write.source_subdir
    out = []
    for folder in _candidate_folders(config):
        got = _covering_type(config, f"{folder}/_concepts/topic.md".lstrip("/"))
        if got is None or got in (_IMPORT_CLASSES | _CONCEPT_CLASSES):
            out.append(folder or "<root>")
    return out


# =============================================================================
# The property, over the glob-discovered layout population.
# =============================================================================


def test_the_population_is_not_empty() -> None:
    """Non-vacuity. A glob that matched nothing would make every test below pass by
    examining zero layouts — the failure mode this repo has paid for repeatedly."""
    layouts = _layouts()
    assert len(layouts) >= 4, sorted(layouts)
    assert {"cybos.yaml", "dev-project.yaml", "karpathy.yaml"} <= set(layouts)


def test_every_layout_mapping_import_classes_can_see_an_imported_note() -> None:
    """★ THE BEAD. `article-summary` in `type_mapping` is a PROMISE that an imported
    article can live here. Before 072-10b, cybos and dev-project both broke it."""
    examined = []
    for name, config in _layouts().items():
        if not (_IMPORT_CLASSES & set(config.type_mapping)):
            continue
        examined.append(name)
        visible = _visible_note_folders(config)
        assert visible, (
            f"{name} maps {sorted(_IMPORT_CLASSES & set(config.type_mapping))} in "
            f"type_mapping but NO folder derived from its own paths[] yields a "
            f"walker-visible note path — an imported note would be written, exit 0, "
            f"and never be indexed (and NOT appear in reindex `skipped[]`)")
    # Non-vacuity: at least one layout must actually be under test.
    assert len(examined) >= 2, examined


def test_every_layout_mapping_concept_classes_can_see_a_concepts_page() -> None:
    """The construct path files `<folder>/_concepts/<slug>.md`. dev-project's other
    globs are SINGLE-level (`tasks/*.md`), so before 072-10b only 5 of its 15 visible
    folders could hold one."""
    examined = []
    for name, config in _layouts().items():
        if not (_CONCEPT_CLASSES & set(config.type_mapping)):
            continue
        examined.append(name)
        assert _visible_concept_folders(config), (
            f"{name} maps concept/entity classes but no derived folder yields a "
            f"walker-visible `_concepts/` page")
    assert len(examined) >= 2, examined


def test_the_probe_refuses_a_genuinely_uncovered_folder() -> None:
    """★ THE DISCRIMINATION CONTROL. `_visible_note_folders` returning a non-empty list
    proves nothing unless the same probe can also say NO. A chain that accepted every
    path would make every assertion above pass on a layout with zero globs."""
    config = _layouts()["cybos.yaml"]
    assert cover_refusal(config, "No Such Folder/x.md") == "unmatched"
    assert cover_refusal(config, "sources/_raw/x.md") == "ignored"       # ignore wins
    assert cover_refusal(config, "sources/x.txt") == "extension"
    # …and the fix's own folder is accepted, so the control is two-sided.
    assert cover_refusal(config, "sources/Some Title.md") is None


# =============================================================================
# cybos: EVERY class in type_mapping, so a newly added one cannot re-open the hole.
# =============================================================================

# Classes that ride a SIBLING glob rather than declaring their own. Each maps to the
# probe path that must be walker-visible — MEASURED below, never asserted. The dict must
# cover the remainder EXACTLY: a class added to `type_mapping` with no glob and no entry
# here goes RED, and so does a stale entry for a class that no longer exists.
_CYBOS_COLOCATED = {
    # the imported-source family rides the `sources/**` glob whose declared type is the
    # generic `summary`; the note's own frontmatter `type:` wins at index time
    "article-summary": "sources/Some Paper.md",
    "meeting-summary": "sources/Some Meeting.md",
    "lesson-summary": "sources/Some Lesson.md",
    # the construct path files these beside the note it extracted them from
    "concept": "sources/_concepts/topic.md",
    "external": "sources/_concepts/some-org.md",
    "person": "sources/_concepts/some-person.md",
    "company": "sources/_concepts/some-co.md",
    "product": "sources/_concepts/some-product.md",
    "group": "sources/_concepts/some-group.md",
}


def test_cybos_every_mapped_class_has_a_walker_visible_home() -> None:
    config = _layouts()["cybos.yaml"]
    declared = {e.type for e in config.paths if e.type}
    mapped = set(config.type_mapping)

    # 1. The co-located table must partition the remainder EXACTLY — no gap, no cruft.
    remainder = mapped - declared - set(config.path_type_fallback.values())
    assert remainder == set(_CYBOS_COLOCATED), (
        f"cybos type_mapping changed. Classes with no glob and no co-located home: "
        f"{sorted(remainder - set(_CYBOS_COLOCATED))}; stale table entries: "
        f"{sorted(set(_CYBOS_COLOCATED) - remainder)}. Give the new class a `paths[]` "
        f"glob, or add its write path here — do not delete this assertion.")

    # 2. Every co-located home is MEASURED against the walker's own chain.
    for page_class, probe in sorted(_CYBOS_COLOCATED.items()):
        assert cover_refusal(config, probe) is None, (
            f"cybos maps {page_class!r} but its write path {probe!r} is not "
            f"walker-visible: {cover_refusal(config, probe)}")

    # 3. Every glob-declared class is trivially visible at its own glob — asserted so a
    #    future glob whose dir is `ignore`d (the reachable case `glob_covers` documents)
    #    cannot pass by living in the `declared` set alone.
    for entry in config.paths:
        if entry.type is None:
            continue
        base = PurePosixPath(entry.glob).parts[0]
        assert cover_refusal(config, f"{base}/probe-home.md") is None, (
            f"cybos glob {entry.glob!r} declares type {entry.type!r} but its own "
            f"directory is not walker-visible")


@pytest.mark.parametrize("name", ["cybos.yaml", "dev-project.yaml"])
def test_the_imported_source_home_is_the_declared_one(name: str) -> None:
    """Pins WHICH folder 072-10b chose, so the fix cannot be silently narrowed to a
    folder no operator would use."""
    config = _layouts()[name]
    assert cover_refusal(config, "sources/Some Paper.md") is None
    assert cover_refusal(config, "sources/nested/deep/Some Paper.md") is None
    assert cover_refusal(config, "sources/nested/_concepts/topic.md") is None
