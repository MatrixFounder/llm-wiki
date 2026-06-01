# Development Plan: TASK 012 — Universal config-driven layout engine + dev-vault bootstrap (R-X1 + R-X2 A-B + R-X3)

> Decomposes [TASK.md](./TASK.md) (RTM R-X1.A..layouts, R-X1.ADR/H/Q/G, R-X3.dogfood,
> R-X2.1..roadmap) into Stub-First beads.
>
> **Methodology:** **Stub-First (TDD)**, **green-throughout** (every bead boundary keeps
> `pytest` green + `mypy --strict scripts/` clean). The **load-bearing invariant** is
> byte-identity for Karpathy vaults (ADR-002 §D8): a **golden-snapshot harness (Bead 0)**
> is captured against the *current* engine and stays green through every later bead.
> Correctness-critical beads (the engine rewrite, the slug convergence, the durability
> read-side, the migration round-trip) run under **`skill-tdd-strict`** (test-first, full
> edge-case unit coverage, no DB over-mocking).
>
> **Recommended operator review checkpoint** after Bead 7 (the R-X1 byte-identity gate),
> before the KNOWN_ISSUES migration + bootstrap (operator-confirmed in the approved plan).

## 0. Architectural Foundation (Reference)

- **Two config systems (D-012-2):** existing per-vault identity/policy (`config_loader.py`
  + `config/wiki-config.schema.yaml`) is untouched; the NEW per-layout-class *grammar*
  lives in `scripts/wiki_index/layout_config.py` + `config/layout-config.schema.yaml` +
  built-in `scripts/wiki_index/layouts/{karpathy,dev-project,obsidian-personal}.yaml`. See
  ARCHITECTURE §3.5.
- **Byte-identity:** `karpathy.yaml` is a *validated projection* of `layout.py` (constants
  NOT deleted). `flat`/`per-project` alias → `karpathy.yaml`. Three slug surfaces kept
  distinct (page=`identity`, course=loose `slugify`, concept-tag=`_slugify_concept`
  untouched).
- **Walk convergence (architecture-review C1):** five physical slug/project walks;
  `check_drift` already delegates; the other three (`find_pages_missing_in_index`,
  `derive_slug`, `_derive_source_project`) converge onto `discover_pages`/`iter_pages`,
  comparing on `(slug, project)` not `f.stem`.
- **Zero DDL:** new doc types via the TYPE_MAPPING tag-route; `pages.type` CHECK untouched;
  `user_version` stays **5**.
- **Class-B "rebuildable markdown"** (ADR-002 §D8 TASK-012 amendment): `docs/issues/*.md`
  Class A; `docs/KNOWN_ISSUES.md` Class B auto-rendered. Amendment **gates PW-H**.
- **ReDoS:** stdlib `re` + load-time budget gate (versioned payload fixture, median-of-N).
  No `regex` dependency.

## 1. Task Execution Sequence

### Phase 0 — Regression anchor (before any refactor)
- **012-00** Golden byte-identity snapshot harness. **No source change.** Captures the
  current `discover_pages` + `reindex_full` row-set for `multi_vault`. Green on current
  code; the tripwire for every later bead. (`skill-tdd-strict`.)

### Phase 1 — Engine foundation (PW-A, the chokepoint everything depends on)
- **012-01** PW-A: `layout_config.py` loader + `config/layout-config.schema.yaml` +
  `layouts/karpathy.yaml` + `Layout` enum expansion + alias map + the
  `test_karpathy_config_matches_layout_constants` invariant. RED-first.

### Phase 2 — Replace hardcoded surfaces (each consumes config; parallel off 012-01)
- **012-02** PW-B + PW-J + PW-K + PW-M: `iter_pages` engine + config-driven
  `discover_pages`; ignore[]-before-paths; file_extensions; project_pattern/template +
  error policy; **SYSTEM_FILES + auto_indexes[].output implicit-ignore** (m1); stable
  POSIX-path sort; **converge `find_pages_missing_in_index`** (C1, `(slug,project)`).
  `tests/fixtures/obsidian-personal-vault/`. RED-first, `skill-tdd-strict`.
- **012-03** PW-C + PW-E: externalise `TYPE_MAPPING` + `_PATH_TYPE_FALLBACK`;
  `normalize_frontmatter` consumes config (default = karpathy built-in).
- **012-04** PW-D: `extract_refs(body, config)` + keep `extract_wiki_links` wrapper;
  **stdlib-`re` ReDoS load-gate** (versioned payload fixture, median-of-N, exit-6).
  RED-first.
- **012-05** PW-L + PW-N: `slug_strategy` (identity/preserve-unicode/transliterate/
  ascii-only) routed in `derive_slug`; **converge `_derive_source_project`** (C1);
  `default_tags`/`extra_tags` merge; APFS-case + NFC/NFD known-limitation tests (warn,
  never silent overwrite). `skill-tdd-strict` on the convergence.
