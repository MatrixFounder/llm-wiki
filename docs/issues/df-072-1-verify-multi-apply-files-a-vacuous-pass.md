---
id: DF-072-1
type: known-issue
status: open
opened_at: 2026-08-07
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
