# Task 005-13: `wiki-lint` alias-collision detection (R-5.6)

## Use Case Connection
- UC-13 (lint detects alias collision)

## Task Goal
Add an `alias-collision` lint category: DB collisions (`find_alias_collisions`: in-table legacy + cross-table slug/name) **plus** a Class A frontmatter scan (two entity pages declaring the same alias surface — the only place a canonical conflict can survive post-hard-PK). `--json` parity; advisory non-zero exit only under `--strict`.

## Changes Description

### Changes in Existing Files
#### File: `scripts/wiki_skills/wiki_lint.py`
- Add `alias_collisions` to the lint result structure + human + `--json` output (same shape as existing categories).
- `--strict` raises the advisory exit code if any collision present (consistent with existing lint policy; default mode reports only).
#### File: `scripts/wiki_index/lint.py` (or wherever lint orchestration lives)
- Call `repo.find_alias_collisions(vault_id)` for DB collisions.
- Add a **frontmatter scan**: walk `_concepts/_entities` pages, collect `aliases:`, detect the same surface claimed by ≥2 entity pages → `AliasCollision(kind="frontmatter")`.

## Test Cases
### E2E (`tests/test_wiki_lint.py`)
1. **TC-E2E-01:** cross-table — alias equals a different entity's slug → reported in `alias_collisions`.
2. **TC-E2E-02:** in-table — legacy DB row (raw-SQL seeded) same alias → 2 slugs → reported.
3. **TC-E2E-03:** frontmatter — two `_concepts/*.md` each declaring `aliases: ["Hermes"]` → reported `kind="frontmatter"`.
4. **TC-E2E-04:** `--json` includes the new category with parity shape; `--strict` → non-zero advisory exit; default → exit 0 with report.
### Regression
- Existing lint categories (orphans, dangling, drift) unaffected; `pytest tests/test_wiki_lint.py` green.

## Acceptance Criteria
- [ ] In-table + cross-table + frontmatter collisions detected.
- [ ] `--json` parity; `--strict` advisory exit; default reports only.
- [ ] `mypy --strict` clean; regression green.

## Notes
Phase-1: empty `alias_collisions` category key present + RED tests; Phase-2: wire DAL + frontmatter scan. Depends on 005-07. The hard PK (005-01) means new in-table dups can't be created via the CLI — in-table detection targets legacy/pre-migration DBs.
