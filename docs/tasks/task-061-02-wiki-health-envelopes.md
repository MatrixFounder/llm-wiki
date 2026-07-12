# Task 061-02 — [LOGIC] `wiki-health` envelopes carry the denominators

RTM: **R-061-1** (surface half). Depends on: `061-01`.

## Goal

`{"total_gaps": 0}` must become impossible to mistake for a real green. Both `wiki-health`
subcommands emit their family's denominators + per-rule `matched` — **additive keys only**,
exit code **still 0 always** (ADR-006 unchanged).

## Context

- `scripts/wiki_skills/wiki_health.py:75-145` — `_run_coverage` (filters **rules** by `--class`
  *before* the DAL call) and `_run_ontology` (filters **violations** by `--class` *after* the
  call, and has an early-return branch when `layout.ontology is None`).
- `scripts/wiki_skills/_common.py::emit` — the one-envelope contract.

## Changes — `scripts/wiki_skills/wiki_health.py`

### `_run_coverage`

```python
report = repo.find_coverage_gaps_report(args.vault, rules)
envelope = {
    "action": "coverage", "vault": args.vault, "rules": len(rules),
    "total_gaps": len(report.gaps),          # unchanged key
    "pages_examined": report.pages_examined, # NEW
    "by_rule": [s.to_json() for s in report.rule_stats],  # NEW
    "by_class": by_class,                    # unchanged
    "gaps": [...],                           # unchanged
}
```

### `_run_ontology`

Add `"edges_examined"`, `"property_pages_examined"`, `"by_rule"`. **The `layout.ontology is
None` early-return branch must emit the same keys (all zero)** — a consumer must never see a
missing key depending on config (this is the same "enumerate the surfaces" discipline: there
are TWO exit paths in this function, not one).

### The `examined nothing` note (the point of the task)

Extend the existing `note` convention:

- coverage, `rules` present but `pages_examined == 0` →
  `"note": "coverage rules are configured, but NO page carries an authored $.type in those classes — nothing was examined (this is not a clean bill of health)"`
- ontology, `edges_examined == 0 and property_pages_examined == 0` → the analogous note.
- the existing "no coverage rules configured for this layout" / "no ontology contract configured
  for this layout" notes stay as-is (a different, already-honest condition).

### `--class` semantics (document in the module docstring; do not change behavior)

Coverage filters **rules** ⇒ the denominators scope to the filtered run. Ontology filters
**violations** ⇒ the denominators describe the whole run (what the DAL actually examined). Both
are honest; the per-rule invariant holds in both (`shown_r ≤ matched_r`). State it, don't
silently leave it ambiguous.

## Test cases — extend `tests/test_wiki_health.py`

1. **TC-02-1** — typed vault, `coverage`: `pages_examined > 0`, `by_rule[*].matched` present,
   exit 0; the per-rule invariant holds **read from the JSON envelope alone**.
2. **TC-02-2 (vacuity)** — untyped vault: `{"total_gaps": 0, "pages_examined": 0}` **plus** the
   `note`. Assert the note text.
3. **TC-02-3** — `ontology` on a vault with typed pages + refs: `edges_examined > 0`,
   `property_pages_examined > 0`; on the untyped vault both `0` + note; on a **karpathy** vault
   (no `ontology:` block) the early-return branch emits the same key set (all zero).
4. **TC-02-4 (additive-only)** — the pre-061 key set is a **subset** of the new envelope's keys
   for both subcommands (freeze the old key list as a literal in the test).
5. **TC-02-5** — `--class` on both subcommands still exits 2 on `INVALID_CLASS`, and the
   invariant still holds on the filtered envelope.

## Verification

```bash
source .venv/bin/activate
pytest tests/test_wiki_health.py tests/test_health_denominators.py -q
mypy --strict scripts/
# manual smoke (JSON eyeball):
python3 -m scripts.wiki_skills.wiki_health coverage --vault <fixture-vault> --db-path /tmp/x.db
```

## Acceptance criteria

- [ ] Both subcommands, **all exit paths** (incl. `ontology`'s `None` early-return), emit the
      new keys. Grep the function for `return emit(` and confirm every site — do not assume
      there is one.
- [ ] Exit code is 0 in every non-error path (ADR-006 unchanged).
- [ ] No key renamed or removed (TC-02-4).
