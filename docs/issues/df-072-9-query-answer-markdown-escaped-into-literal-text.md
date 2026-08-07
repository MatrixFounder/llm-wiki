---
id: DF-072-9
type: known-issue
status: open
opened_at: 2026-08-07
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

## Not fixed here — it is a design decision, not a bug fix

Two directions, and they are not equivalent:

- **(a) Change the contract, not the code.** State in `wiki-query-synthesis/SKILL.md`
  that the answer must be **plain prose without markdown structure**, and say why. Costs
  nothing in security, costs readability. ⚠️ The file is **H-5 hash-pinned** — an approved
  edit must be re-pinned with `scripts/pin_skill_integrity.py --write`.
- **(b) Allow a safe structural subset** on egress (ATX headings, `- ` bullets) while
  still escaping wikilinks, HTML, links and code spans. Better artifact, but it **weakens
  a security control that exists because of the H-4 hardening**, and every relaxation
  needs an injection audit — a `- ` bullet is harmless, a `|` table row that reaches a
  dataview context may not be.

Picking between them is the operator's/architect's call. This issue exists so the choice
is made deliberately rather than discovered again by the next person who reads a filed
answer.

## Related

- `scripts/wiki_skills/_common.py::sanitize_markdown_text` — the allowlist and its H-4
  attack list.
- `skills/wiki-query-synthesis/SKILL.md` — the contract that asks for markdown (H-5
  pinned).
- [[the-unenumerated-surface-lens]] — every automated check passed; only reading the
  output found it.
