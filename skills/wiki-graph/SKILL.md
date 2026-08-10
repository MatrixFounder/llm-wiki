---
name: wiki-graph
description: >-
  Traverse the event graph — the typed page-to-page edges (implements /
  supersedes / causes / relates-to + their auto-derived inverses) between
  knowledge-class pages (decision, requirement, risk, incident, …). Read-only:
  inbound backlinks, one-hop neighbors (in/out/both, by edge kind), and bounded
  supersession/causation chains. Triggers: "what did this decision cause",
  "what supersedes X", "the decision lineage", "what implements this requirement",
  "wiki-graph", "trace the chain". NOT for full-text lookup — use wiki-search /
  wiki-query for finding or answering ABOUT content.
tier: 2
version: 1.0
---

# wiki-graph

Read-only traversal of the TASK 032 / ADR-004 **event graph**: the typed edges in
`page_entity_refs` (`implements`/`implemented-by`, `supersedes`/`superseded-by`,
`causes`/`caused-by`, symmetric `related`). Edges are authored in page frontmatter
(`implements: [[req-x]]`, `caused_by: [[inc-y]]`, …) and indexed on `wiki-reindex`;
inverse edges are auto-derived, so authoring ONE direction makes both queryable.

Run it in your shell (the index DB is resolved like the other `wiki-*` CLIs):

```bash
# inbound: who points AT this page (optionally one edge kind)
wiki-graph backlinks <slug> --vault <id> [--kind implements]

# one-hop neighbors (in / out / both), optionally filtered by edge kind
wiki-graph neighbors <slug> --vault <id> [--direction both] [--kind causes]

# bounded, cycle-safe chain over ONE edge kind (e.g. the supersession lineage)
wiki-graph chain <slug> --vault <id> --kind supersedes [--direction out] [--depth 8]
```

Every **completed subcommand invocation** prints a one-line JSON envelope (pipe to
`python3 -m json.tool`). ⚠️ Not *every* invocation: an argparse refusal (unrecognised flag,
missing subcommand) writes usage to **stderr**, exits **2**, and prints **nothing** to stdout —
so `json.loads(stdout)` on that path fails. Branch on the exit code first (DF-072-3).
`--kind` is validated against the edge ref_types (an invalid one → `INVALID_KIND`,
exit 2, without echoing the value); `chain` requires `--kind`; `--depth` is capped
(cycle-safe). `--db-path` / `--vault-root` resolve the index DB (TASK 022).

## Routing
- Find or answer ABOUT content → `wiki-search` / `wiki-query` FIRST (unchanged).
- Pull a decision's *consequences* / lineage / what-implements-what → `wiki-graph`.
- `wiki-query prepare --follow-edges` weaves graph neighbors into a cited RAG answer.

## Examples
- "What did the RabbitMQ decision cause?" → `wiki-graph neighbors use-rabbitmq --vault v --kind causes --direction out`.
- "Show the decision lineage" → `wiki-graph chain decision-v3 --vault v --kind supersedes`.
- "What implements this requirement?" → `wiki-graph backlinks req-throughput --vault v --kind implements`.
