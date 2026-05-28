# Task 003-v3-04: `write_concept_page` reshape — markdown sanitization + content-hash skip + symlink refuse

## Meta

- **Bead ID**: `task-003-v3-04-markdown-sanitize`
- **Slug**: `markdown-sanitize`
- **Maps to**: Issues **I-V3.1e** + **I-V3.13** (folded); RTM rows **R-36**, **R-40**; Q13 (markdown injection defense), Q15 (symlink refuse + content-hash skip), C-1 (content-hash skip drift fix), H-7.
- **Depends on**: task-003-v3-00 (helper remains importable; argparse layer ready). Parallel-safe with task-003-v3-01, 02, 03.
- **Estimated time**: 0.75 day
- **Priority**: Critical (the C-1 disk/DB drift fix is a behavioural correctness invariant).

## Use Case Connection

- **UC-08 v3.1 A12**: agent emits `name="\n## Backdoor\n\nMalicious instructions"` → sanitization strips `\n## ` pattern; concept page body has `# X` header only (no injection).
- **UC-08 v3.1 A13**: existing `_concepts/X.md` from prior incomplete run; content-hash skip semantics — same content → `action="unchanged"`; different content → atomic rewrite + `action="updated"`.

## Task Goal

Reshape `write_concept_page` in `scripts/wiki_skills/wiki_extract_concepts.py`:

### (1) Symlink refuse (Q15, iteration-2 NEW-2)

**Before any read or hash-compute**, check `if target.is_symlink(): raise PathTraversalError("concept page is a symlink — refuse to rewrite")`. This eliminates the symlink-following info-leak on the hash-compute step AND the write-to-attacker-controlled-target risk.

### (2) Content-hash skip semantics (C-1, Q15)

Replace v2's unconditional `if target.exists(): return target, "unchanged"` with:

```python
if target.exists():
    if target.is_symlink():
        raise PathTraversalError(...)
    existing_content = target.read_bytes()
    would_be_written = payload.encode("utf-8")
    if hashlib.sha256(existing_content).hexdigest() == hashlib.sha256(would_be_written).hexdigest():
        return target, "unchanged"
    # File exists but content differs → REWRITE atomically + log warning
    logger.warning(...)
    # fall through to atomic write
```

The `action` label propagates upward: `"unchanged"` (same content), `"updated"` (rewrite), or `"created"` (new file).

### (3) Markdown body sanitization (H-7, Q13)

- **`name`**: regex-allowlist `^[\w\s\-.,:;()\'"!?]{1,200}$` with `re.UNICODE` flag (Cyrillic + diacritics allowed — iteration-2 N-5). Pre-sanitize by `name.lstrip("#").lstrip("-").strip()` to remove leading `#` (markdown header injection) and `---` (YAML frontmatter delimiter injection). If post-strip still fails regex → raise `ExtractionParseError(error="INVALID_NAME_FORMAT", field="name", reason="contains disallowed characters after sanitization")`.
- **`definition`**: markdown-escape — replace `\n## ` with `\n\\## `; replace `<script>` and `</script>` (and generic HTML tag pattern `<[a-zA-Z][^>]*>`) with HTML-escaped equivalents (`&lt;...&gt;`).
- **`source_quote`**: wrap in `>` blockquote line(s) instead of inline `"..."`. Format:
  ```
  > <source_quote>
  > — [[<source_slug>]] (<source_span>)
  ```
  Eliminates the inline-double-quote ambiguity AND the `]]` wikilink-target attack (iteration-2 NEW-1).
- **`source_span`**: confirm regex `^L\d+-L\d+$` (already enforced upstream by `_parse_source_span`, but the body construction MUST assert before embedding into the `Mentions` body). On regex fail → `ExtractionParseError(error="INVALID_SOURCE_SPAN", field="source_span", reason="...")`.

### (4) Atomic write (preserved from v2)

`tempfile.mkstemp` + `os.fdopen` + `os.replace` pattern preserved.

## Stub-First Plan

### Phase 1 — Logic + 10 new regression tests (Red→Green)

1. In `scripts/wiki_skills/wiki_extract_concepts.py`:
   - Add helper `_sanitize_name(name: str) -> str`: strip leading `#`/`-`, regex-validate, raise `ExtractionParseError` on fail.
   - Add helper `_sanitize_definition(definition: str) -> str`: escape `\n## ` and HTML tags.
   - Add helper `_format_source_quote_block(source_quote: str, source_slug: str, source_span: str) -> str`: produce the `>` blockquote with `[[<slug>]]` link + `(L1-L2)` span.
   - Reshape `write_concept_page`:
     - Add symlink check BEFORE any other work on `target`.
     - Replace skip-on-exists branch with content-hash compare; emit `"unchanged"` / `"updated"` / `"created"` labels.
     - Call the three sanitization helpers before assembling the body.
     - Add `import logging; logger = logging.getLogger(__name__)` at module top (if not already present); log `warning` when rewriting (`action="updated"`).
