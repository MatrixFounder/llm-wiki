# 1.5. Project Anatomy

> Part of [docs/ARCHITECTURE.md](../ARCHITECTURE.md).

> **Superseded (TASK 047):** the `wiki-enrich` ↔ vendored `wiki-ingest` integration flow
> (§1.5.2 / §1.5.3 / §1.5.7 below — the in-process/subprocess two-path design, the
> dual-existence + vendored-snapshot layout, the sync policy, the `WIKI_ENRICH_NO_VENDORED`
> branch) was **retired**: `wiki-enrich` + `scripts/wiki_ingest/` were deleted, `wiki-import` is
> the in-repo construct engine, and concept-page compounding is a derived Class-B render
> (`wiki-index-render --concept-mentions`). Those subsections are kept as history — read them as
> "how it used to work," not the current repo.

This section maps **where things live** in the repository and the symlink graph through which Claude Code resolves a slash command into a Python entry point. Lives here so subagents and operators don't have to reconstruct the layout from `ls` walks.

### 1.5.1. Anatomy of one in-repo skill (template, shown via `/wiki-search`)

Every skill in this repo follows a strict **4-file-of-same-name** convention plus a shared DAL. There are 9 such skills (`wiki-init`, `wiki-search`, `wiki-lint`, `wiki-reindex`, `wiki-index-upsert`, `wiki-index-render`, `wiki-append-log`, `wiki-enrich`, `wiki-extract-concepts`).

```text
operator: "/wiki-search 'query'"
    │
    ▼ Claude Code resolves slash command
~/.claude/commands/wiki-search.md ──symlink──► obsidian-llm-wiki/commands/wiki-search.md
    │                                          (slash-command registration; points to skill)
    ▼
~/.claude/skills/wiki-search/ ───symlink──► obsidian-llm-wiki/skills/wiki-search/SKILL.md
    │                                       (skill manifest: tier, triggers, when/how)
    ▼ SKILL.md delegates to bash CLI
~/.local/bin/wiki-search ───symlink──► obsidian-llm-wiki/bin/wiki-search
    │                                  (POSIX wrapper: cd repo + source .venv + exec python -m)
    ▼
obsidian-llm-wiki/scripts/wiki_skills/wiki_search.py
    │                          (Python entry: argparse + main(argv) + JSON envelope to stdout)
    ▼
obsidian-llm-wiki/scripts/wiki_index/   (shared DAL — see §1.5.4)
    │
    ▼
SQLite ~/Library/Application Support/wiki-index/global.db   (multi-vault, FTS5)
```

**Convention rules:**

| Surface | Path pattern | Naming convention |
|---|---|---|
| Slash command | `commands/wiki-<name>.md` | dash-separated, mirrors CLI name |
| Skill manifest | `skills/wiki-<name>/SKILL.md` | dash-separated dir |
| Bash launcher | `bin/wiki-<name>` (executable) | dash-separated, no extension |
| Python entry | `scripts/wiki_skills/wiki_<name>.py` | underscore-separated (Python module rules) |
| Global symlinks | `~/.claude/{commands,skills}/`, `~/.local/bin/` | created by `bin/install-globally.sh` |

**The 4 in-repo dirs** (`commands/`, `skills/`, `bin/`, `scripts/wiki_skills/`) must stay in lockstep — adding a new skill means 4 new files of matching name. The installer (`bin/install-globally.sh`) discovers each set via globs.

### 1.5.2. Anatomy of cross-process / in-process flow (`/wiki-enrich → wiki-ingest`)

`/wiki-enrich` is the **only** in-repo skill that integrates with `wiki-ingest`. There are **two paths**: a primary in-process path (vendored Python import, default) and a subprocess fallback path (external `wiki-ingest` binary). The manifest contract (v1.1, [WIKI-INGEST-V1.1-CONTRACT.md](./WIKI-INGEST-V1.1-CONTRACT.md)) is identical for both — only the transport changes.

#### Path decision branch

```text
wiki_enrich.py start:
    if _VENDORED_AVAILABLE and not _force_subprocess:  # WIKI_ENRICH_NO_VENDORED truthy set
        → PRIMARY PATH (in-process, below)
    elif shutil.which("wiki-ingest"):
        → FALLBACK PATH (subprocess, below)
    else:
        → emit {"error":"WIKI_INGEST_UNAVAILABLE"}, exit 6
```

