# TASK 017 — Perf + security hardening: drift/delta walk + per-file regex deadline (P-2 · P-3 · R-X1-REDOS-RT)

### 0. Meta Information
- **Task ID:** 017
- **Slug:** `drift-delta-redos-timeout`
- **Mode:** VDD (full pipeline — `/vdd-start-feature`)
- **Status:** ✅ **SHIPPED (uncommitted)** — all 14 beads (017-00…13) done via `/vdd-develop-all`
  (per-phase Sarcasmotron + HITL gates) **+ `/vdd-multi` post-ship hardening (3 critics →
  convergence: logic ✓ security ✓ performance ✓)**. **Zero DDL** (`user_version` 5).
  **908 pytest passed (+4 skipped), `mypy --strict` clean (69 files).** OQ-1..4 resolved in
  Architecture (§11a Q-017-1..4). TASK 016 archived in lockstep.
  - **`/vdd-multi` fixes folded in:** **HIGH** — `derive_project_for_path` was calling
    `_derive_project` **unguarded** (operator `project_pattern` ran under stdlib `re` on the
    `wiki-extract-concepts` ingest path → ReDoS-bypass + `re.error` crash on regex-only syntax);
    now threads `operator_supplied`. **MED** — `_FM_TYPE_RE` matched `type:foo` (no space, a YAML
    plain scalar) where PyYAML yields None → `[ \t]*`→`[ \t]+`. **LOW** ×4 — `guarded_*` fail-CLOSED
    on `deadline=None`; `WIKI_REDOS_BUDGET_S` clamped ≤60 s; `iter_pages` stats only post-filter
    survivors; +NF2 spy test (regex engine not called for built-ins) + doc-drift fix. Deferred
    (critic-agreed out of scope): R-X1-CFG-COST resolve memoization (pre-existing), DST-fold mtime edge.
  - **Benchmark (A/B, `scripts/benchmark.py`):**

    | Op (p50) | before | after n=1000 | after n=10000 | SLO@1k / @10k |
    |---|---|---|---|---|
    | **wiki-lint** | 155.2 ms | **33.7 ms (4.6×)** | 319 ms | 2000 / 30000 |
    | **wiki-reindex-delta** | 21.3 ms | **17.5 ms** | 162 ms | 500 / 2000 |

    The P-3 win is larger than first estimated: per-file PyYAML `safe_load` *dominated* drift
    cost, so the regex `type:` fast-path alone gives 4.6× on `wiki-lint` in **default**
    (always-hash) mode — no `--mtime-skip` needed. All SLOs pass with 12–94× headroom at 10k.
  - **Roast fixes folded in:** LOW (extract_refs built-in pre-compile; `_validate_path_patterns`
    regex-aligned) + MED (`check_drift` mtime compare crash-proofed against aware/naive datetimes).
- **Baseline gate (pre-task, on `main` HEAD `535f59b`):** 879 pytest (+4 skipped),
  `mypy --strict` clean (69 files), `user_version` 5.
- **Closes:**
  - `docs/issues/r-x1-redos-runtime-deadline-residual.md` (**R-X1-REDOS-RT**, SEV-2, security) — the only open SEV-2
  - `docs/issues/p-3-check-drift-re-hashes-every-file.md` (**P-3**, perf)
  - `docs/issues/p-2-reindex-delta-no-op-walk-cost.md` (**P-2**, perf)

