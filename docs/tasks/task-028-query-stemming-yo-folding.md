# TASK 028 — query-side stemming + ё/е folding (Russian-first, script-general)

## 0. Meta
- **Task ID:** 028 · **Slug:** `task-028-query-stemming-yo-folding`
- **Mode:** VDD (full) — task/arch/plan reviews + `/vdd-multi` + code-review
- **Branch:** `task-028-query-stemming-yo-folding`
- **Context:** Two real-vault dogfood recall misses on the user's PARA Obsidian vault
  exposed the FTS layer's morphology gap. (1) Haiku answered `как делать скрипты продаж
  по телефону?` from training because the literal multi-term AND found nothing
  (vault has "Сценарии прода**ж** П-К-Ч"). (2) `что такое продуктовое осведомление?`
  ranked a tangential AI-panel page first and missed the on-topic `03 - Первое касание`
  (uses `осведомлени**е**`×33, `продуктов…`×18). Root cause is the tokenizer:
  `pages_fts USING fts5(... tokenize='unicode61 remove_diacritics 2')` has **no stemming**
  (`сценарий`≠`сценарии`≠`сценариев` are distinct tokens) and does **not** fold `ё↔е`
  (`ё` U+0451 is precomposed; empirically `ещё`=178 vs `еще`=472 hits). The current
  mitigation is a *manual* instruction in `skills/wiki-search/SKILL.md` ("search by the
  stem with a prefix `*`") — a weaker model (or hurried operator) does not honour it,
  which is exactly how both misses happened. **TASK 028 moves the broadening into the
  engine** so default search is inflection-tolerant without hand-crafted prefix queries.
- **Decision:** "сделай оба изменения" — implement **both** stemming (A) **and** the ё/е
  fold (B). Design generalises to other languages via per-term **script detection**.

### Two orthogonal mechanisms (the central design principle — pins F-3 / OQ-1)
1. **Normalization — ALWAYS ON (not gated by `--exact`):** fold `ё→е`/`Ё→Е` (case-preserving). Applied to
   the FTS body corpus (`body_excerpt`, index side) **and** every query term (search
   side). This is *corpus canonicalisation*: both sides agree, so `ещё`/`еще` are one
   token. `--exact` does **not** undo it (the index is folded; an un-folded `--exact`
   query would just miss the folded corpus).
2. **Broadening — DEFAULT ON, `--exact`/`--no-stem` disables:** snowball stem + prefix
   `*` per bare term, so one typed form matches all inflections. This is the recall lever
   that a weak model needn't hand-craft.

- **Constraints:** **zero DDL** (`user_version` stays 5 — no schema/trigger/tokenizer
  change); new **pure-Python** dep **`snowballstemmer==3.1.1`** (pinned EXACT, not `>=`:
  a stem change alters the retrieved hit set, which feeds `wiki-query`'s `question_hash`,
  so a silent dep bump would break filed-answer reproducibility — C1; verified pure-Python `py3-none-any` wheel, no
  C extension — honest precedent vs TASK 017 `regex`); a stem-algorithm bump is a
  deliberate, re-query/reindex-affecting change (documented). `snowballstemmer` ships **no
  `py.typed`** → a single typed wrapper `scripts/wiki_index/_snowball.py` isolates the one
  `# type: ignore[import-untyped]` (F-7; no `types-snowballstemmer` exists). **No**
  `import anthropic` (grep-guarded); `mypy --strict scripts/` clean; Karpathy golden-anchor
  **indexing** byte-identity preserved EXCEPT the layout-agnostic ё→е body fold (intentional,
  applies to every layout).

