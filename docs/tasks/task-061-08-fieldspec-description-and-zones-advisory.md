# Task 061-08 — [LOGIC] Render `FieldSpec.description` in `show` + `report`; `zones` = advisory

RTM: **R-061-6** (Q-061-3 **Option A′ — generalize, don't badge**). Depends on: `061-07`.

## Goal

`zones:` is **advisory, not enforced** — parsed and linted, but **never read by
`iter_sync_candidates()`**; only `exclude:` scopes the walk. Make that fact **data**, not code:
render `FieldSpec.description` in the surfaces that don't render it today, so the `zones`
advisory text — **and every future field's description** — appears with **zero further
interface code**. This *strengthens* the TASK 058 schema-driven invariant instead of eroding it.

## Context — the surface census (this is why plain Option A was FALSE)

`FieldSpec.description` (`_uimodel.py:42,93`) reaches an operator through **`serve` ONLY**:

| Surface | Python consumer | Render sink | Status |
|---|---|---|---|
| `serve` (web editor) | `_server.py:195` (`"description": s.description` in the schema payload) | **`_app_html.py:536-537`** — `spec.description` → the hint `<p class="hint">` | ✅ already renders |
| `show` (CLI envelope + md sidecar) | — (`_cmd_show` **bypasses `build_ui_model` entirely**) | — | ❌ **add** |
| `report` (self-contained HTML) | — (`_report.py` has **0** `FieldSpec.description` reads) | `_row_html` | ❌ **add** |
| `tree` (vault-wide override map) | `_report.py::build_report_model` (holds `ui_model`) | per-folder row tables | ⛔ **deliberate exclusion** — `tree` answers *"where is this key overridden?"*, not *"what does it mean"*; a description column across N folders × M keys would drown the map. Named here so **"renders everywhere"** stays an honest claim with a stated boundary, not an unexamined one. |

> **Beware the false grep.** `grep -rn description scripts/wiki_skills/wiki_config/` also hits
> `_doctor.py:49` (`FixPlan.description`), `_templates.py:61` (`Template.description`) and
> `_app_html.py:788/834` — **different dataclasses**. The set to enumerate is *consumers of
> **`FieldSpec`**`.description`*, not of the word "description".

## Verified fact — report-row pointer keying (MAJOR-2; **read, don't assume**)

`_report.py:110-111` builds rows via `_report_md._flatten(block, f"/{key}", rows)`.
**`_flatten` (`_report_md.py:26-31`) recurses on `dict` ONLY — a list is a LEAF.** Probed:

```
_flatten({"zones": ["Lessons/**"], "resummarize": None}, "", rows)
  → [('/zones', ['Lessons/**']), ('/resummarize', None)]
build_ui_model():  '/zones' present (kind=array, items=string)   ·   '/zones/0' ABSENT
```

So a list key's report row is `/zones`, **which has a FieldSpec** — a naive `pointer in ui_model`
lookup happens to work today. **Do not rely on that.** Implement the lookup as
**nearest-ancestor resolution**, mirroring `resolve_origin` (`_provenance.py:83-95`, already used
at `_report.py:117` for exactly this class of problem — a leaf pointer with no entry of its own).
Re-run the probe at implementation time and paste the output into the bead's Notes.

## Changes

### 1. `config/sync-config.schema.yaml` — the data (line ~70)

```yaml
      zones:
        ...
        description: >
          ADVISORY — not enforced. Vault-root-relative globs that DOCUMENT the sync zones;
          nothing reads them at runtime (`wiki-sync scan <zone>` takes an explicit zone
          argument, and the walk is scoped by `exclude:` alone).
```

Instance validation stays byte-identical (`description` is an annotation).

### 2. `scripts/wiki_skills/wiki_config/__init__.py::_cmd_show` — surface 2

Additive envelope key, fully generic (no key name in code):

```python
model = build_ui_model()
envelope["descriptions"] = {ptr: s.description for ptr, s in model.items() if s.description}
```

Check `_report_md.render_show_report` (the `--report` md sidecar `_cmd_show` also emits): if it
renders a key table, feed the description there too — and **say which way you went** in the Notes.

### 3. `scripts/wiki_skills/wiki_config/_report.py` — surface 3

`build_report_model` already holds `ui_model` (line 100). Add a **nearest-ancestor** resolver
beside the existing `resolve_origin` call (line 117):

```python
def _resolve_description(model: dict[str, FieldSpec], pointer: str) -> str:
    """Nearest-ancestor lookup — the `resolve_origin` precedent. A row pointer with no
    FieldSpec of its own (an array element under a future `_flatten`, a raw-only key under a
    parsed block) inherits its nearest declared ancestor's description instead of silently
    rendering '' — a silent empty string is exactly the failure mode this task exists to kill."""
```

Attach it to each row (`section.rows[].description`) and render it in `_row_html` (line 266) as
an **escaped** hint (`_esc` — descriptions are repo-owned, but the XSS discipline is not negotiable).

### 4. `scripts/wiki_skills/wiki_config/_lint.py::_check_globs` (line 372) — re-word

`ZONE_GLOB_NO_MATCH` shares the message `f"{key}[{i}] matches nothing on disk"` with
`EXCLUDE_GLOB_NO_MATCH`, which **implies enforcement**. Give the loop a per-key message:

- `zones[i]` → *"zones[i] matches nothing on disk — advisory only: zones are never read by the
  sync walk (`wiki-sync scan <zone>` takes an explicit zone; only `exclude:` scopes the walk)"*
- `exclude[i]` → unchanged.

Keep the **code** `ZONE_GLOB_NO_MATCH`, its severity (`SEV_INFO`) and tier (`TIER_MANUAL`) —
`tests/test_wiki_config_validate.py:207,232` assert on code/pointer, not on the message. Touch
`_findings.py` **only if** a message/hint template lives there (check first — it may not).

### 5. `docs/manuals/obsidian-llm-wiki_manual.md:539` (+ RU mirror `:548`)

Mark it: *"`zones` (**advisory** — documents the zones; not read by the walk), `exclude` (**the**
walk scope), `extensions`, `tag_namespace`, the `resummarize` gate"*. EN + RU in lockstep (TASK 059).

