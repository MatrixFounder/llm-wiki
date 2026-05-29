# TASK 008 — Epic 7 RAG layer: `wiki-verify-multi` (R-8, multi-critic verification of cited answers)

> **VDD MODE** — high-integrity decomposition. Requirements structured as
> one Epic with an RTM, detailed Use Cases, and binary Acceptance Criteria.

### 0. Meta Information

- **Task ID:** 008
- **Slug:** `wiki-verify-multi`
- **Mode:** VDD (`/vdd-start-feature` → `/vdd-plan` → `/vdd-develop-all`)
- **Roadmap source:** `docs/ROADMAP.md` → "P1 — Epic 7 RAG layer" → **R-8**
  (`wiki-verify-multi` — 4-critic ensemble for high-stakes query responses;
  off by default; pairs with the `/vdd-multi` infrastructure; layers on the
  `wiki-query` answer).
- **Predecessors:**
  - R-6 / TASK 007 (`wiki-query`) — the RAG answer this task **verifies**; the
    Decision-17 `prepare`/`apply` split, the `_retrieve` keyword-OR retrieval,
    the grounding gate, the markdown-egress sanitiser, and the **R-6.5e reindex
    read-side** (the durability precedent R-8 mirrors) all come from here.
    SHIPPED 2026-05-29 (`c6c249d`).
  - R-3 / TASK 003 v3.1 (`wiki-extract-concepts`) — the original Decision-17
    deterministic-skill + orchestrator-owned-synthesis pattern + the
    `concept-extraction` prompt-skill precedent (`wiki-verify` is its sibling).
  - `/vdd-multi` workflow + `.claude/agents/critic-{logic,security,performance}.md`
    — the adversarial multi-critic infrastructure R-8 reuses for the ensemble.
- **Current HEAD:** `81d8abf` (TASK 007 committed; schema `user_version = 4`).
- **Closes:** nothing in `docs/KNOWN_ISSUES.md` directly; delivers the
  *verification* half of the high-stakes RAG loop (independent audit of a
  synthesised answer against its cited sources).
- **Unblocks:** keeps R-7 (`wiki-research`) independent; strengthens R-X1
  readiness (adds a second `HOST_ONLY_SUBDIRS` member through the same
  role-split seam, proving the seam generalises).
- **Scope decisions (operator-confirmed 2026-05-29, via `/vdd-start-feature`
  AskUserQuestion):**
  - **Verdict surface = a new first-class `_verifications/<slug>.md` page**
    (compounding; role-split via `HOST_ONLY_SUBDIRS`). See D-008-1.
  - **Critic lenses recast for prose** = `factual-grounding`, `logic/coherence`,
    `security/injection`, `completeness/faithfulness` (NOT the ROADMAP's literal
    "performance", which does not map to a prose answer). See D-008-2.
  - **FAIL semantics = record verdict + non-zero exit**; the Class-A answer is
    **never** mutated/quarantined. See D-008-3.
  - **Scope = full Decision-17 loop** (`prepare` → orchestrator critics →
    `apply` + self-index + reindex read-side durability). See D-008-4.
  - **Layout-agnostic is a binding requirement, not a hope** (operator-mandated):
    the query answer and its cited sources are read via `pages.file_path` + the
    DAL, never by reconstructing `<subdir>/<slug>.md` from layout constants; the
    verdict surface lands via the `layout.py` role-split. This makes R-8
    R-X1/R-X2-forward by construction. See D-008-6 / C-8 / NFR-7.

---

### 1. General Description

TASK 007 shipped the **read/synthesis** half of Karpathy's loop: `wiki-query`
retrieves grounded context, the orchestrator synthesises a **cited** answer, and
the answer is filed as a durable `_queries/<slug>.md` page. The grounding gate
already enforces (in Python) that every citation is a *retrieved* source — but it
does **not** check that the answer's *claims* are actually *supported* by those
sources. A citation can be present and the sentence it backs can still
misrepresent, over-claim, or hallucinate beyond what the source says; an answer
synthesised over untrusted `_raw/` content can smuggle an injected directive into
its prose (H-6).

**R-8 `wiki-verify-multi`** adds the **verification** half for *high-stakes*
answers: an **independent, multi-critic audit** of a filed `_queries/<slug>.md`
answer against the actual bodies of its cited sources, producing a durable
`_verifications/<slug>.md` **verdict page** and a machine-readable
PASS/FAIL signal. It is **off by default** — not auto-invoked by `wiki-query`;
an operator (or an orchestrator policy) runs it deliberately on answers that
matter.

**Goal:** an operator (or sub-agent) runs
`wiki-verify-multi "<query-slug>"`; the system gathers the answer + its cited
source bodies into a **verification envelope**, the orchestrator runs the four
critics in its own context (Decision-17 — no `import anthropic`), each critic
returns findings grounded in the examined sources, `apply` validates the verdict,
files `_verifications/<slug>.md` (Class A), self-indexes it (`type=verification`,
a `verifies` backlink to the query page), fires a `verify` log event, and **exits
non-zero on a FAIL verdict** without ever touching the answer page. A later
`wiki-search --types verification` finds the verdict; a full `wiki-reindex`
rebuilds the verdict page and its `verifies` ref from markdown alone.

Per **Decision-17**, `wiki-verify-multi` is a deterministic two-pass skill — a
`prepare` envelope-assembly pass and an `apply` verdict-write-back pass — with the
orchestrator owning the four-critic reasoning in between (a new `wiki-verify`
prompt-contract skill, analogous to `wiki-query-synthesis`). It **reuses, not
reinvents**: `wiki-query`'s `prepare`/`apply` shape, `source_state` idempotency,
`_common.sanitize_markdown_text` egress sanitiser, the atomic-write /
`O_NOFOLLOW` / `validate_inside_vault` primitives, the **direct-DAL self-index**
(no manifest N+1), the **R-6.5e reindex read-side** (extended for `verifies:`),
and the `/vdd-multi` adversarial-critic pattern.

