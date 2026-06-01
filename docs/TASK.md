# TASK 016 — Split `wiki_extract_concepts.py` into a maintainable submodule package

### 0. Meta Information
- **Task ID:** 016
- **Slug:** `split-extract-concepts-module`
- **Mode:** VDD (full pipeline)
- **Branch:** `task-016-split-extract-concepts`
- **Type:** Pure refactor (zero behaviour change, zero DDL, zero public-contract change)
- **Predecessor:** TASK 015 `perf-hardening-extract-concepts` (shipped + committed
  `7fce4b3`; grew this file to **2174 lines** with the batch surfaces + the F1 fix).

---

### 1. General Description

`scripts/wiki_skills/wiki_extract_concepts.py` is **2174 lines** — by far the largest
module in the tree — and now mixes ~38 functions across seven distinct concerns
(validation/sanitization, source IO, DB/entity ops, page writing, the `prepare` command,
the `apply` command, and the argparse/CLI). TASK 015 (batch surfaces + the `_apply_validate`/
`_apply_write` factor + F1) pushed it past the point where a reader can hold it in their
head, and every future change now risks an unrelated regression in the same file.

This task splits it into a **package** `scripts/wiki_skills/wiki_extract_concepts/` with
focused submodules, **strictly preserving behaviour, the public CLI/envelope contracts,
and — the dominant constraint — the test patch-target lock**. It is a mechanical,
green-throughout refactor: no logic changes, no new flags, no schema change.

The **make-or-break constraint** is the **patch-target lock** (PLAN Risk R-2, guarded by
`test_patch_target_lock_at_skill_module` + `test_module_imports_neutral_manifest_consumer`):
tests monkeypatch **eight** symbols at `scripts.wiki_skills.wiki_extract_concepts.<name>`
and require those patches to intercept the call sites. The split must keep that import path
valid and those names rebindable from that namespace, with callers resolving them as facade
globals — otherwise the suite breaks and external callers' patch sites silently no-op.

Patched-symbol set (the lock surface — **8 names**, verified against the tests):
`make_repo`, `load_known_entities`, `validate_manifest`, `index_from_manifest`,
`dispatch_to_indexer`, `_apply_candidates_to_db`, `_try_update_idempotency_state`,
`update_idempotency_state`
(+ `WikiIngestError` is asserted identity-equal to the source module).
Patch-site evidence: `update_idempotency_state` is patched at the facade by
`test_wiki_extract_concepts.py:1868` (C-1 partial-failure) and `:2581` (H-3 DB-lock); its
ONLY caller is `_try_update_idempotency_state`, so that caller must resolve it as a facade
global. `load_known_entities` + `update_idempotency_state` both live in the `_db` leaf yet
MUST be re-imported into the facade and called there as facade globals (the carve-out).

---

### 2. Requirements Traceability Matrix (RTM)

This is a refactor, so every requirement is **MVP** (structural integrity is all-or-nothing).

