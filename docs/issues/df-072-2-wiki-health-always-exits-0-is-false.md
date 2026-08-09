---
id: DF-072-2
type: known-issue
status: fixed
opened_at: 2026-08-07
resolved_at: 2026-08-09
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

## Resolution (2026-08-09)

Closed both halves the defect had — the false prose, and the absence of any falsifier —
in `tests/test_wiki_health_exit_contract.py`:

1. **The executed falsifier.** Both reachable non-zero paths now RUN: `VAULT_NOT_FOUND` (6,
   parametrized over *both* subcommands) and `INVALID_CLASS` (2), plus a success control so
   the true half of the claim stays pinned. Mutating either exit code in `wiki_health.py`
   turns exactly the matching test red. Before this, `tests/test_wiki_health.py:176` asserted
   `rc == 0` only on the success path, so the unqualified claim had no falsifier anywhere.
2. **The doc-truth gate.** Every «always exit 0» claim on a live surface must carry a hedge
   (`on success`, or the codes named). Attribution is by *proximity* to a `wiki-health`
   token, so the sibling `wiki-verify-multi --fail-on=none` claim — different, and true — is
   not swept in.

**Measured: 31 sites across 15 files**, against the issue's stated lower bound of ~20. All
hedged — 27 by «on success», 1 by `0/2/6`, 1 by naming both codes, and **2 by the
`DF-072-2` escape hatch, both inside `D-036-5` itself**: a correction record has to quote
the claim it corrects, and a gate that forbids that produces a worse record than the
escape hatch is a risk. That the hatch is used exactly twice, both in the one place it
was minted for, is itself the check on it. `mypy --strict` clean; 3143 → 3149 tests pass.

**ADR-006 carries a dated correction, `D-036-5`** (2026-08-09), rather than a silent edit:
it quotes the false claim, records the two measured refusal paths, states that the *decision*
was never wrong (a report never gates — only the scope of the word *always* was), and notes
that three sentences in the ADR were corrected in place. `D-036-2`'s own sentence keeps an
inline `corrected 2026-08-09, see D-036-5` marker.

`--verify-hash`-style follow-on: none. `wiki-health`'s behaviour was correct throughout —
this was a documentation defect end to end, and no CLI code changed.

### What building the gate cost, and what that says

The gate was wrong **four times** before it was right, and every failure was the *scan*
under-reporting — the same shape as the defect it hunts. Recorded because a doc-census gate
is now a repo pattern and each of these will recur:

1. **Presence, not proximity.** A neighbouring `wiki-verify-multi` table row inside the
   window suppressed a genuine `wiki-health` claim → `README.md` and the manual's CLI table,
   two surfaces the issue names by name, were silently dropped. Fixed by attributing to the
   *nearest* subject.
2. **One window for two jobs.** Widening the window for attribution let an exit-code table
   800 chars away count as a *hedge*, re-opening two sites mid-fix. Attribution is now wide
   (900), the hedge tight (160) — a reader meets the qualifier in the same breath or not at all.
3. **★ Single-line regex over wrapped prose.** `always[- ]exits?[- ]0` cannot see
   `ALWAYS\n  exits 0` — which is exactly how the claim appears in the **`wiki-health`
   SKILL.md `description:`**, the single most agent-facing copy in the repo, loaded into
   *every* session's skill listing. The same wrap also hid the one CORRECT sentence
   (`wiki_health.py:9`'s «on\nsuccess») and made the gate report it as unhedged. Both
   directions of the same blind spot; fixed with `[-\s]+` and by flattening whitespace and
   markdown emphasis before the hedge check.
4. **The owning module has no token to key on.** `wiki_health.py` says "it always exits 0"
   with no `wiki-health` string nearby, so proximity dropped the claim *in the file that
   owns it* — 5 more sites (2 in the module, 3 in its own tests). Fixed by treating a
   path that names wiki-health as in-context throughout.

A fifth was self-inflicted and is worth its own line: mid-run the CLI appeared to return
**exit 0 with an `INVALID_CLASS` envelope**, which looked like a second live defect. It was
a **stale `__pycache__`** — the mutation `, 2)` → `, 0)` is byte-length-identical, and `cp`
restored the file inside the same mtime second, so Python's `mtime+size` validation accepted
the mutated bytecode while `inspect.getsource` showed the correct text. ⚠️ **Same-length
mutations need `find . -name __pycache__ -exec rm -rf {} +` between runs**, or the harness
will manufacture a defect that does not exist.

### Related

- [[df-072-1-verify-multi-apply-files-a-vacuous-pass]] — the sibling TASK 072 finding.
- [[the-unenumerated-surface-lens]] — this is its documentation-side twin: the surface was
  never enumerated, and the one enumeration that existed (`test_exit_code_doc_truth.py`)
  covered tables, not prose.
- `scripts/wiki_skills/wiki_health.py:9` — the one sentence that was right all along.
