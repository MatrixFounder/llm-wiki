# Task 001-13: `config_loader.py` — `load_config(cwd)` walk-up + deep-merge + JSON Schema validation [LOGIC IMPLEMENTATION]

## Use Case Connection
- All UCs (every skill starts with `load_config(cwd)`)

## Task Goal
Replace any config-loading stubs with a real implementation: walk up the filesystem from `cwd` to find vault root (`WIKI_SCHEMA.md` marker), parse root `CLAUDE.md::wiki:` YAML block, find the nearest `.wiki.yaml` (project override), deep-merge in that order, and validate the result against `config/wiki-config.schema.yaml`. Fail-fast on schema violation per R-01.3.

## Changes Description

### New Files
- `scripts/wiki_index/config_loader.py`:
  - `def find_vault_root(cwd: Path) -> Path:` — walk up looking for `WIKI_SCHEMA.md`; raise `VaultRootNotFoundError` if not found before filesystem root.
  - `def find_project_root(cwd: Path, vault_root: Path) -> Path | None:` — walk up from `cwd` (stopping at `vault_root`) looking for `.wiki.yaml`; return None if none.
  - `def load_root_config(vault_root: Path) -> dict:` — parse `vault_root/CLAUDE.md`, extract YAML block under `wiki:` key (using `pyyaml` + frontmatter pattern).
  - `def load_project_override(project_root: Path) -> dict:` — parse `<project_root>/.wiki.yaml` as YAML.
  - `def deep_merge(base: dict, override: dict) -> dict:` — recursive merge; override wins on scalar; lists replaced (not concatenated); dicts merged recursively.
  - `def load_config(cwd: Path) -> dict:` — orchestrates above + validates result against schema; returns merged config.
  - `class VaultRootNotFoundError(RuntimeError): pass`
  - `class ConfigValidationError(ValueError): pass`
- `tests/test_config_loader.py` — exhaustive: walk-up logic, merge semantics, validation pass/fail.

### Changes in Existing Files
- `scripts/wiki_skills/wiki_init.py` (and other skill scaffolds): replace any inline config-load with `from scripts.wiki_index.config_loader import load_config`.
- `tests/test_e2e_stage1_stubs.py`: replace any stub-config assertions with real merged-config assertions.

### Component Integration
- Returns a dict (not a dataclass) — keeps schema-driven flexibility; downstream skills index by known keys.
- The vault_root discovery handles edge cases: nested vaults (use outermost), symlinks (resolve before walk-up).

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: Load config from inside a fixture project.
   - Input Data: `cwd = tests/fixtures/minimal-vault/Lessons/<course>/`.
   - Expected Result: `load_config(cwd)['vault_id'] == 'minimal-test'`; merge from root + (if present) project override.

### Unit Tests
1. **TC-UNIT-01**: `find_vault_root` walks up correctly.
2. **TC-UNIT-02**: Deep-merge: nested dict merged; list replaced.
3. **TC-UNIT-03**: Missing `vault_id` in root config → `ConfigValidationError`.
4. **TC-UNIT-04**: Invalid `vault_id` format → `ConfigValidationError` (matches schema CHECK).
5. **TC-UNIT-05**: Project override scalar wins over root.

### Regression Tests
- All Stage 1 tests still pass.
- E2E harness updated to assert real config (no more stub config).

## Acceptance Criteria
- [ ] All functions implemented per spec.
- [ ] `mypy --strict scripts/wiki_index/config_loader.py` passes.
- [ ] All TC tests pass.
- [ ] Validation uses `jsonschema.Draft202012Validator` with the schema from task-001-02.
- [ ] E2E stub harness (task-001-11) updated where applicable.

## Notes
- R-01.2 deep-merge: "lists are replaced, not concatenated" — operator override semantics.
- R-01.3 fail-fast: any validation error must include JSON pointer to the offending field.
- `pyyaml.safe_load` only — never `yaml.load`. Security-critical.
