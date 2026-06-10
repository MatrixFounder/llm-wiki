# PLAN — TASK 028 (query stemming + ё/е fold)

Stub-First, green-throughout. Each bead: **stub → RED tests → GREEN logic**, `pytest` +
`mypy --strict scripts/` clean at every bead boundary. Branch
`task-028-query-stemming-yo-folding`. Zero DDL (`user_version` 5); no `import anthropic`.

Planner notes from architecture-review (Q-028 APPROVED): **C-2** pin MIN as a named constant;
**C-3** the FTS5 lexer is its own bead with the R-028-2(a) matrix as RED tests (highest impl
risk); **C-4** add an adversarial "many short tokens → no catch-all `*`" case proving the
post-stem MIN gate.

## Module map (new/changed)
- **NEW** `scripts/wiki_index/_snowball.py` — thin typed wrapper; the ONE
  `# type: ignore[import-untyped]`; per-language stemmer cache; `stem(word: str, lang: str) -> str`.
- **NEW** `scripts/wiki_index/query_normalizer.py` — `fold_yo`, `detect_script`,
  per-term `normalize_term` core (fold→detect→stem→post-stem-MIN guard), the wiki-search
  `stem_fts_query` FTS-expr lexer, and the wiki-query `stem_token` helper. `MIN_STEM_LEN` constant.
- **CHANGE** `scripts/wiki_index/normalization.py` — `normalize_body_for_fts` folds ё→е (R-028-4);
  docstring updated. (Reuses `fold_yo` from `query_normalizer`, or hosts `fold_yo` itself — see Bead 0.)
- **CHANGE** `scripts/wiki_skills/_retrieval.py` — split "gather alias surfaces" from "compose"
  so wiki-search can stem-first-then-OR-aliases (F-1).
- **CHANGE** `scripts/wiki_skills/wiki_search.py` — wire `stem_fts_query` + composition + `--exact`/`--no-stem`; DF-1 fold-aware.
- **CHANGE** `scripts/wiki_skills/wiki_query.py` — per-token stem in `_build_match_query`; `--exact` on `prepare`+`apply` threaded via `_retrieve`.
- **CHANGE** `requirements.txt` — `snowballstemmer==3.1.1`.
- **CHANGE** docs/skill/evals (Bead 5).

> **`fold_yo` placement decision:** host `fold_yo` in `query_normalizer.py` and import it into
> `normalization.py`. No cycle (`normalization` does not import `query_normalizer` today; the new
> import is one-directional). Keeps all ё/е logic in one module. (If a cycle appears in dev, demote
> `fold_yo` to a tiny leaf — but the direct import is expected to be clean.)

## Beads

### Bead 028-0 — engine core (`_snowball.py` + `query_normalizer` primitive) + dep
- **Stub:** `_snowball.stem(word, lang)`; `query_normalizer.{fold_yo, detect_script, normalize_term}`;
  `MIN_STEM_LEN` constant; add `snowballstemmer==3.1.1` to `requirements.txt` + install in `.venv`.
- **RED → GREEN tests** (`tests/test_query_normalizer.py`):
  - `fold_yo`: `ещё→еще`, `Ё→е`, `всё→все`, non-ё identical, NFC-safe (composed input).
  - `detect_script`: Cyrillic→`russian`, Latin→`english`, digits/CJK/punct→`None` (literal).
  - `normalize_term` (default broadening): `сценарии→сценар*`, `осведомление→осведомлен*`,
    `продуктовое→продуктов*`, `agents→agent*`; folds ё then stems (`ещё`→folded→stem).
  - **F-6 post-stem MIN gate (C-2/C-4):** a long word collapsing to a <MIN stem → emitted **literal**
    (no `*`); 1–2-char input → literal; assert no produced atom is a bare short `X*` catch-all.
  - **F-4 idempotency-via-guard:** a term already ending `*` passes through; re-`normalize_term` on a
    `<stem>*` output is a no-op.
  - `--exact` path (broadening off): fold still applied, NO stem/prefix (`сценарии`→`сценарии` folded only).
