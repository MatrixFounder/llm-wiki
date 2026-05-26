# Project: obsidian-llm-wiki

Project-specific agent instructions. The agentic-development framework
(orchestrator prompt, skill loading protocol, pipeline phases) is imported
via `CLAUDE.local.md` → `CLAUDE.agentic.md`.

## What this project is

Multi-vault SQLite-indexed knowledge base implementing Karpathy's llm-wiki
pattern. Provides CLIs (`wiki-init`, `wiki-search`, `wiki-lint`,
`wiki-reindex`, `wiki-index-upsert`, `wiki-index-render`, `wiki-append-log`,
`wiki-enrich`) over an `IndexRepository` DAL (SQLite + FTS5 + WAL).

Phase 3a complete (2026-05-26). See `docs/TASK.md`, `docs/ARCHITECTURE.md`,
`docs/PLAN.md`, `docs/adr/`.

## Knowledge lookup priority

When looking up domain facts, prior decisions, or concept/entity
definitions: prefer **`/wiki-search <vault> "query"`** over grep+Read.
The wiki accumulates compounding knowledge per ADR-002 §D8 (Class A files
canonical; Class B DB rebuildable). Auto-memory at
`~/.claude/projects/.../memory/` is reserved for ephemeral per-session
state and user preferences, not domain knowledge.

## Local development rules

- **Python**: always use `.venv/` virtual environment. Never `pip install`
  globally.
  ```bash
  python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
  ```
- **Node.js**: always use local `node_modules/`. Never `npm install -g`.
- **Tests**: `pytest tests/` from repo root with the venv activated.
- **Type-check**: `mypy --strict scripts/` is the contract for the
  `scripts/` tree.
- **Python version**: 3.14.4 via pyenv (the system 3.9 is incompatible
  with `python-frontmatter`).

## Conventions (orthogonal to the framework)

- New skills/commands/workflows go under repo root: `skills/<name>/SKILL.md`,
  `commands/<name>.md`, `workflows/<name>.md`. Symlinked into
  `.claude/skills/`, `.claude/commands/`, `.agent/skills/`,
  `.agent/workflows/` for vendor compatibility.
- The repo IS the implementation, NOT a vault. Never run
  `wiki-init --scaffold-new --vault .` here — the CLI now requires an
  explicit `--vault <path>` to prevent that mistake.
- Vault artifact paths (`_sources/`, `_concepts/`, `_entities/`, `_raw/`,
  `00-Vault-Index/`, `WIKI_SCHEMA.md`, `*.db*`) are gitignored
  belt-and-braces.

## Pointers

- `README.md` — overview, quick start, external dependencies, repo layout.
- `docs/TASK.md` — current task spec (Phase-3a-complete).
- `docs/ARCHITECTURE.md` — system architecture (multi-vault, ADRs 001+002).
- `docs/KNOWN_ISSUES.md` — deferred items, including perf SEV-1 set
  flagged by `/vdd-multi` 2026-05-26.
- `docs/adr/ADR-001-wiki-ingest-integration.md` — Option I (Wrap + Index).
- `docs/adr/ADR-002-multi-vault-bottleneck-corrections.md` — vault_id
  partitioning + Class A/B/C data layering contract.
- `docs/WIKI-INGEST-V1.1-CONTRACT.md` — external `wiki-ingest` skill
  contract; consumed by `wiki-enrich` (install globally before using).
- `scripts/wiki_index/layout.py` — single source of truth for layout
  constants (`PAGE_SUBDIRS`, `COURSE_TIER_DIR`, `SYSTEM_FILES`,
  `GLOBAL_VAULT_SENTINEL`, etc.).
