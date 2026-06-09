# PLAN 025 — adoption-currency-hardening

Stub-First, smallest-blast-radius-first. Each bead is independently green
(full `pytest` + `mypy --strict scripts/`). Maps to `docs/TASK.md` RTM.

## Bead order & rationale

Config-only additive changes first (lowest risk, fastest to verify), then the
installer refactor (shared validator), then the template, then docs.

### B1 — obsidian-personal built-in adequacy (R-025-3, R-025-4) · code, additive
- **Edit** `scripts/wiki_index/layouts/obsidian-personal.yaml`:
  - `type_mapping`: add the common summary family, additive (all → `db_type: summary`,
    distinguishing tag only — zero re-classification): `tutorial-summary {tag: tutorial}`,
    `article-summary {tag: article}`, `book-summary {tag: book}`, `video-summary
    {tag: video}`, `podcast-summary {tag: podcast}`, `course-summary {tag: course}`.
  - `ignore`: add `"**/_raw/**"`, `"**/.staging/**"`.
- **Tests** (`tests/test_layouts_end_to_end.py` or `test_layout_config.py`):
  - RED→GREEN: a note `type: tutorial-summary` under a numbered folder indexes as
    `db_type=summary` (no `UnmappedTypeError`).
  - a `_raw/foo.md` / `.staging/bar.md` under a numbered folder is NOT indexed.
  - Karpathy/dev-project layouts unchanged (byte-identity assertion still green).
- **Verify**: `pytest -k "layout"`, `mypy --strict scripts/`.

### B2 — installer index_db pre-write guard + error contract (R-025-1, R-025-2) · code
> **Gate amendments (arch M-1/M-2/M-3, plan 🔴-1/🟡-1/🟡-2):** validator returns a
> `Path` (not bool); validator is PURE (does not read the schema file) — caller owns
> the read+strip+`expected_vault_id` short-circuit; `INVALID_INDEX_DB` unifies to
> exit **6**/`index_db` at **every** site INCLUDING the `_validate_index_db_rel`
> YAML-injection path, so the existing `test_init_rejects_injecting_index_db` is
> **updated** rc 2→6 (a deliberate error-path contract change, not "stays green").
- **Refactor** `scripts/wiki_index/config_loader.py`: extract value-validation (lines
  ~143-164: NUL / absolute→env-gate / relative symlink+escape) into a pure
  **`validate_index_db_value(val: str, vault_root: Path) -> Path`** that **returns the
  resolved `Path`** (`expanded` for absolute, `cand` for relative) and **raises
  `ConfigValidationError`** on rejection. It assumes `val` is already `.strip()`-ed and
  does NOT read any file. `resolve_index_db_path` keeps lines 132-142 (read + `None`/
  non-string guard + `expected_vault_id` short-circuit + `val = val.strip()`) and ends
  with `return validate_index_db_value(val, vault_root)` → byte-behaviour-identical.
- **Edit** `scripts/wiki_skills/wiki_init.py` `scaffold_new` + `register_existing`: the
  pre-write guard sits **between** the schema-template write (`scaffold_new` L255) and
  `_ensure_index_db` (L266/L356). Order: `_validate_index_db_rel(_idx)` (YAML-injection
  — already rejects edge-whitespace, so `_idx` is clean) → `validate_index_db_value(_idx,
  vault_root)` in a `try/except ConfigValidationError` → on raise, `_emit(INVALID_INDEX_DB,
  field="index_db", exit=6)` WITHOUT writing → only then `_ensure_index_db`. Unify ALL
  **four** `field: "index-db"` sites (2× INVALID_INDEX_DB L263/L353, 2×
  INDEX_DB_ALREADY_DECLARED L267/L357) to `field: "index_db"`. Exit codes:
  INVALID_INDEX_DB → **6** (incl. the injection path); INDEX_DB_ALREADY_DECLARED →
  stays **2** (distinct error, no conflicting contract). Update the module docstring
  exit-code legend (add exit 2: INVALID_VENDOR, INDEX_DB_ALREADY_DECLARED; exit 6:
  INVALID_INDEX_DB).
- **Tests** (`tests/test_cli_local_db_resolution.py`):
  - RED→GREEN: `scaffold-new --index-db /abs/x.db` WITHOUT env → exit 6, `field:
    index_db`, and `WIKI_SCHEMA.md` **byte-unchanged** (the regression the audit said
    was absent).
  - **Same for `register-existing`** (the more dangerous case — mutates a pre-existing
    operator Class-A file): ungated-absolute → exit 6 + schema byte-unchanged.
  - with `WIKI_ALLOW_ABSOLUTE_INDEX_DB=1` → written (both entry points).
  - **Update** `test_init_rejects_injecting_index_db` assertion rc 2→6 (+ `field:
    index_db`).
  - New unit test: `validate_index_db_value` is pure (give it a non-existent
    `vault_root` schema — it still validates the VALUE, proving no file read) and
    returns the expected `Path` per branch.
  - existing relative/symlink/escape + `resolve_index_db_path` tests stay green
    (shared-validator parity — `test_config_loader_index_db.py` is the guard).
- **Verify**: `pytest -k "local_db or index_db or wiki_init or config_loader"`, `mypy --strict`.

