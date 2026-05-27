# Task 003-04: `extract_concepts_llm` — Anthropic LLM extraction call

## Meta

- **Bead ID**: `task-003-04-llm-extraction`
- **Slug**: `llm-extraction`
- **Maps to**: Issue **I-7.4**; RTM rows **R-33**, **R-34**.
- **Depends on**: task-003-01 (helper stub exists), task-003-03 (known-concepts input source).
- **Estimated time**: 1 day
- **Priority**: Critical (the synthesis core; downstream beads consume its output)

## Use Case Connection

- **UC-08 step 6**: "System: Calls Anthropic API (`claude-sonnet-4-6`, `temperature=0`): sends source body + known-concepts. Prompt instructs: 'identify 3-10 key concepts; use exact slug/name for known concepts; for novel concepts provide slug, name, 1-3 sentence definition, source_quote (10-50 words), source_span (Lstart-Lend), entity_type.'"
- **UC-08 step 7 (parse half)**: "System: Validates LLM response JSON" — the parse/validate path lives here; the classify half lives in 003-05.
- **UC-08 A2**: LLM returns malformed JSON → `EXTRACTION_PARSE_ERROR` exit 4.
- **UC-08 A3**: Anthropic API unavailable → `LLM_API_UNAVAILABLE` exit 3.

## Task Goal

Replace the `NotImplementedError` stub in `wiki_extract_concepts.py::extract_concepts_llm(source_body, known_entities, model, max_tokens) -> list[dict]` with:

