# TASK 052 — wiki-import: meeting participants → `participants:`, not `_concepts/` person pages

## 0. Meta Information
- **Task ID**: 052
- **Slug**: import-participants-not-concepts
- **Type**: VDD fix (bug / config-gap in the construct path)
- **Effort**: S (a+b code ~30 LOC, c docs, d tests)
- **Context**: Dogfood on the live personal vault (`06 - Business Development`, the Айва
  demo import) filed meeting **participants** (Сергей, Алексей Бондарев) as
  `_concepts/*.md` **person pages**. The vault owner's rule: people are **participants**
  of a protocol, not domain concepts (see auto-memory `meeting-participants-not-concepts`).
- **Architecture**: no structural change — a refinement inside the existing config-driven
  write-grammar (ADR-007). `docs/ARCHITECTURE.md` untouched; a one-line note may be added to
  the wiki-import functional sub-doc. No schema change (zero-DDL, `user_version` 7).

## Problem / Motivation (root cause — verified against source)

For a `--kind meeting|lesson` import (grammar = **pyramid**), the REASON step's note-JSON
has **no home for people** and every downstream path treats a `person` entity as a domain
concept, so attendees become `_concepts/` pages:

1. **No participants channel + an entity quota that invites attendees.** The note-JSON
   contract ([reason-contract.md](../skills/wiki-import/references/reason-contract.md) L42-55)
   has **no `participants` field**, while `entities[].type` enumerates
   `person|company|product|group` and Hard-rule L123 mandates **12–15 entities**. A model with
   nowhere to put people and a quota to fill lists the attendees as `{type:"person"}` entities.
2. **`derive_candidates` files every entity type with no person filter.**
   [`_authoring.py`](../scripts/wiki_skills/wiki_import_article/_authoring.py) L361
   (`entity_type: e.get("type", "concept")`) passes `person` straight through; it takes **no**
   grammar/kind argument.
3. **`assemble_note` never stamps `participants:`** ([`_authoring.py`](../scripts/wiki_skills/wiki_import_article/_authoring.py)
   L252-268), so people have literally nowhere to live except an entity page.
4. **The layout maps `person → db_type concept`** ([obsidian-personal.yaml](../scripts/wiki_index/layouts/obsidian-personal.yaml)
   L114, TASK 037 — **correct**; removing it UnmappedTypeError-drops the page, so the mapping
   is NOT the lever).

**Levers assessment (verified):** `--no-concepts` / `extract_concepts:false` only **DEFERS**
filing (the `/wiki-extract-concepts` prompt re-mints persons) — not a durable fix; there is
**no entity-type-exclusion knob** anywhere in config. The load-bearing fix is therefore a
**deterministic code guard** in `derive_candidates` (drop `person` entities for pyramid
grammar), complemented by a real `participants:` home + a contract rule so weak models stop
smuggling people into `entities[]`.

## Goal

Meeting/lesson (pyramid) imports record people in the note's **`participants:` frontmatter**
and **never** file a `_concepts/` page for a `person` entity — deterministically, on any
model — while article/paper/thread (article grammar) behavior stays **byte-identical**.

## Design (3 slices, additive / zero-DDL)

- **(a) Code guard (load-bearing).** `derive_candidates` gains a `grammar: str = "article"`
  kwarg; when `grammar == "pyramid"`, an entity whose sanitized `type == "person"` is skipped
  with reason `participant-not-concept` (reported in `skipped`, **NOT** in
  `_LOSSY_SKIP_REASONS` — it is intentional, not a recoverable loss). Threaded from the
  existing `grammar` at the `apply` call site
  ([__init__.py](../scripts/wiki_skills/wiki_import_article/__init__.py) L613 → L701).
  `group` is deliberately **kept** (a committee/team can be a real domain concept); scope is
  `person` only (the exact complaint).
- **(b) Participants home (complement).** `assemble_note`, for `grammar == "pyramid"` and a
  non-empty `note["participants"]` (list of strings), stamps a `participants:` YAML block
  (each value `_fm_scalar`-sanitized, H-6). Article grammar and pyramid-without-participants
  are untouched → byte-identity preserved.
- **(c) Contract (complement, generalizes to weak models).** Add `participants: [string]` to
  the note-JSON schema (meeting/lesson only) and a Hard rule "meeting/lesson **attendees** go
  in `participants[]`, NOT `entities[]`; `entities[]` is for durable domain concepts
  (companies/products/systems/methods)" to
  [reason-contract.md](../skills/wiki-import/references/reason-contract.md) +
  [skills/wiki-import/SKILL.md](../skills/wiki-import/SKILL.md); note that `apply` now drops
  `person` entities for pyramid kinds.

