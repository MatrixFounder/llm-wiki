# ADR-005: FTS-narrowed tag-membership filtering (reuse the existing index, don't add a speculative one)

- **Status**: Accepted (2026-06-16)
- **Decider**: kuptsov.sergey@gmail.com
- **Context issue**: [`docs/issues/r-x3-metadata-filter-unindexed-scan.md`](../issues/r-x3-metadata-filter-unindexed-scan.md) (`R-X3-MF-SCAN`, SEV-3, open 2026-06-01)
- **Supersedes**: nothing. **Closes the hot (membership) branch** of R-X3-MF-SCAN; explicitly **leaves the scalar/temporal branches as a scan** (this ADR records *why*).
- **Related**: [ADR-002](./ADR-002-multi-vault-bottleneck-corrections.md) §D8 (Class-A canonical / Class-B rebuildable cache), TASK 006 / **P-5** (the dropped speculative `idx_pages_vault_tags`), [ADR-003](./ADR-003-typed-knowledge-classes.md)/[ADR-004](./ADR-004-event-graph-typed-edges.md) (the typed classes/edges whose `--tag` retrieval this accelerates), TASK 013 (R-X3-META-FILTER, the scalar `--where`), TASK 033 (the `tags[]` membership branch), TASK 034 (`--as-of`). Decision: ARCHITECTURE Q-035-1/2.

## Context

`wiki-search` has a **metadata-only path** — a filter with no FTS query (`--tag decision`,
`--status open`, `--as-of 2026-04-15` used alone). It compiles to a scan of the
vault/type/project partition over `pages.frontmatter_json`: one JSON parse per surviving row
(`json_extract` for scalar `=`, `json_each` for `tags[]` membership, `valid_from`/`valid_to`
reads for `--as-of`), then a `USE TEMP B-TREE FOR ORDER BY` filesort with `LIMIT` applied only
after the sort. There is **no index** on `frontmatter_json` — a deliberate choice: TASK 006 /
**P-5** *removed* a speculative `idx_pages_vault_tags` JSON index because no query path used it
and it was dead write-weight on every page insert.

`R-X3-MF-SCAN` documented this with a hard rule — *"do NOT pre-add speculatively — add only
when a real field is measured hot"* — and a trigger — *"a single-vault partition exceeds ~1k
pages AND the metadata-only path is used routinely."*

### Empirical basis (measured 2026-06-16 on the real deployments)

| Branch | Hot field at scale? | 2493-page `personal` vault | Indexed today? |
|---|---|---|---|
| `--tag` / `tags=` **membership** | **YES — `tags` on 2493/2493 pages** | full scan + filesort, **1.50 ms/query** | No (`json_each`) — but **`pages_fts.tags` already exists & is maintained** |
| `--status`/`--severity`/`--where` **scalar** | No — `status` on 59, `severity` on 22 pages (413-page dev vault); ~absent on the 2493-page vault | sub-ms | No |
| `--as-of` **temporal** | No — `valid_from`/`valid_to` on **0** pages (optional overrides, by design); the successor-walk is already index-backed (`idx_refs_page` + PK) | sub-ms | partial |

Two facts drive the decision: (1) the membership branch's trigger **is met** (a 2493-page
partition, well past ~1k, with routine `--tag` typed-class retrieval since TASK 031/033) and
its field is hot on *every* page; (2) the scalar/temporal fields are **sparse-to-absent**, so
an index there would write dead weight on all 2493 pages to speed up the *coldest* paths —
exactly the P-5 mistake. The 1.50 ms cost is itself imperceptible, but the partition only
grows, so closing the one branch that scales with it — **at zero cost** — is warranted.

## Decision

### D1. Fix only the membership branch, and only by reusing `pages_fts.tags`

`pages_fts` is an internal-content FTS5 table whose `AFTER INSERT/UPDATE` triggers **already**
project `json_extract(frontmatter_json, '$.tags')` into an indexed `tags` column
(`sql/wiki-index-v2.sql` §11). That index already exists and is already maintained on every
write. The fix **consumes** it — it adds **no new index, no new column, no DDL, no
`user_version` bump, no extra write-weight**. This is categorically different from P-5: P-5
was adding a *speculative* index for a hypothetical query; here a *real, shipped, measured-hot*
query path (`--tag`) reuses an index that is *already paid for*.

### D2. "FTS narrows, `json_each` confirms" — exact result-set preserved

On the metadata-only path (`not has_match`), when a `where_fields` predicate is on field
**`tags`** AND the value yields ≥1 FTS token, `search_pages` switches the source from
`FROM pages p` to:

```sql
FROM pages_fts JOIN pages p ON pages_fts.rowid = p.id
WHERE pages_fts MATCH ?            -- param: 'tags : ' + fts_quote(value)
```

`tags` is a **fixed literal** column name (never user input); the value is wrapped as an FTS5
phrase with embedded `"` doubled (injection-safe). Every pre-existing AND-clause — vault, type,
project, exclude-types, all `where_fields` predicates **including the `tags` `json_each(...) =
?` confirm**, and any `--as-of` clause — is appended **unchanged**. Score (`0.0`), snippet
(`''`), and `ORDER BY p.project, p.slug, p.vault_id` are identical to the scan path.