## Test cases — `tests/test_wiki_config_cli.py` (+ provenance)

1. **TC-08-1 (all three surfaces, from ONE injected schema field — the GENERIC claim)** — inject
   a synthetic field with `description: "synthetic hint"` (the `061-05` double-monkeypatch
   recipe) and assert the text appears in **(a)** the `show` envelope (`descriptions`),
   **(b)** the rendered HTML report, **(c)** the `serve` schema payload. One test, three
   surfaces, zero interface-code changes ⇒ the R-058-10 evolution invariant *strengthened*.
2. **TC-08-2 (the SHIPPED schema's `zones` row, in the RENDERED HTML)** — not a synthetic field:
   build the report for a real vault whose root `sync.yaml` sets `zones:` and assert the rendered
   HTML **for the `/zones` row** contains "ADVISORY". This is the assertion that would have
   silently passed on `""` under a naive lookup — it must fail loudly if the description does not
   resolve.
3. **TC-08-3 (nearest-ancestor)** — a row pointer with no FieldSpec of its own resolves to its
   ancestor's description. If `_flatten`'s list-as-leaf behavior means no such row exists today,
   assert the **resolver's unit behavior** directly, so the guard survives a future `_flatten`
   change.
4. **TC-08-4 (lint re-word)** — a non-matching `zones` glob still yields code
   `ZONE_GLOB_NO_MATCH` at `/zones/0` (existing tests unchanged) **and** its message contains
   "advisory" and no enforcement claim.
5. **TC-08-5 (HTML escaping)** — a description containing `<script>` renders escaped.

## Verification

```bash
source .venv/bin/activate
pytest tests/test_wiki_config_cli.py tests/test_wiki_config_validate.py tests/test_wiki_config_provenance.py -q
mypy --strict scripts/
# census, re-run at implementation time (exit criterion — paste output into the commit):
grep -rn "FieldSpec" scripts/wiki_skills/wiki_config/*.py
grep -rn "\.description" scripts/wiki_skills/wiki_config/*.py   # then CLASSIFY each hit by owning dataclass
python3 -c "from scripts.wiki_skills.wiki_config._report_md import _flatten; r=[]; _flatten({'zones':['x']}, '', r); print(r)"
```

## Acceptance criteria

- [ ] The **`FieldSpec.description` consumer set** is enumerated by grep, each hit classified by
      owning dataclass, and pasted into the commit message: Python consumers
      `{_server.py, _report.py, __init__.py}`; `serve`'s render sink = `_app_html.py:536`;
      **`tree` named as a deliberate exclusion**.
- [ ] `_flatten`'s leaf semantics re-probed and recorded; the description lookup is
      **nearest-ancestor**, not a bare `in` test.
- [ ] A new schema field's description renders in all three surfaces with **zero** code change
      (TC-08-1, generic — not `zones`-specific); the shipped `zones` text is asserted in the
      **rendered HTML** (TC-08-2).
- [ ] `ZONE_GLOB_NO_MATCH` no longer implies enforcement; code/severity/tier unchanged.
- [ ] Manual 539 + RU mirror corrected. Option B (`x-wiki-advisory` + badge) stays **deferred**.
