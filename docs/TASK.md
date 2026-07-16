# TASK 071 — `export-context`: the third agent-bridge channel (note-context handoff for weak-model agents)

## 0. Meta Information

| | |
|---|---|
| **Task ID** | 071 |
| **Slug** | context-export-channel |
| **Type** | code (feature + adversarial-hardening rebuild) |
| **Status** | **SHIPPED** — ⚠️ this spec is **retroactive**: the Analysis phase was skipped (the task was driven conversationally, first by a Haiku session); it records the task, its mid-course VDD FAIL, and the rebuild, after the fact. |
| **Predecessor** | TASK 070 (`docs/tasks/task-070-agent-bridge-mirror-to-gate.md`) — the build gate this feature's plugin change rides on. Extends TASK 068's selection bridge with a third channel. |
| **Input** | Live weak-model dialog transcripts (Haiku): *"перезагрузи текущую заметку"* → the agent cannot resolve which note / which frontmatter URL / what is selected, and asks the user to paste them. Prior design notes: `export-context` command + disciplined field set; **hook rejected** (H-6 — ambient injection of untrusted content removes the "human explicitly handed it over" boundary). |
| **Baseline** | `3000 passed, 14 skipped` @ `8127c15`. **Exit:** `3020 passed, 14 skipped`, `mypy --strict scripts/` clean (97 files), H-5 re-pinned, agent-bridge drift gate green. |

---

## 1. The problem

A weak-model agent in Obsidian's integrated terminal has **no channel to the live editor state**.
When the user says "перезагрузи заметку" (URL in frontmatter) or "отредактируй текст", the agent
must ask *which note / which URL / which text* — friction the stronger models paper over by
guessing. TASK 041 resolves a *path*, TASK 068 reads a *selection*; neither returns the note's
working context (folder, current heading, cursor, outline, tags, frontmatter) in one call.

**Non-goal (rejected design):** an ambient hook injecting the active note's context every turn.
That erases the H-6 boundary — untrusted note content (frontmatter is author-supplied text) would
flow into the agent context without the human explicitly handing it over, which is exactly the
prompt-injection surface this project fences. Context must be **pulled explicitly** by the agent,
per user turn, via a tool call.

## 2. What shipped

- **Plugin command `agent-bridge:export-context`** (third channel beside `export-selection` /
  `apply-edit`): exports `vault`, `path`, `folder` (`""` at vault root), `editorMode`
  (`source`/`preview`), `source` (`active`/`recent-editor`), `mtime`; in source mode `heading`
  (RAW text, no `#`) + `headingLevel` + `cursor`/`cursorOffset`; opt-in `outline`, `frontmatter`
  (H-6), `selection` (H-6). Preview mode **works** (read-only op) — cursor/heading/selection are
  simply absent. Tags via `getAllTags` (inline **and** frontmatter, `#` stripped). Request file is
  read **once** (nonce + flags from a single snapshot — the 3×-read TOCTOU is closed).
- **`scripts/obsidian_context.py`** (entrypoint `obsidian-context`, launcher `bin/obsidian-context`):
  **imports** `obsidian_selection.py`'s hardened plumbing — headless/CLI guards, TSV CWD→vault
  detection (walk-up + realpath), `_await_result` nonce race guard, reason→exit map with a
  fail-closed default — and adds a **payload nonce re-check** (`context-nonce-mismatch`, exit 4)
  plus `_cleanup` (sibling's sweep + `agent-context.json`) on **every** path.
- **Tier T2-read**, enrolled by name in SKILL.md's Proven-effect carve-out (same tier as its twin
  `export-selection` — a `.obsidian/`-scoped JSON write carrying untrusted note content is never T1).
- **Recipes 12–15** (`references/recipes.md`): get-context, refactor-note, continue-writing,
  research-assistant — high-level operation compositions with honest primitives (no
  insert-at-cursor exists; `selection:apply` replaces, `append` is EOF-only).
- **`bin/install-globally.sh`** now globs `bin/obsidian-*` (the hardcoded single-bin line had
  silently never shipped `obsidian-selection` either — that residual is closed).
- **`tests/test_obsidian_context.py`** — 20 contract tests, sibling's `_run_obsidian`-seam pattern,
  fixtures under `evals/fixtures/context/`; the foreign-nonce test is mutation-pinned (deleting the
  payload check flips it to exit 0 + a cross-note data leak).

## 3. History — the first pass FAILED review (kept as the task's core lesson)

The first implementation (same session, **Haiku** model) was reviewed by `/vdd-multi` (3 parallel
critics: logic / security / performance) plus an orchestrator shell-side pass. Verdict: **FAIL** —
the feature had never worked once, and its contract was partly fabricated:

