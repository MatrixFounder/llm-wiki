# TASK 031 — Typed Knowledge Classes (extended article-type taxonomy) + config-driven layout registry

## 0. Meta
- **Task ID:** 031 · **Slug:** `task-031-typed-knowledge-classes`
- **Mode:** VDD (full pipeline). Mixed config/code/docs task (`scripts/`,
  `config/`, `templates/`, `docs/`), Stub-First, green-throughout, mypy `--strict`.
- **Source:** operator request 2026-06-13 — extend the supported "article types" with
  the best of a "CybOS 2.0" vision (typed knowledge classes: Decision, Requirement,
  Risk, Incident, Hypothesis, Fact, Event), keeping Markdown canonical (ADR-002 §D8).
  Operator clarifications: **Both** (extend `dev-project` + ship a new `cybos` layout);
  **Full set** of 7 classes; **config-driven, nothing hardcoded, per-project
  overridable**; formalize via **ROADMAP + ADR**; **phased** (classification now, the
  event-graph relations as a separate later task). Plan file:
  `~/.claude/plans/virtual-watching-hedgehog.md` (approved).
- **Status:** ✅ **COMPLETE / merge-ready** 2026-06-14 (branch `task-031-typed-knowledge-classes`,
  **uncommitted** per operator rule). All 5 VDD gates green: task/arch/plan reviews APPROVED →
  `/vdd-multi` **converged** (5 LOW: 3 fixed [alias-determinism collision guard, registry key
  type-validation, single registry build] + 2 accepted-residual [absent LAYOUTS_DIR, once-per-resolve
  glob — ARCHITECTURE Q-031-4]) → **code-review MERGE**. **1339 pytest (+5 skipped), mypy strict (75
  files)**; Karpathy byte-identity preserved; zero DDL (`user_version` 5). **Real-vault dogfood GREEN**
  (`obsidian-personal` PARA vault, 2669 md): regression reindex reproduced the live index EXACTLY
  (2485 pages, 0 skips, 2.1 s), FTS/stemming OK, 7 classes adoptable via `.wiki/layout.yaml`
  type_mapping UNION (0 skips); 2 PRE-EXISTING slug collisions surfaced (near-duplicate filenames —
  not a 031 issue). Dogfood doc-fix **DF-031-1** (`--types` is a query filter, not a standalone
  lister) folded. The spec below is the design intent (ACs as planned).
- **Precedent:** `dev-project` already tag-routes new doc types (`task`→`brief`,
  `adr`→`research`) — this is the same zero-DDL move (TASK 012 layout engine). TASK 008
  is the precedent for the **deferred Phase-2** (new `ref_type` + reindex extraction +
  schema bump) — explicitly OUT of scope here.

## 1. Verified recon facts (2026-06-13; line numbers at HEAD)

| # | Fact | Consequence |
|---|------|-------------|
| F1 | `db_type` is a hard-constrained 7-value enum, enforced **twice**: `sql/wiki-index-v2.sql:162` (CHECK) **and** `config/layout-config.schema.yaml:112` (`TypeMappingEntry.db_type` enum) | New classes must route onto an EXISTING db_type (no new enum value) to stay **zero-DDL** |
| F2 | `dev-project.yaml:43-53` tag-routes raw types → `{db_type, tag}` on the existing enum | The taxonomy extension is additive `type_mapping` entries — proven pattern |
| F3 | `normalization.py:89` `TYPE_MAPPING` is the **Karpathy default** only; layouts pass their own `type_mapping` (PW-C) | New types live in **YAML**, never in the Python constant → Karpathy byte-identity preserved |
| F4 | Built-in layouts auto-discovered via `LAYOUTS_DIR.glob('*.yaml')` (`layout_config.py:421`); aliases hardcoded at `:194` `_ALIAS = {"flat":"karpathy","per-project":"karpathy"}`; resolver at `:949` | Dropping `cybos.yaml` already makes the GRAMMAR resolvable; the registry/alias/`--layout` plumbing is the hardcoded gap |
| F5 | `wiki_init.py:50-51` hardcodes `_LAYOUT_CHOICES` (the `--layout choices=`) + `_KARPATHY_LAYOUTS`; used at `:173` (agent-template select) + `:299` (two-tier scaffold dirs) | **Three** sources of truth (F4 `_ALIAS` + these two) → collapse to ONE config-driven registry (R-031-3) |
| F6 | `TypeMappingEntry` / `PathEntry` / `RefRule` are STRICT (`additionalProperties:false`); `LayoutConfig` is too | Adding new `type_mapping` entries is fine; adding new **top-level** layout fields (`aliases`, `init_scaffold`) REQUIRES an additive schema change first |
| F7 | Per-vault override merge (`layout_config.py:425-445`; schema `:18-24`): `type_mapping` **deep-MERGES (UNION)**, `ignore` UNIONs, `paths`/`ref_extraction` **REPLACE** | "Change requirements per project" = `<vault>/.wiki/layout.yaml` type_mapping UNION — already supported, document it |
| F8 | Next free ids: **TASK 031**, **ADR-003**, **ROADMAP R-13**, **Q-031-N**; `user_version` = 5 | Naming locked |
| F9 | Open `R-X1-CFG-COST` (SEV-3): layout-config resolve has no cache / per-file regex recompile | R-031-3 registry helpers MUST cache (parse built-ins once) — do not worsen it |
| F10 | `wiki-search --where` builds a **scalar** predicate `json_extract($.field) = value` (`sqlite_repository.py:547-562`); the routed `type_mapping` tag is appended to the **`tags:` list** (`normalization.py:204`). `--where tag=decision` / `--where tags=decision` therefore **cannot match** a list element (the `json_each` membership form at `:1292` is NOT wired into `--where`). `wiki-search` DOES have `--types <db_type>` (filters `pages.type`) and `tags` is an FTS column | Per-class CLI filtering in Phase 1 = `--types <db_type>` (bucket) + FTS on the tag word; rigorous proof = DB-level `pages.type` + tag-in-`tags`. A list-membership `--where` is a candidate follow-on (R-031-residual, §6) |

