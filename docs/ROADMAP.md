# Roadmap

What's deferred after Phase 3a, ordered by priority. Phase 3a (foundation,
DAL, core ingest, search/lint, reindex, benchmark) is **complete** (see
[ARCHITECTURE.md](ARCHITECTURE.md) status header). Phase 3b: TASK 004
shipped 2026-05-27 (R-V1); TASK 003 v2 shipped 2026-05-28 (R-3 v1+v2);
TASK 003 v3.1 shipped 2026-05-28 commit `43812f2` (Decision-17
deterministic refactor + post-ship `/vdd-multi` 22-finding hardening).
No active task at HEAD — archived specs under [tasks/](tasks/) +
[plans/](plans/).

Status legend:
- **P0** — start when there is a concrete trigger / pain
- **P1** — natural next step; medium effort
- **P2** — useful, larger scope, no urgent driver
- **P3** — situational / wait-for-need

---

## P0 — Active blockers

_(none — R-V1 closed 2026-05-27, R-3 closed 2026-05-28; see Done entries below.)_

### R-V1. wiki-ingest vendoring (Option 5 — Python-import vendor) ✅ DONE 2026-05-27
Promoted from P3 → P0 on 2026-05-27 after operator-confirmed target
**self-contained product / publication** (PyPI / GitHub plugin / Claude
Code plugin marketplace). External `wiki-ingest` dep blocks single-step
install for end-users.

**Chosen approach** (from brainstorming 2026-05-27 — operator owns both
repos, no licensing concerns): **Option 5 Python-import-only vendor**.
Copy `Universal-skills/skills/wiki-ingest/scripts/wiki_ingest/` Python
module into `obsidian-llm-wiki/scripts/wiki_ingest/`; refactor
`wiki_ops.py` `ingest` subcommand to expose a programmatic
`ingest(source, vault_root, vault_id, …) → manifest_dict` function;
replace `subprocess.run(["wiki-ingest", …])` in `wiki_enrich.py` with
direct Python call; keep `--source` CLI flag for backward compat
(external `wiki-ingest` continues to work if installed); drop
`check_wiki_ingest_version` from the in-process path; add
`scripts/sync_wiki_ingest.sh` for periodic snapshot refresh.

**Standalone `wiki-ingest` preserved** in `Universal-skills` for
"simple wiki" users — operator-stated requirement. Both paths
co-exist.

**Tracking task**: TASK 004 `wiki-ingest-vendoring` — **COMPLETE** 2026-05-27.
All 11 beads shipped + `/vdd-multi` adversarial sweep applied 6 hardening
fixes inline (LICENSE-upstream rsync exclude, narrowed exception catch,
truthy env-var parsing, full primary-path PARTIAL_INDEX_FAILURE envelope,
absolute-path rejection, hex-case-insensitive regex). 328 pytest /
mypy strict clean. Self-contained product publication path unblocked.

**Why this is P0 now**: self-contained publication path cannot ship
with subprocess + PATH dependency on a separate repo. Downstream
benefit: TASK 003's manifest-dispatch problem (originally Decision-9
`--manifest-stdin` flag on `wiki-enrich`) is now solved by direct
in-process Python function calls — see TASK 003 v2 / Decision-15
(retracts Decision-9) and Decision-16 (neutral `_manifest_consumer`
module).

**Why not just keep external dep**: operator stated 1-3 month target
of self-contained product / publication. Two-step install (clone two
repos + symlink `wiki-ingest` to `~/.local/bin`) is unfriendly for
end-users via PyPI or plugin marketplaces.

**Effort**: ~1 week focused work (well-bounded refactor: copy module +
extract programmatic API + update one consumer + tests).

---

## P0 — Cleanup (small, do when convenient)

_(R-1 done in commit `81b7aff`; R-2 superseded by R-X4.)_

### R-2. Subagent prompt hook (memory 4b leftover) — SUPERSEDED → R-X4
Inject "before editing concepts or introducing new names, call
`/wiki-search`" into `developer`, `architect`, `critic-*` agent prompts.
The parent CLAUDE.md already carries the rule; this is a proactive cue
for narrow-context subagents.

