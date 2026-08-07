---
id: DF-072-4
type: known-issue
status: open
opened_at: 2026-08-07
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
