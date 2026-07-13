# TASK 063-00 — `extract_decisions` schema block + typed dataclasses

**Phase**: 0 (config surface) · **RTM**: R-063-3′ · **Type**: config + code · **Effort**: 2–3h
**Depends on**: — · **Unblocks**: 063-01, 063-03
**Revision**: v2 — plan-review **M-6, M-7, m-12** applied (PLAN §8).

## Goal

Add the cascading `extract_decisions: {enabled, dirs}` block to **`config/sync-config.schema.yaml`**
and its typed mirror to `scripts/wiki_index/sync_config.py`.

**Why the schema and not the layout:** `wiki-config`'s `set`/`unset` **and its web editor** render
ONLY from `SYNC_SCHEMA_PATH = config/sync-config.schema.yaml` (`_uimodel.py:24`, `_server.py:191`).
It *validates* all three config systems but *edits* only `sync.yaml`. A `typed_dirs` key in
`layouts/*.yaml` would **never appear in the editor at all** — the v5 architectural defect. Putting
the block here is what makes the folder names operator-editable **with zero interface code**.

## Context — files

- **Edit** `config/sync-config.schema.yaml` — `$defs/ExtractDecisions` + `$defs/ExtractDecisionsDirs`;
  `SyncConfig.properties.extract_decisions` with `x-wiki-scope: cascading` (sibling of `summarize:`).
- **Edit** `scripts/wiki_index/sync_config.py` — `ExtractDecisionsDirs` + `ExtractDecisionsConfig`
  frozen dataclasses; `SyncConfig.extract_decisions`; `_parse_extract_decisions()`;
  `load_extract_decisions_raw()` (mirrors `load_summarize_raw`, `:293`).
- **Edit** `scripts/wiki_skills/wiki_config/_provenance.py:279` — `_PARSED_BLOCKS` gains
  `"extract_decisions"` with `default_when_absent=False` (absent ⇒ `None` ⇒ never auto-dispatched).
- **Edit — ⚠️ TWO tests pin the cascading denominator, not one** (plan-review **M-7**). Do not name
  them from memory; **grep the pins**:
  ```bash
  grep -rn "SCOPE_CASCADING\|_PARSED_BLOCKS" tests/ | grep "=="
  #  → tests/test_wiki_config_provenance.py:426   test_ui_model_matches_shipped_schema
  #        assert set(top_level_keys(model, SCOPE_CASCADING)) == {"resummarize", "summarize"}
  #  → tests/test_wiki_config_provenance.py:612   test_parsed_block_table_matches_the_schema_cascading_set
  #        assert set(_PARSED_BLOCKS) == cascading == {"resummarize", "summarize"}
  ```
  **Both** become `{"resummarize", "summarize", "extract_decisions"}`. v1 named only `:612` — so
  "green at every boundary" failed **literally as written**. These two are not an obstacle: they are
  **the surface census doing its job**, and updating them deliberately is the whole point of having it.

## Shape

```yaml
# config/sync-config.schema.yaml — $defs
ExtractDecisionsDirs:
  type: object
  additionalProperties: false      # STRICT: a misspelled class is exit 6, not a silent no-op
  properties:
    decision:    {type: string, x-wiki-format: path, description: 'Folder for extracted `decision` pages…'}
    requirement: {type: string, x-wiki-format: path, description: '…'}
    risk:        {type: string, x-wiki-format: path, description: '…'}

ExtractDecisions:
  type: object
  additionalProperties: false
  properties:
    enabled:
      type: boolean
      description: >
        Auto-dispatch the `wiki-extract-decisions` rail after a summary is filed (TASK 063).
        wiki-sync / wiki-import emit a DISPATCH MARKER; the orchestrator runs the rail — the
        CLIs never call an LLM (Decision-17). ⚠️ REQUIRES that rail: until it ships this key is
        INERT — the marker has no consumer.          # ← m-12: the config chain ships FIRST, so
                                                     #   say so, or `enabled: true` over-promises
    dirs: {$ref: '#/$defs/ExtractDecisionsDirs'}

# SyncConfig.properties  (schema order: after `summarize`)
extract_decisions:
  $ref: '#/$defs/ExtractDecisions'
  x-wiki-scope: cascading
```

The **v1 roster is exactly `{decision, requirement, risk}`** (spec §3) — three explicit properties,
never a free `additionalProperties` map. Two load-bearing reasons: (1)
`test_sync_schema_and_dataclasses_can_never_drift` walks the `$defs` closure and requires name-set
equality with the dataclass tree — a free-form map cannot satisfy it; (2) a misspelled class must be
**exit 6**, never a silently-ignored key.

