# PLAN 074 — CLI I/O contract truth triad (DF-072-3 / -4 / -5)

Spec: `docs/TASK.md`. Stub-First does not apply cleanly here — two of three beads are doc
corrections over shipped behaviour, and the third is a *deletion* of an envelope key. So the
order is **gate-first**: each new gate is written to go RED against the current tree, then the
fix turns it green. That is the Stub-First property that matters (a test that has failed once).

| Bead | Scope | Gate | Status |
|---|---|---|---|
| 074-1 | New `tests/test_cli_envelope_contract.py` — argparse-shape gate + forbidden-key gate, both `bin/`-derived, both with non-vacuity + mutation controls | RED on `wiki-init` (3 sites) before 074-2 | ☑ |
| 074-2 | DF-072-5 — drop `received` from `wiki_init.py:335,478,588`; carry `{error, field, pattern}` | 074-1 forbidden-key gate goes GREEN | ☑ |
| 074-3 | DF-072-4 — exit table in `skills/wiki-lint/SKILL.md`; delete the «Always returns success exit 0» line; fence the exit-1 divergence | `test_exit_code_doc_truth.py` accepts `wiki-lint` in partition A; new envelope-shape test | ☑ |
| 074-4 | DF-072-3 — weaken the quantifier at all **19** sites (EN + RU; the census table below); name the 3 non-JSON modes; fix «branch on `$?`»; fix the 19-slash-commands row | grep census → 0 surviving universals | ☑ |
| 074-7 | `/vdd-multi` adversarial pass (3 critics) → fix loop; see the findings table in `docs/TASK.md` §7 | full suite + mypy green | ☑ |
| 074-5 | Regression run: `pytest tests/`, `mypy --strict scripts/`; re-run the 3 repro commands | all green | ☑ |
| 074-6 | Close the three issue files (`status: fixed` + resolution); regenerate `docs/KNOWN_ISSUES.md` via `wiki-reindex --full` | ledger shows 3 × `fixed` | ☑ |

## 074-1 — the two gates (do this FIRST, and watch it fail)

New file `tests/test_cli_envelope_contract.py`. Population imported, not transcribed:

```python
from tests.test_exit_code_doc_truth import CLIS, _module_for, _module_paths
```

**Gate A — `test_argparse_refusal_emits_no_envelope`** (parametrised over every entry of `CLIS`):
run `bin/<cli> --definitely-not-a-real-flag-0723`, assert `rc == 2` **and** `stdout == b""`.
This is what makes the corrected doc sentence true-by-measurement rather than true-by-review.

**Gate B — `test_no_emit_site_carries_a_forbidden_envelope_key`** (parametrised over every entry
of `CLIS`): AST-walk every `.py` of the CLI's module; for each call whose function name ends in
`emit`, if arg 0 is an `ast.Dict`, assert none of its literal keys ∈ `{content, value, raw,
received}`. Nested dict literals inside the payload are walked too (TASK 064 made the runtime
canary recursive; a static scan that stops at depth 1 would be narrower than the thing it mirrors).

**Controls (AC-8).** `test_the_population_is_not_empty` (≥ 15 CLIs, ≥ 15 with a resolvable
module); `test_gate_a_can_fire` (a probe process that prints to stdout and exits 2 is caught);
`test_gate_b_can_fire` (the scanner finds a planted forbidden key in a synthetic module, and
does **not** flag a non-emit dict carrying the same key).

## 074-2 — DF-072-5

Three sites, same shape:

```python
return _emit({"error": "INVALID_VAULT_ID", "field": "vault_id",
              "pattern": _VAULT_ID_RE.pattern}, exit_code=6)
```

`field` matches the family convention (`{error, field?, reason}` — `wiki_alias.py:88` et al).
`:588` (reconcile) reads the id from `WIKI_SCHEMA.md`, so its `field` is `vault_id` too, and a
`reason` distinguishes «absent» from «malformed» without echoing bytes.

## 074-3 — DF-072-4

