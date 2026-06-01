---
id: Q-007-4
type: known-issue
status: documented
opened_at: 2026-05-29
category: quality
slug: q-007-4-cited-slug-rendered-into-a-sources-slug-wikilink-unsanitized
---

# cited slug rendered into a `## Sources [[slug]]` wikilink unsanitized

- **Symptom**: `_render_query_page` emits `- [[<slug>]]` for each citation; the
  slug is not markdown-escaped (it can't be — escaping would break the Obsidian
  link, which is the point).
- **Root cause**: the slug is the slug-half of a citation that **passed the
  grounding gate** (it equals a retrieved hit's `project/slug`), and retrieved
  hit slugs are page slugs (kebab file stems from the index) — not arbitrary
  operator input. So under the single-user-local threat model the surface is
  index-constrained, not attacker-controlled.
- **Affected**: `scripts/wiki_skills/wiki_query.py::_render_query_page`.
- **Fix plan**: re-evaluate only if `wiki-query` is ever exposed multi-tenant /
  via an MCP shim (same boundary as the F3-residual / D-1 notes). The answer
  *body* is fully sanitized (`sanitize_markdown_text`); only the controlled
  citation wikilinks are intentionally left navigable.

---
