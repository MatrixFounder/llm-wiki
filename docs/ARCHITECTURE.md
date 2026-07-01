# ARCHITECTURE: LLM Wiki MVP

> This is a living INDEX. Section bodies live in
> [docs/architectures/](./architectures/). Edit the relevant chunk and
> keep the one-line summary on this page in sync.

> **Status**: Phase 3b — incremental feature/hardening tasks (one per `docs/tasks/*`).
> The **current** task is in [docs/TASK.md](./TASK.md); the shipped-task log lives in
> [docs/tasks/](./tasks/) + [docs/plans/](./plans/) + git — intentionally not repeated
> here, nor in `CLAUDE.md`. The per-task **design rationale** (Q-0XX) is §11, chunked to
> [architectures/open-questions.md](./architectures/open-questions.md). **Schema
> `user_version 7`** ([sql/wiki-index-v2.sql](../sql/wiki-index-v2.sql)); the DB is a
> Class-B rebuildable cache (ADR-002 §D8 — a schema bump is a `wiki-reindex --full`
> rebuild, never an in-place ALTER). ADRs: [001](./adr/ADR-001-wiki-ingest-integration.md)
> wrap+index · [002](./adr/ADR-002-multi-vault-bottleneck-corrections.md) multi-vault +
> Class A/B/C · [003](./adr/ADR-003-typed-knowledge-classes.md) typed knowledge classes ·
> [004](./adr/ADR-004-event-graph-typed-edges.md) event graph ·
> [005](./adr/ADR-005-fts-narrowed-membership-filter.md) FTS-narrowed membership ·
> [006](./adr/ADR-006-derived-knowledge-health.md) derived knowledge health ·
> [007](./adr/ADR-007-config-driven-write-grammar.md) config-driven write-grammar (Karpathy = a layout YAML).
>
> **Source spec**: [docs/TASK-ref-v2.md](./TASK-ref-v2.md) — full v2 reference specification.
> **Schema**: [docs/SCHEMA-v2.sql](./SCHEMA-v2.sql) — SQLite DDL (multi-vault, partitioned by `vault_id`).
> **Backend choice**: [docs/SQLITE-VS-POSTGRES.md](./SQLITE-VS-POSTGRES.md) — SQLite default, Postgres opt-in via DAL.
> **Layout constants** consolidated in [scripts/wiki_index/layout.py](../scripts/wiki_index/layout.py) — single source of truth for `PAGE_SUBDIRS`, `COURSE_TIER_DIR`, `VAULT_INDEX_DIR`, `LOG_SUBDIR`, `SCAFFOLD_DIRS`, `SYSTEM_FILES`, `GLOBAL_VAULT_SENTINEL`.

---

## Table of Contents

