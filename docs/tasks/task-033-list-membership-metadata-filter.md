# TASK 033 — list-membership metadata filter (`wiki-search` `--where` over list-valued frontmatter + `--tag` sugar)

## 0. Meta
- **Task ID:** 033 · **Slug:** `task-033-list-membership-metadata-filter`
- **Mode:** VDD (full pipeline). Code task (`scripts/`, `tests/`, `docs/`), Stub-First,
  green-throughout, mypy `--strict`. **Zero DDL** (`user_version` stays **6**); no new deps;
  additive + backward-compatible.
- **Source:** operator request 2026-06-15 — close the ROADMAP **R-13 open residual**: a
  list-membership `--where` predicate so per-typed-class filtering (`tag=decision`) is one
  clean command. Logical continuation of TASK 031 (typed knowledge classes) + 032 (event graph).
- **Status:** ✅ **COMPLETE / merge-ready** 2026-06-16 (uncommitted per operator rule).
  Full VDD pipeline green: task-review APPROVED · arch-review APPROVED (binding B-1 +
  M-1/M-3 folded) · plan-review APPROVED · **`/vdd-multi` converged iter-1 (Logic ✓
  Security ✓ Performance ✓ — all clean-pass)** · code-review verified inline (every
  AC↔test mapped). **R-1** `search_pages` predicate generalized to
  `CAST(json_extract …)=? OR EXISTS(json_each … =?)` (the proven `find_pages_citing_source`
  shape, 4-param `(path,value,path,value)` bind) · **R-2** `--tag <v>` sugar · **R-3**
  injection posture preserved (allowlist + twice-bound + no value echo + dup-guard) ·
  **R-4** docs/manuals/ROADMAP-R-13-closed/SKILL v1.5+eval. **Zero DDL** (`user_version` 6),
  backward-compatible. **1393 pytest (+10), mypy --strict clean (76 files).** Real-vault
  dogfood GREEN (obsidian-personal PARA vault, 2493 pages, no reindex — query-time change):
  7 typed classes → exact pages; 5 real tags incl. Cyrillic `Стратоплан`=201/`Переговоры`=58
  match the membership predicate count EXACTLY; `--where 'tags=X'` ≡ `--tag X`; FTS+tag AND;
  scalar back-compat (`date=`); genuine member-match (not whole-list); dup-guard + no-echo.

## 1. Problem

`wiki-search` gained frontmatter metadata filtering in TASK 013 (`--where 'field=value'`,
`--status`, `--severity`). The predicate is **scalar-equality only**:

```sql
... AND CAST(json_extract(p.frontmatter_json, ?) AS TEXT) = ?     -- scripts/wiki_index/sqlite_repository.py:628
```

For a **list-valued** field — `tags: [eg-demo, decision]` — `json_extract($.tags)` returns
the JSON array text `["eg-demo","decision"]`, which never equals a single member, so
`--where 'tags=decision'` always returns nothing. The TASK 031 typed classes route each note's
class to a **tag** (`decision`→tag `decision`, `risk`→`risk`, …) living inside `tags[]`, so
"show me every decision/risk/incident" cannot be done with one clean filter — the operator must
fall back to `--types <db_type>` (a coarse bucket: decision+risk+incident+hypothesis all collapse
to `research`) plus FTS on the tag word (imprecise; FTS-tokenizer-dependent). The `cybos.yaml`
comment and `docs/layouts/cybos.md` both explicitly note this gap.

**Key fact (no new mechanism needed):** the codebase already implements the exact
scalar-OR-list-membership match elsewhere — `SQLiteRepository.find_pages_citing_source`
(sqlite_repository.py:1360) does
`CAST(json_extract(fm, ?) AS TEXT) = ? OR EXISTS (SELECT 1 FROM json_each(fm, ?) WHERE value = ?)`.
TASK 033 brings that proven pattern to the `search_pages` `--where` predicate.

