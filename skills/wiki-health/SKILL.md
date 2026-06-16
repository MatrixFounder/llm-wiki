---
name: wiki-health
description: >-
  Read-only DERIVED knowledge-health report over the event graph + frontmatter
  (R-15 / TASK 036, ADR-006). `wiki-health coverage` lists pages MISSING an
  expected relation — a requirement nothing implements, a capability no agent
  provides, a fact with no source. A gap is data, not a failure, so it ALWAYS
  exits 0. Its sibling lifecycle-drift (authored `status` contradicting the
  graph) rides `wiki-lint` and gates `--strict`. Triggers: "coverage gaps",
  "what requirements have no implementer", "facts without a source", "knowledge
  health", "wiki-health". NOT for full-text lookup — use wiki-search / wiki-query.
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
```

Every invocation prints a one-line JSON envelope (`{action, vault, rules,
total_gaps, by_class, gaps:[{slug, project, class, kind, missing}]}`; pipe to
`python3 -m json.tool`). `--class` restricts to one page class (an unknown class →
`INVALID_CLASS`, exit 2, without echoing the value); an unknown vault →
`VAULT_NOT_FOUND`, exit 6. `--db-path` / `--vault-root` resolve the index DB (TASK 022).

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

## Examples
- "Which requirements have no implementer?" → `wiki-health coverage --vault v --class requirement`.
- "Any facts with no source?" → `wiki-health coverage --vault v --class fact`.
- "Gate CI on stale decision status" → `wiki-lint --vault v --strict` (non-zero if drift).

## Caveat
Drift reads the **auto-derived inverse** edges, which a `wiki-reindex --delta` can leave
transiently stale on one side of a bidirectionally-authored edge until the next `--full`;
so `--strict` drift gating assumes a recent `--full`.
