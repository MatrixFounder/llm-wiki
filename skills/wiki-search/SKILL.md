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
version: 1.3
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
    [--format json|markdown] \
    [--db-path <override>]
```

Or `/wiki-search "<query>" [...]`.

## Contract

- `<query>` is an FTS5 MATCH expression — supports `AND`, `OR`, `NOT`,
  phrase quoting, prefix `*`. Invalid syntax → `sqlite3.OperationalError`.
- `--vaults` omitted OR `all` → searches every registered vault.
- Default output: JSON envelope with `hits[]` (each hit has `vault_id`,
  `slug`, `project`, `type`, `title`, `bm25_score`, `snippet`).

## Search WELL — broaden, don't stop at the first hit, and NEVER hallucinate

FTS5 here is **literal**, **multi-term is implicit AND**, and there is **no stemming**.
So one inflected form misses its siblings, one unmatched token zeroes everything, and
the first lexical hit is often NOT the on-topic page. Two failure modes to design
against:

- **0 hits** does NOT mean "not in the wiki" — usually the query was too tight.
- **A hit that looks tangential** (a generic word matched a side-mention) does NOT mean
  you found the right page — the on-topic page may use a different inflection you didn't
  match. **Do NOT answer from the first lexical match.** For a *"what is X / how do I X"*
  question, gather the top hits and pick the page that's actually ABOUT X.

So **search by the STEM of the DISTINCTIVE word, with a prefix `*`, from the start** —
not one inflected form, and not the generic adjective. Real example: *"что такое
продуктовое осведомление?"* — searching the literal `продуктовое` returns a tangential
AI-panel page; searching the distinctive noun stem `осведомл*` (and/or `продуктов*`)
ranks the correct course page `03-первое-касание` near the top. Then BROADEN further if
needed (the `query` is a full FTS5 MATCH expr — exploit it):

1. **Drop the rare/acronym token, search the distinctive CONTENT words.** For *"что
   такое кпч-сценарий?"* search `"сценарии продаж"` (not `кпч`) → it ranks the right
   page first. The surrounding nouns are far more reliable than an acronym you might
   be mis-typing.
2. **OR-expand & prefix:** `пкч OR сценарий`, `сценари*` (prefix), phrase `"сценарии продаж"`.
3. **Acronym variants:** try hyphenated/un-hyphenated and letter-order transpositions
   (`ПКЧ`/`П-К-Ч`/`КПЧ`) — abbreviations are easy to mis-remember.
4. **Russian specifics (the engine is `unicode61`, no stemmer):** inflected forms are
   DISTINCT tokens (`сценарий`≠`сценарии`≠`сценариев`) → query the **stem with a prefix**
   (`сценари*`), not one fixed form. And `ё` is **NOT** folded to `е` (`ещё`≠`еще`,
   `всё`≠`все`) → if a hit is plausible, try BOTH spellings.
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
