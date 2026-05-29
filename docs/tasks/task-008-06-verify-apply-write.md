# Task 008-06: `wiki-verify-multi apply` (write-side) — verdict validation, grounding gate, FAIL semantics

> **strict-TDD** (high-assurance — the grounding gate + FAIL-exit semantics + the
> never-mutate-the-answer invariant all live here).

## Use Case Connection
- UC-22: Verify → PASS (write the verdict page).
- UC-23: FAIL verdict → **exit 6** + the answer is untouched.
- UC-27: `ANSWER_CHANGED` / `FINDING_SOURCE_NOT_EXAMINED` / `INVALID_VERDICT` refused at the boundary.

## Task Goal
Implement `wiki-verify-multi apply` up to (and including) the Class A file write — **R-8.3 + R-8.7 + R-8.8 (apply half)**. It re-checks the answer (TOCTOU), validates + grounds the orchestrator's verdict JSON, sanitises the verdict body, writes `_verifications/<slug>.md`, and returns the verdict exit code (**exit 6 on FAIL**, never mutating the answer). **DB indexing is 008-07.**

## Changes Description

### Changes in Existing Files

#### File: `scripts/wiki_skills/wiki_verify_multi.py`
- Implement `apply(args) -> int`. CLI:
  `apply --vault V --vault-root P --verification-slug S --query-slug Q --answer-hash HEX (--verdict-stdin | --verdict-file PATH) [--fail-on {critical,high,medium,low,none}] [--orchestrator-id ID] [--force] [--db-path PATH]`
  - `--answer-hash` — 64-lowercase-hex argparse `type=` validator (`INVALID_ANSWER_HASH`, exit 2).
  - **TOCTOU:** `get_page(query_slug)`, recompute `answer_hash` from its body; mismatch with `--answer-hash` → `ANSWER_CHANGED` (exit 2). Re-derive the examined set from the query page's `cites:` (same as `prepare` — Q-008-c).
  - **Load + bound the verdict JSON** (`--verdict-stdin`/`--verdict-file` mutex; file form `validate_inside_vault` + `O_NOFOLLOW`; ≤ cap else `VERDICT_TOO_LARGE`; malformed → `VERDICT_PARSE_ERROR`; exit 4).
  - **Validate** the verdict shape: `verdict ∈ {"pass","fail"}` else `INVALID_VERDICT`; `critics` a list; `findings` a list of `{lens, severity, claim, source?, note}` (exit 4).
  - **Grounding gate:** every `findings[].source` that is present must be a `"<project>/<slug>"` in the examined set (keyed on the full **`project/slug`** tuple) → else `FINDING_SOURCE_NOT_EXAMINED` (exit 4). Enforced in Python, not trusted to the LLM (R-8.8b).
  - **Sanitise** the verdict body (findings rendered to markdown) via `_common.sanitize_markdown_text` (egress injection guard — the findings quote untrusted answer/source text).
  - **Ensure the target directory (adversarial-plan finding CMP-4 — else a migrated v4 vault crashes):** `atomic_write_text` does `tempfile.mkstemp(dir=target.parent)`, which raises `FileNotFoundError` if `_verifications/` does not exist — and a vault migrated v4→v5 (not freshly `--scaffold-new`'d) has no `_verifications/` until the first `apply`. Mirror `wiki_query.py:427-433`: build `verifications_dir = vault_root / layout.VERIFICATIONS_SUBDIR` (**import the constant — a literal `"_verifications"` trips the C-8/NFR-7 grep guard**), `verifications_dir.mkdir(parents=True, exist_ok=True)`, `validate_inside_vault(...)`, **then** write.
  - **Write** `_verifications/<verification_slug>.md` (Class A): frontmatter `type: verification`, `verifies: <query-project>/<query-slug>`, `verdict: <pass|fail>`, `critics: [...]`, `answer_hash: <hex>`, `date:`, optional `cites: [...]` (sources a finding referenced), `tags: [verification]`; body = sanitised findings + a `## Sources` `[[slug]]` list. Atomic write (`O_NOFOLLOW` symlink-refuse → `INVALID_VERIFICATION_PAGE`; tempfile + `os.replace`; content-hash skip → `action:"unchanged"` unless `--force`).
  - **Verdict exit logic (R-8.7):** compute PASS/FAIL vs `--fail-on` (default `high`, Q-008-e): FAIL iff any `factual`/`security` finding has severity ≥ threshold; `logic`/`completeness` advisory below. On FAIL → the page is **still filed**, return **exit 6 `VERDICT_FAIL`**. On PASS or `--fail-on=none` → exit 0.
  - **Exit-6 cross-CLI semantics (adversarial-plan finding SEC-4 — deliberate divergence, document it):** `6` is the wiki-CLI family's **generic error** code (`_common.emit` convention; `scripts/wiki_skills/.AGENTS.md`). Here it is **deliberately repurposed** as the verdict-fail signal — a **SUCCESS envelope with NO `error` key** (`{verdict:"fail", action:"filed", …}`). Callers MUST therefore branch on the **stdout envelope** (`verdict=="fail"` / presence of an `error` key), **never** on `$?==6 ⇒ errored-nothing-written` (which holds for every other wiki CLI). The `wiki-verify-multi` SKILL.md exit-code table + the `workflows/wiki-verify-multi.md` recipe (008-08) MUST state this divergence explicitly so no automated consumer silently discards a filed FAIL verdict.
  - **The `_queries/<slug>.md` answer is NEVER opened for write, edited, or deleted** (D-008-3) — `apply` has no write path to `_queries/`.
  - **Stops before DB indexing** — `record_verify_state` / `upsert_page` / log event are 008-07 (stubbed here).

### Component Integration
`apply` consumes `prepare`'s `verification_slug` + `answer_hash` + the orchestrator's verdict JSON (produced via the `wiki-verify` prompt skill, 008-08). The success envelope: `{vault_id, verification_slug, verdict, verifies, page_indexed:false (until 008-07), action:"filed"|"unchanged"}`.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01 (PASS write):** valid `verdict:"pass"` JSON → `_verifications/<slug>.md` written with `type: verification` + `verifies:` + `verdict: pass`; exit 0.
2. **TC-E2E-02 (FAIL → exit 6):** valid `verdict:"fail"` with a `factual` finding severity `high` → page **filed** with `verdict: fail`; **exit 6**.
3. **TC-E2E-03 (no-mutate invariant):** hash `_queries/<slug>.md` before + after a FAIL `apply` → **byte-identical** (the answer is never touched).
4. **TC-E2E-04 (`--fail-on=none`):** same FAIL verdict + `--fail-on=none` → page filed + **exit 0**.
5. **TC-E2E-05 (ANSWER_CHANGED):** edit the query page body after `prepare` → `apply` recomputes `answer_hash` ≠ `--answer-hash` → exit 2 `ANSWER_CHANGED`; nothing written.
6. **TC-E2E-06 (grounding):** a finding with `source: "_vault_/not-cited"` (not in the examined set) → exit 4 `FINDING_SOURCE_NOT_EXAMINED`; nothing written.
7. **TC-E2E-07 (verdict validation):** `verdict:"maybe"` → `INVALID_VERDICT`; non-JSON → `VERDICT_PARSE_ERROR`; oversized → `VERDICT_TOO_LARGE` (all exit 4, nothing written).
8. **TC-E2E-08 (idempotency / force):** re-run identical `apply` → content-hash skip (`action:"unchanged"`); `--force` rewrites.
9. **TC-E2E-09 (symlink refuse):** target `_verifications/<slug>.md` is a symlink → `INVALID_VERIFICATION_PAGE` (exit 4).

### Unit Tests
1. **TC-UNIT-01:** the PASS/FAIL rule — a `logic` finding at `high` with no `factual`/`security` finding → PASS (advisory); a `security` finding at `high` → FAIL.
2. **TC-UNIT-02:** grounding compares the full `project/slug` (cross-project same-slug fixture: `courseA/foo` cited, finding `source:"_vault_/foo"` → rejected).
3. **TC-UNIT-03 (envelope safety, CWE-117/209):** every error envelope carries `{error, field?, reason}` only — never echoes the answer/source/finding/verdict value (parametrized, extends the `wiki-query` regression).

### Regression Tests
- `prepare` (008-05) unchanged; no write path to `_queries/`; full `pytest` green.

## Acceptance Criteria
- [ ] Verdict JSON validated (`INVALID_VERDICT`/`VERDICT_PARSE_ERROR`/`VERDICT_TOO_LARGE`); grounding gate (`FINDING_SOURCE_NOT_EXAMINED`, `project/slug` key); `ANSWER_CHANGED` TOCTOU.
- [ ] Class A `_verifications/<slug>.md` written (sanitised body; atomic; `O_NOFOLLOW`; content-hash skip; `--force`).
- [ ] FAIL → page filed + **exit 6**; PASS / `--fail-on=none` → exit 0.
- [ ] **The `_queries/<slug>.md` answer is byte-identical before/after (no mutation)** — asserted by hash.
- [ ] Envelope-never-echoes-content invariant holds; full `pytest` green; `mypy --strict` clean.

## Notes
Strict-TDD: write TC-E2E-02/03 (FAIL→exit 6 + no-mutation) and TC-E2E-05/06 (TOCTOU + grounding) RED first. The no-mutation invariant (R-4 risk) and the exit-6 verdict signal (R-8 risk) are the load-bearing correctness properties. Depends on 008-05.
