# Task 068-01: agent-bridge plugin skeleton (structure + type-check harness)

**Phase:** 0 — Stub-First · **RTM:** R-068-1 · **Priority:** Critical · **Depends on:** none · **Tag:** [STUB CREATION]

## Goal
Land the reviewable, type-checkable skeleton of the `agent-bridge` Obsidian plugin — both commands
registered with plain `callback`s but bodies stubbed — plus the self-contained type-check harness that
makes R-068-1's "type-checks against `obsidian.d.ts`" verification concrete without a global toolchain.

## New files (`skills/obsidian-cli/plugin/agent-bridge/`)
- `manifest.json` — `{"id":"agent-bridge","name":"Agent Bridge","version":"0.1.0","minAppVersion":"1.4.0","description":"Read/replace the live editor selection for an agent in the integrated terminal.","isDesktopOnly":false,"author":"obsidian-llm-wiki"}`.
- `main.ts` — the typed source of truth. `export default class AgentBridge extends Plugin`; `onload()`
  registers `this.addCommand({id:"export-selection", name:"Export selection", callback: () => this.exportSelection()})`
  and `{id:"apply-edit", …, callback: () => this.applyEdit()}` (plain `callback`, **not** `editorCallback`).
  Both method bodies stubbed (e.g. `new Notice("agent-bridge: not implemented")` / `return;`) but
  type-correct against the vendored `obsidian.d.ts`. All future I/O goes through `this.app.vault.adapter`.
- `main.js` — a hand-authored CommonJS mirror of the stub (`"use strict"; ... module.exports = AgentBridge;`),
  loadable by Obsidian with no bundler. Kept in lockstep with `main.ts` (README rebuild discipline).
- `obsidian.d.ts` — a **vendored minimal** ambient declaration file: only the symbols the plugin touches
  (`Plugin`, `App`, `Editor`, `EditorPosition`, `MarkdownView`, `TFile`, `DataAdapter`, `Notice`,
  `Command`, `addCommand`, `vault.adapter.{read,write,exists}`, `workspace.activeEditor`,
  `editor.{getRange,replaceRange,getCursor,somethingSelected,getValue}`, `activeEditor.{file,editor,save,getMode}`).
  ⚠️ **Every declared member MUST carry a REAL (non-`any`) signature** — e.g. `getCursor(string):
  EditorPosition`, `getRange(EditorPosition, EditorPosition): string`, `somethingSelected(): boolean`,
  `save(): Promise<void>`. An all-`any` stub makes `tsc --noEmit` pass **vacuously** (explicit `any`
  escapes `strict`/`noImplicitAny`), which would silently defeat R-068-1's whole point.
- `tsconfig.json` — `strict:true`, `noEmit:true`, `module:"commonjs"`, `target:"ES2018"`, includes
  `main.ts` + the vendored `obsidian.d.ts`.
- `package.json` — dev-only: `{"private":true,"devDependencies":{"typescript":"^5"}}` (local
  `node_modules/` only; **never** `npm install -g`).
- `README.md` — install steps (copy the folder to `<vault>/.obsidian/plugins/agent-bridge/`, enable in
  Community Plugins), the §3.1 **manual "rebuild `main.js` from `main.ts` before commit"** discipline
  (no build-hash tie — accepted residual), and the **OQ1 one-time verification**: after first install,
  confirm the command `callback` actually fires while OS focus sits in the integrated terminal, under
  supervision, before relying on it.

## Changes to existing files
- `.gitignore` — ensure `skills/obsidian-cli/plugin/agent-bridge/node_modules/` is ignored (add if the
  existing `node_modules` rule is not global enough).

## Test cases
- **TC-01 (R-068-1):** from `skills/obsidian-cli/plugin/agent-bridge/`, `npx tsc --noEmit` exits 0
  against the stub. *Fallback (Open Question A, recorded deviation):* if `typescript` cannot be fetched
  in the sandbox, verify every symbol/member referenced in `main.ts` resolves against the vendored
  `obsidian.d.ts` by inspection; re-run under a live `tsc` before merge.
- **TC-02:** `manifest.json` parses as JSON and carries `id`, `minAppVersion:"1.4.0"`, `isDesktopOnly:false`.
- **TC-03:** `node -e "require('./main.js')"` loads without throwing (CommonJS export shape valid).
- **TC-04 (R-068-1 negative control — the harness must actually check):** temporarily introduce a
  deliberate type error against a real signature (e.g. `const b: number = ed.editor.somethingSelected()`)
  and confirm `npx tsc --noEmit` exits **non-zero**; revert. This proves the type-check is live and the
  vendored `.d.ts` is not all-`any` — without it, a green `tsc` proves nothing.

## Acceptance criteria
- [ ] All six plugin files + README exist; `main.ts` registers exactly the two plain-`callback` commands.
- [ ] `npx tsc --noEmit` exits 0 (or the recorded symbol-review fallback is documented).
- [ ] No absolute-path / `require('fs')` access anywhere in `main.ts`/`main.js` (I/O is `app.vault.adapter` only).

## Notes
This is `[STUB CREATION]`: no selection I/O logic yet (068-04 fills it). The stub must already be
type-clean so R-068-1's harness is proven working before Phase 1.
