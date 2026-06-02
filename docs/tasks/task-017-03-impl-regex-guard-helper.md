# task-017-03 — [LOGIC] implement the regex guard helper

**Parent:** TASK 017. **Depends on:** 017-01. **RTM:** R-017-1b.

## Goal
Implement `guarded_finditer` / `guarded_search`: stdlib `re` passthrough for built-ins,
`regex` engine with a shrinking per-file deadline for operator patterns.

## Design (locked — ARCHITECTURE.md §3.5)
```python
import re, regex                       # regex = PyPI engine
from time import monotonic

def guarded_finditer(pattern, text, *, operator, deadline):
    if not operator:
        yield from re.compile(pattern).finditer(text)        # byte-identity path
        return
    remaining = None if deadline is None else max(0.0, deadline - monotonic())
    # regex raises the BUILTIN TimeoutError past the deadline (verified — NOT regex.TimeoutError)
    yield from regex.compile(pattern).finditer(text, timeout=remaining)

def guarded_search(pattern, text, *, operator, deadline):
    if not operator:
        return re.compile(pattern).search(text)
    remaining = None if deadline is None else max(0.0, deadline - monotonic())
    return regex.compile(pattern).search(text, timeout=remaining)
```
Notes: compile-caching is fine (both `re` and `regex` cache compiled patterns). `remaining <= 0`
→ pass `timeout=0` (regex treats as immediate deadline → `TimeoutError`).

## Steps
1. Implement both helpers per the design.
2. GREEN `test_guarded_finditer_timeout` (operator `(a|a)*$` on 100 KB single line, deadline
   0.5 s → `TimeoutError` raised within ~0.5 s, asserted with a wall-clock upper bound).
3. Add `test_guarded_builtin_uses_re`: `list(guarded_finditer(r'\[\[([^\]]+)\]\]', body,
   operator=False, deadline=None))` == `list(re.compile(...).finditer(body))` (output parity).

## Verification
- `pytest -q tests/test_task017_hardening.py -k guarded` GREEN.
- `mypy --strict scripts/` clean (the `regex` import typed via `types-regex`).
