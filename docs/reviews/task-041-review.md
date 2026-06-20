# Task Review — TASK 041 (active-note resolution)

- **Date:** 2026-06-20
- **Reviewer:** Task Reviewer (Analysis→Architecture gate, VDD)
- **Target:** `docs/TASK.md` (TASK 041 — active-note resolution)
- **Checklist applied:** `skill-task-review-checklist`, `skill-requirements-analysis`
- **Status:** **APPROVED WITH COMMENTS** — no blocking (🔴) issues; 4 MAJOR + 4 MINOR to fold in during/before Architecture.

## General assessment

A well-structured spec. The RTM has 6 requirements (R-1..R-6), every one carries ≥3
concrete sub-features, and the three locked user decisions are faithfully encoded:
confirm-first-per-session-then-trust (R-2), skill-enhancement + convenience wrapper
(R-3 / Scope), and trigger = app-running + CLI-present + no-path from any shell, NOT
gated on detecting the integrated terminal (R-1, Scope "Out of scope", UC-8). The spec
also does the hard reconciliation work the original request implies — it confronts the
existing **Targeting discipline** "silent footgun" rule head-on and turns it into a
resolve-show-confirm path while keeping the *actual* mutation on an explicit `path=`
(R-1c, R-4d). Critically, it does NOT relax any never-relax eval: E-09/E-10/E-13/E-15
and the E-11 footgun are named as must-stay-green (R-4, R-6, DoD §2), and the H-6
"resolve from live app state, never from note content" rule is explicit (R-4a, UC-6).

The issues below are completeness/accuracy gaps, not contradictions with the skill's
safety posture.

## Comments

### 🔴 CRITICAL
None. No requirement, as written, would break a never-relax eval or a CLAUDE.md
invariant if implemented literally.

### 🟡 MAJOR

- **M1 — The resolution chain ignores the most direct, deterministic resolver the
  live fixture already documents.** R-1b and Q-041-1 frame resolution as
  `obsidian tabs` (focused tab) → `recents` top → active-file default, and call the
  "does `tabs` mark the focused tab?" question a *feasibility hinge* to be "resolved
  live." But the committed help fixture
  (`skills/obsidian-cli/evals/fixtures/obsidian-help-1.12.7.txt`) already answers a
  large part of it:
  - line 10: *"Most commands default to the active file when file/path is omitted"*;
  - `file` ("Show file info", L117) takes no required arg → defaults to the active file;
  - `tags`/`aliases`/`properties`/`tasks` each expose an explicit **`active`** flag;
  - `tabs` (L344) exposes **only** `ids` — **no documented focus marker**, which makes
    `tabs` the *weakest* (not the leading) signal for the focused note.

  So the most likely deterministic resolver is "ask the app for the active file's path
  directly" (`obsidian file` / a read command's active-file default, or an
  `active`-flagged read), with `recents`/`tabs` as *fallbacks/cross-checks* — the
  inverse of the order the TASK leads with. **Fix:** reorder R-1b's probe chain to
  lead with the active-file-defaulting / `active`-flag read commands and demote `tabs`
  to a corroboration/disambiguation signal; restate Q-041-1 accordingly. The wrapper
  contract (R-3, Q-041-4) should pin the chosen command order.

- **M2 — Active-note content-read is unprotected against the H-6 action-escalation
  vector the feature opens.** UC-3 / R-2c make active-note **reads** never prompt
  (correct for the read) — but the feature's value is that the agent then *acts on
  what it read*. The note body is untrusted (H-6); once auto-resolved and read with no
  prompt, an embedded instruction ("also append X to Y", "run command id=…") is the
  E-09/E-10/E-15 attack surface with one fewer human checkpoint. R-4a/UC-6 cover "note
  content cannot set the *target*", not "content cannot escalate the *action*."
  **Fix:** add a sub-feature stating auto-resolved read content is DATA — it cannot
  introduce a new mutation target, a new verb, or a T2*/T3 op; any action beyond the
  user's literal request still goes through normal tiering/confirmation. Add an
  injection-neg eval for action-escalation.

