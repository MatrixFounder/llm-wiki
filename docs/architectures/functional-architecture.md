# 2. Functional Architecture

> Part of [docs/ARCHITECTURE.md](../ARCHITECTURE.md). The functional architecture is split
> across the files in [functional/](./functional/) — **this page is the map**. Cross-references
> of the form "functional-architecture.md §2.x" resolve here, then to the linked file below.

## Contents

| § | Section | Details |
|---|---|---|
| **2.1** | **Functional Components** — the component catalog: Configuration Resolver · Index Layer (DAL) · Source Adapters · Skill Layer · Concept Extractor · Entity Resolver · RAG Query Layer · Verification Layer · Workflow Orchestrator · Migration Tools · + the components diagram | [functional/components.md](./functional/components.md) |
| **2.2** | **Native-App Control Skill** (`obsidian-cli`, TASK 029) — routing / coherence / safety / degradation invariants + **active-note resolution** (§2.2.1, TASK 041 / ADR-008) | [functional/native-app-control.md](./functional/native-app-control.md) |
| **2.3** | **The construct path** (`wiki-import`, TASK 039) — one pipeline, two orthogonal axes; **hardening** (§2.3.1) · **transcript-fetcher** (§2.3.2) · **embedded-video** (§2.3.3) · **converged pipeline** (§2.3.4) + the superseded legacy PARA framing | [functional/construct-path.md](./functional/construct-path.md) |
| **2.4** | **Policy-before-model retrieval scoping** (TASK 049 / R-16) + **read-side audit & derived trust tier** (§2.4.1, TASK 050 / R-17) | [functional/policy-and-trust.md](./functional/policy-and-trust.md) |
| **—** | **Sync Dispatcher** (`wiki-sync`, TASK 018 / R-11) — the batch driver: classification · plan JSON · execution workflow · source freshness & the connector contract (a component of §2.1, detailed here) | [functional/sync-dispatcher.md](./functional/sync-dispatcher.md) |
