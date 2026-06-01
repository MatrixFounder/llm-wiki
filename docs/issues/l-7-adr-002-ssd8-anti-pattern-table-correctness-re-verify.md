---
id: L-7
type: known-issue
status: fixed
opened_at: 2026-05-26
category: logic
slug: l-7-adr-002-ssd8-anti-pattern-table-correctness-re-verify
---

# ADR-002 §D8 anti-pattern table correctness re-verify

- **Symptom**: Architecture review §4 L-7 noted ADR-002 §D8 anti-pattern row "Wiki-links только в БД через JOIN" — schema correctly mirrors to `page_entity_refs` (Class B), not anti-pattern. No fix needed; just confirming.
- **Root cause**: Documentation accuracy check.
- **Affected components**: ADR-002 §D8 anti-pattern table.
- **Fix plan**: Add reviewer confirmation note inline ("Verified consistent with `page_entity_refs` design, 2026-05-26").

---
