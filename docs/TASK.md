# TASK 070 — Replace the plugin's mirror with a gate: real types, generated `main.js`, drift anchor

## 0. Meta Information

| | |
|---|---|
| **Task ID** | 070 |
| **Slug** | agent-bridge-mirror-to-gate |
| **Type** | code (correctness + build/verification infrastructure) |
| **Status** | **v2** — revised after a BLOCKING task-review (3 CRITICAL + 9 MAJOR). See §8. |
| **Predecessor** | TASK 069 (`docs/tasks/task-069-residual-ledger-correction.md`) — recorded these defects; this closes them. Closes **OQ2** (plugin README §"Rebuild discipline"). |
| **Input** | A 122-claim audit of the hand-vendored `obsidian.d.ts` against real `obsidian@1.12.3` + `@codemirror/{state,view}` (9 lenses, adversarial verification, ~4.5M tokens) + 6 design decisions. Artefacts: `confirmed.json` / `refuted.json` / `design-*.md` in the session scratchpad. Every claim below cites `file:line` or is marked **UNVERIFIED**. |
| **Baseline** | `2968 passed, 14 skipped, 0 failed` @ `a8f7a70`. `tests/test_obsidian_selection.py` is at **40** (was 38 — see §6). Dev gate = **0 failures AND ≥2968 passed**, `mypy --strict scripts/` clean. |

---

## 1. The problem

TASK 069 established that **the shipped artifact has no gate at all**. At baseline `a8f7a70`:

- `tsconfig.json` is `noEmit: true`, `include: ["main.ts", "obsidian.d.ts"]` — **`main.js`, the only file Obsidian executes, is type-checked by nothing** (no `allowJs`; tsc is *structurally incapable* of reporting it). *(The working tree is mid-task and now reads `include: ["main.ts"]`; same substance.)*
- **Nothing runs `tsc` automatically** — no CI, no pytest, no script, no hook.
- The declarations it checked against were **hand-written**. R-068-1's own verification claims *"`main.ts` type-checks against **upstream** `obsidian.d.ts`"* (`docs/tasks/task-068-…:335`) — there was no `obsidian` package.
- The plugin's one "executable test" (`node -e "require('./main.js')"`, README TC-03) is **vacuous**: `main.js:19-29` wraps `require("obsidian")` in a try/catch substituting inert stand-ins (`Plugin = class {}`), so it proves the file *parses* — with fake classes.

**Installing the real package immediately falsified the fiction.** Exactly 3 errors, **2 of them in safety guards**:

```
main.ts(161,74) TS2367  'View' and 'MarkdownFileInfo' have no overlap
main.ts(277,12) TS2339  Property 'getMode' does not exist on type 'MarkdownFileInfo'
main.ts(344,12) TS2339  Property 'getMode' does not exist on type 'MarkdownFileInfo'
```

The fabricated `save()` (TASK 068) was **not an anomaly — it was the pattern**.

## 2. What the audit found

**Two HIGH defects.** *(The earlier "122 censused → 66 accurate" statistic is **withdrawn** — see §8 M-4: it counted claim-verdicts, not distinct declarations, and its own artifact lists `MarkdownLeaf` and the `getMode` guard as "accurate". A number that looked like it measured X while measuring Y — inside the task about exactly that.)*

| # | HIGH defect | Evidence |
|---|---|---|
| **H1** | **`getMode` fabricated onto `MarkdownFileInfo`.** Real `MarkdownFileInfo` = `{app; get file(); editor?}` extends `HoverParent` — **no `getMode`** (:3820-3834). `getMode(): MarkdownViewModeType` lives on `MarkdownView` (:4080). Marking it **optional** licensed `?.()`. **The fail-open is `export`-path-only**: `applyEdit`'s later `instanceof MarkdownView` (`main.js:296`) backstops it with `no-saveable-view` *before* any mutation. `exportSelection` (`main.js:222`) has **no backstop**. | **The real harm** (from the audit, restored): for a canvas/hover-popover embedded editor the offsets index the **EMBEDDED** document while `file.path` names the **container** file — *"a coherent-looking but wrong reference that a downstream consumer cannot detect."* API doc :2660: *"returns a `MarkdownFileInfo`, **which may be a `MarkdownView` but not necessarily**"*. `MarkdownEditView` (:3772-3811) implements it with no `getMode`, no `save`, **no `editor`**. |
| **H2** | **`main.js` is outside every gate**, and **nothing runs `tsc`** (§1). | `tsconfig.include`; `test_obsidian_selection.py:237` — the preview test **seeds `read-preview.result.json`**, never runs the plugin. |