#### PRIMARY PATH (in-process, default post-TASK-004)

```text
operator: /wiki-enrich --source raw.md
    │
    ▼ standard 4-file path resolves to scripts/wiki_skills/wiki_enrich.py
    │
    ├── 1. from scripts.wiki_ingest.commands.ingest import ingest as _vendored_ingest
    │       (lazy import at module level; _VENDORED_AVAILABLE = True on success)
    │       NO check_wiki_ingest_version() call on this path.
    │
    ├── 2. _vendored_ingest(source=source, vault=vault_root, vault_id=args.vault, ...)
    │       │   In-process call — no subprocess, no JSON round-trip.
    │       │   ── R-26 invariant preserved: vendored `ingest()` retains
    │       │      `_safety.validate_inside_vault(source, vault)` from upstream
    │       │      (see §1.5.7 file `_safety.py`); confirmed post-sync by
    │       │      content-hash check in `scripts/sync_wiki_ingest.sh` (R-49(b))
    │       │      and verified at runtime by the vendored-import smoke check.
    │       ▼
    │   scripts/wiki_ingest/commands/ingest.ingest()   [vendored copy — see §1.5.7]
    │       │   (runs full wiki-ingest pipeline in-process: register-summary →
    │       │    upsert-page × N → update-index → append-log → log-event)
    │       ├─ filesystem writes under operator's vault:
    │       │   _sources/<slug>.md, _concepts/*, _entities/*, index.md, log.md
    │       └─ returns: manifest dict (v1.1, NOT a JSON string)
    │
    ├── 3. _validate_manifest()  — path-traversal guard, vault_id match, status=ok
    │       (unchanged — same function regardless of path taken)
    │
    ├── 4. index_from_manifest()  — loop manifest["written"]
    │       │   (top-level system files skipped — R-0 fix in commit 156325d)
    │       ▼ in-process call for each non-system written entry
    │   scripts/wiki_skills/wiki_index_upsert.main(argv)
    │       │
    │       ▼
    │   scripts/wiki_index/sqlite_repository.SQLiteRepository.upsert_page()
    │       │
    │       ▼
    │   SQLite global.db
    │
    └── 5. append_log_event()  — mirror manifest["log_event"] → log_events table

stdout: {"action":"enriched", "ingest":<full manifest>, "index":{"upserted":[...], "log_event_id":N}}
```

**Primary path summary**: no subprocess spawned; `wiki-ingest` binary NOT required on PATH; `check_wiki_ingest_version()` NOT called. `IngestError` raised by vendored `ingest()` → emitted as `{"error":"WIKI_INGEST_FAILED", "code":"<code>", ...}`, exit 6 (content error, no fallback attempted).

#### FALLBACK PATH (subprocess — legacy / standalone wiki-ingest use case)

Activated when: `WIKI_ENRICH_NO_VENDORED` env-var is set to a truthy value (case-insensitive `{1, true, yes, on}`; whitespace-stripped) **or** vendored import raises `ImportError` (with `wiki-ingest` on PATH). Preserved for: (a) operator debugging, (b) environments where vendored copy is not yet available, (c) standalone `wiki-ingest` CLI users who invoke `wiki-enrich` without vendoring.

