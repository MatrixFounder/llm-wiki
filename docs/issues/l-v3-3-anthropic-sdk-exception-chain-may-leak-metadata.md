---
id: L-V3.3
type: known-issue
status: fixed
opened_at: 2026-05-28
category: logic
slug: l-v3-3-anthropic-sdk-exception-chain-may-leak-metadata
---

# Anthropic SDK exception-chain may leak metadata

- **Symptom**: `LLMUnavailableError(...) from e` preserved the SDK exception in `__cause__`. The operator-visible JSON envelope only emits `str(e)` of the wrapper (no leak today), but a future caller reaching for `__cause__.args` could surface `request_id` or partial headers from the SDK exception.
- **Root cause**: Python's default exception-chaining behavior; not specific to this code.
- **Affected components**: `scripts/wiki_skills/wiki_extract_concepts.py::extract_concepts_llm`.
- **Resolution**: Changed `from e` → `from None` to suppress the chain. The wrapper exception now has `__cause__ is None`; any future consumer attempting to walk `__cause__.args` finds nothing to leak. Regression test `test_extract_concepts_llm_suppresses_sdk_exception_chain` pins the behavior. CWE-209 closed.
- **STATUS (2026-05-28, v3.1)**: obsolete. The v3.1 deterministic refactor (Decision-17) deleted the in-skill LLM call entirely; `LLMUnavailableError`, `extract_concepts_llm`, and `from None` are all gone. The exception-chain question is moot. Mark closed-by-deletion.

---
