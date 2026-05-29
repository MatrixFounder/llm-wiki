# TASK 005 — Epic 7 completion: confirmed/candidate entity resolution + two-tier alias table + duplicate-merge (R-4 + R-5)

> **VDD MODE** — high-integrity decomposition. Requirements structured as
> two Epics with an RTM, detailed Use Cases, and binary Acceptance Criteria.

### 0. Meta Information

- **Task ID:** 005
- **Slug:** `entity-resolution`
- **Mode:** VDD (`/vdd-start-feature` → `/vdd-plan` → `/vdd-develop-all`)
- **Roadmap source:** `docs/ROADMAP.md` → "P1 — Epic 7 entry-point: entity
  resolver" → **R-4** (confirmed/candidate resolution) + **R-5** (two-tier
  alias table).
- **Predecessors:** R-3 / TASK 003 v3.1 (`wiki-extract-concepts`, the Epic 7
  entry-point that *creates* candidate entities) — SHIPPED 2026-05-28
  (`43812f2`). This task makes those candidates *resolvable + durable*.
- **Closes:** `docs/KNOWN_ISSUES.md` **L-4** (entity_aliases PK lets one
  alias point to multiple entities).
- **Unblocks:** ROADMAP **R-X5** (cross-project entity-graph, Phase F) which
  is explicitly gated on "Epic 7 (R-3..R-5 entity resolver)".

---

### 1. General Description

`wiki-extract-concepts apply` (R-3) emits **candidate** entities
(`is_candidate = 1`) from LLM synthesis. Today there is **no path to confirm
them**, **no alias resolution**, and — critically — **the candidate flag and
aliases do not survive `wiki-reindex --full`**. This task closes Epic 7's
entry-point by delivering the two-tier resolution layer Karpathy's
compounding-artifact promise depends on.

**Goal:** an operator (or an automatic mention-threshold) can *promote*
candidate entities to confirmed; alias surface-strings (`"Hermes"`,
`"Hermes Agent"`, `"Hermes Framework"`) resolve to a single canonical entity
in both search and lint; **duplicate entities created by the LLM
(`hermes-agent` vs `hermes-framework`) can be *merged* into one canonical
entity** — the literal "Hermes / Hermes Agent / Hermes Framework duplication"
the ROADMAP R-4 names; and **every one of these decisions is Class A (markdown
frontmatter) so a full DB rebuild never loses them** (ADR-002 §D8).

#### 1.1 Connection with existing system (grounded facts)

| Fact (verified in repo) | Consequence for this task |
|---|---|
| `entities.is_candidate INTEGER DEFAULT 0` exists ([SCHEMA-v2.sql:104](SCHEMA-v2.sql)); `idx_entities_candidate` partial index exists. | DB column ready; no DDL needed for the flag itself. |
| `write_concept_page` **already writes** `is_candidate: true` + `tags:[concept,candidate]` into Class A frontmatter ([wiki_extract_concepts.py:653-654](../scripts/wiki_skills/wiki_extract_concepts.py)). | Write-side of Class A persistence already exists. |
| `reindex_full` registers entities with `INSERT OR IGNORE … (no is_candidate col)` → **defaults to 0 = confirmed** ([reindex.py:264-273](../scripts/wiki_index/reindex.py)); **never reads `aliases:` frontmatter**. | **Round-trip is broken on the READ side.** `wiki-reindex --full` silently confirms every candidate and drops aliases. R-4.5 + R-5.3 fix this. |
| `entity_aliases` PK = `(vault_id, alias, entity_slug)` ([SCHEMA-v2.sql:147](SCHEMA-v2.sql)) → one alias may point to many entities (**L-4**). | R-5.4 changes PK to `(vault_id, alias)`. |
| `IndexRepository.resolve_entity` is a stub raising `NotImplementedError("entity resolution arrives in Epic 7")` ([repository.py:260-267](../scripts/wiki_index/repository.py)). | R-4/R-5 implement it. |
| `upsert_entity` has a hard SQL downgrade guard `is_candidate = MIN(excluded, existing)` ([sqlite_repository.py:777](../scripts/wiki_index/sqlite_repository.py)) — re-extraction can never demote. | Operator confirm/undo needs a **separate explicit setter** that bypasses MIN(); auto-promote rides the existing confirm path. |
| `mentions_count` recomputed **only** during reindex Step 3 ([reindex.py:301-308](../scripts/wiki_index/reindex.py)). | Auto-promote sweep (R-4.4) **and** merge (R-4.7d) must recompute `mentions_count` themselves before thresholding/reporting, else they read a stale value. |
| `page_entity_refs` has **no FK on `entity_slug`** (schema note: "refs may target unresolved wiki-link slugs", [SCHEMA-v2.sql:231](SCHEMA-v2.sql)); PK = `(vault_id, page_slug, page_project, entity_slug, ref_type)`. | Merge (R-4.7a) can re-point `entity_slug` freely (no FK to break) but must de-dup on the PK. After merge, source pages still contain `[[from-slug]]`; on reindex those refs re-materialise pointing at the now-absent `from` entity → **`resolve_entity` (R-4.5b) and `find_orphan_links` (R-4.5d) must resolve *through aliases*** so the merged-away slug is not flagged as an orphan. The alias registered in R-4.7b is what keeps the redirect durable across reindex. |
| DAL boundary contract: "Skills never construct raw SQL — they call repository methods" ([repository.py:43-45](../scripts/wiki_index/repository.py)). | All new behavior lands as `IndexRepository` methods first; CLIs are thin. |
| Existing CLI surface: `bin/<cmd>` thin wrapper → `python -m scripts.wiki_skills.<mod>`; symlinked into `.claude/` + `.agent/`. | Two new CLIs (`wiki-confirm`, `wiki-alias`) follow this exact pattern. |

