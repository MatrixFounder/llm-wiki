# 032-05 — graph-aware RAG (`wiki-query --follow-edges`)  ·  `tdd-strict` · SEPARABLE final

**Owns:** AC-6.1. **Dep:** 032-03. **Detail:** PLAN.md §2 / ADR-004 D5 / Q-032-4.

> **Separable:** depends only on 032-03 reads. If `question_hash` determinism converges slowly under `/vdd-multi`, this splits to a [LIGHT] follow-up WITHOUT blocking the graph foundation (032-00..04).

## Scope
`wiki-query prepare` optionally follows typed edges from the FTS hits to pull neighbors into the retrieval set.

## Files
- `scripts/wiki_skills/wiki_query.py` — `prepare --follow-edges` (**default OFF**) + `--edge-depth` (cap 3); in `_retrieve` (`:167-205`), after the FTS hits, expand along edges (`refs_from`/`get_backlinks`), **exclude `type=query`/`type=verification`** (mirror `:189`), append AFTER the FTS hits sorted `(ref_type, project, slug)`, dedup vs hit set; fold the expanded set into `_question_hash` (`:87-94`); envelope hits gain `via_edge: {from, ref_type}`.

## Stub-First (RED → GREEN)
`--follow-edges` pulls the `causes` neighbors in STABLE order; `question_hash` identical across `prepare`→`apply` for the same inputs (no `QUESTION_CHANGED`); **default-OFF leaves today's wiki-query behaviour byte-identical** (existing `test_wiki_query_*` green); grounding gate still holds (edge-pulled neighbor cited only if a real hit).

## Verify
`mypy --strict`; existing wiki-query suite green with the flag OFF.
