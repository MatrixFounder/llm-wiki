# Task 068-06: implement obsidian_selection.py `apply` (guarded write-back + coherence marker)

**Phase:** 1 — Logic · **RTM:** R-068-2, R-068-4, R-068-5, R-068-6, R-068-7 · **Priority:** High · **Depends on:** 068-04, 068-05 · **Tag:** [LOGIC IMPLEMENTATION]

## Goal
Turn the `apply` / base64 / no-raw-arg / no-eval / coherence tests GREEN: build the base64 payload, write
it (still encoded) with a nonce, dispatch `apply-edit`, do the nonce-matched read-back, detect success by
shape, map guard failures to exit 7, and emit the coherence dispatch marker.

## Changes — `skills/obsidian-cli/scripts/obsidian_selection.py`
- **Payload assembly (R-068-5):** accept `--expect-b64` + `--replacement-b64` + `--path` (or
  `--from-json FILE` carrying all three). The wrapper keeps them **base64-encoded end to end** — it
  writes `.obsidian/agent-edit.json = {"path": path, "expectB64": …, "replacementB64": …, "nonce": nonce}`
  and dispatches a **fixed** `obsidian command id=agent-bridge:apply-edit`. The decoded selection/
  replacement text therefore reaches **no** subprocess argument (the plugin `TextDecoder`-decodes it).
  `--path` is written into the JSON file, not onto the obsidian argv. **`--path` is VAULT-RELATIVE** (it
  must equal `ed.file.path` for the plugin's GUARD 1); the wrapper resolves the vault root once via
  `obsidian vault info=path` (shared with 068-05) and `os.path.join`s it with `--path` to build the
  absolute `source` for the coherence marker below — the plugin itself never sees an absolute path.
- **Size guard (R-068-4/OQ5):** if `len(expectB64) + len(replacementB64) > 512*1024` →
  `SelectionError(EXIT_USAGE, "payload-too-large — pass --from-json")`, `reason:"payload-too-large"`
  (exit 2). Never truncate. (The temp-file/`require('fs')` hatch stays out of scope, §11.)
- **Dispatch + nonce read-back (the named race design point):** mint `nonce`; write `agent-edit.json`;
  dispatch; `_await_result(nonce)` (shared with `read`) — poll `agent-result.json` until its `nonce`
  matches, else `EXIT_APP_NOT_RUNNING` (4). Success is detected by the result **shape** (`ok===true`),
  **never** by an exit code (ground-truth fact #4).
- **Guard refusals (R-068-2/R-068-6):** result `reason ∈ {path-mismatch, stale-range}` →
  `EXIT_GUARD_REFUSED` (7), envelope carries the reason, **no** re-dispatch (the caller re-reads via
  `read`). `empty-selection` → exit 3.
- **Envelope:** `{ok, mode:"apply", vault, path, newLen, reason}` — **no `from`/`to`** (they are
  meaningless post-replace and the plugin's apply-result never returns them; keeping them would desync the
  fixture and force the wrapper to invent empty fields); `--format` respected.
- **Coherence dispatch marker (R-068-7):** on `ok:true` only — if `--wiki-vault <vid>` is supplied,
  add `coherence: {"action":"wiki-index-upsert","vault":"<vid>","source":"<ABS note path>"}`; if omitted,
  add `coherence: {"skipped":"vault-not-registered"}`. On ANY refusal, **omit** the `coherence` key
  entirely (Decision-17 "omitted, not false"). The wrapper does **not** shell out to `wiki-index-upsert`.

## Test cases
- **TC-E2E-01 (R-068-2):** `apply` against `apply-ok.result.json` → exit 0, `newLen` set, `coherence`
  marker present with the right `source`.
- **TC-UNIT (R-068-7):** ok WITHOUT `--wiki-vault` → `coherence.skipped`; `apply-path-mismatch` /
  `apply-stale-range` → exit 7 + reason + **no** `coherence` key.
- **TC-UNIT (R-068-5):** `test_no_unencoded_text_reaches_argv` GREEN — raw text in neither the argv nor
  `agent-edit.json`; base64 round-trip GREEN; oversize payload → exit 2 `payload-too-large`.
- **TC-UNIT (R-068-4):** `test_wrapper_never_dispatches_eval` GREEN across `apply` too.

## Acceptance criteria
- [ ] Every `apply`-side test is GREEN; success is shape-detected, not exit-code-detected.
- [ ] Base64 both directions; raw text never on an argv; coherence marker present/skipped/omitted per rule.
- [ ] `mypy --strict` clean; no `eval` dispatched under any argument combination.

## Notes
`[LOGIC IMPLEMENTATION]`. The whole roster (068-03) should be GREEN at the end of this task, closing
Phase 1.