## 2. Requirements Traceability Matrix (RTM)

| Req | Description | Acceptance | Verify |
|-----|-------------|------------|--------|
| **R-031-1** | Extend the type taxonomy with 7 typed knowledge classes (decision, requirement, risk, incident, hypothesis, fact, event), tag-routed onto existing db_types. Added to **dev-project** (`type_mapping` only) **and** the new **cybos** layout. | Each of the 7 raw types resolves to the mapped `(db_type, tag)` in both layouts; reindex of a note of each type produces the right `pages.type` + tag with **no `UnmappedTypeError`**. Zero DDL (`user_version` 5). | AC-1.* |
| **R-031-2** | New built-in `cybos` layout — an "operational memory" event-graph vault: `paths[]` for `decisions/ requirements/ risks/ incidents/ hypotheses/ facts/ events/ tasks/ adr/ plans/`, `type_mapping`, `ref_extraction`, `frontmatter_synthesis`, optional `auto_indexes` ledger, inline usage-example comments. | `cybos.yaml` schema-validates against `#/$defs/LayoutConfig`, loads via `resolve_layout_config`, and indexes a fixture vault correctly. | AC-2.* |
| **R-031-3** | **De-hardcode the layout registry** — collapse `_LAYOUT_CHOICES`, `_KARPATHY_LAYOUTS` (`wiki_init.py:50-51`) and `_ALIAS` (`layout_config.py:194`) into ONE YAML-derived, cached registry. Add optional `aliases`/`init_scaffold` schema fields; karpathy.yaml declares them. **The registry reads the RAW built-in YAML mapping (a dedicated light read of the 3 top-level keys), NOT the frozen `LayoutConfig` dataclass** (`_build` does not carry arbitrary keys onto it). **Ship-separable: R-031-3 has no dependency on R-031-1/2 and can land first as a clean low-risk bead.** | A new built-in `*.yaml` becomes a valid `--layout` value with **zero Python edits**; `flat`/`per-project` still resolve to karpathy; two-tier scaffold + agent-template selection still correct. | AC-3.* |
| **R-031-4** | Per-type templates (`templates/page-types/{decision,requirement,risk,incident,hypothesis,fact,event}.md`) with canonical frontmatter incl. **reserved Phase-2 edge keys** (`implements`, `supersedes`, `superseded_by`, `caused_by`, `relates_to`) + example body. | Each template parses as valid frontmatter; `type:` value is in cybos `type_mapping`; a note authored from it reindexes cleanly. | AC-4.* |
| **R-031-5** | Usage/reference docs — `docs/layouts/cybos.md` (type list, per-type frontmatter contract, authoring example, **per-project override recipe**). | Doc enumerates all cybos types with the correct db_type/tag routing and a working `.wiki/layout.yaml` override example. | AC-5.* |
| **R-031-6** | Formalization — **ADR-003** (classification-vs-graph split, config-driven principle, phased hybrid, Phase-2 forward-look); **ROADMAP R-13** (event-graph typed relations, deferred); **ARCHITECTURE §3.5** + **Q-031-N**; **CLAUDE.md/README** narrative (layouts 5→6, supported types). | ADR-003 follows the ADR-002 skeleton; ROADMAP R-13 present + Phase-1 marked shipped under TASK 031; ARCHITECTURE/CLAUDE/README updated. | AC-6.* |
| **R-031-7** | Quality gates — full test suite green, mypy strict, **Karpathy byte-identity preserved**, no new deps, no `import anthropic`, live dogfood. | `pytest` + `mypy --strict scripts/` green; `tests/test_karpathy_byte_identity.py` green; dogfood `samples/cybos-demo` round-trips. | AC-7.* |

