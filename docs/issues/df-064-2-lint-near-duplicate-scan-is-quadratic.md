---
id: DF-064-2
type: known-issue
status: open
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
