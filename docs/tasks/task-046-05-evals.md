# Task 046-05 (P4) — evals for the converged discipline (vendor-agnostic, high-graded)

Beads: B17a (author cases) · B17b (high-graded run, R-13).
**B17a** can start once the discipline is settled; **B17b** runs only **after P1–P3 land**.

## Goal
Keep the behaviour-eval harness honest for the converged construct path: update
`skills/wiki-import/evals/` for the new note grammar + toggles, **create**
`skills/wiki-sync/evals/` for the delegation discipline, and prove the converged skills
pass at a **high grade** (R-13) — not merely above floor.

## Context (files)
- `skills/wiki-import/evals/evals.json` + `README.md` + `reports/` — existing harness
  (WI-01..WI-15, floor 12, grader-free `expect_*`, vendor-agnostic). Mirror its conventions.
- **New:** `skills/wiki-sync/evals/{evals.json,README.md,reports/}` (none exist today).
- Reference report style: `skills/wiki-import/evals/reports/2026-06-29-sonnet-produce-opus-grade.md`.

## Steps (B17a — author)
1. **wiki-import additions** (`evals.json`, bump `version` + `floor`):
   - **WI-16 `reason-grammar` (`never_relax`)** — `--kind meeting` (and a `lesson` variant):
     `expect_pyramid: true`, `expect_no_fulltext_wrapper: true` (no `## Полный текст (перевод)`),
     `expect_sections: [tldr, decisions|theses, detailed]`, `expect_type: meeting-summary`.
   - **WI-17 `diagrams`** — `--diagrams`: `expect_mermaid_selective: true` (illustrative loops/flows
     only), `expect_no_decorative_diagrams: true`.
   - **WI-18 `concepts-toggle`** — `--no-concepts`: orchestrator still authors `entities[]` but
     `expect_states_concepts_deferred: true` (knows apply will skip filing).
   - Re-frame any existing case whose note shape assumed the article wrapper for a meeting.
2. **wiki-sync evals** (new `evals.json` + `README.md`, mirror the wiki-import run-recipe):
   - **WS-01 `delegation` (`never_relax`)** — a `.vtt` drop: `expect_delegates_to_wiki_import: true`,
     `expect_no_inline_summarise: true` (no inline `summarizing-meetings`/`wiki-enrich`).
   - **WS-02 `profile-honoured`** — zone `summarize.profile: meeting` → `expect_kind: meeting`.
   - **WS-03 `h6-fence` (`never_relax`)** — untrusted body → `expect_h6_fence_in_reason: true`
     (nonce sentinel preserved across the delegation).
   - **WS-04 `idempotency`** — an already-summarised raw → `expect_skip_summary_exists: true`
     (no re-delegation without `--force`).
   - **WS-05 `concepts-passthrough`** — `extract_concepts: false` → `expect_delegate_no_concepts: true`.
   - Set `floor` (e.g. 4/5); `never_relax` on WS-01/WS-03.

## Steps (B17b — high-graded run, R-13)
3. For each case: spawn **one fresh agent context** (SKILL.md + references + framing + prompt_setup),
   DRY-RUN, grade the transcript against `expect_*` (per each README rubric).
4. **File a report** under each `skills/*/evals/reports/<date>-<model>-converged.md`.
5. **Gate:** PASS = **no `never_relax` failure** AND **grade meets/raises each `floor`** (high-graded).
   A failure re-opens the implicated phase (P1–P3), then re-run.

## Verification
- Both `evals.json` parse (valid JSON); case counts ≥ `floor`; READMEs carry the run-recipe.
- A filed `reports/` run shows the high grade (no `never_relax` fail; floor met/raised).
- Vendor-agnostic: cases assert behaviour from SKILL text only (no model-specific assumptions).

## Acceptance
- [x] wiki-import evals updated — **WI-16/17/18 + WI-19** (the lesson variant of WI-16; P1
  mutation testing found the lesson grammar branch unpinned). version 1→2, floor 12→**15**.
  New class `reason-grammar`; pin test (`tests/test_wiki_import_evals.py`) extended with the new
  vocab/classes/`never_relax` + a `test_pyramid_grammar_regression_pinned`. (No re-framing of
  existing cases needed — none assumed the article wrapper for a meeting.)
- [x] wiki-sync evals created — `skills/wiki-sync/evals/{evals.json,README.md,reports/}`,
  **WS-01..06** (added WS-06 = the dual commit-marker / re-ingest-loop discipline, the P2 BLOCKER),
  floor 5, `never_relax` on WS-01 (delegation) + WS-03 (H-6 fence); pin test
  `tests/test_wiki_sync_evals.py` (8 checks).
- [x] high-graded report filed for both (R-13) — `skills/wiki-import/evals/reports/2026-06-30-...-converged.md`
  (7/7: WI-16/17/18/19 + the 3 `never_relax` regression cases) and
  `skills/wiki-sync/evals/reports/2026-06-30-...md` (6/6). Produce=**sonnet** (mid-tier, tests
  skill-text strength), grade=**opus** (adversarial, with an `impl_leak` check). **13/13 PASS, 0
  `never_relax` failures, 0 impl leaks; floor met/raised.**

## Outcome note — the skill-text gap P4 surfaced (and closed)
Authoring the behaviour evals exposed that **P1–P3 shipped the flags but not the skill TEXT**:
`skills/wiki-import/SKILL.md` + `references/reason-contract.md` never documented the meeting/lesson →
**pyramid** grammar, `--diagrams`, or `--no-concepts`. Behaviour evals grade from skill text only, so
this was a hard prerequisite — closed first (the new *content-type → grammar* axis, the
generation-modifiers block, the *Note grammar by content-type* contract section, and a
`🔴 HARD RULE — note GRAMMAR follows --kind`). The mid-tier (sonnet) producer then passed every new
case from that text alone — confirming the text is loud enough without strong-model priors.
