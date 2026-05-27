# Task 003-06: `write_concept_page` — atomic `_concepts/<slug>.md` write

## Meta

- **Bead ID**: `task-003-06-concept-page-writer`
- **Slug**: `concept-page-writer`
- **Maps to**: Issue **I-7.6**; RTM rows **R-36**, **R-40**.
- **Depends on**: task-003-01 (helper stub exists), task-003-05 (classifier — feeds the `create_list`).
- **Estimated time**: 0.5 day
- **Priority**: Critical (file-write ownership of `_concepts/<slug>.md` per Decision-8)

## Use Case Connection

- **UC-08 step 8**: "For each `create` item: writes `_concepts/<slug>.md` atomically; calls `repo.upsert_entity(is_candidate=1)`." (This bead handles the file write; 003-07b handles the entity upsert.)
- **UC-08 alternative A4**: `_concepts/` directory does not exist → `mkdir -p`.

## Task Goal

Replace the `NotImplementedError` stub in `wiki_extract_concepts.py::write_concept_page(vault_root, candidate, source_slug, today) -> Path` with an atomic write of a new concept page:

1. Compute target path: `<vault_root>/_concepts/<candidate["slug"]>.md`.
2. Validate target is inside vault via `validate_inside_vault(target, vault_root)` (R-26 path guard).
3. If file already exists → return the path WITHOUT writing (skip-on-exists per R-36(e)). The manifest builder will mark it `action="unchanged"`.
4. Ensure `<vault_root>/_concepts/` directory exists (`mkdir -p`).
5. Build the frontmatter dict per R-36(b) and serialize via `python-frontmatter`:
   - `type: concept`
   - `vault_id: <vault_id>` (ADR-002 §D1.1 invariant)
   - `slug: <slug>`
   - `name: <name>`
   - `date: <today as ISO-8601>`
   - `tags: [concept, candidate]`
   - `is_candidate: true`
   - `source_page: <source_slug>`
   - `trust_level: medium`
6. Build the body: `# <name>\n\n<definition>\n\n## Mentions\n\n- [[<source_slug>]] — "<source_quote>" (lines L<start>-L<end>)`
7. Atomic write via tempfile + `os.replace` (repo-local primitive — Decision-12 default).
8. Return the path.

## Stub-First Plan

**Phase 1 — Red test on stub**:

1. Add to `tests/test_wiki_extract_concepts.py`:
   - `test_write_concept_page_returns_correct_path` (Phase 1):
     - With a `tmp_path` vault_root, call `write_concept_page(tmp_path, candidate={"slug":"foo","name":"Foo",...}, source_slug="src", today="2026-05-27")`.
     - On stub: `NotImplementedError`. After Phase 2: returns `tmp_path / "_concepts" / "foo.md"`.
   - `test_write_concept_page_writes_file_with_frontmatter` (Phase 2 only):
     - After Phase 2, the file exists; parse frontmatter; assert `is_candidate=True`, `vault_id="..."`, `type="concept"`.
   - `test_write_concept_page_skips_existing_file` (Phase 2 only):
     - Pre-create `_concepts/foo.md` with marker content.
     - Call `write_concept_page` with slug=foo.
     - Assert file content unchanged (marker still present).
   - `test_write_concept_page_creates_concepts_dir_if_missing` (Phase 2 only):
     - `vault_root` does NOT have `_concepts/` subdirectory.
     - Call `write_concept_page`.
     - Assert dir was created and file exists.
   - `test_write_concept_page_rejects_path_outside_vault` (Phase 2 only):
     - Construct a malicious candidate with `slug="../escape"`.
     - Assert raises an exception (path-traversal guard).
2. Run pytest — Red on Phase 1.

**Phase 2 — Logic**:

1. Implement using `python-frontmatter` and `os.replace`:
   ```python
   import os
   import tempfile
   from pathlib import Path
   import frontmatter
   from scripts.wiki_index.security import validate_inside_vault

   def write_concept_page(
       vault_root: Path,
       candidate: dict[str, Any],
       source_slug: str,
       today: str,
   ) -> Path:
       concepts_dir = vault_root / "_concepts"
       target = concepts_dir / f"{candidate['slug']}.md"
       validate_inside_vault(target, vault_root)
       if target.exists():
           return target  # skip-on-exists; manifest marks action="unchanged"
       concepts_dir.mkdir(parents=True, exist_ok=True)
       fm = {
           "type": "concept",
           "vault_id": candidate.get("vault_id"),  # caller must populate
           "slug": candidate["slug"],
           "name": candidate["name"],
           "date": today,
           "tags": ["concept", "candidate"],
           "is_candidate": True,
           "source_page": source_slug,
           "trust_level": "medium",
       }
       body = (
           f"# {candidate['name']}\n\n"
           f"{candidate['definition']}\n\n"
           f"## Mentions\n\n"
           f"- [[{source_slug}]] — \"{candidate['source_quote']}\" "
           f"({candidate['source_span']})\n"
       )
       post = frontmatter.Post(body, **fm)
       payload = frontmatter.dumps(post)
       # Atomic write (tempfile + os.replace)
       fd, tmp_path = tempfile.mkstemp(dir=str(concepts_dir), prefix=f".{candidate['slug']}.", suffix=".md.tmp")
       try:
           with os.fdopen(fd, "w", encoding="utf-8") as f:
               f.write(payload)
           os.replace(tmp_path, target)
       except Exception:
           if os.path.exists(tmp_path):
               os.unlink(tmp_path)
           raise
       return target
   ```
