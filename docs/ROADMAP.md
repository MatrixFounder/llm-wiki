# Roadmap

What's deferred after Phase 3a, ordered by priority. Phase 3a (foundation,
DAL, core ingest, search/lint, reindex, benchmark) is **complete** —
see [TASK.md](TASK.md), [PLAN.md](PLAN.md).

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

### R-3. `wiki-extract-concepts` skill (R-18, partial) ✅ DONE 2026-05-28
**Status**: TASK 003 v2 **COMPLETE** (awaiting operator commit per
`/vdd-develop-all` no-auto-commit policy). All 15 beads shipped
(I-7.0..I-7.14) + `/vdd-multi` adversarial sweep applied 6 inline
hardenings (C-1 idempotency ordering CRITICAL, H-1 absolute-path
rejection, H-2 TOCTOU `write_concept_page` tuple-return, H-3 source_slug
kebab validation, M-1 LLM input-size + `BadRequestError` catch, M-2
schema slug regex) + 6 regression tests. **Final state**: 394 pytest /
mypy --strict clean on 55 files. 3 LOW findings deferred (see
`docs/KNOWN_ISSUES.md`).

Architectural decisions shipped:
- **Decision-15** retracts v1 Decision-9: `--manifest-stdin` /
  `--manifest-file` flags on `wiki-enrich` NOT added — in-process Python
  import replaces subprocess dispatch.
- **Decision-16** + I-7.0: `validate_manifest` + `index_from_manifest`
  + `WikiIngestError` extracted from `wiki_enrich.py` into neutral
  sub-layer module `scripts/wiki_skills/_manifest_consumer.py` so no
  skill depends on another skill. `wiki_enrich.py` re-exports for
  back-compat (one release cycle).

Active spec: [docs/TASK.md](TASK.md); v1 PAUSED snapshot archived at
[docs/tasks/task-003-wiki-extract-concepts.md](tasks/task-003-wiki-extract-concepts.md).
RTM R-30..R-43 shipped; R-44 retired; I-7.15 dropped.

LLM-driven pass over a summary page → emits candidate concept slugs,
de-dups against existing `entities` rows, proposes new `_concepts/<slug>.md`
files. After vendoring, calls vendored `wiki_ingest` Python API
in-process rather than wiki-ingest CLI via subprocess.

### R-4. Confirmed / candidate entity resolution (R-18, cybos pattern)
`entities.is_candidate = 1` for LLM-proposed entities; promotion to
`is_candidate = 0` requires operator approval (CLI: `wiki-confirm <slug>`)
or automatic on N mentions. Resolves the "Hermes" / "Hermes Agent" /
"Hermes Framework" duplication problem.

### R-5. Two-tier alias table (already in schema, needs CLI)
`entity_aliases` exists; needs:
- `wiki-alias <slug> --add "Hermes"` CLI to register aliases
- `wiki-search` updated to expand query through aliases
- `wiki-lint` to detect alias-collision (one alias → multiple slugs)

Estimated effort: P1 cluster = 2–4 weeks of focused work. High value.

---

## P1 — Epic 7 RAG layer

### R-6. `wiki-query` (R-19) — RAG over FTS5 + entity graph
Retrieve via `wiki-search` (BM25) + entity-aliased expansion → LLM
synthesis with citations. Output filed back as `_queries/<slug>.md`
(Karpathy "query → page" loop).

### R-7. `wiki-research` (R-20)
Web enrichment of concept pages. Off by default; opt-in per concept.

### R-8. `wiki-verify-multi` (R-21)
4-critic ensemble (logic, security, performance, factual) for
high-stakes query responses. Off by default. Pairs with `/vdd-multi`
infrastructure already in this repo.

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

### R-X1. Universalise layout engine (PW-A..N + PW-Q)
Replace 15 hardcoded surfaces (`PAGE_SUBDIRS`, `TYPE_MAPPING`,
`_PATH_TYPE_FALLBACK`, `_WIKILINK_RE`, slug regex, etc.) with a
YAML-config-driven parser. Three built-in layouts ship:
`karpathy.yaml` (current behaviour, byte-identical), `dev-project.yaml`
(this proposal's primary use case), `obsidian-personal.yaml` (real
iCloud vaults with numbered folders, MOC pattern, Cyrillic, `.base`
files). ~755 src + ~1220 test LoC.

**Acceptance**: all current tests pass unchanged after migration;
`trade-agents` re-indexes byte-identically modulo timestamps; new
Obsidian-personal fixture (Cyrillic, deep hierarchy, system folders)
indexes without PK collisions.

**See**: proposal §11 (full PW table, error policies, ReDoS guard).

### R-X2. Dev-vault + obsidian-personal bootstrap (Phases A-C)
Depends on R-X1. Extend `wiki-init` with `--layout {dev-project,
obsidian-personal}` flag; bootstrap obsidian-llm-wiki itself + one
peer project as first dev-vaults; wire `archive_protocol.py::archive_task()`
in agentic-development to fire `wiki-index-upsert` with `pending.log`
fallback observability. ~140 src + ~200 test LoC across two repos.

**Acceptance**: `wiki-search "ADR-002" --vaults all` returns ranked
hits with snippets; archival of a fake TASK appears in the index;
forced upsert timeout writes to `~/.cache/wiki-index/pending.log`.

**See**: proposal §§2,4,8 (Phases A-C) + §12 (Option C dependency strategy).

### R-X3. KNOWN_ISSUES → per-file migration (Phase D)
Depends on R-X1 + R-X2. One-shot splitter `scripts/migrate_known_issues_to_files.py`
(~280 src + ~200 test LoC, fixture-driven, with partial-confidence
report). After migration: `docs/issues/<id>-<slug>.md` are Class A
canonical, `docs/KNOWN_ISSUES.md` becomes Class B auto-rendered
(ADR-002 §D8 amendment required — see proposal §Phase D "Class A/B
reclassification").

**Acceptance**: `wiki-search "hash drift" --types known-issue --vaults all`
returns one specific issue, not the whole ledger; delete + re-render
produces byte-identical `docs/KNOWN_ISSUES.md`.

**See**: proposal §Phase D + ADR-002 amendment (or new ADR-003).

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
| **P-5** | Dead `idx_pages_vault_tags` JSON-expr index | Drop; add `pages_tags(vault_id, slug, tag)` join table if needed |

Trigger: real vault crosses 1k pages and operations slow down.

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

- All 34 Phase 3a tasks (TASK 001 wiki-mvp)
- Bridge skill `wiki-enrich` integrating with wiki-ingest v1.1
- 8 skills + 8 commands + 8 wrappers + global installer
- Dogfood on trade-agents (5 production bugs found + fixed +
  regression tests)
- VDD multi-adversarial + adversarial round 1 reviews (zero-slop)
- README + Installation flow for any-target-project use
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
  `SUPERSEDED → /wiki-enrich` in [TASK.md](TASK.md); RTM rows R-06.3 and
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
