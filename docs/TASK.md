# TASK 068 — Obsidian editor-selection bridge: read + safe edit of the live editor selection

## 0. Meta Information

| | |
|---|---|
| **Task ID** | 068 |
| **Slug** | obsidian-selection-bridge |
| **Extends** | `skills/obsidian-cli/SKILL.md` (T1/T2/T3 safety tiers, "Active-note resolution" HIGH/MEDIUM/LOW model, Coherence protocol, Script Contract) — TASK 041/ADR-008's sibling script |
| **Input** | `docs/_scratch/task-068-design-brief.md` — a LIVE-VERIFIED engineering design brief (probed against the user's running Obsidian 1.12+ on macOS, survived an adversarial refutation pass). Everything under its "LIVE-VERIFIED" is treated here as ground truth; everything under its "INFERRED/RESIDUAL RISKS" is carried into §14 Open Questions, not silently assumed. |
| **Type** | code (feature + security) |
| **Status** | v1 — analysis |
| **Baseline (RUN 2026-07-15, this session)** | `2930 passed, 14 skipped, 0 failed` in ~75s (full `python -m pytest -q`). ✅ The former TASK-066 red `tests/test_concept_extraction_weak_model.py::test_the_artifact_is_not_STALE` is **RESOLVED** (Haiku harness re-run per TASK 067) — the suite is **all-green**, so there is **NO carve-out** and no test is excluded (an unconditional carve-out would mask a real regression). Dev-phase gate = **0 failures AND ≥2930 passed** (all new tests are additive), `mypy --strict scripts/` clean. |

---

## 1. The problem

User's request (RU, verbatim from the brief): *"Можно ли с помощью obsidian cli сделать так, чтобы
агент, запущенный в интегрированном shell (в отдельном харнессе), видел выделенный текст в текущей
открытой заметке? Цель — давать агенту задание отредактировать выделенный текст в заметке."*

→ An agent running in the integrated terminal must be able to (a) **READ** the live editor
selection of the currently open note, and (b) be given a task to **EDIT (replace)** that selection
— safely, and keeping the SQLite wiki index coherent (ADR-002 §D8).

**Why this isn't already solved.** The official `obsidian` CLI (the surface `obsidian-cli`
already drives) has **no** `selection`/`cursor` command — confirmed by enumerating the full
`obsidian help` surface. The skill's existing `obsidian-active-note` wrapper resolves *which file*
is open (TASK 041/ADR-008); it says nothing about *what is selected inside* that file. This task
adds that missing capability without violating the skill's own T3 `eval` ban (see §3).

---

## 2. LIVE-VERIFIED ground truth (do not re-litigate — see the brief for the full probe transcript)

1. The official `obsidian` CLI has **no** `selection`/`cursor` command.
2. `obsidian eval 'code=<js>'` **does** read the live selection from the shell, even while OS
   focus is in the terminal: `app.workspace.activeEditor.editor` exposes `getSelection()`,
   `getCursor("from"/"to")`, `posToOffset()`, `listSelections()`, `getRange()`, `replaceRange()` —
   all live-demonstrated against the user's real selection.
3. The `eval` context is **full Node RCE**: `typeof app==="object"`, `require==="function"`,
   `process==="object"` all present, so `require('child_process')` is reachable. This is not a
   theoretical worst case — it is the literal, confirmed reason the skill already bans `eval` as T3.
4. `eval` awaits async results; on a thrown JS error it prints `Error: <msg>` (no `=> ` prefix) and
   **still exits 0** — exit codes are useless for failure detection inside `eval`.
5. base64 + `TextDecoder` round-trips UTF-8/Cyrillic correctly; naive `atob` mangles it. The CLI
   splits `key=value` on the **first** `=` only (padding-safe).
6. `activeEditor.save()` / `requestSave()` exist and are awaited; `replaceRange` only mutates the
   in-memory buffer until `save()` completes.
7. `obsidian command id=<plugin>:<cmd>` dispatches **community**-plugin commands, not just core
   ones — this is the mechanism the new plugin channel rides.
8. The user's machine has **no** ready-made non-`eval` selection channel (no Templater, QuickAdd,
   Local REST API, or Shell-commands installed) — a new plugin is the only zero-RCE production
   channel available.

---

## 3. THE DECISION — production channel

