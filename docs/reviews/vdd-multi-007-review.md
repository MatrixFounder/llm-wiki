# `/vdd-multi` Adversarial Review — TASK 007 (`wiki-query` RAG layer)

- **Date:** 2026-05-29
- **Mode:** multi-agent (Workflow): parallel `critic-logic` + `critic-security` +
  `critic-performance` over the 10 implementation files → each finding
  adversarially verified (refute-by-default) → confirmed real+in-scope synthesised.
- **Result:** 11 raw findings → **9 confirmed** real+in-scope → **1 HIGH must-fix**
  + 8 LOW. **Verdict: PASS** after inline fixes.
- **Agents:** 14 · subagent tokens ~804k.

## HIGH must-fix (FIXED inline)

**`type=query` exclusion ran POST-LIMIT → idempotency breaks at scale
(`critic-logic`, empirically reproduced).** `search_pages` applies
`ORDER BY bm25 LIMIT ?` in SQL; `_retrieve` filtered `type != 'query'` in Python
*after*. Once `apply` self-indexes the query page (its body matches the same FTS
terms), the next retrieval for the same question pulls it into the top-`limit`
SQL window where it consumes a slot and is then dropped in Python — silently
evicting a genuine hit. Consequences at ≥`limit` matching pages: (1) a
same-question re-`prepare` reports `is_unchanged=False` (violates UC-17 + the
compounding-loop idempotency promise); (2) an `apply` carrying `prepare`'s hash
hits a spurious `QUESTION_CHANGED`. Invisible at the 1-2-doc test scale.

- **Fix:** push the exclusion into SQL — added `search_pages(exclude_types=...)`
  applied **before** the LIMIT; `_retrieve` passes `exclude_types=['query']` when
  no explicit `--types` allowlist is given; removed the Python post-filter.
- **Regression:** `tests/test_wiki_query_index.py::test_idempotency_holds_at_scale_above_limit`
  (15 matching pages + a filed query page → same-question re-prepare
  `is_unchanged=True`, hash stable, no spurious `QUESTION_CHANGED`).

## LOW — fixed inline (3)

- **both-`--*-stdin` double-drains stdin** → misleading `INVALID_CITATIONS`.
  Fixed: reject `--answer-stdin` + `--citations-stdin` together up front
  (`INVALID_ARGS`, exit 2).
- **`apply` question not byte-capped** (every other payload is). Fixed:
  `len(question) > _MAX_QUESTION_LEN` → `INVALID_QUESTION` (parity with `prepare`).
- **content-hash skip-read followed symlinks** (post-`is_symlink()` TOCTOU).
  Fixed: read the existing file via `os.open(O_NOFOLLOW)` (matches
  `write_concept_page`); `is_symlink()` static refuse retained as belt+braces.

## LOW — deferred (4, → KNOWN_ISSUES Q-007-1..4)

- **Q-007-1** `apply` re-runs the full retrieval to recompute the hash — by
  design (the TOCTOU detection mechanism); one extra bounded FTS query.
- **Q-007-2** self-index re-reads the just-written page — deliberate, to keep the
  apply-written rows byte-identical to the reindex rebuild (UC-20 §D8 symmetry).
- **Q-007-3** `apply` needs the same retrieval-scope flags as `prepare` (else
  `QUESTION_CHANGED`) — inherent to Q-007-1; documented in the workflow recipe.
- **Q-007-4** cited slug rendered into a `## Sources [[slug]]` wikilink
  unsanitized — the slug passed the grounding gate (equals a retrieved hit's
  index-constrained `project/slug`), and escaping would break the navigable
  link; accepted under single-user-local (re-evaluate if exposed multi-tenant).

## Gate

Post-fix: **595 pytest pass / 4 skip**, `mypy --strict` clean (60 files). The
single HIGH correctness defect is closed with a scale regression; the deferred
LOWs are by-design or threat-model-scoped with recorded triggers. PASS.
