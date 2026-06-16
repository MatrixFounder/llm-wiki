---
type: execution
title: "<run label — e.g. wiki-sync run 2026-06-16>"
tags: []
status: success            # success | failed | partial
date: 2026-01-01           # when the run occurred
agent: ""                  # the agent that ran it (free-text; or use the `uses` edge)
workflow: ""               # the workflow executed (free-text; or the `relates_to` edge)
# --- event-graph edges (TASK 032/034) — authored forward, inverse AUTO-DERIVED ---
caused_by: []              # the event / trigger that produced this run (→ causes)
relates_to: []             # the [[workflow]] / [[tool]] involved
---

# <Run label>

## Summary
<What ran, with what inputs.>

## Outcome
<Result; success/failure and why.>

## Errors
<Failures encountered (drives RFC-003 "which workflows fail most" once aggregation lands).>
