# TASK 035 — FTS-narrowed tag-membership search (R-X3-MF-SCAN, membership branch)

## 0. Meta
- **Task ID:** 035 · **Slug:** `task-035-fts-narrowed-tag-membership`
- **Mode:** VDD (full pipeline). Code task (`scripts/`, `tests/`, `docs/`), Stub-First,
  green-throughout, mypy `--strict`. **Zero DDL** (`user_version` stays **7**); **zero new
  deps**; **no `import anthropic`**; Karpathy byte-identity preserved. **Additive,
  behaviour-preserving** — the result set of every existing query is unchanged; the only
  delta is *how fast* the metadata-only `tags`-membership path reaches it.
- **Source:** operator request 2026-06-16 — *"проработай все issues в
  `docs/issues/r-x3-metadata-filter-unindexed-scan.md`"* + *"оформи по этому кейсу также
  отдельный ADR"*. After measuring the real deployments (below), operator chose **Option 1
  (targeted zero-DDL fix)** over the full v7→v8 consolidation (Option 2, contraindicated by
  the data) and over record-only (Option 3).
- **ADR:** **ADR-005** (`docs/adr/ADR-005-fts-narrowed-membership-filter.md`) — the design
  decision + the explicit rejection of speculative scalar expression-indexes (P-5).
- **Status:** ✅ **COMPLETE / merge-ready** 2026-06-16 (uncommitted per operator rule). Full
  VDD pipeline: task/arch/plan reviews **APPROVED** (findings folded in *pre*-implementation —
  the empty→scan safety net, the adversarial equivalence corpus, the private `_use_fts_narrowing`
  seam) + **`/vdd-multi` converged**: Security ✓ **bikeshedding-only** (bound-param +
  phrase-quote-doubling + the `json_each` confirm close all 5 injection vectors); Performance ✓
  — **2 LOW recorded in the issue** (empty-result +3-4 % double-probe; high-cardinality
  near-universal-tag crossover, bounded O(N), not the selective typed-class use case); Logic ✓ —
  iter-1 1 MED **empirically reproduced + fixed + re-verified clean-pass** (a non-`str`
  library-caller value crashed the FTS path where the scan didn't → `isinstance(value, str)` guard
  routes non-str to the scan, equivalence preserved); + **code-review MERGE**. **Live dogfood
  GREEN** (real 2493-page `personal` vault): 6 real tags incl. Cyrillic → 0 mismatches vs scan;
  EXPLAIN driver = `SCAN pages_fts VIRTUAL TABLE` + rowid PK join; **1.93 → 0.47 ms (~4.1×)**.
  **1504 pytest (+11 over the 1493 baseline; the 52-test `test_search_pages_fts_membership.py`),
  mypy strict (76 files).**
  **Operator-requested `/vdd-multi` re-verification + comprehensive dogfood (2026-06-16) —
  CONVERGED / all GREEN** (`docs/reviews/task-035-real-vault-dogfood.md`): the 3-critic re-run over
  the complete final changeset returned **Logic ✓ Security ✓ Performance ✓ all clean-pass** (the
  security scan's 7 "SQL f-string" CRITICALs adjudicated as the hardcoded-constant false-positive
  class — `page_cols`/`_REF_COLS`, never user input; the 1 HIGH + 1 MED are outside the diff,
  pre-existing). The comprehensive real-vault dogfood proved equivalence over **ALL 1135 distinct
  tags** (FTS == scan, list+order; + CLI `--tag` == an independent `json_each` ground truth), full
  CLI composition/edge-case/exit-code coverage (9/9), latency 4–28×, and no regression in the other
  search modes. No new findings; no fixes required.

## 1. Problem

`R-X3-MF-SCAN` (SEV-3, open since 2026-06-01) documents that the `wiki-search` metadata
filter on the **metadata-only path** (a filter with NO FTS query — `--tag X`, `--status X`,
`--as-of D` alone) compiles to a full scan of the vault/type/project partition: one
`json_extract`/`json_each` JSON-parse per surviving row, then a `USE TEMP B-TREE FOR ORDER
BY` filesort, `LIMIT` applied only after the sort. There is no index on
`pages.frontmatter_json` by deliberate design (TASK 006 / **P-5** removed a speculative
`idx_pages_vault_tags` JSON index as dead write-weight).

The issue has three branches (TASK 013 scalar `=`, TASK 033 `tags[]` membership, TASK 034
`--as-of` temporal). **Measurement decides which, if any, to fix** — the issue's own trigger
is *"a single-vault partition exceeds ~1k pages AND the metadata-only path is used
routinely"* and its P-5 rule is *"do NOT pre-add speculatively — add only when a real field
is measured hot."*

### Measured ground truth (2026-06-16, real deployments)

| Path | Hot field at scale? | 2493-page vault | Indexed today? |
|---|---|---|---|
| `--tag` / `tags=` **membership** | **YES — `tags` on all 2493/2493 pages** | scan + filesort, **1.50 ms/query** | No (json_each) — but **`pages_fts.tags` already exists** |
| `--status`/`--severity`/`--where` **scalar** | No — `status` 59, `severity` 22 (413-page dev vault); ~absent in the 2493-page vault | sub-ms | No |
| `--as-of` **temporal** | No — `valid_from`/`valid_to` on **0 pages** (optional overrides, by design); successor-walk already index-backed | sub-ms | partial |

- The 2493-page `personal` partition is **past the 1k trigger**, and `--tag` typed-class
  retrieval is used routinely (TASK 031/033) → the **membership branch trigger is MET**.
- The scalar/temporal branches are **NOT** hot: their fields are sparse-to-absent, so an
  expression index / generated column there would re-introduce exactly the P-5 dead-weight
  the schema removed once. **Out of scope** (recorded in the issue + ADR-005).

