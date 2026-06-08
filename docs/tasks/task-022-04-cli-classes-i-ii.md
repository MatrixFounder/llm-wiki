# task-022-04 — CLI classes (i)+(ii): resolve before `make_repo` [R-022-4]

**Goal:** CLIs that already hold a `vault_root` resolve the local DB via `build_repo_config` BEFORE
opening the repo (fixing the `make_repo→get_vault→root_path` ordering for class (ii)).

**Context (read/edit):**
- Class (i) already root-first: `scripts/wiki_skills/wiki_index_upsert.py`,
  `scripts/wiki_skills/wiki_extract_concepts/__init__.py`.
- Class (ii) `--vault-root` flag but derive-after: `scripts/wiki_skills/wiki_query.py`,
  `scripts/wiki_skills/wiki_sync.py`, `scripts/wiki_skills/wiki_verify_multi.py`.
- (`wiki_index_render` has NO `--vault-root` flag → it is class (iii), handled in task-022-05; NOT here.)
- `wiki_verify_multi` keeps `--vault-root` **required** (its derive-after differs from query/sync's
  optional-derive) — preserve that; only move the DB resolution ahead of `make_repo`.
- Depends on task-022-02.

**Steps (per CLI):**
1. Compute `vault_root` (existing `--vault-root` flag → existing derivation) **before** `make_repo`.
2. Replace the inline `config = {"vault_id": …}; if args.db_path: config["db_path"]=…` with
   `config = build_repo_config(args.vault, vault_root=vault_root, db_path_flag=args.db_path)`.
3. Keep any post-hoc `repo.get_vault(...)` ONLY for zone/display, fed by the same `vault_root` (no
   second resolution). For class (ii) the `_derive_vault_root` that reads `repo` must not be the
   source of the DB decision anymore.

**Verification:** `pytest tests/test_cli_local_db_resolution.py -q` (M-3 — cover all 3 class-(ii), not just sync)
- `::test_sync_local` — `wiki-sync scan <zone> --vault X --vault-root <root>` (NO `--db-path`) → plan
  emitted from the **local** DB; `global.db` has no `vaults` row for X.
- `::test_query_local` — `wiki-query prepare … --vault X --vault-root <root>` resolves the **local** DB
  (the optional-derive ordering-inversion guard); a parametrized fixture covers `wiki_sync`,
  `wiki_query`, `wiki_verify_multi` so none silently opens global.
- full `pytest tests/` (regression for the touched CLIs) + `mypy --strict`.
