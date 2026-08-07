# TASK 072 — R-7 `wiki-research`: close the refuted scope, ship the three fixes it uncovered, gate the survivor

## 0. Meta Information

| | |
|---|---|
| **Task ID** | 072 |
| **Slug** | r7-wiki-research-refutation-and-split |
| **Origin** | Operator request (2026-08-06): *«проработай эту задачу»* against the `### R-7. \`wiki-research\` (R-20)` entry in `docs/ROADMAP.md` — then five lines long, marked *UNBLOCKED (gated on R-6, now shipped)*, carrying no design. (The selection was `:293-297` **on that date**; the anchor is cited instead because a later commit in this very task shifted it by +2 — bead 072-03d finding 5.) |
| **Type** | Analysis → refutation + re-scope (P0-P2 are code/doc; P4-P5 conditional) |
| **Effort** | P0-P3 ≈ **4.5-5 d** (15 beads — see [PLAN.md](PLAN.md); P1b re-estimated **1.5-2.0 d** at plan-review, plus **072-04 in a second repository** and **072-10b** added by the OQ-4 ruling) · P4-P5 ≈ **2 d, CONDITIONAL** on the P3 dogfood |
| **Schema** | **zero DDL** (`user_version` stays 7). No new `pages.type`, no new `ref_type`, no new `event_type`. **No `import anthropic`** (Decision-17). |
| **Predecessor** | TASK 071 (`docs/tasks/task-071-context-export-channel.md`). Directly continues the R-23 Phase B refutation (anchor: `### ★ Phase B — RE-SCOPED` → `**Phase B is CLOSED as REFUTED.**` in `docs/ROADMAP.md`) and TASK 066's measurement doctrine. |
| **Method** | 15-agent adversarial work-up: 6 grounding readers → a kill-attempt + a steelman run in parallel → 3 rival designs from different first principles → 3 judges (invariants / epistemic honesty / cost-value) → synthesis. Every number below was **re-run read-only** by the orchestrator against the live DBs, not taken from an agent. |

---

## 1. The finding, in one paragraph

**R-7 as written is dead, and it should be closed the way R-23 Phase B was closed — as a SUCCESS, by
measurement.** Its headline deliverable ("web enrichment of concept pages") is not merely unbuilt: it
is **blocked by a shipped contract**. Its selection trigger belongs to a predicate family this repo
already CLOSED AS REFUTED. And the loop it was specced to layer on has **never been used once** in the
fourteen months since it shipped. What survives is narrower, real, and measurable — but it is a
*different* feature with a *different* population, and it must earn its funding with a one-hour manual
dogfood before anyone writes a line of code.

---

## 2. Why R-7's stated scope is dead — two independent kills

### 2.1 MECHANISM — the concept definition is write-once, so there is no legal write target

R-7 says *"Web enrichment of concept pages."* There is nowhere legal to put the enrichment:

- **A concept page already on disk classifies as a `mention`**, and the candidate's name/definition are
  **discarded**. A differing rewrite is refused outright — `CONCEPT_PAGE_EXISTS`, exit 4, zero files
  (`scripts/wiki_skills/wiki_extract_concepts/_pages.py:219`).
- **The only auto-maintained region on a concept page is a `BEGIN-AUTO:` block**, which
  `apply_auto_block` rewrites on every render. By contract an AUTO block is a **pure function of
  Class-A/DB state**, so it must be reproducible by `wiki-reindex --full` from markdown alone.
  Externally fetched web prose is not — putting research there **breaks §D8 rebuildability**.
- Every shipped precedent (`_queries/`, `_verifications/`) files a **NEW page and links**. None mutates
  the page it enriches.

⇒ Of the live concept pages, **zero** are legally enrichable in the lead. In-place enrichment is not a
gap in the roadmap; it is a thing the architecture forbids.

### 2.2 MEASUREMENT — the selection trigger is a member of an already-refuted family

R-7's trigger (archive `TASK-ref.md:1215`) is `mentions_count == 1 AND len(definition) < 200`.

Re-measured **read-only** against the LIVE personal vault
(`~/Library/Application Support/obsidian-llm-wiki/personal.db` → root
`.../iCloud~md~obsidian/Documents/ObsidianNotes`, 3359 pages / 747 entities, 2026-08-06):

