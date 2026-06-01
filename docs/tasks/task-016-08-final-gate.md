# task-016-08 — Final gate + docs

**Parent:** TASK 016. **Depends on:** 016-07. **RTM:** R-016-3, R-016-6, R-016-7b, NF1-4, AC-016-9/10.

## Goal
Close the refactor: full acceptance gate, dogfood smoke, behaviour-verbatim verification,
and the doc updates that point at the new layout.

## Context
- `skills/wiki-extract-concepts/SKILL.md:1` `<!-- Sync with scripts/wiki_skills/wiki_extract_concepts.py argparse … -->` pointer.
- `scripts/wiki_skills/.AGENTS.md` (the `wiki_extract_concepts.py` entry).
- ARCHITECTURE.md §2.1 already added in the Architecture phase (no further edit unless layout drifted).

## Steps
1. **Full acceptance gate**:
   - `python -m pytest tests/ -q` → ≥ 879 (+4 skip), 0 failures; the lock/canary/perf/integration guards UNMODIFIED (only the single `_SRC` repoint in `test_extract_concepts_candidate_regression.py` allowed).
   - `mypy --strict scripts/` → 0 errors; no new `type: ignore` beyond carried-over.
   - `python -m scripts.wiki_skills.wiki_extract_concepts --help` → 0.
2. **Dogfood smoke** (AC-016-9): fresh `samples/` vault — scaffold (karpathy) → write a source → `wiki-reindex --full` → `prepare` → `apply --ingest` → `prepare --batch` → `apply --batch-candidates --ingest`; confirm the envelopes match the TASK 015 dogfood shapes (incl. `known_concepts` top-level hoist, batch isolation, `DB_WRITE_FAILED` on an unindexed source).
3. **Behaviour-verbatim spot-check** (AC-016-10): `git diff main…` — confirm the moved function bodies are byte-verbatim (only relocation + import wiring + the one `_SRC` repoint); no logic edit.
4. **Docs**:
   - Repoint the SKILL.md `<!-- Sync -->` comment → `scripts/wiki_skills/wiki_extract_concepts/__init__.py` (where `_build_parser_v3` lands).
   - Update `scripts/wiki_skills/.AGENTS.md`: the `wiki_extract_concepts` entry now documents the package layout (facade + `_validation`/`_sourcing`/`_db`/`_pages`/`_errors`) + the facade-global lock invariant + the `_db` carve-out.
   - Update the CLAUDE.md status header + ROADMAP "Done" entry for TASK 016.

## Acceptance
- ✅ AC-016-1..10 all PASS (see TASK.md): import path + 8 rebindable names + `_manifest_consumer` identity + `-m` + full suite + mypy + advisory sizes + dogfood + verbatim diff.
- ✅ Docs synced (SKILL pointer, .AGENTS.md, ARCHITECTURE §2.1, CLAUDE, ROADMAP).

## Files
- `skills/wiki-extract-concepts/SKILL.md` (sync-pointer repoint)
- `scripts/wiki_skills/.AGENTS.md` (package-layout entry)
- `CLAUDE.md`, `docs/ROADMAP.md` (status/Done)
