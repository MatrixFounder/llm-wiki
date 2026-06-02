# task-017-06 — [LOGIC] align the load-gate engine + document dialect

**Parent:** TASK 017. **Depends on:** 017-02. **RTM:** R-017-1f, R-017-1h.

## Goal
Make the load-time `_redos_budget_check` probe each pattern under the **same** engine that
will run it (operator→`regex`, built-in→stdlib `re`), so load-gate and runtime share one
dialect. Keep the gate as defense-in-depth (it is NOT removed). Document the dialect change.

## Design (locked — ARCHITECTURE.md §3.5)
`_redos_budget_check(config)` currently `re.compile(pat)` for every pattern. Change: when the
pattern's list was operator-supplied (`config.{ref_extraction,paths}_operator_supplied`),
compile/probe with `regex.compile` (the runtime engine); else keep `re.compile`. The
break-on-over budget loop and exit-6 behavior are unchanged. A pattern that fails to compile
under its engine → `LayoutConfigError` (parity with today, edge A-2).

## Steps
1. Branch the compile inside `_redos_budget_check` on per-list provenance.
2. Add a dialect note to the `layout_config.py` module docstring and to
   `config/layout-config.schema.yaml` (`ref_extraction[].regex` / `project_pattern`
   descriptions): "operator patterns run under the PyPI `regex` engine, V0 mode =
   `re`-compatible near-superset".
3. GREEN `test_redos_gate_rejects_operator_regex_under_regex_engine` (a `regex`-catastrophic
   operator pattern is rejected at load with exit-6) + `test_redos_gate_builtin_uses_re`
   (built-in patterns still probed under `re`; karpathy loads clean).

## Verification
- `pytest -q -k "redos_gate"` GREEN; existing `_redos_budget_check` tests green.
- `mypy --strict scripts/` clean.
