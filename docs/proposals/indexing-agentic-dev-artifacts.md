# Proposal — Indexing agentic-development artifacts with obsidian-llm-wiki

> **Status:** PROPOSAL (2026-05-27) — tracked in
> [ROADMAP §P2 "Cross-project indexing"](../ROADMAP.md) as R-X1..R-X5.
> Not yet a TASK; promotion requires `/start-feature` invocation
> after a real-world trigger fires (see §14).
> **Author:** session 2026-05-27, after dogfood + TASK 017 alignment work.
> **Audience:** future-me, future agentic-development sessions.
> **Purpose:** Lay out how obsidian-llm-wiki could become the cross-project
> memory layer for the agentic-development framework — indexing TASKs,
> PLANs, ARCHITECTUREs, ADRs, reviews, audits, KNOWN_ISSUES, roadmaps,
> session snapshots — and what that would buy us.

---

## 1. Motivation

The agentic-development framework already produces well-structured markdown
artifacts at every pipeline phase:

| Phase | Artifact(s) | Location |
|---|---|---|
| Analysis | `TASK.md` → archived `tasks/task-NNN-<slug>.md` | `docs/tasks/` |
| Architecture | `ARCHITECTURE.md` (living) | `docs/`, split into `docs/architectures/` if > 1500 lines |
| Architecture decisions | `ADR-NNN-<slug>.md` | `docs/adr/` |
| Planning | `PLAN.md` → archived `plans/plan-NNN-<slug>.md` | `docs/plans/` |
| Per-atomic-task specs | `task-NNN-XX-<slug>.md` | `docs/tasks/` |
| Reviews (single-pass) | `<phase>-review-<date>.md` | `docs/reviews/` |
| Reviews (multi-critic) | `vdd-multi-<date>.md`, `vdd-adversarial-<date>.md` | `docs/reviews/` |
| Security audits | `security-audit-<date>.md` | `docs/audit/` |
| Product (market/vision/blueprint) | `MARKET_STRATEGY.md`, `PRODUCT_VISION.md`, `APPROVED_BACKLOG.md`, `SOLUTION_BLUEPRINT.md` | `docs/product/` |
| Roadmap | `ROADMAP.md` | `docs/` |
| Known issues ledger | `KNOWN_ISSUES.md` | `docs/` |
| Session state | `latest.yaml` | `.agent/sessions/` |

Each artifact is **canonical markdown**, git-tracked, audit-trailed. But
they have three structural weaknesses:

1. **Search is by-file, not by-fragment.** `git grep "vault_id REQUIRED"`
   works locally; cross-project search across 5+ repos requires manual
   loops. No BM25 ranking, no snippet, no FTS5.
2. **Cross-references are textual, not graphed.** "ADR-001 references
   ADR-002" is a plain link; there's no `[[wiki-link]]` graph view, no
   backlinks, no orphan-link detection.
3. **Decision archaeology is git-blame.** "Why did we relax `vault_id`
   from REQUIRED to nullable on 2026-05-27?" requires reading commit
   messages + diffing TASK.md. A wiki-link from the contract to the
   decision rationale would surface it in O(1).

obsidian-llm-wiki already solves all three for *user knowledge* (concepts,
entities, transcripts) in an Obsidian vault. The proposal: **reuse the
same engine on the development artifacts themselves.**

---

## 2. Architecture vision

### Each project = one vault

A "dev-vault" maps onto an existing repo without restructuring it:

```
<project-repo>/
├── docs/                                     # ← the dev-vault content
│   ├── ARCHITECTURE.md                       # type=architecture
│   ├── TASK.md                               # type=task (current)
│   ├── PLAN.md                               # type=plan (current)
│   ├── ROADMAP.md                            # type=roadmap
│   ├── KNOWN_ISSUES.md                       # type=issues-ledger
│   ├── tasks/                                # type=task (archived)
│   ├── plans/                                # type=plan (archived)
│   ├── adr/                                  # type=adr
│   ├── reviews/                              # type=review
│   ├── audit/                                # type=audit
│   ├── product/                              # type=product-doc
│   └── architectures/                        # type=architecture (sharded)
└── .agent/sessions/latest.yaml               # type=session (optional)
```

This is **NOT** a Karpathy-layout vault. There's no `_sources/`,
`_concepts/`, `_entities/`. The indexer needs a new **dev-vault adapter**
that walks `docs/` (and optionally `.agent/sessions/`) and emits the same
`Page` shape the SQLite expects.

### vault_id per project

Each repo's WIKI metadata lives in a small declaration. Two options:

- **Option A (clean):** `<repo>/docs/WIKI_SCHEMA.md` with frontmatter
  `vault_id: <slug>` + `layout: dev-project`. Indexer recognises
  `layout: dev-project` and loads the built-in
  `layouts/dev-project.yaml` (instead of the Karpathy layout).
- **Option B (zero-friction):** auto-detect via `package.json` /
  `pyproject.toml` / git-root name → kebab-slug. Operator can override
  with `--vault-id <slug>`.

Option A wins on explicitness (no "magic" filename slugification surprises
when two projects share a folder name); Option B wins on operator effort.
Pick A; provide `wiki-init --layout dev-project --vault . --vault-id <slug>`
(extension to existing `wiki-init`, not a new CLI — see §10).

### Cross-project search is the killer feature

```bash
# Find every place we discussed M-4 contract across all dev-vaults
wiki-search "M-4 contract" --vaults all --types adr,task,review

# Find every KNOWN_ISSUE that mentions FTS5
wiki-search "FTS5" --vaults all --types issues-ledger

# Find every VDD-multi finding about path traversal
wiki-search "path traversal" --vaults all --types review
```

Multi-vault FTS5 is already shipped (R-29). Adding new types is a small
schema delta + adapter work, not new core.

---

## 3. Document taxonomy

### Mapping artifacts → types

The `pages.type` CHECK enum currently allows `{summary, concept, query,
brief, research, index}`. Options:

- **Extend the enum** — Schema Change Request (per TASK.md §6.1
  process) to add `task, plan, adr, review, audit, architecture,
  roadmap, issues-ledger, product-doc, session`.
- **Map through TYPE_MAPPING** — keep enum small, use tags. E.g.,
  `type: task` → `pages.type='brief'` + tag `task`.

The TYPE_MAPPING route is what we already do for `lesson-summary`,
`external`, `person`, etc. It scales without schema migration. **Pick
TYPE_MAPPING route.** New mappings:

| Frontmatter `type:` | DB `pages.type` | Tag marker | Producer |
|---|---|---|---|
| `task` | `brief` | `task` | dev-vault adapter |
| `plan` | `brief` | `plan` | dev-vault adapter |
| `architecture` | `research` | `architecture` | dev-vault adapter |
| `adr` | `research` | `adr` | dev-vault adapter |
| `review` | `research` | `review` | dev-vault adapter |
| `audit` | `research` | `audit` | dev-vault adapter |
| `roadmap` | `research` | `roadmap` | dev-vault adapter |
| `issues-ledger` | `research` | `issues-ledger` | dev-vault adapter |
| `product-doc` | `research` | `product` | dev-vault adapter |
| `session` | `index` | `session` | dev-vault adapter |

Search by tag becomes the primary filter: `wiki-search --types brief
--vaults all` for all tasks/plans; or refined: `--filter "tags has 'task'"`.

### Entities for development artifacts

Concept/entity extraction (Epic 7 territory) maps naturally:

- **Concept-like artifacts**: requirements (R-1, R-2, …), patterns (M-4,
  R-26, R-29), invariants (Class A/B/C), components (`SQLiteRepository`,
  `wiki-enrich`).
- **Entity-like artifacts**: agents (`developer`, `architect`,
  `critic-logic`), skills (`vdd-adversarial`, `skill-archive-task`),
  workflows (`vdd-multi`, `framework-upgrade`), tools (`pytest`,
  `mypy`).

If Epic 7 lands (entity resolver), these become first-class wiki nodes
queryable across projects.

---

## 4. Integration points

### When does indexing happen?

Five candidate triggers, increasing automation:

