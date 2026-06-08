# TASK 022 — vault-local-db-resolution (DB location from vault config)

### 0. Meta Information
- **Task ID:** 022
- **Slug:** `vault-local-db-resolution`
- **Mode:** VDD (full) · **Schema:** v5 expected (zero DDL — config/resolution only)
- **Context:** Follow-up to the TASK 021 dogfood. The operator observed that a vault's index
  DB cannot be declared in the vault's own config — every command needed an explicit `--db-path`,
  otherwise the vault registers into the shared global DB. This task lets a vault **own its index
  DB** (Obsidian-native, portable), while preserving the global multi-vault default.
- **Review:** `docs/reviews/task-022-review.md` (APPROVED WITH COMMENTS — incorporated below).
- **Operator decisions (2026-06-08):** **OQ-1 → island** (single-vault; no cross-DB federation).
  **OQ-5 → robust-to-both** (in-vault DB when the folder is not cloud-synced; an explicit
  non-synced path when it is; the iCloud guard stays as the backstop).

## 1. General Description

Today the SQLite index DB is resolved in exactly one place — [`factory.make_repo`](../scripts/wiki_index/factory.py#L134):
`config['db_path']` (set only by `--db-path`) **else** the platform-default **global** DB
(`~/Library/Application Support/wiki-index/global.db` on macOS) via `_resolve_db_path(vault_id)`,
which **ignores `vault_id`** (one `global.db` for all, ADR-002 §D1 — the comment names a "future
per-vault opt-out flag"). No config layer declares the DB.

**Goal:** let `WIKI_SCHEMA.md` (the **identity** layer) optionally declare the vault's index DB via
`index_db:`, so the DB can live with the vault (`<vault_root>/.wiki/index.db`), gitignored + ADR-002
§D8-rebuildable. When unset → behaviour **byte-identical to today** (global DB).

**Connection to existing system (verified):**
- `config_loader.py` already has the disk-only primitives: **`find_vault_root(cwd)`** (public —
  walk up to `WIKI_SCHEMA.md`, like `.git`/`.obsidian`) and `load_root_config(vault_root)` (parse
  frontmatter → `vault_id`, …, and overlays `CLAUDE.md::wiki:`). Adding `index_db` to that dict is
  the small part.
- The hard part is the **ordering inversion** + the **bootstrap circularity**: the fleet pattern is
  `make_repo(config)` **first**, then read `root_path` from the opened DB (`wiki_query`/`wiki_sync`
  `_derive_vault_root`, every `repo.get_vault(args.vault)`). For a local-DB vault that opens GLOBAL
  then fails `get_vault`. Resolution must run `vault_root` (flag → `find_vault_root` walk-up)
  **before** `make_repo`. `wiki-index-upsert` and `wiki-extract-concepts prepare` already do this —
  they are the template.
- **Config layering** (canonical framing): two config *systems* — **identity** (`config_loader`,
  `WIKI_SCHEMA.md`) vs **grammar** (`layout_config`, `.wiki/layout.yaml`); `.wiki/sync.yaml` is
  dispatcher state. `index_db` is **identity** → `WIKI_SCHEMA.md`, never `layout.yaml`/`sync.yaml`.

## 2. Epics & Issues (Chainlink decomposition)

### EPIC A — Vault-declared DB resolution
| Issue | Summary |
|-------|---------|
| **A1** | `WIKI_SCHEMA.md` frontmatter gains optional `index_db:` (string). Two forms: **relative** (default, e.g. `.wiki/index.db`) → resolved under `vault_root`, contained; **absolute/`~`** (explicit escape for cloud-synced vaults) → expanded, used as-is (operator's deliberate choice — same trust as `--db-path`; WIKI_SCHEMA.md is Class A operator-authored). Read raw from `WIKI_SCHEMA.md` frontmatter ONLY (not from the `CLAUDE.md::wiki:` overlay — single redirect surface). |
| **A2** | A single **resolution chain**: `--db-path` flag **>** `index_db` (resolved per A1) **>** global default. Threaded into `make_repo` via a shared helper. Byte-identical when `index_db` absent. The iCloud guard (`validate_db_path`) fires on the resolved path either way (the OQ-5 backstop). |
| **A3** | `wiki-init` writes local-DB vaults end-to-end across **all three** subcommands: `--register-existing` + `--scaffold-new` honour a new `--index-db <relpath>` (or `--local` ⇒ `.wiki/index.db`), write `index_db:` into `WIKI_SCHEMA.md`, and register the `vaults` row into the **local** DB; `--reconcile` resolves the local DB (does not silently open global) when the moved vault declares `index_db`. |
| **A4** | CLI `vault_root` discovery: a shared helper resolves `vault_root` (flag → `config_loader.find_vault_root(cwd)` walk-up) **before** `make_repo`, then `index_db`→`db_path`. Covers the three CLI classes (B-table) **and** the internal ingest sites (`_manifest_consumer.index_from_manifest`, `wiki_index_upsert.upsert_one`). Bare `--vault <id>` with no discoverable root and not in global → `VAULT_ROOT_UNRESOLVED` (no silent global hit). |

### EPIC B — Island semantics (OQ-1 RESOLVED → island)
| Issue | Summary |
|-------|---------|
| **B1** | A local-DB vault is a self-contained **island**. `repo.list_vaults()` (used by `wiki-search`/`wiki-lint`/`wiki-reindex --all-vaults` for "all") spans only the **connected** DB — architecturally it already cannot see another DB (no registry exists). Document this as the contract; **no cross-DB federation** (a registry of local DBs is explicitly OUT of scope, YAGNI). No code change beyond the doc + ensuring "all" never silently means "global" for a local-DB invocation. |

### CLI inventory (per-CLI surface for A4 — 3 classes + internal sites)
| Class | CLIs | Today | Change |
|-------|------|-------|--------|
| (i) root **before** make_repo | `wiki-index-upsert`, `wiki-extract-concepts` | already correct | template — reuse the helper |
| (ii) `--vault-root` flag, derive from DB **after** | `wiki-query`, `wiki-sync`, `wiki-verify-multi` | inverted ordering | move resolution before make_repo |
| (iii) **no `--vault-root`** | `wiki-search`, `wiki-lint`, `wiki-reindex`, `wiki-index-render`, `wiki-alias`, `wiki-confirm`, `wiki-merge`, `wiki-append-log` | global-only | add `--vault-root` (or cwd walk-up) + helper |
| internal | `_manifest_consumer.index_from_manifest`, `wiki_index_upsert.upsert_one` | thread `db_path`/`vault_root` | helper must reach these or enrich/extract reverts to global |

## 3. Requirements Traceability Matrix

| ID | Requirement | MVP? | Sub-features |
|----|-------------|------|--------------|
| **R-022-1** | `index_db` in `WIKI_SCHEMA.md` is parsed + validated | ✅ | (a) JSON-schema: add `index_db` (string) to `WikiRootConfig` (currently `additionalProperties:true` → must be *added*); **ban** it in `WikiProjectOverride` (mirror the `vault_id` ban — identity can't be redirected by a project override); (b) **relative** form: reject `..`/NUL/abs-escape on the *string* + validate the **parent dir** is inside the vault (NOT `validate_inside_vault` on the not-yet-created DB file → it `resolve(strict=True)`s and raises `FileNotFoundError`); (c) **absolute** form allowed (cloud escape), `~`/env-expanded |
| **R-022-2** | Resolution chain `--db-path > index_db > global`, vault_root-driven, run **before** `make_repo` | ✅ | (a) shared helper `_common.build_repo_config(vault_id, *, vault_root, db_path_flag)` → config dict (make_repo stays path-only; helper **lazily imports** `config_loader` inside the fn — no top-level `_common→wiki_index` edge); (b) ordering inverted vs the `make_repo→get_vault→root_path` pattern; (c) `validate_db_path` (iCloud) fires on the resolved local path (OQ-5 backstop); (d) `wiki-enrich` threads the resolved `config['db_path']` into `_manifest_consumer.index_from_manifest(db_path=…)` — no split-brain (M-2) |
| **R-022-3** | `wiki-init` supports local-DB vaults across all 3 subcommands | ✅ | (a) `--index-db <relpath>` / `--local`; (b) writes `index_db:` into `WIKI_SCHEMA.md`; (c) `vaults` row into the **local** DB; (d) `--reconcile` honours `index_db` (no silent global open) |
| **R-022-4** | All make_repo sites resolve the local DB without `--db-path` | ✅ | (a) shared helper applied to all 3 CLI classes + the 2 internal sites (inventory table); (b) class (iii) CLIs gain `--vault-root` or cwd walk-up — **`wiki-search` has none today** (UC-2 must add it); (c) bare `--vault` + no root + not-in-global → `VAULT_ROOT_UNRESOLVED` (named; no path-content echo, CWE-209/117) |
| **R-022-5** | Island semantics defined + documented (B1) | ✅ (doc/guard) | (a) `--vault all`/`--all-vaults` = the connected DB only; (b) no silent cross-DB merge; (c) README/manual/`.AGENTS.md` state the island contract |
| **R-022-6** | Back-compat + safety | ✅ | (a) `user_version` stays 5 (zero DDL); (b) 1056 tests green; (c) `index_db` absent → byte-identical global resolution (ADR-002 §D1 untouched); (d) iCloud guard preserved |

## 4. Use Cases

### UC-1 — Register an existing vault with a local DB (NEW)
- **Actors:** operator, `wiki-init`, `config_loader`, `factory.make_repo`.
- **Main scenario:**
  1. `wiki-init --register-existing --vault <abs> --local` (or `--index-db .wiki/index.db`).
  2. System writes `index_db: .wiki/index.db` into `WIKI_SCHEMA.md`.
  3. The shared helper resolves `<vault_root>/.wiki/index.db`; `make_repo` creates it + applies schema; iCloud-guarded.
  4. The `vaults` row is written into the **local** DB; global is untouched.
- **Alternatives:**
  - **A1 (cloud-synced vault):** the relative `.wiki/index.db` resolves inside an iCloud/Dropbox container → `ICloudRejectionError` with the relocation hint. Operator sets `index_db: ~/wiki-index/<vault>.db` (non-synced, absolute) **or** leaves `index_db` unset (global). [OQ-5 robust-to-both.]
  - **A2 (already has `index_db`):** no `--local` needed — same local resolution.
- **Postcondition:** self-contained vault; `.wiki/index.db` gitignored + rebuildable (`wiki-reindex --full`).
- **Acceptance:** ✅ NO new `vaults` row for `<vault_id>` in `global.db` AND the row IS present in the resolved local DB; ✅ `index_db:` present in `WIKI_SCHEMA.md`.

### UC-2 — Run any CLI against a local-DB vault without `--db-path` (MODIFIES all CLIs)
- **Main scenario:**
  1. `wiki-search "q" --vaults <id> --vault-root <path>` (`wiki-search` uses `--vaults` plural; `--vault-root` is the new flag) **or** run from inside the vault (no flag → cwd walk-up).
  2. Shared helper resolves `vault_root` → `load_root_config` → `index_db` → DB, **before** `make_repo`.
  3. Query runs against the local DB.
- **Alternatives:**
  - **A1 (`--db-path` given):** flag wins over `index_db`.
  - **A2 (bare `--vault <id>`, not in global, no root discoverable):** `VAULT_ROOT_UNRESOLVED` error (not a silent global hit).
- **Acceptance:** ✅ no `--db-path` needed; ✅ `--db-path` still overrides; ✅ `wiki-search`/class-(iii) CLIs accept `--vault-root`.

### UC-3 — Existing global-vault workflow unchanged (REGRESSION GUARD)
- `index_db` absent → every command resolves the global DB exactly as today.
- **Acceptance:** ✅ 1056 tests green; ✅ byte-identical resolution for `index_db`-absent vaults.

## 5. Non-functional Requirements
- **Compatibility:** zero DDL (`user_version` 5); global default untouched fallback.
- **Security:** relative `index_db` parent contained-in-vault (string-level `..`/abs/NUL reject before any filesystem call — `validate_inside_vault` is unusable on the missing file); absolute form = explicit operator escape (same trust surface as `--db-path`, WIKI_SCHEMA.md is Class A); iCloud guard preserved; `index_db` banned in `WikiProjectOverride`; error codes never echo path content.
- **Portability:** relative `index_db` survives a move/clone; absolute is the deliberate cloud-vault opt-out.

## 6. Constraints & Assumptions
- **Constraint:** `index_db` is **identity** (`WIKI_SCHEMA.md`), never grammar (`layout.yaml`) or dispatcher (`sync.yaml`). Read from raw frontmatter only, not the `CLAUDE.md::wiki:` overlay.
- **Constraint:** `make_repo` stays path-only (no `config_loader` import — avoid a new dependency edge); resolution lives in a shared helper called by CLIs.
- **Assumption (operator-confirmed):** island model (no cross-vault federation); robust-to-both cloud posture; precedence `--db-path > index_db > global`.

## 7. Open Questions
- **OQ-1 — RESOLVED → island** (operator). No cross-DB federation; `--vault all` = connected DB only.
- **OQ-5 — RESOLVED → robust-to-both** (operator). In-vault relative DB for non-synced folders; explicit non-synced (absolute) path for cloud-synced; iCloud guard stays.
- **OQ-2 (architecture, non-blocking):** confirm the shared-helper placement (`resolve_repo_config` in a new small module vs extend `config_loader`) so `factory` stays `config_loader`-free. Architect decides.
- **OQ-3 (UX, non-blocking):** `wiki-init` surface — `--local` (implies `.wiki/index.db`) **and** `--index-db <relpath>` (explicit). Default relpath `.wiki/index.db`. Lean: support both.
- **OQ-4 (strictness, non-blocking):** bare `--vault <id>` + no root + not-in-global → **error** (`VAULT_ROOT_UNRESOLVED`), not silent global. Lean: error (silent global is the original surprise).
