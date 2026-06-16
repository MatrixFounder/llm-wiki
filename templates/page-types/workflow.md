---
type: workflow
title: "<workflow name — e.g. wiki-sync>"
tags: []
status: draft               # draft | active | deprecated | superseded  (RFC-005 lifecycle)
date: 2026-01-01
# --- event-graph edges (TASK 032/034) — authored forward, inverse AUTO-DERIVED ---
# A workflow lineage (v1 → v2 → v3) is a `supersedes` chain — query it with
# `wiki-graph chain --kind supersedes <slug>`.
supersedes: []              # prior workflow version this replaces    (→ superseded-by)
superseded_by: []
owned_by: []                # the agent that owns / runs this workflow (→ owns)
uses: []                    # tools the workflow invokes              (→ used-by)
relates_to: []
---

# <Workflow name>

## Purpose
<What this workflow accomplishes.>

## Steps
<Ordered steps.>

## States
<draft → active → deprecated/superseded; what triggers each transition.>