`skills/wiki-lint/SKILL.md`: replace the `Contract` bullet «Always returns success exit `0`…»
with a pointer to a new `## Exit codes` section carrying all four reachable codes, the exit-1
double meaning, and a ⚠️ block modelled on `skills/wiki-verify-multi/SKILL.md:130-136`. Declare
the roster **normative** (so `test_exit_code_doc_truth.py` holds it to completeness — `wiki-lint`
must NOT be added to `_DOES_NOT_CLAIM_COMPLETENESS`). Document the usage row (`2`, argparse), so
`wiki-lint` must NOT be in `_NO_USAGE_ROW_DOCUMENTED` either — both rosters are pinned by
`test_which_tables_document_a_usage_row_is_pinned`, so that pin needs updating in the same edit.

Also note the «real work on a bare invocation» sub-finding (`./bin/wiki-lint` with no args opens
the global DB and lints everything, exit 0). Decide in-line: it is **intended** — the SKILL.md
already documents «omitting `--vault` runs across every registered vault». Say so explicitly so
the question does not get re-opened.

New test in `tests/test_cli_envelope_contract.py`:
`test_wiki_lint_strict_gate_is_a_success_envelope_at_exit_1` — build a tiny vault with a real
gating issue, run the CLI, assert `rc == 1` **and** `json.loads(stdout)` succeeds **and**
`"error" not in env` **and** `env["total_issues"] > 0`.

## 074-4 — DF-072-3 site census (measured 2026-08-10; excludes `docs/{issues,tasks,plans,archive}/`)

| # | Site | Claim |
|---|---|---|
| 1 | `CLAUDE.md:74` | «Every CLI emits one JSON envelope + a stable exit code» |
| 2 | `AGENTS.md:21` | same |
| 3 | `docs/manuals/obsidian-llm-wiki_manual.md:142` | «19 CLIs …, each also a `/wiki-*` slash command» |
| 4 | `docs/manuals/obsidian-llm-wiki_manual.md:143` | I/O contract row |
| 5 | `docs/manuals/obsidian-llm-wiki_manual.md:1608-1610` | «Output is exactly one line of JSON on stdout» |
| 6 | `docs/manuals/obsidian-llm-wiki_manual.md:1628` | «branch on the exit code first» |
| 7 | `docs/manuals/obsidian-llm-wiki_manual.md:1758` | «one JSON envelope per command … branch on `$?`» |
| 8 | `docs/manuals/obsidian-llm-wiki_manual.md:2017` | anti-pattern row «Branch on `$?`, read `.error`» |
| 9 | `docs/manuals/cli-quick-reference.md:154` | «every command prints a JSON envelope» |
| 10 | `docs/manuals/obsidian-llm-wiki_manual.ru.md:147` | RU of #3 |
| 11 | `docs/manuals/obsidian-llm-wiki_manual.ru.md:148` | RU of #4 |
| 12 | `docs/manuals/obsidian-llm-wiki_manual.ru.md:1657-1659` | RU of #5/#6 |
| 13 | `docs/manuals/obsidian-llm-wiki_manual.ru.md:1810` | RU of #7 |
| 14 | `docs/manuals/obsidian-llm-wiki_manual.ru.md:2076` | RU of #8 |
| 15 | `docs/manuals/obsidian-llm-wiki_manual.ru.md:2193` | RU glossary «единственная строка JSON, которую каждая команда печатает» |
| 16 | `docs/manuals/cli-quick-reference.ru.md:159` | RU of #9 |
| 17 | `skills/wiki-graph/SKILL.md:37` | «Every invocation prints a one-line JSON envelope» |
| 18 | `skills/wiki-health/SKILL.md:35` | same |
| 19 | `skills/wiki-config/SKILL.md:71` | «One JSON envelope on stdout, always» |

`scripts/wiki_skills/.AGENTS.md:509` is a *citation* of Decision-17 scoped to `wiki_import_article`
(which has no non-JSON mode) — left as-is; the definition it cites is #1/#2 and is corrected there.

The replacement wording, used consistently:

> One JSON envelope on stdout per **completed subcommand invocation**, plus a stable exit code.
> Two boundaries: an **argparse refusal** precedes the contract (usage to stderr, status 2, empty
> stdout), and three subcommands deliberately print non-JSON on success — `wiki-search --format
> markdown`, `wiki-sync scan --dry-run`, and `wiki-config serve` (banner on stderr, no envelope).
