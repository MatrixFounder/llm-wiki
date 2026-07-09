---
id: P-6
type: known-issue
status: fixed
opened_at: 2026-05-28
category: performance
severity: SEV-2
slug: p-6-known-concepts-payload-o-n-per-prepare-invocation
---

# known_concepts payload O(N) per prepare invocation

- **Symptom**: `prepare` JSON envelope embeds the full known_concepts list. At ~100 entities ~5 KB; at 10k entities ~500 KB. Each invocation pays the serialization + transport cost.
- **Root cause**: Orchestrator needs the full list to drive de-duplication during synthesis; no negotiation step.
- **Affected components**: `scripts/wiki_skills/wiki_extract_concepts.py::prepare`.
- **Fix plan**: Add `--known-concepts-format=slugs-only` flag emitting `[slug, slug, ...]` instead of full `{slug, name, type, aliases}`. Trade-off: smaller payload, but orchestrator must resolve full records against the SKILL.md prompt or via a second prepare call when collision is suspected.
- **Resolution (2026-06-01, TASK 015 R-015-3)**: shipped `prepare --known-concepts-format {full,slugs-only}` (default `full` → backward-compatible). `slugs-only` emits `[slug, …]` (~N×30 B vs ~N×200 B). Applies batch-wide too (computed once in `_load_known_and_drift`). Tests: `test_prepare_slugs_only_format`, `test_prepare_full_default`, `test_prepare_batch_slugs_only`.
- **Residual (2026-07-09, wiki-import path NOT covered by the R-015-3 fix)**: the fix lives on `wiki-extract-concepts prepare`. `wiki-import prepare` has a **separate** known-concepts path — `wiki_import_article/_context.py::known_concepts` — that **always** builds full `{slug, name}` pairs (line 37) and exposes **no** `--known-concepts-format` option (nothing in `wiki_import_article/__init__.py` / `__main__.py` argparse). So a `wiki-import prepare` envelope on a large vault always pays the full O(N×~200 B) payload regardless of R-015-3. Observed 2026-07-09 importing `arxiv.org/abs/2510.08369`: 688 full records / ~63 KB embedded, all crypto/DeFi-irrelevant to an ML paper. **Fix option**: plumb `--known-concepts-format {full,slugs-only}` through `wiki-import prepare` → `_context.known_concepts` (and/or rank/cap by lexical overlap with the fetched raw before embedding).
- **Residual resolution (2026-07-09, TASK 055)**: shipped the primary fix option — `wiki-import prepare` now
  exposes `--known-concepts-format {full,slugs-only}` (default `full` → backward-compatible, byte-identical
  envelope; mirrors the sibling `wiki-extract-concepts` R-015-3 posture), plumbed through
  `_context.known_concepts(..., fmt=…)`. `slugs-only` emits a bare `[slug, …]` list (~N×30 B vs ~N×200 B) —
  pass it on a large vault to keep the `prepare` envelope small. The REASON contract documents the alternate
  shape. Tests: `test_prepare_known_concepts_format_slugs_only` (`tests/test_import_article_prepare.py`),
  `test_known_concepts_slugs_only_shape` (`tests/test_import_article_context.py`).
  **Deferred (unchanged, tracked here):** the *lexical-overlap rank/cap* alternative (embed only the concepts
  topically relevant to the fetched raw) was NOT implemented — it is riskier (could drop a concept the
  orchestrator needs for de-dup) and, like R-015-3, the default stays `full`, so a plain `prepare` on a large
  vault still ships the whole concept list unless the operator opts into `slugs-only`. The vdd perf critic
  flagged this as an accepted trade-off (parity with R-015-3), not a regression. If default-path payload
  becomes a real bottleneck, revisit with a relevance cap under a fresh issue.
