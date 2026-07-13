"""TASK 063-02 — the G4 typed-write placement gate.

ONE implementation of "can the walker SEE a page written here?", shared by its two
callers (`wiki-config validate` — 063-03; the rail's `prepare` preflight — 063-05).
Two would drift, and a gate that disagrees with itself is a second opinion.

★ THE FIXTURE ROSTER IS PLAN §1's. No test here invents its own layout fixture —
that rule exists because the plan got "which layouts are supported" factually wrong
TWICE, both times by measuring ONE of the two conjuncts:

| fixture | typed classes? | globs see the write dir? | verdict |
|---|---|---|---|
| `cybos` | yes | yes (root-anchored `decisions/**/*.md`) | SUPPORTED — root, STRICT names |
| `dev-project` | yes | yes — ONLY after this bead adds the 3 globs | SUPPORTED — root |
| `para-typed` | yes (via `.wiki/layout.yaml`) | yes (generic PARA glob) | SUPPORTED — SIBLING, free names |
| `karpathy` | NO | — | REFUSED (byte-identity-anchored; never edited) |
| `obsidian-personal` (stock) | NO | — | REFUSED |

**A layout supports this rail ⟺ `type_mapping` maps the classes AND the read globs
can see the write path.** Neither half alone is support. `dev-project` satisfied the
first and failed the second, which is how three planned tests came to be written
against a layout the rail would have refused.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.wiki_index.layout_config import (
    TYPED_WRITE_PROBE,
    LayoutConfig,
    glob_covers,
    iter_pages,
    layout_choices,
    load_layout_config,
    resolve_typed_write_dir,
)

TYPED_CLASSES = ("decision", "requirement", "risk")
DEFAULT_DIRS = ("decisions", "requirements", "risks")

# The supported SET. Every name here is justified by the CONJUNCTION below — this
# constant is the claim, and `test_supported_layouts_are_the_conjunction` is the
# measurement that keeps it honest against the whole registry.
SUPPORTED = {"cybos", "dev-project"}

# `para-typed` is not a registry name — it is `obsidian-personal` + a per-vault
# `.wiki/layout.yaml` that unions in the typed classes. It IS the operator's live
# vault, and it is the only fixture exercising SIBLING placement + Cyrillic names.
_PARA_OVERRIDE = {
    "type_mapping": {
        "decision": {"db_type": "research", "tag": "decision"},
        "requirement": {"db_type": "brief", "tag": "requirement"},
        "risk": {"db_type": "research", "tag": "risk"},
    },
}


def _config_for(name: str, tmp_path: Path, override: dict[str, Any] | None = None) -> LayoutConfig:
    """Build a `LayoutConfig` for a REGISTRY name (m-10: `resolve_layout_config_by_name`
    does not exist; the real APIs are `load_layout_config(vault_root, root_config)` +
    `layout_choices()`)."""
    root_config: dict[str, Any] = {"layout": name}
    if override is not None:
        (tmp_path / ".wiki").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".wiki" / "layout.yaml").write_text(
            yaml.safe_dump(override, allow_unicode=True), encoding="utf-8"
        )
        root_config["layout_config"] = ".wiki/layout.yaml"
    return load_layout_config(tmp_path, root_config)


def _para_typed(tmp_path: Path) -> LayoutConfig:
    return _config_for("obsidian-personal", tmp_path, _PARA_OVERRIDE)


# --------------------------------------------------------------------------- #
# ★ The measurement — glob_covers ⟺ the REAL walk (plan-review C-3)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "layout,override,source_dir",
    [
        ("cybos", None, "meetings"),
        ("dev-project", None, "tasks"),
        ("obsidian-personal", _PARA_OVERRIDE, "06 - BD/Acme"),
    ],
)
@pytest.mark.parametrize(
    "dir_name",
    ["decisions", "requirements", "risks", "решения", "_raw", "_raw/deep",
     ".obsidian", "docs", "_templates"],
)
def test_glob_covers_agrees_with_the_real_walk(
    tmp_path: Path, layout: str, override: dict[str, Any] | None,
    source_dir: str, dir_name: str,
) -> None:
    """★ MEASURE the helper against `iter_pages`. Never RESTATE the filter chain.

    The walker's visibility is a 5-way conjunction, and a previous draft of this
    helper enumerated ONE of them (`paths[]`) while its docstring claimed "i.e. the
    walker can see a file written here". That "i.e." IS the project's signature
    failure mode, sitting inside the gate written to prevent it.

    Restating the chain in a test would only re-assert what the helper already
    believes. Writing a real probe file and running the REAL walk covers every
    conjunct the walker has TODAY and every one it gains LATER — with no edit to
    this test. That is the difference between a gate and a paraphrase.

    Both placements are probed (root-anchored and sibling), because the equivalence
    must hold for the paths `resolve_typed_write_dir` actually considers.

    ⚠️ THE `_raw` CASE IS THE BUG, PINNED. On the PARA vault `06 - BD/Acme/_raw/…`
    MATCHES the generic `[0-9][0-9] - */*/**/*.md` glob — so a `paths[]`-only helper
    reports COVERED — while `**/_raw/**` is in `ignore` and the walker skips it. The
    page would be written, never indexed, and raise ZERO lint issues.
    MUT: implement `glob_covers` as a bare `any(rel.full_match(e.glob) ...)` ⇒ RED.
    """
    cfg = _config_for(layout, tmp_path, override)
    probe = f"{TYPED_WRITE_PROBE}.md"

    for rel in (f"{dir_name}/{probe}", f"{source_dir}/{dir_name}/{probe}"):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# probe\n", encoding="utf-8")

        walked = {
            p.path.relative_to(tmp_path).as_posix() for p in iter_pages(tmp_path, cfg)
        }
        assert glob_covers(cfg, rel) == (rel in walked), (
            f"{layout}: glob_covers says {glob_covers(cfg, rel)} for {rel!r}, "
            f"the real walk says {rel in walked}")

        target.unlink()


def test_glob_covers_uses_full_match_never_fnmatch() -> None:
    """C-4, scoped to the HELPER — and RUN, not reasoned about.

    `fnmatch` lets `*` cross a `/`, so it answers MATCH for `decisions/2026/dec.md`
    against `decisions/*.md` where the engine answers NO. An earlier draft measured
    coverage with `fnmatch` and reported a FALSE answer to the operator.

    The `fnmatch.fnmatchcase` calls that DO live in `layout_config.py` are the
    TASK-030 per-SEGMENT matcher of the single-pass walk, where `*` never crosses a
    `/` and the call is correct. So the gate is scoped to the new helper — a
    developer "satisfying" a module-wide `no fnmatch` rule by deleting those calls
    would BREAK THE WALK. (v1's exit criterion was exactly that module-wide rule:
    factually false, and unsatisfiable without regression.)

    ⚠️ MEASURED ON THE COMPILED CODE, NOT ON THE SOURCE TEXT — and BOTH text-shaped
    gates the plan proposed turned out to be broken, in the same way, for the third
    time in this bead's history:

      * `assert "fnmatch" not in inspect.getsource(glob_covers)` FAILS on the
        shipped helper — its docstring *explains* why fnmatch is wrong. To keep that
        gate green you would delete the explanation: **the gate deleting the
        knowledge it exists to protect.**
      * `grep -c fnmatch layout_config.py  # → 4` is now **7**, for the same reason.
        A line count counts MENTIONS, not CALLS.

    So the population is the CALLERS, enumerated from `co_names` (the global names a
    compiled function actually references). Exactly two functions may call fnmatch —
    both halves of the TASK-030 per-SEGMENT matcher, where `*` cannot cross a `/`
    and the call is correct. A third caller, or `glob_covers` among them, is the
    regression this gate exists for; deleting the legitimate two (the "fix" a
    module-wide no-fnmatch rule would provoke) BREAKS THE WALK and is caught here
    too, because the census is an equality, not an upper bound.
    """
    import scripts.wiki_index.layout_config as lc

    def _funcs(obj: Any, prefix: str = "") -> Any:
        for name, member in vars(obj).items():
            if inspect.isfunction(member) and member.__module__ == lc.__name__:
                yield f"{prefix}{name}", member
            elif inspect.isclass(member) and member.__module__ == lc.__name__:
                yield from _funcs(member, f"{name}.")

    callers = sorted(n for n, f in _funcs(lc) if "fnmatch" in f.__code__.co_names)
    assert callers == ["_PatternState.advance", "_PatternState.matches_file"], (
        f"the fnmatch caller census changed: {callers}. Only the TASK-030 "
        f"per-segment matcher may call it (there `*` never crosses a `/`).")

    # The G4 helper FAMILY — none of them may call fnmatch. Named as a family rather
    # than as `glob_covers` alone, because this assertion ALREADY caught a refactor:
    # when the chain moved into `cover_refusal`, a `glob_covers`-only gate went RED
    # for the wrong reason (glob_covers stopped calling `full_match` because it now
    # DELEGATES). A gate pinned to a function NAME breaks when the code is reorganised;
    # a gate pinned to the FAMILY follows the chain wherever it lives.
    family = [glob_covers, lc.cover_refusal, resolve_typed_write_dir,
              lc.typed_write_refusal, lc._typed_write_candidates]
    for fn in family:
        assert "fnmatch" not in fn.__code__.co_names, (
            f"{fn.__name__} CALLS fnmatch — `*` would cross a `/` and it would report "
            f"MATCH for decisions/2026/dec.md against decisions/*.md")

    # ...and SOMEONE in the family must actually do the matching, with `full_match`.
    # Without this half, deleting the matcher entirely would pass the loop above.
    assert any("full_match" in fn.__code__.co_names for fn in family), (
        "no G4 helper matches globs at all — the gate would answer False for "
        "everything, refusing every layout while looking perfectly green")


# --------------------------------------------------------------------------- #
# The placement matrix — from the PLAN §1 roster
# --------------------------------------------------------------------------- #


def test_cybos_places_typed_pages_at_the_ROOT(tmp_path: Path) -> None:
    cfg = _config_for("cybos", tmp_path)
    assert resolve_typed_write_dir(
        cfg, dir_name="decisions", source_rel="meetings/m1.md") == "decisions"
    # the `**` semantics, positively: a nested dir under the root anchor is covered.
    assert glob_covers(cfg, f"decisions/2026/{TYPED_WRITE_PROBE}.md")


def test_cybos_REFUSES_a_custom_name(tmp_path: Path) -> None:
    """cybos is STRICT BY DESIGN, not broken: its globs are root-anchored literals,
    so `решения` is covered by nothing and the rail must REFUSE rather than write an
    invisible page. (Q-063-5 = A: `sync.yaml` must never mutate `layout.yaml` to
    "fix" this — a per-folder config silently rewriting the vault's read grammar
    would change what every OTHER tool sees.)"""
    cfg = _config_for("cybos", tmp_path)
    assert resolve_typed_write_dir(
        cfg, dir_name="решения", source_rel="meetings/m1.md") is None


def test_dev_project_places_typed_pages_at_the_ROOT(tmp_path: Path) -> None:
    """Green ONLY because this bead added the three `paths[]` globs. Before them
    `type_mapping` routed the classes while no glob could see them — half a layout,
    and the half that is invisible is the one that loses pages."""
    cfg = _config_for("dev-project", tmp_path)
    for dir_name in DEFAULT_DIRS:
        assert resolve_typed_write_dir(
            cfg, dir_name=dir_name, source_rel="tasks/t1.md") == dir_name


def test_para_places_typed_pages_as_a_SIBLING_with_cyrillic_names(tmp_path: Path) -> None:
    """The operator's live vault: typed pages beside the note they came from, in
    Russian-named folders."""
    cfg = _para_typed(tmp_path)
    assert resolve_typed_write_dir(
        cfg, dir_name="решения", source_rel="06 - BD/Acme/note.md",
    ) == "06 - BD/Acme/решения"


def test_para_REFUSES_an_ignored_dir_name(tmp_path: Path) -> None:
    """★ The C-3 failure, as a placement decision. `_raw` MATCHES the PARA glob but
    the walker IGNORES it. A `paths[]`-only gate would return
    `06 - BD/Acme/_raw` — a real directory, a written page, an unindexed page, and
    not one lint issue to show for it."""
    cfg = _para_typed(tmp_path)
    assert resolve_typed_write_dir(
        cfg, dir_name="_raw", source_rel="06 - BD/Acme/note.md") is None


def test_placement_is_DERIVED_never_hardcoded(tmp_path: Path) -> None:
    """The same `dir_name`, two layouts, two DIFFERENT answers — because placement
    is a property of the LAYOUT'S read grammar, not of the rail's preference.

    MUT: hardcode "sibling" (the v5 draft) ⇒ cybos returns `meetings/decisions`,
    which cybos's root-anchored globs cannot see ⇒ RED (and in production: a page
    written where nothing reads it).
    MUT: hardcode "root" ⇒ para returns `decisions`, outside every PARA glob ⇒ RED.
    """
    cybos = _config_for("cybos", tmp_path / "a")
    para = _para_typed(tmp_path / "b")
    assert resolve_typed_write_dir(
        cybos, dir_name="decisions", source_rel="meetings/m1.md") == "decisions"
    assert resolve_typed_write_dir(
        para, dir_name="decisions", source_rel="06 - BD/Acme/note.md",
    ) == "06 - BD/Acme/decisions"


# --------------------------------------------------------------------------- #
# ★ The supported-set gate — THE CONJUNCTION (plan-review C-2)
# --------------------------------------------------------------------------- #


def test_supported_layouts_are_the_CONJUNCTION(tmp_path: Path) -> None:
    """★ The gate the plan fumbled TWICE, and the reason PLAN §1 exists.

    Support is `type_mapping maps the classes` **AND** `the read globs can see the
    write dir`. v1 asserted the first conjunct alone — and so it would have gone
    GREEN while `prepare` refused `dev-project` via its own preflight. *The gate
    written to stop the lens was an instance of it.*

    MUT (run it): replace the conjunction with `maps` alone ⇒ this test passes for
    `dev-project` even with the three globs REVERTED — i.e. it reproduces the exact
    false green v1 shipped. A gate that passes in the broken state is not a gate.

    The POPULATION is `layout_choices()` — the registry itself — so a new built-in
    layout cannot join without facing this test.
    """
    for name in layout_choices():
        cfg = _config_for(name, tmp_path / name)
        maps = bool(set(TYPED_CLASSES) & set(cfg.type_mapping))
        sees = all(
            resolve_typed_write_dir(cfg, dir_name=d, source_rel="notes/n.md") is not None
            for d in DEFAULT_DIRS
        )
        assert (maps and sees) == (name in SUPPORTED), (
            f"{name}: maps={maps} sees={sees} — but SUPPORTED says "
            f"{name in SUPPORTED}. Support is the CONJUNCTION; a layout with only "
            f"one half is not supported, it is a trap.")


def test_stock_obsidian_personal_is_refused_but_para_typed_is_not(tmp_path: Path) -> None:
    """The two halves, isolated — this is what makes `para-typed` a legitimate
    fixture rather than a contradiction (C-2b): stock `obsidian-personal` maps ZERO
    typed classes and must be REFUSED; the SAME layout plus a `.wiki/layout.yaml`
    that unions them in is SUPPORTED. Its globs could always see the pages; what it
    lacked was the routing."""
    stock = _config_for("obsidian-personal", tmp_path / "stock")
    para = _para_typed(tmp_path / "para")
    assert not (set(TYPED_CLASSES) & set(stock.type_mapping))
    assert set(TYPED_CLASSES) <= set(para.type_mapping)
    # ...while the read globs of BOTH can see the sibling dir — the half that was
    # never the problem.
    for cfg in (stock, para):
        assert glob_covers(cfg, f"06 - BD/Acme/decisions/{TYPED_WRITE_PROBE}.md")


def test_identity_schema_enum_IS_the_registry() -> None:
    """★ A PRODUCTION DEFECT, found while building a cybos fixture — and it is the
    project's signature lens in its purest form: the layout POPULATION was declared in
    TWO places, and only one of them was maintained.

      `layout_config.layout_choices()`      → 6 layouts (registry, drives `--layout`)
      `config/wiki-config.schema.yaml`      → 5 layouts (identity schema `Layout` enum)

    `cybos` was in the first and not the second. So a vault declaring `layout: cybos`
    in `WIKI_SCHEMA.md` — the documented way, and verbatim what `scripts/benchmark.py`
    writes — FAILED `config_loader.load_config`, and `wiki-config validate` reported a
    spurious `IDENTITY_CONFIG_INVALID` on every cybos vault. It went unnoticed because
    `resolve_layout_config` reads via `load_root_config`, which does NOT validate the
    enum: the vault WALKED correctly while its config was formally invalid. A defect
    that only the validator can see, in the validator nobody ran on this layout.

    The fix is not "add cybos" — that is the instance. The fix is THIS TEST: the enum
    is now pinned EQUAL to the registry, so the two cannot drift again, and a seventh
    layout cannot be added to one without the other.
    """
    import yaml

    from scripts.wiki_index.config_loader import _SCHEMA_PATH as IDENTITY_SCHEMA

    doc = yaml.safe_load(IDENTITY_SCHEMA.read_text(encoding="utf-8"))
    enum = set(doc["$defs"]["Layout"]["enum"])
    assert enum == set(layout_choices()), (
        f"the identity schema's `layout` enum and the layout REGISTRY have drifted: "
        f"registry-only={sorted(set(layout_choices()) - enum)}, "
        f"schema-only={sorted(enum - set(layout_choices()))}. A vault declaring a "
        f"registry-only layout walks correctly but fails `load_config`.")


def test_karpathy_is_refused_for_the_TYPE_MAPPING_conjunct_not_the_glob_one(
    tmp_path: Path,
) -> None:
    """★ THE CONJUNCTION, PROVEN BY THE COUNTEREXAMPLE — and this test's FIRST draft
    was itself the bug, caught by running it.

    That draft asserted `resolve_typed_write_dir(karpathy, ...) is None`, reasoning
    "karpathy is refused, therefore both conjuncts fail". **False.** karpathy's
    `_sources/**/*.md` glob HAPPILY covers `_sources/decisions/probe.md`, so the
    placement conjunct is TRUE. karpathy is refused because it maps ZERO typed
    classes — the OTHER conjunct.

    So a `sees`-only gate would call karpathy supported, and a `maps`-only gate
    would call dev-project-before-this-bead supported. Each half is wrong about a
    DIFFERENT layout, which is exactly why support must be the conjunction and why
    asserting either half alone keeps producing confident false answers.

    (This is the ~32nd instance of the lens in this task family, and the third
    inside machinery written to prevent it. It was caught by RUNNING the assertion,
    not by reviewing it — for the ~32nd time.)

    karpathy is byte-identity-anchored (`scripts/wiki_index/layout.py` is its source
    of truth) and is NEVER edited to make it supported.
    """
    cfg = _config_for("karpathy", tmp_path)
    # conjunct 1 — routing: FALSE. This is the one that refuses karpathy.
    assert not (set(TYPED_CLASSES) & set(cfg.type_mapping))
    # conjunct 2 — placement: TRUE. Stated out loud, because believing it was False
    # is what made the first draft of this test pass for the wrong reason.
    assert resolve_typed_write_dir(
        cfg, dir_name="decisions", source_rel="_sources/s.md") == "_sources/decisions"
