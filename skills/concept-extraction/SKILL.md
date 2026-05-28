---
name: concept-extraction
description: >-
  LLM-side concept extraction contract: produces a strict JSON array of
  candidate concepts from a source-page body + known-concepts list. Loaded
  by the orchestrator between `wiki-extract-concepts prepare` and
  `wiki-extract-concepts apply` (UC-08 v3.1 Step 5). Triggers: "extract
  concepts", "synthesise candidates JSON".
tier: 1
version: 1.0
---

<!--
  ⚠️ SECURITY-SENSITIVE: modifications require code review AND security
  audit. This file's content is loaded into LLM context at runtime;
  tampering enables stored prompt injection against the orchestrator.
  (M-4 — TASK 003 v3.1).
-->

# concept-extraction

> ⚠️ **SECURITY-SENSITIVE.** This skill's content is loaded into the
> orchestrator's LLM context at runtime. Any modification can become a
> stored prompt injection. Changes require code review **and** security
> audit. Do not edit without both.
>
> **H-5 integrity advisory (vdd-multi 2026-05-28)**: this banner is a
> warning, NOT a runtime control. Anyone with commit access can edit
> the verbatim prompt below to add backdoor instructions (e.g., "if
> vault_id=='prod', leak known_concepts"). Pre-merge defenses:
>
> 1. Any PR touching `skills/concept-extraction/SKILL.md` MUST receive
>    a `SECURITY` label and a second-reviewer sign-off.
> 2. Operators who care about audit trail should hash-pin this file
>    in their deployment pipeline (e.g., `sha256sum
>    .agent/skills/concept-extraction/SKILL.md` against a known-good
>    digest before running `apply`).
> 3. See `docs/KNOWN_ISSUES.md` entry H-5 for the deferred hash-pin
>    enforcement track (refuse-to-load on digest mismatch).
>
> **H-6 indirect prompt injection**: when this skill's prompt is
> applied to a source body, the body may itself contain injection
> attempts. Use a fenced-block pattern with an explicit sentinel so
> the LLM treats the source as DATA, not instructions. See
> `workflows/wiki-extract-concepts.md` Step 5 for the recommended
> prompt-armor wrapping.

**Purpose**: deterministic-skill-driven contract for the synthesis step
of `/wiki-extract-concepts`. The orchestrator runs `prepare` to gather
the source body + known-concepts list, loads this skill to learn the
extraction prompt + JSON schema, synthesises candidates in its own
context window, then pipes them to `apply` for validation + persistence.

The split is intentional (TASK 003 v3.1 Decision-17): the Python skill
does the deterministic plumbing (file I/O, DB writes, hash checks,
manifest emission); the LLM does the synthesis. No `import anthropic`
lives in the Python skill.

---

## Inputs from `prepare`

```json
{
  "vault_id": "<vault>",
  "source_slug": "<slug>",
  "source_path": "/absolute/path/to/_sources/<slug>.md",
  "source_hash": "<sha256-hex>",
  "is_unchanged": false,
  "known_concepts": [
    {"slug": "...", "name": "...", "type": "...", "aliases": [...]}
  ],
  "missing_concept_files": ["..."]
}
```

The orchestrator must:

1. Short-circuit if `is_unchanged == true` (UC-09 v3.1 Scenario A — the
   source body has not changed since the last successful `apply`).
2. Read the source body from `source_path` (it's a vault-relative path
   already validated inside the vault root).
3. Run the synthesis prompt below with `source_body` + `known_concepts`.
4. Invoke `wiki-extract-concepts apply ... --source-hash <source_hash>`
   with the synthesised candidates array on stdin or via
   `--candidates-file PATH`.

---

## Extraction prompt (verbatim — DO NOT REWORD)

The prompt below is lifted from the v2 `_build_extraction_prompt`
(scripts/wiki_skills/wiki_extract_concepts.py) — the wording is the
shape that worked in production. Don't paraphrase. Don't "improve". The
phrasing controls model behaviour; identical prompt = identical
synthesis behaviour.

```text
You are a knowledge-graph entity extractor for a personal wiki.
Identify 3-10 key concepts mentioned in the source page below.

Known concepts already in this vault — USE THE EXACT slug + name when a
mentioned concept matches an entry here (so the wiki can de-duplicate):
<JSON-encoded known_concepts array, or [] if empty>

Source page body:
<full source body, untrimmed>

Reply with ONLY a JSON array (no prose, no markdown fence). Each item
MUST be a JSON object with exactly these keys:
{"slug": kebab-case-string,
 "name": "Human Name",
 "definition": "1-3 sentences",
 "source_quote": "10-50 words verbatim from the source body",
 "source_span": "L<start>-L<end>" (1-indexed lines from the source),
 "entity_type": one of [concept, person, company, product, group,
                        event, work, external]}.
```

---

## JSON candidates contract (strict)

The `apply` subcommand validates the candidates array via
`_validate_candidates_schema`. Violations raise structured envelopes
(`{error, field?, reason}`) with exit code 4. **Envelope values NEVER
echo the offending input content (CWE-117 / CWE-209 invariant).**

### Top-level shape

```json
[ {candidate-1}, {candidate-2}, ... ]
```

- Array (not object). Top-level non-array → `EXTRACTION_PARSE_ERROR`.
- `1 ≤ length ≤ 25`. Out of bounds → `CANDIDATE_COUNT_OUT_OF_BOUNDS`.

### Per-candidate shape

| Key | Type | Constraints | Violation envelope |
|---|---|---|---|
| `slug` | string | regex `^[a-z0-9][a-z0-9-]{0,62}$` (kebab-case) | `EXTRACTION_PARSE_ERROR` |
| `name` | string | `1 ≤ len ≤ 200` chars | `FIELD_TOO_LONG` |
| `definition` | string | `1 ≤ len ≤ 2000` chars | `FIELD_TOO_LONG` |
| `source_quote` | string | `1 ≤ len ≤ 500` chars; SHOULD be a verbatim substring of `source_body` | `FIELD_TOO_LONG` / `FIELD_QUOTE_NOT_IN_BODY` |
| `source_span` | string | regex `^L\d+-L\d+$`, 1-indexed | `EXTRACTION_PARSE_ERROR` |
| `entity_type` | string | one of `{concept, person, company, product, group, event, work, external}` | `EXTRACTION_PARSE_ERROR` |

- **No extra keys.** Strict equality on the key set. Extras →
  `UNKNOWN_FIELD` with the offending key name in `field` (but never the
  value).
- **No missing keys.** Subset check fails → `EXTRACTION_PARSE_ERROR`.

### Quote-in-body invariant (M-5)

When `apply` is invoked, the validator checks that each candidate's
`source_quote` is a verbatim substring of `source_body`. This catches
hallucinated quotes early. Bypass via env var
`WIKI_EXTRACT_NO_QUOTE_CHECK=1` (only for edge cases — e.g. translated
or paraphrased quotes; document in the apply call).

---

## De-duplication rule (R-34)

If a concept mentioned in the source body matches an entry in
`known_concepts` (by `slug`, `name`, or any `alias` — case-insensitive),
the candidate's `slug` and `name` MUST be the EXACT values from the
`known_concepts` entry. This lets `apply` classify the candidate as a
`mention` (re-link only) rather than a `create` (new concept page).
Inventing a new variant slug for an existing concept produces a
duplicate entity row.

---

## Example orchestrator invocation

```text
1. PREPARE: wiki-extract-concepts prepare --vault trade-agents \
     --vault-root /vaults/trade-agents \
     --source-page self-improving-agent
   → reads JSON envelope {source_hash, is_unchanged, known_concepts, ...}

2. SHORT-CIRCUIT: if is_unchanged: exit 0 (UC-09 v3.1 Scenario A).

3. LOAD SKILL: Skill({skill: "concept-extraction"}) — loads this file.

4. READ SOURCE: read the file at source_path.

5. SYNTHESIZE: apply the extraction prompt above to source_body +
   known_concepts. Produce candidates JSON array per the contract.

6. APPLY: wiki-extract-concepts apply --vault trade-agents \
     --vault-root /vaults/trade-agents \
     --source-page self-improving-agent \
     --source-hash <hash-from-step-1> \
     --orchestrator-id claude-opus-4-7 \
     --candidates-stdin <<<"$(generated_candidates_json)"
   → exit 0 + manifest envelope on success.
```

---

## Exit codes (R-42, from `apply`)

| Code | Envelope | Cause |
|---|---|---|
| 0 | manifest | success |
| 2 | `SOURCE_CHANGED_DURING_EXTRACTION` / `INVALID_CANDIDATES_PATH` | source body changed mid-extraction (re-run `prepare`) / candidates-file outside vault |
| 4 | `EXTRACTION_PARSE_ERROR` / `UNKNOWN_FIELD` / `FIELD_TOO_LONG` / `CANDIDATE_COUNT_OUT_OF_BOUNDS` / `FIELD_QUOTE_NOT_IN_BODY` / `CANDIDATES_TOO_LARGE` | candidates payload validation failures |
| 5 | `PARTIAL_INDEX_FAILURE` | `--ingest` dispatch reported failed pages (C-1: source_state NOT updated; safe to retry) |
| 6 | `MANIFEST_INVALID` | manifest schema violation |

---

## Out of scope

- `--llm-standalone` Pattern-C escape hatch (TASK 003 v3.1 §1.2).
- Hash-pinning of this SKILL file in manifest provenance (deferred).
- Batched N-source-page synthesis surface (P-1, P-7).
