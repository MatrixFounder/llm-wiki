# task-017-01 — [STUB] guard helper + provenance fields + budget constant

**Parent:** TASK 017. **Depends on:** 017-00. **RTM:** R-017-1a/b (partial), Q-017-1 (partial).

## Goal
Lay the Stub-First surface for the runtime ReDoS guard: the budget constant, the two guard
helper signatures (stubbed), and the `LayoutConfig` provenance fields — plus RED tests.

## Design (locked — ARCHITECTURE.md §3.5 "Runtime ReDoS deadline")
In `scripts/wiki_index/layout_config.py`:
```python
def _env_float(name: str, default: float) -> float: ...   # tiny helper, tolerant parse
WIKI_REDOS_BUDGET_S: float = _env_float("WIKI_REDOS_BUDGET_S", 2.0)

def guarded_finditer(pattern: str, text: str, *, operator: bool,
                     deadline: float | None) -> Iterator[Match[str]]:
    raise NotImplementedError  # 017-03

def guarded_search(pattern: str, text: str, *, operator: bool,
                   deadline: float | None):
    raise NotImplementedError  # 017-03
```
Add to `LayoutConfig` (frozen dataclass, line ~150) two fields with defaults so existing
construction sites stay valid:
```python
ref_extraction_operator_supplied: bool = False
paths_operator_supplied: bool = False
```

## Steps
1. Add `WIKI_REDOS_BUDGET_S` + `_env_float`.
2. Add the two `guarded_*` stubs (typed; `NotImplementedError`).
3. Add the two `LayoutConfig` provenance fields (default `False`).
4. RED tests in `tests/test_task017_hardening.py`:
   - `test_guarded_finditer_timeout` — operator catastrophic pattern `(a|a)*$` on `'a'*60+'!'`
     with `deadline=monotonic()+0.5` should raise `TimeoutError` (RED: stub raises
     `NotImplementedError`).
   - `test_provenance_flags_on_override` — a `LayoutConfig` resolved from a vault whose
     override supplies `ref_extraction` has `ref_extraction_operator_supplied is True`
     (RED until 017-02).

## Verification
- `pytest -q tests/test_task017_hardening.py -k "guarded or provenance"` → the two new tests
  RED (xfail-marked or expected-fail), all else GREEN.
- `mypy --strict scripts/` clean (stubs fully typed).
