# TASK 049 — Policy-before-model retrieval scoping (`classification:` + `--audience`)

## 0. Meta Information
- **Task ID**: 049
- **Slug**: policy-before-model
- **Depends on**: ADR-009 (Proposed → this task realizes it), ROADMAP R-16
- **Decision history**: ADR-009 landed 2026-07-07 (analysis-only pass: Karp/Palantir
  ontology-layer gap audit — pillar 3 "policy enforced before data reaches the model" is
  the one fully-absent pillar). User approved implementation of R-16 as one TASK.

## Problem / Motivation

Every retrieval surface hands ANY indexed page to the orchestrator model: `wiki-search`,
`wiki-query prepare/apply` (incl. `--follow-edges` graph expansion), `wiki-verify-multi`
critics. There is no classification/audience construct anywhere (grep-null, security.md §7:
authZ = file permissions). The only guard is prompt-layer H-6 armor — the "hand it
everything and ask it to keep secrets" anti-pattern. Consequences:

1. A hostile `_raw/` import presents its injection payload to every synthesis (H-6 open).
2. Restricted content leaks into **durable Class-A artifacts** (`_queries/*.md`,
   verification pages) that get committed/synced/read downstream.
3. `--vaults all` (the `_global_` sentinel → `vaults=None` → no vault predicate) bleeds
   any vault's private pages into any other vault's answer.
4. Subagents/critics cannot be run least-privilege.

## Goal

An **optional, default-OFF** retrieval-scope policy layer: an ordered classification
ladder, resolved per page from Class-A state, enforced as **one bound SQL predicate
BEFORE content enters any retrieval envelope**. Zero DDL. Vendor-agnostic (pure CLI
flags + config — identical under claude/codex/gemini/pi/hermes). No prompt-layer
dependence. **No flag + no `policy:` block ⇒ provably byte-identical behavior.**

**Honest boundary (verbatim in all docs):** this scopes *what a model invocation sees*
(least-privilege for cooperating agents; leak containment for filed artifacts and
cross-vault retrieval). It is NOT security against the machine's owner — the operator
holds the files and the DB. Real multi-user authZ stays trigger-gated (ROADMAP P3).

## Design (pinned against current code)

### D1. Class A expression + policy resolution
- Page key (optional): `classification: <level>`. Absent ⇒ vault `default_level`
  (unclassified = lowest — derive-don't-author; no page ever *needs* the key).
- Vault block (optional), in `WIKI_SCHEMA.md` frontmatter (read via the existing
  `load_root_config(vault_root)` — `config_loader.py:206`, which already merges the
  `CLAUDE.md::wiki:` overlay):

  ```yaml
  policy:
    levels: [public, internal, restricted]   # ordered low→high; per-vault
    default_level: public                    # level assumed when the page key is absent
    default_audience: internal               # OPTIONAL: profile when no flag is given
  ```

- **Activation precedence** (pins ADR-009's "defaults to highest ⇒ OFF" precisely —
  Q-049-1): `--audience <level>` flag → active at that level; else
  `policy.default_audience` *if declared* → active **even when it equals the highest
  level** (a declared audience always activates the layer and folds the hash — no
  max-level special case, whose semantics would silently flip if a new top level were
  later added); else **OFF** (`resolve_policy` returns `None`; nothing changes).
  The template/example therefore shows a MID level; docs state plainly that declaring
  `default_audience` on an existing vault causes a one-time `is_unchanged=false` /
  hash re-key on filed queries.
- `--audience` given but no `policy:` block resolvable ⇒ the **built-in ladder**
  `[public, internal, restricted]` applies (flag usable out of the box). "Not
  resolvable" = absent block / not a vault — a PRESENT-but-malformed block (or
  an unreadable config that visibly declares `policy:`) fails LOUD as
  `INVALID_POLICY` even with a flag, never the built-in fallback (vdd-multi
  SEC-3 / logic-LOW-5 reconciliation).
