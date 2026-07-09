# ADR-009 — Policy-before-model retrieval scoping (the ontology-layer access gate)

**Status:** Accepted — **SHIPPED as TASK 049 (2026-07-07)** · **Date:** 2026-07-07 ·
**Supersedes:** none ·
**Relates:** ADR-002 (Class A/B/C + vault_id partitioning), ADR-005 (unindexed metadata-predicate
posture), ADR-006 (derive-don't-author; lint-vs-health split), Decision-17 (deterministic
plumbing), H-6 (untrusted content), ROADMAP R-16…R-19 (the enterprise-readiness theme this ADR
heads).

## Context

### The pattern this repo already implements

The Palantir/Karp "ontology layer" thesis — *don't train models on business data; build a durable
layer above the model that keeps knowledge outside it, unifies sources into semantic objects +
typed links, enforces access policy BEFORE data reaches the model, and makes the LLM a swappable
reasoning engine* — maps onto this codebase as follows (audited 2026-07-07):

| Pillar | Status here | Evidence |
|---|---|---|
| 1. Knowledge outside the model; transient query-time context | **Complete, mechanically enforced** | Decision-17: zero LLM SDK anywhere in `scripts/` (grep-verified); `prepare`/`apply` sandwich; grounding is a Python exit-code gate (`QUESTION_CHANGED`, `CITATION_NOT_RETRIEVED` — `wiki_query.py`), not model goodwill; markdown canonical, DB rebuildable (ADR-002 §D8) |
| 2. Semantic objects + typed links over heterogeneous sources | **Substantial; both gaps now closed** | Entities (8-type enum) + hard-unique aliases + 13 typed page classes (ADR-003) + 15 inverse-closed edge kinds (ADR-004) + graph-derived `--as-of` temporality (TASK 034). ~~Gaps: no declared edge domain/range or property enums (→ R-19); sources are one-shot file imports, no refresh loop (→ R-18)~~ — **R-18 shipped (TASK 051, source freshness / connector substrate); R-19 shipped (TASK 054, formal ontology spec: declared `ontology:` block with validated edge domain/range + property enums, surfaced by `wiki-lint ontology-violation` + `wiki-health ontology`, zero-DDL, read-only, not a write gate).** |
| 3. Policy enforced before data reaches the model | **Absent — this ADR** | No classification/audience/ACL construct exists (grep-null); retrieved bodies enter the model context verbatim; the only guard is prompt-layer H-6 armor — i.e. exactly the "hand it everything and ask it to keep secrets" anti-pattern the thesis rejects |
| 4. Swappable model; the layer is the durable asset | **Complete** | Vendor-neutral prose contracts + JSON envelopes + stable exit codes; symlink fan-out `.claude/`/`.agent/`/`.pi/`; glob-based harness discovery (`home.glob(".*/skills")`) — a new CLI vendor needs zero code change. Residual coupling is dev-harness only (settings.json, hooks, vdd-multi) |

Pillar 3 is the one structural gap where nothing exists at all, and it is the highest-leverage
one: every retrieval surface (`wiki-search`, `wiki-query prepare`/`apply` incl. `--follow-edges`,
`wiki-verify-multi` critics) currently hands ANY indexed page to the orchestrator model —
including hostile `_raw/` captures (KNOWN_ISSUES H-6) and private pages when spanning vaults via
the `_global_` sentinel (`wiki_search.py` passes `vaults=None` → no vault predicate).

### The honest boundary (read this before the design)

There is no authentication and no second user (`docs/architectures/security.md` §7.1: authN N/A,
authZ = file permissions). The operator owns the files AND the SQLite DB — nothing in-process can
be a security boundary against them. What CAN be enforced deterministically is **what a given
model invocation gets to see**: least-privilege for cooperating agents (subagent critics,
low-trust automation), containment of what leaks into durable Class-A artifacts
(`_queries/*.md`, verification pages — which get committed/synced/read downstream;
Class-B `index.md`/ledger renders remain UNSCOPED metadata surfaces, see TASK 049 Out-of-scope), and cross-vault bleed under `--vaults all`. That is the honest, single-operator
version of "policy before the model" — least-privilege *configuration*, not protection from the
machine's owner. A real authZ boundary remains trigger-gated to the Postgres/multi-tenant
migration (ROADMAP "Operational polish" + the R-9 trigger); this ADR must never be sold as it.

## Decision

**Add an optional, default-OFF retrieval-scope policy layer: an ordered classification ladder,
resolved per page from Class-A state, enforced as one bound SQL predicate BEFORE content enters
any retrieval envelope.** Zero DDL; vendor-agnostic (pure CLI flags/env + config); no prompt-layer
dependence.

