# PLAN — TASK 013 `wiki-search-metadata-filter` (R-X3-META-FILTER)

Stub-First, green-throughout. 4 beads. **Zero DDL** (`user_version` stays 5).
mypy `--strict` + full pytest green at every bead.

## Design (locked — see TASK.md §5 + ARCHITECTURE.md §11a Q-013-a..d)

- **CLI surface (Q-013-a):** general repeatable `--where 'field=value'` + sugar
  `--status <v>` / `--severity <v>` (desugar into `where_fields`).
- **DAL (Q-013-b):** extend `search_pages(query, *, where_fields=None, …)`; `query`
  becomes optional. MATCH term present → FTS path + `AND CAST(json_extract(p.frontmatter_json, ?) AS TEXT) = ?`;
  query empty + ≥1 `where_fields` → **non-FTS** `SELECT … FROM pages p WHERE <preds>`.
  (`CAST … AS TEXT` → string-rep match, so numeric frontmatter values match too.)
- **Ordering (Q-013-c):** query-less path `ORDER BY p.project, p.slug, p.vault_id`.
- **Injection (Q-013-d):** field allowlist `[a-z][a-z0-9_]*` via `re.fullmatch` (CLI +
  DAL re-validate); json-path + value BOTH bound params; duplicate-field rejected;
  `INVALID_FILTER` (exit 2) never echoes value.

## Shared helper

`scripts/wiki_skills/_retrieval.py` (or `_common.py`) gains
`validate_filter_field(field: str) -> str` (allowlist regex; raises `ValueError`
on miss) + `parse_where(expr: str) -> tuple[str, str]` (split on first `=`,
validate field, return `(field, value)`; raise on no `=` / empty field). Used by
the CLI; the DAL re-validates field names defensively.

## Beads

| # | Bead | Files | Stub-First RED → GREEN | Acceptance (RTM) |
|---|------|-------|------------------------|------------------|
| **013-00** | No-regression golden anchor | `tests/test_wiki_search_metadata_filter.py` | Capture current `wiki-search "<q>"` output (no flag) on a fixture vault; assert byte-identical. Green on current code; tripwire for 01-03. | R-MF-9 |
| **013-01** | DAL: `where_fields` + query-optional + non-FTS path | `scripts/wiki_index/repository.py` (ABC sig), `scripts/wiki_index/sqlite_repository.py` (`search_pages`), shared `validate_filter_field` | **Stub**: add `where_fields` param returning `[]` for the predicate path + RED E2E. **Green**: parameterized `json_extract(?, ?) = ?` predicates, FTS/non-FTS branch, `(project,slug)` order, DAL-side field re-validation. **Unit**: AND semantics, NULL→non-match, `SEV-2` hyphen, query-less ordering, injection probe (field `a;b`→reject, value `' OR 1=1`→0 rows/clean). | R-MF-1,2,3,4,5,6,7,10 |
| **013-02** | CLI: `--where`/`--status`/`--severity`, query-optional, `INVALID_FILTER` | `scripts/wiki_skills/wiki_search.py`, shared `parse_where` | **Stub**: add args + RED E2E. **Green**: parse/validate `--where`, desugar sugar, `query` `nargs='?'`, refuse empty+empty (usage exit 2), skip alias-expand + FTS-fallback on query-less, wire to `search_pages`, `INVALID_FILTER` envelope (no value echo). **Unit**: sugar→where_fields, repeatable AND, malformed `--where` (no `=`), both-empty refusal, envelope-no-echo, compose with `--types`/`--project`. | R-MF-1,2,6,8, UC-1/2/3 |
| **013-03** | Close issue + re-render ledger + docs | `docs/issues/r-x3-fts-frontmatter-metadata-filter.md`, `docs/KNOWN_ISSUES.md` (rendered), `README.md`, `.AGENTS.md`×2, `docs/ROADMAP.md` | Flip issue `status: open→fixed` + Resolution note; `wiki-index-render --auto-indexes` re-renders the Class-B ledger; `wiki-lint` PW-Q drift guard green; document `--where`/`--status`/`--severity`; ROADMAP R-X3-META-FILTER → done. | R-MF-11, R-MF-9 (final regression) |

## Dependency / order

`013-00` (anchor, stays green throughout) → `013-01` (foundation) → `013-02`
(needs 01) → `013-03` (needs 01+02; closes + documents).

## Verification (end-to-end)

1. `pytest -q` fully green + `mypy --strict scripts/` clean at every bead.
2. **Live dogfood** (the acceptance the issue asked for):
   `wiki-search --status open --severity SEV-2 --vaults obsidian-llm-wiki --db-path .wiki/index.db`
   → returns the open SEV-2 issues (H-PERF-3, P-6, P-7, P-8, R-X1-REDOS-RT = 5).
   NOTE: do NOT add `--types known-issue` — `known-issue` is a frontmatter *tag*,
   not a `pages.type` (the dev-project layout maps it to `pages.type=research`);
   `--status`/`--severity` already scope to issues (only issues carry those fields).
3. **Hyphen**: `--severity SEV-2` works (equality, not FTS — no DF-1 crash).
4. **Injection**: `--where 'status;DROP=x'` → `INVALID_FILTER` exit 2, no value echo;
   `--where "status=' OR 1=1"` → 0 rows (parameterized), no error.
5. **No-regression**: 013-00 anchor + all existing `test_wiki_search*` byte-identical.
6. **Ledger**: issue flipped to `fixed`; re-render byte-identical modulo GENERATED-AT;
   `wiki-lint` no `auto-generated-drift`.

## Out of scope (TASK.md §C5)

- Global registration against the user DB (operational runbook step).
- R-X2c archive hook (deferred, cross-repo).
- Comparison operators / OR / `tag_from_frontmatter` FTS projection (YAGNI follow-ups).
- A `json_extract` generated-column index (zero-DDL constraint; gated by the
  same 1k-page trigger as P-1..P-4).
