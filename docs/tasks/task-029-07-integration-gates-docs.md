# Task 029-07: Integration, gates & docs close-out `[GATES]`

## Use Case Connection
- RTM **R-029-8** (a–e); acceptance §6.1/2/5/6/7; Q-029-3 (optional I-4.3).

## Task Goal
The skill is integrated (docs surfaces current), all quality gates pass, repo
invariants are proven, and the task narrative is closed out.

## Changes Description

### Changes in Existing Files
- `README.md` — skills table: add `obsidian-cli` row (count update if stated).
- `docs/manuals/obsidian-llm-wiki_manual.md` — Mixed-vault section: one paragraph
  ("live-app ops now scriptable; see skills/obsidian-cli") — locate the exact
  anchor at edit time.
- **Optional (Q-029-3, drop without ceremony):** the obsidian-personal agent
  template (`templates/CLAUDE.layout.md.tmpl` or per `templates/agent-files.yaml`
  routing — inspect first) gains a one-line skill mention.
- `docs/ROADMAP.md` — R-12 entry: status flip to reference TASK 029 (pattern:
  the R-11 "SHIPPED (TASK 018…)" header style) **at ship time**.
- `docs/ARCHITECTURE.md` — status-header TASK 029 block: "IN DESIGN" → shipped
  summary (in place; keep ≤ the current block size).
- `CLAUDE.md` — project-status narrative: append the TASK 029 ship paragraph
  (house pattern; concise).
- `.agent/sessions/` state via `update_state.py` (phase boundary).

## Gates (in order)
1. **Scope check (deterministic)**: `git diff --stat <branch-point>` touches ONLY
   `skills/obsidian-cli/**`, the 2 symlinks, `samples/` (untracked/gitignored),
   `docs/**`, `README.md`, optionally `templates/**` — **zero** `scripts/`, `sql/`,
   `tests/`, `requirements*` paths. Then: full `pytest` green (baseline count,
   unchanged) + `mypy --strict scripts/` clean (both trivially — nothing touched;
   run them anyway as the §6.6 proof) + `grep -r "import anthropic" skills/` empty.
2. **skill-validator** (subagent/skill) on `skills/obsidian-cli/` — full audit
   (structure, security, description quality) → PASS required.
3. **Gold-Standard checklist** (skill-creator) — record per-item disposition.
4. **`/vdd-multi` on the skill TEXT** — critic-logic + critic-security (abuse/
   injection focus: can the skill text be twisted to justify a T3 run? does any
   recipe example leak an unsafe pattern? is the S-1 clause bypassable?);
   critic-performance only if it finds a real surface (bounded outputs, probe cost)
   — convergence or documented-residual required.
5. **code-review** subagent on the full diff (docs + skill text) — MERGE verdict.

## Verification
- All 5 gates recorded (reports under `docs/reviews/` per house convention:
  `task-029-vdd-multi-review.md` etc.).
- §6 acceptance criteria 1–7 checked one-by-one in the close-out note (TASK.md
  gets the final status header, then the archive rotation happens at the NEXT
  task's Analysis per skill-archive-task — do NOT self-archive).

## Acceptance Criteria
- [ ] Scope check + pytest/mypy/anthropic proofs recorded.
- [ ] skill-validator PASS; Gold-Standard dispositions recorded.
- [ ] `/vdd-multi` converged (or residuals documented in docs/issues/ per house rule).
- [ ] Docs surfaces updated (README, manual, ROADMAP, ARCHITECTURE header, CLAUDE.md).
- [ ] Q-029-3 decision recorded (included or dropped).

## Notes
Branch: work happens on `task-029-obsidian-cli-skill` (create at 029-00 if not yet);
ship = leave committed on the branch per house practice (operator merges).
