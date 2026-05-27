# Task 003-13: Integration test + fixture source page

## Meta

- **Bead ID**: `task-003-13-integration-test`
- **Slug**: `integration-test`
- **Maps to**: Issue **I-7.13**; RTM row **R-43**.
- **Depends on**: task-003-01..task-003-11 (every helper must have a real implementation).
- **Estimated time**: 0.5 day
- **Priority**: Critical (the E2E gate before regression sweep)

## Use Case Connection

- **UC-08 main scenario** (without `--ingest`) — full pipeline run on a fixture source page.
- **UC-08 main scenario** (with `--ingest`) — full pipeline including in-process indexer dispatch.
- **UC-09 Scenario A** (re-run on unchanged body → `unchanged`) — full pipeline idempotency assertion.

## Task Goal

Create end-to-end integration tests in `tests/test_wiki_extract_concepts_integration.py` exercising the entire pipeline against a fixture source page. The Anthropic LLM call is mocked with a deterministic JSON response so re-runs are byte-identical.

Three scenarios:
1. **First extraction** (no prior `source_state`): manifest contains expected concepts; concept pages written; entity rows + refs in DB.
2. **Re-extraction on unchanged body**: `action="unchanged"`, exit 0, NO LLM call (mock asserts `call_count == 0`).
3. **`--ingest` end-to-end**: combined `{"extraction":..., "index":...}` JSON; in-memory DB shows indexed rows.

## Stub-First Plan

**Phase 1 — Fixture + skipped tests**:

1. Create `tests/fixtures/source_extract/source-page.md`:
   ```markdown
   ---
   type: summary
   slug: trading-agent-demo
   vault_id: test-vault
   ---

   # Self-Improving Trading Agent on Hermes

   This page introduces three concepts: the Hermes API (a tool for accessing
   real-time market data), backtesting (a methodology for evaluating trading
   strategies on historical data), and reinforcement learning (a paradigm where
   agents learn from reward signals).

   The agent uses the Hermes API to fetch L1 order books, then runs backtesting
   on the past 30 days of data, refining its strategy via reinforcement
   learning.
   ```

2. Create `tests/fixtures/source_extract/llm-response.json`:
   ```json
   [
     {
       "slug": "hermes-api",
       "name": "Hermes API",
       "definition": "A tool for accessing real-time market data.",
       "source_quote": "the Hermes API (a tool for accessing real-time market data)",
       "source_span": "L7-L7",
       "entity_type": "tool"
     },
     {
       "slug": "backtesting",
       "name": "Backtesting",
       "definition": "A methodology for evaluating trading strategies on historical data.",
       "source_quote": "backtesting (a methodology for evaluating trading strategies on historical data)",
       "source_span": "L8-L8",
       "entity_type": "concept"
     },
     {
       "slug": "reinforcement-learning",
       "name": "Reinforcement Learning",
       "definition": "A paradigm where agents learn from reward signals.",
       "source_quote": "reinforcement learning (a paradigm where agents learn from reward signals)",
       "source_span": "L9-L10",
       "entity_type": "concept"
     }
   ]
   ```

3. Create `tests/test_wiki_extract_concepts_integration.py` with stubs:
   ```python
   import pytest

   @pytest.mark.skip(reason="phase-2")
   def test_integration_first_extraction(tmp_path, in_memory_repo, mock_anthropic):
       ...

   @pytest.mark.skip(reason="phase-2")
   def test_integration_reextraction_unchanged(tmp_path, in_memory_repo, mock_anthropic):
       ...

   @pytest.mark.skip(reason="phase-2")
   def test_integration_with_ingest_flag(tmp_path, in_memory_repo, mock_anthropic):
       ...
   ```

4. Run pytest → tests collect but skip.

**Phase 2 — Logic**:

1. Implement `mock_anthropic` fixture (in `tests/conftest.py` or inline in the integration file):
   ```python
   @pytest.fixture
   def mock_anthropic(monkeypatch):
       """Patch the Anthropic SDK to return the fixture JSON deterministically."""
       fixture_path = Path(__file__).parent / "fixtures" / "source_extract" / "llm-response.json"
       fixture_content = fixture_path.read_text()

       class _MockResponse:
           class _Content:
               def __init__(self, text):
                   self.text = text
           def __init__(self):
               self.content = [self._Content(fixture_content)]

       class _MockMessages:
           def __init__(self):
               self.call_count = 0
           def create(self, **kwargs):
               self.call_count += 1
               return _MockResponse()

       class _MockClient:
           def __init__(self, *args, **kwargs):
               self.messages = _MockMessages()

       monkeypatch.setattr("anthropic.Anthropic", _MockClient)
       return _MockClient
   ```

