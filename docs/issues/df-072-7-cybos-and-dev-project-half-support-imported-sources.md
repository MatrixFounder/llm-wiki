---
id: DF-072-7
type: known-issue
status: fixed
opened_at: 2026-08-07
resolved_at: 2026-08-07
category: correctness
severity: SEV-2
slug: df-072-7-cybos-and-dev-project-half-support-imported-sources
---

# `cybos` **and** `dev-project` declared the imported-source classes in `type_mapping` with **no read glob that could see them** — an imported note was written, exited 0, and was never indexed, with `skipped[]` EMPTY

The TASK-063 conjunction trap, third recurrence, live on `main`: **a layout must map the
class AND its read globs must SEE the write dir.** TASK 046 added `summary` /
`article-summary` / `meeting-summary` / `lesson-summary` to both layouts' `type_mapping`
— the first conjunct only.

## The measurement (never by eye)

A cybos vault holding a well-formed `Articles/Some Paper.md` (`type: article-summary`)
and `Articles/_concepts/topic.md` (`type: concept`), reindexed full:

```
skipped: []
INDEXED PAGES:
    hypotheses/h1.md | research
files on disk: ['Articles/Some Paper.md', 'Articles/_concepts/topic.md',
                'WIKI_SCHEMA.md', 'hypotheses/h1.md']
```

**Two files, perfectly valid, mapped types — absent from the index and absent from every
report.** This is worse than "pruned": the walker never reached them, and `skipped[]`
only reports files the walker DID see. `wiki-lint` is *structurally incapable* of
flagging it — a page absent from the index cannot fail an index check.

## Why it is not "cybos has no visible folders"

It has 18, and that is the subtle part. The only walker-visible folders were the typed
knowledge-class dirs (`decisions/`, `hypotheses/`, …). So an article was indexable **only
if filed into another class's folder**. A naive check ("is there a visible folder?")
answers YES — and the first cut of the regression test below **passed on the bug** for
exactly that reason. The property must be type-aware: a valid import home is covered by a
glob declaring an imported-source type, or declaring none.

## Scope — the plan named ONE layout, the census found TWO

`docs/PLAN.md` bead 072-10b named `cybos.yaml`. Probing every built-in layout with
`cover_refusal` (the walker's own five-conjunct chain) found **`dev-project.yaml` carries
the identical defect** from the same TASK-046 change. Both fixed in the same commit.

`karpathy` and `obsidian-personal` are correct within their own grammars (`_sources/` at
the vault tier; the numbered PARA folders) — measured, not assumed.

Secondary finding, same probe: dev-project's other globs are **single-level**
(`tasks/*.md`), so only 5 of its 15 visible folders could hold a sibling `_concepts/`
page. The same one-line fix closes it.

## The fix

One glob per layout — `sources/**/*.md`, `type: summary`. `**` covers the sibling
`_concepts/` pages too, so one line closes both halves. `type: summary` is only the
fallback for an untyped capture: a note's own frontmatter `type:` wins
(`normalization.py` PW-C/F precedence), so an `article-summary` filed there still indexes
as `article-summary` — verified end-to-end through a real `reindex_full`.

## Why a TEST and not a comment

**Both layout files already carried a comment block spelling this lesson out — twice**
(DF-049-1 for the RAG write surfaces, then TASK 063 G4 for the typed-knowledge surfaces).
The TASK-046 classes landed anyway. `tests/test_layout_write_home.py` walks the
**glob-discovered** layout population and asserts the property for **every** class in
cybos's `type_mapping`, with an explicit co-located table that must partition the
remainder EXACTLY — so a class added tomorrow with no home goes RED, and so does a stale
entry. Verified against the pre-fix tree: **6 of 7 RED**.

## Operator override (OQ-4 = both)

Generated from the fixed built-in (not transcribed) at
`<scratchpad>/elma-kb-layout-override.yaml`. ⚠️ `<vault>/.wiki/layout.yaml`'s `paths:`
**REPLACES** the built-in list entirely, so the override must carry every glob — which
makes it a maintenance hazard: it freezes the list at generation day and silently misses
any glob a future release adds. **With the repo fix landed it is needed only by an
install that lags this tree.** Not committed as a template for that reason; the
`elma-kb` vault is not present on this machine, so it was not applied to a real vault.

## Residual — NOT fixed here, deliberately

`wiki-import` has **no G4-style gate on the note itself**. `_layout_indexes_concepts`
checks the `_concepts/` half and degrades gracefully, but nothing checks that the NOTE's
own target dir is walker-visible — so filing into any uncovered folder is still silent on
every layout. `wiki-extract-decisions prepare` already does this correctly
(`TYPED_DIR_NOT_COVERED_BY_LAYOUT`, refuse early and loudly). Porting that gate to
`wiki-import` is a behaviour change on a shipped CLI and belongs to its own task; the
glob fix here removes the *cause* on the two broken layouts but not the *class* of
failure.

## Related

- [[the-unenumerated-surface-lens]] — the plan's "4 classes / one layout" was an
  under-count on both axes; the census found 10 classes across 2 layouts.
- `tests/test_layout_write_home.py` — the property, the RED proof, and the
  discrimination control.
- ADR-002 §D8 — Class B must be 100% rebuildable from Class A. A markdown page the
  walker cannot see breaks that invariant silently.