## 3. Acceptance criteria

- **AC-1.1** All 7 raw types appear in `dev-project.yaml` and `cybos.yaml` `type_mapping`, each `{db_type ∈ enum, tag}`: decision→research/decision, requirement→brief/requirement, risk→research/risk, incident→research/incident, hypothesis→research/hypothesis, fact→concept/fact, event→summary/event. *(db_type rationale: research = analysis culminating in a finding [adr precedent]; brief = concise spec statement [task/plan precedent]; concept = atomic definitional unit; **event→summary** = the closest "timestamped narrative record" bucket — all zero-DDL-valid, none forces a new enum value.)*
- **AC-1.2** `normalize_frontmatter` with the cybos/dev-project `type_mapping` returns the mapped `db_type` and appends the tag (unit test over `tests/test_config_type_mapping.py`).
- **AC-1.3** Zero DDL — `PRAGMA user_version` stays 5; no change to `sql/` nor to `config/layout-config.schema.yaml:112` db_type enum.
- **AC-2.1** `cybos.yaml` validates against `#/$defs/LayoutConfig` (strict) and `resolve_layout_config` returns a `LayoutConfig` with the 7 path globs.
- **AC-2.2** E2E: a `samples/cybos-demo` fixture with one note per type indexes via `wiki-reindex --full` with correct `pages.type` + tags and `skipped == []`.
- **AC-2.3** cybos `ref_extraction` extracts wiki-link / markdown-link / id-ref refs (mirror dev-project) — reserved edge keys are NOT extracted (Phase-2; inert markdown).
- **AC-3.1** `layout_choices()` (new, in `layout_config.py`) returns built-in `*.yaml` stems ∪ declared `aliases`, including `cybos`, `flat`, `per-project` — driven purely by YAML, **no Python list literal**. (Reads the raw YAML `layout`/`aliases`/`init_scaffold` keys, not the built `LayoutConfig`.)
- **AC-3.2** `is_two_tier_scaffold(name)` is True for `karpathy`/`flat`/`per-project` (alias-resolved, `init_scaffold: two-tier`) and False for `dev-project`/`obsidian-personal`/`cybos`.
- **AC-3.3** `wiki-init --layout cybos --scaffold-new` succeeds (registers, writes `WIKI_SCHEMA.md` + `CLAUDE.layout.md.tmpl`, NO two-tier dirs); `--layout` rejects an unknown value with the discovered-choices error.
- **AC-3.4** Registry helpers are **cached** (parse built-in YAMLs once) — no per-call re-glob/re-parse (does not worsen R-X1-CFG-COST); built-in-only (no operator-file parsing at choice-build time).
- **AC-4.1** Each `templates/page-types/*.md` carries valid frontmatter with a cybos-mapped `type:` and the reserved edge keys (commented/empty), and reindexes cleanly when copied into a vault.
- **AC-5.1** `docs/layouts/cybos.md` documents every cybos type → (db_type, tag) and a copy-pasteable `.wiki/layout.yaml` per-project override (type_mapping UNION).
- **AC-6.1** `docs/adr/ADR-003-typed-knowledge-classes.md` present (ADR-002 skeleton); `docs/ROADMAP.md` R-13 present; `docs/ARCHITECTURE.md` §3.5 + Q-031-N updated; `CLAUDE.md`/`README.md` reflect 6 layouts + the new types.
- **AC-7.1** Full `pytest` green (new + existing); `mypy --strict scripts/` clean; `tests/test_karpathy_byte_identity.py` green (Karpathy indexing + the new init-metadata keys do NOT alter discovery/pages/refs) **and** `tests/test_layout_config.py::test_karpathy_config_matches_layout_constants` green. **Ordering:** the `config/layout-config.schema.yaml` amendment (`aliases`/`init_scaffold`) MUST land **before/with** the karpathy.yaml key additions — because `LayoutConfig` is `additionalProperties:false`, an un-amended schema rejects EVERY layout at load (`_validate`, `layout_config.py:305`).
- **AC-7.2** No new runtime deps; `grep -r "import anthropic" scripts/` empty.
- **AC-7.3** Dogfood: scaffold `samples/cybos-demo`, author one note per type, `wiki-reindex --full` (`skipped`/`slug_collisions` empty); then **(a)** rigorous DB-level proof — the decision note's row has `pages.type='research'` and `'decision' ∈ tags`; **(b)** human queries — per-class retrieval is **FTS on the tag word** (`wiki-search samples/cybos-demo "decision"` → the decision note; each class's tag word returns its notes), optionally narrowed by `--types <db_type>` (a FILTER on a query — `wiki-search "RabbitMQ" --types concept` → the fact; `--types` ALONE is not a lister, DF-031-1); **and the harder `summary`-bucket overlap (arch-review 🟡-2):** with a `.wiki/layout.yaml` override adding `meeting-summary→summary`, the `event` note and a meeting-summary note both land in `pages.type=summary` yet are retrieved DISTINCTLY via FTS on their tag word (`"event"`→event note, `"standup"`→meeting note), proving the tag separates same-db_type classes. *(No `--where tag=…` — see F10; per-class precise filtering is FTS-on-tag-word in Phase 1.)*

