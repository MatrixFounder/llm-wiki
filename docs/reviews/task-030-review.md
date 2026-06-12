# TASK 030 — task-review record (3-perspective adversarial, 2026-06-12)

Mode: parallel 3-reviewer workflow (fact-check / requirements-quality /
architecture-consistency), each instructed to falsify, not approve.
Iteration 1 verdicts: **3× NEEDS-REVISION** → all findings incorporated into
`docs/TASK.md` v2. Iteration 2: APPROVED (changes verified against each finding
below).

## Findings → resolutions (v2)

### fact-check
- **[HIGH] F-6 falsified** — post-wipe pre-SELECT CAN hit "unchanged" (within-batch
  equal-hash `(slug,project)` collision), and skipping it flips which `file_path`
  survives (first→last). → F-6 rewritten; the flip is recorded as a deliberate,
  correctness-positive delta (aligns DB with the TASK-021 `kept` record); new
  AC-2.6; excluded from the AC-2.1 parity corpus.
- **[HIGH] Swap/rotation renames** (destination path already in `pages.file_path`)
  invisible to the membership predicate; postcondition overclaimed. → Goal +
  UC-30-1 postcondition scoped to "previously-unindexed path"; new A5 residual
  (detectable via `wiki-lint` hash-drift; remedy `--full`); recorded for the
  DF-029-1 resolution note.
- **[MED] F-5 strawman** — the issue plan's trigger-drop + manual FTS bulk-INSERT
  is mechanically workable; rejection re-grounded on: runtime DDL, crash-window
  silent FTS desync, multi-vault shared `pages_fts`. → F-5 rewritten; UC-30-4
  amends the issue file + ROADMAP:608 with the corrected rationale.
- **[MED] Mid-file DML error semantics under chunking** unspecified. → UC-30-2 A2:
  stated equivalence to today's committed-partial end-state; error-path test added.
- **[MED] Stale-DB `UNIQUE(vault_id, file_path)` IntegrityError aborts the whole
  delta.** → F-14 added; per-file `sqlite3.Error` catch (TASK-015 precedent);
  UC-30-1 A4 + AC-1.6, order-independence tested.
- **[LOW] AC-2.1 timestamps** → parity test excludes/freezes volatile columns.
- **[LOW] rel-path string convention** → pinned in F-2 (`str(relative_to())`, no
  `as_posix()`); `reindex.py:396` comment listed in files-to-touch.
- **[LOW] citation drift** (benchmark.py lines) → corrected (F-11).

### requirements-quality
- **[HIGH] swap class** → as above (A5).
- **[HIGH] old-path re-created by a new file in-batch** → A4 + AC-1.6.
- **[MED] case-only rename / NFC-NFD** → A6 + AC-1.7; posture stated
  (self-consistent per-OS; spurious re-ingest lands on the hash short-circuit).
- **[MED] AC-1.4 envelope opacity** → reversed: additive `new_path_ingested`
  field (TASK-020/021 visibility precedent).
- **[MED] non-objective tolerances** → ±5% of baseline p95 pinned (AC-1.5, AC-3.4).
- **[MED] AC-2.4 commit-count mechanism** → `set_trace_callback`, exact assertion
  `ceil(N/K) + C` at two N values, C documented.
- **[MED] compound R-rows** → prune split out as R-030-6 with dedicated AC-3.3.
- **[LOW] crossref Q-030-3↔R-030-1** → fixed; walk deltas enumerated in Q-030-2 v2.
- **[LOW] boundary cases** → AC-1.8, AC-2.7, AC-3.6.
- **[LOW] AC-2.3 not testable** → split: mechanical oracle (own-tx still raises in
  open tx; helpers private) + audit moved to PLAN review step.
- **[LOW] RTM hygiene** → verification columns completed; multi-UC rows noted.
- **[LOW] ship-separability** → stated in §0.

### architecture-consistency
- **[HIGH] doc enumeration incomplete** (README:421, both templates, both manuals,
  karpathy.yaml comment) → F-12 expanded to the nine + two design texts; AC-4.1
  grep widened repo-wide.