## Steps

1. The two `$defs` + the `SyncConfig` property.
2. Frozen dataclasses. `ExtractDecisionsDirs` defaults `decisions`/`requirements`/`risks` (the cybos
   names — so a vault that sets only `enabled: true` works with no `dirs:` at all).
   `ExtractDecisionsConfig.enabled: bool = False` — **off by default** (R-063-3′(c)).
3. `_parse_extract_decisions`: `_is_safe_subdir` (`:258`) on **every** `dirs.*` value → unsafe raises
   `SyncConfigError(..., reason="UNSAFE_SUBDIR")`, **value never echoed** (CWE-209). Normalise
   (strip, drop trailing `/`) exactly as `target_subdir` does.
4. Wire into `load_sync_config` (`:245`) + `_PARSED_BLOCKS`.
5. Update **both** denominator pins.

## Tests (RED first) — `tests/test_sync_config_extract_decisions.py` (new)

- `test_absent_block_is_none` — no block ⇒ `extract_decisions is None` (never auto-dispatched;
  back-compat byte-identity).
- `test_defaults_are_the_cybos_names` — `{enabled: true}` ⇒ `decisions`/`requirements`/`risks`.
- `test_unknown_class_key_is_exit_6` — `dirs: {incident: x}` ⇒ `SyncConfigError`.
  **MUT:** `additionalProperties: true` ⇒ RED.
- `test_unsafe_dir_is_refused_and_value_not_echoed` — `dirs.decision: "../../etc"` ⇒ raises, and
  `"../../etc" not in str(exc)`.

## ★ The RENDERED-surface test (plan-review **M-6** — the operator's actual requirement)

v1 asserted `build_ui_model()` + a `git diff` proxy — i.e. **the UI MODEL**. That is exactly the
TASK-061 bug shape: `FieldSpec.description` lived in the model and rendered in `serve` **only**. And
the existing generic guards do **not** cover this case:

| existing guard | why it does NOT cover us |
|---|---|
| `test_evolution_new_schema_field_needs_no_code` (`:403`) | asserts on the **model**, not on any rendered surface |
| `test_description_reaches_every_surface_from_the_schema_alone` (`:665`) | injects a synthetic key into an **existing** parsed block — `extract_decisions` is a **NEW top-level PARSED cascading block** (`_PARSED_BLOCKS` + frozen dataclass + `_overlay_parsed`), a shape it never exercises |

So assert the **rendered output** of all three surfaces —
`tests/test_wiki_config_extract_decisions_surfaces.py` (new):

- `test_show_envelope_renders_the_dirs` — `wiki-config show`'s JSON envelope contains
  `/extract_decisions/dirs/decision` **with its description**.
- `test_html_report_renders_the_dirs` — `render_html(build_report_model(...))` **output string**
  contains the row. Assert on the HTML, never on the model that feeds it.
- `test_api_schema_renders_the_dirs` — `/api/schema` returns the 6 new pointers.
- **MUT (all three):** revert the schema block ⇒ **all three RED**. A surface that stays green is a
  surface that is **not** reading the schema — and the "zero interface code" claim is false for it.

## Exit criteria

- [ ] `pytest tests/` ≥ 2477 passed, 0 failed. `mypy --strict scripts/` clean.
- [ ] **GREP-THE-SURFACES — "the keys appear everywhere with zero interface code" is a denominator
      claim.** Enumerate the render sinks **from the code**, then assert the diff touched none of them:
      ```bash
      grep -rln "build_ui_model" scripts/wiki_skills/wiki_config/
      #   → _server.py · _report.py · _report_md.py · _lint.py · _provenance.py   (the population)
      git diff --name-only -- scripts/wiki_skills/wiki_config/
      #   → MUST list ONLY _provenance.py (the _PARSED_BLOCKS row — a data table, not interface code)
      ```
      The `git diff` is the **proxy**; the three rendered-surface tests are the **measurement**. v1
      shipped only the proxy — which is how a model-level pass can coexist with an unrendered field.
- [ ] `build_ui_model()` yields exactly **6** new pointers. **Assert the count**, not "they're there".
- [ ] **MUT:** drop `x-wiki-scope: cascading` ⇒ **both** pins (`:426`, `:612`) go RED.

## Rollback

Revert the `$defs` + dataclasses; both pins and `_PARSED_BLOCKS` revert in lockstep. No DB, no vault
files touched.
