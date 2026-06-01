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
