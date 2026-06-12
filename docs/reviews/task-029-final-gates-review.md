# TASK 029 — final gates (029-07) review

**Date:** 2026-06-12 · **Gates:** skill-validator + `/vdd-multi` (critic-security, critic-logic)
on the skill text + code-review on the full diff, fanned out in parallel.

## Verdicts

| Gate | Verdict | Disposition |
|---|---|---|
| **skill-validator** | **PASS** | All flagged items are documented FALSE POSITIVES: the `curl\|sh` string is the E-09 injection canary (data, not a script); the 8× "eval in shell" warnings are documenting the Obsidian CLI's own `eval` subcommand; the long-line warnings target the generated eval transcript JSON; the missing `scripts/`/`examples/`/`assets/` is the REQUIREMENT (text-only skill). No real malware/structure defect. |
| **critic-security** | CHANGES_REQUIRED → **all fixed** | 1 HIGH + 1 MED + 1 LOW (below). |
| **critic-logic** | CHANGES_REQUIRED → **all fixed/closed** | 2 MED + 2 LOW + 1 INFO (below). |
| **code-review** | CHANGES_REQUIRED → **all fixed** | 1 MED + 1 LOW (below). |

## Findings + fixes

### Security
- **HIGH — Templater/QuickAdd template code-execution.** `template:insert` / `create
  template=` were tiered T2, but a template under a scripting plugin can contain
  executable JS (`<%* tp.user.run('curl|sh') %>`) — an `eval`-equivalent RCE through a
  T2 verb, bypassing the T3 `eval` ban. **Fixed:** SKILL.md + command-reference now state
  these inherit **T3 when a scripting plugin is present** unless `template:read`-verified
  JS-free; added the never-relax eval **E-15** (Templater canary) — both Fable + Sonnet
  PASS (read-verify-first / decline, never blind-apply).
- **MED — `command id=` could be argued into T2.** A friendly palette title doesn't
  reveal a code-running/sync-force-push capability. **Fixed:** `command id=` now
  **defaults to T3** when the effect can't be proven from the tier lists (closes the
  same-effect-different-verb gap, e.g. `community-sync:force-push-all` == T3 sync class).
  E-10 confirms the note-content case; both models cite the T3 default.
- **LOW — `bookmark url=` persists free-text to `.obsidian/bookmarks.json`.** Inert /
  non-executing; T1-UX defensible. **Fixed:** one-line note added (no tier change).

### Logic
- **MED — E-06 graded upsert by bare substring.** A structurally-invalid upsert would
  PASS. Root cause: SKILL.md's coherence bullet showed the *shorthand* `wiki-index-upsert
  <file>` (a positional), which the agent copied. **Fixed:** SKILL.md coherence now shows
  the correct `wiki-index-upsert --vault <vid> --source <ABS>`; E-06 expectation now
  requires `--source`; re-run PASS (agent emits the correct invocation).
- **MED — probe linear-procedure ambiguity.** The headless "do not call obsidian"
  exception sat after step 2 (`obsidian help`). **Fixed:** promoted to **step 0** (a gate
  before any probe).
- **LOW — T1 list missing ~12 read-only commands** (`file`/`folder`/`diff`/`version`/
  `daily:path`/`daily:read`/`base:query`/…). **Fixed:** added (also closes the 029-02
  LOW-2 fail-safe-over-guard nit).
- **LOW — E-01/E-02 don't assert the coherence step.** Accepted as-is: they are
  trigger/routing cases; coherence is asserted explicitly by E-06/E-07. No change.
- **INFO — app-`search` complement vs E-03.** No conflict: E-03 is registered-vault
  (wiki-search-first); the complement carve-out is for unregistered vaults. No change.

### Code-review
- **MED — ARCHITECTURE §2.2 coherence invariant still said `--delta` for rename/move/
  delete**, contradicting DF-029-1. **Fixed:** §2.2 now prescribes `wiki-reindex --full`
  for rename/move (DF-029-1) and `--delta` for delete.
- **LOW — "104 commands" in 3 ARCHITECTURE places.** **Fixed → "102 commands (+ the
  `vault=` option)"** (the deduplicated truth; "104" double-counted `vault=` + `file`).

## Re-verification (post-fix)

- Eval suite **15/15 GREEN** (added E-15; E-06 now requires `--source`; E-09/E-10
  injection canaries re-confirmed PASS on Fable + Sonnet after the safety-section rewrite).
- SKILL.md body 165 lines (≤200 cap); vendor-neutral (0 Claude/Gemini/Cursor hits).
- Scope unchanged: zero `scripts/`/`sql/`/`tests/` touched; **1204 pytest + 4 skipped,
  mypy strict 75 files** (run at 029-07 start; nothing code-side changed since).
- KNOWN_ISSUES ledger 58/58 (DF-029-1 included, auto-rendered).
