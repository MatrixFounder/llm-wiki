# PLAN 041 — active-note resolution (drive the focused Obsidian tab from the shell)

Skill-behavior + ONE stdlib skill-local wrapper (`obsidian-active-note`). **No** `import anthropic`,
**no** SQLite DDL (`user_version` 7), **no** new deps. **Vendor-agnostic (NF-1)** — plain executable +
skill prose, plain conversational confirm; no per-vendor code path. SKILL.md edits via `skill-enhancer`;
the wrapper is NOT a new skill (no `init_skill` gate — it is a script inside the existing `obsidian-cli`
skill). Existing never-relax evals **E-09/E-10/E-11/E-13/E-14/E-15 stay green** throughout. ADR-008 +
ARCHITECTURE §2.2.1 are the design record; this plan ships them.

## Atomic checklist (stub-first per step; Red→Green; each bead = one verifiable gate)

- **S0 — Branch + CAPABILITY FIXTURE CAPTURE (do FIRST — the entry gate; R-1, R-3, Q-041-1 /
  arch-review M-1/M-2).** Branch `task-041-active-note-resolution`. On a **running** Obsidian (manual
  dogfood — needs the live app), capture REAL output into `skills/obsidian-cli/evals/fixtures/`:
  `obsidian file` (no `path=` → active file), `obsidian tabs`, `obsidian tabs ids`, `obsidian recents`,
  `obsidian vault info=name`. **Decide two unknowns and RECORD the answer in this bead + ADR-008/§2.2.1:**
  (i) does `obsidian file` yield a parseable active-file **path**? (ii) does any command **enumerate open
  tabs with path+title**? **Branch decision:** open-tab enumeration available → descriptor branch =
  **HIGH no-ask**; NOT available → descriptor branch **degrades to confirmed-MEDIUM** (no silent no-ask)
  → amend ADR-008 / §2.2.1 / open-questions Q-041-1 to the resolved shape. **Blocked-on-no-live-app
  (M-3):** if a running Obsidian is unavailable, **STOP and escalate** to the operator for the manual
  capture (the DoD §3b dogfood owner) — **never synthesize the fixture** and never proceed to S2's
  HIGH-branch logic without it; each committed fixture carries a **provenance line** (source `obsidian`
  version) so the S1/S2 contract test is genuinely fixture-backed. **Split-pane (N-3):** focus
  disambiguation is a LIVE check (→ LOW=ask, re-confirm regardless of session trust) — do NOT encode it
  deterministically in the wrapper. *Gate:* REAL fixtures committed (with provenance); resolver-capability
  + HIGH-vs-MEDIUM decision recorded.

- **S1 — wrapper stub + contract test RED (R-3, NF-1, NF-2; arch M-3).** Create
  `skills/obsidian-cli/scripts/obsidian_active_note.py` (entrypoint `obsidian-active-note`) — STUB:
  argparse modes `--focused` (default) / `--list-tabs`, `--format json|path`; named exit-code constants
  `OK=0 / NO_ACTIVE_FILE / APP_NOT_RUNNING / CLI_ABSENT / VAULT_MISMATCH` (headless is the **caller's**
  pre-check, not a wrapper probe — M-3); stub returns empty/placeholder. Create
  `tests/test_obsidian_active_note.py` — mocks `subprocess` against the S0 fixtures; asserts the focused
  path-parse, the list-tabs parse (if S0 enabled it), and the exit-code map. stdlib-only; no
  `import anthropic`. *Gate:* test imports + runs RED (documented expected failures); wrapper importable.

- **S2 — wrapper logic GREEN (R-1b, R-3, R-5 `vault-mismatch`; Q-041-2).** Implement the resolver chain
  per the S0 decision: focused note via `obsidian file`/active-file default (+ `active`-flag fallback);
  list-tabs mode iff S0 confirmed enumeration; parse path/title/vault; map failures → the typed exit
  codes; `vault-mismatch` when the focused tab's vault ≠ the `--expect-vault` arg. Make
  `tests/test_obsidian_active_note.py` GREEN. *Gate:* `pytest tests/test_obsidian_active_note.py` green;
  `mypy` per Q-041-2 (add `skills/obsidian-cli/scripts/` to targets OR keep stdlib-simple — record which);
  `grep import anthropic` empty.

