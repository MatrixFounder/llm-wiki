# TASK 050 — Read-side audit completeness + derived trust tier (R-17)

## 0. Meta Information
- **Task ID**: 050
- **Slug**: read-audit-trust-tier
- **Depends on**: TASK 049 (policy layer — shipped; R-17 shares its scope-flag plumbing:
  only-when-active hash folds, profile resolution, the pre-LIMIT SQL posture)
- **Decision history**: ROADMAP R-17 (enterprise-readiness theme, ADR-009 context).
  Design refined from the TASK-049-era analysis pass (scratchpad `design-mapping-minimal`
  increment B/D).

## Problem / Motivation

1. **No policy increment is verifiable without read-audit.** `wiki-query apply` logs a
   `query` event ONLY when a new page files (`if changed:` — `wiki_query.py`) and records
   a citation **count**, not which sources entered the answer; an idempotent re-query
   logs nothing; `wiki-query prepare` (the actual retrieval pass) and `wiki-search` log
   nothing at all. "What did the model read" is unanswerable.
2. **No actor identity.** `--orchestrator-id` names the model/tool; nothing names the
   invoking human/agent, so multi-agent setups can't attribute writes.
3. **Provenance is a prompt-side heuristic.** The synthesis contract special-cases
   `_raw/` by PATH STRING matching inside the LLM prompt — the layer itself doesn't tell
   the orchestrator which hits are external captures vs verified content (the H-6
   "the layer knows provenance" gap; Karp pillar 2 hygiene).

## Goal

Four additive slices — **zero DDL** (`query`/`verify` are already in the `event_type`
CHECK enum; `details_json` is a free-form bag), **vendor-agnostic** (flags/env only),
**default behavior unchanged** (new envelope key `trust` is purely additive; every new
flag/env defaults OFF; the `is_unchanged`/`question_hash` contract is untouched unless a
new scope flag is actively used).

### D1 (R-17-i) — `wiki-query apply` audit completeness
Drop the `if changed:` gate around `append_log_event`: EVERY successful apply logs one
`query` event (idempotent re-queries included — `details_json.action:
"filed"|"unchanged"`). `details_json` gains `cited: ["project/slug", ...]` (the actual
slugs, replacing nothing — `cites` count stays for back-compat) and `audience: <level>`
when a policy profile is active. The event stays **Class-C DB-only** (no `log.md` line —
the existing apply-event precedent; `log_md_byte_offset` stays NULL).
`record_query_state`/self-index stay inside `if changed:` (only the LOG moves out).

### D2 (R-17-ii) — `WIKI_ACTOR_ID` actor identity
New `_common.py` helper `actor_id() -> str | None`: reads `WIKI_ACTOR_ID`, validates
against the existing orchestrator-id shape (`^[a-z0-9._:@-]{1,64}$`); **invalid or unset
⇒ None, silently** (ambient env must never fail a CLI; documented). Threaded as
`details_json.actor` (only when set) into the KNOWLEDGE-write event writers:
`wiki-query apply`, `wiki-verify-multi apply`, `wiki-append-log`, the `ingest` event in
`_manifest_consumer` (the wiki-import/upsert/sync provenance path), and the new D3
events. Deliberately NOT threaded into maintenance-batch writers (`reindex`,
`wiki-index-render`, `wiki-init` reclassify) — those are operator-mechanical, not
knowledge attribution (recorded out-of-scope). The shape regex moves to `_common.py`
and is SHARED with `--orchestrator-id`'s validator (no copy to drift). Complementary to
`--orchestrator-id` (model identity), not a replacement.

### D3 (R-17-iii) — opt-in retrieval logging
- `wiki-query prepare --log-retrieval` (default OFF): after a successful retrieval,
  append ONE `query` event — subject = `query_slug`, `details_json = {access: true,
  retrieved: ["project/slug", ...], audience?, actor?}`. Class-C DB-only.
- `wiki-search --log-access` (default OFF): append ONE `query` event — vault_id = the
  home/factory vault (the `_global_` sentinel row exists in `vaults` for cross-vault
  scope), subject = `"search"`, `details_json = {access: true, q: <query control-stripped
  + capped 200 chars>, hits: ["vault:project/slug", ...], audience?, actor?}`.
  The flag makes wiki-search a DB writer — acceptable: WAL insert, no `log.md`, no flock
  (the flock protocol guards `log.md` appends only).
- Failure posture: a logging failure must NOT fail the search/prepare (best-effort —
  catch `sqlite3.Error` at least: a `--db-path`-only DB without the target/`_global_`
  vault row raises `IntegrityError` (FK ON), not `OperationalError` — arch-review F4;
  report `"access_logged": false` in the envelope when the flag was given but the
  insert failed; never crash a read path over telemetry).

