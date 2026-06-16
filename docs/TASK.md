# TASK 036 — Derived knowledge health: lifecycle-drift + coverage (R-15, Track A)

## 0. Meta
- **Task ID:** 036 · **Slug:** `task-036-derived-knowledge-health`
- **Mode:** VDD (full pipeline). Code task (`scripts/`, `tests/`, `config/`, `docs/`),
  green-throughout, mypy `--strict`. **Zero DDL** (`user_version` stays **7**); **zero new
  deps**; **no `import anthropic`**; Karpathy byte-identity preserved (the new layout-grammar
  keys default to `[]`, so non-cybos layouts are unaffected). Read-side only — no Class-A
  writes, no schema migration.
- **Source:** ROADMAP **R-15** (the third RFC batch, RFC-007..011, audited like R-14). The
  high-value, not-yet-built, in-architecture slice is a Class-B **derivation/analysis layer**
  over the existing markdown + event graph. Track A = the two halves that are the SAME
  machinery (LEFT-JOIN the edge graph against page `status`/`type`): **A1 lifecycle-drift**
  (the derivable half of RFC-007) + **A2 coverage gaps** (RFC-010). (Track B RFC-011-polish
  and the deferred RFC-008-lite/RFC-009 are NOT in this task.)
- **ADR:** **ADR-006** (`docs/adr/ADR-006-derived-knowledge-health.md`) — the D-036 decision
  (drift rides `wiki-lint`/`--strict` because it is a CONTRADICTION; coverage is a separate
  always-exit-0 `wiki-health` report because a gap is expected data), and the rejection of
  authored lifecycle state (`type: transition`, `confidence`).
- **Status:** ✅ **COMPLETE / merge-ready** 2026-06-16 (uncommitted per operator rule). Full
  VDD: **`/vdd-multi` converged** — Security ✓ **bikeshedding-only** (every rule value is a
  bound param; the sole string-built fragment is a `?`-placeholder count; `requires_field`
  double-gated by the `[a-z][a-z0-9_]*` `fullmatch` allow-list at load + in the DAL; INVALID_CLASS
  never echoes the offending value), Logic ✓ — **3 findings fixed + re-verified** (list-valued
  `status` phantom-drift → `json_type='text'` guard; empty-container `source: []` → treated as a
  gap; empty/whitespace status values → rejected at config-load; + the `--delta` inverse-edge
  staleness caveat documented), Performance ✓ — **2 fixed** (the per-vault double
  `resolve_layout_config` collapsed to one shared resolve; an `EXPLAIN QUERY PLAN` index-seek
  guard test added) **+ the O(N·rules) cost-shape + tripwire documented** (YAGNI: small typed
  vaults, `$.type` unindexed by P-5). **Live dogfood GREEN** (a real cybos vault: `wiki-lint`
  surfaced 2 drift contradictions — advisory exit 0, `--strict` exit 1; `wiki-health coverage`
  reported 2 gaps exit 0; `--class` filter correct). **1524 pytest (+20 over the 1504 baseline:
  the 20-test health trio), mypy strict (77 files).**

## 1. Problem

The system stores typed knowledge classes + a typed event graph, but knowledge state is
**authored, never derived**: a `status:` is updated by hand, and nothing reports missing
relations. Two derivable signals are unbuilt:

1. **Lifecycle-drift** — a page whose AUTHORED `status` contradicts its graph state (a
   `decision` carrying a `superseded-by` edge but still `status: accepted`; a decision an
   incident `invalidates` but still `accepted`). This is a genuine *contradiction*.
2. **Coverage gaps** — a page MISSING an expected relation (a `requirement` nothing
   `implements`; a `fact` with no `source:`). This is an *absence* — expected, not a failure.

