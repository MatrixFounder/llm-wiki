# Task 061-04 — [STUB / PURE REFACTOR] One shared external-provenance-key constant → BOTH halves

RTM: **R-061-3** (structure half — **zero behavior change**). Depends on: nothing.
Blocks: `061-06` (which extends the constant and changes behavior).

## Goal

Today the external-origin key list is **duplicated across 6+ surfaces**. Make **one constant**
the source of truth and *render* both halves from it — Python `_is_external` **and** the `_EXT`
SQL literal — with the Q-050-3 alignment test **parametrized FROM the constant**, so a future
key cannot drift the halves apart. This bead ships the **same 3 keys** as today: the suite must
be green with **zero behavior change**. `061-06` then flips behavior by editing one tuple.

## Context (grep, don't believe — this is the surface census)

| Site | What it holds today |
|---|---|
| `scripts/wiki_index/policy.py:240-256` | `_is_external`: `for key in ("source", "URL", "url")` |
| `scripts/wiki_index/sqlite_repository/_search.py:128-167` | `_min_trust_clauses`: `_EXT` built with `for k in ("source", "URL", "url") for scheme in ("http","https")` (8 `LIKE` disjuncts: 2 path + 6 key×scheme) |
| `scripts/wiki_index/repository.py:254-265` | `search_pages` docstring **re-enumerates** `$.source`/`$.URL`/`$.url` |
| `skills/wiki-query/SKILL.md:86-87` | prose re-enumeration |
| `docs/architectures/functional/policy-and-trust.md:38` | prose re-enumeration |
| `docs/manuals/obsidian-llm-wiki_manual.md:1811` (+ RU `:1860`) | prose re-enumeration |

The prose surfaces are corrected in `061-09`; **this** bead owns the two executable halves +
the docstrings that reference them.

## Changes

### `scripts/wiki_index/policy.py`

```python
EXTERNAL_PROVENANCE_KEYS: tuple[str, ...] = ("source", "URL", "url")
"""TASK 061 / R-061-3 — the ONE source of truth for the frontmatter keys whose
`http(s)://` SCALAR marks EXTERNAL origin. Rendered into BOTH halves of the
Q-050-3 alignment contract: the Python `_is_external` loop below AND the `_EXT`
SQL literal in `sqlite_repository/_search.py`. Never re-enumerate these keys —
import the constant. (061-06 extends this tuple with the case variants; the
parametrized alignment test in tests/test_trust_tier.py is driven from it, so
both halves and the test move together or not at all.)

Every entry MUST be a bare identifier ([A-Za-z_][A-Za-z0-9_]*): it is interpolated
into a FIXED `$.<key>` json path in SQL. Asserted at import (see _assert below)."""
```

Add a module-level shape guard (cheap, explicit injection posture — the keys are ours, not the
operator's, and this keeps it that way):

```python
_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
assert all(_KEY_RE.fullmatch(k) for k in EXTERNAL_PROVENANCE_KEYS)
```

`_is_external` iterates `EXTERNAL_PROVENANCE_KEYS`; its docstring **references** the constant
instead of listing keys.

### `scripts/wiki_index/sqlite_repository/_search.py`

`from scripts.wiki_index.policy import EXTERNAL_PROVENANCE_KEYS` (module-level import: `policy`
is a pure module whose only heavy import is lazy/inside a function — confirm no cycle with
`python3 -c "import scripts.wiki_index.sqlite_repository"`). Build `_EXT` from the constant;
keep the comment's *rationale* (LIKE ASCII-ci fold, `_` escaped, exact `http(s)://` prefix,
non-scalar rejected) but drop the key enumeration.

### `scripts/wiki_index/repository.py:254-265`

`search_pages`'s `min_trust` docstring: replace the key list with "an `http(s)://`-prefixed
scalar under one of `policy.EXTERNAL_PROVENANCE_KEYS`".

## Test cases — `tests/test_trust_tier.py`

1. **TC-04-1 (alignment, parametrized FROM the constant)** — replace/extend the hand-written
   `test_sql_floor_matches_python_on_all_shapes` corpus with a test parametrized over
   `EXTERNAL_PROVENANCE_KEYS × ("http", "https")`: for each, upsert a page carrying that key and
   assert (a) `trust_tier(...) == "external"` (Python half) **and** (b) `--min-trust internal`
   excludes it in SQL (SQL half). Adding a key to the constant therefore **automatically**
   extends the gate — that is the anti-drift property Q-050-3 demands.
2. **TC-04-2 (render count)** — `_EXT` (or a small helper that returns it) contains exactly
   `2 + 2*len(EXTERNAL_PROVENANCE_KEYS)` `LIKE` disjuncts. Guards against a half-applied edit.
3. **TC-04-3 (single enumeration — the grep-test)** — new
   `tests/test_trust_key_single_source.py`: walk `scripts/**/*.py`, assert **no file other than
   `policy.py`** contains a literal tuple/list enumerating the provenance keys (regex over the
   source text, e.g. `("source"` adjacent to `"url"`/`"URL"`). Converts *"grep, don't believe"*
   into an executable gate.
4. Existing `test_trust_tier_matrix` cases stay green **unchanged** (zero behavior change).

## Verification

```bash
source .venv/bin/activate
pytest tests/test_trust_tier.py tests/test_trust_key_single_source.py tests/test_wiki_query*.py -q
mypy --strict scripts/
python3 -c "import scripts.wiki_index.sqlite_repository, scripts.wiki_index.policy"   # cycle check
git diff --stat   # must show NO change to any docs/tasks/task-050-* or docs/plans/plan-050-*
```

## Acceptance criteria

- [ ] Exactly **one** enumeration of the keys in `scripts/` (TC-04-3 proves it).
- [ ] `_EXT` and `_is_external` are both **rendered from** the constant.
- [ ] **Zero behavior change**: the full suite is green with no test's expectations edited.
