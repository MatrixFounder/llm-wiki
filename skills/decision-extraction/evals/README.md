# `decision-extraction` — the eval set

Nine fixtures. Every one guards a **specific failure mode with a mechanism behind it**,
and every one is **GRADED** — not merely parsed.

## What "graded" means here

Each fixture carries three files:

| file | role |
|---|---|
| `input.md` | the source protocol |
| `expected.json` | the CORRECT extraction — fed through the **real** `apply` validators |
| `grading.json` | **why this fixture exists**, the expected class census, the expected edge census, and (where present) the counterexample's required refusal code |
| `counterexample.json` | the WRONG extraction — must be **REFUSED**, with the exact code stated in `grading.json` |

The runner asserts all four. That matters, because the three weakest ways to write an
eval are all still green without it:

- **an eval whose expected output the rail would REFUSE** teaches the model a shape the
  code rejects, while looking like coverage;
- **an eval with no census** passes even when the extraction silently drops half the
  protocol's own rows — every page it *did* write is perfectly valid, so no validator
  complains. (This is not hypothetical: the first hand extraction on a real protocol
  dropped **4 of 9** decision rows and **5 of 9** risks.);
- **an eval with no counterexample** turns every SKILL rule into prose. A doc rule with
  no failing case is a doc rule that rots.

## ★ Every fixture runs under BOTH slug strategies

The evals used to run on `cybos` alone — **which is `transliterate`, while the operator's
live vault is `obsidian-personal` / `preserve-unicode`.** The eval set was exercising a
slug strategy nobody uses and not exercising the one that ships. Both are run now:

| layout | slug strategy | who runs it |
|---|---|---|
| `cybos` | `transliterate` | the typed-knowledge grammar |
| `para-typed` (`obsidian-personal` + typed classes) | `preserve-unicode` | **the operator's live vault** |

**Edge targets in `expected.json` are TITLES, not slugs** — because a slug is
*layout-dependent*. The runner slugifies an in-batch title with the layout's own
strategy, and passes an existing page's slug (e.g. `dec-ocheredi`) through verbatim.
That is exactly what the REASON step does with `prepare`'s contract.

## ★★ WHY THE INPUTS ARE IN RUSSIAN — and must stay that way

Not a preference. **An English fixture cannot produce the failures these evals exist to
catch.** Measured, not asserted:

| failure mode | reachable in Russian | reachable in English |
|---|---|---|
| `transliterate` collapses **`ё` / `е`** — `Критерии приёмки` and `Критерии приемки` become **one slug**, and the second page **silently overwrites** the first (one file, one DB row, one requirement gone, **zero lint issues** — the count is right) | ✅ fixture **05** | ❌ never |
| `preserve-unicode` mints **Cyrillic slugs** — `is_valid_slug` must accept them (`\w` under `re.UNICODE`) | ✅ | ❌ |
| NFC normalisation in the verbatim-quote check (`ё` is `е` + a combining diaeresis in NFD) | ✅ | ❌ |

Real Russian protocols spell `ё` and `е` inconsistently *in the same document* — fixture
05's `input.md` does exactly that, because real transcripts do. **That is the whole
point**: under `transliterate` the batch is REFUSED (`IN_BATCH_SLUG_COLLISION`); under
`preserve-unicode` it is CORRECT and both pages are written. Both behaviours are right,
and an eval set on one layout proves nothing about the other.

`SKILL.md` stays in **English** — it is read by the model, and English is the project
convention for docs and code. The **inputs are the domain**, and the domain is Russian.

## The fixtures

| # | guards |
|---|---|
| **01** meeting-with-decisions | the happy path — bind to the protocol's OWN sections instead of free-forming; census asserted |
| **02** deferred-no-decisions | ★ **an empty extraction is a SUCCESS**. Without it, `CANDIDATE_COUNT_MIN = 0` is a constant no eval exercises |
| **03** supersede | G3 — a `supersedes` onto an EXISTING page; the rail reconciles its status from the layout's own drift rule |
| **04** bare-id-in-prose | ★ **bare IDs in prose ARE refs** — `DEC-004` in body text creates a reference that must resolve |
| **05** slug-collision-cyrillic | ★★ **the LAYOUT-DEPENDENT fixture** — `ё`/`е` collapse under `transliterate`, stay distinct under `preserve-unicode` |
| **06** decision-causes-risk | ★★ **the edge the first live run FORGOT** — `decision --causes--> risk`: *what risk does this decision CREATE?* |
| **07** open-commitment | ★ **a gap is DATA, not a defect** — the counterexample is the "helpful" invented decision that closes it |
| **08** ontology-violation | ★ **there is no `mitigates`** — the most natural edge to want, and the ontology does not have it |
| **09** participants-are-not-knowledge | ★ attendees belong in `participants:`, never in the graph — the ROSTER is the only enforcement point on this path |
