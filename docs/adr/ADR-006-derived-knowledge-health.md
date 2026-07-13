# ADR-006 — Derived knowledge health (lifecycle-drift + coverage)

- **Status:** Accepted (TASK 036 / ROADMAP R-15, Track A) — 2026-06-16
- **Supersedes / relates:** builds on ADR-003 (typed classes), ADR-004 (event graph),
  and the TASK-034 `--as-of` temporal walk; sibling of ADR-005 (FTS-narrowed membership).

## Context

A third RFC batch (RFC-007 Evolution · 008 Evidence · 009 Pattern Mining · 010 Coverage ·
011 Retrieval Context Builder) proposed turning the knowledge graph into a system that
detects gaps and tracks knowledge evolution. Audited against the project invariants
(Class A/B/C layering, **zero-DDL**, **"derive, don't author new fields"** — the TASK-034
`valid_to` precedent), most of it is either already shipped (RFC-011 ≈ `wiki-query
--follow-edges`) or an anti-pattern (RFC-007's `type: transition` / `confidence`, RFC-008's
`type: evidence` + `strength` — both author state derivable from the graph and force a
schema bump). The high-value, in-architecture residue collapses into ONE capability: a
Class-B **derivation/analysis layer** that computes views over the existing
`pages.frontmatter_json` + `page_entity_refs` graph, adding no fields and no DDL.

