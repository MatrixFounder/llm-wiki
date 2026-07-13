# TASK 063-02 — the CROSS-SYSTEM glob-coverage helper + **placement derivation**

**Phase**: 1 (the gate) · **RTM**: R-063-3 (G4), R-063-3′ · **Type**: code · **Effort**: 3–4h
**Depends on**: 063-00 · **Unblocks**: 063-03, 063-05, 063-12

## Goal

The **single** implementation of the G4 load gate, shared by its two callers (`wiki-config validate`
→ 063-03, and the rail's `prepare` preflight → 063-05). *One gate, two callers, never two
implementations* — a second copy is how the two config systems drift apart.

Two functions in `scripts/wiki_index/layout_config.py`:

```python
def glob_covers(config: LayoutConfig, rel_posix: str) -> bool:
    """True iff `rel_posix` (a vault-relative POSIX file path) matches ≥1 of the
    layout's own `paths[].glob` entries — i.e. the READ walker can SEE a file
    written there."""

def resolve_typed_write_dir(
    config: LayoutConfig, *, dir_name: str, source_rel: str,
) -> str | None:
    """DERIVE the placement of a typed page. Returns the vault-relative POSIX
    DIRECTORY the page must be written to, or None if the layout's read globs
    cover NEITHER placement (⇒ the caller REFUSES — Q-063-5(A))."""
```

## ★ The two axes are INDEPENDENT — and only one is operator-set

| | **PLACEMENT** (root vs sibling) | **NAME** (`decisions` vs `решения`) |
|---|---|---|
| who decides | **DERIVED from the layout** — never operator-set | **operator-set** in `sync.yaml` (cascading) |
| cybos (`decisions/**/*.md`, no catch-all) | **root** ⇒ `decisions/dec-x.md` ✅ | a custom name is **NOT covered** ⇒ **refused** |
| obsidian-personal (generic `[0-9][0-9] - */*/**/*.md`) | **sibling** of the source note ✅ | **any** name works, incl. Cyrillic ✅ |

`resolve_typed_write_dir` therefore **probes, in order**:
1. root-anchored: `f"{dir_name}/{PROBE}.md"` → covered? ⇒ return `dir_name`.
2. sibling-of-source: `f"{PosixPath(source_rel).parent}/{dir_name}/{PROBE}.md"` → covered? ⇒ return it.
3. neither ⇒ `None`. **The caller refuses with an actionable message. It does NOT auto-generate a
   glob** — `sync.yaml` mutating `layout.yaml` would erode the deliberate two-config-system split
   (Q-063-5, settled as **A: REFUSE**).

`PROBE` is a fixed, slug-shaped sentinel (e.g. `"_probe"`); the gate answers *"can the walker see a
`.md` file in this directory"*, which is a property of the **directory**, not of any one slug.

## ⚠️ The matcher is `PurePosixPath.full_match` — **NOT `fnmatch`**

`layout_config.py:986` (`_matches_ignore`) already does this and says why: *stdlib `PurePath.match`
does NOT handle `**`*. An earlier draft of this spec measured coverage with `fnmatch` and **reported
a false result** — `fnmatch` lets `*` cross a `/`, so it answers **MATCH** for
`decisions/2026/dec.md` against `decisions/*.md`, where the real engine answers **NO**. The gate MUST
use the engine's own matcher, or it is a gate against an approximation of the grammar rather than the
grammar. (This project's lesson, one more time: *validate against the real grammar, never against an
assumption about it.*)

## Context — files

- **Edit** `scripts/wiki_index/layout_config.py` — the two helpers, next to `_matches_ignore` (line ~983).
- **Read** `scripts/wiki_index/layouts/cybos.yaml` (root-anchored globs, **no catch-all**),
  `layouts/obsidian-personal.yaml` (generic PARA glob), `layouts/dev-project.yaml`.

## Tests (RED first) — `tests/test_layout_typed_write_dirs.py` (new)

**Coverage matrix — enumerated, not asserted-in-aggregate:**

| layout | dir_name | source_rel | expected |
|---|---|---|---|
| cybos | `decisions` | `meetings/m1.md` | `"decisions"` (root) |
| cybos | `решения` | `meetings/m1.md` | `None` (**refused**) |
| cybos | `risks` | `meetings/m1.md` | `"risks"` |
| obsidian-personal | `решения` | `06 - BD/Acme/note.md` | `"06 - BD/Acme/решения"` (sibling, Cyrillic OK) |
| dev-project | `decisions` | `tasks/t1.md` | per its real globs — **read them, do not assume** |
| karpathy | `decisions` | `_sources/s.md` | `None` |

- `test_glob_covers_uses_full_match_not_fnmatch` — **the discriminating case**:
  `glob_covers(dev_project_cfg, "issues/2026/x.md")` must be **False** (glob is `issues/*.md`), while
  `fnmatch.fnmatch("issues/2026/x.md", "issues/*.md")` is **True**. **MUT:** swap the implementation
  to `fnmatch` ⇒ this test goes RED. *This is the test that would have caught the earlier draft's
  false result.*
- `test_nested_year_folder_is_covered_on_cybos` — `decisions/2026/dec-x.md` **is** covered
  (`decisions/**/*.md`) — the `**` semantics, positively.
- `test_placement_is_derived_never_hardcoded` — assert `resolve_typed_write_dir` returns a **root**
  path on cybos and a **sibling** path on obsidian-personal **for the same `dir_name`**. A hardcoded
  "sibling" (the v5 draft) would silently never be walked by cybos's root-anchored globs.

## Exit criteria

- [ ] `pytest tests/ -q` ≥ 2477 passed. `mypy --strict scripts/` clean.
- [ ] **GREP-THE-SURFACES — the layout population is a denominator claim.** The test must iterate the
      registry, not a hand-typed list:
      ```python
      from scripts.wiki_index.layout_config import layout_choices
      # every built-in layout is classified: covered (typed classes indexable) or refused
      assert set(layout_choices()) == {"karpathy","flat","per-project","dev-project",
                                       "obsidian-personal","cybos"}   # pin the denominator
      ```
      so a **new** built-in layout cannot silently join the supported set without this test failing.
- [ ] **GREP:** `grep -rn "fnmatch" scripts/wiki_index/layout_config.py` ⇒ **no hits**. The engine has
      exactly one matcher.
- [ ] **MUT:** revert `full_match` → `fnmatch` ⇒ `test_glob_covers_uses_full_match_not_fnmatch` RED.
- [ ] **MUT:** hardcode the sibling placement ⇒ `test_placement_is_derived_never_hardcoded` RED.

## Rollback

Delete both helpers. No caller exists yet (063-03/063-05 add them).
