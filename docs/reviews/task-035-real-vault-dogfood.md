# TASK 035 — real-vault comprehensive dogfood + `/vdd-multi` re-verification

- **Date:** 2026-06-16
- **Vault:** `/Users/sergey/Downloads/TestVault/ObsidianNotes-Test` (obsidian-personal PARA,
  vault-local `index_db` at `.wiki/index.db`, `user_version=7`, **2493 pages**, **1135
  distinct tags**)
- **Change under test:** FTS-narrowed `tags`-membership in `wiki-search` (TASK 035, ADR-005)
- **Mode:** READ-ONLY (`wiki-search` does not mutate). No vault data changed.

## `/vdd-multi` re-verification (complete final changeset) — PASS

3 parallel critics over the uncommitted diff, with the orchestrator-supplied evidence block
(tests `pytest tests/` → 1504 passed / 5 skipped; `mypy --strict` clean 76 files; security
scan adjudicated).

- **Logic ✓ clean-pass** — the prior MED (non-`str` value crashed the FTS path) is verifiably
  closed by the `isinstance(value, str)` guard (int/bool/None/float/unbindable all route to the
  scan **symmetrically** → `fts==scan`). No subset/partial-under-match reachable (all-or-nothing
  per value + empty→scan net). RTM behavioural requirements all test-covered.
- **Security ✓ clean-pass** — scanner adjudication **CONFIRMED**: the 7 "SQL f-string (CWE-89)"
  CRITICALs interpolate only hardcoded constants (`page_cols`, `self._REF_COLS`) /
  `?`-placeholder strings — never user input; the 035 diff adds **zero** new f-stringed SQL. The
  1 HIGH (unsafe-YAML `sync_config.py:279`) + 1 MED (SBOM) are **outside the diff, pre-existing**.
  FTS injection inert (phrase-quote `"`-doubling complete; `json_each` confirm is the hard gate);
  no value echo; no DoS (≤2 bounded queries per call).
- **Performance ✓ clean-pass** — ~4.1× holds for the selective (target) case; the 2 LOW
  residuals (empty-case +3-4 % double-probe; near-universal-tag crossover) are correctly bounded
  (O(N), `LIMIT`-capped) and recorded in the issue. Nothing regressed.

> Verdict: **Logic ✓ Security ✓ Performance ✓ (L=1, S=1, P=1; PASS)**.

## Comprehensive dogfood — all GREEN

**A. CLI `--tag` vs an INDEPENDENT `json_each` ground truth** (bypasses `search_pages` entirely)
— 13 sampled tags (high-freq, Cyrillic `Стратоплан`/`ШИП`, hyphenated, rare) → **0 mismatches**;
max-freq tag = 202 pages.

**B. Exhaustive DAL equivalence** — FTS-narrowed vs forced-scan over **ALL 1135 distinct tags**
→ **0 mismatches** (list + order identical). This is the byte-identity contract proven over the
entire real corpus, not a sample.

**C. Composition / edge cases / exit codes (real CLI `main()`)** — 9/9:
| # | check | result |
|---|---|---|
| C1 | `--tag T` ≡ `--where 'tags=T'` | 202 == 202 ✓ |
| C2 | `--tag T --types summary` | ≤ all, rc 0 ✓ |
| C3 | `--tag T --as-of 2026-04-15` | rc 0 (composes) ✓ |
| C4 | `"<query>" --tag T` (has_match path) | rc 0 ✓ |
| C5 | non-existent tag | 0 hits, **rc 0** (empty→scan net) ✓ |
| C6 | injection value `a" OR pages_fts MATCH "b` | no crash, 0 hits, rc 0 ✓ |
| C7 | `--tag x --where tags=y` dup-guard | `INVALID_FILTER`, rc 2, field=tags ✓ |
| C8 | bare (no query/filter) | `INVALID_QUERY`, rc 2 ✓ |
| C9 | JSON envelope keys | exact contract ✓ |

**D. Latency (real vault):**
- selective tag `12daysdune` (1 page): FTS **0.05 ms** vs scan **1.39 ms** (~28×)
- high-cardinality tag `Stratoplan` (202 pages, 8 % of corpus): FTS **0.45 ms** vs scan
  **1.78 ms** (~4×) — still a clear win at this cardinality; the documented crossover only bites
  for a *near-universal* tag, not present here.

**E. EXPLAIN (CLI metadata path):** driver = `SCAN pages_fts VIRTUAL TABLE` →
`SEARCH p USING INTEGER PRIMARY KEY (rowid=?)` — the intended narrowing signature.

**F. Regression (other search modes intact):** plain FTS query, `--as-of` alone, scalar
`--where` all rc 0.

## Conclusion

Correct, complete, nothing broken. The optimization is byte-identical to the scan across the
entire real 1135-tag corpus and through the CLI surface (composition, edge cases, exit codes,
envelope), delivers a 4–28× speedup, and introduces no new logic/security/perf issue. **Zero
DDL**, `user_version` stays 7. No new findings; no fixes required.
