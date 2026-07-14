---
name: decision-extraction
description: The REASON contract for wiki-extract-decisions (TASK 063 / RFC-004) — turn a summarised source note into typed decision/requirement/risk pages with forward edges. Load this after `wiki-extract-decisions prepare`, before `apply`.
---

# decision-extraction

You are extracting **typed knowledge** from a source note into `decision` /
`requirement` / `risk` pages. The CLI does the plumbing; **you do the reading**.

`wiki-extract-decisions prepare` has already given you an envelope. It contains the
**ontology contract** — the class roster, every edge's domain and range, and every
class's `status` enum. That contract is not advice. `apply` validates against it and
**refuses the whole batch on any violation** (exit 4, zero files written).

## Read the protocol's OWN structure — do not free-form extract

These source notes already have the structure. Bind to it:

| protocol section | class |
|---|---|
| «Ключевые решения» / "Key decisions" | `decision` |
| НФТ / KPI / acceptance criteria | `requirement` |
| «Реестр рисков» / "Risks" | `risk` |
| «Открытые вопросы» | usually a `requirement` with no owner yet — see below |

Free-form extraction over a structured document invents structure that is already
there. Inventing is the exact failure this whole rail defends against.

## ★ AN EMPTY EXTRACTION IS A SUCCESS

`[]` is a legitimate, correct, **rewarded** answer. A note with no decisions in it is a
normal note — most notes are.

`apply` returns `action: no_candidates`, **exit 0**. There is no penalty. If you cannot
point at a sentence in the source that states a decision, **there is no decision.**

## ★ EVERY CANDIDATE CARRIES A VERBATIM `source_quote`

The quote must occur **in the source body, verbatim**. `apply` checks it
(`FIELD_QUOTE_NOT_IN_BODY`, exit 4) and there is **no escape hatch** — the env var the
sibling concept-extraction skill honours is deliberately not read here.

This is not paperwork. It is what makes a fabricated decision *mechanically expensive*:
an invention has no quote to point at.

## ★ AN OPEN COMMITMENT IS DATA, NOT A DEFECT

A `requirement` with nothing implementing it is a **`wiki-health coverage` gap** — and a
gap is a **FACT about the engagement**, reported at exit 0. `prepare` emits
`open_commitments: N` as an OUTPUT, because that number is the deliverable.

**Do NOT invent a decision that "closes" it.** The pilot (TASK 062) surfaced three real
open commitments from the operator's own protocols — a target accuracy not yet set, a
client paused on a domestic-software-registry question, a partner action item with no
due date. Every one was a genuine open question with a real client. Inventing a closure
for any of them would have been a lie written into the knowledge base.

## ★★ BARE IDs IN PROSE ARE REFS — never cite one

On the `cybos` layout, `ref_extraction` ships an `id-ref` rule:

```
\b(ADR-\d+|R-\d+(?:\.\d+)*|task-\d+(?:-\d+)*|DEC-\d+|INC-\d+|RISK-\d+|REQ-\d+|HYP-\d+)\b
```

So a sentence in your **body text** like:

> Это отменяет **DEC-004**.

**creates a reference** that must resolve — and if `dec-004` is not a page, `apply`
refuses the batch on G2 (`UNRESOLVED_REF`).

**Rule: reference other pages ONLY via wikilinks to slugs that exist or are in this
same batch. Never cite a bare ID.**

```
✗  Это отменяет DEC-004.
✓  Это отменяет [[dec-ocheredi]].          ← the slug exists (prepare listed it)
✓  Это отменяет прежнее решение по очередям. ← or just say it in words
```

Without this rule, well-written prose bounces the batch repeatedly and the rail feels
*flaky* — a correct gate producing an unusable product.

## The candidate shape

```jsonc
{
  "class": "decision",                     // ∈ the roster prepare gave you
  "title": "Отказаться от Kafka в MVP",
  "status": "accepted",                    // ∈ that class's status enum, from the contract
  "date": "2026-07-14",                    // optional
  "body": "Kafka избыточна для MVP...",     // markdown
  "source_quote": "Мы решили отказаться от Kafka в MVP.",   // ★ VERBATIM, mandatory
  "edges": {                               // ★ FORWARD ONLY
    "implements": ["latency-pod-200ms"],
    "supersedes": ["dec-ocheredi"]
  }
}
```

**Forward edges only.** Author `implements:`; **never** `implemented-by:`. The inverse is
auto-derived at reindex — authoring both sides would let a page assert an edge whose
inverse contradicts it.

**Edge slugs**: use the slugs `prepare` listed in `known_typed_pages` /
`existing_page_slugs`, or the slug another candidate in THIS batch will get. Everything
else is an unresolved ref.

## What `apply` will refuse (so you can avoid it)

| refusal | cause |
|---|---|
| `FIELD_QUOTE_NOT_IN_BODY` | the quote is not verbatim in the source |
| `ONTOLOGY_VIOLATION` | class not in the roster · edge domain/range · status not in the enum |
| `UNRESOLVED_REF` | a wikilink or a **bare ID in prose** that resolves to nothing |
| `IN_BATCH_SLUG_COLLISION` | two candidates whose titles yield the same slug — **give them distinct titles** |
| `REQUIRES_STATUS_RECONCILIATION` | you superseded a decision the operator had already `rejected` |

All of them are **exit 4, zero files written**. The batch is atomic.

## You do not call a model API here

This skill is a **contract**, not a call. The orchestrator (you) reads the source and
synthesises the JSON; the CLI is deterministic plumbing on both sides (Decision-17).
