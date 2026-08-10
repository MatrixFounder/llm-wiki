# TASK 074 — close the DF-072-3/4/5 contract-truth triad: the CLI I/O contract says what the CLIs do

<!-- contract:meta -->

## 0. Meta Information

| | |
|---|---|
| **Task ID** | 074 |
| **Slug** | cli-io-contract-truth-triad |
| **Mode** | Standard (Analysis → Architecture → Planning → Development) |
| **Origin** | Operator request (2026-08-10): «разреши issues» over `docs/issues/df-072-{3,4,5}` |
| **Type** | Contract correction (docs) + 1 behaviour fix (envelope key) + 2 population-derived gates |
| **Predecessor** | TASK 072 bead 072-03d (`f0e926e`) — the machine exit-code census that FOUND all three |
| **Files** | `CLAUDE.md`, `AGENTS.md`, `docs/manuals/*` (EN+RU ×2), `skills/wiki-{graph,health,config,lint}/SKILL.md`, `scripts/wiki_skills/wiki_init.py`, `docs/architectures/functional/components.md`, `tests/test_cli_envelope_contract.py` (new) |
| **Schema** | zero DDL (`user_version` stays 7), no new dependency |
| **Exit codes** | **unchanged** for every CLI (see D-074-2 for why) |

<!-- contract:problem -->

## 1. Problem

Three defects filed by the same census, all instances of one class: **a universal claim the
population was never measured against.**

### DF-072-3 (SEV-3, documentation) — «Every CLI emits one JSON envelope + a stable exit code»

Measured 2026-08-10, `bin/` walked at runtime (23 executables, `.sh` installers excluded):

```console
$ for c in $(ls bin/ | grep -v '\.sh$'); do out=$(./bin/$c --definitely-not-a-real-flag-0723 2>/dev/null); \
    printf '%-24s rc=%-3s stdout_bytes=%s\n' "$c" "$?" "$(printf '%s' "$out" | wc -c | tr -d ' ')"; done
…
wiki-query               rc=2   stdout_bytes=0
…
```

**22/22 emit ZERO stdout bytes on an unrecognised flag** (23 `bin/` names; `wiki-import-article`
is a symlink to `wiki-import` and dedupes to the same program) — argparse writes usage to *stderr* and
exits 2 before any `emit()` runs. Three further shapes break the claim on **success** paths:

| Surface | Measured |
|---|---|
| `wiki-search … --format markdown` | exit 0, stdout is **markdown**, not JSON |
| `wiki-sync scan … --dry-run` | exit 0, stdout is a **multi-line human report** (`wiki_sync.py:345`) |
| `wiki-config serve` | exit 0, banner to **stderr**, **no stdout envelope** (`_server.py:564-572`) |

★ The manual also instructs callers to **«branch on `$?`»** (`:1758`, `:2017`; RU `:1810`, `:2076`)
— the exact practice `skills/wiki-verify-multi/SKILL.md:130` and `commands/wiki-verify-multi.md:45`
forbid **in bold**, because that CLI's exit 6 is ambiguous. Two live contracts, opposite orders.

★ Found in the same table row group: `manual.md:142` / `manual.ru.md:147` still say «19 CLIs
(`wiki-*`), **each also** a `/wiki-*` slash command» — false, and already corrected in `CLAUDE.md`
on 2026-08-07. `commands/` holds 17 of 19; `wiki-graph` and `wiki-health` have **no** wrapper.

### DF-072-4 (SEV-2, correctness) — `wiki-lint --strict` returns exit 1 with a SUCCESS envelope

```console
$ ./bin/wiki-lint --strict --vault obsidian-llm-wiki --vault-root docs
{"action": "linted", "vault": "obsidian-llm-wiki", "total_issues": 3577, "by_category": {…},
 "denominators": {}, "vacuous_checks": [], "vacuous_kinds": []}
EXIT=1
```