### D4 (R-17-iv) — derived per-hit `trust` + `--min-trust`
Ordered tiers **`external`(0) < `internal`(1) < `verified`(2)**, fully DERIVED (no new
authored field):
- `external` — the page's `frontmatter_json` `$.source`, `$.URL`, OR `$.url` (the
  codebase reads/writes both casings — `_fetch.py` reads `url`, `_authoring.py` writes
  `URL`) is an external URL (exact `http://`/`https://` prefix, ASCII-case-insensitive —
  never bare `http`, which would over-match `httpx://`) OR its
  `file_path` lives under a `_raw/` segment (`_raw/...` or `.../_raw/...`; in SQL the
  underscore MUST be escaped — `LIKE '\_raw/%' ESCAPE '\'` — or `_` wildcard-matches
  `Xraw/`; pinned by the alignment test).
- `verified` — an inbound `verifies` ref targets the page's slug
  (`page_entity_refs.ref_type='verifies' AND entity_slug = slug`) AND the page is not
  `external`. **Origin taints: external wins over verified** (min-rule — a verified
  external capture stays `external`; Q-050-1).
- `internal` — everything else.

Surfaces:
- **Annotation (always-on, additive)**: every hit dict in the `wiki-query prepare`
  envelope gains `"trust": "<tier>"`. Derived in Python; the inbound-verifies set is
  fetched in ONE bound query per prepare (new DAL `find_verified_slugs(pairs:
  list[tuple[vault_id, slug]]) -> set[tuple[vault_id, slug]]` — PAIRS, cross-vault-safe:
  a single-vault signature would false-mark a slug verified from another vault's ref
  under `--vaults all`; batched IN-clause over row-values, not per-hit N+1). The synthesis contract's
  `_raw/` path-heuristic paragraph is superseded by the machine-readable field
  (SKILL.md update).
- **`--min-trust {external,internal,verified}`** on `wiki-query prepare` AND `apply`
  (MUST match; drift ⇒ `QUESTION_CHANGED`). **"Active" = the flag is PRESENT**: all
  three values fold into `question_hash` — including `external`, which imposes no SQL
  clause (floor = lowest tier) but still folds, keeping prepare/apply symmetry
  unambiguous; only flag-ABSENCE leaves the hash unchanged (the R-16 audience pattern). Enforced **in SQL, pre-LIMIT** (the
  `exclude_types`/R-16 posture — a filtered page must not consume a top-limit slot):
  - `--min-trust internal` ⇒ `AND NOT <external_predicate>`
  - `--min-trust verified` ⇒ `AND NOT <external_predicate> AND EXISTS(<verifies_ref>)`
  - `--min-trust external` ⇒ no clause (floor = lowest tier; accepted + hash-folded).
  New `search_pages` kwarg `min_trust: str | None = None` (validated against the tier
  enum — `ValueError` on unknown, library-caller defense). The Python tier derivation
  and the SQL predicates MUST agree (R-16's `effective_level`↔SQL alignment lesson —
  test-pinned). `find_verified_slugs` accepts and returns `(vault_id, slug)` PAIRS
  (hits span vaults under `--vaults all`; the EXISTS correlates on `r.vault_id =
  p.vault_id` — the leak-check pattern). `_follow_edges` neighbors get the same floor
  (they bypass `search_pages`). Pinned contract (arch-review F3): (a) the verified
  batch runs ONCE per depth level over the candidate `(vid, slug)` pairs taken from
  `neighbors()` — no extra `get_page` for the batch (the existing per-accepted-candidate
  `get_page` stays and feeds the pure-Python `external` half); (b) the min-trust skip
  marks `seen` then `continue`s INSIDE the canonically-sorted stream, before the
  `_MAX_EDGE_PULLED` cap `break` (filter-inside-loop, never cap-then-filter — the
  question_hash C1 invariant); (c) the verified set is consumed as order-independent
  membership. Deterministic and identical across prepare/apply.

### D5 (arch-review F1) — Class-C audit rows survive `wiki-reindex --full`
Reality check: `reindex_full` today wipes `log_events` per vault and rebuilds ONLY from
`log.md` — so every DB-only event (the existing apply/verify precedent AND all new D1/D3
events) dies on every `--full`, contradicting Class-C semantics (`source_state`/query
state DO survive a Class-B rebuild). Fix: the wipe becomes
`DELETE FROM log_events WHERE vault_id = ? AND log_md_byte_offset IS NOT NULL` —
mirrored rows (offset set) are still wiped + re-parsed from `log.md` (no dupes, log.md
stays authoritative for the mirror); DB-only rows (offset NULL ⇔ never had a log.md
line) are preserved. One WHERE clause + tests (full-rebuild preserves a NULL-offset row;
mirrored rows still round-trip — the existing `test_e2e_rebuildability` counts stay
green since its events are mirrored).

