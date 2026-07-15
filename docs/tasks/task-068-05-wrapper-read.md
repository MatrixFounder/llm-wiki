# Task 068-05: implement obsidian_selection.py `read`

**Phase:** 1 — Logic · **RTM:** R-068-3, R-068-4, R-068-6 · **Priority:** High · **Depends on:** 068-02, 068-03 · **Tag:** [LOGIC IMPLEMENTATION]

## Goal
Turn the `read` half of `tests/test_obsidian_selection.py` GREEN: feature-detect the plugin, dispatch
`export-selection`, do the nonce-fresh read-back, map ladder reasons to exit codes, and emit the envelope.

## Changes — `skills/obsidian-cli/scripts/obsidian_selection.py`
- **Guards (sibling parity):** `_headless_guard()` (`WIKI_HEADLESS=1` → exit 8) and `_require_cli()`
  (`shutil.which("obsidian") is None` → exit 5) run first.
- **Vault root:** resolve the absolute vault root via `_run_obsidian(["vault","info=path"], base)` (fail
  closed to `EXIT_APP_NOT_RUNNING` if not absolute — sibling `_enrich` idiom); build `<root>/.obsidian/`.
- **Feature-detect:** `_plugin_present()` runs `obsidian commands` and scans lines for the
  `agent-bridge:` prefix; absent → `SelectionError(EXIT_PLUGIN_ABSENT, "install the agent-bridge plugin")`
  (**never** an `eval` fallback).
- **Dispatch + nonce read-back:** mint `nonce = uuid4().hex`; write `.obsidian/agent-request.json =
  {"nonce": nonce, "op": "read"}`; dispatch `_run_obsidian(["command","id=agent-bridge:export-selection"], base)`;
  then `_await_result(nonce)` — a bounded poll of `.obsidian/agent-result.json` that returns the parsed
  result only when its `nonce` matches (short-circuits on immediate match; injectable sleep/clock;
  timeout → `EXIT_APP_NOT_RUNNING`). On a matching `ok:true`, read `.obsidian/agent-selection.json`.
- **`--expect-vault`:** compare the result/selection `vault` to `--expect-vault`; mismatch or unverifiable
  → `EXIT_VAULT_MISMATCH` (6) (fail-closed, mirroring the sibling `_check_vault`).
- **Reason → exit map (R-068-4/R-068-6):** `no-editor`/`preview`/`empty-selection` → `EXIT_NO_SELECTION`
  (3); each surfaced as the envelope `reason`, never a raised stack trace.
- **Envelope + `_emit`:** `{ok, mode:"read", vault, path, from, to, fromOffset, toOffset, text, mtime,
  reason}`; `--format json|path|tsv` (`path` prints the absolute note path; `tsv` a stable column order).
  The selection `text` is documented as untrusted content (H-6) in the module docstring.

## Test cases
- **TC-E2E-01 (R-068-3):** `read` happy path against `read-ok.*` fixtures → exit 0, envelope carries the
  captured `text`/offsets.
- **TC-UNIT (R-068-6):** each rung fixture (`no-editor`/`preview`/`empty-selection`) → exit 3 + the exact
  `reason`; `agent-commands-absent.txt` → exit 9; `--expect-vault` wrong → exit 6.
- **TC-UNIT (R-068-4):** headless → 8, cli-absent → 5, result-timeout → 4.

## Acceptance criteria
- [ ] Every `read`-side test in `tests/test_obsidian_selection.py` is GREEN.
- [ ] The wrapper never dispatches `eval`; plugin-absent is exit 9 with no fallback.
- [ ] `mypy --strict` still clean.

## Notes
`[LOGIC IMPLEMENTATION]`. Reuse the sibling's `_emit`/`_check_vault`/`_require_cli` shapes verbatim where
they fit — this is a sibling wrapper, not a new vocabulary.
