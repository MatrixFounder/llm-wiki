# TASK 013 — `wiki-search` frontmatter metadata filter (R-X3-META-FILTER)

### 0. Meta Information (MANDATORY)
- **Task ID:** 013
- **Slug:** `wiki-search-metadata-filter`
- **Mode:** VDD (`/vdd-start-feature` → `/vdd-plan` → `/vdd-develop-all`)
- **Closes:** `docs/issues/r-x3-fts-frontmatter-metadata-filter.md` (R-X3-META-FILTER,
  SEV-3, ux, open). ROADMAP cluster: **P2 cross-project / Daily-use enablement
  (Cluster C, item 1)**.
- **Predecessor:** TASK 012 (`universal-layout-engine`, shipped 2026-06-01,
  `c127b4b`) — which created the status/severity-bearing per-issue files that make
  this filter necessary.

---

### 1. General Description

The R-X3 KNOWN_ISSUES migration (TASK 012) created per-issue Class-A files
(`docs/issues/*.md`) carrying structured frontmatter — `status`, `severity`,
`category`. The `pages_fts` virtual table indexes only *searchable content*
(`title`, `tldr`, `body_excerpt`, `tags`); `pages.frontmatter_json` is **stored
but never projected into FTS**. So today a bare `wiki-search "status open"`
matches the WORD "open" anywhere in bodies (noise), and `severity` is unreachable
via search at all. The R-X3 dogfood surfaced this directly: another agent expected
`status:open` filtering and got body-text noise.

**Goal:** add a *structured metadata filter* to `wiki-search` so frontmatter
fields are filterable as **predicates** (not full-text), letting an operator (or
sub-agent) answer "show me all open SEV-2 issues" against the freshly-bootstrapped
dev-vault ledger.