- [1. Task Description](#1-task-description) (inline)
- [1.5. Project Anatomy](#15-project-anatomy) → [architectures/project-anatomy.md](./architectures/project-anatomy.md)
- [1.6. Skill / Command / Workflow Execution Model](#16-skill--command--workflow-execution-model) → [architectures/skill-command-workflow-model.md](./architectures/skill-command-workflow-model.md) (RU · [EN](./architectures/skill-command-workflow-model.en.md))
- [2. Functional Architecture](#2-functional-architecture) → [architectures/functional-architecture.md](./architectures/functional-architecture.md)
- [3. System Architecture](#3-system-architecture) → [architectures/system-architecture.md](./architectures/system-architecture.md)
- [4. Data Model (Conceptual)](#4-data-model-conceptual) → [architectures/data-model.md](./architectures/data-model.md)
- [5. Interfaces](#5-interfaces) → [architectures/interfaces.md](./architectures/interfaces.md)
- [6. Technology Stack](#6-technology-stack) → [architectures/technology-stack.md](./architectures/technology-stack.md)
- [7. Security](#7-security) → [architectures/security.md](./architectures/security.md)
- [8. Scalability and Performance](#8-scalability-and-performance) → [architectures/scalability-and-performance.md](./architectures/scalability-and-performance.md)
- [9. Reliability and Fault Tolerance](#9-reliability-and-fault-tolerance) → [architectures/reliability-and-fault-tolerance.md](./architectures/reliability-and-fault-tolerance.md)
- [10. Deployment](#10-deployment) → [architectures/deployment.md](./architectures/deployment.md)
- [11. Open Questions](#11-open-questions) → [architectures/open-questions.md](./architectures/open-questions.md)
- [Verification Map](#verification-map) → [architectures/verification-map.md](./architectures/verification-map.md)
- [Quality Checklist (VDD)](#quality-checklist-vdd) (inline)

---

## 1. Task Description

Реализация MVP персональной LLM Wiki поверх Obsidian-vault'а пользователя:
- **Markdown — source of truth** (Karpathy canon).
- **SQLite — derivative cache** (FTS5 + WAL для < 50ms search; rebuildable).
- **Pluggable source adapters** (manual + transcript + light для MVP).
- **Идемпотентные операции**: re-ingest того же source = no-op.
- **iCloud-aware**: SQLite вне vault'а, markdown в iCloud.

Полное описание целей: archived MVP TASK at [tasks/task-002-wiki-mvp.md](./tasks/task-002-wiki-mvp.md).

---

## 1.5. Project Anatomy

Where things live in the repo: anatomy of one in-repo skill (template + symlink graph) and how the CLIs, DAL, and layout engine compose.

> **Superseded (TASK 047):** the `wiki-enrich` ↔ vendored `wiki-ingest` integration flow (the
> primary in-process path + subprocess fallback + the vendored-snapshot layout / sync policy)
> described in the linked body was **retired** — `wiki-import` is the in-repo construct engine and
> concept-page compounding is a derived Class-B render (`wiki-index-render --concept-mentions`).
> Those §1.5.2/§1.5.3/§1.5.7 subsections are kept as accepted-then-superseded history.

→ [details](./architectures/project-anatomy.md)

---

## 1.6. Skill / Command / Workflow Execution Model

Как **один `/wiki-*` вызов реально исполняется** — how-to для человека (с presentation-ready
mermaid-схемами). Объясняет: почему одно имя (`wiki-sync`) встречается как **command +
SKILL + workflow (+ `bin/` + `scripts/`)** и почему это намеренный многоключевой биндинг,
а не дубликат; **симлинк-разветвление** repo-root → `.claude/`/`.agent/`/глобальная
установка (в `.claude/` **нет** `workflows/` — рецепт читается по пути через `Read`);
**ленивая загрузка слоями** (Слой 0 `description`-меню → Слой 1 инжект тела харнессом →
Слои 2–3 `Read`-цепочка workflow + `references/`); **детерминированная диспетчеризация** (`/`
разрешает CLI, не LLM; команды слиты со скилами; одноимённая коллизия безвредна — оба входа
сходятся на одном рецепте); и **управляющая структура workflow** (линейный спайн + цикл по
`entries[]` + ветвления + per-file isolation, исполняемые оркестратором, тогда как
детерминизм сидит в shell-out Decision-17 CLI). Дополняет [§1.5](#15-project-anatomy) (там —
*где лежат файлы*; здесь — *что и откуда берётся при запуске*). Доступно на двух языках
(держатся синхронными).

→ [details (RU)](./architectures/skill-command-workflow-model.md) · [details (EN)](./architectures/skill-command-workflow-model.en.md)

---

## 2. Functional Architecture

Functional components (Configuration Resolver, Source Adapters, Index Layer DAL, Search Layer FTS5, Lint Layer, Workflow Orchestrator, Migration Tools, Concept Extractor, **Entity Resolver** `wiki-confirm`+`wiki-alias`+`wiki-merge`, **RAG Query Layer** `wiki-query`, **Sync Dispatcher** `wiki-sync` [TASK 018 / R-11 — format+content classifier → scan-plan + orchestrated convert/ingest/upsert/skip; **TASK 019** adds a re-summarization **policy gate** — skip-if-summarized (D1 `source_state` ∪ D2a provenance ∪ D2b mirror) + `--force` + per-folder `.wiki/sync.yaml` cascade overrides], **Native-App Control Skill** `obsidian-cli` [TASK 029 / R-12 — prompt-layer routing/safety/coherence over the official Obsidian CLI; design inline at §2.2]) and the connection diagram between them. Includes the full `wiki-extract-concepts` `prepare`/`apply` contract, candidates JSON schema, the TASK 005 Entity Resolver CLI surface + exit-code envelopes (incl. `wiki-merge` duplicate-fold), the TASK 007 `wiki-query` `prepare`/`apply` RAG contract (retrieval envelope + answer/citations contract + grounding gate + `cited`-backlink self-index), operational invariants, and RTM cross-reference.

→ [details](./architectures/functional-architecture.md)

**§2.1 Concept Extractor module decomposition (TASK 016).** The `wiki-extract-concepts`
component is implemented as a **package** `scripts/wiki_skills/wiki_extract_concepts/`
(was a single 2174-line module). The split is a behaviour-preserving structural refactor;
its one architectural invariant is the **patch-target lock** — the import path
`scripts.wiki_skills.wiki_extract_concepts` and **8** monkeypatched symbols
(`make_repo`, `load_known_entities`, `validate_manifest`, `index_from_manifest`,
`dispatch_to_indexer`, `_apply_candidates_to_db`, `_try_update_idempotency_state`,
`update_idempotency_state`) must remain rebindable at that namespace, with in-package
callers resolving them as **facade globals** so `mock.patch("…wiki_extract_concepts.<name>")`
intercepts the call (the R-2 invariant, guarded by `test_patch_target_lock_at_skill_module`).

| Module | Responsibility | Monkeypatch coupling |
|---|---|---|
| `__init__.py` (facade) | Orchestration: `prepare`/`apply`/`dispatch_to_indexer`/`_batch_*`/`main` + the argparse builder; binds all 8 lock symbols as facade globals (callers resolve them here) | **Owns the lock surface** |
| `_validation.py` | Validators, sanitizers, candidate-schema, `classify_candidates`, `_preflight_sanitize`, `_parse_source_span`, regex/const allowlists | none |
| `_sourcing.py` | `_read_file_bounded`, `_resolve_source_inside_sources`, `_all_concepts_dirs`, `_derive_source_project`, `_load_candidates`, `_path_is_absolute`, byte caps | none |
| `_db.py` | `load_known_entities`, `upsert_extracted_entity`, `upsert_entity_refs`, `check_idempotency`, `update_idempotency_state`, `build_manifest`, `_lookup_entity_row` | **carve-out**: `load_known_entities` + `update_idempotency_state` are re-imported into the facade and called there as facade globals |
| `_pages.py` | `write_concept_page` (seeds the derived `BEGIN-AUTO:mentions` block via the shared `_common.format_concept_mentions_body`; TASK 047 retired the embedded per-source quote-block), name allowlist | none |
| `_errors.py` | `ExtractionParseError`, `_envelope_from_parse_error` | none |

`python -m scripts.wiki_skills.wiki_extract_concepts` keeps working via a package
`__main__.py` (the `bin/wiki-extract-concepts` wrapper + the integration subprocess test
depend on it). The decomposition adds **no** data-model, interface, security, or schema
surface — see `docs/TASK.md` (TASK 016) for the full RTM + acceptance gates.

**Import-direction rule (acyclic; the only forbidden edge is leaf → facade).** `_errors`
is the dependency sink. Leaves MAY depend on lower leaves: `_validation` → `_errors`(+`_common`);
`_sourcing` → `_errors`; `_pages` → `_validation` + `_errors`; `_db` → `_validation`
(`upsert_entity_refs` calls `_parse_source_span`) + `_errors`. The facade → all leaves +
`_manifest_consumer` + `factory`. No leaf may import the facade (that would both cycle and
break the facade-global lock). (TASK 047 deleted the dead `_format_source_quote_block` — the
concept-page mentions ledger is now a derived Class-B AUTO block, links only.)

**§2.2 Native-App Control Skill `obsidian-cli` (TASK 029 / R-12 — prompt-layer only).**
The component is **skill text, not code**: `skills/obsidian-cli/` (SKILL.md +
`references/{command-reference,recipes}.md` + `evals/`) symlinked into
`.claude/skills/` + `.agent/skills/`. It sits ABOVE the existing stack: the official
`obsidian` binary (a remote control for the RUNNING desktop app; GA since 1.12.4) is
itself the deterministic plumbing layer — **Decision-17 generalised**: we do not wrap
a binary in Python when the binary already carries a stable CLI contract; the skill
encodes routing judgment, safety policy, and coherence obligations in the
orchestrator's prompt layer, vendor-agnostic (any LLM). Four invariants form the
component contract:

1. **Routing invariant** — knowledge/RAG → `wiki-search`/`wiki-query` FIRST
   (unchanged, restated verbatim in the skill); bulk ingest/index →
   `wiki-sync`/`wiki-reindex`/`wiki-index-upsert`; live-app ops (link-safe
   rename/move, typed properties, tasks, daily notes, templates, Bases queries,
   history restore, UX) → `obsidian` CLI; plain content edits → file tools (+ upsert
   if indexed). App `search`/`search:context` is a complement (no
   BM25/stemming/citations), never the knowledge default.
2. **Coherence invariant (amended TASK 030 / R-030-1)** — any app-side mutation of a
   wiki-registered vault is followed **same-turn** by: `wiki-index-upsert <file>`
   (single-file content change); **`wiki-reindex --delta` for rename/move AND delete**
   (since TASK 030 the delta is rename-aware: an on-disk path absent from
   `pages.file_path` is ingested regardless of mtime — the DF-029-1 class incl.
   `cp -p`/archive/sync imports is closed; visible via the additive
   `new_path_ingested` envelope field; a fresh vault's FIRST `--delta` now ingests
   everything on disk, Q-030-3). `wiki-reindex --full` remains the universal fallback
   and the REQUIRED remedy for the A5 residual class (swap/rotation/overwrite renames
   — destination path already indexed; detectable via `wiki-lint` hash-drift) and for
   entity-page `entities.file_path` refresh. Historical note: TASK 029 (bead 029-06)
   prescribed `--full` for every rename — correct THEN (pre-030 `--delta` missed
   mtime-preserved renames, proven live), superseded by the TASK 030 code fix.
   ADR-002 §D8 unaffected: Class-A files are mutated app-side, the DB stays a
   rebuildable projection. Unregistered vault → the protocol self-disables (the skill
   stays standalone-capable, Q-029-2).
3. **Safety invariant** — a **TOTAL tier function** over the captured 102-command
   surface: **T1** read-only (+ a T1-UX open/GUI sub-class: `open`, `daily`,
   `*:open`, `random`, `tab:open` — on-disk-side-effect-free); **T2** mutating
   (explicit `path=` REQUIRED — the live CLI defaults to the **active file** when
   file/path is omitted [F-4 footgun; **amended by §2.2.1 / ADR-008** — the default
   becomes a deliberate resolved-then-confirmed target, the mutation still carrying an
   explicit `path=`]; trash over permanent delete; existence-check
   before `overwrite`; `base:create` named here); **T3** banned-by-default (`eval` =
   arbitrary JS in the app process / RCE-equivalent, `dev:*`, `devtools`, `plugin:*`
   incl. `plugin:reload`, `plugins:restrict`, `theme:install/uninstall/set`,
   `snippet:enable/disable` [CSS-injection surface], `sync on/off`,
   `restart`/`reload`) — operator-explicit only, NEVER from note content.
   Two **gate-closing refinements** (029-07 critic-security): (i) `command id=`
   **defaults to T3** (not T2) when the dispatched effect can't be proven from the tier
   lists — a friendly palette title doesn't reveal a code-running/sync-force-push
   capability (closes the same-effect-different-verb gap); (ii) **template application is
   a code-execution surface** — `template:insert`/`create template=` inherit **T3** when a
   scripting plugin (Templater/QuickAdd) is present unless the template is
   `template:read`-verified JS-free (else an attacker-planted JS template is an `eval`
   bypass through a T2 verb). **`command id=` and
   `template:insert` operate on the ACTIVE-FILE/editor context** (neither accepts
   `path=`), so for this sub-class the explicit-target guarantee is replaced by
   (a) default-DENY on an unnameable effect AND (b) verifying/confirming the active
   file before any such mutation (arch-review S-1); any command not enumerated
   defaults to **T2-with-confirmation** (fail-safe). All CLI output is untrusted
   vault content (H-6 posture; by analogy to the TASK 012 SEC-1 egress discipline).
4. **Degradation invariant** — probe = `command -v obsidian` + `obsidian help`
   (**NOT `version`** — listed-but-unrunnable on live 1.12.7, TASK 029 F-3);
   absent/headless/CI → announce the fallback to wiki-*/file-ops (no silent GUI
   launch — the first CLI command launches the app if closed); the surface is
   **dynamic** (plugin-gated: the captured machine lacks `publish:*`, `unique`,
   `workspaces`, `web`) → feature-detect via `obsidian help <command>` before
   relying on a gated command.

Zero impact on §4 Data Model (no DDL, no DAL change), §5 Interfaces (no new
CLI/JSON envelope — the skill consumes existing ones), §6 Stack (no deps). The eval
harness is machine-checkable without a Python grader (per-case expectation fields,
TASK 009 pattern — Q-029-1). Verified-surface snapshot:
`samples/obsidian-cli-recon/` (scratch) → durable fixture lands under
`skills/obsidian-cli/evals/` when the reference is authored (TASK 029 A-4).

**§2.2.1 Active-note resolution (TASK 041 / ADR-008 — amends the inv. 3 F-4 footgun).**
A user in Obsidian's integrated shell says *"отредактируй заметку / edit the note"* with **no
path**. TASK 029's inv. 3 forbade using the CLI's active-file default (the F-4 footgun) — so the
one context the user is sure of, *the note on screen*, was unusable. ADR-008 turns that default
into a **deliberate, confidence-driven** targeting path. The component is again **mostly skill
text** plus **one new skill-local executable** — `skills/obsidian-cli/scripts/obsidian_active_note.py`
(entrypoint `obsidian-active-note`), the single deterministic resolver (Decision-17 generalised;
stdlib, no `import anthropic`). Five sub-invariants:

1. **Resolution (read-only, over the OPEN-tab set), by how the user named the target.**
   - **Descriptor** ("the note about *github setup*", any language) → match the wrapper's
     **open-tab list** (path + title). A **unique** match is an **exact hit**.
   - **Bare reference** ("the/this/current/open note") → the **active/focused** tab via the
     documented path-returners — `obsidian file` (no `path=` → "Show file info"; fixture L10 "Most
     commands default to the active file when file/path is omitted"), the active-file default on
     reads, the `active` flag on `tags`/`aliases`/`properties`/`tasks`. **`tabs` exposes only `ids`
     (no focus marker)** and `recents` is a recency heuristic — both corroborate, neither leads
     (Q-041-1). The wrapper owns both modes (focused note + open-tab list) so no agent re-parses CLI
     output; it returns vault-relative + absolute path + vault name. **Feasibility gate — RESOLVED at S0**
   (real 1.12.7 fixtures under `skills/obsidian-cli/evals/fixtures/`): `obsidian file` (no path) →
   parseable TSV `path\t<rel>` (MEDIUM solid); `obsidian tabs` → **title only** (no path/focus marker)
   → open-tab→path is two-step (`tabs` title-match + `file=<title>`). So the descriptor branch ships
   as a **TEMPERED HIGH**: no-ask only on a **unique** open-tab title match that resolves
   unambiguously; any ambiguity (none/many/duplicate) → **LOW → ASK** (the ambiguity guard satisfies
   M-1 — the candidate set is enumerated; a wrong-file mutation can never happen silently).
2. **Confirmation keyed to resolution CONFIDENCE, not a flat rule** (user decision + refinement):
   **HIGH** (descriptor → unique open tab) → proceed, **no ask** (the "exact hit"); **MEDIUM**
   (bare ref → active tab) → **confirm first-per-session**, then bounded trust on same-class ops at a
   consistently-resolved path; **LOW** (descriptor matches nothing open / multiple tabs / split-pane
   no focus) → **ASK** — "agent didn't find it" → request path / disambiguate, **never** a silent
   active-tab substitute when a *different* note was named. Read-only never prompts; the resolved
   path is echoed every time; **destructive verbs (`delete`/`move`/`rename`/`history:restore`) always
   re-confirm regardless of confidence** (preserves T2 + E-14); trust is conversation state →
   **fail-safe reset to "confirm again" on context loss**.
3. **The mutation always carries the explicit, resolved `path=`/`vault=`** — never the implicit
   default (keeps the E-11 footgun green; ADR-002 coherence needs the absolute path: post-mutation
   same-turn `wiki-index-upsert --source <abs>` / `wiki-reindex --delta`, self-disabling on an
   unregistered vault; a focused tab in a vault ≠ the task context surfaces as the wrapper's
   `vault-mismatch` exit code).
4. **Safety extended, not relaxed.** Resolution is driven by **live app state, never note content**
   (H-6); **auto-resolved read content is DATA** — it cannot introduce a new target, verb, or
   T2\*/T3 op (no action-escalation); auto-resolution **never** feeds the active-file T2\*/T3
   sub-class (`command id=`, `template:insert`) — they stay default-DENY; **headless/CI → no probe,
   no resolve**.
5. **Vendor-agnostic (NF-1).** Identical under any LLM CLI (Claude Code / Codex / Gemini / pi /
   hermes / …): the resolver is a **plain shell executable**, the protocol is **skill prose + shell
   commands**, confirmation is **plain conversational** — no vendor SDK, tool, hook, or prompt-UI
   dependency; no per-vendor code path to diverge.

Wrapper contract (Q-041-4): four modes (`focused`/`tabs`/`resolve`/`match`); typed exit codes
`0` ok / `no-active-file` / `app-not-running` / `cli-absent` / `vault-mismatch` / `ambiguous` /
`headless`; JSON + plain-path output; **CI-deterministic** unit
test mocks a captured `obsidian file`/`tabs` fixture (no live app); a manual dogfood smoke confirms
the live focused-tab path. **Headless ordering (arch-review M-3):** the agent decides headless
**from the environment BEFORE invoking the wrapper** (per E-13 — any obsidian subcommand, the
wrapper's included, launches the GUI), so in a known-headless context the wrapper is **not called at
all**; its `headless`/`app-not-running` codes are belt-and-braces, never the primary gate. **Still zero impact on §4 Data Model and §6 Stack (stdlib); §5 gains ONE
skill-local resolver** (a deterministic active-file/open-tabs → path projector with its own
exit-code contract — not a wiki CLI). New evals extend the TASK 029 grader-free harness
(descriptor-HIGH-no-ask, descriptor-LOW-ask, bare-MEDIUM-confirm, destructive-re-confirm,
injection-neg ×2, headless-no-resolve); E-09/E-10/E-11/E-13/E-14/E-15 stay green.

**§2.3 The unified construct path `wiki-import` (TASK 039; generalizes TASK 038's
`wiki-import-article`, now a back-compat alias).** Knowledge enters through ONE config-driven
path with two **orthogonal** axes — **content-type → which REASON harness**
(all content-types → the ONE universal `summarizing-meetings` harness — it handles meetings
AND articles/papers/threads; finished `summary`→register), and **layout (config) → where it files** (Karpathy `_sources/`+root
`_concepts/` vs PARA topic-folder+sibling `_concepts/`, via `resolve_layout_config` — same code
path as `wiki-index-upsert`/`wiki-extract-concepts`). This replaces the TASK 038 *layout-fork*
(which left a PARA meeting transcript with no clean path); the single diagram + orthogonality
matrix are in [functional-architecture §2.3](./architectures/functional-architecture.md). The
original (now-legacy) PARA-import design below is preserved for history. **TASK 046 (converged
construct pipeline)** makes `wiki-import` the **single per-source engine** (it absorbs office/`.vtt`
acquire into `prepare`; `apply` picks output-grammar by `--kind` — pyramid for meeting/lesson, article
otherwise; adds `--diagrams` + `--concepts/--no-concepts`) and turns `wiki-sync` into a **pure batch
driver that delegates per item to `wiki-import`** — retiring the `wiki-sync`↔`wiki-import` acquire/distil
overlap (one owner per concern; §2.3.4 + Q-046-1).

**§2.3.2 Transcript-fetcher: a third wrapped external skill for video sources (TASK 044 — extends ADR-001).**
`dispatch_fetch` in `scripts/wiki_skills/wiki_import_article/_fetch.py` previously routed every
source to one of TWO external skills (`html` or `pdf`). A video URL therefore hit the `html` skill
and captured only the watch-page chrome — no spoken content. TASK 044 adds a THIRD external-skill
fetch branch, `transcript-fetcher`, following the exact composition pattern of `html`/`pdf`
(NF-2, ADR-001 "Wrap + Index").

**External skill contract.** `transcript-fetcher` lives at
`/Users/sergey/dev-projects/Universal-skills/skills/transcript-fetcher/`; its own venv is
`scripts/.venv/bin/python scripts/fetch.py`. CLI: `fetch.py <URL> --out <path.txt> --json-errors
[--lang <code>] [--prefer manual|auto] [--with-description] [--cookies-file PATH]
[--cookies-from-browser BROWSER] [--max-duration-min N]`. Output: a plain-text `.txt` (no
frontmatter) + a sibling `<out>.stat.json` sidecar carrying `transcript_origin`
(`embedded-captions | macwhisper | whisper-cli | whisper-cpp | openai-api`), `quality_flag`
(e.g. `english_auto_translation`), and title/uploader/duration. Optional `<out>.description.md`.
Typed exit codes; exit 7 = `MissingDependency`. A `_transcript_python()` helper mirrors
`_pdf_python()` — prefers the skill's own venv interpreter.

**Routing table (DECISION 2 — hybrid, URL-shape + `--video` flag; Decision-17: zero LLM guesses,
zero network probes in the default path).**

| Source shape | Default route | `--video` flag |
|---|---|---|
| `youtube.com`, `youtu.be`, `vimeo.com` | transcript-fetcher AUTO | n/a (unambiguous) |
| Skool lesson URL (`skool.com/*/…/lesson/`) | transcript-fetcher AUTO | n/a (unambiguous) |
| `x.com/i/broadcasts/<id>`, `x.com/i/spaces/<id>` | transcript-fetcher AUTO | n/a (unambiguous) |
| `x.com/<user>/status/<id>` (ambiguous: text OR video) | existing `html` path | forces transcript path |
| Any other URL / local file | existing `html`/`pdf` dispatch (byte-identical) | — |

Auto-routing applies only to hosts that have **no usable text path** (html returns login/landing
chrome) — it is a pure win with zero regression. The ambiguous `status/<id>` URL stays on the html
default (most tweets are text) so the existing text-only path is never broken.

**Text + video concatenation for `--video` on a status URL (DECISION 3).** When `--video` is
given on an `x.com/<user>/status/<id>` URL both fetches are run: the `html` skill (tweet prose)
AND `transcript-fetcher` (video). The written `_raw/<slug>.md` = the tweet text as a header
section followed by the video transcript as the body. Nothing is lost; neither branch is
short-circuited.

**Typed-error / FETCH_FAILED mapping and the no-media → html fallback.** The `_fetch_transcript()`
function maps transcript-fetcher exit codes into `FetchResult.error` using the same
`FetchResult(ok=False, engine="transcript:<origin>", error={…})` shape as `_fetch_html`/
`_fetch_pdf_url`. Key behaviours:

- **"No media" (transcript-fetcher exit 3 = "no transcript producible") — fallback is SCOPED BY
  HOST CLASS:**
  - on an **`ambiguous_x_status`** URL under `--video`, `_fetch_transcript` returns a typed
    no-media result → `dispatch_fetch` falls back to the existing `_fetch_html` path (mirrors the
    `arxiv_no_html` → pdf fallback). A misused `--video` flag degrades gracefully to the tweet prose.
  - on an **`unambiguous_video`** URL (YouTube/Vimeo/Broadcast/Space) exit 3 maps to
    **`FETCH_FAILED` (exit 10), NO html fallback** — there is no useful text path (html would return
    only the watch-page chrome this task removes). Note exit 3 conflates genuine no-media with
    "ASR produced nothing on real media"; on an unambiguous-video host both are a hard FETCH_FAILED.
  No `_raw/` is written on an empty/failed result either way (R-3 holds).
- **Broadcast/Space with no ASR backend (exit 7)** — mapped to the `FETCH_FAILED` envelope with
  `DEP_MISSING` semantics (exit code 6), carrying an actionable "install ffmpeg + a whisper
  backend" message. No `_raw/` is written on failure (R-3). The `--transcript-bin` flag enables
  fail-fast absent-binary detection via the existing `require_bin()` helper.
- **Login-walled video** — surfaces the same cookies guidance as the existing `_is_x_login_wall`
  check; suggests `--cookies-from-browser` / `--cookies-file`.
- **`quality_flag: english_auto_translation`** — surfaced to the operator in the prepare envelope
  AND recorded in the note frontmatter provenance. This is a hard rule of the transcript-fetcher
  skill.

**Provenance.** `FetchResult.engine` is set to `transcript:<origin>`. As shipped (S0 contract
verification against the real transcript-fetcher source): `transcript_origin` is set ONLY by the X
adapter, so for youtube/vimeo/skool the origin falls back to the stat's `chosen_track_kind`
(+`asr_backend` for ASR) — e.g. `transcript:embedded-captions` / `transcript:auto`. wiki-import
ALWAYS passes `--with-description` (so the stat carries `title`/`uploader`/`upload_date`) and
`--lang <vault-language>` (never the skill's `ru` default). The `.txt` output carries no frontmatter,
so the existing `ensure_source_frontmatter()` function — which already handles the PDF/text-dump
no-FM case — injects the `source:` field without any new code. The `<out>.txt.stat.json` sidecar +
exit-code map (transcript 7→DEP_MISSING exit 6 · 6=rate-limit→FETCH_FAILED · 5=auth→cookies hint ·
3=no-media) were pinned against the real source (resolves Q-044-2).

**Content-type axis stays orthogonal (Decision-17 + `_detect.py` unaffected).** `--kind`
detection in `_detect.py` is unchanged: a transcript body with timestamps/speaker-turns heuristically
maps to `kind=meeting`; the operator may override `--kind`. The one universal `summarizing-meetings`
harness handles all kinds — no new `kind` is introduced. The routing decision in `dispatch_fetch`
is deterministic (URL shape + `--video` flag), never an LLM guess.

**Path-dependent dependency posture.** Captioned YouTube/Vimeo/x-status-video need only `yt-dlp`
(light path). Caption-less broadcasts/spaces additionally need `ffmpeg` + a whisper backend (ASR
path). `ffmpeg` is REQUIRED for HLS sources; absent → exit 7 → `DEP_MISSING` envelope in
`dispatch_fetch`. No new entry in `requirements.txt` — `transcript-fetcher` is an external binary
(like `html`/`pdf`) loaded via `--transcript-bin` (or discovered via `require_bin()`), not a Python
runtime import. **Zero new Python runtime deps; zero SQLite DDL** (`user_version` 7 untouched).

**Invariants preserved.** Decision-17 (no `import anthropic`; deterministic routing); Class A/B/C
layering (`_raw/` written only on a non-empty `ok` result, R-3); `validate_inside_vault` + H-6
frontmatter-injection guards on all write paths (R-26); vendor-agnostic (subprocess + flags, runs
identically under claude/codex/gemini/pi/hermes); zero-DDL posture. New CLI flags (`--video`,
`--transcript-bin`, `--max-duration-min`, `--cookies-from-browser`, `--cookies-file`, `--lang`)
land in `__init__.py`/`__main__.py` and are passed through to `dispatch_fetch`. Design residuals:
Q-044-1.

**§2.3.3 Embedded-video discovery (opt-in `--embedded-videos`) — TASK 044 R-13.**
When the operator passes `--embedded-videos`, `dispatch_fetch` extends the `not_video` html path:
after the html skill fetches the page prose it also discovers, filters, and transcribes `<iframe>`
video embeds found in the raw HTML. The flag is **off by default** and is a **NO-OP** on
`unambiguous_video` and `ambiguous_x_status` URLs (those are `--video`'s domain). Passing both
`--video` and `--embedded-videos` on the same URL is a usage error (exit 2).

**Why raw-HTML scan, not html-skill output.** The html skill (`preprocess.py`) strips `<iframe>`
and `<video>` elements before emitting Markdown, and its `meta.json` sidecar carries no embed
URLs. Composing with the html skill's output is therefore impossible for embed discovery — the
raw page HTML must be read directly. Discovery uses a **single SIZE-CAPPED raw-HTML GET** (reuses
the `urllib` + browser-UA + byte-cap pattern of `_download_pdf`; cap constant
`_EMBED_FETCH_MAX_BYTES`, default 2 MB) followed by a bounded, anchored, ReDoS-safe regex scan
for video-embed URL patterns. The raw-HTML GET is the only additional network call; the html
skill's own fetch (which already ran for the article prose) is separate and unchanged. Design
rationale: Q-044-9 / Q-044-10.

**Filter chain — order is fixed and always applied in full when `--embedded-videos` is set.**

```
allowlist → ad-network denylist → ad-context → ad-param → dedup → cap → fetch
```

1. **Allowlist (H-6 / SSRF).** Only known video-host embed patterns pass:
   `youtube.com/embed`, `youtube-nocookie.com/embed`, `youtu.be`, `player.vimeo.com/video`,
   `vimeo.com`. Any `<iframe src>` not matching is silently dropped — the page cannot trigger a
   fetch to an arbitrary host. Residual SSRF surface (operator-trusted, allowlisted hosts only)
   is documented in `skills/wiki-import/SKILL.md` alongside the pdf residual.

2. **Ad-network host denylist (always-on belt-and-braces).** Drop any embed whose host matches
   a known ad-network domain: `doubleclick.net` (incl. `*.doubleclick.net`,
   `googleads.g.doubleclick.net`, `g.doubleclick.net`), `googlesyndication.com` (incl.
   `pagead2.googlesyndication.com`), `imasdk.googleapis.com` (Google IMA SDK), `2mdn.net`,
   `adnxs.com`, `adservice.google.*`. Most of these are already rejected at step 1 (outside the
   allowlist), but they are listed explicitly here as a belt-and-braces guard against
   youtube-hosted IMA/ad URLs that carry an allowlisted host but resolve to an ad endpoint.
   Logged as skip reason `ad-denylist`.

3. **Ad-context exclusion (always-on, bounded scan).** Skip any allowlisted embed whose
   ENCLOSING element (inspected within a **bounded character window** around each matched
   `<iframe>` — not a full DOM parse) carries class/id/data-* attributes that signal an ad or
   non-content slot. Word-boundary, case-insensitive match on:
   `ad`, `ads`, `advert`, `advertisement`, `advertising`, `sponsor`, `sponsored`, `promo`,
   `promoted`, `dfp`, `adsbygoogle`, `googlead`, `outbrain`, `taboola`, `recommend`, `related`,
   `widget`. Also excluded: embeds inside `<ins class="adsbygoogle">`, inside `<aside>`, inside
   `[role=complementary]`, and inside `[aria-hidden="true"]`. The scan uses a fixed-length
   character window and bounded-quantifier regex — no nested quantifiers, ReDoS-safe by
   construction (same posture as the layout-config load-gate). Logged as skip reason `ad-context`.

4. **YouTube ad-param drop (always-on).** Drop any youtube/youtube-nocookie embed URL carrying
   ad marker query parameters: `ad_type`, `adformat`, `ad_companion` (case-insensitive key match
   on the parsed query string). Logged as skip reason `ad-param`.

5. **Dedup.** The same embed URL appearing multiple times in the raw HTML is fetched once
   (set-based dedup applied after ad-exclusion, before cap). Logged as skip reason `dedup`.

6. **Cap (`--embedded-videos-max N`, default 5).** Applied after ad-exclusion and dedup, so
   ad embeds never consume cap slots. Embeds surviving filtering beyond N are dropped; a note
   naming the count dropped is appended to the prepare envelope's `details` list. Logged as
   skip reason `cap`.

7. **Fetch.** Each surviving embed URL is passed to the existing `_fetch_transcript()` function
   (reused without modification) with `--lang` always forwarded (R-11 invariant).

**Ad-exclusion is always-on — there is no flag to disable it.** When `--embedded-videos` is
active, the three ad-exclusion filters (steps 2–4) are unconditional. Advertising and promotional
embeds must never be transcribed; this is an operator hard requirement. The `--embedded-videos`
flag itself is the opt-in control; ad-exclusion has no separate toggle. Design rationale:
Q-044-11.

**Per-embed failure isolation (contrast §2.3.2's hard-fail).** A transcript failure for one
embed (exit 3 no-media / exit 7 dep-missing / exit 5 auth) is skipped with a logged note in the
envelope `details` and does NOT abort the page import — the article prose remains the primary
content and `_raw` is still written. This is the inverse of the `unambiguous_video` path in
§2.3.2, where exit 3 is a hard `FETCH_FAILED`: embedded videos are supplementary, not primary.

**Skip-reason logging — no silent behavior.** The prepare envelope's `details` MUST log every
discovered embed URL and the reason it was skipped or fetched. Skip reasons are exactly:
`ad-denylist` / `ad-context` / `ad-param` / `not-allowlisted` / `dedup` / `cap` /
`transcript-failure`. An embed that proceeds to fetch and fails is logged as
`transcript-failure`. No embed is silently dropped at any filtering stage.

**`_raw` assembly and provenance.** `_raw` = article prose (primary output of the html skill
fetch), with each successfully transcribed embed appended as a level-2 heading:
`## Embedded video <k> — <title or url>`. `FetchResult.engine = "html+embedded:<count_transcribed>"`,
where `count_transcribed` is the number of embeds that produced a transcript. `_raw` is written
only if the html result was ok and non-empty (R-3 invariant); embedded transcripts are strictly
additive. Each embed's `transcript_origin` is preserved in its heading; any `quality_flag`
(e.g. `english_auto_translation`) from any embed sidecar is aggregated and surfaced in the
prepare envelope per R-8.

**Reuse.** `_fetch_transcript()`, `_video_host()` (for allowlist matching), `require_bin`,
`ensure_source_frontmatter`, and `_fm_safe` are all reused without modification; no fetch or
parse logic is duplicated. Zero new Python runtime deps; zero SQLite DDL (`user_version` 7
untouched). `mypy --strict scripts/` clean; no `import anthropic` (Decision-17).

**Ad-exclusion residual.** Ad-exclusion is a heuristic — a sufficiently disguised embed (no ad
signal in class/id, allowlisted host, no ad query params) may slip through. The residual is
bounded by: (1) `--embedded-videos` is opt-in, (2) cap bounds total embed count, (3) per-embed
failure isolation means a slipped-through ad that returns no transcript is logged harmlessly,
(4) full skip-reason logging gives the operator visibility. The residual and its boundary
conditions are documented in `skills/wiki-import/SKILL.md`. Design rationale: Q-044-11.

**(TASK 038 — legacy framing, retained)** The framework's Karpathy construct path is `wiki-enrich` → external
`wiki-ingest` → (Phase 2) `summarizing-meetings` → concept/entity wiring → index, whose
load-bearing discipline is *passing the known-concepts list to the summary generator* so
`[[wiki-links]]` reuse existing names and never dangle/collide. **PARA had no packaged
equivalent** — `wiki-ingest` writes Karpathy `_sources/` + root `_concepts/_entities/`,
wrong for PARA (TASK 024 finding #2). This component packages the PARA path as a new
**Decision-17** CLI (no `import anthropic`; `prepare`/`apply`) plus a skill/command/workflow
triple. It is **composition, not reinvention** (NF-2): `prepare` shells out to the global
`html` (URL/HTML — which post-2026-06-18 itself owns the Wikipedia-REST-HTML and
arXiv-`/html/` rewrites + typed `EmptyExtraction`/`arxiv_no_html`) and the `pdf` skill
(PDF), writes `_raw/<slug>.md` **only on a non-empty fetch**, and emits an envelope adding
`known_concepts[]` + `existing_page_slugs[]` (sourced from the existing
`wiki-extract-concepts` machinery). The orchestrator (LLM) owns translation/summary,
**fed the known_concepts** (R-6, the core fix). `apply` is the authoring glue the DAO/#01
batches did by hand — per-mode note assembly (full/summary/thread), `_NAME_ALLOWLIST` name
sanitization, verbatim-`source_quote` guarantee, and the **collision guard** (skip a
candidate whose slug == the source note's own slug, or collides with an
`existing_page_slugs` entry — so a generic `defi` concept never evicts the owner's
`Defi.md`) — then delegates concept filing to `wiki-extract-concepts apply` and indexing to
`wiki-index-upsert`/`wiki-reindex`. **Two distinct hashes (do not conflate):**
`prepare.source_hash = sha256(_raw bytes)` is for wiki-import-article's own import idempotency
(R-7) only; the `--source-hash` fed to `wiki-extract-concepts apply` is a **fresh
`sha256` of the just-written PARA note body** (apply re-resolves + re-hashes the *filed
note* and rejects a mismatch as `SOURCE_CHANGED_DURING_EXTRACTION`), with the note's own slug
as that call's `--source-page`. The name sanitizer is a **pre-normalizer that feeds** the
existing `_validation._sanitize_name` reject-gate (rewrite `/`/em-dash/guillemets → safe so
the candidate then passes that gate; reuses its `_NAME_ALLOWLIST`, no duplicate). All write
surfaces (`_raw/`, note, concept pages) route through `validate_inside_vault` (R-26) +
`_is_valid_slug` (a hostile fetched title cannot traverse), and the assembled note body —
YAML frontmatter scalars (title/URL/author/published/tldr) are newline/control-stripped and
quoted (H-6 frontmatter-injection guard); the note BODY is orchestrator-authored markdown,
kept structural (escaping a translation's headings/lists would defeat the purpose — same
trust posture as `wiki-ingest`/`summarizing-meetings` summaries), while the generated
**concept pages** are markdown-sanitized by extract-concepts' `write_concept_page`
(`_sanitize_markdown_text`). The `html`/`pdf` shell-outs are external
skill **binaries** (configurable `--*-bin`, fail-fast if absent) — NOT Python runtime
dependencies, so NF-1 "zero new deps" holds. Zero impact on §4 Data Model (no DDL — rides
`pages`/`entities`/`page_entity_refs`), §6 Stack (no deps). §5 Interfaces gains ONE new CLI
surface (`wiki-import-article prepare|apply` + envelopes). Batch import (the DAO/#01 pattern)
stays a documented **Workflow-tool recipe** in `workflows/wiki-import-article.md` (parallel
translation; serialized DB writes), not a CLI mode. **Skill-call flow diagrams (Karpathy vs PARA,
mermaid)** are in [functional-architecture §2.3](./architectures/functional-architecture.md).
Design rationale: open-questions Q-038-*.

**§2.3.1 Construct-path hardening (2026-06; dogfooding + a 14-round adversarial `/vdd-multi`).**
Six properties were added/repaired so the path works **universally across all four built-in
layouts and any output language**:
- **Internationalization (no hardcoded locale).** The rendered note's language follows the
  vault's `language` (`WIKI_SCHEMA`; **English fallback**, via the guarded `_vault_language`).
  Section headings/labels/origin phrases are localized through a `NOTE_TEMPLATES` registry
  (en + ru built in; a new language = one dict entry); `prepare` emits `language` so the REASON
  step produces title/tldr/bullets/body in it. The note-JSON contract uses **neutral
  `title`/`body`** (legacy `title_ru`/`ru_body` accepted as back-compat aliases).
- **Clickable `_raw` link.** The filed note links to its source capture with an Obsidian
  wikilink `[[_raw/<slug>]]` (resolves in any vault), and `reindex._body_refs` **skips
  `_raw/`-targeted refs** so the link is never a false orphan; `sources:` frontmatter still
  carries the machine-readable path (resummarization).
- **Concept-filing gate.** Concept pages are filed only when the resolved layout can actually
  index a `_concepts/<slug>.md` page (`_layout_indexes_concepts`: a `concept` `type_mapping`
  **and** a glob reaching the sibling `_concepts/`). Concept-capable = karpathy / obsidian-personal
  / cybos; a structured-doc layout like dev-project files the summary note **without** concepts
  (reported, not a failure) — preserving the Class A/B rebuildability invariant (no orphaned,
  non-`--full`-rebuildable markdown).
- **Layout `type_mapping` + ignore.** dev-project + cybos gained `summary`/`article-summary`/
  `meeting-summary`/`lesson-summary` → db_type summary (imported notes index); cybos also gained
  concept/external/person/company/product/group (its concept pages index). karpathy +
  dev-project + cybos gained `**/_raw/**` in `ignore` (the `_raw/` capture is never indexed as a
  phantom page that could clobber the curated note on a shared `(vault_id, slug, project)`).
- **Decision-17 entry points.** A missing `--folder`/`--vault-root` → clean `INVALID_FOLDER`/
  `INVALID_VAULT_ROOT`; a schemaless vault → language `en` (no crash); a hung `html` →
  `FETCH_FAILED(timeout)` with the temp dir reclaimed; the note JSON is a **bounded read**
  (`NOTE_TOO_LARGE` over 32 MiB); and `main()` has a **catch-all backstop** emitting a typed
  `INTERNAL_ERROR` (exception class only — never `str(e)`, CWE-209) so no path raw-tracebacks.
- **Global install is reproducible.** `bin/install-globally.sh` (→ `~/.local/bin` + `~/.claude/
  skills` + `~/.claude/commands`) and `bin/install-project-symlinks.sh` (in-repo `.claude`/
  `.agent` vendor trees) are safe + idempotent (skip-foreign / repair-repo-owned / per-item
  report). **Run them after adding a new `bin/wiki-*`, `skills/wiki-*/`, or `commands/wiki-*.md`**
  — new entries are not auto-propagated.

---

## 3. System Architecture

Architectural style (layered + plugin), system-component breakdown (Skill Layer → Adapters → DAL → SQLite), component-interaction diagram, and the UC-08 Concept Extraction sequence diagram (calling agent owns LLM synthesis; Python skill is deterministic plumbing only). **§3.5 (TASK 012 / R-X1)** adds the **config-driven Layout Engine**: two separate config layers (per-vault identity via `config_loader` + per-layout grammar via the new `layout_config` + built-in `layouts/{karpathy,dev-project,obsidian-personal}.yaml`), the `iter_pages` walk that converges the four hardcoded two-tier walks, the byte-identity strategy (karpathy.yaml = validated projection of `layout.py`; three slug surfaces kept distinct), the ReDoS guard (TASK 012 stdlib-`re` load-gate **+** the TASK 017 runtime per-file `regex` `timeout=` deadline for operator-custom patterns, R-X1-REDOS-RT), the PW-H `auto_indexes[]` renderer + PW-Q lint guard, and the TASK 017 single-stat walk + drift fast-path (P-2/P-3 — Class-B "rebuildable markdown", zero DDL). **TASK 030 (R-030-3/6)** replaced the per-glob walk with the **single-pass iterative alive-set engine** (`_PatternState` NFA per `paths[]` glob; exact `Path.glob` symlink-union parity; PROPER-prefix descent + real `<prefix>/**` ignore-pruning; every dir scandir'd ≤1× — measured 140→61 at 2k files; karpathy "root subtrees never walked" instrumented; matcher deltas enumerated Q-030-2 v4; the DirEntry-stat single-stat mechanism re-pinned). **TASK 031 (R-031-3)** de-hardcodes the layout REGISTRY on top of this engine: the `--layout` choice-set + the two-tier-scaffold family + the legacy alias map (previously three sources of truth — `wiki_init._LAYOUT_CHOICES`/`_KARPATHY_LAYOUTS` + `layout_config._ALIAS`) collapse into ONE cached YAML-derived registry, via two optional additive `LayoutConfig` keys `aliases`/`init_scaffold` (init-only metadata — they do NOT touch the indexer, so Karpathy byte-identity holds); a new built-in layout becomes a valid `--layout` value as a pure drop-in `*.yaml`. The same task adds the **typed-knowledge taxonomy** (decision/requirement/risk/incident/hypothesis/fact/event) as zero-DDL `type_mapping` tag-routes in `dev-project.yaml` + the new `cybos.yaml` (ADR-003; classification only — the event-graph relation layer is deferred Phase-2 per ROADMAP R-13).

→ [details](./architectures/system-architecture.md)

---

## 4. Data Model (Conceptual)

Conceptual entities (Vault, Page, Entity, EntityAlias, PageEntityRef, SourceState, LogEvent) with key attributes, relationships, business rules, and ADR-002 Class A/B/C layering for each. Includes the entity write-path + downgrade-guard semantics, the TASK 005 two-tier confirm/candidate resolution (`is_candidate` as Class A frontmatter), the EntityAlias activation (PK `(vault_id, alias)`, L-4 closed; schema v2→v3 migration), the duplicate-merge path (R-4.7: pure-DML re-pointing, alias-as-redirect, no merge-ledger table), and the TASK 007 RAG additions (query page as a first-class compounding `type=query` artifact; `ref_type='cited'` query→source backlinks with the R-6.5e reindex read-side; `source_state` reuse for query idempotency — all **zero-DDL**, `user_version` stays 4). **TASK 019** (re-summarization policy) is likewise **zero-DDL**: D1 reuses `SourceState` (`source_kind='sync'`), D2a reads `Page.frontmatter_json` (`json_extract`/`json_each`, TASK 013 mechanism) through **two new read-only DAL methods** — `find_pages_citing_source` (single-source check) + `all_cited_sources` (the bulk citation set, hoisted once per scan, Q-019-10) — D2b is filesystem-only — **no new entity/column**, `user_version` stays **5**. **TASK 032 (event graph, ADR-004)** is the **first schema bump since TASK 008**: `PageEntityRef.ref_type` gains an inverse-closed typed-edge set (`implements`/`implemented-by`, `supersedes`/`superseded-by`, `causes`/`caused-by`; `relates_to` reuses the dormant symmetric `related`) — additive CHECK values only, `user_version` **5→6**, migration = Class-B rebuild. No table/PK change. Forward edges are extracted into the source page's single `replace_refs` (M-1); inverse rows (on the *target* page) are materialized by a global post-pass (AM-3 sibling) — see Q-032-1/2/3.

→ [details](./architectures/data-model.md)

---

## 5. Interfaces

External APIs (CLI surface, JSON-envelope shape), internal interfaces (`IndexRepository` ABC + concrete `SQLiteRepository`, incl. the TASK 005 entity-resolution methods + `merge_entities` + alias-aware `find_orphan_links`, and `wiki-confirm`/`wiki-alias`/`wiki-merge` error codes; the TASK 007 `wiki-query` `prepare`/`apply` CLI surface + `check_query_state`/`record_query_state` DAL methods + error codes), and integrations (wiki-ingest manifest contract v1.1).

→ [details](./architectures/interfaces.md)

---

## 6. Technology Stack

Backend (Python 3.14, SQLite 3.35+ with FTS5 + WAL), frontmatter / pyyaml / python-slugify / jsonschema libraries, infrastructure (single-user laptop, optional iCloud-synced vault, no server).

→ [details](./architectures/technology-stack.md)

---

## 7. Security

Threat model (single-user trust scope), authN (N/A) + authZ (file-permission-only), path-traversal guard (`validate_inside_vault`), SQL-injection guard (parameterised statements only, no f-string composition), and the Vendoring Policy (§7.4) covering type fixups, drift detection, and third-party notices. **TASK 029** adds the prompt-layer command-safety surface for the `obsidian-cli` skill — the TOTAL T1/T2/T3 tier model (T3 ban on `eval`/`dev:*`/plugin/snippet/sync mutations; fail-safe T2-with-confirmation default) + the untrusted-CLI-output posture (H-6 class) — design inline at §2.2 (no code change; the threat actor is hostile note content steering an agent, not a second user). **TASK 041 / ADR-008** extends this posture for active-note resolution (§2.2.1): resolution is driven by **live app state, never note content** (H-6); **auto-resolved read content is DATA** — no action-escalation onto a new target/verb/T2\*/T3 op; the F-4 footgun is *amended not deleted* (the mutation still carries an explicit resolved `path=`, so E-11 holds); destructive verbs always re-confirm (E-14); headless → no resolve. The one new artifact is a stdlib skill-local resolver (`obsidian-active-note`) — no new attack surface on the DB/DAL.

→ [details](./architectures/security.md)

---

## 8. Scalability and Performance

Scaling strategy (vertical only — single-user), caching (SQLite FTS5 cache is the only cache), DB optimisation (WAL mode, narrow indexes, no JSON-expr indexes). Open performance items live in [KNOWN_ISSUES.md](./KNOWN_ISSUES.md) (P-4, P-9, P-11, R-X1-CFG-COST, R-X3-MF-SCAN; P-1 closed by TASK 030 — see §8.5).

→ [details](./architectures/scalability-and-performance.md)

---

## 9. Reliability and Fault Tolerance

Error-handling pattern (fail-fast + structured JSON envelopes + exit codes), backup policy (markdown is canonical → git-versioned; DB is rebuildable cache), monitoring (none in MVP; operator-driven).

→ [details](./architectures/reliability-and-fault-tolerance.md)

---

## 10. Deployment

Environments (single-user laptop, optional iCloud sync), CI/CD pipeline (pytest + mypy --strict on PR), configuration (`config/wiki-config.yaml`, `WIKI_*` env vars), and deployment instructions (clone repo, install requirements, symlink skills into vendor dirs).

→ [details](./architectures/deployment.md)

---

## 11. Open Questions

RESOLVED foundational decisions (11a), defer-able items (11b), and the
architecture-specific open/resolved **Q-0XX** entries (11c) — every shipped TASK's
design rationale lives here (the layout engine Q-012, metadata filter Q-013/033,
vault-local DB Q-022, typed classes/event graph Q-031/032, temporal `--as-of`
Q-034, the TASK 035 FTS-narrowed tag-membership **Q-035-1/2**, the TASK 044
transcript-fetcher video routing **Q-044-1**; embedded-video design rationale +
ad-exclusion heuristic **Q-044-9/Q-044-10/Q-044-11**; and TASK 045 Obsidian
deep-link design **Q-045-1/2**).

→ [details](./architectures/open-questions.md)

---

## Verification Map

Requirement → architecture-surface traceability for Phase 3a MVP (R-01..R-26), Concept Extractor (R-30..R-43), wiki-ingest Vendoring (R-45..R-57), Entity Resolver (R-4 + R-5, TASK 005), RAG Query Layer (R-6, TASK 007), and the **Sync Dispatcher re-summarization policy (TASK 019, AC-1..13 → Q-019-1..9)**.

→ [details](./architectures/verification-map.md)

---

## Quality Checklist (VDD)

- [x] **Data Model**: entities + key attributes + relationships + indexes defined (§4 + SCHEMA-v2.sql). Entity write-path documented in §4.1 Entity Business Rules.
- [x] **Traceability**: Verification Map covers Phase 3a (R-01..R-26), Concept Extractor (R-30..R-43), and wiki-ingest Vendoring (R-45..R-57).
- [x] **Security**: AuthN — N/A (single-user); AuthZ — file permissions; path-traversal + SQL-injection protections explicit (§7.3). `validate_inside_vault` applied to every `_concepts/` write path AND every operator-supplied path (source-page, candidates-file).
- [x] **Multi-vault**: every operation carries a `vault_id` predicate or is scoped to `vault_root`. Vendored `ingest()` accepts `vault_id` as explicit kwarg; no hash-fallback.
- [x] **Stub-First**: TASK 005 Entity Resolver is designed Stub-First (DAL signatures + RED tests before logic); `resolve_entity` is promoted from deferred stub → implemented (R-4.5).
- [x] **RAG Query Layer (TASK 007)**: `wiki-query` designed as a deterministic `prepare`/`apply` skill (Decision-17, no LLM in Python); query page is a first-class compounding `type=query` artifact; durability secured by the R-6.5e `cites:`→`'cited'` reindex read-side (the §D8 gate, mirroring R-5.3); zero schema DDL; grounding enforced in Python (`CITATION_NOT_RETRIEVED` / `NO_CONTEXT`).
- [x] **Native-App Control Skill (TASK 029)**: prompt-layer only — routing/coherence/safety/degradation invariants designed (§2.2); zero DDL, zero new Python, no interface change; safety model TOTAL over the verified 102-command surface with fail-safe default (incl. the 029-07 `command id=`→T3 + Templater-template→T3 refinements); eval harness machine-checkable without a grader (Q-029-1).
- [x] **Indexer hardening (TASK 030, SHIPPED)**: rename-aware `--delta` (new-path membership predicate, zero extra I/O, swap-class residual documented), chunked-tx `--full` (private txn-free DML helpers; M-4/FTS-trigger posture untouched), single-pass pruned walk (descent predicate preserves karpathy "root never walked"; `Path.glob` symlink parity); zero DDL; design at Q-030-1..6; spec docs/TASK.md + reviews/task-030-review.md.
- [x] **Typed knowledge classes (TASK 031)**: classification-only Phase 1 — 7 classes tag-routed zero-DDL onto the existing db_type enum (Q-031-1/2) in `dev-project` + new `cybos` layout (Q-031-3); layout registry de-hardcoded to one cached YAML-derived source via additive `aliases`/`init_scaffold` keys (Q-031-4); event graph deferred Phase-2 (Q-031-5 / ROADMAP R-13). ADR-003; Karpathy byte-identity preserved; 1339 pytest, mypy strict; `/vdd-multi` converged (5 LOW: 3 fixed + 2 accepted-residual). DF-031-1 dogfood doc-fix folded.
- [x] **Event graph (TASK 032)**: R-13 Phase 2 — typed page-to-page edges + graph-aware RAG (ADR-004). Schema v5→v6 inverse-closed `ref_type` (first DDL since TASK 008; Class-B rebuild). Forward edges via per-page `replace_refs` (M-1 intact); auto-inverse via a global AM-3-sibling post-pass (Q-032-2); delta scoped-additions + removal-deferred-to-`--full` (provenance-safe, Q-032-3). New `wiki-graph` CLI (Q-032-5) + typed-edge DAL reads (Q-032-6); `wiki-query --follow-edges` graph-RAG, default OFF, deterministic hash (Q-032-4). Karpathy byte-identity preserved. 1381 pytest, mypy strict.
- [x] **List-membership metadata filter (TASK 033)**: `wiki-search --where` now matches list-valued frontmatter (`tags[]`) via `scalar = ? OR EXISTS(json_each … = ?)` — the proven `find_pages_citing_source` shape lifted into `search_pages` (Q-033-1), + a `--tag <value>` sugar flag (Q-033-2). Closes the ROADMAP R-13 residual (one clean per-typed-class command). Backward-compatible (scalar `--status`/`--severity` unchanged), injection posture preserved (allowlist + twice-bound params + no echo + dup-guard), **zero DDL** (`user_version` 6).
- [x] **FTS-narrowed tag membership (TASK 035, ADR-005)**: closes the hot branch of R-X3-MF-SCAN measured on the real 2493-page vault. Metadata-only `--tag`/`tags=` membership now narrows via the already-existing `pages_fts.tags` index ("FTS narrows, `json_each` confirms" — Q-035-2) instead of a full-partition scan; result list byte-identical (superset + exact confirm, empirically 0 mismatches over 40 real tags), zero-token values fall back to the scan. The scalar/temporal/non-tags branches are left as a scan by design (P-5: their fields are sparse/absent — Q-035-1). **Zero DDL** (`user_version` stays 7), no new dep, no layering inversion, Karpathy byte-identity preserved.
- [x] **ADR-001 clarification**: Source Adapters component preserves the single-indexer invariant while allowing derivative page writes (concept pages) by downstream skills.
- [x] **Backward compat**: subprocess fallback path fully preserved (§1.5.2 FALLBACK PATH); external `wiki-ingest` binary remains optional.
- [x] **Obsidian deep-links (TASK 045)**: `wiki-search` JSON hits gain `file_path` (always present) + `obsidian_url` (`obsidian://open?vault=<folder-basename>&file=<encoded-path>`, null when vault unknown — Q-045-1). Vault cache built once per unique `vault_id` across hits (R-3). `--format markdown`: OSC 8 hyperlinks on iTerm2/VS Code terminal; plain URL fallback for pipe + Apple Terminal (detected via `TERM_PROGRAM=Apple_Terminal` — Q-045-2); chat agents show clean title/slug/snippet (obsidian:// not clickable in VS Code webview CSP). H-6 control-char sanitisation (`_term_safe`) applied to title/snippet before TTY output (CWE-150). Zero DDL, zero new deps.
- [x] **Template**: extended template applied (Sections 1-11 covered + §3.4 Sequence Diagram + §1.5.7 vendored-module subsection + §7.4 Vendoring Policy subsection).