- **012-06** PW-F: frontmatter synthesis (no-YAML → `{type:<path>, title:H1∥stem}`);
  karpathy `enabled:false` keeps `UnmappedTypeError`.

### Phase 3 — Ship the two non-Karpathy built-ins; R-X1 gate
- **012-07** `layouts/dev-project.yaml` + `layouts/obsidian-personal.yaml` validated +
  indexing their fixtures end-to-end. **R-X1 byte-identity gate** ⇒ operator review
  checkpoint.

### Phase 4 — KNOWN_ISSUES bundle (PW-H/Q/G) + ADR (= R-X3)
- **012-08** ADR-002 §D8 amendment landed (already drafted this Architecture phase;
  this bead is the *acceptance* that PW-H's Class-B classification + rebuildability
  invariant are pinned). **Gates 012-09.**
- **012-09** PW-H: `auto_indexes[]` render engine (pure-function body + stable total
  order with `id` tiebreaker + GENERATED-AT header + `.wiki/state.json` sha256 +
  `validate_inside_vault` on output) + render-trigger contract (tag-route `known-issue`).
  `skill-tdd-strict` on the rebuildability invariant.
- **012-10** PW-Q: `lint.py::check_auto_generated_unchanged` (re-render + sha256 compare).
- **012-11** PW-G: `scripts/migrate_known_issues_to_files.py` splitter +
  `tests/fixtures/known_issues_migration/` (built from THIS repo's real ledger format) +
  `.migration-report.md` emitter. `skill-tdd-strict` on round-trip parity.
- **012-12** R-X3 dogfood: run the splitter on this repo → `docs/issues/*.md`; re-render
  `docs/KNOWN_ISSUES.md` (Class B); operator reviews report; `wiki-search "hash drift"`
  returns one issue.

### Phase 5 — Bootstrap (R-X2 A-B) + ROADMAP
- **012-13** R-X2.1: `wiki-init --layout` → 5 values; write `layout:` to WIKI_SCHEMA.md.
- **012-14** R-X2.2 (Phase A): bootstrap this repo as dev-vault; `wiki-search "ADR-002"
  --vaults obsidian-llm-wiki`.
- **012-15** R-X2.3 (Phase B): bootstrap one peer dev-vault; `wiki-search "M-4" --vaults all`.
- **012-16** ROADMAP update: mark R-X1 + R-X2(A-B) + R-X3 done; **split R-X2 Phase C
  (archive hook) out as a deferred follow-up entry** (D-012-4). Final regression + docs.

## 2. Dependency DAG (critical-path view)

```
012-00 (golden snapshot) ── stays green through ALL beads ──┐
        │                                                    │
        ▼                                                    │
012-01 (PW-A foundation) ───────────────────────────────────┤
   ├──▶ 012-02 (PW-B/J/K/M discover_pages + C1 converge) ◀── highest risk
   ├──▶ 012-03 (PW-C/E type_mapping)
   ├──▶ 012-04 (PW-D ref + ReDoS)
   │
   ▼
012-05 (PW-L/N slug + tags + C1 converge) ◀─ needs 02,03
   ▼
012-06 (PW-F frontmatter synthesis) ◀─ needs 01,02,05
   ▼
012-07 (dev-project + obsidian-personal built-ins) ─── R-X1 GATE ⇒ operator review
   ▼
012-08 (ADR acceptance) ──▶ 012-09 (PW-H render) ──▶ 012-10 (PW-Q lint)
                                   ▼                        │
                            012-11 (PW-G splitter) ──▶ 012-12 (R-X3 dogfood)
                            (012-12 JOINS 09 + 10 + 11: render-trigger + lint-flag + split)
   ▼
012-13 (wiki-init --layout) ──▶ 012-14 (Phase A) ──▶ 012-15 (Phase B) ──▶ 012-16 (ROADMAP)
```

## 3. Stub-First Application (per `tdd-stub-first`, green-throughout)

| Bead | Code surface? | Phase-1 stub | Phase-1 test (Red→Green on stub) | Phase-2 logic |
|---|---|---|---|---|
| 012-00 | test-only | — | snapshot current rows; assert == golden | n/a (anchor) |
| 012-01 | `layout_config.py` | `load_layout_config` returns hardcoded karpathy `LayoutConfig` | invariant test vs `layout.py`; schema-reject misspelled key | real loader + alias + override merge + validate |
| 012-02 | `reindex.discover_pages`, `iter_pages` | `iter_pages` returns today's hardcoded walk | 012-00 stays green; obsidian fixture 3-project test | glob+ignore+ext+project_pattern+sort; converge `find_pages_missing_in_index` |
| 012-03 | `normalization` | `normalize_frontmatter(config=None)` = today | existing normalization tests green; dev `task`→brief+tag | consume config maps |
| 012-04 | `parsing.extract_refs` | wrapper returns `extract_wiki_links` output | karpathy refs byte-identical; ReDoS exit-6 | iterate `ref_extraction[]`; budget gate |
| 012-05 | `parsing.derive_slug` | `slug_strategy: identity` = `path.stem` | karpathy slugs unchanged; Cyrillic preserve/translit | route strategy; converge `_derive_source_project`; tags merge |
| 012-06 | `parsing.parse_frontmatter` | synthesis disabled → today | karpathy type-less still raises; obsidian synth | H1∥stem title |
| 012-07 | `layouts/*.yaml` | configs present, validate | both fixtures index correctly | full end-to-end |
| 012-08 | docs only | — | ADR amendment present + invariant defined | n/a |
| 012-09 | `rendering`, `wiki_index_render` | render stub returns header-only | delete→re-render byte-identical (modulo header) | group/sort + state.json + trigger |
| 012-10 | `lint` | `check_auto_generated_unchanged` returns [] | hand-edit flagged | re-render+sha256 compare |
| 012-11 | `migrate_known_issues_to_files.py` | emits 1 file + empty report | fixture round-trip parity | parser + report emitter |
| 012-12 | dogfood (data) | — | `wiki-search` returns one issue; re-render identical | run migration |
| 012-13 | `wiki_init` | `--layout` accepts 5 values | scaffold dev-project writes `layout:` | resolution wiring |
| 012-14 | data/bootstrap | — | `wiki-search ADR-002` hits | reindex |
| 012-15 | data/bootstrap | — | `wiki-search M-4 --vaults all` hits | peer reindex |
| 012-16 | docs only | — | ROADMAP marks done + records deferred Phase C | n/a |

## 4. Use Case Coverage

| UC | Beads |
|---|---|
| UC-29 byte-identical Karpathy re-index | 012-00, 012-01..07 (gate) |
| UC-30 obsidian-personal vault | 012-02, 012-05, 012-06, 012-07 |
| UC-31 dev-project docs search | 012-03, 012-04, 012-07, 012-14 |
| UC-32 KNOWN_ISSUES migration | 012-08..12 |
| UC-33 cross-project search | 012-15 |
| UC-34 custom config (ReDoS + schema guard) | 012-01, 012-04 |

## 5. RTM Coverage Matrix

| RTM ID | Bead(s) |
|---|---|
| R-X1.A (PW-A) | 012-01 |
| R-X1.B (PW-B/J/K/M) | 012-02 |
| R-X1.C/E (PW-C/E) | 012-03 |
| R-X1.D (PW-D + ReDoS) | 012-04 |
| R-X1.L/N (PW-L/N) | 012-05 |
| R-X1.F (PW-F) | 012-06 |
| R-X1.layouts | 012-07 |
| R-X1.ADR | 012-08 (drafted in Architecture phase) |
| R-X1.H (PW-H) | 012-09 |
| R-X1.Q (PW-Q) | 012-10 |
| R-X1.G (PW-G) | 012-11 |
| R-X3.dogfood | 012-12 |
| R-X2.1 | 012-13 |
| R-X2.2 (Phase A) | 012-14 |
| R-X2.3 (Phase B) | 012-15 |
| R-X2.roadmap | 012-16 |

## 6. Risk Register

| Risk | Sev | Mitigation | Bead |
|---|---|---|---|
| Byte-identical drift | HIGH | golden snapshot + `test_karpathy_config_matches_layout_constants`; `identity` slug; `_slugify_concept` untouched | 012-00, 012-01, 012-05 |
| PK-drift from un-converged walk (C1) | HIGH | converge `find_pages_missing_in_index`+`derive_slug`+`_derive_source_project` on `(slug,project)` | 012-02, 012-05 |
| Glob recursion/order | MED→LOW | `Path.glob` native `**`; stable POSIX-path sort; no test asserts order | 012-02 |
| obsidian-personal multi-glob re-walk (M1) | LOW | scoped claim; YAGNI single-pass; perf-floor NFR at fixture scale | 012-02 |
| ReDoS | MED | stdlib `re` + load-gate (versioned payload, median-of-N, exit-6) | 012-04 |
| preserve-unicode PK collision (NFC/NFD/APFS) | MED | `identity` for Karpathy; `transliterate` default cross-platform; collision warns | 012-05 |
| Ledger render non-determinism (M2) | MED | pure-function body; total order + `id` tiebreaker; sha256 over header-stripped body | 012-09 |
| PW-H before ADR amendment | gating | 012-08 lands ADR acceptance before 012-09 | 012-08→09 |
| Splitter silent data loss | MED | `.migration-report.md` flags low-confidence; round-trip parity fixture | 012-11 |
| Scope size | — | hard-stop review after 012-07 (R-X1 gate) | 012-07 |

## 7. Definition of Done (acceptance gate — 012-16)

- ✅ `pytest -m 'not slow'` + `pytest -m slow` fully green; `mypy --strict scripts/` clean.
- ✅ Golden snapshot (012-00) green at HEAD; Karpathy re-index byte-identical modulo `last_modified`.
- ✅ `test_karpathy_config_matches_layout_constants` + `test_discover_pages_is_path_sorted` green.
- ✅ obsidian-personal fixture: 3 same-named files → 3 projects, Cyrillic preserved, `.base`/`.obsidian` excluded, collision warns.
- ✅ dev-project: `wiki-search "ADR-002" --vaults obsidian-llm-wiki` returns hits.
- ✅ cross-project: `wiki-search "M-4" --vaults all` spans 2 vaults.
- ✅ KNOWN_ISSUES: delete + `--auto-indexes` byte-identical (modulo GENERATED-AT); `wiki-lint` flags a manual edit; `wiki-search "hash drift"` returns one issue.
- ✅ ReDoS: pathological operator pattern → config-load exit-6; built-ins pass.
- ✅ ROADMAP marks R-X1/R-X2(A-B)/R-X3 done + records deferred R-X2 Phase C.
- ✅ `user_version` still 5 (zero DDL); ADR-002 §D8 amendment present.
- ✅ Per-bead `/vdd-multi` + code-review gates clean.

## 8. Effort Summary

| | |
|---|---|
| Beads count | 17 (012-00 .. 012-16) |
| New source | ~835 LoC (proposal total minus the deferred ~60+80 archive hook) |
| New tests | ~1340 LoC (~60% of total — deliberate, not assumed) |
| Schema | **zero DDL** (`user_version` stays 5) |
| New runtime deps | **none** (stdlib `re`; reuse pyyaml/jsonschema/python-slugify) |
| New files | `layout_config.py`, `config/layout-config.schema.yaml`, `layouts/{karpathy,dev-project,obsidian-personal}.yaml`, `migrate_known_issues_to_files.py`, fixtures |

## 9. Open Issues / Planner Judgement Calls

1. **Per-bead spec files** (`docs/tasks/task-012-NN-*.md`) — **all 17 materialised up-front**
   (012-00 .. 012-16). The original plan deferred 012-03..16 to just-in-time (plan-review
   MINOR-2 accepted that); on operator request (2026-06-01) the full set was authored so the
   planning artifacts are complete (canonical `/vdd-plan`) and `/vdd-develop-all` can run
   without per-bead authoring pauses.
2. **`skill-tdd-strict` beads:** 012-00 (anchor), 012-02 (engine + C1 converge), 012-04
   (ReDoS load-gate — security surface per NFR-4; promoted per plan-review MAJOR-2),
   012-05 (slug convergence), 012-09 (rebuildability invariant), 012-11 (round-trip
   parity), 012-12 (dogfood acceptance). All others standard Stub-First.
3. **Q-012-e/f resolved** in Architecture (§11a): renderer = dependency-free Python +
   optional `string.Template` asset; override merge = REPLACE on operator key.
4. **Peer dev-vault (Q-012-g):** default `Universal-skills`; operator confirms at 012-15.
5. **012-08 ADR** was drafted during the Architecture phase (the amendment is already in
   ADR-002); this bead is its *acceptance pin* (rebuildability invariant well-defined),
   keeping the gate-before-PW-H ordering explicit (not a fresh authoring task).
6. **012-02 keeps PW-B/J/K/M consolidated** rather than split per TASK R-X1.B's SHOULD
   (plan-review MAJOR-1): the four PW codes share one `iter_pages` surface + one fixture,
   and a partial split would leave the engine half-rewritten across bead boundaries under
   the golden anchor. Atomicity-of-*verification* is preserved — task-012-02 enumerates a
   distinct RED-first test per PW code (PW-K ignore, PW-M ext, PW-J project_pattern, C1
   converge).
7. **012-09 (PW-H)** is the second-most-complex bead (`skill-tdd-strict`); its up-front
   spec is authored at the head of Phase 4 (flagged by plan-review MINOR-2), not now.
8. **Perf-floor NFR (NFR-5 / ARCHITECTURE §3.5 M1):** the obsidian-personal multi-glob
   re-walk is **YAGNI-deferred** — no perf-floor test ships in this Epic unless a large
   personal vault demonstrably slows; recorded as a Risk-Register LOW, not a DoD gate
   (reconciles plan-review MAJOR-4 with the architecture's own hedge).

## 10. Start Signal

Begin with **012-00** (golden snapshot — no source change, establishes the tripwire), then
**012-01** (PW-A foundation). Both are written up-front; the plan-review gate validates the
decomposition before development proceeds past 012-01.