---

### 2. Requirements Traceability Matrix (RTM)

#### Epic 7a — R-4 Confirmed / candidate entity resolution

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **R-4.1** | Confirm-state is **Class A durable** (frontmatter ↔ DB round-trip). | ✅ | (a) `reindex_full` reads `is_candidate` from entity-page frontmatter instead of hardcoding 0; (b) absent key ⇒ confirmed (`0`) for back-compat with existing vaults; (c) `wiki-reindex --full` of a vault with `is_candidate: true` pages preserves the flag. |
| **R-4.2** | `wiki-confirm <slug>` CLI promotes candidate → confirmed. | ✅ | (a) write-back `is_candidate: false` (+ drop `candidate` tag) to the entity's `file_path` frontmatter atomically; (b) mirror to DB (`is_candidate=0`); (c) idempotent (already-confirmed ⇒ exit 0 `unchanged`); (d) `--vault <id>` required, `ENTITY_NOT_FOUND` envelope on miss. |
| **R-4.3** | `wiki-confirm <slug> --undo` demotes confirmed → candidate (operator-explicit). | ✅ | (a) explicit DB setter that **bypasses the MIN() guard**; (b) frontmatter write-back `is_candidate: true`; (c) refuses on a non-existent entity. |
| **R-4.4** | `wiki-confirm --auto [--threshold N]` bulk-promotes by mention count. | ✅ | (a) recompute `mentions_count` for the vault first (freshness); (b) promote every candidate with `mentions_count ≥ N` (default **3**, configurable); (c) `--dry-run` lists what *would* promote; (d) emit JSON summary `{promoted:[slugs], threshold, scanned}`. |
| **R-4.5** | Implement `IndexRepository.resolve_entity` (retire the Epic-7 stub). | ✅ | (a) resolve by slug → `Entity` (confirmed or candidate); (b) resolve **through aliases** (surface string → canonical entity); (c) `None` on no match (no raise); (d) make `find_orphan_links` **alias-aware** — a `page_entity_refs` target that matches a registered alias resolves to its entity and is **not** reported as an orphan (required so merged-away slugs from R-4.7 do not pollute lint). |
| **R-4.6** | `wiki_extract_concepts apply` keeps writing the Class A candidate flag (regression guard). | ✅ | (a) pin `is_candidate: true` in `write_concept_page` frontmatter; (b) regression test that a freshly-applied candidate survives `reindex --full` as a candidate. |
| **R-4.7** | `wiki-merge <from-slug> <into-slug>` folds a duplicate entity into a canonical one (resolves the literal Hermes/Hermes-Agent/Hermes-Framework duplication R-4 names). | ✅ | (a) re-point every `page_entity_refs.entity_slug = from` → `into`, de-duplicating on the `(page, into, ref_type)` PK by keeping the higher `trust_level`; (b) absorb `from`'s aliases into `into` (re-point `entity_aliases`, skip-and-report on hard-PK collision) **and** register `from`'s slug + canonical name as new aliases of `into` (`alias_type=former_name`) — the **alias *is* the durable redirect**; (c) Class A: append the absorbed surfaces to `into`'s frontmatter `aliases:` list **and delete the `from` entity page from disk** atomically (so `reindex --full` does not re-materialise `from`); (d) recompute `into.mentions_count`; (e) refuse self-merge (`INVALID_MERGE`) and missing endpoints (`ENTITY_NOT_FOUND`); (f) `--dry-run` reports ref-count + aliases that *would* move, writes nothing. |