- **mypy:** the only `# type: ignore[import-untyped]` is in `_snowball.py`; `query_normalizer` fully typed.

### Bead 028-1 — wiki-search FTS-expression lexer `stem_fts_query` (own bead, C-3)
- **Stub:** `stem_fts_query(query: str, *, stem: bool) -> str`.
- **RED → GREEN safety matrix** (`tests/test_query_normalizer.py::lexer`): each passes through with
  bare-token stemming only —
  `"сценарии продаж"` (quoted phrase untouched), `a AND b`, `x OR y`, `p NOT q`,
  `NEAR(сценарии продажи, 3)` (keyword + arglist untouched, **bare args inside NOT stemmed** — they're
  inside the NEAR group; pin the chosen rule), `title:сценарии` / `{title body}:сценарии` (col-filter
  prefix preserved; decide+test whether the term after `:` is stemmed — default: preserve the filtered
  term literal in v1, documented), `сценари*` (already-`*` untouched), `-всё` / `+term` / `^term`
  (sigil preserved), uppercase `AND/OR/NOT/NEAR` never stemmed as Latin words.
  - **Bare-term path:** `сценарии продаж` (no quotes) → `сценар* продаж*` (folded+stemmed).
  - **Never-unparseable invariant:** for every valid input above, `stem_fts_query` output parses as
    valid FTS5 (assert via an in-memory FTS table `MATCH` smoke, no `OperationalError`).
- `stem=False` → fold-only (no `*`).

### Bead 028-2 — wiki-search wiring (composition F-1 + `--exact` + DF-1)
- **`_retrieval.py`:** add `alias_surfaces(repo, query, vaults) -> set[str]` (the gather half of
  `expand_query`); keep `expand_query` for back-compat (still used by anyone else / pinned tests).
- **`wiki_search.py`:** build `match = "(" + stem_fts_query(raw, stem=not exact) + ")"`; if expand →
  ` + " OR " + " OR ".join(fts_quote(fold_yo(s)) for s in sorted(alias_surfaces))`. Add `--exact`
  (alias `--no-stem`) arg. DF-1 fallback: `_search(fold_yo(_fts_quote(raw)))` then `INVALID_QUERY`.
- **RED → GREEN e2e** (`tests/test_wiki_search_stemming.py`, seeded vault):
  - bare `сценарии продаж` ranks the `Сценарии-продаж-П-К-Ч` page first (was AND-miss);
  - bare `продуктовое осведомление` ranks `03-первое-касание` near top, no manual `*`;
  - alias+inflection: an alias-hit query still broadens the typed words (F-1 regression);
  - `--exact` reproduces pre-028 literal result for ё-free content (regression anchor);
  - DF-1: a hyphen/`:`-bearing raw query → clean `INVALID_QUERY` (no trace).

### Bead 028-3 — wiki-query wiring (per-token F-2 + `--exact` symmetry C1)
- **`wiki_query.py`:** in `_build_match_query`, per token → `stem_token(tok, stem)` →
  `fts_quote(stem)+"*"` (broadening) or `fts_quote(fold_yo(tok))` (exact); alias lookup uses the raw
  token, surfaces folded+quoted. Add `--exact`/`--no-stem` to **both** `prepare` and `apply`
  subparsers; thread `args.exact` into `_retrieve` → `_build_match_query`.
- **RED → GREEN e2e** (`tests/test_wiki_query_stemming.py`):
  - `prepare "продуктовое осведомление"` (default) retrieves `03-первое-касание`;
  - prepare-default → apply-default reproduces `question_hash` (no `QUESTION_CHANGED`);
  - prepare-default → apply-`--exact` → `QUESTION_CHANGED` (documented expected);
  - `--exact` accepted on both subparsers; reproduces pre-028 retrieval (ё-free);
  - determinism: `stem_token` byte-stable (snapshot a few stems).