### B3 — layout-aware CLAUDE.md agent template (R-025-5) · code + templates
- **Edit** `templates/CLAUDE.md.tmpl`: drop the `rm "$$HOME/.../global.db"` line
  from §4 Rebuild (leave `wiki-init --register-existing` + `wiki-reindex --full`).
- **Add** `templates/CLAUDE.layout.md.tmpl`: a layout-aware agent file for
  `dev-project`/`obsidian-personal` (no Karpathy tiers; documents reindex/upsert in
  place, `.wiki/{layout,sync}.yaml` tuning, lookup priority via `wiki-search`,
  `wiki-sync` for mixed zones; a rebuild = `wiki-reindex --full` resolving the
  declared `index_db`). Uses the same `${vault_id}/${language}/${layout}`
  placeholders.
- **Edit** `scripts/wiki_skills/wiki_init.py` `_write_agent_files` (gate 🟢-1 + arch
  Q-025-3 note): inside the per-vendor loop, when `layout` is non-Karpathy, OVERRIDE
  the resolved `template_name` to `CLAUDE.layout.md.tmpl` for **every selected vendor**
  (so `--vendor gemini --layout dev-project` also gets the layout template, written to
  GEMINI.md). Thread `layout` into `_write_agent_files` (a new param; it is already in
  `placeholders` for the substitution). The new template's `${...}` keys MUST be a
  subset of `{vault_id, language, layout, description}` — else `.substitute` raises
  `KeyError` and the per-vendor `except` silently records `"error"` (no agent file).
- **Tests**: `wiki-init --scaffold-new --layout obsidian-personal` writes a CLAUDE.md
  containing the PARA flow markers and NOT `_sources`/`global.db`; `--layout karpathy`
  writes the (fixed) Karpathy template; `--vendor gemini --layout obsidian-personal`
  resolves to the layout template (no crash, GEMINI.md written, status `"written"` not
  `"error"`); assert template selection per (layout, vendor).
- **Verify**: `pytest -k "wiki_init or agent_files or scaffold"`, `mypy --strict`.

### B4 — operator documentation (R-025-6, R-025-7, R-025-8) · docs only
- `config/sync-config.schema.yaml`: `ProvenanceRef.match` gains a `description`
  (both modes + choose-which rule; basename basenames both sides).
- `config/layout-config.schema.yaml`: top `description` gains the merge-asymmetry
  note (ignore=UNION, type_mapping=MERGE, paths/ref_extraction=REPLACE).
- `docs/manuals/obsidian-llm-wiki_manual.md`: add (a) provenance match-mode note,
  (b) paths=REPLACE callout in the override section, (c) custom-`type:` →
  per-vault `type_mapping` note.
- `workflows/wiki-sync.md`: a short "provenance match mode" note (basename robust
  for id-named transcript corpora).
- `docs/ARCHITECTURE.md`: soften Q-019-10 "orphaned knob" (cross-ref Q-025-4).
- `docs/runbooks/personal-vault-adoption.md`: change the footer follow-ups from
  "candidate TASK 025" to "closed in TASK 025".
- **Verify**: grep checks per RTM; `wiki-lint` on the docs dev-vault clean (the
  schema/manual edits are not indexed pages; ARCHITECTURE/runbook are).

### B5 — gates & close-out
- Full `pytest` + `mypy --strict scripts/` green.
- Karpathy golden-anchor byte-identity re-verified.
- `/vdd-multi` (logic/security/performance) → converge.
- code-review APPROVED.
- Archive `docs/TASK.md`→`docs/tasks/task-025-…md`, `docs/PLAN.md`→`docs/plans/plan-025-…md`;
  update CLAUDE.md narrative + auto-memory.

## Risk notes
- **Back-compat — three enumerated error-path deltas (B2)** (plan-reviewer): all on
  error paths, none on a success/valid-input path. (1) `INVALID_INDEX_DB` exit 2→6 for
  the malformed/injection cases in `wiki_init`; (2) the **same** 2→6 for the
  `_validate_index_db_rel` injection path (`test_init_rejects_injecting_index_db`
  updated); (3) JSON-envelope `field` rename `index-db`→`index_db` on BOTH
  `INVALID_INDEX_DB` and `INDEX_DB_ALREADY_DECLARED`. Disclosed here so `/vdd-multi`
  logic + code-review don't read them as undisclosed regressions. No success-path or
  page type/slug/project change.
- **Shared-validator parity (B2)**: `resolve_index_db_path` must remain
  byte-behaviour-identical after delegating — it keeps read+strip+`expected_vault_id`
  (132-142) and delegates only 143-164; the validator is pure (no file read) and
  returns the resolved `Path`. The existing security tests (HIGH-S1/S2, symlink, escape,
  NUL) in `test_config_loader_index_db.py` are the guard.
- **Template scope (B3)**: the layout switch applies to **every selected vendor** (the
  resolved template is overridden in the per-vendor loop); the new template's
  placeholders are a subset of the existing four (no `KeyError`→silent-error).
- **Karpathy byte-identity**: B1 per-bead canary + B5 `test_karpathy_byte_identity.py`.
- **PW-Q drift (B4)**: the ARCHITECTURE Q-019-10 softening is prose, not the
  KNOWN_ISSUES ledger — must not trip the auto-rendered-ledger drift guard.
