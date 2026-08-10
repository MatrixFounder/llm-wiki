---
id: DF-072-4
type: known-issue
status: fixed
opened_at: 2026-08-07
fixed_at: 2026-08-10
category: correctness
severity: SEV-2
slug: df-072-4-wiki-lint-strict-exit-1-success-envelope
---

# `wiki-lint --strict` returns **exit 1 with a SUCCESS envelope** — the second instance of a divergence the repo documents as unique to `wiki-verify-multi`, and this one is warned about nowhere

- **Symptom**:

  ```console
  $ ./bin/wiki-lint --strict --vault obsidian-llm-wiki --vault-root docs
  {"action": "linted", "vault": "obsidian-llm-wiki", "total_issues": 3560,
   "by_category": {"orphan-link": 3554, "hash-mismatch": 6}, "denominators": {},
   "vacuous_checks": [], "vacuous_kinds": []}
  EXIT=1
  ```

  The envelope has **no `error` key** — it is a normal success payload. The non-zero status is the
  gating signal (`wiki_lint.py:99`: `exit_code = 1 if (args.strict and gating) else 0`).

- **Why this is a defect and not a design**: the repo already treats «non-zero exit carrying a
  success envelope» as an exceptional, carefully-fenced divergence — for `wiki-verify-multi`'s
  exit 6 it has an adversarial review finding (SEC-4), a plan invariant, a `SKILL.md` row, a
  command doc and a code comment, all saying *branch on the envelope, never on `$?`*. **This
  second instance has no warning anywhere**: `skills/wiki-lint/SKILL.md` has no exit-code table at
  all (three inline mentions, one of them «Always returns success exit 0»).

- **★ And it collides with the family's own convention.** Every corrected exit table in the repo
  now says: **`1` = unhandled exception, no envelope, raw traceback, NOT a contract error**
  (`skills/wiki-query/SKILL.md`, `skills/wiki-verify-multi/SKILL.md`,
  `skills/wiki-extract-concepts/SKILL.md`, `components.md` ×2 — several corrected in `f0e926e`).
  A caller applying that convention reads a perfectly successful `--strict` gate run as a crash.
  So the two live meanings of code 1 are mutually exclusive, and one of them is undocumented.

- **Related, same CLI**: `wiki-lint` is also the only CLI that performs **real work on a bare
  invocation** — no argparse-required argument, so `./bin/wiki-lint` opens the GLOBAL db and runs
  a full lint (exit 0). Worth deciding in the same pass whether that is intended.

- **Fix shape** (not done here — this issue exists so it is not lost). Two options, and the choice
  is a real one:
  1. **Document it**: give `skills/wiki-lint/SKILL.md` an exit-code table with the divergence
     fenced exactly as `wiki-verify-multi`'s is — «`1` = `--strict` gate tripped, **success
     envelope**, branch on the envelope not `$?`» — and correct the «Always returns success
     exit 0» line. Cheapest; keeps the CI contract stable.
  2. **Move the gate signal off code 1** (e.g. to the family's `6`) so code 1 keeps one meaning
     across the whole family. Breaks any existing CI wired to `wiki-lint --strict`; needs a
     deliberate migration note.

  Option 1 is the conservative default; option 2 is the one that removes the collision rather
  than annotating it. ⚠️ Whichever is chosen, pin it with a test asserting the **envelope shape**
  (`"error" not in env`) alongside the code — a `rc == 1`-only assertion cannot tell this apart
  from a traceback.

- **Found by**: the machine exit-code census of TASK 072 bead 072-03d (`f0e926e`). Not caught by
  `tests/test_exit_code_doc_truth.py` because `wiki-lint` is in partition B — it has a `SKILL.md`
  with **no exit table**, so there is nothing to check against. That gap is itself recorded in the
  test's partition assertion.

---

## Resolution — TASK 074, 2026-08-10 (option 1, and why option 2 was refused on evidence)

**Fixed by option 1** — documented and fenced. `skills/wiki-lint/SKILL.md` gains a `## Exit codes`
section declared **normative**, listing all four reachable codes (`0`, `1`×2 meanings, `2`
argparse, `6` inherited `INVALID_INDEX_DB`), with a ⚠️ box modelled byte-for-byte on
`skills/wiki-verify-multi/SKILL.md:130-136`. The "Always returns success exit `0`" line at `:62`
is deleted. `wiki-lint` therefore moves from **partition B to partition A** of
`tests/test_exit_code_doc_truth.py` — it is now held to usage-row truth, phantom-freedom **and**
completeness, and it is deliberately absent from `_DOES_NOT_CLAIM_COMPLETENESS`.

**★ Option 2 was refused because it does not do what it claims.** It proposed moving the gate
signal «to the family's `6`». `wiki-lint` **already reaches 6**: `INVALID_INDEX_DB`, inherited
from `build_repo_config` (`wiki_lint.py:73`). Putting the gate there would have **reproduced the
exact `wiki-verify-multi` exit-6 ambiguity** — 6 = error envelope *or* 6 = success envelope —
rather than removing any collision. Two further reasons, both secondary to that one:

- exit-1-on-findings is the **universal linter convention** (ruff, eslint, shellcheck, flake8);
  the family's «1 = crash» is the local outlier, and moving `wiki-lint` off 1 would surprise every
  operator who has wired a linter before;
- exit 1 is pinned by live tests (`tests/test_lint_near_duplicate.py:182`,
  `tests/test_lint_denominators.py:191`) and by five doc surfaces that call it the CI gate.

Recorded as **D-074-2** in `docs/tasks/task-074-*`.

**★ The residual collision is now DISCRIMINABLE, not merely annotated** — which is what the
issue's own ⚠️ demanded. The two meanings of 1 differ in envelope shape, and the discriminator is
stronger than `"error" not in env`: a **crash emits no envelope at all** (stdout empty), a tripped
gate emits a parseable success payload. Pinned by
`tests/test_cli_envelope_contract.py::test_wiki_lint_strict_gate_is_a_success_envelope_at_exit_1`
(rc **and** shape **and** `total_issues > 0`) plus its mirror at exit 0 without `--strict`.

**Sub-finding resolved**: `wiki-lint` doing real work on a bare invocation is **intended**, not an
accident — the SKILL.md already specified «omitting `--vault` runs across every registered vault»,
and it now says so explicitly in the Contract section so the question is not re-opened.
