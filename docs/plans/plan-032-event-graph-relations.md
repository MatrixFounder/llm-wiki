# Development Plan: TASK 032 — Event Graph (typed edges + graph-aware RAG, R-13 Phase 2)

> **Status**: PLANNED 2026-06-15.
> **Task ID**: 032 / Slug: `task-032-event-graph-relations`
> **Source spec**: [docs/TASK.md](./TASK.md) (RTM R-032-1..8; recon F1-F9; ACs; UCs).
> task-review: NEEDS-REVISION (1 BLOCKING C-1 + 5 MAJOR) → folded → re-review APPROVED.
> **Architecture spec**: [docs/adr/ADR-004-event-graph-typed-edges.md](./adr/ADR-004-event-graph-typed-edges.md)
> (D1-D7 + D-DAL) + [docs/ARCHITECTURE.md](./ARCHITECTURE.md) status block + §4 + **Q-032-1..6**.
> arch-review: NEEDS-REVISION (M1 orphan-target FK, M2 inverse-pass ordering) → folded → re-confirm APPROVED.
> **Methodology**: **Stub-First / red-green, green-throughout**; full suite + `mypy --strict` green at
> every bead boundary. **`tdd-strict`** on **032-00** (DDL/migration), **032-02** (inverse + delta —
> the trickiest correctness), **032-05** (question_hash determinism).
> **Branch**: `task-032-event-graph-relations` (no auto-commit — operator's standing rule).
> **Ship-separability**: **032-00..05 are the graph foundation; 032-05 (graph-RAG) is the separable
> final code bead** — if `question_hash` determinism converges slowly under `/vdd-multi` it splits to a
> [LIGHT] follow-up without blocking the rest (ADR-004 D5 / R-032-6).
> **Constraints (binding)**: **DDL this task** — additive `ref_type` CHECK values + `user_version` 5→6
> ONLY; no table/PK change; migration = **Class-B rebuild** (ADR-002 §D8; TASK 008 shape). **M-1
> intact** (forward edges ride the per-page `replace_refs`; inverses are a GLOBAL post-pass, NEVER a 2nd
> per-page write). **Karpathy byte-identity** (`_edge_refs`→`[]` without edge keys; golden anchor +
> `test_karpathy_config_matches_layout_constants` green bead-by-bead). **question_hash determinism (C1)**.
> No new deps; **no `import anthropic`**; injection-safe CLI (TASK 013); depth-capped + cycle-safe traversal.
> **Out-of-scope**: graph viz/export; cross-vault edges; edge weights; migrating the operator's live index.

---

## 0. Architectural Foundation (Reference)

| Surface | Change | Binding constraints |
|---|---|---|
| `sql/wiki-index-v2.sql` | `page_entity_refs.ref_type` CHECK (`:195-198`) += `implements`,`implemented-by`,`supersedes`,`superseded-by`,`causes`,`caused-by` (6); **reuse `related`** for `relates_to` (NO `relates-to`). `PRAGMA user_version` 5→**6** (`:461`). | additive only; no table/PK/index change; FK on `(vault_id,page_slug,page_project)` enforced (`:204`) — drives the orphan-target skip |
| `scripts/wiki_index/models.py` | `PageRef.ref_type` docstring → v6 set | mypy strict; no Literal change (it's `str`) |
| `scripts/wiki_index/reindex.py` | NEW `_edge_refs(updated_fm, …)` (key→ref_type map; list+scalar; target resolved via `slug_strategy`+alias like `_body_refs`); called **always-on** in `_frontmatter_refs` (`:197`, forward only → unioned into the page's single ref-set). NEW global **inverse pass** in `reindex_full` **between AM-3 (`:879`) and Step-3 `_recompute_mentions` (`:884`)**. NEW **scoped reconciliation** in `reindex_delta`. | forward = M-1 intact; inverse: join `entity_slug`→`pages.slug`, **skip orphan targets**, use **target's `page_project`**, `INSERT OR IGNORE` (idempotent/bidirectional), no self-loop; delta: upsert+delete-stale+orphan-delete (load-bearing), A5 residual |
| `scripts/wiki_index/repository.py` + `sqlite_repository.py` | `get_backlinks(…, ref_type=None)` kind-filter + NEW `refs_from(vault_id, page_slug, project, ref_type=None)` + NEW bounded `neighbors`/`chain` | ABC + impl in **lockstep** (mypy strict); bound params; depth-cap + visited-set cycle-safe; reuse `idx_refs_type/entity/page` |
| `scripts/wiki_skills/wiki_graph.py` (**NEW** 16th CLI) + symlinks (`.claude/`, `.agent/`) | `neighbors`/`chain`/`backlinks` × `--kind`/`--direction {in,out,both}`/`--depth` (capped); JSON envelope | read-only; injection-safe (slug/kind allowlist, bound params, **no value echo on error** — TASK 013); `INVALID_*` exit codes |
| `scripts/wiki_skills/wiki_query.py` | `prepare --follow-edges` (**default OFF**) + `--edge-depth` (cap 3); `_retrieve` edge-expansion after FTS; fold into `_question_hash` | deterministic: neighbors appended after FTS hits, sorted `(ref_type,project,slug)`, deduped, **exclude `type=query`/`type=verification`**; `apply` re-derivation round-trips (C1) |
| `templates/page-types/*.md` | edge-key comments: "INERT (Phase 1)" → "extracted as typed edges (Phase 2)" | keys already authored — doc-comment tweak only |
| `tests/` | `test_schema_v6.py` (+ populated-v5-rejection); edge-extraction; inverse full+delta; DAL; `wiki-graph`; graph-RAG; **flip** `test_cybos_reserved_edge_keys_inert`→`test_cybos_edges_extracted` (populated fixture) | Karpathy anchor green bead-by-bead |
| docs | ADR-004 (done); ROADMAP **R-13 Phase 2 → SHIPPED**; ARCHITECTURE status flip; manuals EN/RU + `docs/layouts/cybos.md` (authoring + querying edges) | consistency with as-built |

---

## 1. Bead breakdown

| Bead | Title | Owns ACs | Dep | tdd-strict |
|---|---|---|---|---|
| **032-00** | schema v5→v6 + models + `test_schema_v6` (incl. populated-v5 rejection) | AC-1.1/1.2/1.3 | — | ✓ |
| **032-01** | `_edge_refs` FORWARD extraction (key→ref_type, always-on in `_frontmatter_refs`) | AC-2.1/2.2 | 032-00 | |
| **032-02** | auto-inverse: global full pass + delta scoped reconciliation | AC-3.1/3.2/3.3/3.4 | 032-01 | ✓ |
| **032-03** | DAL typed-edge reads (`get_backlinks(kind=)`+`refs_from`+`neighbors`/`chain`) | AC-4.1 | 032-00 | |
| **032-04** | `wiki-graph` CLI (traversal reader) | AC-5.1 | 032-03 | |
| **032-05** | graph-aware RAG (`wiki-query --follow-edges`) — separable final | AC-6.1 | 032-03 | ✓ |
| **032-06** | activate edges (flip inert test) + docs (ROADMAP/ARCHITECTURE/manuals/cybos.md/templates) | AC-7.1, AC-8.* | 032-01..05 | |

---

## 2. Bead detail (Stub-First)

### 032-00 — schema v5→v6  (`tdd-strict`)
- `sql/wiki-index-v2.sql`: `ref_type` CHECK += the 6 values (comment `-- TASK 032 / R-032-1 (schema v6)`); `PRAGMA user_version = 6`. `models.py` `PageRef.ref_type` doc → v6 set.
- **Tests (RED first):** NEW `tests/test_schema_v6.py` mirroring `test_schema_v5.py` — `user_version==6`; each of the 6 new ref_types INSERTs (PRAGMA foreign_keys OFF, as v5 test does); a bogus ref_type raises `IntegrityError`; **AC-1.3 populated-v5 rejection**: build an INLINE table with the OLD 5-value CHECK, populate a row, attempt `INSERT … 'implements'` → `IntegrityError` (proves the rebuild is mandatory — the live schema file is now v6, so the old CHECK is reconstructed inline). Bump the version-pin asserts in `test_schema_v3/v4/v5.py` + `test_schema_smoke.py` to 6.
- **Verify:** full suite green (version pins updated); mypy strict; Karpathy anchor green.

### 032-01 — `_edge_refs` forward extraction
- `reindex.py`: NEW `_edge_refs(updated_fm, vault_id, page_slug, page_project, skipped)` — for each frontmatter key in the map (`implements`,`implemented_by`,`supersedes`,`superseded_by`,`causes`,`caused_by`,`relates_to`), list- or scalar-valued, resolve each target (`[[wikilink]]`/slug) via the layout `slug_strategy` + alias map (same path as `_body_refs`), emit `PageRef(ref_type=<mapped>)`. De-dup on `(entity_slug, ref_type)`; report-and-skip malformed (no value echo). Call it **always-on** in `_frontmatter_refs` (union into the returned list — NOT db_type-gated).
- **Tests (RED):** key→ref_type map pinned; a `decision` page with `implements: [[req-x]]` + `caused_by: inc-y` (scalar) yields the two forward refs with resolved slugs; a directly-authored `superseded_by:` yields `superseded-by`; **Karpathy anchor green** (no edge keys → `_edge_refs`→`[]`).
- **Verify:** mypy strict; anchor green.

### 032-02 — auto-inverse derivation  (`tdd-strict`)
- `reindex_full`: NEW global pass between AM-3 (`:879`) and Step-3 (`:884`): `SELECT page_slug, page_project, entity_slug, ref_type FROM page_entity_refs WHERE vault_id=? AND ref_type IN (<forward set>)`; for each, look up the **target** page (`JOIN pages ON entity_slug=slug` within vault) → **skip if no row** (orphan); `INSERT OR IGNORE` the inverse `(page_slug=target, page_project=target.project, entity_slug=source, ref_type=<inverse>)`; skip self-loops; `related` mirrors symmetrically.
- `reindex_delta`: scoped reconciliation per changed source A — recompute A's forward edges' inverses (same skip/target-project), `INSERT OR IGNORE`; delete inverses `WHERE entity_slug=A AND ref_type IN (<inverse set>)` no longer implied; run the delete on A's orphan-delete path too.
- **Tests (RED):** AC-3.1 (one direction → both rows; ordering proven by a `mentions_count` assertion that counts the inverse); AC-3.2 (2nd full = no-op; author-both → one row each); **AC-3.3 orphan-target** (orphan edge → forward kept, inverse NOT derived, no crash); AC-3.4 delta contract (edit a page's edges → inverse refreshed on target; source-delete → back-pointers gone; documented rename residual).
- **Verify:** full + delta idempotency; mypy strict; anchor green.

### 032-03 — DAL typed-edge reads
- `repository.py` ABC + `sqlite_repository.py`: `get_backlinks(vault_id, entity_slug, ref_type=None)` (additive kw, default all-kinds); NEW `refs_from(vault_id, page_slug, project, ref_type=None)`; NEW `neighbors(...)`/`chain(...)` (depth-capped, visited-set).
- **Tests (RED):** fixture graph (decision→task→incident); inbound/outbound by kind; chain resolves; cycle terminates; ABC+impl signatures agree (mypy strict).

### 032-04 — `wiki-graph` CLI
- NEW `scripts/wiki_skills/wiki_graph.py` (+ symlinks `.claude/skills`/`.agent/skills` if a SKILL.md ships, else just the CLI): subcommands `neighbors`/`chain`/`backlinks`; `--kind`/`--direction`/`--depth`/`--vault`/`--db-path`/`--vault-root`; JSON envelope; allowlist-validate slug + kind, bound params, no value echo on error; depth cap.
- **Tests (RED):** each subcommand over the fixture graph; bad kind/slug → clean error envelope (exit code); depth cap enforced.

### 032-05 — graph-aware RAG  (`tdd-strict`, separable)
- `wiki_query.py`: `prepare --follow-edges` (default OFF) + `--edge-depth` (cap 3); after FTS hits in `_retrieve`, expand along edges (`refs_from`/`get_backlinks`), exclude `query`/`verification`, append after hits sorted `(ref_type,project,slug)`, dedup; fold the expanded set into `_question_hash`; envelope `via_edge` provenance.
- **Tests (RED):** `--follow-edges` pulls the `causes` neighbors in stable order; `question_hash` deterministic across `prepare`/`apply` (no QUESTION_CHANGED); default-OFF leaves today's behavior byte-identical (existing wiki-query tests green).

### 032-06 — activate + docs
- Flip `test_cybos_reserved_edge_keys_inert` → `test_cybos_edges_extracted` (fixture POPULATES the edge keys; assert the typed refs + an inverse materialize). Tweak `templates/page-types/*` edge-key comments (INERT→active).
- Docs: ROADMAP **R-13 Phase 2 → SHIPPED**; ARCHITECTURE status flip; manuals EN/RU + `docs/layouts/cybos.md` (authoring edges + `wiki-graph` + `wiki-query --follow-edges`); README CLI count 15→16.

---

## 3. Carry-forwards (gate findings, already folded — verify at dev)

- **task-review C-1** (inverse can't ride per-page write) → 032-02 global pass; **§5/AC-3.1/3.2** corrected.
- **arch-review M1** (orphan-target FK `IntegrityError`) → 032-02 join+skip+target-project; **AC-3.3** test.
- **arch-review M2** (inverse-pass order vs `_recompute_mentions`) → 032-02 between AM-3 and Step-3; counts include edges.
- **arch-review m1** (delta orphan-delete load-bearing) → 032-02 delta delete-on-orphan.
- **Karpathy byte-identity** — assert green at EVERY bead (esp. 032-01/02).

## 4. Verify + gates (032-06 close)
Full `pytest` + `mypy --strict scripts/` green; Karpathy anchor green; `grep -r "import anthropic" scripts/` empty; **`reindex --full` Class-B rebuild** on a fixture v6 DB; **real-vault dogfood** (a cybos/dev-project vault: author a decision→task→incident chain, `wiki-graph chain`, `wiki-query --follow-edges "what did X cause?"`); then **`/vdd-multi`** (logic/security/performance) + **code-review**.