No `error` key — a normal success payload (`wiki_lint.py:99`). But every corrected exit table in
the repo now says **`1` = unhandled exception, no envelope, raw traceback, NOT a contract error**.
A caller applying the family convention reads a working `--strict` gate as a crash, and
`skills/wiki-lint/SKILL.md` has **no exit table at all** — its only contract line (`:62`) says
«**Always returns success exit `0`**», which the run above falsifies.

`wiki-lint`'s full reachable code set (one `emit()` site + inherited + argparse):

| Code | Envelope | Meaning |
|---|---|---|
| 0 | success | no gating issues, or `--strict` absent |
| **1** | **success** | `--strict` gate tripped ← *undocumented* |
| **1** | **none** | unhandled exception, raw traceback ← *the collision* |
| 2 | none | argparse |
| 6 | error (`INVALID_INDEX_DB`) | inherited from `build_repo_config` (`wiki_lint.py:73`) |

### DF-072-5 (SEV-3, security) — `wiki-init` emits the one key `components.md` forbids

```console
$ ./bin/wiki-init --register-existing --vault $V --db-path $V/t.db     # WIKI_SCHEMA.md: vault_id: BAD--ID!!
{"error": "INVALID_VAULT_ID", "received": "BAD--ID!!", "pattern": "^[a-z][a-z0-9-]{1,30}[a-z0-9]$"}
EXIT=6
```

Reproduced on **all three** emit sites (`wiki_init.py:335` scaffold-new, `:478` register-existing,
`:588` reconcile). `docs/architectures/functional/components.md:291` states the invariant as «every
error envelope emits `{error, field?, reason, violations?}` **only, with NO `content`, `value`,
`raw`, or `received` keys**». A one-token grep would have found this at any point in 14 months.

★ **The population is the defect.** The three envelope-safety canary suites cover
`wiki_alias`, `wiki_merge`, `wiki_query`, `wiki_verify_multi`, `wiki_extract_concepts`,
`wiki_extract_decisions`, `wiki_search`, `wiki_sync` — *the CLIs the invariant was written for*.
`wiki_init` is imported by nine test files and by **none** of them. The one CLI that violates the
invariant is the one CLI the invariant could never fire on — the unenumerated-surface lens,
reproduced inside the machinery built to prevent it (4th recorded recursive instance).

<!-- contract:use-cases -->

## 2. Use Cases

**UC-1 — an integrating agent parses stdout.** A cron job runs `wiki-search … --format markdown`
or mistypes a flag. Reading the contract, it knows *before* writing the call that stdout is not
JSON on those two paths, and that a usage refusal is argparse's (2, stderr, empty stdout).

**UC-2 — an integrating agent wires `wiki-lint --strict` into a gate.** It reads a real exit table
for `wiki-lint`, sees `1` carries **two** meanings, and branches on the envelope (JSON-parseable
stdout with no `error` key ⇒ gate tripped; empty stdout ⇒ crash) rather than on `$?` alone.

**UC-3 — an operator typos a `vault_id`.** `wiki-init` refuses with `{error, field, pattern}`. The
operator learns *which* input was wrong and *what shape* was expected; the offending bytes never
land in whatever consumes the envelope (CWE-117).

**UC-4 — a new CLI is added tomorrow.** It is in scope for both new gates automatically, because
both derive their roster by walking `bin/`. Excluding one requires an explicit entry with a reason.

<!-- contract:acceptance -->

## 3. Acceptance Criteria