**Status (2026-05-27)**: Superseded by **R-X4** (Phase E of the
cross-project indexing proposal — see P2 section below). Same scope,
broader context: R-X4 wires the prompt cue *and* the index it would
query against. Track R-X4, retire R-2.

---

## P1 — Epic 7 entry-point: entity resolver

The Karpathy compounding-artifact promise lives here. Currently a single
ingest touches one source page + index + log (~3 pages); Karpathy says
10–15. Closing that gap requires the entity layer.

### R-3. `wiki-extract-concepts` skill (R-18, partial) ✅ DONE 2026-05-28 (v2 + v3.1)
**Status**: SHIPPED. Both v2 (LLM-call inside skill, 396 pytest) and v3.1
(Decision-17 deterministic refactor: synthesis moved to orchestrator,
LLM call deleted, anthropic dep dropped, 450 pytest + 22-finding
`/vdd-multi` hardening) closed 2026-05-28. See full ship summary in
**Done since 2026-05-25** below; archived specs at
[docs/tasks/task-003-v3.1-wiki-extract-concepts.md](tasks/task-003-v3.1-wiki-extract-concepts.md)
(v3.1), [docs/tasks/task-003-v2-wiki-extract-concepts.md](tasks/task-003-v2-wiki-extract-concepts.md)
(v2), [docs/tasks/task-003-wiki-extract-concepts.md](tasks/task-003-wiki-extract-concepts.md)
(v1 paused snapshot).

Architectural decisions shipped:
- **Decision-15** (v2) retracts v1 Decision-9: `--manifest-stdin` /
  `--manifest-file` flags on `wiki-enrich` NOT added — in-process Python
  import replaces subprocess dispatch.
- **Decision-16** (v2) + I-7.0: `validate_manifest` +
  `index_from_manifest` + `WikiIngestError` extracted from
  `wiki_enrich.py` into neutral sub-layer module
  `scripts/wiki_skills/_manifest_consumer.py` so no skill depends on
  another skill.
- **Decision-17** (v3.1): Python skills are deterministic plumbing; LLM
  synthesis lives in the calling agent's context (Claude Code / Gemini
  CLI / Cursor). `wiki-extract-concepts` split into `prepare` + `apply`
  subcommands; calling agent runs `Skill({skill: "concept-extraction"})`
  + `Read(source_path)` + own-context synthesis between the two CLI
  calls. **BREAKING CHANGE**: legacy single-command invocation rejected
  at argparse.

### R-4. Confirmed / candidate entity resolution (R-18, cybos pattern) ✅ DONE 2026-05-29 (TASK 005)
`entities.is_candidate = 1` for LLM-proposed entities; promotion to
`is_candidate = 0` via operator approval (`wiki-confirm <slug>`) or
`wiki-confirm --auto --threshold N` (default 3). `is_candidate` is now Class A
(frontmatter) round-tripped through `wiki-reindex --full` (R-4.1, was silently
reset). `resolve_entity` resolves slug-or-alias; `find_orphan_links` is
alias-aware. **`wiki-merge <from> <into>`** (R-4.7) folds the "Hermes / Hermes
Agent / Hermes Framework" duplicates into one canonical entity (the alias table
is the durable redirect; reindex canonicalizes refs — AM-3).

### R-5. Two-tier alias table ✅ DONE 2026-05-29 (TASK 005)
`entity_aliases` activated: PK fixed to `(vault_id, alias)` (closes **L-4**;
schema v2→v3); `wiki-alias <slug> --add/--remove/--list` writes Class A
frontmatter + DB mirror; `wiki-reindex --full` mirrors `aliases:` frontmatter
(report-and-skip on collision); `wiki-search` expands queries through aliases
by default (`--no-expand-aliases` opt-out); `wiki-lint` detects alias collisions
(in-DB + cross-table + Class A frontmatter scan; `--strict` advisory exit).

**Shipped**: TASK 005 (17 beads, Stub-First, green-throughout). See archived
spec/plan at [tasks/task-005-*.md](tasks/) + [plans/plan-005-*.md](plans/) and
the §D8 durability acceptance (UC-14/UC-15) in
`tests/test_entity_resolution_durability.py`. **Unblocks R-X5** (cross-project
entity graph, gated on Epic 7).

---

## P1 — Epic 7 RAG layer

