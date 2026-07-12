# Task 061-01 — [LOGIC] Three denominators, three populations, per-rule `matched`

RTM: **R-061-1** (logic half). Depends on: `061-00`. Blocks: `061-02` (`wiki-health` envelopes)
**and `061-03`** (`wiki-lint` — it consumes **both** `find_lifecycle_drift_report` **and**
`find_ontology_violations_report`; the ontology numbers computed here are NOT `wiki-health`-only).

## Goal

Replace the `061-00` zeros with real counts, so a health report can never again say "0
violations" without saying **how much it examined**. There are **three** populations across the
two checks — `find_ontology_violations` iterates **edges** (domain/range) **and pages**
(property enums) **in one call**.

## Context (read first)

- `scripts/wiki_index/sqlite_repository/_health_rules.py` — all three finders. Note the two
  loops in `find_ontology_violations`: `for edge in ontology.edges:` (→ `FROM page_entity_refs`)
  and `for prop in ontology.properties:` (→ `FROM pages p`). **That is the two-population split.**
- `scripts/wiki_index/layouts/cybos.yaml:151-212` — the shipped rules: 3 drift, 3 coverage,
  7 ontology edges, 11 ontology properties.
- `scripts/wiki_index/layout_config.py:692-709` — `validate_ontology` gates every declared edge
  against `reindex._INVERSE_REF_TYPE`; `verifies` is **not in that map**, i.e. it is not merely
  undeclared but **undeclarable**. That is what makes the "declared edge vocabulary" a *positive*
  definition rather than a leaky one.

## Definitions (implement exactly these; they are the requirement)

| Denominator | Population | SQL |
|---|---|---|
| `pages_examined` (coverage) | pages whose **authored** `$.type` ∈ ⋃ `coverage_rules[].class` | `COUNT(*) FROM pages WHERE vault_id=? AND json_extract(frontmatter_json,'$.type') IN (…)` |
| `pages_examined` (drift, see `061-03`) | pages whose `$.type` ∈ ⋃ `drift_rules[].class` | same shape |
| `edges_examined` | `page_entity_refs` rows whose `ref_type` ∈ ⋃ `ontology.edges[].edge` (the **declared edge vocabulary** — NOT all refs; `mentioned` is excluded by construction) | `COUNT(*) FROM page_entity_refs WHERE vault_id=? AND ref_type IN (…)` |
| `property_pages_examined` | pages whose `$.type` ∈ ⋃ `ontology.properties[].class` | `COUNT(*) FROM pages WHERE …$.type IN (…)` |

Per-rule `matched` = **rows meeting that rule's precondition**:

- coverage rule `r`: pages with `$.type = r.page_class` (the gap condition is the `NOT
  EXISTS`/empty-field part, not the precondition).
- ontology **edge** rule `e`: the rows the existing loop already fetches for `ref_type = e.edge`
  → `matched_e = len(rows)`; **free, no extra query**.
- ontology **property** rule `p`: pages with `$.type = p.page_class` **AND**
  `json_type(frontmatter_json, '$.<field>') = 'text'` (a PRESENT scalar the rule can judge —
  an absent value is a coverage concern, not a contradiction; mirrors the finder's own filter).

`RuleStat.findings` per rule: coverage `{"gaps": n}` · edge `{"domain": n, "range": n}` ·
property `{"property": n}`.

## Changes — `scripts/wiki_index/sqlite_repository/_health_rules.py`

1. Private helpers (bound params only; **no `IN ()` ever** — PLAN P-061-C):

```python
def _count_pages_of_classes(self, vault_id: str, classes: set[str]) -> int:
    """0 when `classes` is empty — NEVER compose a degenerate `IN ()` (the
    hand-built-rule precedent above: skip, never crash, never inject)."""
def _count_refs_of_types(self, vault_id: str, ref_types: set[str]) -> int:
def _count_pages_with_scalar(self, vault_id: str, page_class: str, field: str) -> int:
    """field is validate_filter_field'd THEN bound as a `$.<field>` path."""
```

2. `find_coverage_gaps_report` / `find_ontology_violations_report`: compute the counts, tally
   per-rule findings while iterating (do not re-scan the result list twice), build the report.
3. **Collapse the legacy methods into wrappers** — `find_coverage_gaps` →
   `self.find_coverage_gaps_report(...).gaps`; same for drift/ontology. One code path ⇒ the
   findings and the denominators can never drift apart. (TC-00-2 in `061-00` is what makes this
   safe; keep it.)
4. COST comment: one extra COUNT scan per rule family (`$.type` is unindexed by design, P-5 —
   **no new index**); fine for the small typed partitions, mirrors the existing per-rule scan cost.

## Test cases — extend `tests/test_health_denominators.py`

1. **TC-01-1 (typed fixture ⇒ non-zero)** — `build_health_vault`: assert the EXACT numbers
   (derive them from `tests/_health_fixtures.py::_FILES`, e.g. coverage `pages_examined` counts
   the `requirement`+`capability`+`fact` pages = 2+1+3 = 6; ontology `property_pages_examined`
   counts every page whose `$.type` ∈ the 11 property classes). Compute the expectation in the
   test from the fixture dict, do **not** hand-copy a magic number.
2. **TC-01-2 (untyped fixture ⇒ 0 — THE VACUITY GATE)** — `build_cybos_vault` with only
   untyped pages (frontmatter with **no** `type:`, plus a `type: concept` page, which is a
   non-typed class): `pages_examined == 0`, `edges_examined == 0`,
   `property_pages_examined == 0` **while** `total_gaps == 0` / `total_violations == 0`. This is
   the LIVE-vault state, reproduced in CI.
3. **TC-01-3 (per-rule invariants — P-061-A)** — for every rule stat:
   `gaps_r ≤ matched_r ≤ pages_examined`; `domain_e ≤ matched_e` **AND** `range_e ≤ matched_e`
   **AND** `matched_e ≤ edges_examined`; `property_p ≤ matched_p ≤ property_pages_examined`.
   **A comment in the test states why `total_gaps ≤ pages_examined` is NOT asserted** (two rules
   may target one class ⇒ one page can gap twice — RTM constraint 3).
4. **TC-01-4 (matched is not a proxy for examined)** — a fixture with typed pages but **no**
   edges: coverage `pages_examined > 0` while the `requires_edge` rule's `matched > 0` and
   `gaps == matched` (every page gaps). Proves `matched` and the denominator are independent.
5. **TC-01-5 (legacy parity kept)** — TC-00-2 still passes after the wrapper collapse.

## Verification

```bash
source .venv/bin/activate
pytest tests/test_health_denominators.py tests/test_wiki_health.py tests/test_ontology_violations.py \
       tests/test_lifecycle_drift.py tests/test_health_rules_config.py -q
mypy --strict scripts/
```

## Acceptance criteria

- [ ] Three denominators with the three distinct nouns; `property_pages_examined` is **not**
      called `pages_examined`.
- [ ] Empty rule/edge/property sets ⇒ `0`, with **no SQL executed** (grep the diff for `IN ()`).
- [ ] `edges_examined` counts ONLY the declared edge vocabulary (a test asserts a `mentioned`-only
      vault reads `edges_examined == 0` even with thousands of refs — the LIVE 8836-ref trap).
- [ ] Legacy list methods are wrappers; all pre-existing health/lint/ontology tests unchanged and green.