| | |
|---|---|
| entities with an EMPTY/NULL definition | **0 / 747** |
| mean definition length | **164.9 chars** |
| `len(definition) < 200` alone | 611 / 747 (81.8 %) |
| **the conjunction R-7 specifies** | **310 / 747 = 41.5 %** |

The 200-char cut sits **below the corpus mean by construction**, so it measures **LENGTH** — precisely
the artifact that killed the IDF sum in `docs/ROADMAP.md` (anchor: the blockquote headed
`### The IDF-SUM FAMILY is refuted.`). A predicate that flags 41.5 % of a
corpus containing **zero** measured garbage is a constant, not a filter. The family is CLOSED by the
paragraph beginning `**Phase B is CLOSED as REFUTED.**`, and its reopening bar (**≥30 measured examples per class, INCLUDING
short-but-good definitions**) is untouched by a raw length cut.

> ### ★ 2.3 A CORPUS ERROR, CAUGHT AND CORRECTED — record it, it is the most transferable lesson here
>
> All three rival designs independently cited **"515 entities … 369/515 = 71.7 % … mean 174"** as the
> load-bearing refutation statistic. **That is a TestVault snapshot, not the live vault.** Two
> databases both register `vault_id = 'personal'`, which is how one wrong corpus propagated through
> three independent analyses undetected. The live figures are **747 / 310 / 164.9 → 41.5 %**.
>
> The *direction* of every refusal survives — 41.5 % is still constant-like and the cut still measures
> length — **but the number was wrong, and this repo has paid for a hand-typed four-number claim
> before** (TASK 066 §2; `skills/concept-extraction/evals/measure_definition_idf.py` exists because of
> it). **Standing correction: name a vault by ROOT PATH, never by `vault_id`,** and ship any census as
> a re-runnable command rather than a figure in prose.

### 2.4 The other two triggers

- **Orphan-link stub minting** — measurable and enormous (**6512 distinct orphan targets** in the live
  personal vault) but **entirely the wrong class**: ~90 % are attachment/image/media slugs, and a
  hand-classified sample of the filtered remainder was still ~80 % noise (PPT fragments, Notion
  `untitled-database-untitled` residue, bare integers, content hashes, `.wav` exports). Applied as
  specified it mints **thousands of pages named after image files**. Separating the ~tens of real
  targets needs a classifier the repo does not have and that is not cheaper than doing it by hand.
- **Manual `/wiki-research --question`** — decomposes exactly into shipped parts (§4).

### 2.5 ★ The substrate has never been used

`SELECT COUNT(*) FROM pages WHERE type='query'` and `SELECT COUNT(*) FROM page_entity_refs WHERE
ref_type='cited'` both return **0** on **every** live index DB (personal 3359 pages · elma-kb 136 ·
obsidian-llm-wiki docs 577), and `_queries/` does not exist on disk in the live vault at all. R-6
shipped 2026-05-29 and has filed **zero organic pages in fourteen months**. R-7's own architectural
premise — *"layers on the `wiki-query` retrieval/synthesis loop"* — layers on an **unexercised loop**,
and would inherit its two live holes (§5.1) into something that can reach the open web.

---

## 3. What SURVIVES — a different population, measured and non-empty

Not "under-developed concepts" but **pages whose own frontmatter declares them unresolved, and whose
truth condition is external to the vault by nature.** Re-run read-only 2026-08-06:

| population | count | denominator | vault |
|---|---|---|---|
| `type: hypothesis`, `status: proposed`, no inbound `cited`/`verifies` | **20** | 20 (**100 %**) | `elma-kb` |
| `verified_on` ∈ {`ответа в чате нет`, `проверки в чате не было`} | **19 + 1 = 20** | 20 (**100 %**) | `elma-kb` |
| open `risk` (10) + `decision` (11), zero external corroboration | **21** | 21 (100 %) | `personal` (live BD deal) |

The vault has **declared in Class A that it does not know**, no internal source has since answered, and
the answers are on public vendor documentation. This is the one case `wiki-query` alone **cannot**
serve: retrieval over the vault returns `NO_CONTEXT` by construction, because the source chat contains
the question and explicitly no answer.

