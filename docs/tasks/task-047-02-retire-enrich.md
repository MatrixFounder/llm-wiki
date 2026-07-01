# Task 047-02 (P2) — retire `wiki-enrich` + vendored `wiki_ingest` (clean delete)

Beads: B6 (remove code) · B7 (tests) · B8 (docs). **The derived-ledger design (P1) ports NOTHING
from `wiki_ingest`** — so this is a pure delete + reference cleanup, no re-home.

## Goal
Remove the redundant legacy on-ramp + its 6,372-LOC vendored dependency and every reference, now that
`wiki-import` is the unified engine (TASK 046) and concept compounding is a derived render (P1).

## Context (to remove)
- `bin/wiki-enrich`, `commands/wiki-enrich.md`, `skills/wiki-enrich/`, `workflows/wiki-enrich.md`,
  `scripts/wiki_skills/wiki_enrich.py`, `scripts/wiki_ingest/` (whole tree) + any `.claude/`/`.agent/` symlinks.
- Tests (vendored-only — nothing in the host depends on them after P1): `test_vendored_ingest_api.py`,
  `test_vendored_import.py`, `test_wiki_enrich.py`, `test__page_merge.py`, `test__markdown.py`, the
  vendored half of `test_layout_invariants.py`.
- Docs: `README.md` (CLI 18→17, drop the `wiki-enrich` row + the ADR-001 Option-I `manifest → wiki-enrich`
  diagram), `THIRD_PARTY_NOTICES.md` (drop `wiki_ingest`), `CLAUDE.md` (drop `wiki-enrich`/vendored
  `wiki-ingest` + the WIKI-INGEST contract pointer + §7.4 vendoring policy),
  `docs/WIKI-INGEST-V1.1-CONTRACT.md` (archive with an ADR-001-superseded note), `scripts/wiki_skills/.AGENTS.md`
  + `scripts/wiki_index/.AGENTS.md` (drop the vendored-constants drift notes).

## Steps
1. **B6** — `git rm` the code + symlinks. Verify nothing in `scripts/`/`bin/` imports
   `scripts.wiki_ingest` or shells `wiki-enrich`.
2. **B7** — delete the vendored-only tests; add `tests/test_no_wiki_ingest_imports.py` (R-6: no
   `from scripts.wiki_ingest`/`import wiki_ingest` under `scripts/`+`bin/`). Confirm the suite is green
   after deletions (no orphaned imports/fixtures; the derived renderer's coverage is P1's own tests).
3. **B8** — update all docs (above). `wiki-lint`/doc-lint for dangling links to removed files; confirm
   README CLI inventory == 17 and no diagram references `wiki-enrich`.

## Acceptance
- [ ] R-6: `grep -rn 'wiki_ingest' scripts/ bin/` shows no code import; `wiki-enrich` removed everywhere.
- [ ] R-7: docs say 17 CLIs; `THIRD_PARTY_NOTICES` drops `wiki_ingest`; no dangling links.
- [ ] Full suite green + `mypy --strict` clean after the deletions.

## Care
- `test_layout_invariants.py` guarded vendored constants matching the HOST constants — with the vendor
  gone the guard is moot, but verify the HOST `scripts.wiki_index.layout` constants are unaffected
  (the host is the source of truth; nothing host-side changes).
