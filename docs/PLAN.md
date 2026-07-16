# PLAN 070 — agent-bridge: mirror → gate

**Spec:** `docs/TASK.md` (v3, APPROVED) · **Architecture:** `docs/architectures/functional/native-app-control.md` §2.2.3 (APPROVED)
**Baseline:** `2968 passed, 14 skipped, 0 failed` @ `a8f7a70`; `tests/test_obsidian_selection.py` at **40**.

---

## 0. Why the order is not negotiable

**Four** constraints came out of the gates. The first three are violable orderings — break one and a
requirement goes **inert**, still "passing", which is this task's whole subject. The fourth is a
*property* that must hold rather than a sequence that can be reordered.

| Constraint | Why |
|---|---|
| **B-03 (guard fix) before B-05 (generate)** | ★ **The strongest one, and the first draft failed to name it.** `--write` refuses to re-pin on a type error, and B-01 guarantees 3 — so B-05 **literally cannot run** until B-03 lands. Mechanical, not advisory. |
| **B-05 (generate) before B-06 (pin)** | The pin gates `main.ts`. Until `main.js` *comes from* `main.ts`, the pin gates a file Obsidian never executes — `design-version-pin.md` risk 1: *"inert until the esbuild-generate decision lands"*. *(The first draft said "B-04" — a stale renumbering inside the table of non-negotiables. Fixed.)* |
| **B-01 (real types) before B-03 (guard fix)** | R-070-5's fix is defined by the real API (`getMode` on `MarkdownView`, `WorkspaceLeaf.view: View`). Against the fiction it cannot even be expressed. |
| **B-02's `--write` tsc-gating before B-07's final pin** | A receipt minted before `--write` is tsc-gated matches a `main.ts` that was **never type-checked**. R-070-9's transitive L0 would be *false for the shipped state* — C-1 surviving inside C-1's fix. *(Delivered by B-02, so this is satisfied by construction — kept because the property, not the ordering, is what must hold.)* |

### RTM coverage — every requirement is owned; two span two beads

*(The first draft had no such table, which is exactly how R-070-7 slipped through unmapped.)*

| Req | Bead | Req | Bead |
|---|---|---|---|
| R-070-1 | B-01 | R-070-6 | B-04 |
| R-070-2 | B-06 | **R-070-7** | **B-03 (vocabulary only)** — code+tests already landed (TASK §6) and are guarded transitively by the ≥2968 baseline; but its **vocabulary never landed**: `selection-nonce-mismatch` appears in **zero** markdown under `skills/obsidian-cli/`, and `SKILL.md:395` — an **H-5-pinned contract loaded verbatim into the orchestrator's context** — still describes exit 4 as *"(result timeout / stale nonce never matched)"* while the code emits a reason it does not list. A contract omitting a reason the code emits is this project's failure mode in its purest form. B-03 already edits those lines and already re-pins H-5 ⇒ near-free. |
| R-070-3 | B-05 | R-070-8 | B-05 (try/catch) + B-07 (README prose) |
| R-070-4 | B-02 | R-070-9 | B-02 (gate) + B-07 (final pin under it) |
| R-070-5 | B-03 | | |

**The Red→Green here is real, not ceremonial.** `design-drift-gate.md` measured it: today's hand-authored
`main.js` is `e14f5e08…` (14,634 B); esbuild emits `05d906d4…` (12,191 B). **The gate is RED the moment
it exists** and stays red until B-05 regenerates. Phase 1 does not fake a failure — it exposes one.

## 1. Phase 1 — build the gate; it goes RED against reality

- [ ] **B-01 · [R-070-1]** Delete the fiction; wire the real types.
  - `obsidian.d.ts` → deleted (currently parked as `obsidian.d.ts.VENDORED-FOR-AUDIT`; delete that too).
  - `tsconfig.json` → `include: ["main.ts"]`, `skipLibCheck: true`, `lib: ["ES2018","DOM"]`.
  - `package.json` → `obsidian` **1.12.3 exact** (already installed), `esbuild` **0.28.1 exact**,
    `typescript` **pinned exact** (today `^5` → 5.9.3 — R-070-9(b)).
  - **Verify (expected RED, and that is the point):** `npx tsc --noEmit` → **exactly 3 errors**
    (TS2367 @161, TS2339 @277, TS2339 @344). A green here means the types are not really wired.
    `grep -rc "declare module" <plugin>/` → 0.

