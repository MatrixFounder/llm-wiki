# task-015-10 — Close issues + docs gate

**Parent:** TASK 015. **Depends on:** 015-09. **RTM:** R-015-NF1, AC-015-9..11.

## Goal
Mark all four fixed issues closed, re-render the KNOWN_ISSUES ledger, update AGENTS and
ROADMAP docs, and run the final acceptance gate.

## Steps

1. **Close issue files** — in each file, set `status: fixed` and add a `## Resolution`
   section:
   - `docs/issues/h-perf-3-index-from-manifest-argparse-in-loop.md`
   - `docs/issues/p-6-known-concepts-payload-o-n-per-prepare-invocation.md`
   - `docs/issues/p-7-no-batch-surface-for-n-source-page-workflows.md`
   - `docs/issues/p-8-wal-pragma-setup-cost-compounded-across-the-two-process-workflow.md`

   Resolution notes:
   - H-PERF-3: "Fixed in TASK 015 bead 015-02/03: `upsert_one` programmatic entry-point
     in `wiki_index_upsert`; `index_from_manifest` loop calls `upsert_one` (not `main(argv)`)
     with a shared repo. Eliminates N argparse calls + N connection-open/close cycles."
   - P-8: "Partially fixed in TASK 015 bead 015-03: `index_from_manifest` optional `repo`
     param eliminates the per-entry connection cycle (H-PERF-3 fix) and the extra
     `append_log_event` connection. The `prepare`/`apply` process-boundary cost is
     a Decision-17 design invariant (acceptable); PRAGMA caching deferred."
   - P-6: "Fixed in TASK 015 bead 015-05: `prepare --known-concepts-format slugs-only`
     emits `[slug,…]` reducing payload from ~500 KB to ~30 KB at 1k entities."
   - P-7: "Fixed in TASK 015 bead 015-07/09: `prepare --batch <slugs.json>` (known_concepts
     once) + `apply --batch-candidates <combined.json>` (single repo, independent per-entry
     transactions, shared-repo `index_from_manifest`)."

2. **Re-render the KNOWN_ISSUES ledger**:
   ```bash
   source .venv/bin/activate
   wiki-index-render --auto-indexes --vault-root docs --db-path .wiki/index.db
   ```
   Confirm the 4 issues now show `status: fixed` in the ledger.

3. **Run `wiki-lint` PW-Q drift guard**:
   ```bash
   wiki-lint --vault-root docs --db-path .wiki/index.db
   ```
   Confirm: no `auto-generated-drift` warning.

4. **Update `.AGENTS.md` files** (Developer role only):
   - `scripts/wiki_skills/.AGENTS.md`: add `upsert_one` entry under `wiki_index_upsert.py`;
     update `_manifest_consumer.py` `index_from_manifest` signature; add
     `_batch_prepare` + `_batch_apply` + `_recon_single` + `_apply_candidates_to_db` to
     `wiki_extract_concepts.py` section.
   - `tests/.AGENTS.md` (if exists): note `test_perf_hardening.py`.

5. **Update `docs/ROADMAP.md`**: add TASK 015 to the "Done since 2026-05-25" section.

6. **Final acceptance gate**:
   ```bash
   pytest -q
   mypy --strict scripts/
   ```
   Confirm ≥ baseline pytest count + 0 mypy errors.

## Acceptance
- ✅ All 4 issue files show `status: fixed`.
- ✅ `docs/KNOWN_ISSUES.md` re-rendered; `wiki-lint` no drift (AC-015-9).
- ✅ `pytest -q` count ≥ 852 + new tests, 0 unexpected failures (AC-015-11).
- ✅ `mypy --strict scripts/` — 0 errors (AC-015-10).
- ✅ `docs/ROADMAP.md` TASK 015 Done entry.

## Files
- `docs/issues/h-perf-3-*.md` (status: fixed)
- `docs/issues/p-6-*.md` (status: fixed)
- `docs/issues/p-7-*.md` (status: fixed)
- `docs/issues/p-8-*.md` (status: fixed)
- `docs/KNOWN_ISSUES.md` (re-rendered)
- `scripts/wiki_skills/.AGENTS.md` (update)
- `docs/ROADMAP.md` (update)