### R-6. `wiki-query` (R-19) — RAG over FTS5 + entity graph ✅ DONE 2026-05-29 (TASK 007)
Retrieve via `wiki-search` (BM25) + entity-aliased expansion → **orchestrator-
owned** LLM synthesis with citations (Decision-17 `prepare`/`apply` split; no
`import anthropic`) → output filed back as `_queries/<slug>.md`, a **first-class
compounding page** (indexed `type=query`, FTS-searchable, `cited` backlinks,
§D8-durable via the R-6.5e reindex read-side). Grounding enforced in Python
(`NO_CONTEXT` refusal + `CITATION_NOT_RETRIEVED` keyed on `project/slug`).
**Zero schema DDL** (`pages.type='query'`, `ref_type='cited'`,
`event_type='query'`, generic `source_state` all pre-existed; `user_version`
stays 4); two code-only changes — `layout.py` `_queries` (R-X1-forward role split
`INGEST_SHARED_SUBDIRS`/`HOST_ONLY_SUBDIRS`) + the reindex `cites:`→`'cited'`
read-side. **Shipped**: TASK 007 (10 beads, Stub-First green-throughout; 3 VDD
gates APPROVED). See archived spec/plan at [tasks/task-007-*.md](tasks/) +
[plans/plan-007-*.md](plans/).

### R-7. `wiki-research` (R-20) — UNBLOCKED (gated on R-6, now shipped)
Web enrichment of concept pages. Off by default; opt-in per concept. Layers on
the `wiki-query` retrieval/synthesis loop (R-6) — now shipped, so R-7 is
unblocked. Needs a web-access design (overlaps `deep-research`); still
**off-by-default** + a separate TASK.

### R-8. `wiki-verify-multi` (R-21) ✅ DONE 2026-05-29 (TASK 008)
Off-by-default multi-critic verification of a filed `wiki-query` answer against
its cited sources. Recast for prose (D-008-2): four critics — **factual-grounding,
logic-coherence, security-injection, completeness-faithfulness** (the ROADMAP's
"performance" lens dropped as a non-fit for prose). Decision-17 `prepare`/`apply`
(no `import anthropic`; the four-critic audit lives in the orchestrator via the
`wiki-verify` prompt skill, optionally fanned out via `Agent` Layer-A like
`/vdd-multi`). Verdict filed as a **first-class compounding** `_verifications/verify-<slug>.md`
page (`type=verification`, `verifies` backlink, §D8-durable via the R-8.5e reindex
read-side that generalises R-6.5e). **FAIL = record verdict + non-zero exit (6) +
NEVER mutate the Class-A answer** (D-008-3); the authoritative PASS/FAIL is the
Python `--fail-on` rule (default `high`), not the LLM's self-report. **Layout-agnostic**
by construction (reads the answer + cited sources via `pages.file_path`; grep-guarded
— C-8/NFR-7), so R-X1/R-X2-forward. **First RAG-layer task requiring DDL — schema
v4→v5** (`pages.type+='verification'`, `ref_type+='verifies'`, `event_type+='verify'`,
`index_meta` parity; Class-B reindex migration). **Shipped**: TASK 008 (11 beads,
Stub-First green-throughout; 4 VDD gates incl. `/vdd-adversarial` on the plan;
one found-in-dev serious-deviation fixed — verdict↔query `pages` PK collision →
`verify-<slug>` distinct slug). See archived spec/plan at [tasks/task-008-*.md](tasks/)
+ [plans/plan-008-*.md](plans/). Pairs with `/vdd-multi`.

---

## P2 — Cross-project indexing

Design doc: [`docs/proposals/indexing-agentic-dev-artifacts.md`](proposals/indexing-agentic-dev-artifacts.md)
(2026-05-27, 1259 lines, /vdd-adversarial PASS).

Total scope: ~815 source + ~1300 test = **~2115 LoC** across two repos,
~2.5-3 week focused task. Tier-trimmed delivery available — see proposal
§13 "Honest-scope tier".

**Trigger to start** (per proposal §13 + §14): operator runs `git grep`
across 3+ repos for the same concept twice in a session, OR wants to
answer "where in my Obsidian vault did I write about X?" and Obsidian's
search is too slow. Until then, status = PROPOSAL.