| # | Trigger | Pros | Cons | Recommended phase |
|---|---|---|---|---|
| **a** | Manual `wiki-reindex --full --vault <id>` per project | Simplest; operator-explicit | High friction at scale | Bootstrap / migration |
| **b** | `skill-archive-task` hook — after rotation, call `wiki-index-upsert` | Lands rotation + index in one step; reuses existing skill | Couples archival skill to wiki dependency | Phase 1 |
| **c** | Git `post-commit` hook — `wiki-reindex --delta` if `docs/` changed | Auto, no agent involvement | Slows commits; sensitive to non-doc commits | Phase 2 (opt-in) |
| **d** | CI workflow on merge to main — full reindex + cross-project lint | Centralised; doesn't pollute local | Lag between commit and search-availability | Phase 3 |
| **e** | Periodic background daemon (`wiki-watch-projects`) | Most "set & forget" | Resource use; one more process to manage | Optional, future |

**Proposed rollout**: a → b → c (opt-in). Don't build (d) or (e) until
real demand surfaces.

### `archive_protocol.py` integration sketch (high-level)

Patch lands in `agentic-development/.agent/tools/archive_protocol.py`
(the Python mirror of `skill-archive-task`; **not** the markdown
protocol doc — see §12 for the full sketch including `pending.log`
observability and feature detection). High-level shape:

```python
def archive_task_with_indexing(task_path, plan_path):
    archived_task = archive_task(task_path)         # existing
    archived_plan = archive_plan(plan_path)         # existing
    _maybe_index(archived_task)                      # NEW — see §12
    _maybe_index(archived_plan)                      # NEW — see §12
```

`_maybe_index` is feature-detected (no-op if `wiki-index-upsert` not on
PATH) and fail-silent with a `pending.log` breadcrumb. See §12 for the
full code + the `wiki-reindex --replay-pending` replay path.

### Layout dispatch

Today `scripts/wiki_source/manual.py` reads files from `_sources/`,
`_concepts/`, `_entities/`. After §11 pre-work, there is **no separate
adapter file** — the same config-driven engine handles every layout
natively. Dispatch is by `WIKI_SCHEMA.md` frontmatter `layout:` field:

- `layout: karpathy` → uses built-in `layouts/karpathy.yaml` (current behaviour)
- `layout: dev-project` → uses built-in `layouts/dev-project.yaml` (new — paths in §11)
- `layout: obsidian-personal` → uses built-in `layouts/obsidian-personal.yaml`
- Operators can ship a custom `<vault>/.wiki/layout.yaml` and reference
  it from `WIKI_SCHEMA.md` frontmatter.

The dev-project layout's `paths[]` table (in §11) carries the
type-inference rules that an adapter would have hardcoded:
`docs/tasks/*.md` → `type: task`, `docs/adr/*.md` → `type: adr`, etc.
Cross-reference extraction is config-driven too (PW-D / `ref_extraction[]`),
picking up R-NN / ADR-NNN / task-NNN-XX identifiers and
`[[wiki-link]]` / Markdown-link forms.

Plug-and-play with existing `IndexRepository.upsert_page` /
`replace_refs` — no DAL changes.

### `wiki-init --layout dev-project` helper

Extension to existing `wiki-init` (no new top-level command — see §10):

```bash
wiki-init --layout dev-project --vault . --vault-id obsidian-llm-wiki
# Writes docs/WIKI_SCHEMA.md:
#   ---
#   vault_id: obsidian-llm-wiki
#   layout: dev-project
#   schema_version: '2.0'
#   ---
# Registers in global SQLite
# Runs wiki-reindex --full
```

Idempotent. Doesn't touch existing project files.

---

## 5. Concrete queries this would unlock

### For operators (you)

```bash
# Why did we choose Option I in ADR-001? What were the alternatives?
wiki-search "Option I" --vaults obsidian-llm-wiki --types adr

# What perf findings has /vdd-multi raised in any project?
wiki-search "SEV-1" --vaults all --types review

# Has the FTS5 contentless_delete issue come up anywhere?
wiki-search "contentless_delete" --vaults all

# Every place we've referenced ADR-002 §D8 (rebuildability invariant)
wiki-search "D8 rebuildability" --vaults all

# Backlinks: where is task-001-30 mentioned besides its own file?
wiki-backlinks --slug task-001-30 --vaults obsidian-llm-wiki
```

### For agents (sub-tasks during /vdd-develop)

```python
# developer agent, about to introduce a new concept name
hits = wiki_search("rebuildability invariant", vaults=["obsidian-llm-wiki"])
if hits:
    # Don't reinvent; cite ADR-002 §D8 instead
    ...

# critic-security agent, reviewing a path-traversal-touching change
prior = wiki_search("path traversal", vaults=["all"], types=["review", "audit"])
# Pull every prior finding to compare with current critique

# analyst agent, writing a new TASK.md
similar = wiki_search("transcript ingest", vaults=["all"], types=["task"])
# Surface prior tasks that touched similar surface
```

### For cross-project pattern detection

```bash
# Which projects have a KNOWN_ISSUE about hash drift?
wiki-search "hash drift" --vaults all --types issues-ledger

# Where have we used the cybos two-tier confirmed/candidate pattern?
wiki-search "cybos two-tier" --vaults all

# Every TASK that mentions stub-first methodology
wiki-search "stub-first" --vaults all --types task
```

### Graph traversal (when Epic 7 entity resolver lands)

```bash
# Show me the dependency graph: which ADRs reference ADR-002?
wiki-graph --slug ADR-002 --direction inbound --vaults all

# What patterns share a backing source with the M-4 contract?
wiki-co-occur --slug M-4 --vaults all
```

---

## 6. Where this differs from "just use grep + git"

| Concern | grep + git | wiki-indexed |
|---|---|---|
| Ranking | None (line matches) | BM25 — most relevant first |
| Snippet with context | `-A 3 -B 3` flags | Auto-extracted, highlighted |
| Cross-project | Loop over repos manually | One query, `--vaults all` |
| Backlinks / graph | None | `find_orphan_links`, `get_backlinks` |
| Type filter | Per-path regex | First-class `--types task,adr` |
| Concept / entity dedup | None | `find_cross_vault_concept_duplicates` |
| Historical archaeology | `git log -p`, slow | Indexed `pages.last_modified` + frontmatter `date:` |
| Agent integration | Each agent rolls its own | Single `wiki-search` skill, already in `.claude/skills/` |

grep stays best for "exact regex in current working tree". wiki-indexed
wins for "where was this concept discussed across projects and time".

---

## 7. Open challenges

### 7.1 Schema / type enum

Use TYPE_MAPPING route (pick mapping per artifact kind). No schema
migration. Cleaner long-term: a one-off `pages.type` enum extension to
include `task`, `plan`, `adr`, `review`, `audit`, `architecture`,
`roadmap`. Defer until usage proves the typing pattern is stable.

### 7.2 vault_id collision across home + work

If `obsidian-llm-wiki` exists on two machines (laptop + workstation) and
both register the SAME `vault_id`, the global SQLite at each location
will have its own copy — fine. But syncing? If both machines write to a
shared SQLite (DropBox / iCloud), corruption per ADR-002 §D8. Don't.

If both want to share index content: emit + ingest via wiki-ingest
manifests (rebuildable per ADR-002 §D8). The wiki DB is local cache;
markdown is the canonical synced layer.

### 7.3 Privacy / scope

Some project artifacts are private (NDA, security audit details). The
indexer needs:
- Per-vault `is_private` flag (already plausible via `vaults` table
  column).
- `wiki-search --vaults all` default = exclude private; opt-in
  `--include-private` flag.
- Agent prompts default to current vault only; cross-project search
  requires operator approval.

### 7.4 Dev-vault layout vs Karpathy layout coexistence

A project COULD have BOTH a Karpathy vault (knowledge base, e.g.
`trade-agents`) AND a dev-vault (its own docs/). They are different
vault_ids. `wiki-search` doesn't care — both partition by vault_id.
The dev-vault adapter only fires for vaults marked
`layout: dev-project`.

### 7.5 Session snapshots — value vs noise

`.agent/sessions/latest.yaml` rotates frequently. Indexing every
snapshot bloats the DB. Two options:
- Index only the LATEST snapshot per vault (overwrite-on-upsert).
- Skip snapshots entirely; they're ephemeral state, not knowledge.

Recommend the second — too noisy.

### 7.6 Cross-references between dev artifacts and Karpathy artifacts

