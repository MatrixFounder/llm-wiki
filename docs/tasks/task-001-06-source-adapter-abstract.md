# Task 001-06: `SourceAdapter` abstract base + dataclasses [STUB CREATION]

## Use Case Connection
- UC-02 (manual adapter implements this contract)
- UC-05 (bulk migration uses manual adapter)

## Task Goal
Define the `SourceAdapter` `abc.ABC` interface and the request/response dataclasses (`SourceItem`, `SourceOutput`) that all source adapters (manual in Phase 3a; transcript/light in Phase 3b) implement.

## Changes Description

### New Files
- `scripts/wiki_source/__init__.py` — already created in task-001-02; this task adds module content.
- `scripts/wiki_source/base.py`:
  - `@dataclass(frozen=True) class SourceItem: kind: Literal['manual','transcript','light']; source_path: Path; vault_root: Path; vault_id: str; extra: dict`
  - `@dataclass(frozen=True) class SourceOutput: page_slug: str; project: str; output_path: Path; file_hash: str; trust_level: Literal['high','medium','low']; frontmatter: dict; body_text: str; refs: list[PageRef]`
  - `class SourceAdapter(abc.ABC):`
    - `@abc.abstractmethod def authenticate(self, config: dict) -> None: ...` — no-op for manual; OAuth for future email.
    - `@abc.abstractmethod def fetch(self, item: SourceItem) -> SourceOutput: ...` — main entry; produces normalized output.
    - `@abc.abstractmethod def dedup_state_key(self, item: SourceItem) -> str: ...` — returns a stable key for `source_state` table (e.g., `sha256(abs(source))[:16]`).
- `tests/test_source_adapter_base.py` — TC-UNIT abstract enforcement.

### Changes in Existing Files
None.

### Component Integration
- `SourceAdapter` returns `SourceOutput` to the caller; the calling skill (`wiki-index-upsert`) then constructs a `Page` from the output and invokes `repo.upsert_page` + `repo.replace_refs`.
- `PageRef` is imported from `scripts.wiki_index.models` — adapter is the producer.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: Cannot instantiate `SourceAdapter` directly.
   - Input Data: `SourceAdapter()`.
   - Expected Result: `TypeError`.

### Unit Tests
1. **TC-UNIT-01**: Dataclasses frozen.
2. **TC-UNIT-02**: `mypy --strict scripts/wiki_source/base.py` passes.

### Regression Tests
- task-001-03 dataclass tests still pass.

## Acceptance Criteria
- [ ] Abstract `SourceAdapter` declared with three abstract methods.
- [ ] `SourceItem` and `SourceOutput` dataclasses frozen.
- [ ] `mypy --strict scripts/wiki_source/` passes.
- [ ] `tests/test_source_adapter_base.py` passes.

## Notes
- Phase 3a only manual; Phase 3b adds `wiki-source-transcript` and `wiki-source-light` — same interface.
- `dedup_state_key` is the bridge to `source_state` table (used by transcript A4 idempotency in Phase 3b; manual adapter returns a no-op key but the method must still exist).
