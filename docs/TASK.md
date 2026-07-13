# TASK 063 — `wiki-extract-decisions` (RFC-004): the typed-knowledge extraction rail

## 0. Meta Information
- **Task ID**: 063
- **Slug**: wiki-extract-decisions
- **Origin**: TASK 062 operator feedback. The pilot authored 20 typed pages **by hand** and proved the
  extraction is mechanical — but also proved **there is no process**: `wiki-import --kind` accepts only
  `{meeting, lesson, article, paper, thread, summary}` (no typed class), emits a `meeting-summary`, and the
  conveyor **stops**. `wiki-extract-decisions` does not exist.
- **Type**: Feature (the missing rail)
- **Effort**: M
- **Schema**: **zero DDL** (`user_version` 7). Typed classes + edges already exist (ADR-003/004); this task
  only *produces* them. **No `import anthropic`** (Decision-17).
- **Revision**: **v6**, after four BLOCKING task-reviews + **operator requirements** (2026-07-13):
  the rail must be **invocable from config** (like its sibling `extract_concepts`), and the **folder names
  must be configurable AND visible in the `wiki-config` editor**. The second requirement exposed a real
  architectural defect in v5 — see R-063-3′. v1 shipped **two factually false claims**, both of the
  project's signature failure mode — *asserting coverage of a surface without enumerating it*:
  (a) *"anything `apply` accepts, `wiki-lint --strict` accepts"* — but `--strict` gates on **13 categories**
  (`exit_code = 1 if (strict and issues)`), not just ontology; (b) *"Karpathy/cybos/obsidian-personal each
  file correctly"* — but **karpathy and obsidian-personal map ZERO typed classes**; only `cybos` and
  `dev-project` do. Both were caught by a grep, not by reasoning.
  **v3** folds in four more, and the sharpest was created by v2's own fix: **R-063-8's hardcoded
  `status: superseded` VIOLATES G1** — `supersedes` is legal `requirement → requirement`, but the
  `requirement` status enum is `[draft, approved, implemented, dropped]`, with **no `superseded`**.
  *The fix for G3 authored the exact contradiction G1 exists to prevent.* Also: **prose creates refs**
  (cybos ships an `id-ref` regex over `DEC-\d+|REQ-\d+|ADR-\d+…`, so "отменяет DEC-004" in body text is an
  `orphan-link` surface — G2 said "wikilinks", the wrong surface again); and **the v2 acceptance protocol
  itself could report a FALSE GREEN** (`lint.py:298`: *"`--delta` can leave [inverse edges] transiently
  stale … `--strict` drift gating assumes a recent `--full`"*) — this project's signature disease,
  reproduced inside this task's own acceptance criteria.
  **v4** folds in two more, both structural. (a) v3 made R-063-8's **value** config-derived but left its
  **precondition** hardcoded as `{proposed, accepted}` — a **decision-specific** set: `workflow`'s enum is
  `[draft, active, deprecated, superseded]`, so v3 would **never patch a workflow** (drift fires), and a
  `decision` with `status: rejected` would be **skipped** (drift fires). *v2's bug, one field to the left.*
  (b) **The delta property is satisfiable by SILENCE.** `find_pages_missing_in_index` walks via
  `discover_pages` (`_health_scan.py:186`), so a file matching **no glob is never discovered** ⇒ **never
  reported** ⇒ a glob-invisible page raises **zero** lint issues and `lint_before == lint_after` **passes**.
  A rail that writes files nobody can see satisfies the property perfectly — **and so does a rail that
  writes nothing at all.** The structural twin of round 1's lesson: *an acceptance criterion must not be
  satisfiable by doing nothing.*

## 1. Problem

TASK 062 proved the typed layer works on real content — and that **maintaining it is impossible today.**

```
wiki-import <transcript>  →  meeting-summary  →  ⛔ END OF CONVEYOR
```

The 20 typed pages behind `wiki-health`'s **first earned green** were written **by an agent, by hand**.

**Why this matters more than more content:** a one-shot typed dump that nobody maintains is **worse than
nothing** — it goes stale and then *lies with a confident face*. The value loop (`wiki-health coverage` as
the open-commitment agenda before the next meeting; `wiki-lint --strict` catching lifecycle drift;
`wiki-graph` for decision lineage) only materialises if re-extraction is **cheap**. **Do not scale the pilot
to other zones until this rail exists.**

## 2. The property (narrowed to something that is actually TRUE)

Before staging the pilot's pages, the agent hand-wrote a Python check — *are the `status` values in the
declared enums? do the `implements` edges satisfy the declared domain/range?* — and `wiki-lint --strict` was
consequently clean on the first try. **That check must live in the code, not in the agent**, and it can: the
ontology is already a machine-readable contract (`OntologyConfig`/`OntologyEdge`/`OntologyProperty`,
`models.py:461-486`).

**v1's headline was overclaimed. `apply` can NOT guarantee a `--strict`-clean vault** — `--strict` fails on
*any* of 13 issue categories, including pre-existing vault state it never touched, and including
`orphan-link`, which the ontology check **cannot** catch (it *skips* unresolved targets by design).

**The true, falsifiable property — a DELTA, not an absolute:**

> **If the vault is `wiki-lint --strict`-clean *before* the run, it is still `--strict`-clean *after*
> `apply` + `wiki-reindex --full`.**
> Test as `lint_issues_before == lint_issues_after`, **never** as `lint_after == []`.

It decomposes into **SIX** guarantees, each its own requirement, because each is a *different surface*:

| # | Guarantee | Without it, the failing category is |
|---|---|---|
| **G1** | ontology conformance — class ∈ roster, **domain AND range**, `status` ∈ enum | `ontology-violation` |
| **G2** | `apply` runs **the resolved layout's OWN `ref_extraction` rules** over the fully-rendered candidate page (frontmatter + body) and requires **every extracted target** to resolve — to an existing page/entity/**alias**, or to a page in the same batch. ⚠️ **NOT "wikilinks"** — cybos ships an `id-ref` regex, so **plain prose** ("отменяет DEC-004") creates refs. The write side must be validated against the layout's **read grammar**, never against an assumption about it — *the same invariant as G4, wearing the ref-extraction costume* | `orphan-link` (**ontology CANNOT catch this — it skips unresolved targets by design**; and `find_orphan_links` scans **all** of `page_entity_refs`, with no `ref_type` filter) |
| **G3** | a `supersedes` edge **reconciles the target's `status`** (R-063-8) | `lifecycle-drift` (**guaranteed**: cybos declares `{decision, superseded-by, expect_status: superseded}`) |
| **G4** | the resolved layout can actually **index** the classes, and the write path is **visible to the read globs** (R-063-3) | `missing-in-db` (unmapped `$.type` is a hard reindex SKIP) |
| **G5** | **every page `apply` touches — including a page it PATCHES (R-063-8) — is in the manifest it indexes** | `hash-mismatch` (a mutated file whose DB row still carries the old hash) |
| **G6** | ★ **POSITIVE: everything `apply` wrote is VISIBLE.** After `apply` + `wiki-reindex --full`: (a) every written page has a `pages` row with the expected `slug`/`project`/`$.type` (asserted via the repo, **not** via lint); (b) every authored forward edge is in `page_entity_refs` **and its inverse is derived**; (c) every **patched** page is re-indexed with its new hash (G5's *positive* half); (d) counts reconcile — `pages_written == pages_indexed`, `edges_authored == edges_indexed` | **NONE — and that is the point.** Lint is **structurally incapable** of seeing a glob-invisible page (`find_pages_missing_in_index` walks via `discover_pages`, so an unglobbed file is never even discovered). This is the strongest argument for R-063-3's **load gate**: it is the only *preventive* defence |

**★ ORDERING IS NORMATIVE — the 7th surface.** The existing-page **collision re-check runs BEFORE G1/G2**,
and **G1/G2 validate the POST-DROP batch**. If any *surviving* candidate carries an edge or link targeting a
**dropped** candidate, the drop **escalates to a contract violation ⇒ refuse the batch, zero writes.**
*Why:* validate `{D, R}` with `D.implements: [[r-slug]]` (range OK against in-batch R), then drop R on a
slug collision, then write D anyway — and D's edge now resolves to the **pre-existing** page of that slug
(class `summary` ∉ `implements.to`) ⇒ **a new `ontology-violation`**. Both halves of the property are blind
to it: the counts still reconcile (the dropped candidate was never written) and G1/G2 already passed —
**against a batch that no longer exists.**
> **A validation computed against a hypothetical batch is not a validation of what got written.**
> A benign drop is benign only when nothing in the batch depends on it.

**★ THE PROPERTY IS A CONJUNCTION: `(delta-clean) AND (G6)`.** Neither alone suffices —
**the delta property catches HARM; G6 catches SILENCE.** A rail that writes glob-invisible files, or that
writes nothing at all, passes the delta property perfectly.

**Precondition does real work:** the property's *"clean before"* premise is what closes the
`{decision, invalidated-by, forbid_status}` drift rule — a pre-existing dangling `invalidates` edge is
impossible in a clean vault, so a new page can never inherit one. Stated so a reader does not think the
rule is unhandled.

**⚠️ ACCEPTANCE PROTOCOL — verify under `wiki-reindex --full`, NOT `--delta`.** Drift reads the
**auto-derived inverse** edges, and `--delta` can leave them transiently stale on one side of a
bidirectionally-authored edge (`lint.py:298`) — so a `--delta`-based test can report `lint_before ==
lint_after` while the vault is **actually drifted**, surfacing only at the next `--full`. That is a check
that examined nothing reporting green, *inside this task's own acceptance criteria*.

## 3. Design — clone the proven rail

```
wiki-import <transcript>          →  meeting-summary                              (unchanged)
        ▼
wiki-extract-decisions prepare    →  source body + source-hash handshake
                                     + KNOWN typed pages (don't duplicate)
                                     + ★ THE ONTOLOGY CONTRACT (roster, edge domain/range, status enums)
                                     + existing_page_slugs (collision guard)
                                     + ⛔ PREFLIGHT: refuse if the layout can't index the classes (G4)
        ▼
   [orchestrator REASON]          →  candidates JSON  (skills/decision-extraction/SKILL.md)
        ▼
wiki-extract-decisions apply      →  ★ VALIDATE (G1+G2+G3) — refuse the batch, exit 4, ZERO writes
                                     write to the layout's typed dirs (config-driven, glob-verified)
                                     reconcile supersede targets (R-063-8)
                                     never clobber hand-edited pages (R-063-9)
        ▼
wiki-reindex --full               →  inverse edges auto-derive (ADR-004). ⚠️ --full, NOT --delta:
                                     drift reads the INVERSES, and --delta can leave them transiently
                                     stale (lint.py:298) -> a --delta test can report a FALSE GREEN.
```

**v1 class roster: `{decision, requirement, risk}`** — exactly what the pilot proved. cybos maps 20+ classes;
everything outside the roster is **refused by `apply`**. This also settles Q-063-3 for free: `person` ∉ roster
⇒ dropped, honouring the standing rule that participants live in `participants:` frontmatter, not pages.

## 4. Requirements Traceability Matrix

| ID | Requirement | Acceptance |
|---|---|---|
| **R-063-1** | `prepare` emits the **ontology contract** (roster, edge domain/range, status enums), known typed pages, `existing_page_slugs`, and a `--source-hash` handshake | ⚠️ **`dev-project` maps the typed classes but ships NO `ontology:` block and NO `drift_rules`** — there, G1 degrades to a roster-only check and G3 is moot. The delta property still HOLDS (both sides vacuous), so this is not a lie — but a green `apply` there means **"validated almost nothing"**, and per the TASK-061 lesson **that must be ANNOUNCED, not inferred.**<br>`apply`'s envelope therefore carries the house-standard **denominators**: `validation: {roster_size, edges_checked, properties_checked, links_checked}` + a **`vacuous_validation: true`** marker when the layout declares no `ontology:`. *A validator that examined nothing must not look green.* |
| **R-063-2** | **G1 — `apply` validates every candidate against the ontology BEFORE any write**: class ∈ roster, edge **domain**, edge **RANGE** (⚠️ requires resolving an out-of-batch target's class **from the DB** — a domain-only validator would pass v1's example vacuously), `status` ∈ enum | A bad-**domain** *and* a bad-**RANGE** *and* a bad-**status** candidate each rejected. **The envelope lists ALL violations at once** (`violations: [{index, class, kind, detail}]`) — one repair round, not N. **Validation failure ⇒ ZERO files written** (validate before opening the DB, the `_apply_validate` precedent) |
| **R-063-3** | **G4 — typed pages go where the layout's READ globs can see them.** New layout key `write.typed_dirs` expressing **root-anchored** (cybos: `decisions/`) **vs sibling-of-source** (obsidian-personal-style) — *not* a hardcoded "sibling", which cybos's root-anchored globs (`decisions/**/*.md`, **no catch-all**) would silently never walk | **LOAD GATE (new invariant):** every layout's `typed_dirs` output path **must match ≥1 of that layout's own `paths[]` globs** — *a write grammar the read grammar cannot see is a silently-dropped page.* **Supported set stated honestly: `cybos`, `dev-project`, and any vault whose `.wiki/layout.yaml` adds the classes** (the operator's LIVE vault). **karpathy and obsidian-personal map ZERO typed classes** ⇒ `prepare` **refuses** with an actionable envelope (the `concepts_indexable` precedent) |
| **R-063-4** | Forward edges only; **inverses auto-derive at `wiki-reindex --full`** (M-1 intact). ⚠️ **NOT `--delta`** — inverse derivation is precisely what `--delta` leaves transiently stale (`lint.py:298`), and this row's acceptance *depends* on it | `implements: N` ⇒ `implemented-by: N` after reindex; no inverse on disk |
| **R-063-5** | **Idempotent**: unchanged source ⇒ no-op (`source_state` hash); changed source ⇒ re-extract; `--force` bypasses | Second run ⇒ `action: unchanged`, zero writes. A **post-validation** failure leaves `source_state` **unset** ⇒ retry is safe (`PARTIAL_INDEX_FAILURE`, exit 5) |
| **R-063-6** | REASON contract at `skills/decision-extraction/SKILL.md`, **mapping the protocol's existing sections** ("Ключевые решения" → decision · НФТ/KPI → requirement · "Реестр рисков" → risk) rather than free-form extracting | Bound to a **named eval set** with expected outputs (`skills/decision-extraction/evals/`, per CLAUDE.md — durable fixtures live with the owning skill, **not** `samples/`).<br>⚠️ **SKILL.md MUST warn REASON that BARE IDs IN PROSE ARE REFS** on cybos (`DEC-004`, `REQ-012`, `ADR-7`, `R-15`, `task-63` all match the `id-ref` regex). Guidance: reference other pages **only** via wikilinks to slugs that exist or are in the same batch; **never cite a bare ID** — otherwise well-written prose bounces the batch on G2 repeatedly and the operator experiences the rail as flaky |
| **R-063-7** | **Anti-fabrication is a MECHANISM, not a wish** (see §5 Q-063-4): (a) `CANDIDATE_COUNT_MIN = **0**` — an empty set is **SUCCESS** (`action: no_candidates`, exit 0); (b) every candidate carries a `source_quote` **verified verbatim against the source body** (`FIELD_QUOTE_NOT_IN_BODY`, exit 4); (c) the `WIKI_EXTRACT_NO_QUOTE_CHECK` env escape is **NOT honoured** in this skill | ⚠️ The precedent has `_CANDIDATE_COUNT_MIN = 1` — cloning it makes *"this note has no decisions"* an **exit-4 failure**, so the model's cheapest path to a green run is to **invent one**. **Negative eval fixture required**: a transcript that explicitly *defers* a choice ("отложили", "вернёмся") ⇒ expected `decisions: []` |
| **R-063-8** | **G3 — supersede reconciliation. DECIDED: option (A), but DRIFT-RULE-DRIVEN, never hardcoded.**<br>⚠️ **v2's hardcoded `status: superseded` VIOLATED G1**: `supersedes` is legal `requirement → requirement`, and the `requirement` enum is `[draft, approved, implemented, dropped]` — **no `superseded`**. The fix authored the contradiction it prevents.<br>**The correct value is already in config:** patch the target's `status` to the **`expect_status` of the `drift_rule` matching `(target_class, superseded-by)`**. **If no such rule exists for that class** (requirement, adr, pattern…) ⇒ **patch NOTHING** — there is no drift to prevent, and inventing a status would violate the class's enum.<br>**AUTHORITY ENVELOPE — `apply` may modify an existing page ONLY when ALL hold:** (1) it is the declared target of a `supersedes` edge **in this batch**; (2) a `drift_rule` exists for `(target_class, superseded-by)`; **(3) THE PRECONDITION IS THE DRIFT RULE'S OWN FIRING CONDITION, read from config — never hand-enumerated.** ⚠️ v3 hardcoded `{proposed, accepted}`, which is **decision-specific**: `workflow`'s enum is `[draft, active, deprecated, superseded]`, so v3 would **never patch a workflow** and drift would fire. Correct rule: **patch ⟺ the target's `$.status` is scalar text AND `status != rule.expect_status`** (`_health_rules.py:312-317`). An absent / null / non-scalar status **never drifts** ⇒ never patched (no gratuitous Class-A edit); an already-`superseded` page is a no-op (idempotent).<br>**(3″) A PROTECTED TERMINAL STATUS REFUSES THE BATCH.** `decision.status: rejected` ⇒ **do NOT silently skip** (a skip leaves the `lifecycle-drift` finding standing and **breaks the property**) and do NOT overwrite. **Refuse:** `REQUIRES_STATUS_RECONCILIATION`, exit 4, zero writes. Superseding a *rejected* decision is a semantic contradiction the **operator** must resolve — not something the rail may paper over; (4) the edit is **a single frontmatter scalar** — body bytes, key order and comments preserved (**the comment-preserving ruamel sandwich**, TASK 058); (5) the new value is **∈ the class's ontology enum** — *a G1 self-check on apply's own write*; (6) the patch is reported as an explicit diff (`reconciled: [{slug, field, from, to}]`) **and the patched page is IN THE MANIFEST** (G5 — else its DB hash goes stale ⇒ `hash-mismatch`); (7) a **backup** is written (`.wiki/backups/`, TASK 058) — the escalation is reversible.<br>**NOT flag-gated.** An opt-in flag would make the headline invariant *conditional on a flag* — v1's disease in a new costume; and by authoring `supersedes: [[D1]]` the operator has already asserted D1 is superseded. **`--no-reconcile` is the opt-OUT, and it refuses the WHOLE BATCH** (zero pages written, `REQUIRES_STATUS_RECONCILIATION`) whenever the batch contains a `supersedes` edge — writing the pages *without* the patch would silently break G3 and turn the opt-out into a footgun. | **Enumerated, not assumed** — `supersedes.to` = `{decision, requirement, workflow, adr, pattern}`:<br>• `REQ-B supersedes REQ-A` (no drift rule for requirement) ⇒ **zero patches, zero violations** ✅<br>• `DEC-B supersedes DEC-A(accepted)` ⇒ patched to `superseded`, manifested, backed up, diff reported ✅<br>• `DEC-B supersedes WF-A(status: active)` ⇒ **WF-A patched to `superseded`** (∈ workflow enum) — v3 would have skipped it and drift would fire ✅<br>• `DEC-B supersedes DEC-A(status: rejected)` ⇒ **REFUSED, zero writes** (`REQUIRES_STATUS_RECONCILIATION`) ✅<br>• target with no `status:` ⇒ no patch (can't drift) ✅<br>**No new `lifecycle-drift` and no new `ontology-violation` under `--full`** in every case. **In-batch supersede**: if D3 supersedes sibling D2, D2 is **WRITTEN WITH** the reconciled status — a batch where a candidate is superseded by a sibling while carrying `status: accepted` is **rejected** |
| **R-063-9** | **Re-extraction reconciliation — Class-A ownership is sacred.** (a) generated pages carry `extracted_from: <source_slug>`; the write-time content **hash is stored OUT-OF-BAND in the DB** (`source_state`, legitimate Class-C state, ADR-002 §D8) — ⚠️ a hash stored *inside* the file cannot be a hash *of* the file (v2's stamp was self-referential and the guard would silently never fire);<br>**(b′) PRECEDENCE — "never clobber" governs WHOLE-PAGE REWRITES (re-extraction content), NOT the R-063-8 single-scalar patch.** ⚠️ Read as absolute, (b) would **skip** the patch on a *hand-edited generated decision* that is a supersede target — the single most likely operator action (adding rationale) — leaving `lifecycle-drift` standing and **breaking the property**: the exact failure fixed in R-063-8(3″), one requirement to the right. The patch is safe on a hand-edited page **by construction** (one frontmatter scalar, body bytes + comments preserved via the ruamel sandwich, backup, reported diff). So: hand-edited generated page as supersede target ⇒ **PATCHED** inside the authority envelope, **body edits preserved**, `TYPED_PAGE_HAND_EDITED` reported for the *content* skip. The **only** refusal remains (3″) — a protected terminal status — because that is a conflict of **intent**, not of **bytes**;<br>**(a′) HAND-AUTHORED TARGET — DECIDED.** A page with **no recorded write hash** is **operator-owned**, and that is the ONLY case that exists in production today (the 20 pilot pages are all hand-authored). Refusing them would make G3 **unreachable on the only vault that has typed pages**. So: `apply` **still patches** it — but strictly inside R-063-8's authority envelope (single scalar, drift-rule-derived value, backup, reported diff). Never a body edit, never a rewrite; (b) **NEVER clobber** a page whose current hash ≠ its recorded write hash — skip + loud `TYPED_PAGE_HAND_EDITED` (⚠️ **inverts the concepts precedent**, which atomically rewrites + warns — if the operator hand-set `status: superseded`, the next run would **revert it**, resurrecting the very drift this task exists to kill); (c) prior-run pages absent from the new candidate set are **reported as `stale: [...]`** — **never auto-deleted**; `--prune` is opt-in | A hand-edited generated page survives re-extraction untouched. A re-worded decision reports the old page as `stale`, does not delete it |
| **R-063-10** | **H-6 + governance.** (a) The input is an UNTRUSTED transcript whose text lands in YAML frontmatter (`status:`, edge lists) and page bodies. Reuse the precedent's guards: `_sanitize_*`, the YAML-delimiter-injection guard, `_is_valid_slug` as a traversal gate | A candidate with `supersedes: [[../../x]]` (traversal) or a `status` containing `\n---\n` (frontmatter break-out) is **refused**.<br>**(b) NO DECLASSIFICATION PUMP:** a generated page **inherits the SOURCE page's `classification:`** when the vault declares a `policy:` block. Inert today (policy is declared-but-OFF, TASK 061 §5) and it does not affect the lint delta (`classification-leak` fires only on `cited`/`verifies` refs, which typed pages don't carry) — but the moment R-16 is enabled, a decision extracted from a `confidential` transcript that silently inherits `default_level` turns this rail into a **declassification pump**.<br>**(c)** `apply` **never authors an `aliases:` key** — closes the `alias-collision` category by construction |
| **R-063-11** | **No `import anthropic`**; one JSON envelope + stable exit codes; caps stated (candidate max, `SOURCE_TOO_LARGE`) | grep-gated. **Overflow REFUSES — never truncates** (silent truncation would lose decisions, which is this task's own disease) |
| **R-063-12** | **Slugs are derived with the LAYOUT'S OWN `slug_strategy`** — never a naive kebab (the same "validate against the layout's grammar, never an assumption" invariant as G2/G4). ⚠️ cybos declares `slug_strategy: transliterate` and the source protocols are **Russian**, so two candidates whose titles transliterate to the same slug would have the **second silently overwrite the first on disk** — one decision lost, **one file, one DB row, ZERO lint issues** (invisible to the delta property AND to a naive G6 count). **In-batch slug uniqueness is a CONTRACT VIOLATION ⇒ refuse the batch**; assert `len(set(slugs)) == len(candidates)`. The existing-page collision re-check uses the same derivation | Two Russian-titled candidates colliding under `transliterate` ⇒ **refused, zero writes** — not "last one wins" |

### R-063-3′ — ★ THE CONFIG SPLIT (operator requirement; v5 was architecturally WRONG here)

**v5 put `write.typed_dirs` in the LAYOUT config** (`layouts/*.yaml` / `.wiki/layout.yaml`). Verified defect:
`wiki-config`'s `set`/`unset` **and its web editor** render **only** from
`SYNC_SCHEMA_PATH = config/sync-config.schema.yaml` (`_uimodel.py:24`, `_server.py:191`). It *validates* all
three config systems but *edits* only `sync.yaml`. **So `typed_dirs` in the layout would never appear in the
editor at all** — failing the operator's requirement, and silently violating TASK 058's own schema-driven
invariant.

**But a naive move to `sync.yaml` re-creates the very bug G4 prevents.** The two systems own different halves:

| System | Owns | Scope |
|---|---|---|
| `.wiki/sync.yaml` (`sync-config.schema.yaml`) | **WHERE TO WRITE** — the folder names | per-folder, **cascading** |
| `.wiki/layout.yaml` (`layout-config.schema.yaml`) | **WHAT THE WALKER SEES** — the `paths[]` globs | per-vault |

Set `dirs.decision: "решения"` in a zone while the layout's globs don't cover it ⇒ **a glob-invisible page**
⇒ exactly the silent loss G4 exists to prevent — *and lint is structurally incapable of reporting it.*

**Resolution — the load gate becomes a CROSS-SYSTEM check, and `wiki-config validate` already validates all
three systems, so it has a legitimate home:**

> **New `extract_decisions:` block in `sync.yaml`** (cascading, sibling of `summarize:`):
> ```yaml
> extract_decisions:
>   enabled: true                 # the config-driven invocation (Q-063-2)
>   dirs:                         # ★ configurable folder names — schema-driven ⇒ they appear in
>     decision:    decisions      #   `wiki-config` show / report / SERVE with ZERO interface code
>     requirement: requirements   #   (the TASK-058 invariant, and the reason this belongs in sync.yaml)
>     risk:        risks
> ```
> **★ CROSS-SYSTEM LOAD GATE (the G4 invariant, spanning two config systems):** every `dirs.*` value,
> resolved against the folder it applies to, **MUST match ≥1 of the resolved layout's `paths[]` globs.**
> Enforced in **BOTH** `wiki-config validate` (a new finding code) **and** the rail's own `prepare`
> preflight — refuse with an actionable message, never write a page the walker cannot see.
>
> ⚠️ **Layout-dependent, so it must be CHECKED, never assumed:** obsidian-personal's generic
> `[0-9][0-9] - */*/**/*.md` catches **any depth** ⇒ any folder name works (the operator's live vault).
> **cybos's globs are root-anchored** (`decisions/**/*.md`, no catch-all) ⇒ **only the declared roots work**;
> a custom name there is refused, not silently dropped.

**Acceptance:** (a) the three `dirs.*` keys **appear in `wiki-config serve`/`report`/`show` with zero
interface-code changes** (pin it — this IS the TASK-058 evolution invariant); (b) a `dirs.*` value not
covered by the layout's globs is **refused** by both `wiki-config validate` and `prepare`; (c) `enabled:
false` (or absent) ⇒ the rail is never auto-dispatched; (d) per-zone cascade works — two engagements may use
different folder names.

### File surface (for the Planner)

`scripts/wiki_skills/wiki_extract_decisions/{__init__,_validation,_pages,_db,_errors}.py` (new package,
mirroring `wiki_extract_concepts`) · **`config/sync-config.schema.yaml`** (the new `extract_decisions:`
block — `enabled` + `dirs`, with `x-wiki-scope: cascading`; this is what makes it appear in the editor) ·
**`scripts/wiki_index/sync_config.py`** (parse it) · **`scripts/wiki_skills/wiki_config/_lint.py`** (the
cross-system glob-coverage finding) · `scripts/wiki_index/layout_config.py` (the glob-coverage helper, shared
by validate and prepare) · `scripts/wiki_index/layouts/{cybos,dev-project}.yaml`
· `skills/decision-extraction/{SKILL.md,evals/}` · `commands/wiki-extract-decisions.md` ·
`bin/wiki-extract-decisions` · `tests/`.
**Do NOT touch** `karpathy.yaml` (byte-identity-anchored) or `obsidian-personal.yaml` — adding typed classes
to them is a separate decision (§7).

## 5. Open questions — DECIDED (not left to the implementer)

- **Q-063-1 — separate CLI vs a `--kind` on `wiki-extract-concepts`?** ***Settled: separate CLI.*** Different
  populations (entities vs typed pages with edges), different validation (concepts have no ontology
  contract), different write grammar (per-class dirs vs `_concepts/`).
- **Q-063-2 — auto-chain from `wiki-import` / `wiki-sync`?** ***REVERSED by operator requirement (v6):
  YES, config-driven — and the precedent was already there.*** `.wiki/sync.yaml`'s `summarize:` block
  already carries **`extract_concepts`**, which toggles exactly this kind of downstream filing step. So
  **`extract_decisions`** is its natural sibling, not a new concept.
  **Mechanism (Decision-17 preserved):** `wiki-sync` / `wiki-import` do **not** call an LLM — they emit a
  **dispatch marker**, and the orchestrator runs the rail as a second step (precisely how `wiki-sync`
  already delegates to `wiki-import`). The CLI stays deterministic plumbing.
  The rail remains **independently invocable** by hand (the `wiki-extract-concepts` posture is kept).
- **Q-063-3 — `person` candidates / the TASK-052 participants guard?** ***Settled: `person` ∉ the v1 roster
  `{decision, requirement, risk}`, so it is refused by `apply`.*** The participants guard in `wiki-import` is
  keyed on *pyramid grammar* and does not cover this rail — the roster is what protects it here.
- **Q-063-4 — how do we stop the model inventing decisions?** ***Settled: three mechanisms, not a
  wish*** (R-063-7): min-count **0**, mandatory verbatim `source_quote`, and a negative eval fixture.
  **And the contract must state that an unimplemented `requirement` is a `wiki-health coverage` gap = DATA,
  always exit 0 — NOT a defect to close** — or the model will "helpfully" invent a closing decision so
  nothing looks unfinished. `apply` reports `open_commitments: N` as an **output**, so gaps read as the
  deliverable they are.

## 6. Failure matrix

| Case | Envelope / exit |
|---|---|
| Source not indexed (FK) | `DB_WRITE_FAILED`, exit 5 |
| Source edited between `prepare` and `apply` | `SOURCE_CHANGED_DURING_EXTRACTION`, exit 2 (`--source-hash` handshake) |
| Ontology violation (any of G1) | `ONTOLOGY_VIOLATION` (a distinct error inside exit 4), **all** violations listed, zero writes |
| Layout cannot index the classes | refused in **`prepare`**, actionable envelope |
| Candidate slug collides with an existing page from another source | benign **drop + loud warning**, exit 0 (the `CONCEPTS_DROPPED` precedent). ⚠️ `prepare`'s `existing_page_slugs` is a **snapshot** — a slug can appear between `prepare` and `apply`, so `apply` **re-checks the collision set** against the repo it already opens |
| REASON returns malformed JSON | exit 4, zero writes |
| Post-validation index failure | `PARTIAL_INDEX_FAILURE`, exit 5, `source_state` **unset** ⇒ retry safe |
| Supersede target has a **protected terminal status** (`decision: rejected`) | `REQUIRES_STATUS_RECONCILIATION`, exit 4, **zero writes** — the operator resolves the contradiction, the rail never papers over it |
| `--no-reconcile` + the batch contains a `supersedes` edge | `REQUIRES_STATUS_RECONCILIATION`, exit 4, **whole batch refused** |
| **In-batch slug collision** (two candidates ⇒ one slug under the layout's `slug_strategy`) | contract violation ⇒ **refuse the batch**, exit 4. ⚠️ Silently "last-one-wins" would lose a decision with **zero lint issues** |

**Contract-violation vs benign-skip split** (settled): a *contract* violation (ontology / schema /
quote-grounding / traversal) ⇒ **refuse the whole batch, exit 4, zero writes**. A *benign* skip ⇒ **drop + loud warning, exit 0** — this covers an **EXISTING-PAGE** slug collision
(subject to the normative ordering rule in §2) and a layout that can't index one class. An **IN-BATCH** slug
collision is **NOT** benign: it is a contract violation ⇒ **refuse the batch, exit 4** (R-063-12).

## 7. Out of scope

- Auto-chaining from `wiki-import` (Q-063-2).
- A `meeting-summary` profile that emits typed pages in one pass — plausible later, but it couples the
  summariser to the ontology; prove the separate rail first.
- Scaling the pilot to other vault zones (deliberately blocked on this task — §1).
- Adding typed classes to `karpathy` (byte-identity-anchored) or `obsidian-personal` — a separate decision.

## 8. Completion

_(filled on ship)_
