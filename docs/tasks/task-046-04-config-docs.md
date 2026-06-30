# Task 046-04 (P3) — `.wiki/sync.yaml summarize:` config + docs

Beads: B13 (stub) · B14 (R-10, schema) · B15 (R-11/R-12, loader) · B16 (docs). Stub-First.
**Depends on** P2 (config drives the delegation knobs).

## Goal
A per-zone `summarize:` block in `.wiki/sync.yaml` selects the distil variant that
`wiki-sync` passes to `wiki-import`: `profile`→`--kind`, `diagrams`→`--diagrams`,
`extract_concepts`→`--concepts/--no-concepts`, `target_subdir`→folder suffix. Per-folder
deep-merge (deepest-wins), exactly like `resummarize:`. Absent block ≡ current defaults.

## Context (files to edit)
- `config/sync-config.schema.yaml` — add `$defs/Summarize` + `summarize:` on `SyncConfig`.
- `scripts/wiki_index/sync_config.py` — parse + per-folder deep-merge `summarize` (reuse the
  `resummarize` cascade machinery); resolve effective per file; map to `wiki-import` flags.
- Docs: `skills/wiki-import/SKILL.md`, `skills/wiki-sync/SKILL.md`,
  `workflows/{wiki-import,wiki-sync}.md`, `docs/ARCHITECTURE.md` (§1 Sync Dispatcher line).
- New test: `tests/test_sync_config_summarize.py`. Reference: existing sync-config / resummarize tests.

## Steps
1. **B13** — create test file with 5 `@pytest.mark.skip` stubs.
2. **B14 (R-10)** — schema `$defs/Summarize` (STRICT, `additionalProperties:false`):
   `profile` (enum `[auto,meeting,lesson,article]` → wiki-import `--kind`; `auto` default — `pyramid`
   dropped: it has no `--kind`; the pyramid *grammar* comes from `meeting`/`lesson`), `diagrams` (bool),
   `extract_concepts` (bool), `target_subdir` (string); `summarize: {$ref:'#/$defs/Summarize'}`
   on `SyncConfig.properties`. Unknown key / bad enum → `INVALID_SYNC_CONFIG` (exit 6), no echo.
3. **B15 (R-11/R-12)** — loader: parse `summarize`, deep-merge per-folder deepest-wins (mirror the
   `resummarize` cascade), default-resolve when absent (`profile` from detected kind, `diagrams`
   false, `extract_concepts` true, `target_subdir` ""). Expose the resolved block to `scan` so
   P2's `entry.delegate` reads it.
4. **B16 [DOCS]** — update SKILLs (lesson kind, pyramid grammar, flags, office/vtt acquire,
   delegation, `summarize:` block), workflows, and the ARCHITECTURE §1 Sync Dispatcher component
   line ("batch driver delegating to wiki-import"). Remove stale "inline summarise" claims.

## Test Cases
- **TC-UNIT-01 (R-10)** `_accept`: a valid `summarize:` loads; `_reject_unknown_key` + `_bad_profile`
  → exit 6, message does not echo the value.
- **TC-UNIT-02 (R-11)** `_deepmerge`: a `<folder>/.wiki/sync.yaml` setting only `diagrams: true`
  inherits the root `profile`.
- **TC-UNIT-03 (R-12)** `_default_backcompat`: no `summarize:` → resolved `concepts` ON, `diagrams`
  off, `profile` from detected kind.

## Verification
`pytest tests/test_sync_config_summarize.py tests/test_*sync_config* -v` green.
`mypy --strict scripts/` clean. Loader security tests (256 KiB cap, alias refusal) still pass on
configs carrying `summarize:`. End-to-end: a `samples/` PARA zone with
`summarize:{profile:meeting,diagrams:true,extract_concepts:false}` → two pyramid notes, no concepts.

## Acceptance
- [ ] schema accept/reject + deep-merge + default-backcompat tests green.
- [ ] loader hardening preserved; zero-DDL (`user_version` 5).
- [ ] all SKILL/workflow/ARCHITECTURE docs reflect the converged model (no stale claims).
