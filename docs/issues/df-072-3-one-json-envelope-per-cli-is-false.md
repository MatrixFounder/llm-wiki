---
id: DF-072-3
type: known-issue
status: fixed
opened_at: 2026-08-07
fixed_at: 2026-08-10
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

---

## Resolution — TASK 074, 2026-08-10

**Fixed.** The quantifier was weakened at **19 sites** (EN + RU) to «one JSON envelope per
**completed subcommand invocation**», with both boundaries named at each site rather than left as
unstated exceptions to a universal:

- the **argparse refusal** precedes the contract — usage to **stderr**, status **2**, **empty
  stdout** (re-measured 2026-08-10: **22/22** distinct programs — 23 `bin/` names, of which
  `wiki-import-article` is a symlink to `wiki-import`; `.sh` installers excluded);
- the **three deliberate non-JSON success modes** — `wiki-search --format markdown`,
  `wiki-sync scan --dry-run`, `wiki-config serve` (stderr banner, no stdout envelope).

Sites: `CLAUDE.md:74`, `AGENTS.md:21`, `docs/manuals/obsidian-llm-wiki_manual.md` (Surface + I/O
rows, the integration-model section, the key-takeaway box, the anti-pattern table),
`docs/manuals/cli-quick-reference.md`, the four RU mirrors, and
`skills/wiki-{graph,health,config,search}/SKILL.md`.

**★ The `branch on $?` contradiction is closed.** Every «branch on `$?`» instruction (EN ×2,
RU ×2) now reads *read the envelope's `error` key and branch on that; `$?` is a coarse
pre-filter* — and names **both** ambiguous codes explicitly: `wiki-verify-multi`'s 6 (filed FAIL
verdict vs `INVALID_INDEX_DB`) and `wiki-lint`'s 1 (tripped `--strict` gate vs crash — see
DF-072-4). A new anti-pattern row calls out unconditional `json.loads(stdout)` directly.

**★ Adjacent falsehood fixed in the same pass**: the Surface row one line above
(`manual.md:142` / `manual.ru.md:147`) still claimed «19 CLIs …, **each also** a `/wiki-*` slash
command» — corrected in `CLAUDE.md` on 2026-08-07 but never in the manuals. Measured: `commands/`
holds **17 of 19**; `wiki-graph` and `wiki-health` have no wrapper.

**Mechanised** (this issue's own "natural follow-on"): `tests/test_cli_envelope_contract.py`
Gate A — parametrised over a **runtime `bin/` walk**, it executes every CLI with a bogus flag and
asserts `rc == 2` **and** `stdout == b""`. The corrected sentence is now a measurement, and a CLI
added tomorrow is in scope without editing the gate. What the gate deliberately does **not**
assert — the three non-JSON success modes — is stated in its docstring, per TASK 074 §4.

⚠️ **A `/vdd-multi` pass caught this fix asserting its own over-coverage.** The first cut wrote
«**Both** halves are gated» in `CLAUDE.md`, `AGENTS.md` and the manual — while the gate's own
docstring says, in its CANNOT block, that it does *not* cover the three non-JSON success modes.
That is precisely DF-072-3's disease (a universal claiming a mechanisation it does not have)
re-committed inside DF-072-3's fix. Corrected at all four sites: boundary 1 is **gated**,
boundary 2 is a **maintained list**, and each says which it is.

**Also corrected in the same pass** — the manual's `1` row named `wiki-lint --strict` as the sole
exit-1 divergence. Measured: **three**. `wiki-init` returns `MISSING_VAULT_ARG` at exit 1 with a
normal *error* envelope (documented in its own SKILL.md table), and `wiki-import`'s
`ImportArticleError` defaults to `EXIT_USAGE = 1`, so e.g. `FETCH_FAILED` lands there too. A
caller told "1 = crash, no envelope" would discard two perfectly good envelopes.
