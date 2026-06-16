# PLAN 035 — FTS-narrowed tag-membership search

Stub-First, green-throughout. For a **behaviour-preserving optimization** the RED→GREEN gate is
the **EXPLAIN-plan** test (RED: the metadata-only `--tag` query shows a full `pages` SCAN; GREEN
after the change: it shows the `pages_fts` join). The **equivalence/correctness** tests are
**green-throughout** — they encode the invariant "result list before == after" and must pass on
the scan *and* the FTS-narrowed path (that is the regression guarantee). Maps to `docs/TASK.md`
RTM R-1..R-8. Single DAL surface; zero DDL; mypy `--strict`.

## Bead order

### 035-00 — RED gate: EXPLAIN shows the FTS join (R-1)
- New `tests/test_search_pages_fts_membership.py::test_metadata_only_tag_uses_fts_join`:
  build a small `tmp_path` vault DB, run `EXPLAIN QUERY PLAN` for the DAL's metadata-only
  `--tag` query, assert it `SEARCH … pages_fts` (FTS virtual table) and does **not** full-`SCAN
  pages`. **RED** against current code.
- Acceptance: test exists and fails before 035-01.

### 035-01 — Implement the FTS-narrowed membership branch (R-1, R-3, R-6, GREEN)
- Factor the shared AND-clauses (vaults/types/exclude/project/`where_fields` loop incl. the
  tags `json_each` confirm/`as_of`) into a private `_filter_clauses(...) -> (sql, params)` so
  the scan and FTS-narrowed metadata queries are built from ONE clause source (no drift); the
  has_match path keeps using it too (behaviour-preserving — pinned by the full suite).
- `SQLiteRepository.search_pages`, metadata-only branch only (`not has_match`):
  - detect an FTS-narrowable predicate: first `where_fields` pair with `field == "tags"` AND
    `any(c.isalnum() for c in value)` → `fts_narrow_value` (`any(isalnum)` is a **perf
    fast-path only**, NOT a correctness gate — ADR-005 D3).
  - build `scan_sql`/`scan_params` (today's `FROM pages p WHERE 1=1` + clauses) ALWAYS.
  - if `fts_narrow_value`: build `fts_sql` = `FROM pages_fts JOIN pages p ON pages_fts.rowid =
    p.id WHERE pages_fts MATCH ?` + the SAME clauses; the MATCH param is the single bound
    string `"tags : " + _fts_phrase(value)` (SQL text carries only `MATCH ?` — never f-string
    `tags` in; M-arch-m1), `_fts_phrase` an **inlined** local (`'"' + v.replace('"','""') +
    '"'`, comment cross-refs `_retrieval.fts_quote`; no `wiki_skills` import — ADR-005 D5).
    Execute `fts_sql`; **if it returns zero rows OR raises `sqlite3.OperationalError`, re-run
    `scan_sql`** (the load-bearing safety net — ADR-005 D3).
  - else: execute `scan_sql`.
  - ORDER BY/LIMIT/score(`0.0`)/snippet(`''`) identical across both metadata queries.
- Private test seam: add a keyword-only `_use_fts_narrowing: bool = True` to the concrete
  `SQLiteRepository.search_pages` (NOT the ABC) so 035-02 can drive the REAL scan path
  (`=False`) vs the FTS path (default) with the same input — exercises production code both
  ways, no SQL duplication/drift (resolves plan-review 🟡-2).
- mypy strict; 035-00 turns GREEN.

### 035-02 — Equivalence + edge-case tests (R-2, R-3, R-4, green-throughout)
A helper that runs the same filter **twice** — once via the new path, once forcing the scan —
and asserts the returned `(vault, project, slug)` lists are **identical**:
- tag shapes: plain (`decision`), hyphenated (`AI-Agents`), numeric-leading (`9-stadii`),
  Cyrillic (`Идея`), mixed-case (`Decision` vs `decision`), a tag that is a **substring of
  another** tag (over-match guard), multi-word/space tag.
- a page where the value matches as a **scalar** `tags: decision` (not a list) — still works
  (json_each over a scalar yields the one row; FTS text is the scalar) (R-5 superset).
- absent field / no match → empty, both paths.
- **zero-token** value (`+`, `  `, `—`) with a fixture page literally tagged `+` → both paths
  return that page (the guard sends it to the scan) (R-3).
- composition: `--tag` + `--as-of`, `--tag` + `--types`, `--tag` + `--project`, `--tag` +
  a 2nd non-tags `--where` field — identical to the scan (R-4).
- injection: tag value `a" OR pages_fts MATCH "b`, `*`, `tags:foo`, `a OR b` → no crash, no
  extra rows (phrase-quoted + confirm) (R-6).

### 035-03 — Regression sweep (R-5, R-7)
- `pytest tests/` full green (esp. `test_wiki_search_metadata_filter`, `test_wiki_search_as_of`,
  `test_search_pages`, `test_wiki_search_stemming`, `test_wiki_search_alias_expansion`).
- `mypy --strict scripts/` clean (file count unchanged — no new module).
- Confirm a non-tags list field (`--where 'concepts=x'`) and the **FTS path** (a real query +
  `--tag`) are byte-unchanged (still scan / still the small-MATCH json_each).

### 035-04 — `/vdd-multi` + code-review + docs (R-8)
- Parallel `critic-logic` / `critic-security` / `critic-performance` over the diff; reproduce +
  fix any finding before acceptance; converge.
- `code-reviewer` over the change.
- Docs: `R-X3-MF-SCAN` issue → MEASURED + membership-branch **SHIPPED** (keep scalar/temporal
  open, evidence-backed); ADR-005 (done) + ADR cross-refs; CLAUDE.md narrative (TASK 035);
  `skills/wiki-search/SKILL.md` (note the membership path is FTS-indexed now — behaviour
  identical); manuals EN/RU one-liner; ARCHITECTURE Q-035 (done).

## Risk register
- **R: FTS under-matches → silent lost result.** Mitigated by the `any(isalnum)` guard (superset
  proof) + the `json_each` confirm + the equivalence test matrix. The confirm is load-bearing;
  a test pins that dropping it would change results.
- **R: injection via the tag value into the FTS expression.** Mitigated by phrase-quoting
  (`"`-doubled) + the confirm; injection test in 035-02.
- **R: layering inversion (DAL→wiki_skills).** Avoided by inlining the quote (ADR-005 D5);
  grep-guard in review.
- **R: ORDER/score/snippet drift.** The FTS branch reports the same `0.0`/`''`/`(project,slug,
  vault_id)` as the scan; equivalence test asserts list (not set) equality.