- **M3 — "Confirm once per session, then trust" has no bound on what the single
  confirmation authorizes.** R-2b waves through later mutating active-note ops after
  one yes — unbounded, so a yes on `append` could later wave through a `delete`/`move`
  without re-prompting, colliding with E-14 (trash-first must be stated+confirmed) and
  per-op confirmation for destructive verbs. **Fix:** scope session-trust to
  *non-destructive single-file content* mutations (append/prepend/property:set/task) on
  a *consistently-resolved* path; require fresh confirmation for
  `delete`/`move`/`rename`/`history:restore` of an auto-resolved target. Reference E-14.

- **M4 — Two acceptance criteria are not objectively verifiable.** DoD §3 ("live
  dogfood … prints the correct focused-tab path") depends on a human-operated Obsidian
  and the unresolved Q-041-1 — not CI-assertable. DoD §6 is conditional ("If ADR-008 is
  adopted…") so it is not a pass/fail gate. **Fix:** split §3 into (a) a deterministic,
  mockable contract test of the wrapper's parse + typed-exit-code map (assertable
  against a captured `file`/`tabs` fixture) and (b) a separately-noted manual dogfood
  smoke step; make ADR-008 a firm deliverable or move §6 to follow-ups. Tie the new
  evals in §1 to the concrete wrapper exit-code contract.

### 🟢 MINOR

- **N1 — `recents` as a focus proxy is unsound.** `recents` (L271) lists *recently
  opened* files; the most-recent is not necessarily the *focused* tab. Flag it as a
  heuristic, not a truth source (reinforces M1's reorder).
- **N2 — The `active`-flag read commands + global active-file default are missing from
  the doc-update scope.** R-6c only mentions `tabs`/active-file; widen it to the
  `active` flag on `tags`/`aliases`/`properties`/`tasks` and the fixture-L10 default.
- **N3 — Multi-vault wrapper exit code for "focused window is a non-wiki / unexpected
  vault" is unspecified.** R-3c enumerates no-active / app-not-running / headless /
  cli-absent; add the cross-vault case to Q-041-4 so an eval can assert it.
- **N4 — Confirmation-state persistence is conversation-only; make the failure mode
  explicit.** If the session/context is lost (compaction, new invocation), the policy
  must reset to "confirm again" — fail-safe, never silently inherit trust.

## Invariant / never-relax check (explicit)

- **E-09 / E-10 / E-15 (injection, never-relax):** preserved by R-4a/R-4b + UC-6; M2
  strengthens the action-escalation edge. OK with M2.
- **E-13 (headless degradation, never-relax):** preserved — R-1 gates on app-running;
  R-4c mandates no-probe-no-resolve in headless/CI; DoD §1 adds a headless eval. OK.
- **E-11 (footgun):** kept green — R-1c/R-4d require the actual mutation to carry an
  explicit resolved `path=`. OK.
- **E-14 (trash-first / permanent delete):** at risk only via M3's unbounded
  session-trust; fix M3 to preserve it.
- **E-03 (wiki-search-first, never-relax):** preserved — Scope + UC-3. OK.
- **CLAUDE.md invariants:** no `import anthropic`, zero-DDL/`user_version` 7 untouched,
  H-6 untrusted content (R-4a + M2). OK.

## Open-questions audit

Q-041-1..6 are genuine ambiguities, not placeholders for decided items, and do NOT
re-open the three locked decisions. Caveat: Q-041-1 overstates the uncertainty (M1) and
Q-041-6 (ADR-008) is left lean-yes that DoD §6 then makes conditional (M4). Tighten both.

## Recommendation

**APPROVED WITH COMMENTS.** Proceed to Architecture. Fold M1–M4 into `docs/TASK.md`
(M1 reorder + M2 action-escalation guard are the most load-bearing; M3 preserves E-14;
M4 makes the gate checkable). N1–N4 absorb in the same edit. No blocking issues.
