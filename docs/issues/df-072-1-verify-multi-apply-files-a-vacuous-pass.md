---
id: DF-072-1
type: known-issue
status: fixed
opened_at: 2026-08-07
resolved_at: 2026-08-08
category: correctness
severity: SEV-2
slug: df-072-1-verify-multi-apply-files-a-vacuous-pass
---

# `wiki-verify-multi apply` files a **PASS verdict over ZERO examined sources** — the two floors its own `prepare` carries are absent from `apply`

- **Symptom**: a query page with `cites: []` (or whose every cited slug is unresolvable) is
  **refused by `prepare`** — exit 2 `NO_SOURCES` — but **accepted by `apply`**, which writes a
  `_verifications/verify-<slug>.md` page with `verdict: pass` and self-indexes it, at **exit 0**.
  The verification layer thus certifies an answer against **nothing**, and the artifact is
  Class-A durable and FTS-searchable like any earned verdict.

- **The rail already knows this is wrong.** `prepare` carries BOTH floors, and the second one is
  commented in exactly these terms:

  ```python
  # scripts/wiki_skills/wiki_verify_multi.py
  :250   if not cites:      → NO_SOURCES, exit 2
  :257   if not examined:   → NO_SOURCES, exit 2
         # "refuse rather than file a vacuous PASS over zero sources (vdd-multi L-3)"
  ```

  `apply` unpacks the same tuple at `:456`, checks `ANSWER_CHANGED`, calls `_gather_examined` at
  `:464` — and has **neither** floor.

- **Why `prepare` does not gate it.** `--verify-hash` is `default=None` (parser `:656`, help
  "Optional for back-compat") and the TOCTOU check is gated `if args.verify_hash is not None`
  (`:475`). So `apply` can be invoked **without ever running `prepare`**, and the refusal that
  exists upstream is simply never reached.

- **Reproduced** (three scenarios, all with a `{"verdict":"pass","critics":["factual"],
  "findings":[]}` payload, reusing the seeding helpers from `tests/test_wiki_verify_apply.py`):

  | scenario | `prepare` | `apply` |
  |---|---|---|
  | page with `cites: []` | exit 2 `NO_SOURCES` | **exit 0, filed, `page_indexed: true`** |
  | same, with a self-computed `--verify-hash` | exit 2 `NO_SOURCES` | **exit 0, filed** |
  | `cites:` non-empty but every entry unresolvable | exit 2 `NO_SOURCES` | **exit 0, filed** |

- **Relation to TASK 072 P1a.** This is the *same defect class* as the `NO_CITATIONS` hole closed
  in `wiki-query apply` (commit `f0f6b71`): a grounding gate that passes because it examined an
  empty population. It is **not** introduced by that change — it is pre-existing, and it was
  found by the adversarial review OF that change, which asked whether the sibling rail had the
  same vacuity. Half of it did not (`prepare` is correct); half of it did.

- **Reachability today is low, and that is the whole risk profile.** `type='query'` pages number
  **1** across all 17 live index DBs and `cites: []` pages number **0**, so nothing is currently
  mis-verified. But the population is zero for the same reason R-6 has never been used — not
  because the path is closed. The moment `wiki-query` is exercised, a `--force`-style re-apply or
  a hand-edited `cites:` reaches this.

- **Fix shape** (not done here — this issue exists so it is not lost): lift the two `prepare`
  floors into `apply`, before the render, emitting the same `NO_SOURCES` envelope. Zero DDL.
  ⚠️ Choose the exit code deliberately: `prepare` uses **2**, but in `apply` the analogous
  refusals are the payload-contract class (**4**) — see the reasoning recorded in `f0f6b71`. Pin
  it with a test that asserts the **envelope**, not the bare exit code, and with the mutation
  executed; a `code == 2`-only assertion cannot distinguish this from `ANSWER_CHANGED`.

- **Also worth deciding in the same pass**: whether `--verify-hash` should stay optional. A
  back-compat default of `None` is what lets `apply` run without the `prepare` that would have
  refused — the TOCTOU guard and the grounding floor are load-bearing for different reasons, but
  both are skipped by the same flag default.

## Resolution (2026-08-08)

Both `prepare` floors lifted into `apply`, verbatim, in `scripts/wiki_skills/wiki_verify_multi.py`:
floor #1 (`if not cites`) after the `ANSWER_CHANGED` TOCTOU check, floor #2 (`if not examined`)
immediately after `_gather_examined` and **before** the `--verify-hash` compare — so a correctly
self-computed hash over the empty examined set cannot reach the write either. No escape hatch.

**Exit 2, not 4** — the issue flagged this as a deliberate choice, and it lands opposite to the
`f0f6b71` sibling. There, the empty list was in the LLM-**supplied verdict payload**, so exit 4
("re-synthesise") was the actionable class. Here `cites:` is read from the query page **on disk**:
re-synthesising the verdict cannot fix it, so the correct action is STOP. That is the class
`prepare` uses and the class its own block-mates (`ANSWER_CHANGED`, `VERIFY_CONTEXT_CHANGED`)
already use, and it keeps the one documented instruction — `workflows/wiki-verify-multi.md`'s
"`NO_SOURCES` (exit 2) → surface and STOP" — true for both subcommands instead of forking it.

