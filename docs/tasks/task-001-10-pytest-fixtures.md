# Task 001-10: pytest fixtures — minimal-vault + multi-vault (trade-agents-shaped) [STUB CREATION]

## Use Case Connection
- All UCs (test corpora consumed by E2E + unit tests)

## Task Goal
Create deterministic vault fixtures under `tests/fixtures/` that all subsequent tasks (Stage 1 stubs and Stage 2 impl) can use. Both fixtures match the two-tier promotion-spec layout so that reindex tests have realistic input.

## Changes Description

### New Files
- `tests/fixtures/__init__.py` — empty.
- `tests/fixtures/.AGENTS.md` — fixture conventions: "All fixtures rooted under `tests/fixtures/`; each fixture's `WIKI_SCHEMA.md` MUST contain `vault_id` per ADR-002 §D1.1; do not commit large binary artifacts."
- `tests/fixtures/minimal-vault/` — single-vault, 3 pages:
  - `WIKI_SCHEMA.md` with frontmatter `vault_id: minimal-test`, `schema_version: 2.0`.
  - `_sources/alpha.md`, `_sources/beta.md`, `_concepts/example-concept.md` — minimal frontmatter (`type`, `title`, `date`, `tags`) + 1-2 wiki-links each.
  - `log.md` with 2 events (per R-09 format).
- `tests/fixtures/multi-vault/` — two-tier shape, 2 vaults:
  - `vault-alpha/` with `WIKI_SCHEMA.md` (vault_id: `vault-alpha`), `_sources/`, `_concepts/`, `Lessons/<course>/_concepts/` (course-local), and `log.md`.
  - `vault-beta/` mirroring layout with `vault_id: vault-beta`; intentionally shares one concept slug (`shadow-ai.md`) for cross-vault duplicate detection tests (R-29).
- `tests/conftest.py` — pytest fixtures:
  - `@pytest.fixture def minimal_vault(tmp_path) -> Path:` — copies `tests/fixtures/minimal-vault/` to a tmp dir, returns the path.
  - `@pytest.fixture def multi_vault(tmp_path) -> dict[str, Path]:` — copies both vaults, returns `{'vault-alpha': ..., 'vault-beta': ...}`.
  - `@pytest.fixture def repo_factory(tmp_path) -> Callable[[], IndexRepository]:` — returns a callable that creates a fresh `SQLiteRepository` on a tmp DB file (initially raises `NotImplementedError` on use; becomes functional after task-001-15).

### Changes in Existing Files
- `pytest.ini` — add `[pytest]` option `addopts = --strict-markers --tb=short`.

### Component Integration
- Stage 2 tasks reuse these fixtures via `pytest` injection.
- task-001-11 E2E harness explicitly consumes both `minimal_vault` and `multi_vault`.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: `minimal_vault` fixture yields a path with `WIKI_SCHEMA.md` containing `vault_id`.
   - Input Data: pytest function takes `minimal_vault` arg.
   - Expected Result: `(minimal_vault / 'WIKI_SCHEMA.md').exists()`; YAML frontmatter parseable; `vault_id == 'minimal-test'`.

### Unit Tests
1. **TC-UNIT-01**: Multi-vault fixture has both vaults with distinct `vault_id`.
2. **TC-UNIT-02**: Shared-slug concept (`shadow-ai.md`) exists in both vaults under `_concepts/`.

### Regression Tests
- N/A (new fixtures only).

## Acceptance Criteria
- [ ] Both fixture trees present.
- [ ] `WIKI_SCHEMA.md` in each vault has valid `vault_id` matching the SQLite CHECK pattern.
- [ ] `conftest.py` exposes `minimal_vault`, `multi_vault`, `repo_factory`.
- [ ] All TC tests pass.

## Notes
- DO NOT use real iCloud paths in fixture metadata — keep everything under pytest `tmp_path`.
- Shared `shadow-ai.md` is the lynchpin of R-29 cross-vault duplicate detection tests.
- Course-local concept directories (`Lessons/<course>/_concepts/`) test promotion-spec §5.1 walk-up.