Could a dev-vault concept page reference a `trade-agents` concept page?
Technically yes via cross-vault `[[wiki-link]]` (Obsidian-style). For
indexer: `page_entity_refs` carries `(vault_id, page_slug, page_project)`
+ `entity_slug` (see `sql/wiki-index-v2.sql:176-186`); the table itself
supports cross-vault references in shape, but **whether the FK to
`entities` actually allows cross-vault resolution still needs
verification** — the schema FK at line 186 references `pages`, not
`entities`, so entity-side cross-vault is unconstrained today, but
that's an absence-of-constraint, not a positive feature, and needs an
acceptance test before Phase F relies on it. Open as a follow-up
verification item in Phase F.
Useful when it works: "the M-4 invariant is implemented in
`SQLiteRepository` and referenced in
`trade-agents/_concepts/Database Pattern.md`."

---

## 8. Phased rollout

### Phase A — Single-project bootstrap (~2-3 days, depends on §11 pre-work complete)

1. Add `dev-project` layout to the YAML config loader (PW-A) — i.e.,
   register the built-in `layouts/dev-project.yaml` as a valid
   `WIKI_SCHEMA.md` frontmatter `layout:` value. No separate
   `dev_project.py` adapter needed once the config-driven engine
   (§11 PW-A..N) is in.
2. Write `wiki-init` `--layout dev-project` flag — wires
   `WIKI_SCHEMA.md` frontmatter.
3. Bootstrap obsidian-llm-wiki itself as the first dev-vault:
   `wiki-init --layout dev-project --vault . --vault-id obsidian-llm-wiki`.
4. Confirm: `wiki-search "ADR-002" --vaults obsidian-llm-wiki` returns
   real hits with snippets.

### Phase B — Multi-project (~1 day)

5. Bootstrap one more dev-vault: trade-agents, or Universal-skills.
6. Confirm cross-project: `wiki-search "M-4" --vaults all`.

### Phase C — `archive_protocol.py` integration (~1 day)

7. Patch `agentic-development/.agent/tools/archive_protocol.py::archive_task()`
   per the §12 Option C sketch — feature-detected shell-out to
   `wiki-index-upsert` + `pending.log` on failure. Behind a flag
   (`enable_wiki_index`) for safety.
8. Adversarial test: archive a fake TASK, confirm new row appears in
   SQLite without any operator-visible failure path; force
   `wiki-index-upsert` to timeout and confirm `pending.log` captures
   the drop.

### Phase D — `KNOWN_ISSUES` → per-file + auto-rendered ledger

**Decision: Model B** — one file per issue under `docs/issues/`, with
the existing `docs/KNOWN_ISSUES.md` becoming an auto-rendered index
(read-only projection, like the vault `index.md`). This aligns with the
config-driven engine from §11 (`auto_indexes[]` config entry handles
the render).

### Class A/B reclassification (ADR-002 §D8 implication)

The migration changes which file is canonical. Before:

| File | Class | Authoritative for |
|---|---|---|
| `docs/KNOWN_ISSUES.md` | **A — canonical** | issue status, severity, lifecycle |
| (no per-issue files) | — | — |

After migration:

| File | Class | Authoritative for |
|---|---|---|
| `docs/issues/<id>-<slug>.md` | **A — canonical** | issue status, severity, lifecycle, history |
| `docs/KNOWN_ISSUES.md` | **B — derived/rebuildable** | aggregated ledger view; regenerable from `docs/issues/` via `auto_indexes[]` |

This is a new sub-case of Class B: **rebuildable markdown** (today's
Class B is SQLite cache). ADR-002 must be amended (or a thin ADR-003
opened) to register the sub-case before Phase D ships, otherwise future
agents reading §D8 will be ambiguous about which file to trust.

**Concrete invariant**: deleting `docs/KNOWN_ISSUES.md` and re-running
`wiki-index-render --auto-indexes` must produce a byte-identical file
(modulo a `<!-- GENERATED-AT: <iso8601> -->` header line). This is the
rebuildability test, mirrored from ADR-002 §D8.

### When the render fires (state-machine pin)

`auto_indexes[]` rendering is triggered by **any of**:

1. `wiki-index-upsert` whose upsert batch creates OR deletes a
   `type: known-issue` row → trigger render at end of upsert tx.
2. Explicit `wiki-index-render --auto-indexes` CLI invocation.
3. `wiki-reindex --full` / `--delta` always runs `auto_indexes[]` at end.

This closes the desync gap between "issue file deleted (resolved policy A)"
and "ledger updated": both happen in the same git commit because both
land via the same `wiki-index-upsert` call.

**Why this and not single-file Model A**: the agent already maintains a
rich lifecycle inline today (visible in
`Universal-skills/docs/KNOWN_ISSUES.md`): `Status:` updates per work
phase, severity downgrades after partial fixes, multi-tier sub-issues
(`Logic-tier LOWs` / `Security-tier LOWs` inside a single deferral),
timer-based deferrals (`14-day timer started 2026-05-14, deadline
2026-05-28`), "Do not" anti-rationalisation blocks, cross-links to
backlog rows / source files / ADR sections. Forcing all that into a
single ledger document is workable today; once we add multi-project
indexing, **per-issue files give the agent the same expressivity with
better search granularity** (`wiki-search "timer 14-day" --types
known-issue --vaults all`).

### Per-issue file shape

```yaml
---
id: P-1                            # stable identifier (P-N for perf, S-N security, etc.)
type: known-issue
status: open                       # open | partially_closed | deferred | resolved | wontfix
opened_at: 2026-05-27
closed_at: null                    # set when status → resolved/wontfix
closing_commit: null               # git hash that closed it (for archaeology)
category: performance              # performance | security | logic | docs | ux
severity: SEV-1                    # SEV-1 (blocks scale) | SEV-2 (UX) | SEV-3 (cosmetic)
                                   # downgrade allowed: HIGH → MED after partial fix
slug: reindex-full-per-page-transactions

# Timer-based deferral (Universal-skills pattern — optional):
timer:
  started_at: null                 # date timer began
  deadline: null                   # auto-expire date
  on_expiry: promote-to-task       # promote-to-task | re-evaluate | escalate

# Lifecycle history — agent APPENDS, never overwrites:
history:
  - {date: 2026-05-27, event: opened, by: vdd-multi-iter-1, note: "Critic flagged"}
  # - {date: 2026-06-15, event: severity_downgrade, from: SEV-1, to: SEV-2, by: task-002-04}
  # - {date: 2026-07-01, event: partial_close, commit: abc1234, note: "Bulk-tx landed"}

# Cross-references (used by ref-extraction + auto_indexes):
affected_components:
  - scripts/wiki_index/reindex.py
  - scripts/wiki_index/sqlite_repository.py
related_adrs:    [ADR-002]
related_tasks:   []
related_issues:  []
backlog_row:     null              # link to backlog if this deferral has explicit ownership
---

# Per-page transactions in reindex_full

…full issue body, identical content to the current ledger entry…

## Workaround
…

## Fix path
…

## Do not
- Claim this as "fixed" by trimming X — that reduces Y not the structural Z.
```

### Agent-maintained lifecycle (mirrors Universal-skills convention)

The agent updates the per-issue file inline as work progresses:

| Trigger | Agent action |
|---|---|
| New issue surfaced (lint, vdd-multi, audit) | Create `docs/issues/<id>-<slug>.md` with `status: open`; append history entry |
| Partial fix lands | Update `status: partially_closed`, optionally downgrade `severity`, append history entry with commit hash |
| Full fix lands | Update `status: resolved`, set `closed_at` + `closing_commit`. **Then apply Resolution Policy (below).** |
| Operator decides "wontfix" | Update `status: wontfix` + `closed_at`; do NOT delete (decision rationale belongs in body) |
| Timer expires | Auto-promote: open a new task that references this issue; agent updates history entry |

### Resolution policy (choice — pin in config)

Three options for what happens when `status: resolved`:

