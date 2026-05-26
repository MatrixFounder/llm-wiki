# Task 001-28: `wiki-search` CLI impl [LOGIC IMPLEMENTATION]

## Use Case Connection
- UC-03 (search across vault)
- R-10, R-29

## Task Goal
Replace `wiki-search` stub with the real impl: parse `--vaults`, `--types`, `--project`, `--limit`, `--format`. Call `repo.search_pages(...)` (task-001-17). Render results as Markdown (default) or JSON (`--format json`). Latency SLO < 50ms on 1K-page corpus.

## Changes Description

### New Files
None.

### Changes in Existing Files

#### File: `scripts/wiki_skills/wiki_search.py`

**Function `main()`:**
- Args:
  - `query` (positional, required).
  - `--vaults <comma-list>` (default `all` → None passed to `search_pages`).
  - `--types <comma-list>` (default None).
  - `--project <name>` (default None).
  - `--limit <int>` (default 20).
  - `--format {markdown,json}` (default markdown).
- `config = load_config()`; `repo = make_repo(config)`.
- Parse `--vaults all` → None; else split CSV.
- `hits = repo.search_pages(query, vaults=vaults_list, types=types_list, project=project, limit=limit)`.
- If `--format json` → print `json.dumps([{"vault_id": h.page.vault_id, "slug": h.page.slug, "project": h.page.project, "title": h.page.title, "bm25_score": h.bm25_score, "snippet": h.snippet}, ...])`.
- If markdown → render:
  ```markdown
  ## "<query>" — <N> mentions
  - [[<vault_id>:<project>/<slug>]] (BM25=<score>) — "<snippet>"
  ...
  ```
- Exit 0 on success; exit 1 on `ValidationError`.

### Component Integration
- Replaces stub; updates E2E harness with real assertion (e.g., search for "Sharpe" on multi-vault fixture returns hits from both vaults).

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: `wiki-search "shadow ai" --format json` on multi-vault fixture → JSON list with ≥ 1 hit; both vaults represented if R-29 active.
2. **TC-E2E-02**: `wiki-search "x" --vaults vault-alpha` → only `vault-alpha` hits.
3. **TC-E2E-03**: No matches → empty list (markdown: "No matches" line).
4. **TC-E2E-04**: Latency: search on 1K-page fixture < 50ms (SLO).

### Unit Tests
1. **TC-UNIT-01**: `--vaults all` translates to None in repo call.
2. **TC-UNIT-02**: Markdown output contains `<b>...</b>` snippet markers (passed from repo).
3. **TC-UNIT-03**: SQL injection in query: `'; DROP TABLE pages--` → DB intact.

### Regression Tests
- task-001-17 search_pages tests still pass.
- task-001-08 scaffold tests updated.

## Acceptance Criteria
- [ ] All CLI flags wired to repo.search_pages.
- [ ] Markdown + JSON formats both work.
- [ ] Cross-vault search verified.
- [ ] SLO met.
- [ ] All TC tests pass.

## Notes
- UC-03 AC requires explicit `<b>/</b>` markers — these come from the repo layer; CLI just passes through.
- `--vaults all` is sugar — None means "all" in the repo API.
- The Markdown format mirrors [TASK.md UC-03 step 6](../TASK.md).
