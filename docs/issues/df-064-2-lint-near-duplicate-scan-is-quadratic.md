---
id: DF-064-2
type: known-issue
status: fixed
opened_at: 2026-07-14
category: performance
severity: SEV-3
slug: df-064-2-lint-near-duplicate-scan-is-quadratic
---

# `wiki-lint`'s near-duplicate-concept scan is an unbounded O(n²) pairwise `SequenceMatcher` sweep

- **Symptom**: `check_near_duplicate_concepts` (`scripts/wiki_index/lint.py`, TASK 064) enumerates
  **every pair** of concept slugs in the vault and scores each with
  `difflib.SequenceMatcher(...).ratio()`. It runs on **every** `wiki-lint` invocation, including
  `--all` across vaults. The inlined `real_quick_ratio` length bound prunes *scoring*, but not the
  quadratic **pair enumeration**.

- **Measured** (the shipped `_dup_key` + `NEAR_DUP_CUTOFF`, on the operator's own corpus size):

  | concepts | pairs | added to every lint run |
  |---|---|---|
  | **685** (re-counted from the live DB, 2026-07-14) | **~234,600** | **~0.6 s** |
  | 2,000 | 1,999,000 | 4.98 s |
  | 5,000 | 12,497,500 | **31.9 s** |

  *(The "720" in the original filing was an estimate; the live `entities` table holds **685** —
  684 concept pages. The conclusion is unchanged, and the number is now measured rather than
  remembered.)*

- **Why it is only SEV-3 today, and why it will not stay that way**: 0.6 s is tolerable. But a
  compounding vault is the **explicit design goal** of this project, so the input to this loop grows
  without bound while the cost grows with its square. The check is *advisory* (it never gates
  `--strict`), so the failure mode is a lint run that becomes too slow to run — i.e. the duplicate
  work-queue quietly stops being consulted, which is the exact outcome the check was added to
  prevent.

- **Root cause**: TASK 064 demoted the near-duplicate gate from a write-time refusal to an advisory
  (see `skills/concept-extraction/evals/README.md` for why — the 0.88 cutoff was *anti-correlated
  with meaning*) and added the lint category so the **existing** corpus becomes a `wiki-merge` work
  queue. The lint half was written for correctness first; its complexity was accepted knowingly and
  is recorded here rather than left to be discovered.

- **Fix sketch**: block the O(n²) enumeration itself, not just the scoring.
  1. **Bucket by a cheap key before pairing** — e.g. sorted character bigram set, or first/last 3
     chars of `_dup_key`, or length band. Only compare within a bucket. A plural/transliteration/
     word-order variant shares a bucket with its twin by construction; an unrelated pair does not.
  2. Or index the `_dup_key`s in a trigram/BK-tree and query neighbours within an edit radius.
  3. Either way: **re-measure against the live pairs the cutoff was calibrated on**
     (`виталик-бутерин`/`vitalik-buterin`, `сатоши-накамото`/`сатоси-накамото`,
     `бессрочный-фьючерс`/`бессрочные-фьючерсы`) — a faster scan that stops finding them is not a fix.

---

## ★ FIXED (2026-07-15) — the difflib cascade, completed. 3× faster, output-identical.

**Profiled first, not assumed.** `wiki-lint --strict` on the live vault (~2.0 s) was dominated
by `check_near_duplicate_concepts` → `difflib.SequenceMatcher.ratio()` (~1.4 s self-time in
`find_longest_match` + `get_matching_blocks`). It was the single largest cost of the whole run —
so the "6 SEV-3 with a common root" framing was wrong: there is no common root, and ONE
dominates.

**Root cause, exact:** difflib is a THREE-rung cascade of ever-tighter upper bounds on `ratio()`
— `real_quick_ratio` (length) → `quick_ratio` (char multiset) → `ratio` (LCS). The scan inlined
the FIRST rung and jumped straight to the THIRD, skipping the middle one. Measured on the live
684-concept corpus: of **47,474** pairs that clear the length bound, `quick_ratio` clears all but
**4** — so **99%** of the `ratio()` calls were avoidable.

**Fix:** add the `quick_ratio` rung + reuse the `SequenceMatcher` seq2 chain (built once per
outer key, not once per pair). `quick_ratio() >= ratio()` ALWAYS, so the reported set is provably
unchanged — it only drops calls that were going to fail. Result: **2000 ms → 651 ms** (3× on the
full `--strict` run; 6× on the scan itself), with the near-dup output byte-identical.

**Order-stability:** the seq2-reuse loop walks j-outer, which would emit in a different order than
the original i-outer scan on a corpus with more than today's 2 hits. `out.sort(...)` restores the
original's exact (page_slug, duplicate_of) order. `test_near_dup_cascade_is_OUTPUT_IDENTICAL_to_
the_naive_scan` pins it against a from-scratch naive re-implementation, on a fixture whose
near-dup pairs STRADDLE in sort order so the two loop orders genuinely diverge (the first fixture
did not, and its "MUT ⇒ RED" claim was false until the fixture was rebuilt and the mutation
re-run).

**Still quadratic in the pair COUNT** — but the constant is now tiny, and the tail is bounded by
the cheap `quick_ratio`, not the expensive `ratio`. A true sub-quadratic blocking scheme is
unnecessary at the corpus sizes this vault will reach; if it is ever needed, the sound approach is
length-window blocking (a strictly tighter version of the length prune already here).