| ID | Requirement | MVP? | Sub-features |
|----|------------|------|--------------|
| **R-016-1** | Convert the module to a package `wiki_extract_concepts/` | **YES** | (a) `wiki_extract_concepts/__init__.py` is the **facade** — the import path `scripts.wiki_skills.wiki_extract_concepts` stays valid; (b) submodules created under the package; (c) the old single `.py` file is removed (replaced by the package dir); (d) `python -m scripts.wiki_skills.wiki_extract_concepts` still resolves `main()` (a `__main__.py` or `main` re-export) |
| **R-016-2** | **Preserve the patch-target lock** (dominant constraint) | **YES** | (a) all **8** patched names (`make_repo`, `load_known_entities`, `validate_manifest`, `index_from_manifest`, `dispatch_to_indexer`, `_apply_candidates_to_db`, `_try_update_idempotency_state`, `update_idempotency_state`) are bound as **facade (`__init__`) globals**, rebindable via `mock.patch("scripts.wiki_skills.wiki_extract_concepts.<name>")`; (b) every caller of a patched name lives in the facade and resolves it as a **module global of the facade** (so a patch on the facade intercepts the call — the R-2 invariant; specifically `_try_update_idempotency_state` must call `update_idempotency_state` as a facade global, and `dispatch_to_indexer` must call `validate_manifest`/`index_from_manifest` as facade globals); (c) `test_patch_target_lock_at_skill_module` + `test_module_imports_neutral_manifest_consumer` pass **UNMODIFIED**; (d) `WikiIngestError`/`validate_manifest`/`index_from_manifest` remain `is`-identical to `_manifest_consumer`'s |
| **R-016-3** | Preserve public CLI + envelope contracts | **YES** | (a) `prepare`/`apply` subcommands, all flags, all exit codes (0/1/2/4/5/6) unchanged; (b) every success + error envelope **byte-identical** (incl. batch shapes, `DB_WRITE_FAILED`, `known_concepts` hoist); (c) the CWE-117/209 canary `test_apply_error_envelopes_never_echo_content` passes unmodified |
| **R-016-4** | Extract pure leaf clusters into submodules | **YES** | (a) `_validation.py` (validators, sanitizers, candidate-schema, `classify_candidates`, `_preflight_sanitize`, `_parse_source_span`, regex/const allowlists); (b) `_sourcing.py` (`_read_file_bounded`, `_FileTooLargeError`, `_resolve_source_inside_sources`, `_all_concepts_dirs`, `_derive_source_project`, `_load_candidates`, `_path_is_absolute`, byte caps); (c) `_db.py` (`load_known_entities`, `_lookup_entity_row`, `upsert_extracted_entity`, `upsert_entity_refs`, `check_idempotency`, `update_idempotency_state`, `build_manifest`); (d) `_pages.py` (`write_concept_page`, `_format_source_quote_block`, name allowlist); (e) `_errors.py` (`ExtractionParseError`, `_envelope_from_parse_error`) |
| **R-016-5** | Keep the monkeypatch-coupled orchestration layer in the facade | **YES** | (a) **Facade-shape (A) is a HARD constraint** (Open Question 1 resolved → A): `dispatch_to_indexer`, `prepare`/`_load_known_and_drift`/`_recon_single`/`_batch_prepare`, `apply`/`_apply_validate`/`_apply_write`/`_apply_candidates_to_db`/`_batch_apply`, `_build_parser_v3`, `main`, `_try_update_idempotency_state` are DEFINED in `__init__.py` itself (NOT a re-exported `_runtime` — the `_runtime` option is rejected: it reintroduces the facade-global resolution risk the lock forbids); (b) leaf submodules have **no** monkeypatch coupling, with the explicit **carve-out**: `load_known_entities` AND `update_idempotency_state` live in `_db.py` but are re-imported into the facade and called there as facade globals (so `mock.patch(wec.load_known_entities)` / `mock.patch(wec.update_idempotency_state)` intercept the facade callers) |
| **R-016-6** | No collateral churn in other modules | **YES** | (a) `wiki_enrich.py`, `_manifest_consumer.py`, `layout_config.py` continue to import/work unchanged; (b) the `skills/wiki-extract-concepts/SKILL.md` `<!-- Sync with …argparse… -->` pointer (line 1) is repointed to wherever `_build_parser_v3` lands (facade `__init__.py` per R-016-5a); `workflows/wiki-extract-concepts.md` unaffected; (c) no import added to any module that didn't already depend on extract-concepts |
| **R-016-7** | Mandated test import-path moves (the ONLY permitted non-guard test edits) | **YES** | (a) `tests/test_extract_concepts_candidate_regression.py:18` sets `_SRC = …/wiki_extract_concepts.py` and `:23` does `_SRC.read_text()` to grep-pin `write_concept_page`'s `"is_candidate": True` + `"tags": [...]` strings → when the `.py` becomes a package dir this raises `IsADirectoryError`; since `write_concept_page` moves to `_pages.py`, `_SRC` MUST be repointed to `…/wiki_extract_concepts/_pages.py` (a pure path move — the pinned-string assertions stay identical); (b) any other test importing a relocated PRIVATE symbol from the facade must still resolve it — notably `tests/test_slug_strategy.py:73` does `from …wiki_extract_concepts import _derive_source_project` (moves to `_sourcing.py` but MUST remain importable from the facade — covered by R-016-2(a)/AC-016-1, so NO test edit needed there); (c) these are import-path relocations, **never** contract relaxations |
| **R-016-NF1** | Zero behaviour change | **YES** | Karpathy byte-identity + all golden-snapshot tests pass; no envelope, exit-code, file-write, or DB-state difference |
| **R-016-NF2** | Full test suite green, **no test edits to the lock/contract guards** | **YES** | `pytest tests/` ≥ 879 (+4 skip) green; the patch-target-lock tests + envelope canary pass **unmodified**; any test edit must be justified as a pure import-path move, never a contract relaxation |
| **R-016-NF3** | `mypy --strict scripts/` clean | **YES** | all 63+ files (now incl. the new submodules) pass mypy `--strict`; no new `type: ignore` beyond those carried verbatim from the original file |
| **R-016-NF4** | Each submodule readable in isolation | **YES** | target ≤ ~450 lines per submodule; facade `__init__` substantially smaller than 2174 (target ≤ ~900); no submodule re-introduces a god-file |

