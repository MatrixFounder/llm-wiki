# TASK 046 — Converge the construct path: `wiki-import` = per-source engine, `wiki-sync` = batch driver

## Problem / Motivation

The construct tools **duplicate**. Today **two** code paths own *acquire + distil*:

- **`wiki-import`** = fetch (`prepare`: html/pdf/transcript) → REASON → `apply`
  (**article-shaped** `assemble_note` + **always** concepts).
- **`wiki-sync`** ingest = convert (docx/pptx/xlsx/pdf) + de-timestamp (vtt) →
  `summarizing-meetings` (**pyramid**) → file/index → **always** concepts.

The overlap is real and already flagged in
[functional-architecture §2.3](architectures/functional-architecture.md) ("A future
task may route `wiki-sync ingest` → `wiki-import` to retire the overlap"). Two
symptoms it causes:

1. A PARA **transcript/webinar** has no clean path to a **rich pyramid without
   concepts** — `wiki-import apply` makes an article-shaped note and force-files
   concepts. The 2026-06-30 webinar import ("Building AI-Native Startups [003]")
   had to be done **by hand**.
2. The same "raw → summary → index" logic is maintained twice, in two grammars.

## Goal

Collapse to **one per-source engine** and **one batch driver** (the convergence the
architecture already anticipated), with **zero duplication** of acquire/distil:

- **`wiki-import` = the per-source engine** (unit of work = ONE source). It absorbs:
  - **(A) universal acquire+normalize** in `prepare`: in addition to URL/PDF/video,
    handle **office (docx/pptx/xlsx)** + **`.vtt`/`.srt` de-timestamp** + local
    `.md`/`.txt` → `_raw/<slug>.md`. (Moved out of `wiki-sync`'s executor.)
  - **(B) output-grammar by `--kind`** in `apply`: `meeting`/`lesson` → **pyramid**
    (rich `summarizing-meetings` structure), `article`/`paper`/`thread` → the
    existing article wrapper, `summary` → register. Add **`lesson`** kind (→
    `generate-detailed-meeting-summary` educational overlay).
  - **(C) `--diagrams`** flag — selective-mermaid overlay on any kind.
  - **(D) `--concepts` / `--no-concepts`** flag — gate the concept-filing step
    (**default ON** — zero regression; `--no-concepts` defers to `/wiki-extract-concepts`).
- **`wiki-sync` = the batch driver** (the "what's new / re-ingest" brain). It **drops
  its own summarise/enrich/extract/convert executor** and instead: walk zone →
  classify (source / ready-note / skip) → decide new-vs-reingest (`source_state` /
  `resummarize` / `--force`) → **delegate each due SOURCE item to `wiki-import`**
  (prepare→REASON→apply) with settings resolved from `.wiki/sync.yaml`; ready notes
  → `wiki-index-upsert`; record the commit-marker on success.
- **Settings flow:** `.wiki/sync.yaml` `summarize:` (`profile`→`--kind`,
  `diagrams`→`--diagrams`, `extract_concepts`→`--concepts/--no-concepts`,
  `target_subdir`→`--folder` suffix), per-folder deep-merge (like `resummarize:`).
  A direct `/wiki-import` call takes the same flags — one knob-set, two entry points.

After this, the de-dup audit holds: acquire+normalize and distil each have **one**
owner (`wiki-import`); `wiki-sync` is a pure batch driver; `wiki-index-upsert` /
`wiki-extract-concepts` are shared leaf tools, not pipelines. `wiki-enrich` stays a
**legacy Karpathy-only** on-ramp (separate retirement — out of scope).

## Phases (stub-first within each)

- **P1 — `wiki-import` output-grammar + toggles (the engine's new shape).**
  `apply` assembles a **pyramid** for `--kind meeting|lesson` (vs the article wrapper
  for `article|paper|thread`); add `lesson` kind; add `--diagrams` and
  `--concepts/--no-concepts`. RED tests first.
- **P1b — `wiki-import prepare` universal acquire+normalize.**
  `dispatch_fetch` gains office (docx/pptx/xlsx) + `.vtt`/`.srt` de-timestamp
  branches (reuse the harness skills + transcript-fetcher `_vtt_to_text.py`) → a
  source of any supported format produces `_raw/<slug>.md`.
- **P2 — `wiki-sync` delegates to `wiki-import`.**
  Replace the inline executor (workflow Step 4) with per-item `wiki-import`
  delegation; `scan` plan emits, per due source entry, the resolved `wiki-import`
  invocation (kind/diagrams/concepts/folder). `upsert`/`skip` unchanged. Retire the
  inline summarise/enrich/extract recipe steps.
- **P3 — config + docs.**
  `.wiki/sync.yaml` `summarize:` block (schema `$defs/Summarize`, loader deep-merge),
  update `skills/{wiki-import,wiki-sync}/SKILL.md`, `workflows/*`, ARCHITECTURE
  (retire the overlap note; the converged diagram), open-questions Q-046-1.
- **P4 — evals (vendor-agnostic behaviour), high-graded.**
  Update `skills/wiki-import/evals/` for the new discipline (meeting/lesson → **pyramid**
  grammar, `--diagrams` selective-mermaid, `--no-concepts` deferral) and **create**
  `skills/wiki-sync/evals/` (it has none) for the **delegation** discipline (classify →
  new/re-ingest decision → delegate to `wiki-import`, never inline-distil; honour the
  `summarize:` profile; keep the H-6 fence in the delegated REASON). Grader-free,
  machine-checkable `expect_*` fields — same harness as the existing wiki-import evals,
  authored to the `never_relax` bar. **High-graded gate (R-13):** after P1–P3 land, run
  both eval sets against the converged skills and **file a report under `reports/`** showing
  a **high grade** (no `never_relax` failure; meet-or-raise each skill's `floor`) — the eval
  is not "done" until the implementation passes it at a high grade, not merely above floor.

## Requirements (RTM)

| ID | Requirement | Phase | Acceptance test |
|----|-------------|-------|-----------------|
| R-1 | `wiki-import apply --kind meeting` files a **pyramid** note (`type: meeting-summary`), not the article wrapper | P1 | `test_import_apply_pyramid_grammar[meeting]` |
| R-2 | `--kind lesson` → pyramid (`type: lesson-summary`; educational overlay is an orchestrator-recipe concern over the shared harness) | P1 | `test_import_apply_pyramid_grammar[lesson]` |
| R-3 | `--kind article|paper|thread` → unchanged article wrapper (byte-compat) | P1 | `test_import_apply_article_unchanged` |
| R-4 | `--diagrams` adds mermaid overlay; absent → none | P1 | `test_import_apply_diagrams_flag` |
| R-5 | `--no-concepts` skips concept filing; default (omitted) files concepts as today | P1 | `test_import_apply_concepts_toggle` |
| R-6 | `prepare` normalizes docx/pptx/xlsx → `_raw/<slug>.md` | P1b | `test_import_prepare_office` |
| R-7 | `prepare` de-timestamps `.vtt`/`.srt` → `_raw/<slug>.md` | P1b | `test_import_prepare_vtt` |
| R-8 | `wiki-sync scan` emits a per-source `wiki-import` delegation (kind/diagrams/concepts) in the plan | P2 | `test_sync_scan_delegates_to_import` |
| R-9 | `wiki-sync` no longer references inline summarise/enrich/extract for `ingest` (executor delegates) | P2 | recipe review + `test_sync_plan_no_inline_distil` |
| R-10 | `.wiki/sync.yaml` `summarize:{profile,diagrams,extract_concepts,target_subdir}` accepted; unknown key → exit 6, no echo | P3 | `test_sync_config_summarize_accept` / `_reject` |
| R-11 | `summarize:` deep-merges deepest-wins per folder; maps to `wiki-import` flags | P3 | `test_sync_config_summarize_deepmerge` |
| R-12 | Absent `summarize:` ≡ current default (kind from detect, concepts ON) | P3 | `test_sync_summarize_default_backcompat` |
| R-13 | Evals updated (`wiki-import`) + created (`wiki-sync`) for the converged discipline, **high-graded** — a filed `reports/` run passes with no `never_relax` failure + meets/raises each `floor` | P4 | eval-harness report under `skills/*/evals/reports/` |

## Invariants to preserve
- **Decision-17** — no `import anthropic`; the LLM step stays the orchestrator's
  REASON between `wiki-import prepare` and `apply`. `wiki-sync scan` stays
  deterministic plan-only.
- **Zero-DDL** — `summarize:` is file config; `user_version` stays 5.
- **No new pipeline / engine** — the convergence REMOVES a path; it adds none.
- **Back-compat** — concepts default ON; `--kind article` byte-identical; absent
  `summarize:` ≡ today's wiki-sync defaults.
- **STRICT config** (`additionalProperties:false`, no value echo), **H-6** (cap +
  alias-refusing loader), **idempotency** (commit-marker short-circuit) — unchanged.
- **`known_concepts` injection** discipline (R-6) preserved on every REASON path.

## Out of scope
- Retiring `wiki-enrich` / external `wiki-ingest` (legacy Karpathy on-ramp) — a
  separate task; it stays coexisting.
- Any DB schema change.

## Verification
- `pytest tests/` green (new + no regression); `mypy --strict scripts/` clean.
- End-to-end on a `samples/` PARA vault: drop a `.vtt` + a `.docx` in a zone with
  `.wiki/sync.yaml summarize:{profile:meeting,diagrams:true,extract_concepts:false}`
  → `wiki-sync` → two pyramid notes, no concepts, indexed; a second run is a no-op.
- Direct `/wiki-import --kind meeting --diagrams --no-concepts <URL>` → same pyramid.
- `wiki-reindex --full` still rebuilds (Class-B gate).
