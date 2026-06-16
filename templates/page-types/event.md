---
type: event
title: "<what occurred — e.g. Release 4.3 shipped>"
tags: []
kind: release              # meeting | release | milestone | deploy | other
date: 2026-01-01           # when it occurred — the timestamp `wiki-search --as-of` keys on
# --- event-graph edges (TASK 032/034) — authored ONE direction, inverse AUTO-DERIVED on reindex ---
# An event is a dated hub: it can ACTIVATE a decision (TASK 034) and CAUSE incidents.
activates: []              # decisions this event puts into effect (→ activated-by)
causes: []                 # incidents / events this one triggers  (→ caused-by)
relates_to: []
---

# <Event title>

## What happened
<A timestamped narrative record of the occurrence.>

## Links
<The [[decision]]s it activated, tasks spawned, [[incident]]s it triggered — traverse with `wiki-graph`.>