## 1. Requirements & RTM
| ID | Requirement | MVP? | Sub-features / Verification |
|----|-------------|------|------------------------------|
| **R-028-1** | **Query-side, script-aware stemming + ё-fold primitive.** New pure module `scripts/wiki_index/query_normalizer.py` over a typed `_snowball.py` wrapper. Core per-term: fold ё (always) → detect script (Cyrillic→`russian`, Latin→`english`, other/digits→literal) → stem (when broadening on) → guard. **Default-on**; `--exact` (alias `--no-stem`) disables **stemming only** (fold stays). | ✅ | (a) unit: stems ru/en, leaves CJK/numbers literal, **NFC-safe** fold; (b) **MIN gate on POST-stem length** (F-6): if `len(stem) < MIN` (≈3 Cyr) emit the term **literal, no `*`** — a long word collapsing to a 2-char stem must NOT become a catch-all `аг*`; unit-test long→short-stem→literal and 1–2-char input→literal; (c) **idempotency via the `*`-guard, NOT the stemmer** (F-4): the snowball stem is NOT idempotent (`осведомлен`→`осведомл`), so re-running the FTS rewrite on its OWN output is a no-op *because every produced term ends in `*`* — unit-test that property, and that a term already ending in `*` is passed through. |
| **R-028-2** | **`wiki-search` integration — FTS-expression-aware (F-9).** A lexer in `query_normalizer` walks the raw FTS5 MATCH expr and stems+folds ONLY bare, sigil-free, unquoted content tokens; passes through **verbatim**: quoted phrases, paren groups, `NEAR(...)` + its arg list, column filters (`col:`, `{a b}:`), the **uppercase operator keywords** `AND/OR/NOT/NEAR`, any term already ending `*`, and any `^`/`-`/`+`-sigil term. **Composition (F-1, corrected):** stem the bare query FIRST, then OR-in the (quoted, fold-ed, **unstemmed**) alias surfaces: `(<stemmed-folded-raw>) OR "alias1" OR "alias2"` — NOT `stem(expand_query(raw))` (which would skip the whole quoted query and broaden nothing on an alias hit). Add `--exact`/`--no-stem`. **DF-1 fallback unchanged in shape** but folds: on `OperationalError` re-run the literal folded quoted phrase `fold(fts_quote(raw))`; prove the stemmed expr never itself raises `OperationalError` from a valid input. | ✅ | (a) FTS-safety matrix: `"сценарии продаж"`, `a AND b`, `NEAR(x y, 3)`, `col:foo`, `{title body}:x`, `term*`, `-всё`, `^term` each pass through with bare-token stemming only; (b) e2e: bare `wiki-search "сценарии продаж"` ranks `Сценарии-продаж-П-К-Ч` first; `продуктовое осведомление` ranks `03-первое-касание` near top with **NO manual prefix**; (c) alias+inflection e2e: an alias-hit query still gets inflection broadening on the typed words (regression vs F-1); (d) `--exact` reproduces pre-028 literal result **byte-identical for ё-free content** (ё-content stays consistently folded both sides — the corrected anchor, F-3); (e) DF-1 fallback still yields clean `INVALID_QUERY`, never a stack trace. |
| **R-028-3** | **`wiki-query` integration — per-token (F-2).** `_build_match_query` already `fts_quote`s every token, so stemming MUST happen at the TOKEN level **before** `fts_quote`, emitting a quoted-prefix `"<stem>"*` per token (valid FTS5); alias surfaces use the **raw** token (lookup), fold-ed + quoted. Add `--exact`/`--no-stem` to **both** `prepare` AND `apply` subparsers, threaded through the shared `_retrieve`. **question_hash symmetry (C1):** because `_question_hash` is recomputed in `apply` and a mismatch → `QUESTION_CHANGED`, the flag must be symmetric and the stemmer deterministic. | ✅ | (a) e2e: `wiki-query prepare "продуктовое осведомление"` (default) retrieves `03-первое-касание` (RAG path independently pinned, not assumed from wiki-search); (b) prepare-default → apply-default **reproduces `question_hash`**; (c) prepare-default → apply-**exact** → `QUESTION_CHANGED` (documented, expected); (d) `--exact` accepted on both subparsers + reproduces pre-028 retrieval (ё-free); (e) stemmer byte-stable for the pinned version (determinism assertion). |
| **R-028-4** | **ё/е index-side fold (B).** Fold `ё→е`/`Ё→е` in the FTS body corpus via `normalize_body_for_fts` → `body_excerpt` (route taken by upsert + both reindex paths through `_build_page`; triggers copy `body_excerpt` verbatim, so folding at the row-write site is sufficient — no trigger change). **Zero DDL**; takes effect on next `wiki-reindex --full` (Class-B rebuild, ADR-002 §D8). `pages.title`/`tldr` are **NOT** folded → titles keep `ё` (display fidelity). **`snippet()` IS a real display consumer** of `body_excerpt` (F-5): result snippets render the е-form — a deliberate, accepted cosmetic change for ru ё/е; `wiki-verify-multi` reads the raw FILE (unaffected). | ✅ | (a) unit: `fold_yo("ещё")=="еще"`, `Ё→е`, non-ё text identical, NFC-safe; (b) index parity AFTER `--full` reindex: body `ещё` found by query `еще` and vice-versa; (c) `pages.title` NOT folded (display assertion); (d) Karpathy indexing byte-identical for ё-free content; (e) `normalization.py` docstring updated to document the fold. |
| **R-028-5** | **Skill + evals + docs currency** (operator-mandated: "не забудь обновить скилл skills/wiki-search и evals"). | ✅ | (a) `skills/wiki-search/SKILL.md`: correct the 4 now-false sites (L55 "no stemming"; L56-58 "one inflected form misses its siblings"; L66-71 manual-prefix-as-primary; L80-83 "unicode61, no stemmer" + "ё is NOT folded" + "try BOTH spellings") → describe engine stemming + always-on ё/е fold; document `--exact`; recast manual stem-prefix as a **fallback / explicit-control** lever; update Contract+Invocation (L47-48); **version 1.3→1.4**; `analyze_gaps.py` shows **no NEW gaps vs the pre-028 baseline** (the pre-existing framework-template gaps — Red Flags / Execution-Mode / `examples/` / CSO-prefix — are a separate skill-hardening follow-up, not TASK 028 scope). (b) `evals/evals.json`: reconcile ALL of #1-#4 with default-on stemming (not just #4) — #4 expected = **default** search finds `03-первое-касание` (drop "must manually prefix"); **keep #2 (КПЧ↔ПКЧ transposition is NOT morphological → stemming does NOT fix it → stays the fallback-broadening + anti-hallucination contract) and #3 (grounding)**; update the top-level description (L3); ADD ≥3 engine-behaviour cases (stemming-recall, ё/е-fold parity, `--exact` precision, mixed ru+en); state the post-update count. (c) Docs: `docs/manuals/{cli-quick-reference,obsidian-llm-wiki_manual}.md` + `.ru` mirrors + `docs/ARCHITECTURE.md` search section + `README.md` (L49/L396 feature surfaces) — add default stemming + ё/е fold + `--exact` + the one-time `--full`-reindex-for-body-ё note + the `query_normalizer` seam. `sql/wiki-index-v2.sql` L366 + README L142 tokenizer DDL string stays UNCHANGED (zero-DDL). |

