# Task 001-24: `wiki-source-manual` adapter impl [LOGIC IMPLEMENTATION]

## Use Case Connection
- UC-02 (manual ingest)
- UC-05 (bulk migration uses manual adapter)
- R-26 (path-traversal)
- R-15.3 (trust_level='high' for manual)

## Task Goal
Replace `ManualSourceAdapter.fetch` stub with real impl: validate source path inside vault (task-001-12), parse YAML frontmatter, compute SHA256 of body, extract wiki-links into `PageRef`s with `trust_level='high'`, derive slug + project, return populated `SourceOutput`.

## Changes Description

### New Files
- `scripts/wiki_source/parsing.py`:
  - `def parse_frontmatter(path: Path) -> tuple[dict, str]:` — uses `python-frontmatter`; raises `FrontmatterParseError` (extends `ValueError`) if malformed.
  - `def extract_wiki_links(body: str) -> list[tuple[str, int, str]]:` — finds `[[link]]` and `[[link|display]]` patterns; returns list of `(target_slug, line_number, source_quote)`. Quote = the matching line (truncated to 200 chars).
  - `def compute_file_hash(body: str | bytes) -> str:` — `hashlib.sha256(body.encode('utf-8') if str else body).hexdigest()`.
  - `def derive_slug(path: Path, vault_root: Path) -> tuple[str, str]:` — returns `(slug, project)`. Project is derived from path: if file is under `<vault>/Lessons/<course>/...` → project = `<course>` (kebab-slugified); else → `'_vault_'` sentinel.

### Changes in Existing Files

#### File: `scripts/wiki_source/manual.py`

**Class `ManualSourceAdapter`:**

**Method `fetch(self, item: SourceItem) -> SourceOutput`:**
- Replace stub body:
  1. `abs_source = validate_inside_vault(item.source_path, item.vault_root)` (R-26).
  2. `frontmatter_dict, body_text = parse_frontmatter(abs_source)`.
  3. Validate required frontmatter fields per `lint.required_frontmatter` config; raise `MissingRequiredFieldError` if missing.
  4. `file_hash = compute_file_hash(body_text)`.
  5. `slug, project = derive_slug(abs_source, item.vault_root)`.
  6. `links = extract_wiki_links(body_text)`.
  7. Build refs: for each `(target, line_no, quote)` → `PageRef(vault_id=item.vault_id, page_slug=slug, page_project=project, entity_slug=target, ref_type='wikilink', line_start=line_no, line_end=line_no, source_quote=quote, trust_level='high')`.
  8. Return `SourceOutput(page_slug=slug, project=project, output_path=abs_source, file_hash=file_hash, trust_level='high', frontmatter=frontmatter_dict, body_text=body_text, refs=refs)`.

**Method `dedup_state_key(self, item: SourceItem) -> str`:**
- Returns `sha256(str(abs_source))[:16]`.

### Component Integration
- Called from `wiki-index-upsert` (task-001-25) which then translates `SourceOutput` → `Page` + `repo.upsert_page` + `repo.replace_refs`.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: Ingest `minimal_vault/_sources/alpha.md` → returns `SourceOutput` with correct slug, hash, frontmatter, refs.
2. **TC-E2E-02**: Path traversal: `item.source_path = ../../etc/passwd` → `PathTraversalError` (translatable to `{error: "PATH_OUTSIDE_VAULT"}` JSON envelope at CLI layer).
3. **TC-E2E-03**: SQL injection in frontmatter: `title: "'; DROP TABLE pages--"` — parsing succeeds; downstream `upsert_page` (parameterized) keeps DB intact.

### Unit Tests
1. **TC-UNIT-01**: `extract_wiki_links` finds `[[foo]]` and `[[foo|bar]]` (display alias); returns target=`foo` in both cases.
2. **TC-UNIT-02**: `compute_file_hash` is deterministic.
3. **TC-UNIT-03**: `derive_slug` returns `('alpha', '_vault_')` for `<vault>/_sources/alpha.md`.
4. **TC-UNIT-04**: `derive_slug` returns `('lesson-01', 'zeroone-systems')` for `<vault>/Lessons/ZeroOne Systems/lesson-01.md`.
5. **TC-UNIT-05**: Missing required field → `MissingRequiredFieldError` with field name.
6. **TC-UNIT-06**: All refs have `trust_level='high'` (R-15.3 conformance).

### Regression Tests
- task-001-07 stub tests adjusted: now expect real output (not hardcoded).
- E2E harness updated.

## Acceptance Criteria
- [ ] All `fetch` steps per spec.
- [ ] Path-traversal enforced.
- [ ] `trust_level='high'` for all manual refs (R-15.3).
- [ ] All TC tests pass.
- [ ] `mypy --strict scripts/wiki_source/` passes.

## Notes
- Slug derivation rule MUST match `wiki-ingest` two-tier conventions (promotion-spec §5.1) — verify against `trade-agents/` real layout in task-001-30.
- `python-frontmatter` library used (declared in requirements.txt task-001-02).
- The `extract_wiki_links` regex: `re.compile(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]')` — captures target, ignores display alias.
