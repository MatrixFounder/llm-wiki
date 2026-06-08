# task-022-01 — `config_loader.resolve_index_db_path` [R-022-1]

**Goal:** a pure resolver that turns a vault's optional `index_db` (raw `WIKI_SCHEMA.md` frontmatter)
into an absolute DB `Path`, or `None` when unset — with relative-form containment that resists a
symlinked `.wiki/` escape, and an absolute-form operator escape.

**Context (read/edit):**
- `scripts/wiki_index/config_loader.py` — `_split_frontmatter`, `find_vault_root`, `load_root_config`,
  `ConfigValidationError`. Add the new fn here (beside the other identity primitives).
- `scripts/wiki_index/security.py` — model only; do NOT use `validate_inside_vault` (it
  `resolve(strict=True)`s → `FileNotFoundError` on the not-yet-created DB).

**Steps:**
1. Add `def resolve_index_db_path(vault_root: Path) -> Path | None:`.
2. `base, _ = _split_frontmatter((vault_root / _WIKI_SCHEMA_MARKER).read_text())` (RAW frontmatter —
   NOT `load_root_config`, to bypass the `CLAUDE.md::wiki:` overlay). `val = base.get("index_db")`;
   `if not isinstance(val, str) or not val.strip(): return None`.
3. **Absolute/`~`/`$VAR`:** if `os.path.isabs(expanded)` after `expanduser`+`expandvars` → return
   `Path(expanded)` (operator escape; iCloud guard applied downstream by `make_repo`).
4. **Relative:** reject NUL (`"\x00" in val`) and a path that is absolute-as-written; compute
   `cand = (vault_root / val)`; require
   `cand.parent.resolve(strict=False).is_relative_to(vault_root.resolve())` else raise
   `ConfigValidationError("index_db escapes the vault")` (no value echo). Return `cand`.
5. Full docstring (the two forms + the single-redirect-surface rationale).
6. **Stub-First:** first commit the body as `return None` with the docstring + write the RED test;
   confirm RED; then implement; confirm GREEN.

**Verification:** `pytest tests/test_config_loader_index_db.py -q`
- relative `.wiki/index.db` → `<root>/.wiki/index.db`; absolute `~/wiki/x.db` → expanded abs;
  `../escape.db` → raises; symlink `<root>/.wiki -> /tmp/out` + relative → raises; absent → `None`;
  error never contains the offending value (CWE-209).
- `mypy --strict scripts/wiki_index/config_loader.py`.