**Fabrications load-bearing for the fix:**

- **`interface MarkdownLeaf { view: MarkdownView }` was invented so `leaf.view === info` would compile.** `MarkdownLeaf` occurs **zero times** in the real package. Real: `getLeavesOfType(viewType: string): WorkspaceLeaf[]` (:7050); `WorkspaceLeaf.view: View` (:7282) — carrying *"Do not attempt to cast this to your custom `View` without first checking `instanceof`."* The fiction erased the type **and its warning**. Runtime works today; **the type system was switched off**.
- **`MarkdownView.getMode(): string`** widened the real union `MarkdownViewModeType = 'source'|'preview'` (:4106).
- **`EditorView` declared only `hasFocus` + `state`** (`VENDORED:175-178`) — **`baseTheme` absent**. This one hid the entire popout fix (§8 M-7).

**Three bugs nobody was looking for**, surfaced by the preview-guard design:

- **Silent wrong-target.** Narrowing *inside* `resolveEditor`'s active branch and falling through to `lastEditor` makes a non-`MarkdownView` active editor silently retarget a **different note** — and every apply guard passes, because they check the *live* selection. The refusal must happen **at** the active editor.
- **`rememberEditor` is corrupted by the same fabrication** (`main.ts:131`). It stores *any* `MarkdownFileInfo`, but `isAttached` proves liveness via `leaf.view === info` where `leaf.view` is a `MarkdownView` — so a non-`MarkdownView` memory can **never** pass, and `main.ts:149` then **nulls out a good remembered `MarkdownView`**. A transient canvas focus evicts the note the agent could have acted on.
- **`copy-selection-ref` is a third consumer** — the census is **3**, not 2. It has **no** preview guard today, so it copies the stale source-mode selection under a confident `@path#L12-14` label. R-070-5 changes this **human-facing hotkey**'s behaviour → must be in the dogfood (§7).

## 3. Requirements (RTM)

