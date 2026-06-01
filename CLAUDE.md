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
idempotency re-arm, L-3 vacuous-pass refusal; 672 pytest, mypy strict);
committed `49c7723`; **TASK 009 (R-9 critic-prompt hardening — scope the `wiki-verify`
4 lenses [anti-bleed] + a shared severity rubric + few-shot + the C2 `factual`-backstop;
plus a **durable, reproducible eval harness** at `skills/wiki-verify/evals/`) shipped
2026-05-30** (6 beads, Stub-First RED→GREEN; **6 gates** — task/arch/plan +
security-audit + code-review + `/vdd-multi` [2 HIGH instrument bugs fixed →
clean-pass]; **zero code/schema change**, `user_version` 5; measured baseline→enriched
delta: lens-bleed violations 10→3, false-positives 2→0, gate verdict-correctness +
recall →1.0, injection recall 100% held; **702 pytest, mypy strict**). TASK 010/011
(wiki-verify eval-v3/v4) shipped 2026-05-30..06-01. **TASK 012 (R-X1 universal
config-driven layout engine + R-X2 A-B + R-X3) — R-X1 SHIPPED + R-X2/R-X3 engine+tooling
SHIPPED 2026-06-01**: ~15 hardcoded layout surfaces replaced by a YAML-config engine
(`scripts/wiki_index/layout_config.py` + `config/layout-config.schema.yaml` + built-in
`scripts/wiki_index/layouts/{karpathy,dev-project,obsidian-personal}.yaml`); two separate
config layers (per-vault identity vs per-layout grammar); byte-identical for Karpathy
(golden anchor); stdlib-`re` ReDoS load-gate; PW-G/H/Q (KNOWN_ISSUES splitter +
auto-rendered ledger + drift lint guard); `wiki-init --layout` (5 values); **zero DDL**
(`user_version` 5; new doc types via TYPE_MAPPING tag-route). ADR-002 §D8 amended
(Class-B "rebuildable markdown"). **810 pytest (+4 skipped), mypy strict.** The operator
decision (repo-root `WIKI_SCHEMA.md` vs `docs/`-relative globs) was **RESOLVED →
`docs/`-relative** (vault_root = `<repo>/docs`, committed `docs/WIKI_SCHEMA.md`,
repo root stays vault-free); the **live** dev-vault bootstrap of THIS repo + the
KNOWN_ISSUES dogfood are **DONE** — `docs/issues/*.md` are the Class-A per-issue
sources and `docs/KNOWN_ISSUES.md` is now the auto-rendered Class-B ledger. All 17
beads (012-00..16) + the `/vdd-multi` post-ship hardening (SEC-1 egress-sanitization
of the untrusted ledger, LOG-1 delta-reindex auto-index render, perf) are **committed
`c127b4b`** (on top of the R-X1 pre-flight `4608a50`). **R-X2 Phase C
(agentic-development archive hook) deferred** (ROADMAP R-X2c); residual perf/UX items
tracked in `docs/issues/`. See `docs/ARCHITECTURE.md`
§3.5, `docs/adr/` (ADR-002 §D8 TASK-012 amendment), `docs/tasks/` (`task-012-*.md`)
+ `docs/plans/`.
**TASK 013 (R-X3-META-FILTER — `wiki-search` frontmatter metadata filter) SHIPPED
2026-06-01, committed `177fd5a`**: general repeatable `--where 'field=value'` +
`--status`/`--severity` sugar → parameterized `CAST(json_extract(frontmatter_json, ?)
AS TEXT) = ?` predicate (string-rep match → numeric `priority=1` works; hyphenated
`SEV-2` via equality, not FTS); optional query → non-FTS `(project, slug, vault_id)`
listing; injection-safe (field allowlist `[a-z][a-z0-9_]*` via `re.fullmatch`,
path+value bound, dup-field rejected, `INVALID_FILTER` never echoes value); **zero DDL**
(`user_version` 5). Full VDD pipeline + `/vdd-multi` + code-review. **TASK 014
(dogfood-fixes) SHIPPED 2026-06-01** (uncommitted on `177fd5a`): closes
**R-X1-REF-SLUGIFY** (SEV-2 — `reindex._body_refs` slugifies ref targets via the
layout's `slug_strategy` so `[[Title Case]]`/`[[Идеи]]` resolve under non-`identity`
layouts; karpathy=no-op→byte-identity; dev-vault orphans 2228→2160) + two CLI-UX
fixes (`wiki-query --vault-root` now optional/derived; `wiki-alias --list` lists the
whole vault via new `repo.list_all_aliases`). **852 pytest (+4 skipped), mypy strict.**
**TASK 015 (perf-hardening-extract-concepts) SHIPPED 2026-06-01** (uncommitted): closes
the four SEV-2 hot-path issues **H-PERF-3** (`wiki_index_upsert.upsert_one(vault_id, src,
vault_root, repo)` programmatic entry-point — no argparse-in-loop; `main()` delegates),
**P-8** (`index_from_manifest` + `dispatch_to_indexer` optional `repo`; `apply --ingest`
threads its open repo → one `make_repo`), **P-6** (`prepare --known-concepts-format
{full,slugs-only}`), **P-7** (`prepare --batch <slugs.json>` + `apply --batch-candidates
<combined.json>` — one repo reused across all entries, per-entry isolation). `apply`
factored into `_apply_validate` (no repo — input errors never touch the DB, preserving the
CWE-117 canary ordering) + `_apply_write`; `prepare` into `_load_known_and_drift` +
`_recon_single`. Hardened by **`/vdd-multi` ×2 (all critics clean)**: `sqlite3.Error` in the
per-entry catch (DB fault isolates, never crashes the batch); batch `prepare` hoists
`known_concepts`/`missing_concept_files` to the envelope top level (O(N+|known|), not
O(N·|known|) stdout — deviation from R-015-4c, recorded in TASK.md); batch `apply` loads
known once + grows the dedup set in place (O(E), not O(N·E)); idempotency-failure →
per-entry `partial`; M-2 abspath leak closed; combined.json cap 1 MiB→10 MiB. **Deferred:**
single-outer-transaction batching (SQLite nested-txn limit). **Zero DDL** (`user_version`
5). **877 pytest (+4 skipped), mypy strict.**
**TASK 016 (split-extract-concepts-module) SHIPPED 2026-06-01** (uncommitted, branch
`task-016-split-extract-concepts`): pure structural refactor — the 2174-line
`wiki_extract_concepts.py` god-module split into a **package**
`scripts/wiki_skills/wiki_extract_concepts/` (facade `__init__.py` 1071 lines +
leaves `_validation`/`_sourcing`/`_db`/`_pages`/`_errors` + `__main__.py`). **Zero
behaviour/CLI/envelope/exit-code/schema change.** The patch-target lock is preserved:
the 8 monkeypatched names (`make_repo`, `load_known_entities`, `validate_manifest`,
`index_from_manifest`, `dispatch_to_indexer`, `_apply_candidates_to_db`,
`_try_update_idempotency_state`, `update_idempotency_state`) stay rebindable at
`scripts.wiki_skills.wiki_extract_concepts.<name>` as facade globals (`_db` carve-out
for `load_known_entities`+`update_idempotency_state`); acyclic import-direction
(facade→leaves; `_errors` sink). All moved bodies byte-identical (verbatim, hash-proven
per bead); green-throughout (full VDD pipeline: task/arch/plan reviews + Sarcasmotron
per bead). **879 pytest (+4 skipped), mypy strict (69 files).** See `docs/TASK.md`,
`docs/PLAN.md`, `docs/ARCHITECTURE.md` §2.1, `docs/tasks/task-016-*.md`.

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
- **Testing & dogfooding vaults go under `samples/`** (e.g. `samples/<name>/`,
  used as `--vault-root samples/<name>`) — one known home instead of scattered
  `/tmp` vaults. `samples/` is **gitignored** (scratch tree — see `.gitignore`),
  so its `*.db*` + `_sources/`/`_concepts/`/… artifacts never get committed and
  the repo-is-not-a-vault invariant still holds. Durable, **committed** test
  fixtures (e.g. a skill's eval set) live under their owning
  `skills/<name>/evals/`, **not** `samples/`.

## Pointers

- `README.md` — overview, quick start, external dependencies, repo layout.
- `docs/tasks/` + `docs/plans/` — task/plan specs. **Current: TASK 014
  `dogfood-fixes`** (`docs/TASK.md`; closes R-X1-REF-SLUGIFY + 2 CLI-UX gaps from
  the 2026-06-01 comprehensive dogfood; done compactly — no separate `docs/PLAN.md`,
  the RTM/fix-plans are inline in TASK.md). Predecessors archived: `task-013-wiki-search-metadata-filter.md`
  (R-X3-META-FILTER, shipped `177fd5a`) + `plan-013-*`; `task-012-universal-layout-engine.md`
  (+ 17 per-bead `task-012-00..16-*.md`) + `plan-012-*`; `task-011`/`task-010`
  (wiki-verify eval-v3/v4); `task-009-wiki-verify-critic-rubric.md` (durable eval
  harness at `skills/wiki-verify/evals/` — `evals.json` + `grade.py` + `reports/`);
  `task-008-wiki-verify-multi.md`.
- `docs/ARCHITECTURE.md` — system architecture (multi-vault, ADRs 001+002,
  status header tracks Phase 3a/3b progress).
- `docs/KNOWN_ISSUES.md` — **auto-rendered Class-B ledger** (TASK 012 / R-X3) over
  the per-issue Class-A sources in `docs/issues/*.md`. Regenerate with
  `wiki-index-render --auto-indexes`; a manual edit is flagged by `wiki-lint`
  (PW-Q drift guard). Holds the deferred items (perf SEV-1 set, the R-X1-*
  residuals, R-X3-META-FILTER). Edit the per-issue files, never the ledger.
- `docs/adr/ADR-001-wiki-ingest-integration.md` — Option I (Wrap + Index).
- `docs/adr/ADR-002-multi-vault-bottleneck-corrections.md` — vault_id
  partitioning + Class A/B/C data layering contract.
- `docs/WIKI-INGEST-V1.1-CONTRACT.md` — external `wiki-ingest` skill
  contract; consumed by `wiki-enrich` (install globally before using).
- `scripts/wiki_index/layout.py` — single source of truth for the **karpathy**
  layout constants (`PAGE_SUBDIRS` = `INGEST_SHARED_SUBDIRS` ∪ `HOST_ONLY_SUBDIRS`
  incl. `QUERIES_SUBDIR`, `COURSE_TIER_DIR`, `SYSTEM_FILES`,
  `GLOBAL_VAULT_SENTINEL`, etc.; R-X1-forward role split per TASK 007). Since
  TASK 012 these are *projected into* `layouts/karpathy.yaml` but stay the source
  of truth (byte-identity anchor); they are NOT superseded by the engine below.
- `scripts/wiki_index/layout_config.py` — **TASK 012 / R-X1 config-driven layout
  engine** (`LayoutConfig`, `iter_pages`, `resolve_layout_config`, ReDoS load-gate);
  built-in layouts at `scripts/wiki_index/layouts/{karpathy,dev-project,obsidian-personal}.yaml`;
  schema `config/layout-config.schema.yaml`. The per-layout *grammar* layer,
  separate from the per-vault identity `config_loader.py` (two-systems split).