> **★ THE DISCRIMINATION CONTROL — the exact control whose absence killed R-23 Phase B — PASSES.**
> Same rule KIND, same corpus, different class:
> **SIGNAL** `hypothesis` matching the sentinel = **20 / 20 (100 %)** ·
> **CONTROL** `fact` pages with an absent/empty `source:` = **0 / 54 (0 %)**.
> A rule that flags 100 % of one class and 0 % of another over the same corpus is measuring the
> **corpus**, not the schema. Signal alone would be a vacuous RED — the refuted `<200` cut wearing the
> other colour. **Both halves are the merge gate.**

> **★ A TRAP FOUND AND CLIMBED OUT OF — recorded so nobody re-digs it.** The obvious rule
> `{class: hypothesis, requires_field: source}` measures **20/20** and looks superb. It is a
> **TEMPLATE ARTIFACT**: `templates/page-types/hypothesis.md` has no `source:` key at all, while
> `fact.md` declares one on line 6. It would measure *"the template lacks the field"* — structurally
> identical to the IDF sum measuring length. **Discarded.** Prefer a **structural** selector (authored
> type + status + a frontmatter value in a forbidden set + absence of a corroborating ref) to any
> scalar threshold: a structural selector cannot repeat the IDF failure by construction.

---

## 4. The composition already exists — every link verified

| step | primitive | status |
|---|---|---|
| SEARCH | external `html` skill `--search QUERY [OUT] --max-results N`, vendor-neutral provider fallback, per-result fetch through its **own SSRF-guarded ladder**, `query:` + `source:` frontmatter per result | **SHIPPED, unwired** (`~/.claude/skills/html/scripts/html2md/cli.py:93-100`) |
| INGEST | `wiki-import prepare --source <local .md>` — the `local-md` branch ingests a search-result note verbatim, lifting title/author/date | **SHIPPED** |
| TRUST | the note's `URL:`/`sources:` scalar makes `trust_tier` derive `external` for free — no new authored field | **SHIPPED** |
| SYNTHESIS | `wiki-query prepare/apply`, grounding enforced in Python (`CITATION_NOT_RETRIEVED`) | **SHIPPED** |

**So R-7 is a composition, not a mechanism** — with one caveat that is the whole reason it needs a
written contract rather than a wiki page:

> ★ **THE `--source-url` STEP IS LOAD-BEARING AND EASY TO MISS.** The `local-md` branch lifts
> title/author/date but **NOT `source:`**, and `apply` defaults `source_url` from the model's note
> `URL` key. Omit `--source-url` and the imported page carries **no http(s) provenance scalar**,
> `trust_tier` derives `internal` instead of `external`, and **`--min-trust internal` silently fails to
> floor a web-sourced page.** Nobody gets that right by hand twice.

---

## 5. The three fixes this analysis uncovered — all independent of R-7, all shipping regardless

### 5.1 ★ P1a — a VACUOUS GREEN inside `wiki-query`'s own anti-hallucination gate

**Verified in code** (`scripts/wiki_skills/wiki_query.py:678-694`). The citations shape gate bounds
**above only** — `len(citations) > _MAX_CITATIONS` — and never below. Therefore `[]`:

- satisfies `isinstance(citations, list)` ✓
- satisfies `all(isinstance(c, str) …)` **vacuously** ✓
- satisfies the `"/" in c` shape check **vacuously** ✓
- makes `any(c not in retrieved_keys for c in citations)` **False**

⇒ **`CITATION_NOT_RETRIEVED` — the anti-hallucination mechanism itself — passes VACUOUSLY**,
`_render_query_page`'s `if citations:` guard skips `## Sources`, and a `cites: []` page is filed and
self-indexed at **exit 0**. Combined with `--min-hits 0` (accepted on `prepare`; `len(hits) < 0` is
never true) that is a **complete exit-0 path to a filed, indexed, zero-grounding answer page.**

**Fix**: one condition beside the existing shape gate → `{"error": "NO_CITATIONS", "field":
"citations", "reason": "at least one citation is required"}`, exit 4, zero files. **No env bypass, no
`--allow-uncited` escape hatch** — the `FIELD_QUOTE_NOT_IN_BODY` doctrine, where the *absence* of an
escape is what makes it a mechanism. The same condition neuters the `--min-hits 0` vector: with
`retrieved_count: 0` the key set is empty, so a non-empty list fails `CITATION_NOT_RETRIEVED` and an
empty one now fails `NO_CITATIONS`.