---

### 3. Problem Description

#### 3.1 The god-module (2174 lines, 7 concerns)
The function inventory clusters cleanly:
- **validation/sanitization**: `_validate_source_hash`, `_validate_orchestrator_id`,
  `_path_is_absolute`, `_validate_candidates_schema`, `_sanitize_name`,
  `_sanitize_definition`, `_preflight_sanitize`, `classify_candidates`,
  `_format_source_quote_block`, `_parse_source_span`, the regex/const allowlists.
- **source IO**: `_read_file_bounded`, `_FileTooLargeError`,
  `_resolve_source_inside_sources`, `_all_concepts_dirs`, `_derive_source_project`,
  `_load_candidates`, byte caps.
- **DB/entity ops**: `load_known_entities`, `_lookup_entity_row`,
  `upsert_extracted_entity`, `upsert_entity_refs`, `check_idempotency`,
  `update_idempotency_state`, `build_manifest`.
- **page writing**: `write_concept_page`, `_format_source_quote_block`.
- **`prepare` command**: `prepare`, `_load_known_and_drift`, `_recon_single`,
  `_batch_prepare`.
- **`apply` command**: `apply`, `_apply_validate`, `_apply_write`,
  `_apply_candidates_to_db`, `_batch_apply`, `dispatch_to_indexer`,
  `_envelope_from_parse_error`.
- **CLI**: `_build_parser_v3`, `main`.

#### 3.2 The patch-target lock (the hard part)
`test_patch_target_lock_at_skill_module` proves that
`mock.patch("scripts.wiki_skills.wiki_extract_concepts.index_from_manifest")` intercepts
the call **inside** `dispatch_to_indexer`. This only holds because `dispatch_to_indexer`
resolves `index_from_manifest` as a **module global** of `wiki_extract_concepts`. A naive
split (move `dispatch_to_indexer` to a submodule that does `from ._manifest_consumer import
index_from_manifest`) **breaks the lock**: the patch rebinds the facade global, but the
submodule's call site reads its own local binding. `test_perf_hardening` additionally
patches `load_known_entities`, `_apply_candidates_to_db`, `_try_update_idempotency_state`,
`dispatch_to_indexer`, `make_repo` at the facade; `test_wiki_extract_concepts` also patches
`update_idempotency_state` at the facade (the 8th lock symbol, caller =
`_try_update_idempotency_state`). **Design rule:** all 8 patched names + their callers stay
co-located in the facade namespace and use facade-global resolution.

