# task-022-02 — `_common.build_repo_config` (the resolution chain) [R-022-2]

**Goal:** one CLI-shared helper encoding `--db-path > index_db > global`, producing the `make_repo`
config dict — `make_repo` stays untouched.

**Context (read/edit):**
- `scripts/wiki_skills/_common.py` — add the fn; mirror the **lazy-import** discipline of
  `resolve_entity_file` (imports `security` inside the body).
- `scripts/wiki_index/factory.py` — `make_repo` (UNCHANGED; consumes `config['db_path']`).
- Depends on task-022-01.

**Steps:**
1. `def build_repo_config(vault_id: str, *, vault_root: Path | None, db_path_flag: str | None) -> dict[str, Any]:`
2. `cfg: dict[str, Any] = {"vault_id": vault_id}`.
3. `if db_path_flag: cfg["db_path"] = db_path_flag; return cfg` (flag wins).
4. `if vault_root is not None:` lazily `from scripts.wiki_index.config_loader import resolve_index_db_path`;
   `p = resolve_index_db_path(vault_root); if p is not None: cfg["db_path"] = str(p)`.
5. `return cfg` (no `db_path` → `make_repo` falls back to global = byte-identical to today).
6. **Stub-First:** stub honours only `db_path_flag` (ignores index_db) + docstring; RED test asserts
   index_db is consumed; then GREEN.

**Verification:** `pytest tests/test_build_repo_config.py -q`
- `db_path_flag` present → wins (index_db ignored); no flag + `vault_root` with `index_db` → that path;
  no flag + `vault_root=None` → dict has NO `db_path` key (global fallback, R-022-6 byte-identity);
  an `index_db` resolving into an iCloud path → `make_repo(build_repo_config(...))` raises
  `ICloudRejectionError` (guard reused, unchanged).
- `mypy --strict scripts/wiki_skills/_common.py`.