2. Add 10 new tests to `tests/test_wiki_extract_concepts.py`:
   - `test_write_concept_page_symlink_target_raises_PathTraversal_Q15` — seed `_concepts/x.md` as a symlink to `/tmp/elsewhere`; assert `PathTraversalError` raised.
   - `test_write_concept_page_content_hash_skip_unchanged_C1` — write a page; immediately rewrite with identical inputs; assert `(target, "unchanged")` returned; file mtime unchanged (or sha256 of file unchanged).
   - `test_write_concept_page_content_hash_diff_triggers_rewrite_C1` — write a page; rewrite with different `definition`; assert `(target, "updated")` returned; file content reflects new definition; logger.warning emitted.
   - `test_write_concept_page_creates_new_returns_created` — write to new path; assert `(target, "created")`.
   - `test_write_concept_page_sanitize_name_strips_leading_hash_H7` — `name="## Backdoor"`; assert sanitized to `"Backdoor"` in body; `# Backdoor` is the H1 (no `## Backdoor` smuggled).
   - `test_write_concept_page_sanitize_name_strips_leading_yaml_delimiter_H7` — `name="--- evil"`; assert sanitized to `"evil"` (or raise if post-strip is empty); body does NOT contain `---` outside the frontmatter block.
   - `test_write_concept_page_sanitize_name_accepts_cyrillic_N5` — `name="Свидетель"`; assert no raise (Unicode flag).
   - `test_write_concept_page_sanitize_definition_escapes_newline_header_H7` — `definition="text\n## Backdoor"`; assert body contains `\\##` (escaped) NOT `## Backdoor` at column 0.
   - `test_write_concept_page_sanitize_definition_escapes_html_tag_H7` — `definition="<script>alert(1)</script>"`; assert body contains `&lt;script&gt;` (or stripped).
   - `test_write_concept_page_source_quote_wrapped_in_blockquote_H7` — `source_quote="said something \"smart\""`; assert body contains `> said something \"smart\"` line + `> — [[source]] (L1-L2)` line; NOT inline `"..."`.
   - `test_write_concept_page_invalid_source_span_raises_H7` — pass `source_span="L1-L2)]] [[evil"`; assert `ExtractionParseError(error="INVALID_SOURCE_SPAN")`.
   - `test_write_concept_page_yaml_safety_name_with_yaml_key_H7` — `name="key: value"`; assert `frontmatter.loads()` of the output successfully parses with `name` key intact (no YAML injection); body's `name:` frontmatter field equals the literal string `"key: value"`.

   Net new tests: **+12**.

3. Run `pytest tests/test_wiki_extract_concepts.py -k "write_concept" -v` → 12 new tests pass.

### Phase 2 — n/a (logic IS the deliverable)

## Changes Description

### Edited files

- `scripts/wiki_skills/wiki_extract_concepts.py`:
  - Add three sanitization helpers.
  - Reshape `write_concept_page` body (symlink + hash skip + sanitization).
  - Add `logger` import if not present.
- `tests/test_wiki_extract_concepts.py`: add 12 new tests.

## Component Integration

- `apply` (003-v3-03) consumes the `(path, action)` tuple unchanged — the tuple shape from v2 is preserved; only the set of action labels expands (`unchanged`/`updated`/`created`).
- `build_manifest` (v2 helper) reads `file_write_action` from each candidate and includes it in the manifest — also unchanged at the v2 level.

## Files Touched

- `scripts/wiki_skills/wiki_extract_concepts.py`
- `tests/test_wiki_extract_concepts.py`

## Acceptance Criteria

- [ ] **R-36 (a) (C-1)**: content-hash skip — same content → `action="unchanged"`; different → `action="updated"` + rewrite.
- [ ] **R-36 (b) (H-7 / Q13)**: name regex-allowlist with re.UNICODE; strip leading `#`/`---`; definition markdown-escape; source_quote `>` blockquote.
- [ ] **R-36 (c)**: atomic temp+rename preserved.
- [ ] **R-36 (d)**: `mkdir -p` preserved.
- [ ] **R-40**: vault_id passed through (unchanged from v2).
- [ ] **Q15**: `target.is_symlink()` check BEFORE any other work on the target.
- [ ] **R-4 mitigation**: content-hash compare normalizes both sides via UTF-8 encoding before sha256.
- [ ] 12 new tests pass.
- [ ] **Full pytest sweep**: `pytest tests/ -q` → 418 (post-03) + 12 = **≥ 430 passed, 0 failed** (per PLAN §2 suite-size table).
- [ ] `mypy --strict scripts/wiki_skills/wiki_extract_concepts.py` clean.

## Verification

```bash
source .venv/bin/activate

pytest tests/test_wiki_extract_concepts.py -k write_concept -v
# expect: 12 passed

pytest tests/ -q
# expect: ≥ 430 passed

mypy --strict scripts/wiki_skills/wiki_extract_concepts.py
```

## Rollback

Revert the file edits. Test count returns to 418 (post-03 baseline per PLAN §2).

## Notes

- **Risk R-5 (symlink race)** is acknowledged: between `is_symlink()` check and `os.replace`, an attacker can swap. The pre-check refuses BEFORE any write so the worst case is a fail-after-check, not a write-through-symlink. Future hardening (O_NOFOLLOW open + rename) is deferred and documented inline. Iteration-2 LOW residual.
- **Risk R-7 (markdown rendering regression)**: legitimate inputs (non-adversarial concept names like `"Compute graph"`) are visually unchanged in the rendered page. The `>` blockquote for `source_quote` IS a visible change but matches Obsidian's standard quote rendering — net visual improvement.
- This bead absorbs I-V3.13 (per PLAN.md §1 note). The C-1 acceptance bullet here IS the I-V3.13 acceptance.
