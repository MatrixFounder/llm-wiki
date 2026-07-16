# TASK 070-01 — [R-070-1] Delete the fiction, wire the real types

**Goal:** `obsidian.d.ts` gone; `main.ts` type-checks against the real pinned package. Expected outcome is **3 tsc errors** — that is success, not failure.

**Context:** `skills/obsidian-cli/plugin/agent-bridge/{obsidian.d.ts.VENDORED-FOR-AUDIT,tsconfig.json,package.json}`, `node_modules/obsidian/obsidian.d.ts` (1.12.3, installed).

**Steps**
1. `git rm` the vendored `obsidian.d.ts`; delete `obsidian.d.ts.VENDORED-FOR-AUDIT` (audit scratch).
2. `tsconfig.json`: `include: ["main.ts"]`, `skipLibCheck: true`, `lib: ["ES2018","DOM"]`, keep `strict`/`noEmit`.
3. `package.json`: `obsidian` `1.12.3`, `esbuild` `0.28.1`, **`typescript` pinned exact** (replace `^5`; today resolves to 5.9.3). No carets anywhere.

**Verification**
- `npx tsc --noEmit` → **exactly 3**: TS2367 main.ts(161,74); TS2339 getMode main.ts(277,12); TS2339 main.ts(344,12).
  ⚠️ A GREEN here means the real types are NOT wired — investigate, do not proceed.
- `grep -rc "declare module" skills/obsidian-cli/plugin/agent-bridge/` → 0.