> **Operator decisions locked in Analysis (carry into Architecture):**
> - **D-017-A (ReDoS mechanism):** use the **PyPI `regex` library with its built-in
>   `timeout=`** for operator-supplied patterns. Cross-platform + thread-safe + the engine
>   *actually* interrupts a catastrophic search because the deadline is checked **inside**
>   its backtracking loop. The pure-stdlib alternatives were rejected (each verified on this
>   repo's CPython 3.14.4, standard GIL build):
>     - **`signal.alarm` (SIGALRM):** Unix- and main-thread-only; the handler runs only
>       *between* Python bytecodes, so it may not even break a single C-level `re.search`.
>     - **thread + `join(timeout)`:** unsound — CPython has no thread-kill API, and stdlib
>       `re`/`sre` holds the **GIL for the whole match**. Measured: a catastrophic search in
>       a worker thread froze the *entire* interpreter for its full duration — `join(0.3)`
>       did not return until ~1.37 s (it can't reacquire the GIL), and the main thread ran
>       **zero** iterations until the regex finished. The worker is an **un-killable runaway
>       thread** pinning a core (NOT an OS "zombie" — that term belongs to the subprocess
>       case). No real timeout, no live main thread.
>     - **subprocess + kill:** *sound* (the OS can SIGKILL → core actually freed) but heavy
>       (process spawn + body IPC per file) and carries the real zombie/`wait()`-reap burden.
>   **Verified empirically (CPython 3.14.4 + `regex` 2026.5.9, this repo's `.venv`):** on a
>   pattern catastrophic *under the `regex` engine* (`(a|a)*$`, ~2.8 s uninterrupted),
>   `search`/`finditer` with `timeout=0.5` raised the **builtin `TimeoutError`** at
>   **500.2 ms (+0.2 ms overshoot)** even on a **100 KB single-line** body — no hang. Bonus:
>   `regex` *releases the GIL* during matching (6.4 M main-thread iterations ran concurrently
>   vs **0** under stdlib `re`), and it optimizes away several `re`-catastrophic shapes
>   (`(a+)+$`, `(x+x+)+y`) outright — a net ReDoS reduction. **Caveat (→ Architecture):**
>   patterns are operator-authored for stdlib `re`; `regex` is a near-superset (V0 mode =
>   `re`-compatible) but a *different engine*, so running them under `regex` is a documented
>   dialect change, and the load-time `_redos_budget_check` gate should compile/probe under
>   `regex` too for consistency. Cost accepted: **one new dependency**, knowingly relaxing
>   the TASK 012 stdlib-only ReDoS posture for a sound runtime guarantee. The exception is
>   the **builtin `TimeoutError`** (NOT `regex.TimeoutError` — verified). *(operator-confirmed twice)*
> - **D-017-B (P-3 drift default):** **always full-hash by default** (integrity-first —
>   `check_drift` catches Class A↔B tampering, so a preserved-mtime edit must NOT slip).
>   The mtime short-circuit is **opt-in only**. The cheap default win is the
>   PyYAML→regex fast-path for the `type:` field.
> - **D-017-C (DDL):** **Zero-DDL, mtime-only.** `last_modified` is already persisted in
>   `pages`; do **not** add a `file_size` column. `user_version` stays **5**.

---

### 1. General Description

Three open backlog items share the same maintenance surface (`reindex` / `check_drift` /
the config-driven layout walk) and ship together as one bounded hardening task. One is a
real security debt; two are scale-readiness perf fixes the operator flagged as imminent
(*"1k pages will arrive soon; 10k is the real wall"*).

1. **R-X1-REDOS-RT (SEV-2, security — top priority).** The PW-D ReDoS gate
   (`layout_config._redos_budget_check`) vets operator-supplied `ref_extraction[].regex`
   and `paths[].project_pattern` at config-load against *short* adversarial payloads. A
   pattern that is linear on those short payloads but catastrophic only on **long real file
   content** (e.g. a 100 KB single-line body) slips through — stdlib `re` has **no timeout**,
   so a catastrophic `pattern.finditer(line)` in [`extract_refs`](scripts/wiki_source/parsing.py#L97)
   or `re.compile(...).search(rel_posix)` in [`_derive_project`](scripts/wiki_index/layout_config.py#L429)
   can hang `wiki-reindex` indefinitely on a crafted page. A load-time synthetic gate can
   never be complete; the only sound mitigation is a **runtime deadline at the consumer**.

2. **P-3 (`check_drift` re-hashes every file).** [`SQLiteRepository.check_drift`](scripts/wiki_index/sqlite_repository.py#L623-L641)
   `read_bytes()` + sha256 + `yaml.safe_load` on **every** page for type-mismatch detection
   (`_extract_frontmatter_type` at [sqlite_repository.py:676](scripts/wiki_index/sqlite_repository.py#L676)
   still uses PyYAML). At 10k pages the `wiki-lint` 30 s SLO is at risk. Per D-017-B the
   default stays full-hash (integrity); the win is a regex fast-path for `type:` plus an
   opt-in mtime short-circuit.

3. **P-2 (`reindex_delta` no-op walk cost).** [`reindex_delta`](scripts/wiki_index/reindex.py#L265)
   already short-circuits re-ingest on `mtime <= cutoff` (reindex.py:303), but it pays a
   **redundant `path.stat()` per file** (reindex.py:299) on top of the `vault_root.glob()`
   walk inside [`iter_pages`](scripts/wiki_index/layout_config.py#L483) — `Path.glob`
   allocates a `Path` per entry and does not surface the `DirEntry` stat the OS already
   fetched. A no-op delta at 10k pages risks the 2 s SLO. Win: one stat per file (reuse the
   walk's stat / `os.scandir`), zero DDL.

All three fixes are **zero DDL**, **backward-compatible** (new flags additive; defaults
preserve current behavior), and **byte-identity-preserving for built-in layouts**
(karpathy golden anchor `tests/test_karpathy_byte_identity.py` must stay green).

---

### 2. Requirements Traceability Matrix (RTM)

| ID | Requirement | MVP? | Sub-features |
|----|------------|------|--------------|
| **R-017-1** | Per-file runtime regex deadline for operator-custom patterns via PyPI `regex` `timeout=` (closes R-X1-REDOS-RT) | **YES** | (a) add `regex>=2024.0` to `requirements.txt` + install into `.venv`; resolve `mypy --strict` typing for it (bundled stubs vs `types-regex`); (b) a small timeout-guarded extraction helper that compiles+runs an **operator-custom** pattern through `regex` with a wall-clock `timeout=` (ceiling from a named module constant); (c) `extract_refs` routes operator-custom `ref_extraction[].regex` through (b); on the builtin `TimeoutError` (raised by `regex`, verified) → **skip this file's refs with a WARN**, never raise, never hang; (d) `_derive_project` routes operator-custom `project_pattern` through (b); on timeout → `UNMATCHED_PROJECT` + WARN (parity with the existing pattern-miss policy); (e) **built-in layouts (karpathy / dev-project / obsidian-personal) keep the existing stdlib `re` path** — zero `regex`-engine overhead, byte-identity preserved; (f) the load-time `_redos_budget_check` PW-D gate **stays** (defense-in-depth; runtime deadline is the completeness backstop, not a replacement) **and is aligned to compile/probe operator patterns under the `regex` engine** so load-gate and runtime share one dialect; (g) WARN/skip reasons never echo the offending pattern or file body (CWE-117/209); (h) document the `re`→`regex` dialect change (V0 = `re`-compatible) in the layout-config docs + schema notes; (i) `mypy --strict` clean |
| **R-017-2** | `check_drift` type-extraction fast-path + opt-in mtime short-circuit (closes P-3) | **YES** | (a) replace PyYAML in `_extract_frontmatter_type` with a regex fast-path for `^type:\s*(\S+)` inside the frontmatter block, **PyYAML fallback** retained for quoted/edge values → type extraction byte-identical on the existing corpus; (b) **default behavior unchanged = always full-hash** (D-017-B integrity-first); (c) opt-in flag (e.g. `--mtime-skip` on the `wiki-lint` / check_drift surface) → when stored `last_modified` == disk `mtime`, skip the re-hash (still hashes on mismatch); (d) add `last_modified` to the `check_drift` `SELECT` for the opt-in comparison (already a `pages` column → **zero DDL**); (e) opt-in path documented as integrity-relaxed (a preserved-mtime tamper can slip); (f) optional micro-opt: `hashlib.file_digest` streaming hash; (g) `mypy --strict` + tests |
| **R-017-3** | `reindex_delta` / page-walk single-stat (closes P-2) | **YES** | (a) eliminate the redundant `path.stat()` at reindex.py:299 — reuse the stat the discovery walk already performs (thread an `mtime` onto `DiscoveredPage`, or migrate `iter_pages` to `os.scandir` whose `DirEntry` caches `stat`); (b) **iteration order + match semantics (first-match-wins, `ignore[]`, `file_extensions`, SYSTEM_FILES/auto-index outputs) stay byte-identical** — `iter_pages` tests + karpathy golden anchor green; (c) the `mtime <= cutoff` no-op short-circuit preserved; (d) zero DDL; (e) `check_drift` reuses the same single-stat walk where it shares `discover_pages` |
| **R-017-4** | Tests + performance evidence | **YES** | (a) unit test: an operator-custom layout with a pattern that is linear on short payloads but catastrophic on a long single-line body → deadline fires → file skipped + WARN, run completes (R-017-1); (b) test: built-in karpathy reindex byte-identical, no `regex` engine touched (R-017-1e); (c) tests for the regex `type:` fast-path incl. quoted/edge fallback (R-017-2a) and `--mtime-skip` correctness incl. hash-on-mismatch (R-017-2c); (d) `scripts/benchmark.py` **before/after** for `reindex-delta` (no-op) + `wiki-lint` at `--n 1000` (and `--n 10000` if feasible) recorded in this TASK; (e) full pytest ≥ baseline (+ new), `mypy --strict` clean |

**Non-functional requirements**

| ID | Requirement |
|----|-------------|
| **NF1** | **Zero DDL** — `user_version` stays **5** (D-017-C). |
| **NF2** | **Built-in byte-identity** — `tests/test_karpathy_byte_identity.py` and `iter_pages` ordering tests stay green; built-in layouts pay zero `regex`-engine cost. |
| **NF3** | `mypy --strict scripts/` clean (incl. the new `regex` dependency typing). |
| **NF4** | Full `pytest tests/` green at ≥ 879 (+4 skipped) plus the new R-017-4 tests. |
| **NF5** | Backward-compatible CLI/envelope — new flags additive; defaults reproduce current behavior; no exit-code change. |
| **NF6** | **Supply chain** — `regex` is a single, widely-used, actively-maintained PyPI package; pin a floor version and note the dependency in `README.md` external-deps + `requirements.txt`. Untrusted-data logging stays CWE-117/209-safe. |
| **NF7** | **Performance evidence** — no blind index/algorithm changes (P-5 lesson); P-2/P-3 wins demonstrated by `scripts/benchmark.py` deltas, not projections. |

---

### 3. Use Cases

**UC-1 (R-017-1, primary — the security fix).**
An operator runs a vault under a **custom** `WIKI_SCHEMA.md` layout whose
`ref_extraction[].regex` is catastrophic on long input. A page contains a 100 KB
single-line body. `wiki-reindex --delta`/`--full` reaches that page.
- *Expected:* the timeout-guarded `regex` search hits its per-file deadline, the file's
  ref-extraction is **skipped with a WARN** (recorded in the existing `skipped[]` channel,
  reason not echoing the pattern/body), the reindex **continues and completes**. No hang.

**UC-2 (R-017-1e, built-in no-regression).**
A standard karpathy vault is reindexed.
- *Expected:* output is **byte-identical** to today; the `regex` engine is never invoked
  (stdlib `re` path); the golden anchor test passes unchanged.

**UC-3 (R-017-2, drift integrity vs speed).**
`wiki-lint` on a 1k-page vault, no edits since last index.
- *Default:* full sha256 of every file (integrity-first) — drift report correct, type
  mismatches detected via the regex fast-path (no PyYAML per file).
- *`--mtime-skip`:* files whose `last_modified` matches disk `mtime` skip the re-hash →
  near-instant no-op lint; a content edit that changes `mtime` is still hashed and caught.

**UC-4 (R-017-3, delta no-op walk).**
`wiki-reindex --delta` no-op on a 1k-page vault.
- *Expected:* completes well under the 500 ms (n=1000) delta SLO; **one** stat syscall per
  file (no redundant `path.stat()` after discovery); iteration order unchanged.

**Alternative / edge scenarios**
- **A-1:** `regex` import unavailable at runtime → fail fast with a clear install hint
  (`pip install -r requirements.txt`); built-in-layout vaults must still work if the guard
  is only reached for custom patterns (architecture must decide import strategy).
- **A-2:** A `regex` pattern that is *itself* malformed under the `regex` dialect → surfaces
  as a load-time `LayoutConfigError` (parity with the existing `_redos_budget_check`
  compile check), not a runtime crash.
- **A-3:** `_extract_frontmatter_type` regex fast-path misses an unusual-but-valid `type:`
  (quoted, folded) → PyYAML fallback yields the same value as today (no new false drift).
- **A-4:** `--mtime-skip` with a clock-skewed / mtime-preserving tamper → documented
  integrity relaxation; default mode (full-hash) still catches it.

---

### 4. Acceptance Criteria

- **AC-017-1** (R-X1-REDOS-RT): a regression test with a catastrophic-on-long-body
  operator pattern proves `wiki-reindex` skips the offending file with a WARN and completes
  within a bounded wall-clock; **without** the fix the same test hangs/times out. The open
  issue is marked `fixed`.
- **AC-017-2** (built-in invariant): `tests/test_karpathy_byte_identity.py` + `iter_pages`
  ordering tests pass unchanged; a test asserts the `regex` engine is not invoked for a
  built-in layout.
- **AC-017-3** (P-3): `_extract_frontmatter_type` returns identical results to PyYAML on the
  full repo corpus; `check_drift` default mode still full-hashes (integrity test:
  preserved-mtime tamper IS detected in default mode); `--mtime-skip` skips re-hash on
  mtime-match and still hashes on mtime-change. Issue `fixed`.
- **AC-017-4** (P-2): a `reindex_delta` no-op performs exactly one stat per discovered file
  (asserted via a stat-counting spy or `os.scandir` usage); iteration order byte-identical;
  benchmark delta recorded. Issue `fixed`.
- **AC-017-5** (gates): `pytest` green ≥ baseline + new tests; `mypy --strict` clean;
  `user_version` still 5; `scripts/benchmark.py` before/after numbers for delta + lint at
  n=1000 captured in the TASK status block.
- **AC-017-6** (docs): `requirements.txt` + `README.md` external-deps updated for `regex`;
  the three issue Class-A files set to `status: fixed`; `docs/KNOWN_ISSUES.md` re-rendered
  via `wiki-index-render --auto-indexes`.

---

### 5. Open Questions — ✅ ALL RESOLVED in Architecture (see ARCHITECTURE.md §11a Q-017-1..4)

> OQ-1 → provenance booleans on `LayoutConfig`; OQ-2 → per-file budget (`WIKI_REDOS_BUDGET_S`
> = 2.0 s); OQ-3 → opt-in `wiki-lint --mtime-skip`, always-hash default; OQ-4 → `types-regex`.
> The original framing is kept below for traceability.

- **OQ-1 (built-in vs operator-custom detection):** `resolve_layout_config` deep-merges a
  built-in base with an optional per-vault override; `LayoutConfig` currently carries **no
  provenance** for which patterns came from the override. Architecture must choose: (i) tag
  pattern provenance during the merge; (ii) compare resolved pattern strings against the
  built-in base; or (iii) always route through `regex` but rely on the timeout never firing
  for vetted built-ins (simplest, but adds engine overhead to built-in vaults — conflicts
  with NF2's "pay zero"). **Recommendation:** (i) or (ii) to honor D-017-A's "built-in pays
  zero."
- **OQ-2 (timeout scope + ceiling):** `regex`'s `timeout=` is per call (verified: fires at
  the deadline +0.2 ms). But `extract_refs` calls `finditer` **per line**, so a naïve
  per-call timeout bounds each line to the ceiling → worst case `N_lines × ceiling` for a
  crafted many-line file. Choose a **per-file aggregate budget** (e.g. a shrinking deadline
  threaded across the file's `finditer`/`search` calls, or wrap the whole page-extraction)
  vs a simpler per-call ceiling, and set the default constant — bounding total per-file cost
  without false-positiving a legitimately large-but-linear page.
- **OQ-3 (`--mtime-skip` surface):** exact flag name and which CLIs expose it
  (`wiki-lint`; `wiki-reindex` already uses mtime). Default OFF (D-017-B).
- **OQ-4 (`regex` typing under mypy --strict):** does `regex` ship inline stubs, or is
  `types-regex` (+ `requirements`) needed? Resolve so NF3 holds.

---

### 6. Out of Scope (explicitly deferred)

- **P-1** (`reindex_full` per-page transactions), **P-4** (benchmark default n), **R-X1-CFG-COST**
  (config memoization), other SEV-3/perf issues — not in this bundle.
- **`file_size` column / any DDL** — rejected by D-017-C.
- **RE2 / google-re2** linear engine — rejected in favor of `regex` (heavy C/C++ Abseil
  build, partial wheels, dialect drift). Recorded for completeness only.
- Replacing the load-time `_redos_budget_check` — it stays (defense-in-depth).