| Policy | Behaviour | Pros | Cons |
|---|---|---|---|
| **A — Delete on fix** (Universal-skills current) | Delete `docs/issues/<id>-<slug>.md` in same commit as the fix. Text preserved in commit body. | Ledger stays focused on actionable items; matches existing practice | Resolved issues no longer in hot search (must use `git log`) |
| **B — Move to `resolved/`** | `git mv docs/issues/<id>.md docs/issues/resolved/<id>.md`; file stays indexed with `extra_tags: [resolved]` | History stays hot-searchable: "have we hit hash drift before?" answers yes via `wiki-search` | More git churn; auto-index needs separate Resolved section |
| **C — TTL + auto-archive** | Status=resolved stays in `docs/issues/` for 30 days, then auto-moves to `resolved/`. Eventual hot vs cold | Compromise: recent fixes still discoverable, ancient ones cold | More moving parts; clock dependency |

**Recommendation: A (Universal-skills convention)** for default. Operator
can switch to B via config `resolution_policy: preserve` if they want
long-term searchability over hot-ledger focus. C only if real signal
shows a "where did I see this last week?" pain point.

### Migration (one-shot, dogfooded here)

`scripts/migrate_known_issues_to_files.py` (~250-400 LoC + tests — see
re-estimate below):

**Pre-implementation step**: build a parsing acceptance fixture from
the current real `docs/KNOWN_ISSUES.md` of this repo (and a snapshot
of Universal-skills' KNOWN_ISSUES). Capture 5-15 issues that cover
the messy shapes:
- inline `Status:` runs across phases
- severity downgrades expressed in prose ("Originally HIGH, downgraded
  to MED after partial fix in commit abc1234")
- multi-tier sub-issues ("Logic-tier LOWs:" / "Security-tier LOWs:"
  block within a single deferral)
- timer-based deferrals ("14-day timer started YYYY-MM-DD")
- "Do not" anti-rationalisation blocks
- cross-links to backlog rows / ADR sections

The fixture lives at `tests/fixtures/known_issues_migration/` and is
the **acceptance bar** for PW-G. Round-trip parity = "after splitter →
render, ledger matches original modulo whitespace + the
GENERATED-AT header". Anything the splitter cannot round-trip cleanly
becomes an explicit operator-review step in step 5 below, NOT a silent
data loss.

**Splitter steps**:

1. Parse `docs/KNOWN_ISSUES.md` `##` and `###` headers; extract per-issue
   fields (Status, Severity, Location, etc.) into frontmatter.
2. Preserve all Universal-skills patterns: timer deferrals, multi-tier
   sub-issues (one parent file + sub-files OR one file with
   `sub_issues[]`), do-not blocks, cross-links, severity downgrade
   notes from prose.
3. Emit `docs/issues/<id>-<slug>.md` per issue, plus
   `docs/issues/.migration-report.md` listing every issue the splitter
   wasn't fully confident about (incomplete frontmatter, ambiguous
   nesting, etc.) — flagged for manual review.
4. Run `wiki-index-render --auto-indexes` (PW-H) to regenerate
   `docs/KNOWN_ISSUES.md` from the new files; output is a structured
   index, not a wall of text.
5. Agent + operator review `.migration-report.md` together, fix the
   flagged issues manually, re-render. Then operator approves, commits.

**LoC re-estimate**: the fixture-driven approach plus partial-confidence
report means PW-G is realistically 250-400 LoC + tests, not 120. The
splitter is 60% of that; tests + the migration-report emitter + the
operator-review tooling is the other 40%.

After migration, all subsequent issue updates go through the per-file
files. `docs/KNOWN_ISSUES.md` is auto-generated — header
`<!-- GENERATED-AT: <iso8601> by wiki-index-render --auto-indexes -->`
plus a sha256 of the rendered body stored in `.wiki/state.json`. Lint
rule `scripts/wiki_index/lint.py::check_auto_generated_unchanged`
re-renders to a temp buffer at lint time and compares; mismatch =
"manual edit detected, run `wiki-index-render --auto-indexes` to
overwrite, or move your edit into the per-issue file." (~30 LoC; folded
into existing `wiki-lint`, no new CLI surface.)

9. Write the splitter + renderer; migrate
    `obsidian-llm-wiki/docs/KNOWN_ISSUES.md` as the first dogfood. Then
    `wiki-search "hash drift" --types known-issue --vaults all` returns
    one specific issue, not the whole ledger.

### Phase E — Agent prompt integration (~1 day, depends on
agentic-development availability)

10. Add proactive `wiki-search` cue to developer / architect /
    critic-* prompts (the deferred R-2 from current ROADMAP).
11. Per `obsidian-llm-wiki/CLAUDE.md` "Knowledge lookup priority"
    rule, but pushed into subagent prompts where context isolation
    today blocks cross-project insight.

### Phase F — Epic 7 entity resolver lands (multi-week, separate
TASK)

12. Concept / entity nodes for development artifacts get first-class
    treatment.
13. `wiki-graph` traversals across project artifacts.
14. RAG-style synthesis: "Generate a meta-ROADMAP that consolidates
    all P0 items across active projects."
15. Resolve the §7.6 cross-vault `entity_slug` FK verification item
    before Phase F ships.

Phase A unlocks immediate value; B confirms the cross-project promise;
C through E build up the daily-usage friction floor; F is the
"compounding artifact" payoff.

---

## 9. Connection to existing ROADMAP

**Tracked in [`docs/ROADMAP.md`](../ROADMAP.md) §P2 "Cross-project
indexing" as five entries**:

| ROADMAP ID | Proposal section | Priority | Depends on |
|---|---|---|---|
| **R-X1** | §11 (PW-A..N + PW-Q — universal layout engine) | P2 | — |
| **R-X2** | §§2,4,8 Phases A-C (dev-vault + obsidian-personal bootstrap + archive hook) | P2 | R-X1 |
| **R-X3** | §Phase D (KNOWN_ISSUES → per-file migration) | P2 | R-X1, R-X2 |
| **R-X4** | §Phase E (agent-prompt cue integration) — **supersedes ROADMAP R-2** | P3 | R-X2 + agentic-development memory work |
| **R-X5** | §Phase F (entity-graph cross-project) | P3 | Epic 7 (ROADMAP R-3..R-5) + R-X2 |

**Interactions with other ROADMAP entries**:

- **P1 Epic 7 (entity resolver)** is the prerequisite for **R-X5 only**
  (Phase F). R-X1..R-X4 are independent — they don't need entity
  canonicalisation across projects.
- **P2 Epic 6 (source adapters)** is orthogonal — this proposal does
  not add a streaming-source adapter; it adds layouts to the existing
  config-driven engine.
- **ROADMAP R-2 (subagent prompt hook, currently DEFERRED)** is fully
  superseded by R-X4. Update R-2's status to `SUPERSEDED → R-X4`.

Priority slot: **P2**, ahead of Epic 6's source adapters (personal
payoff arrives sooner). R-X1+R-X2+R-X3 form the deliverable bundle;
R-X4 and R-X5 are P3 follow-ups gated on external work.

---

## 10. Naming

No new top-level brand. The dev-vault IS a wiki, just with development
artifacts as its sources. Extend `wiki-init` with a `--layout dev-project`
flag (and `--layout obsidian-personal` for the personal-vault case) and
that's the surface. Rejected alternatives, for the record:

- `wiki-dev-index` — generic, ambiguous.
- `wiki-meta` — too clever.
- `agentic-dev-vault` — descriptive but long.
- `wiki-project-index` — adds a new top-level command for what is
  fundamentally a config choice, not a new tool.

---

## 11. Pre-work — config-driven parser (universal layout engine)

The first draft of this section listed seven hardcoded patches
(PW-1..PW-7) to make obsidian-llm-wiki understand dev-project layout.
Reviewing the surface, **every one of those patches is a config value
masquerading as Python code**: hardcoded `PAGE_SUBDIRS`, hardcoded
`_PATH_TYPE_FALLBACK`, hardcoded `TYPE_MAPPING`, hardcoded ref-extraction
regex. Each new layout (dev-project, future formats) would require yet
another patch.

**Better path: externalise the layout into a YAML config**, let the
engine consume it. Karpathy, dev-project, and real-world Obsidian
personal vaults all become *instances of the same parser, with
different configs*. New layouts add config files, not code.

> **Anti-rationalisation check**: "config-driven" is not free.
> The config layer introduces its own bug surface — parse errors,
> schema drift, untested config combinations, ReDoS-prone operator
> regex (mitigated in PW-D), undefined behaviour on regex/template
> mismatch (pinned in PW-J error policy). The trade is: fewer code
> patches per new layout, more rigour required at config-load time.
> PW-A's JSON Schema validation + PW-D's ReDoS guard + PW-J's error
> policy are non-negotiable infrastructure, not nice-to-haves.