```text
operator: WIKI_ENRICH_NO_VENDORED=1 wiki-enrich --source raw.md
    │         (or: vendored import raised ImportError, wiki-ingest found on PATH)
    │
    ▼ scripts/wiki_skills/wiki_enrich.py (subprocess branch)
    │
    ├── 1. check_wiki_ingest_version()  — shutil.which("wiki-ingest"); semver guard ≥ 1.1
    │
    ├── 2. subprocess.run(["wiki-ingest", "ingest", "--source", X, "--output-format", "json", ...])
    │       │
    │       ▼ separate venv, separate codebase
    │   ~/.local/bin/wiki-ingest ─symlink─► Universal-skills/.../scripts/wiki-ingest
    │       │                              (POSIX shell wrap; exec python3 wiki_ops.py "$@")
    │       ▼
    │   Universal-skills/skills/wiki-ingest/scripts/wiki_ops.py
    │       │   (multi-subcommand argparse dispatcher)
    │       ▼
    │   wiki_ingest/_dispatch.py → wiki_ingest/commands/<X>.py
    │       │
    │       ├─ filesystem writes under operator's vault:
    │       │   _sources/<slug>.md, _concepts/*, _entities/*, index.md, log.md
    │       └─ stdout: JSON manifest v1.1 (CONTRACT §1)
    │
    ├── 3. _validate_manifest()  — path-traversal guard, vault_id match, status=ok
    │
    ├── 4. index_from_manifest()  — loop manifest["written"]
    │       │   (top-level system files skipped — R-0 fix in commit 156325d)
    │       ▼ in-process call for each non-system written entry
    │   scripts/wiki_skills/wiki_index_upsert.main(argv)
    │       │
    │       ▼
    │   scripts/wiki_index/sqlite_repository.SQLiteRepository.upsert_page()
    │       │
    │       ▼
    │   SQLite global.db
    │
    └── 5. append_log_event()  — mirror manifest.log_event → log_events table

stdout: {"action":"enriched", "ingest":<full manifest>, "index":{"upserted":[...], "log_event_id":N}}
```

**Fallback path summary**: requires `wiki-ingest` on PATH; `check_wiki_ingest_version()` active; JSON round-trip via subprocess stdout. Silent activation (no user-visible warning unless `--verbose` or DEBUG log). Steps 3-5 are identical between both paths.

**Manifest-dispatch contract:** `wiki-enrich`'s `--source` flag is the sole entry point. Manifest dispatch for downstream skills (`wiki_extract_concepts`) happens **in-process** via direct import of `validate_manifest` + `index_from_manifest` from the neutral module `scripts.wiki_skills._manifest_consumer`. No `--manifest-file` / `--manifest-stdin` CLI flags exist; the in-process call obviates them.

### 1.5.3. External dependency: `wiki-ingest` anatomy (different pattern)

`wiki-ingest` lives in a **separate repo** (`Universal-skills`) and has a **different internal anatomy** from this project. This is not a contradiction — it reflects different evolution paths and is bridged via the v1.1 contract.

```text
Universal-skills/skills/wiki-ingest/
├── SKILL.md                       (single skill manifest)
├── scripts/
│   ├── wiki-ingest                (POSIX shell launcher — single binary,
│   │                               not 1-of-N like this repo's bin/)
│   ├── wiki_ops.py                (multi-subcommand argparse dispatcher;
│   │                               scan | init | ingest | register-summary | lint |
│   │                               reindex | promote | demote | classify-folder | …)
│   ├── wiki_ingest/               (Python package, internal modules)
│   │   ├── _classify.py, _dispatch.py, _frontmatter.py, _markdown.py,
│   │   ├── _page_merge.py, _safety.py, _vault.py
│   │   └── commands/              (per-subcommand modules)
│   └── tests/
├── references/                    (manifest_schema.md, exit_codes.md, ingest_workflow.md, …)
├── assets/, examples/, evals/
```

**Pattern contrast — single mega-CLI vs N small CLIs:**

| | This repo (`obsidian-llm-wiki`) | External (`wiki-ingest`) |
|---|---|---|
| User-facing entry points | 8 separate CLIs (`wiki-search`, `wiki-lint`, …) | 1 CLI with N subcommands (`wiki-ingest <cmd>`) |
| Bash launchers | 8 files in `bin/` | 1 file in `scripts/` |
| Python entry style | 8 modules in `scripts/wiki_skills/` | 1 dispatcher `wiki_ops.py` + per-cmd modules under `wiki_ingest/commands/` |
| Slash-command surface | 8 `/wiki-X` commands | None natively — invoked via subprocess by `/wiki-enrich`, or by operator from shell |
| Skill manifest | Per-skill `SKILL.md` (8 files) | One `SKILL.md` for the whole tool |

**Neither pattern is wrong**; they reflect that this repo splits operations into composable units (DAL-thin CLIs), while `wiki-ingest` keeps related operations under one cohesive synthesis tool. The bridge (`/wiki-enrich`) is the seam.

