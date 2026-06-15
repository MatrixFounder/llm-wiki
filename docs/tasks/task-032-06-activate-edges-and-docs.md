# 032-06 — activate edges + docs + close

**Owns:** AC-7.1 + AC-8.*. **Dep:** 032-01..05. **Detail:** PLAN.md §2 / §4.

## Scope
Flip the inert-edges test to active; bring docs to as-built; final verify + gates.

## Files
- `tests/test_cybos_e2e.py` — replace `test_cybos_reserved_edge_keys_inert` (asserts `kinds ⊆ {mentioned}`) with `test_cybos_edges_extracted`: a fixture that **populates** the edge keys → assert the typed forward refs + a derived inverse materialize after `reindex_full`.
- `templates/page-types/*.md` — edge-key comment "INERT (Phase 1)" → "extracted as typed edges (Phase 2 / TASK 032)".
- `docs/ROADMAP.md` — **R-13 Phase 2 → ✅ SHIPPED (TASK 032)**.
- `docs/ARCHITECTURE.md` — TASK 032 status block 🚧→✅; Quality-Checklist item `[ ]`→`[x]`.
- `docs/manuals/obsidian-llm-wiki_manual.md` + `.ru.md` — authoring edges + `wiki-graph` + `wiki-query --follow-edges`.
- `docs/layouts/cybos.md` — the edges are now LIVE (drop the "Phase 2 deferred" framing for the authoring section; keep the query examples).
- `README.md` + `CLAUDE.md` — CLI count 15→16 (`wiki-graph`); TASK 032 ship-log entry.

## Verify (AC-8)
Full `pytest` + `mypy --strict scripts/` green; Karpathy anchor green; `grep -r "import anthropic" scripts/` empty; **`reindex --full` Class-B rebuild** on a v6 fixture; **real-vault dogfood** (decision→task→incident chain via `wiki-graph chain` + `wiki-query --follow-edges "what did X cause?"`).

## Gates
`/vdd-multi` (logic/security/performance + adversarial verify) → code-review MERGE.