> ### ★ THE HOLE IS EXECUTED, NOT ARGUED
> Two probes run against unmodified `main` during planning — pasted because this repo does not accept
> an assertion that a test *would* fail:
> **Probe A** — seed 1 source, `prepare "Hermes routing"` → `retrieved_count: 1`; `apply` with
> `citations = []` → **exit 0**, envelope
> `{"query_slug":"hermes-routing","cites":[],"page_indexed":true,"action":"filed"}`,
> `_queries/hermes-routing.md` written with `cites: []` and **no `## Sources`**, `pages` row
> `type='query'` created, `ref_type='cited'` rows = **0**.
> **Probe B** — `prepare "<no-match>" --min-hits 0` → exit 0, `retrieved_count: 0`; `apply` with `[]`
> → **exit 0**, page filed **and indexed**.
> The complete exit-0 path to a filed, indexed, zero-grounding answer page is **real**.

*Ship unconditionally.* The path is reachable today but harmless **only while nothing can fetch the
web** — and that is exactly the assumption R-7 would remove.

### 5.2 ★ P1b — two unguarded SSRF call sites, made urgent by any web composition

`scripts/wiki_skills/wiki_import_article/_fetch.py:490` (`_download_pdf`) and `:898`
(`_download_raw_html`) call `urllib.request.urlopen` with **no private-IP check and silent 30x
following**. Both are annotated `# noqa: S310 (operator URL)` — **the code's own comment states the
assumption a search fan-out would invalidate in one step.** A grep for `_assert_public_http` /
`is_private` / `ssrf` over that file returns **0 hits: 2 call sites, 0 guarded.**

**Fix**: route through the `html` skill's already-correct guarded ladder. **Do NOT port a guard** —
guards are IMPORTED, never re-ported (the recorded `obsidian-context` failure mode). **Acceptance: the
test must feed hostile URLs (private IP, redirect-to-private, non-http scheme) through the ACTUAL call
site.** A test fed only operator-typed URLs is the vacuous green this repo has already paid for.

### 5.3 P2 — the surviving population is INEXPRESSIBLE in the shipped health system

`wiki-health` / `wiki-lint` examine all 20 elma-kb hypothesis pages and pronounce them **healthy** —
because `proposed` is a legal status and `verified_on` is *present*, it just carries a value **meaning
unverified**. The shipped `CoverageRule` vocabulary expresses *field absent/empty* and *no typed edge*,
but not **"present and a non-answer."** Not a vacuous green — the denominator is honest — but a **blind
spot the rule vocabulary cannot express.**

**Fix**: optional `forbid_values: [str]` on `CoverageRule`. Gap becomes *field absent/empty* (existing)
**OR** *value ∈ forbid_values* (new). Absent key ⇒ byte-identical behaviour. **Ship the MECHANISM only
— the sentinel strings are one importer's Russian authoring convention and belong in the operator's
live `<vault>/.wiki/layout.yaml` override, never in a built-in layout.**

> Verified constraint that forces a FIELD rather than an EDGE: `valid_edges = set(_INVERSE_REF_TYPE)`,
> and `_INVERSE_REF_TYPE` contains neither `verifies` nor `cited` — a `requires_edge: verifies` rule is
> **rejected at load, exit 6**.

### 5.4 ★ Bonus defect found en route — `cybos.yaml` half-support, live on `main`

`scripts/wiki_index/layouts/cybos.yaml` declares **`summary` / `article-summary` / `meeting-summary` /
`lesson-summary`** in `type_mapping`, but its `paths:` list is **18 class dirs + `_queries` +
`_verifications`** — **zero globs that can see an imported source note** (verified programmatically,
not by eye). That is the **TASK-063 conjunction trap** (*the layout must map the class AND its read
globs must SEE the write dir*), shipped and live. An import into a cybos vault is **written, exit 0,
then pruned by the next reindex.** `elma-kb` — the dogfood target — is a cybos vault. This blocks P5
step (d) and must be decided **before** the dogfood, not discovered during it (**OQ-4**).

