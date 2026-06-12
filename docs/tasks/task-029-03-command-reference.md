# Task 029-03: Command reference from a FRESH live capture `[LOGIC IMPLEMENTATION]`

## Use Case Connection
- RTM **R-029-5** (a–e); F-1/F-2/F-3/F-8; Q-029-4 investigation; TASK A-4 (durable fixture).

## Task Goal
`references/command-reference.md` catalogs the FULL live surface — every captured
command with params/flags, tier tag, gating tag, and format availability —
version-stamped and provably complete against the capture.

## Changes Description

### New Files
- `skills/obsidian-cli/evals/fixtures/obsidian-help-1.12.7.txt` — the durable
  committed capture (TASK A-4; supersedes the `samples/obsidian-cli-recon/` scratch).
- `skills/obsidian-cli/evals/fixtures/obsidian-commands-1.12.7.txt` — sorted
  command-name list extracted from it.

### File: `skills/obsidian-cli/references/command-reference.md` (replace TODO)
1. **Fresh capture first**: re-run `obsidian help > fixtures/obsidian-help-1.12.7.txt`
   (app already running ⇒ no GUI side effect; do NOT pipe through `head` — the
   Analysis capture was SIGPIPE-truncated once). Extract the command list.
2. **Q-029-4 probe**: re-test `obsidian version` (+ `obsidian help version`); record
   the outcome in an "Anomalies" note (it remains OFF the probe path regardless).
3. **Catalog by category** (the help file's own grouping): per command — syntax,
   params/flags (from help), output `format=` availability incl. the default (F-8;
   "no format= — text only" where absent), tier tag `[T1]/[T1-UX]/[T2]/[T3]`
   (normative source: SKILL.md tier lists; N-2: `sync:status/history/deleted/read` +
   `history`/`history:list/read` = T1, `history:restore`/`sync:restore` = T2,
   `sync on|off` = T3; `reload`≠`restart`≠`plugin:reload` kept distinct), gating tag
   `[core]`/`[plugin-gated]` (observed-missing-from-some-help ⇒ plugin-gated) /
   `[doc-only — unverified]` (web-doc commands NOT in the capture: `publish:*`,
   `unique`, `workspaces`, `workspace:save/load/delete`, `web`, `recents`? — tag
   exactly what the fresh capture says, not this list).
4. **Setup appendix**: macOS (symlink; live-verified marker), Windows (terminal
   redirector; doc-derived marker), Linux (binary copy; doc-derived marker).
5. **Version stamp + re-verify procedure**: "verified against Obsidian 1.12.7,
   macOS, <capture-date>; on an Obsidian minor bump re-capture `obsidian help` and
   diff against `evals/fixtures/obsidian-commands-*.txt`".

## Verification (deterministic)
- Completeness diff (Bash, no repo code) — **DIRECTIONAL, both ways (plan-review
  REC-1)**: with `CAP` = the sorted captured list and `CAT` = the sorted command
  names extracted from the catalog table (extraction regex adapted to the final
  table layout; record the exact command used):
  - `comm -23 CAP CAT` → empty (**no captured command missing from the catalog**);
  - `comm -13 CAP CAT` → empty (**no phantom catalog row absent from the capture**;
    `[doc-only]` entries live in a SEPARATE clearly-marked table excluded from
    `CAT`, so they never mask a one-sided gap).
  The acceptance is the property (1:1 coverage), checked in BOTH directions —
  a symmetric `comm -3` alone could hide a one-sided miss.
- Every catalog row carries BOTH a tier tag and a gating tag (`grep -c` parity).
- `grep -c 'TODO 029-03'` == 0; version stamp present.
- Tier-tag consistency vs SKILL.md lists: every `[T3]`-tagged command appears in
  SKILL.md's T3 list or matches the totality default note (spot-check + record).

## Acceptance Criteria
- [ ] Fresh untruncated capture committed as fixtures (both files).
- [ ] All captured commands cataloged 1:1 (diff empty), each with tier + gating + format info.
- [ ] Q-029-4 outcome recorded in the Anomalies note.
- [ ] Setup appendix with per-platform verification markers; version stamp + re-verify procedure.

## Notes
If the fresh capture differs from the Analysis snapshot (plugins toggled meanwhile),
the FRESH capture wins; note the delta in Anomalies — that's F-2 (dynamic surface)
demonstrated, not an error.