- **[HIGH] karpathy "root tree never walked" property destroyed by a naive
  single-pass walk** → new R-030-6 descent predicate (prefix-match paths[] globs +
  prunable ignores); AC-3.3(ii) fat-fixture instrumented test.
- **[HIGH] symlink no-descend silently deletes indexed rows; posture claim
  selective** → Q-030-2 v2 reversed to EXACT `Path.glob` parity (F-10, empirically
  confirmed on 3.14); AC-3.5.
- **[MED] case-sensitivity third delta unenumerated** → UC-30-3 A4 +
  Q-024-residual-2 amendment scheduled.
- **[MED] functional-architecture.md:213-219 single-tx claim stale** → UC-30-4 (2).
- **[MED] equal-hash collision corner** → AC-2.6 (joint with fact-check HIGH-1).
- **[MED] YAGNI gate substitution** → §0 "operator override" note; §3.5 wording
  update scheduled.
- **[MED] Q-021-2 invariant unpinned** → A2 invariant stated
  (seeded ∩ ingested = ∅) + composite test in AC-1.3.
- **[LOW] ROADMAP P2 mechanism text refuted** → UC-30-4 (3).
- **[LOW] NFC/NFD posture** → A6.

## Verified-clean (carried forward as constraints)
Zero-DDL across all requirements; M-4/M-1 preserved by construction; TASK-021
L-1/L-2/self-update guards green as designed; in-vault symlink tolerance
(TC-UNIT-02) untouched.

---

# Gate 2 — arch+plan review (3-perspective, 2026-06-12)

Reviewers: arch-review / plan-review / spec-validator. Iteration 1 verdicts:
**3× NEEDS-REVISION** → all findings folded into TASK.md v3 + ARCHITECTURE
Q-030-2/5/6 v3 + PLAN/beads. Key findings → resolutions:

### Blocking (design changed)
- **[HIGH arch + HIGH plan] A6 non-convergence / AC-1.2 unsatisfiable** — the
  `upsert_page` "unchanged" short-circuit returns BEFORE any UPDATE, so a
  moved-but-unedited file's `file_path` would never refresh → perpetual
  re-detection on every delta (loop, not a wave). → R-030-1 gains a targeted
  `UPDATE pages SET file_path=…` on the `is_new_path ∧ unchanged` outcome
  (zero-DDL, repo-conn precedent — NOT via the 030-02 helper, preserving
  030-01 ⊥ 030-02); new AC-1.9 convergence test (second delta = true no-op);
  A8 persistent-skip retry documented.
- **[HIGH arch] chunk lock-hold across file I/O** — K=500 in-txn derivations
  ≈ 10 s write-lock holds vs the 5 s default busy timeout → writer starvation on
  shared `global.db`; unbounded on cold iCloud. → **stage-then-flush** (Q-030-5
  v3): derive OUTSIDE the txn into a K∧32 MiB-capped buffer; flush DML-only
  (ms-scale lock); lock-hold guard test (AC-2.4b); derivation errors now
  isolated OUTSIDE the txn (strictly better than today).
- **[HIGH spec + MED arch] symlink+overlap parity hole** — boolean any-pattern
  descent + symlink-blind attribution would inflate the match set and flip
  attribution on operator layouts (counterexample `Areas/**/*.md` +
  `Areas/*/notes/*.md` with a symlinked `Areas/link`). → **per-pattern
  alive-sets** threaded down the walk (Q-030-2 v3): symlinked component keeps a
  pattern alive only via an explicit non-`**` segment; attribution restricted to
  patterns alive at the containing dir; AC-3.5 gains cases (iv)/(v); 030-04
  property test strengthened to full DiscoveredPage-tuple equality incl. symlink
  fixtures.
- **[HIGH plan] AC-4.1 grep blind to wrapped lines; tenth surface found** —
  `CLAUDE.md:387-388` (live per-session instructions) wraps the pattern across
  lines. → F-12 = TEN surfaces; AC-4.1 uses `rg -iU` multiline + a defined
  adjudication allowlist; new AC-4.4 (CLAUDE.md annotation + Q-030-3 doc leg).
- **[MED spec] `RecursionError` DoS on a recursive walk** → iterative
  explicit-stack walk REQUIRED + AC-3.8 ≥1500-deep fixture + PLAN risk row.

