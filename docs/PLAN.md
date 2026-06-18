# PLAN 038 — `wiki-import-article`: PARA construct path

New **Decision-17** CLI (package, mirroring the `wiki_extract_concepts` decomposition) +
skill/command/workflow triple. **Stub-first**: signatures + failing tests → green → logic.
Green throughout; `mypy --strict scripts/`; **zero-DDL** (`user_version` 7); **zero new
deps**; **no `import anthropic`**. Composition only — shells out to `html2md`/`pdf`, calls
`wiki-extract-concepts`/`wiki-index-upsert` (NF-2). Karpathy & `wiki-enrich` untouched.

## Module layout (target)

```
scripts/wiki_skills/wiki_import_article/
  __init__.py     # facade: prepare / apply / main + argparse (+ the lock surface if any)
  __main__.py     # `python -m …` entry (bin wrapper + subprocess test depend on it)
  _fetch.py       # fetch dispatch: shell out html2md|pdf, bin-resolve+fail-fast,
                  #   never-empty-_raw, propagate typed exits (FetchFailed/EmptyExtraction/arxiv_no_html)
  _context.py     # known_concepts (reuse extract-concepts) + existing_page_slugs (DB∪_concepts∪stems)
  _authoring.py   # per-mode note assembly, name sanitization, verbatim-quote guarantee, collision guard
  _errors.py      # envelopes + stable exit codes
bin/wiki-import-article            # PATH wrapper (source venv + PYTHONPATH, no cd — TASK 027 pattern)
skills/wiki-import-article/SKILL.md
commands/wiki-import-article.md
workflows/wiki-import-article.md   # single-article + batch (Workflow-tool recipe)
tests/test_import_article_*.py
```

## Atomic checklist (stub-first, Red→Green per step)

- **S0 — Scaffold + branch.** Branch `task-038-…`. Create the package with stubbed
  signatures (`raise NotImplementedError`), `__main__.py`, `bin/` wrapper, the 3 doc files
  as headers, symlinks into `.claude/`+`.agent/`. **Skill-creation gate (`[BYPASS]`,
  recorded):** `wiki-import-article` is a *product* `wiki-*` skill following the established
  repo-root hand-authored convention (same as `wiki-enrich`/`wiki-alias`/`wiki-extract-concepts`
  — none were created via `init_skill.py`); the framework's `init_skill.py` gate is for
  `.agent/skills/` *meta-skills*, so it is intentionally bypassed here, with symlinks done by
  the existing `bin/link-{skill,command,workflow}.sh`. (If a reviewer prefers the template,
  `init_skill.py skills/wiki-import-article --tier 2` can seed it instead.) Add
  `tests/test_import_article_*.py` skeleton (all `xfail`/red). `mypy --strict` passes on stubs.
  *Gate:* tests collected, red.
- **S1 — `_fetch.py` (R-1, R-3).** Tests first (mock `subprocess` for html2md/pdf):
  URL→html2md; `*.pdf`→pdf skill; html2md `arxiv_no_html`→pdf fallback; `FetchFailed`/
  `EmptyExtraction`(exit 11)→**no `_raw/` written** + typed envelope; non-empty→`_raw/<slug>.md`
  written. Bin paths configurable (`--html2md-bin`/`--pdf-extract-bin`) + fail-fast if absent.
  Then implement. *Gate:* S1 tests green.
- **S2 — `_context.py` (R-2).** Tests: `known_concepts` from the extract-concepts machinery for
  a target project; `existing_page_slugs` = `pages.slug` ∪ `_concepts/` slugs ∪ note-stems. Then
  implement (read-only DB/FS; no DDL). *Gate:* S2 tests green.
- **S3 — `prepare` facade (R-1+R-2+R-3).** Wire `_fetch`+`_context` → envelope
  `{raw_path,title,author,date,source_hash,mode,known_concepts[],existing_page_slugs[]}`.
  `source_hash = sha256(_raw bytes)` — **for wiki-import-article's own import idempotency
  (R-7) ONLY**; it is NOT threaded into `wiki-extract-concepts apply` (different byte stream
  — see S5). Tests: envelope schema + the failure pass-through. *Gate:* S3 green.
