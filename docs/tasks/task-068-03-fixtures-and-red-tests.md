# Task 068-03: deterministic fixtures + the FULL RED test roster

**Phase:** 0 — Stub-First · **RTM:** R-068-4, R-068-5, R-068-6, R-068-7, R-068-10 · **Priority:** Critical · **Depends on:** 068-02 · **Tag:** [STUB CREATION]

## Goal
Author the committed, live-app-free fixtures and the COMPLETE `tests/test_obsidian_selection.py` roster
so every requirement lands RED against the 068-02 stubs (proving the greens in Phase 1 are earned).

## New fixture files (`skills/obsidian-cli/evals/fixtures/selection/`)
- `agent-commands-present.txt` — `obsidian commands` output listing `agent-bridge:export-selection` and
  `agent-bridge:apply-edit` (plus a few realistic core/community ids).
- `agent-commands-absent.txt` — a `commands` listing WITHOUT any `agent-bridge:` prefix (→ exit 9).
- `read-ok.selection.json` — `{ok:true,vault,path,from:{line,ch},to:{line,ch},fromOffset,toOffset,text,mtime,exportedAt,nonce}`.
- `read-ok.result.json` — `{ok:true,mode:"read",nonce,...}`.
- `read-no-editor.result.json` — `{ok:false,reason:"no-editor",nonce}`.
- `read-preview.result.json` — `{ok:false,reason:"preview",nonce}`.
- `read-empty-selection.result.json` — `{ok:false,reason:"empty-selection",nonce}`.
- `apply-ok.result.json` — `{ok:true,mode:"apply",newLen,nonce}`.
- `apply-path-mismatch.result.json` — `{ok:false,reason:"path-mismatch",nonce}`.
- `apply-stale-range.result.json` — `{ok:false,reason:"stale-range",nonce}`.
- `read-stale-nonce.result.json` — a **leftover prior-invocation** result: correct shape,
  `{ok:true,mode:"read",...}`, but a nonce that does **NOT** match the current request's minted nonce
  (exercises the read-back-race guard — decision 2 of the PLAN).
- `b64-vectors.json` — a list of `{plaintext, expected_b64}` where `plaintext` covers Cyrillic (`Привет`)
  + a double-quote + a `\d`-style backslash sequence + a literal newline.

Every `*.result.json`/`*.selection.json` carries the `nonce` the read-back matches on. The test drives
the wrapper by monkeypatching `_run_obsidian` (for `obsidian commands`/`vault info=path`/`command id=…`)
**and** pointing the vault root at a `tmp_path` whose `.obsidian/` is pre-seeded with the chosen fixtures
(so file reads are real but deterministic — no live app).

## New test file: `tests/test_obsidian_selection.py`
Mirror `tests/test_obsidian_active_note.py` (importlib `_load()`, `_runner()` arg-prefix map,
`monkeypatch.setattr(mod, "_run_obsidian", …)`, `shutil.which` patch). Roster (all RED vs stubs):
- **Per-subcommand** happy path: `read` ok, `apply` ok.
- **Per exit code (R-068-4):** one case each asserting `main([...])` returns
  `0` (ok), `2` (usage / payload-too-large), `3` (no-selection reasons), `4` (result timeout / app not
  running), `5` (cli absent), `6` (vault-mismatch via `--expect-vault`), `7` (guard-refused),
  `8` (`WIKI_HEADLESS=1`), `9` (plugin-absent). Each case **also asserts the envelope `reason`** (not the
  exit code alone) — so exit-2 `usage` (argparse) is never conflated with exit-2 `payload-too-large`, and
  no case passes against the stub's out-of-set sentinel `1`.
- **Stale-nonce read-back (R-068-4, the headline race guard):** `test_read_rejects_stale_result` —
  pre-seed `.obsidian/agent-result.json` with `read-stale-nonce.result.json` (ok:true, WRONG nonce); the
  wrapper mints a fresh nonce, dispatches, polls, sees no matching nonce within the (injected, no-op)
  deadline, and returns **exit 4** — it must NOT accept the stale `ok:true` as a false success.
- **Per ladder rung reason (R-068-6):** `no-editor`, `preview`, `empty-selection`, `vault-mismatch`,
  `path-mismatch`, `stale-range`, `plugin-absent` — assert the envelope `reason` value AND a clean
  (non-crashing) return, never a raised stack trace to the caller.
- **base64 (R-068-5):** `test_b64_roundtrip` over `b64-vectors.json` (encode → decode == original,
  utf-8 semantics matching the plugin's `TextDecoder`); `test_no_unencoded_text_reaches_argv` — capture
  every `_run_obsidian` call + the bytes written to `agent-edit.json` during an `apply` and assert the
  raw decoded replacement/path text appears in **neither** (only its base64 form).
- **no-eval (R-068-4):** `test_wrapper_never_dispatches_eval` — across every subcommand/rung run, no
  `_run_obsidian` call has `args[0] == "eval"`; plus a static `"eval"`-as-dispatched-arg grep of the script.
- **coherence marker (R-068-7):** ok+`--wiki-vault` → envelope `coherence.action=="wiki-index-upsert"`
  with the correct `vault` + absolute `source`, present exactly once; ok WITHOUT `--wiki-vault` →
  `coherence.skipped=="vault-not-registered"`; every refusal reason → NO `coherence` key at all.

## Test cases
- **TC-E2E-01:** `pytest tests/test_obsidian_selection.py -q` runs and is **RED** (assertion failures
  against the not-implemented stubs), not an import/collection error.

## Acceptance criteria
- [ ] All fixtures exist and parse; nonces present.
- [ ] The full roster (subcommands, 9 exit codes each asserting `reason`, 7 rung reasons, the stale-nonce
      read-back guard, base64 ×2, no-eval, coherence ×3) is written and RED against the stubs.

## Notes
`[STUB CREATION]`. Determinism mirrors the sibling's committed fixtures — no `obsidian` process is ever
spawned. The nonce short-circuits the read-back poll on the first iteration (fixtures pre-carry the
matching nonce), so tests never sleep.
