# task-018-01 — [STUB] DAL `get_source_state` / `set_source_state`

**Parent:** TASK 018. **Depends on:** 018-00. **RTM:** E3.4d, Q-018-8. **Design:** ARCHITECTURE.md §11a Q-018-8 + interfaces §5.4 + data-model *SourceState partition*.

## Goal
Lay the Stub-First DAL surface for the `wiki-sync`-owned idempotency partition.

## Design (locked)
`source_state` is the existing table (PK `(vault_id, source_kind, scope, key)`, **no
`source_kind` CHECK** → `'sync'` is legal data, zero DDL). Two **generic** methods (NOT the
query-specific `check_query_state`/`record_query_state`):
```python
def get_source_state(self, vault_id: str, source_kind: str, scope: str, key: str) -> str | None: ...
def set_source_state(self, vault_id: str, source_kind: str, scope: str, key: str, value: str) -> None: ...
```

## Steps
1. Add both abstract signatures to `IndexRepository` (`scripts/wiki_index/repository.py`).
2. Add `SQLiteRepository` stubs (`scripts/wiki_index/sqlite_repository.py`) → `raise NotImplementedError`.
3. RED `test_source_state_roundtrip` in `tests/test_wiki_sync.py` (set then get returns the value) — fails on the stub.

## Verification
- `pytest -q -k source_state_roundtrip` → RED (xfail-marked); all else GREEN; `mypy --strict` clean (fully typed).
