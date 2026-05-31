# PLAN — TASK 010 (`wiki-verify` eval-v3, adversarial reasoning extension)

> Decomposes [TASK.md](./TASK.md) (RTM 10.1–10.8) into Stub-First beads. The full
> design rationale + schema-valid case drafts live in the approved session plan
> (`~/.claude/plans/agile-giggling-corbato.md`). **Zero code/schema change** — fixtures
> + one new test module + a recorded orchestrator-run measurement. v3 is a separate
> file, so the committed v1/v2 reproducibility pins stay byte-identical.

## Stub-First strategy (applied to an eval set)

The "stub" here is the **case skeleton + the well-formedness test**: author the cases,
stand up the deterministic invariant test (RED while spans/verdicts are wrong → GREEN
when they resolve and `_is_fail`-match). Only once well-formedness is GREEN do we run
the (LLM) 4-critic measurement and pin its reproducibility. This keeps every deterministic
artifact CI-locked before any orchestrator-run step.

## Beads

| Bead | Title | RTM | Outputs | Gate |
|---|---|---|---|---|
| **010-01** | 18 seeded cases (groups 1–4) | 10.1–10.4 | `evals-v3.json` (seeded portion, ids 33–50) | well-formedness test (010-02) green on seeded |
| **010-02** | well-formedness test | 10.6a-b | `tests/test_wiki_verify_v3.py` | RED→GREEN; v1/v2 pins untouched |
| **010-03** | 4 natural multi-doc cases | 10.5 | synthetic sources in `samples/eval-bench/` (scratch) → `wiki-query` organic answers → dual-blind consensus labels → `evals-v3.json` ids 51–54 | well-formedness green on all 22 |
| **010-04** | orchestrator-run measurement | 10.7a | `reports/v3/shipped-run-outputs.json` + `shipped-grading.json` | `grade_run` deterministic |
| **010-05** | reproducibility pin + report | 10.6c, 10.7b-c | repro-pin test in `test_wiki_verify_v3.py` + `reports/v3/benchmark-v3.md` | repro-pin green |
| **010-06** | docs + regression verification | 10.8 | `README.md` v3 section (KNOWN_ISSUES D-010-1 already added) | full `pytest tests/` green + `mypy --strict scripts/` |

## Bead detail

### 010-01 — 18 seeded cases (ids 33–50)
- Mirror the v2 case shape exactly (`id,name,domain,construction,question,answer,examined,
  injection_class,expected_findings,forbidden_findings,expected_verdict,expected_exit`).
- Groups & ownership per TASK RTM 10.1–10.4. Each group has a clean/FP-guard PASS counterpart.
- 3b conflict cases → `completeness`/`medium` ⇒ `expected_verdict:"pass"`, exit 0 (D-010-1;
  the gate doesn't fail on completeness). A fabricated-third **fail** bridge proves the suite
  still gates a conflict scenario when a real fabrication is present.
- Spans **verbatim** substrings of `answer` or an `examined` body; two-finding cases use
  **distinct** `defect_id`s; negation spans scoped to the polarity clause.

### 010-02 — well-formedness test (`tests/test_wiki_verify_v3.py`)
- Mirror `test_wiki_verify_v2.py`: `len==22` (after 010-03; assert seeded count first if split),
  domain count, ids unique, `construction ∈ {seeded,natural}`.
- Per-case invariants for BOTH constructions: lens/severity vocab; `span ⊂ answer + " " +
  join(bodies)`; unique `(defect_id,lens)`; `_is_fail([{lens,severity:min_severity}…],"high")
  == (verdict=="fail")` and `expected_exit == 6 if fail else 0`.
- Import `_is_fail`/`_SEV_ORDER`/`_VALID_LENSES` from the shipped gate (no reimplementation).

### 010-03 — 4 natural multi-doc cases (ids 51–54)
- Author the synthetic multi-source articles into `samples/eval-bench/` (gitignored scratch),
  register/index, run `wiki-query` to produce **organic** answers over them.
- **Dual-blind consensus label**: two independent labeler passes (sub-agents) blind to the
  scoped lens prompt and to each other → reconcile to consensus; drop unresolved disagreements.
- Encode `construction:"natural"`, `defect_id`=`nat-NNN-<lens>`, consensus
  `expected_findings`/`verdict`. Only inline bodies are committed (not the scratch vault).
- Focus: composition + cross-source conflict (where organic behavior is most revealing).

### 010-04 — orchestrator-run measurement
- Run `workflows/wiki-verify-eval.md` over all 22 cases against the **shipped** `SKILL.md`.
- Critics **blind** to `expected_findings`; each block H-6-fenced. Batch by group; echo `4×22=88`.
- Record `shipped-run-outputs.json` (`{case_id:[4 critic outputs]}`) + `shipped-grading.json`
  (`grade_run` output). Pin `SKILL.md` blob hash + `evals-v3.json` hash + run date in the report.

### 010-05 — reproducibility pin + benchmark-v3.md
- Add `test_v3_shipped_grading_reproducible`: `grade_run(cases, committed-run)==committed-grading`.
- `benchmark-v3.md`: per-group rollup (recall / severity-match / verdict-match / FP /
  unsanctioned-purity), **seeded vs natural broken out**; flag any class the shipped prompt misses.

### 010-06 — docs + regression verification
- README v3 section (case shape unchanged; note multi-source + the 4 groups + the natural mix).
- Full `pytest tests/` green (≥709 baseline + v3); `mypy --strict scripts/` unaffected;
  v1/v2 pins byte-identical (`test_wiki_verify_v2.py`, `test_wiki_verify_evals.py` green).

## Regression safety (carried from the approved plan)

1. **Adding the dataset is provably non-regressive** — v3 is a separate file; `grade.py` +
   committed v1/v2 run-outputs untouched ⇒ v1/v2 pins byte-identical. The new tests EXPOSE
   gaps; they don't change production behavior. TASK 010 cannot worsen prior results by construction.
2. **A future prompt change (deferred 3b rule / miss-driven fix) is gated separately** — full-
   corpus v1+v2+v3 A/B; accept only if v1+v2 metrics are non-degrading (`recall_rate`,
   `verdict_match_rate`, `injection_recall_rate` ↑/=; `unsanctioned_purity_violations`,
   `false_positive_count` ↓/=) AND the v3 target improves; per-case diff (not just aggregate)
   against the committed `enriched-v4-grading.json` floor.
3. **No gaming** — ground-truth fixed before critics run (seeded mechanical; natural
   consensus-labeled blind to the prompt); critics blind to `expected_findings`.

## Out of scope
- `SKILL.md` conflict-lens sentence (separate security-reviewed PR; D-010-1 in KNOWN_ISSUES).
- Any miss-driven prompt fix; a v2+v3 superset file.