#### Epic 7b — R-5 Two-tier alias table

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **R-5.1** | `wiki-alias <slug> --add "<surface>"` registers an alias. | ✅ | (a) append to entity-page frontmatter `aliases:` list (Class A, Obsidian-native flat list); (b) mirror to `entity_aliases` (Class B) with `alias_type` (default `spelling_variant`, override via `--type`); (c) reject if the surface collides with another entity's alias/slug/name (see R-5.6); (d) idempotent re-add ⇒ `unchanged`. |
| **R-5.2** | `wiki-alias <slug> --remove "<surface>"` / `--list`. | ✅ | (a) `--remove` drops from frontmatter + DB; (b) `--list` prints current aliases for the slug; (c) `--remove` of an absent alias ⇒ exit 0 `unchanged`. |
| **R-5.3** | `reindex_full` mirrors Class A `aliases:` → `entity_aliases`. | ✅ | (a) parse `aliases:` (flat YAML list) from each `_concepts/_entities` page; (b) upsert into `entity_aliases` with default `alias_type`; (c) on a hard-PK conflict the page is **kept** but the conflicting alias is **skipped and recorded** in the reindex warnings/`skipped` report — **never a silent `INSERT OR IGNORE`** (the conflict must reach the operator, see R-5.6e). |
| **R-5.4** | Fix `entity_aliases` PK → `(vault_id, alias)` (closes **L-4**). | ✅ | (a) SCHEMA-v2.sql + sql/wiki-index-v2.sql DDL change; (b) `entity_slug` becomes a regular column; (c) bump `PRAGMA user_version 2→3` + `schema_meta`; (d) migration note: DB is Class B → existing DBs rebuilt via `wiki-reindex --full` (documented, no in-place ALTER). |
| **R-5.5** | `wiki-search` expands query through aliases (**default on**). | ✅ | (a) for each matched alias/entity, OR-expand the FTS MATCH with canonical name + sibling aliases; (b) `--no-expand-aliases` disables (byte-identical to today's behavior); (c) expansion respects `--vaults` scoping; (d) does not change BM25 ordering semantics beyond the added OR terms. |
| **R-5.6** | `wiki-lint` detects alias collisions. | ✅ | (a) in-table: same `alias` → ≥2 distinct `entity_slug` (only reachable on a pre-migration / hand-built DB — the hard PK prevents new ones); (b) cross-table: an `alias` string equal to a *different* entity's canonical `slug` or `name`; (c) surfaced as a new lint category with `--json` parity; (d) non-zero advisory exit only if `--strict` (consistent with existing lint policy); (e) **Class A frontmatter scan** — detect two entity pages whose `aliases:` claim the same surface string. Post-hard-PK these can never *coexist* in the DB (the mirror reports + skips one per R-5.3c), so the canonical conflict is visible only at the file layer; lint must read frontmatter to stay authoritative on the source of truth. |

---

### 3. Use Cases

#### 3.1 UC-09 — Confirm a candidate entity
- **Actors:** Operator; System (CLI + DAL).
- **Preconditions:** Vault registered; `_concepts/hermes-agent.md` exists with
  `is_candidate: true`; DB row `is_candidate=1`.
- **Main scenario:**
  1. Operator runs `wiki-confirm hermes-agent --vault trade-agents`.
  2. System looks up the entity, reads its `file_path` frontmatter.
  3. System atomically rewrites frontmatter `is_candidate: false`, removes the
     `candidate` tag, preserving all other keys/body (reuses the
     `O_NOFOLLOW` + atomic-temp + content-hash primitives from
     `write_concept_page`).
  4. System mirrors `is_candidate=0` into the DB via the explicit setter.
  5. System prints `{"slug":"hermes-agent","status":"confirmed","changed":true}` exit 0.
- **Alternative scenarios:**
  - **A1 already confirmed:** step 2 finds `is_candidate=0` → no write, prints
    `"changed":false` exit 0 (idempotent).
  - **A2 entity not found:** `ENTITY_NOT_FOUND` envelope, exit 3.
  - **A3 file_path missing on disk:** `ENTITY_FILE_MISSING` envelope, exit 4
    (DB/disk drift — operator told to run `wiki-reindex --delta`).
  - **A4 `--undo`:** inverse — sets `is_candidate: true` (R-4.3), bypassing the
    MIN() guard.
- **Postconditions:** Frontmatter and DB agree; `wiki-reindex --full` is a
  no-op on the flag (durability).
- **Acceptance Criteria:**
  - ✅ Confirm flips both Class A frontmatter **and** DB.
  - ✅ A subsequent `wiki-reindex --full` keeps `is_candidate=0`.
  - ✅ Re-running confirm is idempotent (`changed:false`).

#### 3.2 UC-10 — Auto-promote candidates by mention threshold
- **Actors:** Operator (or future cron); System.
- **Preconditions:** Vault has candidates with varying `page_entity_refs` counts.
- **Main scenario:**
  1. Operator runs `wiki-confirm --auto --threshold 3 --vault trade-agents`.
  2. System recomputes `mentions_count` for the vault (fresh COUNT over
     `page_entity_refs`).
  3. System selects candidates with `mentions_count ≥ 3`.
  4. For each, performs the UC-09 confirm flow (frontmatter + DB).
  5. Prints `{"promoted":["hermes-agent",…],"threshold":3,"scanned":N}` exit 0.
- **Alternative scenarios:**
  - **A1 `--dry-run`:** steps 1-3 only; prints the would-promote list, writes nothing.
  - **A2 none qualify:** `"promoted":[]` exit 0.
  - **A3 default threshold:** omitting `--threshold` uses **N=3**.
- **Postconditions:** Promoted entities are confirmed + durable.
- **Acceptance Criteria:**
  - ✅ Promotion uses a freshly-recomputed `mentions_count`, not stale.
  - ✅ `--dry-run` mutates nothing (frontmatter + DB unchanged).
  - ✅ Threshold boundary is `≥` (a candidate with exactly N mentions promotes).

#### 3.3 UC-11 — Register / manage an alias
- **Actors:** Operator; System.
- **Preconditions:** Entity `hermes-agent` exists.
- **Main scenario:**
  1. `wiki-alias hermes-agent --add "Hermes Framework" --vault trade-agents`.
  2. System verifies no collision (R-5.6 rules) for `"Hermes Framework"`.
  3. System appends to the entity page frontmatter `aliases:` list (Class A).
  4. System mirrors to `entity_aliases` (Class B) with default
     `alias_type=spelling_variant`.
  5. Prints `{"slug":"hermes-agent","alias":"Hermes Framework","action":"added"}`.
- **Alternative scenarios:**
  - **A1 duplicate add:** alias already present → `action:"unchanged"` exit 0.
  - **A2 collision:** surface already an alias of / equal to a *different*
    entity → `ALIAS_COLLISION` envelope, exit 5, names the conflicting slug.
  - **A3 `--remove`:** drops from frontmatter + DB (absent ⇒ `unchanged`).
  - **A4 `--list`:** prints the current alias list for the slug.
- **Postconditions:** Alias round-trips through `wiki-reindex --full`.
- **Acceptance Criteria:**
  - ✅ `--add` writes both Class A frontmatter and Class B DB row.
  - ✅ Full reindex reconstructs the alias from frontmatter alone.
  - ✅ Collision is refused with a non-zero, named-conflict envelope.

#### 3.4 UC-12 — Search with alias expansion
- **Actors:** Operator / sub-agent; System.
- **Preconditions:** `hermes-agent` has aliases `["Hermes", "Hermes Framework"]`.
- **Main scenario:**
  1. `wiki-search trade-agents "Hermes"`.
  2. System resolves `"Hermes"` → entity `hermes-agent`, gathers its canonical
     name + sibling aliases.
  3. System OR-expands the FTS MATCH with those surface strings.
  4. Returns ranked hits that mention *any* surface form, BM25-ordered.
- **Alternative scenarios:**
  - **A1 `--no-expand-aliases`:** behaves byte-identically to current search.
  - **A2 surface not an alias:** expansion is a no-op; plain FTS as today.
- **Postconditions:** Recall improved without changing default ranking math.
- **Acceptance Criteria:**
  - ✅ A page mentioning only `"Hermes Framework"` is returned for query `"Hermes"` (default).
  - ✅ `--no-expand-aliases` returns exactly today's result set.

#### 3.5 UC-13 — Lint detects alias collision
- **Actors:** Operator; System.
- **Preconditions:** A DB (pre-migration or hand-edited frontmatter) where
  `"Hermes"` is an alias of both `hermes-agent` and `hermes-bus`, **or**
  `"Hermes"` equals another entity's `slug`/`name`.
- **Main scenario:**
  1. `wiki-lint --vault trade-agents`.
  2. System runs the new alias-collision query.
  3. Reports each collision with the alias + the set of conflicting slugs.
- **Alternative scenarios:**
  - **A1 `--json`:** collisions appear in the JSON sidecar with parity.
  - **A2 `--strict`:** collisions raise the advisory exit code; default mode reports only.
- **Acceptance Criteria:**
  - ✅ Both in-table and cross-table collisions are detected.
  - ✅ `--json` output includes the new category with the same shape as existing categories.

#### 3.6 UC-14 — Durability round-trip (the load-bearing acceptance test)
- **Actors:** System (`wiki-reindex --full`).
- **Preconditions:** A vault with one confirmed entity (`is_candidate:false`),
  one candidate (`is_candidate:true`), and one alias.
- **Main scenario:**
  1. Snapshot DB state for the three facts.
  2. Delete the DB; run `wiki-reindex --full`.
  3. Re-read DB state.
- **Acceptance Criteria:**
  - ✅ Confirmed stays confirmed; candidate stays candidate; alias is rebuilt —
    **all reconstructed from markdown alone** (ADR-002 §D8 Class A→B test passes).

#### 3.7 UC-15 — Merge a duplicate entity into the canonical one
- **Actors:** Operator; System (CLI + DAL).
- **Preconditions:** Vault registered; the LLM created two entities for the
  same real-world thing — `hermes-framework` (the duplicate) and `hermes-agent`
  (the keeper); both have `_concepts/*.md` pages and `page_entity_refs`.
- **Main scenario:**
  1. Operator runs `wiki-merge hermes-framework hermes-agent --vault trade-agents`.
  2. System verifies both entities exist and `from ≠ into`.
  3. **Class A first (source of truth):** appends `hermes-framework` (slug) +
     its canonical name + its own aliases to `hermes-agent`'s frontmatter
     `aliases:` list (`alias_type=former_name`), reusing the `O_NOFOLLOW` +
     atomic-temp primitives; then **deletes `_concepts/hermes-framework.md`**
     from disk atomically.
  4. **Class B mirror (one transaction):** re-points every
     `page_entity_refs.entity_slug = 'hermes-framework'` → `'hermes-agent'`,
     de-duplicating on `(page, 'hermes-agent', ref_type)` by keeping the higher
     `trust_level`; re-points `entity_aliases` (skip-and-report on collision);
     registers the redirect aliases; deletes the `hermes-framework` entity row;
     recomputes `hermes-agent.mentions_count`.
  5. Prints `{"from":"hermes-framework","into":"hermes-agent","refs_repointed":N,"aliases_absorbed":M,"action":"merged"}` exit 0.
- **Alternative scenarios:**
  - **A1 `--dry-run`:** steps 2 only + a read-only count; prints the
    would-merge report `{"refs_repointed":N,"aliases_absorbed":M,"dry_run":true}`, writes nothing.
  - **A2 self-merge (`from == into`):** `INVALID_MERGE` envelope, exit 5.
  - **A3 endpoint missing:** `ENTITY_NOT_FOUND` envelope (names which side), exit 3.
  - **A4 alias collision on re-point:** a `from` alias already maps to a third
    entity → that one alias is **skipped and reported** in the summary
    (`"aliases_skipped":[...]`); the merge still completes.
  - **A5 `from` file missing on disk (DB/disk drift):** `ENTITY_FILE_MISSING`
    envelope, exit 4 (operator told to `wiki-reindex --delta` first).
- **Postconditions:** `from` no longer exists as an entity; its surface strings
  resolve to `into` through the alias table; a subsequent `wiki-reindex --full`
  **does not re-materialise `from`** and reconstructs the redirect aliases from
  `into`'s frontmatter alone.
- **Acceptance Criteria:**
  - ✅ After merge, `resolve_entity(from-surface)` returns the `into` entity.
  - ✅ `[[from-slug]]` references in source pages are **not** flagged as orphans
    by `wiki-lint` (alias-aware, R-4.5d).
  - ✅ `into.mentions_count` equals the de-duplicated union of both entities' refs.
  - ✅ Full reindex reproduces the merged state from markdown alone (`from`
    page absent + `into.aliases` carrying the old surfaces) — the §D8 gate.
  - ✅ `--dry-run` mutates neither frontmatter, files, nor DB.

---

### 4. Non-functional Requirements

- **NFR-1 (ADR-002 §D8 compliance):** confirm-state and aliases are Class A
  canonical (frontmatter) + Class B mirror. The §D8 test — "delete the column,
  reindex, does it restore? Yes ⇒ Class B" — must pass. No new Class C field.
- **NFR-2 (DAL boundary):** no raw SQL in skills; all behavior via new
  `IndexRepository` methods (e.g. `set_entity_candidate`, `list_candidates`,
  `recompute_mentions`, `auto_promote_candidates`, `add_alias`, `remove_alias`,
  `list_aliases`, `expand_aliases`, `find_alias_collisions`, `merge_entities`,
  plus `resolve_entity`); `find_orphan_links` is extended to be alias-aware
  (R-4.5d). Postgres backend stays implementable (`merge_entities` is a single
  transaction of UPDATE/DELETE statements — no SQLite-specific feature).
- **NFR-3 (security):** frontmatter write-back reuses the existing
  `O_NOFOLLOW` + atomic-temp + path-inside-vault primitives (no new symlink /
  traversal surface). Alias/surface strings are validated + length-capped;
  error envelopes never echo offending content (CWE-117/CWE-209 invariant
  already enforced by `wiki-extract-concepts` regression tests — extend it).
- **NFR-4 (typing/tests):** `mypy --strict scripts/` clean; `pytest tests/`
  green; Stub-First (signatures + RED tests before logic).
- **NFR-5 (performance):** auto-promote `mentions_count` recompute is a single
  set-based `UPDATE`, not per-row (consistent with reindex Step 3). Alias
  expansion adds bounded OR terms (cap expansion breadth to avoid FTS blow-up).
- **NFR-6 (backward compat):** existing vaults without `is_candidate`/`aliases`
  frontmatter reindex unchanged (absent ⇒ confirmed, no aliases). Default
  search behavior changes (expansion on) — documented; `--no-expand-aliases`
  restores exact prior output.

---

### 5. Constraints and Assumptions

- **C-1 New CLIs:** `wiki-confirm`, `wiki-alias`, `wiki-merge` — each needs
  `bin/<cmd>` wrapper, `scripts/wiki_skills/<mod>.py`, a `skills/<name>/SKILL.md`,
  `commands/<name>.md`, `workflows/<name>.md`, and the symlink set
  (`.claude/`, `.agent/`) per CLAUDE.md conventions.
- **C-2 Schema migration:** PK change is breaking but cheap here — the DB is
  Class B/rebuildable + gitignored. `apply_schema` uses
  `CREATE TABLE IF NOT EXISTS` (won't ALTER an existing table); migration path
  is **bump `user_version` 2→3 + `wiki-reindex --full`**, not in-place ALTER.
  Document in ADR-002 (or an ADR-003 stub) and in the migration note.
- **C-3 Frontmatter key:** confirm-state uses the existing
  `is_candidate: true|false` boolean (already written by `write_concept_page`).
  Aliases use Obsidian-native flat `aliases:` list.
- **C-4 alias_type round-trip limitation:** the flat Obsidian `aliases:` list
  carries no type, so `alias_type` defaults to `spelling_variant` on reindex
  mirror. A richer `--type` set via `wiki-alias` is Class B only and will
  normalize to the default on full reindex (documented limitation — alias_type
  is not load-bearing for search/lint).
- **C-5 Scope fence:** implements R-4 (incl. `wiki-merge`, R-4.7) + R-5 only.
  RAG layer (R-6..R-8) and cross-project graph (R-X5) remain out of scope and
  gated on this task.
- **C-6 Env:** Python 3.14.4 via pyenv + `.venv`; never global installs.
- **C-7 Merge redirect = aliases, NOT wikilink rewriting:** `wiki-merge`
  resolves the duplicate by **deleting the `from` entity page + registering its
  surfaces as aliases of `into`** (the alias table is the redirect). It does
  **not** rewrite `[[from-slug]]` wikilinks inside `_sources`/other pages
  (that is what `wiki_ingest`'s `promote`/`demote` do for a different layer);
  durable redirection relies on alias-aware resolution (R-4.5b/d) instead.
  Vault-wide wikilink rewriting is explicitly out of scope (heavier, mutates
  Class A source bodies, higher blast radius) — revisit only if a real vault
  shows stale-link friction.
- **C-8 Merge write-order:** Class A mutation first (append `into.aliases` +
  delete `from` page atomically), then the Class B DB transaction. If the DB
  mirror fails after the file ops, the state is recoverable via
  `wiki-reindex --delta` (Class A is canonical) — surfaced as
  `MERGE_MIRROR_FAILED`, exit 6.

---

### 6. Open Questions

> Critical scope/architecture ambiguities were resolved with the operator at
> analysis time (see Decision Log). Residual items below are **minor /
> implementation-level** — to be settled in Architecture/Planning, not blocking.

- **Q1 (resolved → decided):** Auto-promotion on N mentions — **IN SCOPE**
  (`wiki-confirm --auto`, default N=3, configurable). *(operator-confirmed)*
- **Q2 (resolved → decided):** alias uniqueness — **hard PK fix**
  `(vault_id, alias)` + lint cross-table check (closes L-4). *(operator-confirmed)*
- **Q3 (resolved → decided):** search alias expansion — **on by default**,
  `--no-expand-aliases` opt-out. *(operator-confirmed)*
- **Q3b (resolved → decided):** duplicate-merge — **IN SCOPE** as
  `wiki-merge <from> <into>` (R-4.7). *(operator-confirmed 2026-05-29 refinement)*
- **Q6 (minor, defer to Architecture):** `from`-page disposition on merge —
  **delete + alias-redirect** is the chosen mechanism (C-7). Open sub-point:
  should the deleted `from` page be hard-removed or moved to a `_merged/`
  tombstone dir for audit? Proposed default: hard-remove (git history is the
  audit trail; the vault is the working set). Non-blocking.
- **Q4 (minor, defer to Architecture):** alias-expansion breadth cap — what
  maximum number of OR terms per query before truncation (perf guard)?
  Proposed default: cap at the matched entity's alias set + name (no transitive
  expansion). Non-blocking.
- **Q5 (minor, defer to Architecture):** should `wiki-confirm --auto` also fire
  the `entity-confirmed` log event per promoted slug (log.md mirror), or a
  single batch event? Proposed: one `log_event` per promotion for backlink
  traceability. Non-blocking.

#### Decision Log (analysis-time, operator-confirmed)
- **D-005-1** Confirm-state + aliases are **Class A frontmatter + Class B
  mirror** — forced by ADR-002 §D8 (DB-only would be a rejected anti-pattern
  and would not survive `wiki-reindex --full`).
- **D-005-2** Auto-promote **included** (N=3 default, configurable, `--dry-run`).
- **D-005-3** entity_aliases PK → `(vault_id, alias)` (**hard fix**, closes L-4)
  + `wiki-lint` cross-table collision detection.
- **D-005-4** `wiki-search` alias expansion **on by default**; `--no-expand-aliases`.
- **D-005-5** (2026-05-29 refinement) Duplicate-**merge included** as
  `wiki-merge <from> <into>` (R-4.7): re-point refs (dedup on PK), absorb +
  register redirect aliases (`former_name`), delete the `from` Class A page,
  recompute mentions. Redirect mechanism = **alias table, not wikilink
  rewriting** (C-7); `resolve_entity` + `find_orphan_links` become alias-aware
  (R-4.5b/d) so merged-away slugs neither break resolution nor pollute lint.
  This realises the literal "Hermes/Hermes-Agent/Hermes-Framework duplication"
  R-4 was created to solve.