**`--verify-hash` stays optional.** It was never the mechanism: the floors now hold whether or not
it is passed, which is what makes them floors. Making it required would break back-compat callers
to re-close a hole that is already closed, and would re-locate the guarantee back into a flag.

### The test-side trap this fix walked into

Floor #1 is **subsumed** by floor #2 — `_gather_examined([])` returns an empty examined set — so
with only `error` + exit asserted, **deleting floor #1 left the suite fully green**. The two floors
differ solely in their operator-facing `reason` ("you cited nothing" vs "your cites are all
broken" — different fixes), so that string is the only observable that separates them, and it is
what the test now asserts. `tests/test_wiki_verify_prepare.py` has the identical blind spot on
prepare's pair (`test_no_sources` asserts code + `error` only); left as-is, noted here.

Verified by mutation, each run from a clean tree (a first batch was contaminated because
`str.replace(..., 1)` hit `prepare`'s **byte-identical** copy — the floors are duplicated, so a
mutation must target the **last** occurrence):

| mutation (in `apply`) | tests killed |
|---|---|
| delete floor #1 | `test_apply_refuses_empty_cites` |
| delete floor #2 | `test_apply_refuses_when_every_cite_is_unresolvable` |
| floor #1 `NO_SOURCES` → `INVALID_CITATIONS` | the 2 empty-`cites:` tests |
| floor #1 exit 2 → 4 | the 2 empty-`cites:` tests |
| floor #2 exit 2 → 4 | `test_apply_refuses_when_every_cite_is_unresolvable` |
| floor #2 `NO_SOURCES` → `INVALID_CITATIONS` | `test_apply_refuses_when_every_cite_is_unresolvable` |

Four tests in `tests/test_wiki_verify_apply.py`, all reproducing the reported invocation (a
self-computed `answer_hash`, no `prepare` run): the three scenarios from the table above plus a
**non-vacuity control** — the same un-prepared `apply` with one resolvable cite still files at
exit 0, so the floors refuse zero sources, not all sources. Each asserts the envelope and that
no `_verifications/` page exists (scenario 1 also asserts no `pages` row), never a bare exit code.

### Dogfooded live (2026-08-09) — `TestVault/ObsidianNotes-Test`, `vault_id: personal`

3054 pages, `obsidian-personal` layout (**not** karpathy), vault-local `.wiki/index.db` at
`user_version 7`, Cyrillic slugs and nested projects (`CybOS Demo/wiki-dogfood/…`) — none of
which the repo tests cover. Before/after with **identical invocations**, the "before" run
executed from a `git worktree` at `d53e35f^`:

| | `apply` on `cites: []` | on `cites:` where none resolve |
|---|---|---|
| **before** (`d53e35f^`) | `exit 0` · `{"verdict":"pass","page_indexed":true,"action":"filed"}` · a real Class-A `_verifications/*.md` on disk, indexed, with a `verifies` ref | — |
| **after** (`52371cd`) | `exit 2 NO_SOURCES` · "cites nothing" · nothing written | `exit 2 NO_SOURCES` · "cites 2 source(s) but none are indexed/readable" · nothing written |

The defect was **live-reachable on a real vault**, not a lab artifact: the pre-fix run filed a
`verdict: pass` page certifying an answer against zero sources, and `_verifications/` did not
even exist before it. The two floors' `reason` strings discriminated correctly in the field.

**Non-vacuity control, zero writes.** On the REAL 7-cite query page, control flows *past* both
floors and lands on the next gate (`VERIFY_CONTEXT_CHANGED` with a bad `--verify-hash`;
`ANSWER_CHANGED` with a bad answer hash — confirming the ordering too). Had the floors
over-refused, these would have said `NO_SOURCES`.

⚠️ **Ordering note found en route**: `--verdict-file` must be vault-inside, and post-fix the
floors fire BEFORE the payload is read — so a `/tmp` verdict yields `NO_SOURCES` (floor) after
the fix but `INVALID_VERDICT` (payload) before it. A before/after comparison must put the
verdict file inside the vault or it compares two different gates.

**Vault restored**: probe pages deleted → `wiki-reindex --full` (3054 pages, 0 skipped, 0
collisions, 3.9 s) → identical type distribution to the start snapshot, real query page
byte-identical. One Class-C `log_events` row survived by design (ADR-002 §D8 — Class C is not
rebuilt from markdown); `wiki-lint` does not see it and **no CLI removes it**, so it took
direct SQL.

### Related

- [[df-072-9-query-answer-markdown-escaped-into-literal-text]] — the other TASK 072 dogfood finding.
- `f0f6b71` — the `NO_CITATIONS` floor in `wiki-query apply`; same defect class, opposite exit
  class, and the review of *that* change is what found *this*.
- [[the-unenumerated-surface-lens]] — and its test-side twin: a green suite over a branch nothing
  can reach.
