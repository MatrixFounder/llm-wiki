---
id: DF-074-4
type: known-issue
status: fixed
opened_at: 2026-08-10
fixed_at: 2026-08-10
category: correctness
severity: SEV-2
slug: df-074-4-wiki-lint-reports-an-unknown-vault-as-clean
---

# `wiki-lint --strict` reports a vault that **does not exist** as a clean bill of health — exit 0, `total_issues: 0`, `vacuous_checks: []` — and it is the CI gate

- **Symptom** (measured 2026-08-10 on the live `ObsidianNotes-Test` vault, 3286 notes):

  ```console
  $ wiki-lint --vault no-such-vault-xyz --vault-root . --db-path .wiki/index.db --strict
  {"action": "linted", "vault": "no-such-vault-xyz", "total_issues": 0, "by_category": {},
   "denominators": {}, "vacuous_checks": [], "vacuous_kinds": []}
  EXIT=0
  ```

  The same typo on the **same DB**, through the sibling built for the same job:

  ```console
  $ wiki-health coverage --vault no-such-vault-xyz --vault-root . --db-path .wiki/index.db
  {"error": "VAULT_NOT_FOUND", "vault": "no-such-vault-xyz"}
  EXIT=6
  ```

  For contrast, the *real* vault on that DB reports **6556** issues and exits 1 under `--strict`.

- **★ Why this is SEV-2 and not a curiosity.** `wiki-lint --strict` is the project's stated **CI
  gate** (`docs/CLAUDE.md:150` — "exit non-zero on any issue … (CI gate)"; `README.md`; both
  manuals). A typo in a CI config, a renamed vault, or a `--vault` that drifts out of sync with
  `WIKI_SCHEMA.md` therefore turns the gate **permanently green** while examining nothing. That is
  strictly worse than the gate not existing, because it reports success.

- **★★ And the honest-denominator machinery cannot see it.** TASK 061 exists precisely to stop
  "a `0` that means nothing was examined" from reading as a green, and it does not fire here:
  `denominators: {}` means *"these config-driven checks do not apply to this layout"* — a
  deliberate, documented distinction from *"examined 0"* — so `vacuous_checks` is `[]` and
  `total_issues: 0` presents as earned. The one signal designed to catch a vacuous green is
  structurally silent on the most vacuous input possible: a vault that isn't there.

- **Mechanism.** `wiki_lint.main` (`scripts/wiki_skills/wiki_lint.py:69-78`) passes
  `vaults=[args.vault]` straight into `run_all_checks_report`; the checks filter `WHERE vault_id
  = ?`, match nothing, and return an empty issue list. There is **no existence check**.
  `wiki_health.main` has one — an explicit `VAULT_NOT_FOUND` → exit 6 — which is why the two
  disagree. The repository already exposes what is needed (`repo.get_vault(vault_id) is None`,
  the same call `wiki_init.register_existing` uses).

- **Relationship to DF-072-2** (`«wiki-health always exits 0» is FALSE`, fixed): that issue's
  whole point was that a look-up error must **not** read as a clean report, and it closed the hole
  for `wiki-health`. `wiki-lint` — the CLI that actually **gates** — was never checked for the
  same thing. The population of that fix was the CLI the claim was written about. Same lens as
  DF-072-5.