### Real-world Obsidian vault driving scope (2026-05-27)

A user's existing iCloud Obsidian vault has the structure:
- Numbered top-level folders: `01 - Inbox`, `02 - Personal Home`
- Folder + same-name MD (MOC pattern): `Household/` + `Household.md`
- Deep hierarchy: `02 - Personal Home/Purchases/Tradingview 06.09.2025.md`
- Underscore-prefixed system folders: `_daily/`, `_clippings/`,
  `_inbox/`, `_templates/`
- Multilingual filenames: `Квартиры.md` alongside `Household.md`
- Date-stamped filenames: `Tradingview 06.09.2025.md`
- Non-markdown content: `.base` files (Obsidian Bases)
- No frontmatter on most notes — standard Obsidian practice
- Service folders: `.obsidian/`, `.trash/`

This single real example **promoted six additional features from
"deferred" to "core"** in the config engine — see PW-J..PW-N below.
Without them, the engine handles maybe 60% of real Obsidian vaults
and breaks silently on the other 40%.

### Config schema (full surface)

`scripts/wiki_index/layouts/dev-project.yaml` (built-in, can be
overridden per-vault via `<vault>/.wiki/config.yaml` or
`WIKI_SCHEMA.md` frontmatter `layout_config:`):

```yaml
schema_version: '2.0'
layout: dev-project

# --- Global exclusions (PW-K) ----------------------------------------
# Patterns are evaluated before paths[] matching. Anything matching
# ignore[] is skipped entirely — never visited, never read.
ignore:
  - ".git/**"
  - ".obsidian/**"                       # Obsidian metadata
  - ".trash/**"                          # Obsidian trash
  - "_templates/**"                      # not content
  - "**/*.base"                          # Obsidian Bases — not md
  - "**/.DS_Store"                       # macOS noise
  - "**/.pytest_cache/**"
  - "**/__pycache__/**"

# --- File-extension allow-list (PW-M) -------------------------------
# Engine only reads `*.md` by default. Operator can extend.
file_extensions: [.md]

# --- Slug strategy (PW-N for multilingual content) -------------------
# Three options:
#  - preserve-unicode: keep original (Cyrillic, CJK survive — use when
#    operator's tooling can handle Unicode slugs end-to-end)
#  - transliterate: python-slugify's built-in transliteration
#    (Квартиры → kvartiry)
#  - ascii-only: strip non-ASCII entirely (LOSSY — last resort)
slug_strategy: transliterate

# --- Path matching ---------------------------------------------------
# Globs evaluated in order; first match wins. Files matching no
# pattern AND no ignore[] are emitted as warnings (PW-K lint).
paths:
  - {glob: "docs/tasks/*.md",            type: task}
  - {glob: "docs/plans/*.md",            type: plan}
  - {glob: "docs/adr/*.md",              type: adr}
  - {glob: "docs/reviews/*.md",          type: review}
  - {glob: "docs/audit/*.md",            type: audit}
  - {glob: "docs/architectures/*.md",    type: architecture}
  - {glob: "docs/product/*.md",          type: product-doc}
  - {glob: "docs/issues/*.md",           type: known-issue}
  - {glob: "docs/issues/resolved/*.md",  type: known-issue, extra_tags: [resolved]}
  - {glob: "docs/TASK.md",               type: task}
  - {glob: "docs/PLAN.md",               type: plan}
  - {glob: "docs/ARCHITECTURE.md",       type: architecture}
  - {glob: "docs/ROADMAP.md",            type: roadmap}
  - {glob: "docs/proposals/*.md",        type: proposal}

# --- Type mapping ----------------------------------------------------
# raw_type (from frontmatter or path inference) → DB shape.
# db_type MUST be one of pages.type CHECK enum
# (summary, concept, query, brief, research, index).
# tag goes into pages.tags JSON array for FTS5 filtering.
type_mapping:
  task:         {db_type: brief,    tag: task}
  plan:         {db_type: brief,    tag: plan}
  adr:          {db_type: research, tag: adr}
  review:       {db_type: research, tag: review}
  audit:        {db_type: research, tag: audit}
  architecture: {db_type: research, tag: architecture}
  roadmap:      {db_type: research, tag: roadmap}
  known-issue:  {db_type: research, tag: known-issue}
  product-doc:  {db_type: research, tag: product}
  proposal:     {db_type: research, tag: proposal}

# --- Ref extraction --------------------------------------------------
ref_extraction:
  - kind: wiki-link
    regex: '\[\[([^\]|]+)(?:\|[^\]]+)?\]\]'
    target_group: 1
  - kind: markdown-link
    regex: '\[([^\]]+)\]\(([^)]+\.md(?:#[^)]+)?)\)'
    target_group: 2
    transform: stem
  - kind: id-ref
    regex: '\b(ADR-\d+|R-\d+(?:\.\d+)*|task-\d+(?:-\d+)*|M-\d+|P-\d+|UC-\d+(?:\.\d+)*|PERF-\w+-\d+|Sec-\w+-\d+)\b'
    target_group: 1

# --- Auto-rendered indexes (extends wiki-index-render) ---------------
auto_indexes:
  - source_type: known-issue
    output: docs/KNOWN_ISSUES.md
    group_by: category
    sort_within_group: [severity, opened_at]
    template: assets/known-issues-ledger.md.tmpl

# --- Frontmatter synthesis (PW-F + PW-L fallback chain) -------------
# Inject minimal frontmatter for files without YAML.
frontmatter_synthesis:
  enabled: true
  title_source: first_h1
  fallback_title: filename_stem          # if no H1 in body
```

### Real-world example: `layouts/obsidian-personal.yaml` (built-in)

Built-in config for a typical personal Obsidian vault with numbered
top-level folders, underscore-prefixed system dirs, MOC pattern, deep
hierarchy, multilingual filenames, and `.base` files. **Drives the
full set of PW-J..PW-N features.**

```yaml
schema_version: '2.0'
layout: obsidian-personal

ignore:
  - ".obsidian/**"
  - ".trash/**"
  - "_templates/**"
  - "**/*.base"                          # Obsidian Bases — not md
  - "**/.DS_Store"

file_extensions: [.md]
slug_strategy: preserve-unicode          # Cyrillic survives end-to-end

paths:
  # --- Underscore system folders — explicit `project` per area ------
  - glob: "_daily/**/*.md"
    type: daily-note
    project: "_daily"
    default_tags: [daily]

  - glob: "_clippings/**/*.md"
    type: clipping
    project: "_clippings"
    default_tags: [clipping]

  - glob: "_inbox/**/*.md"
    type: note
    project: "_inbox"
    default_tags: [inbox, draft]

  # --- Numbered top-level folders (PW-J: project from path) ---------
  # NOTE: order matters — most specific glob first. Engine evaluates
  # paths[] in order; first match wins. Two entries here keep templates
  # as plain `${name}` substitution (no shell-style ternaries — see
  # PW-J §Substitution semantics).

  # Two-component project: "NN - Area/Sub/.../X.md" → project="Area/Sub"
  - glob: "[0-9][0-9] - */*/**/*.md"
    type: note
    project_pattern: '^(?P<num>\d+)\s*-\s*(?P<area>[^/]+)/(?P<sub>[^/]+)/'
    project_template: '${area}/${sub}'

  # Single-component project: "NN - Area/X.md" (no sub-folder) → project="Area"
  - glob: "[0-9][0-9] - */*.md"
    type: note
    project_pattern: '^(?P<num>\d+)\s*-\s*(?P<area>[^/]+)/'
    project_template: '${area}'

  # --- The MOC note itself: "02 - Personal Home.md" -----------------
  - glob: "[0-9][0-9] - *.md"
    type: note
    project_pattern: '^(?P<num>\d+)\s*-\s*(?P<area>[^.]+)\.md$'
    project_template: '${area}'
    extra_tags: [moc]

  # --- Standalone root-level notes (no folder, no number) -----------
  - glob: "*.md"
    type: note
    project: "_root_"

type_mapping:
  note:        {db_type: summary, tag: null}
  daily-note:  {db_type: summary, tag: daily}
  clipping:    {db_type: summary, tag: clipping}

frontmatter_synthesis:
  enabled: true
  title_source: first_h1
  fallback_title: filename_stem

ref_extraction:
  - kind: wiki-link
    regex: '\[\[([^\]|#]+)(?:#[^|\]]*)?(?:\|[^\]]+)?\]\]'
    target_group: 1
  - kind: markdown-link
    regex: '\[([^\]]+)\]\(([^)]+\.md(?:#[^)]+)?)\)'
    target_group: 2
    transform: stem
```

