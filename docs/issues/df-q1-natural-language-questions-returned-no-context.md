---
id: DF-Q1
type: known-issue
status: fixed
opened_at: 2026-05-29
category: dogfood
slug: df-q1-natural-language-questions-returned-no-context
---

# natural-language questions returned NO_CONTEXT

- **Symptom**: `wiki-query prepare "How does the Hermes agent route messages?"`
  returned `NO_CONTEXT` (0 hits) on a vault that clearly contains the answer.
- **Root cause**: `prepare` passed the raw question straight to FTS5 `MATCH`,
  which is an **implicit AND over every token** (incl. stopwords/question-words
  "how"/"does"/"the") — so a real natural-language question almost never matches
  any document. The in-process tests passed only because they used queries where
  *all* tokens are present ("Hermes routing"); the `/vdd-multi` critics reviewed
  code logic, not a live NL question — so only real-content dogfooding surfaced
  it. This broke the **core RAG use case** (UC-16's own example question).
- **Affected**: `scripts/wiki_skills/wiki_query.py::_retrieve`.
- **Resolution**: added `_build_match_query` — tokenises the question (Unicode-
  aware, no hardcoded stopword list → multilingual/Cyrillic-safe) and builds an
  FTS5 **OR-of-terms** query (keyword retrieval, match-any, BM25-ranked); each
  token is alias-expanded through the entity table. Documents matching the
  salient content tokens rank highest; stopwords that match nothing contribute
  nothing. Regression: `tests/test_wiki_query_prepare.py::test_natural_language_question_retrieves`.
  Verified on real content: the question above retrieves the correct top hit by
  a wide BM25 margin in both dogfood vaults.
