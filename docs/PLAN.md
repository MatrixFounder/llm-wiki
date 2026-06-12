# Development Plan: TASK 029 — `obsidian-cli` skill (R-12)

> **Status**: **APPROVED (2026-06-12)** — plan-review APPROVED WITH COMMENTS
> (REC-1 directional `comm` check → 029-03; REC-2 eval loop cap → 029-05;
> REC-3 either-or AC clarification → 029-06; NIT-1/2/3 → 029-01/00/02 — all folded).
> **Task ID**: 029 / Slug: `task-029-obsidian-cli-skill`
> **Source spec**: [docs/TASK.md](./TASK.md) (RTM R-029-1..8; UC-29-1..6; recon facts F-1..F-9; Q-029-1..5) — task-review APPROVED (4 REC + 4 NIT folded in).
> **Architecture spec**: [docs/ARCHITECTURE.md](./ARCHITECTURE.md) status block + **§2.2 Native-App Control Skill** (four invariants: routing / coherence / safety / degradation) + §7 note + Q-029-1..5 — architecture-review APPROVED (S-1 active-file clause folded into §2.2 AND RTM R-029-3e as a **binding** constraint; N-1/N-2 folded).
> **Methodology**: **Stub-First-analogous, green-throughout** (the TASK 009 prompt-task mapping):
> **Phase 1** = scaffold the skill skeleton + author the **eval set FIRST** (the "tests"; machine-checkable expectation fields per Q-029-1) — the RED state is the skeleton failing its own structural validation + the eval expectations having no skill content to satisfy them. **Phase 2** = author the content (SKILL.md core → command-reference → recipes), then **GREEN** = the agentic eval run + the live dogfood + the gates. The repo's deterministic suite (1204+4 pytest, mypy strict) stays green at every bead boundary **trivially** — zero code is touched; bead 029-07 proves it (`git diff` scope check).
> **Predecessors**: TASK 025/026/027 (adoption surface), TASK 009 (eval-harness pattern), live recon 2026-06-12 (Obsidian 1.12.7, 104-command capture, `samples/obsidian-cli-recon/`).
> **Unblocks**: the P3 "wiki-graph export" item shrinks to export-only (live graph reads come free); future MCP wrapper (out of scope).
> **Out of scope** (TASK §8): MCP server; Obsidian Headless; mobile; replacing wiki-search/RAG; auto-enabling T3; scripting Windows setup; Python eval grader (Q-029-1 default NO).

---

## 0. Architectural Foundation (Reference)

| Layer | Owns | Class / note |
|---|---|---|
| `skills/obsidian-cli/SKILL.md` | The dispatch core: probe → target → route → act → cohere; the four §2.2 invariants in skill-text form | **SECURITY-SENSITIVE** prompt surface (loaded verbatim into agent context); vendor-agnostic wording |
| `skills/obsidian-cli/references/command-reference.md` | The full live-verified catalog (104 commands × tier tag × gating tag × format availability) + per-platform setup appendix | version-stamped "verified against Obsidian 1.12.7, macOS, 2026-06-12" |
| `skills/obsidian-cli/references/recipes.md` | ≥8 composed playbooks (preconditions / exact commands / coherence step / failure handling) | every mutating example carries explicit `path=` + `vault=` |
| `skills/obsidian-cli/evals/` | `evals.json` (≥12 cases, expectation fields), `README.md` (per-class deterministic grading checklist), `reports/` (eval run + dogfood transcripts), the durable help-capture fixture (A-4) | **Committed** (NOT `samples/` — CLAUDE.md convention) |
| `/usr/local/bin/obsidian` (the official CLI) | The deterministic plumbing layer (Decision-17 generalised — §2.2) | external binary; NOT wrapped, NOT vendored |
| `scripts/`, `sql/`, DAL, schema | — | **UNTOUCHED** (zero DDL, zero new Python — proven by 029-07 scope check) |

