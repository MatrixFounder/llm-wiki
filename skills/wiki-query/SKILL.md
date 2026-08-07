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
  `"project/slug"` strings; **at least one entry** (an empty array → `NO_CITATIONS`,
  exit 4) and **every entry must be a retrieved hit** (grounding gate) → else
  `CITATION_NOT_RETRIEVED` (exit 4). (Both payloads can't share stdin — pipe one,
  file the other → else `INVALID_ARGS`, exit 2.)
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

This table is the **normative roster** for this CLI — every reachable code is listed,
including the ones this CLI inherits rather than raises itself.

| Code | `error` | Cause |
|---|---|---|
| 0 | — (envelope; `is_unchanged` on prepare, `action:"unchanged"` on apply) | success / short-circuit. ⚠️ **no manifest mode** — this CLI files exactly one page, so the manifest machinery is deliberately bypassed (`wiki_query.py:556-558`). |
| **1** | — (**no envelope at all**) | an **unhandled exception**: corrupt `--db-path`, unwritable `_queries/`, … stdout is EMPTY and a raw traceback goes to stderr. **Not a contract error** — treat as a bug/environment fault, never as "bad flag". |
| **2** | — (argparse, **no envelope** unless the flag parsed) | missing flag / no subcommand / unrecognized argument. argparse's own exit status is **2**, always. |
| 2 | `INVALID_QUESTION` / `INVALID_SLUG` / `INVALID_QUERY` | bad question / slug / FTS expression |
| 2 | `NO_CONTEXT` | **prepare only** — retrieved hits `< --min-hits` |
| 2 | `QUESTION_CHANGED` / `INVALID_QUESTION_HASH` / `INVALID_VAULT_ROOT` | apply hash mismatch / malformed hash / bad vault root |
| 2 | `INVALID_AUDIENCE` / `INVALID_POLICY` | `--audience` is not one of the vault's policy levels / the `policy:` block is malformed |
| 2 | `INVALID_ARGS` | both payloads asked for stdin (`--answer-stdin` **and** `--citations-stdin`) |
| 2 | `SKILL_INTEGRITY_DRIFT` | **prepare only**, and only under `WIKI_STRICT_SKILL_INTEGRITY=1`: the pinned REASON contract's integrity status is not `ok` — that is `drift` (bytes changed) **or** `unpinned` (absent from the manifest) **or** `manifest_unavailable` (no manifest on disk). The last two do **not** imply changed bytes. ⚠️ envelope shape exception — see below. |
| 4 | `ANSWER_TOO_LARGE` | answer payload over the size cap |
| 4 | `INVALID_ANSWER_PATH` | `--answer-file` is not a vault-inside regular file |
| 4 | **`NO_CITATIONS`** | the citations array is well-formed but **EMPTY** — an answer must cite ≥1 retrieved source |
| 4 | `INVALID_CITATIONS` | citations payload malformed, **or** over the 64 KiB cap, **or** `--citations-file` is not a vault-inside regular file. Branch on `field`: `citations` = re-synthesise, `citations-file` = fix the call. |
| 4 | `CITATION_NOT_RETRIEVED` | a citation is not in the recomputed hit set |
| 4 | `INVALID_QUERY_PAGE` | target `_queries/<slug>.md` is a symlink (refused) |
| **6** | `INVALID_INDEX_DB` | **inherited from `build_repo_config`**, raised by *both* subcommands before any work: the vault's `index_db:` escapes the vault / is a symlink / is an unsafe absolute path. ⚠️ envelope carries an extra `hint` key. |

**Grounding is a TRIPLE, and all three are Python, not prompt discipline:**
`NO_CONTEXT` (exit 2, **prepare** — *nothing was retrieved*) · `NO_CITATIONS` (exit 4,
**apply** — *grounding was not claimed*) · `CITATION_NOT_RETRIEVED` (exit 4, **apply** —
*grounding was claimed OUTSIDE the recomputed hit set*; this is the only one of the three
keyed on the `project/slug` tuple). No flag permits an uncited answer: `--force` is
consumed downstream at the content-hash skip.

> `--min-hits 0` is **prepare-only** (`apply` declares no such flag) and merely disables
> the `NO_CONTEXT` refusal — it does **not** empty the retrieval. With a question that
> matches, `prepare --min-hits 0` retrieves normally and `apply` files normally. What it
> cannot do is turn an *empty* retrieval into a filed page: then `[]` fails `NO_CITATIONS`
> and any non-empty array fails `CITATION_NOT_RETRIEVED`.

**What the orchestrator should DO — read the CODE, not the exit number.** The exit
number alone does not tell you, because exit 4 mixes two classes:
- **RE-SYNTHESISE and re-apply** — the synthesis violated its *output contract*:
  `NO_CITATIONS`, `CITATION_NOT_RETRIEVED`, `ANSWER_TOO_LARGE`, and `INVALID_CITATIONS`
  *when the payload is malformed*.
- **STOP and forward** — everything else, including the exit-4 codes that are
  **invocation or filesystem faults**: `INVALID_ANSWER_PATH`, `INVALID_QUERY_PAGE`
  (a symlink on disk — re-synthesising is non-terminating, the error never clears), and
  `INVALID_CITATIONS` *when it names `citations-file`* (check `field`). Plus every exit 2
  (you called it wrong or the world changed), exit 6 (vault config), and exit 1 (a bug).

**Universal envelope invariant** (CWE-117/209): an error envelope carries `{error,
field?, reason}` and **never** the offending question/answer/citation value. Two envelopes
carry additional keys, and neither leaks a value: `SKILL_INTEGRITY_DRIFT` carries
`{error, integrity}` (**no `field`/`reason`** — the block is value-free hashes/status) and
`INVALID_INDEX_DB` adds a `hint`. The no-echo guarantee holds for all of them.

## Related

- [`workflows/wiki-query.md`](../../workflows/wiki-query.md) — end-to-end orchestrator recipe.
- [`skills/wiki-query-synthesis/SKILL.md`](../wiki-query-synthesis/SKILL.md) — the synthesis prompt + answer/citations contract.
- `wiki-search` — shares the alias-expanded FTS retrieval (`scripts/wiki_skills/_retrieval.py`); finds filed query pages (compounding).
- `docs/ARCHITECTURE.md` §2 RAG Query Layer + §4 Data Model (query page, `cited` refs, R-6.5e).
- ROADMAP **R-8 `wiki-verify-multi`** — **SHIPPED 2026-05-29** (TASK 008); the off-by-default
  verification layer over an answer this CLI filed.
- ROADMAP **R-7 `wiki-research`** — **RE-SCOPED 2026-08-06** (TASK 072) to *external corroboration
  of open typed questions*: it layers on this loop for the one case retrieval alone cannot serve —
  a page whose own frontmatter declares it unresolved, so vault retrieval returns `NO_CONTEXT` by
  construction. Its original *"web enrichment of concept pages"* scope is **refuted, non-reopenable**.