- [ ] **B-02 · [R-070-4 + R-070-9]** The gate, written before the thing it gates is fixed.
  - `scripts/build_agent_bridge.py` — single source of the recipe. `ESBUILD_ARGV` = `main.ts --bundle
    --external:obsidian --external:@codemirror/view --external:@codemirror/state --format=cjs
    --target=es2018 --platform=browser --log-level=warning`. **`cwd=PLUGIN_DIR` + relative entry**
    (esbuild stamps the entry path: rel `05d906d4…` vs abs `3b3a3645…`). `check=True` — a broken build
    raises, never degrades to a skip. Mirrors `scripts/pin_skill_integrity.py`.
  - **Per-tool predicates** (R-070-9(a)): `_esbuild_present()` = node + `node_modules/.bin/esbuild`;
    `_tsc_present()` = node + `node_modules/.bin/tsc`. **Never one shared `toolchain_present()`** — the
    hazard is *esbuild absent + typescript present ⇒ the tsc gate skips though it could have run*.
  - `--write`: runs **`tsc --noEmit` FIRST**; **refuses to re-pin on a type error**; **HARD-FAILS if
    `tsc` is absent — never skips** (that skip would kill the transitive L0 at the one site it rests on).
  - `config/agent-bridge-build.json` — receipt: `sha256(main.ts)`, `sha256(main.js)`, esbuild version +
    argv, tsc version + "0 errors".
    ⚠️ **The receipt is NOT minted in B-02 — it cannot be.** `--write` refuses on a type error and B-01
    guarantees 3, so at B-02 no receipt can honestly exist. **B-02 ships the file absent**, and L0 must
    treat *"receipt missing"* as **RED (drift), never as an error or a skip** — a missing receipt is the
    un-pinned state, which is exactly what L0 is for. **B-05 mints the first honest receipt**
    (its `npm run build` IS `--write`, which re-pins by definition, once B-03 has cleared the errors);
    **B-07 re-affirms** it under the live gate — idempotent belt-and-braces, since nothing touches
    `main.ts`/`main.js` after B-05. **Three bypasses are banned — they are distinct holes, so ban all three in
    both docs:** `--force` (skips the tsc refusal), `--build-only`/`--no-pin` (builds without re-pinning
    ⇒ L0 stays red through B-06, and invites exactly the "no receipt until B-07" misreading), and
    hand-authoring a `"0 errors"` nobody proved — a lie in the artifact whose entire job is to not be one.
  - `tests/test_agent_bridge_build_drift.py` — **L0** hash-pins **both** files, zero toolchain; **L1**
    byte-compare (needs node); **L2** `WIKI_STRICT_PLUGIN_BUILD=1` ⇒ skip becomes failure
    (⚠️ **latent** — no CI exists to set it: `docs/issues/arch-10-*`; L0 carries the guarantee).
    Skip predicate = toolchain absence only. **Never `except Exception: skip`.**
    Includes **`test_bundle_externalizes_what_obsidian_provides_at_runtime`** — the sole guard for a
    build-green catastrophe (drop `--external` → 419,223 B, exit 0, no warning, 2nd CM6 instance,
    ViewPlugin silently never draws, **11/12 still green**).
  - **Verify (expected RED):** L1 red (`e14f5e08…` ≠ `05d906d4…`); the tsc gate red (3 errors).

## 2. Phase 2 — make it green, in dependency order

