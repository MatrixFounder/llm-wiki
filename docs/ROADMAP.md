# Roadmap

What's deferred after Phase 3a, ordered by priority. Phase 3a (foundation,
DAL, core ingest, search/lint, reindex, benchmark) is **complete** (see
[ARCHITECTURE.md](ARCHITECTURE.md) status header). **Phase 3b is
substantially complete through TASK 028** (2026-06-09): Epic 7 entity
resolver (R-3/4/5) + RAG layer (R-6/8), the universal config-driven layout
engine (R-X1/X2/X3), `wiki-sync` (R-11), vault-local index DBs (TASK 022),
the installer + real-vault adoption surface (TASK 025/026/027), and
query-side stemming + ё/е folding (TASK 028) have all shipped. **No active
task at HEAD** — every remaining roadmap item is **trigger-gated** (see the
priority legend). **R-12 (`obsidian-cli` skill) SHIPPED 2026-06-12 as TASK 029**
(native Obsidian CLI control layer; see the P1 entry below). Archived specs
under [tasks/](tasks/) + [plans/](plans/).

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

### R-11. `wiki-sync` — format-aware, tag-routed ingest/upsert dispatcher — ✅ SHIPPED (TASK 018, 2026-06-03)
**Shipped** as TASK 018 (`task-018-wiki-sync`): `wiki-sync scan` (deterministic
plan JSON — own bounded walk → classify → sha256 → `is_unchanged`) +
`wiki-sync record` (executor commit-marker) + `workflows/wiki-sync.md` (the
Decision-17 orchestrator: convert→`_raw/.staging/` · `.vtt`/`.srt` de-timestamp ·
**H-6 fence** · summarise · enrich · extract · upsert · skip · per-vault lock ·
per-file isolation) + `skills/wiki-sync/SKILL.md` + `config/sync-config.schema.yaml`.
**Zero DDL** — idempotency rides a new `source_state` `source_kind='sync'`
partition via two generic DAL methods (`get/set_source_state`); `user_version`
stays 5. Hardened by **two adversarial gates**: the per-phase 3-critic pass (security:
anchorless deep-nesting DoS → controlled exit 6; logic: 2 crash-on-malformed-
frontmatter + 1 idempotency `None`-hash false-positive; performance: ext-set
hoist) **and** a final full-surface `/vdd-multi` converging to clean-pass on all
three (security MED `.md`-read OOM cap; logic MED UTF-8-BOM parity + `record`
FK-test; sec LOW canonical-path + full-path config-symlink containment; workflow
H-6 nonce / `flock`-primary / SEC-A3 staging guard). **73 new tests**
(`tests/test_wiki_sync.py` + `tests/test_wiki_sync_e2e.py` over committed
`tests/fixtures/sync/**` incl. a real `yaml:dbfolder` sidecar; **986 pytest +4
skipped** overall). **Residual (P2,
deferred — recorded, not silent):** the perf MED — a `.md` is read twice (decoded
for classify + re-opened for hash); the architecture pre-accepted this "honest,
bounded" read-cost (binaries pruned pre-read, zones scoped). A future fuse reads
the bytes once. **PDF-OCR is now wired** (2026-06-03 — the upstream Universal-skills
`pdf_ocr.py`/ocrmypdf block shipped): the executor OCRs a scanned PDF
(`pdf_extract` exit 10) then ingests it; `needs-ocr` is now only the
engine-unavailable fallback. **Out of scope (unchanged):** binary-attachment
indexing at scale, daily-block dedup.

<details><summary>Original proposal (for history)</summary>

The automation that actually **closes the 3→10–15 pages-per-ingest gap** on a
*real, mixed* personal vault. The static layout engine (R-X1) classifies files by
**path** and only *indexes* `.md` that already exists; it cannot (a) bring in
non-markdown sources operators actually drop into a collection folder
(transcripts `.txt`/`.vtt`/`.srt`, office docs, PDFs), (b) decide per note whether
to run a full LLM **ingest** (`wiki-enrich` → `_sources/_concepts/_entities/`) vs a
plain **upsert** (index a ready note as-is), or (c) exclude content-defined noise
(generated-view sidecars). `wiki-sync` is a thin **format-aware + content-aware
dispatcher** layered over the existing idempotent CLIs.

**(1) Format front-stage — route by extension before any indexing:**

| Input | Handling |
|---|---|
| `.docx` / `.xlsx` / `.pptx` / `.pdf` | **deterministic convert → `.md`, then ingest.** Reuses the operator's Universal-skills converter scripts + the harness `docx`/`pdf`/`pptx`/`xlsx` skills; **~0 LLM tokens** (only the downstream ingest synthesis costs tokens). **PDF-OCR is the open gap** (tracked in Universal-skills). |
| `.txt` / `.vtt` / `.srt` (plain-text source) | **implicitly raw → ingest, no tag needed** (`.vtt`/`.srt` get a de-timestamp pass first) |
| `.md` note | → the tag + view rules in (2)/(3) |
| images / other binary | **skip** (out of scope — 6000+ attachments) |

**(2) Tag vocabulary for the `.md` layer (namespace `wiki/`):**

