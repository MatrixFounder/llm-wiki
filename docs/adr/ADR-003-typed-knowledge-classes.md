# ADR-003: Typed Knowledge Classes — extended article-type taxonomy + the classification-vs-graph split

- **Status**: Accepted (2026-06-13)
- **Decider**: innokentiy.georgievskiy@mdcloud.tech
- **Supersedes**: nothing (extends [ADR-002](./ADR-002-multi-vault-bottleneck-corrections.md) §D8 Class-A/B layering and the TASK 012 config-driven layout engine)
- **Empirical basis**: operator request to grow the wiki from a flat *Page* store into one carrying typed knowledge classes (a "CybOS 2.0" vision — Decision, Requirement, Risk, Incident, Hypothesis, Fact, Event), keeping Markdown canonical. The `dev-project` layout already proves the mechanism: `task`→`brief`+tag, `adr`→`research`+tag (`scripts/wiki_index/layouts/dev-project.yaml:43-53`).
- **Related**: [docs/TASK.md](../TASK.md) (TASK 031, RTM R-031-1..7), [docs/ROADMAP.md](../ROADMAP.md) R-13 (Phase-2 event graph), [docs/layouts/cybos.md](../layouts/cybos.md) (cybos reference), ADR-002 §D8 (Class A canonical / Class B rebuildable).

## Context

The wiki today resolves an "article type" through three layers:

1. **DB enum** — `pages.type` is a hard-constrained 7-value set (`summary`, `concept`, `query`, `brief`, `research`, `index`, `verification`), enforced **twice**: `sql/wiki-index-v2.sql:162` (CHECK) and `config/layout-config.schema.yaml:112` (`TypeMappingEntry.db_type` enum). A new db_type is a schema migration (`user_version` bump + `wiki-reindex --full`), per the TASK 008 precedent.
2. **Raw `type:` per layout** — the user-facing "article type", tag-routed onto the 7 db_types via each layout's `type_mapping` (karpathy 15, dev-project 10, obsidian-personal 14).
3. **Entity types** — a separate 8-value enum on `entities.type` (incl. `event`, `work`).

The operator wants an **extended list** of typed knowledge classes. Two goals are commonly conflated and must be separated:

- **Classification** — "this page *is* a Decision / Risk / Incident". A labelling concern.
- **The event graph** — "this Decision *supersedes* that one; this Incident was *caused-by* that Decision; this Task *implements* that Decision". A typed-edge concern.

These are independent in the engine. Classification is a `type_mapping` entry (zero schema change). The graph needs typed page-to-page edges (`page_entity_refs.ref_type` + reindex frontmatter extraction) — a bounded schema change, and **independent of db_type** (an edge does not require a new `pages.type`). Conflating them led to the tempting-but-wrong "promote every class to a first-class db_type", which is the worst cost/value point: maximum schema churn that *still* yields no graph.

## Decision

### D1. Classification ships as tag-route onto existing db_types — ZERO DDL

The 7 classes are added to layout `type_mapping` as raw types routed onto the existing enum + a filterable tag — **no new db_type, no schema migration** (`user_version` stays 5):

| raw `type:` | db_type | tag | rationale |
|---|---|---|---|
| decision | research | decision | analysis culminating in a choice (adr precedent) |
| requirement | brief | requirement | concise spec statement (task/plan precedent) |
| risk | research | risk | analysis of a threat |
| incident | research | incident | postmortem analysis |
| hypothesis | research | hypothesis | a proposed explanation to test |
| fact | concept | fact | atomic definitional unit |
| event | summary | event | closest "timestamped narrative record" bucket |

This matches every task shipped since TASK 007 (zero DDL) and the existing dev-project precedent. **Trade-off accepted (recorded):** precise per-class CLI filtering is *coarse* — the tag lands in the `tags:` **list**, and `wiki-search --where` is scalar-equality, so per-class filtering is via `--types <db_type>` (the bucket) + FTS on the tag word, not `--where tag=decision`. A list-membership `--where` is a candidate follow-on (ROADMAP), not built here.

### D2. Both homes — extend `dev-project` and ship a new `cybos` layout

`dev-project.yaml` gains the 7 `type_mapping` entries only (opt-in via explicit `type:` frontmatter; its `paths[]` routing is untouched). A new built-in **`cybos`** layout ("operational memory" / event-graph vault) ships with `paths[]` folders (`decisions/ requirements/ risks/ incidents/ hypotheses/ facts/ events/` + the engineering spine `tasks/ adr/ plans/`), so one vault holds the decision→task→incident chain. Per-project bespoke types use the existing `<vault>/.wiki/layout.yaml` `type_mapping` **UNION** override (no fork, no Python).

