# task-017-04 — [LOGIC] wire `extract_refs` to the guard (per-file budget)

**Parent:** TASK 017. **Depends on:** 017-02, 017-03. **RTM:** R-017-1c, AC-017-1, AC-017-2.

## Goal
Route operator-custom `ref_extraction[].regex` through the guard with a per-file deadline;
degrade to skip-file-with-WARN on timeout. Built-in layouts keep the stdlib `re` path.

## Design (locked — ARCHITECTURE.md §3.5)
`scripts/wiki_source/parsing.py`:
```python
def extract_refs(body, rules, *, operator_supplied: bool = False,
                 budget_s: float = WIKI_REDOS_BUDGET_S) -> list[tuple[str, int, str]]:
    deadline = monotonic() + budget_s if operator_supplied else None
    out = []
    try:
        for i, line in enumerate(body.splitlines(), start=1):
            quote = line.strip()[:200]
            for rule in rules:
                for m in guarded_finditer(rule.regex, line, operator=operator_supplied,
                                          deadline=deadline):
                    ...                       # unchanged target/transform logic
    except TimeoutError:
        logging.getLogger(__name__).warning(
            "[redos-skip] ref-extraction exceeded %.1fs budget; skipping file refs "
            "(%d lines scanned)", budget_s, i)        # names neither pattern nor body
        return []                                     # deterministic: empty, not partial
    return out
```
Caller: `reindex.py` `_body_refs` (the `extract_refs(out.body_text, ref_rules)` site at
:228) passes `operator_supplied=config.ref_extraction_operator_supplied`. The pre-compile of
`rules` (current line 92) moves into `guarded_finditer` (which compile-caches), or stays for
the built-in branch — keep behavior identical for built-ins.

## Steps
1. Add the two kwargs; thread the deadline; wrap the loop in the `TimeoutError` handler.
2. Update the `reindex._body_refs` call site to pass the provenance flag.
3. GREEN `test_extract_refs_operator_timeout_skips` (UC-1: operator catastrophic rule on a
   100 KB single line → `[]` + WARN, no hang) and `test_extract_refs_builtin_byte_identical`
   (UC-2: built-in wiki-link rule output unchanged vs current).

## Verification
- `pytest -q -k "extract_refs"` GREEN; existing parsing/reindex tests green.
- AC-017-1: an integration-style test reindexing a tiny custom-layout vault with the bad
  pattern completes (wall-clock bounded) and records the skip.
- `mypy --strict scripts/` clean.
