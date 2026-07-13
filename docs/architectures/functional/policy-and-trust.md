# 2.4. Policy-before-model retrieval scoping (TASK 049 / R-16 — realizes ADR-009)

**Contents**

- [2.4. Policy-before-model retrieval scoping](#24-policy-before-model-retrieval-scoping-task-049--r-16--realizes-adr-009)
- [2.4.1 Read-side audit + derived trust tier](#241-read-side-audit--derived-trust-tier-task-050--r-17)

The retrieval layer gains an **optional, default-OFF** classification gate, composed of:

1. **The ladder** — an ordered per-vault level `policy:` block in `WIKI_SCHEMA.md` (read via the existing `load_root_config` overlay path).
2. **The page key** — an optional `classification:` frontmatter key (absent ⇒ vault `default_level` — derive-don't-author).
3. **The scope flag** — `--audience <level>` on `wiki-search` / `wiki-query prepare|apply` / `wiki-verify-multi prepare|apply` (+ `wiki-import --classification` as the H-6 `_raw/`-quarantine stamp).

Enforcement is **deterministic and pre-envelope** (Karp pillar 3 — policy before the model, never prompt-armor):

- **One bound SQL predicate** — `COALESCE(CAST(json_extract($.classification) AS TEXT), ?) IN (…)` appended to `search_pages`' shared `clause_parts` **before LIMIT** (all three query shapes — the `exclude_types` precedent).
- **Two per-page Python gates** on the `get_page` paths that bypass search — `wiki-query _follow_edges` (before the `_MAX_EDGE_PULLED` truncation) and `wiki-verify-multi _gather_examined` (excluded cites become a count-only `restricted_count`).
- **Hash fold** — the audience folds into `question_hash` **only when a profile is active** (OFF ⇒ hash bytes unchanged; a prepare/apply mismatch fails loudly as `QUESTION_CHANGED`); the existing `CITATION_NOT_RETRIEVED` gate then mechanically prevents citing an out-of-tier page in a filed answer.
- **Fail-closed** — unknown/foreign level strings are rejected (the `IN` property; cross-vault scope uses the HOME vault's ladder).

Lint gains `classification-leak` (lower page cites/verifies higher — contradiction ⇒ `--strict` rail, ADR-006 posture) + `invalid-classification` (warning).

> **Honest boundary (ADR-009):** the gate scopes what a *model invocation* sees — least-privilege for cooperating agents + leak containment for filed Class-A artifacts — **NOT** authZ against the machine's owner.

Zero impact on §4 Data Model (**zero DDL** — rides `frontmatter_json` on the ADR-005-accepted unindexed path; `user_version` 7); §5 gains only flags + one new pure module (`scripts/wiki_index/policy.py`) + two DAL params + `find_classification_leaks`; §6 unchanged (no deps). Design rationale: Q-049-1..4 (§11i); enforcement-point inventory in Q-049-4.

## 2.4.1 Read-side audit + derived trust tier (TASK 050 / R-17)

**Audit half.**
- `wiki-query apply` logs its `query` event on EVERY success (the `if changed:` gate moves off the log call — idempotent re-queries leave an `action: unchanged` trail) with the **cited slugs** (not a count) + active `audience`.
- Opt-in `wiki-query prepare --log-retrieval` / `wiki-search --log-access` record the retrieved/hit slug sets.
- `WIKI_ACTOR_ID` (validated, shared shape with `--orchestrator-id`, invalid ⇒ silently absent) threads `details_json.actor` through the knowledge-write events (query/verify/append-log/ingest — maintenance writers deliberately excluded).
- All audit events are **Class-C DB-only** (`log_md_byte_offset` NULL — the established apply/verify precedent; Q-050-2: telemetry must not spam the operator's Class-A `log.md`). **D5** makes that shape durable: the `reindex_full` wipe now spares NULL-offset rows (`... AND log_md_byte_offset IS NOT NULL`) — pre-050 EVERY DB-only event died on every `--full` (mirrored rows still wipe + re-parse from `log.md`, which stays authoritative for the mirror).
- Logging is best-effort on read paths (a failed insert reports `access_logged: false`, never a crash).

**Trust half.**
- Every prepare hit carries a DERIVED `"trust"` tier — `external(0) < internal(1) < verified(2)`, MIN-rule (origin taints: external + verified ⇒ external, Q-050-1).
- Computed from an `http(s)://` scalar under one of **`policy.EXTERNAL_PROVENANCE_KEYS`** (TASK 061 / R-061-3 — the ONE source of truth, deliberately not re-listed here; both halves of the Q-050-3 contract are *rendered* from it), the `_raw/` path segment, and inbound `verifies` refs (ONE batched `find_verified_slugs` per prepare and per edge-depth-level — no N+1); it supersedes the synthesis contract's `_raw/` path heuristic with machine-readable signal.
- **TASK 061 / R-061-3 — the key set carries its CASE VARIANTS** (`source`/`Source`/`SOURCE`/`url`/`Url`/`URL`). Pre-061 only `source`/`url`/`URL` were recognised, so **18 live pages carrying `Source:`** derived `internal` — the trust layer failed OPEN. Enumeration (not case-folding) is forced by the **Q-050-3 alignment** constraint, *not* by performance: SQLite `json_extract` matches its path key **case-sensitively**, so a true fold needs `json_each` + `lower(key)` **in SQL only** — precisely the asymmetric predicate Q-050-3 forbids.
  - **Honest limit** — this closes 100% of the *observed* leak, **not the class**: a typo-shaped key (`uRL:`, `Source_URL:`) still fails open (no tool emits those). `SOURCE`/`Url` have 0 live pages — cheap defense-in-depth (this is *not* a P-5 concern; P-5 is about speculative indexes).
  - **Known residual — Q-061-4** — vault-specific provenance keys (`youtube:` 9 pages, `teachable:` 9) are *different keys*, not case variants, and still derive `internal`. The contract is about external ORIGIN, not key spelling, so this **is** a defect; it is deferred by **mechanism** (it needs a per-vault `external_keys:` config surface, which does not belong in a fix task), not by defect. Test-pinned in its known-wrong state on BOTH halves (`test_vault_specific_provenance_key_still_internal_q0614`) so it stays visible.
  - **Blast radius** — **default search/prepare output is UNCHANGED** (the newly-`external` pages still rank and return; only their `trust` annotation moved). Only an explicit `--min-trust internal|verified` caller sees the 18 pages drop out.
- Optional `--min-trust` (prepare+apply, MUST match — flag-present folds into `question_hash` incl. the no-clause `external` floor) filters **in SQL pre-LIMIT** with predicates test-pinned to the Python derivation (Q-050-3; `LIKE '\_raw/%' ESCAPE '\'`).

Zero DDL; composes with §2.4's audience scoping (both fold, both filter). Zero impact on §4/§6.
