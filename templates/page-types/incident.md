---
type: incident
title: "<what happened — e.g. 2026-06 queue overflow outage>"
tags: []
status: resolved           # open | mitigated | resolved
severity: 2                # 1 (critical) .. 4
date: 2026-01-01           # detection date
# --- event-graph edges (TASK 032/034) — authored ONE direction, inverse AUTO-DERIVED on reindex ---
# `caused_by` is the high-value edge (decision → incident); `invalidates` is what lets an
# incident retire a decision in a `wiki-search --as-of` query (TASK 034).
caused_by: []              # the decision / change / risk that led to this incident (→ causes)
invalidates: []            # decisions this incident VOIDS                          (→ invalidated-by)
relates_to: []             # the [[risk]] it materialised
---

# <Incident title>

## Summary
<One-paragraph what/when/impact.>

## Timeline
- <ts> — <event>

## Root cause
<The underlying cause.>

## Resolution & follow-ups
<How it was resolved; action items (tasks).>
