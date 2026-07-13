# TASK 063-00 — `extract_decisions` schema block + typed dataclasses

**Phase**: 0 (config surface) · **RTM**: R-063-3′ · **Type**: config + code · **Effort**: 2–3h
**Depends on**: — · **Unblocks**: 063-01, 063-03

## Goal

Add the cascading `extract_decisions: {enabled, dirs}` block to **`config/sync-config.schema.yaml`**
and its typed mirror to `scripts/wiki_index/sync_config.py`.

**Why the schema and not the layout:** `wiki-config`'s `set`/`unset` **and its web editor** render
ONLY from `SYNC_SCHEMA_PATH = config/sync-config.schema.yaml` (`_uimodel.py:24`, `_server.py:191`).
It *validates* all three config systems but *edits* only `sync.yaml`. A `typed_dirs` key in
`layouts/*.yaml` would **never appear in the editor at all** — the v5 architectural defect. Putting
the block here is what makes the folder names operator-editable **with zero interface code**.

## Context — files

- **Edit** `config/sync-config.schema.yaml` — new `$defs/ExtractDecisions` + `$defs/ExtractDecisionsDirs`;
  new `SyncConfig.properties.extract_decisions` with `x-wiki-scope: cascading` (sibling of `summarize:`).
- **Edit** `scripts/wiki_index/sync_config.py` — `ExtractDecisionsDirs` + `ExtractDecisionsConfig`
  frozen dataclasses; `SyncConfig.extract_decisions: ExtractDecisionsConfig | None`;
  `_parse_extract_decisions()`; `load_extract_decisions_raw()` (mirrors `load_summarize_raw`, line 293).
- **Edit** `scripts/wiki_skills/wiki_config/_provenance.py` — add `"extract_decisions"` to `_PARSED_BLOCKS`
  (line 279) with `default_when_absent=False` (absent ⇒ `None` ⇒ the rail is never auto-dispatched).
- **Edit** `tests/test_wiki_config_provenance.py:612` — the gate
  `assert set(_PARSED_BLOCKS) == cascading == {"resummarize", "summarize"}` becomes
  `{"resummarize", "summarize", "extract_decisions"}`. **This edit is the proof the surface census is
  live**: it fails loudly the moment a cascading block is added without registering it.
- **Read (precedent)** `Summarize` in the schema + `SummarizeConfig`/`_parse_summarize`
  (`sync_config.py:134-145, 270-299`).

## Shape

```yaml
# config/sync-config.schema.yaml — $defs
ExtractDecisionsDirs:
  type: object
  additionalProperties: false      # STRICT: a misspelled class is exit 6, not a silent no-op
  properties:
    decision:    {type: string, x-wiki-format: path, description: '…'}
    requirement: {type: string, x-wiki-format: path, description: '…'}
    risk:        {type: string, x-wiki-format: path, description: '…'}

ExtractDecisions:
  type: object
  additionalProperties: false
  properties:
    enabled: {type: boolean, description: 'Auto-dispatch the wiki-extract-decisions rail …'}
    dirs:    {$ref: '#/$defs/ExtractDecisionsDirs'}

# SyncConfig.properties
extract_decisions:
  $ref: '#/$defs/ExtractDecisions'
  x-wiki-scope: cascading
```

The **v1 roster is exactly `{decision, requirement, risk}`** (spec §3) — three explicit properties,
not a free `additionalProperties` map. Two reasons, both load-bearing:
(1) `test_sync_schema_and_dataclasses_can_never_drift` walks the `$defs` closure and requires
name-set equality with the dataclass tree — a free-form map cannot satisfy it;
(2) a misspelled class name must be **exit 6**, never a silently-ignored key.

## Steps

1. Write the two `$defs` + the `SyncConfig` property (schema order: after `summarize`).
2. Mirror as frozen dataclasses. `ExtractDecisionsDirs` defaults: `decision="decisions"`,
   `requirement="requirements"`, `risk="risks"` — the cybos folder names, so a vault that just sets
   `enabled: true` works with no `dirs:` at all. `ExtractDecisionsConfig.enabled: bool = False`
   (**off by default** — R-063-3′(c)).
3. `_parse_extract_decisions`: reuse `_is_safe_subdir` (line 258) on **every** `dirs.*` value → an
   unsafe path raises `SyncConfigError("INVALID_SYNC_CONFIG", …, reason="UNSAFE_SUBDIR")`, **value
   never echoed** (CWE-209). Normalise (strip, drop trailing `/`) like `target_subdir`.
4. Wire into `load_sync_config` (line 245) + `_PARSED_BLOCKS`.
5. Update the `test_parsed_block_table_matches_the_schema_cascading_set` equality set.

## Tests (RED first)

`tests/test_sync_config_extract_decisions.py` (new):
- `test_absent_block_is_none` — no `extract_decisions:` ⇒ `SyncConfig.extract_decisions is None`
  (⇒ never auto-dispatched; back-compat byte-identity).
- `test_defaults_are_the_cybos_names` — `extract_decisions: {enabled: true}` ⇒ dirs
  `decisions`/`requirements`/`risks`.
- `test_unknown_class_key_is_exit_6` — `dirs: {incident: x}` ⇒ `SyncConfigError` (`additionalProperties:
  false`). **MUT:** loosen to `additionalProperties: true` ⇒ this test goes RED.
- `test_unsafe_dir_is_refused_and_value_not_echoed` — `dirs.decision: "../../etc"` ⇒ raises;
  `"../../etc" not in str(exc)`.
- Extend `tests/test_wiki_config_provenance.py::test_sync_schema_and_dataclasses_can_never_drift`
  — **already** walks the whole closure; it must stay green (it is the drift gate for this bead).

## Exit criteria

- [ ] `pytest tests/` ≥ 2477 passed, 0 failed. `mypy --strict scripts/` clean.
- [ ] **GREP-THE-SURFACES (the operator's requirement, and it is a denominator claim):** the three
      `dirs.*` keys must appear in **every** interface surface with **zero interface-code changes**.
      Enumerate the surfaces from the code, do not assert "all":
      ```bash
      # the render sinks that consume build_ui_model() — this IS the population
      grep -rln "build_ui_model" scripts/wiki_skills/wiki_config/
      #   → _server.py (/api/schema) · _report.py (HTML) · _report_md.py (show) · _lint.py · _provenance.py
      # the gate: this bead's diff must touch NONE of them except _provenance.py's _PARSED_BLOCKS table
      git diff --name-only -- scripts/wiki_skills/wiki_config/
      #   → must list ONLY _provenance.py
      ```
- [ ] `python3 -c "from scripts.wiki_skills.wiki_config._uimodel import build_ui_model as b; \
      print([p for p in b() if p.startswith('/extract_decisions')])"` prints the 4 new pointers
      (`/extract_decisions`, `/extract_decisions/enabled`, `/extract_decisions/dirs`,
      `…/dirs/{decision,requirement,risk}` = 6 total). **Assert the count, not "they're there".**
- [ ] **MUT:** revert the `x-wiki-scope: cascading` annotation ⇒
      `test_parsed_block_table_matches_the_schema_cascading_set` goes RED.

## Rollback

Revert the schema `$defs` + the dataclass; `_PARSED_BLOCKS` and the equality set revert in lockstep.
No DB, no vault files touched.
