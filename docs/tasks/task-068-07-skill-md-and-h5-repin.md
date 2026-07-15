# Task 068-07: SKILL.md edits + H-5 re-pin

**Phase:** 2 — Docs/security · **RTM:** R-068-8, R-068-9 · **Priority:** High · **Depends on:** 068-06 · **Tag:** [DOC/SECURITY]

## Goal
Extend `skills/obsidian-cli/SKILL.md` with the two new command rows, the Script Contract, the security
tiers/confirmation policy, and — critically — the explicit `command id=` proven-effect carve-out; then
re-pin the H-5 hash so `tests/test_h5_skill_integrity.py` stays green.

## Changes — `skills/obsidian-cli/SKILL.md`
- **Top-20 quick reference:** add rows
  `obsidian command id=agent-bridge:export-selection` → "read the live editor selection" · **T2** and
  `obsidian command id=agent-bridge:apply-edit` → "replace the live selection (guard-gated)" · **T2**.
- **Safety tiers — the `command id=` carve-out (R-068-8, load-bearing):** immediately after the existing
  "`command id=…` defaults to T3, not T2 … whenever the effect cannot be PROVEN from this skill's own
  tier lists" sentence, add a **named exception**: `agent-bridge:export-selection` (T2-read) and
  `agent-bridge:apply-edit` (T2-mutating, guard-gated) are proven-effect exceptions **because this skill
  enumerates their exact effects** (selection I/O + `.obsidian/`-scoped JSON, no proc/net) — without this
  sentence the pinned diff would read as a silent weakening of the `command id=` guard.
- **Security tiers + confirmation policy (R-068-9 / §6/§9):** `selection:read` = T2-read, MEDIUM,
  confirm-first-then-trust per session (`somethingSelected()===false` is always an ASK); `selection:replace`
  = T2-mutating, confidence-gated — no-ask only when the transform verb came from the USER's turn (E-20/
  E-21 absolute), the atomic path+range+`somethingSelected` guard passes, per-file session trust holds,
  and `replaceRange` is used; whole-doc/large-delete re-confirms with char counts even under trust;
  session-trust fail-safe resets on context loss. Selection bodies are untrusted (H-6).
- **The `eval` T3 row:** keep the classification; append "the only sanctioned production selection channel
  is the `agent-bridge` plugin; `eval` is never auto-dispatched for a selection task".
- **Script Contract:** a paragraph for `obsidian_selection.py` (stdlib-only, no `import anthropic`, single
  `_run_obsidian` seam, `read`/`apply` (or `--from-json`), `--format json|path|tsv`, plugin-only /
  never-`eval`, the typed exit codes `0/2/3/4/5/6/7/8/9`, the coherence dispatch marker).
- **Safety Boundaries:** note that selection I/O is the T2 plugin channel; `eval`-selection is refused as
  routine; bodies are untrusted (H-6).
- **References list + Validation Evidence:** add the plugin dir + `scripts/obsidian_selection.py` +
  `tests/test_obsidian_selection.py`.

## Re-pin
- Run `python3 scripts/pin_skill_integrity.py --write` (a reviewable manifest diff of the ONE changed
  contract). `references/recipes.md` is NOT pinned — do not expect it in the diff (068-08).

## Test cases
- **TC-01 (R-068-8):** `tests/test_h5_skill_integrity.py` GREEN post-re-pin
  (`test_every_pinned_hash_matches_the_live_file` in particular).
- **TC-02 (R-068-8):** the SKILL.md diff contains the `command id=` carve-out naming both `agent-bridge:*`
  ids (manual review + grep for `agent-bridge:apply-edit` in SKILL.md).
- **TC-03 (R-068-9):** the two new evals (068-08) pass — cross-checked there.

## Acceptance criteria
- [ ] SKILL.md carries the two command rows, the carve-out, the Script Contract, the §6/§9 policy, and the
      updated `eval` row.
- [ ] `config/skill-integrity.sha256` re-pinned in the same change; `test_h5_skill_integrity.py` green.

## Notes
This is the security-labelled edit R-068-8 exists to make visible. Do NOT touch any other pinned contract.