### R-X1. Universalise layout engine (PW-A..N + PW-Q) ✅ DONE 2026-06-01 (TASK 012)
Replaced the 15 hardcoded surfaces with a **YAML-config-driven engine**
(`scripts/wiki_index/layout_config.py` + `config/layout-config.schema.yaml` +
built-in `scripts/wiki_index/layouts/{karpathy,dev-project,obsidian-personal}.yaml`).
**Two separate config layers** (D-012-2): the existing per-vault identity config
is untouched; the new layer carries per-layout-class grammar. `flat`/`per-project`
alias → `karpathy`. **Byte-identical for Karpathy** (golden-snapshot anchor +
`test_karpathy_config_matches_layout_constants`; `identity` slug strategy; three
slug surfaces kept distinct). **ReDoS = stdlib `re` + load-time budget gate**
(D-012-3, covers `ref_extraction` + `project_pattern`; no new dependency). PW-G/H/Q
engine shipped too (auto_indexes render + KNOWN_ISSUES splitter + lint guard).
**Zero DDL** (`user_version` stays 5; new doc types via the TYPE_MAPPING tag-route).
Architecture-review caught + fixed a real fifth-walk PK-drift bug (`find_pages_missing_in_index`,
C1). **Shipped**: beads 012-00..010 (Stub-First green-throughout; task/architecture/plan
gates APPROVED; per-bead Roast). See `docs/tasks/task-012-*.md` + ADR-002 §D8 TASK-012
amendment. **See**: proposal §11.

### R-X2. Dev-vault + obsidian-personal bootstrap (Phases A-B) ✅ DONE 2026-06-01 (TASK 012)
Depends on R-X1 (done). `wiki-init --layout {flat,per-project,karpathy,dev-project,
obsidian-personal}` shipped (012-13; dev/obsidian layouts skip the Karpathy
page-subdir scaffold). Bootstrap + cross-project capability acceptance-tested
end-to-end (012-14/15). **Operator decision RESOLVED (2026-06-01): option (b)** —
`dev-project.yaml` globs are `docs/`-root-relative and **vault_root = `<repo>/docs`**,
so the committed dev-vault declaration is `docs/WIKI_SCHEMA.md` and the repo root
stays vault-free ("repo is not a vault" preserved; no gitignore change). This repo
was **live-bootstrapped** as `obsidian-llm-wiki` (270 pages indexed) and the R-X3
KNOWN_ISSUES dogfood ran on it.

> **OPERATOR FOLLOW-UPS (dogfood friction, not blockers):**
> 1. **Local vs global DB.** The live index lives in a **gitignored `.wiki/index.db`**
>    (self-contained; used to render the ledger). `wiki-search` defaults to the GLOBAL
>    DB (`~/Library/Application Support/wiki-index/global.db`), which does NOT contain
>    this repo — so a bare `wiki-search "X"` finds nothing here. Until you register
>    globally, the correct command is:
>    `wiki-search "<q>" --vaults obsidian-llm-wiki --db-path .wiki/index.db`.
>    To make daily/cross-project search "just work", run once:
>    `wiki-init --register-existing --vault docs` (+ `wiki-reindex --full`) against the
>    global DB. (Deliberately not done automatically — it writes to the global user DB.)
> 2. ~~**Frontmatter metadata isn't FTS-filterable** (`status`/`severity`)~~ —
>    ✅ **FIXED 2026-06-01 (TASK 013, R-X3-META-FILTER).** `wiki-search --status
>    open --severity SEV-2 --vaults <vid>` (general `--where 'field=value'` +
>    `--status`/`--severity` sugar) now compiles to a parameterized `json_extract`
>    predicate; query optional for a pure metadata listing. See R-X3-META-FILTER
>    below + `docs/tasks/task-013-*.md`.

**See**: proposal §§2,4,8 (Phases A-C) + §12.