#### 3.3 `python -m` entry point
`python -m scripts.wiki_skills.wiki_extract_concepts` is the working-tree invocation used
by dogfood + (potentially) the installed CLI. A package needs `__main__.py` (or a
`main`-bearing `__init__`) so `-m` keeps working.

---

### 4. Use Cases

#### UC-016-1: Operator — CLI unchanged (regression)
1. `python -m scripts.wiki_skills.wiki_extract_concepts prepare|apply …` behaves
   byte-identically to pre-016.
**Acceptance:** the TASK 015 dogfood recipe reproduces the same envelopes; exit codes unchanged.

#### UC-016-2: Test harness — patch-target lock holds
1. `mock.patch("scripts.wiki_skills.wiki_extract_concepts.index_from_manifest")` still
   intercepts `dispatch_to_indexer`'s call; the 8 patched names still rebind at the facade.
**Acceptance:** `test_patch_target_lock_at_skill_module` + `test_module_imports_neutral_manifest_consumer` + `test_perf_hardening` pass **unmodified**.

#### UC-016-3: Developer — find code by concern
1. A developer changing candidate validation opens `_validation.py` (~400 lines), not a
   2174-line file; a DB change opens `_db.py`; etc.
**Acceptance:** each submodule is single-concern and ≤ ~450 lines.

#### UC-016-4: Sibling modules unaffected
1. `wiki_enrich.py` / `_manifest_consumer.py` / `layout_config.py` import + run unchanged.
**Acceptance:** their test suites stay green with no edits.

---

### 5. Acceptance Criteria

| ID | Criterion | Pass/Fail |
|----|-----------|-----------|
| AC-016-1 | `import scripts.wiki_skills.wiki_extract_concepts as wec` succeeds; every previously-public name (`prepare`, `apply`, `main`, `dispatch_to_indexer`, `load_known_entities`, `classify_candidates`, `write_concept_page`, `build_manifest`, `ExtractionParseError`, …) AND the externally-referenced PRIVATE names (the 8 `_`-prefixed/lock symbols + `_derive_source_project`, imported by `tests/test_slug_strategy.py:73`) resolve on `wec` | PASS when all resolve |
| AC-016-2 | `test_patch_target_lock_at_skill_module` + `test_module_imports_neutral_manifest_consumer` pass **with zero edits** | PASS |
| AC-016-3 | `wec.validate_manifest is _manifest_consumer.validate_manifest` (and `index_from_manifest`, `WikiIngestError`) — identity preserved | PASS |
| AC-016-4 | Each of the **8** patched names (R-016-2a) is rebindable: a `mock.patch("...wiki_extract_concepts.<name>")` is observed by the in-package caller — regression-proven specifically by `test_patch_target_lock_at_skill_module` (index_from_manifest), `test_wiki_extract_concepts.py:1868/2581` (update_idempotency_state), and `test_perf_hardening.py` (load_known_entities/_apply_candidates_to_db/_try_update_idempotency_state/dispatch_to_indexer/make_repo) | PASS |
| AC-016-5 | `python -m scripts.wiki_skills.wiki_extract_concepts --help` exits 0 and shows `{prepare,apply}`; **`tests/test_wiki_extract_concepts_integration.py` (the `-m` subprocess invocation, line ~87) passes unmodified** | PASS |
| AC-016-6 | Full `pytest tests/` ≥ 879 (+4 skip), **0 unexpected failures**; the lock/canary guards (`test_patch_target_lock_at_skill_module`, `test_module_imports_neutral_manifest_consumer`, `test_apply_error_envelopes_never_echo_content`) AND **all of `test_perf_hardening.py`** pass unmodified | PASS |
| AC-016-7 | `mypy --strict scripts/` — 0 errors; no new `type: ignore` beyond carried-over ones | PASS |
| AC-016-8 | Readability NFR (**advisory targets, not hard pass/fail**): aim for each new submodule ≤ ~450 lines and facade `__init__.py` ≤ ~900 lines; the binding gate is only that the old 2174-line single file is gone and no submodule re-introduces a god-file | PASS (advisory) |
| AC-016-9 | Dogfood smoke (fresh `samples/` vault): scaffold→reindex→prepare→apply→batch reproduce TASK 015 envelopes | PASS |
| AC-016-10 | `git diff` shows **no logic edits** — only moves + import wiring + the facade re-export shim, plus the single mandated `_SRC` path repoint in `test_extract_concepts_candidate_regression.py` (R-016-7a); reviewer spot-checks that moved bodies are verbatim | PASS |

