# TASK 038 — `wiki-import-article`: PARA construct path (the PARA analog of wiki-enrich/wiki-ingest)

## 0. Meta
- **Task ID:** 038 · **Slug:** `task-038-wiki-import-article-para-ingest`
- **Mode:** VDD (code-reviewer + critic-security + self-improvement-verificator on the
  plan). Code task (`scripts/`, `tests/`, `skills/`, `commands/`, `workflows/`, `docs/`),
  green-throughout, `mypy --strict scripts/`. **Zero DDL** (`user_version` stays **7**),
  **zero new runtime deps**, **no `import anthropic`** (Decision-17). Karpathy paths
  untouched.
- **Branch:** `task-038-wiki-import-article-para-ingest`.

## 1. Problem / motivation

The framework has a polished, packaged **construct path for Karpathy**:
`wiki-enrich` → external `wiki-ingest` → (Phase 2) `summarizing-meetings`
→ concept/entity wiring → SQLite index. The key discipline there is that
`wiki-ingest` **passes the known-concepts list to the summary generator** so the
summary's `[[wiki-links]]` reuse existing concept names and don't dangle or collide
(wiki-ingest SKILL.md:34 "always pass known-concepts").

For **PARA** vaults (the user's personal vault, `obsidian-personal` layout) there is
**no packaged equivalent**. `wiki-ingest` is Karpathy-only — it writes summaries to
`_sources/` and concept/entity pages to the **vault-root** `_concepts/_entities/`, which
is wrong for PARA (TASK 024 finding #2: PARA files a summary as a *note* in its topic
folder + sibling `_concepts/`). So every PARA article import is improvised ad-hoc.

The DAO + #01 import batches proved the cost of improvising: the ad-hoc Workflow
**skipped the known-concepts injection** and re-hit exactly the failures the Karpathy
chain prevents — ~12 orphan `[[wikilinks]]`, a self-collision (`усреднение-стоимости`),
and a generic-name collision where a new `defi` concept page **evicted the owner's
existing `Defi.md` note from the index**. Each batch also re-derived the same glue by
hand (`/tmp/g01_author.py`, `g01_fix_quotes.py`): name sanitization, verbatim-quote
guarantee, per-mode note assembly, and the empty-raw-on-FetchFailed bug.

**This task packages the PARA construct path** — the PARA analog of `wiki-enrich` — so it
is repeatable, idempotent, and **reuses the known-concepts discipline by design** instead
of re-discovering its absence each batch.

## 2. Scope

### In scope
- A new **Decision-17** CLI `wiki-import-article` (`prepare`/`apply` contract; no LLM in
  Python) that packages the deterministic plumbing the batches did by hand.
- A `skills/wiki-import-article/SKILL.md` + `commands/wiki-import-article.md` +
  `workflows/wiki-import-article.md` (+ vendor symlinks) describing the orchestrator-driven
  loop (the LLM owns translation/summary; the CLI owns fetch-dispatch + filing).
- The `workflows/` doc covers **BOTH** the single-article steps **and** the batch
  (DAO/#01) recipe — parallel translation via the Workflow tool, then serialized `apply`;
  the **CLI itself stays per-article** (no `--batch` mode — Q-038-4).
- Reuse of existing pieces — **no reinvention**: fetch via the `html2md` / `pdf` skills;
  known-concepts + concept filing via `wiki-extract-concepts` (`prepare` already emits
  `known_concepts`); note indexing via `wiki-index-upsert` / `wiki-reindex`.
- The lessons baked in as tested code: name sanitization (`_NAME_ALLOWLIST`-safe),
  verbatim-quote guarantee, self-slug + existing-note/page slug collision guard,
  per-mode note assembly (full / summary / thread), **never write an empty `_raw/`** on a
  failed/empty fetch. (The Wikipedia REST-HTML + arXiv `/html/` fetch quirks are NO LONGER
  ours — html2md now owns them; we just call html2md.)

### Out of scope (explicit non-goals)
- Changing `wiki-ingest` / `summarizing-meetings` (external skills) — not ours to edit.
- Karpathy behaviour (untouched; `wiki-enrich` stays the Karpathy path).
- The `html2md` fetch quirks — **already fixed upstream 2026-06-18** (Wikipedia REST-HTML
  rewrite, arXiv `/html/` rewrite, `EmptyExtraction` exit 11). We consume the fixed behaviour;
  we do not touch html2md.
- Schema/DDL changes (zero-DDL; rides existing `pages`/`entities`/`page_entity_refs`).
- Doing the LLM translation inside Python (forbidden by Decision-17).

## 3. Requirements (RTM)

| ID | Requirement | Verify |
|----|-------------|--------|
| **R-1** | `wiki-import-article prepare` deterministically fetches a source (URL or local raw) to `_raw/<slug>.md` inside the target PARA folder by **dispatching to the existing skills only**: HTML/URL → `html2md`; PDF → `pdf` skill. **html2md (post-2026-06-18 fix) now itself auto-rewrites Wikipedia→REST-HTML and arXiv `/abs\|/pdf`→`/html`** and emits typed `arxiv_no_html` when only a PDF exists → `prepare` then falls back to the `pdf` skill. The CLI must NOT re-encode those fetch quirks (NF-2); it dispatches on the html2md **exit code** (the authoritative html2md exit-code table is the contract), not stderr text. | unit: URL→html2md; `*.pdf`→pdf; html2md `arxiv_no_html`→pdf fallback invoked; + e2e on fixtures |
| **R-2** | `prepare` emits an envelope with `{raw_path, title, author, date, source_hash, mode, known_concepts[], existing_page_slugs[]}`. `source_hash = sha256(_raw bytes)` — **for import idempotency only** (R-7), NOT the hash fed to extract-concepts (see R-4). `known_concepts` = the target project's existing concept names (reuse `wiki-extract-concepts` machinery); `existing_page_slugs` = note+concept slugs in the project (for the collision guard). | unit: envelope schema |
| **R-3** | **Never persist an empty `_raw/`** — `prepare` propagates html2md's typed exits (`FetchFailed`, `EmptyExtraction` exit 11, `arxiv_no_html`) into its own envelope and writes **no** raw file on failure; the `needs-manual` stub is the orchestrator's call. (The empty-body case is now html2md's typed `EmptyExtraction`, not a silent exit 0 — so the guard is a clean exit-code check.) | unit: FetchFailed/EmptyExtraction → no file |
| **R-4** | `wiki-import-article apply` takes the orchestrator's structured note (`title_ru/tldr/summary_bullets/ru_body?/entities[]`) + `mode` + target folder + `existing_page_slugs[]` (round-tripped from `prepare`), and: assembles the PARA note (per-mode body), **sanitizes entity names** (rewrite `/`, em-dash, guillemets → safe — a *normalizer that FEEDS* the existing `wiki-extract-concepts` `_sanitize_name` reject-gate, reusing its `_NAME_ALLOWLIST`, NOT a re-implementation), **guarantees every `source_quote` is verbatim** in the note, writes the note, then files concept pages via `wiki-extract-concepts apply --source-page <the note's own slug> --source-hash <sha256 of the just-written note body>` (NOT `prepare.source_hash` — those are different byte streams; see Design), indexes the note, emits a combined manifest. All write paths (`_raw/`, note, concepts) route through `validate_inside_vault` (R-26) + `_is_valid_slug` + a target-symlink refusal; YAML frontmatter scalars are newline/control-stripped + quoted (H-6 frontmatter-injection guard) while the note body stays orchestrator-authored markdown (concept pages are sanitized by extract-concepts). | unit + e2e round-trip |
| **R-5** | **Collision guard**: `apply` skips any candidate whose slug == the source note's own slug (self-dup) OR collides with an `existing_page_slugs` entry (generic names like `defi` must NOT evict an owner note). Skipped candidates are reported, not silently dropped. | unit: both collision cases + S5 facade e2e |
| **R-6** | **Known-concepts discipline (the core fix)**: the SKILL/workflow MUST pass `prepare.known_concepts` into the orchestrator's reasoning prompt so proposed entity names reuse existing concept names; documented as a hard rule (mirror `wiki-ingest` SKILL.md:34). | SKILL.md review + e2e: a known concept reused, not duplicated |
| **R-7** | Idempotent + Class-B-clean: re-running `apply` on an unchanged source is a no-op/`unchanged` (keyed on `prepare.source_hash` = the `_raw` hash); a `wiki-reindex --full` after import yields **0 new slug_collisions** introduced by the import. | e2e: re-run + reindex --full collisions==0 |
| **R-8** | Skill/command/workflow triple + symlinks (`.claude/`, `.agent/`), consistent with the repo convention; `workflows/wiki-import-article.md` documents BOTH single-article and the **batch** path (parallel translation via the Workflow tool, the DAO/#01 pattern). | file existence + lint |
| **NF-1** | Decision-17: **no `import anthropic`** in the new module (grep-guarded). One JSON envelope + stable exit codes per subcommand. `mypy --strict scripts/` clean. Zero-DDL, zero new runtime deps. | grep + mypy + test |
| **NF-2** | Reuse, not reinvention: the new CLI **shells out** to `html2md`/`pdf` (configurable `--*-bin`, like `wiki-enrich --wiki-ingest-bin`) and **calls** `wiki-extract-concepts`/`wiki-index-upsert` internals — it does not duplicate fetch/concept/index logic. | code review |

## 4. Acceptance / definition of done
1. `pytest tests/` green incl. new `tests/test_import_article_*.py`; existing suite unchanged.
2. `mypy --strict scripts/` clean; `grep -r "import anthropic" scripts/wiki_skills/wiki_import_article` → empty.
3. **e2e (the proof)** on a **`samples/`-rooted PARA fixture vault** (per the CLAUDE.md
   "testing & dogfooding vaults under `samples/`" rule; scratch cleaned after): import a
   source via `/wiki-import-article` end-to-end → PARA note in the right folder + concept
   pages reusing existing concept names (no new collision), `wiki-reindex --full`
   collisions==0, `wiki-lint` orphan-link delta ≈ 0 for that note (wikilinks resolve because
   known-concepts were injected). Optional live proof: one real-source re-import on the
   working copy `ObsidianNotes-Test`.
4. Anti-regression: `wiki-enrich` (Karpathy) untouched; Karpathy byte-identity intact.
5. VDD: code-reviewer + critic-security APPROVE; `skill-self-improvement-verificator` validates the PLAN.

## 5. Risks / open questions
- **Q-038-1** New CLI vs. orchestrate-existing-CLIs-from-the-workflow-only? (Heavy vs light.)
  Lean: a thin CLI for the *plumbing* (fetch-dispatch + authoring glue + collision guard)
  so the lessons are tested code with a home; the *reasoning* stays in the SKILL/workflow.
- **Q-038-2** Where do `known_concepts` + `existing_page_slugs` come from — extend
  `wiki-extract-concepts prepare` (already emits `known_concepts`) or a dedicated scan?
- **Q-038-3** Fetch dispatch: shell out to the global `html2md`/`pdf` skills (paths vary per
  machine) — make bin paths configurable + fail-fast if absent (wiki-enrich precedent).
- **Q-038-4** Batch path: keep it as a documented Workflow recipe in the workflow doc, or
  add a `--batch` manifest mode to the CLI? (Lean: document the Workflow recipe; CLI stays per-article.)

(Design rationale resolved in `docs/architectures/open-questions.md` Q-038-*.)