- [ ] **B-03 · [R-070-5]** H1: make the fail-open **unrepresentable**.
  - `main.ts`: `MarkdownFileInfo` leaves the plugin. Resolution types as `MarkdownView`; a
    non-`MarkdownView` is refused **at the active editor** (`unsupported-view`) and **never falls
    through to `lastEditor`** (that fall-through silently retargets a *different note* and every apply
    guard then passes). `lastEditor: MarkdownView | null`; `rememberEditor` narrows.
  - Wrapper: `"unsupported-view": EXIT_NO_SELECTION` (**3**) in `_REASON_EXIT`; **keep
    `no-saveable-view`** as a legacy alias (the plugin installs by *copying* — a vault may run an older
    `main.js` than the repo's wrapper).
  - Vocabulary: `SKILL.md:394-397` (**H-5-pinned ⇒ re-pin via `python3 scripts/pin_skill_integrity.py
    --write`**), `references/recipes.md:309,323`.
  - **[R-070-7] vocabulary, folded in here** (the only place the RTM table maps it): `SKILL.md:395` still
    describes exit 4 as *"(result timeout / stale nonce never matched)"* — it **omits
    `selection-nonce-mismatch`, a reason the shipped code emits**, and that file is loaded **verbatim**
    into the orchestrator's context. `grep -r selection-nonce-mismatch skills/obsidian-cli/ --include=*.md`
    → currently **0 hits**. Add it here; the H-5 re-pin above already covers the cost.
  - **Verify:** `npx tsc --noEmit` → **0 errors, zero casts, zero `any`** (the convergence test — a fix
    needing a cast is fighting the API). New wrapper tests for `unsupported-view` → exit 3 and the
    legacy alias. `pytest tests/test_h5_skill_integrity.py` green after re-pin.

- [ ] **B-04 · [R-070-6]** Popout highlight — one line, not thirty.
  - `main.ts`: `const persistSelectionTheme = EditorView.baseTheme({ [`.${PERSIST_SELECTION_CLASS}`]:
    { backgroundColor: "var(--text-selection)" } });` → `this.registerEditorExtension([persistSelectionExtension,
    persistSelectionTheme])`. **Delete** the `document.head` `<style>` block (`main.ts:197-201`) **and**
    its `this.register(() => style.remove())` — cleanup becomes `registerEditorExtension`'s job.
  - **`window-open`/`iterateAllLeaves` is REJECTED.** CM6 mounts style modules per view root, so the
    popout is covered and dedup is structural.
  - **Verify — and read the parametrisation before you panic:** the design's test file is
    `@parametrize("src_path", [_MAIN_JS, _MAIN_TS])`, so each surviving test runs **twice**. At B-04 the
    correct state is **`[main.ts]` GREEN, `[main.js]` RED** — `main.js` is still the hand-authored mirror
    and only B-05 regenerates it. ⚠️ **Do NOT hand-patch `main.js` to go green here.** The design's
    §"Exact code" offers a ready-made `main.js` patch; taking it is the hand-mirror discipline B-02 makes
    a **gate violation** and B-07 deletes from the README. Either accept the RED window (02→05, see §0)
    or land the test file in B-05.
  - Tests: **2 surviving** (`test_highlight_css_is_a_cm6_base_theme`,
    `test_highlight_css_never_injected_into_one_document`). **Do NOT copy the other two** — one is moot
    (no hand-mirror left to forget a destructure in), one goes RED (`obsidian`'s `"main": ""` is
    types-only, so `require('./main.js')` cannot resolve outside Obsidian).

- [ ] **B-05 · [R-070-3 + R-070-8]** Generate `main.js`; retire the vacuous smoke test.
  - `npm run build` (= `build_agent_bridge.py --write`) → `main.js` **generated**. The hand-authored
    file, incl. its try/catch inert stand-ins (`main.js:19-29`), is **gone**.
  - **Verify:** L1 **GREEN** (byte-identical); two builds identical; `node --check main.js` passes.
    `node -e "require('./main.js')"` **now throws** — expected, and why TC-03 is replaced by
    `node --check`: the old test only ever proved *the file parses with fakes*.
  - ⚠️ **The shipped hash will NOT be `05d906d4…`.** That hash is esbuild(**today's** `main.ts`); B-03 and
    B-04 change `main.ts`, so the build legitimately moves. Use it only as the *pre-fix* anchor proving
    the gate is red today. **`05d906d4…` in TASK R-070-3's AC is stale by construction** — do not "fix" a
    correct build to reach it; the criterion is *byte-identical to the build of the current `main.ts`*,
    reproduced twice.

- [ ] **B-06 · [R-070-2]** Pin == `minAppVersion` == `1.12.3`.
  - `manifest.json`: `minAppVersion` 1.4.0 → **1.12.3**. One number; tsc refuses above, Obsidian
    refuses to load below.
  - **Verify:** tests — pin exact (no caret) · pin == minAppVersion · lockfile == pin.

- [ ] **B-07 · [R-070-9 + R-070-8 + docs]** Mint the final pin under the live gate; make the docs honest.
  - **Re-pin under the tsc-gated `--write`** (ordering constraint §0 — else the receipt attests nothing).
  - README: install enumerates **`manifest.json` + `main.js`** (not "copy this whole folder" — this is
    what makes "never ships into a vault" a *mechanism*); §"Rebuild discipline" → the build+gate;
    delete the hand-mirror instruction (`:129`), which B-02 makes a **gate violation**; TC-03 → `node --check`.
  - ARCH §2.2.2 ledger: OQ2 **closed**; H1/H2 recorded; OQ-070-1/3/4/5 carried; **the popout row
    corrected** (it still prescribed the rejected `window-open` — that row *is* what produced C-2).
  - **Verify:** full suite ≥ 2968 / 0 failed; `mypy --strict scripts/` clean; H-5 green; no
    "hand-authored"/"lockstep by hand" left in the README.

## 3. Phase 3 — the only gate that can actually fail

- [ ] **B-08 · [AC]** **LIVE DOGFOOD** — the regenerated `main.js` is a **new artifact** and H2 means no
  suite covers the plugin. Nothing in Phases 1–2 proves it runs.
  - In the user's Obsidian, from the **integrated terminal**: `read` returns the selection · `apply`
    writes it back · **`read` in a popout** (closes **OQ-070-4** — `instanceof` across window realms is
    UNVERIFIED; do not close it by argument) · popout shows the persisted highlight ·
    **`copy-selection-ref` still behaves** (the third consumer — R-070-5 changes it).
  - **OQ-070-3** if cheap: `minAppVersion: "99.0.0"` → reload → confirm refusal. Until run, R-070-2's
    runtime half stays documentation-grade.

## 4. Mutation proofs — the acceptance evidence (assertions do not count)

| Mutation | Expected |
|---|---|
| reintroduce a type error in `main.ts`, rebuild, re-pin | **RED** — *if green, the task has failed regardless of everything else* |
| hand-edit `main.js` **and** re-pin | L0 green, **L1 RED** |
| edit `main.ts`, don't rebuild, **no node** | **RED** at L0 (`3 skipped, 1 failed`) — the skip is non-vacuous |
| drop `--external:@codemirror/view`, rebuild, re-pin | **RED** at the externals test (only 1 of 12 fires — that is the point) |
| remove `unsupported-view` from `_REASON_EXIT` | **RED** (else exit 4 = infinite retry on a deterministic refusal) |
| `tsc` absent + `--write` | **HARD FAIL**, never skip |
| ★ **esbuild absent + typescript present** | the **tsc gate still RUNS** (must not skip). Mandated by R-070-9's own verification column and **missing from this table's first draft** — while `design-drift-gate.md:51-52` ships copy-paste-ready code implementing the *single shared* `toolchain_present()`, i.e. the exact hazard. A developer who copies the working scratchpad code ships the hole **and every other mutation here still passes**. The per-tool predicate was *asserted* in B-02 and pinned by nothing — in the table headed "assertions do not count". |

## 5. Out of scope (stated, not forgotten)

**OQ-070-1** the read race is narrowed, not closed (per-dispatch request files or a lock — a separate
task). **OQ-070-5** the `omission-driven` audit lens died twice; it has **already cost us once**
(`baseTheme` hidden ⇒ C-2). Re-run it **narrowly** over the ~10 symbols the plugin touches — cheap,
bounded, hit rate demonstrated. **NF-3** the ~39 LOW type-only discrepancies get no individual work:
`tsc` reports exactly 3 errors, all in B-03, which is mechanical proof no other LOW is load-bearing.
**`docs/issues/arch-10-*`** (no CI exists; every `WIKI_STRICT_*` is latent) is filed, not fixed here.