| # | Criterion | Verification |
|---|---|---|
| AC-1 | No surviving universal «every/always CLI emits one JSON envelope» claim; each site names the argparse path **and** the three deliberate non-JSON success modes | grep census re-run; 0 hits outside `docs/issues/`, `docs/tasks/`, `docs/plans/`, `docs/archive/` |
| AC-2 | The «branch on `$?`» advice is corrected everywhere (EN ×3, RU ×3) to «branch on the envelope» with the `wiki-verify-multi` / `wiki-lint` ambiguity named | grep `branch on \`\$?\``; RU `ветвитесь по \`\$?\`` |
| AC-3 | `manual.md:142` / `manual.ru.md:147` state the measured command count (17 of 19), not «each also» | read the rows |
| AC-4 | `skills/wiki-lint/SKILL.md` has an exit table fencing the exit-1 divergence exactly as `wiki-verify-multi`'s is; the «Always returns success exit `0`» line is gone | read; `test_exit_code_doc_truth.py` moves `wiki-lint` from partition B to partition A |
| AC-5 | `wiki-init` emits **no** `received` key on any of the 3 sites; the envelope carries `{error, field, pattern}` | `grep -rn '"received"' scripts/` → 0 hits; re-run the 3 repro commands |
| AC-6 | A gate proves the argparse-refusal shape over a **`bin/`-derived** roster: rc 2 + zero stdout bytes | new `tests/test_cli_envelope_contract.py`, parametrised over `_discover_clis()` |
| AC-7 | A gate proves no error envelope in **any** `bin/`-derived CLI carries a forbidden key | same file; AST scan over every emit-site dict literal |
| AC-8 | Both new gates carry a non-vacuity control **and** a mutation control (they can fail) | the controls fail when fed a known-bad probe |
| AC-9 | `wiki-lint --strict`'s divergence is pinned by an **envelope-shape** assertion, not `rc == 1` alone | new test asserts JSON-parseable stdout with no `error` key at rc 1 |
| AC-10 | Full suite green; `mypy --strict scripts/` clean | `pytest tests/`, `mypy --strict scripts/` |
| AC-11 | All three issue files move to `status: fixed` with the resolution recorded; ledger regenerated | `wiki-reindex --full --vault obsidian-llm-wiki --vault-root docs` |

<!-- contract:non-goals -->

## 4. Non-Goals

- **No exit-code change for any CLI.** See D-074-2.
- **No new envelope key.** The discriminator DF-072-4 asks to pin (JSON-parseable stdout without
  an `error` key) already exists; adding a `gated:` key would be a contract expansion the issue
  did not ask for.
- **No removal of the deliberate non-JSON modes.** `--format markdown`, `wiki-sync scan --dry-run`
  and `wiki-config serve` are features. The claim is what was wrong, not the behaviour.
- **No mechanisation of free prose.** `test_exit_code_doc_truth.py`'s docstring states that
  boundary; the two new gates assert **data** (a process's stdout bytes; a dict literal's keys).

<!-- contract:decisions -->

## 5. Decisions

**D-074-1 — DF-072-5 takes option 1 (comply), not option 2 (amend the invariant).**
The invariant exists to close CWE-117 log injection. `pattern` already tells the caller the shape
expected and `field` names the input, so the diagnostic value of `received` is redundant; the only
thing lost is the offending bytes, which is the point. Amending a security invariant to legalise
its single violator is the wrong direction.

**D-074-2 — DF-072-4 takes option 1 (document + fence), not option 2 (move the gate off code 1).**
Three measured reasons, the first of which is decisive:

1. **Option 2 as written does not do what it claims.** It proposes moving the gate signal «to the
   family's `6`». `wiki-lint` already reaches 6 — `INVALID_INDEX_DB`, inherited from
   `build_repo_config` (`wiki_lint.py:73`). Moving the gate there would reproduce the *exact*
   `wiki-verify-multi` ambiguity (6 = error envelope *or* 6 = success envelope) instead of
   removing it. The collision would be relocated, not closed.
2. **Exit 1 on findings is the universal linter convention** (ruff, eslint, shellcheck, flake8).
   The family's «1 = crash» convention is the local outlier; moving `wiki-lint` off 1 would
   surprise every operator who has wired a linter before.
3. **It is pinned by live tests and by five doc surfaces** as the CI gate
   (`tests/test_lint_near_duplicate.py:182`, `tests/test_lint_denominators.py:191`, `README.md`,
   both manuals, `docs/CLAUDE.md:150`). Breaking it buys nothing that (1) does not already refute.

