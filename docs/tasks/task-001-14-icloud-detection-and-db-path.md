# Task 001-14: iCloud detection + platform-default DB path resolver [LOGIC IMPLEMENTATION]

## Use Case Connection
- UC-01 (wiki-init refuses to put DB inside iCloud)
- All factory consumers (R-03)

## Task Goal
Replace the stub `_is_icloud_path` and `_resolve_db_path` in `scripts/wiki_index/factory.py` with real implementations. iCloud detection uses a pinned regex (M-6 from architecture review). DB path resolution uses per-platform default (macOS: `~/Library/Application Support/wiki-index/global.db`; Linux: `~/.local/share/wiki-index/global.db`; Windows: `%APPDATA%/wiki-index/global.db`).

## Changes Description

### New Files
None.

### Changes in Existing Files

#### File: `scripts/wiki_index/factory.py`

**Function `_is_icloud_path(p: Path) -> bool`:**
- Replace stub body with: `_ICLOUD_RE = re.compile(r'/Mobile Documents/(iCloud~|com~apple~)')`; return `bool(_ICLOUD_RE.search(str(p.resolve())))`.
- Pinned regex from M-6: matches both `iCloud~md~obsidian` and `com~apple~CloudDocs`.

**Function `_resolve_db_path(vault_id: str, platform: str) -> Path`:**
- Replace stub. Use `platform` argument (default: `sys.platform`) to pick:
  - `'darwin'`: `Path.home() / 'Library/Application Support/wiki-index/global.db'`
  - `'linux'`: `Path.home() / '.local/share/wiki-index/global.db'`
  - `'win32'`: `Path(os.environ['APPDATA']) / 'wiki-index/global.db'`
  - Other: raise `RuntimeError(f'Unsupported platform: {platform}')`.
- Note: `global.db` (single file for all vaults per ADR-002 §D1), NOT per-vault — `vault_id` param kept for future per-vault opt-out, currently ignored.
- Ensure parent dir exists (`p.parent.mkdir(parents=True, exist_ok=True)`).

**Function `validate_db_path(p: Path) -> None` (new):**
- Resolves `p` and asserts `not _is_icloud_path(p)`; raises `ICloudRejectionError` with hint to use `--db-path` override.

### Component Integration
- Factory `make_repo` (task-001-20) will call `validate_db_path` before instantiating the repo.
- `wiki-init` (task-001-21) calls `_resolve_db_path` to determine default location.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: On a fixture path containing `Mobile Documents/iCloud~md~obsidian/`, `validate_db_path` raises.
2. **TC-E2E-02**: On a non-iCloud path, `validate_db_path` does not raise.

### Unit Tests
1. **TC-UNIT-01**: Both iCloud patterns (`iCloud~` and `com~apple~`) detected.
2. **TC-UNIT-02**: macOS default path = `~/Library/Application Support/wiki-index/global.db`.
3. **TC-UNIT-03**: Linux default path = `~/.local/share/wiki-index/global.db`.
4. **TC-UNIT-04**: Unknown platform raises `RuntimeError`.

### Regression Tests
- task-001-05 stub tests adjusted to acknowledge real behavior.

## Acceptance Criteria
- [ ] iCloud regex matches both `iCloud~md~obsidian` and `com~apple~CloudDocs` paths.
- [ ] All per-platform defaults match TASK.md UC-01 step 5.
- [ ] `mypy --strict` passes.
- [ ] All TC tests pass.

## Notes
- M-6 (architecture review): pinned regex avoids drift from "looks iCloud-y" heuristics.
- `/private/tmp/wiki-test-vault/Mobile Documents/...` (the fixture pattern from TASK.md §6.3) is correctly flagged — test it.
- `--db-path <custom>` override (UC-01 A3) is exposed via factory in task-001-20.
