# obsidian-llm-wiki — agent instructions (vendor-neutral)

Cross-vendor instruction file (pi / Codex / hermes / any `AGENTS.md`-aware CLI). Claude Code
reads `CLAUDE.md` (richer — it also imports the agentic-development orchestration via
`CLAUDE.local.md`, which uses a Claude-specific `@import` syntax other CLIs can ignore). This
file is the portable subset: everything you need to work on **the framework repo itself**.

## What this is
A multi-vault, SQLite-indexed knowledge base (Karpathy llm-wiki pattern): **markdown is the
canonical source of truth; the SQLite index is a 100%-rebuildable cache.** The repo ships **18
`wiki-*` CLIs** (construct / search / resolve-entities / answer-verify / maintain) plus the
`obsidian-cli` skill (drives the running Obsidian app). The repo **is the implementation, NOT a
vault** — never run `wiki-init --scaffold-new --vault .` here.

## Durable invariants (a change must not break)
- **Class A/B/C layering (ADR-002 §D8):** Class A = vault markdown (canonical); Class B = the DB
  + auto-rendered ledgers (rebuildable — `wiki-reindex --full` is the gate); Class C = minimal
  DB-only state. The DB never holds knowledge the markdown doesn't.
- **Decision-17 (deterministic plumbing):** the LLM-shaped skills carry **no `import anthropic`** —
  Python does retrieval/validation/filing in a `prepare`/`apply` contract; the orchestrator owns
  the reasoning step. Every CLI emits one JSON envelope + a stable exit code.
- **Schema = `user_version 7`** (`sql/wiki-index-v2.sql`). A bump is a Class-B rebuild, never an
  in-place ALTER. Default posture is **zero-DDL** (ride `frontmatter_json` + existing columns).
- **Config-driven layouts:** per-vault *identity* (`config_loader.py`) is distinct from per-layout
  *grammar* (`layout_config.py` + `layouts/*.yaml`).
- **Vendor-agnostic (NF-1):** features work identically under any LLM CLI (Claude / Codex / Gemini /
  pi / hermes). The `wiki-*` + `obsidian-active-note` binaries are on `PATH`; skills are
  `SKILL.md` + frontmatter any agent reads; no vendor SDK in the plumbing.

## How to operate the wiki / Obsidian from here
- Knowledge lookup: prefer **`wiki-search <vault> "query"`** over grep+Read, and over raw SQL or
  `find`/`grep` to locate a note (use the hit's `file_path`; the column is `file_path`, not
  `source_path`). Especially unreliable in iCloud vaults.
- The on-`PATH` CLIs (`~/.local/bin/wiki-*`, `obsidian-active-note`) run from any shell.
- pi: run `bin/install-globally.sh` once → the skills land in `~/.pi/skills/` and surface as
  `/skill:wiki-search` etc. (enable `enableSkillCommands` in pi settings). `bin/install-project-symlinks.sh`
  populates `.pi/skills/` for working in this repo.

## Local development rules
- **Python**: always the `.venv/` (`python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`). Never `pip install` globally. Python **3.14** (pyenv; system 3.9 is incompatible).
- **Node.js**: local `node_modules/` only.
- **Tests**: `pytest tests/` from repo root with the venv active.
- **Type-check**: `mypy --strict scripts/` is the contract for the `scripts/` tree.
- New skills/commands/workflows live under `skills/<name>/SKILL.md`, `commands/<name>.md`,
  `workflows/<name>.md`; `bin/install-project-symlinks.sh` mirrors them into the vendor trees.

## Pointers
- `CLAUDE.md` — the full project instructions (Claude-oriented but mostly portable).
- `README.md` — overview, quick start, repo layout. · `docs/` — ADRs, `ARCHITECTURE.md`, `tasks/`,
  `manuals/`. · The current task is in `docs/TASK.md` / `docs/PLAN.md`.
