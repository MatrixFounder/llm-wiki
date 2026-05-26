# Task 001-02: Repo scaffolding + requirements.txt + `wiki-config.schema.yaml` stub [STUB CREATION]

## Use Case Connection
- UC-01: `wiki-init` (consumes config schema for validation)
- All UCs (each skill load_config first)

## Task Goal
Establish the implementation tree (`scripts/wiki_index/`, `scripts/wiki_source/`, `tests/`, `sql/`, `.agent/sessions/`), declare Python dependencies in `requirements.txt`, and add a JSON Schema 2020-12 stub (`config/wiki-config.schema.yaml`) covering `WikiRootConfig` (root `CLAUDE.md::wiki:` block) and `WikiProjectOverride` (`.wiki.yaml`). Schema MUST require `vault_id` per ADR-002 §D1.1.

## Changes Description

### New Files
- `requirements.txt` — `pyyaml>=6.0`, `python-frontmatter>=1.0`, `python-slugify>=8.0`, `jsonschema>=4.20`, `pytest>=7.4`, `pytest-cov>=4.1`, `mypy>=1.7`.
- `scripts/__init__.py` — empty.
- `scripts/wiki_index/__init__.py` — empty.
- `scripts/wiki_index/.AGENTS.md` — module memory describing DAL responsibility.
- `scripts/wiki_source/__init__.py` — empty.
- `scripts/wiki_source/.AGENTS.md` — adapters module memory.
- `tests/__init__.py` — empty.
- `tests/.AGENTS.md` — testing conventions (fixtures live in `tests/fixtures/`; pytest config in `pytest.ini`).
- `config/wiki-config.schema.yaml` — JSON Schema 2020-12 with two top-level definitions: `WikiRootConfig` (requires `vault_id`, `language`, `layout`, `paths`, optional `lint`, `transcript`, `light_summary`) and `WikiProjectOverride` (all fields optional, no `vault_id`).
- `config/.AGENTS.md` — config artifacts memory.
- `.agent/sessions/.gitkeep` — placeholder.
- `pytest.ini` — `[pytest]\ntestpaths = tests\npython_files = test_*.py\naddopts = --strict-markers`.

### Changes in Existing Files
None (initial scaffolding).

### Component Integration
- Schema will be consumed in task-001-13 by `config_loader.py` via `jsonschema.validate()`.
- `vault_id` pattern in schema MUST match SQLite CHECK: `^[a-z][a-z0-9-]{1,30}[a-z0-9]$` AND not `^.*--.*$` AND length 3-32 (M-1 from architecture review).

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: Validate a fixture config passes JSON Schema.
   - Input Data: `tests/fixtures/configs/valid-root-config.yaml` with `vault_id: trade-agents`, `language: en`, `layout: per-project`.
   - Expected Result: `jsonschema.validate(...)` does not raise.

### Unit Tests
1. **TC-UNIT-01**: Missing `vault_id` rejected.
   - Input Data: root config without `vault_id`.
   - Expected Result: `ValidationError` with `vault_id` mentioned.
2. **TC-UNIT-02**: Invalid `vault_id` format rejected.
   - Input Data: `vault_id: 1bad`, `vault_id: AB`, `vault_id: foo--bar`.
   - Expected Result: each raises `ValidationError`.

### Regression Tests
- N/A.

## Acceptance Criteria
- [ ] Directory tree as listed exists.
- [ ] `requirements.txt` contains all named packages.
- [ ] `pip install -r requirements.txt` succeeds in fresh venv.
- [ ] `config/wiki-config.schema.yaml` is valid JSON Schema 2020-12 (`jsonschema.Draft202012Validator.check_schema(...)` does not raise).
- [ ] Schema enforces `vault_id` REQUIRED + pattern + length per ADR-002 §D1.1.
- [ ] All TC-UNIT tests pass.
- [ ] Each new source directory has a `.AGENTS.md`.

## Notes
- Schema stub may use `additionalProperties: true` for now — tightening is part of task-001-13.
- Do NOT include `wiki-ingest` config keys in this MVP schema — Phase 3b extension.
- The pattern `^[a-z][a-z0-9-]{1,30}[a-z0-9]$` matches the SQLite CHECK (M-1) — must round-trip.