| Class | Representative findings |
|---|---|
| **Fatal happy-path** | `vaults verbose format=json` parsed as JSON — the CLI has **no** `format=` on `vaults` (TSV) → CWD auto-detect *always* failed (exit 6); dispatch omitted `vault=`; launcher broke via the `~/.local/bin` symlink; installer never linked the bin. |
| **Fabricated contract** | SKILL.md (H-5 hash-pinned!) cited `tests/test_obsidian_context.py` — **the file did not exist**; documented exits 2/5/8 unreachable; `--from-json` declared but never read; `reason == "command-failed"` compared against `f"command-failed ({code})"` — never equal. The re-pin had mechanically legalized the false claim. |
| **Security (H-6)** | No cleanup on error paths (plaintext note context left at rest in a synced `.obsidian/`); no payload nonce check (concurrent export → wrong note's data under `ok:true`); selection exported **unconditionally** while frontmatter was opt-in "for security"; tier T1 *below* its own twin's T2. |
| **Systemic** | ★ The unenumerated-surface lens, twice: (a) the sibling's guards existed next door and were re-ported *without* them; (b) the installer's hardcoded bin line sat two lines above the repo's own "ENUMERATE THE POPULATION" banner. |

**Remedy that shaped the rebuild:** guards are **imported from the sibling, never re-ported**
(`import obsidian_selection as _sel` — one source of truth), and every closed finding is pinned by
a test, a type error, or a live smoke — not by prose.

## 4. Requirements (retroactive RTM — each maps to evidence)

| ID | Requirement | Evidence |
|---|---|---|
| R-071-1 | One-call context read works from the vault's integrated terminal, bare (CWD auto-detect) | sibling `detect_vault_from_cwd` (TSV/realpath/walk-up); smoke via PATH symlink |
| R-071-2 | Explicit pull only — no ambient hook; untrusted fields (frontmatter, selection) **opt-in**, off by default | plugin `includeSelection`/`includeFrontmatter` gates; `test_read_default_flags_are_off` |
| R-071-3 | Preview mode succeeds (read-only op); cursor/heading absent, `editorMode:"preview"` | `resolveView` split from `resolveEditor`; `test_read_ok_preview_mode` |
| R-071-4 | Both result AND payload are nonce-attributed; concurrent export fails closed | `test_read_rejects_foreign_context_payload_is_exit_4` (mutation-pinned), `…unstamped…`, `…stale_result…` |
| R-071-5 | Exchange files swept on **every** path (plaintext never left at rest in `.obsidian/`) | `test_exchange_files_cleaned_up_on_success` / `…on_plugin_refusal` |
| R-071-6 | Never `eval`; plugin-absent ⇒ typed exit 9 | `test_wrapper_never_dispatches_eval`, `test_static_source_never_dispatches_eval`, `test_read_plugin_absent_is_exit_9` |
| R-071-7 | Full typed degradation ladder: 0/2/3/4/5/6/8/9 all reachable, reasons stable | one test per rung (headless=8, cli-absent=5, vault-mismatch=6, unknown-reason fail-closed=4) |
| R-071-8 | Tier T2-read, named in the Proven-effect carve-out; H-5 pin honest | SKILL.md §Safety tiers + §Note context export; `tests/test_h5_skill_integrity.py` (25 green) |
| R-071-9 | Installer ships every `obsidian-*` launcher (enumerated, not name-guessed) | `install-globally.sh` glob; live run: 3 links present |
| R-071-10 | `heading` raw (no `#`) + `headingLevel`; tags unified inline+frontmatter, `#`-stripped; `folder` `""` at root; `editorMode` never collides with envelope `mode` | plugin `getAllTags`/normalization; `test_read_ok_source_mode` |
| R-071-11 | Recipes only compose primitives that exist (no insert-at-cursor fiction; EOF-append labelled; jq guarded; on-PATH launcher; Decision-17 `prepare` never "synthesizes") | recipes 12–15 rewritten |
| R-071-12 | mypy `--strict` clean; plugin `main.js` generated via the TASK-070 gate only | 97 files clean; `config/agent-bridge-build.json` re-pinned, drift test green |

## 5. Exit evidence

- Full suite **3020 passed, 14 skipped** (baseline 3000 + 20 new contract tests), 0 failed.
- `mypy --strict scripts/` — clean, 97 source files.
- Agent-bridge build gate: `tsc 5.9.3: 0 errors` against real `obsidian@1.12.3`; drift test green.
- H-5: `config/skill-integrity.sha256` re-pinned over the corrected SKILL.md; 25 integrity tests green.
- Live smoke: launcher via `~/.local/bin` symlink OK; `WIKI_HEADLESS=1` ⇒ typed exit 8 before any
  `obsidian` call.

## 6. Residuals / deferred

- **Critic re-convergence not run:** `/vdd-multi` Phase 3 prescribes re-spawning each critic to a
  clean pass after fixes; instead every finding was closed with a pinned test/type/smoke. A formal
  re-run remains available on demand.
- **No behaviour eval for the new channel** in `evals/evals.json` (routing/injection canaries for
  context-read phrasing) — candidate follow-up.
- **CM6 selection-tooltip** (floating button on selection → copy-selection-ref) — separate UX
  mini-feature, unscheduled.
- **Plugin runtime remains untested by an executable harness** (TASK 070 residual, unchanged): type
  gate + contract tests cover the wrapper side; plugin logic is verified by live dogfood only.
