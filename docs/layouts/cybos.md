# The `cybos` layout — typed knowledge classes ("operational memory")

> TASK 031 / R-031-1/2 · ADR-003 · built-in: `scripts/wiki_index/layouts/cybos.yaml`

`cybos` is a built-in layout for an **operational-memory / event-graph vault** — a
knowledge base whose value lives in *changes*, not just entities: Decisions,
Requirements, Risks, Incidents, Hypotheses, Facts, and Events, plus the engineering
spine (Tasks, ADRs, Plans). It is the home for the "CybOS 2.0" typed-knowledge vision.

It is **opt-in** and changes nothing for existing vaults:

```bash
wiki-init --scaffold-new --layout cybos --vault /path/to/vault
```

`cybos` is an *existing-tree* layout (`init_scaffold: none`) — `wiki-init` writes
`WIKI_SCHEMA.md` + the agent file and registers the vault, but does **not** scaffold the
Karpathy `_sources/_concepts/…` two-tier tree. You create the folders below.

## Folders → types

Each knowledge class is a top-level folder (`paths[]` glob, first-match-wins). A note's
type comes from its folder (no frontmatter `type:` required), or from an explicit
`type:` if you keep notes elsewhere.

| Folder | raw `type:` | `pages.type` (db_type) | tag |
|---|---|---|---|
| `decisions/` | decision | research | `decision` |
| `requirements/` | requirement | brief | `requirement` |
| `risks/` | risk | research | `risk` |
| `incidents/` | incident | research | `incident` |
| `hypotheses/` | hypothesis | research | `hypothesis` |
| `facts/` | fact | concept | `fact` |
| `events/` | event | summary | `event` |
| `tasks/` | task | brief | `task` |
| `adr/` | adr | research | `adr` |
| `plans/` | plan | brief | `plan` |

**Zero DDL.** Every class tag-routes onto the existing 7-value `pages.type` enum
(`summary`, `concept`, `query`, `brief`, `research`, `index`, `verification`) — no
schema migration. db_type rationale: *research* = analysis culminating in a finding;
*brief* = concise spec/task; *concept* = atomic definitional unit; *summary* =
timestamped narrative record (ADR-003 D1).

## Authoring a note

Copy the matching template from `templates/page-types/<type>.md` (each carries the
canonical frontmatter). Example decision (`decisions/use-rabbitmq.md`):

```markdown
---
type: decision
title: "Use RabbitMQ for async messaging"
status: accepted
date: 2026-05-12
---

# Use RabbitMQ for async messaging

## Context
Polling the DB for work does not scale past ~N msg/s.

## Decision
Adopt RabbitMQ (AMQP 0-9-1) for async task dispatch.

## Consequences
+ decoupled producers/consumers; − new operational dependency.
```

Frontmatter-less notes also work — the title is synthesised from the first `# H1`.

## Finding typed knowledge

Per-class retrieval in Phase 1 is **FTS on the tag word** (the routed tag is an FTS
column), optionally **narrowed by `--types <db_type>`**. It is NOT a scalar field
match: the routed tag lands in the `tags:` **list**, and `wiki-search --where` is
scalar-equality on a `json_extract` (it cannot match a list element).

```bash
# primary per-class retrieval — FTS on the tag word (each class's tag returns its notes):
wiki-search <vault> "decision"           # -> the decision notes
wiki-search <vault> "incident"           # -> the incident notes

# narrow an FTS query to a db_type bucket with --types (a FILTER on a query, not a
# standalone lister — `--types research` alone returns nothing):
wiki-search <vault> "RabbitMQ" --types concept     # RabbitMQ hits, narrowed to facts
wiki-search <vault> "queue" --types research       # queue hits, narrowed to the research bucket
```

> A standalone single-predicate list-membership filter (e.g. `--tag decision`, or a
> "list every page of type X") is a documented follow-on (ROADMAP) — Phase 1 uses the
> FTS tag word above.

## Per-project customisation (no fork, no Python)

Add a bespoke type or extra ignore globs for one vault via
`<vault>/.wiki/layout.yaml` — `type_mapping` **UNIONs** with the built-in cybos
mapping (and `ignore` UNIONs); `paths`/`ref_extraction` **REPLACE** wholesale if you
supply them (so re-declare the built-ins if you extend those):

```yaml
# <vault>/.wiki/layout.yaml
type_mapping:
  risk-register: {db_type: research, tag: risk-register}   # added to the built-ins
ignore:
  - "drafts/**"                                             # extends the base ignores
```

## The event graph — typed edges (TASK 032 / ADR-004, ✅ LIVE)

The edge keys — `implements`, `supersedes`, `superseded_by`, `caused_by`, `relates_to`
(+ the directly-authorable `implemented_by`/`causes`) — are now **extracted as typed
page-to-page edges** on `wiki-reindex` (schema v6). Author ONE direction; the **inverse
is auto-derived** (`implements`↔`implemented-by`, `supersedes`↔`superseded-by`,
`causes`↔`caused-by`; `relates_to` is symmetric `related`). Values are `[[wikilinks]]`
or bare slugs, scalar or a list. Orphan targets keep a forward link but derive no inverse.

```yaml
# decisions/use-rabbitmq.md
type: decision
implements: [[req-throughput]]      # → req-throughput is implemented-by this decision
caused_by: [[inc-queue-overflow]]   # → that incident causes this decision (inverse derived)
supersedes: [[decision-v1]]         # → decision-v1 superseded-by this one
```

Query the graph (read-only):

```bash
wiki-graph backlinks req-throughput --vault <id> --kind implements   # who implements it
wiki-graph neighbors use-rabbitmq  --vault <id> --direction both      # one-hop edges
wiki-graph chain     decision-v3   --vault <id> --kind supersedes     # supersession lineage
```

…or weave the graph into a cited RAG answer:

```bash
wiki-query prepare "what did the RabbitMQ decision cause?" --vault <id> --follow-edges
```

`--follow-edges` (default OFF) expands the FTS hits along typed edges (depth 1, capped 3),
deterministically (folded into `question_hash`). Markdown stays canonical; the graph is a
rebuildable Class-B projection (ADR-002 §D8 / ADR-004). Delta refreshes edge *additions*;
edge/source *removals* are repaired by `wiki-reindex --full` (provenance-safe — ADR-004 D4).
