# PLAN 046 — Converge construct path (`wiki-import` engine + `wiki-sync` driver)

Stub-First, Red → Green. Each **Bead** is atomic and verified by a **single test**.
Phases are ordered by dependency: **P1 → P1b → P2 → P3**. RTM IDs (R-1…R-12) are from
[docs/TASK.md](TASK.md); every RTM item maps to exactly one logic Bead.

**Branch:** `task-046-converge-construct`. **No DDL** (`user_version` 5). **No
`import anthropic`.** Concepts default ON (back-compat). `--kind article` byte-identical.

---

## Chainlink decomposition (Epic → Issue → Bead)

**Epic:** make `wiki-import` the single per-source engine (acquire+distil) and
`wiki-sync` a pure batch driver that delegates to it — retire the acquire/distil overlap.

### Issue P1 — `wiki-import` output-grammar + toggles  →  [task-046-01](tasks/task-046-01-import-grammar-toggles.md)

- **B1 [STUB CREATION]** — branch + RED tests.
  Create `tests/test_import_grammar_toggles.py` with the P1 tests (real RED tests, stronger
  than skip-stubs): `test_import_apply_pyramid_grammar` (parametrized meeting+lesson),
  `test_import_apply_pyramid_thread_mode_keeps_digest_origin`,
  `test_import_apply_article_unchanged`, `test_import_apply_diagrams_flag`,
  `test_import_apply_diagrams_default_false`, `test_import_apply_concepts_toggle`,
  `test_import_apply_article_no_concepts_no_empty_entities`.
  *Gate:* collected; the unimplemented-feature assertions FAIL (RED) before B2–B6.
- **B2 [R-2]** — add `lesson` kind + note-type.
  `_detect.py`: `KINDS` += `"lesson"`; `KIND_HARNESS["lesson"] = "summarizing-meetings"`.
  `__init__.py` kind→type map (line ~68): `"lesson": "lesson-summary"`.
  *Test:* `test_import_apply_pyramid_grammar[lesson]` (frontmatter `type: lesson-summary` + pyramid grammar).
- **B3 [R-1]** — pyramid output-grammar in `assemble_note`.
  `_authoring.py`: `assemble_note(..., grammar: str = "article")`; when
  `grammar == "pyramid"` emit `frontmatter + H1 + source/raw header + body` (the
  REASON-authored pyramid) WITHOUT the `## Полный текст (перевод)` wrapper; append the
  `## Ключевые сущности` entity footer only when concepts are on. `__init__.py` derives
  `grammar = "pyramid" if kind in {"meeting","lesson"} else "article"`.
  *Test:* `test_import_apply_pyramid_grammar[meeting]` (no "Полный текст" heading, carries the
  pyramid body + entity footer, `type: meeting-summary`).
- **B4 [R-4]** — `--diagrams` flag.
  `__init__.py` apply argparse: `--diagrams` (store_true). Surfaced in the apply
  manifest (`"diagrams": bool`) + passed to the REASON-harness selection in the recipe
  (no body mutation on the CLI side; the harness emits mermaid). 
  *Test:* `test_import_apply_diagrams_flag` (manifest carries `diagrams: true`).
- **B5 [R-5]** — `--concepts/--no-concepts` toggle.
  `__init__.py` apply: mutually-exclusive group, default `concepts=True`; gate the
  `_file_concepts(...)` call (line ~659); on `--no-concepts` skip it and add
  `"concepts": "deferred"` to the manifest.
  *Test:* `test_import_apply_concepts_toggle` (no-concepts → 0 concept pages +
  manifest `concepts: deferred`; default → concepts filed as today).
- **B6 [R-3]** — article-grammar regression guard.
  Confirm `--kind article|paper|thread` still routes `grammar="article"` →
  byte-identical `assemble_note` output.
  *Test:* `test_import_apply_article_unchanged` (structural/golden compare vs current).

### Issue P1b — `wiki-import prepare` universal acquire+normalize  →  [task-046-02](tasks/task-046-02-prepare-acquire.md)

- **B7 [STUB CREATION]** — RED tests.
  `tests/test_import_prepare_acquire.py`: stubs `test_import_prepare_office`,
  `test_import_prepare_vtt`. *Gate:* collected, SKIP.
