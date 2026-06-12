# 030-03 — Chunked-tx `reindex_full` (R-030-2b, closes P-1)

**RTM:** R-030-2. **UC:** UC-30-2. **Depends:** 030-02.

## Goal
**Stage-then-flush** (Q-030-5 v3, arch-review HIGH-2): the per-page loop STAGES
each chunk OUTSIDE any txn (all `derive_indexed_page` file I/O → a prepared
`(page, refs, entity_row, alias_rows)` buffer bounded by `REINDEX_TX_CHUNK=500`
pages ∧ `REINDEX_TX_CHUNK_BYTES=32 MiB`), then FLUSHES DML-only under one
caller-owned `BEGIN IMMEDIATE` via the 030-02 helpers — the write lock is held
ms-scale, never across file I/O (shared `global.db` writers / cold iCloud reads
unaffected). The flush path skips the per-page hash pre-SELECT (F-6 — chosen for
the `kept`-alignment, not perf).

## RED first
1. **Commit-count (AC-2.4):** `sqlite3.Connection.set_trace_callback` counting
   BOTH `BEGIN` forms + `COMMIT` on a **constrained fixture** (zero log.md
   events; fixed entity/alias counts; C's composition documented in-test);
   assert `commits == ceil(N/K) + C` at N<K and N%K==0 (monkeypatch K small,
   e.g. 4). RED today (≈2N per-page commits).
2. **Lock-hold guard (AC-2.4b):** instrument `derive_indexed_page` + the trace
   callback to assert NO file read occurs between `BEGIN IMMEDIATE` and `COMMIT`
   (staging complete before flush). RED against an in-txn-derivation
   implementation.
3. **Row parity (AC-2.1, mechanism decided — plan-review MED):** chunked
   `reindex_full` vs a test-local **public-DAL replay loop** (`upsert_page` +
   `replace_refs` per page — post-030-02 the public methods ARE the old per-page
   path; no production seam, no golden dump) → identical
   `pages`/`page_entity_refs`/`entities`/`entity_aliases` rows + FTS hits;
   volatile timestamp columns excluded/frozen.
4. **F-6 corner (AC-2.6):** two byte-identical files colliding on
   `(slug,project)` → DB `file_path` == the `slug_collisions` record's `kept`
   (the later POSIX-sorted file). RED today (pre-SELECT short-circuit keeps the
   first).
5. **Q-030-5 error paths:** (i) mid-flush DML failure (monkeypatch
   `_replace_refs_in_txn` to raise for one slug) → file in `skipped`, chunk
   commits, others intact, run completes; (ii) **fatal mid-flush** — injection =
   monkeypatched `COMMIT` failure (the per-file `except Exception` never sees it
   — plan-review MED) → chunk rolled back, `finish_batch_run("failed")`, FTS row
   count == pages row count (no desync).
6. **Boundaries (AC-2.7):** N=0, N<K, N%K==0, byte-cap early flush (one
   oversized-body fixture).

## GREEN
- Staging pass per chunk (derive + buffer, OUTSIDE txn; per-file try/except moves
  to staging — derivation errors → `skipped` with zero DML, strictly better than
  today); flush pass: `BEGIN IMMEDIATE` →
  `_upsert_page_in_txn(conn, page, skip_unchanged_check=True)` +
  `_replace_refs_in_txn(...)` + entity/alias INSERTs (bare DML, join the chunk)
  → `COMMIT`.
- Keep `_detect_slug_collision` AFTER the upsert (order unchanged — runs in the
  flush pass).
- Update the `reindex.py:543-546` comment block (contingency → implemented).

## Acceptance
- ✅ AC-2.1, 2.4, 2.6, 2.7 + Q-030-5 tests green; karpathy golden + §D8
  rebuildability + alias/cites/verifies suites green UNMODIFIED.
- ✅ AC-2.3 audit: grep-enumerate `BEGIN IMMEDIATE` sites in `scripts/` — only the
  pre-existing sites + the chunk loop; helpers absent from the ABC.
- ✅ mypy strict; Sarcasmotron pass.