2. Implement `test_integration_first_extraction`:
   - Set up vault filesystem under `tmp_path` (copy fixture source page to `tmp_path/<source-slug>.md` and ensure the page is registered in `in_memory_repo`).
   - Call `main(["--vault","test-vault","--vault-root",str(tmp_path),"--source-page","trading-agent-demo","--db-path",":memory:"])`.
   - Assert exit 0.
   - Assert stdout JSON has `status="ok"`, `written` has 3 items.
   - Assert `<tmp_path>/_concepts/hermes-api.md` exists.
   - Assert `in_memory_repo` has 3 new entity rows with `is_candidate=1`.
   - Assert 3 `page_entity_refs` rows with `trust_level='medium'`, non-null `source_quote`, integer `line_start`/`line_end`.

3. Implement `test_integration_reextraction_unchanged`:
   - First, run `main(...)` once (same setup as test #1).
   - Reset the mock's `call_count` (`mock_anthropic.messages.create.call_count = 0`).
   - Run `main(...)` again — same args.
   - Assert exit 0.
   - Assert stdout JSON has `action="unchanged"`, `manifest is None`.
   - Assert `call_count == 0` (no LLM call on second run).

4. Implement `test_integration_with_ingest_flag`:
   - Same setup as test #1, but add `--ingest` flag.
   - Assert exit 0.
   - Assert stdout JSON has both `extraction` and `index` keys.
   - Assert `index["upserted"]` has at least 3 entries (one per concept page).
   - Assert `SELECT count(*) FROM pages WHERE vault_id='test-vault' AND type='concept'` in the in-memory DB returns 3.

5. Unskip; run pytest → Green.

## Changes Description

### New Files

- `tests/fixtures/source_extract/source-page.md` — fixture source page (3 concepts mentionable).
- `tests/fixtures/source_extract/llm-response.json` — fixed LLM response for deterministic re-runs.
- `tests/test_wiki_extract_concepts_integration.py` — 3 integration tests.

### Changes in Existing Files

- `tests/conftest.py` — add `mock_anthropic` fixture (or inline in the integration file if conftest changes are out of scope for this bead).

### Component Integration

- This is the most realistic test of the pipeline shy of a live LLM call. The smoke recipe in TASK.md §7 covers the live case operator-side.

## Files Touched (explicit list)

- `tests/fixtures/source_extract/source-page.md` (new)
- `tests/fixtures/source_extract/llm-response.json` (new)
- `tests/test_wiki_extract_concepts_integration.py` (new)
- `tests/conftest.py` (modified — add `mock_anthropic` fixture)

## Test Surface

- **New**: 3 integration tests:
  - `test_integration_first_extraction`
  - `test_integration_reextraction_unchanged`
  - `test_integration_with_ingest_flag`

## Acceptance Criteria

- [ ] **R-43(e)**: extraction on the fixture source page → manifest contains ≥ 1 concept with correct fields (verified by `test_integration_first_extraction`).
- [ ] **R-43(f)**: re-run on same fixture → `status=unchanged`, 0 LLM calls (verified by `test_integration_reextraction_unchanged`).
- [ ] `--ingest` end-to-end variant works (verified by `test_integration_with_ingest_flag`).
- [ ] No live LLM call — fixture file is the deterministic source of truth.
- [ ] All 3 integration tests pass.
- [ ] `mypy --strict` clean.
- [ ] Full sweep `pytest tests/ -q` still green.

## Verification

```bash
pytest tests/test_wiki_extract_concepts_integration.py -v
pytest tests/ -q

# Sanity: no live API call
grep -rn "anthropic.Anthropic()" tests/test_wiki_extract_concepts_integration.py
# expect: no real instantiation; only inside the mock fixture
```

## Rollback

`rm -rf tests/fixtures/source_extract/ tests/test_wiki_extract_concepts_integration.py` and revert the `tests/conftest.py` fixture addition. The per-bead unit tests still cover individual helpers; only the E2E gate is removed.

## Notes

- The fixture source page is intentionally short but realistic — 3 concepts is the minimum to exercise both `create` and (via re-run with a pre-seeded entity) `mention` paths.
- The mock fixture pattern is the same one used by `tests/test_wiki_enrich.py` for SDK mocking — reuse helpers if they exist; otherwise inline.
- **No live LLM call in CI** — the fixture is hermetic. Operator-driven live tests live in the smoke recipe (TASK.md §7 step 3a/4).
- Future bead (R-4 promotion CLI) will need its own integration test reusing this fixture.
- `tmp_path` is pytest's built-in tempdir fixture — auto-cleaned. The vault structure (`_concepts/`, source page) is set up per-test for isolation.