## 2. Scope — one delta

**Route ONLY the metadata-only `tags`-membership branch through the already-existing,
already-maintained `pages_fts.tags` FTS index**, as a candidate **narrower**, keeping the
exact `json_each(...) = ?` predicate as the **confirmer**. "FTS narrows, json_each confirms."

- **Where:** `SQLiteRepository.search_pages`
  ([sqlite_repository.py:548](../scripts/wiki_index/sqlite_repository.py#L548)),
  metadata-only branch (`not has_match`) only. The FTS branch (`has_match`, a real query
  present) is untouched — the issue already calls its `json_extract` on the small MATCH
  candidate set "a non-issue".
- **How:** when `not has_match` AND a `where_fields` predicate is on field `tags` AND the
  value yields ≥1 FTS token (guard: `any(c.isalnum() for c in value)`), build
  `FROM pages_fts JOIN pages p ON pages_fts.rowid = p.id WHERE pages_fts MATCH ?` with a
  **column-filtered phrase** param `'tags : ' + fts_quote(value)` (column name `tags` is a
  FIXED literal; value is FTS-phrase-quoted, doubling `"`). All existing AND-clauses (vault/
  type/project/exclude/`where`/`as_of`) — **including the `tags` json_each confirm** — append
  unchanged. ORDER BY / score / snippet identical to the scan path (`0.0`, `''`,
  `project,slug,vault_id`).
- **Correctness invariant (empirically validated):** for any value whose FTS phrase has ≥1
  token, the FTS column-match set is a **superset** of the exact json_each set (same tokenizer
  folds both sides; the element's tokens always appear adjacently in that element's FTS text —
  the match is all-or-nothing *per value*, not per page). The json_each confirm removes FTS
  extras → **result list byte-identical to today**.
  - *Evidence:* 40 real tags over the 2493-page vault (hyphenated `AI-Agents`,
    numeric-leading, transliterated-Cyrillic) → **0 mismatches**; 5 zero-token values
    (`+`,`-`,`  `,`—`,`::`) → FTS returns 0 without error, all `any-alnum=False`.
- **Safety net (design-review M2, the load-bearing correctness mechanism):** correctness does
  NOT rest on the `any(isalnum)` guard (which is only a *perf fast-path* — it can be true while
  unicode61 yields no token, e.g. `½`/`②`). The net is: **if the FTS-narrowed query returns
  ZERO rows, re-run the plain scan.** Because the match is all-or-nothing per value, a value
  that FTS can't tokenize → FTS ∅ → fall back → the scan returns the literal-tag pages → no
  silent under-match. Belt-and-braces: an `sqlite3.OperationalError` from a degenerate MATCH
  also falls back (phrase-quoting makes this near-unreachable; kept as defense).

### Out of scope (explicit, recorded in the issue + ADR-005)
- Scalar `--where`/`--status`/`--severity` expression index or generated column (P-5: fields
  sparse/absent; `--where` is general so a per-field column doesn't generalize).
- `--as-of` `valid_from`/`valid_to` generated columns (0 pages author them).
- Any schema change / `user_version` bump.
- The other-list-field membership (`concepts`, `participants`, …) — no FTS projection; the
  optimization is `tags`-specific (the only FTS-indexed list column). Their scan is unchanged.

## 3. Requirements Traceability Matrix

| # | Requirement | Acceptance | Verify |
|---|---|---|---|
| R-1 | Metadata-only `tags`-membership uses `pages_fts.tags` to narrow | EXPLAIN shows `pages_fts` as the DRIVING table joined by rowid (positive signature, not "absence of SCAN" — M-task-1); `tags` column-name is a hardcoded constant, a non-`tags` field never takes the FTS branch (M-task-2) | `test_*` + EXPLAIN assertion |
| R-2 | Result list byte-identical to the pre-035 scan, all tag shapes incl. adversarial | parametrized equality over an adversarial corpus (plain / hyphenated / numeric / Cyrillic NFC&NFD / mixed-case / substring-of-another / multi-word / embedded `"` / backslash / interior-whitespace / symbol) (M-arch-1) + `>limit` ORDER-BY-boundary slice (M-plan-4) | equivalence tests |
| R-3 | Zero-/no-token value falls back to scan; the FTS-empty safety net catches under-match | `--tag '+'`/`'½'` returns the same as the scan (literal-punctuation fixture); a deterministic over-match (`SEV-2` probed `sev`) proves the `json_each` confirm is load-bearing (M-plan-5) | edge tests |
| R-4 | Composition unchanged | `--tag` + `--as-of`, + `--types`, + `--project`, + a 2nd non-`tags` `--where`, + `--vault all` tie-break all identical to the scan | composition tests |
| R-5 | Scalar/list-non-tags/temporal branches untouched (regression) | existing `test_wiki_search_metadata_filter` / `_as_of` / `test_search_pages` green | full suite |
| R-6 | Injection-safe | tag value with FTS-special chars / quotes / `OR`/`*`/column-syntax cannot break out (phrase-quoted) or return wrong rows (confirm) | adversarial test |
| R-7 | Library-caller defense | DAL re-validates field; CLI dup-guard/echo posture unchanged | DAL test |
| R-8 | Docs current | issue → MEASURED + membership SHIPPED; ADR-005; ADR index; CLAUDE.md; manuals; SKILL.md | review |

## 4. Non-goals / invariants
- `mypy --strict scripts/` clean; full `pytest tests/` green; no new dep; no `import anthropic`.
- No layering inversion: the FTS phrase-quote is inlined in the DAL (the DAL must not import
  the `wiki_skills._retrieval.fts_quote`; `wiki_skills` depends on `wiki_index`, not vice-versa).
- Karpathy byte-identity preserved (a vault with no `tags` filter never touches the new path).
