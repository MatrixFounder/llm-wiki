---
id: DF-072-2
type: known-issue
status: open
opened_at: 2026-08-07
category: documentation
severity: SEV-2
slug: df-072-2-wiki-health-always-exits-0-is-false
---

# «`wiki-health` **always exits 0**» is FALSE — and it is asserted in an **Accepted ADR**, `CLAUDE.md`, `README.md`, `ARCHITECTURE.md`, the manual and the ROADMAP

- **Symptom**: the doctrine that a coverage gap is *data, not a failure* — so the CLI never
  signals failure through `$?` — is stated without qualification across ~20 live surfaces. It is
  false on two reachable paths.

  ```console
  $ ./bin/wiki-health coverage --vault definitely-no-such-vault
  {"error": "VAULT_NOT_FOUND", "vault": "definitely-no-such-vault"}
  EXIT=6

  $ ./bin/wiki-health coverage --vault obsidian-llm-wiki --vault-root docs --class bogus
  {"error": "INVALID_CLASS", "valid": [...]}
  EXIT=2
  ```

- **★ The one correct wording in the repository is the source docstring** — `scripts/wiki_skills/
  wiki_health.py:9` says it «ALWAYS exits 0 **on success**». **Every derived copy dropped the two
  words that made it true.** That is the transferable finding: the falsehood was manufactured by
  paraphrase, not by a wrong measurement, and each copy looked like faithful restatement.

- **Where it is asserted** (re-derive, do not trust this list — it is a lower bound):

  ```console
  $ grep -rln 'always exit[s]* 0\|ALWAYS exits 0' --include='*.md' --include='*.py' . \
      | grep -v '^./samples'
  ```

  Live forward-looking surfaces include `docs/adr/ADR-006-derived-knowledge-health.md` (**an
  Accepted ADR — three times**, incl. the D-036-2 rationale), `CLAUDE.md:58`, `README.md:465`,
  `docs/ARCHITECTURE.md`, `docs/manuals/obsidian-llm-wiki_manual.md`, `docs/manuals/
  cli-quick-reference.md`, `docs/ROADMAP.md`, `skills/wiki-health/SKILL.md`.

- **Why it matters operationally**: `wiki-health` is the R-15 read-only reporter. A CI step or a
  wrapper written against the documented contract (`wiki-health … ; echo "always fine"`) treats a
  **typo'd vault name** as a clean health report. The failure mode is a silent green over a run
  that examined nothing — the exact class TASK 061 exists to indict.

- **The test does not catch it**: `tests/test_wiki_health.py:176` asserts `rc == 0` **only on the
  success path**, so the unhedged claim has no falsifier anywhere.

- **Fix shape** (not done here): propagate the source docstring's hedge to every copy — «always
  exits 0 **on success**; look-up and argument errors still use the family codes (6
  `VAULT_NOT_FOUND`, 2 `INVALID_CLASS`)». Amend ADR-006 with a dated correction rather than a
  silent edit — it is an *Accepted* decision record and the claim is load-bearing in its
  rationale. Add the falsifier test (`--vault <nonexistent>` ⇒ 6) so the claim can go RED.

- **Found by**: the machine exit-code census of TASK 072 bead 072-03d (`f0e926e`). Note the census
  itself does **not** assert this class — `tests/test_exit_code_doc_truth.py` covers table rows,
  and «always exits 0» is free prose in eight different phrasings. Closing it mechanically would
  need an executed per-CLI probe of the claim, which is tractable and is the natural follow-on.
