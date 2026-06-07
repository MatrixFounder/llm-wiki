# Task 019.02: [LOGIC] loader parse + detect defaults + back-compat — `skill-tdd-strict`

## Use Case Connection
- UC-5 · E3.1 · AC-7, AC-9, AC-11

## Task Goal
Parse the `resummarize:` block into `ResummarizeConfig`; apply schema defaults the
validator does NOT inject; preserve back-compat (absent block → `None`).

## Changes Description
#### File: `scripts/wiki_index/sync_config.py`
- `load_sync_config`: after `_validate(raw)`, build `resummarize` from `raw.get("resummarize")`:
  - absent → `None` (≡ TASK 018, AC-7).
  - `mode` default `if-missing`.
  - `detect` **omitted → `{source_state: True}`** only (OQ-5); else read each toggle.
  - `mirror.summary_ext` default `.md`; `mirror.match` default `group-key` when `key`/`group_key`
    present else `stem-relpath`; `provenance_ref.fields` default `[source, sources]`,
    `match` default `vault-rel-path`.
- Construct the frozen dataclasses (tuples for lists).

## Test Cases
### Unit (RED-first per `skill-tdd-strict`)
1. **TC-02-1:** absent block → `SyncConfig.resummarize is None`; **bead-00 golden re-run green** (AC-7).
2. **TC-02-2:** `resummarize: {mode: always}` → `detect == {source_state:True}` (default).
3. **TC-02-3:** full block round-trips into typed dataclasses.
4. **TC-02-4:** unknown key → `INVALID_SYNC_CONFIG` exit-6 path, **value never echoed**.
5. **TC-02-5:** bad `mode` enum → `INVALID_SYNC_CONFIG`.

## Acceptance Criteria
- [ ] Defaults applied per OQ-5; absent block ≡ TASK 018 (golden green).
- [ ] `mypy --strict` clean; full regression green.

## Notes
Strict bead: write the RED for TC-02-4/02-1 before the parse code.
