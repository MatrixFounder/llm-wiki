# TASK 069 — [LIGHT] Correct the TASK-068 residual ledger (docs-only)

## 0. Meta Information

| | |
|---|---|
| **Task ID** | 069 |
| **Slug** | residual-ledger-correction |
| **Type** | docs (correction) |
| **Mode** | **[LIGHT]** — no deps, no new source files, no schema, no `auth*`/`payment*`/`crypto*`, <30 min |
| **Predecessor** | TASK 068 (`docs/tasks/task-068-obsidian-selection-bridge.md`) |
| **Follow-up** | **TASK 070** (pipeline, NOT light) — close OQ2: real `obsidian` types + generated `main.js` + drift gate. Also carries the popout fix (§3, item B) **and the `read`-path nonce check** (§1.2 C — a real defect this task found but must not fix: it needs an exit-code-family decision + a concurrency test, i.e. pipeline work, in code TASK 070 already opens). |
| **Baseline** | `2968 passed, 0 failed` (RUN 2026-07-16, commit `23bb974`). Docs-only task ⇒ gate = suite unchanged. |

---

## 1. What is broken

Two problems, both **in the living docs**, both created by me.

### 1.1 `docs/architectures/functional/native-app-control.md` §2.2.2 contradicts itself

The `/update-docs` pass (commit `23bb974`) **appended** a correction without removing the claim it
refutes. The same section now asserts both:

| Line | Claim |
|---|---|
| 279 (stale) | "**OQ1 … is now LIVE-PROVEN**: the 2026-07-15 dogfood showed the `callback` fires while OS focus sits in the integrated terminal **AND reads the real selection**" |
| 302 (correct) | "The original OQ1 verification was run from an **EXTERNAL shell** … and therefore **never exercised the real case**" |

Both are 25 lines apart in one section. The stale paragraph (271–288) carries **three** dead claims:

1. **OQ1 "LIVE-PROVEN"** — falsified by the correction below it. What the 2026-07-15 dogfood proved
   is narrower: the `callback` *fires* under terminal focus. It did **not** read the real selection —
   `activeEditor` was null there, which is the whole reason the `recent-editor` fallback exists.
2. **"covered only by `npx tsc --noEmit` (types, against the vendored `obsidian.d.ts`)"** — stated as
   if the vendored file were a gate; the ★ lesson 40 lines below says it is a **mirror**.
3. **OQ5 "the temp-file/`require('fs')` escape hatch itself is deferred, out of scope"** — stale:
   **`--from-json` shipped** as the ARG_MAX escape valve (`obsidian_selection.py:351`).

### 1.2 The residual list is wrong on 2 of 4 items

The carried-forward list says: *popout style · export size-cap · concurrent-dispatch race · no JS
test runtime*. Verified against the code: **one is not a real defect** (A), one is **worse than the
list said** (C — the list was right that it is a race; *my* first verdict of "fail-safe" was the
error, caught in review), and one is misdiagnosed at the root (D):

| # | Claimed | Verified reality |
|---|---|---|
| A | "`export-selection` has no size cap while `apply` does" | **Not a defect.** `apply`'s `_MAX_B64_LEN = 512 KiB` is an **ARG_MAX guard on inline argv**, deliberately bypassable via `--from-json` (`obsidian_selection.py:469-476`). `export` has **no argv in its path** — the plugin writes a file, the wrapper reads it. There is no asymmetry to mirror; copying the constant would cargo-cult a guard whose reason does not apply. |
| B | "persist-selection `<style>` is main-window-only" | **Real.** `main.ts:198-200` appends to the bare `document.head` (main window). **But ordering-blocked** — see §3. |
| C | "concurrent dispatch unguarded (race)" | ⚠️ **REAL — my first analysis was wrong** (caught by the fresh-context review, not by me). Split the paths. **`apply` is fail-safe:** GUARD 1/2/3 validate against the *live* selection, so a clobbered `agent-edit.json` only lands its own author's edit; a loser times out. **`read` is NOT:** the nonce is matched on `agent-result.json`, then `agent-selection.json` is read **unchecked** (`obsidian_selection.py:390`) — a dispatch landing in that window hands agent A agent B's path + note text under `ok:true`, chaining into a guard-*passing* write on a selection A never received. The plugin writes a nonce into that payload (`main.ts:302`) the wrapper never compares — a guard field written and never read. One-line fix → TASK 070. |
| D | "no executable test runtime — the root cause of the fabricated `save()`" | **Real but misdiagnosed.** Understated *and* wrong on cause — see §2. |

---