- New pure module `scripts/wiki_index/policy.py`: frozen `PolicyProfile(levels,
  default_level, audience)`, `resolve_policy(vault_root, flag) -> PolicyProfile | None`,
  `allowed_levels(profile)` (= levels up to and incl. audience), `effective_level(fm,
  default)`. Validation: levels = non-empty unique list of `[a-z][a-z0-9_-]*` strings
  (≤16), `default_level`/`default_audience`/flag ∈ levels. Violation → typed error the
  CLIs map to `INVALID_AUDIENCE`/`INVALID_POLICY` exit 2 — **never echoing the value**
  (CWE-209/117).
- Schema: `$defs/PolicyConfig` added to `config/wiki-config.schema.yaml` + a `policy`
  property on `WikiRootConfig` (DiD — strict validation lives in `policy.py`, since
  `load_root_config` alone does not schema-validate); `policy` **banned** in
  `WikiProjectOverride` (like `vault_id`/`index_db` — a subdir override must not weaken
  the vault's policy).
- Cross-vault (`--vaults all`): the profile is resolved from the HOME vault and its
  allowed-level list applies uniformly; a foreign vault's unknown level strings **fail
  closed** (excluded) via the `IN`-clause property.

### D2. DAL — one choke point, pre-LIMIT
`search_pages` (ABC `repository.py:155`, impl `sqlite_repository.py:594`) gains two
keyword params: `allowed_classifications: list[str] | None = None`,
`classification_default: str | None = None`. When not None, append to the shared
`clause_parts` (built once for all three query shapes — FTS, metadata scan,
FTS-narrowed; `sqlite_repository.py:632`):

```sql
AND COALESCE(CAST(json_extract(p.frontmatter_json, '$.classification') AS TEXT), ?)
    IN (?,...)
```

Fixed literal JSON path; default + every level bound as parameters (the repo's
no-f-string-values posture). Because `clause_parts` is shared and applied **before
LIMIT** (the `exclude_types` precedent, `:642-647`), a filtered page never consumes a
result slot on ANY path. `CAST` normalizes a numeric/boolean authored value to text
(same rationale as the `--where` scalar branch). Unknown values (typos, foreign
ladders) are excluded automatically — fail-closed. **Library-caller defense
(arch-review MED-2):** the params are both-or-neither — `allowed_classifications`
without `classification_default` raises `ValueError` in the DAL (mirroring the
`where_fields` re-validation posture) so an unclassified page can never silently
vanish via `COALESCE(NULL, NULL)`. An explicitly-authored `classification: null` is
JSON-null → `COALESCE` picks `default_level` — i.e. **null ≡ absent** (test-pinned).

### D3. `wiki-search --audience <level>`
Resolve the profile via `resolve_vault_root_for_cli(args)` (walk-up; outside a vault
with no flag ⇒ OFF). Bad flag value ⇒ `INVALID_AUDIENCE` exit 2, value never echoed
(mirrors `INVALID_FILTER`). Active profile ⇒ pass `allowed_classifications` +
`classification_default` into both `search_pages` calls (`wiki_search.py:202,218`);
echo `"audience": <level>` in the JSON envelope.

### D4. `wiki-query --audience <level>` (the risky slice)
- Flag on BOTH `prepare` and `apply` subparsers (like `--exact`/`--follow-edges`:
  "MUST match or the question_hash diverges → QUESTION_CHANGED").
- `_retrieve` (`wiki_query.py:241`, shared prepare/apply) resolves the profile once and
  threads allowed/default into `repo.search_pages` — covers the FTS path AND the DF-1
  quoted-phrase fallback identically.
- `_follow_edges` (`wiki_query.py:187`): per-page gate — after `repo.get_page`, skip
  when `effective_level(page.frontmatter_json, default) ∉ allowed` (exactly like the
  existing `type in ("query","verification")` skip at `:230`), **inside** the sorted
  stream and before the `_MAX_EDGE_PULLED` truncation, so expansion stays deterministic
  and identical across prepare/apply.
- `_question_hash` (`wiki_query.py:87`): fold the audience **only when a profile is
  active** — `parts.append("\x00audience:" + audience)` after the hit list. OFF ⇒ hash
  bytes unchanged ⇒ existing filed queries' recorded `check_query_state` hashes still
  match (`is_unchanged` keeps working). A prepare/apply audience mismatch then fails
  loudly as the existing `QUESTION_CHANGED` (exit 2, `:488`).
- Grounding gate hardening **for free**: filtered pages never enter `hits`, so
  `CITATION_NOT_RETRIEVED` (`:533`) mechanically blocks citing a restricted page in a
  filed `_queries/` answer under a lower profile. (Add a test, not code.)
- Envelope: `prepare`/`apply` echo `"audience": <level>` when active.
- Contract prose: `skills/wiki-query-synthesis/SKILL.md` same-flags list + parser
  epilogs gain `--audience`.

### D5. `wiki-verify-multi --audience <level>`
Flag on `prepare` AND `apply` (the examined set feeds `_verify_hash` — asymmetry would
break the grounding gate, same reason as the `_MAX_CITES` cap being in the shared
helper). `_gather_examined` (`wiki_verify_multi.py:139`) gains the gate: a cite whose
resolved page level ∉ allowed is EXCLUDED from `examined` and counted in a new envelope
field `"restricted_count": N` (count only — never content, never slugs; CWE-209
posture). **The field is emitted only when a profile is active — absent under OFF**
(NFR-1 byte-identity; same rule for every audience-related envelope key in D3/D4).
Missing/malformed cites keep their existing `missing` semantics. (ADR-009 named this
field `restricted_cites[]`; renamed to the scalar `restricted_count` — reconcile the
ADR in R-8.)

### D6. Lint — leak + vocabulary checks (`wiki-lint`, ADR-006 posture)
- `check_classification_leak` (new, in `lint.py` beside `check_lifecycle_drift`
  `:176-210`): a page whose `cited`/`verifies` ref targets a page with a **higher**
  effective level than its own — a filed answer that would republish restricted
  content. True contradiction ⇒ severity warning → **error under `--strict`**.
- `invalid-classification` (same new check's second output): an authored
  `classification` text value not in the vault's declared ladder — explains fail-closed
  exclusions. Severity: warning (not strict-gated — an authoring slip, not a graph
  contradiction).
- DAL `find_classification_leaks(vault_id, levels, default_level)` in
  `sqlite_repository.py` (+ ABC): SQL fetches candidate `('cited','verifies')` ref
  pairs joined src×target pages — target join guarded by the **COUNT=1 same-slug
  pattern** (as-of walk `:706-711`; a project-less `entity_slug` must not flag an
  unrelated same-slug page) — plus both sides' `json_extract($.classification)`;
  **rank comparison in Python** (partitions are small; avoids SQL rank gymnastics).
  All values bound.
- Wiring: in `run_all_checks` (`lint.py:34`) per-vault, gated on the vault actually
  declaring a `policy:` block (`load_root_config(v.root_path)` in a try/except —
  unreadable/absent schema file ⇒ skip silently). No policy ⇒ no DAL call, no output —
  the R-15 no-op precedent.

### D7. `wiki-import --classification <level>` (opt-in stamp)
New flag: stamps `classification: <level>` into the authored note's frontmatter AND the
`_raw/<slug>.md` capture's frontmatter. Value validated by shape only
(`[a-z][a-z0-9_-]{0,15}` — same ≤16 cap as a policy level, D1) — the vault may not
declare a ladder; an out-of-ladder value is lint's job (`invalid-classification`). This is the standing implementation of the
KNOWN_ISSUES **H-6 "`_raw/` second-class"** mitigation: a hostile capture classified
`restricted` never presents its payload to a lower-audience synthesis.

### Out of scope (recorded)
Audit enrichment (cited slugs / `WIKI_ACTOR_ID` / `--log-retrieval`) = **R-17**, next
task. Folder-glob `classification_paths` defaults = Phase 2 of R-16 (needs the
normalize-time injection path; deferred). Users/roles/identity store, crypto, RLS,
field-level redaction, MCP policy server: rejected in ADR-009 — do not re-open.
Section-level redaction: rejected (launders the snippet; the synthesis contract reads
cited bodies from disk). **`wiki-graph` stays unscoped** — it returns edge
structure/titles, not page bodies, and is not a synthesis feed; R-16 covers only
model-feeding retrieval surfaces (revisit only if graph output starts carrying
bodies). **Class-B renders + extract-concepts derivation stay unscoped**
(arch-review LOW-3): `wiki-index-render` ledgers/`index.md` still surface restricted
pages' titles/slugs into committed Class-B artifacts, and operator-directed
`wiki-extract-concepts` derives unclassified `_concepts/` pages from a restricted
source — metadata/derivation channels, not retrieval envelopes; "leak containment"
claims cover filed `_queries/`/verification pages only (reconcile the ADR-009
"index.md renders" mention in R-8). **Accepted limitation (Q-049-2 note):** query pages carry no audience marker —
a lower-audience re-query of the same question re-files the same `_queries/<slug>.md`
(intentional re-synthesis under the new scope; the content-hash skip plus
`QUESTION_CHANGED` on stale hashes make this loud, not silent).

## Requirements (RTM)

| ID | Requirement | Verification |
|---|---|---|
| **R-1** | `policy.py`: `PolicyProfile`/`resolve_policy`/`allowed_levels`/`effective_level`; precedence flag > `default_audience` > OFF; built-in ladder for flag-without-block; strict value validation, no value echo. Schema: `$defs/PolicyConfig` in `config/wiki-config.schema.yaml`; `policy` banned in `WikiProjectOverride` | unit tests: precedence matrix, bad-ladder/bad-level rejection, CWE-209 message shape; schema tests: PolicyConfig validates, a `.wiki.yaml` carrying `policy` is rejected |
| **R-2** | `search_pages` classification predicate: pre-LIMIT, all three query shapes, `COALESCE+CAST+IN` all-bound, fail-closed on unknown values (incl. a foreign vault's ladder under `--vaults all` / `_global_`) | DAL tests incl. LIMIT-window test (restricted page must not evict a visible hit), FTS + scan + FTS-narrowed paths, unknown-label exclusion, cross-vault foreign-label fail-closed, `classification: null` ≡ absent, both-or-neither param `ValueError` |
| **R-3** | `wiki-search --audience`: profile resolution (HOME vault under cross-vault scope), `INVALID_AUDIENCE` exit 2, envelope `audience` echo **only when active** | CLI tests; no-vault-root + flag ⇒ built-in ladder; `--vaults all` + `--audience` ⇒ home profile applied uniformly (UC-7) |
| **R-4** | `wiki-query --audience` on prepare+apply: `_retrieve` plumb (FTS + DF-1 fallback), `_follow_edges` per-page gate pre-truncation, hash fold only-when-active, `QUESTION_CHANGED` on mismatch, `CITATION_NOT_RETRIEVED` blocks out-of-tier cites; envelope `audience` echo **only when active** | e2e: prepare→apply round-trip under profile; mismatch test; edge-gate determinism test; out-of-tier citation test |
| **R-5** | `wiki-verify-multi --audience` prepare+apply symmetric; excluded cites → `restricted_count` (count only, **emitted only when active**) | tests: examined-set symmetry, envelope field presence/absence, no content/slug leak |
| **R-6** | lint: `classification-leak` (strict-gated) + `invalid-classification` (warning); DAL `find_classification_leaks` with COUNT=1 guard; no-op without `policy:` block | lint fixtures: leak via `cites:`, leak via `verifies:`, same-slug-two-projects non-flag, invalid value, policy-less vault silence |
| **R-7** | `wiki-import --classification` stamps note + `_raw` frontmatter; shape-validated | import test: frontmatter carries the key on both files; bad shape exit 2 |
| **R-8** | Docs: `templates/WIKI_SCHEMA.md.tmpl` policy block (mid-level `default_audience` example + hash-re-key warning); `skills/wiki-query-synthesis/SKILL.md` same-flags; wiki-search/wiki-query/wiki-verify-multi/wiki-import SKILL.md flag docs; ADR-009 → Accepted **with body reconciliation** (Q-049-1 precedence pin replaces "highest⇒OFF"; `restricted_cites[]`→`restricted_count`; `CAST` added to the SQL snippet; "index.md renders" leak-containment claim narrowed to Class-A filed artifacts); ROADMAP R-16 → SHIPPED; ARCHITECTURE §2/§5/§7 + Q-049-* rationale; H-6 issue file mitigation note | doc diff review; lint PW-Q clean (edit per-issue file, re-render ledger) |
| **NFR-1** | **OFF ≡ byte-identical**: no flag + no block ⇒ no SQL clause, unchanged `question_hash`, unchanged envelopes | ADR-005-D2-style equivalence test (OFF results ≡ pre-change, hash stability against a recorded fixture) |
| **NFR-2** | Vendor-agnostic + Decision-17: flags/config only, no vendor tool/hook, no `import anthropic` | grep gate; no new deps |
| **NFR-3** | Zero DDL: `user_version` stays 7; no new column/index/table | schema file untouched; `wiki-reindex --full` round-trip green |
| **NFR-4** | CWE-209/117: no flag/config/frontmatter VALUE echoed in any error or lint surface beyond the allow-listed level names the operator themself declared | error-message tests |
| **NFR-5** | `mypy --strict scripts/` clean; full pytest suite green | CI commands |

## Use Cases

- **UC-1** Operator scopes a search: `wiki-search v "salary" --audience internal` — the
  `restricted` HR page is absent from hits AND cannot have consumed a top-limit slot.
- **UC-2** RAG under low audience: prepare→synthesise→apply with `--audience internal`;
  a citation naming a restricted page fails `CITATION_NOT_RETRIEVED`; the filed
  `_queries/` page can never republish restricted content.
- **UC-3** Least-privilege critics: `wiki-verify-multi prepare --audience public` — a
  restricted cited source is excluded from every critic envelope (`restricted_count`).
- **UC-4** Leak detection: a public digest page `cites:` a restricted source →
  `wiki-lint` reports `classification-leak`; gates CI under `--strict`.
- **UC-5** Existing vaults: no `policy:` block anywhere ⇒ every CLI behaves
  byte-identically to today (equivalence test).
- **UC-6** Hostile import quarantine: `wiki-import <url> --classification restricted` ⇒
  the capture and note never enter a lower-audience retrieval envelope (H-6 mitigation).
- **UC-7** Cross-vault scope: `wiki-search --vaults all --audience internal` from vault
  A — A's ladder applies uniformly; vault B's pages labeled with B's own (unknown to A)
  levels are excluded (fail-closed), never silently included.

## Invariants that must not break
Class A/B/C (ADR-002 §D8) — `classification` is authored Class A, mirrored via the
existing `frontmatter_json` path; **zero DDL** (`user_version` 7); Decision-17 (no
`import anthropic`); H-6 (policy is an ingress gate — allowed content stays UNTRUSTED
data; egress sanitizers unchanged); Karpathy byte-identity (no layout/indexer change);
`question_hash` back-compat (fold only-when-active); vendor-agnostic NF-1.

## Open Questions
None blocking. Q-049-1 (activation precedence pin), Q-049-2 (whole-page vs
section-level — resolved: whole-page), Q-049-3 (COUNT=1 leak-join guard) to be recorded
in `docs/architectures/open-questions.md` during the Architecture phase.
