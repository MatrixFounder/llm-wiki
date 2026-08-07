---
id: DF-072-5
type: known-issue
status: open
opened_at: 2026-08-07
category: security
severity: SEV-3
slug: df-072-5-wiki-init-echoes-the-offending-value
---

# `wiki-init` emits a **`received`** key echoing the offending value — the one key `components.md` names as forbidden — and it is the one CLI excluded from every envelope-safety suite

- **Symptom**:

  ```console
  $ ./bin/wiki-init --register-existing --vault $V --vault-id 'BAD--ID!!' --db-path $V/t.db
  {"error": "INVALID_VAULT_ID", "received": "ok", "pattern": "^[a-z][a-z0-9-]{1,30}[a-z0-9]$"}
  EXIT=6
  ```

  Three emit sites carry it: `scripts/wiki_skills/wiki_init.py:335`, `:478`, `:588`.

- **The prohibition and its violation use the same word.** `docs/architectures/functional/
  components.md:291` states the invariant as: «every error envelope emits `{error, field?, reason,
  violations?}` **only, with NO `content`, `value`, `raw`, or `received` keys**». A one-token grep
  for `received` would have found this at any point in the last 14 months.

- **★ The sharpest part is the test population.** The three envelope-safety canary suites cover
  `wiki_alias`, `wiki_merge`, `wiki_query`, `wiki_verify_multi`, `wiki_extract_concepts`,
  `wiki_extract_decisions`, `wiki_search`, `wiki_sync` — **the CLIs the invariant was written
  for.** `wiki_init` is imported by nine test files and by **none** of them. So the one CLI that
  violates the invariant is the one CLI the invariant was never able to fire on:

  ```console
  $ for f in $(grep -rln 'canary\|CWE-117' tests/*.py); do \
      echo "$f: $(grep -oE 'wiki_[a-z_]+' $f | sort -u | tr '\n' ' ')"; done
  ```

  *The test population was derived from the instances already known* — the unenumerated-surface
  lens, reproduced inside the machinery built to prevent it. This is the fourth recorded recursive
  instance (cf. G4, G6, the H-5 marker-only enrolment).

- **Why SEV-3 and not higher — state the mitigation honestly.** The echoed value is an
  **operator-supplied `vault_id`**, read from Class-A `WIKI_SCHEMA.md` frontmatter or a CLI flag —
  **not** source-body content and not retrieved page text. So the narrower and more important
  clause of the invariant, «**never a byte of source-body content**» (H-6), is *not* broken here.
  What is broken is the stated universal, and the log-injection surface it was written to close
  (CWE-117: the value lands verbatim in whatever consumes the envelope).

- **Fix shape** (not done here). Either:
  1. **Comply** — drop `received` from the three sites (the `pattern` key already tells the caller
     what was expected, and `field` names what was wrong), or
  2. **Amend the invariant** — if echoing an operator-supplied identifier is deliberate, say so at
     `components.md:291` and everywhere the universal is restated, and name `wiki-init` as the
     stated exception. A boundary that is STATED is honest; one that is merely true is the disease.

  ⚠️ Whichever is chosen, **the real fix is the population**: extend the canary matrix to enumerate
  the CLI roster from `bin/` rather than from a hand-list, so the next CLI cannot be excluded by
  omission. `tests/test_exit_code_doc_truth.py` (`f0e926e`) has a working `_discover_clis()` to
  reuse.

- **Found by**: the machine exit-code census of TASK 072 bead 072-03d. Out of that gate's stated
  scope (it checks table rows against reachable codes, not envelope *keys*), which is why this is
  an issue rather than a test.