- **Fix shape** (not done here — outside TASK 074's diff; `wiki_lint.py` was not touched by it):
  1. Guard in `wiki_lint.main`: when `--vault` is given and `repo.get_vault(args.vault) is None`,
     emit `{"error": "VAULT_NOT_FOUND", "field": "vault"}` at **exit 6**, matching `wiki-health`
     and the family. Omitting `--vault` (all-vaults mode) is unaffected.
  2. Add the row to `skills/wiki-lint/SKILL.md`'s exit table, which declares itself the
     **normative roster** — it currently lists `6 INVALID_INDEX_DB` only, because that is genuinely
     all the CLI can emit today. The table is *accurate*; the CLI is what is wrong.
  3. ⚠️ Pin it with a test asserting the **envelope**, not just the code — an `rc == 6`-only
     assertion cannot tell `VAULT_NOT_FOUND` from the inherited `INVALID_INDEX_DB`, which is the
     same trap `tests/test_cli_envelope_contract.py` was written for.
  4. Consider the same sweep across the family: `wiki-search --vaults <typo>` likewise returns
     `{"hits": [], "count": 0}` at exit 0. For *search* an empty result may be legitimate, so this
     is a question to answer deliberately rather than a defect by analogy — **which is the point:
     enumerate the roster, don't reason from the one instance you found.**

- **Found by**: the TASK 074 dogfood on `/Users/sergey/Downloads/TestVault/ObsidianNotes-Test`
  (2026-08-10) — while verifying that the DF-072-4 exit-1 fence works on a real vault. It does;
  this turned up in the adjacent probe that checked what exit 6 looks like. Pre-existing:
  `git diff HEAD~1 -- scripts/wiki_skills/wiki_lint.py scripts/wiki_index/lint.py` is empty.

---

## Resolution — 2026-08-10

**Fixed, and the mandated family sweep found a second defect.**

`wiki_lint.main` now refuses a named-but-unregistered vault before any check runs:
`{"error": "VAULT_NOT_FOUND", "field": "vault", "reason": "…"}` at **exit 6**, matching
`wiki-health` and `wiki-graph`. All-vaults mode (no `--vault`) is untouched — that is a
deliberate scope, not an unknown one.

### The sweep — enumerated, not reasoned from the one instance

Fix-shape item 4 said to answer the family question deliberately. Measured across every
vault-taking CLI on a real DB:

| CLI | before | after |
|---|---|---|
| `wiki-health coverage` / `ontology` | 6 `VAULT_NOT_FOUND` | unchanged ✓ |
| `wiki-graph neighbors` | 6 `VAULT_NOT_FOUND` | unchanged ✓ |
| `wiki-index-render` | 6 `VAULT_NOT_REGISTERED` | unchanged ✓ (token differs — noted, not churned) |
| **`wiki-lint`** / `--strict` | **0, SUCCESS envelope** | **6 `VAULT_NOT_FOUND`** |
| **`wiki-reindex --delta` / `--full`** | **1, NO envelope, raw traceback echoing the vault_id** | **6 `VAULT_NOT_FOUND`** |
| `wiki-search --vaults <typo>` | 0, `{"hits": [], "count": 0}` | **unchanged — deliberately** |

★ **`wiki-reindex` was the second defect.** `reindex_full`/`reindex_delta` raise
`ValueError("vault_id=… not registered")` and nothing caught it, so a typo exited **1 with no
envelope** — which, under the convention TASK 074 had just made normative, tells the operator
their own typo is a bug in the CLI. Guarded at the CLI rather than by catching the `ValueError`,
so the DAL keeps its invariant.

**`wiki-search` is left alone on purpose.** `--vaults a,b` where one id is unknown is a real
use case, and an empty result set is a legitimate answer for a *search*. Changing it would be
reasoning by analogy — the failure mode this whole task is about. Recorded here as a stated
boundary rather than a silent one.

### Pinned

`tests/test_cli_envelope_contract.py` — four new cases asserting the **envelope**, not just the
code (`rc == 6` alone cannot separate `VAULT_NOT_FOUND` from the inherited `INVALID_INDEX_DB`):
the refusal for `wiki-lint` × {plain, `--strict`} and `wiki-reindex` × {`--full`, `--delta`},
that the refusal does **not** echo the operator's value, that it produces **no traceback**, and
— the other direction — that a **registered but clean** vault still exits 0 with a real report,
so the fix cannot turn an earned zero into a refusal.

### Two other gates fired on this change, and both were right

- **`test_a_table_claiming_completeness_is_complete[wiki-lint]`** went red: the new code was
  reachable and undocumented. `skills/wiki-lint/SKILL.md`'s normative table gained the row.
- **`test_h1_sink_census_is_complete`** (TASK 061) went red: `wiki_lint.main` now has a FOURTH
  output sink. Its docstring says a fourth sink must force a *decision* about denominators —
  the decision is **no**: a refusal envelope carries an `error` key and examined nothing, which
  is the opposite of the false green denominators exist to prevent. The census now asserts two
  classes (3 report sinks that must carry the payload, 1 refusal that must not fake it).

★ **Coverage side-effect worth noting**: giving `wiki-lint` and `wiki-reindex` an explicit
literal error envelope moved **both out of `_NO_LITERAL_ERROR_ENVELOPE`** — the static-scan blind
spot shrank from 5 CLIs to 3, and literal error envelopes rose 199 → 202. The pin's failure
message asks the author to prefer restoring literal coverage over widening the exclusion; here
the defect fix did that on its own.