Two such views are the same query machinery (`EXISTS`/`NOT EXISTS` of a typed edge against a
page's authored `$.status`/`$.type`):

- **lifecycle-drift** — the AUTHORED `status` *contradicts* the graph (a decision carrying a
  `superseded-by` edge but still `status: accepted`). This is the derivable half of RFC-007.
- **coverage gaps** — a page is *missing* an expected relation (a requirement nothing
  implements; a fact with no `source:`). This is RFC-010.

## Decision

**D-036-1 — Build a read-only Class-B health layer; reject authored lifecycle state.**
`find_lifecycle_drift` / `find_coverage_gaps` DAL methods compute the views from existing
data. No new frontmatter fields, no new page types, no schema migration (`user_version`
stays 7). `type: transition`, `confidence`, `type: evidence`+`strength`, and any auto-fix
that mutates a Class-A `status` are rejected.

**D-036-2 — Same machinery, two surfaces, split by base-rate/actionability (NOT
semantics).** Drift is a *contradiction* (almost always a real defect) → it rides
**`wiki-lint`** as a new `lifecycle-drift` issue category and inherits the existing exit
policy: advisory by default, non-zero only under **`--strict`** (the one SEMANTIC check that
belongs on lint's CI gate). Coverage is an *absence* (expected, high base-rate on a young
vault) → a separate read-only **`wiki-health coverage`** CLI that **always exits 0** (a gap
is data, not a failure). Gating coverage would cry wolf; reporting drift only-on-`--strict`
would hide a contradiction. The discriminator is actionability, not "semantic vs structural".

**D-036-3 — Rules are layout grammar, validated at load.** `drift_rules` / `coverage_rules`
live in `layouts/*.yaml` (cybos is the only **built-in** that ships them; the other built-ins
default to none → the checks no-op). An operator's own `.wiki/layout.yaml` may ship rules too —
and the live `personal` vault does, which is precisely why D-036-4 below matters: **declared
rules with an empty population are the vacuous-green case, not the no-op case.** The
*machinery* is universal; the *rules* are layout-specific. Edge vocabulary is
validated against `reindex._INVERSE_REF_TYPE` (the same allow-list `wiki-graph` traverses)
and field names against the metadata-filter allow-list, at config-load (fail-loud, exit 6).
A page is keyed by `json_extract(frontmatter_json,'$.type')` — the RAW class, NOT
`pages.type` (the db-bucket). The `EXISTS` correlation uses `page_slug = p.slug AND
page_project = p.project` (the auto-derived inverse edge — unambiguous on the page side, so
no cross-project COUNT guard is needed). Only a SCALAR text status (`json_type='text'`) is a
contradiction; NULL/list/object statuses are never drift.

**D-036-4 — THE DENOMINATOR CONTRACT: a report states what it EXAMINED.** *(Amendment —
TASK 061 / R-061-1, 2026-07-13. Does not change D-036-1..3; it closes a reporting hole in
them.)*

D-036-2 makes a coverage gap "data, not a failure" and always exits 0. That is right — but
it left `{"total_gaps": 0}` **indistinguishable from a real green**. On the live vault every
health surface reported `0` because **nothing typed existed to examine**, not because
anything was healthy. A check that examined nothing reported green, and so every "0
violations" observed to date carried **zero information**.

Therefore: **every health report emits its DENOMINATOR — the size of the population it
actually examined — and says so explicitly (an honest `note`) when that denominator is 0.**
Denominators are read-side `COUNT(*)` over existing columns: **zero DDL**, `user_version`
stays 7; the keys are **additive only** (every pre-061 consumer still parses). They are
**reporting, never gating** — `wiki-lint --strict`'s exit code still rides the issues alone,
and `wiki-health` still always exits 0.

**One noun per POPULATION — and the populations are not interchangeable.** The count of
populations is a **grep result, not an intuition**: `find_ontology_violations` iterates
**edges** (for domain/range) *and* **pages** (for property enums) **in one call**, so a
single denominator there would answer *"how many pages did the ontology check?"* with a
count of **refs** — reproducing the very bug this amendment fixes, one layer down.

| Surface | Population examined | Noun |
|---|---|---|
| `wiki-health coverage` | pages whose authored `$.type` ∈ ⋃ `coverage_rules[].class` | `pages_examined` |
| `wiki-lint` `lifecycle-drift` | pages whose `$.type` ∈ ⋃ `drift_rules[].class` | `pages_examined` (its OWN population) |
| `wiki-health ontology` / `wiki-lint` `ontology-violation` — edge rules | refs whose `ref_type` ∈ the declared edge vocabulary | `edges_examined` |
| …the SAME call's property rules | pages whose `$.type` ∈ ⋃ `ontology.properties[].class` | `property_pages_examined` |

The bare noun `pages_examined` therefore names **two different populations** across the two
CLIs. That is safe **only** because they never share an envelope, and because `wiki-lint`'s
payload is **per-check-keyed** (`lifecycle-drift.pages_examined` vs
`ontology-violation.{edges_examined, property_pages_examined}`). **Any future surface that
merges these payloads MUST re-qualify the noun.**

**The invariant is PER RULE, against that rule's OWN family denominator** — never a total:

```
∀ coverage rule r:  gaps_r     ≤ matched_r ≤ pages_examined
∀ drift    rule d:  drift_d    ≤ matched_d ≤ pages_examined            (drift's own)
∀ edge     rule e:  domain_e ≤ matched_e  AND  range_e ≤ matched_e  AND  matched_e ≤ edges_examined
∀ property rule p:  property_p ≤ matched_p ≤ property_pages_examined
```

⚠️ **`total_gaps ≤ pages_examined` is FALSE on correct data** and must never be asserted: the
schema permits two rules on one class, so **one page can gap twice**. Likewise a per-rule
*sum over kinds* is false for edges — domain and range are separate checks that can **both**
fire on the **same** ref row — hence per-rule findings are a **per-kind dict**, not one
integer.

Why per-rule `matched` **and** a denominator, when either alone looks sufficient: drift's
precondition is `$.type = class` **AND** the edge already exists, so a bare `matched: 0`
cannot tell **"no `decision` pages at all"** (today) from **"50 decisions, none carrying a
`superseded-by` edge"** (the state right after adoption). Only the denominator separates
them.

## Consequences

- **Positive.** Zero DDL, zero new fields, fully aligned with derive-don't-author. Reuses the
  proven `--as-of` `NOT EXISTS` SQL and the `wiki-graph` CLI shape. A new health rule (or a new
  layout's rules) is a drop-in YAML edit, zero Python.
- **Positive (D-036-4).** A vacuous green is now *visibly* vacuous: `total_gaps: 0` with
  `pages_examined: 0` reads as **"nothing was examined"**, which is **not** a clean bill of
  health. The layer was inert on real content, and now says so instead of congratulating
  itself.
- **Known limitation (documented).** Drift reads the *auto-derived* inverse edges, which a
  `wiki-reindex --delta` can leave transiently stale on one side of a bidirectionally-authored
  edge until the next `--full`; so `--strict` drift gating assumes a recent `--full`.
- **Cost.** One `pages` scan per rule (`O(N·rules)`; `$.type` is unindexed by design, P-5) —
  fine for the small typed vaults; revisit a single CASE/CTE pass only if a typed partition
  grows large (tripwire noted in `find_lifecycle_drift`).
- **Deferred (own tasks).** RFC-008-lite (evidence via the existing `trust_level`), RFC-009
  pattern-mining (`GROUP BY ref_type HAVING count`), RFC-011-polish (subgraph grouping in
  `wiki-query` synthesis — Track B), and body-section coverage (H2 parsing).
