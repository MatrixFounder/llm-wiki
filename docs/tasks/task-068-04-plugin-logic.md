# Task 068-04: implement the agent-bridge plugin (export-selection + apply-edit)

**Phase:** 1 — Logic · **RTM:** R-068-1, R-068-2 · **Priority:** Critical · **Depends on:** 068-01 · **Tag:** [LOGIC IMPLEMENTATION]

## Goal
Replace the 068-01 stubs with the real selection-read and guarded selection-replace logic in `main.ts`,
and hand-author the byte-equivalent CommonJS `main.js`. All I/O via `app.vault.adapter` under `.obsidian/`.

## Changes — `main.ts` (and mirror into `main.js`)
- **`exportSelection()` (command `export-selection`):**
  - Read `const ed = this.app.workspace.activeEditor`. If `!ed || !ed.editor || !ed.file` → write a
    result `{ok:false, reason:"no-editor", nonce}` and return (no throw).
  - If `ed.getMode?.() === "preview"` → `{ok:false, reason:"preview", nonce}`.
  - Else capture `from=editor.getCursor("from")`, `to=editor.getCursor("to")`,
    `fromOffset=editor.posToOffset(from)`, `toOffset=editor.posToOffset(to)`,
    `text=editor.getRange(from,to)`, `vault=this.app.vault.getName()`, `path=ed.file.path`,
    `mtime=ed.file.stat.mtime`, `exportedAt=Date.now()`, and the `nonce` read from `agent-request.json`.
  - `somethingSelected()===false` → still write `{ok:false, reason:"empty-selection", nonce}` (the wrapper
    turns this into an ASK — never a silent empty read).
  - Write `.obsidian/agent-selection.json` (the capture) and mirror the outcome to
    `.obsidian/agent-result.json` **last** (so the wrapper's nonce read-back never sees a half-written file).
- **`applyEdit()` (command `apply-edit`):**
  - Read + JSON-parse `.obsidian/agent-edit.json` → `{path, expectB64, replacementB64, nonce}`.
    **The payload carries NO `from`/`to`** — see the concurrency note below.
  - Decode `expect`/`replacement` from base64 via `Uint8Array` + `TextDecoder("utf-8")` (NEVER `atob`,
    ground-truth fact #6).
  - `const ed = this.app.workspace.activeEditor`. If `!ed || !ed.editor || !ed.file` →
    `{ok:false, reason:"no-editor", nonce}`; if `ed.getMode?.()==="preview"` →
    `{ok:false, reason:"preview", nonce}`; if `!ed.editor.somethingSelected()` →
    `{ok:false, reason:"empty-selection", nonce}` (checked BEFORE the range guards — no selection means
    no live `from`/`to` to compare).
  - **Derive the coordinates from the LIVE selection at apply time:**
    `const from = ed.editor.getCursor("from"), to = ed.editor.getCursor("to")`.
  - **GUARD 1** `payload.path === ed.file.path` else `{ok:false, reason:"path-mismatch", nonce}`;
    **GUARD 2** `ed.editor.getRange(from,to) === expect` else `{ok:false, reason:"stale-range", nonce}`.
    On ANY guard failure: write the refusal result and return **without touching the buffer**.
  - All guards pass → `ed.editor.replaceRange(replacement, from, to)` (**never** `vault.modify`), then
    `await ed.save()`, then write `.obsidian/agent-result.json = {ok:true, mode:"apply", newLen:
    replacement.length, nonce}` **last**.
  - **Optimistic-concurrency semantics (load-bearing — do NOT source `from`/`to` from the payload):**
    `from`/`to` are recomputed from the CURRENT selection every apply; GUARD 2 then compares the current
    selection's `getRange(from,to)` against the `expect` captured at read time. This is precisely what
    makes "caret moved / re-selected / line edited since the read → `stale-range` refusal" real. Sourcing
    `from`/`to` from the payload would make GUARD 2 tautological and would replace at stale coordinates.

## Constraints
- Only `this.app.vault.adapter.{read,write,exists}` for file I/O — no absolute paths, no `require('fs')`,
  no `child_process`, no network (this is the whole least-privilege argument vs `eval`).
- Commands stay plain `callback` (read `activeEditor` inside), not `editorCallback`.

## Test cases
- **TC-01 (R-068-1):** `npx tsc --noEmit` from the plugin dir exits 0 (or the recorded fallback).
- **TC-02 (R-068-2):** manual inspection / grep: `replaceRange` present, `vault.modify` absent,
  `save()` awaited **after** `replaceRange`, result mirrored on every branch, no fs/child_process/network.
  (The guard/refusal *behaviour* is exercised end-to-end by the Python fixtures in 068-03 via the
  pre-seeded `agent-result.json` rungs — the plugin has no live-app test, per the design brief.)

## Acceptance criteria
- [ ] `export-selection` + `apply-edit` implemented with GUARD 1/GUARD 2/`somethingSelected`,
      `replaceRange`+`await save`, every outcome mirrored to `agent-result.json` with the nonce echo.
- [ ] `main.ts` type-checks clean; `main.js` is a faithful CommonJS mirror; I/O is `app.vault.adapter` only.

## Notes
`[LOGIC IMPLEMENTATION]`. The nonce is echoed from `agent-request.json`/`agent-edit.json` so the wrapper
can distinguish this dispatch's result from a stale prior one (the named read-back-race design point).

**Residual (weakest verification link — disclose honestly, carry to §2.2.2 in 068-09):** the plugin's
guard *logic itself* (the JS `getRange(from,to) === expect` comparison, the live `getCursor` derivation,
the `replaceRange`→`await save` ordering) has **no executable test runtime** in this repo — there is no
headless Obsidian/CM6 harness. The Python fixtures in 068-03 simulate the plugin's *output*
(pre-seeded `agent-result.json` per rung), NOT its internal logic. So this JS is covered only by
`npx tsc --noEmit` (types) + code inspection (TC-02) + the one-time on-install manual verification (OQ1).
This is an accepted, documented residual, not an oversight.
