---
name: wiki-health
description: >-
  Read-only DERIVED knowledge-health report over the event graph + frontmatter
  (R-15 / TASK 036, ADR-006). `wiki-health coverage` lists pages MISSING an
  expected relation — a requirement nothing implements, a capability no agent
  provides, a fact with no source. A gap is data, not a failure, so it ALWAYS
  exits 0. Its sibling lifecycle-drift (authored `status` contradicting the
  graph) rides `wiki-lint` and gates `--strict`. `wiki-health ontology` (R-19)
  reports pages that contradict the declared ontology contract (edge domain/range,
  property enums). Triggers: "coverage gaps", "what requirements have no implementer",
  "facts without a source", "ontology violations", "does this edge point at the right
  type", "knowledge health", "wiki-health". NOT for full-text lookup — use wiki-search /
  wiki-query.
tier: 2
version: 1.0
---

# wiki-health

Read-only **derived knowledge health** (R-15 / TASK 036 / ADR-006): views computed
over `pages.frontmatter_json` + the `page_entity_refs` event graph — no new fields,
no DDL. Rules are layout-config-driven (`coverage_rules` / `drift_rules` in
`layouts/*.yaml`; the **cybos** layout ships them, other layouts → an empty report).

```bash
# pages missing an expected edge/field (always exit 0 — a gap is data)
wiki-health coverage --vault <id> [--class requirement]
# pages CONTRADICTING the declared ontology contract (R-19; always exit 0 — report view)
wiki-health ontology --vault <id> [--class decision]
```

Every invocation prints a one-line JSON envelope. **coverage**: `{action, vault, rules,
total_gaps, pages_examined, by_rule, by_class, vacuous_populations, vacuous_kinds,
gaps:[{slug, project, class, kind,
missing}]}` where `kind ∈ {edge, field, field-value}` (see below).
**ontology**: `{action, vault, total_violations, edges_examined,
property_pages_examined, by_rule, by_kind, by_class, vacuous_populations, vacuous_kinds,
violations:[{slug, project, class, kind, ref, detail, target}]}` where
`kind ∈ {domain, range, property}`. Pipe to
`python3 -m json.tool`. `--class` restricts to one page class (an unknown class →
`INVALID_CLASS`, exit 2, without echoing the value); an unknown vault →
`VAULT_NOT_FOUND`, exit 6. `--db-path` / `--vault-root` resolve the index DB (TASK 022).

### A gap has THREE shapes — read `kind`, not just the count (TASK 072 / P2)
`gaps[].kind` says **why THIS page is a gap**:

| `kind` | meaning | rule shape |
|---|---|---|
| `edge` | the page carries no typed edge of that ref_type | `requires_edge: implemented-by` |
| `field` | the frontmatter scalar is **absent or empty** (`''`/`[]`/`{}`) | `requires_field: source` |
| `field-value` | the scalar is **PRESENT and a non-answer** | `requires_field: … ` + `forbid_values: […]` |

`field-value` exists because a page can satisfy every *absence* check and still say
nothing: `verified_on: "not verified"` is present, non-empty, and worthless. Without the
modifier such a page reports as **covered** — not a vacuous green (the denominator is
honest) but a blind spot no reading of the numbers reveals. ADR-006 D-036-3a.

⚠️ **The offending VALUE is deliberately NOT in the envelope.** `missing` carries the FIELD
NAME for all three kinds — the value is untrusted frontmatter (H-6), and `kind` plus the
rule's own declared vocabulary already say everything actionable. Open the page.

⚠️ **`forbid_values` sentinels ship in NO built-in layout** — they are an authoring
convention and live in the operator's `<vault>/.wiki/layout.yaml`. If you expected
`field-value` findings and got none, check that the vault actually declares the rule.
`by_rule[].kind` is `field-value` for a forbid-carrying rule, so the envelope tells you
which rules can produce that kind without re-reading the layout.

### Read the DENOMINATOR, not just the count (TASK 061 / R-061-1)
`{"total_gaps": 0}` alone is **ambiguous**: it means either "healthy" or "**nothing was
examined**". So every report envelope also states the population it actually looked at:

- **coverage** — `pages_examined` = pages whose *authored* `$.type` is in ⋃ the (possibly
  `--class`-filtered) `coverage_rules[].class`. A page with no `type:`, or a non-rule class
  (`concept`/`moc`/`*-summary`), is **not examined**.
- **ontology** — **TWO** denominators, because one call spans two populations:
  `edges_examined` = `page_entity_refs` rows whose `ref_type` is in the contract's declared
  edge vocabulary (a `mentioned` wikilink is **not** one); `property_pages_examined` = pages
  whose `$.type` is in ⋃ `properties[].class`. Deliberately *not* one shared `pages_examined`.
- **`by_rule`** — per rule: `{class, kind, ref, matched, matched_by_kind, findings}`.
  `matched` = rows meeting that rule's **precondition**; `findings` is a **dict per kind**
  (one examined edge row can be *both* a `domain` and a `range` violation).