- **B8 [R-6]** — office conversion branch.
  `_fetch.py` `dispatch_fetch` local-file tail (line ~682): local `.docx/.pptx/.xlsx`
  → invoke the matching harness skill → markdown → `FetchResult(engine="convert-office")`.
  *Test:* `test_import_prepare_office` (a `.docx` fixture → `_raw/<slug>.md`, non-empty).
- **B9 [R-7]** — vtt/srt de-timestamp branch.
  `_fetch.py`: local `.vtt/.srt` → reuse `transcript-fetcher/scripts/sources/_vtt_to_text.py`
  → `FetchResult(engine="vtt")`.
  *Test:* `test_import_prepare_vtt` (a `.vtt` fixture → de-timestamped `_raw/<slug>.md`).

### Issue P2 — `wiki-sync` delegates to `wiki-import`  →  [task-046-03](tasks/task-046-03-sync-delegation.md)

- **B10 [STUB CREATION]** — RED tests.
  `tests/test_sync_delegation.py`: stubs `test_sync_scan_delegates_to_import`,
  `test_sync_plan_no_inline_distil`. *Gate:* collected, SKIP.
- **B11 [R-8]** — scan plan emits the `wiki-import` delegation.
  `wiki_sync.py`: for `ingest`/`convert+ingest` entries add
  `entry.delegate = {tool:"wiki-import", source, folder, kind, diagrams, concepts}`
  (+ `_delegate_folder`). Knobs default `auto`/`false`/`true`; populated from `summarize`
  config in P3. **Additive** — classifier `converter`/`normalize`/`staged_target` stay as the
  detected-format hint (dropping them breaks ~24 existing assertions; wiki-import re-detects).
  *Test:* `test_sync_scan_delegates_to_import` (`delegate.tool=="wiki-import"` + kind/concepts/folder).
- **B12 [R-9]** — retire inline distil in the recipe.
  `workflows/wiki-sync.md` Step 4a/4b → ONE "distil = delegate to wiki-import" step: run
  `wiki-import` prepare→REASON→apply per `entry.delegate` (conversion is wiki-import prepare's
  job, P1b); keep 4c (`upsert`) + 4d (`record` the original source hash = D1 idempotency). No
  inline `summarizing-meetings`/`wiki-enrich`/`wiki-extract-concepts`.
  *Test:* `test_sync_plan_delegates_not_inline` (every distil entry carries a wiki-import
  `delegate`; `upsert`/`skip` carry none) + recipe review.

### Issue P3 — `.wiki/sync.yaml summarize:` config + docs  →  [task-046-04](tasks/task-046-04-config-docs.md)

- **B13 [STUB CREATION]** — RED tests.
  `tests/test_sync_config_summarize.py`: stubs `..._accept`, `..._reject_unknown_key`,
  `..._bad_profile`, `..._deepmerge`, `..._default_backcompat`. *Gate:* collected, SKIP.
- **B14 [R-10]** — schema `$defs/Summarize` + key.
  `config/sync-config.schema.yaml`: `Summarize` $def — `profile`
  (enum `[auto,meeting,lesson,article]` → wiki-import `--kind`; `auto` default), `diagrams` (bool), `extract_concepts`
  (bool), `target_subdir` (string); `summarize: {$ref}` on `SyncConfig`. STRICT.
  *Test:* `_accept` / `_reject_unknown_key` / `_bad_profile`.
- **B15 [R-11][R-12]** — loader deep-merge + flag mapping.
  `scripts/wiki_index/sync_config.py`: parse + per-folder deep-merge `summarize`
  (reuse the `resummarize` cascade); resolve effective per file; map
  `profile→--kind`, `diagrams→--diagrams`, `extract_concepts→--concepts/--no-concepts`,
  `target_subdir→--folder` suffix. Absent block ≡ detected kind + concepts ON.
  *Tests:* `_deepmerge` (folder overrides only `diagrams`, inherits `profile`),
  `_default_backcompat` (no block → current defaults).
- **B16 [DOCS]** — SKILL/workflow/ARCHITECTURE sync.
  Update `skills/wiki-import/SKILL.md` (lesson kind, pyramid grammar, `--diagrams`,
  `--concepts/--no-concepts`, office/vtt acquire), `skills/wiki-sync/SKILL.md` (delegation
  + `summarize:` block + plan field), `workflows/{wiki-import,wiki-sync}.md`. ARCHITECTURE
  §2.3.4 + the §1 Sync Dispatcher component line updated to "batch driver delegating to
  wiki-import". *Gate:* `wiki-sync --help` / docs review; no stale "inline summarise" claims.

