---
id: DF-064-3
type: known-issue
status: fixed
opened_at: 2026-07-14
category: correctness
severity: SEV-3
slug: df-064-3-derive-candidates-misreads-the-identity-sentinel
---

# `derive_candidates` reads `derive_concept_slug`'s `identity` sentinel as "invalid slug" — a future caller would file **zero** concepts on every karpathy vault

- **Symptom (latent — not reachable today)**: `derive_concept_slug(name, strategy)`
  (`wiki_extract_concepts/_gates.py`) returns **`None`** under `slug_strategy: identity` to mean
  *"this layout declares NO name→slug derivation — skip the G8 gate"*. `identity` maps a file
  **stem** to a slug, not a **name** to a slug, so there is nothing to verify.

  `wiki_import_article/_authoring.py::derive_candidates` treats that `None` as **"invalid slug"**
  and **skips the candidate**.

- **Demonstrated at the function boundary**:

  ```
  derive_candidates(entities=[Sharpe Ratio, Diversification], slug_strategy='identity', …)
    → candidates = []
    → skipped    = [{'name': 'Sharpe Ratio',    'reason': 'invalid-slug'},
                    {'name': 'Diversification', 'reason': 'invalid-slug'}]
  ```

  Names that are **already valid slugs** regress too: pre-TASK-064, `liquidity` / `amm` /
  `proof-of-stake` produced exactly those slugs; now all three are `SKIP invalid-slug`.

- **Why it does not fire today**: the only shipped caller (`wiki_import_article.apply`) passes
  `mint = _mint_strategy(layout.slug_strategy)`, which **substitutes `preserve-unicode` for
  `identity`** — so `derive_candidates` never actually receives `identity`. Karpathy imports were
  verified end-to-end and still file concepts correctly.

- **Why it is filed anyway**: this is a **loaded footgun with a silent failure mode**. A future
  caller that passes `layout.slug_strategy` straight through — the obvious, natural thing to write —
  files **zero concept pages on every karpathy vault**, reporting `skipped: invalid-slug` for
  perfectly valid names, at **exit 0**. Nothing fails; the concepts simply never appear. That is the
  same shape as the defect TASK 064 exists to remove.

- **Root cause**: a **tri-state return** (`str` = derived slug · `None` = *no derivation declared* ·
  and, in the caller's reading, `None` = *invalid*) collapsed into a boolean at the call site. The
  sentinel's meaning is documented in `derive_concept_slug`'s docstring but not enforced by its type.

- **FIXED (TASK 065)** — the sentinel was made unmisreadable rather than the next reader trusted.
  The one function answering two questions became two functions answering one each, in
  `wiki_extract_concepts/_gates.py`:

  | function | the question it answers | who asks |
  |---|---|---|
  | `layout_derives_slugs(strategy)` | *"is there a rule to CHECK a slug against?"* | the **gate** (G8) |
  | `mint_concept_slug(name, strategy)` | *"give me a slug I can USE"* | the **producer** (`derive_candidates`) |

  `mint_concept_slug` mints on **every** layout (on `identity` it mints in the `preserve-unicode`
  keyspace — the same reasoning `_mint_strategy` already carried, now moved *inside* the function
  so the next caller inherits it), and still pushes the result through the rail's own
  normalisation, so what it produces is a slug the charset gate and G8 both accept **by
  construction**. Its `None` now means exactly one thing: the derivation really is degenerate.

  Verified on the issue's own reproduction: under `identity`, `derive_concept_slug` returns `None`
  for every name (*correct* — nothing to check) while `mint_concept_slug` yields
  `sharpe-ratio` / `diversification` / `виталик-бутерин`. The regression the issue describes is
  gone, and a future caller passing `layout.slug_strategy` straight through is now safe.
