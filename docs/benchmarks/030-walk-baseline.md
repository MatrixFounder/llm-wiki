# TASK 030 — walk baseline (bead 030-00, CURRENT per-glob engine)

Captured 2026-06-12, macOS (APFS), Python 3.14.4, current `iter_pages`
(one `Path.glob` per `paths[]` entry). Fixtures: `tests/walk030_util.py`
builders (`build_para_vault` ≥2k files; `build_fat_karpathy_vault`).
Instrumentation: `tests/walk030_util.count_scandirs` (os.scandir spy).
KEY CONTRACT (corrected per the 030-00 Sarcasmotron MED-1): counter keys are
`os.path.normpath(os.fspath(path))` in the CALLER's spelling — the globber
resolves nothing, and macOS `/var` ↔ `/private/var` aliases stay distinct
key strings. Zero/exact-count assertions MUST go through
`walk030_util.count_for(counts, dir)` (resolved-path comparison) — a direct
`counts[str(d)]` lookup can pass vacuously on a spelling mismatch.

## PARA-synthetic (obsidian-personal layout) — 2084 indexable files

| metric | value |
|---|---|
| `os.scandir` calls (one `iter_pages`) | **140** |
| distinct directories enumerated | 69 |
| directories enumerated >1× | **69 (all)** — histogram: 68 dirs ×2, root ×4 |
| wall time, median of 3 | **94.1 ms** |

The R-X1-OBS-WALK ~N× re-walk confirmed: the vault root is scandir'd 4×
(entries 4/5/6/7), every other dir ≥2×. Ignored subtrees (`**/_raw/**`) ARE
traversed and only post-filtered (the issue file's "Prevention" overstatement,
TASK 030 F-7).

## fat-karpathy — 110 indexable files + 600 planted fat files

| metric | value |
|---|---|
| `os.scandir` calls | 25 |
| distinct directories enumerated | 11 |
| `.obsidian/` / `.git/` / `attachments/` enumerations | **0** (never walked today — the §3.5 property the 030-05 rewrite must preserve BY CONSTRUCTION) |
| wall time, median of 3 | 2.1 ms |

## AC-3.3 targets (030-05)

- PARA: every directory scandir'd EXACTLY once (≈69 calls, was 140); `_raw`
  subtrees 0× (prunable-ignore).
- fat-karpathy: fat subtrees stay 0×; root gains exactly ONE scandir
  (footnoted delta — Q-030-6).
- AC-3.4: PARA wall-time strictly improved; lean karpathy/dev-project within
  ±5% of this baseline protocol.

## SLO baselines (same machine, `scripts/benchmark.py`, report-only)

See committed JSONs: `030-baseline-n1000.json`, `030-baseline-n10000.json`.
**Provenance (bead protocol, Sarcasmotron MED-2):** each JSON is the median of
THREE harness invocations, keyed by `wiki-reindex-full` p95; all three per-run
values are recorded in the JSON's `_provenance` block (the harness itself runs
the full op once per invocation — `scripts/benchmark.py:169`, pre-existing).
±5% tolerances (AC-1.5/2.5/3.4) bind to the kept-median numbers on THIS
machine, using the same 3-invocation protocol for the AFTER capture (030-06).