1. **Class A expression.** One optional page frontmatter key `classification: <level>`; a vault
   `policy:` block in `WIKI_SCHEMA.md` (merged by `load_root_config`, `config_loader.py`):
   `levels: [public, internal, restricted]` (ordered, per-vault-configurable), `default_level`
   (assumed when the key is absent — unclassified = lowest, derive-don't-author), and an
   OPTIONAL `default_audience`. **Activation precedence (pinned in Q-049-1):** `--audience`
   flag → active; else `default_audience` *if declared* → active — even at the highest level
   (a declared audience ALWAYS activates and folds the hash; a max-level=OFF special case was
   rejected: adding a new top level later would silently flip semantics); else OFF. A flag
   with no resolvable block uses the built-in ladder.
   Mirroring is automatic: `frontmatter_json` already stores the whole authored map
   (`reindex.normalize_frontmatter`), so the key is queryable via
   `json_extract($.classification)` with **no indexer change and no schema bump**. Phase 2
   (optional): folder-glob defaults (`classification_paths: {"_raw/**": restricted}`) injected at
   normalize time — the same idiom as type-mapping tag-routes.

2. **Enforcement point — one SQL choke point, pre-LIMIT.** `search_pages` gains an optional
   `allowed_classifications` parameter (paired both-or-neither with `classification_default` —
   library-caller defense); when active it appends
   `AND COALESCE(CAST(json_extract(p.frontmatter_json,'$.classification') AS TEXT), ?) IN (?,…)`
   to the shared `clause_parts` (all values bound; fixed JSON path — the repo's
   no-f-string-values posture; the `CAST` normalizes non-string authored values so they fail
   closed on both the SQL and Python paths).
   Because the clause is shared by all three query shapes and applied **before LIMIT** (the
   `exclude_types` precedent), a filtered page never consumes a result slot and never enters the
   envelope of `wiki-search` or `wiki-query prepare`/`apply`. Unknown/foreign level strings fail
   **closed** (excluded by the `IN` property). Three bypass paths get their own gates:
   `wiki-query _follow_edges` (per-page level check before the `_MAX_EDGE_PULLED` truncation, so
   prepare/apply stay deterministic); the `question_hash` (fold the audience in **only when a
   profile is active** — existing filed queries keep matching; a prepare/apply audience mismatch
   then fails loudly as `QUESTION_CHANGED`); `wiki-verify-multi _gather_examined` (excluded cites
   become a scalar `restricted_count` — never content, never slugs, CWE-209;
   emitted only when a profile is active). The existing
   `CITATION_NOT_RETRIEVED` gate then mechanically guarantees a restricted page can never be
   cited in a filed answer under a lower profile.

3. **Caller identity.** Self-declared profile, precedence `--audience <level>` flag > vault
   `policy.default_audience` > OFF. Cross-vault: resolve the profile from the home vault; foreign
   vocabularies fail closed. Bad value ⇒ `INVALID_AUDIENCE` exit 2, value never echoed.

4. **Whole-page granularity, deliberately.** Section-level stripping (FTS-only redaction) would
   launder the snippet while the synthesis contract still lets the orchestrator Read the cited
   body from disk — false confidence, no single enforcement point. Whole-page filtering is one
   bound clause, deterministic, hash-compatible, byte-testable. (Vendor-specific deny-globs in
   `templates/vault.claude-settings.json` remain available as documentation-level
   defense-in-depth for direct file reads.)

5. **Lifecycle.** `wiki-lint`: new `classification-leak` check (a page citing/verifying a page of
   a HIGHER level — a true contradiction ⇒ the `--strict` rail, per ADR-006 D-036-2) +
   `invalid-classification` warning (authored value outside the declared ladder). Audit: enrich
   the existing `query` log event with the cited slugs + audience (zero DDL — `details_json` is
   free-form); opt-in `wiki-query prepare --log-retrieval` closes the reads-unlogged gap (ROADMAP
   R-17). H-6 synergy: `wiki-import --classification restricted` is the standing implementation
   of the H-6 "treat `_raw/` as second-class" mitigation — a hostile capture never even presents
   its payload to a lower-audience synthesis. Policy never makes *allowed* content trusted; H-6
   armor and `sanitize_markdown_text` egress guards are unchanged.

6. **Default OFF = byte-identical.** No flag and no `policy:` block ⇒ `allowed_classifications is
   None` ⇒ no clause appended, no hash change. Acceptance for the implementing TASK: an
   ADR-005-D2-style equivalence test (OFF results ≡ pre-change results, byte-for-byte).

## Consequences

**Positive.** The last absent Karp pillar gets its honest single-operator implementation:
retrieval scope becomes a deterministic property of the layer (SQL), not a request to the model
(prompt). Subagents/critics can run least-privilege; filed Class-A artifacts stop being a leak
channel for restricted content; `_raw/` quarantine falls out for free; the same primitive gives
cross-vault bleed control. All hard invariants hold: zero DDL (rides `frontmatter_json` on the
ADR-005-accepted unindexed path), derive-don't-author (only an *optional* key + derived
defaults), vendor-agnostic (flags/env/config — no vendor tool or hook), Class A canonical.

**Cost / risk.** The `wiki-query` slice is the risky part (hash fold + `_follow_edges` gate must
be identical in prepare and apply); the predicate rides the unindexed metadata scan — acceptable
per ADR-005 (sparse field; revisit trigger = a >1k-page partition filtering routinely). Operator
discipline is still required (an unclassified sensitive page is `default_level`); lint's leak
check is the safety net, not a guarantee.

**Alternatives rejected.** (a) Prompt-layer-only ("ask the model nicely") — the exact
anti-pattern; H-6 stays open by design. (b) Per-vault `index_db` islands as the only control —
already exist, but all-or-nothing and unusable within one vault. (c) Postgres RLS / users table /
redaction engine / crypto — no identity exists to hang them on; trigger-gated multi-tenant scope.
(d) Field-level redaction — needs a field schema that doesn't exist; violates derive-don't-author;
whole-page subsumes it at this scale.

## Verification (for the implementing TASK)

OFF-equivalence test (byte-identical results + unchanged `question_hash` with no profile);
fail-closed test (unknown level excluded); `_follow_edges` prepare/apply determinism under a
profile; `CITATION_NOT_RETRIEVED` on an out-of-tier citation; `classification-leak` /
`invalid-classification` lint fixtures; `restricted_count` is count-only and absent under OFF; `mypy --strict`;
full suite green. Grep-gate: no `import anthropic` (Decision-17 untouched).
