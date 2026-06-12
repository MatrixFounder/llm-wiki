# 030-07 — Docs/skill close-out + final gates (R-030-4)

**RTM:** R-030-4. **UC:** UC-30-4. **Depends:** 030-06.

## Goal
All TEN live surfaces + two design texts updated in lockstep; issues closed with
CORRECTED rationales; final gates run.

## Steps
1. **Issue files (Class A):**
   - `df-029-1-…md` → `status: fixed`; resolution note: new-path predicate;
     the A5 swap/rotation residual named (detectable via `wiki-lint` hash-drift;
     remedy `--full`).
   - `p-1-…md` → `fixed`; Fix-plan line REPLACED with the shipped mechanism
     (chunked caller-owned tx via private txn-free helpers); rejection rationale
     for trigger-drop recorded (runtime DDL / crash-window FTS desync /
     cross-vault `pages_fts`); acceptance line amended per Q-030-1.
   - `r-x1-obsidian-multiglob-rewalk.md` → `fixed`; "Prevention" line corrected
     (ignore-prune is now real, was post-walk filter).
   - `wiki-index-render --auto-indexes` → KNOWN_ISSUES re-rendered (AC-4.2, PW-Q).
2. **Architecture (living docs):** §2.2 coherence invariant → `--delta` for
   rename/move-to-new-path (+ swap caveat + `--full` fallback); §3 summary line;
   `system-architecture.md` §3.5 walk section rewritten (single-pass + descent
   predicate; YAGNI-gate wording → "operator-overridden, built (TASK 030)");
   `functional-architecture.md:213-219` single-tx claim corrected (F-3);
   Q-024-residual-2 amended (A4 resolves the parity gap); ARCHITECTURE status
   block 🔄 → ✅.
3. **ROADMAP:** P2 row (P-1 ✅ + corrected mechanism text); R-12/DF-029-1 wording;
   R-X1-OBS-WALK closure note.
4. **Skill:** `skills/obsidian-cli/` SKILL.md coherence rule + recipes +
   command-reference → `--delta`-first; eval E-07 expectation updated; re-run
   **E-07 + routing canaries only** (Q-030-4) → green, transcript filed under
   `skills/obsidian-cli/evals/reports/`.
5. **Remaining surfaces:** `README.md:421`, `templates/CLAUDE.md.tmpl:295`,
   `templates/CLAUDE.layout.md.tmpl:152`, `docs/manuals/…manual.md:616`,
   `…manual.ru.md:626-627`, **`CLAUDE.md:387-388`** (TASK-029 narrative —
   superseded-by-TASK-030 annotation; the TENTH surface, wraps across lines);
   verify `karpathy.yaml` walk comment still true; document the Q-030-3
   fresh-vault-delta widening in §2.2 or the DF-029-1 resolution note (AC-4.4).
6. **AC-4.1 hard gate (multiline + adjudicated):**
   `rg -iU 'full[^.]{0,60}rename|rename[^.]{0,60}full'` repo-wide. Allowlist:
   archived records (`docs/tasks/`, `docs/plans/`, `docs/reviews/`,
   `.agent/sessions/`, `skills/obsidian-cli/evals/reports/`), test identifiers,
   and the NEW corrected wording ("`--full` universal fallback / swap-class
   remedy"). Every remaining hit individually adjudicated in the close-out notes.
7. **Final gates:** full pytest + mypy strict; per-phase Sarcasmotron already
   done; **post-ship `/vdd-multi`** (critic-logic / critic-security /
   critic-performance → convergence); code-review gate; CLAUDE.md narrative entry
   + auto-memory update; session-state update. **NO auto-commit** (operator rule).

## Acceptance
- ✅ AC-4.1, AC-4.2, AC-4.3, AC-4.4 green; all gates pass; zero-DDL + no-new-deps
  grep guards green (`user_version` 5); P-1 wording uses "per-page commits"
  (arch-review LOW — log-event/step-2.5 commits are fixture-dependent and stay).
