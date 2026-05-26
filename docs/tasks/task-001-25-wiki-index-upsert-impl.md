# Task 001-25: `wiki-index-upsert` impl — R-07.1 / .2 / .3 / .4 / .5 [LOGIC IMPLEMENTATION]

## Use Case Connection
- UC-02 (manual ingest pipeline)
- UC-05 (bulk migration)
- UC-06, UC-07 (deferred to Phase 3b adapter, but R-07.4/.5 apply here too)

## Task Goal
Replace `wiki-index-upsert` CLI stub with the real impl: load config, instantiate the appropriate adapter (manual only in Phase 3a), call `fetch()`, normalize frontmatter via R-07.4 type-mapping table ([§6.1](../TASK.md)), normalize body via R-07.5 (Mermaid + SECTION strip), call `repo.upsert_page` + `repo.replace_refs` in a single transaction, return JSON with action outcome.

## Changes Description

### New Files
- `scripts/wiki_index/normalization.py`:
  - `_MERMAID_RE = re.compile(r"^```mermaid\s*\n.*?^```\s*$", re.DOTALL | re.MULTILINE)`.
  - `_SECTION_RE = re.compile(r"<!--\s*SECTION:[a-z0-9_-]+\s*-->")`.
  - `_MERMAID_OPEN_RE = re.compile(r"^```mermaid", re.MULTILINE)`.
  - `_MERMAID_CLOSE_RE = re.compile(r"^```\s*$", re.MULTILINE)`.
  - `class BodyNormalizationError(ValueError): pass`
  - `def normalize_body_for_fts(body: str) -> str:`
    - Sanity check: count `^```mermaid` openings vs matched closing fences via `_MERMAID_RE.findall`. If `count(_MERMAID_OPEN_RE.findall(body)) != count(_MERMAID_RE.findall(body))` → `raise BodyNormalizationError('unclosed mermaid fence')` (R-07.5 anti-tail-eat).
    - Apply `_MERMAID_RE.sub('', body)` (strip fenced blocks).
    - Apply `_SECTION_RE.sub('', body)` (strip section anchors only).
    - Return normalized body.
  - `TYPE_MAPPING: dict[str, tuple[str, str | None]] = {  # frontmatter_type → (db_type, marker_tag)
      'summary': ('summary', None),
      'summary-light': ('summary', 'summary-light'),
      'lesson-summary': ('summary', 'lesson-summary'),
      'meeting-summary': ('summary', 'meeting-summary'),
      'concept': ('concept', None),
      'query': ('query', None),
      'brief': ('brief', None),
      'research': ('research', None),
      'index': ('index', None),
      'log': ('log', None),
  }`
  - `class UnmappedTypeError(ValueError): pass`
  - `def normalize_frontmatter(fm: dict) -> tuple[dict, str]:` — returns `(updated_fm, db_type)`:
    - Lookup `fm.get('type')` in `TYPE_MAPPING`; if missing → `raise UnmappedTypeError(...)`.
    - `(db_type, marker) = TYPE_MAPPING[type]`.
    - Build new tags list: original tags + [marker if marker else nothing] + slugified concepts (R-07.4).
    - Concepts via `python-slugify.slugify(c, lowercase=True, separator='-', regex_pattern=r'[^a-z0-9\-]')`.
    - Deduplicate tags preserving order.
    - Return `(fm_with_updated_tags, db_type)`.

### Changes in Existing Files

#### File: `scripts/wiki_skills/wiki_index_upsert.py`

Replace stub `main()`:
- Parse args: `--vault <id>`, `--source <path>`, `--adapter {manual}` (default manual).
- `config = load_config(Path.cwd())`.
- `repo = make_repo(config)`.
- `adapter = ManualSourceAdapter()` (only manual in Phase 3a).
- `item = SourceItem(kind='manual', source_path=Path(args.source), vault_root=vault_root, vault_id=args.vault, extra={})`.
- `output = adapter.fetch(item)`.
- Apply normalization:
  - `updated_fm, db_type = normalize_frontmatter(output.frontmatter)` (R-07.4).
  - `normalized_body = normalize_body_for_fts(output.body_text)` (R-07.5).
- Build `Page` dataclass:
  - `title = updated_fm.get('title', output.page_slug)`.
  - `tldr = updated_fm.get('tldr')`.
  - `date = updated_fm.get('date')`.
  - `last_modified = datetime.fromtimestamp(output.output_path.stat().st_mtime).isoformat()`.
  - `body_excerpt = normalized_body[:1000]` (first 1KB).
  - `tags = updated_fm.get('tags', [])`.
- `BEGIN IMMEDIATE`:
  - `outcome = repo.upsert_page(page)`.
  - `repo.replace_refs(vault_id, slug, project, output.refs)`.
- Output JSON: `{"action": outcome, "vault_id": ..., "slug": ..., "project": ..., "refs_count": len(output.refs)}`.

### Component Integration
- This is the central pipeline; `wiki-init`, `wiki-reindex`, bulk migration all call it (or invoke via subprocess).
- R-07.4 + R-07.5 normalization is centralized here, not duplicated in adapters.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: Ingest `_sources/alpha.md` → DB row present, `outcome='inserted'`; re-ingest → `outcome='unchanged'`.
2. **TC-E2E-02**: Frontmatter `type: lesson-summary` → DB `pages.type='summary'`, tags contains `'lesson-summary'`.
3. **TC-E2E-03**: Body with `\`\`\`mermaid\nflowchart\n\`\`\`` → `body_excerpt` does not contain `flowchart` (R-07.5).
4. **TC-E2E-04**: Body with `<!-- SECTION:agent-metadata -->` → stripped from `body_excerpt`.
5. **TC-E2E-05**: Body with `<!-- TODO: revisit -->` (generic comment) → preserved (whitelist).
6. **TC-E2E-06** (N-2 fix — verbatim per TASK.md R-07.5 AC): Body containing the literal sequence
   ```
   ```mermaid
   flowchart LR
       A --> B
   ```
   (i.e., opening ` ```mermaid\n ` followed by content but NO closing ` ``` `, EOF before fence closes)
   MUST `raise BodyNormalizationError('unclosed mermaid fence')` at the normalization step BEFORE any DB write. Verification: `SELECT count(*) FROM pages WHERE slug='<test-slug>'` returns `0` (no partial state leak); `pages_fts MATCH 'flowchart'` returns no rows. Anti-tail-eat regression: ensure the regex does NOT silently consume body-to-EOF as one fenced block.
7. **TC-E2E-07**: `type: lecture-notes` (unmapped) → `UnmappedTypeError`, no DB mutation.

### Unit Tests
1. **TC-UNIT-01**: `slugify("OAuth 2.0") == "oauth-2-0"`.
2. **TC-UNIT-02**: Concepts merged with tags, dedup preserves order.
3. **TC-UNIT-03**: Frontmatter `concepts[]` preserved verbatim in `pages.frontmatter_json` AND slugified in `tags`.
4. **TC-UNIT-04**: SQL injection via title → DB intact.
5. **TC-UNIT-05**: `BEGIN IMMEDIATE` semantics: second concurrent writer blocks until first commits.

### Regression Tests
- task-001-16 upsert tests still pass.
- task-001-24 manual adapter tests still pass.
- E2E harness updated to real values.

## Acceptance Criteria
- [ ] R-07.1/.2/.3 implemented (parse + hash + tx upsert).
- [ ] R-07.4 type-mapping applied; UC-07 AC `pages.type='summary'` + tag `'lesson-summary'` verified.
- [ ] R-07.5 body normalization with pinned regex; unclosed-fence fails fast.
- [ ] `INSERT OR REPLACE` NOT used (M-4).
- [ ] All TC tests pass.

## Notes
- The frontmatter on disk is NEVER mutated — `type: lesson-summary` stays in the file even though DB stores `'summary'` (UC-07 AC + ADR-002 §D8 Class A canonical).
- Pinned regex (R-07.5): exactly `^```mermaid\s*\n.*?^```\s*$` with `DOTALL | MULTILINE` flags — verbatim.
- `python-slugify` known lossy normalization documented: `slugify("C++") == "c"` — logged at INFO, not error.
