# obsidian-llm-wiki

A multi-vault, SQLite-indexed knowledge base for Obsidian, implementing
Karpathy's [llm-wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
pattern. **Markdown is the canonical source of truth; SQLite (FTS5 + WAL) is a
100%-rebuildable derivative cache.** You get fast full-text + metadata search, an
entity/concept graph, RAG-with-citations, and a verification layer — all driven
from the shell or from inside a Claude Code session as `/wiki-*` slash commands.

> **Status**: Phase 3a complete (2026-05-26); Phase 3b through **TASK 030**
> (indexer hardening: rename-aware `--delta`, 2× faster chunked `--full`,
> single-pass pruned walk; shipped 2026-06-12). Schema **v5**
> (`user_version = 5`). **1310+ pytest passed,
> `mypy --strict` clean on 75 source files.** The repo's own `docs/` is
> registered as a live `dev-project` vault and dogfoods the toolchain. See
> [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the living architecture and
> [CLAUDE.md](CLAUDE.md) for the full per-task ship log.

---

## Table of Contents

- [What it does](#what-it-does)
- [Anatomy: how the system is layered](#anatomy-how-the-system-is-layered)
- [Data model](#data-model)
- [The universal layout engine](#the-universal-layout-engine)
- [Installation](#installation)
  - [A. Install for any project (recommended)](#a-install-for-any-project-recommended)
  - [B. Install for development of this repo](#b-install-for-development-of-this-repo)
- [Quick start: put a vault under the index](#quick-start-put-a-vault-under-the-index)
- [The `prepare` / `apply` pattern (agent-driven skills)](#the-prepare--apply-pattern-agent-driven-skills)
- [CLI reference — all 15 commands](#cli-reference--all-15-commands)
- [External dependency: `wiki-ingest`](#external-dependency-wiki-ingest)
- [Repo layout](#repo-layout)
- [Development](#development)
- [Pointers](#pointers)

---

## What it does

An llm-wiki is a knowledge base that **compounds**: every source you ingest is
distilled into atomic, cross-linked concept and entity pages, so the next query
is answered against an ever-richer corpus instead of re-reading raw material.
This repo is the **index + tooling layer** for that pattern:

- **Ingest** a raw source (transcript, article, meeting note) → LLM-synthesised
  concept/entity pages, additive merge, contradiction flagging, a `log.md` entry.
- **Search** the whole corpus with FTS5 BM25 ranking + frontmatter-metadata
  filters, across one vault or many. Default search is **inflection-tolerant**
  (per-term script-aware stemming — Cyrillic→russian, Latin→english) and
  **ё/е-folded**; `--exact` opts out to literal terms.
- **Resolve entities**: candidate → confirmed promotion, aliases (one surface
  string → one entity per vault), and merging of duplicates.
- **Query (RAG)**: retrieve over FTS5 + the entity graph, synthesise a *cited*
  answer, and file it back as a first-class compounding page.
- **Verify**: an off-by-default multi-critic audit of a filed answer against the
  sources it cited — it records a verdict, it never edits the answer.
- **Stay healthy**: lint for orphan links, dangling refs, hash drift, type
  mismatches, and cross-vault concept duplicates.

The core invariant (ADR-002 §D8): **the vault's markdown is canonical; the DB is
a rebuildable cache.** `wiki-reindex --full` restores the entire index from disk
with no semantic loss. That means you can delete the `.db` at any time and rebuild
it, and that hand-edits to markdown are first-class — not something the tooling
will clobber.

![Overview-infographic](Images/overview-infographic.png)
---

## Anatomy: how the system is layered

Two ADRs define the shape:

- **ADR-001** ([Option I — wrap + index](docs/adr/ADR-001-wiki-ingest-integration.md)):
  the **file layer** (LLM-driven page synthesis) is owned by an external skill,
  `wiki-ingest`; **this repo owns the index layer** — it reads that skill's output
  and serves fast queries. (As of TASK 004 `wiki-ingest` is *vendored* in-process,
  so no external install is required — see [below](#external-dependency-wiki-ingest).)
- **ADR-002** ([multi-vault + data layering](docs/adr/ADR-002-multi-vault-bottleneck-corrections.md)):
  one global SQLite DB partitioned by `vault_id`, with a three-class data contract.

```
                      Operator / Claude agent
                              │
          ┌───────────────────┴───────────────────┐
          ▼ FILE LAYER (Class A)                   ▼ INDEX LAYER (Class B/C)
   wiki-ingest (vendored)                     this repo
   concept/entity synthesis,                  IndexRepository DAL
   additive merge, log.md                     SQLite + FTS5 + WAL
          │                                          │
          ▼  writes canonical markdown                ▼  reads / writes rebuildable cache
   _sources/  _concepts/  _entities/          pages · entities · aliases · refs · log_events
   index.md   log.md   WIKI_SCHEMA.md                │
          │                                          │
          └──── manifest JSON ──► wiki-enrich ───────┘
                                       │
                       wiki-search · wiki-query · wiki-lint · …
```

The code is split into clean layers under `scripts/`:

| Layer | Path | Responsibility |
|---|---|---|
| **DAL** | `scripts/wiki_index/` | `IndexRepository` ABC + `SQLiteRepository`; FTS5, WAL, atomic upserts (M-4: `ON CONFLICT … DO UPDATE`, never `INSERT OR REPLACE`), drift detection, `log.md ↔ log_events` bi-directional sync, rendering, lint, reindex, security helpers. |
| **Layout engine** | `scripts/wiki_index/layout_config.py` + `layouts/*.yaml` | YAML-config-driven "what files exist / what page-type are they" — replaces ~15 previously-hardcoded surfaces (TASK 012). |
| **CLIs** | `scripts/wiki_skills/` | 15 thin entry points (14 `wiki_*.py` modules + the `wiki_extract_concepts/` package) wrapping the DAL + helper modules (`_common`, `_retrieval`, `_manifest_consumer`). |
| **Source adapters** | `scripts/wiki_source/` | Pluggable raw-source parsing (`manual` today; transcript/email/… reserved). |
| **Vendored file layer** | `scripts/wiki_ingest/` | In-process snapshot of the external `wiki-ingest` skill (TASK 004). |
| **Shell wrappers** | `bin/wiki-*` | Make every CLI runnable from any CWD (handle `cd` + venv activation + `exec`). |
| **Skills / commands / workflows** | `skills/`, `commands/`, `workflows/` | Canonical definitions, symlinked into `.claude/` and `.agent/` for vendor compatibility. |

**The repo *is* the implementation, not a vault.** Running
`wiki-init --scaffold-new --vault .` at the repo root is rejected by design.
(Since TASK 012 the repo's own `docs/` is registered as a `dev-project` vault —
`vault_root = <repo>/docs`, with a committed `docs/WIKI_SCHEMA.md` — so
`wiki-search "ADR-002" --vaults obsidian-llm-wiki` works while the repo root
itself stays vault-free.)

---

## Data model

![data-model-infopraphic](Images/data-model-infopraphic.png)

One global DB (`sql/wiki-index-v2.sql`, `user_version = 5`), every table
partitioned by `vault_id`. The three-class contract (ADR-002 §D8):

- **Class A** — vault markdown. Semantic, canonical, human-/LLM-authored.
- **Class B** — DB rows + *rendered* markdown (`index.md`, the auto-rendered
  ledgers). A **rebuildable cache** — regenerable from Class A via reindex.
- **Class C** — DB-only operational state (minimal: e.g. `vaults.registered_at`).

Core tables:

| Table | Holds |
|---|---|
| `vaults` | Registry of all vaults sharing the DB; `vault_id` is **required, explicit** in `<vault>/WIKI_SCHEMA.md` (`^[a-z][a-z0-9-]{2,31}$`, no hash fallback). |
| `entities` | Canonical concepts/people/companies/products/… with definitions, contact fields, mention counts, and an `is_candidate` flag (1 = LLM-extracted/unconfirmed, 0 = confirmed). |
| `entity_aliases` | One alias → **exactly one** entity per vault (PK `(vault_id, alias)`, schema v3); `wiki-search` expands through them. |
| `pages` | Wiki pages: `summary` · `concept` · `query` · `brief` · `research` · `index` · `verification`; FTS5-mirrored. Upserts preserve `pages.id` so the FTS5 rowid stays stable. |
| `page_entity_refs` | M:N page ↔ entity edges with provenance: `mentioned` · `defined-here` · `related` · `cited` · `verifies`. |
| `log_events` | Structured mirror of `<vault>/log.md` (bi-directional, M-2 contract). |
| `pages_fts` | FTS5 virtual table (`unicode61 remove_diacritics 2`), kept in sync by triggers. |
| `batch_runs`, `source_state`, `schema_meta` | Reindex bookkeeping, per-source dedup, migration markers. |
| `interactions`, `extracted_items` | Reserved for future Epics (tables present, indexes deferred). |

Convenience views: `index_meta` (pages+entities catalog), `known_concepts`
(for ingest-time concept injection), `v_concept_cooccurrence`, `v_vault_stats`.

The DB is a Class B cache, so schema upgrades are **not** in-place `ALTER`s — a
`vN→vN+1` migration on a populated DB is "delete the `.db`/`-wal`/`-shm`, then
`wiki-init --register-existing` + `wiki-reindex --full`" (see ADR-002 §D8).

**Where the DB lives (TASK 022).** Default: one global DB (`~/Library/Application
Support/wiki-index/global.db`), partitioned by `vault_id`. A vault may instead declare
`index_db: .wiki/index.db` in `WIKI_SCHEMA.md` (or `wiki-init … --local`) to own a portable,
in-vault DB. Precedence: `--db-path` > `index_db` > global; relative paths are vault-root-relative
(contained — a symlink/`..` escape is rejected). For an iCloud/Dropbox vault, point `index_db` at an
**absolute** non-synced path — but because `WIKI_SCHEMA.md` travels with the vault (a cloned/synced
vault is attacker-shippable), an absolute `index_db` is **gated behind `WIKI_ALLOW_ABSOLUTE_INDEX_DB=1`**
(and the iCloud WAL-corruption guard still applies). A local-DB vault is an **island** — `--vault all`
spans only the connected DB.

---

## The universal layout engine

Different vaults have different shapes. TASK 012 (R-X1) replaced ~15 hardcoded
"where do pages live / what type are they" surfaces with a **YAML-config-driven
engine** (`scripts/wiki_index/layout_config.py`, schema
`config/layout-config.schema.yaml`). Three layouts ship built-in
(`scripts/wiki_index/layouts/`):

| Layout | For |
|---|---|
| `karpathy` | The original llm-wiki shape. **Byte-identical** to the legacy hardcoded behaviour — a validated projection of `layout.py`, golden-anchor-guarded. |
| `dev-project` | A software repo's `docs/` tree — TASKs, ADRs, issues. (This is what the repo's own docs use.) |
| `obsidian-personal` | Numbered folders + Unicode titles. |

New vault shapes become **config, not code**. Pick one with
`wiki-init --layout <name>`. The `auto_indexes[]` feature renders a Class-B
"rebuildable markdown" ledger from per-item Class-A sources (e.g. this repo's
[docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md) is auto-rendered from
`docs/issues/*.md`).

Two deliberately separate config systems: per-vault **identity**
(`config_loader.py` — who this vault is) vs per-layout-class **grammar** (the
engine above — how this *kind* of vault is shaped).

**Security note (TASK 012 + 017):** operator-supplied layout regexes
(`ref_extraction[].regex`, `paths[].project_pattern`) are guarded against ReDoS
both at load time (a stdlib-`re` budget gate) and at runtime (a per-file
deadline via the PyPI [`regex`](https://pypi.org/project/regex/) engine with
`timeout=`, env-overridable via `WIKI_REDOS_BUDGET_S`, default 2.0s). Built-in
layouts use stdlib `re` and pay zero overhead.

---

## Installation

Two install paths. **Most users want (A).** Requires **Python 3.14+** (via
pyenv — the system 3.9 is incompatible with `python-frontmatter`).

### A. Install for any project (recommended)

After this one-time setup, `/wiki-*` slash commands work from **any** Claude Code
project, and `wiki-search "x"` etc. work from **any** shell — the wrappers handle
CWD + venv activation automatically.

```bash
# 1. Clone the repo to a stable location
git clone <repo> ~/dev-projects/obsidian-llm-wiki
cd ~/dev-projects/obsidian-llm-wiki

# 2. Create a venv and install deps
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Symlink wrappers, skills, and commands into user-global Claude Code dirs
bash bin/install-globally.sh

# Done — /wiki-enrich works in-process via the vendored wiki_ingest module.
# (Optional: install upstream wiki-ingest to enable the subprocess fallback.)
```

`bin/install-globally.sh` is idempotent (`ln -sfn`) and links:

| Source | Target | Count |
|---|---|---|
| `bin/wiki-*` | `~/.local/bin/wiki-*` (or `$WIKI_INSTALL_BIN`) | 15 shell wrappers |
| `skills/wiki-*/` | `~/.claude/skills/wiki-*/` | 17 skill definitions |
| `commands/wiki-*.md` | `~/.claude/commands/wiki-*.md` | 15 slash commands |

Ensure `~/.local/bin` is on your `PATH` (the installer warns if not). Then jump
to [Quick start](#quick-start-put-a-vault-under-the-index).

### B. Install for development of this repo

Only needed if you're contributing to obsidian-llm-wiki itself (tests, DAL,
framework work).

```bash
# 1. Clone + venv + deps (same as A.1–A.2)
git clone <repo> && cd obsidian-llm-wiki
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# 2. Wire framework + project skills into this repo's .claude/ and .agent/
bash /path/to/agentic-development/install.sh install \
     --vendor claude --force-system-link    # one-time
bash bin/install-project-symlinks.sh         # repo-local wiki-* skills

# 3. Run tests + type-check
pytest tests/           # full suite green (~28s; see the status block for the current count)
mypy --strict scripts/  # clean on 75 source files (vendored package excluded
                        # via mypy.ini override per Decision-14)
```

Optionally also run `bin/install-globally.sh` to dogfood the wrappers from other
projects while developing.

---

## Quick start: put a vault under the index

After install (A), from any directory:

```bash
# 1. Your vault needs `vault_id: <slug>` in its WIKI_SCHEMA.md (ADR-002 §D1.1).
#    Run wiki-init once to get a suggested slug if it's missing:
wiki-init --register-existing --vault /path/to/MyVault
#   → if missing: { "error": "MISSING_VAULT_ID", "suggested_vault_id": "my-vault" }

# 2. After adding vault_id, register the vault:
wiki-init --register-existing --vault /path/to/MyVault

# 3. First full index (this is also the Class-A → Class-B rebuildability gate):
wiki-reindex --full --vault my-vault

# 4. Day-to-day: search before you grep
wiki-search "concept name" --vaults my-vault

# 4b. Filter by frontmatter metadata (status / severity / any field).
#     Compiles to a CAST(json_extract(...) AS TEXT) predicate (not full-text),
#     so hyphenated (SEV-2) and numeric (priority=1) values match by string.
wiki-search --status open --severity SEV-2 --vaults my-vault
wiki-search "drift" --where 'status=open' --vaults my-vault   # combine with FTS
```

For a brand-new vault, use `wiki-init --scaffold-new --vault /path --layout karpathy`.
Both `--scaffold-new` and `--register-existing` write an **agent-instructions file**
into the vault root so an agent launched there has the wiki operating instructions —
**`CLAUDE.md` by default**; pass `--vendor gemini` for `GEMINI.md` (Gemini CLI), or
`--vendor claude,gemini` / `--vendor all` for both. Vendors are configured in
[`templates/agent-files.yaml`](templates/agent-files.yaml); existing files are never
clobbered.

### Choosing where the index lives: global (default) vs vault-local

You don't have to decide anything up front — by default every vault shares **one
global DB** (`~/Library/Application Support/wiki-index/global.db` on macOS,
`~/.local/share/wiki-index/...` on Linux), partitioned by `vault_id`, and the steps
above just work. A vault can instead **own its index** so the DB travels with it
(portable, gitignored, rebuildable). You pick the variant at init time — the only
difference is what `wiki-init` writes into `WIKI_SCHEMA.md`:

```bash
# (a) GLOBAL — the default. Nothing to declare; all vaults share one DB.
wiki-init --register-existing --vault /path/to/MyVault

# (b) VAULT-LOCAL — DB lives at <vault>/.wiki/index.db (vault-relative, contained).
#     --local writes `index_db: .wiki/index.db` into WIKI_SCHEMA.md and registers
#     into that local DB instead of the global one.
wiki-init --register-existing --vault /path/to/MyVault --local

# (b') VAULT-LOCAL at a custom in-vault path:
wiki-init --register-existing --vault /path/to/MyVault --index-db db/index.db

# (c) CLOUD-SYNCED vault (iCloud/Dropbox) — SQLite must NOT sit in the byte-syncing
#     folder (WAL/shm corruption), so point at an ABSOLUTE path outside the sync
#     root. Absolute paths require an explicit opt-in (the schema file travels with
#     the vault, so a synced/cloned config could otherwise redirect writes):
WIKI_ALLOW_ABSOLUTE_INDEX_DB=1 \
  wiki-init --register-existing --vault /path/to/MyVault \
            --index-db ~/wiki-dbs/myvault.db
```

`--local`/`--index-db` are just a convenience — you can equally hand-edit
`WIKI_SCHEMA.md` and add `index_db: .wiki/index.db` to the frontmatter yourself.
**Resolution precedence is always `--db-path` (a per-command override, mainly for
testing) > `index_db` (declared in `WIKI_SCHEMA.md`) > global.** A vault with a
local DB is an **island**: `wiki-search --vaults all` spans only that DB, never the
global one. **iCloud paths are auto-rejected** wherever they appear, to prevent
SQLite corruption.

Inside a Claude Code session, every command below is also invokable as a slash
form (`/wiki-init`, `/wiki-search`, …); the agent auto-suggests them when trigger
phrases match (see each [SKILL.md](skills/) for triggers).

---

## The `prepare` / `apply` pattern (agent-driven skills)

Three skills do LLM work but keep **zero `anthropic` import** in the Python (the
"Decision-17" split). The Python halves are deterministic; the LLM step is owned
by the orchestrator agent, sandwiched between two CLI calls:

```
wiki-query prepare   →  [agent reads the retrieval envelope, synthesises a
                         cited answer per the wiki-query-synthesis contract]
                     →  wiki-query apply   (files _queries/<slug>.md)
```

The same shape powers `wiki-verify-multi` (`prepare` → 4 critics →
`apply` files `_verifications/verify-<slug>.md`) and `wiki-extract-concepts`
(`prepare` recon → agent synthesises candidate JSON per the `concept-extraction`
contract → `apply` writes pages + entities). The contract skills
(`wiki-query-synthesis`, `wiki-verify`, `concept-extraction`) have no CLI — they
are the prompts the orchestrator loads between the two halves. When you run these
inside Claude Code, the agent drives all three steps for you.

---

## CLI reference — all 15 commands

Each command has a `SKILL.md` under [`skills/`](skills/) with the full contract,
exit codes, and JSON-envelope schema, plus a slash-command wrapper under
[`commands/`](commands/). Slash forms (`/wiki-…`) are equivalent to the shell
binaries.

> 📖 **Want the *why*, not just the flags?** The commands below are grouped by the
> role they play in the compounding-knowledge loop. For the full methodology —
> what each command is *for*, how to work with the vault's markdown (standard and
> custom layouts), and how to drive the wiki from another agent — see the
> **[obsidian-llm-wiki Manual](docs/manuals/obsidian-llm-wiki_manual.md)**.

### Vault lifecycle

*Bring a vault under management and keep the cache reconciled with its canonical markdown.*

| Command | What it does |
|---|---|
| `wiki-init --register-existing --vault <path> [--vendor <list>]` | Register a pre-existing vault in the index (one-time, per vault). Also writes the agent file if absent (`CLAUDE.md` by default; `--vendor gemini`/`all`), so the vault is agent-workable. |
| `wiki-init --scaffold-new --vault <path> [--layout <name>] [--vendor <list>]` | Scaffold a brand-new vault layout + an agent file (`CLAUDE.md` by default; `--vendor` picks Gemini/both). `--layout` ∈ `karpathy` · `dev-project` · `obsidian-personal` (+ custom). |
| `wiki-init --reconcile --vault <path>` | Rename / re-point a registered vault. |
| `wiki-reindex --full --vault <vid>` | Wipe + rebuild the DB from markdown (the Class A→B gate; rare, authoritative). |
| `wiki-reindex --delta --vault <vid>` | Incremental mtime/hash-based reindex after manual edits. |
| `wiki-index-upsert --vault <vid> --file <path>` | Index a single markdown file (idempotent — file-hash match → no-op). |
| `wiki-index-render --vault <vid> [--auto-indexes]` | Render `index.md` from the DB (preserves `<!-- BEGIN-CUSTOM -->` blocks); `--auto-indexes` also renders Class-B ledgers. |

### Search & retrieval

*The everyday read path — search before you grep; turn the corpus into cited answers and audit them.*

| Command | What it does |
|---|---|
| `wiki-search "<query>" --vaults <vid>[,<vid>…]` | FTS5 BM25 search across one/many vaults; ranked hits + snippets; expands aliases. |
| `wiki-search [--status <v>] [--severity <v>] [--where 'field=value'] --vaults <vid>` | Filter by frontmatter metadata (query optional → pure listing). |
| `wiki-query prepare/apply --vault-root <path>` | RAG: retrieve → orchestrator-cited synthesis → file a compounding `_queries/<slug>.md` page (`prepare`/`apply`). |
| `wiki-verify-multi prepare/apply` | Off-by-default 4-critic audit of a filed answer vs its cited sources → `_verifications/verify-<slug>.md` verdict page; FAIL records + exits non-zero, never mutates the answer. |

### Knowledge construction

*Turn raw material into compounding pages, and keep the chronological log in sync.*

| Command | What it does |
|---|---|
| `wiki-sync scan <zone> --vault <vid>` | Format-aware, tag-routed dispatcher: walk a zone → deterministic **plan JSON** (convert / ingest / upsert / skip per file; `#wiki/raw\|skip\|keep` tags; generated-view sidecars auto-skipped). The orchestrator ([`workflows/wiki-sync.md`](workflows/wiki-sync.md)) executes it with per-file idempotency (`wiki-sync record`) — office/PDF convert, **scanned-PDF OCR** (eng+rus), transcript de-timestamp → summarise → enrich → extract. A **re-summarization policy** (TASK 019, opt-in `resummarize:` in `.wiki/sync.yaml`, per-folder overridable) skips a raw source whose summary already exists (`source_state` ∪ provenance ∪ filesystem mirror) unless `--force`; a new raw sharing an already-summarised N:1 key is skipped + a **merge/split WARN** (TASK 021) names the levers (`--force` to merge / finer key to split). The MVP front of the *Mixed vault* pattern — see the [Manual](docs/manuals/obsidian-llm-wiki_manual.md). |
| `wiki-enrich --vault <vid> --source <file>` | End-to-end: invoke (vendored) `wiki-ingest` on a raw source, then mirror its manifest into the index. |
| `wiki-extract-concepts prepare/apply …` | Two-pass LLM concept extraction from an indexed source page → candidate pages + entities + manifest (`--ingest` auto-dispatches in-process). |
| `wiki-append-log --vault <vid> …` | Append a structured event to `log.md` *and* mirror it to `log_events` (atomic, flock + fsync). |

### Native Obsidian app (`obsidian-cli` skill)

*Drive the **running** Obsidian desktop app (Obsidian 1.12+ official CLI) for the things
files+SQLite can't reach — and keep the index coherent after.*

| Skill | What it does |
|---|---|
| [`obsidian-cli`](skills/obsidian-cli/SKILL.md) | A **prompt-layer, vendor-agnostic** skill teaching any LLM agent to route between the `wiki-*` toolchain (knowledge/RAG/bulk — still first for lookups) and the native `obsidian` CLI (link-safe rename/move, typed properties, tasks, daily notes, Bases queries, history restore, open-in-app). Carries a **total 3-tier safety model** (T1 read / T2 mutate / T3 banned-by-default incl. `eval`), a **mutation→index coherence protocol** (`wiki-index-upsert` after a content edit; **`wiki-reindex --delta` after a rename/move** — rename-aware since TASK 030: the moved file's new path is ingested despite the preserved mtime, closing DF-029-1; `--full` = universal fallback + swap-class remedy), and graceful degradation when the CLI is absent/headless. Full 102-command reference + recipes + behaviour evals under [`skills/obsidian-cli/`](skills/obsidian-cli/). **No Python, no DDL** — it orchestrates existing CLIs. |

### Entity resolution (Epic 7)

*Curate the entity graph so it stays a graph, not a pile — vet candidates, unify spellings, dedupe.*

| Command | What it does |
|---|---|
| `wiki-confirm <slug> --vault <vid>` | Promote a candidate entity to confirmed (`--undo` to demote; `--auto --threshold N` to bulk-promote by mention count). |
| `wiki-alias (--add\|--remove) <surface> <slug> --vault <vid>` / `wiki-alias --list [<slug>]` | Manage alias surface-strings (Class A frontmatter + DB mirror; hard-unique per vault). `--list` without a slug lists every alias in the vault. |
| `wiki-merge <duplicate-slug> <canonical-slug> --vault <vid>` | Fold a duplicate entity into the canonical one — re-point refs, absorb + register redirect aliases, delete the dup page. |

### Health

*Keep the compounding honest — surface broken links, drift, and duplicates; prove the cache is rebuildable.*

| Command | What it does |
|---|---|
| `wiki-lint --vault <vid>` (or `--all`) | SQL-level health-check: orphan links, dangling refs, missing-on-disk pages, hash drift, type mismatches, cross-vault concept duplicates. `--mtime-skip` for a faster integrity-relaxed pass. |

---

## External dependency: `wiki-ingest`

**Optional since TASK 004.** `wiki-enrich` composes with the `wiki-ingest` skill (v1.1+), which owns the
LLM-driven file layer (page synthesis, additive merge, `log.md` append,
contradiction detection). Since TASK 004 that module is **vendored** into
`scripts/wiki_ingest/` and called in-process by default — **no external install
required** for normal operation. Two paths:

- **Primary (default):** in-process call into the vendored `scripts.wiki_ingest`
  package. No subprocess, no `PATH` dependency. Active when the vendored import
  succeeds and `WIKI_ENRICH_NO_VENDORED` is unset.
- **Fallback (subprocess):** legacy path via a `wiki-ingest` binary on `PATH`.
  Active when the vendored import fails, or `WIKI_ENRICH_NO_VENDORED=1` is set
  (escape hatch for debugging/comparison/standalone users).

Provenance + sync workflow:
[`scripts/wiki_ingest/VENDORED_FROM.md`](scripts/wiki_ingest/VENDORED_FROM.md);
refresh via `bash scripts/sync_wiki_ingest.sh [--dry-run]`. Contract:
[docs/WIKI-INGEST-V1.1-CONTRACT.md](docs/WIKI-INGEST-V1.1-CONTRACT.md). License
notices: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Other CLIs (`wiki-search`, `wiki-lint`, `wiki-reindex`, …) are self-contained and
need no `wiki-ingest`. `wiki-extract-concepts` calls the Anthropic API directly
(set `ANTHROPIC_API_KEY`); its `--ingest` auto-dispatch uses the neutral
`_manifest_consumer` module in-process.

---

## Repo layout

```
docs/                       ARCHITECTURE.md, ROADMAP, ADRs, schemas, tasks/, plans/, issues/
  adr/                      ADR-001 (wrap+index), ADR-002 (multi-vault + Class A/B/C)
  KNOWN_ISSUES.md           auto-rendered Class-B ledger over docs/issues/*.md
config/                     layout-config / wiki-config / sync-config schema.yaml (the 3 config systems)
sql/wiki-index-v2.sql       the SQLite DDL (user_version = 5)
templates/                  WIKI_SCHEMA.md.tmpl + per-vendor agent files (CLAUDE.md/GEMINI.md)
                            mapped in agent-files.yaml — for new/registered vaults

scripts/
  wiki_index/               DAL: repository, sqlite_repository, lint, reindex, rendering,
                            normalization, security, layout, layout_config, sync_config
  wiki_index/layouts/       karpathy.yaml, dev-project.yaml, obsidian-personal.yaml
  wiki_skills/              15 CLI entry points + _sync/_common/_retrieval/_manifest_consumer
  wiki_source/              source adapters (base, manual, parsing)
  wiki_ingest/              vendored file layer (snapshot of external wiki-ingest)
  benchmark.py              synthetic-vault SLO harness
  sync_wiki_ingest.sh       refresh the vendored snapshot

skills/                     18 canonical SKILL.md dirs (17 wiki-* + concept-extraction)
commands/wiki-*.md          15 slash-command wrappers (Claude Code)
workflows/wiki-*.md         multi-step orchestration recipes (incl. wiki-sync executor)
bin/wiki-*                  15 shell wrappers (cd + venv + exec)
bin/install-globally.sh     global install (path A)
bin/install-project-symlinks.sh   repo-local symlinks (dev path B)
tests/                      pytest suite (full suite green; count in the status block) + fixtures
samples/                    gitignored scratch tree for dogfooding vaults
```

---

## Development

```bash
source .venv/bin/activate
pytest tests/           # 1310+ passed (see git log for the current count)
mypy --strict scripts/  # clean on 75 source files (the contract for scripts/)

# Performance SLO gate (TASK 030 / Q-030-1) — run before shipping indexer hot-path changes:
WIKI_BENCH_SLO=1 pytest tests/test_benchmark_slo_gate.py   # n=1000, enforced
python -m scripts.benchmark --n 10000 --enforce-slos       # manual 10k gate
# Protocol + evidence conventions: docs/runbooks/perf-slo-gate.md
```

Conventions:

- **Python** always via `.venv/`; **Node** always via local `node_modules/`.
  Never install globally.
- New skills/commands/workflows go at the repo root
  (`skills/<name>/SKILL.md`, `commands/<name>.md`, `workflows/<name>.md`) and are
  symlinked into `.claude/` and `.agent/` by the `bin/link-*.sh` helpers.
- Vault artifacts (`_sources/`, `_concepts/`, `_entities/`, `00-Vault-Index/`,
  `*.db*`, …) are gitignored. Dogfooding vaults live under `samples/` (also
  gitignored). Durable test fixtures live under their owning
  `skills/<name>/evals/`.
- The agentic-development framework (orchestrator, analysis→architecture→plan→
  develop→review skills/workflows) is installed as a symlink and lives *outside*
  git (`.agentic-development/`, `System/`, framework skills under `.agent/`,
  `.claude/`). Re-run `bin/install-project-symlinks.sh` after a fresh clone to
  reconnect the project's `wiki-*` skills.

---

## Pointers

- **[docs/manuals/obsidian-llm-wiki_manual.md](docs/manuals/obsidian-llm-wiki_manual.md)** — the methodology manual: why each command exists, working with Obsidian documents (standard + custom layouts), and driving the wiki from another agent.
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — living architecture (multi-vault, ADRs, status header tracking shipped tasks).
- **[docs/ROADMAP.md](docs/ROADMAP.md)** — forward-looking work (e.g. the deferred R-X2c archive hook).
- **[docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md)** — auto-rendered Class-B ledger over `docs/issues/*.md` (deferred perf set + residuals). Edit the per-issue files, never the ledger.
- **[docs/tasks/](docs/tasks/)** + **[docs/plans/](docs/plans/)** — archived task/plan specs (lockstep).
- **[docs/adr/ADR-001-wiki-ingest-integration.md](docs/adr/ADR-001-wiki-ingest-integration.md)** — Option I (wrap + index).
- **[docs/adr/ADR-002-multi-vault-bottleneck-corrections.md](docs/adr/ADR-002-multi-vault-bottleneck-corrections.md)** — `vault_id` partitioning + Class A/B/C contract.
- **[docs/WIKI-INGEST-V1.1-CONTRACT.md](docs/WIKI-INGEST-V1.1-CONTRACT.md)** — external `wiki-ingest` skill contract.
- **[sql/wiki-index-v2.sql](sql/wiki-index-v2.sql)** — the schema DDL.
- **[scripts/wiki_index/layout.py](scripts/wiki_index/layout.py)** — single source of truth for the `karpathy` layout constants.
- **[CLAUDE.md](CLAUDE.md)** — project agent instructions + the full per-task ship log.
</content>
</invoke>