| Signal | Action |
|---|---|
| `#wiki/raw` (or file in `_raw/`) | full **ingest** via `wiki-enrich` (transcripts, webinars, clippings to distill) |
| *(no wiki tag)* | **upsert** the ready note as-is |
| `#wiki/skip` | never index (drafts, sensitive — manual override that always wins) |
| `#wiki/keep` | opt-in index for zones excluded by default (e.g. `_daily/`) |

**(3) Generated-view sidecars — always skipped (navigation, not knowledge).**
Detected by marker, not by name alone:
- frontmatter `database-plugin:` **and/or** a fenced ` ```yaml:dbfolder ` body → **DB Folder** view;
- a body that is essentially a single fenced ` ```base ` (or a companion `.base`) → **Bases** view;
- a single fenced ` ```dataviewjs ` / ` ```dataview ` body → **Dataview** view;
- the **folder-note** naming pattern (stem == parent/sibling dir).

Anything the heuristic misses is caught by an explicit `#wiki/skip`.

Conceptual flow (per file in a zone):

```mermaid
flowchart TD
    SCAN["wiki-sync scans the zone(s)"] --> F{"by extension"}
    F -->|".docx .xlsx .pptx .pdf"| CONV["convert → .md<br/>(deterministic scripts, ~0 tokens;<br/>PDF-OCR = open gap)"]
    F -->|"images / other binary"| SKIPB["skip — out of scope"]
    F -->|".txt .vtt .srt — text source"| ENR
    F -->|".md"| V{"generated view?<br/>database-plugin: / base /<br/>dataviewjs / yaml:dbfolder /<br/>folder-note"}
    CONV --> ENR
    V -->|yes| SKIP["skip — navigation, not knowledge"]
    V -->|no| K{"#wiki/skip ?"}
    K -->|yes| SKIP
    K -->|no| R{"#wiki/raw ?"}
    R -->|yes| ENR["wiki-enrich → _sources/_concepts/_entities<br/>(idempotent via source_state hash)"]
    R -->|no| UPS["wiki-index-upsert — ready note, as-is"]
    classDef raw fill:#fdeede,stroke:#e0a050;
    classDef act fill:#e8f0ff,stroke:#5577cc;
    class ENR,CONV raw;
    class UPS,SKIP,SKIPB act;
```

**Builds on**: R-3 (`wiki-extract-concepts`), `wiki-enrich`, `wiki-index-upsert`
(all idempotent via `source_state`/file-hash); the R-X1 layout engine + the
multi-vault "search-only + enrich-zone" split (documented in
`docs/manuals/obsidian-llm-wiki_manual.md` → *Mixed vault*); the operator's
office→md converter scripts (Universal-skills) + harness `docx`/`pdf`/`pptx`/`xlsx`
skills. **Scope**: a `wiki-sync` workflow/skill = format front-stage (extension
routing + deterministic convert shell-out) + a content classifier (view-sidecar
markers; folder-note stem==dir; frontmatter tag read) + dispatch to the existing
CLIs; per-vault tag config; dry-run + per-file report; idempotent re-runs. **NOT in
scope** (future): indexing binary attachments at scale; dedup of repeated blocks
across daily notes; **PDF-OCR completion** (lives in Universal-skills). **Trigger**:
an operator runs a mixed vault where dropping a transcript / office doc into a
collection folder should "just" become a compounding wiki without hand-invoking
`wiki-enrich` per file. **Effort**: ~1 small TASK (Stub-First; mostly orchestration
over existing CLIs + a shell-out conversion stage).

</details>

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

## P1 — Native Obsidian app integration

