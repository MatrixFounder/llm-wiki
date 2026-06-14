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

## Phase 2 — the event graph (deferred, ROADMAP R-13)

The templates reserve five **edge keys** — `implements`, `supersedes`, `superseded_by`,
`caused_by`, `relates_to` — as authored-but-**inert** frontmatter. Phase 1 ignores them
(classification only). When Phase 2 ships (typed `page_entity_refs.ref_type` edges +
reindex frontmatter-edge extraction, TASK 008 precedent), these become the typed
page-to-page edges of the event graph (decision → task → commit → release → incident) —
**with no re-authoring**, because the canonical Markdown already carries them
(Markdown canonical, DB rebuildable — ADR-002 §D8). See ADR-003 D4.
