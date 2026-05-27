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

### R-0. wiki-ingest v1.1 release ⏳ EXTERNAL DEPENDENCY
The `/wiki-enrich` bridge is built and unit-tested against
[docs/WIKI-INGEST-V1.1-CONTRACT.md](WIKI-INGEST-V1.1-CONTRACT.md) §1
(JSON manifest from `ingest --output-format json`).

**Current state (2026-05-27 smoke check)**: installed wiki-ingest reports
`version: 1.0` and provides only atomic operations (`upsert-page`,
`register-summary`, `update-index`, `append-log`). The orchestrator
`ingest` subcommand that emits a manifest is **not yet released**.

**Bridge behaviour**: wiki-enrich correctly fails fast with envelope
`{"error":"WIKI_INGEST_FAILED", "message":"wiki-ingest not found on
PATH; install wiki-ingest v1.1+"}` (exit 6) — graceful degradation
already covered by `tests/test_wiki_enrich.py` mocks.

**Unblock path**: ship wiki-ingest v1.1 with `ingest` mode + `--version`
flag + the manifest schema. Until then, operators use the atomic ops
directly (or wait).

---

## P0 — Cleanup (small, do when convenient)

### R-1. Mark UC-06 / UC-07 as superseded by `/wiki-enrich` ✅ DECIDED 2026-05-27
The original Phase 3b plan had `wiki-light-summary` (UC-06, R-24) and
`wiki-source-transcript` (UC-07, R-06.3) as separate code paths.
`/wiki-enrich` (Bridge skill, built 2026-05-25) covers the same surface
via the wiki-ingest manifest pipeline — end-to-end ingestion for
transcripts AND any markdown source.

**Action**: Update [TASK.md](TASK.md) RTM rows R-06.3 and R-24 to status
`SUPERSEDED → wiki-enrich` and trim Use Cases 06 / 07 to a one-line
pointer at the new skill.

Effort: ~30 min documentation update.

### R-2. Subagent prompt hook (memory 4b leftover) — DEFERRED
Inject "before editing concepts or introducing new names, call
`/wiki-search`" into `developer`, `architect`, `critic-*` agent prompts.
The parent CLAUDE.md already carries the rule; this is a proactive cue
for narrow-context subagents.

**Status**: Blocked — agent prompts live in the agentic-development
framework which is being evolved in a separate project. Memory-strategy
decision is pending there. Revisit once that work lands.

---

## P1 — Epic 7 entry-point: entity resolver

The Karpathy compounding-artifact promise lives here. Currently a single
ingest touches one source page + index + log (~3 pages); Karpathy says
10–15. Closing that gap requires the entity layer.

### R-3. `wiki-extract-concepts` skill (R-18, partial)
LLM-driven pass over a summary page → emits candidate concept slugs,
de-dups against existing `entities` rows, proposes new `_concepts/<slug>.md`
files via `wiki-ingest` upserts. Output schema mirrors the wiki-ingest
manifest so `wiki-enrich` can consume it.

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

- **wiki-ingest vendoring** — current external dep works. Vendor into
  `skills/wiki-ingest/` when publishing as a self-contained product.
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