### R-12. `obsidian-cli` skill — teach any LLM agent the native Obsidian CLI ✅ SHIPPED (TASK 029, 2026-06-12)
**Status: SHIPPED** as TASK 029 (`task-029-obsidian-cli-skill`, uncommitted on branch
`task-029-obsidian-cli-skill`). The skill `skills/obsidian-cli/` (SKILL.md + `references/{command-reference,recipes}.md`
+ `evals/`) ships: a 4-invariant dispatch core (routing / coherence / safety / degradation),
a **total** T1/T2/T3 command-safety model over the **verified 102-command** live surface
(`eval`/`dev:*`/plugin-snippet-theme mutations T3-banned; `command id=`+`template:insert`
active-file default-DENY S-1), the mutation→index coherence protocol (`wiki-index-upsert`
for content; rename/move: `--full` per the ORIGINAL TASK-029 mitigation of DF-029-1 —
SUPERSEDED 2026-06-12 by TASK 030's rename-aware `--delta`, skill updated in lockstep), the full live-verified
catalog + a diff-driven version-update Maintenance procedure, ≥8 recipes, and **14/14 GREEN**
behaviour evals (Fable+Sonnet injection canaries). Full VDD + per-bead Sarcasmotron +
**live dogfood** that found+fixed **DF-029-1** (SEV-2: `--delta` misses an mtime-preserved
rename). **Zero DDL** (`user_version` 5), **zero new Python**, no `import anthropic`,
1204 pytest + mypy strict unchanged. See `docs/tasks/task-029-*.md`, `docs/plans/plan-029-*.md`,
ARCHITECTURE §2.2 + Q-029-1..5.

<details><summary>Original proposal (for history)</summary>
**Was: PROPOSED 2026-06-12 (worked out; trigger FIRED — operator request).**

**What changed upstream**: Obsidian 1.12 ships an **official CLI**
(early-access 2026-02-10; **GA in 1.12.4, 2026-02-27**; requires installer
≥ 1.12.7; free, no Catalyst). It is a **remote control for the running
desktop app** — commands talk to the live Obsidian instance over its own
channel (the first command launches the app if closed; the separate
"Obsidian Headless" product is NOT this). Syntax:
`obsidian [vault=<name|id>] <command> [param=value …] [flags]`; many commands
emit `json|csv|tsv|md|yaml`; `file=` resolves like a wikilink, `path=` is
exact vault-relative. Surface ≈ 100 commands: files/content
(`create/append/prepend/move/rename/delete` — **rename/move update backlinks
app-side**), search (`search`, `search:context`), live graph reads
(`backlinks/links/unresolved/orphans/deadends`), **typed properties**
(`property:set/read/remove`), tasks (`tasks` filterable, `task` status
update), daily notes (`daily*`), templates (`template:*`, `unique`),
**Bases** (`bases`, `base:views`, `base:query format=json`), version history
(`history*`, `diff`, `sync:history`/`sync:restore`/`sync:deleted`),
workspace/tabs, bookmarks, publish (`publish:*`), plugin/theme management,
command-palette dispatch (`command <id>` — reaches ANY plugin command), and a
dev tier (`eval` = arbitrary JS in the app process, `dev:*` CDP, screenshots).
Docs: <https://obsidian.md/help/cli>.

**The gap**: the framework treats a vault as **files + SQLite**; the running
app is a *second runtime* — live link graph, typed properties, tasks, Bases,
recovery history, publish — none of it reachable from our CLIs. Today an
agent that renames a note via `mv` silently breaks every inbound wikilink
(`wiki-lint` only counts the orphans afterwards); it cannot flip a task
checkbox, set a typed property, append to today's daily note, query a Base,
or restore a clobbered file from history. The official CLI closes all of that
**iff the agent knows when to reach for it vs the wiki toolchain vs a plain
file edit** — that routing judgment is the skill. House Decision-17 applies
cleanly: the `obsidian` binary already IS the deterministic plumbing layer;
wrapping it in Python would add a brittle shim for zero determinism gain. So:
a **prompt-layer skill, vendor-agnostic (any LLM), zero new Python, zero DDL**.

**Deliverable — `skills/obsidian-cli/` (Gold-Standard structure)**:
1. **`SKILL.md`** — lean dispatch core in any-LLM wording (no
   harness-specific tool names; "run in your shell"): availability probe
   (`obsidian help`, bounded timeout — NOT `version`, which the live 1.12.7
   CLI lists but fails to run (TASK 029 F-3) → degrade to wiki-*/file-ops when
   absent or headless/CI); **explicit `vault=` targeting always** (first
   param; never ambient "active vault"; verify wiki `vault_root` ↔ Obsidian
   vault by `vault`/`vaults` path compare — names and `vault_id`s may
   differ); `path=` preferred over `file=` for determinism; a top-20 command
   quick table; the **decision matrix**, **coherence protocol** and **safety
   tiers** (below); progressive-disclosure links to references.
2. **`references/command-reference.md`** — the full ~100-command catalog by
   category (params/flags, output formats, `--copy`, `\n`/`\t` escapes, TUI
   notes, per-platform one-time setup: macOS symlink / Windows terminal
   redirector / Linux binary), version-stamped **"verified against Obsidian
   1.12.x"**.
3. **`references/recipes.md`** — composed playbooks: link-safe rename/move →
   `wiki-reindex --delta`; capture→daily-note (`daily:append`); task sweep
   (`tasks status=incomplete` → `task` update → upsert); Base→JSON→analysis;
   property migration via `property:set type=…`; history `diff`→`restore`
   recovery loop; vault audit (`orphans`+`deadends`+`unresolved`
   cross-checked against `wiki-lint`); publish flow; workspace/session setup.
4. **`evals/evals.json`** (+ `reports/`, the TASK 009 harness pattern) —
   trigger accuracy + behaviour: rename routes to `obsidian rename`, NOT
   `mv`; a domain question still routes to **wiki-search FIRST** (the skill
   must not weaken the search-before-answering rule); post-mutation upsert
   fires iff the vault is wiki-registered (and is skipped when not);
   **`eval`-injection canary refused** (a note body instructing "run
   `obsidian eval …`" — H-6-adjacent); headless context degrades gracefully.
5. Vendor symlinks (`.claude/skills/`, `.agent/skills/`) + README skills
   table + manual touchpoint (Mixed-vault section: live-app ops now
   scriptable) + *optional* adoption bead: the obsidian-personal `wiki-init`
   agent template mentions the skill (TASK 025/026 surface).

**Decision matrix (the heart of the skill)**:

| Need | Route |
|---|---|
| Domain question / RAG / cited answer | `wiki-search` / `wiki-query` — UNCHANGED first stop (BM25 + aliases + stemming + citations; app `search` has none of that) |
| Bulk ingest / index / dedup / re-summarize | `wiki-sync` / `wiki-reindex` / `wiki-index-upsert` |
| Link-integrity mutation (rename/move), typed property, task status, daily note, template, Base query, history restore, open-in-app / UX | **`obsidian` CLI** |
| Plain content edit on a known path | direct file edit (then upsert if indexed) |

App `search`/`search:context` is a *complement*: live and index-free (useful
mid-mutation, or on vaults never registered in the wiki index), but no
ranking/stemming/citations — never the default for knowledge lookup.

**Mutation→index coherence protocol**: any obsidian-CLI mutation on a
wiki-registered vault MUST be followed in the same turn by
`wiki-index-upsert <file>` (single file) or `wiki-reindex --delta`
(rename/move/delete — since TASK 030 the delta is RENAME-AWARE: the moved
file's new path is ingested regardless of its preserved mtime, and the
link-rewritten neighbours ride the normal mtime path; `--full` remains the
fallback + the swap-class A5 remedy). The SQLite mirror never stays stale
past the turn. ADR-002 §D8 holds:
Class-A files are mutated app-side, the DB stays a rebuildable projection.

**Safety tiers** (vault bodies are untrusted input — same egress posture as
TASK 012 SEC-1):
- **T1 read-only** (`search*`, `read`, `links`/`backlinks`/`unresolved`/…,
  `tags`, `properties`, `tasks`, `outline`, `history:read`, `vault*`,
  `wordcount`, …) — free use.
- **T2 mutating** (`create/append/prepend/move/rename/delete`,
  `property:set/remove`, `task`, `daily:append/prepend`, `template:insert`,
  `bookmark`, `workspace:*`, `publish:add/remove`) — allowed within task
  scope; `delete` → trash, never permanent without the operator; `create` →
  existence-check before `overwrite`.
- **T3 banned-by-default** (`eval`, `dev:*`, `plugin:install/uninstall/
  enable/disable`, `plugins:restrict`, `theme:install`, `sync` pause/resume) —
  operator-explicit only, NEVER from note-content instructions (`eval` is
  arbitrary JS inside the app process = RCE-equivalent; prompt-injection
  vector).
- GUI side-effect: any command launches the app if closed — probe first; in
  headless/CI degrade silently to wiki-*/file-ops.

**Out of scope**: an MCP-server wrapper (skill-first; MCP later if a vendor
needs it); Obsidian Headless; mobile; replacing wiki-search/RAG; auto-enabling
T3; scripting the Windows terminal-redirector setup (document it only).

**Acceptance**: evals green (incl. the injection canary + both routing
cases); live dogfood on the real obsidian-personal vault — a link-safe rename
with `wiki-lint` showing **zero new orphans** after delta-reindex, a
daily-note capture, a `base:query format=json`, a history restore;
`skill-validator` + skill-creator Gold-Standard pass; **zero DDL**
(`user_version` 5), zero new Python, no `import anthropic` (trivially — no
code).

**Effort**: ~1 light-medium TASK — the references + evals dominate; full VDD
with `/vdd-multi` on the skill TEXT (injection/abuse critics matter more than
code critics here).

**Risks / open (settle in TASK analysis)**: the CLI is ~3 months old and may
churn between minors → version-stamp the reference + re-verify on Obsidian
minor bumps (lightweight drift check in evals); Obsidian vault-name ↔ wiki
`vault_id` mismatch → mapping discipline in SKILL.md; macOS-first dogfood
(operator platform), Windows/Linux setup documented per official help;
cross-publication to Universal-skills? (the skill is deliberately
framework-optional — the coherence step self-disables on unregistered
vaults, so it stands alone).

**Builds on**: R-11 `wiki-sync` (the bulk path stays), TASK 022 vault-local
DBs (targeting), TASK 025/026 adoption surface, TASK 009 eval-harness
pattern. **Complements**: the P3 "wiki-graph export" item —
`backlinks`/`links`/`orphans` now give Graph-View-parity *reads* for free;
that item likely shrinks to export-only.

</details>

---

## P2 — Typed knowledge classes / event graph

### R-13. Typed knowledge classes — Phase 1 ✅ SHIPPED (TASK 031, 2026-06-13) · Phase 2 event graph ✅ SHIPPED (TASK 032, 2026-06-15)

The "CybOS 2.0" vision: grow the wiki from a flat *Page* store into one carrying
**typed knowledge classes** (Decision, Requirement, Risk, Incident, Hypothesis,
Fact, Event), keeping Markdown canonical (ADR-002 §D8). Design: **ADR-003**.

**Phase 1 — classification (SHIPPED, TASK 031):** the 7 classes tag-route, **zero
DDL**, onto the existing `pages.type` enum via layout `type_mapping`, added to the
`dev-project` layout (opt-in `type:`) and a new built-in **`cybos`** layout
(operational-memory vault — `decisions/ requirements/ risks/ incidents/ hypotheses/
facts/ events/` + the engineering spine). Bundled with **R-031-3**, the
config-driven layout registry de-hardcode (`--layout` choices + alias map +
two-tier-scaffold family collapsed into one YAML-derived cached registry via
additive `aliases`/`init_scaffold` keys → a new layout is a drop-in `*.yaml`, zero
Python edits). Per-type templates at `templates/page-types/*`; reference at
[`docs/layouts/cybos.md`](layouts/cybos.md). See `docs/tasks/task-031-*`.

**Phase 2 — the event graph ✅ SHIPPED (TASK 032, ADR-004):** typed page-to-page
edges (`implements`/`implemented-by`, `supersedes`/`superseded-by`, `causes`/
`caused-by`; `relates_to` reuses the symmetric `related`) link the classes into a
graph of system evolution (decision → task → incident → release). **Schema v5→v6**
(first DDL since TASK 008; Class-B rebuild) extends `page_entity_refs.ref_type`;
`reindex._edge_refs` extracts the frontmatter edges (forward, M-1 intact) and a global
post-pass **auto-derives the inverses** (orphan-skip; idempotent; AFTER AM-3 / BEFORE
mentions-recompute). The reserved-but-inert edge keys from Phase 1 became live with no
re-authoring. New **`wiki-graph`** CLI (16th: `neighbors`/`chain`/`backlinks`) + typed-edge
DAL reads (`get_backlinks(kind=)`/`refs_from`/`neighbors`/`edge_chain`); **graph-aware
RAG** via `wiki-query prepare --follow-edges` (default OFF, deterministic `question_hash`).
Delta: scoped inverse-additions + removal-deferred-to-`--full` (provenance-safe). See
ADR-004, `docs/tasks/task-032-*`, ARCHITECTURE Q-032-1..6. **Residual candidate** (still
open): a list-membership `--where` filter (TASK 013 surface) for one-predicate per-class
filtering (Phase-1 classes use `--types <db_type>` + FTS on the tag word).

**Phase-2 trigger (historical)**: a real cybos vault accumulates enough cross-linked
decisions/incidents that "what did this decision cause / what implements it?"
becomes a routine query. Relates to [R-X5](#r-x5-entity-graph-cross-project-phase-f).

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

### R-X3. KNOWN_ISSUES → per-file migration (Phase D) ✅ DONE 2026-06-02 (engine+splitter TASK 012; live migration committed)
> **Live migration COMPLETE (2026-06-02):** this repo's KNOWN_ISSUES was split on-disk —
> **57 per-issue Class-A files** live in `docs/issues/*.md` and `docs/KNOWN_ISSUES.md` is now the
> **auto-rendered Class-B ledger** (`<!-- GENERATED-AT … by wiki-index-render --auto-indexes -->`),
> guarded by the PW-Q drift lint. Edit the per-issue files, never the ledger; regenerate with
> `wiki-index-render --auto-indexes`. The R-X2 live dev-vault bootstrap it depended on is likewise done.
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
| **P-1** | ~~`reindex_full`: N transactions, no batching~~ ✅ DONE 2026-06-12 (TASK 030) | Stage-then-flush chunked tx (K=500 ∧ 32 MiB; lock = DML-only). **Measured 2.0×** (full @10k 4601→2353 ms). NOTE: the old "temporary FTS5 trigger drop" idea was REJECTED on record — runtime DDL + crash-window FTS desync + cross-vault `pages_fts` impact (see the P-1 issue file). |
| **P-2** | ~~`reindex_delta`: full filesystem walk on no-op~~ ✅ DONE 2026-06-02 (TASK 017) | Single-stat walk — `DiscoveredPage.mtime` reused (no 2nd stat). |
| **P-3** | ~~`check_drift`: re-hashes every file~~ ✅ DONE 2026-06-02 (TASK 017) | regex `type:` fast-path (**4.6×** `wiki-lint` @1k, default mode) + opt-in `--mtime-skip`. |
| **P-4** | Benchmark default `n=100` only | CI mode with `--scale all --enforce-slos`. Interim (TASK 030 / Q-030-1): the opt-in LOCAL gate exists — `WIKI_BENCH_SLO=1 pytest tests/test_benchmark_slo_gate.py` + the manual 10k run (`docs/runbooks/perf-slo-gate.md`); P-4 proper (CI) stays open. |
| **P-5** | ~~Dead `idx_pages_vault_tags` JSON-expr index~~ ✅ DONE 2026-05-29 (TASK 006, schema v4) | Dropped. |

Trigger: real vault crosses 1k pages and operations slow down.

Closure note (TASK 030, 2026-06-12): **R-X1-OBS-WALK** (obsidian-personal multi-glob
re-walk, KNOWN_ISSUES) is CLOSED by the single-pass alive-set walk — scandirs 140→61
at 2k files, every dir exactly once; see the issue file + ARCHITECTURE §3.5/§8.5.
New residual filed by the TASK 030 post-ship `/vdd-multi` (SEV-3, scale-gated):
**P-030-DELTA-BULK** — whole-vault `--delta` ingest keeps per-file atomic txns
(~1.7× vs chunked `--full` @2k; deliberate — per-file atomicity closed the
partial-write hole); fix shape = stage-then-flush for the delta cohort
(`docs/issues/p-030-delta-bulk-ingest-per-file-txns.md`).

**Newer documented residuals** (recorded, not silent; none with an active trigger):
- **wiki-query V×T alias fan-out** (ARCHITECTURE Q-028-3) — `_build_match_query` does one
  `expand_query_aliases` SQL call per (vault × token). **Pre-existing** (predates TASK 028;
  verified on `main`), invisible at single-vault (V=1) — the common case — and only bites
  `--vaults all` over a large multi-vault DB. Fix = per-vault alias prefetch (`list_all_aliases`
  → in-memory map) → O(V) queries. Deferred (YAGNI for island single-vault DBs).
- **wiki-sync `.md` read twice** (R-11 residual) — a `.md` is decoded for classify + re-opened
  for hash. Architecture pre-accepted (binaries pruned pre-read, zones scoped). A future fuse
  reads the bytes once.
- **Single-outer-transaction batching** (TASK 015 deferred) — batch `apply`/`prepare` reuse one
  repo but not one transaction (SQLite nested-txn limit → needs batch-mode upsert methods).

> **TASK 017 (`drift-delta-redos-timeout`) shipped 2026-06-02** — closes the only open
> **SEV-2 R-X1-REDOS-RT** (runtime per-file `regex` `timeout=` deadline for operator-custom
> layout patterns; built-ins stay stdlib `re`/byte-identity) **+ P-2 + P-3**. **Zero DDL**
> (`user_version` 5). 908 pytest / mypy strict (incl. `/vdd-multi` post-ship hardening:
> 1 HIGH unguarded-`derive_project_for_path` + MED + 4 LOW). New dep: `regex` (+`types-regex`).

> **TASK 006 (consolidation/hardening) shipped 2026-05-29** — schema **v3→v4**
> (drop dead `idx_pages_vault_tags` P-5 + `event_date` GENERATED L-2; `'log'`
> enum L-5 already-absent), reindex name fallback (L-8), `_recompute_mentions`
> dedup (F12c), `wiki-lint` frontmatter scan from `pages.frontmatter_json`
> (P-10+F12b — removes a 2nd O(N) YAML sweep), + doc clarifications (L-1/6/7).
> Scale-gated perf (P-1/2/3/4/9/11) + threat-gated security
> (D-1/D-2/H-5/H-6/Q17) remain deferred with their triggers
> (**P-6/P-7/P-8 + H-PERF-3 closed by TASK 015** 2026-06-01). See
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
- **wiki-graph** export — the read/traversal CLI **shipped** (TASK 032: backlinks/
  neighbors/chain over typed edges). Remaining: a graphviz / mermaid **export** of the
  edge graph for Obsidian Graph-View parity.
- **CI workflow** for benchmarks — wire `bench --enforce-slos` into a
  GitHub Action (currently runs locally only).
- **`docs/ARCHITECTURE.md` Index-Mode split** (doc-hygiene) — the file crossed the
  1500-line soft threshold (1528 after TASK 032); two arch-reviews deferred the §11
  (Q-NNN decision-log) split to a dedicated task to avoid `#q-0NN-N` anchor churn
  mid-feature. Extract §11 → `architectures/open-questions.md` + a short index.

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

- **TASK 028 (query-stemming-yo-folding) — 2026-06-09.** Query-side, script-aware **stemming**
  (default-on; `--exact`/`--no-stem` opt-out; per-term by script — Cyrillic→`russian`,
  Latin→`english`, pinned pure-Python `snowballstemmer==3.1.1`) + always-on **ё/е folding**
  (corpus + query) — closes two real recall misses on the personal vault. New
  `scripts/wiki_index/{_snowball,query_normalizer}.py`; two call sites (wiki-search FTS-expr
  lexer, F-1 `(<stemmed>) OR "alias"`; wiki-query per-token `"<stem>"*`, `--exact` symmetric
  across prepare/apply for `question_hash`). Guards: post-stem MIN, ALL-CAPS acronym,
  stem-must-be-prefix (English `-y→-i`). Full VDD + `/vdd-multi` ×2 converged (caught + fixed a
  whitespace-query `ValueError` regression). **Zero DDL** (`user_version` 5), Karpathy
  byte-identical for ё-free content. **1204 pytest**, mypy strict. Dogfooded on the real vault
  (ё-fold 133→173, stemming 67→244). See `docs/tasks/task-028-*.md` + ARCHITECTURE Q-028-1..6.
- **TASK 026/027 (installer ships vault `.claude/settings.json` + CLI works from a vault) —
  2026-06-09** (committed `1ee638f`). (026) `wiki-init` drops the vendor's settings file
  (VERBATIM, non-destructive) via config-driven `settings_file`/`settings_template`. (027) the
  8 skill SKILL.mds + wrappers fixed so `wiki-*` works **from inside a vault** (on-PATH wrapper;
  `bin/wiki-*` drop `cd`, `source $REPO/.venv` + `PYTHONPATH` + `PYTHONSAFEPATH=1`). See
  ARCHITECTURE Q-026-1, `docs/tasks/task-026-*.md`.
- **TASK 025 (adoption-currency-hardening) — 2026-06-09.** Closes a 4-agent adoption-currency
  audit run after the first real-vault dogfood: installer absolute-`--index-db` pre-write guard
  (`config_loader.validate_index_db_value`), `INVALID_INDEX_DB` unified exit 6; obsidian-personal
  built-in `type_mapping` += the `*-summary` family + `_raw`/`.staging` ignore; layout-aware
  `CLAUDE.layout.md.tmpl`; basename-provenance / paths=REPLACE / custom-type docs. Full VDD +
  `/vdd-multi` converged. **Zero DDL**. See `docs/tasks/task-025-*.md` + ARCHITECTURE Q-025-1..4.
- **TASK 024 (upsert-layout-fts-hardening) — 2026-06-08.** **R-1** `wiki-index-upsert` is now
  LAYOUT-AWARE (shared `reindex.derive_indexed_page` serves all 3 sites → upsert files
  byte-identically to reindex; fixes `_vault_`-misfiling + dup-on-reindex on PARA vaults). **R-2**
  FTS indexes the FULL body (dropped `body_excerpt[:1000]`; deep terms searchable). **R-4** D2a
  provenance NFC/NFD normalisation; OCR convert+ingest path re-validated. Full VDD + `/vdd-multi`.
  **Zero DDL**. See `docs/tasks/task-024-*.md` + ARCHITECTURE Q-024-1..4.
- **TASK 023 (personal-vault dogfood hardening) — 2026-06-08** (ad-hoc batch, no separate spec).
  obsidian-personal `type_mapping` summary family; structured object-valued `sources:` provenance
  (`all_cited_sources` harvests `{id,url,file}`); opt-in `transcript_dedup` SyncConfig. Zero DDL.
- **TASK 022 (vault-local-db-resolution) — 2026-06-08.** A vault may declare `index_db:` in
  `WIKI_SCHEMA.md` → its SQLite index travels WITH the vault (portable, gitignored). Precedence
  `--db-path > index_db > global`; island model (`--vault all` spans only the connected DB).
  `/vdd-multi` hardening (leaf-symlink containment, absolute-path gate
  `WIKI_ALLOW_ABSOLUTE_INDEX_DB`, expected-vault-id guard, `INVALID_INDEX_DB`). **Zero DDL**. See
  `docs/tasks/task-022-*.md` + ARCHITECTURE Q-022-1..4.
- **TASK 019/020/021 (sync-resummarize + reindex-slug-collision + dogfood-hardening) —
  2026-06-07/08.** (019) `wiki-sync` re-summarization gate — a raw is re-ingested only if `--force`
  or no summary exists (D1 source_state ∪ D2a provenance ∪ D2b filesystem mirror; per-folder
  cascade). (020) `wiki-reindex` now emits a `slug_collisions` envelope field on intra-project PK
  collisions (was silent). (021) repeat dogfood + 2 adversarial `critic-logic` passes → merge/split
  WARN + cross-batch delta collision seeding + `--all-vaults --delta`. **Zero DDL**. See
  `docs/tasks/task-019-*.md` / `task-020-*.md` / `task-021-*.md`.
- **TASK 018 (`wiki-sync`, R-11) — 2026-06-03.** See the R-11 entry above (P1) for the full
  summary. Format-aware, tag-routed ingest dispatcher; **zero DDL** (`source_kind='sync'`); two
  adversarial gates; 986 pytest.
- **TASK 017 (drift-delta-redos-timeout) — 2026-06-02.** Closes the last open SEV-2
  **R-X1-REDOS-RT** (runtime per-file `regex` `timeout=` ReDoS deadline for operator-custom layout
  patterns; built-ins stay stdlib `re`/byte-identity) + **P-2** (single-stat delta walk) + **P-3**
  (`check_drift` `type:` regex fast-path, 4.6× `wiki-lint` @1k). New dep `regex`(+`types-regex`).
  **Zero DDL**. See `docs/tasks/task-017-*.md` + ARCHITECTURE Q-017-1..4.
- **TASK 016 (split-extract-concepts-module) — 2026-06-01.** Pure structural refactor: the
  2174-line `scripts/wiki_skills/wiki_extract_concepts.py` god-module split into a **package**
  — facade `__init__.py` (orchestration: `prepare`/`apply`/`dispatch_to_indexer`/`_batch_*`/
  `main`/`_build_parser_v3`, 1071 lines) + leaves `_validation` (375) / `_sourcing` (332) /
  `_db` (273) / `_pages` (227) / `_errors` (60) + `__main__.py`. **Zero behaviour / CLI /
  envelope / exit-code / schema change.** The **patch-target lock** is preserved: the 8
  monkeypatched names stay rebindable at `scripts.wiki_skills.wiki_extract_concepts.<name>`
  as facade globals (`_db` carve-out re-imports `load_known_entities` +
  `update_idempotency_state` into the facade); acyclic import-direction (facade→leaves;
  `_errors` is the sink; no leaf→facade edge). `_SOURCE_KIND` relocated `_sourcing`→`_db`
  (its only consumers). All moved bodies byte-identical (verbatim, hash-proven per bead);
  green-throughout, leaf-first. Full VDD pipeline (task/arch/plan reviews all APPROVED —
  task-review caught the lock surface was **8** symbols not 7; plan-review pinned
  `_path_is_absolute`→`_validation`) + per-bead Sarcasmotron + dogfood smoke. **879 pytest
  (+4 skip), mypy strict (69 files).**
- **TASK 015 (perf-hardening-extract-concepts) — 2026-06-01.** Closes four SEV-2
  hot-path issues in `wiki-extract-concepts` / `_manifest_consumer`: **H-PERF-3**
  (`wiki_index_upsert.upsert_one(vault_id, src, vault_root, repo) → dict` programmatic
  entry-point — no argparse-in-loop; `main()` delegates), **P-8** (`index_from_manifest`
  + `dispatch_to_indexer` optional `repo` param; `apply --ingest` threads its open repo →
  one `make_repo` per invocation), **P-6** (`prepare --known-concepts-format
  {full,slugs-only}`), **P-7** (`prepare --batch <slugs.json>` + `apply --batch-candidates
  <combined.json>` — one repo reused across all entries, per-entry error isolation).
  `apply` factored into `_apply_validate` (no repo — input errors never touch the DB,
  preserving the CWE-117 canary ordering) + `_apply_write`; `prepare` into
  `_load_known_and_drift` + `_recon_single`. **Hardened by `/vdd-multi` ×2 (all critics
  clean):** `sqlite3.Error` in the per-entry catch (one DB fault isolates, never crashes
  the batch); batch `prepare` hoists `known_concepts`/`missing_concept_files` to the
  envelope top level (O(N+|known|) stdout, not O(N·|known|)); batch `apply` loads known
  entities once + grows the dedup set in place (O(E), not O(N·E)); idempotency-failure →
  per-entry `partial`; M-2 absolute-path leak closed; combined.json cap 1 MiB→10 MiB.
  **Deferred:** single-outer-transaction batching (SQLite nested-txn limit → needs
  batch-mode upsert methods). **Zero DDL** (`user_version` 5), additive/backward-compatible.
  877 pytest (+4 skip), mypy strict.
- **TASK 014 (dogfood-fixes) — 2026-06-01.** Fixes from the comprehensive dogfood
  (dev-vault + karpathy/obsidian-personal/dev-project sandbox vaults across all
  layout classes + aliases + cross-vault search). Closes **R-X1-REF-SLUGIFY**
  (SEV-2): `reindex._body_refs` slugifies ref targets via the layout's
  `slug_strategy`, so `[[Title Case]]`/`[[Идеи]]` resolve under non-`identity`
  layouts (transliterate/preserve-unicode) instead of becoming false `orphan-link`s
  — `identity`/karpathy is a verbatim no-op (byte-identity held); dev-vault orphans
  dropped 2228→2160; 7-case layout-matrix test. Plus two CLI-UX fixes: `wiki-query
  --vault-root` now optional (derived from the registered vault's `root_path`), and
  `wiki-alias --list` lists the whole vault when no slug is given (new
  `repo.list_all_aliases`). New deferred perf issue **R-X3-MF-SCAN** (metadata-filter
  unindexed scan, 1k-page trigger). **Zero DDL** (`user_version` 5). 852 pytest
  (+4 skip), mypy strict. Done compactly (no separate PLAN; RTM inline in TASK.md).
- **TASK 013 (R-X3-META-FILTER) — 2026-06-01.** `wiki-search` frontmatter metadata
  filter (Cluster C / daily-use enablement). General repeatable `--where 'field=value'`
  + `--status`/`--severity` sugar → parameterized `CAST(json_extract(frontmatter_json, ?)
  AS TEXT) = ?` predicate (string-rep match → numeric values like `priority=1` work too);
  optional query → non-FTS `(project, slug, vault_id)`-ordered listing. Injection-safe
  (field allowlist `[a-z][a-z0-9_]*` via `re.fullmatch` at CLI + DAL; path + value bound;
  duplicate-field rejected; `INVALID_FILTER` never echoes value). **Zero DDL**
  (`user_version` 5). Full VDD pipeline (Analysis → Architecture Q-013-a..d → Plan →
  4 beads Stub-First) + `/vdd-multi` (logic/security/perf) + code-review. Live dogfood:
  `--status open --severity SEV-2` returns the 5 open SEV-2 issues; R-X3-META-FILTER flipped to `fixed`
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
    [docs/KNOWN_ISSUES.md](KNOWN_ISSUES.md): ~~**H-PERF-3**~~ (SEV-2 —
    `_manifest_consumer` argparse-in-loop N+1) **— CLOSED by TASK 015**
    (`wiki_index_upsert.upsert_one` programmatic entry-point); **H-5**
    (`concept-extraction/SKILL.md` hash-pin enforcement), **H-6**
    (indirect prompt-injection canary scanning),
    ~~**P-8**~~ (two-process WAL setup cost) **— CLOSED by TASK 015**
    (connection reuse via `index_from_manifest(repo=…)`), **L-4** (`>=` deps
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
