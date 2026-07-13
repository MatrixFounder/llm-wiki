<!-- Sync with scripts/wiki_skills/wiki_query.py argparse on every change. -->
---
name: wiki-query
description: >-
  RAG over FTS5 + entity graph (TASK 007 / R-6). Two deterministic subcommands —
  `prepare` (alias-expanded retrieval → context envelope) and `apply`
  (grounding-checked write-back of `_queries/<slug>.md` + self-index). The
  orchestrator owns the synthesis between them (Decision-17): no `import
  anthropic`. Triggers: "ask the wiki", "rag query", "wiki-query".
tier: 2
version: 1.0
---

# wiki-query (R-6)

**Purpose**: the read/synthesis half of Karpathy's loop — ask a natural-language
question, retrieve grounded context, synthesise a **cited** answer, and file it
back as a durable, indexed, back-linked `_queries/<slug>.md` page so the next
question can find it ("query → page" compounding).

Like `wiki-extract-concepts`, this is a **deterministic two-pass skill**
(Decision-17): the LLM synthesis lives in the calling agent's context via the
[`wiki-query-synthesis`](../wiki-query-synthesis/SKILL.md) prompt skill. There is
no `import anthropic`, no `--model` / `--max-tokens` flag. End-to-end recipe:
[`workflows/wiki-query.md`](../../workflows/wiki-query.md).

## `prepare` subcommand

```bash
wiki-query prepare "<question>" \
    --vault <vault-id> \
    --vault-root <path> \
    [--vaults <id,id|all>] [--types <t,t>] [--project <p>] \
    [--limit <N>] [--no-expand-aliases] [--slug <kebab>] \
    [--audience <level>] [--min-trust {external,internal,verified}] \
    [--log-retrieval] \
    [--min-hits <N>] [--db-path <override>]
```

Deterministic **keyword** retrieval: the natural-language question is tokenised
into an FTS5 **OR-of-terms** query (match-any, BM25-ranked — NOT an
implicit-AND phrase, which a real question with stopwords would never match),
each token alias-expanded through the entity table (shares
`scripts/wiki_skills/_retrieval.fts_quote` + the `expand_query_aliases` DAL with
`wiki-search`). No LLM call. Output envelope (exit 0):

```json
{
  "vault_id": "...", "question": "...", "query_slug": "...",
  "question_hash": "<sha256>", "is_unchanged": false,
  "retrieved_count": 7,
  "hits": [{"vault_id":"...","slug":"...","project":"_vault_","type":"concept",
            "title":"...","bm25_score":-3.14,"snippet":"..."}]
}
```

