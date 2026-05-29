# Project: obsidian-llm-wiki

Project-specific agent instructions. The agentic-development framework
(orchestrator prompt, skill loading protocol, pipeline phases) is imported
via `CLAUDE.local.md` → `CLAUDE.agentic.md`.

## What this project is

Multi-vault SQLite-indexed knowledge base implementing Karpathy's llm-wiki
pattern. Provides CLIs (`wiki-init`, `wiki-search`, `wiki-lint`,
`wiki-reindex`, `wiki-index-upsert`, `wiki-index-render`, `wiki-append-log`,
`wiki-enrich`, `wiki-extract-concepts`, the Epic 7 entity resolver
`wiki-confirm` / `wiki-alias` / `wiki-merge`, the Epic 7 RAG layer
`wiki-query`, and the Epic 7 RAG verification layer `wiki-verify-multi`)
over an `IndexRepository` DAL (SQLite + FTS5 + WAL).

Phase 3a complete (2026-05-26). Phase 3b: TASK 003 v2 shipped 2026-05-28;
TASK 003 v3.1 (Decision-17 deterministic refactor) shipped 2026-05-28
(commit `43812f2`); TASK 005 (Epic 7 entity resolution — R-4 confirmed/
candidate + `wiki-merge` + R-5 alias table) shipped 2026-05-29 (17 beads +
`/vdd-multi` 8-fix hardening; schema v2→v3 closes KNOWN_ISSUES L-4); TASK 006
(consolidation/hardening, schema v3→v4) shipped 2026-05-29 (`ba4fa92`);
TASK 007 (Epic 7 RAG layer — `wiki-query` R-6: retrieve→orchestrator-owned
cited synthesis→compounding `_queries/<slug>.md`) shipped 2026-05-29 (10 beads,
3 VDD gates + `/vdd-multi` ×2 + dogfood; **zero DDL**, `user_version` 4);
**TASK 008 (Epic 7 RAG verification — `wiki-verify-multi` R-8: off-by-default
4-critic prose audit of a filed answer→compounding `_verifications/verify-<slug>.md`;
FAIL=record+exit6, never mutate the answer) shipped 2026-05-29** (11 beads,
Stub-First green-throughout; 4 VDD gates incl. `/vdd-adversarial` on the plan;
**schema v4→v5** — verdict type + `verifies` ref + `verify` event; layout-agnostic
via `pages.file_path` (grep-guarded); 4 VDD gates + `/vdd-multi` post-ship
3-fix hardening — L-1 case-insensitive PASS/FAIL gate + enum validation, L-2
idempotency re-arm, L-3 vacuous-pass refusal; 672 pytest, mypy strict). No active
task at HEAD (working tree has TASK 008 uncommitted — nothing auto-committed). See
`docs/ARCHITECTURE.md`, `docs/adr/`, and the archived task/plan pairs under
`docs/tasks/` + `docs/plans/`.

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
- `docs/tasks/` + `docs/plans/` — archived task/plan pairs (no
  `docs/TASK.md` at HEAD — most recent: `task-008-wiki-verify-multi.md`
  shipped 2026-05-29; per-bead specs at `task-008-01..11-*.md`; review
  records at `docs/reviews/{task,architecture,plan,vdd-adversarial-plan,vdd-multi}-008*`;
  predecessor `task-007-wiki-query-rag.md`).
- `docs/ARCHITECTURE.md` — system architecture (multi-vault, ADRs 001+002,
  status header tracks Phase 3a/3b progress).
- `docs/KNOWN_ISSUES.md` — deferred items, including perf SEV-1 set
  flagged by `/vdd-multi` 2026-05-26.
- `docs/adr/ADR-001-wiki-ingest-integration.md` — Option I (Wrap + Index).
- `docs/adr/ADR-002-multi-vault-bottleneck-corrections.md` — vault_id
  partitioning + Class A/B/C data layering contract.
- `docs/WIKI-INGEST-V1.1-CONTRACT.md` — external `wiki-ingest` skill
  contract; consumed by `wiki-enrich` (install globally before using).
- `scripts/wiki_index/layout.py` — single source of truth for layout
  constants (`PAGE_SUBDIRS` = `INGEST_SHARED_SUBDIRS` ∪ `HOST_ONLY_SUBDIRS`
  incl. `QUERIES_SUBDIR`, `COURSE_TIER_DIR`, `SYSTEM_FILES`,
  `GLOBAL_VAULT_SENTINEL`, etc.; R-X1-forward role split per TASK 007).
