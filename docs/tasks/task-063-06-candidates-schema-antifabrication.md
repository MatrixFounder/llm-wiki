# TASK 063-06 — candidates schema + **anti-fabrication as a MECHANISM**

**Phase**: 3 (apply validation) · **RTM**: R-063-7, R-063-11 · **Type**: code · **Effort**: 3h
**Depends on**: 063-04, 063-05 · **Unblocks**: 063-07 … 063-11

## Goal

`_validation.py`: the strict candidates schema + the three anti-fabrication mechanisms. **Pure
validation — no repo, no writes** (the `_apply_validate` precedent: input errors must never touch the
DB, and this ordering is what makes "validation failure ⇒ ZERO files written" true by construction
rather than by care).

## The candidate shape

```jsonc
{
  "class": "decision",                       // ∈ roster {decision, requirement, risk} — else refused
  "title": "Отказаться от Kafka в MVP",
  "status": "accepted",                      // ∈ the class's ontology enum (checked in 063-08)
  "date": "2026-07-13",
  "body": "...",                             // markdown
  "source_quote": "…решили отказаться от Kafka…",   // ★ MANDATORY, verbatim
  "edges": {"supersedes": ["dec-kafka-poc"], "implements": ["req-latency"]}   // forward only
}
```

## ★ The three mechanisms (Q-063-4 — settled as mechanisms, not a wish)

1. **`CANDIDATE_COUNT_MIN = 0`.** An empty set is **SUCCESS**: `{"action": "no_candidates"}`, **exit 0**.
   > ⚠️ **The precedent has `_CANDIDATE_COUNT_MIN = 1`** (`wiki_extract_concepts/_validation.py`).
   > Cloning it makes *"this note has no decisions"* an **exit-4 failure** — so the model's cheapest
   > path to a green run is to **invent one**. The constant carries this comment, permanently.
2. **Mandatory verbatim `source_quote`.** Every candidate's quote must occur **in the source body**
   (`quote in source_body`, after the same NFC/whitespace normalisation the precedent uses). Miss ⇒
   `FIELD_QUOTE_NOT_IN_BODY`, **exit 4, zero writes**.
3. **The `WIKI_EXTRACT_NO_QUOTE_CHECK` env escape is NOT honoured here.** The precedent honours it.
   This skill does not — grounding is the mechanism, and an env var that switches it off is a
   mechanism with an off switch. Test it, don't just omit it.

**Caps (R-063-11) — overflow REFUSES, never truncates.** `CANDIDATE_COUNT_MAX`, `FIELD_CAPS` per
field, `_MAX_CANDIDATES_BYTES`, `_MAX_SOURCE_BODY_BYTES`. *Silent truncation would lose decisions —
which is this task's own disease.*

## Context — files

- **Edit** `scripts/wiki_skills/wiki_extract_decisions/_validation.py`, `_errors.py`.
- **Read** `wiki_extract_concepts/_validation.py` — `_validate_candidates_schema`,
  `_REQUIRED_CANDIDATE_KEYS`, `_FIELD_CAPS`, `_preflight_sanitize`, and the quote-in-body check
  (**and the env escape, so you can see exactly what you are NOT cloning**).
- **Read** `wiki_extract_concepts/__init__.py::_apply_validate` — the validate-before-open-the-DB
  ordering contract (guarded by the CWE-117 canary tests).

## Steps

1. `_REQUIRED_CANDIDATE_KEYS` / optional keys; `UNKNOWN_FIELD` on anything else (strict — a
   misspelled `sorce_quote` must not silently disable grounding).
2. `validate_candidates_schema(candidates, *, source_body, roster)` → raises `ExtractionParseError`
   carrying **ALL** violations (not the first — one repair round, not N; see 063-08 for the envelope).
3. `CANDIDATE_COUNT_MIN = 0` with the comment above.
4. Quote check; no env escape.
5. Caps → `CANDIDATES_TOO_LARGE` / `FIELD_TOO_LONG` / `SOURCE_TOO_LARGE`, all exit 4/2, **never a
   truncation**.

## Tests (RED first) — `tests/test_extract_decisions_validation.py` (new)

- `test_empty_candidates_is_success_exit_0` — `[]` ⇒ exit **0**, `action: no_candidates`, **zero
  files written**. **MUT:** set `CANDIDATE_COUNT_MIN = 1` ⇒ RED. *This single test is the whole
  anti-fabrication posture; without it the model has a standing incentive to invent a decision.*
- `test_quote_not_in_body_refuses` — exit 4, `FIELD_QUOTE_NOT_IN_BODY`, zero writes.
- `test_no_quote_check_env_escape_is_not_honoured` — set `WIKI_EXTRACT_NO_QUOTE_CHECK=1`, bad quote
  ⇒ **still exit 4**. **MUT:** honour the env var ⇒ RED.
- `test_missing_source_quote_key_refuses` — the key is REQUIRED, absence ≠ "no grounding needed".
- `test_unknown_field_refuses` — `{"sorce_quote": …}` ⇒ `UNKNOWN_FIELD`, exit 4.
- `test_overflow_refuses_never_truncates` — `CANDIDATE_COUNT_MAX + 1` candidates ⇒ exit 4 and the
  written-page count is **0**. Assert on the filesystem, not just the envelope.
- `test_class_outside_roster_refuses` — `class: person` ⇒ refused. *(Q-063-3: this is what protects
  the participants rule here — the `wiki-import` pyramid guard does NOT cover this rail; the roster
  does.)*
- `test_validation_failure_touches_no_db` — patch `make_repo` to raise; a schema-invalid payload must
  still exit 4 (⇒ validation ran **before** the DB was opened).

## Exit criteria

- [ ] `pytest tests/ -q` ≥ 2477 passed. `mypy --strict scripts/` clean.
- [ ] **GREP:** `grep -rn "NO_QUOTE_CHECK" scripts/wiki_skills/wiki_extract_decisions/` ⇒ **no hits**
      (the escape is absent, not merely unused).
- [ ] **GREP:** `grep -rn "CANDIDATE_COUNT_MIN" scripts/wiki_skills/wiki_extract_decisions/` ⇒ `= 0`,
      with the comment.
- [ ] **MUT:** each of the three mechanisms reverted ⇒ its named test goes RED. All three verified.

## Rollback

`_validation.py` reverts to stubs; `apply` still stubbed. Tree green.