---

## 6. Recommended shape — a SPLIT, not one of the three designs

Three judges crowned three different winners (invariants → the rail, 9; epistemic honesty → the health
increment, 9; cost/value → the workflow, 8.5). That is not indecision: each lens measured a real and
*different* property, and the items they independently praised are **separable**.

| # | Item | Conditional? | Effort |
|---|---|---|---|
| **P0** | Re-scope R-7 + correct the **five live promise sites** + three false architecture claims + H-5 re-pin | no | 0.5 d |
| **P1a** | `NO_CITATIONS` floor in `wiki-query apply` (§5.1) | no | 0.5-1.0 d |
| **P1b** | SSRF-guard the two `urlopen` sites (§5.2) — **blocking prerequisite to any web work** | no | 1.5-2.0 d |
| **P2** | `forbid_values` on `CoverageRule` (§5.3) | no | 1.5 d |
| **P3** | ★ **Operator hand-runs the chain twice** on two real elma-kb hypotheses | no | **1 h operator time** |
| **P4** | The composition as a **workflow** (3 markdown files, zero new Python) | **YES — on P3** | 1.5 d |
| **P5** | Live non-vacuity proof: `type='query'` and `ref_type='cited'` move **0 → ≥1** | **YES — on P3** | 0.5 d |

> ### ★ THE PRE-REGISTERED FALSIFICATION CRITERION — stated in advance, non-renegotiable
> If the **P3** dogfood cannot produce one result the operator wants to keep — provider unreachable
> without a token, results unusable, or the artifact simply unwanted — then **R-7 is CLOSED entirely**,
> P4/P5 are never funded, and the correct output of this task is the closure plus the three fixes.
> Naming that outcome **now** is what stops it being renegotiated after two weeks of sunk cost.
> One hour of operator time can cancel ~2 weeks of engineering; that is the cheapest gate available.

---

## 7. Scope fence — what this task will NOT do (with the numbers)

1. **NOT a 20th `wiki-*` CLI.** Baseline: TASK 063 cost **19 beads / 1 916 lines of rail / 2 546 lines
   of task docs / 4 blocking reviews** — for a rail with **fewer** moving parts. Motivating population
   here: 41 pages across 2 vaults, one operator.
2. **NOT a new page class or `_research/` subdir.** It would flow through `layout.py` constants →
   `HOST_ONLY_SUBDIRS` → `PAGE_SUBDIRS` → `SCAFFOLD_DIRS` → `_PATH_TYPE_FALLBACK` → the `paths:` globs
   **AND** `type_mapping` of four layout YAMLs. **DF-049-1 is the recorded proof this exact population
   was already missed once.** It additionally turns **three** hardcoded test rosters RED and silently
   ships wrong docs in **three more**.
3. **NOT `type: research` as an identifier** — already an occupied coarse bucket (~15 typed classes
   funnel into it on dev-project/cybos; **202 live rows** carry it). `--types research` would over-match.
4. **ZERO DDL.** In particular the archive's `wiki-append-log event=research` is **REFUSED**:
   `event_type` is a closed 12-value CHECK, SQLite cannot ALTER-relax a CHECK on a populated table, and
   a bump moves **eight** test files hardcoding `== 7`. Reuse `event_type='query'` + `details_json`.
5. **NOT the concept-enrichment triggers** (§2.2) and **not any scalar definition-quality gate.**
6. **NOT orphan-link stub minting** (§2.4).
7. **NOT in-place enrichment of a concept page** (§2.1).
8. **NOT a `classification:`-keyed egress gate**, and **not** the archive's privacy decision #5
   (`private: true` / `tags:[confidential]` / `wiki.research.private_concepts`). Measured: **0 pages
   carry `classification:` and 0 carry `private:` across every live DB** — the gate would fire on
   nothing. *Separately:* `docs/architectures/security.md:18` currently claims that schema is
   *«готова»*; that claim is **FALSE** against `config/wiki-config.schema.yaml` and must be
   **CORRECTED, not extended.**
9. **NOT a re-opening of ADR-009's closed YAGNI list** (users/roles, crypto, RLS, field-level
   redaction, MCP policy server).
