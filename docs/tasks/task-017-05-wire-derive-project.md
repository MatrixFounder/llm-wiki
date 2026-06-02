# task-017-05 — [LOGIC] wire `_derive_project` to the guard

**Parent:** TASK 017. **Depends on:** 017-02, 017-03. **RTM:** R-017-1d.

## Goal
Run operator-custom `project_pattern` under the guard; on timeout return `UNMATCHED_PROJECT`
+ WARN (exact parity with the existing pattern-miss branch). Built-ins keep stdlib `re`.

## Design (locked — ARCHITECTURE.md §3.5)
`scripts/wiki_index/layout_config.py::_derive_project(rel_posix, entry, *,
operator_supplied: bool = False)`:
```python
if entry.project_pattern is not None:
    try:
        match = guarded_search(entry.project_pattern, rel_posix,
                               operator=operator_supplied,
                               deadline=(monotonic() + WIKI_REDOS_BUDGET_S
                                         if operator_supplied else None))
    except TimeoutError:
        _LOG.warning("[redos-skip] project_pattern exceeded budget for %s (glob=%s)",
                     rel_posix, entry.glob)          # path is short/known; no pattern echo
        return UNMATCHED_PROJECT
    if match is None:
        _LOG.warning("[unmatched-pattern] %s (glob=%s)", rel_posix, entry.glob)
        return UNMATCHED_PROJECT
    ...                                              # unchanged template/slug logic
```
`iter_pages` passes `operator_supplied=config.paths_operator_supplied` at the `_derive_project`
call site (layout_config.py:497).

## Steps
1. Add the kwarg + `TimeoutError` branch; thread the flag from `iter_pages`.
2. GREEN `test_derive_project_operator_timeout_unmatched` (custom `project_pattern`
   catastrophic on a long synthetic rel-path → `UNMATCHED_PROJECT` + WARN, no hang).

## Verification
- `pytest -q -k "derive_project"` GREEN; karpathy byte-identity green (built-in path
  unchanged); `mypy --strict scripts/` clean.