1. Prompt construction: combine `source_body` + serialized `known_entities` JSON into a structured prompt that instructs Claude Sonnet 4.6 to return a JSON array of concepts.
2. Anthropic API call via the official SDK (`anthropic` Python package). `temperature=0`, `max_tokens` capped per R-33(c).
3. Response parsing: validate the JSON returned by the LLM against the expected schema (required fields: `slug`, `name`, `definition`, `source_quote`, `source_span`, `entity_type`).
4. On malformed JSON → raise `ExtractionParseError` (new exception, caught by `main` and mapped to exit 4).
5. On API error (network, auth, rate-limit) → raise `LLMAPIUnavailableError` (or wrap the SDK's exception) (caught by `main` → exit 3).

## Stub-First Plan

**Phase 1 — Red tests on stub**:

1. Confirm `extract_concepts_llm` is still a `NotImplementedError` stub.
2. Add to `tests/test_wiki_extract_concepts.py`:
   - `test_build_prompt_includes_known_concepts`:
     - Patch `anthropic.Anthropic` to return a fixed JSON response.
     - Call `extract_concepts_llm(source_body="...", known_entities=[{"slug":"alpha","name":"Alpha"}], model="claude-sonnet-4-6", max_tokens=4096)`.
     - On stub: assert `NotImplementedError`. After Phase 2: assert that the SDK call was made with a prompt string containing `"alpha"` and `"Alpha"`.
   - `test_extract_concepts_llm_parses_valid_json` (Phase 2 only — skip with `pytest.skip("phase-2")` in Phase 1):
     - Mock SDK to return valid JSON array of 2 concepts.
     - Assert returned list has 2 dicts with all required fields.
   - `test_extract_concepts_llm_raises_on_malformed_json` (Phase 2 only):
     - Mock SDK to return `"not json {"`.
     - Assert `ExtractionParseError` raised.
   - `test_extract_concepts_llm_raises_on_api_error` (Phase 2 only):
     - Mock SDK to raise `anthropic.APIConnectionError`.
     - Assert `LLMAPIUnavailableError` raised (or original re-raised — pick one and stick).
   - `test_extract_concepts_llm_uses_temperature_zero` (Phase 2 only):
     - Mock SDK; assert the `messages.create(...)` call kwargs contain `temperature=0`.
3. Run pytest — Phase 1: 1 test fails NotImplementedError (Red), 4 skip.

**Phase 2 — Logic**:

1. Add exception classes at the top of `wiki_extract_concepts.py`:
   ```python
   class ExtractionParseError(Exception):
       """Raised when LLM returns JSON that does not match the expected schema."""

   class LLMAPIUnavailableError(Exception):
       """Raised when the Anthropic API is unreachable or auth-failed."""
   ```
2. Implement the prompt builder as a private helper:
   ```python
   def _build_extraction_prompt(source_body: str, known_entities: list[dict[str, Any]]) -> str:
       known_block = json.dumps(known_entities, indent=2) if known_entities else "[]"
       return f"""You are a knowledge-graph entity extractor...
       Known concepts in this vault (use exact slug/name when concept is already known):
       {known_block}

       Source page body:
       {source_body}

       Return a JSON array. Each item: {{"slug": "...", "name": "...", "definition": "...",
       "source_quote": "...", "source_span": "L<start>-L<end>", "entity_type": "..."}}.
       Identify 3-10 key concepts. Reply with ONLY the JSON array, no prose."""
   ```
3. Implement the SDK call:
   ```python
   def extract_concepts_llm(
       source_body: str,
       known_entities: list[dict[str, Any]],
       model: str = "claude-sonnet-4-6",
       max_tokens: int = 4096,
   ) -> list[dict[str, Any]]:
       import anthropic
       client = anthropic.Anthropic()
       prompt = _build_extraction_prompt(source_body, known_entities)
       try:
           response = client.messages.create(
               model=model,
               temperature=0,
               max_tokens=max_tokens,
               messages=[{"role": "user", "content": prompt}],
           )
       except (anthropic.APIConnectionError, anthropic.AuthenticationError, anthropic.RateLimitError) as e:
           raise LLMAPIUnavailableError(str(e)) from e
       raw = response.content[0].text
       try:
           parsed = json.loads(raw)
       except json.JSONDecodeError as e:
           raise ExtractionParseError(f"LLM returned non-JSON: {raw[:500]}") from e
       if not isinstance(parsed, list):
           raise ExtractionParseError(f"LLM returned non-list: {raw[:500]}")
       _validate_extraction_schema(parsed)  # asserts required fields on each item
       return parsed
   ```
4. Implement `_validate_extraction_schema(items)`:
   - For each item, assert keys: `slug`, `name`, `definition`, `source_quote`, `source_span`, `entity_type`.
   - `source_span` must match regex `^L\d+-L\d+$` (Decision-10 format).
   - `entity_type` must be in the `entities.type` CHECK enum: `{person, concept, tool, dataset, source, event}`.
   - On violation, raise `ExtractionParseError` with the offending item dump.
5. Unskip the Phase-2 tests; run pytest — Green.
6. Wire into `main()`: catch `ExtractionParseError` → emit `{"error":"EXTRACTION_PARSE_ERROR",...}` → exit 4; catch `LLMAPIUnavailableError` → exit 3.

## Changes Description

### New Files

- None.

### Changes in Existing Files

#### File: `scripts/wiki_skills/wiki_extract_concepts.py`

- Add `ExtractionParseError` and `LLMAPIUnavailableError` exception classes near the top.
- Add `_build_extraction_prompt(source_body, known_entities) -> str` private helper.
- Add `_validate_extraction_schema(items: list[dict]) -> None` private helper.
- Replace `extract_concepts_llm` stub body with the SDK call + parse + validate logic.
- Update `main()` exit-code mapping for codes 3 and 4 (catch the two new exceptions).

#### File: `tests/test_wiki_extract_concepts.py`

- Add 5 unit tests (1 from Phase 1 unskipped + 4 new): prompt construction, valid JSON parse, malformed JSON error, API error, `temperature=0`.

### Component Integration

- Output (list of dicts) consumed by `classify_candidates` (003-05).
- Caller pattern (in `main()`):
  ```python
  known = load_known_entities(repo, args.vault)
  llm_results = extract_concepts_llm(source_body, known, args.model, args.max_tokens)
  create_list, mention_list = classify_candidates(llm_results, {e["slug"] for e in known})
  ```

## Files Touched (explicit list)

- `scripts/wiki_skills/wiki_extract_concepts.py` (modified — 1 stub replacement + 2 new helpers + 2 new exception classes + exit-code wiring)
- `tests/test_wiki_extract_concepts.py` (modified — add 5 tests)
- `requirements.txt` (verify `anthropic>=0.34.0` is already present; if not, add — TASK 003 was paused without this so it might need adding)

## Test Surface

- **New**: 5 unit tests in `tests/test_wiki_extract_concepts.py`:
  - `test_build_prompt_includes_known_concepts`
  - `test_extract_concepts_llm_parses_valid_json`
  - `test_extract_concepts_llm_raises_on_malformed_json`
  - `test_extract_concepts_llm_raises_on_api_error`
  - `test_extract_concepts_llm_uses_temperature_zero`

## Acceptance Criteria

- [ ] **R-33(a)**: model defaults to `claude-sonnet-4-6`; overridable via `--model`.
- [ ] **R-33(b)**: `temperature=0` on every API call (verified by `test_extract_concepts_llm_uses_temperature_zero`).
- [ ] **R-33(c)**: `max_tokens <= 4096` enforced.
- [ ] **R-33(d)**: prompt instructs LLM to return JSON array with required fields; format verified by `test_build_prompt_includes_known_concepts`.
- [ ] **R-33(e)**: malformed JSON → `EXTRACTION_PARSE_ERROR` with raw response in error details (verified by `test_extract_concepts_llm_raises_on_malformed_json`).
- [ ] **R-34(a)**: known-concepts JSON embedded in prompt with "use exact slug/name" instruction.
- [ ] **R-42(d)**: `main()` maps `ExtractionParseError` → exit 4.
- [ ] **R-42(c)**: `main()` maps `LLMAPIUnavailableError` → exit 3.
- [ ] All 5 unit tests pass.
- [ ] `mypy --strict` clean.
- [ ] Full sweep `pytest tests/ -q` still green.

## Verification

```bash
pytest tests/test_wiki_extract_concepts.py -v -k "extract_concepts_llm or build_prompt"
pytest tests/ -q
mypy --strict scripts/wiki_skills/wiki_extract_concepts.py
```

## Rollback

Revert `extract_concepts_llm` to `NotImplementedError`, remove the new exception classes and helpers, remove the 5 new tests. Downstream beads (003-05+) will fail until restored.

## Notes

- **Tests must NEVER make a live API call** — Anthropic SDK is mocked via `unittest.mock.patch("anthropic.Anthropic")` in every test. Live LLM calls happen only in the smoke recipe (TASK.md §7 step 3a/4) and the operator-driven integration variant in 003-13.
- The prompt is intentionally simple — improvement is a future bead. R-3 ships a working prompt; quality refinement is operator-driven on real vaults.
- `source_span` validation regex is `^L\d+-L\d+$` per Decision-10. The parsing of these strings into integer pairs lives in 003-08 (`upsert_entity_refs`).
- Recommendation: catch `anthropic.APIConnectionError`, `AuthenticationError`, `RateLimitError` explicitly and wrap into `LLMAPIUnavailableError`. Other anthropic errors (e.g., `APIStatusError` with non-retryable 5xx) propagate as-is — operator sees the raw SDK message.