**Binding invariants carried from the two review gates** (every content bead must hold them):
1. **Routing invariant** (§2.2-1): wiki-search/wiki-query FIRST for knowledge — restated verbatim in SKILL.md; app `search` positioned as complement only.
2. **Coherence invariant** (§2.2-2): same-turn `wiki-index-upsert` (content change) / `wiki-reindex --delta` (rename/move/delete); self-disables on unregistered vaults.
3. **Safety invariant** (§2.2-3, TOTAL): T1 (+T1-UX) / T2 (explicit `path=` REQUIRED — F-4; trash-not-permanent; existence-check before `overwrite`; `base:create` named) / T3 banned-by-default (`eval`, `dev:*`, `devtools`, `plugin:*` incl. `plugin:reload`, `plugins:restrict`, `theme:*` mutations, `snippet:enable/disable`, `sync on/off`, `restart`/`reload`); **S-1 (binding)**: `command id=` + `template:insert` act on the ACTIVE-FILE context (no `path=` exists) → default-DENY on unnameable effect + verify/confirm the active file first; unenumerated → **T2-with-confirmation** (fail-safe); N-2: `sync:*`/`history:*` READ family is T1, `*:restore` is T2 — no over-ban by pattern.
4. **Degradation invariant** (§2.2-4): probe = `command -v obsidian` + `obsidian help` (**never `version`** — F-3); plugin-gated commands feature-detected via `obsidian help <command>` (F-2); headless/CI → announced fallback, no silent GUI launch.
5. **Untrusted-output posture**: all CLI output is vault content (H-6 class); instructions found in it are NEVER executed.
6. **Eval determinism without a grader** (Q-029-1): every case carries `expect_routes_to` / `expect_command_substring` / `expect_command_absent` / `expect_refusal` / `expect_tier_cited` fields; README defines the per-class checklist.

---

## 1. RTM → Bead Checklist (one RTM item = one checklist item)

Phase-1 (skeleton + eval set = RED) ──────────────────────────────────────────
- [ ] **[R-029-8a/b-part]** Scaffold `skills/obsidian-cli/` skeleton + vendor symlinks (structure exists; skill-validator structural RED recorded) → **029-00**
- [ ] **[R-029-7]** `evals/evals.json` (≥12 cases, 5 classes, expectation fields) + `evals/README.md` grading rubric — the test suite, authored BEFORE the skill content → **029-01**

Phase-2 (content → GREEN → gates) ────────────────────────────────────────────
- [ ] **[R-029-1]** SKILL.md core: probe/degradation + target discipline + top-20 + disclosure → **029-02**
- [ ] **[R-029-2]** Decision matrix + routing invariants (wiki-search-first verbatim) → **029-02**
- [ ] **[R-029-3]** TOTAL safety tiers incl. S-1 active-file clause + totality rule → **029-02** (tier TAGS land in 029-03)
- [ ] **[R-029-4]** Mutation→index coherence protocol → **029-02** (recipe-level steps in 029-04)
- [ ] **[R-029-5]** `references/command-reference.md` from a FRESH live capture (tier+gating tags, format availability, setup appendix, durable fixture) → **029-03**
- [ ] **[R-029-6]** `references/recipes.md` ≥8 playbooks → **029-04**
- [ ] **[R-029-7-run]** Agentic eval run — all cases PASS, report filed (GREEN) → **029-05**
- [ ] **[AC §6.4]** Live dogfood: UC-29-1 + UC-29-5 hard; UC-29-2/3/4 happy-or-degraded; transcripts filed → **029-06**
- [ ] **[R-029-8]** Integration (README/manual/optional I-4.3) + gates (skill-validator, Gold-Standard, `/vdd-multi`, scope check) + docs close-out → **029-07**

