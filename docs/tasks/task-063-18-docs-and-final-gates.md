# TASK 063-18 — docs, ADR/ARCHITECTURE, and the FINAL GATES

**Phase**: 5 (acceptance) · **RTM**: all · **Type**: docs + gates · **Effort**: 3h
**Depends on**: 063-00 … 063-17 · **Unblocks**: ship

## Goal

Close the task: documentation that a future reader can act on, and the gates that prove the whole
thing is what it claims to be.

## Docs

- **`CLAUDE.md`** — the CLI census says **"18 `wiki-*` CLIs"**. It is now **19**.
  ⚠️ **This is a denominator claim in the project's own front matter.** Update the count **and** add
  `wiki-extract-decisions` to the *Construct* bullet. Then **grep for every other place the count is
  stated** (`README.md`, `docs/ARCHITECTURE.md`, `commands/`, skill docs) — a count updated in one of
  four places is this project's signature failure, committed against itself.
  ```bash
  grep -rn "18 \`wiki-\*\`\|18 wiki-\|eighteen" --include=*.md . | grep -v docs/tasks/
  ```
- **`README.md`** — the CLI table + quick start.
- **`docs/ARCHITECTURE.md`** (+ the relevant `docs/architectures/` chunk) — the rail's place in the
  conveyor: `wiki-import → meeting-summary → wiki-extract-decisions → typed pages → wiki-graph /
  wiki-health`. Record the **two-config-system split** (names in `sync.yaml`, grammar in
  `layout.yaml`) and the **cross-system load gate** as an architectural invariant, because the next
  person to add a write-side folder key will otherwise re-create the v5 defect.
- **`docs/architectures/open-questions.md`** — Q-063-1 … Q-063-5, with their settled answers and the
  reasoning (especially **Q-063-5 = REFUSE**, not auto-generate: `sync.yaml` must not mutate
  `layout.yaml`).
- **`docs/TASK.md` §7** — ⚠️ **correct the stale "Out of scope: auto-chaining from `wiki-import`"
  line.** It was reversed by the v6 operator requirement (see 063-17). Ship the spec without an
  internal contradiction.
- **`docs/TASK.md` §8 Completion** — fill on ship.

## FINAL GATES (each one is a measurement, not an assertion)

- [ ] **Tests**: `pytest tests/ -q` — **≥ 2477 passed**, 0 failed. Record the new total.
- [ ] **Types**: `mypy --strict scripts/` — clean. Record the file count (was 88).
- [ ] **Zero DDL (I-1)**: `git diff --stat main -- sql/` ⇒ **empty**. `user_version` is still **7**:
      ```bash
      sqlite3 <db> 'PRAGMA user_version;'    # → 7
      ```
- [ ] **Decision-17 (I-2/I-3)**: the globbing test from 063-04/063-17 passes —
      `grep -rn "import anthropic" scripts/wiki_skills/` ⇒ **no hits**, over the whole tree.
- [ ] **The property (063-15)**: both halves green on the cybos sample vault, under
      **`wiki-reindex --full`**. And `grep -rn "\-\-delta" tests/test_extract_decisions_property.py`
      ⇒ **no hits**.
- [ ] **The TASK-058 evolution invariant (the operator's requirement)**: the three `dirs.*` keys are
      live in **`wiki-config show`**, **`report`**, and **`serve`** — verified by *running* them
      against a fixture vault, not by reading the code:
      ```bash
      wiki-config show   --vault-root samples/cybos | grep -c "extract_decisions"   # > 0
      wiki-config report --vault-root samples/cybos -o /tmp/r.html && grep -c "dirs" /tmp/r.html
      curl -s localhost:PORT/api/schema | jq '[.[] | select(.pointer | startswith("/extract_decisions"))] | length'   # → 6
      ```
      and `git log -p --stat` for the whole task shows **zero** changes to `_app_html.py`,
      `_server.py`, `_report.py`, `_report_md.py`. *That is the invariant: a new field, zero interface
      code.*
- [ ] **Dogfood** on the live BD vault zone (read-only first): `prepare` on one real protocol ⇒ inspect
      the envelope ⇒ **do not `apply` until the operator reviews the candidates.** The rail's first
      real run is an operator decision, not a plan step.

## The review lens — run it over the whole diff before declaring done

This project's signature failure mode — **asserting that a mechanism covers a surface without
enumerating the surfaces it actually covers** — has recurred ~25 times, **four of them inside this
spec**. **Every instance was caught by a grep or a mutation test, never by reasoning.**

So, over the final diff:

1. **Every "covers all N" / "one X per Y" claim** in code comments, docstrings, PLAN, TASK and the new
   SKILL.md: does it carry a **grep** that enumerates N from the code? If not, either add the grep or
   **delete the claim**.
2. **Every gate**: run the mutation. *Would this test FAIL if the fix were reverted?*
   **A gate that cannot fail is the disease.** The mutations are listed per bead as `MUT:` — execute
   them, do not trust the list.
3. **Every denominator in an envelope** (`roster_size`, `edges_checked`, `properties_checked`,
   `links_checked`, `open_commitments`, `pages_written`, `edges_authored`): is it **computed** from
   the population, or **restated** from a literal? A restated denominator is a lie with a number
   attached.

## Exit criteria

- [ ] All gates above, executed and recorded (paste the actual numbers into `docs/TASK.md` §8).
- [ ] `wiki-lint --strict` clean on the repo's own dev-project vault (we dogfood our own linter).
- [ ] Code review (`skill-code-review-checklist`) + security audit (`skill-adversarial-security`) on
      the full task diff.
- [ ] `docs/TASK.md` §7 corrected, §8 filled.
