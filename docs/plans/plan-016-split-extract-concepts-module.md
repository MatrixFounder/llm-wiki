# PLAN — TASK 016 `split-extract-concepts-module`

Green-throughout, **leaf-first** refactor. Each bead moves ONE cluster, re-exports it from
the facade, and is GREEN only when the **full** suite + `mypy --strict` pass (the existing
tests — especially the patch-target-lock + CWE canary + `test_perf_hardening` — ARE the
regression gate; there are no new tests, this is a pure structural move). **Never proceed on
red.** Behaviour, CLI, envelopes, exit codes, and schema are frozen.

## Dominant invariant (every bead must preserve it)
The **patch-target lock**: `scripts.wiki_skills.wiki_extract_concepts` stays importable and
the **8** monkeypatched names remain rebindable as **facade (`__init__.py`) globals**, with
in-package callers resolving them there — `make_repo`, `load_known_entities`,
`validate_manifest`, `index_from_manifest`, `dispatch_to_indexer`, `_apply_candidates_to_db`,
`_try_update_idempotency_state`, `update_idempotency_state`. Guarded by
`test_patch_target_lock_at_skill_module` + `test_module_imports_neutral_manifest_consumer`
(both must pass UNMODIFIED). Facade shape **(A)** is mandatory: orchestration + lock symbols
are DEFINED in `__init__.py`; leaves never import the facade.

## Per-bead gate (run after EVERY bead)
```bash
source .venv/bin/activate
python -m pytest tests/ -q            # ≥ 879 (+4 skip), 0 failures
mypy --strict scripts/               # 0 errors
python -m scripts.wiki_skills.wiki_extract_concepts --help   # exits 0, shows {prepare,apply}
```

## Bead checklist (Epic → Issue → Bead; RTM-linked)

### Epic A — Package skeleton
- [ ] **[R-016-NF2] 016-00** — Anchor: confirm baseline green (879+4skip) + mypy clean; record the 8-symbol lock surface + the 2 file-path-literal tests as the gate. No code change. → [task-016-00](tasks/task-016-00-anchor.md)
- [ ] **[R-016-1] 016-01** — Convert `wiki_extract_concepts.py` → package `wiki_extract_concepts/` (`__init__.py` = the verbatim current module body; add `__main__.py` → `main()`). Repoint `test_extract_concepts_candidate_regression.py` `_SRC` → `wiki_extract_concepts/__init__.py` (R-016-7a, interim). → [task-016-01](tasks/task-016-01-package-skeleton.md)

### Epic B — Extract pure leaves (no monkeypatch coupling)
- [ ] **[R-016-4e] 016-02** — Extract `_errors.py` (`ExtractionParseError`, `_envelope_from_parse_error`); facade `from ._errors import *`. → [task-016-02](tasks/task-016-02-errors.md)
- [ ] **[R-016-4a] 016-03** — Extract `_validation.py` (validators, sanitizers, candidate-schema, `classify_candidates`, `_preflight_sanitize`, `_parse_source_span`, regex/const allowlists). → [task-016-03](tasks/task-016-03-validation.md)
- [ ] **[R-016-4b] 016-04** — Extract `_sourcing.py` (`_read_file_bounded`, `_FileTooLargeError`, `_resolve_source_inside_sources`, `_all_concepts_dirs`, `_derive_source_project`, `_load_candidates`, `_path_is_absolute`, byte caps). Verify `test_slug_strategy.py:73` `_derive_source_project` facade-import still resolves (R-016-7b — NO test edit). → [task-016-04](tasks/task-016-04-sourcing.md)
- [ ] **[R-016-4d] 016-05** — Extract `_pages.py` (`write_concept_page`, `_format_source_quote_block`, name allowlist). Repoint `_SRC` → `wiki_extract_concepts/_pages.py` (R-016-7a, final). → [task-016-05](tasks/task-016-05-pages.md)

### Epic C — Extract `_db` (with the lock carve-out)
- [ ] **[R-016-4c + R-016-2 carve-out] 016-06** — Extract `_db.py` (`load_known_entities`, `_lookup_entity_row`, `upsert_extracted_entity`, `upsert_entity_refs`, `check_idempotency`, `update_idempotency_state`, `build_manifest`). Facade re-imports `load_known_entities` + `update_idempotency_state` and calls them as facade globals; explicitly re-run the perf load-once + the `update_idempotency_state` H-3 patch tests. → [task-016-06](tasks/task-016-06-db.md)

### Epic D — Settle facade + final gate
- [ ] **[R-016-2 + R-016-5] 016-07** — Settle the facade: confirm orchestration (`prepare`/`apply`/`dispatch_to_indexer`/`_batch_*`/`_apply_*`/`_recon_single`/`_load_known_and_drift`/`main`/`_build_parser_v3`) + the 8 lock re-exports are correct; prove the R-2 lock by running the lock + all `test_perf_hardening` patch tests. Verify facade ≤ ~900 lines (advisory). → [task-016-07](tasks/task-016-07-settle-facade.md)
- [ ] **[R-016-3/6 + NF1-4] 016-08** — Final gate: full suite + mypy + dogfood smoke + submodule-size check + `git diff` logic-verbatim spot-check; repoint SKILL.md `<!-- Sync -->` pointer (R-016-6b); update `scripts/wiki_skills/.AGENTS.md`. → [task-016-08](tasks/task-016-08-final-gate.md)

## Execution order & dependencies
`016-00 → 016-01 → 016-02 → 016-03 → 016-04 → 016-05 → 016-06 → 016-07 → 016-08` (strict
linear; each depends on the prior being green). Leaf order respects the dependency DAG
(`_errors` first — it is the sink; `_validation` before `_pages`/`_db` which import it;
`_sourcing` independent). The orchestration layer + lock symbols **never leave** `__init__.py`.

## Risks
- **R-1 (patch-target lock break)**: a moved-out caller of a patched name resolves it in the
  leaf namespace → `mock.patch(wec.<name>)` no-ops. *Mitigation*: callers of patched names
  stay in `__init__`; the `_db` carve-out re-imports `load_known_entities`/
  `update_idempotency_state` into the facade; the lock + perf patch tests run every bead.
- **R-2 (circular import)**: a leaf importing the facade. *Mitigation*: enforce the acyclic
  import-direction rule (ARCHITECTURE §2.1); `_errors` is the sink; only `facade → leaves`.
- **R-3 (`_SRC.read_text` breakage)**: the `.py`→package conversion makes `_SRC.read_text()`
  raise `IsADirectoryError` (the path is now a directory) in
  `test_extract_concepts_candidate_regression.py`. *Mitigation*: repoint `_SRC` in 016-01
  (→`__init__.py`) and again in 016-05 (→`_pages.py`, when `write_concept_page` moves).
- **R-4 (hidden behaviour drift)**: an accidental logic edit during a move. *Mitigation*: moves
  are verbatim cut/paste; 016-08 does a `git diff` body-verbatim spot-check; golden/byte-identity
  tests gate every bead.
