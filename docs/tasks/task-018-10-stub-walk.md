# task-018-10 — [STUB] own bounded walk surface

**Parent:** TASK 018. **Depends on:** 018-05. **RTM:** E3.1e, EC-1/ID-5.

## Goal
Stub the wiki-sync-OWN discovery walk (NOT `iter_pages`, which is `.md`-only).

## Design (locked)
```python
@dataclass(frozen=True)
class Candidate:
    path: Path          # absolute
    rel: str            # vault-relative POSIX
    mtime: float
    in_raw: bool
    in_exclude_zone: bool

def iter_sync_candidates(zone: Path, *, vault_root: Path, config: SyncConfig) -> list[Candidate]: ...  # stub → []
```
Exclusion set: `_raw/.staging/**`, `_raw/.locks`, `_raw/failed`, plus `config.exclude` globs.

## Steps
1. Add `Candidate` + the `iter_sync_candidates` stub (returns `[]`) to `_sync.py`.
2. RED `test_walk_discovers_heterogeneous` — a fixture zone with `.md/.txt/.vtt/.docx` should
   yield ≥4 candidates (fails on the empty stub).

## Verification
- `pytest -q -k walk_discovers` → RED; `mypy --strict` clean.