> **Dual existence of `wiki-ingest`:** the skill exists in two forms simultaneously. The copy in `Universal-skills` remains the standalone CLI for "simple wiki" users who install `wiki-ingest` independently. The vendored copy at `scripts/wiki_ingest/` in this repo is for in-process use only — it is a snapshot of the upstream, not a live link, and is not intended as a user-facing CLI (though it remains usable as one via `python -m scripts.wiki_ingest.commands.ingest`). The two copies may diverge over time; the sync policy in §1.5.7 governs how drift is detected and resolved. The external `wiki-ingest` binary is no longer required for standard `wiki-enrich` operation — the vendored copy is the primary path; the binary stays optional (enables subprocess fallback for debugging or environments without the vendored copy). Cross-reference: §1.5.7 (vendored module anatomy).

### 1.5.4. Shared DAL layer (`scripts/wiki_index/`)

All 8 in-repo skills converge on the DAL. **No skill talks to SQLite directly; everything goes through `IndexRepository`.**

> **Vendored-module DAL invariant:** The vendored `scripts/wiki_ingest/` module does NOT use the DAL — it writes vault files only (Class A canonical per ADR-002 §D8). Index upsert of those files flows through `IndexRepository` via `index_from_manifest()` in `wiki_enrich.py` (steps 4-5 of the §1.5.2 diagram — same shape for both primary and fallback paths). Multi-vault invariant preserved: vendored `ingest()` accepts `vault_id` as an explicit parameter; all DB writes in the indexing step carry `vault_id=?` predicates via `repo.upsert_page()`.

```text
scripts/wiki_index/
├── repository.py          — IndexRepository ABC (abstract methods)
├── sqlite_repository/     — concrete SQLite impl as a domain-package (TASK 056; import path
│   │                        unchanged: `from scripts.wiki_index.sqlite_repository import …`)
│   ├── __init__.py        — SQLiteRepository assembly + frozen public re-exports
│   ├── _base.py           — SQLiteRepositoryBase(IndexRepository): connection/PRAGMAs/
│   │                        exceptions + shared _in_clause
│   ├── _vaults.py / _pages.py / _refs_graph.py / _search.py
│   ├── _health_rules.py / _health_scan.py / _events.py
│   └── _entities.py / _merge.py / _state.py
├── factory.py             — make_repo(WikiConfig) → backend instance
├── models.py              — dataclasses: Page, Entity, Vault, LogEvent, PageRef, …
├── layout.py              — constants: SYSTEM_FILES, PAGE_SUBDIRS, SCAFFOLD_DIRS,
│                            COURSE_TIER_DIR, VAULT_INDEX_DIR, LOG_SUBDIR
├── security.py            — validate_inside_vault (R-26 guard), assert_no_symlink_escape
├── normalization.py       — body strip: Mermaid fences, SECTION anchors (R-07.5)
├── lint.py                — SQL queries for orphans/dangling/drift/duplicates
├── reindex.py             — full + delta reindex algorithms
├── rendering.py           — index.md projection from pages table
├── logfile.py             — monthly rotation, log_md_byte_offset for round-trip
└── config_loader.py       — WikiConfig parser (CLAUDE.md::wiki: + .wiki.yaml merge)
```

**Stub-First invariant:** `resolve_entity` is a deferred read-path stub (`NotImplementedError`); it will be activated by R-4 (entity promotion / candidate-vs-confirmed resolution). `upsert_entity` is fully implemented as the entity write-path method.

### 1.5.5. Symlink graph (installation footprint)

Generated by `bin/install-globally.sh` (idempotent, `ln -sfn`):

```text
~/.local/bin/wiki-<name>           ──► obsidian-llm-wiki/bin/wiki-<name>            (CLI access)
~/.local/bin/wiki-ingest           ──► Universal-skills/skills/wiki-ingest/scripts/wiki-ingest
                                       (manually symlinked — separate repo)
~/.claude/commands/wiki-<name>.md  ──► obsidian-llm-wiki/commands/wiki-<name>.md    (slash command)
~/.claude/skills/wiki-<name>/      ──► obsidian-llm-wiki/skills/wiki-<name>/        (skill manifest)
~/.claude/skills/wiki-ingest/      ──► Universal-skills/skills/wiki-ingest/         (external skill manifest)
```