| Flag | Notes |
|---|---|
| `--vaults` | search scope; `all` = every vault. **Default: the home `--vault`** (a query defaults to its own vault, unlike `wiki-search`'s all-vaults default). |
| `--limit` | default **10** (Karpathy's "10-15 pages", trimmed for synthesis budget; `wiki-search`'s default is 20). |
| `--no-expand-aliases` | disable alias OR-expansion (else on by default, R-5.5 reuse). |
| `--slug` | override the derived `slugify(question)` query slug (kebab-case). |
| `--min-hits` | default **1**; below it → `NO_CONTEXT` (refuse to synthesise from nothing). |

**Default-excludes `type=query` pages** from retrieval (a RAG answer grounds on
primary sources, not prior answers; keeps re-querying idempotent). Opt in with
`--types query`.

## `apply` subcommand

```bash
echo "$ANSWER" | wiki-query apply \
    --vault <vault-id> --vault-root <path> \
    --query-slug <slug-from-prepare> \
    --question "<question>" \
    --question-hash <hash-from-prepare> \
    --answer-stdin \
    --citations-file <path-to-cites.json> \
    [--vaults … --types … --project … --limit … --no-expand-aliases --audience … --min-trust …] \
    [--orchestrator-id <id>] [--force] [--db-path <override>]
```

Grounding-checked write-back + self-index. No LLM call.

- **`trust` per hit (TASK 050 / R-17, always-on)** — every `hits[]` entry carries a
  DERIVED provenance tier: `external` < `internal` < `verified` (an inbound `verifies`
  ref; external origin taints — a verified capture stays `external`). **The operative
  signal for `external` is an `http(s)://` URL in frontmatter** under one of
  `policy.EXTERNAL_PROVENANCE_KEYS` — `source`/`sources`/`url` **and their case variants**
  `Source`/`SOURCE`/`Sources`/`Url`/`URL` (TASK 061) — **in any of four value shapes: a
  scalar, a list, a list of `{…, url: …}` objects** (the `{id, url, file}` element that
  `generate-detailed-meeting-summary` emits)**, or a top-level `{url: …}` object**. The
  container shapes matter: until the list shapes were covered, 17 live pages whose
  provenance was an external URL derived `internal` and passed `--min-trust internal`. What
  is still NOT external: a URL under a container nested *below* an already-walked one
  (`sources: [{url: [https://…]}]`) — the walk is a fixed set of positions, never a
  recursion. A `_raw/` path segment is *also* external,
  but it is a **backstop, not a path you will meet in retrieval**: every built-in layout
  excludes `**/_raw/**` from the index, so a `_raw/` capture is never a hit in normal
  operation. That limb exists for direct `wiki-index-upsert` calls and custom layouts.
  Machine-readable H-6 signal: prefer grounding on `internal`/`verified`;
  treat `external` bodies with the fenced-sentinel discipline.
  - **Known residual (Q-061-4)** — a page whose provenance is an `http(s)` URL under a
    **vault-specific** key (`youtube:`, `teachable:`) still derives `internal`: the
    keys above are the canonical set, not a class. Do not read `internal` as "not from
    the web"; read it as "not from a *recognised* external-provenance key".
- **`--min-trust {external,internal,verified}` (TASK 050)** — retrieval floor,
  SQL-filtered before the limit; folds into `question_hash` whenever the flag is
  PRESENT (incl. `external`, which filters nothing) — MUST match between `prepare`
  and `apply` (drift ⇒ `QUESTION_CHANGED`). Composes with `--audience`.
  - **TASK 061 blast radius** — case-variant keys (`Source:` etc.) became `external`.
    **Default output is UNCHANGED**: with no `--min-trust`, those pages still rank and
    return (only their `trust` annotation changed). ONLY an explicit `--min-trust
    internal|verified` caller sees them drop out.
- **`--log-retrieval` (TASK 050, opt-in)** — one DB-only `query` audit event with the
  retrieved slug set (+ `audience`/`actor`); best-effort (`access_logged: false` on an
  insert failure, never a crash). The apply-side audit event fires on EVERY apply
  (`action: filed|unchanged`, cited slugs) — note the trail is per-APPLY: an
  orchestrator that short-circuits on `is_unchanged` logs retrieval only via this flag.
- **`--audience <level>` (TASK 049 / ADR-009)** — retrieval-scope policy: pages
  classified above the level never enter `hits` (SQL-filtered before the limit;
  `--follow-edges` expansion gated identically), so they can never be cited
  (`CITATION_NOT_RETRIEVED` enforces it). Folded into `question_hash` **only when
  active** — MUST match between `prepare` and `apply` (mismatch → `QUESTION_CHANGED`).
  Default OFF (no flag + no vault `policy.default_audience` ⇒ byte-identical).
  Bad value → `INVALID_AUDIENCE` exit 2 (never echoed).
- `--question-hash HEX` — **required**; the value `prepare` emitted, verbatim
  (64 lowercase hex). `apply` re-runs the same retrieval and recomputes it;
  mismatch → `QUESTION_CHANGED` (exit 2 — corpus changed mid-pipeline; re-run).
- **Retrieval-scope flags MUST mirror `prepare`** so `apply` reproduces the same
  retrieval/hash. Pass the identical `--vaults`/`--types`/`--project`/`--limit`/
  `--no-expand-aliases` values.
- `--answer-stdin | --answer-file` (mutex) — the synthesised markdown answer
  (≤256 KiB; file form vault-inside + `O_NOFOLLOW`).
- `--citations-stdin | --citations-file` (mutex) — a JSON array of
  `"project/slug"` strings; **every entry must be a retrieved hit** (grounding
  gate) → else `CITATION_NOT_RETRIEVED` (exit 4). (Both payloads can't share
  stdin — pipe one, file the other.)
- `--orchestrator-id` — regex `^[a-z0-9._:@-]{1,64}$`; default `"orchestrator"`.
- `--force` — re-file even when the rendered page is byte-identical (else a
  content-hash skip returns `action:"unchanged"`).

Success envelope: `{"vault_id","query_slug","cites":[…],"page_indexed":true,"action":"filed"|"unchanged"}`.

The query page is written Class A (`_queries/<slug>.md`: `type: query`,
`question:`, `date:`, `cites: [project/slug,…]`, `tags: [query]`, sanitised
answer body + a `## Sources` `[[slug]]` list), then **self-indexed via direct
`upsert_page` + `replace_refs`** (NOT the manifest/`main(argv)` N+1) — a `pages`
row (`type=query`) + `cited` `page_entity_refs` + a `query` log event. It is
FTS-searchable immediately, and `wiki-reindex --full` rebuilds the `cited` refs
from the `cites:` frontmatter (R-6.5e — the §D8 durability spine).

## Exit codes

| Code | `error` | Cause |
|---|---|---|
| 0 | — (envelope / manifest / `is_unchanged` / `unchanged`) | success / short-circuit |
| 1 | — (argparse) | missing flag / no subcommand |
| 2 | `INVALID_QUESTION` / `INVALID_SLUG` / `INVALID_QUERY` | bad question / slug / FTS expression |
| 2 | `NO_CONTEXT` | retrieved hits `< --min-hits` (prepare) |
| 2 | `QUESTION_CHANGED` / `INVALID_QUESTION_HASH` / `INVALID_VAULT_ROOT` | apply hash mismatch / malformed hash / bad vault root |
| 4 | `ANSWER_TOO_LARGE` / `INVALID_ANSWER_PATH` | answer payload too large / not a vault-inside regular file |
| 4 | `INVALID_CITATIONS` / `CITATION_NOT_RETRIEVED` | citations payload malformed / a citation not in the retrieved set |
| 4 | `INVALID_QUERY_PAGE` | target `_queries/<slug>.md` is a symlink (refused) |

**Universal envelope invariant** (CWE-117/209): error envelopes carry `{error,
field?, reason}` only — never the offending question/answer/citation value.

## Related

- [`workflows/wiki-query.md`](../../workflows/wiki-query.md) — end-to-end orchestrator recipe.
- [`skills/wiki-query-synthesis/SKILL.md`](../wiki-query-synthesis/SKILL.md) — the synthesis prompt + answer/citations contract.
- `wiki-search` — shares the alias-expanded FTS retrieval (`scripts/wiki_skills/_retrieval.py`); finds filed query pages (compounding).
- `docs/ARCHITECTURE.md` §2 RAG Query Layer + §4 Data Model (query page, `cited` refs, R-6.5e).
- ROADMAP **R-7 `wiki-research`** / **R-8 `wiki-verify-multi`** — deferred, layer on this loop.
