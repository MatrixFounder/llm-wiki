---
id: DF-072-3
type: known-issue
status: open
opened_at: 2026-08-07
category: documentation
severity: SEV-3
slug: df-072-3-one-json-envelope-per-cli-is-false
---

# «Every CLI emits **one JSON envelope** + a stable exit code» is FALSE on the usage path — and it is the Decision-17 paragraph in `CLAUDE.md`

- **Symptom**: the project's most-repeated universal CLI claim has at least three counterexamples.

  ```console
  $ ./bin/wiki-query --definitely-not-a-flag 2>/dev/null | wc -c
  0            # argparse refuses: ZERO stdout bytes, no envelope at all, exit 2
  ```

  Measured across the family: **19/19 CLIs emit no envelope on an unrecognised flag.** Two further
  shapes break it on *success* paths:

  - `wiki-search "…" --format markdown` exits 0 having printed **non-JSON markdown**;
  - `wiki-sync scan` (dry-run) prints a multi-line human report (`wiki_sync.py:345`);
  - `wiki-config serve` prints a banner to stderr and returns 0 **without any stdout envelope**
    (`wiki_config/_server.py:564-572` — no `emit()` on that path), while
    `skills/wiki-config/SKILL.md:71` says «One JSON envelope on stdout, **always**».

- **Where it is asserted**: `CLAUDE.md:71` and `AGENTS.md:21` (the Decision-17 paragraph),
  `docs/manuals/obsidian-llm-wiki_manual.md:143` and `:1758`, `skills/wiki-graph/SKILL.md:37` and
  `skills/wiki-health/SKILL.md:33` (both phrased «**Every invocation** prints a one-line JSON
  envelope» — the quantifier is what makes them false), `skills/wiki-config/SKILL.md:71`.

- **★ The manual contradicts a skill contract for the same binary.** `manual.md:1758` instructs
  callers to «branch on `$?`» — the exact practice `skills/wiki-verify-multi/SKILL.md` and
  `commands/wiki-verify-multi.md` forbid **in bold**, because that CLI's exit 6 is ambiguous
  (see the correction shipped in `f0e926e`). Two live contracts, opposite instructions.

- **Severity is SEV-3, deliberately**: no data loss and no wrong answer — the risk is a caller
  written against the universal claim that does `json.loads(stdout)` unconditionally and crashes
  (or silently swallows) on the usage path instead of surfacing the argparse message. The correct
  reading was always available in the code; only the docs over-quantified.

- **Fix shape** (not done here): weaken the quantifier where it is false — «one JSON envelope per
  **completed subcommand invocation**; argparse refusals precede the contract and use argparse's
  own convention (status 2, message on stderr, empty stdout)» — and name the two deliberate
  non-JSON output modes (`--format markdown`, `wiki-sync scan` dry-run, `wiki-config serve`)
  rather than leaving them as exceptions to a stated universal. Fix the `manual.md:1758`
  «branch on `$?`» advice in the same pass; it is actively wrong for `wiki-verify-multi`.

- **Found by**: the machine exit-code census of TASK 072 bead 072-03d (`f0e926e`). Explicitly
  **out of** `tests/test_exit_code_doc_truth.py`'s scope, which is stated in that file's docstring
  — the envelope-shape claim is prose, and a gate that pretended to cover it would be the same
  overclaim this task exists to remove. Mechanising it is tractable (probe each CLI's stdout on a
  bogus flag) and is the natural follow-on.
