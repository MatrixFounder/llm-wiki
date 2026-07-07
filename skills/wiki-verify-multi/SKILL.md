<!-- Sync with scripts/wiki_skills/wiki_verify_multi.py argparse on every change. -->
---
name: wiki-verify-multi
description: >-
  Off-by-default multi-critic verification of a filed wiki-query answer against
  its cited sources (TASK 008 / R-8). Two deterministic subcommands — `prepare`
  (assemble the answer + cited source bodies into a verification envelope) and
  `apply` (grounding-checked verdict write-back of `_verifications/verify-<slug>.md`
  + self-index; non-zero exit on FAIL; never mutates the answer). The orchestrator
  owns the four-critic audit between them (Decision-17): no `import anthropic`.
  Triggers: "verify the answer", "wiki-verify-multi".
tier: 2
version: 1.0
---

# wiki-verify-multi (R-8)

**Purpose**: the verification half of the high-stakes RAG loop — take a filed
`_queries/<slug>.md` answer, independently audit it against the actual bodies of
its cited sources with a **four-critic ensemble** (factual-grounding /
logic-coherence / security-injection / completeness-faithfulness), and file a
durable, indexed, back-linked `_verifications/verify-<slug>.md` verdict page +
signal PASS/FAIL via the exit code. **Off by default** — `wiki-query` never
invokes it.

Like `wiki-query`, this is a **deterministic two-pass skill** (Decision-17): the
four-critic reasoning lives in the calling agent's context via the
[`wiki-verify`](../wiki-verify/SKILL.md) prompt skill. No `import anthropic`,
no `--model`. End-to-end recipe: [`workflows/wiki-verify-multi.md`](../../workflows/wiki-verify-multi.md).

## `prepare` subcommand

```bash
wiki-verify-multi prepare <query-slug> \
    --vault <vault-id> --vault-root <path> \
    [--slug <kebab>] [--audience <level>] [--db-path <override>]
```

Loads the audited `type=query` page (vault-tier) + its `cites:` source bodies —
**read via the stored `pages.file_path`** (layout-agnostic; never reconstructs
`<subdir>/<slug>.md`). No LLM call. Output envelope (exit 0):
`{vault_id, query_slug, question, answer_excerpt, answer_hash, verify_hash,
is_unchanged, verification_slug, examined[], examined_count, missing_cites[]}`.

| Flag | Notes |
|---|---|
| `<query-slug>` | the slug of the filed `_queries/<slug>.md` to verify (positional). |
| `--slug` | override the derived verification slug. **Default: `verify-<query-slug>`** — a *distinct* slug so the verdict page does not collide with the audited query page on the `pages` PK `(vault_id, slug, project)`. |
| `is_unchanged` | true → a prior identical verdict exists; the orchestrator short-circuits. |

`NO_SOURCES` (exit 2) if the query page cites nothing (refuse to verify an answer
with no sources). A cited slug with no indexed `pages` row is excluded from
`examined` and reported in `missing_cites`.

**Policy scope (TASK 049 / ADR-009)** — `--audience <level>` runs the critics
least-privilege: a cited source classified ABOVE the level is excluded from
`examined` **before its body is read** and only counted in a `restricted_count`
envelope field (never named — the critics must not learn what was withheld).
MUST match the value passed to `apply` (the examined set feeds `verify_hash` +
the grounding gate); pass prepare's `verify_hash` to `apply --verify-hash` — a
drifted audience/examined set then fails loudly as `VERIFY_CONTEXT_CHANGED`
(exit 2) instead of filing a verdict under the wrong scope. Absent under OFF;
all cites restricted → `NO_SOURCES`. Note the "count only, never slugs" claim
holds for the envelope IN ISOLATION: a party that also holds the query page's
`cites:` list can derive the restricted members by set difference — acceptable
within the honest boundary (the orchestrator owns the vault), but a
least-privilege critic given only the envelope cannot.

## `apply` subcommand

