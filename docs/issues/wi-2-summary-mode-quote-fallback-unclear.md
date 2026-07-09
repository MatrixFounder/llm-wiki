---
id: WI-2
type: known-issue
status: fixed
opened_at: 2026-07-09
closed_at: 2026-07-09
category: robustness
severity: SEV-3
slug: wi-2-summary-mode-quote-fallback-unclear
---

# wiki-import: in `mode=summary` the entity-quote "body-line" fallback has no body — clarify + guard

- **Symptom / risk**: `reason-contract.md` (Hard rule 2) says that when an `entities[].quote` is not a verbatim substring, `apply` "falls back to a body line that mentions the entity by name … if there's no such line it drops the candidate (`no-verbatim-quote`)." But in `mode=summary` the note `body` is **null** by design (depth-by-mode table) — the entity's only textual home is `tldr` + `summary_bullets`. So the described body-line safety net is either (a) unreachable, silently dropping every entity whose quote isn't an exact substring of tldr/bullets, or (b) actually searching the *rendered* note text (which includes the bullets) — the contract doesn't say which, and the two behaviours differ materially.
- **Why it matters**: an author following the contract for a `paper`/`summary` import can lose concept pages with no obvious signal. In the 2026-07-09 dogfood (`arxiv.org/abs/2510.08369`) this was avoided only by hand-authoring all 13 quotes as verified substrings of the bullets (quote-first + a pre-apply substring self-check) — i.e. the fallback was never exercised, so its summary-mode behaviour is unverified from that run.
- **Root cause**: the fallback was specified against the full-mode grammar (which has a `## Полный текст` body); summary-mode grammar (tldr + bullets only) wasn't carved out.
- **Affected components**: `skills/wiki-import/references/reason-contract.md` (Hard rule 2; depth-by-mode + note-grammar tables); the quote-resolution path in `wiki-extract-concepts` apply invoked by `scripts/wiki_skills/wiki_import_article/` (verify what text the fallback searches).
- **Fix plan**:
  1. **Verify** what the quote-fallback searches in summary mode — the rendered note (tldr + bullets) or only the `body` field. If the latter, make it search the rendered summary text so bullets count.
  2. **Document explicitly** in the contract: "in `mode=summary`, `body` is null → every `entities[].quote` MUST be a verbatim substring of `tldr`/`summary_bullets`; there is no body fallback." Make the summary-mode pre-apply self-check state this.
  3. Consider surfacing a `no-verbatim-quote` drop count more prominently in the `apply` envelope's `warnings[]` for summary mode (today `CONCEPTS_DROPPED` exists; make sure it fires here).
- **Resolution (2026-07-09, TASK 055)**: **verified** the behaviour is (b) — the quote fallback searches the
  **rendered** note, not a `body` field. `apply` calls `derive_candidates(entities, note_text, …)` where
  `note_text` is the fully-assembled note (`__init__.py`), which in `mode=summary` contains the `tldr` + the
  `## Ключевые выводы` bullets. So `verbatim_quote`'s name-mention fallback **does** search the bullets; an
  entity named in NO bullet/tldr drops `no-verbatim-quote`, and that reason **is** in `_LOSSY_SKIP_REASONS`
  → the `CONCEPTS_DROPPED` warning already fires (fix plan item 3 satisfied). **Documented explicitly** in
  `skills/wiki-import/references/reason-contract.md` Hard rule 2 with a dedicated `mode=summary` carve-out
  (body is null → every `entities[].quote` MUST be a verbatim substring of `tldr`/`summary_bullets`; the
  fallback searches the rendered summary text; drops surface as `CONCEPTS_DROPPED`). Regression test:
  `test_wi2_summary_mode_quote_fallback_searches_rendered_bullets` (`tests/test_import_article_authoring.py`)
  proves a bullet-line mention rescues a paraphrased quote and a name absent from tldr+bullets is dropped.
  No code change to the quote path was needed (it was already correct); this closes the contract-ambiguity.