### D3. Config-driven, nothing hardcoded — collapse the layout registry to one YAML-derived source

Today three sources of truth describe layouts, two hardcoded in Python: `wiki_init._LAYOUT_CHOICES`, `wiki_init._KARPATHY_LAYOUTS`, and `layout_config._ALIAS`. TASK 031 collapses these into a **single YAML-derived, cached registry**: two *optional, additive* `LayoutConfig` schema fields — `aliases: [string]` and `init_scaffold: {two-tier, none}` (default `none`) — declared by each built-in layout (`karpathy.yaml` declares `aliases: [flat, per-project]`, `init_scaffold: two-tier`). `layout_config` exposes `layout_choices()` / `is_two_tier_scaffold()` / `resolve_alias()` reading the **raw built-in YAML** (not the frozen `LayoutConfig` dataclass), cached so as not to worsen R-X1-CFG-COST. **Result: a new layout is a pure drop-in `*.yaml` with zero Python edits.** The `aliases`/`init_scaffold` keys are init-only metadata and MUST NOT affect indexing (Karpathy golden byte-identity preserved). The schema amendment lands before/with the karpathy.yaml keys (a strict `additionalProperties:false` config rejects every layout otherwise).

### D4. Phased — classification now (Phase 1), the event graph later (Phase 2)

Phase 1 (TASK 031) ships classification + cybos + the registry + templates + docs + this ADR + ROADMAP R-13. The **event graph** (typed edges `implements`/`supersedes`/`caused-by`/`relates-to`, `ref_type` extension, reindex frontmatter-edge extraction, schema v5→v6) is **deferred** to its own task (ROADMAP R-13; TASK 008 precedent). The edge keys are **reserved (authored-but-inert)** in the Phase-1 templates so the canonical Markdown already carries the data when Phase 2 lights it up — Markdown canonical, DB rebuildable (ADR-002 §D8).

### D5. Templates + usage examples are committed config-data, not code

Per-type templates (`templates/page-types/*.md`) carry the canonical frontmatter (incl. reserved edge keys) + an example body; `docs/layouts/cybos.md` documents each type's contract, an authoring example, and the per-project override recipe. Nothing about the taxonomy lives in a Python literal.

## Consequences

### Positive
- Zero DDL, fully additive, reversible; Karpathy golden anchor untouched.
- Adding any future layout (or class) becomes a config-only change (D3) — directly serves the operator's "nothing hardcoded / change requirements per project" principle.
- The classification-vs-graph split (D4) sequences risk: the high-value, low-risk taxonomy ships immediately; the schema-touching graph is a deliberate, bounded second step.
- Markdown stays canonical: edge data is authored now, indexed later (no re-authoring when Phase 2 lands).

### Negative
- Per-class CLI filtering is coarse in Phase 1 (D1 trade-off) — mitigated by `--types`+FTS and a documented follow-on.
- The registry de-hardcode (D3) touches the strict layout schema + `wiki_init` + `layout_config`; the schema/key ordering is a sharp edge (mitigated: ordering pinned in the TASK + tests).

### Neutral
- `cybos` is opt-in (`wiki-init --layout cybos`); existing vaults are unaffected.
- `event` page-type (D1) coexists with the unrelated `entities.type='event'` and the `log_events` operational log — three distinct "event" notions, by design.

## Implementation Path

1. **Schema first** — add `aliases`/`init_scaffold` to `config/layout-config.schema.yaml` (D3).
2. **Registry** — `karpathy.yaml` metadata keys; `layout_config` helpers (cached); `wiki_init` consumes them (drop the 3 hardcoded literals).
3. **Taxonomy** — `cybos.yaml` (full) + `dev-project.yaml` `type_mapping` (D1/D2).
4. **Templates + docs** — `templates/page-types/*`, `docs/layouts/cybos.md` (D5).
5. **Formalize** — this ADR, ROADMAP R-13, ARCHITECTURE §3.5 + Q-031-N, CLAUDE.md/README.
6. **Verify** — tests (routing, registry, cybos load, e2e fixture, Karpathy anchor), `mypy --strict`, dogfood `samples/cybos-demo`.

Phase 2 (separate task, ROADMAP R-13): typed edges + `ref_type` extension + reindex extraction + schema v5→v6.

### References
- TASK 008 — the new-typed-page-class + new-ref-kind + new-event precedent (schema v4→v5).
- TASK 012 — the config-driven layout engine this extends.
- ADR-002 §D8 — Class A canonical / Class B rebuildable.
