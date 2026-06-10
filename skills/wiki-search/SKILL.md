---
name: wiki-search
description: >-
  Use BEFORE answering ANY question about a vault's subject matter — a how-to,
  a definition, domain facts, prior decisions, or a concept/entity lookup: search
  the wiki first, do not answer from training. FTS5 full-text search across one or
  more registered vaults, returning ranked hits with BM25 score + snippet.
  Triggers: "search wiki", "find in vault", "wiki-search", "what is", "how do I",
  any vault-domain question.
tier: 2
version: 1.4
---

# wiki-search

Read-only FTS5 query against the multi-vault SQLite index. Single-vault,
multi-vault, or cross-vault (`_global_` sentinel).

## When to use

- Agent / operator looking up a concept slug, entity name, or fragment in
  the knowledge base before doing anything else.
- Phase 3a knowledge-lookup default — see `CLAUDE.md` "Knowledge lookup
  priority".
- Before creating a concept/entity page, search to avoid duplicates.

## When NOT to use

- Need full file contents → `Read` after `wiki-search` returns the path.
- Search disk for files not yet indexed → `Glob` or `find`.

## Invocation

```bash
wiki-search "<query>" \
    [--vaults "<id1,id2>" | --vaults all] \
    [--types summary,concept,entity] \
    [--project _vault_] [--limit 20] \
    [--exact | --no-stem] \
    [--format json|markdown] \
    [--db-path <override>]
```

Or `/wiki-search "<query>" [...]`.

## Contract

- `<query>` is an FTS5 MATCH expression — supports `AND`, `OR`, `NOT`,
  phrase quoting, prefix `*`. Invalid syntax → `sqlite3.OperationalError`
  (caught → a quoted-phrase fallback, then a clean `INVALID_QUERY`).
- **TASK 028 — default search is inflection-tolerant.** Bare content terms are
  auto **stemmed + prefixed** (`сценарии`→`сценар*`, `agents`→`agent*`) and
  **ё/е-folded** before MATCH, so one typed form finds its siblings. Quoted
  phrases, operators, `col:` filters, `^`/`-`/`+`-sigils, and already-`*` terms
  are passed through untouched. `--exact` (alias `--no-stem`) disables stemming
  for precise literal terms (the ё/е fold still applies — the corpus is folded).
- `--vaults` omitted OR `all` → searches every registered vault.
- Default output: JSON envelope with `hits[]` (each hit has `vault_id`,
  `slug`, `project`, `type`, `title`, `bm25_score`, `snippet`).

## Search WELL — broaden, don't stop at the first hit, and NEVER hallucinate

Default search is **inflection-tolerant** (TASK 028): bare terms are auto stemmed +
prefixed and **ё/е-folded**, so `продуктовое осведомление` already finds the page using
`осведомлени*`/`продуктов*` without a hand-crafted prefix, and `ещё`/`еще` are one token.
But **multi-term is still implicit AND**, and the top hit is often still tangential. Two
failure modes remain:

- **0 hits** does NOT mean "not in the wiki" — usually one rare/mistyped token zeroed the
  AND (stemming does NOT fix typos, synonyms, or acronym letter-order).
- **A tangential top hit** (a generic word matched a side-mention) does NOT mean you found
  the right page. **Do NOT answer from the first lexical match.** For a *"what is X / how
  do I X"* question, gather the top hits and pick the page that's actually ABOUT X.

When the default search underdelivers, BROADEN (the `query` is a full FTS5 MATCH expr —
exploit it). Manual prefixing is now a **fallback / fine-control lever**, not the primary
path:

1. **Drop the rare/acronym token, search the distinctive CONTENT words.** For *"что такое
   кпч-сценарий?"* search `сценарии продаж` (not `кпч`). The surrounding nouns are far
   more reliable than an acronym you might be mis-typing — and stemming does NOT help an
   acronym (it's not a morphological variant).
2. **Acronym variants:** try hyphenated/un-hyphenated and letter-order transpositions
   (`ПКЧ`/`П-К-Ч`/`КПЧ`) — abbreviations are easy to mis-remember; the engine treats them
   literally (ALL-CAPS tokens are NOT stemmed, to keep acronyms exact).
3. **Explicit control:** add your own prefix (`сценари*`), `OR`-expand (`пкч OR сценарий`),
   or quote a phrase (`"сценарии продаж"`) when you want precise behaviour. Use `--exact`
   to turn OFF stemming entirely for literal-term precision (ё/е still folds).
4. **Russian/other-language notes:** stemming is engine-side per term by script (Cyrillic→
   russian, Latin→english); `ё`/`е` are folded both in the query and the body corpus, so
   you no longer need to try both spellings. Residuals: only the body is index-folded, so a
   **ё-form** query for a term that lives ONLY in a `title`/`tldr`/`tag` (never the body) can
   miss — prefer the **е-form** (it works everywhere); and the **body** ё-fold needs a one-time
   `wiki-reindex --full` to take effect (stemming + query ё-fold are immediate).
5. **Filesystem fallback:** `Glob`/`grep`/`Read` over the vault for not-yet-indexed or
   fuzzy matches (re-`wiki-reindex --delta` if the file exists but isn't indexed).

**Grounding (MANDATORY — core-principles).** An answer about the vault's content MUST
be grounded in pages you actually retrieved (cite the `slug`). If, after broadening,
retrieval is genuinely empty, say so plainly — *"no page in the wiki matches `<term>`"*
— and offer `/wiki-enrich` to add a source. **NEVER invent a definition/expansion of an
unknown term** (e.g. guessing what an acronym "probably" stands for). A fabricated answer
is worse than "not found": it silently defeats the whole point of a compounding wiki.

## Exit codes

| Code | Envelope |
|---|---|
| 0 | `{"action": "searched", "query": ..., "hits": [...], "count": N}` |
