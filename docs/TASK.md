# TASK 039 — unify the construct path: content-type-dispatched REASON + layout-aware filing

## 0. Meta
- **Task ID:** 039 · **Slug:** `task-039-unified-construct-path`
- **Mode:** VDD (code-reviewer + critic-security + critic-logic + self-improvement-verificator
  on the plan). Code task (`scripts/`, `tests/`, `skills/`, `commands/`, `workflows/`, `docs/`),
  green-throughout, `mypy --strict scripts/`. **Zero DDL** (`user_version` 7), **zero new deps**,
  **no `import anthropic`** (Decision-17). Back-compat: TASK 038's surface keeps working (alias).
- **Branch:** `task-039-unified-construct-path`.

## 1. Problem / motivation

TASK 038 split the construct on-ramp along the **wrong axis — by layout**: `wiki-enrich`
(Karpathy) vs `wiki-import-article` (PARA). That contradicts the framework's own
config-driven-layout principle (a layout is a drop-in YAML; skills are layout-aware via
`resolve_layout_config`, not forked per layout — exactly how `wiki-index-upsert` (TASK 024)
and `wiki-extract-concepts` (TASK 037) already work).

The fork has a concrete hole: **a meeting transcript dropped into a PARA vault has no clean
path.** `wiki-import-article` is article-shaped (REASON harness was article-only);
`wiki-enrich`→`wiki-ingest`→`summarizing-meetings` files Karpathy layout (wrong for PARA,
TASK 024 finding #2); the user's meetings went through an ad-hoc
`/generate-detailed-meeting-summary`+`wiki-index-upsert`. Three inconsistent entry points.

**The construct pipeline has TWO orthogonal concerns, and they must be decoupled:**
- **Layout (CONFIG) → WHERE it files.** Derived from `resolve_layout_config`; one code path
  files Karpathy (`_sources/` + root `_concepts/`) OR PARA (topic-folder + sibling `_concepts/`).
- **Content-type (DETECT/flag) → the note `type:` + what the harness emphasizes.** All
  content-types run the ONE universal `summarizing-meetings` harness; finished-summary → no REASON.

This task generalizes TASK 038's `wiki-import-article` into ONE content-type-dispatched,
layout-aware **`wiki-import`** so `{meeting, article, paper, thread, summary} × {Karpathy, PARA, …}`
all flow through the same path, layout chosen by config — the universal approach.

## 2. Scope

### In scope
- **Rename / generalize** `wiki-import-article` → `wiki-import` (content-neutral): the package
  `scripts/wiki_skills/wiki_import_article/` → `wiki_import` (or keep module, add a content-neutral
  CLI name), `bin/wiki-import-article` → `bin/wiki-import`, skill/command/workflow renamed. **Keep
  a back-compat alias** `wiki-import-article` (bin + skill) → `wiki-import` (TASK 038 callers + the
  committed #01/#04 docs still work).
- **`--kind {meeting,article,paper,thread,summary,auto}`** on `prepare` + **content-type detection**
  (PRE-FLIGHT heuristics: transcript markers / speaker turns → meeting; prose/headings → article;
  arxiv/PDF dense → paper; X/thread → thread; `concepts:`+`related:` or `type: *-summary` frontmatter
  → finished-summary). `auto` is the default; explicit `--kind` overrides.
- **REASON dispatch** documented in SKILL/workflow: kind → harness — the ONE universal `summarizing-meetings` harness for all content-types
  (a separate `summarizing-articles` would be redundant), `none` for finished summaries. The CLI stays Decision-17 (the harness is the orchestrator's
  reasoning step); `prepare` only DETECTS + reports the kind + the recommended harness.
- **Layout-aware filing in `apply` for BOTH Karpathy and PARA**, one code path via
  `resolve_layout_config`: Karpathy note → `_sources/<slug>.md`, concepts → root `_concepts/`;
  PARA note → `<folder>/<slug>.md`, concepts → sibling `_concepts/`. Per-kind note `type:`
  (`meeting-summary` / `article-summary` / `summary`), not hard-coded `article-summary`.
- **Update the architecture** to ONE unified construct path (the §2.3 diagrams collapse the
  two-path split into one path with the two orthogonal axes; `wiki-enrich`/`wiki-ingest` documented
  as the legacy/external Karpathy-raw path). Manuals/quick-ref updated.
- A companion **postanovka for `summarizing-meetings`** (external, Universal-skills) — already
  written (`IMPROVEMENTS-postanovka-wiki-harness.md`): make it a drop-in note-JSON REASON harness.

### Out of scope (explicit non-goals)
- Editing the external `wiki-ingest` / `summarizing-meetings` skills (separate postanovka).
- Folding `wiki-enrich` away — it stays as the legacy Karpathy-raw path (alias/coexist; a future
  task may route `wiki-sync ingest` → `wiki-import`).
- Schema/DDL changes; new deps; LLM inside any CLI.
- RU translation of meetings (meetings stay source-language; only articles `full`-translate).

## 3. Requirements (RTM)

| ID | Requirement | Verify |
|----|-------------|--------|
| **R-1** | `wiki-import` is the content-neutral CLI (prepare/apply); `wiki-import-article` remains a working **alias** (bin + skill + command). | alias invocation works; tests |
| **R-2** | `prepare --kind {meeting,article,paper,thread,summary,auto}` + `auto` detection (PRE-FLIGHT heuristics). Envelope carries the resolved `kind` + the recommended REASON harness name. | unit: each kind detected; envelope has kind+harness |
| **R-3** | **Layout-aware filing (one code path)**: `apply` files note + concepts per `resolve_layout_config` — Karpathy (`_sources/`+root `_concepts/`) AND PARA (folder+sibling `_concepts/`). Per-kind note `type:`. | e2e: a Karpathy vault AND a PARA vault each round-trip; reindex --full collisions==0 |
| **R-4** | **REASON dispatch by content-type** is documented (SKILL/workflow): all content-types → the ONE universal `summarizing-meetings` harness, summary→register directly. The known_concepts-injection rule holds. | SKILL review; e2e meeting + article |
| **R-5** | A **meeting transcript in a PARA vault** flows end-to-end: detect meeting → summarizing-meetings REASON → PARA filing (note `type: meeting-summary` + sibling `_concepts/`) → index, with the collision guard + known_concepts discipline. (The TASK 038 hole, now closed.) | e2e (the headline proof) |
| **R-6** | Back-compat: TASK 038 behaviour (PARA article import) unchanged through the new `wiki-import` (and the alias); the committed #01/#04 notes/flows still valid. Karpathy `wiki-enrich` untouched. | existing import-article tests pass under the rename |
| **NF-1** | Decision-17 (no `import anthropic`; one JSON envelope + stable codes); `mypy --strict scripts/` clean; zero-DDL; zero new deps. | grep + mypy + tests |
| **NF-2** | Reuse, not reinvention: filing via `resolve_layout_config`/`wiki-extract-concepts`/`wiki-index-upsert`; the REASON harness is the existing universal `summarizing-meetings` (no redundant `summarizing-articles`). | code review |

## 4. Acceptance / definition of done
1. `pytest tests/` green (renamed/extended import tests + the rest); `mypy --strict scripts/` clean; no `import anthropic`.
2. **e2e on a `samples/` fixture, BOTH layouts:** (a) PARA article (TASK 038 parity), (b) **PARA meeting transcript** (the new proof), (c) Karpathy article/summary — each → correct filing, reindex --full collisions==0, lint orphan-delta≈0.
3. Back-compat: `wiki-import-article` alias works; committed #01/#04 unaffected.
4. VDD: code-reviewer + critic-security + critic-logic APPROVE; self-improvement-verificator validates the PLAN.
5. Companion `summarizing-meetings` postanovka filed (done).

## 5. Risks / open questions
- **Q-039-1** Rename strategy: physically rename the package vs keep `wiki_import_article` module + add a `wiki-import` entry + alias? (Lean: keep the module dir to minimize churn; add `wiki-import` bin/skill/command/workflow as the primary, `wiki-import-article` as alias symlinks/wrappers.)
- **Q-039-2** Content-type detection confidence — heuristics can misfire; `--kind` override + `auto` reporting its guess (operator can correct). PRE-FLIGHT surfaces low-confidence.
- **Q-039-3** Karpathy filing in `apply`: does `apply` already file correctly when `--folder=_sources` + extract-concepts (layout-aware)? Validate; generalize note `type:` + target by layout.
- **Q-039-4** `summarizing-meetings` note-JSON contract is opt-in upstream (postanovka) — until it ships, the meeting REASON harness produces the note JSON via the orchestrator following `summarizing-meetings`' procedure + the reason-contract (the harness guides; the orchestrator emits the JSON). No hard dependency on the external change.

(Design rationale → `docs/architectures/open-questions.md` Q-039-*.)