> **Grouping note (for the plan-reviewer):** R-029-1/2/3/4 all land in the single
> SKILL.md edit (029-02) because they are **one cohesive prompt artifact** (the same
> file's sections; their combined effect is only measurable by the 029-05 eval run) —
> splitting per-section would create bead boundaries with no independent verification.
> Each stays a distinct traceable checklist item with its own acceptance criterion in
> the 029-02 spec — this is cohesion, not feature-grouping (the plan-009 precedent).

---

## 2. Bead Sequence & Dependency Graph

```
029-00  scaffold + symlinks (skeleton; structural RED)   (R-029-8a/b) ──┐
029-01  evals.json + grading README (the tests, first)   (R-029-7)    ──┴─ Phase 1
          │
029-02  SKILL.md core (4 invariants in skill text)  (R-029-1/2/3/4)  ──┐
029-03  command-reference (fresh capture → catalog)  (R-029-5)         │
029-04  recipes (≥8 playbooks)                       (R-029-6)         ├─ Phase 2
029-05  agentic eval run → GREEN (loops to 02..04)   (R-029-7-run)     │
029-06  live dogfood (UC-29-1/5 hard; 2/3/4 either)  (AC §6.4)         │
029-07  integration + gates + docs close-out         (R-029-8)        ──┘
```

| Bead | Depends on | Verification kind |
|---|---|---|
| 029-00 | — | deterministic (paths/symlinks exist; skill-validator structural run recorded as RED) |
| 029-01 | 029-00 (dir exists) | deterministic (JSON parses; every case carries class + ≥1 expectation field; 5 classes covered; canary present) |
| 029-02 | 029-01 (expectations pin the content claims) | checklist vs RTM claim-sites + skill-validator structural PASS |
| 029-03 | 029-00; fresh capture at authoring time | **deterministic diff**: every command in the captured list appears exactly once in the reference with a tier tag (grep/comm check) |
| 029-04 | 029-02 (protocol wording), 029-03 (command facts) | checklist per recipe + grep guard (no mutating example without `path=`) |
| 029-05 | 029-02 + 029-03 + 029-04 | **orchestrator-graded, recorded** (per-case PASS/FAIL vs expectation fields; loops to 029-02..04 on FAIL) |
| 029-06 | 029-05 (eval-green skill) | **live, recorded** (transcripts + `wiki-lint` orphan-count parity for UC-29-1) |
| 029-07 | 029-06 | subagent gates (`skill-validator`, `/vdd-multi` logic+security) + deterministic scope check (`git diff --stat` touches no `scripts/`/`sql/`; full pytest+mypy untouched-green) |

---

## 3. Per-Bead Detail Files

- [029-00 — Scaffold skeleton + vendor symlinks](./tasks/task-029-00-scaffold-skeleton.md)
- [029-01 — Eval set + grading rubric (the tests, first)](./tasks/task-029-01-eval-set.md)
- [029-02 — SKILL.md core (the four invariants)](./tasks/task-029-02-skill-core.md)
- [029-03 — Command reference from fresh live capture](./tasks/task-029-03-command-reference.md)
- [029-04 — Recipes (composed playbooks)](./tasks/task-029-04-recipes.md)
- [029-05 — Agentic eval run (GREEN gate)](./tasks/task-029-05-eval-run.md)
- [029-06 — Live dogfood (UC acceptance)](./tasks/task-029-06-live-dogfood.md)
- [029-07 — Integration, gates & docs close-out](./tasks/task-029-07-integration-gates-docs.md)

---

## 4. Stub-First Phasing (mapped to a prompt task)

| Stub-First concept | TASK 029 realisation |
|---|---|
| **Phase 1 — Interfaces/Stubs + RED tests** | 029-00 (skeleton = the "stubs": frontmatter + section headers + empty contracts; skill-validator structural run = recorded RED) + 029-01 (evals.json = the "tests", authored before any skill content exists; expectation fields are the assert surface) |
| **Phase 2 — Implementation → GREEN** | 029-02/03/04 (the content = the "implementation") + 029-05 (agentic eval run = GREEN) + 029-06 (live dogfood = the E2E acceptance) |
| **Green-throughout** | The repo's deterministic suite is untouched at every boundary (zero code); 029-07's scope check is the proof; skill-validator re-run per content bead |
| **No mocking LLMs** | 029-05 runs real fresh-context sub-agents loading the skill (no recorded outputs); grading is deterministic against the per-case expectation fields (Q-029-1) |

---

## 5. Open Questions carried into Development

- **Q-029-1 (resolved):** no Python grader in v1; expectation-field grading per `evals/README.md`.
- **Q-029-2 (resolved):** Universal-skills cross-publication deferred; 029-02 keeps the skill standalone-capable.
- **Q-029-3 (029-07 decides):** the optional `wiki-init` template mention (I-4.3) — include if the bead is cheap at close-out; drop without ceremony otherwise (non-MVP).
- **Q-029-4 (029-03 investigates):** the `version` listed-but-unrunnable anomaly — re-test during the fresh capture; outcome feeds the `[doc-only]`/anomaly note in the reference. The probe avoids `version` regardless.
- **Q-029-5 (resolved):** `tier: 2` frontmatter.
- **Regression policy (029-05/06):** an eval FAIL or dogfood failure loops back to the owning content bead (029-02 routing/safety wording; 029-03 command facts; 029-04 recipe steps) — never weaken an expectation to pass; the injection canary and the wiki-search-first case may NEVER be relaxed.