## 4. Use cases

- **UC-31-1** Author `type: decision` (a `decisions/ADR-like.md`) in a dev-project or cybos vault → indexed as `pages.type=research` + tag `decision` (in the `tags` list); discoverable via FTS on the tag word (`wiki-search "decision"` → the decision notes), optionally narrowed by `--types research` (a query filter, not a standalone lister — DF-031-1). Precise per-class scalar filtering (`--where tag=decision`) is NOT available in Phase 1 (F10).
- **UC-31-2** `wiki-init --scaffold-new --layout cybos --vault <path>` → vault registered, `WIKI_SCHEMA.md` + agent file written, **no** `_sources/_concepts/…` dirs (init_scaffold=none).
- **UC-31-3** A maintainer drops `scripts/wiki_index/layouts/ops-journal.yaml` → `--layout ops-journal` is immediately valid with **zero Python edits** (R-031-3 payoff).
- **UC-31-4** `wiki-reindex --full` over a cybos vault holding one note per knowledge class → all route correctly; `slug_collisions`/`skipped` empty.
- **UC-31-5** A project needs a bespoke type → adds `type_mapping: {risk-register: {db_type: research, tag: risk-register}}` to `<vault>/.wiki/layout.yaml`; built-in cybos types AND the custom one both index (UNION merge).
- **UC-31-6** A Karpathy vault is reindexed → byte-identical output (golden anchor), proving the change is fully isolated to the new/extended layouts.

## 5. Constraints (binding)

- **Zero DDL** — `user_version` stays 5; no `sql/` change; no new db_type (the `config/layout-config.schema.yaml:112` enum is untouched). New types route onto existing db_types only.
- **No new deps**; **no `import anthropic`** (grep-guarded).
- **Karpathy byte-identity** — `tests/test_karpathy_byte_identity.py` green; the new `aliases`/`init_scaffold` keys on `karpathy.yaml` are **init-only metadata** and MUST NOT affect indexing (discovery/pages/refs).
- **Config-driven / no-hardcode** — the 7 classes + the layout registry live in YAML/config, never in Python literals; per-project overridable via `.wiki/layout.yaml`.
- **Do not worsen R-X1-CFG-COST** — registry helpers cached; no new `resolve_layout_config` calls on hot paths.
- **Schema additive only** — `aliases`/`init_scaffold` are OPTIONAL with safe defaults (`[]` / `none`); existing layout YAMLs without them keep working.

## 6. Out of scope (Phase 2 — documented, not built)

The **event graph**: typed page-to-page edges (`implements` / `supersedes` / `caused-by`
/ `relates-to`), `page_entity_refs.ref_type` extension, reindex frontmatter-edge
extraction, schema v5→v6. Recorded in **ADR-003** + **ROADMAP R-13**; the edge keys are
**reserved (authored-but-inert)** in the Phase-1 templates so the canonical Markdown
already carries the data when Phase 2 lights it up. TASK 008 is the implementation
precedent.

**Also deferred (R-031-residual, candidate follow-on, NOT built here):** a
**list-membership `--where` operator** (or a `--tag <value>` sugar) so a tag-routed
class is filterable by a single exact predicate (`tags` contains `decision`), using the
existing `json_each` EXISTS form (`sqlite_repository.py:1292`). Phase 1 ships the
classification + documents that precise per-class CLI filtering is `--types <db_type>` +
FTS; the membership filter is a TASK 013-surface enhancement recorded in ROADMAP, not in
scope now.