The residual collision is therefore **documented and fenced**, exactly as SEC-4 fenced
`wiki-verify-multi`'s — and it is now **discriminable**, which the issue's own ⚠️ requires: a
crash produces **no envelope at all** (empty stdout), a tripped gate produces a parseable success
envelope. That is the assertion AC-9 pins.

**D-074-3 — the two new gates derive their roster from `bin/`, never from a hand-list.**
This is the actual fix for both DF-072-3 and DF-072-5: a census predicate derived from the
instances already found is not a census. Automatic inclusion, explicit exclusion — reusing
`_discover_clis()` from `tests/test_exit_code_doc_truth.py` rather than re-transcribing it.

<!-- contract:risks -->

## 6. Risks

| Risk | Mitigation |
|---|---|
| The AST forbidden-key scan false-positives on a non-envelope dict (e.g. `_report.py:120`'s `"value"`) | Scan only dict literals passed as the payload arg of an `emit`-suffixed call — the same shape `_reachable_pairs` already proves it can resolve. `_report.py` / `_authoring.py` hits are not emit payloads. |
| The argparse-shape gate spawns 22 subprocesses | ⚠️ **The first draft of this row said "same cost the existing test already pays" — that was false** (`/vdd-multi` P2). The existing usage test skips before spawning for every CLI in `_NO_USAGE_ROW_DOCUMENTED`, so it spawned **4**; the roster now costs **22 + 5 + 2 = 29**. Measured, not estimated: the whole module is **3.0 s** (0.08–0.12 s per spawn), and collection grows 0.33 s → 0.54 s. Timeout cut 60 s → 20 s so a whole-roster hang is ~7 min, not ~22. |
| Adding an exit table to `skills/wiki-lint/SKILL.md` moves it into partition A of `test_exit_code_doc_truth.py`, which then holds it to completeness | Deliberate and desirable. `wiki-lint` will declare its roster **normative** and list all four codes incl. the inherited 6. |
| A doc-only correction drifts again | AC-6/AC-7 convert the two falsifiable halves into gates. The prose halves (`--format markdown` etc.) stay prose, and that boundary is stated. |

<!-- contract:review -->

## 7. Adversarial review (`/vdd-multi`, 3 critics, 2026-08-10)

Verdict **FAIL → fixed**. All three critics returned `issues-found`. Every load-bearing claim was
re-verified against the code before acting; two were overstated and are recorded as such.

**★ The headline: this task's own thesis fired on this task.** The fix for "a universal claim the
population was never measured against" shipped three of its own — corrected below.

| # | Critic(s) | Finding | Disposition |
|---|---|---|---|
| L-01 | logic | `CLAUDE.md`/`AGENTS.md`/manual (EN+RU) said «**Both** halves are gated» while the gate's own CANNOT block disclaims the three non-JSON modes | **Fixed** at 4 sites: boundary 1 gated, boundary 2 a maintained list, each labelled |
| L-02 · F2 | logic + security | `_NO_LITERAL_ERROR_ENVELOPE` measures CLIs with **zero** literals; a CLI keeping one could add unlimited invisible envelopes. «The blind spot cannot grow by omission» was **false**. Measured: **41 invisible emit sites, 10 in "covered" CLIs** | **Fixed**: `_NON_LITERAL_EMIT_SITES` pins the per-CLI count |
| L-05 · F11 | logic + security | `_common.py` — the shared emitter carrying `INVALID_INDEX_DB` for **every** `wiki-*` CLI — was outside all 22 scan sets; "every source file of every CLI" was false | **Fixed**: `test_no_shared_emitter_carries_a_forbidden_key` over a computed set difference |
| L-10 | logic | Error-bearing classification was top-level-only; a leak nested in a *success* payload (`skipped[]`, `violations[]`) was invisible | **Fixed**: any-depth classification + a mutation-control case |
| L-03 | logic | The manual's exit-`1` row named `wiki-lint` as the sole divergence; `wiki-init` (`MISSING_VAULT_ARG`) and `wiki-import` (`EXIT_USAGE=1`) also return **error envelopes at 1** | **Fixed** in EN + RU |
| F1 · L-04 | security + logic | `wiki_init.py:460` still echoed `str(args.vault)` verbatim — same CWE-117, under a key the denylist doesn't cover, 19 lines from a site this task "fixed" | **Fixed** → `{error, field, reason}`; Gate B's claim reworded to what it proves (**key names**, not values) |
| F3 | security | `reindex.py` emitted `str(e)` from a bare `except Exception` into `skipped[]`, which `wiki-reindex` prints verbatim — in a CLI this task **pins as a blind spot** | **Fixed** → `type(e).__name__`. ⚠️ *Critic overstated*: the reachable messages carry paths + line/column, **not** literal source bytes, so the narrow H-6 clause was not broken |
| L-08 | logic | `_validate_vault_id` had no type guard — `vault_id: 2026` (int), `yes` (bool), a date or a list are **truthy**, reached `.match()` → TypeError, exit 1, empty stdout | **Fixed**: `isinstance` guard, matching `factory.py:114` |
| L-19 · F9 | logic + security | `reconcile()` lacked the `FileNotFoundError` guard its sibling has → traceback on a typo'd `--vault` | **Fixed** → `VAULT_NOT_FOUND` at 6 |
| L-07 | logic | The new `reason` ternary reported "has no vault_id" for **unparseable YAML** — misleading when the file plainly has one (this file's own DF-3 bug) | **Fixed**: `_frontmatter_defect()` names the category, value-free |
| L-20 | logic | The new `wiki-lint` exit table called exit-1-no-envelope "a bug/environment fault"; a malformed `--vault` and an iCloud `--db-path` both raise there — plain user input | **Fixed**: row now says so |
| F10 | security | `components.md:291` states the invariant as an allowlist **and** a denylist; only the denylist is true or enforced | **Fixed**: restated as the enforced denylist |
| F12 | security | «the token must never land in a logged stdout» overstates — stderr is not a confidentiality boundary | **Fixed**: names the real protections (fragment, bind, HMAC) |
| L-12 · P2 · P12 | all three | Three transcribed counts wrong in a task about not transcribing counts: `23`→**22** CLIs, `18`→**17**, PLAN `16`→**19** | **Fixed**, each re-measured |
| P2 | perf | The risk row's "same cost the existing test already pays" was false — 4 spawns vs 22 | **Fixed** with measured numbers |
| P1 · P3–P6 | perf | Import-time AST work; redundant parses; 60 s timeouts | **Measured, then fixed proportionately**: lazy `lru_cache` (collection +0.21 s, now amortised), timeouts 60→20 s / 120→45 s. ⚠️ *Critic's 3–11 s estimate refuted by measurement*: the whole module is **3.0 s** |
| L-11 · L-13–L-18 · L-21–L-23 · P10 | logic + perf | Pin remedies invited the wrong fix; `splitlines()[-1]` tolerated stray stdout; fixture asserted only `> 0`; `_literal_keys` descended into `Call`/`Lambda`; unanchored wrapper regex | **All fixed** |
| F4 · F5 · F8 | security | `obsidian-*` echo an unallowlisted plugin `reason`; two TSV emitters don't escape; `_global_` accepted as a `vault_id` | **Filed, not folded in** — genuinely outside this diff: DF-074-1, DF-074-2, DF-074-3 |
| P5 · P7 · P8 | perf | Parallelise the 22 spawns; `@pytest.mark.slow`; share the lint fixture | **Declined with measurement**: the module is 3.0 s total; marking it slow would remove the gate from local loops to save ~3 s |
| F7 · F13 · F14 · P11 | security + perf | `pattern` safe to echo; H-5 manifest correct (no re-pin owed); no subprocess side effects; zero runtime cost | **No action — confirmed clean** |

★ **What the review proves about the mechanism**: the blind spot the gate *declared* was hiding a
real defect (F3), and the gate's own coverage claim was the thing that hid it. Declaring a blind
spot is not closing it; **counting** it is the weaker but honest guarantee, and it is what ships.
