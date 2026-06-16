---
type: agent
title: "<agent name — e.g. Claude Code>"
tags: []
status: active              # active | deprecated | retired
date: 2026-01-01
# --- event-graph edges (TASK 032/034) — authored forward, inverse AUTO-DERIVED ---
# Values may be IDs or [[wikilinks]]; leave [] if unused. `wiki-graph` traverses these.
uses: []                    # tools / CLIs this agent invokes        (→ used-by)
implements: []              # capabilities this agent provides       (→ implemented-by)
owns: []                    # workflows this agent owns / runs        (→ owned-by)
relates_to: []
# Temporal: `wiki-search --as-of` derives "active on date X" from `date` + the
# supersede/invalidate graph — no valid_to needed. Add optional `valid_from:`/`valid_to:`
# ONLY to override (future-effective / known retirement date).
---

# <Agent name>

## Role
<What this agent is responsible for.>

## Capabilities
<What it can do — link `[[capability]]` pages it `implements`.>

## Tools
<Which `[[tool]]` pages it `uses`.>