### R-X2c. Archive-hook integration (Phase C) — DEFERRED (operator decision D-012-4, 2026-06-01)
Split out of R-X2. Wire `agentic-development/.agent/tools/archive_protocol.py::archive_task()`
to fire `wiki-index-upsert` (feature-detected shell-out + `~/.cache/wiki-index/pending.log`
observability, behind an `enable_wiki_index` flag — proposal §12 Option C). **Deferred
on purpose: stabilise + dogfood the wiki first, then extend to the framework.** This is a
CROSS-REPO change (separate branch/commit in agentic-development, with its tests there);
no compile coupling either direction. **Trigger**: the wiki is in daily dev use + the
R-X2 live bootstrap decision (above) is made. **See**: proposal §12.

### R-X3. KNOWN_ISSUES → per-file migration (Phase D) ✅ ENGINE+SPLITTER DONE 2026-06-01 (TASK 012); live migration held with R-X2 bootstrap
Depends on R-X1 + R-X2. `scripts/migrate_known_issues_to_files.py` shipped (012-11):
parses THIS repo's `## [date] <id> <title> [STATUS]` ledger format into per-issue
Class-A files with verbatim bodies + a partial-confidence `.migration-report.md`
(flag, never drop). **Validated on the real 743-line `docs/KNOWN_ISSUES.md`** (012-12
test): all 50 issues split with count parity + no empty bodies; 2 flagged for review
(`N-008-1` unknown prefix, `D-010-2` unusual status). The auto-rendered ledger (PW-H)
+ drift lint guard (PW-Q) are shipped + tested (rebuildability byte-identical modulo
GENERATED-AT; `id` tiebreaker; sha256 in `.wiki/state.json`). The **live on-disk
migration** of this repo (write `docs/issues/*.md` + replace the prose ledger with the
rendered index) is **held with the R-X2 live-bootstrap decision** (the render needs the
repo registered as a dev-vault) — the operator runs it once that's decided + reviews the
report. ADR-002 §D8 amended for the Class-B "rebuildable markdown" sub-case.

**Acceptance**: `wiki-search "hash drift"` returns one specific issue (`known-issue`
is a frontmatter *tag*, not a `pages.type`, so `--types known-issue` is a no-match —
filter issues via `--status`/`--severity`, or FTS the body as here); delete +
`wiki-index-render --auto-indexes` reproduces byte-identical `docs/KNOWN_ISSUES.md`
(modulo GENERATED-AT). **See**: proposal §Phase D + ADR-002 §D8 amendment.

### R-X4. Agent-prompt cue integration (Phase E) — supersedes R-2
Add proactive `/wiki-search` cue to `developer` / `architect` /
`critic-*` subagent prompts in agentic-development. Same scope as
the original R-2, but landed *after* R-X2 so the prompted index
actually exists. **Priority: P3** — blocked on agentic-development
memory-strategy decision (separate project).

**See**: proposal §Phase E.