## Requirements Traceability Matrix (RTM)

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| R1 | `derive_candidates` drops `person` entities for pyramid grammar | ✅ | (1) add `grammar: str = "article"` kwarg; (2) `grammar=="pyramid"` + sanitized `type=="person"` ⇒ skip with reason `participant-not-concept`, `continue`; (3) `group`/`company`/`product`/`external`/`concept` unaffected; (4) thread `grammar=grammar` from the apply call site (L701) |
| R2 | `assemble_note` stamps `participants:` for pyramid | ✅ | (1) `grammar=="pyramid"` AND `note["participants"]` non-empty ⇒ emit a `participants:` YAML block from the list; (2) each value `_fm_scalar`-sanitized (H-6, no YAML-key/newline injection); (3) placed in frontmatter (after `lang:`); (4) article grammar OR absent participants ⇒ NO block (byte-identity) |
| R3 | Note-JSON contract documents `participants[]` + the rule | ✅ | (1) add `participants: [string]` (meeting/lesson) to the schema in `reason-contract.md` + `SKILL.md`; (2) Hard rule: attendees → `participants[]`, not `entities[]`; (3) state that `apply` drops `person` entities for pyramid kinds; (4) entity-count guidance clarified (entities = domain concepts, not people) |
| R4 | Invariants preserved | ✅ | (1) zero-DDL (`user_version` 7 — `participants` rides `frontmatter_json`); (2) Decision-17 (no `import anthropic`; deterministic plumbing + JSON envelope); (3) byte-identity for article grammar AND pyramid-without-participants; (4) `participant-not-concept` NOT in `_LOSSY_SKIP_REASONS` (quiet, observable only in `skipped[]`); (5) vendor-agnostic (contract + code, no model-specific capability) |
| R5 | Test coverage | ✅ | (1) `derive_candidates(grammar="pyramid")` drops `person`, keeps concept/company/product/external/group; (2) `derive_candidates(grammar="article")` KEEPS `person` (back-compat); (3) `assemble_note(grammar="pyramid")` stamps `participants:` from note; article grammar does NOT; H-6 injection attempt neutralized; (4) `apply` integration: a meeting note with person entities ⇒ 0 person `_concepts/` pages + participants in frontmatter; (5) full `pytest` + `mypy --strict scripts/` green |

## Use Cases

- **UC-1 (meeting import).** `/wiki-import call.txt --kind meeting`: the REASON step lists
  attendees in `participants[]` and domain entities (companies/products/systems) in
  `entities[]`. `apply` files the note with `participants:` frontmatter and `_concepts/` pages
  only for the domain entities — **no** person pages.
- **UC-2 (weak model still leaks a person into `entities[]`).** Even if the model ignores the
  contract and lists an attendee as `{type:"person"}`, `derive_candidates` (pyramid) drops it
  (`participant-not-concept`) — deterministic, no person page filed.
- **UC-3 (article import unchanged).** `/wiki-import article.md --kind article` referencing a
  researcher as a `person` entity still files that concept page (article grammar); output
  byte-identical to today.
- **UC-4 (BD zone).** With `06 - Business Development/.wiki/sync.yaml` `profile: meeting`, a
  future transcript ingested via `wiki-sync` yields a clean protocol: participants in
  frontmatter, no person concept pages — even with `extract_concepts: true` (so genuine
  competitor/tool concepts are still filed).

## Invariants that must not break

- **Zero-DDL** — `participants:` is ordinary frontmatter (`frontmatter_json`); no schema
  change. `user_version` stays 7.
- **Decision-17** — no `import anthropic`; both code slices are deterministic plumbing; the
  orchestrator owns REASON.
- **Byte-identity (scoped)** — article/paper/thread grammar unchanged; pyramid **without**
  `participants` unchanged. Only pyramid-**with**-participants gains the frontmatter block and
  loses person concept pages (the intended behavior).
- **Non-lossy skip** — `participant-not-concept` is intentional; it must NOT raise a
  `CONCEPTS_DROPPED` warning (kept out of `_LOSSY_SKIP_REASONS`), only appear in `skipped[]`.
- **Vendor-agnostic** — contract + deterministic code; works across every LLM CLI.

## Open Questions

- **Q-052-1 (drop `group` too?)** — NO for MVP. `person` is the exact complaint; a
  `group`/committee/team can be a legitimate domain concept (e.g. «архитектурный комитет»).
  Keep `group`; revisit only if a real over-filing case appears.
- **Q-052-2 (participants placement)** — frontmatter `participants:` (queryable via
  `--where`, mirrors the `summarizing-meetings` template) vs a body section. Chosen:
  frontmatter (metadata, filterable, and the native meeting template already uses it).
- **Q-052-3 (retro-clean existing person pages?)** — out of scope for the framework change;
  the live-vault cleanup (Айва note) was already done manually this session.
- **Q-052-4 (non-attendee persons).** The drop is by TYPE, not attendance — a `person` merely
  MENTIONED (a cited author, a candidate) is also dropped and is NOT auto-added to
  `participants[]`. Accepted: pyramid notes do not concept-track people by design; the drop is
  **visible in `skipped[]`** (not a silent loss), and a page can be minted deliberately via
  `/wiki-extract-concepts`. Restricting the drop to persons matched in `participants[]` was
  rejected — brittle name-matching ("Иван" vs "Иван Петров — CTO") for negligible benefit.