## 2. Non-goals
- **No custom FTS5 tokenizer** (needs a C extension — not pure-Python).
- **No index-side stemming** (would need a stemmed shadow corpus + degrade `snippet()`;
  query-side stemming is reversible, zero-reindex, `--exact`-able).
- **No trigger/DDL change** (the body-only app fold + the always-on query fold achieve ё/е
  recall within zero-DDL). **Documented residual (vdd-multi logic MED):** only `body_excerpt`
  is index-folded; `pages_fts` ALSO indexes `title`, `tldr`, and `tags` UNFOLDED, while the
  query is always folded — so a **ё-form** query for a term that lives ONLY in a `title`/`tldr`/
  `tag` (never the body) is a narrow ё-form-only recall regression vs pre-028 (and `--exact` is
  thus byte-identical only for ё-FREE content in those columns). The е-form query (the common
  Russian typing) is unaffected; the body case is improved. Folding `title`/`tags` into the FTS
  shadow needs trigger DDL (tags ride `json_extract` in the trigger) → out of zero-DDL scope.
  Alias resolution is also ё-sensitive (exact-match) — register ё-bearing aliases in the е-form.
- **No per-vault `language:`-driven stemmer selection in v1** (per-term script detection
  covers ru+en — the only in-scope languages — and is robust to `--vaults all`; a
  `language:`-driven Latin-stemmer override is a documented future extension).
- **No new CLI**, **no envelope/exit-code change**, **no DAL signature change** (the
  rewrite happens above `search_pages`; `search_pages` stays a pure MATCH executor).

## 3. Other-languages design (answers "А как будет с другими языками?")
Stemming is **per-term by script**, not Russian-only: snowball ships **36** stemmers
(pure-Python). v1 maps Cyrillic→`russian`, Latin→`english` (English benefits too:
`agents`→`agent*`); all other scripts→literal (graceful — never mangled; CJK is also
poorly served by `unicode61`, an orthogonal pre-existing limit). A German/French vault is
a documented future `language:`-override; `--vaults all` works because detection is
per-term, not per-vault.

## 4. Acceptance
- RTM R-028-1..5 verified; full `pytest` green + `mypy --strict scripts/` clean;
  `import anthropic` grep-guard holds; `user_version` still 5.
- `--exact` = no stemming/broadening but **ё-fold still applied both sides** → byte-identical
  to pre-028 for ё-free content; folded-consistent for ё-content (the corrected anchor).
- Karpathy indexing byte-identical for ё-free content; the ё→е body fold is the only
  intentional indexing delta (layout-agnostic).
- `snowballstemmer==3.1.1` pinned; mypy-strict typed via the `_snowball.py` wrapper.
- skill-enhancer `analyze_gaps.py` shows no NEW gaps vs the pre-028 baseline (pre-existing
  template gaps are an out-of-scope follow-up); evals valid + reconciled + expanded.
- Full VDD: task/arch/plan reviews APPROVED → `/vdd-multi` converged → code-review APPROVED.

## 5. Open Questions — RESOLVED (carried into ARCHITECTURE Q-028-*)
- **OQ-1 (default-on stemming).** RESOLVED **default-on** + `--exact` opt-out — the two
  production misses were *default* searches; auto-broaden is the whole point.
- **OQ-2 (ё/е reindex cost).** RESOLVED accept the one-time `wiki-reindex --full` (Class-B,
  seconds even at ~2.5k pages); stemming + query-side ё-fold work immediately, only **body**
  ё-recall is gated on the reindex.
- **OQ-3 (MIN length).** RESOLVED gate on **post-stem** length (≈3 Cyrillic), emit literal
  below it (F-6). Exact constant tuned against the eval set in dev.
- **OQ-4 (stem ↔ alias order).** RESOLVED **stem-first, OR-in quoted alias surfaces** (F-1
  corrected) — alias surfaces stay exact, typed words still broaden.
- **OQ-5 (`--exact` semantics).** RESOLVED `--exact` disables **stemming/broadening only**;
  ё/е fold is corpus normalization and stays on both sides (F-3).
- **OQ-6 (question_hash).** RESOLVED `--exact` threaded symmetrically through wiki-query
  `prepare`+`apply` via `_retrieve`; stemmer pinned-deterministic (C1).