---

### 6. Non-Goals

- **No behaviour, flag, envelope, exit-code, or schema change** (this is a pure structural refactor).
- **No re-pointing of test patch targets** — the lock surface `scripts.wiki_skills.wiki_extract_concepts.<name>` is a stability contract; tests are NOT to be relaxed to accommodate a weaker split. (Pure import-path moves in NON-lock tests are permitted only if a symbol genuinely relocates AND the test still asserts the same behaviour.)
- **No new dependency**, no connection pooling, no perf work (TASK 015 territory; the deferred single-transaction batching stays deferred).
- **No rename of any public function/flag** (only physical relocation across files).
- **No splitting of sibling modules** (`_manifest_consumer.py`, `_common.py` stay as-is).

---

### 7. Implementation phasing (green-throughout, leaf-first)

> Refactor analogue of Stub-First: move ONE leaf cluster at a time, re-export from the
> facade, run the **full** suite + mypy after each move. Never proceed on red. The
> monkeypatch-coupled orchestration layer moves LAST (or stays in the facade).

| Phase | Scope |
|-------|-------|
| 0 | **Anchor**: confirm baseline (879+4skip green, mypy clean); record the patched-symbol set; pin `test_patch_target_lock` + perf/canary as the gate. |
| 1 | Create the package skeleton: `wiki_extract_concepts/__init__.py` (re-exports everything from a temporary `_impl` OR start as a 1-line `from ._impl import *`-style shim) + `__main__.py`. Suite green. |
| 2 | Extract `_errors.py` (`ExtractionParseError`, `_envelope_from_parse_error`); facade re-exports. Green. |
| 3 | Extract `_validation.py`; facade re-exports; callers reference via facade where patched. Green. |
| 4 | Extract `_sourcing.py`. Green. |
| 5 | Extract `_pages.py`. Green. |
| 6 | Extract `_db.py` (incl. `load_known_entities` — re-imported into facade, called there as a facade global so `patch(wec.load_known_entities)` still works). Green + **explicit** re-run of `test_perf_hardening` load-once/patch tests. |
| 7 | Settle the facade: `prepare`/`apply`/`dispatch_to_indexer`/`_batch_*`/`main` + the 8 patched-name re-exports; verify the R-2 lock invariant by running the lock + perf patch tests. Green. |
| 8 | Final gate: full suite, mypy strict, dogfood smoke, submodule-size check, `git diff` logic-verbatim spot-check; update `.AGENTS.md` + `ARCHITECTURE.md` + SKILL.md pointer. |

---

### 8. Open Questions

1. **Facade shape — RESOLVED → (A).** The orchestration layer (`prepare`/`apply`/
   `dispatch_to_indexer`/`_batch_*`/`main` + the 8 patched-name re-exports) is defined
   **directly in `__init__.py`**, not a re-exported `_runtime.py`. Rationale: shape (B)
   reintroduces the exact facade-global-resolution fragility the patch-target lock forbids
   (a `_runtime` caller would resolve a patched name in `_runtime`'s namespace, not the
   facade's, silently breaking `mock.patch(wec.<name>)`). Pinned as a hard constraint in
   R-016-5(a) so the Planner/Architect cannot reopen it.
2. None blocking — behaviour is frozen; the only design risk is the patch-target lock,
   fully addressed by R-016-2/5/7 (8 facade-global lock symbols + the `_db` carve-out for
   `load_known_entities`/`update_idempotency_state`).