**Approach:** Fix-option **1** from the issue (the issue's recommended option) —
a structured filter flag that compiles to a parameterized
`CAST(json_extract(p.frontmatter_json, '$.<field>') AS TEXT) = ?` predicate on the
existing `search_pages` SQL (the `CAST` matches by string representation so numeric
frontmatter values match too — `/vdd-multi` refinement). **No schema change**
(`user_version` stays 5; reuses the
already-stored `frontmatter_json` column) — consistent with TASK 012's zero-DDL
posture. Fix-option 2 (`tag_from_frontmatter` layout option copying values into
the FTS-indexed `pages.tags`) is explicitly **out of scope** (touches
`normalize_frontmatter` + the layout schema + has the FTS5-hyphen hazard on
values like `SEV-2`; revisit only if predicate-filtering proves insufficient).

**Connection with existing system:** extends `scripts/wiki_skills/wiki_search.py`
(CLI) + `scripts/wiki_index/{repository,sqlite_repository}.py::search_pages` (DAL).
The metadata predicate path is **equality via `json_extract`, NOT FTS MATCH**, so
hyphenated values (`SEV-2`, `known-issue`) work without tripping the DF-1 FTS5
hyphen hazard.

---

### 2. List of Use Cases

#### UC-1 — Filter a text search by a frontmatter field (NEW)
- **2.2 Actors:** operator / sub-agent (search consumer); System (DAL).
- **2.3 Preconditions:** target vault indexed; pages carry `frontmatter_json`
  (true for `dev-project` issue pages — the ledger renders from it).
- **2.4 Main Scenario:**
  1. Operator runs `wiki-search "drift" --where 'status=open' --vaults obsidian-llm-wiki --db-path .wiki/index.db`.
  2. System runs the FTS MATCH for `drift` **AND** the parameterized
     `json_extract(frontmatter_json,'$.status')='open'` predicate.
  3. System returns only hits matching both, ranked by BM25 as today.
- **2.5 Alternative Scenarios:**
  - **A1 — unknown/typo'd field:** field name fails the allowlist regex →
    `INVALID_FILTER` envelope (exit 2), names the field, never echoes a value.
  - **A2 — field absent on a page:** `json_extract` returns NULL → that page
    simply doesn't match the `= ?` predicate (no error).
- **2.6 Postconditions:** result set is the intersection of FTS hits and the
  metadata predicate(s); existing output schema unchanged.
- **2.7 Acceptance Criteria:**
  - ✅ `--where 'field=value'` is **repeatable**; multiple filters → **AND**.
  - ✅ Hyphenated values work: `--where 'severity=SEV-2'` returns the SEV-2 set.
  - ✅ Output JSON/markdown schema byte-identical to today when no `--where` given.

#### UC-2 — Query-less metadata listing (NEW)
- **2.3 Preconditions:** as UC-1.
- **2.4 Main Scenario:**
  1. Operator runs `wiki-search --where 'status=open' --where 'severity=SEV-2' --vaults obsidian-llm-wiki --db-path .wiki/index.db` **with no positional query**.
  2. System detects no FTS MATCH term + ≥1 metadata predicate → takes a
     **non-FTS path** (`SELECT … FROM pages WHERE <predicates>`, no `pages_fts`
     join), ordered deterministically.
  3. System returns all matching pages.
- **2.5 Alternative Scenarios:**
  - **A1 — neither query nor filter given:** argparse/handler refuses with a
    usage error (a bare `wiki-search` with nothing is meaningless).
  - **A2 — query-less but with `--no-expand-aliases` etc.:** alias expansion is a
    no-op on the non-FTS path (documented).
- **2.6 Postconditions:** deterministic, BM25-free ordering on the query-less path.
- **2.7 Acceptance Criteria:**
  - ✅ A pure metadata filter (no positional query) returns rows without raising.
  - ✅ Ordering is deterministic (e.g. `(project, slug)`), documented, test-locked.

#### UC-3 — Combine metadata filter with existing facets (MODIFY of UC-03 search)
- **2.4 Main Scenario:** `--where` composes with the existing `--types`,
  `--project`, `--vaults`, `--limit` filters (all AND, all parameterized).
- **2.7 Acceptance Criteria:**
  - ✅ `--where` + `--types <pages.type>` + `--vaults <id>` intersect correctly
    (NB: `--types` filters `pages.type`, e.g. `summary`/`research`/`concept` — NOT
    a frontmatter tag like `known-issue`).
  - ✅ All existing `wiki-search` tests pass unchanged (no regression).

---

### 3. Non-functional Requirements

- **Security (PRIMARY):** the metadata filter is the new untrusted-input surface.
  - **NFR-S1** Field name MUST be validated against an allowlist regex
    (`[a-z][a-z0-9_]*` via `re.fullmatch` — NOT `.match`+`$`, which would let a
    trailing `\n` slip) — rejects JSON-path traversal / SQL metacharacters.
  - **NFR-S2** The JSON path (`'$.'+field`) MUST be passed as a **bound parameter**
    to `json_extract`, and the value as a bound parameter — never string-formatted
    into SQL. (SQLite accepts `json_extract(col, ?)` with the path bound.)
  - **NFR-S3** Error envelopes MUST NOT echo the offending value (CWE-209/CWE-117
    consistency with the rest of the skill family).
- **Performance:** `json_extract` over `frontmatter_json` is an **unindexed row
  scan** of the vault's pages. Acceptable at current scale (hundreds of pages).
  Document as an accepted residual; a generated-column + index is a *future*
  enhancement gated by the same 1k-page trigger as P-1..P-4 (NOT in this task —
  zero-DDL constraint).
- **Compatibility:** zero behaviour change when no metadata flag is passed
  (golden: existing `test_wiki_search*` byte-identical).
- **Compatibility (DDL):** zero schema change; `user_version` stays 5.

---

### 4. Constraints and Assumptions

- **C1 — Zero DDL.** Reuse `pages.frontmatter_json`; no new column/index/table.
- **C2 — Equality only (v1).** `field=value` exact match, by **string
  representation** (`CAST(json_extract(...) AS TEXT)` — so `priority=1` matches a
  numeric frontmatter value; booleans serialize to `1`/`0`). No `<`/`>`/`!=`/`LIKE`
  /range. (Severity ordering needs a rank map — a separate enhancement; YAGNI.)
- **C3 — AND semantics** across multiple `--where` filters (no OR in v1); two
  predicates on the same field are rejected (`INVALID_FILTER`).
- **C4 — Assumption:** `frontmatter_json` is populated for filterable pages. TRUE
  for `dev-project` issue pages (the auto-rendered ledger reads `status`/`severity`
  /`category` from it). Pages with no frontmatter simply never match a `--where`.
- **C5 — Scope = R-X3-META-FILTER only.** This is Cluster C item 1. The two sibling
  Cluster-C items are **NOT** in this task:
  - *Global registration* (`wiki-init --register-existing --vault docs` + reindex
    against the global DB) is **operational** — captured as a runbook note /
    README acceptance step, not code.
  - *R-X2c archive hook* (cross-repo `agentic-development` change) stays a
    **deferred follow-up** (ROADMAP R-X2c) — separate task/branch.
- **C6 — On completion:** flip `docs/issues/r-x3-fts-frontmatter-metadata-filter.md`
  `status: open → fixed` and re-render the ledger (`wiki-index-render
  --auto-indexes`) so the Class-B `docs/KNOWN_ISSUES.md` reflects it; `wiki-lint`
  PW-Q drift guard must stay green.

---

### 5. Open Questions (for Architecture / operator)

- **Q1 — CLI surface.** Ship a general repeatable `--where 'field=value'` as the
  primitive, **plus** convenience aliases `--status <v>` / `--severity <v>`
  (the two fields the dogfood actually wanted)? Or `--where` only? *Analyst lean:
  `--where` primitive + `--status`/`--severity` sugar that desugar to it.*
- **Q2 — DAL shape.** Extend `search_pages` with an optional `where_fields:
  list[tuple[str,str]] | None` param and make `query` optional, **or** add a
  separate `filter_pages()` DAL method for the query-less path? *Analyst lean:
  one method — extend `search_pages`, branch internally on "has MATCH term".*
- **Q3 — Query-less ordering.** With no FTS MATCH there is no BM25 — order by
  `(project, slug)`? by `last_modified`? *Analyst lean: `(project, slug)`
  deterministic.*
- **Q4 — Field-name allowlist policy.** Static regex only (`[a-z][a-z0-9_]*`),
  or also a per-layout `filterable_fields` allowlist in the layout config? *Analyst
  lean: static regex for v1 (any well-formed field is allowed); a per-layout
  allowlist is a YAGNI follow-up.*

---

## Requirements Traceability Matrix (RTM)

| Req | Source | Use Case | Acceptance test (planned) |
|-----|--------|----------|---------------------------|
| **R-MF-1** structured `--where 'field=value'` filter | R-X3-META-FILTER fix-opt 1 | UC-1 | `--where 'status=open'` returns only open pages |
| **R-MF-2** repeatable `--where`, AND semantics | C3 | UC-1/UC-3 | two `--where` → intersection |
| **R-MF-3** hyphenated values via equality (not FTS) | issue (DF-1 hazard) | UC-1 | `--where 'severity=SEV-2'` returns SEV-2 set |
| **R-MF-4** query-less pure-metadata listing | UC-2 | UC-2 | no positional query + `--where` returns rows |
| **R-MF-5** deterministic query-less ordering | Q3 | UC-2 | order locked by test |
| **R-MF-6** field-name allowlist (injection guard) | NFR-S1 | UC-1/A1 | `--where 'a;b=x'` → `INVALID_FILTER` exit 2 |
| **R-MF-7** parameterized json-path + value | NFR-S2 | UC-1 | injection probe yields no rows / clean error |
| **R-MF-8** envelopes never echo values | NFR-S3 | UC-1/A1 | regression test on error payload |
| **R-MF-9** zero behaviour change w/o flag | NFR compat | UC-3 | existing `test_wiki_search*` unchanged |
| **R-MF-10** zero DDL | C1 | — | `user_version` still 5 |
| **R-MF-11** close issue + re-render ledger + lint green | C6 | — | issue `fixed`; PW-Q drift guard passes |