### Folded (spec/plan precision)
- AC-2.1 parity mechanism decided: public-DAL replay loop (no production seam,
  no golden dump). AC-2.4: constrained fixture (zero log events), both BEGIN
  forms, C composition in-test; "per-page commits" wording. Q-030-5(ii) fatal
  injection = monkeypatched COMMIT. 030-00's A6 pin moved wholly to 030-01
  (cannot be green pre-fix); case-only rename tests name their layout
  (lowercasing vs identity). `new_path_ingested_total` in `--all-vaults`
  (+`wiki_reindex.py` in files-to-touch). AC-3.7 assigned (030-05 diff-review).
  AC splits declared (AC-1.5/2.3/2.5). `docs/benchmarks/` convention declared
  (§8.4 stays canonical). `tdd-strict` named for 030-01/030-05. A7 = stale-mtime
  edit scenario. Entity-page boundary pinned (`entities.file_path` refreshes on
  `--full` only — postcondition scoped, concept-page e2e sibling). Karpathy
  root-scandir footnote ("root subtrees"); Q-030-6 PROPER-prefix rule; F-6
  pre-SELECT skip recorded as alignment-motivated. Q-030-2 wording fix
  (`is_dir(follow_symlinks=True)` + `is_symlink()` gate).

### Verified-clean (gate 2)
Descent predicate sufficient+necessary for all three built-ins (no under-descent
constructible); membership predicate vault-scoped + convention-consistent
(`UNIQUE(vault_id, file_path)` per-vault); RTM→bead coverage complete; 030-04
genuinely unwired; 030-00 pins genuinely green-today; commit-count/F-6 tests
genuinely RED-today; all nine+ doc-surface line refs spot-checked real at HEAD;
Q-030-1 three legs land in beads; no-auto-commit stated; benchmark CLI
signatures match the beads' assumptions.

---

# Close-out record (bead 030-07) — AC-4.1 adjudication table

`rg -iU 'full[^.]{0,60}rename|rename[^.]{0,60}full'` (TRUE-multiline variant — the
`[^.\n]` form cannot produce the wrapped `CLAUDE.md:387` row below; corrected per the
030-07 iter-2 STYLE note) repo-wide, allowlist =
archived records (`docs/tasks/`, `docs/plans/`, `docs/reviews/`,
`.agent/sessions/`, `skills/obsidian-cli/evals/reports/`). Every surviving hit,
individually adjudicated (zero live `--full`-for-ordinary-rename prescriptions):

| hit | class | verdict |
|---|---|---|
| `templates/CLAUDE.md.tmpl:296`, `docs/issues/df-029-1:44-45`, `README.md:11` | NEW corrected wording (`--delta`-first; `--full` = fallback/swap remedy) | allowed |
| `CLAUDE.md:387`, `docs/ARCHITECTURE.md:290,449`, `docs/ROADMAP.md:314-315` | superseded/historical annotations (TASK 029 record, explicitly marked superseded by TASK 030) | allowed |
| `docs/ARCHITECTURE.md:~1330` (Q-030-4), `docs/TASK.md` F-12/AC-4.1 text | design/task records DESCRIBING the flip | allowed |
| `tests/test_task030_delta_rename.py:374`, `tests/test_wiki_reindex_delta.py:151` | test identifiers (`…entities_on_full_only`, `reindex_full(r, "renamev")`) | allowlisted |
| `skills/obsidian-cli/references/recipes.md` fallback block | `--full` explicitly CONDITIONED on pre-TASK-030 frameworks / the swap-class residual | allowed |

Gate verdict: **PASS** (substantively confirmed independently by the 030-07
Sarcasmotron's own adjudication, which reached the identical conclusion).

**Iteration-2 honesty note (recorded per the Sarcasmotron's demand):** the iter-2
refinement report claimed README:498 was "likewise de-numbered" — it was NOT (the
`str.replace` silently no-op'd on a wording mismatch; no assert guarded it). Caught
by the reviewer's grep; fixed in iteration 3 (`README.md` now contains zero stale
count strings — verified `grep -c 1083 README.md` == 0).
