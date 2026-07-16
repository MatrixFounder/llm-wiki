# 2.2. Native-App Control Skill (`obsidian-cli` — TASK 029 / R-12, prompt-layer only)

**Contents**

- [2.2. Native-App Control Skill](#22-native-app-control-skill-obsidian-cli--task-029--r-12-prompt-layer-only)
  - [Component contract — four invariants](#component-contract--four-invariants)
- [2.2.1 Active-note resolution](#221-active-note-resolution-task-041--adr-008--amends-the-inv-3-f-4-footgun)
- [2.2.2 Editor-selection bridge](#222-editor-selection-bridge-task-068--the-plugin-over-eval-decision)
- [2.2.3 Mirror → gate](#223-mirror--gate-task-070--the-plugins-verification-architecture)

The component is **skill text, not code**: `skills/obsidian-cli/` (SKILL.md +
`references/{command-reference,recipes}.md` + `evals/`) symlinked into
`.claude/skills/` + `.agent/skills/`. It sits ABOVE the existing stack:

- The official `obsidian` binary (a remote control for the RUNNING desktop app; GA
  since 1.12.4) is itself the deterministic plumbing layer.
- **Decision-17 generalised**: we do not wrap a binary in Python when the binary
  already carries a stable CLI contract.
- The skill encodes routing judgment, safety policy, and coherence obligations in the
  orchestrator's prompt layer, vendor-agnostic (any LLM).

## Component contract — four invariants

**1. Routing invariant.** Route each request to its correct tool:

- knowledge/RAG → `wiki-search`/`wiki-query` FIRST (unchanged, restated verbatim in
  the skill);
- bulk ingest/index → `wiki-sync`/`wiki-reindex`/`wiki-index-upsert`;
- live-app ops (link-safe rename/move, typed properties, tasks, daily notes,
  templates, Bases queries, history restore, UX) → `obsidian` CLI;
- plain content edits → file tools (+ upsert if indexed).

App `search`/`search:context` is a complement (no BM25/stemming/citations), never the
knowledge default.

**2. Coherence invariant (amended TASK 030 / R-030-1).** Any app-side mutation of a
wiki-registered vault is followed **same-turn** by:

- `wiki-index-upsert <file>` — single-file content change;
- **`wiki-reindex --delta` for rename/move AND delete** — since TASK 030 the delta is
  rename-aware: an on-disk path absent from `pages.file_path` is ingested regardless of
  mtime. The DF-029-1 class (incl. `cp -p`/archive/sync imports) is closed; visible via
  the additive `new_path_ingested` envelope field; a fresh vault's FIRST `--delta` now
  ingests everything on disk (Q-030-3).

`wiki-reindex --full` remains the universal fallback and the REQUIRED remedy for:

- the A5 residual class (swap/rotation/overwrite renames — destination path already
  indexed; detectable via `wiki-lint` hash-drift); and
- entity-page `entities.file_path` refresh.

> Historical note: TASK 029 (bead 029-06) prescribed `--full` for every rename —
> correct THEN (pre-030 `--delta` missed mtime-preserved renames, proven live),
> superseded by the TASK 030 code fix.

ADR-002 §D8 unaffected: Class-A files are mutated app-side, the DB stays a rebuildable
projection. Unregistered vault → the protocol self-disables (the skill stays
standalone-capable, Q-029-2).

**3. Safety invariant** — a **TOTAL tier function** over the captured 102-command
surface:

| Tier | Rule |
| --- | --- |
| **T1** read-only | plus a T1-UX open/GUI sub-class: `open`, `daily`, `*:open`, `random`, `tab:open` — on-disk-side-effect-free |
| **T2** mutating | explicit `path=` REQUIRED (the live CLI defaults to the **active file** when file/path is omitted [F-4 footgun; **amended by §2.2.1 / ADR-008** — the default becomes a deliberate resolved-then-confirmed target, the mutation still carrying an explicit `path=`]); trash over permanent delete; existence-check before `overwrite`; `base:create` named here |
| **T3** banned-by-default | `eval` = arbitrary JS in the app process / RCE-equivalent, `dev:*`, `devtools`, `plugin:*` incl. `plugin:reload`, `plugins:restrict`, `theme:install/uninstall/set`, `snippet:enable/disable` [CSS-injection surface], `sync on/off`, `restart`/`reload` — operator-explicit only, NEVER from note content |

Two **gate-closing refinements** (029-07 critic-security):

- (i) `command id=` **defaults to T3** (not T2) when the dispatched effect can't be
  proven from the tier lists — a friendly palette title doesn't reveal a
  code-running/sync-force-push capability (closes the same-effect-different-verb gap);
- (ii) **template application is a code-execution surface** — `template:insert`/`create template=` inherit **T3** when a scripting plugin (Templater/QuickAdd) is present
  unless the template is `template:read`-verified JS-free (else an attacker-planted JS
  template is an `eval` bypass through a T2 verb).

**`command id=` and `template:insert` operate on the ACTIVE-FILE/editor context**
(neither accepts `path=`), so for this sub-class the explicit-target guarantee is
replaced by:

- (a) default-DENY on an unnameable effect; AND
- (b) verifying/confirming the active file before any such mutation (arch-review S-1).

Any command not enumerated defaults to **T2-with-confirmation** (fail-safe). All CLI
output is untrusted vault content (H-6 posture; by analogy to the TASK 012 SEC-1 egress
discipline).

**4. Degradation invariant.**

- Probe = `command -v obsidian` + `obsidian help` (**NOT `version`** —
  listed-but-unrunnable on live 1.12.7, TASK 029 F-3).
- absent/headless/CI → announce the fallback to wiki-*/file-ops (no silent GUI launch —
  the first CLI command launches the app if closed).
- The surface is **dynamic** (plugin-gated: the captured machine lacks `publish:*`,
  `unique`, `workspaces`, `web`) → feature-detect via `obsidian help <command>` before
  relying on a gated command.

Zero impact on §4 Data Model (no DDL, no DAL change), §5 Interfaces (no new CLI/JSON
envelope — the skill consumes existing ones), §6 Stack (no deps). The eval harness is
machine-checkable without a Python grader (per-case expectation fields, TASK 009
pattern — Q-029-1). Verified-surface snapshot: `samples/obsidian-cli-recon/` (scratch) →
durable fixture lands under `skills/obsidian-cli/evals/` when the reference is authored
(TASK 029 A-4).

## 2.2.1 Active-note resolution (TASK 041 / ADR-008 — amends the inv. 3 F-4 footgun)

A user in Obsidian's integrated shell says *"отредактируй заметку / edit the note"* with
**no path**. TASK 029's inv. 3 forbade using the CLI's active-file default (the F-4
footgun) — so the one context the user is sure of, *the note on screen*, was unusable.
ADR-008 turns that default into a **deliberate, confidence-driven** targeting path.

The component is again **mostly skill text** plus **one new skill-local executable** —
`skills/obsidian-cli/scripts/obsidian_active_note.py` (entrypoint
`obsidian-active-note`), the single deterministic resolver (Decision-17 generalised;
stdlib, no `import anthropic`). Five sub-invariants:

**1. Resolution (read-only, over the OPEN-tab set), by how the user named the target.**

- **Descriptor** ("the note about *github setup*", any language) → match the wrapper's
  **open-tab list** (path + title). A **unique** match is an **exact hit**.
- **Bare reference** ("the/this/current/open note") → the **active/focused** tab via the
  documented path-returners — `obsidian file` (no `path=` → "Show file info"; fixture
  L10 "Most commands default to the active file when file/path is omitted"), the
  active-file default on reads, the `active` flag on
  `tags`/`aliases`/`properties`/`tasks`. **`tabs` exposes only `ids` (no focus marker)**
  and `recents` is a recency heuristic — both corroborate, neither leads (Q-041-1).

The wrapper owns both modes (focused note + open-tab list) so no agent re-parses CLI
output; it returns vault-relative + absolute path + vault name.

> **Feasibility gate — RESOLVED at S0** (real 1.12.7 fixtures under
> `skills/obsidian-cli/evals/fixtures/`): `obsidian file` (no path) → parseable TSV
> `path\t<rel>` (MEDIUM solid); `obsidian tabs` → **title only** (no path/focus marker)
> → open-tab→path is two-step (`tabs` title-match + `file=<title>`). So the descriptor
> branch ships as a **TEMPERED HIGH**: no-ask only on a **unique** open-tab title match
> that resolves unambiguously; any ambiguity (none/many/duplicate) → **LOW → ASK** (the
> ambiguity guard satisfies M-1 — the candidate set is enumerated; a wrong-file mutation
> can never happen silently).

**2. Confirmation keyed to resolution CONFIDENCE, not a flat rule** (user decision +
refinement):

- **HIGH** (descriptor → unique open tab) → proceed, **no ask** (the "exact hit");
- **MEDIUM** (bare ref → active tab) → **confirm first-per-session**, then bounded trust
  on same-class ops at a consistently-resolved path;
- **LOW** (descriptor matches nothing open / multiple tabs / split-pane no focus) →
  **ASK** — "agent didn't find it" → request path / disambiguate, **never** a silent
  active-tab substitute when a *different* note was named.

Cross-cutting rules:

- Read-only never prompts; the resolved path is echoed every time.
- **destructive verbs (`delete`/`move`/`rename`/`history:restore`) always re-confirm
  regardless of confidence** (preserves T2 + E-14).
- trust is conversation state → **fail-safe reset to "confirm again" on context loss**.

**3. The mutation always carries the explicit, resolved `path=`/`vault=`** — never the
implicit default (keeps the E-11 footgun green; ADR-002 coherence needs the absolute
path: post-mutation same-turn `wiki-index-upsert --source <abs>` / `wiki-reindex --delta`, self-disabling on an unregistered vault; a focused tab in a vault ≠ the task
context surfaces as the wrapper's `vault-mismatch` exit code).

**4. Safety extended, not relaxed.**

- Resolution is driven by **live app state, never note content** (H-6).
- **auto-resolved read content is DATA** — it cannot introduce a new target, verb, or
  T2\*/T3 op (no action-escalation).
- auto-resolution **never** feeds the active-file T2\*/T3 sub-class (`command id=`,
  `template:insert`) — they stay default-DENY.
- **headless/CI → no probe, no resolve**.

**5. Vendor-agnostic (NF-1).** Identical under any LLM CLI (Claude Code / Codex / Gemini
/ pi / hermes / …): the resolver is a **plain shell executable**, the protocol is
**skill prose + shell commands**, confirmation is **plain conversational** — no vendor
SDK, tool, hook, or prompt-UI dependency; no per-vendor code path to diverge.

Wrapper contract (Q-041-4): four modes (`focused`/`tabs`/`resolve`/`match`); typed exit
codes `0` ok / `no-active-file` / `app-not-running` / `cli-absent` / `vault-mismatch` /
`ambiguous` / `headless`; JSON + plain-path output; **CI-deterministic** unit test mocks
a captured `obsidian file`/`tabs` fixture (no live app); a manual dogfood smoke confirms
the live focused-tab path.

> **Headless ordering (arch-review M-3):** the agent decides headless **from the
> environment BEFORE invoking the wrapper** (per E-13 — any obsidian subcommand, the
> wrapper's included, launches the GUI), so in a known-headless context the wrapper is
> **not called at all**; its `headless`/`app-not-running` codes are belt-and-braces,
> never the primary gate.

**Still zero impact on §4 Data Model and §6 Stack (stdlib); §5 gains ONE skill-local
resolver** (a deterministic active-file/open-tabs → path projector with its own
exit-code contract — not a wiki CLI). New evals extend the TASK 029 grader-free harness
(descriptor-HIGH-no-ask, descriptor-LOW-ask, bare-MEDIUM-confirm,
destructive-re-confirm, injection-neg ×2, headless-no-resolve);
E-09/E-10/E-11/E-13/E-14/E-15 stay green.

## 2.2.2 Editor-selection bridge (TASK 068 — the plugin-over-eval decision)

A user in Obsidian's integrated shell says *"отредактируй выделенный текст / edit the selected
text"*. Neither the official `obsidian` CLI (no `selection`/`cursor` command) nor §2.2.1's
active-note resolver (which resolves *which file* is open, not *what is selected inside* it)
reaches the live editor selection. The one channel that DOES reach it, `obsidian eval`, is
already T3-banned by §2.2's invariant 3 (full Node RCE) — so this capability could not simply
extend the existing surface without either bypassing that ban or inventing a new one.

**The decision: a ~110-line local Obsidian plugin, `agent-bridge`, not `eval`.** Two plain-
`callback` commands (`export-selection` / `apply-edit`, NOT `editorCallback` — reading
`activeEditor` inside the callback body is strictly more robust than gating on an
editor-focused callback signature) dispatched via `obsidian command id=agent-bridge:<id>` — a
**T2** verb: selection I/O plus a handful of `.obsidian/`-scoped JSON files, no process/network
access, a strict subset of `eval`'s full RCE blast radius. Every rejected alternative (a
Shell-commands plugin, Templater, the Local REST API, `dev:cdp`, `workspace.json`
persistence, the URI scheme) was independently disqualifying (TASK.md §3). `eval` stays T3
exactly as already classified: a manual, operator-explicit fallback for machines that haven't
installed the plugin — the Python wrapper this task ships (`obsidian_selection.py`) **never
emits `eval`** under any code path, keeping the T3 decision with the human operator and
preserving the skill's E-09 injection canary after this task (E-27/E-28 extend it to the
selection use case specifically).

**The `command id=` proven-effect carve-out (R-068-8).** §2.2's invariant 3 already makes
`command id=…` default-T3 "whenever the effect cannot be proven from the tier lists" — a
friendly palette title doesn't reveal a code-running capability. Classifying
`agent-bridge:export-selection`/`:apply-edit` as T2 is legitimate ONLY because SKILL.md now
enumerates their exact effects; the SKILL.md edit therefore **names them as explicit
exceptions** to that default-DENY rule rather than silently loosening it — this is precisely
the H-5-pinned diff class the skill-contract-integrity mechanism (TASK 067) exists to make
reviewable: `config/skill-integrity.sha256` is re-pinned in the same change as the SKILL.md
edit, and `tests/test_h5_skill_integrity.py` goes RED on any edit that isn't.

**The channel-independent write-back contract.** Both the plugin and a manual `eval`
fallback must honour the same optimistic-concurrency guard, atomically, inside ONE program:
(a) `activeEditor.file.path === <path read>`, (b) `editor.getRange(from,to) === <exact
baseline text captured at read time>`, (c) `somethingSelected() === true` — refuse on ANY
mismatch (a read in one invocation and a write in a separate later one is a forbidden TOCTOU
window unless this triple guard re-validates at write time, which it always must).
`editor.replaceRange`, never `vault.modify` or a raw disk write, keeps the mutation on
Obsidian's own undo stack; `await activeEditor.save()` runs before the plugin reports
`ok:true`, since `replaceRange` alone only touches the in-memory buffer. The payload (path,
expected-baseline text, replacement text) is base64-encoded in BOTH directions — never
string-interpolated raw into JS/JSON — immune to both string-boundary injection and the CLI's
own `\n`/`\t` argument mangling; the plugin decodes with `Uint8Array`/`TextDecoder`, never bare
`atob` (which mangles non-Latin-1 text, e.g. Cyrillic). Every outcome (success or refusal) is
mirrored to `.obsidian/agent-result.json` carrying a caller-minted `nonce`, so the wrapper's
bounded poll (`_await_result`) can tell THIS dispatch's result apart from a stale one left over
from a prior invocation (`obsidian command id=…` is fire-and-return, so a naive re-read of the
result file would otherwise risk accepting a leftover success). Success is detected by the
result's **shape** (`ok===true`), never by exit code alone — a thrown-in-`eval` error prints
`Error: …` and still exits 0, exactly the failure mode this design avoids by routing through
the plugin instead.

**The Decision-17 wrapper, `obsidian_selection.py`.** Stdlib-only, no `import anthropic`/`from
anthropic`, a single monkeypatched `_run_obsidian` seam (mirroring `obsidian_active_note.py`);
subcommands `read`/`apply` (or `--from-json`, the ARG_MAX escape valve); feature-detects the
plugin (`obsidian commands` scan for the `agent-bridge:` prefix) BEFORE ever dispatching;
plugin-absent is always a typed exit 9, never a silent fallback. Typed exit codes extend the
resolver's scheme (`0 ok · 2 usage/payload-too-large · 3 no-selection · 4 app-not-running ·
5 cli-absent · 6 vault-mismatch · 7 guard-refused · 8 headless · 9 plugin-absent`). A successful
`apply` envelope carries a `coherence` dispatch marker (`wiki-index-upsert --vault <vid>
--source <ABS path>`, or `{"skipped":"vault-not-registered"}`) — run only after the wrapper
observes `ok:true`, never speculatively, per §2's coherence invariant.

**Security tiers + confirmation policy (R-068-9)** extend §2.2's Safety invariant, not replace
it: `selection:read` = T2-read, MEDIUM confidence (confirm first-per-session, then trust;
`somethingSelected()===false` is always an ASK) — the same HIGH/MEDIUM/LOW model §2.2.1
established for active-note resolution. `selection:replace` = T2-mutating, confidence-gated:
no-ask write-back only when the transform verb came from the user's OWN turn (never
content-sourced — E-20/E-21 stays absolute), the write-back guard triple passes, per-file
session trust already holds, and the write uses `replaceRange`; a whole-document/large-delete
replace re-confirms with character counts even under established trust, keyed to blast radius
exactly like §2.2.1's folder-vs-file asymmetry. The selection **body** is untrusted content
(H-6), exactly like a note body or search hit elsewhere in this skill.

**The honest residual (restated 2026-07-16 — the original wording claimed more than was proven).**
The gate on the plugin's JS is weaker than "`tsc` + inspection" implies. Verified:

- **`main.js` is not type-checked at all.** `tsconfig.json` is `noEmit: true` with `include:
  ["main.ts", "obsidian.d.ts"]`. The committed `main.js` — a hand-authored CommonJS mirror (340
  lines against `main.ts`'s 404) and **the only file Obsidian executes** — is outside it. The manual
  inspection read `main.ts` too.
- **Nothing runs `tsc` automatically** — no CI, no pytest, no script; it is a hand-typed `npx tsc
  --noEmit` that no gate will ever repeat.
- **The declarations it checks against are hand-written.** `package.json` carries `typescript` only;
  there is **no `obsidian` package**. R-068-1's own verification reads *"`main.ts` type-checks
  against **upstream** `obsidian.d.ts`"* — the requirement was closed against a hand-authored file,
  which is exactly where the fabricated `save()` (★ below) lived.

⇒ The shipped artifact's only real gate is a live dogfood. The Python fixtures simulate the plugin's
*output* (pre-seeded `agent-result.json` per degradation rung), never its internal logic. Tracked as
**OQ2** (plugin README §"Rebuild discipline"), scheduled for **TASK 070**: a real `obsidian`
devDependency + an `esbuild`-generated `main.js` + a byte-identity drift gate — the same anchor trick
the karpathy layout already uses.

★ **A test runtime is not the cure, and would look like one.** A hand-written fake (`{file, editor,
save: jest.fn()}`) would be authored from the *same wrong model of the API* that produced the
fabricated type: the test passes, the bug survives, and now a green check stands behind it. **A fake
mirrors your beliefs exactly as vendored types do** — the root cause is *no contact with the real
API*, not *no tests*. Tests over the guard ladder are worth writing **after** TASK 070, not before.

**OQ1 — what the dogfoods actually proved.** The `callback` **fires** while OS focus sits in the
integrated terminal: proven 2026-07-15. It did **not** read the real selection then — that run was
launched from an *external* shell, where the note stays Obsidian's active leaf, so it never
exercised the real case; from the integrated terminal `activeEditor` is null and every command
returned `no-editor`. The selection read is proven only **after** the `recent-editor` fallback
(2026-07-16 dogfood) — see the editor-resolution correction below.

**Residual ledger, as of 2026-07-16.** Of the carried-forward items, **one dissolved on inspection
and one got worse** — the concurrency entry was recorded here as "fail-safe", which review proved
false. Recording *why* in each direction, because a wrong ledger sends the next reader off to build
the wrong thing — or past a real one:

| Item | Status |
|---|---|
| Popout windows get no persist highlight | **Real → scheduled in TASK 070 (R-070-6); see §2.2.3.** `main.ts:198-200` appends the `<style>` to the bare `document.head` (main window); a popout owns its own `document`. ⚠️ **This row's earlier "the fix needs an `on("window-open", …)` overload" is WRONG and is kept struck-through rather than deleted, because it did real damage:** it was reasoned from the vendored fiction, whose `EditorView` declared only `hasFocus` + `state` — **`baseTheme` was absent**. TASK 070's first draft duly prescribed ~30 lines of `window-open` plumbing (its C-2) by reading this row as a decision. The real fix is **one line**: `EditorView.baseTheme`, letting CM6 mount the CSS per view root (dedup structural, cleanup free). A ledger entry written from a fiction propagates the fiction — which is the whole thesis of §2.2.3. |
| `export-selection` has no size cap while `apply` does | **Not a defect — the asymmetry is misread.** `apply`'s `_MAX_B64_LEN` (512 KiB) is an **ARG_MAX guard on inline argv**, deliberately bypassed by `--from-json`. `export` has no argv in its path (the plugin writes a file, the wrapper reads it), so there is nothing to mirror; copying the constant would cargo-cult a guard whose reason does not apply. |
| Concurrent dispatch is unguarded | **Real on `read`; fail-safe on `apply`.** ⚠️ *This row's first draft claimed "diagnostics-only" — false, and caught in review. Split the paths.* **`apply` IS fail-safe:** GUARD 1/2/3 validate every payload against the *live* selection, so a clobbered `agent-edit.json` can only land its own author's intended edit (a cross-file clobber trips GUARD 1 `path-mismatch`), and a losing agent times out. **`read` is NOT:** the nonce is matched on `agent-result.json` (`_await_result`), but `agent-selection.json` is then read **unchecked** (`obsidian_selection.py:390`) — a second dispatch landing between those two steps hands agent A agent B's path and note text under `ok:true`, which then chains into a *guard-passing* write against a selection A was never given. The plugin already writes the nonce into that payload (`main.ts:302`, `main.js:246`); the wrapper reads 8 fields from it and compares none of them — **a guard field written and never read**. The fix is a one-line nonce comparison, **not** a lock file → **TASK 070**. Test gap that let this through: `tests/test_obsidian_selection.py` pins the *sequential* stale-nonce case only; the concurrent clobber is untested. |
| **OQ3** — cross-machine plugin availability | Unchanged: depends on whether the vault syncs `.obsidian/plugins/` at all (many git/iCloud setups exclude `.obsidian/`) — a known rather than surprising failure mode. |
| **OQ5** — the ARG_MAX ceiling | **Escape valve shipped**, contrary to the earlier "deferred" note: `--from-json` (`obsidian_selection.py:351`) takes a file and is not subject to the cap. What stays unmeasured is only where a realistic selection sits against macOS's ~1 MB whole-argument limit; the 512 KiB guard fails loud rather than truncating. |

Zero impact on §4 Data Model (no DDL, no DAL change), §5 Interfaces (a new script contract, no
new wiki CLI/JSON envelope), §6 Stack (stdlib Python + one dev-only TypeScript devDependency
scoped to the plugin's own type-check harness, never a runtime dependency of the vault — "scoped",
not "gated": see the residual below for what that type-check does and does not prove). New
evals extend the harness (E-27 — an `eval`-injection refusal for the selection use case, E-09
sibling; E-28 — a second-`code=`-argument attacker note, ground-truth fact #5); E-09/E-20/E-21
stay green.

**The editor-resolution correction (2026-07-16 dogfood) — the design's own premise was unmet.**
`app.workspace.activeEditor` is **null** whenever the active leaf is not a markdown editor — and
Obsidian's **integrated terminal is a leaf**, so it is null in exactly the scenario this component
exists for (an agent typing in that terminal). Live-verified: `activeLeafType:
"terminal:terminal"`, `activeEditor: null`, while the note's editor still held the selection. The
original OQ1 verification was run from an EXTERNAL shell — where the note remains Obsidian's active
leaf — and therefore never exercised the real case. §2.2.1's resolver has carried a `recent-open`
fallback for precisely this reason; the plugin now mirrors it: remember the last active markdown
editor (`active-leaf-change` + `onLayoutReady`, invalidated by an identity check against the live
leaf list when its leaf detaches) and resolve through it, tagging the envelope `source:
"active" | "recent-editor"` so a fallback resolve is visible, never silent (MEDIUM confidence,
same discipline as §2.2.1).

**Write-back guards, as shipped.** `somethingSelected` → **saveable-view** (`instanceof
MarkdownView`, checked BEFORE mutating: `save()` is inherited from `TextFileView`, it is *not* on
`MarkdownFileInfo`) → **GUARD 1** path → **GUARD 2** position (`posToOffset(live) ===` the offsets
captured at read time; REQUIRED) → **GUARD 3** content (`getRange === expect`). GUARD 2 exists
because content alone is not a guard: an identical string re-selected elsewhere in the same file
satisfies GUARD 3, and the wrong occurrence would be replaced silently. GUARD 3 remains because
offsets can survive while the text under them changes. Coordinates always come from the LIVE
selection; the payload's offsets are used to *compare*, never as the replace coordinates. The
mutate→save→mirror tail is wrapped so it can never leave the buffer edited with no result mirrored
(typed `save-failed`), and the wrapper cleans up the `.obsidian/agent-*.json` exchange files —
`agent-selection.json` holds note text in plaintext inside a directory Sync/git/iCloud replicate.

★ **Architectural lesson, recorded because it outlives this component:** hand-vendored API types
are a **mirror, not a gate** — `tsc` confirms whatever you assert. This plugin's `obsidian.d.ts`
declared a `save()` that the real `MarkdownFileInfo` does not have, so the type-check "passed"
against a fiction while the call could `TypeError` *after* the buffer was mutated. A precisely-typed
fabrication defeats the gate harder than an `any` would, because it looks verified. Vendored
declarations must be copied from the real package and the code narrowed to fit them — never the
reverse. (Found by the /vdd-adversarial pass; the fix is proven by a negative control — removing
the narrowing makes `tsc` fail.)

**Delivery (the "built ≠ agent-usable" correction, 2026-07-15 dogfood).** A capability an agent
must invoke on its own is only usable if it is *addressable* and *discoverable*, symmetric with
§2.2.1's `obsidian-active-note` resolver. So the wrapper ships the same delivery trio: a `bin/`
launcher (`bin/obsidian-selection`, installed on PATH at `~/.local/bin/`) so a bare
`obsidian-selection read`/`apply` command exists; **CWD→vault auto-detection** (`detect_vault_from_cwd`
+ a `--no-detect-vault` escape, ported from the resolver) so a call from Obsidian's integrated
terminal targets *that* vault with no `--vault`; and a `SKILL.md` `description`/Triggers surface
that names the selection use case (`"what text is selected"`, `"выделенный текст"`) so an agent
routes to it. The initial ship had the working channel but none of the three — a weak agent could
not find or address it (surfaced only by the live dogfood, not the unit gates).

---

## 2.2.3 Mirror → gate (TASK 070 — the plugin's verification architecture)

**The structural defect §2.2.2 recorded is two canonical artifacts for one truth.** `main.ts`
(reviewed, type-checked) and a hand-authored `main.js` (executed, checked by nothing), kept in
agreement by discipline. A hand-maintained "mirror" of a canonical source is not a mirror — it is a
**second canon that drifts**, and the drift is invisible precisely where it matters, because the
checked file is not the run file.

> **Not a Class A/B/C violation — the earlier draft of this paragraph said so and was wrong.**
> ADR-002 §D8's classes are **vault-scoped by definition** ("Vault-only"; "Vault-canonical +
> DB-mirrored"), and `main.js` satisfies no clause of Class B: no vault representation, no DB
> mirror, no conflict rule, and `wiki-reindex --full` does not rebuild it — the plugin is outside
> the index entirely (see the "does NOT change" paragraph below, which the frame contradicted).
> Under the ADR's own TASK-012 amendment, repo-bundled code/config like `layouts/*.yaml` is
> **Class C operational**; `main.ts`/`main.js` are Class C. Recorded rather than quietly deleted
> because an appealing-but-unratified frame in a living doc gets cited as settled by the next
> reader — this document's whole subject.

What IS earned is the **analogy**, and ADR-002 names it directly: build-and-compare is to `main.js`
what **`wiki-reindex --full`** is to the index, and the byte-identity anchor is the same one the
**karpathy layout** already stands on — the ADR's *"standing §D8 rebuildability test"*. Generation
plus that test is what makes discipline unnecessary: `main.ts` + the real pinned `obsidian` package
are the source; `main.js` becomes a **build product** nobody is asked to maintain. Precisely: hand
lockstep is no longer *asked for*, and **the suite goes RED when someone runs it** — with no CI and
no hooks (see L2 below), the ladder still fires only when a human runs `pytest`. "Nobody can drift"
would overclaim at the trigger layer; "drift is caught the moment anyone looks" is what is true.

Three fictions sat on top of that:

| Fiction | Reality |
|---|---|
| `obsidian.d.ts` — hand-written (204 lines) | the real package is 7,517 lines; the vendored file declared a `save()`, a `getMode?()`, and an entire `MarkdownLeaf` type **that do not exist**, invented so the code would compile |
| `tsc` checks the plugin | `include: ["main.ts"]`, no `allowJs` ⇒ **structurally incapable** of reporting the executed file |
| `node -e "require('./main.js')"` tests it | `main.js:19-29` substitutes inert stand-ins (`Plugin = class {}`) ⇒ proves the file **parses, with fakes** |

**TASK 070 collapses all three into one real dependency and demotes `main.js` to Class B.**
`main.ts` + the real pinned `obsidian` package are canonical; `main.js` becomes a **build product**;
the drift gate is its rebuildability check — the same architectural role `wiki-reindex --full` plays
for the index. Nothing is "kept in lockstep by hand" any more, because nothing *can* be.

**The receipt is the repo's existing pin-and-receipt idiom, second instance — plus one strengthening.**
`scripts/build_agent_bridge.py` + `config/agent-bridge-build.json` mirror `scripts/pin_skill_integrity.py`
+ `config/skill-integrity.sha256` (H-5): a repo-owned manifest of hashes, a `--write` that re-pins an
APPROVED change, and a test that goes RED on any un-re-pinned edit. Reusing the idiom rather than
inventing one is the point — the review surface is a manifest diff either way. The **strengthening**
H-5 does not have: `--write` is **gated on `tsc`**. H-5's `--write` rewrites its manifest
unconditionally and answers hand-editing with prose (*"Do NOT hand-edit a hash — the diff is meant to
be reviewed, not authored"*). That matters for how strongly the L0 below may be stated.

**The gate ladder, and why each rung exists** (a rung that cannot fail is not a rung):

- **L0 — hash pin, zero toolchain.** Pins **both** `main.ts` and `main.js`. Runs anywhere, so a skip
  cannot hide drift. *Cannot* catch a hand-edited `main.js` that was also re-pinned.
- **L1 — byte compare, needs node.** Rebuilds and compares. Catches exactly L0's blind spot.
- **L2 — `WIKI_STRICT_PLUGIN_BUILD=1`.** Skip becomes failure. The skip predicate is
  **toolchain-absence only** and **per-tool** — never one shared `toolchain_present()`, or the tsc
  gate falls silent when *esbuild* is missing. Never `except Exception: skip`, which would convert
  the drift being hunted into a green.
  > ⚠️ **L2 is LATENT, and saying otherwise would be this document's own failure mode.** The design
  > it comes from says "CI sets it" — **there is no CI.** Verified 2026-07-16: no `.github/`, no
  > Makefile/justfile/tox/nox, no `.pre-commit-config.yaml`, no active git hooks. (§10 Deployment's
  > claim of a *"CI/CD pipeline (pytest + mypy --strict on PR)"* is **false** and predates this
  > check — filed, not silently patched here.) The identical situation already exists for H-5:
  > `WIKI_STRICT_SKILL_INTEGRITY` is set **only by its own tests' monkeypatch**, by nothing else.
  > So L2 is a rung built for a CI that does not exist yet — real, but firing for nobody today.
  > **L0 is therefore what actually carries the non-vacuity guarantee**, which is exactly what it
  > was designed for; L2 is upside if a CI ever lands, not a layer to count today.

**★ Byte-green ≠ type-correct — the gate needs both halves.** esbuild does not typecheck: it emits
12,191 valid-looking bytes from a `main.ts` that `tsc` rejects with 3 errors. So generation alone
would have produced a *new* vacuous green (edit → rebuild → re-pin → all green → type errors
shipped). `tsc --noEmit` therefore runs **in pytest**, its compiler is pinned exact and receipted
like esbuild's, and **`--write` refuses to re-pin on a type error** — which is also the only way the
type gate gets an L0, since you cannot type-check without a type-checker: a receipt whose `main.ts`
hash still matches means "the last re-pin passed `tsc`".

> **Stated precisely, because the L0 claim is the load-bearing one.** That inference is
> **mechanism + review**, not mechanism alone: the receipt is a text file, and `--write` is the
> *sanctioned* path to it, not the *only* one — exactly the concession H-5 already makes in prose.
> Two preconditions it silently needs, both of which Planning must land or the claim is false for
> the shipped state: **(a) `--write` must HARD-FAIL when `tsc` is absent, never skip** — a skip
> there is the same "gate silenced by a missing tool" death the pytest rung guards against,
> relocated to the single site the whole L0 rests on; and **(b) the final pin must be minted under
> the live gate** — a receipt written before `--write` was tsc-gated matches a `main.ts` that was
> never type-checked. The tsc *version* is receipted too, so reverting `main.ts` without the
> lockfile is detectable rather than silently green.

**★ Determinism is a precondition, not a nicety.** A byte-identity anchor over non-deterministic
output is theatre. esbuild is deterministic *given a fixed cwd* — it stamps the entry path into the
output, so the build **must** run with `cwd=PLUGIN_DIR` and a relative entry (`// main.ts` →
`05d906d4…`; an absolute entry from elsewhere → `3b3a3645…`). This is the same byte-identity
discipline the karpathy layout already anchors on.

**★ The design principle the fixes converge on: prefer unrepresentable over guarded.** The preview
fail-open is not re-guarded — the resolution is *typed* as `MarkdownView`, so the fabricated
`getMode?.()` call has nowhere to live, and all 3 type errors die with **zero casts**. (A fix needing
a cast is fighting the API; a fix that deletes casts is agreeing with it.) Likewise the popout CSS is
not chased across windows: `EditorView.baseTheme` makes CM6 mount it per view root, so
double-injection is structurally impossible and cleanup is `registerEditorExtension`'s job — one line
replacing thirty and their four failure modes. The one place a guard is irreducible (`--external`,
whose omission silently ships a second CM6 instance and a ViewPlugin that never draws) keeps an
explicit test, because there the catastrophe **is** representable.

**What this does NOT change.** No DDL (`user_version` 7); no `import anthropic` (Decision-17); the DB,
DAL and every `wiki-*` CLI are untouched — the plugin is outside the index entirely. The T2
`command id=agent-bridge:…` channel and the T3 `eval` ban (§2.2.2) are unchanged, and
`unsupported-view` is an **additive** refusal reason.

**What it DOES change — the vault threat model is unchanged; the dev-side one is not.** Saying "the
threat model is unchanged" would be the wrong sentence in a repo that hash-pins its own prose (H-5)
and treats retrieved bytes as untrusted (H-6). This plugin's `package.json` is the repo's **only** npm
manifest, so its tree *is* the repo's entire npm supply-chain surface, and TASK 070 grows it from 1
direct dependency to 3 (14 dirs on disk). Concretely: **`esbuild` runs `postinstall: node install.js`**
— install-time code execution — and pulls a **platform-native binary** (`@esbuild/darwin-arm64`), so
the tree differs per machine. Mitigated, not eliminated: every dep is **exact-pinned**, `package-lock.json`
carries integrity hashes, and nothing is installed on a user's machine — but the surface is now
stated rather than assumed.

**Vault-side, "dev-only" is a mechanism, not an assertion** — two real ones: `manifest.json` means
Obsidian executes `main.js` alone and never `node_modules/`; `.gitignore` excludes `node_modules/`,
so a clean checkout has no toolchain to copy. The weak link is **procedure**: the README's install
step says "copy this whole folder". R-070-8 rewrites it to enumerate `manifest.json` + `main.js`,
which is what turns the claim into a mechanism.

**Carried honestly (see TASK 070 §4):** the read-path race is **narrowed, not closed** (OQ-070-1);
`minAppVersion` enforcement is documented but **unobserved** (OQ-070-3); `instanceof` across window
realms is **unverified** and closed by dogfood, not argument (OQ-070-4); the `omission-driven` audit
lens **died and has already cost us once** — it hid `EditorView.baseTheme`, which is why the first
draft of the popout requirement prescribed thirty lines of the wrong thing (OQ-070-5).