#### 1.1 Connection with existing system (grounded facts)

| Fact (verified in repo) | Consequence for this task |
|---|---|
| `pages.type` CHECK = `('summary','concept','query','brief','research','index')` ([sql/wiki-index-v2.sql:162-164](../sql/wiki-index-v2.sql)) — **`'verification'` is NOT present**; `TYPE_MAPPING` ([normalization.py:74-93](../scripts/wiki_index/normalization.py)) has no `verification` key. | **DDL #1 (required):** add `'verification'` to the `pages.type` CHECK + `TYPE_MAPPING["verification"]=("verification",None)` + `_PATH_TYPE_FALLBACK[VERIFICATIONS_SUBDIR]="verification"`. Unlike TASK 007 (where `'query'` pre-existed), **R-8 cannot be zero-DDL** — a first-class verdict page type is not pre-provisioned. This forces a schema **v4→v5** bump (R-8.9). |
| `page_entity_refs.ref_type` CHECK = `('mentioned','defined-here','related','cited')` ([sql/wiki-index-v2.sql:194-196](../sql/wiki-index-v2.sql)) — **no `'verifies'`**. PK is `(vault_id, page_slug, page_project, entity_slug, ref_type)`. | **DDL #2 (proposed):** add `'verifies'` to the `ref_type` CHECK for the verdict→query edge (the queryable "what verifies this answer?" relationship; `idx_refs_type` already covers it). *Alternative to shrink the DDL surface to one enum:* reuse `'cited'` (the verdict "cites" the query + sources it examined) — **Architecture decides** (Q-008-a). |
| `log_events.event_type` CHECK = `('ingest','query','lint','reindex','promote','demote','backfill','reclassify','resolve-contradiction','fix-dangling','fix-orphan')` ([sql/wiki-index-v2.sql:225-230](../sql/wiki-index-v2.sql)) — **no `'verify'`**. | **DDL #3 (proposed):** add `'verify'` for the verdict log event (mirrors TASK 007's `'query'` event for traceability; carries the verdict + `--orchestrator-id` provenance in `details_json`). |
| The `pages_fts_{ai,ad,au}` triggers ([sql/wiki-index-v2.sql:371-386](../sql/wiki-index-v2.sql)) index **every** `pages` row — they do **NOT** filter on `type`. | A `type=verification` page is **FTS-searchable automatically** once the CHECK admits it — **no trigger change** needed. (Contrast the `index_meta` view below.) |
| The `index_meta` catalog view ([sql/wiki-index-v2.sql:393-402](../sql/wiki-index-v2.sql)) selects `WHERE type IN ('summary','concept','query')`. | **DDL #4 (proposed):** add `'verification'` to that WHERE so verdict pages appear in the catalog / `wiki-index-render`. Optional but desirable for parity with `query` pages. |
| `source_state` is a generic `(vault_id, source_kind, scope, key) → value` table ([sql/wiki-index-v2.sql:341](../sql/wiki-index-v2.sql)); TASK 007 added `check_query_state`/`record_query_state` DAL wrappers ([repository.py:380-395](../scripts/wiki_index/repository.py)). | Verify idempotency reuses it (`source_kind='verification'`, `scope=verification_slug`, `key='verify_hash'`) — **no new table**. Add sibling DAL methods `check_verify_state`/`record_verify_state` (NFR-2). |
| **The R-6.5e reindex read-side** — `_cited_refs_from_frontmatter(...)` ([reindex.py:91-147](../scripts/wiki_index/reindex.py)) parses a `type=query` page's `cites:` frontmatter into `ref_type='cited'` refs, **unioned into the single `replace_refs`** in both `reindex_delta` (line ~237) and `reindex_full` (line ~350) under a `if db_type == "query":` branch. | **Structural change (the durability spine — R-8.5e):** extend the read-side with a `db_type == "verification"` branch that parses `verifies:` → `ref_type='verifies'` (exact mirror of R-6.5e), unioned into the same single `replace_refs`. Without it, a verdict page's `verifies` backlink is lost on full reindex (§D8 semantic loss) — the *same* read-side gap fixed once for `aliases:` (R-5.3) and once for `cites:` (R-6.5e). |
| `pages.file_path` is a stored **vault-root-relative** path (e.g. `_queries/foo.md`) on every page row; `IndexRepository` exposes `get_page`/`search_pages`/`resolve_entity` ([repository.py](../scripts/wiki_index/repository.py)). | **R-8 reads the query answer + each cited source body via `pages.file_path` resolved against `--vault-root` (and the DAL), NOT by reconstructing `_sources/<slug>.md` from layout constants** — this is what makes R-8 layout-agnostic / R-X1+R-X2-forward (C-8 / NFR-7, operator-mandated). |
| Layout role-split: `HOST_ONLY_SUBDIRS = (QUERIES_SUBDIR,)`; `PAGE_SUBDIRS = (*INGEST_SHARED_SUBDIRS, *HOST_ONLY_SUBDIRS)` ([layout.py:48-56](../scripts/wiki_index/layout.py)). | **R-8.5:** add `VERIFICATIONS_SUBDIR = "_verifications"` to `HOST_ONLY_SUBDIRS` (one line; the verdict surface joins `_queries` as a host-only page-bearing subdir). This is the R-X1-forward seam the operator asked R-8 to exercise (a second member proves the role-split generalises). |
| `wiki-query`'s `_index_query_page` self-indexes via a **direct `upsert_page` + `replace_refs` on one repo connection** — explicitly NOT the `_manifest_consumer`→`main(argv)` N+1 (H-PERF-3/P-8). | `wiki-verify-multi apply` self-indexes the verdict page the same way (one page → direct DAL; reuse `reindex._build_page` + the new `verifies`-ref builder for byte-identical rows). |
| `_common.sanitize_markdown_text` egress allowlist + `atomic_write_text` + `O_NOFOLLOW`/symlink-refuse + `validate_inside_vault` ([_common.py](../scripts/wiki_skills/_common.py)). | `apply` writes `_verifications/<slug>.md` reusing these; the verdict body (critic findings — which **quote** the answer/sources, i.e. untrusted material) is sanitised on egress (injection guard, NFR-3). |
| `/vdd-multi` runs `critic-{logic,security,performance}` in parallel via the `Agent` tool (Layer A), each with independent context, then merges/dedups ([workflows/vdd-multi.md](../workflows/vdd-multi.md)). | R-8's orchestrator critic step **reuses this fan-out pattern**; Architecture decides whether the four lenses run as the existing `.claude/agents/critic-*` subagents (re-pointed at prose) or as a dedicated `wiki-verify` prompt skill driving the lenses (Q-008-d). Either way the synthesis stays orchestrator-owned (Decision-17). |
| H-6 (KNOWN_ISSUES): retrieved bodies are untrusted; `wiki-query-synthesis` carries prompt-armor. | **The answer body AND the cited source bodies fed to the critics are equally untrusted.** The `wiki-verify` prompt skill carries the same H-6 armor; `apply`'s sanitiser is the egress backstop for the verdict body. |

