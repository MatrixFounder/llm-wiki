# Development Plan: TASK 031 — Typed Knowledge Classes + config-driven layout registry

> **Status**: PLANNED 2026-06-13.
> **Task ID**: 031 / Slug: `task-031-typed-knowledge-classes`
> **Source spec**: [docs/TASK.md](./TASK.md) (RTM R-031-1..7; recon F1-F10; UC-31-1..6;
> ACs). task-review: NEEDS-REVISION (M-1 query defect + m-1/m-2/m-3) → all folded.
> **Architecture spec**: [docs/adr/ADR-003-typed-knowledge-classes.md](./adr/ADR-003-typed-knowledge-classes.md)
> (D1-D5) + [docs/ARCHITECTURE.md](./ARCHITECTURE.md) status block + §3.5 prose + **Q-031-1..5**.
> arch-review: APPROVED-WITH-COMMENTS (🟡-1 cache/test-isolation + 🟡-2 event/summary
> dogfood folded; see Carry-forwards).
> **Methodology**: **Stub-First / red-green, green-throughout** — each bead lands its
> tests FIRST (RED for new behaviour; GREEN pins BEFORE the refactor they protect), then
> the minimal implementation; the full suite + `mypy --strict scripts/` is green at every
> bead boundary. `tdd-strict` applies to **031-00** (touches the `wiki-init` CLI surface +
> the loader — a behaviour-preserving refactor under a golden anchor).
> **Branch**: `task-031-typed-knowledge-classes` (no auto-commit — operator's standing rule).
> **Ship-separability**: **031-00 (registry de-hardcode) ⊥ {031-01 taxonomy}** — the
> registry collapse has no dependency on the new types and can merge alone; `--layout cybos`
> simply becomes valid once both land. 031-02/03/04 are doc/test close-out.
> **Constraints (binding)**: Zero DDL (`user_version` 5; no `sql/` change; the
> `layout-config.schema.yaml:112` db_type enum untouched — route onto existing db_types
> only). No new deps; no `import anthropic`. **Karpathy byte-identity** (golden anchor +
> `test_karpathy_config_matches_layout_constants` green bead-by-bead). New `aliases`/
> `init_scaffold` are OPTIONAL additive schema keys (default `[]`/`none`), init-only — they
> MUST NOT touch discovery/pages/refs. Do not worsen R-X1-CFG-COST (registry cached).
> **Out-of-scope guards**: NO `page_entity_refs.ref_type` change, NO reindex frontmatter-edge
> extraction, NO new db_type (Phase-2 / ROADMAP R-13). `normalization.TYPE_MAPPING` (Karpathy
> Python default) untouched. The reserved edge keys in templates are INERT markdown.

---

## 0. Architectural Foundation (Reference)

| Surface | Change | Binding constraints |
|---|---|---|
| `config/layout-config.schema.yaml` | `#/$defs/LayoutConfig` += optional `aliases: {array of string, default []}` + `init_scaffold: {enum [two-tier, none], default none}`. **Lands FIRST** (strict `additionalProperties:false` rejects every layout until amended — TASK §AC-7.1). | additive/optional; no db_type enum change; meta-validates (`_get_validator` check_schema) |
| `scripts/wiki_index/layouts/karpathy.yaml` | += `aliases: [flat, per-project]` + `init_scaffold: two-tier` (init-only metadata) | golden anchor: `_build` ignores these → indexing byte-identical; `test_karpathy_config_matches_layout_constants` green |
| `scripts/wiki_index/layout_config.py` | NEW cached registry: `layout_choices()`, `is_two_tier_scaffold(name)`, `resolve_alias(name)` reading RAW built-in YAML (`layout`/`aliases`/`init_scaffold`); fold `_ALIAS` (:194) into the derived alias map; `load_layout_config:416` uses `resolve_alias`. | cache keyed on per-file `(path, st_mtime_ns)` + re-glob each call (drop-in new yaml works) + `_reset_registry_cache()` test hook (🟡-1); built-in-only (no operator file at choice time) |
| `scripts/wiki_skills/wiki_init.py` | DELETE `_LAYOUT_CHOICES`/`_KARPATHY_LAYOUTS` (:50-51); `--layout choices=` ← `layout_choices()` (:581); the two membership checks (:173 agent-template, :299 two-tier scaffold) ← `is_two_tier_scaffold(...)` | no hardcoded literal; CLI envelope/exit-codes unchanged |
| `scripts/wiki_index/layouts/cybos.yaml` | NEW full layout (paths/type_mapping/ref_extraction/frontmatter_synthesis/auto_indexes; `init_scaffold: none`) | schema-valid; 7 classes + engineering spine; built-in ref patterns → stdlib `re` (TASK 017) |
| `scripts/wiki_index/layouts/dev-project.yaml` | += 7 `type_mapping` entries (additive; `paths[]` untouched) | existing dev-project routing unchanged |
| `templates/page-types/*.md` (7 NEW) | per-type frontmatter + reserved INERT edge keys + example body | each `type:` ∈ cybos type_mapping; valid frontmatter |
| `docs/layouts/cybos.md` (NEW) | per-type contract + authoring examples + per-project `.wiki/layout.yaml` override recipe | — |
| `docs/ROADMAP.md`, `CLAUDE.md`, `README.md` | R-13 (Phase-2 event graph, deferred) + layouts 5→6 + supported-types narrative | — |
| `tests/` (+ `tests/fixtures/cybos/`) | registry tests; 7-type routing (dev-project+cybos); cybos schema-load; e2e reindex fixture; Karpathy anchor green | committed fixtures under `tests/fixtures/` (not `samples/`) |

---

## 1. Bead breakdown

| Bead | Title | Owns ACs | Dep |
|---|---|---|---|
| **031-00** | config-driven layout registry (de-hardcode) | AC-3.1/3.2/3.3/3.4, AC-7.1 (anchor) | — (ship-separable) |
| **031-01** | cybos layout + dev-project type_mapping | AC-1.1/1.2/1.3, AC-2.1/2.2/2.3 | 031-00 (schema; `--layout cybos`) |
| **031-02** | per-type templates + cybos reference doc | AC-4.1, AC-5.1 | 031-01 (type names) |
| **031-03** | formal docs — ROADMAP R-13 + CLAUDE/README | AC-6.1 | 031-01 |
| **031-04** | e2e fixture + dogfood + full-suite close | AC-7.2, AC-7.3 | all |

---

## 2. Bead detail (Stub-First)

### 031-00 — config-driven layout registry  (`tdd-strict`)
**Order:** schema → karpathy keys → registry helpers → wiki_init rewiring.
1. **Schema (first):** add `aliases`/`init_scaffold` to `#/$defs/LayoutConfig` (optional, defaults). Meta-validate.
2. **karpathy.yaml:** add `aliases: [flat, per-project]` + `init_scaffold: two-tier`.
3. **Registry (`layout_config.py`):** module `_REGISTRY_CACHE: dict[Path, tuple[int, dict]]` (key = path, val = (`st_mtime_ns`, parsed-top-keys)); `_builtin_registry()` re-globs `LAYOUTS_DIR`, parses/refreshes per stale mtime; `layout_choices()`→sorted(stems ∪ all `aliases`); `resolve_alias(name)`→builtin stem (alias→target, else name); `is_two_tier_scaffold(name)`→`resolve_alias` then `init_scaffold == 'two-tier'`; `_reset_registry_cache()` for tests. Replace `_ALIAS` usage at `load_layout_config:416` with `resolve_alias`; keep `_ALIAS` only if a derived fallback is cleaner (prefer deriving from YAML).
4. **wiki_init.py:** import the helpers; `--layout` `choices=layout_choices()`; `:173`+`:299` use `is_two_tier_scaffold(placeholders["layout"] / _layout)`.
- **Stub-First tests (RED first):** `test_layout_choices_includes_builtins_and_aliases` (cybos/flat/per-project present, no Python literal); `test_is_two_tier_scaffold` (True karpathy/flat/per-project, False dev-project/obsidian-personal/cybos); `test_resolve_alias_parity` (flat/per-project→karpathy — keep `test_alias_resolution_to_karpathy` green); `test_dropin_new_layout_appears` (write temp `LAYOUTS_DIR/zz-probe.yaml` after `_reset_registry_cache()`, assert in `layout_choices()`, then remove + reset — **proves 🟡-1 cache invalidation + isolation**); `test_wiki_init_rejects_unknown_layout` (discovered-choices error); GREEN pins: existing wiki-init scaffold/register behaviour unchanged.
- **Verify:** golden anchor + `test_karpathy_config_matches_layout_constants` green; `mypy --strict`.

### 031-01 — cybos layout + dev-project type_mapping
- **cybos.yaml:** `layout: cybos`, `slug_strategy: transliterate`, `init_scaffold: none`, `file_extensions: ['.md']`, `ignore` (`.git/**`, `.obsidian/**`, `**/.DS_Store`, `_raw/**`, `.staging/**`); `paths[]` first-match for `decisions/ requirements/ risks/ incidents/ hypotheses/ facts/ events/ tasks/ adr/ plans/ *.md` (project `_vault_`) + bare `TASK.md`/etc. if useful; `type_mapping` = the 7 classes (table) + task/plan/adr (spine); `path_type_fallback: {}`; `ref_extraction` = dev-project's 3 rules (wiki-link/markdown-link/id-ref); `frontmatter_synthesis: {enabled: true, first_h1, filename_stem}`; optional `auto_indexes` (decisions→DECISIONS.md group_by status). Inline per-type comment block.
- **dev-project.yaml:** append the 7 `type_mapping` entries.
- **Stub-First tests (RED):** extend `tests/test_config_type_mapping.py` with a `_CYBOS_TM`/`_DEV_TM`-extended map asserting all 7 routes (db_type+tag) — also assert in BOTH layouts loaded via `load_layout_config`; `test_cybos_config_loads_and_validates` (schema-valid, 7 path globs, init_scaffold none); E2E reindex over `tests/fixtures/cybos/` (one note per type) → correct `pages.type`+tags, `skipped`/`slug_collisions` empty (AC-2.2); AC-2.3 reserved edge keys NOT extracted as refs.
- **Verify:** Karpathy anchor green (cybos/dev-project changes isolated); `mypy --strict`.

### 031-02 — per-type templates + cybos reference doc
- 7 `templates/page-types/*.md` (canonical frontmatter: `type`, `title`, `tags`, `created`/`date`, reserved INERT `implements`/`supersedes`/`superseded_by`/`caused_by`/`relates_to` commented; example body).
- `docs/layouts/cybos.md`: type→(db_type,tag) table; per-type authoring example; the F10 filtering note (`--types`+FTS, no `--where tag=`); per-project `.wiki/layout.yaml` UNION override recipe; reserved-edge-keys/Phase-2 note.
- **Tests:** `test_page_type_templates_valid` (each parses; `type` ∈ cybos type_mapping; reserved keys present-but-inert).

### 031-03 — formal docs
- `docs/ROADMAP.md`: **R-13** (event-graph typed relations — Phase 2; P2; deferred; TASK 008 precedent; cites ADR-003). Mark Phase-1 taxonomy shipped under TASK 031.
- `CLAUDE.md`: layouts 5→6, the new types, TASK 031 ship-log entry (after TASK 030).
- `README.md`: supported-layouts/types line (6 layouts).
- (ADR-003 + ARCHITECTURE done in Architecture phase.)

### 031-04 — e2e fixture + dogfood + close
- Commit `tests/fixtures/cybos/` (one minimal note per type, from the templates).
- Dogfood (gitignored scratch): `wiki-init --scaffold-new --layout cybos --vault samples/cybos-demo` (AC-3.3: registers, no two-tier dirs, CLAUDE.layout template); author one note/type; `wiki-reindex --full`; assert DB-level `pages.type`+tag; `wiki-search --types research` (bucket) + FTS `"incident"`; **🟡-2: event/summary distinct retrieval** (FTS on the event note's term — same db_type `summary` as meeting/lesson summaries, separated by tag word).
- Full `pytest` + `mypy --strict scripts/`; `grep -r "import anthropic" scripts/` empty (AC-7.2).

---

## 3. Carry-forwards (arch-review APPROVED-WITH-COMMENTS)

- **🟡-1 (031-00) — registry cache mechanism + test isolation.** Cache keyed on per-file
  `(path, st_mtime_ns)` with a re-glob each call (so UC-31-3 drop-in is seen) **and** a
  `_reset_registry_cache()` hook; `test_dropin_new_layout_appears` exercises both. Reuse the
  `_VALIDATOR` module-singleton precedent (`layout_config.py:284-299`). Does not add a
  `resolve_layout_config` call to any hot path (R-X1-CFG-COST non-worsening).
- **🟡-2 (031-04) — event/summary overlap dogfood.** AC-7.3(b) explicitly demonstrates the
  `event` note (db_type `summary`) is retrievable DISTINCTLY from generic summaries via FTS
  on its `event` tag word, proving the tag separates same-db_type classes (the harder case
  than the research/incident demo).
- **🟢-2 (done)** ADR-003/Q-031-4 line-number drift corrected to `:50-51`.
- **🟢-1 (sequencing)** ADR-003 §Related links `ROADMAP.md` R-13 (031-03) + `docs/layouts/cybos.md`
  (031-02) — both authored in Dev; confirm links resolve at close.

## 4. Out of scope (Phase 2 — ROADMAP R-13)

Typed page-to-page edges (`implements`/`supersedes`/`caused-by`/`relates-to`),
`page_entity_refs.ref_type` extension, reindex frontmatter-edge extraction, schema v5→v6,
and the candidate list-membership `--where` filter (TASK 013 surface) — documented, NOT built.