2. Caller (in `main()`) must pass `candidate["vault_id"]` — annotate `vault_id` onto each candidate dict before calling, e.g.:
   ```python
   for cand in create_list:
       cand["vault_id"] = args.vault
       write_concept_page(args.vault_root, cand, args.source_page, today)
   ```
3. Unskip Phase-2 tests; run pytest — Green.

## Changes Description

### New Files

- None.

### Changes in Existing Files

#### File: `scripts/wiki_skills/wiki_extract_concepts.py`

- Replace `write_concept_page` stub body with the atomic-write logic.
- Import: `frontmatter`, `tempfile`, `os`, `validate_inside_vault`.
- In `main()`, ensure `cand["vault_id"] = args.vault` is set before calling (or accept `vault_id` as an explicit parameter — pick one approach; the signature option keeps the function pure).

#### File: `tests/test_wiki_extract_concepts.py`

- Add 5 unit tests (one Phase-1 + 4 Phase-2).

### Component Integration

- Output (file path) consumed by:
  - 003-10 (manifest builder) — populates `manifest["written"][i]["path"]`.
  - 003-07b (entity upsert) — same `vault_id`, `slug`, etc. used.

## Files Touched (explicit list)

- `scripts/wiki_skills/wiki_extract_concepts.py` (modified — 1 stub replacement + imports)
- `tests/test_wiki_extract_concepts.py` (modified — add 5 tests)

## Test Surface

- **New**: 5 unit tests:
  - `test_write_concept_page_returns_correct_path`
  - `test_write_concept_page_writes_file_with_frontmatter`
  - `test_write_concept_page_skips_existing_file`
  - `test_write_concept_page_creates_concepts_dir_if_missing`
  - `test_write_concept_page_rejects_path_outside_vault`

## Acceptance Criteria

- [ ] **R-36(a)**: target path is `<vault_root>/_concepts/<slug>.md`.
- [ ] **R-36(b)**: frontmatter contains all 9 required fields.
- [ ] **R-36(c)**: body has `# <name>`, definition paragraph, `## Mentions`, provenance line referencing source slug + source_quote + line span.
- [ ] **R-36(d)**: write is atomic (tempfile + `os.replace`); failures clean up the tempfile.
- [ ] **R-36(e)**: existing file → skip; return path; no overwrite.
- [ ] **R-40(b)**: concept pages written under `vault_root` (verified by R-26 guard).
- [ ] **R-40(d)**: `validate_inside_vault` applied to every target path (verified by `test_write_concept_page_rejects_path_outside_vault`).
- [ ] All 5 unit tests pass.
- [ ] `mypy --strict` clean.
- [ ] Full sweep `pytest tests/ -q` still green.

## Verification

```bash
pytest tests/test_wiki_extract_concepts.py -v -k "write_concept_page"
pytest tests/ -q
mypy --strict scripts/wiki_skills/wiki_extract_concepts.py
```

## Rollback

Revert `write_concept_page` to `NotImplementedError`; remove tests. Downstream beads still fail-safe (manifest builder skips empty `written[]`).

## Notes

- **Atomic-write primitive choice** (planner-level micro-decision per PLAN.md §9.2 + TASK.md I-7.6 note): defaults to **repo-local primitive** (`tempfile.mkstemp` + `os.replace`). Alternative was `scripts.wiki_ingest._safety.atomic_write_text` (vendored), but importing vendored primitives increases the snapshot's coupling (Decision-12 minimisation).
- The `_concepts/<slug>.md` filename uses the candidate's `slug` literally — assumes the LLM returned a clean slug. If LLM returns `Foo Bar`, the slugification needs to happen in 003-04 (extraction), NOT here. Recommendation: add a `slug_strict` regex check in `_validate_extraction_schema` (003-04 Phase 2) — `^[a-z0-9-]+$`.
- The `## Mentions` body is intentionally minimal in R-3. Future bead (R-4 promotion / R-5 aliases) will enrich it.
- `python-frontmatter` requires Python 3.10+ (project uses 3.14, per CLAUDE.md).
