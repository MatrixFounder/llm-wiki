# Task 001-03: `IndexRepository` abstract base + dataclasses [STUB CREATION]

## Use Case Connection
- UC-02 (upsert), UC-03 (search), UC-04 (lint), UC-05 (bulk migration)
- All UCs that interact with the DB go through this interface

## Task Goal
Define the Python `abc.ABC` interface `IndexRepository` and the typed dataclasses passed across the DAL boundary (`Page`, `Entity`, `PageHit`, `LogEvent`, `Vault`, `OrphanLink`, `BatchRun`, `PageRef`, `DriftReport`). All methods are declared abstract; no concrete implementation in this task.

## Changes Description

### New Files
- `scripts/wiki_index/models.py` — dataclasses:
  - `@dataclass(frozen=True) class Vault: vault_id: str; name: str; root_path: Path; schema_version: str; registered_at: datetime; config_json: dict | None`
  - `@dataclass(frozen=True) class Page: vault_id: str; slug: str; project: str; type: Literal['summary','concept','query','brief','research','index','log']; title: str; tldr: str | None; date: date | None; last_modified: datetime; file_hash: str; frontmatter_json: dict; body_excerpt: str; tags: list[str]`
  - `@dataclass(frozen=True) class Entity: vault_id: str; slug: str; type: str; name: str; aliases: list[str]; description: str | None; is_external: bool`
  - `@dataclass(frozen=True) class PageHit: page: Page; bm25_score: float; snippet: str`
  - `@dataclass(frozen=True) class PageRef: vault_id: str; page_slug: str; page_project: str; entity_slug: str; ref_type: str; line_start: int | None; line_end: int | None; source_quote: str | None; trust_level: Literal['high','medium','low']`
  - `@dataclass(frozen=True) class LogEvent: id: int | None; vault_id: str; event_ts: datetime; event_type: str; subject: str | None; pages_created_json: list[str]; pages_updated_json: list[str]; details_json: dict; log_md_path: str | None; log_md_byte_offset: int | None`
  - `@dataclass(frozen=True) class OrphanLink: vault_id: str; source_page_slug: str; source_page_project: str; target_slug: str; line_start: int | None; source_quote: str | None`
  - `@dataclass(frozen=True) class BatchRun: id: int | None; vault_id: str; mode: Literal['full','delta']; started_at: datetime; finished_at: datetime | None; status: Literal['success','failure','partial']; notes: str | None`
  - `@dataclass(frozen=True) class DriftReport: missing_in_db: list[Path]; missing_on_disk: list[tuple[str, str]]; hash_mismatch: list[tuple[str, str]]; type_mismatch: list[tuple[str, str, str, str]]` — last tuple is `(slug, project, file_type, db_type)`
- `scripts/wiki_index/repository.py` — `class IndexRepository(abc.ABC)` with all abstract methods (signatures listed below). All methods raise `NotImplementedError` by virtue of being abstract.
- `tests/test_models.py` — dataclass smoke tests (instantiation, frozen-ness).

### Changes in Existing Files
None.

### Abstract Methods (all `@abc.abstractmethod` in `IndexRepository`)

```python
# Vault registry (R-27)
def register_vault(self, vault: Vault) -> None: ...
def get_vault(self, vault_id: str) -> Vault | None: ...
def list_vaults(self) -> list[Vault]: ...
def rename_vault(self, old_vault_id: str, new_vault_id: str) -> None: ...   # ON UPDATE CASCADE

# Pages CRUD (R-04, R-07)
def upsert_page(self, page: Page) -> Literal['inserted','updated','unchanged']: ...
def get_page(self, vault_id: str, slug: str, project: str) -> Page | None: ...
def delete_page(self, vault_id: str, slug: str, project: str) -> None: ...

# Search (R-10, R-29)
def search_pages(self, query: str, *, vaults: list[str] | None = None,
                 types: list[str] | None = None, project: str | None = None,
                 limit: int = 20) -> list[PageHit]: ...

# Refs (R-07)
def upsert_refs(self, refs: list[PageRef]) -> None: ...
def replace_refs(self, vault_id: str, page_slug: str, page_project: str,
                 refs: list[PageRef]) -> None: ...
def get_backlinks(self, vault_id: str, entity_slug: str) -> list[PageRef]: ...

# Lint (R-11, R-29)
def find_orphan_links(self, vault_id: str | None = None) -> list[OrphanLink]: ...
def find_pages_missing_in_index(self, vault_id: str, vault_root: Path) -> list[Path]: ...
def check_drift(self, vault_id: str) -> DriftReport: ...
def find_cross_vault_concept_duplicates(self) -> list[tuple[str, list[str]]]: ...   # (concept_slug, [vault_id, ...])

# Log events (R-28)
def append_log_event(self, event: LogEvent) -> int: ...   # returns autoincrement id
def query_log_events(self, vault_id: str, *, since: datetime | None = None,
                     until: datetime | None = None,
                     event_types: list[str] | None = None) -> list[LogEvent]: ...

# Batch runs
def begin_batch_run(self, vault_id: str, mode: Literal['full','delta']) -> int: ...
def finish_batch_run(self, run_id: int, status: str, notes: str | None = None) -> None: ...
def last_batch_run(self, vault_id: str) -> BatchRun | None: ...

# Stub (Epic 7)
def resolve_entity(self, vault_id: str, slug: str) -> Entity | None:
    raise NotImplementedError('entity resolution arrives in Epic 7')
```

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: Cannot instantiate `IndexRepository` directly.
   - Input Data: `IndexRepository()`.
   - Expected Result: raises `TypeError` (Python ABC enforcement).

### Unit Tests
1. **TC-UNIT-01**: All dataclasses are frozen.
   - Tested entity: `Page`, `Vault`, `Entity`, etc.
   - Expected Result: assigning to an attribute raises `dataclasses.FrozenInstanceError`.
2. **TC-UNIT-02**: `mypy --strict scripts/wiki_index/repository.py` passes.

### Regression Tests
- N/A.

## Acceptance Criteria
- [ ] All dataclasses listed in `scripts/wiki_index/models.py`.
- [ ] All abstract methods listed in `scripts/wiki_index/repository.py`.
- [ ] `mypy --strict scripts/wiki_index/` passes.
- [ ] `IndexRepository()` raises `TypeError`.
- [ ] `tests/test_models.py` passes.

## Notes
- ADR-002 §D8 Class A/B/C labels are NOT stored in dataclasses but are documented in docstrings for each model field.
- `tags: list[str]` is denormalized from JSON for ergonomics — `frontmatter_json['tags']` is the source.
- `resolve_entity` intentionally raises `NotImplementedError` instead of being abstract — concrete subclasses inherit the stub without override.
