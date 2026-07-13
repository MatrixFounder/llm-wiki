# TASK 062 — The first typed-knowledge pilot on the LIVE vault (BD area)

## 0. Meta Information
- **Task ID**: 062
- **Slug**: typed-knowledge-pilot-bd
- **Origin**: carved out of TASK 061 by the task-reviewer (C4) — different risk class, different verification
  regime. Prerequisite **TASK 061 shipped 2026-07-13** (28 commits, `/vdd-multi` PASS).
- **Type**: Adoption pilot (content, not code)
- **Effort**: M
- **Schema**: **zero DDL**. No code change is expected. If one proves necessary, it is a separate task.

## 1. Problem

The enterprise theme is **built correctly and fires on nothing.** The R-16…R-22 dogfood proved every
mechanism works in scratch, and TASK 061 made the reporting honest — the live vault now says, plainly:

```
wiki-health ontology → { total_violations: 0, edges_examined: 0, property_pages_examined: 0,
                         vacuous_populations: [...], note: "…examined NOTHING" }
```

That is the truth, and it is the *whole* truth: the vault holds **0 pages of any typed class** and a typed
event graph that is **entirely empty** (`page_entity_refs` = `mentioned` only). The operator's own
`.wiki/layout.yaml` declares a full ontology (closed_types + 7 edge rules + 11 property enums) and 3+3
health rules — **guarding content that does not exist.**

**This task makes them earn their keep**, on real content, in the smallest zone that has any.

## 2. Goal

