# PLAN 049 — Policy-before-model retrieval scoping

Phases by dependency: **P1 (foundation) → P2 (enforcement) → P3 (lint + import) → P4
(docs)**. Stub-first within each phase (signatures + RED tests → GREEN). RTM IDs
(R-1…R-8, NFR-1…5) from `docs/TASK.md`. Single developer pass; every bead ends with
the full suite green (`pytest -q`) + `mypy --strict scripts/`.

## P1 — Foundation (R-1, R-2, NFR-1, NFR-3)

**049-01 `policy.py` module** — new `scripts/wiki_index/policy.py`:
`PolicyError(ValueError)`, frozen `PolicyProfile(levels: tuple[str, ...],
default_level: str, audience: str)`, `BUILTIN_LEVELS = ("public", "internal",
"restricted")`, `_LEVEL_RE = [a-z][a-z0-9_-]{0,15}` (≤16), `parse_policy_block(raw:
object) -> tuple[levels, default_level, default_audience|None]` (strict shape
validation, no value echo — messages name the field only), `resolve_policy(vault_root:
Path | None, audience_flag: str | None) -> PolicyProfile | None` (precedence per
Q-049-1: flag > declared `default_audience` > OFF; flag-without-block ⇒ built-in
ladder; reads the block via `config_loader.load_root_config`, absent/unreadable
`WIKI_SCHEMA.md` ⇒ no block), `allowed_levels(profile) -> list[str]`,
`effective_level(fm: dict | None, default_level: str) -> str` (non-str/None ⇒
default — null ≡ absent). Tests `tests/test_policy.py`: precedence matrix (8 cases),
bad ladder (dup/empty/shape/oversize), flag ∉ levels, default_level ∉ levels, CWE-209
message shape, effective_level null/absent/non-str.

**049-02 DAL predicate** — `repository.py` ABC + `sqlite_repository.py`
`search_pages`: new kwargs `allowed_classifications: list[str] | None = None`,
`classification_default: str | None = None`; both-or-neither guard (`ValueError`);
clause appended to the shared `clause_parts`:
`AND COALESCE(CAST(json_extract(p.frontmatter_json, '$.classification') AS TEXT), ?)
IN (…placeholders…)` — params `[default, *levels]`. Tests
`tests/test_search_classification.py` (new): fixture vault with
public/internal/restricted/unlabeled/null-labeled/foreign-labeled pages; assert (a)
FTS path, (b) metadata-scan path, (c) FTS-narrowed `--tag` path all filter identically;
(d) LIMIT-window: restricted page must not evict a visible hit (limit=1 test); (e)
unknown/foreign label excluded; (f) null ≡ absent ≡ default_level; (g) both-or-neither
ValueError; (h) **OFF-equivalence**: `allowed_classifications=None` ⇒ results
byte-identical to a pre-change golden (reuse the ADR-005 D2 equivalence pattern —
same query, both modes, assert equal lists).

## P2 — Enforcement surfaces (R-3, R-4, R-5, NFR-1, NFR-4)

**049-03 `wiki-search --audience`** — flag; resolve profile
(`resolve_vault_root_for_cli` → `resolve_policy`); `PolicyError` →
`INVALID_AUDIENCE` exit 2 (no value echo); thread allowed/default into BOTH
`search_pages` calls; envelope gains `"audience": <level>` **only when active**.
Tests: CLI e2e under profile (restricted page absent), OFF envelope has no `audience`
key, bad flag exit 2, flag-without-vault-root uses built-in ladder, `--vaults all`
home-profile (UC-7).

**049-04 `wiki-query --audience`** — flag on `prepare` + `apply` subparsers (epilog:
MUST match, like `--exact`/`--follow-edges`); **profile resolved at the top of
`prepare` and of `apply`** (plan-review F2 — `_question_hash` and the envelope echo
live there, `:359`/`:488`), then threaded down: allowed/default into `_retrieve` →
the `_search` closure (covers FTS + DF-1 fallback); `_follow_edges`
gains `allowed`/`default` params — per-page skip after `get_page` (like the
type-skip), before `_MAX_EDGE_PULLED` truncation; `_question_hash(question, hits,
audience=None)` — appends `"\x00audience:" + audience` only when not None; prepare and
apply envelopes echo `audience` only when active. Tests
`tests/test_wiki_query_audience.py` (new): e2e prepare→apply round-trip under profile
(hash matches, filed page cites only visible sources); prepare@internal /
apply@(none) ⇒ `QUESTION_CHANGED`; out-of-tier citation ⇒ `CITATION_NOT_RETRIEVED`;
edge-gate determinism (restricted neighbor skipped identically in prepare+apply,
truncation stable); OFF ⇒ hash identical to a no-flag golden (NFR-1 hash-stability).

**049-05 `wiki-verify-multi --audience`** — flag on `prepare` + `apply` (MUST-match
note); resolve profile in both; `_gather_examined(..., allowed, default)` — excluded
cite → counted, not appended (shared helper keeps prepare/apply symmetric); envelope
`"restricted_count": N` only when active. Tests: symmetric examined set, field
presence/absence, no slug/content leak in envelope, verify_hash stability across
prepare/apply under the same audience.