### Out of scope (recorded)
Tamper-evident/signed audit (meaningless while the operator owns the files — ADR-009
YAGNI); logging reads of `wiki-graph`/`wiki-extract-concepts` (not retrieval envelopes);
`wiki-verify-multi --log-retrieval` (its prepare envelope is already the examined-set
record); an authored `trust_level` page field (the `page_entity_refs.trust_level` column
is edge-level and stays untouched — derive-don't-author); log rotation/retention (P3);
per-hit trust in `wiki-search` output (search hits carry `file_path` — the orchestrator
doesn't ground on search; revisit on demand).

## Requirements (RTM)

| ID | Requirement | Verification |
|---|---|---|
| **R-1** | apply logs on EVERY success (filed + unchanged) with `cited` slugs, `action`, `audience?`, `actor?`; log stays DB-only; `record_query_state`/index untouched by the move | e2e: filed run + idempotent re-run each yield one event; details shape asserted; no log.md write |
| **R-2** | `actor_id()` helper: valid env → threaded as `details_json.actor` in query/verify/append-log events; invalid/unset → absent, no error | unit: shape matrix; e2e per CLI with/without env |
| **R-3** | `--log-retrieval` on prepare: one `query` event with retrieved slugs; OFF default = zero writes; logging failure never fails prepare | e2e: flag on/off; failure injection (readonly DB) → prepare still 0 with `access_logged: false` |
| **R-4** | `--log-access` on wiki-search: one event, capped+stripped query text, hits list; `_global_` scope works; OFF default = zero writes; read path never fails over telemetry | e2e incl. `--vaults all`; CWE-117 strip test |
| **R-5** | `trust` annotation on every prepare hit; derivation matrix (external URL / `_raw/` path / verifies-ref / plain); ONE batched DAL query (`find_verified_slugs`) | unit matrix + e2e envelope; no per-hit N+1 (call-count seam) |
| **R-6** | `--min-trust` prepare+apply: SQL pre-LIMIT predicates ≡ Python tier (alignment tests); hash fold only-when-active; drift ⇒ `QUESTION_CHANGED`; `_follow_edges` floor gate deterministic; LIMIT-window test | DAL tests (3 shapes × 2 floors), e2e round-trip + mismatch, eviction test |
| **R-6b** | `reindex_full` preserves NULL-offset `log_events` rows; mirrored rows still wiped+re-parsed (no dupes) | test: DB-only event survives `--full`; mirrored count unchanged; rebuildability suite green |
| **R-7** | Docs: wiki-query/wiki-search SKILL.md flags; wiki-query-synthesis SKILL.md — `trust` field replaces the `_raw/` path heuristic paragraph; ROADMAP R-17 → SHIPPED; ARCHITECTURE §2.4 note + Q-050-*; templates untouched | doc diff review |
| **NFR-1** | Default-path stability: no flag/env ⇒ no hash change; the ONLY unconditional deltas are (a) the D1 completeness event (an idempotent re-apply gains exactly ONE DB-only `query` event; the filed-apply event gains `cited`/`action`) and (b) the additive `trust` hit key (`is_unchanged` unaffected) | goldens: hash stability; event-count delta ≡ D1 event only; envelope diff = trust only |
| **NFR-2** | Zero DDL; Decision-17; vendor-agnostic; CWE-209/117 (no value echo; capped/stripped subject text) | grep + schema untouched + message tests |
| **NFR-3** | `mypy --strict`; full suite green; karpathy byte-identity intact | CI commands |

## Use Cases
- **UC-1** Compliance question "what did the model read for answer X": the apply event's
  `cited` slugs + (opt-in) prepare's `retrieved` list answer it from `log_events`.
- **UC-2** Multi-agent attribution: `WIKI_ACTOR_ID=critic-security` in a subagent's env →
  every filed verdict carries `actor: critic-security`.
- **UC-3** H-6-hardened synthesis: orchestrator sees `trust: external` on a `_raw/`
  capture hit — machine signal, not path guesswork; operator runs
  `--min-trust internal` to ground only on non-external pages.
- **UC-4** Verified-only answering: `--min-trust verified` retrieves only pages with an
  inbound verification.
- **UC-5** Idempotent re-query still leaves an audit trail (`action: unchanged`) —
  NOTE (R-7 scope): the wiki-query workflow/SKILL short-circuits apply on `is_unchanged`;
  document that the trail is per-APPLY (an orchestrator that stops at prepare logs
  retrieval only via `--log-retrieval`), so UC-5 is "supported", not forced.

## Invariants that must not break
Zero DDL (`user_version` 7); Decision-17; H-6 (trust annotation is metadata — allowed
content stays untrusted DATA); `question_hash` back-compat (folds only-when-active);
M-2 log.md↔DB contract (new events are deliberately DB-only Class C — the mirror is for
operator-authored log lines); R-16 policy layer composition (audience + min-trust
compose: both fold, both filter); Karpathy byte-identity (no layout change).

## Open Questions
Q-050-1 (tier precedence: external taints verified — min-rule; plus the project-less
`entity_slug` imprecision: a cross-project same-slug inbound `verifies` over-classifies —
accepted derive-model cost, noted, no COUNT=1 guard for an advisory tier), Q-050-2 (audit events
are Class-C DB-only — why not log.md), Q-050-3 (SQL↔Python trust alignment contract) —
to be recorded in `docs/architectures/open-questions.md` §11j during Architecture.
