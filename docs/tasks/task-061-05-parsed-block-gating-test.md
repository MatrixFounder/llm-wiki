# Task 061-05 — [RED GATE] ADD the parsed-block gating test (xfail-strict, proven RED)

RTM: **R-061-5**. Depends on: nothing. Blocks: `061-07` (the fix that turns it GREEN).

## Goal

Land a test that **FAILS before R-061-4 and passes after** — a *real* gate, not a vacuous one.
It is landed **first**, marked `@pytest.mark.xfail(strict=True)`, so:

- the suite stays **green** at this commit (an expected failure is not a failure), **and**
- the gate is **mechanically proven RED** (a strict xfail **errors the suite** if it passes) —
  which is exactly the evidence R-061-5 asks for, recorded in CI instead of in a claim.

`061-07` deletes the marker. If the marker's removal does not flip it to GREEN, the fix is wrong.

## Context (read first)

- `scripts/wiki_skills/wiki_config/_provenance.py:306-334` — the cascading-block fold. The bug:
  `effective_block = _to_jsonable(typed)` renders **only the frozen dataclass's declared
  fields**, so a key present in the merged RAW dict but unknown to `SummarizeConfig` /
  `ResummarizeConfig` **vanishes from `effective`** — while `_assign_origins` (line 314, over the
  RAW block) still records a `provenance` pointer for it. Result: a pointer with no value.
- `scripts/wiki_skills/wiki_config/__init__.py:129-179` — `_cmd_show` (builds `effective` +
  `provenance` from `FolderProvenance`; **bypasses `build_ui_model`**).
- `scripts/wiki_skills/wiki_config/_report.py:100-124` — `build_report_model` flattens
  `prov.effective` into rows ⇒ **a key missing from `effective` has no report row**. That is why
  R-061-5 says *assert on the RENDERED REPORT*.
- **DO NOT RETARGET** `tests/test_wiki_config_provenance.py:374
  ::test_evolution_new_schema_field_needs_no_code` — it legitimately covers the **raw-passthrough
  `else` branch** (`_provenance.py:326`), i.e. a *future top-level block*, not a new key inside a
  *parsed* block. It must still pass, untouched.

## How to construct the state (both schema paths must be patched — enumerate, don't assume)

The loader is **strict** (`additionalProperties: false`), so a synthetic key must be added to
the **schema doc** the two independent consumers read:

| Consumer | Path constant | Cache to reset |
|---|---|---|
| `_load_validated_raw` (accepts the key) | `scripts.wiki_index.sync_config._SCHEMA_PATH` | `sync_config._VALIDATOR = None` |
| `build_ui_model` (scopes the key) | `scripts.wiki_skills.wiki_config._uimodel.SYNC_SCHEMA_PATH` | `_uimodel._MODEL_CACHE = None` |

Copy `config/sync-config.schema.yaml` into `tmp_path`, inject the synthetic properties, then
`monkeypatch.setattr` **both** path constants + reset **both** caches. (The technique is already
used by `test_build_ui_model_memoizes_until_schema_mtime_changes` — reuse it verbatim.)

## Changes — `tests/test_wiki_config_provenance.py`

```python
@pytest.mark.xfail(strict=True, reason="R-061-4 not landed: the parsed-dataclass path drops "
                                       "schema keys the dataclass does not declare")
@pytest.mark.parametrize("pointer,yaml_body", [
    ("/summarize/future_knob",              "summarize:\n  future_knob: kept\n"),
    ("/resummarize/future_knob",            "resummarize:\n  future_knob: kept\n"),
    ("/resummarize/detect/future_knob",     "resummarize:\n  detect:\n    future_knob: kept\n"),  # NESTED
])
def test_parsed_block_unknown_key_reaches_effective(tmp_path, monkeypatch, pointer, yaml_body):
    ...
    # 1. show envelope:  the pointer resolves to a VALUE in `effective`
    # 2. rendered report: `render_html(build_report_model(...))` contains the pointer
    # 3. INVARIANT: every `provenance` pointer has a corresponding `effective` value
```

Parametrized over `summarize` **AND** `resummarize` (R-061-5) **and** a **nested** pointer —
because "the fix covers the block" is exactly the kind of claim this task exists to distrust: a
shallow `{**raw, **parsed}` overlay would pass the first two cases and fail the third.

Assert on the **rendered report** (`_report.render_html`), not only on `build_ui_model` /
`compute_folder_provenance`.

## Verification

```bash
source .venv/bin/activate
pytest tests/test_wiki_config_provenance.py -q       # 3 xfailed, 0 failed, everything else passed
pytest tests/test_wiki_config_provenance.py -q -rx   # confirm the xfail REASON is the R-061-4 bug,
                                                     # not a typo/import error in the test itself
mypy --strict scripts/
```

> **Trap to avoid:** an xfail that fails for the *wrong reason* (a broken fixture) is a vacuous
> gate — the very disease this task treats. Run with `-rx` and read the captured traceback: it
> must show the **missing pointer**, not a `KeyError`/`SyncConfigError` from the harness.

## Acceptance criteria

- [ ] The new test is **ADDED**; `test_evolution_new_schema_field_needs_no_code` is **untouched
      and still passing**.
- [ ] 3 params, all `xfail(strict=True)`; suite green.
- [ ] The captured xfail traceback proves the failure is the missing `effective` value.