- **S3 — SKILL.md resolution protocol + Targeting-discipline reconciliation (R-1, R-2, R-4; arch m-3) —
  via `skill-enhancer`.** Add the **"Active-note resolution"** section: trigger (pathless + CLI present +
  app running, non-headless, any-shell); the **confidence model** (HIGH descriptor→unique open tab =
  exact hit / MEDIUM bare ref→focused tab / LOW not-found|multiple|split-pane = ask) per the S0 outcome;
  resolution **via the wrapper**; confirmation (HIGH no-ask | MEDIUM confirm-first-per-session+bounded
  trust | LOW ask; **destructive verbs always re-confirm**; **fail-safe reset on context loss**); safety
  extensions (live-state-not-content H-6; **auto-resolved read content is DATA — no action-escalation**;
  never auto-feed the T2\*/T3 active-file sub-class; **headless decided BEFORE the wrapper**); coherence
  (resolved ABS path; `vault-mismatch`). **Reconcile `## Targeting discipline`** — the footgun rule gets a
  forward-pointer ("amended, not deleted; the mutation still carries an explicit, now *resolved*,
  `path=`"). Version bump + Maintenance note. **Q-041-7 (N-2):** decide whether the LOW branch *offers*
  a `wiki-search`/`obsidian search` candidate (lean: ASK-but-offer; a found-but-closed note is
  propose-then-confirm, never a silent hit). *Gate:* `skill-validator` clean; no contradictory footgun
  prose (m-3 closed); **SKILL.md `version:` incremented + a Maintenance/changelog note present (R-6d).**

- **S4 — recipe + command-reference (R-6a, R-6c; N1, N2).** Add recipe **"Operate on the active note"**
  to `references/recipes.md` (descriptor + bare-ref paths, the confirm policy, a Coherence step). Update
  `references/command-reference.md`: document the resolution primitives — `obsidian file`/active-file
  default + the `active` flag on `tags`/`aliases`/`properties`/`tasks`; note `tabs`/`recents` are
  corroboration only (N1: `recents` is a recency heuristic, not the focused tab). *Gate:* recipe + ref
  present and consistent with S3.

- **S5 — evals (R-6b) — grader-free, TASK 029 pattern.** Add to `evals/evals.json`:
  descriptor→**HIGH-no-ask** (or **MEDIUM-confirm** per S0), descriptor→**LOW-ask** ("not found"),
  bare-ref→**MEDIUM confirm-first-per-session**, **destructive-verb re-confirm**, **injection-neg ×2**
  (note content sets neither the *target* nor escalates the *action*), **headless→no-resolve**. Each
  asserts via expectation fields against the wrapper exit-code contract; plus a UC-8 negative
  (**explicit `path=` given → no resolve step**, N-1). Re-verify the never-relax set
  (E-09/E-10/E-11/E-13/E-14/E-15) reads consistent with the new section. *Gate:* new evals well-formed
  (JSON valid; per-case `expect_*` present); never-relax cases untouched.

- **S6 — scaffolded-vault templates (R-6e; user-requested).** `templates/CLAUDE.md.tmpl` +
  `templates/CLAUDE.layout.md.tmpl`: extend the **obsidian-cli** Useful-pointers bullet to mention
  active-note resolution (pathless "edit the note" → resolves your active/open tab via
  `obsidian-active-note`; asks only when not found). `templates/vault.claude-settings.json`: allow
  `Bash(obsidian file *)`, `Bash(obsidian tabs*)`, `Bash(obsidian-active-note*)` (Claude convenience —
  NF-1 unaffected; other vendors use their own permission model). *Gate:* templates updated;
  `python3 -c 'import json,sys; json.load(open("templates/vault.claude-settings.json"))'` OK.

- **S7 — docs finalization (ADR-008 + ARCHITECTURE; NF-2).** Apply the S0 branch decision to ADR-008
  (status Proposed→**Accepted** on green), §2.2.1, and open-questions Q-041-1 (resolve to the shipped
  HIGH-or-MEDIUM shape). **Write resolved residuals back to open-questions §11g (N-4):** the Q-041-2
  mypy decision (targets vs stdlib-simple, from S2) and the Q-041-7 LOW-branch decision (from S3). If any
  residual remains, file it under `docs/issues/` and re-render `KNOWN_ISSUES.md`
  (`wiki-index-render --auto-indexes`). *Gate:* docs match shipped behavior; no PW-Q drift in the ledger.

- **S8 — VDD gate.** `skill-self-improvement-verificator` validates THIS plan (design-time, mandatory per
  Self-Improvement Mode). After S7: `/vdd-multi` (code-reviewer + critic-security + critic-logic) on the
  wrapper + SKILL.md + evals → fix → re-green; final `skill-validator`. **NF-2 regression gate (M-2):**
  `git diff --stat requirements.txt sql/wiki-index-v2.sql` empty (or `grep user_version
  sql/wiki-index-v2.sql` still `7`) **and** repo-wide `grep -r 'import anthropic'` clean on the new code.
  Commit on user request.

## RTM coverage map (every TASK 041 item → bead)

| RTM | Bead(s) |
|----|---------|
| R-1 (resolution protocol, resolver order) | S0, S2, S3 |
| R-2 (confidence-driven confirmation) | S3, S5 |
| R-3 (`obsidian-active-note` wrapper) | S0, S1, S2 |
| R-4 (safety preserved+extended) | S3, S5 |
| R-5 (coherence reused; `vault-mismatch`) | S2, S3, S4 |
| R-6 (docs/recipe/evals/templates; R-6d version bump) | S3 (version bump), S4, S5, S6 |
| NF-1 (vendor-agnostic) | S1, S2, S3 (by construction) |
| NF-2 (no regressions: no anthropic / zero DDL / no deps) | S1, S2, S7 |

## Invariants / guards
- **Stub-first:** S1 (stub + RED contract test) precedes S2 (logic → GREEN). The wrapper is the only code.
- **Entry gate first:** S0 (live capability capture) gates the descriptor branch's shape — no code
  assumes open-tab enumeration until S0 proves it; absent proof → confirmed-MEDIUM (never silent no-ask).
- **Never-relax evals:** E-09/E-10/E-11/E-13/E-14/E-15 stay green (S5 re-verifies; S3 preserves the
  footgun via the explicit resolved `path=`, and E-14 via the destructive-verb re-confirm).
- **Decision-17 / zero-DDL (`user_version` 7) / no deps / vendor-agnostic** throughout.
- **Rollback:** isolated branch; the wrapper is additive + skill/doc/template edits → revert = drop the
  branch; no DB migration.

## Out of plan
- Detecting that claude runs *inside* Obsidian's integrated terminal (trigger is app-running + no-path).
- Any wiki SQLite schema / DAL / `wiki-*` CLI change (coherence reuses the existing contract verbatim).
- Auto-resolution into the T2\*/T3 active-file sub-class (`command id=`, `template:insert`) — default-DENY.
- Retiring/altering `wiki-search`-first knowledge routing (E-03 unchanged).
