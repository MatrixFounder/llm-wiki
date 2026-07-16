# TASK 070-07 — [R-070-9 + R-070-8] Final pin under the live gate; honest docs

**Goal:** the receipt attests something. The README stops teaching the discipline the gate now forbids.

**Context:** `skills/obsidian-cli/plugin/agent-bridge/README.md` (:80 install, :113-141 rebuild discipline, :148-152 files), `docs/architectures/functional/native-app-control.md` §2.2.2 ledger.

**Steps**
1. **Re-pin under the tsc-gated `--write`** — ordering constraint: a receipt minted before `--write` was gated matches a `main.ts` that was never type-checked.
2. README install → enumerate **`manifest.json` + `main.js`**, not "copy this whole folder". This is what turns "never ships into a vault" from an assertion into a mechanism.
3. README §Rebuild discipline → `npm run build` + the gate. **Delete** ":129 manually re-transcribe … into main.js" — 070-02 makes it a **gate violation**. TC-03 → `node --check main.js`. Drop `obsidian.d.ts` from §Files/§Install.
4. ARCH §2.2.2 ledger: OQ2 **closed**; H1/H2 recorded; OQ-070-1/3/4/5 carried; **the popout row corrected** — it still prescribes the rejected `window-open`, and that row *is* what produced C-2.

**Verification** — `pytest -q` ≥ 2968 / 0 failed; `mypy --strict scripts/` clean; H-5 green; `grep -i "hand-authored\|lockstep by hand" README.md` → nothing.