How a sample of files lands under this config:

| File path | matched glob | type | project | slug |
|---|---|---|---|---|
| `01 - Inbox.md` | `[0-9][0-9] - *.md` | `note` | `Inbox` | `01 - Inbox` (preserve) |
| `_daily/2026-05-26.md` | `_daily/**/*.md` | `daily-note` | `_daily` | `2026-05-26` (tag=`daily`) |
| `02 - Personal Home/Квартиры.md` | `[0-9][0-9] - */*.md` | `note` | `Personal Home` | `Квартиры` |
| `02 - Personal Home/Household/Household.md` | `[0-9][0-9] - */*/**/*.md` | `note` | `Personal Home/Household` | `Household` |
| `02 - Personal Home/Purchases/Tradingview 06.09.2025.md` | `[0-9][0-9] - */*/**/*.md` | `note` | `Personal Home/Purchases` | `Tradingview 06.09.2025` |
| `01 - Inbox (base).base` | `**/*.base` in ignore | — | — | (skipped) |
| `.obsidian/workspace.json` | `.obsidian/**` in ignore | — | — | (skipped) |

Three different `intake.md` files under `02 - Personal Home/X/`,
`02 - Personal Home/Y/`, `03 - Work/Z/` now land in **three different
`project` values** — no PK collision.

### Built-in layouts shipped with the engine

| Layout file | Use case |
|---|---|
| `karpathy.yaml` | Two-tier Karpathy vault (current `_sources/_concepts/_entities/Lessons/`) — built-in encodes today's hardcoded behaviour bit-for-bit |
| `dev-project.yaml` | Software project's `docs/` (TASK, PLAN, ADR, reviews, audit, issues, proposals) |
| `obsidian-personal.yaml` | Personal Obsidian vault: numbered top-levels, `_system/` folders, MOC pattern, multilingual, deep hierarchy |

Operators can extend or override any of these via
`<vault>/.wiki/config.yaml` or by writing their own
`<vault>/.wiki/layout.yaml` referenced from WIKI_SCHEMA frontmatter.

### Pre-work re-cast as engine generalisation

**LoC column** = `~<source>+<tests>` (tests run ~1.5-2× source for unit-heavy code).

| # | Change | File(s) | LoC (src+tests) | Why |
|---|---|---|---|---|
| **PW-A** | **Layout-config schema + loader** | `scripts/wiki_index/layout_config.py` + `scripts/wiki_index/layouts/{karpathy,dev-project,obsidian-personal}.yaml` + JSON Schema validation in `config_loader.py` | ~80+140 | Defines the config shape above. Validates with `jsonschema` (already a dependency). Caches per-vault. |
| **PW-B** | **Config-driven `discover_pages`** | `scripts/wiki_index/reindex.py` | ~40+80 | Replace hardcoded `PAGE_SUBDIRS` + course-tier walk with config-driven glob iteration. Existing Karpathy walk reproduced via built-in config (no behavioural drift). |
| **PW-C** | **Config-driven type inference** | `scripts/wiki_index/normalization.py` (delete `_PATH_TYPE_FALLBACK`; consume config `paths[].type` + first-H1 fallback) | ~30+50 | One code path; what differs between vaults is config, not the function. |
| **PW-D** | **Config-driven ref extraction** (with ReDoS guard) | `scripts/wiki_source/parsing.py::extract_wiki_links` → `extract_refs(body, config)` | ~60+120 | Drop hardcoded `_WIKILINK_RE`; iterate `config.ref_extraction[]`. Karpathy config carries only the wiki-link pattern → identical output. Dev-project config adds markdown-link and id-ref patterns. **ReDoS protection**: compile via the `regex` PyPI module (not stdlib `re`) and call `regex.compile(...).search(body, timeout=0.5)`. On timeout: log WARN with the offending pattern + skip that ref-extraction rule for the file. At config-load time, run every pattern against a 100KB synthetic-adversarial payload (`('a'*100 + 'b'*100) * 1000` etc.) and reject configs whose patterns exceed 10ms median — exit 6 with a clear error. Built-in `karpathy.yaml` / `dev-project.yaml` / `obsidian-personal.yaml` patterns are pre-vetted; the guard exists for operator-supplied configs. |
| **PW-E** | **Config-driven TYPE_MAPPING** | `scripts/wiki_index/normalization.py` (delete `TYPE_MAPPING` dict; consume config `type_mapping`) | ~20+40 | Same shape, just sourced from config. Built-in Karpathy config carries the current 13 entries verbatim. |
| **PW-F** | **Frontmatter synthesis** (with title fallback chain) | `scripts/wiki_source/parsing.py::parse_frontmatter` | ~60+100 | When file has no YAML block, synthesise `{type: <path-inferred>, title: <fallback>}`. Title source: first_h1 → filename_stem. Critical for Obsidian vaults where most notes have no frontmatter. |
| **PW-G** | **`KNOWN_ISSUES` splitter (one-shot)** | `scripts/migrate_known_issues_to_files.py` | ~280+200 | Per §Phase D below. Re-estimated 2026-05-27 against the fixture-driven acceptance bar: 60% splitter + 40% partial-confidence reporter + tests. Dogfooded on `docs/KNOWN_ISSUES.md` of this repo. Preserves Universal-skills-style rich fields (status, severity, timer, do-not blocks, cross-refs). |
| **PW-H** | **`wiki-index-render` extension for `auto_indexes[]`** | `scripts/wiki_index/rendering.py` + the entry point referenced by `commands/wiki-index-render.md` (currently `python -m scripts.wiki_index.commands.wiki_index_render` per the wrapper at `bin/wiki-index-render`) | ~80+130 | Currently renders one `index.md` per vault. Extend: walk `config.auto_indexes[]`, render each output (e.g. `docs/KNOWN_ISSUES.md` grouped by category, sorted by severity). Preserves `<!-- BEGIN-CUSTOM:name -->` blocks as today. **Render-trigger contract**: also invoked at the end of any `wiki-index-upsert` whose batch creates OR deletes a `type: known-issue` row (per §Phase D state-machine pin) — so the ledger stays consistent with `docs/issues/*.md` deletions without a separate hook. |
| **PW-J** | **`project` derivation from path pattern** (with error policy) | `scripts/wiki_index/reindex.py::discover_pages` + config schema | ~60+100 | Adds `paths[].project`, `paths[].project_pattern`, `paths[].project_template` fields. Engine derives `pages.project` via regex+template substitution (e.g., `02 - Personal Home/Household/X.md` → `project="Personal Home/Household"`). Solves the deep-hierarchy PK-collision problem for real Obsidian vaults. Karpathy config keeps the existing two-tier behaviour via `project_pattern: '^Lessons/(?P<course>[^/]+)/'` + `project_template: '${course}'`; root tier uses `project: "_vault_"` literal. **Template engine**: Python `string.Template` (`${name}` substitution only, NO shell-style `${name:+...}` or `${name-default}`). Conditional logic = split into multiple `paths[]` entries ordered specific-first. **Error policy**: (a) regex fails to compile at config-load → reject config, exit 6 with line/column in YAML; (b) glob matches a file but `project_pattern` doesn't match its path → log WARN `[unmatched-pattern] <file>` and assign `project: "_unmatched_"` (operator sees it in the index and can fix the config); (c) template references a named group not produced by the pattern → reject config at load, exit 6. |
| **PW-K** | **Global `ignore[]` patterns** | `scripts/wiki_index/layout_config.py` + `scripts/wiki_index/reindex.py::discover_pages` | ~20+50 | Top-level glob list evaluated BEFORE `paths[]` matching. Skips `.obsidian/**`, `.trash/**`, `_templates/**`, `**/*.base`, `**/.DS_Store`, etc. Critical for any real vault; today these would be walked and (mostly) rejected later in the pipeline — wasted I/O + risk of accidental partial-match. Implementation: use `pathlib.PurePath.match` only for non-recursive patterns; recursive (`**`) patterns require `fnmatch`-on-relative-path or a thin custom matcher — pin the chosen approach in PW-A schema validation tests. |
| **PW-L** | **UTF-8 / Cyrillic slug strategy** (with cross-platform caveats) | `scripts/wiki_index/normalization.py::_slugify_concept` + `scripts/wiki_source/parsing.py::derive_slug` | ~30+80 | Config field `slug_strategy: preserve-unicode \| transliterate \| ascii-only`. Today's hardcoded `slugify(..., regex_pattern=r'[^a-z0-9\-]')` strips Cyrillic completely (`Квартиры` → empty). New strategy table: preserve = `regex_pattern=r'[^\w\-]'` with `allow_unicode=True`; transliterate = current strict ASCII behaviour; ascii-only = lossy fallback (existing default). **Known limitations under `preserve-unicode`** (documented in the layout YAML comments): (a) shell quoting of non-ASCII CLI args is shell-dependent — `wiki-search --slug Квартиры` works in UTF-8 shells but breaks in locale-stripped environments; (b) APFS is case-insensitive by default while ext4 is case-sensitive — slugs differing only by case collide on macOS but not on Linux, so cross-platform vaults must avoid case-only distinctions; (c) iCloud sync may normalise NFC ↔ NFD between macOS and Linux clones, producing silent slug duplication. **Recommendation**: default `transliterate` for any vault that may be cross-platform synced; `preserve-unicode` only for single-OS workflows where the operator owns end-to-end tooling. |
| **PW-M** | **File-extension allow-list** | `scripts/wiki_index/reindex.py::discover_pages` | ~10+30 | Config field `file_extensions: [.md]` (default). Engine only walks files with allowed extensions. Skips `.base` (Obsidian Bases), `.canvas`, `.excalidraw`, etc. without operator listing each in `ignore[]`. |
| **PW-N** | **`paths[].default_tags` + `extra_tags`** | `scripts/wiki_index/normalization.py::normalize_frontmatter` | ~15+40 | Per-glob auto-tag injection. `default_tags: [inbox, draft]` on `_inbox/**/*.md` glob applies those tags to every matching file. `extra_tags: [moc]` on the same-name-md-as-folder glob. Merges with frontmatter `tags:` (de-duplicated). Eliminates need for operator to edit every existing note's frontmatter. |
| **PW-Q** | **`auto-generated` lint guard** | `scripts/wiki_index/lint.py::check_auto_generated_unchanged` | ~30+60 | New check: for every `auto_indexes[].output` target, store the sha256 of the last-rendered body in `.wiki/state.json`. Lint re-renders to a temp buffer at lint time and compares; mismatch → "manual edit detected at `<path>`, run `wiki-index-render --auto-indexes` to overwrite, or move your edit into the per-issue file." Bundled with PW-H; folded into existing `wiki-lint` CLI (no new command). |
| **PW-I** | **(deferred) `pages.type` enum extension** | `sql/wiki-index-v2.sql`, `docs/SCHEMA-v2.sql` | ~5 SQL | Long-term cleaner — native enum values instead of tag-route. Defer until usage validates the typing pattern. |
| **PW-O** | **(deferred) Date extraction from filename** | `scripts/wiki_source/parsing.py` | ~30+50 | Config field `date_extraction[]` with regex + groups. Auto-populates `pages.date` from filenames like `Tradingview 06.09.2025.md`. Nice ergonomic improvement but date can also live in frontmatter; defer to follow-up. |
| **PW-P** | **(deferred) MOC pattern recognition** | new helper in `scripts/wiki_index/` | ~40+80 | Detect folder + same-name MD (`Household/` + `Household.md`) → tag both as related; allow auto-rendered MOC sections. Defer — `extra_tags: [moc]` on a glob covers the common case for now. |