**`.claude/` and `.agent/` in this repo are themselves symlink farms** pointing into `skills/`, `commands/`, `workflows/` — keeping a single source of truth while satisfying vendor-specific resolver paths (Claude Code, Gemini, ...).

### 1.5.6. Quick reference: "I want to add a new skill / modify an existing one"

| Goal | Touch these files |
|---|---|
| Add a new skill `wiki-foo` | `bin/wiki-foo` (executable) + `skills/wiki-foo/SKILL.md` + `commands/wiki-foo.md` + `scripts/wiki_skills/wiki_foo.py` + `tests/test_wiki_foo.py`; then `bin/install-globally.sh` to wire up symlinks |
| Modify CLI surface of `wiki-X` | Argparse in `scripts/wiki_skills/wiki_X.py`; update `skills/wiki-X/SKILL.md` examples; update `commands/wiki-X.md` if slash-trigger changes |
| Add a DAL method | `scripts/wiki_index/repository.py` (ABC) + the owning domain module in `scripts/wiki_index/sqlite_repository/` (e.g. a health analysis → `_health_rules.py`; see the §1.5.4 package tree) + every test fixture that mocks `IndexRepository` (otherwise import-time `TypeError`) |
| Touch SQL schema | `docs/SCHEMA-v2.sql` (DDL) + the affected `scripts/wiki_index/sqlite_repository/_*.py` domain modules (queries) + migration story in `docs/MIGRATION-*.md` if breaking |
| Add a workflow file | `workflows/<name>.md` (e.g. `wiki-enrich.md`) + symlink into `.agent/workflows/` |
| Sync vendored wiki-ingest | `bash scripts/sync_wiki_ingest.sh` (rsync snapshot refresh with hash-divergence guard) + commit updated `scripts/wiki_ingest/` tree and `scripts/wiki_ingest/VENDORED_FROM.md` |

### 1.5.7. Vendored module anatomy (`scripts/wiki_ingest/`)

This subsection describes the provenance, sync policy, and public API surface of the vendored `wiki_ingest` Python package.

**Path:** `obsidian-llm-wiki/scripts/wiki_ingest/`

**Directory layout:**

```text
scripts/wiki_ingest/
├── __init__.py               — package init; re-exports __version__ = "1.1.0" (snapshot version)
├── VENDORED_FROM.md          — provenance metadata (not a Python module; gitignore-exempt)
│                               Fields: source_commit, synced_at, source_path,
│                                       file_hashes (SHA256 per *.py for divergence detection),
│                                       local_patches (list of documented local divergences)
├── _classify.py
├── _dispatch.py
├── _frontmatter.py
├── _markdown.py
├── _page_merge.py
├── _safety.py
├── _vault.py
└── commands/
    ├── __init__.py
    ├── append_log.py
    ├── classify_folder.py
    ├── demote.py
    ├── find.py
    ├── ingest.py             — PRIMARY REFACTOR (I-V.3): adds IngestError + ingest() fn
    ├── init.py
    ├── lint.py
    ├── log_event.py
    ├── promote.py
    ├── reindex.py
    ├── register_summary.py
    ├── scan.py
    ├── update_index.py
    └── upsert_page.py
```

**Provenance file (`VENDORED_FROM.md`):** Records `source_commit` (upstream `git rev-parse HEAD` SHA or `"non-git"` if source is not a git checkout), `synced_at` (ISO-8601 timestamp), `source_path` (resolved path used during sync), `file_hashes` (SHA256 content hash of each committed `*.py` file — used by the sync script to detect local divergence before overwriting), and `local_patches` (list of documented intentional divergences from upstream, e.g. type-annotation fixups for `mypy --strict` compliance). This file is committed alongside the vendored copy and is the authoritative record of snapshot state.

**Sync script (`scripts/sync_wiki_ingest.sh`):** rsync-based snapshot refresh. Workflow: (1) read `VENDORED_FROM.md::file_hashes`; (2) recompute hashes of current vendored files; (3) abort with per-file diff if any hash diverges from the recorded value and neither `local_patches` entry covers it nor `--accept-local-divergence` is passed (prevents silent overwrite of local fixups); (4) rsync from source path excluding `__pycache__/` and `*.pyc`; (5) update `VENDORED_FROM.md` with new SHA and timestamp. Flags: `--source <path>` (default: `../../Universal-skills/skills/wiki-ingest/scripts/wiki_ingest/`), `--dry-run` (print what would sync, no mutations), `--accept-local-divergence` (bypass hash abort, operator assumes responsibility).

