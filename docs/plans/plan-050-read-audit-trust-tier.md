# PLAN 050 — Read-side audit completeness + derived trust tier (R-17)

Phases: **P1 (audit spine: D1+D2+D5) → P2 (opt-in read logging: D3) → P3 (trust: D4)
→ P4 (docs)**. Stub-first within each bead (signatures + RED → GREEN); every bead ends
with the full suite + `mypy --strict` green. RTM IDs from `docs/TASK.md`.

## P1 — Audit spine (R-1, R-2, R-6b)

**050-01 [R-2] `actor_id()` + shared shape** — `_common.py`: move the orchestrator-id
regex to `_common.ORCH_ID_RE` (wiki_query/wiki_verify_multi import it — no copy; fold
the FOURTH copy `wiki_extract_concepts/_validation._ORCHESTRATOR_ID_RE` too —
`_validation → _common` is an allowed leaf edge per §2.1, and the patch-target lock
covers symbols, not constants);
`actor_id() -> str | None` reads `WIKI_ACTOR_ID`, `fullmatch` or None (invalid/unset ⇒
silently None). Tests: shape matrix (valid/invalid/unset/oversize), no error on garbage.

**050-02 [R-1] apply audit completeness** — `wiki_query.apply`: move `append_log_event`
OUT of `if changed:` (record_query_state + self-index stay in); `details_json` gains
`cited: [project/slug...]`, `action: filed|unchanged`, `audience?` (profile active),
`actor?`. Tests (`tests/test_wiki_query_audit.py`, new): filed run → 1 event with slugs;
idempotent re-run → +1 event `action: unchanged`; audience threading; actor threading;
NFR-1 golden (event-count delta ≡ this event only; no log.md file appears).

**050-03 [R-2] actor in verify/append-log/ingest events** — `wiki_verify_multi.apply`,
`wiki_append_log`, `_manifest_consumer` ingest event: `details_json.actor` when set.
Tests per writer (with/without env).

**050-04 [R-6b] reindex_full spares Class-C audit rows** — `reindex.py` wipe loop:
special-case `log_events` → `DELETE ... WHERE vault_id = ? AND log_md_byte_offset IS
NOT NULL`. Tests: a NULL-offset event survives `--full`; a mirrored (offset-set) event
still wipes + re-parses without dupes; `tests/test_e2e_rebuildability.py` untouched
and green.

## P2 — Opt-in read logging (R-3, R-4)

**050-05 [R-3] `wiki-query prepare --log-retrieval`** — flag; after successful retrieval
(post `min_hits` gate), best-effort append (`try/except sqlite3.Error` minimum — a
`--db-path`-only DB without the vault row raises `IntegrityError`, FK ON): subject =
`query_slug`, details `{access: true, retrieved: [...], audience?, actor?}`; envelope
gains `access_logged: true|false` ONLY when the flag was given. Tests: on/off, event
shape, failure injection (unregistered-vault DB) → exit 0 + `access_logged: false`.

**050-06 [R-4] `wiki-search --log-access`** — flag; one event: vault_id = the log
target computed as `vaults_list[0] if vaults_list and len(vaults_list)==1 else
GLOBAL_VAULT_SENTINEL` (plan-review MED-1 — do NOT reuse `factory_vault`, which is
`[0]` for ANY non-empty list and would mis-log `--vaults a,b` to `a`), subject `"search"`,
details `{access: true, q: <control-stripped, ≤200 chars>, hits: ["vault:project/slug"],
audience?, actor?}`; same best-effort posture + `access_logged` echo only-when-flagged.
Tests: single-vault, `--vaults all` (`_global_` row), **`--vaults a,b` → `_global_`**
(MED-1), CWE-117 strip/cap, failure injection, OFF ⇒ zero writes.

## P3 — Trust tier (R-5, R-6)

**050-07 [R-5] tier derivation + DAL batch** (LOW-3: the Python `_raw` path check is
ASCII-case-insensitive to match SQLite `LIKE` — a `_RAW/` row sits in the corpus) — `policy.py` (or a sibling pure module —
decide at implementation; keep Decision-17): `TRUST_TIERS = ("external", "internal",
"verified")`, `trust_tier(page, verified: bool) -> str` (external: exact
`http://`/`https://` ASCII-ci prefix on `$.source`/`$.URL`/`$.url` scalar strings —
non-scalar ⇒ not external — OR a `_raw` path segment; min-rule: external beats
verified). DAL `find_verified_slugs(pairs) -> set[(vault_id, slug)]` (ABC + impl; one
bound query, row-value IN or OR-chain). Tests: derivation matrix (incl. list/object
source, `Xraw/` non-match, case variants), DAL pairs semantics + cross-vault
false-positive guard.

**050-08 [R-5] prepare envelope annotation** — `_hit_dict` gains `trust`; prepare
computes the verified set in ONE `find_verified_slugs` call over the final hit list.
Tests: envelope matrix e2e; call-count seam (one DAL call); **named NFR-1 golden
`test_default_envelope_diff_is_trust_only`** (default-path prepare envelope vs a
pre-050 recorded shape: the ONLY new key per hit is `trust`).

**050-09a [R-6] `search_pages.min_trust` SQL + alignment** — kwarg `min_trust` (enum-validated
`ValueError`); SQL in shared `clause_parts` pre-LIMIT: `internal` ⇒ `AND NOT <ext>`;
`verified` ⇒ `AND NOT <ext> AND EXISTS(verifies corr. vault_id)`; `external` ⇒ no
clause. `<ext>` uses `LIKE '\_raw/%' ESCAPE '\'` + `'%/\_raw/%' ESCAPE '\'` + http-prefix
`LIKE 'http://%'`/`'https://%'` on the three JSON paths (all literals; values bound where
any). Tests (09a): SQL↔Python alignment matrix (3 shapes × 2 floors ×
the derivation corpus incl. `_RAW/`), LIMIT-window eviction.

**050-09b [R-6] wiki-query `--min-trust` plumbing** — flag on prepare+apply
(MUST-match epilog), fold `\x00min_trust:<v>` into `_question_hash` when flag PRESENT
(incl. `external`); `_follow_edges` floor gate per the pinned contract (batch per depth
level over candidate pairs pre-cap; seen+continue inside the sorted stream). Tests
(09b): e2e round-trip + drift ⇒ `QUESTION_CHANGED`, edge-gate determinism, `external`
folds but filters nothing, compose with `--audience`.

## P4 — Docs (R-7)

**050-10 [R-7]** — SKILL.md: wiki-query (flags `--log-retrieval`/`--min-trust`, trust field),
wiki-search (`--log-access`), wiki-query-synthesis (the `trust` field SUPERSEDES the
`_raw/` path-heuristic paragraph — rewrite it to key on `trust: external`; keep the
fenced-sentinel rule); workflow note: the audit trail is per-APPLY (UC-5 "supported not
forced"). ROADMAP R-17 → SHIPPED one-liner; ARCHITECTURE quality-checklist row
(§2.4.1/§11j already landed). Final gates: full suite, `mypy --strict`, `grep import
anthropic` ∅, `user_version` 7 untouched, karpathy byte-identity green.

## Order & risk
01→02→03→04 (spine) → 05→06 (independent) → 07→08→09a→09b (the risky slice lands
last, split SQL-first, after the derivation matrix is green) → 10. No bead touches layouts or the
schema. NFR-1 goldens live in 050-02 (audit delta) and 050-09 (hash stability).