**Totals (core PW-A..N + PW-Q, deferring PW-I/O/P)**:
- Source: ~755 LoC
- Tests: ~1220 LoC
- **Combined: ~1975 LoC** in obsidian-llm-wiki.

That's an order of magnitude beyond my first estimate (~200 LoC for
path-aware patches), but the **payoff is durable**:
- No code change ever needed to add a new doc type, system folder,
  multilingual filename, or non-md content — just config entries.
- Karpathy, dev-project, and obsidian-personal share one engine,
  exercise the same code paths in tests.
- Future layouts drop in as config files.
- Real-world Obsidian vaults are first-class, not "you should
  restructure your vault to fit our schema."

**Order**:
- PW-A first (foundation everything depends on).
- PW-B / PW-C / PW-D / PW-E / PW-J / PW-K / PW-M in parallel (each
  replaces one hardcoded surface with a config consumer).
- PW-L (slug strategy) and PW-N (default_tags) next — small but cross-cut.
- PW-F (frontmatter synthesis) — depends on PW-A.
- PW-G + PW-H + PW-Q land together (splitter + renderer + lint guard)
  immediately before Phase D migration.
- PW-I / PW-O / PW-P deferred.

After all of the above, `scripts/wiki_source/dev_project.py` is **not
needed** — the config-driven engine handles every layout natively.
What remains is extending `wiki-init` with `--layout {karpathy,
dev-project, obsidian-personal}` flag handling (~80 source + ~120 test
LoC total, single CLI surface — not three separate commands; see §10)
that writes the appropriate `<vault>/WIKI_SCHEMA.md` with the chosen
`layout:` field.

### Sanity check: existing Karpathy vaults must continue to work

Acceptance criterion for PW-A..PW-N: **all current tests pass without
modification** after the engine is config-driven. The built-in
`karpathy.yaml` config encodes today's behaviour. `trade-agents`
re-reindexed under the new engine produces byte-identical SQL rows
modulo `last_modified` timestamps. This is the rebuildability invariant
in test form (ADR-002 §D8).

For the multilingual + deep-hierarchy fixtures (Obsidian-personal
vault), add a new test fixture `tests/fixtures/obsidian-personal-vault/`
with at least: a Cyrillic-named MD, a deep-hierarchy collision case
(three same-named files under different `<area>/<sub>/`), a `_inbox/`
draft, an `.obsidian/` directory, an ignored `.base` file. Acceptance:
all expected pages indexed with correct `project` values, no PK
collisions, no `.base` rows leaked into the index.

---

## 12. Dependency strategy — obsidian-llm-wiki ↔ agentic-development

Architectural question: who depends on whom, and how does the
agentic-development pipeline trigger indexing?

### Current state (one-way)

```
obsidian-llm-wiki  ←─ install.sh symlinks ─  agentic-development
                          (framework used as meta-tool)
```

obsidian-llm-wiki uses agentic-development for its own VDD pipeline.
Nothing flows back.

### What this proposal needs (reverse direction)

agentic-development's `skill-archive-task` should fire indexing after
rotating TASK.md / PLAN.md. Four strategies:

| Strategy | Coupling direction | Pros | Cons | Verdict |
|---|---|---|---|---|
| **A. Hard** — framework imports indexer code | framework → indexer | Tight integration | Framework loses generality; breaks projects without indexer | **NO** |
| **B. Inverted hard** — indexer monkey-patches framework | indexer → framework | One source of indexer-specific logic | Requires pub/sub mechanism the framework doesn't have | Defer |
| **C. Loose, shell-out + feature-detected** | none (subprocess) | Zero compile coupling; framework stays generic; indexer stays optional; mirrors how `wiki-enrich` shells out to `wiki-ingest` | Subprocess overhead per archive (~150-300ms cold-start of Python interpreter — tolerable at archival cadence, which is sub-1Hz); feature-detection logic | **PHASE 1 — DEFAULT** |
| **D. Formal hook spec** | framework defines, indexer implements | Cleanest separation; multiple indexers can plug in | Requires upfront hook design; YAGNI until 2nd indexer | Phase 2 |

### Option C — concrete sketch

Insertion point: **`agentic-development/.agent/tools/archive_protocol.py::archive_task()`**
(confirmed canonical path; the `skill-archive-task` SKILL.md is the
protocol doc, the Python module is the executable mirror — patch the
Python module, not the markdown).

