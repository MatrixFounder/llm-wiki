---
id: P-030-DELTA-BULK
type: known-issue
status: open
opened_at: 2026-06-13
category: performance
severity: SEV-3
slug: p-030-delta-bulk-ingest-per-file-txns
---

# `reindex_delta` whole-vault bulk ingest keeps per-file transactions

- **Symptom**: when `--delta` ingests a LARGE cohort in one run (the Q-030-3
  fresh-vault first delta; a mass folder-rename making every file new-path), each
  file commits its own per-file transaction (atomic page+refresh+refs — the
  TASK 030 `/vdd-multi` LOGIC-MED fix), while `--full` flushes K=500-page chunks.
  **Measured @2k (3-run median)**: full **446.6 ms** vs whole-vault delta
  **763.6 ms** (~1.7×). Found by the TASK 030 post-ship `/vdd-multi`
  (PERF-030-M2, verifier-confirmed); the per-file-txn cadence is DELIBERATE there
  (per-file atomicity is what fixed the permanently-unrepaired partial-write).
- **Operator guidance (current)**: for routine renames/moves and small deltas the
  `--delta`-first rule stands (correct + convergent + cheap). For a KNOWN bulk
  ingest (fresh registration, mass folder-rename of a big subtree), `--full` is
  ~1.7× faster at scale — both are correct.
- **Fix plan (deferred, scale-gated)**: reuse the 030-03 stage-then-flush shape
  for the delta touched/new-path cohort (derivation outside the txn, chunked
  DML flushes via the 030-02 helpers) while KEEPING per-file rollback isolation
  semantics (per-file SAVEPOINTs inside the chunk, or accept chunk-granular
  rollback for the bulk cohort only). Trigger: a real vault where bulk deltas
  are routine and the gap is felt.
