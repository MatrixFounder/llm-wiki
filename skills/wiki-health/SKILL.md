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
total_gaps, by_class, gaps:[{slug, project, class, kind, missing}]}`. **ontology**:
`{action, vault, total_violations, by_kind, by_class, violations:[{slug, project, class,
kind, ref, detail, target}]}` where `kind ∈ {domain, range, property}`. Pipe to
`python3 -m json.tool`. `--class` restricts to one page class (an unknown class →
`INVALID_CLASS`, exit 2, without echoing the value); an unknown vault →
`VAULT_NOT_FOUND`, exit 6. `--db-path` / `--vault-root` resolve the index DB (TASK 022).

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
