# Task 007-05: `wiki-query apply` (write-side) — hash-check, grounding gate, Class A write

> **strict-TDD** (high-assurance — this is the anti-hallucination grounding gate).

## Use Case Connection
- UC-16: Ask → cited answer page (the write pass).
- UC-17: Idempotent re-run (content-hash skip; `--force`).
- UC-21: Citation-grounding violation refused at the boundary.

## Task Goal
Implement the `apply` write-side (RTM R-6.3 + R-6.7-apply): re-retrieve + recompute `question_hash` and compare to `--question-hash` (TOCTOU detection); validate the orchestrator's `--citations` payload against the retrieved hit set (the grounding gate); sanitise the answer; and atomically write `_queries/<query_slug>.md` as Class A. **DB indexing is 007-06** — this bead stops at the file write (Class-A-first, mirroring `wiki-merge`'s C-8 write-order).

## Changes Description

### Changes in Existing Files

#### File: `scripts/wiki_skills/_common.py`
- Lift `_sanitize_markdown_text` from `wiki_extract_concepts.py` into `_common.py` as `sanitize_markdown_text(text: str) -> str` (text-only allowlist: HTML-escape `&<>`, escape backticks/`[`/`]`/line-leading markdown actives). Update `wiki_extract_concepts.py` to import it (no behavior change — keep its existing regression tests green).

#### File: `scripts/wiki_skills/wiki_query.py`
- Flesh out the `apply` subparser flags: `--vault`, `--vault-root`, `--query-slug`, `--question` (verbatim), `--question-hash` (argparse `type=` validator: 64 lowercase hex → `INVALID_QUESTION_HASH` exit 2 for a library caller), `--answer-stdin`|`--answer-file` (mutex, bounded read; file form `validate_inside_vault` + `O_NOFOLLOW`), `--citations-stdin`|`--citations-file` (mutex, JSON list), `--orchestrator-id` (regex `^[a-z0-9._:@-]{1,64}$`, default `"orchestrator"`), `--force`, `--db-path`.
- `apply(args) -> int` (write-side portion):
  1. Re-run the same retrieval as `prepare` (reuse the `prepare` retrieval path) → recompute `question_hash`. If `≠ --question-hash` → `{"error":"QUESTION_CHANGED",…}` exit 2 (orchestrator re-runs; no auto-retry).
  2. Load + bound the answer (`ANSWER_TOO_LARGE` over cap) and parse `--citations` JSON (must be a list of `"project/slug"` strings → `INVALID_CITATIONS` exit 4 on shape).
  3. **Grounding gate:** build the retrieved key set `{f"{h['project']}/{h['slug']}"}`; any citation ∉ set → `{"error":"CITATION_NOT_RETRIEVED","field":"citations","reason":"a citation is not in the retrieved set"}` exit 4 (no value echoed — CWE-117/209). Comparison key = full `project/slug` tuple.
  4. `sanitize_markdown_text(answer)`; build frontmatter `{type: query, question, date: <today>, cites: [<project/slug>…], tags: [query]}`; body = sanitised answer (+ optional trailing `## Sources` `[[project/slug]]` list per Q-A8 — `cites:` frontmatter remains authoritative).
  5. Atomic write `<vault_root>/_queries/<query_slug>.md` via `atomic_write_text` + symlink-refuse (`O_NOFOLLOW`) + `validate_inside_vault`. Content-hash skip: if an existing file is byte-identical → `changed:false` (unless `--force`).
  6. Return a partial result for 007-06 to index (in-process this is one `apply` call; the bead seam is internal — write first, then index).

### Component Integration
Consumes the `prepare` retrieval path + `sanitize_markdown_text`. Produces the Class A `_queries/<slug>.md` file that 007-06 indexes. The `wiki-query-synthesis` skill (007-07) defines the answer/citations contract this validates against.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01 (happy write):** valid `--question-hash` (from a prior `prepare`) + answer + citations ⊆ hits → `_queries/<slug>.md` written with `type: query` + `cites:` + sanitised body; exit 0.
2. **TC-E2E-02 (QUESTION_CHANGED):** mutate the corpus between prepare and apply so the recomputed hash differs → `QUESTION_CHANGED` exit 2; no file written.
3. **TC-E2E-03 (grounding, UC-21):** a citation `"_vault_/not-retrieved"` not in the hit set → `CITATION_NOT_RETRIEVED` exit 4; no file written; envelope echoes no slug value.
4. **TC-E2E-04 (cross-project key):** hit set has `courseA/foo`; citation `"_vault_/foo"` (same slug, different project) → `CITATION_NOT_RETRIEVED` (project/slug key, not bare slug).
5. **TC-E2E-05 (idempotent / --force):** re-apply identical → `changed:false` (content-hash skip); `--force` rewrites.

### Unit Tests
1. **TC-UNIT-01:** `--question-hash` argparse validator rejects non-64-hex → `INVALID_QUESTION_HASH`.
2. **TC-UNIT-02:** `--citations` non-list / non-`project/slug` strings → `INVALID_CITATIONS`.
3. **TC-UNIT-03:** `sanitize_markdown_text` neutralises a hostile answer (`[[inject]]`, backticks, HTML, leading `#`/`---`) — shared with the existing `wiki_extract_concepts` sanitiser tests.

### Regression Tests
- `wiki_extract_concepts` sanitiser regression suite stays green after the `_common` lift.
- Symlink-refuse + `validate_inside_vault` behave as in `write_concept_page`.

## Acceptance Criteria
- [ ] `QUESTION_CHANGED` on hash mismatch; `CITATION_NOT_RETRIEVED` on un-grounded citation (project/slug key); `INVALID_CITATIONS`/`ANSWER_TOO_LARGE`/`INVALID_QUESTION_HASH` envelopes.
- [ ] `_queries/<slug>.md` written atomically (Class A) with the frontmatter contract; symlink-refuse + content-hash skip + `--force`.
- [ ] No offending content echoed in any envelope (CWE-117/209).
- [ ] Full `pytest` green; `mypy --strict scripts/` clean.

## Notes
Strict-TDD: write the grounding/hash-mismatch RED tests first. The file-write/index seam (this bead writes the file; 007-06 indexes it) follows the `wiki-merge` Class-A-first order so a DB failure leaves recoverable Class A state.