### Issue P4 — evals (vendor-agnostic, high-graded)  →  [task-046-05](tasks/task-046-05-evals.md)

- **B17a [EVALS-AUTHOR]** — author the cases (do NOT run yet).
  `skills/wiki-import/evals/evals.json`: add cases for the new discipline — WI-16
  meeting/lesson → **pyramid** (expect: pyramid sections, no `## Полный текст` wrapper,
  `type: meeting-summary`), WI-17 `--diagrams` → **selective** mermaid (illustrative, not
  decorative), WI-18 `--no-concepts` → orchestrator still authors entities but states
  concepts are **deferred**. Update framing of any case whose note shape changed; bump
  `version` + `floor`. **Create** `skills/wiki-sync/evals/{evals.json,README.md}` (mirror
  the wiki-import harness): WS-01 classify+**delegate** (never inline-distil), WS-02 honour
  `summarize.profile`→`--kind`, WS-03 keep H-6 fence in the delegated REASON, WS-04
  new-vs-reingest (don't re-summarise an already-summarised raw), WS-05 pass `--no-concepts`
  through. All `expect_*` machine-checkable; `never_relax` on the load-bearing ones.
  *Gate:* both `evals.json` parse; case count ≥ floor; README run-recipe present.
- **B17b [EVALS-RUN, R-13]** — high-graded gate (**after P1–P3 land**).
  Run both eval sets (one fresh agent context per case, per README) against the converged
  skills; grade the transcripts against `expect_*`; **file a report** under each
  `skills/*/evals/reports/`. *Gate:* **no `never_relax` failure; grade meets/raises each
  `floor`** — high-graded, not merely above floor (R-13). A failure here re-opens P1–P3.

---

## RTM coverage

| RTM | Bead | Phase | Test |
|-----|------|-------|------|
| R-1 | B3 | P1 | `test_import_apply_pyramid_grammar[meeting]` |
| R-2 | B2 | P1 | `test_import_apply_pyramid_grammar[lesson]` |
| R-3 | B6 | P1 | `test_import_apply_article_unchanged` |
| R-4 | B4 | P1 | `test_import_apply_diagrams_flag` |
| R-5 | B5 | P1 | `test_import_apply_concepts_toggle` |
| R-6 | B8 | P1b | `test_import_prepare_office` |
| R-7 | B9 | P1b | `test_import_prepare_vtt` |
| R-8 | B11 | P2 | `test_sync_scan_delegates_to_import` |
| R-9 | B12 | P2 | `test_sync_plan_delegates_not_inline` + recipe review |
| R-10 | B14 | P3 | `test_sync_config_summarize_accept/_reject` |
| R-11 | B15 | P3 | `test_sync_config_summarize_deepmerge` |
| R-12 | B15 | P3 | `test_sync_config_summarize_default_backcompat` |
| R-13 | B17a/B17b | P4 | eval-harness report under `skills/*/evals/reports/` (high-graded) |

## Dependency order
1. **P1** (B1→B2→B3→B4→B5→B6) — the engine must speak pyramid + toggles first.
2. **P1b** (B7→B8→B9) — engine accepts office/vtt (independent of P1; can interleave).
3. **P2** (B10→B11→B12) — depends on P1 (delegation passes `--kind`/`--concepts`) + P1b
   (conversion lives in prepare).
4. **P3** (B13→B14→B15→B16) — config drives P2's delegation knobs; docs last.
5. **P4** (B17a → B17b) — **B17a** (author cases) can start early once the discipline is
   settled; **B17b** (high-graded run, R-13) is the FINAL gate — it runs only after P1–P3
   land, and a `never_relax`/below-floor failure re-opens the relevant phase.

## Global gates (every Bead)
- `pytest tests/` green (the Bead's test + no regression).
- `mypy --strict scripts/` clean.
- No `import anthropic`; no `*.sql`/`user_version` change.
- After each phase: `wiki-reindex --full` rebuild sanity + session-state update.
- **`skill-tdd-strict`** (exhaustive edge + negative cases, not just the happy stub) for the
  security-sensitive beads — **B14/B15** (`summarize:` schema + loader: H-6 256 KiB cap, alias
  refusal, `INVALID_SYNC_CONFIG` no-echo, ReDoS-safe) — and the **`never_relax`** eval cases
  (WI-16, WS-01, WS-03). Everything else follows `skill-tdd-stub-first`.
