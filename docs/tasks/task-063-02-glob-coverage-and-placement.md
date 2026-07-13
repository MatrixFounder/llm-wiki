# TASK 063-02 — the walker-chain coverage helper · placement derivation · `dev-project` globs

**Phase**: 1 (the gate) · **RTM**: R-063-3 (G4), R-063-3′ · **Type**: code + config · **Effort**: 4h
**Depends on**: 063-00 · **Unblocks**: 063-03, 063-05, 063-12
**Revision**: v2 — plan-review **C-2, C-2b, C-3, C-4, m-10** applied (PLAN §8).

## Goal

**One goal, two halves:** *make the write placement and the read grammar agree — for every supported
layout.* That means the coverage helper **and** the `dev-project.yaml` globs, because a helper that
correctly reports "dev-project cannot see this" while the spec says dev-project is supported is not a
gate — it is a contradiction with a test suite.

This is the **single** implementation of the G4 load gate, shared by its two callers
(`wiki-config validate` → 063-03, and `prepare`'s preflight → 063-05). *One gate, two callers, never
two implementations.*

---

## ★ Part 1 — `glob_covers` is the walker's **FULL FILTER CHAIN** (plan-review C-3)

> **v1's helper enumerated 1 of 5 conjuncts, and its docstring said *"i.e. the READ walker can SEE a
> file written there."* That "i.e." IS the lens** — the G4 gate, with the G4 hole.

`iter_pages` visibility (`layout_config.py:1197-1213`) is a **conjunction**:

```
suffix ∈ config.file_extensions
  ∧ name ∉ SYSTEM_FILES
  ∧ rel ∉ {auto_indexes[].output}
  ∧ ¬ _matches_ignore(rel, config.ignore)          ← ★ the conjunct v1 missed
  ∧ ∃ paths[] glob alive at this dir that matches
  ∧ S_ISREG(stat)                                   ← (the probe is a real file, so this holds)
```

**The concrete, reachable failure v1 permitted:** `dirs.decision: "_raw"` on the operator's PARA
vault ⇒ `[0-9][0-9] - */*/**/*.md` **matches** ⇒ v1's gate says **COVERED** ⇒ but `**/_raw/**` is in
`ignore` ⇒ the walker **skips it** ⇒ **a glob-invisible page, zero lint issues.** *The precise loss
G4 exists to prevent, arriving through the conjunct the gate did not enumerate.*

```python
def glob_covers(config: LayoutConfig, rel_posix: str) -> bool:
    """True iff a real `.md` file at `rel_posix` would be DISCOVERED by `iter_pages` —
    the walker's full filter chain, not just a `paths[]` match. Equivalence with the
    real walk is MEASURED, not asserted (see the test below)."""

def resolve_typed_write_dir(config: LayoutConfig, *, dir_name: str, source_rel: str) -> str | None:
    """DERIVE the placement of a typed page → the vault-relative POSIX DIRECTORY it must be
    written to, or None if NEITHER placement is walker-visible (⇒ the caller REFUSES —
    Q-063-5(A): `sync.yaml` must never mutate `layout.yaml`)."""
```

**`resolve_typed_write_dir` probes, in order:** (1) root-anchored `f"{dir_name}/{PROBE}.md"` → covered
⇒ return `dir_name`; (2) sibling `f"{parent(source_rel)}/{dir_name}/{PROBE}.md"` → covered ⇒ return
it; (3) neither ⇒ `None`. `PROBE` is a fixed slug-shaped sentinel — the gate answers *"can the walker
see a `.md` file in this **directory**"*, a property of the directory, not of any one slug.

### ⚠️ The matcher: `PurePosixPath.full_match`, **never** `fnmatch` — and the gate is **scoped** (C-4)

v1's exit criterion — *"`grep fnmatch layout_config.py` ⇒ no hits"* — is **FACTUALLY FALSE and can
never go green**. The engine **imports** fnmatch (`:30`) and calls `fnmatch.fnmatchcase` at **`:1055`**
and **`:1085`** — the per-**segment** matcher of the TASK-030 single-pass walk, where it is **correct**
(it never crosses `/`). *"Exactly one matcher" was itself an ungrepped denominator* — and a developer
"satisfying" v1's gate by deleting those calls **breaks the walk**.

**The scoped gate:** `glob_covers` must use `full_match`; the 3 pre-existing hits are **pinned by line
and count** so the gate cannot be satisfied by deleting them (see Exit criteria).

*Why `full_match` at all:* `fnmatch` lets `*` cross a `/`, so it answers **MATCH** for
`decisions/2026/dec.md` against `decisions/*.md` where the real engine answers **NO**. An earlier spec
draft measured with `fnmatch` and reported a false result.

---

## ★ Part 2 — `dev-project.yaml` gains the three typed globs (plan-review C-2)

**Verified:** `layouts/dev-project.yaml:75-77` **maps** `decision`/`requirement`/`risk` in
`type_mapping`, but `:33-57` has **no `decisions/**`, `requirements/**`, `risks/**` glob and no
catch-all** ⇒ `resolve_typed_write_dir` returns `None` ⇒ **`prepare` refuses dev-project via its own
preflight** ⇒ the three planned `vacuous_validation` tests could never pass.

The spec's §"File surface" **already names `layouts/dev-project.yaml` as a file to edit.** So:

```yaml
# scripts/wiki_index/layouts/dev-project.yaml — paths[], additive
  - {glob: "decisions/**/*.md",    type: decision,    project: "_vault_"}
  - {glob: "requirements/**/*.md", type: requirement, project: "_vault_"}
  - {glob: "risks/**/*.md",        type: risk,        project: "_vault_"}
```

Additive, **zero-DDL**, and **no walk change today** (no such dirs exist). `karpathy.yaml` is
**byte-identity-anchored — never touch it**; `obsidian-personal.yaml` is likewise untouched (the
`para-typed` fixture supplies the classes via a `.wiki/layout.yaml` override — PLAN §1).

---

## Tests (RED first) — `tests/test_layout_typed_write_dirs.py` (new)

### The measurement that covers all five conjuncts, forever (C-3)

```python
def test_glob_covers_agrees_with_the_real_walk(tmp_path):
    """MEASURE the helper against iter_pages — never ASSERT the chain from memory.
    This mechanically covers every conjunct the walker has TODAY and every one it
    gains LATER, without this test being edited."""
    for dir_name in ("decisions", "_raw", ".obsidian", "риски", "docs"):
        rel = f"{dir_name}/probe.md"
        write(tmp_path / rel)
        walked = {p.path.relative_to(tmp_path).as_posix() for p in iter_pages(tmp_path, cfg)}
        assert glob_covers(cfg, rel) == (rel in walked)      # ⟺, both directions
```
- **The `_raw` case is the C-3 bug, pinned**: on `para-typed` it **matches a `paths[]` glob** yet is
  **ignored** by the walker ⇒ `glob_covers` must be **False**. **MUT:** implement `glob_covers` as a
  bare `paths[]` match ⇒ RED.

### The placement matrix — from the PLAN §1 fixture roster, never invented per-bead (C-2b)

| fixture | dir_name | source_rel | expected |
|---|---|---|---|
| `cybos` | `decisions` | `meetings/m1.md` | `"decisions"` (**root**) |
| `cybos` | `decisions/2026` | — | covered (`decisions/**/*.md`; the `**` semantics, positively) |
| `cybos` | `решения` | `meetings/m1.md` | **`None`** — refused (strict by design) |
| `dev-project` (post-Part-2) | `decisions` | `tasks/t1.md` | `"decisions"` (**root**) |
| **`para-typed`** | `решения` | `06 - BD/Acme/note.md` | `"06 - BD/Acme/решения"` (**sibling**, Cyrillic OK) |
| **`para-typed`** | `_raw` | `06 - BD/Acme/note.md` | **`None`** — the ignore conjunct |
| `karpathy` | any | — | **`None`** |
| `obsidian-personal` (stock) | any | — | **`None`** (zero typed classes) |

- `test_placement_is_derived_never_hardcoded` — the same `dir_name` yields a **root** path on cybos
  and a **sibling** path on `para-typed`. **MUT:** hardcode "sibling" (the v5 draft) ⇒ cybos RED
  (and the page would be glob-invisible — the silent loss G4 exists to prevent).

### ★ The supported-set gate — **the CONJUNCTION** (C-2; this is the one v1 fumbled)

```python
SUPPORTED = {"cybos", "dev-project"}     # + any vault whose .wiki/layout.yaml adds the classes

def test_supported_layouts_are_the_conjunction():
    for name in layout_choices():                      # the population, from the registry (m-10)
        cfg  = _config_for(name)                       # resolve_layout_config / load_layout_config
        maps = bool({"decision","requirement","risk"} & set(cfg.type_mapping))
        sees = all(resolve_typed_write_dir(cfg, dir_name=d, source_rel=PROBE_SRC) is not None
                   for d in ("decisions","requirements","risks"))
        assert (maps and sees) == (name in SUPPORTED)   # ★ NOT `maps` alone — v1's bug
```
**MUT:** assert on `maps` alone ⇒ the test goes **green while the rail refuses dev-project** — which
is exactly the state v1 shipped. Run this mutation and confirm it produces the v1 false-green, then
restore the conjunction. *A gate that passes in the broken state is not a gate.*

⚠️ **m-10:** `resolve_layout_config_by_name` **does not exist**. Real APIs:
`resolve_layout_config(vault_root)`, `load_layout_config(vault_root, root_config)`,
`_builtin_registry()`, `layout_choices()`. Build `_config_for(name)` in the test's conftest from those.

## Exit criteria

- [ ] `pytest tests/ -q` ≥ 2477 passed, 0 failed. `mypy --strict scripts/` clean.
- [ ] **The walk-equivalence test passes for every dir_name in its matrix** — and it is written as a
      `⟺` against a **real `iter_pages` walk**, not as a restatement of the chain. *That is the
      difference between a gate and a paraphrase.*
- [ ] **GREP (scoped, C-4):** the new helper uses `full_match`, and the pre-existing `fnmatch` hits are
      **pinned by count** so the gate cannot be "satisfied" by breaking the walk:
      ```bash
      grep -c "fnmatch" scripts/wiki_index/layout_config.py            # → 4 (import :30, doc :1012,
                                                                       #     fnmatchcase :1055, :1085)
      ```
      ```python
      # RUN, don't reason: read the helper's OWN source, not the file's.
      assert "fnmatch" not in inspect.getsource(glob_covers)
      ```
      i.e. **`glob_covers` contains no `fnmatch`; the TASK-030 segment matcher is untouched.** The count
      pin (`→ 4`) and the source assertion are **complementary**: an `fnmatch` added *inside* `glob_covers`
      breaks both; one added *elsewhere* breaks only the count.
      ⚠️ **Do NOT** write this as `grep -n fnmatch <file> | grep -c "def glob_covers"` — that pipes
      fnmatch-matching lines into a search for the *def line*, so it is `0` **by construction**, whether or
      not the helper uses `fnmatch`. A gate that cannot fail. (Caught by plan-review; the very lens this
      bead exists to close — see PLAN §0.)
- [ ] **GREP:** `git diff --name-only -- scripts/wiki_index/layouts/` ⇒ **`dev-project.yaml` ONLY.**
      karpathy is byte-identity-anchored; obsidian-personal is out of scope (spec §7).
- [ ] `wiki-reindex --full` on a dev-project vault **before and after** the glob addition produces an
      **identical** page set (no `decisions/` dir exists ⇒ additive means additive). Measure it.

## Rollback

Delete both helpers + revert the 3 YAML lines. No caller exists yet (063-03/063-05 add them).