- **S4 — `_authoring.py` (R-4, R-5).** Tests per concern: per-mode body (full/summary/thread);
  name sanitization — a **normalizer** (rewrite `/`, em-dash, guillemets, `&` → safe) that
  **feeds** the existing `_validation._sanitize_name` reject-gate and **reuses its
  `_NAME_ALLOWLIST`** (no duplicate allowlist, NF-2); verbatim-quote guarantee
  (agent quote ⊂ body, else line-around-name fallback — must end verbatim); **collision guard**
  (skip slug == note's own slug; skip slug ∈ `existing_page_slugs`; skipped→reported). Then
  port/implement from the `/tmp/g01_{author,fix_quotes}.py` logic. *Gate:* S4 green.
- **S5 — `apply` facade (R-4, R-5, R-7).** Inputs: structured note + `mode` + target folder +
  **`existing_page_slugs[]`** (round-tripped from prepare via `--existing-page-slugs`, so the
  S4 collision guard fires end-to-end, not just in the unit). Flow: assemble note → write PARA
  note → `wiki-index-upsert` (layout-aware) → `wiki-extract-concepts apply --candidates-stdin
  --source-page <the note's own slug> --source-hash <FRESH sha256 of the just-written note
  body>` (NOT `prepare.source_hash` — apply re-hashes the *filed note* and rejects a mismatch as
  `SOURCE_CHANGED_DURING_EXTRACTION`; `--source-page` is required for single-page apply) →
  combined manifest. Idempotency: unchanged source (by `prepare.source_hash`) → `action:"unchanged"`.
  All writes via `validate_inside_vault` (R-26). Tests + e2e round-trip on a tmp PARA fixture vault
  (incl. an end-to-end collision-guard assertion). *Gate:* S5 + round-trip green.
- **S6 — Skill/command/workflow (R-6, R-8).** `SKILL.md` documents the prepare→reason→apply loop
  and the **hard rule: inject `prepare.known_concepts` into the orchestrator's translation/summary
  prompt** (mirror wiki-ingest SKILL.md:34) + per-mode depth. `workflows/…` = single-article steps
  **and** the batch Workflow-tool recipe (parallel translate under a schema → serialized `apply`).
  `commands/…` thin wrapper. Symlinks verified. Eval set under `skills/wiki-import-article/evals/`.
- **S7 — Real-vault e2e + gates (DoD 2-4).** Re-import ONE #01 source via `/wiki-import-article`
  on `ObsidianNotes-Test`: PARA note in the right folder, concepts reuse existing names (no new
  collision), `wiki-reindex --full` collisions==0, `wiki-lint` orphan-link delta≈0 for that note.
  `mypy --strict scripts/`; `grep -r "import anthropic" scripts/wiki_skills/wiki_import_article`
  empty; full `pytest`. *Gate:* all green; cleanup any scratch in the test vault after.
- **S8 — VDD + verificator (DoD 5).** `skill-self-improvement-verificator` on THIS plan
  (pre-dev gate — **done at design time**, this run); after S7, `/vdd-multi` (code-reviewer +
  critic-security per TASK §0/DoD 5, **+ critic-logic** as an intentional superset) →
  fix findings → re-green. Commit only on user request.

## Invariants / guards (carry through every step)
- **NF-2 (no reinvention):** never duplicate fetch/concept/index logic — shell out / call the
  existing surfaces. A test asserts `_fetch` calls the html2md/pdf bins (not an inline fetcher).
- **Decision-17:** grep-guard `import anthropic` absent; one JSON envelope + stable exit codes.
- **Collision guard is the headline fix** — the `defi`-evicts-`Defi.md` and `усреднение-стоимости`
  self-dup cases from #01 become regression tests (S4).
- **Never-empty-`_raw/`** — the SSRN/researchgate empty-file bug becomes a regression test (S1).
- **Zero-DDL / Class-B-rebuildable** — `wiki-reindex --full` after import is clean (S7).
- **Rollback** — the work is an isolated branch + a **net-new package** (no edits to existing
  modules), so revert = drop the branch/package; zero-DDL means no DB migration to unwind
  (`wiki-reindex --full` rebuilds Class B from markdown).

## Out of plan
- Editing `html2md`/`pdf`/`wiki-ingest`/`summarizing-meetings` (external/already-fixed).
- Any schema bump, new dependency, or a `--batch` CLI mode (Q-038-4: Workflow recipe instead).
