# task-017-13 — Close issues + docs gate

**Parent:** TASK 017. **Depends on:** 017-12. **RTM:** AC-017-6, NF6.

## Goal
Flip the three closed issues to `fixed`, re-render the Class-B ledger, and sync the docs.

## Steps
1. Set `status: open → fixed` in the three Class-A issue files:
   - `docs/issues/r-x1-redos-runtime-deadline-residual.md`
   - `docs/issues/p-3-check-drift-re-hashes-every-file.md`
   - `docs/issues/p-2-reindex-delta-no-op-walk-cost.md`
   (edit the per-issue files, **never** the ledger — PW-Q.)
2. Re-render the ledger: `wiki-index-render --auto-indexes` → `docs/KNOWN_ISSUES.md`;
   confirm `wiki-lint` PW-Q drift guard is clean.
3. `requirements.txt` already carries `regex`/`types-regex` (017-00) — add `regex` to
   `README.md` external-deps / dependency list with the one-line ReDoS-guard justification.
4. Update `.AGENTS.md` (the `scripts/wiki_index` + `scripts/wiki_source` ones touched), and
   `docs/ROADMAP.md` (mark R-X1-REDOS-RT + P-2 + P-3 Done), and the `CLAUDE.md` status
   header (TASK 017 shipped line).

## Verification
- `wiki-lint` clean (no PW-Q manual-drift flag on the ledger).
- The three issues no longer appear as `open` in `docs/KNOWN_ISSUES.md`.
- `grep -L "status: fixed"` over the three files returns none; final `pytest`/`mypy` green.