## 2. The `tsc` claim is worse than documented, and the proposed cure is wrong

**Understated.** The docs say *"tsc + inspection are its only gate."* Verified:

- `tsc` is **invoked by nothing automatic** — no CI, no pytest, no script. It was run by hand.
- `tsconfig.json` is `noEmit: true`, `include: ["main.ts", "obsidian.d.ts"]` — **`main.js` is not in
  it**. `main.js` is a hand-authored mirror (340 lines vs `main.ts`'s 404), and it is **the only file
  that runs**. Inspection, too, read `main.ts`.
- `package.json` devDeps = `typescript` only. There is **no `obsidian` package** — yet R-068-1's own
  verification reads *"`main.ts` type-checks against **upstream** `obsidian.d.ts`"*. The requirement
  was closed against a hand-written file. (README §"Rebuild discipline" already discloses the
  hand-mirror honestly as **OQ2** — that is the thread to pull.)

⇒ **The shipped artifact has no gate at all.**

**Wrong cure.** "Add a test runtime" does not fix this. A hand-written fake (`{file, editor, save:
jest.fn()}`) would be written from the **same wrong model of the API** that produced the fabricated
type — the test would pass, the bug would survive, now with a green check behind it. **A fake mirrors
your beliefs exactly as vendored types do.** The root cause is *no contact with the real API*, not
*no tests*. Recording this matters: an uncorrected ledger sends the next person to build the fake
harness and feel safer for it.

---

## 3. Expected fix (scope of THIS task)

**Docs only. No code.**

1. **ARCH §2.2.2** — replace the stale residual paragraph (271–288): delete the OQ1 self-contradiction
   (keep the narrow, true claim: the callback fires; the selection read needed the fallback), state the
   three verified facts about the gate (AC2) while **cross-referencing rather than restating** the ★
   mirror lesson that already sits below it, and mark OQ5's escape valve **shipped**.
2. **ARCH §2.2.2** — restate the residual ledger per §1.2 A–D: A dissolved with its reason, B real +
   ordering-blocked, **C real on `read` / fail-safe on `apply`** (corrected in review — see §1.2 C;
   the fix routes to TASK 070), D reframed per §2 (incl. the no-fake-harness note).
3. **`skills/.AGENTS.md`** — align the TASK-068 `Residual:` sentence with D (it currently repeats
   "tsc + inspection are its only gate").
4. **`skills/obsidian-cli/plugin/agent-bridge/README.md`** — §"Rebuild discipline" is honest; point
   OQ2 at the TASK-070 follow-up so the reader knows the fix is scheduled, not merely regretted.

**Out of scope — deferred to TASK 070 (pipeline):** real `obsidian` devDependency, deleting the
vendored `obsidian.d.ts`, `esbuild` main.ts→main.js, the byte-identity drift gate, **and item B
(popout)**. B is deferred *for a reason, not for convenience*: the fix needs a `window-open` overload,
and the vendored d.ts declares exactly one event (`on(name: "active-leaf-change", …)`). Adding it by
hand today means writing one more belief about the API into **the same file that produced the
fabricated `save()`**. B is cheap *after* the types are real, and reckless before.

The archived `docs/tasks/task-068-*.md` is a **historical snapshot and is not edited** — corrections
land in the living docs (ARCHITECTURE / `.AGENTS.md` / README) per `skill-archive-task`.

## 4. Acceptance criteria

- [ ] No sentence in §2.2.2 claims the 2026-07-15 dogfood proved OQ1's selection read; no two
      statements in the section contradict each other on editor resolution.
- [ ] §2.2.2 states that `main.js` is outside `tsconfig`'s `include`, that nothing runs `tsc`
      automatically, and that no `obsidian` package is installed.
- [ ] Residual A is recorded as dissolved **with the reason**, not silently dropped.
- [ ] Residual C is recorded as **REAL on the `read` path** (not "dissolved"/"diagnostics-only"), with
      the `apply`-vs-`read` split, the unchecked `obsidian_selection.py:390`, the written-never-read
      nonce, and the one-line fix routed to TASK 070 — in **both** ARCH §2.2.2 and `skills/.AGENTS.md`.
- [ ] D records that a fake-based harness would reproduce the failure mode.
- [ ] R-068-1's falsified "upstream `obsidian.d.ts`" verification is noted as such.
- [ ] Suite unchanged: `2968 passed, 0 failed`. No `SECURITY-SENSITIVE` marker added. H-5 green
      (no pinned contract touched — verify, don't assume).

## 5. Open questions

None blocking. TASK 070's shape is settled (§3 Out of scope); its sequencing is the user's call.
