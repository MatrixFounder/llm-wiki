# Task Review — TASK 028 (query stemming + ё/е fold)

- **Date:** 2026-06-09
- **Reviewer:** VDD task-review (multi-agent: task-reviewer + design pre-mortem + docs-currency sweep)
- **Status:** **APPROVED** (initial `APPROVED_WITH_COMMENTS` → all CRITICAL/MAJOR resolved in the rewrite)

## General assessment
The spec correctly covers both operator-requested changes (A stemming, B ё/е fold) + the
operator reminder (skill/evals/docs currency), is non-contradictory with the architecture,
and holds the zero-DDL invariant (`user_version` 5). Three design-level issues surfaced by
the adversarial pre-mortem were material and are now fixed in `docs/TASK.md`.

## Comments & resolutions

### 🔴 CRITICAL
- **C1 — `wiki-query` question_hash reproducibility.** Stemming feeds `_build_match_query`
  → `_question_hash`, recomputed in `apply` (mismatch → `QUESTION_CHANGED`). **Resolved:**
  R-028-3 requires `--exact` threaded symmetrically through `prepare`+`apply` via `_retrieve`
  + a deterministic, **exactly-pinned `snowballstemmer==3.1.1`** (Constraints) + verification
  cases (b)/(c)/(e).

### 🟡 MAJOR
- **F-1 — composition order.** `stem(expand_query(raw))` is wrong: `expand_query` quotes the
  WHOLE raw query (`surfaces.add(query)` + `fts_quote`), so a quote-preserving stemmer
  broadens nothing on an alias hit. **Resolved:** R-028-2 inverts to stem-first then OR-in
  quoted alias surfaces `(<stemmed-folded-raw>) OR "alias1" …`; e2e (c) pins the alias+inflection case.
- **F-2 — two distinct call sites.** `wiki-query` already `fts_quote`s every token → a shared
  FTS-expr stemmer over its output stems nothing. **Resolved:** R-028-3 stems per-token
  BEFORE `fts_quote` → `"<stem>"*`; wiki-search uses the FTS-expr lexer (R-028-2). Shared
  primitive = the per-term core in `query_normalizer`. RAG path independently eval'd (a).
- **F-3 — `--exact` byte-identity is false post-fold.** **Resolved:** the central design split
  — ё/е fold is ALWAYS-ON corpus normalization (index + query, even `--exact`); only stemming
  is `--exact`-gated. Anchor restated: byte-identical for ё-free content, folded-consistent for ё.
- **`--exact` on wiki-query unverified** → R-028-3(d) adds it on both subparsers.

### 🟢 MINOR
- **F-4** idempotency is via the `*`-guard, not the (non-idempotent) stemmer → R-028-1(c).
- **F-5** `snippet()` IS a real (accepted-cosmetic) display consumer of `body_excerpt` →
  R-028-4 wording corrected; `wiki-verify-multi` reads the raw file (unaffected).
- **F-6** MIN gates on **post-stem** length (avoid catch-all `аг*`) → R-028-1(b).
- **F-7** `snowballstemmer` has no `py.typed` → typed `_snowball.py` wrapper, one ignore →
  Constraints. "~25 stemmers" corrected to **36** (§3).
- **F-9** the FTS lexer pass-through matrix (NEAR/col:/`{a b}:`/operator keywords/sigils) →
  R-028-2(a) + DF-1 fallback kept, fold-aware.
- **Eval reconciliation** (#1-#4, not just #4; keep #2 КПЧ transposition as a non-morphological
  fallback+grounding contract; keep #3 anti-hallucination) → R-028-5(b).

## Docs-currency (R-028-5 completeness)
Exhaustive grep: only `skills/wiki-search/SKILL.md` (4 claim sites + version + Contract) and
`evals/evals.json` (eval #4 ×2 + description) assert the now-false facts as CURRENT behaviour.
Manuals (EN+RU), quick-ref (EN+RU), ARCHITECTURE, README carry NO false claim to delete but
need the new behaviour ADDED (R-028-5(c)). `normalization.py` docstring is the B edit site.
SQL DDL tokenizer string + README L142 stay UNCHANGED (zero-DDL). All named in R-028-5.

## Recommendation
Proceed to Architecture. Encode OQ-1..6 resolutions + the F-1/F-2/F-3 design as Q-028-* in
`docs/ARCHITECTURE.md`, then Planning.
