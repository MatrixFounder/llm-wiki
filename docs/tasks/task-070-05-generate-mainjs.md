# TASK 070-05 — [R-070-3 + R-070-8] Generate main.js; retire the vacuous smoke test

**Goal:** `main.js` becomes a build product. The drift gate goes GREEN because the artifact is real, not because the test was loosened.

**Context:** `skills/obsidian-cli/plugin/agent-bridge/main.js` (hand-authored, 340 lines, `e14f5e08…`), `scripts/build_agent_bridge.py` (from 070-02).

**Steps**
1. Add `"scripts": {"build": "python3 ../../../../scripts/build_agent_bridge.py --write"}` to the plugin `package.json` (path relative to the plugin dir).
2. Run it. `main.js` is regenerated — the hand-authored file **and** its try/catch inert stand-ins (`:19-29`) are gone.
3. Confirm the export shape survives: `module.exports = __toCommonJS(main_exports)` + `default: () => AgentBridge` — the shape `mermaid-tools` ships while **enabled in the user's live vault**.

**Verification** — L1 **GREEN** (byte-identical); two builds byte-identical; `node --check main.js` passes.

> ⚠️ **The shipped hash will NOT be `05d906d4…`.** That value is esbuild(**pre-fix** `main.ts`); 070-03
> and 070-04 change `main.ts`, so the build legitimately moves. It is only the *pre-fix* anchor proving
> the gate is red today. **Do not "fix" a correct build to reach a stale number** — the criterion is
> *byte-identical to the build of the CURRENT `main.ts`*, reproduced twice.
> This bead also **mints the first honest receipt** (`--write` re-pins by definition).
`node -e "require('./main.js')"` now **throws** — expected: that test only ever proved the file parses *with fakes*.
