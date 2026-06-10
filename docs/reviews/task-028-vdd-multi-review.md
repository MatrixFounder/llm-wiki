# /vdd-multi + code-review — TASK 028 (query stemming + ё/е fold)

## Second /vdd-multi pass (2026-06-10, operator: "проверь … ничего не поломалось")
Re-ran all three critics on the FINAL post-fix tree + a regression gate (1203→1204 pytest,
mypy strict, zero DDL, no anthropic). **Security CLEAN · Performance CLEAN** (V×T re-confirmed
pre-existing). **Logic found ONE NEW MED — a regression the first pass's empty-base guard
surfaced**: `wiki-search "   "` (any all-whitespace query) → the stemming lexer collapses it to
`""` → `search_pages("")` raises `ValueError`, which the DF-1 net (only `OperationalError`)
never caught → **uncaught crash** (reproduced: `ValueError`, exit 1). **FIXED:** strip the query
at the `wiki_search.main` boundary (`query_arg = args.query.strip()` → whitespace-only ⇒ clean
`INVALID_QUERY` exit 2, mirroring wiki-query's question-strip; echo now reports the stripped
query; `assert query_arg is not None` narrows the FTS branch for mypy). Regression test
`test_main_whitespace_query_clean_invalid_not_crash` (4 whitespace variants → exit 2).
**critic-logic re-verify → clean-pass** (NBSP U+00A0 stripped; punctuation-only `"..."` → a
non-empty base → OperationalError→DF-1, never ValueError; blank+`--where` → metadata listing;
the assert is provably unreachable). **Converged: Logic ✓ Security ✓ Performance ✓ (iters L=2,
S=1, P=1). 1204 pytest / 4 skip, mypy strict clean.**

---

## First /vdd-multi pass (2026-06-09)

- **Date:** 2026-06-09
- **Verdict:** **CONVERGED — MERGE.** No BLOCKING. Security CLEAN; Logic/Performance/Code-review
  COMMENTS, all triaged (fixed or documented). Full suite **1203 passed / 4 skipped**, mypy
  strict clean (75 files), zero DDL (`user_version` 5), no `import anthropic`.

## critic-security — CLEAN
Full taint path CLI→lexer→FTS verified: the query reaches `pages_fts MATCH ?` as a **bound
parameter** (no SQL/MATCH injection); regexes are linear (no ReDoS); the post-stem `MIN_STEM_LEN`
+ acronym guard prevent catch-all `*` DoS; `snowballstemmer==3.1.1` pinned, pure-Python, the one
`type: ignore` isolated to `_snowball.py`. One bikeshed LOW (no query-length cap on wiki-search —
local-operator boundary, O(n)) — not actioned.

## critic-logic — COMMENTS (1 MED documented, 2 LOW fixed)
- **MED — ё-fold column asymmetry.** Only `body_excerpt` is index-folded; `pages_fts` also indexes
  `title`/`tldr`/`tags` UNFOLDED while the query is always folded → a **ё-form** query for a term
  living ONLY in a title/tldr/tag (no body occurrence) is a narrow ё-form-only recall regression
  vs pre-028. Full symmetry needs trigger DDL (tags ride the trigger's `json_extract`) → out of
  zero-DDL scope. **Resolution: documented accurately** (was "title only" → now title/tldr/tags) in
  TASK §2, ARCHITECTURE Q-028-5, SKILL.md residual; the е-form (common typing) is unaffected, the
  body case is improved.
- **LOW — empty `()` group** for a whitespace-only query that resolves to an alias (unreachable
  today). **Fixed:** `build_search_query` returns early when `base` is blank (+ regression test).
- **LOW — alias lookup is ё-sensitive** (exact-match on the raw token). **Documented** (register
  ё-aliases in the е-form; fold-aware lookup is a future consistency pass).

## critic-performance — COMMENTS (1 MED pre-existing, 3 LOW micro-opts)
- **MED — wiki-query alias expansion V×T fan-out.** **Verified PRE-EXISTING** (`git show
  HEAD:…wiki_query.py` line 144-146 — the per-token loop pre-dates TASK 028; this task kept the
  identical loop, added only the per-token stem). NOT a 028 regression → **documented** as a future
  prefetch follow-up (ARCHITECTURE Q-028-3); not fixed (scope discipline).
- **LOW ×3** — DF-1 double-retrieval on special-char queries; `fold_yo` 4 `.replace()` passes;
  `stem()` not per-word memoized (irrelevant for one-shot CLI). All negligible/micro — not actioned.

## code-reviewer — MERGE (3 LOW fixed)
- RTM R-028-1..5 + ARCHITECTURE Q-028-1..6 fully complied; 88 new tests RED→GREEN, real
  SQLiteRepository fixtures (not over-mocked), the never-unparseable invariant + guards + hash
  symmetry covered; independently fuzzed `stem_fts_query` (14 exprs) — all parseable.
- **LOW — `analyze_gaps clean` wording** inaccurate (the 9 reported gaps all PRE-DATE 028 — verified
  vs `git show HEAD`). **Fixed:** wording → "no NEW gaps vs the pre-028 baseline".
- **LOW — `Ё→е` vs `Ё→Е` drift** (code is case-preserving `Ё→Е`). **Fixed:** TASK/ARCH prose aligned.
- **LOW — dead `or`-branch** in `test_build_match_query_exact_fold_only`. **Fixed:** asserts the
  deterministic folded output.
