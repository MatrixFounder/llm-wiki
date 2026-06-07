# Task 019.05: [STUB→LOGIC] D2a DAL `find_pages_citing_source` — `skill-tdd-strict`

## Use Case Connection
- UC-1 · E2.2 · AC-2, AC-9

## Task Goal
Add a read-only DAL method that answers "does any indexed page cite this raw file in its
`source:`/`sources:` frontmatter?" — the D2a provenance signal. Zero DDL.

## Changes Description
#### File: `scripts/wiki_index/repository.py` (ABC)
- Add `@abstractmethod find_pages_citing_source(self, vault_id: str, rel_path: str, fields: tuple[str, ...]) -> list[str]`
  — returns slugs of pages whose any `field` frontmatter equals `rel_path` (scalar) or
  contains it (list). Docstring: zero-DDL, read-only, reuses `frontmatter_json`.

#### File: `scripts/wiki_index/sqlite_repository.py`
- Stub: `raise NotImplementedError` (RED `test_find_pages_citing_source`).
- Impl: for each **allowlisted** field (`re.fullmatch(r'[a-z_]+', field)` — else skip/raise):
  build `path = '$.' + field`; predicate
  `CAST(json_extract(p.frontmatter_json, ?) AS TEXT) = ?`  **OR**
  `EXISTS (SELECT 1 FROM json_each(p.frontmatter_json, ?) WHERE value = ?)`
  (the `json_each` path arg is built from the allowlisted field; `rel_path` **bound** as a
  param both times). `WHERE p.vault_id = ?`. Returns `[row["slug"]]`.

## Test Cases
### Unit (RED-first)
1. **TC-05-1 (RED→GREEN):** a page with `source: _raw/x.txt` → `find_pages_citing_source(v, "_raw/x.txt", ("source","sources"))` returns its slug.
2. **TC-05-2 (list-valued, N:1):** page `sources: [a.txt, b.txt]` → query for `a.txt` and `b.txt` both hit.
3. **TC-05-3 (negative):** no citing page → `[]`.
4. **TC-05-4 (vault-scoped):** a citing page in another vault is NOT returned.
5. **TC-05-5 (injection-safe):** a crafted `rel_path` with quotes is matched literally (bound), not interpreted.

## Acceptance Criteria
- [ ] Zero DDL (`user_version` 5); read-only; field allowlist enforced.
- [ ] `mypy --strict` clean; regression green.

## Notes
Reuse the TASK 013 pattern: `sqlite_repository.py:513` (`json_extract(…, ?)`) +
`:1277` (`json_each(frontmatter_json, '$.aliases')`).