## P3 — Lint + import (R-6, R-7)

**049-06 DAL `find_classification_leaks`** — ABC + impl: SQL over `page_entity_refs r
JOIN pages src` (composite src key) `WHERE r.vault_id=? AND r.ref_type IN
('cited','verifies')` + target join `pages tgt ON tgt.vault_id=r.vault_id AND
tgt.slug=r.entity_slug` **guarded by COUNT=1 same-slug** (Q-049-3); SELECT both sides'
`json_extract($.classification)`; return raw rows; **rank comparison in Python** in a
small helper. Returns typed hits (src slug/project/level, tgt slug/level, ref_type).
All values bound. **In-bead RED tests** (plan-review F4): direct DAL unit tests —
leak found, same-slug-two-projects skipped (COUNT=1), no-refs ⇒ empty — land in this
bead, before the lint consumer (049-07).

**049-07 lint checks** — `lint.py`: `check_classification_policy(repo, vid,
vault_root, strict)` (name it one check, two categories): reads the vault `policy:`
via `load_root_config` in try/except (no block / unreadable ⇒ `[]`, no DAL call —
R-15 no-op precedent); emits `classification-leak` (warning → **error under
--strict**) per leak (details: src/tgt slugs + levels — these are operator-declared
level names + slugs, not content) and `invalid-classification` (warning, never
strict-gated) for pages whose text-valued `$.classification` ∉ ladder (SQL:
`json_type='text' AND NOT IN`, bound). Wire into `run_all_checks` per-vault. Tests
`tests/test_lint_classification.py`: leak via `cites:`, leak via `verifies:`,
same-slug-two-projects NOT flagged (COUNT=1), invalid value flagged, null/absent not
flagged, policy-less vault silent, `--strict` severity flip for leak only.

**049-08 `wiki-import --classification`** — flag on **BOTH `prepare` and `apply`
subparsers** (plan-review F3 — the two artifacts are written in different passes):
shape-validate `[a-z][a-z0-9_-]{0,15}` → exit 2 `INVALID_CLASSIFICATION` (no echo);
stamp `classification: <level>` into (a) the `_raw/<slug>.md` frontmatter via a
**dedicated injection** — NOT riding `ensure_source_frontmatter`, whose early-return
skips captures that already carry `source:`/`url:` (`_fetch.py:208-209`) — and (b)
the authored note frontmatter (`_authoring.assemble_note` fm block). Tests: both
files carry the key (incl. a capture that already had `source:`); bad shape exit 2;
omitted flag ⇒ byte-identical output (NFR-1 for the construct path).

## P4 — Docs + closure (R-8, NFR-2)

**049-09 config schema + template** — `config/wiki-config.schema.yaml`:
`$defs/PolicyConfig` (levels/default_level/default_audience, STRICT
additionalProperties: false) + `policy: $ref` on `WikiRootConfig` + `not: required:
[policy]` added to the `WikiProjectOverride` allOf bans; `templates/WIKI_SCHEMA.md.tmpl`
documents the optional block (mid-level `default_audience` example + one-time
hash-re-key warning). Schema tests: PolicyConfig validates; `.wiki.yaml` with `policy`
rejected.

**049-10 docs sweep** — `skills/wiki-query-synthesis/SKILL.md` same-flags list +
`--audience`; SKILL.md flag docs for wiki-search / wiki-query / wiki-verify-multi /
wiki-import; ADR-009 → **Accepted** with body reconciliation (Q-049-1 pin replaces
"highest⇒OFF"; `restricted_cites[]`→`restricted_count`; CAST in the SQL snippet;
"index.md renders" claim narrowed); ROADMAP R-16 → SHIPPED one-liner; ARCHITECTURE
Quality-Checklist entry (**§2.4/§7.6/§11i Q-049-1..4 already landed in the
Architecture phase** — remaining delta is the checklist row + the §5 interfaces
summary clause); `docs/issues/h-6-*.md` mitigation note (+ re-render the
KNOWN_ISSUES ledger if the renderer applies to this repo's docs — else note-only).
Final gates: full `pytest -q`, `mypy --strict scripts/`, grep `import anthropic` → ∅,
`user_version` untouched, **`wiki-reindex --full` round-trip green on a sample vault
with classified pages** (NFR-3), **`requirements.txt` unchanged / no new imports**
(NFR-2).

## Bead order & risk

01 → 02 → 03 → 04 → 05 → 06 → 07 → 08 → 09 → 10. The risky slice is **049-04**
(hash fold + edge gate determinism) — it lands only after 01/02 are green and carries
the densest test set. NFR-1 is enforced twice: the DAL OFF-equivalence golden (049-02h)
and the wiki-query hash-stability golden (049-04). No bead touches
`sql/wiki-index-v2.sql`, `reindex.py`, or any layout YAML — Karpathy byte-identity is
structurally untouched.