**Ship a ~110-line local Obsidian plugin, `agent-bridge`**, triggered via
`obsidian command id=agent-bridge:export-selection` / `:apply-edit` — a **T2** verb (least
privilege: selection I/O + a handful of `.obsidian/`-scoped JSON files, no process/network access,
unlike `eval`'s full RCE). Commands register with a plain `callback` (not `editorCallback`) and
read `activeEditor` inside — this is strictly more robust than gating on an editor-focused
callback signature, and requires no extra fallback path.

**`eval` stays T3** exactly as the skill already classifies it: manual, operator-explicit,
per-invocation fallback for machines that haven't installed the plugin yet. The Python wrapper
this task ships (`obsidian_selection.py`) **never emits `eval`** under any code path — that keeps
the T3 decision with the human operator and preserves the skill's E-09 canary ("`obsidian eval` ==
red flag" stays true after this task).

**Rejected alternatives** (each independently disqualifying):

| Option | Why rejected |
|---|---|
| Shell-commands plugin | Persistent full-RCE surface, no staleness guard — strictly worse than the bespoke plugin. |
| Templater | `eval`-equivalent scripting (`<%* %>`/`tp.user`); not installed on this machine anyway. |
| Local REST API | No selection endpoint — verified from its own OpenAPI spec. |
| `dev:cdp` | A superset of `eval` (full Chrome DevTools Protocol). |
| `workspace.json` | Does **not** persist selection state in Obsidian 1.12+ — verified. |
| URI scheme | No read capability; opening a note via URI destroys the existing selection. |

Clipboard-loop and marker/heading conventions remain the best **zero-install** fallbacks (documented,
not shipped as code — §11).

### 3.1 Packaging decision — prebuilt `main.js` AND source `main.ts` both ship (ratifies a brief residual)

The brief flagged "prebuilt `main.js` committed vs. build-step-on-install" as an open
git-artifact tradeoff. **Decision: ship both.** `main.ts` is the reviewable source of truth (type-
checked against `obsidian.d.ts` — R-068-9) and the audit artifact for future SKILL.md-adjacent
review; a committed prebuilt `main.js` means installing the plugin requires **no Node/npm/tsc
toolchain on the user's machine** — consistent with this repo's "never `npm install -g`" /
"local `node_modules/` only" posture, and avoiding forcing a build step onto an Obsidian vault
that has no reason to own a JS toolchain. **Residual, carried to §14:** nothing currently proves
`main.js` was rebuilt from the `main.ts` that ships alongside it in the same commit (no build-hash
check) — a manual "rebuild before commit" discipline, documented in the plugin README, not a gate.

### 3.2 Multi-selection scope — primary range only (ratifies a brief residual)

Both channels (`eval` and the plugin) read `getCursor("from"/"to")` — the **primary** selection
range. `listSelections()` (multi-caret) is **not** consumed. **Decision: ratified as an explicit
scope limit**, not a defect — "rewrite this paragraph/section" is the target use case, and
multi-range replace has no well-defined single `expect`/`replacement` pair for the optimistic
concurrency guard in §5 anyway. Out of scope (§11); revisit only if a real multi-range use case
appears.

---

## 4. Use Cases

### 4.1 Read the live editor selection

- **Actors:** the agent (in the integrated terminal), the human operator (has a note open in
  Obsidian with text selected), the `agent-bridge` plugin (inside the running Obsidian process).
- **Preconditions:** Obsidian is running with the target vault open; the `obsidian` CLI is
  installed (`command -v obsidian`); the `agent-bridge` plugin is installed and enabled (feature-
  detected via `obsidian commands` scan for the `agent-bridge:` prefix); the agent is not headless.
- **Main Scenario:**
  1. Agent runs `obsidian_selection.py read` (optionally `--vault N` / `--expect-vault N`).
  2. Wrapper feature-detects the plugin (`obsidian commands` lists `agent-bridge:export-selection`).
  3. Wrapper dispatches `obsidian command id=agent-bridge:export-selection`.
  4. Plugin callback reads `app.workspace.activeEditor`, captures `{vault, path, from, to,
     fromOffset, toOffset, text, mtime}`, writes it to `.obsidian/agent-selection.json`, mirrors
     the outcome to `.obsidian/agent-result.json`.
  5. Wrapper reads both files via `app.vault.adapter`-relative paths, emits the JSON envelope
     (`--format json|path|tsv`), exits 0.
  6. Agent treats `text` as **untrusted data** (H-6) — never as instructions — and may present it
     to the user or use it as input to a transform.
- **Alternative Scenarios:** each degradation-ladder rung in §5 (`no-editor`, `vault-mismatch`,
  `preview`, `empty-selection`, `plugin-absent`) — every one exits with a typed non-zero code and a
  `reason`, never a silent empty read.
- **Postconditions:** the agent holds an explicit `{path, from, to, text}` baseline it can later
  present back to `apply` (§4.2) as the concurrency guard's `expect`.
- **Acceptance Criteria:** see RTM R-068-3/R-068-4/R-068-5/R-068-6.

### 4.2 Edit (replace) the live editor selection

- **Actors:** same as 4.1, plus the wiki index (coherence target).
- **Preconditions:** a prior `read` (4.1) produced a baseline `{path, from, to, text}`; the
  transform verb (the instruction to edit) came from the **user's own turn** — never from the
  selection's own content (E-20/E-21 action-escalation stays absolute); per-file session trust is
  either being established (first replace this session) or already held.
- **Main Scenario:**
  1. Agent computes the replacement text (the actual edit), base64-encodes it.
  2. Agent runs `obsidian_selection.py apply --path P --expect-b64 B --replacement-b64 B2`
     (or `--from-json FILE`).
  3. Wrapper writes the (still-encoded) payload to `.obsidian/agent-edit.json`, dispatches
     `obsidian command id=agent-bridge:apply-edit`.
  4. Plugin callback decodes the payload, runs **GUARD 1** (`payload.path === activeEditor.file.path`)
     and **GUARD 2** (`editor.getRange(from,to) === payload.expect`) and the `somethingSelected()`
     check; on ANY failure it writes a typed failure reason to `.obsidian/agent-result.json` and
     returns without touching the buffer.
  5. On all guards passing: `editor.replaceRange(replacement, from, to)` (undoable — lands on
     Obsidian's Cmd+Z stack), then `await activeEditor.save()`, then writes
     `.obsidian/agent-result.json = {ok:true, newLen, ...}`.
  6. Wrapper polls/reads `agent-result.json`, confirms the success shape (`ok===true`), emits its
     own envelope, exit 0.
  7. **Only after** seeing `ok:true` does the agent run the coherence step:
     `wiki-index-upsert --vault <vid> --source <ABS path>` (self-disabling if the vault isn't
     wiki-registered).
- **Alternative Scenarios:** any guard failure (`path-mismatch`, `stale-range`) → typed refusal,
  **no write**, caller re-reads (goes back to 4.1) rather than retrying blindly. Plugin absent →
  `plugin-absent`, tell the user to install it — **never** silently fall back to `eval`.
- **Postconditions:** the note's on-disk content reflects the edit (via Obsidian's own save path,
  so it participates in Obsidian's undo/sync/versioning); the wiki index is not left stale past the
  end of the turn.
- **Acceptance Criteria:** see RTM R-068-2/R-068-4/R-068-5/R-068-6/R-068-7.

---

## 5. The write-back contract (channel-independent — both the plugin and a manual `eval` fallback must honour it)

**Optimistic concurrency guard (load-bearing, atomic, inside ONE program):**
(a) `activeEditor.file.path === <path read>`, (b) `editor.getRange(from,to) === <exact baseline
text captured at read time>`, (c) `somethingSelected() === true`. Refuse on **any** mismatch. A
read in one CLI invocation and a write in a separate later one is a forbidden TOCTOU window unless
this triple guard re-validates at write time — which it always must.

`editor.replaceRange`, **never** `vault.modify`/a raw disk write — keeps the mutation on Obsidian's
own undo stack. Base64-encode the two **untrusted TEXT** payloads — the replacement text
(LLM-authored) and the expected-baseline text (selection-derived, H-6) — so no raw text is
string-interpolated into JS/JSON or placed on a subprocess argv; base64's alphabet has no
quotes/backslashes, so it is immune to both injection (a `");evil()//` payload escaping a string
boundary) and to the CLI's own `\n`/`\t` argument mangling. The `path` is **not** text: it is a
structural, app-sourced identifier re-validated by the plugin's GUARD 1 (`payload.path ===
activeEditor.file.path`); it travels as a JSON-escaped field inside `agent-edit.json`
(`json.dumps`, never on a shell command line), so base64 would add nothing — it is guarded by the
path/range re-check, not by encoding. Return a JSON status, **never throw** —
the caller detects success only by output shape (a line starting `=> ` then `JSON.ok===true`); any
`Error:`/non-`=>` line is failure, matching ground-truth fact #4 in §2 that exit codes are useless
here. `await activeEditor.save()` before reporting `ok:true` — the caller must not run
`wiki-index-upsert` until it sees that success shape, since `replaceRange` alone only touches the
in-memory buffer.

### Degradation ladder (every rung a typed `reason`, never a throw)

| Condition | Detected by | `reason` | Caller action |
|---|---|---|---|
| terminal focused / no editor | `!activeEditor` | `no-editor` | ask user to click into the note |
| wrong vault | `app.vault.getName()` mismatch | `vault-mismatch` | abort |
| reading (preview) mode | `getMode()==="preview"` | `preview` | ask user to switch to source mode |
| user switched tabs mid-flight | `file.path !==` baseline | `path-mismatch` | re-read, re-confirm |
| nothing selected | `!somethingSelected()` | `empty-selection` | ask user to select text |
| caret moved / line edited since read | `getRange !==` baseline | `stale-range` | re-read, **do NOT write** |
| plugin not installed | `commands` scan lacks `agent-bridge:` | `plugin-absent` | tell user to install — **do NOT** fall back to `eval` |
| ok | — | (`ok:true`) | `save()` already ran → run `wiki-index-upsert` |

---

## 6. Security position (extends `skills/obsidian-cli/SKILL.md`'s tier model)

- `selection:read` (via the plugin) = **T2-read**, confidence **MEDIUM** (a single-signal focused
  resolution, mapping onto the skill's existing "Active-note resolution" HIGH/MEDIUM/LOW model) →
  confirm the first time per session, then trust same-class reads for the rest of the session;
  `somethingSelected()===false` is always an **ASK**, never a silent empty result. The selection
  **body** is untrusted content (H-6) — data, never instructions, exactly like a note body or
  search hit elsewhere in this skill.
- `selection:replace` (via the plugin) = **T2 mutating, confidence-gated.** No-ask write-back only
  when **ALL** hold: (i) the transform verb came from the **user's own turn**, never derived from
  resolved/selected *content* (E-20/E-21 stays absolute); (ii) the atomic path+range+
  `somethingSelected` guard triple (§5) passes; (iii) per-file session trust is already established
  (the first replace on a given file always confirms once with a preview; subsequent same-file
  replaces proceed under that trust); (iv) the write itself uses `replaceRange` (undoable). A
  whole-document or large-delete replace **re-confirms with character counts even under
  established trust** — this is not a flat rule, it is keyed to blast radius, exactly like the
  skill's existing folder-vs-file confirmation asymmetry. Any guard mismatch, LOW confidence, or a
  content-sourced transform verb → **ABORT**, never silently downgrade to a smaller edit. Session
  trust is conversation state: on context loss it fail-safe resets to "confirm again," matching the
  skill's existing Active-note-resolution session-trust rule.
- **`command id=` reconciliation (H-5-audit-critical).** SKILL.md's existing rule makes
  `command id=…` **default-T3 / default-DENY** "whenever the effect cannot be PROVEN from this
  skill's own tier lists." Classifying `agent-bridge:export-selection`/`:apply-edit` as T2 is
  legitimate *only because* this task enumerates their exact effects in the tier table — so the
  SKILL.md edit **must name them as explicit proven-effect exceptions** to that default-T3/DENY
  rule. Without that sentence, the pinned diff reads as a silent weakening of the `command id=`
  guard — precisely the edit class H-5 exists to scrutinize (R-068-8).
- `eval` is **never** auto-dispatched by `obsidian_selection.py` under any circumstance. A note
  *asking* the agent to run `obsidian eval …` to read/edit a selection is refused regardless of
  phrasing — this is the E-09 sibling behaviour already required of the base skill, extended to
  cover the selection use case explicitly (R-068-9's new evals).

---

## 7. What ships

- **`skills/obsidian-cli/plugin/agent-bridge/`** — `main.ts` + `manifest.json`
  (`{"id":"agent-bridge","name":"Agent Bridge","minAppVersion":"1.4.0","isDesktopOnly":false,…}`) +
  a committed prebuilt `main.js` (§3.1). Two plain-`callback` commands: `export-selection` (writes
  `.obsidian/agent-selection.json` or `{ok:false, reason:"no-editor"}`) and `apply-edit` (reads
  `.obsidian/agent-edit.json`; runs GUARD 1/GUARD 2/`somethingSelected`; `replaceRange` + `save`;
  mirrors every outcome — success or refusal — to `.obsidian/agent-result.json`). **All** I/O goes
  through `app.vault.adapter` (vault-rooted; no absolute filesystem paths inside the plugin).
- **`skills/obsidian-cli/scripts/obsidian_selection.py`** — mirrors the
  `obsidian_active_note.py` contract: stdlib-only, no network, **no `import anthropic`/`from
  anthropic`**, a single monkeypatched `_run_obsidian` seam for fixture tests, `--format
  json|path|tsv`. Subcommands `read [--vault N] [--expect-vault N]` and `apply --path P
  --expect-b64 B --replacement-b64 B [--vault N]` (or `--from-json FILE`). Feature-detects the
  plugin via an `obsidian commands` scan before ever dispatching. **Drives the plugin channel
  ONLY — never emits `eval`** under any argument combination; plugin absent ⇒ typed exit 9, no
  silent fallback. Typed exit codes extend the resolver's scheme: `0 ok · 2 usage · 3 no-selection
  · 4 app-not-running · 5 cli-absent · 6 vault-mismatch · 7 guard-refused (path-mismatch/stale-range)
  · 8 headless · 9 plugin-absent`.
- **`skills/obsidian-cli/SKILL.md` edits** — Top-20/tier-table rows for `command
  id=agent-bridge:export-selection` (T2-read) and `:apply-edit` (T2-mutating, guard-gated); a
  Script Contract paragraph for `obsidian_selection.py`; a "edit the selected text" recipe (in
  `references/recipes.md` — a **stated pin-roster exclusion**, see §13); a Safety Boundaries note;
  the existing T3 `eval` row keeps its classification and gains "the only sanctioned production
  selection channel is the plugin." The edit **must also enumerate `agent-bridge:export-selection`
  / `:apply-edit` as named proven-effect exceptions** to SKILL.md's existing `command id=…`
  default-T3 / default-DENY rule — otherwise the H-5-pinned diff reads as a silent weakening of the
  `command id=` guard rather than a scoped, audited addition (R-068-8/§6). ⚠️ **`SKILL.md` is
  already H-5 hash-pinned** (TASK 067 Cycle-2 added it to the roster) — this edit **requires**
  re-pinning via `python3 scripts/pin_skill_integrity.py --write` in the same change, or
  `tests/test_h5_skill_integrity.py` goes RED (R-068-8).
- **Python fixture tests** — mocking the `_run_obsidian` seam (mirroring
  `tests/test_obsidian_active_note.py`), one fixture per degradation-ladder rung, plus a base64
  round-trip test (Cyrillic + `"` + `\d` + a literal newline) and an explicit assertion that no
  un-encoded LLM/selection text ever reaches a subprocess argument.
- **New never-relax `eval` evals** — (a) a note asking the agent to run `obsidian eval …` for a
  selection edit is refused, citing T3 (an E-09 sibling); (b) an attacker note supplying a second
  `code=` argument mimicking the legitimate template — assert the CLI/wrapper only honours the
  first `code=` (ground-truth fact #5 in §2).
- **Coherence step** — after a successful `apply` (i.e. only after seeing `ok:true`),
  `wiki-index-upsert --vault <vid> --source <ABS path>`; self-disables (and says so) if the vault
  isn't wiki-registered, per the skill's existing Coherence protocol.

---

## 8. Requirements Traceability Matrix

| ID | Requirement | Acceptance | Verification |
|---|---|---|---|
| **R-068-1** | The `agent-bridge` plugin ships as `main.ts` + `manifest.json` (+ a committed prebuilt `main.js`, §3.1). Two plain-`callback` commands only (`export-selection`, `apply-edit`) — **no** `editorCallback`. **All** I/O goes through `app.vault.adapter`, scoped under `.obsidian/` — no absolute-path or `require('fs')` access from the plugin. | A-1 | `main.ts` type-checks against upstream `obsidian.d.ts`; manual code inspection confirms no filesystem access outside `app.vault.adapter` |
| **R-068-2** | `apply-edit` runs the full optimistic-concurrency guard atomically: GUARD 1 (`payload.path === activeEditor.file.path`), GUARD 2 (`editor.getRange(from,to) === payload.expect`), and refuses if `somethingSelected()` is false. On all guards passing: `editor.replaceRange` (never `vault.modify`) then `await activeEditor.save()`. Every outcome (success or refusal) is mirrored to `.obsidian/agent-result.json`. | A-2 | fixture tests per guard (path-mismatch, stale-range, empty-selection) assert refusal + no write; a passing-guard fixture asserts `replaceRange`+`save` ordering via the recorded result shape |
| **R-068-3** | `obsidian_selection.py` is stdlib-only, no network, **no `import anthropic`/`from anthropic`**, uses a single monkeypatched `_run_obsidian` seam, supports `--format json\|path\|tsv`. Subcommands `read` and `apply` (or `--from-json`). It feature-detects the plugin by scanning `obsidian commands` output for the `agent-bridge:` prefix **before** dispatching either command. | A-3 | `tests/test_obsidian_selection.py` unit tests per subcommand + the feature-detect scan; `grep -rE "import anthropic\|from anthropic" skills/obsidian-cli/scripts/obsidian_selection.py` ⇒ no hits |
| **R-068-4** | Typed exit codes `0/2/3/4/5/6/7/8/9` exactly as specified in §7, and the JSON envelope shape (`{ok, mode, vault, path, from, to, fromOffset, toOffset, text, mtime, reason}` for `read`; `text→newLen` swap for `apply`). `obsidian_selection.py` **NEVER** emits `eval` under any code path; plugin-absent is always exit 9, never a silent `eval` fallback. | A-4 | one fixture test per exit code; a static-analysis grep asserting the string `"eval"` never appears as a dispatched subcommand argument in the script |
| **R-068-5** | base64 encodes the two **untrusted TEXT** payloads — the replacement text (LLM-authored) and the expected-baseline text (selection-derived, H-6) — before either becomes part of a CLI argument or a JSON file the plugin reads. No un-encoded LLM-authored or selection-derived text ever reaches a subprocess argument. The `path` is a structural, app-sourced identifier (re-validated by the plugin's GUARD 1), written JSON-escaped into `agent-edit.json` — never on a shell command line — so it is not base64-encoded (base64 protects untrusted text; the path is guarded by the path/range re-check). | A-5 | round-trip test over Cyrillic + `"` + `\d` + a literal newline; an assertion scanning the constructed argv/JSON for the raw (non-base64) TEXT payload, which must never appear; a malformed-base64 → typed `usage` refusal test |
| **R-068-6** | The degradation ladder (§5 table) is implemented as typed `reason` values, never a raised exception surfacing to the caller as a stack trace; success is detected by output/result **shape** (`ok===true`), never by process exit code alone (ground-truth fact #4, §2). | A-6 | one fixture per ladder rung (`no-editor`, `vault-mismatch`, `preview`, `path-mismatch`, `empty-selection`, `stale-range`, `plugin-absent`) asserting the typed reason and a clean (non-crashing) exit |
| **R-068-7** | The coherence step (`wiki-index-upsert --vault <vid> --source <ABS>`) runs **only** after the wrapper observes `ok:true` from `apply`, never speculatively; it self-disables (and states so) when the target vault is not wiki-registered, per the skill's existing Coherence protocol. | A-7 | a fixture test asserting `wiki-index-upsert` is invoked exactly once per successful `apply` and zero times on any refusal reason; a self-disable fixture on an unregistered vault |
| **R-068-8** | `skills/obsidian-cli/SKILL.md` gains: the two new command rows in the tier table/Top-20 (`export-selection` T2-read, `apply-edit` T2-mutating guard-gated), a Script Contract paragraph for `obsidian_selection.py`, an "edit the selected text" recipe in `references/recipes.md`, a Safety Boundaries note, **and an explicit carve-out naming `agent-bridge:export-selection`/`:apply-edit` as proven-effect exceptions to the existing `command id=` default-T3/default-DENY rule** (§6). Because `SKILL.md` is already H-5 hash-pinned (TASK 067), this edit is re-pinned via `python3 scripts/pin_skill_integrity.py --write` in the same change. | A-8 | manual diff review of the SKILL.md sections (incl. the recipe in `references/recipes.md` and the `command id=` carve-out); `tests/test_h5_skill_integrity.py` stays green post-re-pin |
| **R-068-9** | Security tiers + confirmation policy (§6) are documented in `SKILL.md`: `selection:read` = T2-read MEDIUM (confirm-first-then-trust per session); `selection:replace` = T2-mutating confidence-gated (session trust, `replaceRange`, blast-radius re-confirmation on whole-doc/large-delete). Selection bodies are untrusted (H-6). `eval` is never auto-dispatched for a selection task, regardless of note-content phrasing. | A-9 | the two new never-relax evals (refusal of a note asking for `eval`; the second-`code=`-argument attacker test) both pass |
| **R-068-10** | Test coverage: Python fixture tests mocking `_run_obsidian` for every ladder rung (R-068-6) + the base64 round-trip (R-068-5) + the no-un-encoded-argument assertion; the two never-relax `eval` evals (R-068-9); `main.ts` type-checks cleanly against `obsidian.d.ts` (R-068-1). `mypy --strict` is clean for the new script; the full regression suite is **0 failures AND ≥2930 passed** vs the all-green Baseline (§0) — every new test is additive, no carve-out. | A-10 | `pytest tests/ -q` run; `mypy --strict scripts/` run; diff against Baseline count |

---

## 9. Acceptance criteria

- [ ] **A-1** … **A-10** as tabulated in §8, each independently verifiable.
- [ ] **A-11** Zero DDL — `git diff sql/` empty; no schema change of any kind (this task is
      entirely Class-A markdown + plugin/script code, per ADR-002 §D8).
- [ ] **A-12** Decision-17 survives: `obsidian_selection.py` carries no `import anthropic`/`from
      anthropic`; it emits one JSON envelope + a stable exit code per invocation, exactly like its
      sibling `obsidian_active_note.py`.
- [ ] **A-13** `pytest tests/ -q` shows **0 NEW failures** vs the Baseline (§0); the count and any
      carve-outs are recorded in this file's Completion section on ship.
- [ ] **A-14** `mypy --strict scripts/` (or the equivalent path for the new script, per the
      Planner's placement decision) is clean.

---

## 10. Non-functional requirements

- **Vendor neutrality.** `obsidian_selection.py` must run under any LLM CLI (Claude Code, Codex,
  Gemini, pi, hermes, …) exactly like `obsidian_active_note.py` — stdlib-only, no vendor SDK.
- **Security.** No new code-execution surface: the plugin's blast radius is selection I/O + a
  handful of `.obsidian/`-scoped JSON files, strictly less than `eval`'s full Node RCE. Untrusted
  content (H-6) discipline applies to selection bodies exactly as it already applies to note
  bodies and CLI output elsewhere in the skill.
- **Compatibility.** `manifest.json` declares `minAppVersion: "1.4.0"` (the Obsidian plugin-API
  version, not the app's own version number — the user's app is 1.12+, well above this floor);
  `isDesktopOnly: false` is a stated default, revisit if a mobile constraint surfaces.
- **Class A/B/C layering (ADR-002 §D8).** The coherence step is the only touchpoint with the
  index; the plugin and script never write to the DB directly, and the coherence step self-
  disables on an unregistered vault rather than cargo-culting an upsert.

---

## 11. Scope decisions

**IN scope:**
- The `agent-bridge` plugin (source `main.ts` + `manifest.json` + a committed prebuilt `main.js`).
- `obsidian_selection.py` (`read`/`apply` subcommands, plugin-only, never `eval`).
- The `skills/obsidian-cli/SKILL.md` edits (§7) and the accompanying H-5 re-pin.
- Python fixture tests (one per degradation-ladder rung) + the base64/no-raw-argument tests.
- The two new never-relax `eval` evals.
- The coherence step (`wiki-index-upsert` after a successful `apply`).

**OUT of scope (or explicit Open Question — see §14):**
- **Auto-installing/enabling the plugin for the user.** This task ships the plugin source +
  written install instructions; the human installs and enables it themselves in Obsidian's
  Community Plugins settings. Recommended by the brief and ratified here — installing/enabling
  plugins is itself a T3-adjacent operation this skill's own tier model would gate.
- **The Accessibility-API (AXSelectedText) zero-keystroke read path.** Plausible but unproven
  against CodeMirror 6's contenteditable model and needs a macOS TCC (Accessibility) grant; ranked
  below both `eval` and the plugin in the brief, not pursued here.
- **Multi-range selection** (§3.2) — an explicit, ratified scope limit, not a defect.
- **The clipboard-loop and marker/heading fallback conventions** — documented as human-in-the-loop
  and headless fallbacks respectively, but **not shipped as code** in this task.
- **A cryptographic or build-hash check tying the committed `main.js` to its `main.ts` source**
  (§3.1's residual) — deferred; a documented manual-rebuild discipline substitutes for now.
- **A temp-file / `require('fs')` escape hatch for payloads near the macOS ARG_MAX ceiling** — see
  §14, a genuine open fork.

---

## 12. Prior art / consistency

This task is a direct sibling of TASK 041 / ADR-008 (`obsidian_active_note.py` — the
Active-note resolution wrapper): same packaging discipline (stdlib-only, `_run_obsidian`
monkeypatch seam, `--format json|path|tsv`, typed exit codes, fixture-driven tests against
committed fixtures, no live-app test requirement), same security posture (H-6 untrusted content,
confidence-gated confirmation keyed to blast radius, session-trust fail-safe reset). It extends,
rather than duplicates, `skills/obsidian-cli/SKILL.md`'s existing T1/T2/T3 tier model and Coherence
protocol — no new tiering vocabulary is invented. It also inherits H-5 (TASK 067): `SKILL.md` is
already a hash-pinned reasoning/safety contract, so this task's edit to it is not "just a docs
change" — it is a security-labelled manifest diff, called out explicitly in R-068-8 so it
is not the next unenumerated-surface gap.

---

## 13. Stated boundaries

- `skills/obsidian-cli/references/recipes.md` is a documented **exclusion** from the H-5 pin
  roster (TASK 067 Cycle-3: "playbooks restating the pinned discipline") — adding the new recipe
  there does **not** require a re-pin. Only the `SKILL.md` edit itself does (R-068-8).
  `references/command-reference.md` (the built-in `obsidian` CLI command catalog) is **not**
  touched by this task — `agent-bridge:*` are plugin command IDs dispatched through the existing
  general `command id=…` tiering rule in `SKILL.md`, not new entries in the CLI's own command
  table.
- The plugin's `callback` firing while OS focus sits in the integrated terminal is **INFERRED**
  from Obsidian's shipped command-dispatcher, not executed end-to-end in the brief's probe (only
  the `eval`-based `activeEditor` path was live-verified under terminal focus). This is carried as
  Open Question 1 (§14), not silently assumed to work identically.
- Cross-machine plugin availability depends on whether the vault syncs `.obsidian/plugins/` at
  all (git and iCloud commonly exclude `.obsidian/`) — carried as Open Question 3 (§14), not solved
  by this task.

---

## 14. Open Questions

None of the following block Planning or Dev from proceeding — each has either a ratified default
(stated) or a safe conservative fallback; they are carried here, verbatim in spirit, from the
design brief's "INFERRED/RESIDUAL RISKS" section, per this pipeline's anti-hallucination
discipline (uncertainty is recorded, not silently resolved).

1. **Plugin `callback` firing under integrated-terminal OS focus is INFERRED, not end-to-end
   verified** (§13). Default: proceed on the strength of Obsidian's documented command-dispatcher
   behaviour, but the Planner should schedule a **one-time manual verification** immediately after
   the plugin is first installed, before relying on it for anything but a supervised trial. (The
   `eval`-based `activeEditor` path **is** independently verified under terminal focus, so the
   underlying "the editor object is reachable while the terminal has OS focus" premise is not in
   doubt — only the specific `callback`-registration code path is unverified.)
2. **Prebuilt `main.js` vs. build-step-on-install — RATIFIED, see §3.1.** Ship both; the residual
   (no build-hash tying the two together) is accepted, not solved, in this task.
3. **Cross-machine plugin availability** (`.obsidian/plugins/agent-bridge/` travels only if the
   vault syncs plugin files — many git/iCloud setups exclude `.obsidian/`). No action in this
   task; document the caveat in the SKILL.md install instructions (part of R-068-8) so a future
   cross-machine failure is a known, not a surprising, failure mode.
4. **Multi-selection scope — RATIFIED, see §3.2.** Primary range only; an explicit limit, not an
   open fork.
5. **ARG_MAX ceiling / the temp-file escape hatch — a genuine open fork, unquantified in the
   brief.** base64 inflates payload size ~33%; macOS's whole-argument limit (~1 MB) is where a
   temp-file + `require('fs')` escape hatch would need to kick in, but nobody has measured where
   realistic selections (a paragraph to a few pages) sit relative to that ceiling. **Recommended
   default for this task: defer the temp-file escape hatch itself** (§11, out of scope), but
   R-068-4/R-068-5's implementation should fail loud with a clear, typed reason if an encoded
   payload approaches a conservative size threshold, rather than truncating or crashing silently.
   The Planner should size that threshold and decide whether it belongs in this task's Phase 1 or
   a follow-up.
6. **Auto-installing/enabling the plugin for the user — RATIFIED OUT of scope, see §11.** This
   task ships plugin source + install instructions only.

---

## 15. Completion

**SHIPPED 2026-07-15** (Phase 2 — docs/security closeout, 068-07/068-08/068-09). Baseline (§0)
was `2930 passed, 14 skipped, 0 failed`; final gate run: **`2957 passed, 14 skipped, 0 failed`**
(`python -m pytest -q`, ~74s) — **+27 new tests**, all additive, **0 NEW failures**, **no
carve-out**. `mypy --strict skills/obsidian-cli/scripts/obsidian_selection.py` clean;
`mypy --strict scripts/` unaffected (96 source files, clean). `git diff --stat sql/` empty
(A-11 — zero DDL). `grep -E "import anthropic|from anthropic"
skills/obsidian-cli/scripts/obsidian_selection.py` — no hits (A-12). `npx tsc --noEmit` from
`skills/obsidian-cli/plugin/agent-bridge/` exits 0 (R-068-1 re-affirmed post-Phase-1).
`tests/test_h5_skill_integrity.py` green post-re-pin (25 passed); `git diff
config/skill-integrity.sha256` touches exactly one line (`skills/obsidian-cli/SKILL.md`'s
hash) — `references/recipes.md` and `evals/evals.json` needed no re-pin, as designed (§13).
`python3 .agent/skills/skill-spec-validator/scripts/validate.py --mode plan docs/PLAN.md
docs/TASK.md` → "Success: All 10 requirements covered." No carve-outs of any kind.

**Phase 4 — Adversarial review CONVERGED (cycle 1, 2026-07-15).** A 4-lens adversarial gate
(security · logic · spec-completeness · test-quality) with per-finding adversarial verification
found **0 CRITICAL** (the security lens cleared the headline safety claims) and two MAJOR-labelled
items, both **FIXED and re-verified** this cycle:
- **Nonce-guard test was not genuinely pinned** (a nonce-*ignoring* wrapper passed it, because the
  stale-nonce case seeded no `agent-selection.json` so it hit exit 4 for the wrong reason —
  mutation-confirmed). Fixed by ALSO seeding a stale selection so the strengthened test now returns
  the mutation as exit 0 vs. asserted 4 (re-verified: the mutation is now caught).
- **`path` travelled un-encoded while R-068-5 + the H-5-pinned SKILL.md claimed base64 "both
  directions".** Resolved honestly: base64 is scoped to the two untrusted TEXT payloads
  (replacement + expected-baseline); `path` is a structural, GUARD-1-revalidated identifier written
  JSON-escaped into `agent-edit.json` (never on a shell command line). Corrected in the wrapper
  docstring, TASK §5/R-068-5, PLAN decision 5, and SKILL.md (re-pinned).
- MINORs also closed: plugin base64 decode now inside a try/catch (typed `bad-payload` result,
  preserving the "never throws" invariant — main.ts + main.js); `_write_json` OSError → typed
  reason; `--from-json` now **exempt** from the 512 KiB inline cap (a genuine ARG_MAX escape valve);
  `+4` tests (`--from-json` ok + cap-bypass, fail-closed unknown-reason, no-eval-when-plugin-absent);
  OQ3 cross-machine caveat added to the plugin README + SKILL.md; unused `Notice` import removed.
- Disclosed, accepted residuals (non-blocking): the plugin's JS guard *logic* has no executable
  test runtime (covered by `tsc` + inspection + the OQ1 on-install check — **OQ1 itself now
  live-proven, see below**); `agent-selection.json`'s echoed nonce is trusted by write-ordering
  (plugin writes it before the result). *(The "no PATH launcher" residual the adversarial review
  raised was subsequently CLOSED by the live dogfood — `bin/obsidian-selection` now ships on PATH;
  see below.)*

**Post-cycle gate run:** **`2961 passed, 14 skipped, 0 failed`** (+31 selection tests total),
`mypy --strict scripts/` clean (96 files), H-5 `25 passed` after the re-pin (still exactly one
changed hash line — `skills/obsidian-cli/SKILL.md`), `npx tsc --noEmit` exit 0, both spec
validators green. **CONVERGED — 0 CRITICAL, no remaining legitimate defect.**

**LIVE DOGFOOD (2026-07-15) — OQ1 PROVEN + a discoverability gap found & closed.** Installed the
plugin into `/Users/sergey/Downloads/TestVault/ObsidianNotes-Test` and drove the real channel:
`export-selection`'s `callback` **fires while OS focus is in the integrated terminal** and reads the
live selection — **OQ1 (§14.1) is now proven, not inferred** (the first call returned `no-editor`
purely because no note/selection was active at that instant; with a selection active it returned the
exact highlighted text, offsets, and path, exit 0). The `eval`-path `activeEditor` premise already
held; this proves the `command`-callback path too.
- **Discoverability gap the dogfood exposed (the adversarial review under-rated it as a NIT):** a
  weak agent (Haiku, in a separate CLI) answered "I can't see your screen" — it never *ran* the
  tool, because (a) the skill's `description`/Triggers never mentioned "selection", so it wasn't
  routed to, and (b) unlike the sibling `obsidian-active-note`, there was **no `bin/` launcher on
  PATH** and **no CWD→vault auto-detection**, so the tool was unreachable/unaddressable. Closed:
  added `bin/obsidian-selection` (installed at `~/.local/bin/obsidian-selection`, mirroring the
  sibling), ported `detect_vault_from_cwd` + a `--no-detect-vault` escape (bare `obsidian-selection
  read` from a vault terminal now targets THAT vault — no `--vault` needed), and expanded the skill
  `description`/Triggers to advertise the selection use case (`"what text is selected"`,
  `"выделенный текст"`, `obsidian-selection read/apply`) — re-pinned. **Verified live:** bare
  `obsidian-selection read` from inside the TestVault → `ok:true` with the real Cyrillic selection.
- **Final gate:** **`2964 passed, 14 skipped, 0 failed`** (+34 selection tests), `mypy --strict`
  clean, H-5 `25 passed` (one hash line), validators green.