10. **NOT `wiki-discover`** (never adopted; its predicate is the refuted one) and **NOT the name
    `wiki-enrich`** (burned by TASK 047's clean delete).
11. ~~**NOT an automatic `status:` transition.**~~ ★ **RELAXED by OQ-3 (2026-08-06)** — the
    composition **may** write frontmatter, including `status:`, subject to the four guardrails in
    §8.2. It remains fenced in one respect: a `status:` value **outside the layout's declared R-19
    ontology enum** is refused, so the machine can only move a page to a state the operator's own
    ontology already admits.
12. **NOT a dispatch marker.** "Off by default" means **mechanically** that no code path in `scripts/`
    can initiate a web search — a **grep-assertable property**, not a config default set to `false`.
13. **NOT coupled to R-8.** Its input population (`cited` refs) is measured **0** everywhere, so any
    coupling would be untested by construction.

> **★ D-9 — a standing rule wherever this is documented: a web-origin page may NEVER mint a `verifies`
> ref.** Such a page derives `trust_tier = external` for free; if it minted `verifies` onto a vault
> page, that page would satisfy `--min-trust verified`'s `EXISTS(… ref_type='verifies')` clause —
> **laundering open-web evidence into the highest trust tier.** Use `related` (self-inverse, already in
> the CHECK enum and in `_INVERSE_REF_TYPE`, needs no reindex change) and accept that it is
> semantically weaker than the relation deserves. Stated, not hidden.

---

## 8. Open questions

### 8.1 DECIDED by the operator (2026-08-06)

| ID | Decision | Consequence |
|---|---|---|
| **OQ-1** | ★ **RE-SCOPE R-7 IN PLACE.** Keep the number; rewrite the body to *external corroboration of open typed questions*; record the refuted original scope **and its numbers** as a **non-reopenable sub-section**. | P0 rewrites the `### R-7. \`wiki-research\` (R-20)` entry in place rather than deleting it. The **five** promise sites keep pointing at a **live** entry — the fifth, `docs/architectures/verification-map.md:105`, was found by the plan-review gate and calls **both** R-7 and R-8 deferred (R-8 shipped 2026-05-29). **Risk this decision accepts:** keeping the number risks the old *"web enrichment of concept pages"* framing leaking back — mitigated by writing §2.1/§2.2 verbatim into the entry as a non-reopenable sub-section with the reopening bar stated. |
| **OQ-2** | ★ **WORKFLOW NOW, RAIL LATER ON A NAMED TRIGGER.** Ship the composition as 3 markdown files, zero new Python. Build the rail **only if** the workflow is used ≥N times **AND** an actual egress mistake is observed in the recorded `query:` history. | P4 is the workflow shape. The rail's stronger mechanism (Python refuses before the subprocess; fetched bytes persisted so a quote is re-verifiable) is **deferred, not discarded** — and the trigger is written into the ROADMAP entry so it is a decision, not an omission. **Stated limit:** the workflow's egress control is a durable greppable `query:` receipt, **not a gate** — under Decision-17 Python cannot observe the outbound string. Do not let a reviewer read it as stronger than it is. |

### 8.2 ALSO DECIDED by the operator (2026-08-06) — nothing remains open

| ID | Decision | Consequence |
|---|---|---|
| **OQ-3** | ★ **Frontmatter mutation is ALLOWED.** The composition may write the target page's frontmatter directly, not merely print a suggested edit. | **Relaxes scope-fence item 11.** Four non-optional guardrails ([PLAN.md](PLAN.md) §7): frontmatter only / body byte-untouched · **re-index in the SAME step** (`upsert_one`) or `wiki-lint` reports `hash-mismatch` — and there is **no PW-Q net**, since `check_auto_generated_unchanged` iterates `config.auto_indexes`, `[]` on karpathy/obsidian-personal/cybos · a `--dry-run` printing the exact frontmatter diff · a `status:` value must be in the layout's declared **R-19 ontology enum**, refusing otherwise. That last one deliberately turns an advisory declaration into a **write gate on this one surface**. |
| **OQ-4** | ★ **BOTH** — repo fix (its own issue) **and** the operator override. | The `cybos.yaml` half-support (§5.4) becomes **bead 072-10b**, independent of everything else: the missing read glob + a **two-conjunct regression test over every class in `type_mapping`**, verified with `glob_covers`/`resolve_typed_write_dir` and never by eye. ⚠️ The vault override's `paths` **REPLACES** the built-in list entirely, so it must carry the full list. Kept in a separate commit from the `forbid_values` edits — same file, unrelated defect. |
| **OQ-5** | **Capability-probe once per run** (`--help \| grep -q -- <verb>`), stop legibly. A version-pinning contract is accepted as later work "once precedents accumulate". | ★ **This applies to P1b, not only P4** — Q-072-1's ruling adds a **new** verb, so every not-yet-updated install breaks. The probe must **fail CLOSED** (refuse; never fall back to `urlopen`) and emit a `DEPENDENCY_MISSING`-shaped envelope naming the remediations, never a generic `FETCH_FAILED` (exit 10). |
| **Q-072-1** | ★ **B** — add a raw-bytes verb to the operator's own `Universal-skills/skills/html`. | The html skill **deliberately refuses PDF bytes** (`acquire.py:688`, `%PDF-` magic) and the pdf skill makes **zero** network calls — so the guarded ladder exists with no door for the file type we need. B opens that door at the guard's owner. **A2** rejected (private API · relative imports break the `spec_from_file_location` precedent · `httpx` absent from `requirements.txt`); **C** rejected on record (`urlopen` re-resolves DNS unpinned and still follows redirects — *porting trust, not importing a guard*); **D** rejected (removes 3 live dispatch branches). ⚠️ **Cross-repo**: outside this repo's pytest/mypy/H-5 gates, and its lead time gates 072-07. |
| **Q-072-2** | **(a)** — a second `_SKILL_BIN_SPEC` key (`html_launcher` → `scripts/html`). | `scripts/html2md.py` is a 27-line shim with **no verb routing**; the verbs live on the extensionless launcher. The new `WIKI_*` var must land in `config/skills.env.example` in the **same commit** or `test_env_example_documents_every_var` goes RED, plus a `deployment.md` line. Bonus: the launcher **re-execs into the skill's own venv**, where `httpx` already lives — the dependency problem that sank A2 does not exist on this path. |
| **N** | **10** uses, **AND** a recorded egress mistake — both conjuncts. | Written into the ROADMAP entry by bead 072-00. A trigger without a number is an intention. |

---

## 9. Failure matrix

| Failure | Detection | Consequence if missed |
|---|---|---|
| Editing `skills/wiki-query-synthesis/SKILL.md:159` without re-pinning | `tests/test_h5_skill_integrity.py` goes RED | Suite red; **must** re-pin via `scripts/pin_skill_integrity.py --write` in the same commit — never hand-edit a hash |
| `NO_CITATIONS` added without executing the mutation | — | An assertion that a test *would* go red is not a test (`tests/.AGENTS.md`) |
| SSRF test fed only benign URLs | — | **Vacuous green** — the exact disease this task documents |
| `forbid_values` shipped with built-in sentinels | Review | Bakes one operator's Russian convention into a shipped layout |
| P4 shipped without the inline H-6 fence | Judge-1 fatal flaw | The SELECT step reads **raw fetched web bodies** before the pinned wiki-import contract loads |
| Doc census skipped | **Nothing** — entirely ungated | Commit `bc0875a` had to repair both manual appendices, stuck at 17 rows with two shipped CLIs missing |
| Corpus attribution left as `vault_id` | Review | Two DBs both register `vault_id='personal'` — §2.3 |

---

## 10. Completion

- **P0-P2** merged, `pytest tests/` green, `mypy --strict scripts/` clean, H-5 re-pinned.
- **P1a/P1b** each carry a test whose **RED was executed**, not asserted.
- **P2** merge gate: **both** halves of the discrimination control pasted into this doc
  (signal 20/20 · control 0/54).
- **P3** run by the operator, outcome recorded — **including a FAIL, which closes R-7 entirely.**
- **P4-P5** only if P3 passed; P5 records `type='query'` and `ref_type='cited'` moving **0 → ≥1** on
  the live vault, and `wiki-reindex --full` reproducing both rows (§D8).

**Full census of surfaces** (~40 entries incl. the "NOT touched, with reasons" half) is carried in the
workflow transcript and folds into `docs/PLAN.md` at the Planning phase.
