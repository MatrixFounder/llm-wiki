# 031-04 — e2e fixture + dogfood + full-suite close

**Owns:** AC-7.2 + AC-7.3. **Dep:** all. **Detail:** PLAN.md §2 / §3 🟡-2.

## Scope
Commit the e2e fixture, run the live dogfood, confirm the full regression + invariants.

## Files
- `tests/fixtures/cybos/` (committed) — one minimal note per type (from the 031-02 templates) under the cybos folder structure.
- `tests/test_cybos_e2e.py` (or extend existing) — scaffold-register + `reindex_full` over the fixture → each note's `pages.type`+tag correct; `skipped`/`slug_collisions` empty.

## Dogfood (gitignored scratch — `samples/`)
`wiki-init --scaffold-new --layout cybos --vault samples/cybos-demo` (AC-3.3: registers, NO two-tier dirs, `CLAUDE.layout.md.tmpl`); author one note/type; `wiki-reindex --full`; DB-level assert `pages.type`+tag; `wiki-search samples/cybos-demo --types research` (bucket) + FTS `"incident"`; **🟡-2 event/summary distinct retrieval** — FTS on the event note's term (same db_type `summary` as meeting/lesson summaries, separated by tag word).

## Verify
Full `pytest` + `mypy --strict scripts/` green; `grep -r "import anthropic" scripts/` empty (AC-7.2); Karpathy golden anchor green.
