# 030-00 — Baselines + semantic pins (Phase 1)

**RTM:** R-030-5 (baseline leg) + the F-8 test-gap closure. **Depends:** —.

## Goal
Freeze the ground truth BEFORE any engine change: benchmark baselines committed,
and the semantics the rewrite must preserve pinned by GREEN tests on the CURRENT
engine.

## Steps (order binding)
1. Capture baselines (venv, quiet machine, 3 runs, keep medians):
   `python -m scripts.benchmark --n 1000 --output docs/benchmarks/030-baseline-n1000.json`
   and `--n 10000 --output docs/benchmarks/030-baseline-n10000.json`.
2. Build the two walk fixtures (committed under `tests/fixtures/walk030/` as
   builders, generated content under `tmp_path` at test time):
   - **PARA-synthetic** ≥2k files (obsidian-personal shape: `NN - Area/Sub/**`,
     `_daily/`, `_inbox/`, planted `**/_raw/**` + `.obsidian/**` subtrees);
   - **fat-karpathy**: standard karpathy tree + planted `.obsidian/`, `.git/`,
     `attachments/` subtrees with many files.
   Record the CURRENT engine's wall-time + scandir counts for both (monkeypatched
   `os.scandir`/`pathlib` counter) into `docs/benchmarks/030-walk-baseline.md`.
3. Write the **GREEN semantic pins** (must pass on the current engine — they pin
   semantics, not the bug):
   - `test_iter_pages_overlap_first_match_wins` (AC-3.1): root `NN - Area.md`
     under obsidian-personal → exactly ONE DiscoveredPage, entry-6 attribution
     (`project=<Area>`, `extra_tags` incl. `moc`) — closes the F-8 gap.
   - `test_iter_pages_symlink_parity_*` (AC-3.5, 5 cases on the CURRENT engine):
     (i) `**`-only-reachable symlinked dir NOT descended; (ii) explicit non-`**`
     segment symlinked dir descended; (iii) leaf file symlink discovered;
     (iv) overlap+symlink attribution (`Areas/**/*.md` + `Areas/*/notes/*.md`,
     `Areas/link` symlinked → attributed to the explicit entry); (v)
     `**`-beyond-symlink subtree NOT discovered. All five GREEN on `Path.glob`
     today — they pin the union semantics the alive-set must reproduce.
   - (The A6 case-only-rename test moved WHOLLY to 030-01 — it observes post-fix
     behavior and cannot be green on the current engine; plan-review MED.)
4. mypy `--strict` + full suite green (nothing changed but tests/fixtures).

## Acceptance
- ✅ Baseline JSONs + walk-baseline note committed; `docs/benchmarks/` convention
  declared in PLAN §Methodology (evidence JSONs; §8.4 stays canonical narrative).
- ✅ All new pins GREEN on the current engine; zero existing tests modified.
- ✅ Counter instrumentation utility lives in `tests/` (not `scripts/`).
- ✅ Sarcasmotron pass on the bead diff.