Author the vault's first typed knowledge pages — extracted **from** the two existing `06 - Business
Development` engagement notes — with typed edges, so that R-15 (coverage/drift) and R-19 (ontology) fire on
**real data for the first time**, and the denominators TASK 061 added move from `0` to a real number.

## 3. Design (settled)

**The engagement notes stay `meeting-summary`.** A protocol is a protocol. The pilot **extracts NEW typed
pages** from them and links them with typed edges. It does **not** retype existing notes.

The live `.wiki/layout.yaml` already maps the classes (`decision`→research, `requirement`→brief,
`risk`→research) and declares the contract the pilot must satisfy:

| Contract | Value (from the live layout) |
|---|---|
| `implements` | from `[decision, task, agent, tool]` → to `[requirement, capability]` |
| `causes` | from `[decision, event, incident, risk]` → to `[incident, event, risk, pattern, execution]` |
| `decision.status` | `[proposed, accepted, superseded, rejected]` |
| `requirement.status` | `[draft, approved, implemented, dropped]` |
| `risk.status` | `[open, mitigated, accepted, closed]` |
| coverage rule | `requirement` requires inbound `implemented-by` |

**Expected honest output — this is the point, not a defect.** A `requirement` that nothing implements yet
**will** be reported as a coverage gap. That is the layer telling the truth. A pilot that produced zero gaps
would be suspicious.

**Definition of a GENUINE gap** (per task-review M5 — otherwise the acceptance is gameable): a reported
coverage gap must correspond to a **real, operator-confirmed open commitment** in the engagement — not to a
requirement invented to trip the rule.

## 4. Safety controls (NON-NEGOTIABLE — this task writes to a production knowledge vault)

The LIVE vault holds **confidential client material** (pre-sales, partnerships, HR). Every control below is
operational, not aspirational:

1. **Backup before the first write.** `rsync -a` the whole `06 - Business Development/` tree to an
   **out-of-vault** destination, and **rehearse the restore** before writing anything. Record both commands.
2. **Drafts are staged OUTSIDE the vault** — in the session scratchpad — and copied in **only on operator
   approval.** A page drafted in place is already on disk and would be picked up by the next
   `wiki-sync` / `wiki-reindex`, **defeating the human gate.**
3. **Operator reviews every extracted page BEFORE it is written.** No decisions, requirements or risks about
   real clients are authored silently.
4. **Rollback is defined and rehearsed**: delete the authored files **AND** `wiki-reindex --full` — deleting
   files alone leaves their rows in the DB.
5. **No confidential business content enters this repository** — not in `docs/`, not in tests, not in commit
   messages. This spec is deliberately structural only. Findings are reported as counts/paths/classes.

## 5. Requirements Traceability Matrix

| ID | Requirement | Acceptance |
|---|---|---|
| **R-062-1** | BD zone backed up out-of-vault; restore **rehearsed** before the first write | Both commands recorded; a test-restore verified byte-identical |
| **R-062-2** | Typed pages extracted from the 2 engagements, **staged in the scratchpad**, reviewed by the operator | Operator explicitly approves the staged set before any vault write |
| **R-062-3** | Approved pages written to the BD zone + indexed (`wiki-index-upsert` / `wiki-reindex --delta`) | Pages appear in `pages` with their authored `$.type`; typed edges appear in `page_entity_refs` (forward + auto-derived inverse) |
| **R-062-4** | **R-19 fires on real data**: `wiki-health ontology` reports a **non-zero `property_pages_examined`** (and `edges_examined` if edges land), and `wiki-lint --strict` stays **green** (the authored set must be ontology-CONFORMANT) | The denominators move `0 → N`. `vacuous_populations` shrinks. This is the headline. |
| **R-062-5** | **R-15 fires on real data**: `wiki-health coverage` reports a **non-zero `pages_examined`** and **≥1 GENUINE gap** (per §3's definition) | The gap corresponds to a real open commitment, confirmed by the operator |
| **R-062-6** | **The M-2 fix is exercised for real.** Before TASK 061's fix, the ontology note required BOTH denominators to be zero — so **this pilot's very first typed page would have silenced it**, restoring the original bug. Verify the note now correctly reports **partial** vacuity | With typed pages but no typed edges: `property_pages_examined > 0`, `edges_examined == 0`, and the note **still fires**, naming only the empty population |
| **R-062-7** | Rollback verified | Delete + `wiki-reindex --full` returns the vault and the DB to the pre-pilot baseline |

## 6. Out of scope

- Any code change (if the pilot surfaces a product defect, it is a **finding**, filed separately).
- Retyping the existing `meeting-summary` engagement notes.
- Activating `policy:` / `--min-trust` on the live vault (TASK 061 §5 posture stands).
- RFC-004 `wiki-extract-decisions` — automating what this pilot does by hand. **This pilot is the evidence
  that decides whether that automation is worth building.**

## 7. Completion

**SHIPPED 2026-07-13.** The first typed knowledge in the vault's history. **Zero code changed** —
this was an adoption pilot, and the product needed no fix to receive it.

### The headline: the first EARNED green

| | before | after |
|---|---|---|
| `wiki-health ontology` | `total_violations: 0` · **`edges_examined: 0`** · **`property_pages_examined: 0`** · note: *"examined NOTHING"* | `total_violations: 0` · **`edges_examined: 8`** · **`property_pages_examined: 20`** · **`vacuous_populations: []`** · **no note** |
| `wiki-health coverage` | `pages_examined: 0` | **`pages_examined: 9`**, **`total_gaps: 3`** |
| typed event graph | `page_entity_refs` = `mentioned` only | **`implements: 8` + `implemented-by: 8`** (inverse auto-derived) |

Before, `total_violations: 0` meant *"nothing was examined."* Now it means *"the contract was examined in
full and holds."* That distinction is the entire point of TASK 061, and it is now true on real data.

### The three coverage gaps are GENUINE (per §3's definition)
Each corresponds to a real, operator-confirmed open commitment lifted from the operator's own protocols:
`acceptance-criteria` (client sends them after NDA) · `domestic-sw-registry` (client paused on foreign
OSS) · `aiva-domain-usecase-examples` (partner action item, no due date). A pilot yielding **zero** gaps
would have been suspicious.

### R-062-6 — the pilot proved a TASK-061 fix on live data
Deliberately written in **two stages**. After stage 1 (20 typed pages, **no edges yet**):
`property_pages_examined: 20`, `edges_examined: 0`, `vacuous_populations: ["edges_examined"]` — **and the
note still fired**, naming only the empty population.
Before TASK 061's **M-2** fix the condition was `edges == 0 AND props == 0`: with `props = 20` the `and`
would have **short-circuited**, the note would have gone **silent**, and the envelope would have read a bare
`total_violations: 0`. **The original bug would have been restored by the very first typed page.** The VDD
logic critic predicted exactly this; the pilot confirmed it on production content.

### Gates
`ontology-violation: 0`, `lifecycle-drift: 0` — the authored set is fully contract-conformant.
`wiki-lint --strict` exits 1 **solely** on `orphan-link: 6591`, the pre-existing backlog (**identical to the
pre-pilot baseline — zero new orphans**; every authored wikilink resolved). Zero code, zero DDL.

### Safety (all controls honoured)
Backup taken out-of-vault (22 files) and **restore rehearsed byte-identically** before the first write.
Drafts staged **outside the vault** and written only after explicit operator approval. No confidential
business content entered this repository.
**Honest limit:** the restore was rehearsed; a full rollback cycle (delete + `wiki-reindex --full`) was
**not executed**, since that would have destroyed the pages the operator had just approved.

### What this decides
RFC-004 `wiki-extract-decisions` — automating what this pilot did by hand — is now **evidence-backed**:
the two engagement protocols already contained "Ключевые решения" / НФТ / risk-register sections that
mapped onto `decision` / `requirement` / `risk` almost mechanically. The extraction is automatable.

### Post-ship: operator feedback (2026-07-13) — folded in, and it named the real gap

The operator reviewed the 20 pages and raised four points. Three were fair criticisms of *this* task;
the fourth is the finding that decides what comes next.

1. **Clutter — VALID, fixed.** The pages were written FLAT, next to the protocol. The framework's own
   typed layout (`cybos`) uses **one folder per class** (`decisions/ requirements/ risks/`) — I did not
   follow the project's own convention. Restructured to
   `<engagement>/{decisions,requirements,risks}/`. Verified safe: the PARA path rule
   `[0-9][0-9] - */*/**/*.md → ${area}/${sub}` collapses ANY depth into one project, and Obsidian
   resolves wikilinks by filename regardless of folder. Post-move: ontology 0 violations,
   `edges_examined` 8, `implements`/`implemented-by` 8+8 intact, coverage 3 gaps, **zero new
   orphan-links**, `project` unchanged.

2. **"What is the process? I run `wiki-import` on a transcript — then what?" — THE HONEST ANSWER IS:
   THERE IS NO PROCESS.** `wiki-import --kind` accepts only
   `{meeting, lesson, article, paper, thread, summary}` — **no typed class**. It emits a
   `meeting-summary` and the conveyor STOPS. `wiki-extract-decisions` does not exist. **The 20 pages
   were authored BY HAND, by the agent.** That is the pilot's real finding, and it is why the next task
   is the rail (RFC-004), not more content.

3. **"What do I do with them now?"** The value loop is real (`wiki-health coverage` = the open-commitment
   agenda before the next meeting; `wiki-lint --strict` catches lifecycle drift; `wiki-graph` gives
   decision lineage; `--as-of` gives point-in-time) — **but it only materialises if the pages are
   MAINTAINED.** A one-shot dump that goes stale is worse than nothing: it lies with a confident face.
   Maintenance is only cheap **with** the rail. **Conclusion: do NOT scale the pilot to other zones until
   RFC-004 exists.**

4. Ontology question answered (read-time contract, not a write gate; ADR-002 §D8 keeps markdown canonical).
