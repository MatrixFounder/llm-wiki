# VDD Multi-Adversarial Report — TASK 008 `wiki-verify-multi` (R-8)

**Date:** 2026-05-29
**Critics:** critic-logic · critic-security · critic-performance (parallel, Layer-A)
**Scope:** the TASK 008 change set (new skill `wiki_verify_multi.py`, the reindex
`_frontmatter_refs` generalisation, the verify-state DAL, the v5 schema, the
rename fanout) — "verify correct + complete + nothing broke".
**Verdict:** **PASS** — 1 HIGH + 2 MEDIUM fixed inline + regression-locked;
security bikeshedding-only; performance findings addressed. critic-logic
iteration-2 re-verification: **clean-pass**. Final: **672 pytest / 4 skip, mypy --strict clean**.

## Findings + dispositions

### 🟠 HIGH — L-1 (logic): case-sensitive PASS/FAIL gate defeated the safety premise [FIXED]
`_is_fail` compared `lens`/`severity` case-sensitively, so a critic emitting
`severity:"High"` / `lens:"Factual"` (common LLM casing) silently scored as
non-failing → a real high-severity factual finding derived **PASS**, defeating
the whole "Python rule overrides the LLM's self-report". The SKILL contract also
claimed a severity-enum validation the code never performed.
**Fix:** `_is_fail` now lowercases both fields; `apply` rejects any finding whose
lowercased `lens ∉ {factual,logic,security,completeness}` or `severity ∉
{low,medium,high,critical}` with `INVALID_VERDICT` (contract == code; closes both
case-drift and out-of-vocab). Regression: `test_severity_case_insensitive_fail`,
`test_invalid_severity_rejected`, `test_invalid_lens_rejected`. **iter-2 CLOSED.**

### 🟡 MEDIUM — L-3 (logic): vacuous PASS on non-empty cites but zero examined [FIXED]
`prepare` emitted `NO_SOURCES` only on empty `cites:`; if every cite was
missing/malformed, `examined=[]` yet it filed a (vacuous) verification.
**Fix:** `prepare` now refuses `NO_SOURCES` when `examined` is empty after the
gather. Regression: `test_all_cites_missing_is_no_sources`. **iter-2 CLOSED**
(apply-side absence of the guard confirmed a sound prepare/apply division — the
grounding gate + TOCTOU still hold on a direct apply).

### 🟡 MEDIUM — L-2 (logic): idempotency never re-armed after a crash [FIXED]
`record_verify_state` was inside `if changed:`; a crash between the file write
and the record (or a hand-authored page) left the file present but the state
absent → `prepare` never reported `is_unchanged` → the 4-critic audit re-ran
forever.
**Fix:** `v_hash` computed before the branch; on the `not changed` path, re-record
when `check_verify_state != v_hash` (crash-recovery re-arm). Regression:
`test_rearm_verify_state_when_state_absent`. **iter-2 CLOSED** (`--force` →
`changed=True` → the `if` branch, no double-record).

### 🟢 Security — bikeshedding-only (the bar is met)
critic-security confirmed the **#1 attack — YAML frontmatter forgery via the
verdict body — is NOT exploitable** (two layers: per-field `sanitize_markdown_text`
escaping the leading `-`/`#`/… of an injected `---`, + `frontmatter.dumps`
emitting the real frontmatter first; python-frontmatter only parses frontmatter
at doc start). All controls honoured in CODE: CWE-117/209 envelopes, O_NOFOLLOW
+ validate_inside_vault + symlink-refuse on every read/write, exact-membership
grounding gate (no prefix/substring pivot), `--orchestrator-id` regex, no-mutate
invariant, SECURITY-SENSITIVE banner + H-6 armor.
**Action:** the one ask — the forgery defense was **untested** (S-1) → added
`test_frontmatter_forgery_via_finding_note_is_neutralised` (asserts the page
parses as one doc with the trusted `verdict`/`type` + no smuggled key). LOW-2
(`## Sources` wikilink not re-sanitised) + LOW-3 (symlink pre-check is advisory;
O_NOFOLLOW is authoritative) accepted as parity with `wiki-query` (Q-007-4) — no change.

### 🟢 Performance — addressed
- **P-1 (MED):** `_index_verification_page` re-reads the just-written file via the
  manual adapter (unbounded) — the deliberate byte-identity §D8 symmetry cost
  (parity with `wiki_query` Q-007-2; the bytes were just written from the bounded
  verdict payload). **Documented** in the docstring; no refactor (the symmetry is
  the 008-09 acceptance constraint).
- **P-2 (LOW):** no cap on processed `cites:`. **Fixed** — `_MAX_CITES=100` cap in
  the SHARED `_gather_examined` (symmetric across prepare/apply so the grounding
  gate can't desync; overflow reported in `missing_cites`).
- Connection handling, N+1, self-index routing (no manifest N+1), state queries
  (PK point-lookups), regex/datetime hoisting, `_frontmatter_refs` purity (no I/O)
  — all clean.

## Deferred / documented (LOW, by-design / parity)
- **L-4** answer_hash anchors the body not `cites:` frontmatter (TOCTOU on a
  mid-pipeline cite edit) — fail-safe (apply re-derives examined; a removed cite
  → FINDING_SOURCE_NOT_EXAMINED); parity with Q-007-3.
- **L-5 / L-008-2** `verify_hash` keys on the cited-source *set*, not source body
  content — parity with TASK 007 `question_hash`; docstring corrected + KNOWN_ISSUES
  L-008-2 recorded.
- **L-6** `_index_verification_page` passes a throwaway `skipped` sink — defensive,
  parity with `wiki_query`; apply always writes a well-formed `verifies:`.

## Convergence
critic-logic **clean-pass** (iter-2); critic-security **bikeshedding-only**;
critic-performance findings addressed. 672 pytest / 4 skip; mypy --strict clean
(61 files). 6 new regression tests added. Nothing auto-committed.
