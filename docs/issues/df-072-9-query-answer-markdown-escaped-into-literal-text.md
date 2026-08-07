---
id: DF-072-9
type: known-issue
status: fixed
opened_at: 2026-08-07
resolved_at: 2026-08-07
category: quality
severity: SEV-3
slug: df-072-9-query-answer-markdown-escaped-into-literal-text
---

# `wiki-query apply` escapes the synthesised answer's **structural** markdown, so a filed answer renders as literal text — while `wiki-query-synthesis/SKILL.md` instructs the orchestrator to produce *"a concise markdown answer"*

Found by the first end-to-end dogfood of the RAG loop on a real 3054-page vault. Not
visible from the code: `apply` exits 0, the page indexes, the citations validate, and
every test passes. It is visible only by **reading the artifact in the vault**.

## What lands on disk

The orchestrator wrote `## 1. Векторный (семантический) поиск`, `- Страница-концепт …`
and `` `1/(k + rank)` ``. The filed page contains:

```
\## 1. Векторный (семантический) поиск
\- Страница-концепт определяет гибридный поиск как схему, где …
… суммой \`1/(k + rank)\` по всем системам …
```

In Obsidian that is a wall of visible backslashes: no headings, no bullets, no code
spans. For a knowledge base whose whole purpose is that filed answers **compound**, an
answer nobody wants to re-read is a real cost.

## The two halves are each correct — the contradiction is between them

- `_common.sanitize_markdown_text` is a deliberate **text-only allowlist**, and its
  docstring says so: it escapes leading `#`/`>`/`|`/`*`/`+`/`-`/`~`, all backticks, and
  all brackets, "so `text` renders as literal plain prose". That is the R-6.3 egress
  guard and the H-4 hardening — **the security control working exactly as specified**.
- `skills/wiki-query-synthesis/SKILL.md` tells the orchestrator to "Produce: 1. A concise
  **markdown** answer that cites the sources it draws on", and its output contract says
  "Plain markdown prose."

An orchestrator that follows the contract literally produces structure; the sanitizer
escapes precisely that structure. The SKILL.md warns that HTML and `[[wikilinks]]` will
render as literal text — it does **not** say the same of headings, bullets and code
spans, so the contract reads as if ordinary markdown survives. It does not.

## Reproducer

```bash
wiki-query prepare "<question>" --vault <v> --vault-root <root>
printf '## Heading\n\n- bullet\n\n`code`\n' \
  | wiki-query apply --vault <v> --vault-root <root> --query-slug <slug> \
      --question "<question>" --question-hash <hash> \
      --answer-stdin --citations-file <cites.json>
grep -n '\\\\#\\|\\\\-\\|\\\\`' <root>/_queries/<slug>.md
```

## Scope

`sanitize_markdown_text` is shared (Decision-16), so `wiki-extract-concepts` concept
bodies get the same treatment. It matters less there — a concept definition is one or two
sentences of prose — and much more for a `_queries/` answer, which is the one artifact
this system asks an LLM to *structure*.

## ✅ FIXED 2026-08-07 — option (b), scoped so it relaxes nothing that did not ask

**`_common.sanitize_answer_markdown`**, a SECOND function used only by `wiki-query
apply`'s answer body. `sanitize_markdown_text` is byte-for-byte unchanged, so the
concept/decision/verify rails keep the strict guard.

The escape set is IDENTICAL — HTML entities, every backtick, every bracket. Only the
line-leading rule narrowed: a line whose stripped form is `#{1,6}` + space + text, or `-`
+ space + text, keeps its leading character. Still escaped: `#tag` (an Obsidian tag —
pollutes the vault tag index), `---`, `~~~` (**the alternative code fence — the one
leading character here that is genuinely dangerous**), `>`, `|`, `*`, `+`.

★ **The relaxation makes the guard COHERENT rather than weaker in kind.** Measured, not
argued: ordered lists (`1. item`) have ALWAYS passed through untouched, because digits
were never in `_LINE_LEADING_MD_ACTIVES`. The shipped behaviour rendered a numbered list
and mangled a bulleted one — an asymmetry nobody chose.

`tests/test_answer_sanitizer.py` (36 tests): the H-4 attack list re-run through the NEW
function; a lookalike table where each entry differs from an allowed form by ONE
character; the composition case the relaxation actually creates (a wikilink riding inside
an allowed bullet); and a blast-radius control asserting the STRICT function still
escapes structure. Mutation-verified — heading rule without the space requirement → 3
RED; structural rule widened to any leading char → **11 RED**, including `~~~mermaid`.

`skills/wiki-query-synthesis/SKILL.md` now states exactly what survives, in a table, and
tells the orchestrator not to reach for tables/blockquotes/code spans. H-5 re-pinned.

### Considered and rejected

Two other directions, recorded because rejecting them is part of the decision:

- **(a) Change the contract, not the code.** State in `wiki-query-synthesis/SKILL.md`
  that the answer must be **plain prose without markdown structure**, and say why. Costs
  nothing in security, costs readability. ⚠️ The file is **H-5 hash-pinned** — an approved
  edit must be re-pinned with `scripts/pin_skill_integrity.py --write`.
- **(c) Widen the SHARED function** — allow a safe structural subset on egress (ATX headings, `- ` bullets) while
  still escaping wikilinks, HTML, links and code spans. Better artifact, but it **weakens
  a security control that exists because of the H-4 hardening**, and every relaxation
  needs an injection audit — a `- ` bullet is harmless, a `|` table row that reaches a
  dataview context may not be.

**(a) was rejected on a mechanism argument, not a taste one**: the rule "write plain
prose" is enforced by a *sanitizer*, so a violation is not caught — it is silently
mangled. A contract that fights a strong model prior (every model writes headings for a
structured answer) and whose enforcement is invisible is a contract that degrades in the
dark. **(c) was rejected on blast radius**: it would relax H-4 for a rail built from
untrusted extracted text to solve a problem in a different rail.

## Related

- `scripts/wiki_skills/_common.py::sanitize_markdown_text` — the allowlist and its H-4
  attack list.
- `skills/wiki-query-synthesis/SKILL.md` — the contract that asks for markdown (H-5
  pinned).
- [[the-unenumerated-surface-lens]] — every automated check passed; only reading the
  output found it.
