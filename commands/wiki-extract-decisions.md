---
description: Typed-knowledge extraction (RFC-004) — prepare (recon + the ontology contract) → orchestrator synthesises candidates → apply (validates against the ontology, then writes typed pages + edges). Turns a meeting protocol into decision/requirement/risk pages.
---

Two-pass orchestrator workflow (TASK 063 / RFC-004, Decision-17).

Turns a summarised source note into **typed knowledge**: `decision` /
`requirement` / `risk` pages plus the typed edges between them — the pages
TASK 062 proved a human can extract by hand from a meeting protocol, and
proved are worth having (they produced the vault's first EARNED ontology
green).

The CLI is deterministic and **never calls an LLM** — the orchestrator owns
the REASON step. The prompt/contract lives in
`.agent/skills/decision-extraction/SKILL.md`.

```bash
wiki-extract-decisions prepare --vault X --vault-root Y --source-page Z

# → the orchestrator reads the source body + the emitted ONTOLOGY CONTRACT
#   (class roster, edge domain/range, per-class status enums), synthesises
#   candidates JSON, then:

wiki-extract-decisions apply --vault X --vault-root Y --source-page Z \
                             --source-hash <the hash prepare emitted> \
                             --candidates-stdin [--ingest]
```

## What `prepare` refuses, and why it refuses EARLY

`prepare` PREFLIGHTS the layout (G4). If the vault's layout maps no typed
classes, or the configured folder is invisible to the layout's read globs, it
REFUSES before any reasoning is asked for.

That refusal costs you one message. The alternative costs you a decision page
that was **written, never indexed, and raised no lint issue** — because a
glob-invisible page is never discovered by the walk, so nothing downstream can
report it. `wiki-config validate` renders the same refusal, from the same
helper, at config-edit time.

## What `apply` refuses

Any contract violation ⇒ **exit 4 and ZERO files written**. A partially written
typed batch is worse than none: the graph would assert edges to pages that do
not exist. The candidates are validated against the ontology BEFORE the first
write — class ∈ roster, edge domain, edge RANGE (a target outside the batch is
resolved from the index), `status` ∈ that class's enum.

## An empty result is a SUCCESS

`action: no_candidates`, exit 0. A note with no decisions in it is a normal
note. If "no decisions" were a failure, the cheapest way to a green run would
be to invent one.
