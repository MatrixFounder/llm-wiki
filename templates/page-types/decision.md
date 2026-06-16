---
type: decision
title: "<short imperative — e.g. Use RabbitMQ for async messaging>"
tags: []
status: proposed            # proposed | accepted | superseded | rejected
date: 2026-01-01
deciders: []
# --- event-graph edges (TASK 032/034) — authored ONE direction, inverse AUTO-DERIVED on reindex ---
# Values: [[wikilinks]] / slugs / IDs (DEC-/REQ-/INC-…), scalar or list. Leave [] if unused. `wiki-graph` traverses these.
implements: []              # requirements this decision satisfies          (→ implemented-by)
supersedes: []              # prior decisions this replaces                 (→ superseded-by)
superseded_by: []           # a later decision that replaces this one       (→ supersedes)
causes: []                  # incidents / events this decision brings about (→ caused-by)
invalidated_by: []          # an incident that VOIDS this decision          (→ invalidates) — read by `--as-of`
activated_by: []            # an event that PUTS this decision into effect  (→ activates)
relates_to: []
# Temporal: `wiki-search --as-of` derives "active on date X" from `date` + the supersede/invalidate
# graph — no valid_to needed. Add optional `valid_from:` / `valid_to:` ONLY to override (future-effective / sunset).
---

# <Decision title>

## Context
<What forces / constraints are at play? What problem prompts the choice?>

## Decision
<The choice made, stated plainly.>

## Consequences
<Positive / negative / neutral outcomes.>