### R-X5. Entity-graph cross-project (Phase F)
Depends on **Epic 7 (R-3..R-5 entity resolver)** + R-X2. Concept /
entity nodes for development artifacts become first-class; `wiki-graph`
traversals across project artifacts; RAG-style synthesis ("meta-ROADMAP
consolidating all P0 items across active projects"). Also closes the
proposal §7.6 verification item (cross-vault `entity_slug` FK semantics).
**Priority: P3** — multi-week, separate TASK, gated on Epic 7.

**See**: proposal §Phase F + §7.6.

---

## P2 — Epic 6 multi-source ingestion

Each adapter is a self-contained sub-project; do them one at a time
when a real source pipeline appears.

| Adapter | Source | Spec status |
|---|---|---|
| `wiki-source-email` | IMAP / MS Graph | spec only |
| `wiki-source-telegram` | TS GramJS (`scripts/wiki_telegram/`) | spec only |
| `wiki-source-web` | Article extraction + research mode | spec only |
| `wiki-brief` | Cross-source daily digest | spec only |

Picking the first depends on what stream of knowledge actually flows
through. For most operators: **telegram** (channels with curated lessons)
or **email** (newsletters). Web is a different beast — overlaps with
`wiki-research`.

---

## P2 — Performance hardening

All five are documented in [KNOWN_ISSUES.md](KNOWN_ISSUES.md). They pass
at N=100 (current default benchmark) but flag risk at 10k pages.

| ID | Issue | Mitigation |
|---|---|---|
| **P-1** | `reindex_full`: N transactions, no batching | Bulk-tx + temporary FTS5 trigger drop |
| **P-2** | `reindex_delta`: full filesystem walk on no-op | mtime/size short-circuit |
| **P-3** | `check_drift`: re-hashes every file | mtime/size first-pass; streaming hash |
| **P-4** | Benchmark default `n=100` only | CI mode with `--scale all --enforce-slos` |
| **P-5** | ~~Dead `idx_pages_vault_tags` JSON-expr index~~ ✅ DONE 2026-05-29 (TASK 006, schema v4) | Dropped. |

Trigger: real vault crosses 1k pages and operations slow down.

> **TASK 006 (consolidation/hardening) shipped 2026-05-29** — schema **v3→v4**
> (drop dead `idx_pages_vault_tags` P-5 + `event_date` GENERATED L-2; `'log'`
> enum L-5 already-absent), reindex name fallback (L-8), `_recompute_mentions`
> dedup (F12c), `wiki-lint` frontmatter scan from `pages.frontmatter_json`
> (P-10+F12b — removes a 2nd O(N) YAML sweep), + doc clarifications (L-1/6/7).
> Scale-gated perf (P-1/2/3/4/6/7/8/9/11, H-PERF-3) + threat-gated security
> (D-1/D-2/H-5/H-6/Q17) remain deferred with their triggers. See
> `docs/tasks/task-006-*.md`.

---

## P3 — Security & robustness

### R-9. D-2: R-26 enforcement on operator-supplied output paths
`wiki-lint --report <path>`, `wiki-index-render --output <path>`,
`wiki-lint --json-sidecar <path>` — currently accept any path.

**Trigger**: threat model changes to multi-tenant / untrusted operator.
Until then, operator-trusted scope is fine.

### R-10. D-1: `assert_no_symlink_escape` Unix-effective coverage
Current implementation walks `Path.parent` lexically; the escape check
(`is_relative_to(anchor)`) can't trigger on Unix (anchor = `/`). Either
upgrade to an FD-based mediated walk or document the limit and remove
the misleading docstring.

---

## P3 — Operational polish

- ~~**wiki-ingest vendoring**~~ — **promoted to P0 as R-V1** on 2026-05-27.
- **Postgres backend** — `IndexRepository` ABC was designed for this.
  Trigger: corpus > 100k pages, or multi-writer concurrency.
- **wiki-graph** export — emit graphviz / mermaid of entity links for
  Obsidian Graph View parity.
- **CI workflow** for benchmarks — wire `bench --enforce-slos` into a
  GitHub Action (currently runs locally only).

---

## Open questions

- **Does Epic 7 happen here or in a separate repo?** Entity resolver
  + RAG might warrant its own project once it grows.
- **Wiki adoption pattern**: do we expect operators to dogfood `wiki-*`
  themselves, or is the primary user a sub-agent calling these tools?
  Affects how aggressive auto-memory integration becomes.
- **Vault discoverability**: should there be a `wiki-list-vaults`
  command? Useful for cross-vault search when operator forgets vault_ids.

---

## Done since 2026-05-25

- **TASK 013 (R-X3-META-FILTER) — 2026-06-01.** `wiki-search` frontmatter metadata
  filter (Cluster C / daily-use enablement). General repeatable `--where 'field=value'`
  + `--status`/`--severity` sugar → parameterized `json_extract(frontmatter_json, ?)`
  predicate; optional query → non-FTS `(project, slug)`-ordered listing. Injection-safe
  (field allowlist `^[a-z][a-z0-9_]*$` at CLI + DAL; path + value bound; `INVALID_FILTER`
  never echoes value). **Zero DDL** (`user_version` 5). Full VDD pipeline (Analysis →
  Architecture Q-013-a..d → Plan → 4 beads Stub-First). Live dogfood: `--status open
  --severity SEV-2` returns the 5 open SEV-2 issues; R-X3-META-FILTER flipped to `fixed`
  + ledger auto-re-rendered (PW-Q drift-clean). 833 pytest (+4 skipped), mypy strict.
  See `docs/tasks/task-013-*.md`.
- **TASK 012 (R-X1 + R-X2 A-B engine + R-X3 engine) — 2026-06-01.** Universal
  config-driven layout engine: 17-bead plan (012-00..16), full VDD pipeline gated
  (task/architecture/plan reviews APPROVED — architecture-review caught a real C1
  fifth-walk PK-drift bug). R-X1 (012-00..07) committed; 012-08..16 on the working
  tree. Two separate config layers; 3 built-in layouts; karpathy byte-identical
  (golden anchor); stdlib-`re` ReDoS gate; PW-G/H/Q; `wiki-init --layout`; zero DDL.
  803 pytest, mypy strict (63 files). Live dev-vault bootstrap + KNOWN_ISSUES dogfood
  held on the R-X2 operator decision; R-X2c (archive hook) deferred.
- All 34 Phase 3a tasks (TASK 001 wiki-mvp)
- Bridge skill `wiki-enrich` integrating with wiki-ingest v1.1
- 8 skills + 8 commands + 8 wrappers + global installer (now 9 after R-3)
- Dogfood on trade-agents (5 production bugs found + fixed +
  regression tests)
- VDD multi-adversarial + adversarial round 1 reviews (zero-slop)
- README + Installation flow for any-target-project use
- **R-3 / TASK 003 v2 closed 2026-05-28** — `wiki-extract-concepts` Epic 7
  entry-point shipped. LLM-driven concept extraction (Claude Sonnet 4.6,
  `temperature=0`); kebab-validated slugs; `_concepts/<slug>.md` atomic
  writes; `entities` rows with `is_candidate=1` + SQL `MIN()` downgrade
  guard (R-37b); `page_entity_refs` with `trust_level='medium'` and
  parsed `Lstart-Lend` line spans (Decision-10); source-state idempotency
  short-circuit (R-39). Decisions 15 (in-process dispatch retracts v1
  Decision-9 subprocess+CLI-flag) + 16 (neutral `_manifest_consumer`
  module — no skill depends on another skill) shipped. 15 atomic beads
  (I-7.0..I-7.14) + `/vdd-multi` adversarial sweep with 6 inline hardenings
  (C-1 idempotency ordering, H-1 absolute-path rejection, H-2 TOCTOU
  tuple-return, H-3 source_slug validation, M-1 LLM input-size +
  BadRequestError catch, M-2 schema slug regex) + 3 deferred LOWs closed
  inline (L-V3.1 datetime hoist, L-V3.2 NULL defensive check, L-V3.3
  CWE-209 exception-chain suppression). 396 pytest / mypy --strict clean
  on 55 files. R-44 retired, I-7.15 dropped.
- **R-3 / TASK 003 v3.1 closed 2026-05-28** (commit `43812f2`) —
  `wiki-extract-concepts` **deterministic refactor** per Decision-17
  + Option A green-throughout invariant + post-ship `/vdd-multi`
  22-finding hardening landed in the same commit. **19 beads shipped**
  via `/vdd-develop-all` (Phase -1: 11a; Phase 0: 00; Phase 1: 01-06;
  Phase 2: 07-10; Phase 3: 11-12; Phase 4: 13-17). Skill split into two
  subcommands: `prepare` (recon + idempotency + missing-concept-files
  drift sweep via `os.scandir`) + `apply` (consume operator-synthesised
  candidates JSON + write pages + upsert entities + manifest + optional
  in-process indexer dispatch). LLM call deleted; `import anthropic`
  removed; `anthropic>=0.34.0` dropped from `requirements.txt`.
  - **v3.1 surface**: strict candidates validator (count bound 1–25,
    per-field caps, strict-equality on keys, optional quote-in-body
    check, L-1 type-coverage on slug/source_span/entity_type, L-2
    `re.ASCII` on span regex); sub-envelopes with CWE-117/CWE-209
    invariant (no offending value echoed; parametrized regression test
    `test_apply_error_envelopes_never_echo_content` enforces);
    `_sanitize_markdown_text` text-only allowlist for concept-page body
    (HTML-escape `&<>`, escape `[]` + backticks + leading-line markdown
    actives — closes javascript-link / data-URI / HTML-entity-smuggling
    / Obsidian-wikilink / dataview injection vectors); content-hash
    skip semantics in `write_concept_page` (via `os.open(O_NOFOLLOW)`
    for the existing-file read); symlink refuse on target;
    `--source-hash` argparse `type=` validator (64-lowercase-hex);
    `_sources/` layout invariant (no traversal escape to other vault
    subdirs); cross-platform `_path_is_absolute()`; bounded
    `_read_file_bounded(O_NOFOLLOW + fstat)` for source + candidates
    reads; FIFO/device/socket guard on `--candidates-file`;
    sanitization pre-flight (no partial commits on mid-loop sanitize
    failure); `update_idempotency_state` wrapped in
    `try/except sqlite3.OperationalError` → new
    `IDEMPOTENCY_UPDATE_FAILED` envelope (exit 5, preserves C-1
    retry-safety); logger warning on default `--orchestrator-id`.
  - **New exit-code envelopes** (vdd-multi-fix): `INVALID_SOURCE_HASH`
    (exit 2, C-1 library-caller defense), `INVALID_SOURCE_SPAN` (exit
    4, M-4 sanitization pre-flight), `IDEMPOTENCY_UPDATE_FAILED` (exit
    5, H-3 DB-lock graceful path).
  - **Final gate**: 450 pytest pass + 4 skipped, mypy --strict clean
    (55 files), anthropic-free invariant clean, patch-target lock clean.
  - **Architectural follow-ups deferred** to
    [docs/KNOWN_ISSUES.md](KNOWN_ISSUES.md): **H-PERF-3** (SEV-2 —
    `_manifest_consumer` argparse-in-loop N+1; needs
    `wiki_index_upsert` programmatic entry-point), **H-5**
    (`concept-extraction/SKILL.md` hash-pin enforcement), **H-6**
    (indirect prompt-injection canary scanning),
    **P-8** (two-process WAL setup cost — bumped SEV-3 → SEV-2 after
    counting `--ingest`-path connection cycles), **L-4** (`>=` deps
    unpinned; add `pip-compile` lockfile + `pip-audit` to CI).
  - **BREAKING CHANGE**: legacy single-command CLI invocation no longer
    accepted; argparse routes to `prepare` / `apply` subparsers and
    errors out with a helpful pointer on missing subcommand.
- **R-V1 / TASK 004 closed 2026-05-27** — wiki-ingest Python-import-only
  vendor (Option 5). `scripts/wiki_ingest/` snapshot from
  `Universal-skills/skills/wiki-ingest/`; `scripts/wiki_skills/wiki_enrich.py`
  refactored to in-process primary path + subprocess fallback (gated by
  `WIKI_ENRICH_NO_VENDORED` env var, accepts case-insensitive
  `{1, true, yes, on}` after `/vdd-multi` H-3 fix). `mypy.ini` package
  override silences ~190 vendored typing errors per Decision-14 time-box.
  `scripts/sync_wiki_ingest.sh` snapshot refresh with SHA256 divergence
  check and `LICENSE-upstream` preservation (Apache 2.0 §4). 11 atomic
  beads + 6 `/vdd-multi` hardening fixes + 33 new tests. Publication
  path (PyPI / GitHub plugin / Claude Code marketplace) unblocked.
- **R-1 closed 2026-05-27** (commit `81b7aff`) — UC-06/UC-07 marked
  `SUPERSEDED → /wiki-enrich` in [TASK 002 wiki-mvp](tasks/task-002-wiki-mvp.md); RTM rows R-06.3 and
  R-24 carry the status, Use Case bodies retain SUPERSEDED banners with
  historical spec preserved.
- **R-0 closed 2026-05-27** — wiki-ingest v1.1 contract alignment.
  Universal-skills shipped `wiki-ingest 1.1.0`; bridge smoke against a
  clean temp vault returns `{"action":"enriched", "index":{"upserted":[1
  source page], "log_event_id":N}}` exit 0. End-to-end smoke also
  surfaced an integration bug in this repo (`wiki_enrich.index_from_manifest`
  was routing top-level system files `index.md`/`log.md` through page-upsert
  and tripping `UnmappedTypeError`); fixed by a top-level-only
  `SYSTEM_FILES` filter (Class B/C per ADR-002 §D8 — `index.md` is a
  `wiki-index-render` projection, `log.md` is mirrored via `log_event`).
  Two regression tests guard the filter incl. false-positive subdir
  namesakes (`_concepts/index.md` etc.). 295 pytest passed, mypy strict
  clean.