Both are computable today (zero new fields, zero DDL) from `pages.frontmatter_json` + the
`page_entity_refs` graph — the same `EXISTS`/`NOT EXISTS` machinery the TASK-034 `--as-of`
walk already uses. The RFC's proposed authored state (`type: transition`, `confidence`,
`type: evidence` + `strength`) is rejected (violates Class-A/B layering + "derive, don't
author" — the TASK-034 `valid_to` precedent).

## 2. Scope — two read-side slices, one machinery

- **A1 — lifecycle-drift as `wiki-lint` rules.** A new `lifecycle-drift` `LintIssue` category.
  Rules are **layout-config-driven** (`drift_rules` in `layouts/*.yaml`; cybos ships 3
  high-confidence contradiction rules: decision `superseded-by`→expect `superseded`; decision
  `invalidated-by`→forbid {proposed,accepted}; workflow `superseded-by`→expect `superseded`).
  A page is matched by `json_extract(frontmatter_json,'$.type')` (the RAW class, **not**
  `pages.type`) + an `EXISTS` over `page_entity_refs` where `page_slug` IS the page (the
  auto-derived inverse edge — unambiguous on the page side, no COUNT guard needed). A NULL/
  non-scalar status is NEVER drift. **D-036: drift rides `wiki-lint`** — advisory by default,
  non-zero only under `--strict` (it is a contradiction, the one SEMANTIC check that belongs
  on lint's gate).
- **A2 — coverage gaps as a new read-only `wiki-health` CLI** (17th `wiki-*`). `wiki-health
  coverage --vault <vid> [--class C]`: `requires_edge` (NOT EXISTS that ref_type on the page)
  or `requires_field` (frontmatter scalar `$.<field>` absent/empty/empty-container). cybos
  ships 3 rules (requirement/capability `implemented-by`; fact `source`). **Always exit 0** —
  a gap is data, not a failure (contrast drift). Clone of `wiki-graph` (single envelope,
  allow-listed `--class`, exit `0/2/6`).

Both rule sets are validated at config-load (`_validate_health_rules`): edge vocabulary
against `reindex._INVERSE_REF_TYPE`, field names via `validate_filter_field`, exactly-one-of
via the schema `oneOf` + a defensive re-check. The DAL methods (`find_lifecycle_drift` /
`find_coverage_gaps`) take the rules and bind every value.

### Out of scope (recorded in ADR-006 / ROADMAP R-15)
- Authored lifecycle state: `type: transition`, `confidence`, auto-status-rewrite (007 full).
- `type: evidence` + `strength` schema v8 (008 full); RFC-008-lite (`trust_level`) is deferred.
- RFC-009 pattern-mining (`GROUP BY ref_type HAVING count`) — deferred to vault density.
- RFC-011-polish (Track B — subgraph grouping in `wiki-query` synthesis) — separate track.
- Body-section coverage (decision `## Rationale`, incident `## Root cause`) — needs H2 parsing.
- Any auto-fix (mutating a Class-A `status`) — would need a `prepare`/`apply` write contract.

## 3. Requirements Traceability Matrix

| # | Requirement | Acceptance | Verify |
|---|---|---|---|
| R-1 | Lifecycle-drift flags authored-status-vs-graph contradictions per layout rules | the 3 cybos rules catch forward- AND inverse-authored `superseded-by`, and `invalidated-by` + live status; nothing else | `test_lifecycle_drift::test_find_lifecycle_drift_dal` |
| R-2 | NULL / non-scalar status is never drift | absent status + `status: [superseded]` (list) not flagged (`json_type='text'` guard) | `test_drift_controls_not_flagged`, `test_list_valued_status_not_drift` |
| R-3 | Drift rides `wiki-lint`: advisory default, gates `--strict` | exit 0 default (issues reported); exit 1 under `--strict` | `test_lint_reports_lifecycle_drift`, `test_lint_cli_strict_gates_on_drift` |
| R-4 | Coverage reports edge-absence + field-emptiness gaps; always exit 0 | requirement/capability no `implemented-by`; fact empty/absent/empty-container `source` | `test_wiki_health::test_coverage_all`, `test_empty_container_source_is_gap` |
| R-5 | `wiki-health` controls + `--class` filter + envelope hygiene | covered pages absent; `--class` scopes; INVALID_CLASS (2, no echo); VAULT_NOT_FOUND (6); no-rules note | `test_coverage_controls_not_gaps`/`_class_filter`/`_invalid_class_no_echo`/`_vault_not_found`/`_no_rules_note` |
| R-6 | Layout-config-driven, validated at load; zero DDL | cybos ships 3+3 rules; unknown edge / bad field / both-branches / empty status → LayoutConfigError | `test_health_rules_config::*` |
| R-7 | Injection-safe; index-backed | all rule values bound; `$.field` allow-listed; EXISTS rides an index seek not a full scan | critic-security clean + `test_drift_exists_uses_refs_index` |
| R-8 | Docs current | ADR-006; ROADMAP R-15 SHIPPED; CLAUDE.md (17 CLIs); ARCHITECTURE; README; SKILL/command | review |

## 4. Non-goals / invariants
- `mypy --strict scripts/` clean; full `pytest tests/` green; no new dep; no `import anthropic`.
- Decision-17: deterministic SQL + config; one JSON envelope + stable exit code (NOT
  prepare/apply — that contract is for Class-A writers; these are read-only analytics).
- Class A/B/C: output is a derived view, never persisted as knowledge; `user_version` stays 7.
- Layout-grammar change (new `layout-config.schema.yaml` keys) is NOT a DB-schema change.