| ID | Requirement | MVP | Verification |
|---|---|---|---|
| **R-070-1** | **Real types replace the fiction.** Delete `obsidian.d.ts`; depend on `obsidian@1.12.3` (exact) + real `@codemirror/{state,view}` (peer-installed). | ✅ | `obsidian.d.ts` absent; `grep -rc "declare module" skills/obsidian-cli/plugin/agent-bridge/` = 0 (**`-r`** — `grep -c` on a directory errors, so the check could neither pass nor fail as first written. Verified sound: the *only* `declare module` hit anywhere in the plugin dir, node_modules included, is the vendored fiction itself) |
| **R-070-2** | **Pin == `minAppVersion` == `1.12.3`.** Raise `manifest.json` 1.4.0 → 1.12.3 so both guards agree on one number: tsc refuses APIs above it, Obsidian refuses to load below it (:4971). **Inert as a gate until R-070-3 lands** (it gates a file Obsidian never executes) ⇒ Planning must order R-070-3 first. | ✅ | tests: pin exact (no caret) · pin == minAppVersion · lockfile == pin |
| **R-070-3** | **`main.js` is GENERATED.** esbuild `--bundle --external:obsidian --external:@codemirror/view --external:@codemirror/state --format=cjs --target=es2018 --platform=browser`, run with **`cwd=PLUGIN_DIR` + relative entry** (load-bearing: esbuild stamps the entry path as a comment — **independently reproduced**: rel `05d906d4…` vs abs `3b3a3645…`). Committed prebuilt (a vault installs with **no** Node/npm). | ✅ | **Reproducible across runs.** ⚠️ The literal `05d906d4760a035fc46e` (independently reproduced, matching the design's hash) is esbuild(**pre-fix** `main.ts`) — R-070-5/6 change `main.ts`, so **the shipped hash legitimately differs and this AC must not be read as pinning that literal**. What is pinned: two builds of the *current* `main.ts` are byte-identical, and the committed `main.js` equals them. Export shape **empirically retired**: emits `module.exports = __toCommonJS(main_exports)` + `default: () => AgentBridge` — byte-for-byte the shape `mermaid-tools` ships while **enabled in the user's live vault**. `node --check main.js` |
| **R-070-4** | **Drift gate, 3 layers** (`tests/test_agent_bridge_build_drift.py` + `scripts/build_agent_bridge.py` + `config/agent-bridge-build.json`, mirroring `pin_skill_integrity.py`/`skill-integrity.sha256`). **L0** hash-pins **both** `main.ts` and `main.js` — runs with **zero toolchain**, so a skip cannot hide drift. **L1** byte-compare (needs node) — catches what L0 structurally cannot: a hand-edited `main.js` that was *also* re-pinned. **L2** `WIKI_STRICT_PLUGIN_BUILD=1` ⇒ skip becomes failure. Skip predicate is **toolchain-absence only**; never `except Exception: skip`. **Must include `test_bundle_externalizes_what_obsidian_provides_at_runtime`** — dropping `--external` yields 419,223 bytes, **exit 0, no warning**, a 2nd CM6 instance, and the ViewPlugin silently never draws, with **11 of 12 tests still green**. That test is the sole guard for a build-green catastrophe. | ✅ | mutation-proven: node absent + `main.ts` edited → `3 skipped, 1 failed`; tampered+re-pinned → L0 green, **L1 red**; a failing build **fails**, never skips |
| **R-070-9** *(numbered late deliberately — it groups with the gate requirements R-070-3/4, not with the fixes)* | **`tsc --noEmit` runs in pytest.** **Without this the whole task is vacuous**: esbuild does **not** typecheck — it happily emits 12,191 bytes from a `main.ts` that `tsc` rejects with 3 errors. Byte-green ≠ type-correct. Three things this requirement must NOT inherit naively from R-070-4: **(a) per-tool skip predicate.** `_tsc_present()` = `node` + `node_modules/.bin/tsc`; **never** reuse esbuild's `toolchain_present()`. The dangerous direction is not "node present, typescript absent" (that fails loud — predicate True ⇒ `FileNotFoundError`); it is **esbuild absent + typescript present ⇒ the tsc gate skips although it could have run**. A gate that goes quiet because a *different* tool is missing reports nothing. **(b) Pin the type gate's own compiler.** `typescript` is `^5` today (→ 5.9.3) — floating, receipted nowhere, while esbuild is exact *and* in the receipt. The moment `tsc` stops being "a thing someone types" and becomes a gate, `^5` silently reintroduces the over-promise the obsidian pin exists to prevent. Pin exact; add a `tsc` block (version + `sha256(main.ts)` + "0 errors") to `config/agent-bridge-build.json`. **(c) `scripts/build_agent_bridge.py --write` MUST run `tsc --noEmit` first and refuse to re-pin on error.** Otherwise `--write` re-pins `main.ts`'s hash without `tsc` ever running — **C-1 surviving inside C-1's own fix**. This is also what buys R-070-9 a **genuine L0** (which it cannot otherwise have — you cannot type-check without a type-checker, so a no-node machine would leave it with L2 alone): once `--write` is gated on tsc, the receipt's `main.ts` hash matching the live `main.ts` *transitively* means "the last re-pin passed tsc" — red on **any** machine, zero toolchain. | ✅ | edit `main.ts` to reintroduce a type error + rebuild + re-pin ⇒ **RED** (mutation-proven, not asserted). Also: esbuild absent + typescript present ⇒ tsc gate still **runs** |
| **R-070-5** | **H1 fix — make the fail-open unrepresentable, not re-guarded.** Type the resolution as `MarkdownView`; refuse a non-`MarkdownView` **at** the active editor with a new typed reason `unsupported-view` (**never** fall through to `lastEditor`). Narrow `lastEditor` to `MarkdownView`. **Must reach the wrapper contract:** add `"unsupported-view": EXIT_NO_SELECTION` (**exit 3**) to `_REASON_EXIT` (`obsidian_selection.py:323-343`) — else the fail-closed default returns **4 = RETRY** and the agent retries a deterministic refusal forever. **3 is the only coherent code, and this task states it rather than deferring it:** 4 means *retry* (this refusal is deterministic — retrying reproduces it), 7 means *guard-refused* (that class is a **payload** conflicting with live state; `export` has no payload at all), so it belongs with the other "there is nothing here to give you" rungs. **Keep `no-saveable-view` as a legacy alias** — the plugin installs by **copying** the folder (README:80), so a vault can run an older `main.js` than the repo's wrapper. Update the vocabulary in `SKILL.md:394-397` (**H-5-pinned ⇒ anticipate the re-pin**) and `references/recipes.md:309,323`. | ✅ | **kills all 3 tsc errors with zero casts / zero `any`** — the convergence test: a fix needing a cast is fighting the API |
| **R-070-6** | **Popout persist-highlight — outcome, not mechanism.** The highlight persists in **every** open document (main + popouts); no double-injection; cleanup structural. *Design recommendation (Planning to confirm):* `EditorView.baseTheme` — CM6 mounts style modules per view root (`@codemirror/view/dist/index.js:7987`), the `<style>` is created **in the target document** (`style-mod.js:93,100`), dedup is **structural** (`style-mod.js:82,111`), and re-mount on window-drag is handled (`setRoot()` → `mountStyles()`, :8304-8310). **`window-open`/`iterateAllLeaves` is REJECTED**: ~30 lines and four failure modes to replace one line that has none. | ✅ | **2 of the design's 6 tests** — `test_highlight_css_is_a_cm6_base_theme`, `test_highlight_css_never_injected_into_one_document`. The other two are **void by construction of this task** and must NOT be copied: `test_main_js_destructures_editorview_…` is moot (R-070-3 deletes the hand-mirror — esbuild always emits the require, so it pins output that cannot fail), and `test_main_js_loads_under_plain_require` goes **RED** (R-070-8 drops the try/catch, and `node_modules/obsidian/package.json:14` is `"main": ""` — types-only, genuinely unresolvable at runtime). Empirically: `MAIN: style tags = 1`, `POPOUT: style tags = 1` after 3 mounts |
| **R-070-7** | **Read-path nonce check** — reason `selection-nonce-mismatch`, **exit 4** (no-attributable-result ⇒ RETRY; **not** 7, which means abort). | ✅ | **Code + tests ALREADY LANDED (§6)** — 2 mutation-pinned tests, guarded transitively by the ≥2968 baseline. ⚠️ **Its VOCABULARY did not land**: `selection-nonce-mismatch` appears in **zero** markdown under `skills/obsidian-cli/`, and `SKILL.md:395` — an H-5-pinned contract loaded **verbatim** into the orchestrator's context — still describes exit 4 without it. A contract omitting a reason the code emits is this project's failure mode exactly. Owned by PLAN B-03, whose H-5 re-pin already covers the cost. |
| **R-070-8** | **Retire the vacuous smoke test.** Drop the try/catch require-fallback (a deliberate `main.js`↔`main.ts` divergence existing *only* to make TC-03 pass); replace TC-03 with `node --check main.js` — same real guarantee, no divergence. **Rewrite the README's OQ2 prose**: :116 ("hand-authored … kept in lockstep by hand"), :118 ("**no automated check**"), :129 ("manually re-transcribe … into `main.js`" — which R-070-4 makes a **gate violation**), §Files :148-152, §Install :81 (still names `obsidian.d.ts`). | ✅ | README carries no hand-mirror instruction; TC-03 is `node --check` |

**Non-goals (NF).** NF-1: no DDL (`user_version` stays 7). NF-2: no `import anthropic` (Decision-17). NF-3: **the remaining ~39 LOW type-only discrepancies get no individual work** — not on a statistic, but on mechanical proof: **`tsc` against the real package reports exactly 3 errors, all addressed by R-070-5**, so no other LOW is load-bearing at compile time. (All 43 confirmed entries were read; every LOW is verified against `main.js` and the great majority are *stricter* than reality, i.e. fail-closed. None misfiled.) Deleting the fiction fixes them by construction; enumerating them would be the mirror-maintenance habit this task ends. NF-4: the concurrency race is **narrowed, not closed** — OQ-070-1.

## 4. Open questions

- **OQ-070-1 (accepted residual).** R-070-7 narrows the read race; it does not close it. The nonce attributes a payload to a *request-file content*, not a dispatch: if B overwrites `agent-request.json` before the plugin reads it, the plugin stamps B's nonce onto **both** outputs — A fails closed (exit 4), but B may match a payload captured by A's dispatch. Bounded: one live selection per vault (B gets a genuine app selection, not A's private data), and any `apply` is re-guarded against the live editor, so a stale capture **refuses**. Closing it needs per-dispatch request files or a lock — **deliberately out of scope**.
- ~~**OQ-070-2**~~ — **SETTLED**, was never open: `design-drift-gate.md` answers it with 3 mutation-proven mechanisms and an executed 8-row matrix (folded into R-070-4).
- **OQ-070-3 (UNVERIFIED).** Obsidian's **enforcement** of `minAppVersion` is documented (:4971) but not observed. If it only warns, R-070-2's runtime half is documentation-grade and only the tsc half holds. Check: `minAppVersion: "99.0.0"` → reload → confirm refusal. **Do not claim it works until run.**
- **OQ-070-4 (UNVERIFIED).** Obsidian augments DOM `Node` with `instanceOf<T>()` (:60-62) — *"Cross-window capable instanceof check"* — because plain `instanceof` **fails across window realms**. R-070-5 rests on `instanceof MarkdownView`. *Reviewer's read: likely safe, since the realm hazard is for DOM globals, not Obsidian's single-realm JS classes — but **UNVERIFIED**.* Close it in the dogfood (§7), not by argument.
- **OQ-070-5 (known unexamined — and it has already cost us).** The `omission-driven` lens died twice. **Its absence produced a wrong requirement**: `baseTheme` is absent from the vendored `EditorView`, so v1's R-070-6 prescribed ~30 lines of `window-open` plumbing to replace a one-line fix the fiction had hidden. Not a clean bill — a **receipt**. Mitigation: re-run the lens **narrowly** over the ~10 symbols the plugin actually touches (bounded, cheap, hit rate just demonstrated).

## 5. Scope discipline

Fix **H1 (incl. the 3 free bugs), H2 (both halves — generation AND automatic `tsc`), popout, the pin**. Do **not** hand-patch the LOWs (NF-3).

## 6. Process disclosure — code that landed out-of-process

**R-070-7's implementation was written to the working tree by an audit subagent asked to *design*, not implement, which then died mid-stream without reporting.** Discovery was **accidental** — the re-run agent's first line was a correction to my premise. Harness error: analysis agents had write tools and a prompt asking for "the exact diff". **The fix is removing write tools from analysis agents, not retyping verified code.**

**Enumeration method** (stated because the tree is *also* intentionally dirty from my own scouting, so provenance is non-trivial): a full `git status --porcelain` sweep against `a8f7a70` at discovery. My deltas: `obsidian.d.ts` moved aside, `tsconfig.json`, `package.json`/`package-lock.json` (npm install). The dead subagent's: `skills/obsidian-cli/scripts/obsidian_selection.py` (+31), `tests/test_obsidian_selection.py` (+39, 38→40), `skills/obsidian-cli/evals/fixtures/selection/read-foreign-nonce.selection.json` (new). Other design agents *self-assert* they left the repo untouched — an agent self-claim, which this project does not accept unverified; the sweep is what confirms it.

I did **not** ratify on the subagent's say-so: I read the diff line by line, and an independent reviewer verified it again (guard at `obsidian_selection.py:421-427`; exit 4 = the right family; 2 tests pinning the **harm** — `"Secrets/Private Journal.md"` / `"ANOTHER-AGENTS-NOTE-TEXT"` must not reach stdout). **Kept.** One thing corrected immediately: its docstring claimed concurrent invocations *"never read each other's data"* — stronger than the code delivers (OQ-070-1). An agent, inside the task about claims stronger than the code, wrote a claim stronger than the code.

## 7. Acceptance criteria

- [ ] `obsidian.d.ts` **gone**; `tsc --noEmit` green against the real pinned package; **no `any`/cast introduced** by R-070-5.
- [ ] **R-070-9 mutation-proven**: reintroduce a type error in `main.ts`, rebuild, re-pin ⇒ suite **RED**. (If this passes green, the task has failed regardless of everything else.)
- [ ] `main.js` byte-identical to the build; two builds identical; the drift gate RED on a hand-edit and on `main.ts`-without-rebuild — **proven by mutation, not assertion**.
- [ ] Dropping `--external` ⇒ **RED** (the externals guard fires).
- [ ] The preview guard **cannot** fail open: a non-`MarkdownView` is refused at resolution (`unsupported-view`), never silently retargeted. `unsupported-view` is in `_REASON_EXIT` with a **stated** exit code; `no-saveable-view` still maps (legacy alias).
- [ ] `pin == minAppVersion == 1.12.3`; lockfile agrees; pin exact.
- [ ] **LIVE DOGFOOD (the only real gate — H2 means no suite covers the plugin).** In the user's Obsidian, from the integrated terminal: `read` returns the selection; `apply` writes it back; **`read` also works in a popout** (closes OQ-070-4 — do not claim R-070-5 correct in popouts by argument); a popout shows the persisted highlight; **`copy-selection-ref` still behaves** (third consumer, R-070-5 changes it). The regenerated `main.js` is a **new artifact** — nothing else proves it runs.
- [ ] Suite ≥ 2968 / 0 failed; `mypy --strict scripts/` clean; H-5 green (`SKILL.md` re-pin **expected** per R-070-5).
- [ ] ARCHITECTURE §2.2.2 ledger: OQ2 closed, H1/H2 recorded, OQ-070-1/3/4/5 carried honestly, **and
      the popout row corrected** — it still prescribed the `window-open` overload this task rejects,
      reasoned from the fiction (`baseTheme` was absent from the vendored `EditorView`). That row *is*
      what produced C-2; leaving it would leave the trap one section above its own fix.
- [ ] **`scripts/build_agent_bridge.py --write` HARD-FAILS when `tsc` is absent — never skips**, and
      the **final pin is minted under the live tsc gate** (a receipt written before `--write` was gated
      matches a `main.ts` that was never type-checked). Without both, R-070-9's transitive L0 is false
      for the shipped state — and a skip there is the same "gate silenced by a missing tool" death
      R-070-9(a) guards against, relocated to the one site the whole L0 claim rests on.

## 8. Revision log (v1 → v2)

A BLOCKING task-review returned **3 CRITICAL + 9 MAJOR**. Its diagnosis, accepted verbatim: *"the TASK is a weaker document than the evidence it sits on."* **Root cause: I wrote v1 without reading two of the six design docs I had commissioned** (`design-popout-fix.md`, `design-drift-gate.md`), so v1's requirements came from the docs' *rejected alternatives* and *open problems* instead of their *decisions*.

| | Fix |
|---|---|
| **C-1** | **No requirement made `tsc` automatic** — §1's headline defect, closed by nothing; post-070 a vacuous green was reachable (edit `main.ts`, rebuild, re-pin → all green, 3 type errors shipped). → **R-070-9**. |
| **C-2** | R-070-6 mandated the design's **explicitly rejected** alternative. → outcome-stated; `EditorView.baseTheme`. |
| **C-3** | `unsupported-view` existed **only in this file** — `_REASON_EXIT` didn't know it ⇒ exit 4 = infinite retry on a deterministic refusal; legacy alias + H-5 re-pin unanticipated. → folded into R-070-5. |
| **M-1** | R-070-3 claimed "(verified deterministic)" for `bundle:false` while every determinism/mutation result came from the **`--bundle`** recipe. → adopted the verified recipe + the **cwd** determinism input (both independently reproduced here). `bundle:false` **rejected**, and its merit recorded: under it the `--external` footgun is structurally impossible (nothing is bundled, so a dropped flag cannot inline a second CM6), and the two recipes' outputs differ by only 12,188 vs 12,191 bytes with an identical export shape. Rejected anyway because `--bundle` is the recipe that was actually verified end-to-end (5-run determinism, the cwd input, the mutation matrix, the export-shape proof) and is future-proof if a real dependency is ever added — and because preferring my unverified variant over the scratchpad's evidence would repeat the C-2 error exactly. |
| **M-2** | The export-shape change (`module.exports = AgentBridge` → esbuild's) was unnamed — wrong shape = **plugin doesn't load at all**. → retired empirically in R-070-3. |
| **M-3** | OQ-070-2 was labelled open; it was settled. → folded into R-070-4. |
| **M-4** | The census statistic didn't survive its own artifacts. → **withdrawn**; NF-3 now rests on the tsc-error count. |
| **M-5** | H1's blast radius overstated (apply has a backstop; export doesn't) and the *stronger* real harm (embedded-document offsets) had been dropped. → §2 corrected. |
| **M-6** | `copy-selection-ref`, the third consumer, was unenumerated — **inside the task about unenumerated surfaces**. → §2 + dogfood. |
| **M-7** | OQ-070-5 was too weak: the missing lens **already cost us C-2**. → recorded as a receipt; narrow re-run. |
| **M-8** | §6 didn't state how the affected-file list was derived. → method stated. |
| **M-9** | The dogfood didn't exercise R-070-5 ↔ R-070-6 (OQ-070-4). → `read` in a popout. |
| MINORs | Baseline tsconfig quoted (v1 quoted the mid-task state as the finding); 41 → ~39; OQ2/README rows (R-070-8); R-070-2 ordering; `grep` path. |

**One more, found while fixing M-1 and worth recording:** my own "3 runs → deterministic ✓" check had been hashing **empty output** — zsh does not word-split an unquoted `$ARGS`, so esbuild never ran, and three identical hashes of the empty string read as a pass. Caught only by recognising `e3b0c442…` by sight. **The third vacuous green of this session, and the first one I built myself.** *(The re-review used this against me, as intended: it treated the confession as a licence to distrust every "independently reproduced" in v2, then checked the load-bearing one — R-070-3's `05d906d4…` converges with the design doc's independently-derived hash. Two agents, two runs, one hash. An empty run would have read `e3b0c442…`.)*

### v2 → v3 (re-review: APPROVED, 4 MAJOR folded in, no re-analysis)

| | Fix |
|---|---|
| **M-1** | R-070-9's skip predicate must be **per-tool**. The hazard I failed to name is the mirror of the one I did: not "node present, typescript absent" (that fails loud), but **esbuild absent + typescript present ⇒ the tsc gate skips though it could have run** — a gate silenced by a *different* tool's absence. |
| **M-2** | ★ **The type gate's own compiler was unpinned** (`typescript: "^5"` → 5.9.3, receipted nowhere) while esbuild is exact *and* receipted. And `--write` re-pinned `main.ts`'s hash **without ever running `tsc`** — **C-1 surviving inside C-1's own fix**. Fixed by pinning tsc, receipting it, and gating `--write` on it — which also gives R-070-9 the **L0 it had claimed but could not have** (you cannot type-check without a type-checker). |
| **M-3** | R-070-6's verification imported 2 tests authored in a **pre-R-070-3 world**: one goes moot (no hand-mirror left to forget a destructure in), one goes **RED** (`obsidian`'s `"main": ""` is types-only). v2 imported the designs' *decisions* faithfully but did not re-base them onto the world its own other requirements create — the same error class as v1, one level up. |
| **M-4** | Deferring the `unsupported-view` exit code to Planning was C-3 in a thinner disguise: the evidence had already decided it. **Stated: exit 3.** |
| MINORs | `grep -r`; "Design recommendation (Planning to confirm)"; the cryptic "3-byte" claim expanded; R-070-9's out-of-order ID explained. |

**Reviewer's own correction, recorded because it cuts both ways:** its v1 report claimed `skill-task-review-checklist` was "not loadable" (`.agent/skills/` = only `.DS_Store`). False — the directory holds 68 **symlinks**; its Glob is symlink-blind. It re-ran with the checklist applied and flagged the same blindness in its `node_modules/.bin/*` probe before it could become a finding. A tool reporting absence it cannot see is the same failure shape as everything else here.
