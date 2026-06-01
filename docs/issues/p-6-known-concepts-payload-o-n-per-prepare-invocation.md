---
id: P-6
type: known-issue
status: open
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