### Bead 028-4 — ё/е index-side body fold (R-028-4)
- **`normalization.py`:** `normalize_body_for_fts` applies `fold_yo` (after mermaid/SECTION strip);
  docstring updated (NFC-safe, layout-agnostic, intentional indexing delta).
- **RED → GREEN** (`tests/test_yo_fold_index.py`, seeded vault + `reindex_full`):
  - body `ещё` found by query `еще` AND body `еще` found by `ещё` (after reindex — symmetric);
  - `pages.title` with `ё` is NOT folded (read back the row → title keeps `ё`);
  - Karpathy indexing byte-identical for ё-free content (existing golden anchors stay green);
  - `snippet()` of a ё-body shows the е-form (assert the documented cosmetic).

### Bead 028-5 — skill + evals + docs currency (R-028-5)
- **`skills/wiki-search/SKILL.md`:** correct L55 / L56-58 / L66-71 / L80-83; document `--exact`
  (Contract + Invocation); recast manual stem-prefix as fallback; bump `version: 1.3 → 1.4`.
- **`skills/wiki-search/evals/evals.json`:** update top-level description; eval #4 expected =
  **default** search finds `03-первое-касание` (drop "must manually prefix"); KEEP #2 (КПЧ↔ПКЧ
  transposition — non-morphological, stays fallback+grounding) + #3 (anti-hallucination); ADD
  cases: stemming-recall (`сценарии продаж`→`Сценарии-продаж-П-К-Ч` first), ё/е-fold parity
  (`еще`↔`ещё`), `--exact` precision, mixed ru+en. State final count.
- **Docs:** `docs/manuals/{cli-quick-reference,obsidian-llm-wiki_manual}.md` + `.ru` mirrors +
  `README.md` (L49/L396) — add default stemming + ё/е fold + `--exact` + the one-time `--full`
  reindex-for-body-ё note. ARCHITECTURE Q-028 already done.
- **Gate:** `python3 .../skill-enhancer/scripts/analyze_gaps.py skills/wiki-search` clean.

### Bead 028-6 — final verification (no new code)
- Full `pytest` green; `mypy --strict scripts/` clean; `grep -r "import anthropic" scripts/` empty;
  `user_version` still 5; `--exact` byte-identity regression (ё-free) holds.
- `/vdd-multi` (logic/security/performance) → converge; code-review APPROVED.

## Plan-review addenda (incorporated)
- **M-1 (Bead 2+3):** `--exact`/`--no-stem` is `action="store_true", default=False` → **omitting it ⇒
  stemming ON** (the OQ-1 contract). Add a RED test "no flag ⇒ broadening on" (not just the inverse).
- **M-2 (Bead 3):** explicit rule in `_build_match_query` — stem each *token* to its `"<stem>"*` atom,
  fold+quote each *alias surface* separately, union into the surfaces set, then `sorted` join. Two
  inflections of one root MAY collapse to one stem atom (intended) — add a RED test asserting it.
- **m-1 (Bead 3):** add one combined `--exact` + `--no-expand-aliases` case (orthogonal axes).
- **m-2 (Bead 3):** the post-stem `sorted` join (not token order) is what anchors `question_hash`
  determinism — note inline so a future dedup refactor can't break C1.
- **m-3 (Bead 4):** import direction MUST stay `normalization → query_normalizer` (one-directional;
  `query_normalizer` must NOT import `normalization`).
- **m-4 (Bead 0):** inline comment in `requirements.txt` next to the EXACT `==3.1.1` pin (deviates
  from the repo `>=` convention — C1 rationale); verify the installed wheel is `py3-none-any` (no C ext).

## Risk register
- **Highest impl risk:** Bead 1 FTS lexer (C-3) — mitigated by the RED safety matrix + the
  never-unparseable smoke + the unchanged DF-1 net.
- **Perf/abuse:** post-stem MIN gate (C-4) prevents catch-all `*` scans.
- **Reproducibility:** pinned `==3.1.1` + `--exact` symmetry (C1).
- **Cosmetic:** ё-folded snippets (accepted, documented F-5).