```python
def archive_task(task_path: Path) -> Path:
    archived = _rotate_file(task_path)        # existing behaviour
    _maybe_index(archived)                     # NEW — best-effort
    return archived

def _maybe_index(archived_path: Path) -> None:
    """Feature-detected shell-out. Fails silently for the caller — but
    every failure mode is logged to ~/.cache/wiki-index/pending.log so
    operators can replay via `wiki-reindex --replay-pending`."""
    if not shutil.which("wiki-index-upsert"):
        return  # no indexer on PATH — silent, nothing to log
    vault_id = _detect_dev_vault_id(archived_path)
    if not vault_id:
        return  # this project isn't a dev-vault — silent
    try:
        result = subprocess.run(
            ["wiki-index-upsert",
             "--vault", vault_id,
             "--source", str(archived_path)],
            capture_output=True, timeout=10, check=False,
        )
        if result.returncode != 0:
            _log_pending(archived_path, vault_id,
                         f"exit={result.returncode}",
                         result.stderr[:500].decode("utf-8", "replace"))
    except subprocess.TimeoutExpired:
        _log_pending(archived_path, vault_id, "timeout", "10s exceeded")
    except OSError as e:
        _log_pending(archived_path, vault_id, "oserror", str(e))

def _log_pending(path: Path, vault_id: str, kind: str, detail: str) -> None:
    """Append one JSON line per failure to a user-cache log. ~10 LoC;
    indexer's `wiki-reindex --replay-pending` consumes + clears it."""
    log = Path.home() / ".cache" / "wiki-index" / "pending.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": datetime.utcnow().isoformat(), "vault_id": vault_id,
             "path": str(path), "kind": kind, "detail": detail}
    with log.open("a") as f:
        f.write(json.dumps(entry) + "\n")

def _detect_dev_vault_id(any_doc_path: Path) -> str | None:
    """Walk up from any document looking for docs/WIKI_SCHEMA.md
    with `layout: dev-project`. Cached per-process by repo root."""
    ...
```

**Observability invariant**: archival NEVER raises due to indexing,
but every drop is logged. Operator can periodically run
`wiki-reindex --replay-pending` to ingest the backlog and truncate the
log. Without this, a silently-stale index has no breadcrumb.

This is **symmetric** with how `wiki-enrich` shells out to wiki-ingest:
both sides feature-detect via PATH; both fail-fast gracefully; neither
imports the other's code.

### Filesystem layout (already correct)

```
~/dev-projects/
├── agentic-development/         # framework, peer
├── obsidian-llm-wiki/            # this repo, peer
├── trade-agents/                 # user vault, peer
└── Universal-skills/             # peer skill projects (wiki-ingest)
```

All peers, none nested. Runtime connections via three installers:

1. `agentic-development/install.sh` — wires framework into target project.
2. `obsidian-llm-wiki/bin/install-globally.sh` — wires wiki-* commands
   into `~/.local/bin/` and `~/.claude/skills/`.
3. Universal-skills install (per-skill `assets/install.sh` or symlink
   into `~/.claude/skills/`).

After all three: `skill-archive-task` finds `wiki-index-upsert` via
PATH; no knowledge of obsidian-llm-wiki's filesystem location required.

### What goes into agentic-development (Phase E of rollout)

A small, optional, feature-detected modification:

1. ~30 lines in `skill-archive-task`'s archival script (the
   `_maybe_index` snippet above).
2. Optional similar hook in developer / architect / critic-* prompts:
   "before introducing new names or editing concept pages, run
   `wiki-search` if available."
3. **No new files in agentic-development that mention obsidian-llm-wiki**.
   Indexer remains optional; framework remains general.

### Long-term — Option D when second indexer appears

If you ever add a second indexer (Postgres backend, vector store,
external service), promote to a formal hook spec — symmetric to how
Claude Code's `.claude/hooks/` already works:

```yaml
# .agent/hooks/post-archive.yaml (future)
hooks:
  post-archive-task:
    - command: wiki-index-upsert
      args: ["--vault", "$VAULT_ID", "--source", "$ARCHIVED_PATH"]
      on-error: log-and-continue
    - command: my-other-indexer
      args: [...]
```

Don't build until the second indexer exists. YAGNI.

---

## 13. Bottom line

Indexing agentic-development artifacts + real-world Obsidian vaults is
**two engineering bets** that together unlock cross-project memory:

1. **Universalise the layout engine** (§11) — replace 15 hardcoded
   surfaces (PW-A..N + PW-Q lint guard) with a YAML-config-driven
   parser. Karpathy, dev-project, and obsidian-personal become three
   instances of the same engine. ~755 source + ~1220 test LoC in this
   repo. Pays off forever: new layouts (and even non-trivial vault
   structures with deep hierarchy, multilingual filenames, system
   folders, MOC patterns) add config, not code.
2. **Hook agentic-development's archival into wiki-index-upsert**
   (§12 Option C) — feature-detected, fail-silent + observable via
   `pending.log`. ~60 source + ~80 test LoC in
   `agentic-development/.agent/tools/archive_protocol.py`. No
   compile-time coupling either direction.

Plus a one-shot KNOWN_ISSUES migration (§Phase D) that dogfoods the
config-driven engine and reproduces the Universal-skills agent-
maintained-status workflow in per-file form. Migration size included
in PW-G above.

**Total**: ~815 source + ~1300 test = **~2115 LoC** across two repos.
~2.5-3 week focused task (could be smaller if scope-trimmed — see
below). Test cost is ~60% of total; cuts to test budget should be
deliberate, not assumed.

**The payoff is durable**: every TASK / PLAN / ADR / review / audit /
known-issue / proposal across every project AND every Obsidian
personal vault (with whatever exotic structure) becomes queryable,
ranked, snippetted, cross-referenced — without per-doc-type or
per-layout Python patches.

### Honest-scope tier (when scope-trimming)

If real signal arrives faster than the full proposal can be built,
ship in three layers:

- **Tier 1 — Minimum viable indexing (~440 LoC source + ~700 LoC tests,
  ~5-6 days)**:
  - PW-A (config schema)
  - PW-B (config-driven discover_pages)
  - PW-E (config-driven type_mapping)
  - PW-J (project from path — **critical for any non-flat vault**)
  - PW-K (ignore[] — critical for skipping `.obsidian/`, `.trash/`)
  - PW-M (file_extensions allow-list — skips `.base` etc.)
  - PW-G (KNOWN_ISSUES splitter)
  - PW-H (auto-rendered indexes — **bundled with PW-G**: splitting
    without rendering removes the existing ledger view with no
    replacement, which is a regression. Always ship together.)

  This is enough to index dev-projects AND real Obsidian vaults. No
  agentic-development hook yet — operators run `wiki-reindex --delta`
  manually after commits.

- **Tier 2 — Polish (+~150 LoC source + ~250 LoC tests)**: PW-C / PW-D /
  PW-F / PW-L / PW-N. Adds proper ref extraction, frontmatter synthesis
  with H1 fallback, multilingual slug handling, default_tags injection.
  Search ranking + cross-references work right.

- **Tier 3 — Automation (+~140 LoC source + ~200 LoC tests, across two
  repos)**: `wiki-init --layout {dev-project,obsidian-personal}` flag
  handling (single CLI surface) + Option C shell-out hook in
  agentic-development's `archive_protocol.py::archive_task()` with
  `pending.log` observability.

- **Deferred indefinitely**: PW-I (enum extension), PW-O (date
  extraction), PW-P (MOC pattern recognition).

Trigger to start: when you find yourself running `git grep` across 3+
repos for the same concept twice in the same session, OR when you
want to ask "where in my Obsidian vault did I write about X?" and
the answer requires opening Obsidian's slow search. That's the moment
the manual cost exceeds the build cost.

---

## 14. Decision deferred

This is a **PROPOSAL**, not a decision. Open questions waiting for
real-world signal:

- Is cross-project search actually used? Or do operators stay in one
  repo at a time?
- Does `skill-archive-task` integration help or just couple skills?
- Is dev-project layout discoverable by agents naturally, or do we
  need explicit prompts?

Revisit when:
- A second project is dogfood-ready (Universal-skills TASK 017 ships).
- A real cross-project query failure surfaces ("I know we discussed X
  somewhere but can't find it").
- Epic 7 entity resolver gets prioritised.