- **`matched_by_kind`** — ⚠️ **the number you must actually read.** `matched` counts rows the
  check **cannot judge**: an edge rule's `domain` fires only on a **typed source** page, its
  `range` only on a **resolved + typed target**. A vault whose `uses` refs all point at
  dangling or untyped targets reports `{matched: 500, findings: {domain: 0, range: 0}}` —
  which *reads* as "500 examined, all clean" while `range` examined **zero**. Mirrors
  `findings` key for key (`set(matched_by_kind) == set(findings)`).
- **`vacuous_populations`** — the `*_examined` denominators that are `0`. `[]` = every
  population had something in it. A **partial** zero counts: `{edges_examined: 0,
  property_pages_examined: 1}` means all seven edge rules judged **nothing**.
- **`vacuous_kinds`** — `[{class, kind, ref, finding_kind}]`: rules that **matched rows but
  could judge none of them**. `[]` = no rule's count is a lie. A rule with `matched: 0` is
  *not* listed — it is openly empty (see its `by_rule` row), not hiding.
- **`note`** — emitted when *any* population or rule×kind examined nothing *while rules are
  configured*, naming **which**: the report says out loud that it is **not a clean bill of
  health**. (A layout with **no** rules / **no** `ontology:` block gets its own, different
  note.)

**`total_violations: 0` / `total_gaps: 0` is a clean bill of health ONLY when
`vacuous_populations == []` and `vacuous_kinds == []`.** Do not re-derive this yourself; the
CLI has already done it.

Invariants hold **per rule, per kind, against that rule's own family denominator**:

```
∀ kind k:  findings[k] ≤ matched_by_kind[k] ≤ matched ≤ <family denominator>
```

Do **not** compute health from `matched` alone — that is the number proven above not to be
judgeable. Do **not** read `total_gaps ≤ pages_examined`: two rules may target one class, so
a page can gap twice and the total can exceed the population.


> **`--class` scoping (ontology).** The envelope echoes `class_filter`. Note the asymmetry: `--class` narrows
> only `violations[]` (it is applied AFTER the DAL call), so `edges_examined` / `property_pages_examined` /
> `vacuous_populations` / `vacuous_kinds` **describe the WHOLE run, not the filtered class**. Do not read
> `{total_violations: 0, edges_examined: 500}` under `--class decision` as "500 decision edges were judged".

## Ontology contract (R-19 / TASK 054)
`wiki-health ontology` is the **always-exit-0 report** over the layout's declared
`ontology:` block (cybos only): `closed_types`, `edges` (per-ref_type domain→range),
`properties` (per-class value enums). An **edge domain/range or property** contradiction
is *also* surfaced by `wiki-lint` as `ontology-violation` (advisory; **gates `--strict`**)
— the CI-gating rail. `closed_types` is enforced at **index time** (reindex SKIPS a page
whose authored `$.type` ∉ the roster, reported in `wiki-reindex --full`'s `skipped[]`), so
it produces no separate read-side finding (Q-054). NOT a write gate — a violating page
still indexes (markdown canonical, ADR-002 §D8).

## Two surfaces, one machinery (D-036)
- **Coverage = an *absence*** (expected on a young vault) → `wiki-health coverage`,
  **always exit 0**. cybos rules: requirement/capability with no `implemented-by`;
  fact with an empty/absent `source:`.
- **Lifecycle-drift = a *contradiction*** (authored `status` vs the graph — e.g. a
  decision carrying a `superseded-by` edge but still `status: accepted`) → it rides
  **`wiki-lint`** (category `lifecycle-drift`): advisory by default, **non-zero under
  `--strict`**. Run `wiki-lint --vault <id> [--strict]` for drift.

## Routing
- Find or answer ABOUT content → `wiki-search` / `wiki-query` FIRST (unchanged).
- "What's missing / where are the gaps?" → `wiki-health coverage`.
- "Is anything's status stale vs the graph?" → `wiki-lint` (lifecycle-drift) / `--strict` to gate.
- "Does anything violate the ontology (wrong edge type / bad status value)?" →
  `wiki-health ontology` (report) or `wiki-lint --strict` (gate `ontology-violation`).

## Examples
- "Which requirements have no implementer?" → `wiki-health coverage --vault v --class requirement`.
- "Any facts with no source?" → `wiki-health coverage --vault v --class fact`.
- "Gate CI on stale decision status" → `wiki-lint --vault v --strict` (non-zero if drift).
- "Do any decisions implement the wrong type / carry a bad status?" →
  `wiki-health ontology --vault v --class decision`.

## Caveat
Drift reads the **auto-derived inverse** edges, which a `wiki-reindex --delta` can leave
transiently stale on one side of a bidirectionally-authored edge until the next `--full`;
so `--strict` drift gating assumes a recent `--full`.