> **Note on the schema filename:** the live DDL lives in `sql/wiki-index-v2.sql`
> — the `-v2` is a legacy era name; the file currently encodes `PRAGMA
> user_version = 4` (TASK 006). R-8 bumps it to **5**. Do not mistake the
> filename for a stale v2 artifact.

---

### 2. Requirements Traceability Matrix (RTM)

#### Epic 7d — R-8 `wiki-verify-multi` (multi-critic verification of cited answers)

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **R-8.1** | `wiki-verify-multi prepare <query-slug>` assembles a **deterministic verification envelope** (no LLM call). | ✅ | (a) resolve the target `_queries/<query-slug>.md` page via the DAL (`get_page` by `(vault_id, slug='<query-slug>', project)`); error `QUERY_NOT_FOUND` if absent or not `type=query`; (b) read the **answer body + `question:` + `cites:` frontmatter** from the query page via `pages.file_path` (NOT a reconstructed path — C-8/NFR-7); (c) for each `cites:` `project/slug`, resolve the cited page via the DAL and read its **body** via *its* `pages.file_path` — **layout-agnostic source access**; (d) compute an `answer_hash` (and check `source_state` for `is_unchanged`); (e) emit envelope `{vault_id, query_slug, question, answer_excerpt, answer_hash, is_unchanged, verification_slug, examined:[{project,slug,title,body_excerpt}], examined_count}`. |
| **R-8.2** | The four-critic verification is **orchestrator-owned** (Decision-17) with a strict verdict contract. | ✅ | (a) **no `import anthropic`** in the skill — zero LLM calls in Python; (b) a new `wiki-verify` prompt-contract skill (repo-root `skills/wiki-verify/SKILL.md`, symlinked) defines the four lenses (**factual-grounding**: every claim ⊆ examined sources; **logic/coherence**: no contradiction/non-sequitur; **security/injection**: no smuggled directive/unsafe content in the answer; **completeness/faithfulness**: no un-cited or hallucinated claim) + the verdict JSON schema; (c) it carries the **H-6 untrusted-content** prompt-armor (the answer + examined source bodies are data, not directives); (d) **per-finding grounding**: every finding that references a source MUST name a `project/slug` present in `prepare`'s `examined` set (R-8.8). |
| **R-8.3** | `wiki-verify-multi apply` writes the verdict as a **Class A** verification page. | ✅ | (a) write `_verifications/<verification-slug>.md` via `atomic_write_text` + `O_NOFOLLOW`/symlink-refuse + `validate_inside_vault`; (b) frontmatter `type: verification`, `verifies: <project>/<query-slug>`, `verdict: pass\|fail`, `critics: [factual,logic,security,completeness]`, `answer_hash:` (sha256 of the audited answer body — the TOCTOU anchor), `date:`, optional `cites: [project/slug,…]` (the subset of sources a finding referenced), `tags: [verification]`; body = sanitised critic findings + a `## Sources` `[[slug]]` list; (c) `--verdict-stdin\|--verdict-file` (the verdict JSON) + `--answer-hash` passed verbatim from `prepare`; (d) sanitise the verdict body via `_common.sanitize_markdown_text` (egress); (e) `--answer-hash` mismatch (the answer page changed between `prepare` and `apply`) → exit 2 `ANSWER_CHANGED` (the `QUESTION_CHANGED` analog; re-run, never auto-retry). |
| **R-8.4** | The verdict page **compounds** — indexed + back-linked. | ✅ | (a) `apply` upserts the verdict page into `pages` (`type='verification'`) via `upsert_page`; (b) writes a `verifies` `page_entity_refs` row from the verdict page → the query page (`ref_type='verifies'`, keyed on the query `project/slug`); plus optional `cited` refs for referenced sources; (c) FTS-searchable immediately after `apply` (the FTS triggers index all types); (d) **self-index via a direct `upsert_page` + `replace_refs` on one repo connection** — NOT the manifest/`main(argv)` N+1 (H-PERF-3/P-8); reuse `reindex._build_page` + the new `verifies`-ref builder for rows byte-identical to a `wiki-reindex --full`. |
| **R-8.5** | `_verifications/` is a **discoverable page-bearing subdir** via the layout role-split. | ✅ | (a) add `VERIFICATIONS_SUBDIR = "_verifications"` to [layout.py](../scripts/wiki_index/layout.py); (b) add it to `HOST_ONLY_SUBDIRS` (so it flows into `PAGE_SUBDIRS` → `discover_pages`/drift/render, and into `SCAFFOLD_DIRS` → `wiki-init --scaffold-new`); (c) add `_PATH_TYPE_FALLBACK[VERIFICATIONS_SUBDIR] = "verification"` (defensive type inference); (d) **no literal `"_verifications"` string anywhere outside `layout.py`** — every caller imports the constant (the chokepoint that makes R-X1's future migration one config line; C-8/NFR-7). |
| **R-8.5e** | **Reindex read-side: re-materialise `verifies` refs from `verifies:` frontmatter** (the §D8 durability spine; the R-6.5e analog). | ✅ | (a) extend the reindex page-rebuild so a `type=verification` page's `verifies:` frontmatter (`project/slug`) is parsed into a `ref_type='verifies'` ref (sibling to `_cited_refs_from_frontmatter`, or a generalised `_frontmatter_refs(db_type)` helper); (b) **union into the single `replace_refs`** in *both* `reindex_full` and `reindex_delta` (the R-6.5e delta-symmetry lesson — both paths or none); (c) if verdict pages carry `cites:`, also re-materialise those as `'cited'` (reuse the existing `cites:`→`'cited'` branch for `type=verification` too); (d) skip-and-report malformed/empty `verifies:`/`cites:` entries (no silent drop, mirroring R-5.3c/R-6.5e c); (e) implement in `reindex.py` (type-aware branch), NOT in `ManualSourceAdapter` (which hardcodes `'mentioned'`). |
| **R-8.6** | Idempotency / re-run semantics. | ✅ | (a) on success `apply` records `verify_hash` in `source_state` (`source_kind='verification'`, `scope=verification_slug`); (b) a `prepare` whose `verify_hash` is unchanged returns `is_unchanged=true` → orchestrator short-circuits (mirrors UC-17); (c) `verify_hash = sha256(answer_hash ‖ ordered examined `project/slug` set)` so a re-verify after the *answer* or the *cited sources* changed re-triggers the critics (Q-008-b); (d) `--force` re-verifies even when unchanged; (e) byte-identical verdict page → content-hash skip (`action:"unchanged"`). |
| **R-8.7** | **FAIL semantics** — record the verdict, signal via exit code, never mutate the answer. | ✅ | (a) the verdict is `pass\|fail` (Architecture defines the rule, e.g. FAIL iff any `factual`/`security` finding ≥ a severity threshold, configurable via `--fail-on`, default mirrors `/vdd-multi`); (b) on FAIL, `apply` still **files** the verdict page (the audit trail is the value) and returns a **non-zero exit code** (`exit 6 VERDICT_FAIL`, distinct from error exits) so the orchestrator/CI can branch; (c) the Class-A `_queries/<slug>.md` answer is **NOT** edited, flagged, quarantined, or deleted — it stays canonical (D-008-3); (d) `--fail-on=none` always exits 0 (report-only mode, parity with `/vdd-multi --fail-on`). |
| **R-8.8** | **Grounding / no-fabrication of findings** (anti-hallucination, at the Python boundary). | ✅ | (a) `prepare` with zero examined sources (a query page with empty `cites:`) → exit 2 `NO_SOURCES` (cannot verify an answer that cites nothing — refuse rather than rubber-stamp); (b) each verdict finding that names a source `project/slug` is validated against the `examined` set → `FINDING_SOURCE_NOT_EXAMINED` (exit 4) if absent (the `CITATION_NOT_RETRIEVED` analog; keyed on the full `project/slug` tuple); (c) the `verdict` enum is validated (`pass\|fail`) → `INVALID_VERDICT` (exit 4) otherwise; (d) grounding is enforced in Python, not trusted to the LLM. |
| **R-8.9** | **Schema v4→v5** migration (the honest DDL cost — see C-5). | ✅ | (a) `sql/wiki-index-v2.sql`: `pages.type` CHECK `+= 'verification'`; `page_entity_refs.ref_type` CHECK `+= 'verifies'` (**per Q-008-a's proposed default**; if Architecture instead reuses `'cited'`, R-8.5e/C-3/R-8.4b collapse accordingly — this sub-feature does not foreclose Q-008-a); `log_events.event_type` CHECK `+= 'verify'`; `index_meta` view WHERE `+= 'verification'`; `PRAGMA user_version = 5`; (b) `docs/SCHEMA-v2.sql` mirror + header comment for v5; (c) migration on a **populated** v4 DB = **delete `.db`/`-wal`/`-shm` → `wiki-init --register-existing` → `wiki-reindex --full`** (the DB is Class B rebuildable; the deletion forces a fresh v5 schema apply — **bare `wiki-reindex --full` only DELETEs rows and cannot relax a CHECK on an existing table**, adversarial-plan DUR-2; no in-place ALTER); (d) a `tests/test_schema_v5.py` pins the new enums + `user_version`; the **three** existing `user_version == 4` pins (`test_schema_v4.py`/`test_schema_smoke.py`/`test_schema_v3.py`) move to `5` in the schema bead. *(There is no `user_version`-gated in-place auto-reseed in the codebase — do not claim one; DEC-4.)* |
| **R-8.10** | **Off-by-default opt-in** (ROADMAP "off by default"). | ✅ | (a) `wiki-verify-multi` is a **separate command** — `wiki-query` does NOT auto-invoke it; (b) the verdict page is only created when an operator/orchestrator runs the verify command; (c) the `workflows/wiki-verify-multi.md` recipe documents it as a deliberate, high-stakes-answer step layered *after* a `wiki-query apply`; (d) no change to `wiki-query`'s default behaviour. |

---

### 3. Use Cases

#### 3.1 UC-22 — Verify a filed answer, verdict PASS (happy path)
- **Actors:** Operator / sub-agent; Orchestrator (LLM, the four critics); System (CLI + DAL).
- **Preconditions:** A `_queries/<slug>.md` answer page exists (filed by
  `wiki-query apply`), with a non-empty `cites:` list; the cited source pages
  are indexed and on disk.
- **Main scenario:**
  1. Operator runs `wiki-verify-multi "how-does-the-hermes-agent-route-messages" --vault trade-agents --vault-root /vaults/trade-agents`.
  2. `prepare` loads the query page (answer body + `question:` + `cites:`) and,
     for each cited `project/slug`, reads the cited source body **via its
     `pages.file_path`** (layout-agnostic). It emits the verification envelope
     (`examined_count: 4`, `answer_hash`, `verification_slug`).
  3. Orchestrator loads the `wiki-verify` skill, treats the answer + examined
     bodies **as untrusted data**, and runs the four critics; each returns
     findings grounded in the examined sources. The merged verdict is `pass`
     (no factual/security findings above threshold).
  4. `apply` re-checks `--answer-hash`, validates the verdict + finding sources,
     sanitises the verdict body, writes `_verifications/how-does-the-hermes-agent-route-messages.md`
     (Class A), upserts it as `type=verification`, writes a `verifies` ref to the
     query page, fires a `verify` log event.
  5. Prints `{"verification_slug":"…","verdict":"pass","verifies":"_vault_/how-…","page_indexed":true,"action":"filed"}` exit **0**.
- **Alternative scenarios:**
  - **A1 `is_unchanged`:** `prepare` finds the same `verify_hash` in
    `source_state` → `is_unchanged=true`; orchestrator stops (UC-24).
  - **A2 `--slug my-verdict`:** operator-supplied verification slug overrides the derived one.
- **Postconditions:** `_verifications/<slug>.md` exists, is FTS-searchable, and
  its `verifies` ref round-trips through `wiki-reindex --full` (UC-26).
- **Acceptance Criteria:**
  - ✅ The verdict page is written with `type: verification` + `verifies:` + `verdict: pass`.
  - ✅ The cited source bodies were read via `pages.file_path`, not a reconstructed `_sources/<slug>.md` path (assert no literal subdir string on the read path).
  - ✅ `wiki-search trade-agents "Hermes" --types verification` returns the new verdict page after apply.
  - ✅ Exit code is 0.

#### 3.2 UC-23 — Verdict FAIL surfaces a non-zero exit; the answer is untouched
- **Actors:** Orchestrator (finds an unsupported claim); System (CLI).
- **Preconditions:** A filed answer makes a claim not supported by any cited
  source (factual finding above threshold).
- **Main scenario:**
  1. `prepare` assembles the envelope; the orchestrator's `factual` critic flags
     an unsupported claim; merged verdict is `fail`.
  2. `apply` files `_verifications/<slug>.md` with `verdict: fail` + the findings,
     fires the `verify` log event, and returns exit **6** (`VERDICT_FAIL`).
  3. The orchestrator/CI sees the non-zero exit and surfaces the verdict to the operator.
- **Alternative scenarios:**
  - **A1 `--fail-on=none`:** the verdict page is still filed with `verdict: fail`,
    but `apply` exits 0 (report-only).
- **Acceptance Criteria:**
  - ✅ On FAIL, exit code is non-zero (`6`) and the verdict page records `verdict: fail`.
  - ✅ The `_queries/<slug>.md` answer file is **byte-identical** before and after (no mutation/quarantine) — asserted by hash.
  - ✅ `--fail-on=none` files the same verdict page but exits 0.

#### 3.3 UC-24 — Re-verify an unchanged answer (idempotent short-circuit)
- **Actors:** Operator; System.
- **Preconditions:** `_verifications/<slug>.md` was filed; the answer + its cited
  sources are unchanged since.
- **Main scenario:**
  1. Operator re-runs the same `wiki-verify-multi "<query-slug>"`.
  2. `prepare` recomputes `verify_hash`, finds it in `source_state`, emits `is_unchanged=true`.
  3. Orchestrator emits `{"status":"unchanged","verification_slug":"…"}` and STOPs — no critics, no write.
- **Alternative scenarios:**
  - **A1 `--force`:** re-runs the critics and overwrites even when unchanged.
  - **A2 answer changed:** if the operator re-ran `wiki-query` and the answer body
    changed, `verify_hash` differs → re-verification proceeds (the compounding
    loop re-audits a re-synthesised answer).
- **Acceptance Criteria:**
  - ✅ An unchanged re-verify performs **no** critic run and **no** write.
  - ✅ A changed answer (or changed cited source) re-triggers verification.

#### 3.4 UC-25 — Compounding: a later search finds the verdict + backlink
- **Actors:** Operator; System.
- **Preconditions:** UC-22 filed `_verifications/q1.md` verifying `_queries/q1.md`.
- **Main scenario:**
  1. Operator runs `wiki-search trade-agents "Hermes" --types verification`.
  2. The result set includes the verdict page.
  3. Operator inspects backlinks: the `verifies` ref links the verdict → the query page.
- **Acceptance Criteria:**
  - ✅ A filed verdict page is returned by FTS search (recall into the loop).
  - ✅ A `verifies` `page_entity_refs` row exists from the verdict page → the query page.
  - ✅ `--types verification` filters to verdict pages; default search behaviour for `_queries` is unchanged.

#### 3.5 UC-26 — Durability round-trip (the load-bearing §D8 acceptance test)
- **Actors:** System (`wiki-reindex --full`).
- **Preconditions:** A vault with one filed verdict page (`type: verification`,
  `verifies: project/query-slug`) and the query + cited pages on disk.
- **Main scenario:**
  1. Snapshot DB state: the verdict page row + its `verifies` ref.
  2. Delete the DB (`.db`/`-wal`/`-shm`); run `wiki-reindex --full`.
  3. Re-read DB state.
- **Acceptance Criteria:**
  - ✅ The `_verifications/<slug>.md` page is rediscovered (because
    `VERIFICATIONS_SUBDIR ∈ HOST_ONLY_SUBDIRS ⊂ PAGE_SUBDIRS`, R-8.5b) and
    re-indexed as `type=verification`.
  - ✅ Its `verifies` ref is reconstructed from the `verifies:` frontmatter alone,
    as `ref_type='verifies'`, by the **R-8.5e reindex read-side** (it does **not**
    degrade to `'mentioned'`). This criterion is RED until R-8.5e lands (the
    current pipeline reads body wikilinks only).
  - ✅ Both `wiki-reindex --full` **and** `--delta` reconstruct the ref (delta-symmetry).

#### 3.6 UC-27 — Grounding/answer-change violations refused at the boundary
- **Actors:** Orchestrator (mis-verifies); System (CLI).
- **Preconditions:** (a) a finding references a `project/slug` not in `prepare`'s
  `examined` set; or (b) the answer page changed between `prepare` and `apply`.
- **Main scenario:**
  1. `apply` validates each finding source against the examined set → a stray
     source → `FINDING_SOURCE_NOT_EXAMINED` (exit 4); nothing written.
  2. `apply` recomputes `answer_hash`; mismatch with `--answer-hash` →
     `ANSWER_CHANGED` (exit 2); nothing written.
- **Acceptance Criteria:**
  - ✅ The grounding + TOCTOU checks are enforced in Python, not trusted to the LLM.
  - ✅ The error envelope names the violating field/shape **without echoing** the
    offending answer/source/finding value (CWE-117/209 invariant; extend the
    `wiki-query` envelope regression).

#### 3.7 UC-28 — Layout-agnostic: verify works on a non-Karpathy vault (R-X1/R-X2-forward acceptance)
- **Actors:** System (CLI + DAL).
- **Preconditions:** A vault whose source pages do **not** live under `_sources/`
  (simulated: a query page whose `cites:` target page has a `file_path` in a
  differently-named directory, indexed in `pages`).
- **Main scenario:**
  1. `prepare` resolves each cited source via the DAL and reads its body via the
     stored `pages.file_path` — **not** by constructing `_sources/<slug>.md`.
- **Acceptance Criteria:**
  - ✅ `prepare` returns the cited source body even though the source is not under
     a Karpathy-layout subdir (proves the source-access path is layout-agnostic).
  - ✅ A unit/grep guard asserts `wiki_verify_multi.py` contains **no** literal
     page-subdir string — **every `PAGE_SUBDIRS` member** (`_sources`,
     `_concepts`, `_entities`, `_queries`, `_verifications`), not an enumerated
     subset — so the query-page read path is layout-agnostic too; all layout
     access goes through `layout.py` / `pages.file_path`.

---

### 4. Non-functional Requirements

- **NFR-1 (ADR-002 §D8 compliance):** the verdict page is **Class A canonical**
  (`_verifications/<slug>.md` incl. `verifies:`/`cites:`) + **Class B mirror**
  (`pages` row + `verifies`/`cited` refs, re-materialised on reindex by R-8.5e).
  `source_state` verify-idempotency is **Class C** (operational, rebuildable).
  The §D8 round-trip (UC-26) must pass — which is *why* R-8.5e is mandatory.
- **NFR-2 (DAL boundary):** **no raw SQL in the skill**; verify-state idempotency
  is added as **new `IndexRepository` methods** (`check_verify_state` /
  `record_verify_state`, thin `source_state` wrappers, mirroring TASK 007's
  `check/record_query_state`), plus reuse of `get_page` / `search_pages` /
  `upsert_page` / `replace_refs`. All statements vanilla DML (Postgres-portable).
- **NFR-3 (security):** verdict write-back reuses `O_NOFOLLOW` + atomic-temp +
  `validate_inside_vault` (no new traversal/symlink surface). The verdict body
  (critic findings quoting untrusted answer/source text) is sanitised via
  `_common.sanitize_markdown_text` (egress). The answer + examined source bodies
  are treated as **untrusted data** in the `wiki-verify` prompt (H-6 armor).
  Error envelopes carry `{error, field?, reason}` only — never echo offending
  content (CWE-117/209; extend the `wiki-query` regression).
- **NFR-4 (typing/tests):** `mypy --strict scripts/` clean; `pytest tests/`
  green; **Stub-First** (signatures + RED tests before logic); **green-throughout**
  (the suite never goes red across bead boundaries — the TASK 007 invariant).
- **NFR-5 (performance):** `prepare` reads the query page + N cited source bodies
  (N = `len(cites)`, bounded by the answer's citation count, ≤50 per the
  `wiki-query` citation cap) — bounded I/O, no full vault scan. `apply`
  self-indexes the one verdict page via **direct `upsert_page` + `replace_refs`**
  — it MUST NOT route through `_manifest_consumer`→`main(argv)` (H-PERF-3/P-8
  N+1). Adding `_verifications` to `PAGE_SUBDIRS` adds one directory to the
  reindex walk (bounded; P-2 inherited, not worsened); the R-8.5e `verifies:`
  parse is O(1) per verdict page.
- **NFR-6 (backward compat):** existing vaults without `_verifications/` reindex
  unchanged (absent dir ⇒ no verdict pages). Adding `_verifications` to
  `HOST_ONLY_SUBDIRS` is purely additive. The **v4→v5 migration on a populated
  DB is delete `.db`/`-wal`/`-shm` → `wiki-init --register-existing` →
  `wiki-reindex --full`** (Class B rebuild, no ALTER; the deletion forces the
  fresh v5 schema — bare `wiki-reindex --full` can't relax a CHECK on an existing
  table, DUR-2). No existing CLI flag changes meaning; `wiki-query` behaviour is unchanged.
- **NFR-7 (layout-agnostic — R-X1/R-X2-forward, operator-mandated, BINDING):**
  *(a)* every source/page read resolves through `pages.file_path` + the DAL —
  **never** by reconstructing `<subdir>/<slug>.md` from a layout constant; *(b)*
  the new verdict surface is declared **only** in `layout.py`
  (`VERIFICATIONS_SUBDIR` ∈ `HOST_ONLY_SUBDIRS`) and every caller imports the
  constant — **no literal `"_verifications"` string outside `layout.py`**; *(c)*
  no new hardcoded `TYPE_MAPPING`/`_PATH_TYPE_FALLBACK`/slug-regex/`_WIKILINK_RE`
  surface beyond the single role-tagged additions in R-8.5/R-8.9. Consequence:
  when R-X1 universalises the layout into YAML config, R-8's surfaces migrate as
  one config entry (the `_queries` precedent) and its source-access path needs
  **zero** change; when R-X2 introduces non-Karpathy layouts, `wiki-verify-multi`
  works unchanged. UC-28 + the no-literal-subdir grep guard are the acceptance.

---

### 5. Constraints and Assumptions

- **C-1 New CLI `wiki-verify-multi`:** needs `bin/wiki-verify-multi` wrapper,
  `scripts/wiki_skills/wiki_verify_multi.py`, `skills/wiki-verify-multi/SKILL.md`
  (deterministic-CLI reference), `commands/wiki-verify-multi.md`,
  `workflows/wiki-verify-multi.md`, **plus** a `wiki-verify` prompt-contract
  skill (`skills/wiki-verify/SKILL.md` — the orchestrator-owned four-critic
  prompt + verdict JSON schema, analogous to `wiki-query-synthesis`,
  **SECURITY-SENSITIVE**), and the full symlink set (`.claude/`, `.agent/`).
- **C-2 Decision-17 (forced):** verification reasoning is orchestrator-owned;
  `wiki-verify-multi` is a deterministic `prepare`/`apply` skill with **no**
  `import anthropic` and no `--model`/`--max-tokens` flags.
- **C-3 Frontmatter contract:** `type: verification`, `verifies: <project>/<query-slug>`,
  `verdict: pass|fail`, `critics: [factual,logic,security,completeness]`,
  `answer_hash: <sha256 of the audited answer body>` (the verdict's TOCTOU
  anchor; renamed from a confusing `question_hash:` per arch-review N-2),
  `date: <YYYY-MM-DD>`, optional `cites: [<project>/<slug>,…]`,
  `tags: [verification]`. Body = sanitised findings + `## Sources` `[[slug]]` list.
- **C-4 Scope fence:** implements **R-8 only**. R-7 (`wiki-research`, web
  enrichment) stays separate and independent. R-8 does **not** modify
  `wiki-query`'s default behaviour (it is off-by-default, R-8.10).
- **C-5 Schema DDL IS required (v4→v5) — NOT zero-DDL:** unlike TASK 007 (where
  `'query'`/`'cited'`/`'query'`-event/`source_state` all pre-existed), the
  verdict page type, the `verifies` ref-type, and the `verify` log-event are
  **not** pre-provisioned (verified §1.1). R-8.9 adds them and bumps
  `PRAGMA user_version` 4→5. The migration on a populated DB is **delete the
  `.db`/`-wal`/`-shm` → `wiki-init --register-existing` → `wiki-reindex --full`**
  (Class B rebuildable, no in-place ALTER; bare `wiki-reindex --full` only DELETEs
  rows and cannot relax a CHECK on an existing table — adversarial-plan DUR-2 —
  so the file deletion that forces a fresh v5 schema apply is load-bearing;
  ADR-002 §D8 amendment). This is the single biggest structural cost of R-8 and the
  primary item for the Architecture + plan review to scrutinise.
- **C-6 Reuse the `wiki-query` loop:** the `prepare`/`apply` shape, the
  `source_state` idempotency, the egress sanitiser, the direct-DAL self-index,
  and the **R-6.5e reindex read-side** (extended, not duplicated) are reused.
  If the `_cited_refs_from_frontmatter` read-side must generalise to handle
  `verifies:`, refactor it into one `_frontmatter_refs(db_type, fm, …)` helper
  rather than copy-pasting (DRY; both query + verification paths stay in sync).
- **C-7 Idempotency state = `source_state`:** reuse the generic table
  (`source_kind='verification'`); do **not** add a `verify_state` table. Access
  it through new DAL methods (NFR-2).
- **C-8 LAYOUT-AGNOSTIC (operator-mandated, BINDING — R-X1/R-X2-compat is a
  requirement, not a hope):** read the query answer + every cited source body via
  `pages.file_path` + the DAL; declare the verdict surface only via the
  `layout.py` `HOST_ONLY_SUBDIRS` role-split; never emit a literal page-subdir
  string outside `layout.py`. Enforced by UC-28 + a grep guard test. (This is the
  exact constraint the operator attached to `/vdd-start-feature`.)
- **C-9 Off-by-default:** `wiki-verify-multi` is invoked deliberately; `wiki-query`
  never calls it automatically (R-8.10).
- **C-10 Verdict pages never create entities:** a verdict page is a `pages` row
  that *verifies* a query page and *references* sources; it does **not** upsert
  `entities` rows and is not alias-expandable as a search term.
- **C-11 Critic fan-out mechanism (Architecture decides — Q-008-d):** the four
  lenses may run as (i) the existing `.claude/agents/critic-{logic,security,performance}.md`
  subagents re-pointed at prose + a new `critic-factual`, or (ii) a single
  `wiki-verify` prompt skill that drives all four lenses in one orchestrator
  context. Either way the synthesis stays orchestrator-owned (Decision-17) and
  the Python skill never calls a model.
- **C-12 Env:** Python 3.14.4 via pyenv + `.venv`; never global installs.

---

### 6. Open Questions

> The four load-bearing scope/shape ambiguities were resolved with the operator
> at analysis time via `/vdd-start-feature` AskUserQuestion (see Decision Log
> D-008-1..4). Residual items below are implementation-level — to be settled in
> Architecture/Planning. **Q-008-c is borderline-blocking** (it defines the verify
> idempotency semantics) and must be settled before R-8.6 is decomposed.

- **Q-008-a (Architecture — DDL surface minimisation):** verdict→query ref-type —
  dedicated **`'verifies'`** (queryable "what verifies this answer?"; +1 enum) vs
  reuse **`'cited'`** (the verdict cites the query it examined; 0 extra enum).
  **Proposed: `'verifies'`** — the relationship *is* the point of R-8 and we are
  already bumping schema; a distinct ref-type makes backlink traversal meaningful.
  Non-blocking (either keeps v4→v5).
- **Q-008-b (Architecture — settle before R-8.6):** `verify_hash` composition.
  **Proposed: `sha256(answer_hash ‖ ordered examined project/slug set)`** so a
  re-verify re-triggers when *either* the answer body *or* any cited source
  changed (the verify loop tracks both inputs it audited). Defines UC-24's
  `is_unchanged` semantics.
- **Q-008-c (Architecture — borderline-blocking):** does `prepare` derive the
  examined-source set from the query page's **`cites:` frontmatter** (cheap,
  authoritative — the answer's own declared citations) or **re-run the original
  retrieval**? **Proposed: read `cites:`** — verification audits *the cited
  answer as filed*, not a fresh retrieval; this avoids the Q-007-1 double-FTS
  cost and is the correct semantics (we verify what the answer claimed to use).
  The `answer_hash` TOCTOU still guards a mid-pipeline answer change. Settle
  before R-8.1/R-8.6 are planned.
- **Q-008-d (Architecture):** critic fan-out mechanism — reuse `.claude/agents/critic-*`
  subagents (+ a `critic-factual`) vs a single `wiki-verify` prompt skill driving
  four lenses (C-11). **Proposed: a `wiki-verify` prompt skill** (keeps R-8
  self-contained + Decision-17-pure + vendor-portable; the workflow MAY still
  fan out to the `Agent` tool when running under Claude Code, mirroring
  `/vdd-multi`'s Layer-A/Fallback split). Non-blocking.
- **Q-008-e (Architecture):** the PASS/FAIL rule + default `--fail-on` threshold.
  **Proposed:** FAIL iff any `factual` or `security` finding has severity ≥
  `high`; `logic`/`completeness` findings are advisory below that bar; default
  `--fail-on=high` (parity with a strict `/vdd-multi`); `--fail-on=none` →
  report-only exit 0 (R-8.7d). Non-blocking.
- **Q-008-f (Architecture):** should the verdict page carry `cites:` (the subset
  of sources a finding referenced) in addition to `verifies:`? **Proposed: yes,
  optional** — emit `cites:` only for sources actually referenced by a finding
  (so the verdict page links to the evidence), re-materialised via the existing
  `cites:`→`'cited'` read-side (R-8.5e c). Non-blocking.
- **Q-008-g (minor):** dogfood — run `wiki-verify-multi` on a throwaway `/tmp`
  vault built from real content (as TASK 005/007 did), verifying a real
  `wiki-query` answer. **Proposed: yes**, reuse the TASK 007 dogfood vaults
  (the repo IS the implementation, not a vault — CLAUDE.md). Non-blocking.

#### Decision Log (analysis-time, operator-confirmed)
- **D-008-1** Verdict surface = a **new first-class `_verifications/<slug>.md`
  page** (compounding artifact: indexed `type=verification`, FTS-searchable,
  `verifies` backlink, §D8-durable), added to `HOST_ONLY_SUBDIRS` via the same
  role-split as `_queries`. *(operator-confirmed via AskUserQuestion)*
- **D-008-2** Critic lenses **recast for prose** = `factual-grounding`,
  `logic/coherence`, `security/injection`, `completeness/faithfulness`. The
  ROADMAP's literal "performance" lens is dropped (it does not map to a prose
  answer); the count stays four. *(operator-confirmed)*
- **D-008-3** FAIL semantics = **record the verdict + return a non-zero exit
  code**; the Class-A `_queries/<slug>.md` answer is **never** mutated,
  quarantined, or deleted (it stays canonical; the verdict page + exit code are
  the outputs). `--fail-on=none` → report-only exit 0. *(operator-confirmed)*
- **D-008-4** Scope = the **full Decision-17 loop** — `prepare` (assemble
  envelope from the query answer + cited source bodies) → orchestrator runs the
  four critics in its own context → `apply` (grounding-checked verdict + Class A
  write + self-index + reindex read-side durability R-8.5e). No trimming of the
  durability spine. *(operator-confirmed)*
- **D-008-5** **Schema DDL IS required (v4→v5)** — `wiki-verify-multi` is **not**
  zero-DDL (the operator's "zero-DDL if possible" explicitly admits this): the
  verdict page type / `verifies` ref-type / `verify` log-event are not
  pre-provisioned in the v4 schema (verified §1.1). The migration is a
  `wiki-reindex --full` (Class B rebuild, no ALTER) — the documented v2→v3→v4
  discipline. *(grounded finding, surfaced at analysis time; C-5 / R-8.9)*
- **D-008-6** **Layout-agnostic source access + verdict-surface role-split are a
  binding requirement** (operator-mandated on `/vdd-start-feature`): R-8 reads
  the answer + cited sources via `pages.file_path` + DAL and declares the verdict
  surface only in `layout.py`, so R-X1 (YAML layout engine) migration is one
  config line and R-X2 (non-Karpathy layouts) needs zero R-8 change. Enforced by
  UC-28 + the no-literal-subdir grep guard (NFR-7 / C-8). *(operator-confirmed)*
- **D-008-7** Verification reasoning is **orchestrator-owned** (Decision-17
  forced): `wiki-verify-multi` is a deterministic `prepare`/`apply` skill; the
  four-critic reasoning lives in the calling agent's context via a `wiki-verify`
  prompt-contract skill. No `import anthropic`. *(precedent — TASK 003 v3.1 / 007)*
