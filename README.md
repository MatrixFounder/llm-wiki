# obsidian-llm-wiki

Multi-vault SQLite-indexed knowledge base for Obsidian, implementing
Karpathy's [llm-wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
pattern. Markdown is the canonical source; SQLite (FTS5 + WAL) is a
rebuildable derivative cache.

> **Status**: Phase 3a complete (2026-05-26) — 34 tasks landed, 293 tests
> green, mypy `--strict` clean, dogfooded on a real two-tier vault.
> See [docs/TASK.md](docs/TASK.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Table of Contents

- [What's in this repo](#whats-in-this-repo)
- [Architecture](#architecture)
- [External dependency: `wiki-ingest`](#external-dependency-wiki-ingest)
- [Installation](#installation)
  - [A. Install for any target project (recommended)](#a-install-for-any-target-project-recommended)
  - [B. Install for development of this repo](#b-install-for-development-of-this-repo)
- [Use on a vault](#use-on-a-vault)
- [CLI reference (slash forms)](#cli-reference-slash-forms)
- [Repo layout](#repo-layout)
- [Development](#development)
- [Pointers](#pointers)

---

## What's in this repo

The **index layer** for an Obsidian-style llm-wiki. Provides:

- **DAL** (`scripts/wiki_index/`) — `IndexRepository` ABC + `SQLiteRepository`
  with multi-vault partitioning, FTS5, WAL, atomic upserts (M-4 contract),
  bi-directional `log.md ↔ log_events` sync, drift detection.
- **CLIs** (`scripts/wiki_skills/`) — eight thin entry points wrapping the
  DAL: `wiki-init`, `wiki-search`, `wiki-lint`, `wiki-reindex`,
  `wiki-index-upsert`, `wiki-index-render`, `wiki-append-log`, plus
  `wiki-enrich` (bridge to `wiki-ingest`, see [External dependency](#external-dependency-wiki-ingest)).
- **Skills/commands/workflows** (`skills/`, `commands/`, `workflows/`) —
  canonical definitions, symlinked into `.claude/` and `.agent/` for
  vendor compatibility.
- **Shell wrappers** (`bin/wiki-*`) — make every CLI runnable from any
  CWD; symlinked into `~/.local/bin` by the global installer.
- **Migration + benchmarks** (`scripts/wiki_migrate_flat_to_folders.py`,
  `scripts/benchmark.py`).

The repo *is* the implementation. **It is not a vault** — running
`wiki-init --scaffold-new --vault .` is rejected by design.

---

## Architecture

ADR-001 ([Option I: wrap + index](docs/adr/ADR-001-wiki-ingest-integration.md)):
the file layer is owned by an external skill (`wiki-ingest`); this repo
indexes its output and serves fast queries.

ADR-002 ([multi-vault + data layering](docs/adr/ADR-002-multi-vault-bottleneck-corrections.md)):
one global SQLite DB partitioned by `vault_id`. Class A (markdown,
canonical) → Class B (DB, rebuildable cache) → Class C (DB-only
operational, minimal).

```
       Operator / Claude agent
                │
   ┌────────────┴────────────┐
   ▼ file layer              ▼ index layer
/wiki-ingest               this repo
(external)                    │
   │ writes markdown           │ reads / writes SQLite
   ▼                           ▼
canonical files          rebuildable cache
   │                           │
   └─manifest JSON─►  /wiki-enrich (bridge)
                           │
                       /wiki-search, /wiki-lint
```

---

## External dependency: `wiki-ingest`

`/wiki-enrich` composes with the `wiki-ingest` skill (v1.1+), which
owns the LLM-driven file layer — concept/entity page synthesis,
additive merge, log.md append, contradiction detection.

Install `wiki-ingest` globally so the binary is on `PATH` (typically
under `~/.claude/skills/wiki-ingest/`) before invoking `/wiki-enrich`.
Contract: [docs/WIKI-INGEST-V1.1-CONTRACT.md](docs/WIKI-INGEST-V1.1-CONTRACT.md).

Other CLIs (`wiki-search`, `wiki-lint`, `wiki-reindex`, etc.) are
self-contained and do not need `wiki-ingest`.

---

## Installation

Two install paths. Most users want **(A)**.

### A. Install for any target project (recommended)

After this one-time setup, `/wiki-*` slash commands work from **any**
Claude Code project, and `wiki-search "x"` etc. work from **any** shell —
the wrappers handle CWD + venv activation automatically.

```bash
# 1. Clone the repo to a stable location
git clone <repo> ~/dev-projects/obsidian-llm-wiki
cd ~/dev-projects/obsidian-llm-wiki

# 2. Create a Python venv and install deps (Python 3.14+ via pyenv)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Install wrappers, skills, and commands into user-global Claude Code dirs
bash bin/install-globally.sh
```

What `bin/install-globally.sh` does (idempotent):

| Source | Target | What |
|---|---|---|
| `bin/wiki-*` (8 files) | `~/.local/bin/wiki-*` | Shell wrappers |
| `skills/wiki-*/` (8 dirs) | `~/.claude/skills/wiki-*/` | Skill definitions |
| `commands/wiki-*.md` (8 files) | `~/.claude/commands/wiki-*.md` | Slash commands |

Override the wrapper destination with `WIKI_INSTALL_BIN=/some/path`.
Ensure `~/.local/bin` is on your shell `PATH` (the installer prints a
warning if not). Then jump to [Use on a vault](#use-on-a-vault).

### B. Install for development of this repo

You only need this if you're contributing to obsidian-llm-wiki itself
(running tests, modifying the DAL, working on the agentic-development
framework alongside).

```bash
# 1. Clone + venv + deps (same as A.1–A.2)
git clone <repo>
cd obsidian-llm-wiki
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# 2. Wire framework + project skills into this repo's .claude/ and .agent/
bash /path/to/agentic-development/install.sh install \
     --vendor claude --force-system-link    # one-time
bash bin/install-project-symlinks.sh         # repo-local wiki-* skills

# 3. Run tests + type-check
pytest tests/           # 293 passed, 4 skipped (~3s)
mypy --strict scripts/  # clean on 30 source files
```

Optionally also run `bin/install-globally.sh` so you can dogfood the
wrappers from other projects while developing.

---

## Use on a vault

After install (A), from any directory:

```bash
# 1. Add `vault_id: <slug>` to your vault's WIKI_SCHEMA.md (ADR-002 §D1.1)
#    No fallback — required field. Run wiki-init to get a suggested slug:
wiki-init --register-existing --vault /path/to/MyVault
#   → if missing: { "error": "MISSING_VAULT_ID", "suggested_vault_id": "..." }

# 2. After adding vault_id, register
wiki-init --register-existing --vault /path/to/MyVault

# 3. First full index (also the rebuildability gate)
wiki-reindex --full --vault my-vault

# 4. Day-to-day: search before grep
wiki-search "concept name" --vaults my-vault
```

Inside a Claude Code session, the same commands are invokable as
`/wiki-init`, `/wiki-search`, etc. (slash forms). The agent will
auto-suggest them whenever the trigger phrases match (see each
[SKILL.md](skills/) for the trigger keywords).

DB lives at `~/Library/Application Support/wiki-index/global.db` on
macOS (`~/.local/share/wiki-index/...` on Linux). iCloud paths are
auto-rejected to prevent SQLite corruption.

---

## CLI reference (slash forms)

| Command | When |
|---|---|
| `/wiki-init --register-existing --vault <path>` | one-time, per vault |
| `/wiki-init --scaffold-new --vault <path>` | brand-new vault layout |
| `/wiki-search "<query>" --vaults <vid>` | every time you need a fact |
| `/wiki-reindex --delta --vault <vid>` | after manual markdown edits |
| `/wiki-reindex --full --vault <vid>` | rebuild from scratch (rare) |
| `/wiki-lint --vault <vid>` | periodic health-check |
| `/wiki-index-render --vault <vid>` | regenerate index.md projection |
| `/wiki-enrich --vault <vid> --source <file>` | new raw source → end-to-end |

Each has a SKILL.md under [`skills/`](skills/) with full contract,
exit codes, and JSON envelope schema. Discoverable via Claude Code's
Skill tool and from the `.claude/` / `.agent/` vendor trees.

---

## Repo layout

```
docs/                  TASK.md, PLAN.md, ARCHITECTURE.md, ADRs, schemas
scripts/wiki_index/    DAL + lint + reindex + rendering + security
scripts/wiki_source/   Source adapters (manual; future: transcript, email, ...)
scripts/wiki_skills/   CLI entry points (8 thin wrappers)
scripts/benchmark.py   Synthetic-vault SLO harness
scripts/wiki_migrate_flat_to_folders.py   tmp2/ → _sources/ one-shot
skills/wiki-*/         canonical SKILL.md for our 8 skills
commands/wiki-*.md     slash-command wrappers (Claude Code)
workflows/wiki-*.md    workflow definitions (multi-step orchestration)
bin/wiki-*             shell wrappers (cd + venv + exec)
bin/install-globally.sh        global install (recommended path A)
bin/install-project-symlinks.sh  repo-local symlinks (dev path B)
bin/link-*.sh          one-off helpers for adding a new skill/command/workflow
sql/                   wiki-index-v2.sql (DDL)
templates/             WIKI_SCHEMA.md.tmpl, CLAUDE.md.tmpl for new vaults
tests/                 pytest suite (293 tests) + fixtures
```

---

## Development

```bash
source .venv/bin/activate
pytest tests/           # 293 passed, 4 skipped (~3s)
mypy --strict scripts/  # clean on 30 source files
```

The agentic-development framework (orchestrator, skills/workflows for
analysis → architecture → plan → develop → review) is installed as a
symlink — its content lives outside the repo (`.agentic-development/`,
`System/`, framework skills under `.agent/skills/`, `.claude/skills/`,
etc.) and never enters git. See `.gitignore`.

Custom project skills under `skills/wiki-*/` are tracked. Re-running
`bin/install-project-symlinks.sh` after a fresh clone reconnects them
to this repo's `.claude/` and `.agent/` trees.

---

## Pointers

- **[docs/TASK.md](docs/TASK.md)** — current task spec (Phase 3a complete)
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — system architecture, multi-vault design
- **[docs/PLAN.md](docs/PLAN.md)** — development plan & exit criteria
- **[docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md)** — deferred items, including performance SEV-1 set
- **[docs/adr/ADR-001-wiki-ingest-integration.md](docs/adr/ADR-001-wiki-ingest-integration.md)** — Option I (wrap + index)
- **[docs/adr/ADR-002-multi-vault-bottleneck-corrections.md](docs/adr/ADR-002-multi-vault-bottleneck-corrections.md)** — vault_id, Class A/B/C contract
- **[docs/WIKI-INGEST-V1.1-CONTRACT.md](docs/WIKI-INGEST-V1.1-CONTRACT.md)** — external skill contract
- **[scripts/wiki_index/layout.py](scripts/wiki_index/layout.py)** — single source of truth for layout constants
