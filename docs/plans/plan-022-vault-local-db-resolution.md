# PLAN 022 — vault-local-db-resolution

Stub-First, green-throughout. Zero DDL (`user_version` 5). `factory.make_repo` UNCHANGED.
Each bead is verifiable by a single (parametrized) test. RTM IDs from `docs/TASK.md`.

**Strategy (`planning-decision-tree`):** the two new pure-ish units (`resolve_index_db_path`,
`build_repo_config`) land first as stub+RED→GREEN (Phase 1); the CLI/init/internal wiring consumes
them (Phase 2). The global-DB fallback is the invariant guarded throughout (R-022-6).

## Dependency order
`02-01 (resolve_index_db_path)` → `02-02 (build_repo_config)` → {`02-03 schema`, `02-04 CLI i/ii`,
`02-05 CLI iii`, `02-06 wiki-enrich`, `02-07 wiki-init`} → `02-08 island docs` → `02-09 regression+dogfood`.

---

## Phase 1 — new components (stub → RED → GREEN)

### ☐ [R-022-1] task-022-01 — `config_loader.resolve_index_db_path`
- **New pure fn** `resolve_index_db_path(vault_root: Path) -> Path | None` in
  `scripts/wiki_index/config_loader.py`, beside `find_vault_root`/`load_root_config`.
- Reads `index_db` from the **RAW** `WIKI_SCHEMA.md` frontmatter via `_split_frontmatter`
  (**NOT** `load_root_config` — bypass the `CLAUDE.md::wiki:` overlay, the single-redirect-surface
  decision). Missing key / non-str → `None`.
- **Relative** form: reject (`ValueError`/`ConfigValidationError`) a string containing NUL or that is
  absolute; resolve `(vault_root / rel)`; verify `.parent.resolve(strict=False).is_relative_to(vault_root.resolve())`
  (closes the symlinked-`.wiki/` escape — arch M-1); return the (unresolved-but-joined) `Path`.
- **Absolute / `~`** form: `Path(os.path.expanduser(os.path.expandvars(val)))` → return as-is
  (explicit operator escape; iCloud guard is applied later by `make_repo`).
- **Stub:** `return None` + full docstring. **RED test** asserts the relative case returns the
  joined path (fails on the stub). Then GREEN.
- **Verify:** `pytest tests/test_config_loader_index_db.py` — relative-in-vault → `<root>/.wiki/index.db`;
  absolute `~/x.db` → expanded; `index_db: ../escape.db` → raises; symlinked `.wiki/`→out → raises;
  absent → `None`.

### ☐ [R-022-2] task-022-02 — `_common.build_repo_config` (the chain)
- **New fn** `build_repo_config(vault_id: str, *, vault_root: Path | None, db_path_flag: str | None) -> dict[str, Any]`
  in `scripts/wiki_skills/_common.py`. Chain: `db_path_flag` → else (if `vault_root`)
  `resolve_index_db_path(vault_root)` → else nothing. Returns `{"vault_id": vault_id}` plus
  `"db_path"` when one was resolved. **Lazy `import scripts.wiki_index.config_loader` INSIDE the fn**
  (arch M-3 — no top-level `_common→wiki_index` edge that `rendering` transitively pulls).
- **Stub:** ignore `index_db`, honour only `db_path_flag` (≡ today's inline pattern). **RED test**
  asserts `index_db` is used when no flag (fails on stub). Then GREEN.
- **Verify:** `pytest tests/test_build_repo_config.py` — flag wins over index_db; index_db used when
  no flag; neither + `vault_root=None` → no `db_path` key (→ global, R-022-6 byte-identity);
  iCloud-resident resolved path still reaches `make_repo`'s guard (assert `make_repo` raises
  `ICloudRejectionError`, guard unchanged).

### ☐ [R-022-1] task-022-03 — JSON schema (DiD)
- `config/wiki-config.schema.yaml`: add `index_db: {type: string, minLength: 1}` to
  `WikiRootConfig.properties`; ban it in `WikiProjectOverride` via
  `allOf: [{not: {required: [vault_id]}}, {not: {required: [index_db]}}]` (NOT a single
  `not: required:[vault_id, index_db]` — that only rejects having BOTH; arch MN-1).
- **Verify:** `pytest tests/test_schema_index_db.py` — `Draft202012Validator` on `#/$defs/WikiRootConfig`
  accepts `{vault_id, index_db}`; on `#/$defs/WikiProjectOverride` rejects `{index_db: …}` and
  `{vault_id: …}`. (Binding validation is in 02-01; this is DiD via `load_root_config`.)

## Phase 2 — wiring (consume the helper; each with its E2E test)

### ☐ [R-022-4] task-022-04 — CLI classes (i)+(ii): resolve before `make_repo`
- Switch to `build_repo_config(...)`: class (i) already root-first — `wiki_index_upsert`,
  `wiki_extract_concepts`; class (ii) `--vault-root` but derive-after — `wiki_query`, `wiki_sync`,
  `wiki_verify_multi` (move resolution **before** `make_repo`; keep the post-hoc `get_vault` only for
  zone/root display, fed by the same `vault_root`). `wiki_index_render` already has `--vault-root`.
