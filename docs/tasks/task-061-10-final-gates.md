# Task 061-10 — [GATES] Zero-DDL / additive-envelope / frozen-archive / suite + module memory

RTM: **R-061-1 … R-061-7** (the cross-cutting gates). Depends on: every prior bead.

## Goal

Prove — mechanically, not by assertion — that TASK 061 kept its three structural promises, and
land the module-memory + architecture updates the repo's conventions require.

## 1. Executable gates (add as tests where they don't exist)

| Gate | How |
|---|---|
| **Zero DDL** | `sql/wiki-index-v2.sql` untouched (`git diff --stat` shows nothing under `sql/`), and a test asserting `PRAGMA user_version == 7` on a freshly-applied schema (extend the existing schema test if one exists — grep `user_version` in `tests/`). No new index (P-5). |
| **Additive-only envelopes** | One test per touched CLI (`wiki-health` coverage + ontology, `wiki-lint`) freezing the **pre-061 key set** as a literal and asserting it is a **subset** of the emitted keys. Renames/removals fail. |
| **Frozen archives** | `git diff --name-only origin/main...HEAD \| grep -E "docs/(tasks/task-050\|plans/plan-050)"` → empty; `git diff origin/main...HEAD -- docs/architectures/open-questions.md \| grep -E "^[-+].*Q-050"` → empty (Q-061-* additions only). |
| **Decision-17** | `grep -rn "import anthropic" scripts/` → empty. |
| **Suite + types** | `pytest tests/` fully green; `mypy --strict scripts/` clean. |

## 2. Module memory (repo convention — `.AGENTS.md` per source dir)

- `scripts/wiki_index/.AGENTS.md` — `_health_rules.py` now returns **reports** (three
  denominators, three populations; the legacy list methods are wrappers). `lint.py` gains
  `LintReport` / `run_all_checks_report`. `policy.py` owns `EXTERNAL_PROVENANCE_KEYS` — the ONE
  enumeration, rendered into the `_search.py` `_EXT` SQL half.
- `scripts/wiki_skills/.AGENTS.md` — the new `wiki-health` / `wiki-lint` envelope keys;
  `wiki_config` renders `FieldSpec.description` in `show` + `report` (was `serve`-only).

## 3. Architecture / docs (living, in place)

- `docs/architectures/functional/policy-and-trust.md` — the trust half: one constant, both
  halves; the `_raw/` backstop; Q-061-4's residual. (Body edited in `061-06`/`061-09`; here just
  confirm the section still reads coherently end-to-end.)
- The knowledge-health section (grep `docs/architectures/` for ADR-006 / `wiki-health`) — add the
  **denominator contract**: a report now states what it examined; `total_* = 0` with
  `*_examined = 0` means *nothing was examined*, which is **not** a clean bill of health.
- `docs/TASK.md` §6 **Completion** — fill on ship (what landed, what is still open: Q-061-4,
  TASK 062).

## 4. LIVE confirmatory anchor (operator-run, NOT a CI gate)

On the personal vault (read-only, always exit 0):

```bash
wiki-health coverage --vault <personal> --vault-root <root>   # expect pages_examined: 0 …
wiki-health ontology --vault <personal> --vault-root <root>   # … despite 713 `concept` pages
wiki-lint --vault <personal> --vault-root <root>              # denominators.lifecycle-drift.pages_examined: 0
```

This is the whole thesis, made visible: the layer was **inert**, and now says so. Record the
output in the task's Completion section. (Adoption of typed knowledge on real content is
**TASK 062**, whose prerequisite is this task.)

## Verification

```bash
source .venv/bin/activate
pytest tests/ -q
mypy --strict scripts/
grep -rn "import anthropic" scripts/ ; echo "^ must be empty"
git diff --name-only origin/main...HEAD | grep -E "docs/(tasks/task-050|plans/plan-050)" ; echo "^ must be empty"
```

## Acceptance criteria

- [ ] All five gates in §1 pass, each as a **command whose output is pasted into the commit/PR**.
- [ ] `.AGENTS.md` module memory updated for both touched trees.
- [ ] `docs/TASK.md` §6 filled; `docs/PLAN.md` checklist fully ticked.
- [ ] The LIVE anchor is recorded (or explicitly skipped with a reason).
