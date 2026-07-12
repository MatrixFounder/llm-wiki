# Task 061-07 — [LOGIC] `show.effective` = parsed dataclass OVERLAID on the merged raw dict

RTM: **R-061-4** (and turns `061-05`'s RED gate GREEN). Depends on: `061-05`.

## Goal

`wiki-config show`'s `effective` must be built by **overlaying the parsed dataclass onto the
merged raw dict** for **EVERY parsed cascading block** — today that is `summarize` **and**
`resummarize` (both take the frozen-dataclass path at `_provenance.py:320-324`) — stated
**generically**, so a future parsed block inherits the fix instead of re-introducing the bug.

Invariant to hold: **`show` never emits a `provenance` pointer with no corresponding `effective`
value.**

## Context

`scripts/wiki_skills/wiki_config/_provenance.py:306-334`:

```python
for block_name in cascading:                     # cascading comes from the SCHEMA (x-wiki-scope)
    ...                                          # merged = deep_merge of the raw blocks
    if block_name == "resummarize":              # <-- parsed  → dataclass fields ONLY
    elif block_name == "summarize":              # <-- parsed  → dataclass fields ONLY
    else:                                        # <-- raw passthrough (the future_block test)
```

`_assign_origins` (line 314) walks the **RAW** block ⇒ pointers exist for keys the dataclass
drops. That asymmetry IS the bug.

## Changes — `scripts/wiki_skills/wiki_config/_provenance.py`

1. A **dispatch table**, so "which blocks are parsed" is one declaration, not two `elif`s:

```python
_PARSED_BLOCKS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "resummarize": lambda merged: _parse_resummarize(merged),
    "summarize":   lambda merged: _parse_summarize(merged) or SummarizeConfig(),
}
```

2. A **deep** overlay (shallow is not enough — a nested `resummarize.detect.<new>` key must
   survive too; `061-05`'s third param proves it):

```python
def _overlay_parsed(raw: dict[str, Any], parsed: Any) -> Any:
    """R-061-4: the PARSED value wins for every key the dataclass declares (defaults
    injected, values normalised); every raw key the dataclass does NOT declare is
    PRESERVED. Recurses on dict/dict — mirrors deep_merge's branch condition, the same
    discipline `_assign_origins` follows, so `effective` and `origins` cover the SAME
    pointer set (that equality is the tested invariant)."""
```

3. Rewrite the fold body:

```python
parser = _PARSED_BLOCKS.get(block_name)
if parser is not None:
    parsed = _to_jsonable(parser(merged)) if (found or block_name == "summarize") else None
    effective_block = _overlay_parsed(merged, parsed) if parsed is not None else None
else:
    effective_block = merged if found else None      # unchanged raw-passthrough branch
```

Preserve today's two semantics **exactly**: `resummarize` absent ⇒ `None`; `summarize` absent ⇒
the default `SummarizeConfig()` (never `None`).

4. `_tag_defaults` needs **no** change — it only tags pointers with **no** origin, and a
   raw-only key already has one from `_assign_origins`. **Verify by reading it (line 212), don't
   assume**; add a test asserting a raw-only key's origin is its LEVEL, not `default`.

## Test cases

1. **Remove the `xfail(strict=True)` marker** from `test_parsed_block_unknown_key_reaches_effective`
   (`061-05`) ⇒ all 3 params GREEN. *This is the R-061-5 acceptance: RED before, GREEN after.*
2. **TC-07-1 (the invariant, over every fixture)** — add to the shared assertions used by the
   existing provenance fixtures: `set(provenance) ⊆ {pointers reachable in effective} ∪ {block
   pointers}` — i.e. no pointer without a value. Run it over **all** the existing cascade
   fixtures (`_ROOT_FULL`, `_CHILD_GROUP_KEY`, Cyrillic/space folders, three-level shadow chain).
3. **TC-07-2 (parsed still wins)** — a raw `summarize.target_subdir: "  x/  "` still shows the
   **normalised** parsed value (`"x"`), not the raw string; `resummarize.mode` default
   (`if-missing`) still appears when absent. Proves the overlay did not become a raw passthrough.
4. **TC-07-3 (origin of a raw-only key)** — the synthetic key's origin is the level that defined
   it (not `"default"`).
5. **TC-07-4 (report row)** — `wiki-config report` renders a row for the synthetic key
   (already covered by `061-05`'s report assertion; keep it).
6. **Equivalence release-gate untouched** — `_assert_equivalence` (engine merged+parsed == the
   REAL resolver) must still pass **unchanged**: the overlay changes `effective` (a *display*
   surface), never `merged_raw` (the resolver-equivalence surface). Confirm both properties still
   hold for every fixture.

## Verification

```bash
source .venv/bin/activate
pytest tests/test_wiki_config_provenance.py tests/test_wiki_config_cli.py tests/test_wiki_config_validate.py \
       tests/test_wiki_config_doctor.py -q
pytest tests/ -q
mypy --strict scripts/
```

Prove the gate one more time, by hand, and paste the output into the commit message:

```bash
git stash push scripts/wiki_skills/wiki_config/_provenance.py
pytest tests/test_wiki_config_provenance.py::test_parsed_block_unknown_key_reaches_effective -q   # MUST FAIL (3)
git stash pop
pytest tests/test_wiki_config_provenance.py::test_parsed_block_unknown_key_reaches_effective -q   # MUST PASS (3)
```

## Acceptance criteria

- [ ] A new field inside **either** parsed block appears in `show.effective` **and** gets an HTML
      report row.
- [ ] The parsed-block set is **one declaration** (`_PARSED_BLOCKS`), not an `elif` chain — a
      future parsed block inherits the fix.
- [ ] The `provenance ⇒ effective` invariant is asserted over every fixture.
- [ ] `test_evolution_new_schema_field_needs_no_code` (raw-passthrough `else` branch) still passes.