```bash
wiki-verify-multi apply \
    --vault <vault-id> --vault-root <path> \
    --verification-slug <slug-from-prepare> \
    --query-slug <query-slug> \
    --answer-hash <hash-from-prepare> \
    --verify-hash <hash-from-prepare> \
    (--verdict-stdin | --verdict-file <path>) \
    [--fail-on {critical,high,medium,low,none}] \
    [--audience <level>] \
    [--orchestrator-id <id>] [--force] [--db-path <override>]
```

Grounding-checked verdict write-back + self-index. No LLM call.

- `--answer-hash HEX` — **required**; the value `prepare` emitted (64 hex). `apply`
  re-reads the query page + recomputes it; mismatch → `ANSWER_CHANGED` (exit 2 —
  the answer changed mid-pipeline; re-run).
- `--verdict-stdin | --verdict-file` (mutex) — the orchestrator's verdict JSON
  (≤256 KiB; file form vault-inside + `O_NOFOLLOW`). See `wiki-verify` for the schema.
- `--fail-on` — verdict severity threshold (default **`high`**, Q-008-e): FAIL iff
  any `factual`/`security` finding ≥ threshold; `none` → always exit 0.
- **The Class-A `_queries/<slug>.md` answer is NEVER mutated** (D-008-3).

Success envelope: `{vault_id, verification_slug, verifies, verdict, page_indexed, action}`.
The verdict page is Class A (`_verifications/verify-<slug>.md`: `type: verification`,
`verifies:`, `verdict:`, `critics:`, `answer_hash:`, `cites:`, `tags:[verification]`),
then **self-indexed via direct `upsert_page` + `replace_refs`** (a `pages` row
`type=verification` + a `verifies` `page_entity_ref` to the query page + a `verify`
log event). `wiki-reindex --full` rebuilds the `verifies` ref from the `verifies:`
frontmatter (R-8.5e).

## Exit codes

| Code | `error` | Cause |
|---|---|---|
| 0 | — (envelope / `is_unchanged` / `unchanged` / PASS / `--fail-on=none`) | success / short-circuit |
| 1 | — (argparse) | missing flag / no subcommand |
| 2 | `QUERY_NOT_FOUND` / `NO_SOURCES` | no `type=query` page / it cites nothing |
| 2 | `ANSWER_CHANGED` / `INVALID_ANSWER_HASH` / `INVALID_SLUG` / `INVALID_VAULT_ROOT` | answer moved mid-pipeline / bad hash / bad slug / bad root |
| 2 | `VERIFY_CONTEXT_CHANGED` / `INVALID_AUDIENCE` / `INVALID_POLICY` | TASK 049: examined set / audience drifted since prepare / bad level / malformed vault policy block |
| 4 | `INVALID_VERDICT` / `VERDICT_PARSE_ERROR` / `VERDICT_TOO_LARGE` | verdict JSON malformed / not JSON / over-cap |
| 4 | `FINDING_SOURCE_NOT_EXAMINED` | a finding cites a source not in the examined set (grounding gate) |
| 4 | `INVALID_VERIFICATION_PAGE` | target `_verifications/<slug>.md` is a symlink (refused) |
| **6** | **`VERDICT_FAIL`** | a `fail` verdict at/above `--fail-on`. **The verdict page IS still filed** — a SUCCESS envelope (no `error` key). **Deliberate divergence** from the family's `6 = error` convention: callers MUST branch on the **stdout envelope** (`verdict:"fail"`), not `$? == 6`. |

**Universal envelope invariant** (CWE-117/209): error envelopes carry `{error,
field?, reason}` only — never the offending answer/source/finding/verdict value.

## Related

- [`workflows/wiki-verify-multi.md`](../../workflows/wiki-verify-multi.md) — end-to-end recipe.
- [`skills/wiki-verify/SKILL.md`](../wiki-verify/SKILL.md) — the four-critic verdict prompt + JSON contract (**SECURITY-SENSITIVE**).
- `wiki-query` — the RAG answer this layer verifies; `docs/ARCHITECTURE.md` §2 Verification Layer + §4 Data Model (verification page, `verifies` ref, R-8.5e).
