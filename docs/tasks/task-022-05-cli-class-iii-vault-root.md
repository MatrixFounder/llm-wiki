# task-022-05 — CLI class (iii): add `--vault-root` + cwd walk-up to 8 CLIs [R-022-4]

**Goal:** the 8 CLIs with no `--vault-root` flag today gain it (+ cwd walk-up) and resolve the local DB
via `build_repo_config`.

**Context (read/edit):** `scripts/wiki_skills/{wiki_search,wiki_lint,wiki_reindex,wiki_index_render,wiki_alias,wiki_confirm,wiki_merge,wiki_append_log}.py`
- `scripts/wiki_index/config_loader.py::find_vault_root(cwd)` + `VaultRootNotFoundError`. Depends on task-022-02.
- **Verified flag membership:** these 8 have NO `--vault-root` argparse flag (no collision). The ones
  that already have it — `wiki_query`/`wiki_sync`/`wiki_verify_multi` (02-04), `wiki_index_upsert`/
  `wiki_extract_concepts` (02-04), `wiki_enrich` (02-06) — are out of scope here.

**Steps (uniform, per CLI):**
1. `p.add_argument("--vault-root", default=None, help="Vault root (derive local index DB from WIKI_SCHEMA.md). Walks up from CWD when omitted.")`.
2. Resolve before `make_repo`: `vault_root = Path(args.vault_root) if args.vault_root else None`; if
   `None`, try `find_vault_root(Path.cwd())` inside `try/except VaultRootNotFoundError` → stays `None`
   (global path remains valid for global vaults).
3. `config = build_repo_config(<vault_id>, vault_root=vault_root, db_path_flag=args.db_path)`.
4. **`wiki-search` is the outlier — it uses `--vaults` (plural), not `--vault`** (M-1). Derive
   `vault_id = vaults_list[0] if vaults_list and vaults_list[0] != "all" else GLOBAL_VAULT_SENTINEL`
   and feed THAT into `build_repo_config` (note: `build_repo_config` resolves `index_db` off
   `vault_root` regardless of a sentinel `vault_id`, so `--vaults all --vault-root <root>` still hits
   the local DB). The other 7 use `args.vault or GLOBAL_VAULT_SENTINEL`.
5. Unresolved-root error: emit a `VAULT_ROOT_UNRESOLVED`-class envelope **only** when a local vault is
   addressed with no resolvable root and it is absent from global. Source the code string from a
   single new `_common` constant (e.g. `_common.VAULT_ROOT_NOT_FOUND`) reused by all 8 — do NOT
   hand-wave "reuse existing" (m-1); no path-content echo (CWE-209/117). For the common global case
   (`vault_root=None`, vault in global) behaviour is unchanged.

**Verification:** `pytest tests/test_cli_local_db_resolution.py -q`
- `::test_search_local_flag` — `wiki-search "q" --vaults X --vault-root <root>` → hits local DB.
- `::test_search_local_cwd` — CWD inside the vault, no flag → walk-up resolves local (any of the 8).
- `::test_global_unchanged` — a global vault (no `index_db`), no `--vault-root` → byte-identical global
  behaviour, asserted across all 8 (parametrized). Full `pytest` + `mypy --strict`.