**Why the result is byte-identical, not merely "close":** FTS5's `unicode61 remove_diacritics
2` tokenizer folds the stored `tags` text and the query phrase **the same way**, so the tokens
of any exact array element always appear in that element's FTS text → the FTS column-match set
is a **superset** of the exact `json_each` membership set. The retained `json_each` confirm
removes the FTS extras (e.g. over-matches from tokenization or substrings). Superset ∩ exact-
confirm = exact. Empirically validated: 40 real tags from the 2493-page vault (hyphenated
`AI-Agents`, numeric-leading, transliterated-Cyrillic) → **0 mismatches** vs the scan.

### D3. The load-bearing net is "FTS returns ∅ → re-run the scan" (not the alnum guard)

A value that FTS5 cannot tokenize (pure punctuation `+`/`—`/`::`, **or** a value that is
`isalnum`-true yet yields no unicode61 token — superscripts `²`, fractions `½`, circled
numerals `②`) breaks the superset guarantee: FTS returns ∅ and would *under-match* a page
carrying that literal tag (a silent lost result — worse than slow). Because the FTS phrase
match is **all-or-nothing per value** (the element's tokens are isolated by the JSON array
delimiters, so they tokenize identically in every page that contains the element), a value FTS
can't tokenize matches **no** page — which is indistinguishable, at the result level, from a
legitimately-empty tag search. So the correctness net is simply: **if the FTS-narrowed query
returns zero rows, re-run the plain scan.** This makes correctness **independent** of any
Python-side character predicate.

`any(c.isalnum() for c in value)` is therefore demoted to a **performance fast-path only** —
it lets the obvious tokenless cases skip straight to the scan (avoiding one empty FTS probe);
it is explicitly NOT relied upon for correctness (design-review M2). Belt-and-braces, an
`sqlite3.OperationalError` from a degenerate MATCH also falls back (phrase-quoting makes this
near-unreachable — `fts_quote` always emits a valid FTS string literal — so it is documented
defense, not the primary net). The equivalence test over an adversarial corpus (embedded
quotes/backslashes/interior-whitespace/symbols/ё-е/NFC-NFD, plus a `>limit` ORDER-boundary
slice) is the **gate** that turns this prose argument into a verified invariant (M1) — "40 real
tags, 0 mismatches" is supporting evidence, not the guarantee.

### D4. Leave the scalar and temporal branches as a scan — on purpose (P-5)

No expression index, generated column, or schema change for `--where`/`--status`/`--severity`
or `--as-of`'s `valid_from`/`valid_to`. The data shows those fields are sparse-to-absent;
indexing them would re-introduce P-5 dead-weight, and `--where` is a *general* primitive (any
field) so a per-field index doesn't even generalize. Other list fields (`concepts`,
`participants`, …) have no FTS projection, so the optimization is `tags`-specific. When/if a
*scalar* field is later measured hot, the issue's fix-option 1/2 (a targeted expression index
or generated column) applies — but not pre-emptively.

### D5. No layering inversion

The FTS phrase-quote is **inlined in the DAL** (`sqlite_repository.py`). The DAL
(`scripts/wiki_index`) must not import `scripts/wiki_skills._retrieval.fts_quote` — `wiki_skills`
depends on `wiki_index`, not the reverse. The one-line quote (`'"' + v.replace('"','""') + '"'`)
is trivially duplicated rather than inverting the dependency.

## Consequences

**Positive**
- The one metadata-only path that scales with the (only-growing) corpus stops doing a full
  partition scan, at **zero schema/write cost** — it reuses an index that already exists.
- Result sets are provably unchanged (superset + exact confirm), so no behavioural risk, no
  migration, no re-index required. Existing vaults benefit immediately.
- The P-5 discipline is honoured *and* documented: we reject the speculative scalar indexes
  with measured justification, so this isn't re-litigated.

**Negative / residual**
- Only the `tags` field benefits; scalar `--where` and `--as-of` still scan (acceptable —
  measured cold; the issue stays `open` with a narrowed, evidence-backed scope).
- A second, FTS-shaped query path now exists on the metadata branch (more code, more tests).
  Mitigated by the equivalence test matrix (result list before == after across tag shapes) and
  the fall-back guards.
- FTS tokenization semantics (folding/substring over-match) are *relied upon* to be a superset;
  the `json_each` confirm is the invariant that makes this safe and must never be dropped.

**Rejected alternatives**
- *Full consolidation (schema v7→v8 generated columns + indexes for status/severity/valid_*)* —
  contraindicated by the data (sparse/absent fields → P-5 dead-weight); a Class-B rebuild for
  the coldest paths; doesn't generalize to arbitrary `--where`.
- *FTS-only (drop the `json_each` confirm)* — changes results (tokenization over-matches,
  `SEV-2`→`sev`+`2`); unacceptable correctness regression.
- *A normalized tag table* — a real new write-path + schema for a 1.5 ms problem; over-built.
- *Record-only (keep deferred)* — defensible (1.5 ms is imperceptible) but leaves the only
  scaling branch un-optimized when a zero-cost reuse exists.