- **Verify:** `pytest tests/test_cli_local_db_resolution.py::test_sync_local` — register a sample vault
  with `index_db`; `wiki-sync scan <zone> --vault X --vault-root <root>` (no `--db-path`) hits the
  **local** DB; global `vaults` has no row for X.

### ☐ [R-022-4] task-022-05 — CLI class (iii): add `--vault-root` + walk-up to 8 CLIs
- Add `--vault-root` + the resolve-before-make_repo helper to the 8 that lack the flag: `wiki_search`,
  `wiki_lint`, `wiki_reindex`, **`wiki_index_render`**, `wiki_alias`, `wiki_confirm`, `wiki_merge`,
  `wiki_append_log`. Root = `args.vault_root` → `config_loader.find_vault_root(cwd)` walk-up.
  Unresolved + local-needed → a single `_common`-sourced `VAULT_ROOT_NOT_FOUND` code string (m-1; no
  path echo, CWE-209/117). **`wiki-search` is the outlier — `--vaults` (plural), not `--vault`** (M-1):
  derive `vault_id = vaults_list[0] if vaults_list and vaults_list[0]!="all" else GLOBAL_VAULT_SENTINEL`.
- **Verify:** `pytest …::test_search_local_flag` (`wiki-search "q" --vaults X --vault-root <root>` → local)
  + `…::test_search_local_cwd` (run from inside the vault, no flag → walk-up resolves local) +
  `::test_global_unchanged` (all 8 parametrized).

### ☐ [R-022-2] task-022-06 — `wiki-enrich` internal-site threading (no split-brain)
- `wiki_enrich.main`: run `build_repo_config(...)` and pass the resolved `config["db_path"]` into
  `_manifest_consumer.index_from_manifest(..., db_path=…)` (existing kwarg — **no signature change**);
  `wiki_index_upsert.upsert_one` inherits via the open `repo`.
- **Verify:** `pytest …::test_enrich_writes_local` — `wiki-enrich` against a local-DB vault writes the
  page into the **local** DB; global untouched (the M-2 split-brain regression guard).

### ☐ [R-022-3] task-022-07 — `wiki-init` local-DB across subcommands
- Add `--local` (⇒ `.wiki/index.db`) and `--index-db <relpath>` to `scaffold_new` + `register_existing`;
  write `index_db:` into the rendered `WIKI_SCHEMA.md` (extend `WIKI_SCHEMA.md.tmpl` conditionally or
  post-write the key); build the repo via `build_repo_config` so the `vaults` row lands in the **local**
  DB. `reconcile` resolves a declared `index_db` (no silent global open).
- **Verify:** `pytest …::test_init_register_local` — `wiki-init --register-existing --vault <abs> --local`
  → `index_db` present in `WIKI_SCHEMA.md`; `vaults` row in `<root>/.wiki/index.db`; **no** new row in
  global.

### ☐ [R-022-5] task-022-08 — island contract + nested-vault docs
- Document the island model + nested-vault consequence (a sub-vault with its own `index_db` routes to a
  different DB) in `README.md`, `docs/manuals/…manual.md`, and `scripts/wiki_*/.AGENTS.md`. Confirm
  `--vault all`/`--all-vaults` never silently means "global" for a local-DB invocation (it already
  spans only the connected DB).
- **Verify:** `pytest …::test_all_vaults_island` — `wiki-lint --all-vaults` on a local-DB connection
  enumerates only that DB's vault(s); doc grep for the island/nested note.

### ☐ [R-022-6] task-022-09 — full regression + real dogfood
- Full `pytest tests/` + `mypy --strict scripts/` green; grep-guard zero DDL (`user_version` 5), no new
  deps. Real end-to-end on a `samples/` vault: register `--local`, run `wiki-reindex --full` +
  `wiki-search` + `wiki-sync scan` with NO `--db-path`; assert all hit the local DB and `global.db`
  mtime/rowset unchanged. `--db-path` still overrides (precedence).
- **Verify:** the suite + the scripted dogfood assertions.

---

## Notes / risks
- **02-05 is the widest edit** (8 CLIs) but each is the same ~3-line helper swap + one `add_argument`;
  the parametrized E2E covers them uniformly. No `--vault-root` collisions (verified: the flag exists
  today only on `wiki_query`/`wiki_sync`/`wiki_verify_multi`/`wiki_index_upsert`/`wiki_enrich`/
  `wiki_extract_concepts`). `wiki-search` uses `--vaults` (plural) — special-cased (M-1).
- `resolve_index_db_path` reads RAW frontmatter (binding validation in code); the schema add (02-03) is
  DiD via `load_root_config`. Keep the two validation sites consistent (both reject `..`/abs-as-relative).
- `make_repo` is not edited in any bead — the iCloud guard + global fallback are reused as-is (R-022-6).