## 2. Requirements Traceability Matrix (RTM)

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **R-1** | `search_pages` `--where` predicate matches **list membership** as well as scalar equality | ✅ | (a) extend the per-field predicate to `scalar = ? OR EXISTS(json_each membership = ?)`; (b) mirror the proven `find_pages_citing_source` SQL shape; (c) value bound (one bound param reused for both branches or two bound copies); (d) backward-compatible — scalar fields (`status`/`severity`) unchanged in result set |
| **R-2** | `--tag <value>` CLI convenience (the "one clean command") | ✅ | (a) argparse flag mirroring `--status`/`--severity`; (b) maps to `where_fields += ("tags", value)`; (c) participates in the dup-field guard; (d) documented as sugar for `--where 'tags=<value>'` |
| **R-3** | Injection-safety + correctness invariants preserved | ✅ | (a) field-name allowlist (`validate_filter_field`) still gates `tags` and any field; (b) value never echoed on error (CWE-209/117); (c) one-predicate-per-field dup guard still fires for `--tag`/`--where tags=`; (d) `json_each` over a scalar/absent field is safe (no error, no false match) |
| **R-4** | Docs + ROADMAP currency | ☐ | (a) `skills/wiki-search/SKILL.md` (+ version bump, evals); (b) manuals EN/RU `wiki-search` section; (c) `docs/layouts/cybos.md` + `cybos.yaml` comment flip ("now filterable via `--where tags=`/`--tag`"); (d) ROADMAP R-13 residual → closed; (e) ARCHITECTURE Q-033 note |

## 3. Use Cases

- **UC-1 (main):** `wiki-search --tag decision --vaults personal` → every page with `decision`
  ∈ `tags[]` (the typed-class listing). Optionally `wiki-search "broker" --tag risk` to combine
  FTS + class.
- **UC-2:** `wiki-search --where 'tags=incident' --vaults v` → identical to `--tag incident`
  (the general primitive; works for ANY list field, e.g. `--where 'aliases=Hermes'`).
- **UC-3 (back-compat):** `wiki-search --status open` / `--where 'severity=SEV-2'` on scalar
  fields → unchanged behaviour and result set.
- **UC-4 (alt — pure listing):** `wiki-search --tag decision` with no FTS query → non-FTS
  metadata listing of all decisions (the existing query-optional path).

## 4. Acceptance Criteria

- **AC-1:** `--where 'tags=decision'` returns exactly the pages whose `tags[]` contains
  `decision`; a page tagged only `risk` is excluded.
- **AC-2:** `--tag decision` ≡ `--where 'tags=decision'` (same hits).
- **AC-3:** scalar `--where 'status=open'` / `--status open` / `--severity SEV-2` return the
  same pages as before TASK 033 (no regression; proven by the existing TASK 013 tests staying green).
- **AC-4:** `--tag x --where 'tags=y'` (or `--tag x --tag y` if argparse allowed) → the
  one-predicate-per-field guard fires → `INVALID_FILTER` exit 2, value not echoed.
- **AC-5:** an invalid field name still raises `INVALID_FILTER` (allowlist), value never echoed.
- **AC-6:** `--tag` combines with `query` + `--types` + `--vaults` (AND-ed) and with the
  pure-listing path (no query).
- **AC-7:** `mypy --strict scripts/` clean; full `pytest` green (existing + new).
- **AC-8:** Karpathy/global behaviour unaffected; zero DDL (`user_version` 6).

## 5. Design decisions (resolved — not blocking)

- **D1 — `--where` uses the REAL field name (`tags`), not a magic singular `tag`.** The general
  primitive is `--where 'tags=decision'` (honest field semantics; works for any list field). A
  separate `--tag` *sugar* flag (mirroring `--status`/`--severity`) gives the clean one-word UX
  and maps to field `tags`. We do NOT special-case a `tag→tags` field rename inside `--where`
  (surprising; collides with a real `tag` field if one ever exists).
- **D2 — generalize the predicate for ALL fields, not just `tags`.** Adding `OR EXISTS(json_each…)`
  to every `--where` field is backward-compatible: for a scalar field, `json_each` over the scalar
  yields one row equal to the scalar (same truth as the `=` branch); for an absent field both
  branches are false. So no field needs special handling and any future list field (`aliases`,
  `related`) is filterable for free. (Matches the proven `find_pages_citing_source` pattern.)
- **D3 — perf:** the predicate stays an unindexed `json_extract`/`json_each` scan — the **same
  class** as the documented open residual **R-X3-MF-SCAN** (SEV-3). No new index; note it, don't
  regress it. The `json_each` EXISTS-subquery is per-row but bounded by the (already small)
  candidate set the FTS/type filters narrow to.

## 6. Open Questions

- None blocking. (D1/D2/D3 above resolve the only design forks.)

## 7. Out of scope

- A list-membership operator *syntax* beyond plain `field=value` (e.g. `field~=`, `field IN`).
- Indexing `tags[]` for the filter (the R-X3-MF-SCAN perf residual stays as-is).
- Changing `--types` semantics or the db_type bucket mapping.