> **`--accept-local-divergence` use policy** (operator discipline; not enforced by CI today): every invocation MUST be followed by adding a `local_patches[]` entry to `VENDORED_FROM.md` in the same commit, explaining what diverged and why. If the entry is missing, the next sync will catch it and abort again. Future hardening (TASK 005+): a pre-commit hook can enforce the rule.

**Public API surface (post-TASK-004 refactor):**

```python
from scripts.wiki_ingest.commands.ingest import ingest, IngestError

# ingest() — programmatic entry point (Decision-13)
manifest_dict: dict = ingest(
    source=Path("/path/to/raw-summary.md"),
    vault=Path("/path/to/vault-root"),
    vault_id="my-vault",          # optional; if given, must match WIKI_SCHEMA.md
    source_hash=None,              # optional pre-computed sha256-hex (idempotency)
    known_concepts=None,           # decorative in v1.1; reserved for synthesiser integration
    dry_run=False,
    timeout_seconds=600,           # reserved; not enforced in-process
    quiet=True,                    # suppress human-readable stdout lines
)
# Returns: v1.1 manifest dict (status="ok", written=[], log_event={...}, ...)
# Raises: IngestError on all failure modes (no sys.exit() in the call graph)

# IngestError attributes:
#   message: str          — human-readable description
#   code: str             — e.g. "SOURCE_NEEDS_SUMMARIZATION"
#   phase: str | None     — pipeline phase where failure occurred
#   written_so_far: list  — partial success state
#   child_exit_code: int  — 0 if not applicable
```

The CLI surface is preserved: `execute(args: argparse.Namespace)` continues to work by calling `ingest()` internally and converting `IngestError` to `_safety.die()`. This means `python -m scripts.wiki_ingest.commands.ingest --source X --vault Y --output-format json` still exits 0 and emits a valid v1.1 manifest (R-57 acceptance criterion).

**Vendoring policy:**

- The vendored copy is a **snapshot**, NOT a live link. It does not auto-update.
- **Upstream-first fix policy (Decision-12):** All bug fixes and improvements go to `Universal-skills/skills/wiki-ingest` first. After upstream merge, run `bash scripts/sync_wiki_ingest.sh` to pull the fix down. Do not divergently fork the vendored copy — local modifications must be documented in `VENDORED_FROM.md::local_patches` and upstreamed promptly.
- **Drift detection:** The sync script's hash-divergence guard (comparing `file_hashes` in `VENDORED_FROM.md` against current on-disk SHA256s) detects local edits before overwriting. Any `local_patches` entry exempts the corresponding file from the abort.
- **Type annotation fixups (R-50):** If upstream is loose on type annotations, the vendored copy may carry `# VENDORED-PATCH:` comment blocks with local fixes. Each such fixup is listed in `local_patches`. If cumulative fixup effort exceeds 2 hours (I-V.4 time-box), add minimal `# type: ignore[<error>]` comments with `# UPSTREAM-ISSUE:` references instead of deep-fixing.
- **Third-party notices:** `THIRD_PARTY_NOTICES.md` (repo root) is **always written** — credits upstream wiki-ingest: project name, upstream repo path (`Universal-skills/skills/wiki-ingest`), SPDX license identifier (or `"NOASSERTION — operator-owned, internal"` if upstream has no LICENSE), snapshot SHA, sync date. The `LICENSE-upstream` file copy (`scripts/wiki_ingest/LICENSE-upstream`) is **conditional**: created only if upstream carries a `LICENSE` file. Sync script detects upstream LICENSE presence and warns the operator if missing so the `NOASSERTION` fallback is a deliberate choice, not a silent omission (R-55).

**Multi-vault invariant:** The vendored `ingest()` accepts `vault_id` as an explicit keyword argument (Decision-13 signature). Callers (`wiki_enrich.py`) pass `vault_id=args.vault` explicitly. The vendored module does not derive `vault_id` by hash fallback — the explicit-required invariant from ADR-002 §D1.1 is preserved in the API contract.

---

