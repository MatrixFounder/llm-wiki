# TASK 063-16 — `decision-extraction` SKILL.md + the named eval set

**Phase**: 5 (acceptance) · **RTM**: R-063-6, R-063-7 · **Type**: docs + fixtures · **Effort**: 3–4h
**Depends on**: 063-05, 063-06 · **Unblocks**: 063-18

## Goal

The **REASON contract** — the one step the CLI deliberately does not perform (Decision-17). It lives at
`skills/decision-extraction/SKILL.md`, with a durable eval set at `skills/decision-extraction/evals/`
(per CLAUDE.md: durable fixtures live with the **owning skill**, never in `samples/`).

## Content — map the protocol's EXISTING sections, don't free-form extract

The source protocols already have the structure. The contract **binds to it**:

| protocol section | class |
|---|---|
| «Ключевые решения» | `decision` |
| НФТ / KPI | `requirement` |
| «Реестр рисков» | `risk` |

Free-form extraction over a structured document invents structure that is already there — and
inventing is the failure mode this whole task is defending against.

## ★ The warning that stops the rail feeling flaky

> **BARE IDs IN PROSE ARE REFS on cybos.** `DEC-004`, `REQ-012`, `ADR-7`, `R-15`, `task-63` **all**
> match the layout's `id-ref` regex — so a sentence like *"это отменяет DEC-004"* creates a ref that
> **must resolve**, or `apply` refuses the batch on G2.
>
> **Guidance to REASON:** reference other pages **only** via wikilinks to slugs that exist or are in
> the same batch. **Never cite a bare ID.**

Without this warning, well-written prose bounces the batch on G2 repeatedly and the operator
experiences the rail as **flaky** — a correct gate producing an unusable product.

## ★ The anti-fabrication contract, stated to the model

- An empty extraction is **SUCCESS**. `decisions: []` is a legitimate, correct answer.
- Every candidate MUST carry a **verbatim `source_quote`** from the source body.
- **An unimplemented `requirement` is a `wiki-health coverage` gap = DATA, always exit 0 — NOT a
  defect to close.** Say it in the SKILL, or the model will "helpfully" invent a closing decision so
  that nothing looks unfinished. `apply` reports `open_commitments: N` as an **output**, so gaps read
  as the deliverable they are.

## Eval set — `skills/decision-extraction/evals/`

| fixture | input | expected |
|---|---|---|
| `01-meeting-with-decisions/` | a protocol with «Ключевые решения» | 3 decisions, 2 requirements, 1 risk — with quotes |
| `02-deferred-no-decisions/` | ★ **the NEGATIVE fixture** — a transcript that explicitly *defers* («отложили», «вернёмся к этому») | **`decisions: []`**, exit 0 |
| `03-supersede/` | a protocol that overturns a prior decision | one decision with `supersedes:` → an existing slug |
| `04-bare-id-in-prose/` | prose citing `DEC-004` | expected: a **wikilink**, not a bare ID (the SKILL's rule, demonstrated) |

**Fixture 02 is not optional.** It is the mechanism from R-063-7 in fixture form: it proves that "no
decisions" is a reachable, rewarded outcome. Without it, `CANDIDATE_COUNT_MIN = 0` is a constant no
eval ever exercises.

## Context — files

- **New** `skills/decision-extraction/SKILL.md` (+ symlink into `.claude/skills/`, `.agent/skills/`
  per CLAUDE.md).
- **New** `skills/decision-extraction/evals/{01..04}/{input.md, expected.json}`.
- **Read (precedent)** `skills/concept-extraction/SKILL.md`; `skills/wiki-import/evals/` for the
  eval-fixture layout.

## Tests — `tests/test_decision_extraction_evals.py` (new)

- `test_every_eval_expected_output_passes_apply_validation` — feed each `expected.json` through the
  **real** `_validation` + `validate_ontology` + `validate_refs` ⇒ **zero violations**.
  *An eval whose own expected output the rail would refuse is worse than no eval.*
- `test_negative_fixture_is_success` — fixture 02's `expected.json` (`[]`) ⇒ **exit 0**,
  `action: no_candidates`. **MUT:** `CANDIDATE_COUNT_MIN = 1` ⇒ RED.
- `test_bare_id_fixture_would_be_refused` — fixture 04's *counter-example* (the bare-ID version) ⇒
  `UNRESOLVED_REF`. The SKILL's rule is thereby **demonstrated by a failing case**, not merely asserted.
- `test_skill_md_documents_the_id_ref_hazard` — grep `SKILL.md` for the cybos `id-ref` warning.
  A doc rule with no test rots.

## Exit criteria

- [ ] `pytest tests/ -q` ≥ 2477 passed. `mypy --strict scripts/` clean.
- [ ] **GREP-THE-SURFACES:** the eval runner **globs** `skills/decision-extraction/evals/*/` — it does
      **not** hardcode `01..04`. A fixture added later is exercised automatically; a hardcoded list is
      how fixture #5 gets silently skipped.
- [ ] SKILL.md contains **no** `import anthropic`-adjacent instruction to call a model API — the
      orchestrator owns REASON; the SKILL describes the *contract*, not a *call*.

## Rollback

Delete the skill dir + symlinks. The CLI is unaffected (it never reads the SKILL).
