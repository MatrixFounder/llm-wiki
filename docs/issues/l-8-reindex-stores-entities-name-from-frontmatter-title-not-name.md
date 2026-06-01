---
id: L-8
type: known-issue
status: fixed
opened_at: 2026-05-29
category: logic
slug: l-8-reindex-stores-entities-name-from-frontmatter-title-not-name
---

# reindex stores entities.name from frontmatter `title`, not `name`

- **Symptom**: `reindex_full` registers an entity with `name = updated_fm.get("title", slug)` ([reindex.py](../scripts/wiki_index/reindex.py)). `write_concept_page` ([wiki_extract_concepts.py](../scripts/wiki_skills/wiki_extract_concepts.py)) emits `name:` (not `title:`), so a freshly-extracted concept page round-trips with `entities.name == slug` (the display name is lost on the DB side until the page also carries `title:`).
- **Root cause**: Pre-existing field-name mismatch (predates TASK 005); reindex was written against `title`, the concept-extractor against `name`.
- **Affected components**: `scripts/wiki_index/reindex.py` (entity registration), `scripts/wiki_skills/wiki_extract_concepts.py::write_concept_page`.
- **Impact on Epic 7**: minor — `wiki-merge`'s name-based redirect alias degrades to the slug (already registered), so resolution is unaffected; only a human-readable display name is missing. Surfaced during TASK 005 005-16 acceptance.
- **Fix plan**: either have reindex fall back `title or name or slug`, or have `write_concept_page` also emit `title:`. Defer — orthogonal to entity resolution; pick up in a docs/normalization polish bead.
