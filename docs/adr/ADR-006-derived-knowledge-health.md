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
live in `layouts/*.yaml` (cybos ships them; other layouts default to none → the checks
no-op). The *machinery* is universal; the *rules* are layout-specific. Edge vocabulary is
validated against `reindex._INVERSE_REF_TYPE` (the same allow-list `wiki-graph` traverses)
and field names against the metadata-filter allow-list, at config-load (fail-loud, exit 6).
A page is keyed by `json_extract(frontmatter_json,'$.type')` — the RAW class, NOT
`pages.type` (the db-bucket). The `EXISTS` correlation uses `page_slug = p.slug AND
page_project = p.project` (the auto-derived inverse edge — unambiguous on the page side, so
no cross-project COUNT guard is needed). Only a SCALAR text status (`json_type='text'`) is a
contradiction; NULL/list/object statuses are never drift.

## Consequences

- **Positive.** Zero DDL, zero new fields, fully aligned with derive-don't-author. Reuses the
  proven `--as-of` `NOT EXISTS` SQL and the `wiki-graph` CLI shape. A new health rule (or a new
  layout's rules) is a drop-in YAML edit, zero Python.
- **Known limitation (documented).** Drift reads the *auto-derived* inverse edges, which a
  `wiki-reindex --delta` can leave transiently stale on one side of a bidirectionally-authored
  edge until the next `--full`; so `--strict` drift gating assumes a recent `--full`.
- **Cost.** One `pages` scan per rule (`O(N·rules)`; `$.type` is unindexed by design, P-5) —
  fine for the small typed vaults; revisit a single CASE/CTE pass only if a typed partition
  grows large (tripwire noted in `find_lifecycle_drift`).
- **Deferred (own tasks).** RFC-008-lite (evidence via the existing `trust_level`), RFC-009
  pattern-mining (`GROUP BY ref_type HAVING count`), RFC-011-polish (subgraph grouping in
  `wiki-query` synthesis — Track B), and body-section coverage (H2 parsing).
