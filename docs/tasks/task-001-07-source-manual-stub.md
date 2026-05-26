# Task 001-07: `wiki-source-manual` adapter stub [STUB CREATION]

## Use Case Connection
- UC-02 (manual ingest of existing markdown)
- UC-05 (bulk migration of `tmp2/`)

## Task Goal
Concrete `ManualSourceAdapter(SourceAdapter)` whose `fetch(...)` returns a hardcoded `SourceOutput` for any input. Path-traversal validation is a stub returning `True` (real validation in task-001-12 and called from task-001-24). Establishes the call-site so the E2E stub harness can be wired.

## Changes Description

### New Files
- `scripts/wiki_source/manual.py`:
  - `class ManualSourceAdapter(SourceAdapter):`
    - `def authenticate(self, config: dict) -> None: pass` (no-op).
    - `def fetch(self, item: SourceItem) -> SourceOutput:` — returns hardcoded `SourceOutput(page_slug='stub-page', project='_vault_', output_path=item.source_path, file_hash='0'*64, trust_level='high', frontmatter={'type': 'summary', 'title': 'STUB'}, body_text='STUB BODY', refs=[])`.
    - `def dedup_state_key(self, item: SourceItem) -> str: return 'stub-key'`.
- `tests/test_source_manual_stub.py` — asserts hardcoded output is returned.

### Changes in Existing Files
None.

### Component Integration
- Returned by adapter dispatcher (currently not present; will be added in task-001-25 when `wiki-index-upsert` impl wires it).
- E2E harness (task-001-11) asserts `fetch` returns the hardcoded stub.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: `ManualSourceAdapter().fetch(any_item)` returns hardcoded output.
   - Input Data: `SourceItem(kind='manual', source_path=Path('/tmp/x.md'), vault_root=Path('/tmp'), vault_id='test', extra={})`.
   - Expected Result: `SourceOutput(page_slug='stub-page', project='_vault_', file_hash='0'*64, ...)`.
   - Note: at stub stage, hardcoded result is expected.

### Unit Tests
1. **TC-UNIT-01**: `trust_level` is `'high'` (matches R-15.3 for manual).
2. **TC-UNIT-02**: `refs` is empty list (real ref extraction in task-001-24).

### Regression Tests
- task-001-06 abstract enforcement still holds.

## Acceptance Criteria
- [ ] Class instantiates, all three methods exist.
- [ ] `fetch(...)` returns the documented hardcoded output regardless of input.
- [ ] `tests/test_source_manual_stub.py` passes.

## Notes
- Real frontmatter parsing, file_hash computation, and ref extraction are all task-001-24.
- The `'0'*64` hash placeholder is intentional — flags the stub clearly in any leaked output.
