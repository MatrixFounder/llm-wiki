# 5. Interfaces

> Part of [docs/ARCHITECTURE.md](../ARCHITECTURE.md).


### 5.1. External APIs

**No exposed APIs.** Вся система — local CLI (Claude Code skills). Внешние API только потребляются:
- **Anthropic API** (Claude Haiku/Sonnet) — для `wiki-source-light`. HTTPS, JSON, key-auth via `ANTHROPIC_API_KEY` env.
- **Future** (Epic 6): Gmail-MCP (OAuth), Telegram MTProto (session keys via GramJS), Exa/Perplexity/Firecrawl MCPs.

### 5.2. Internal Interfaces

**Skill ↔ Skill**: через subprocess + stdout JSON contract. Каждый skill эмиттит:

```json
{
  "action": "added" | "updated" | "unchanged" | "skipped",
  "slug": "...",
  "details": { ... }
}
```

или error envelope:

```json
{
  "error": "ERROR_CODE",
  "message": "...",
  "file": "..."
}
```

**Skill ↔ DAL**: через Python imports. `make_repo(config)` factory.

**Entity Resolver CLIs (TASK 005):** `wiki-confirm` / `wiki-alias` / `wiki-merge` follow the same success (`{status|action, slug, …}`) and error (`{error, field?, reason}`) envelopes. `wiki-confirm`/`wiki-alias` error codes: `ENTITY_NOT_FOUND` (exit 3), `ENTITY_FILE_MISSING` (exit 4), `ALIAS_COLLISION` (exit 5). `wiki-merge` owns an **independent** code space (no cross-binary collision): `ENTITY_NOT_FOUND` (3), `ENTITY_FILE_MISSING` (4), `INVALID_MERGE` self-merge (5), `MERGE_MIRROR_FAILED` Class-A-mutated-DB-failed (6) — all illustrative, finalised in Planning against the `wiki-extract-concepts` code space. New `IndexRepository` methods: `set_entity_candidate`, `list_candidates`, `recompute_mentions`, `auto_promote_candidates`, `add_alias` / `remove_alias` / `list_aliases`, `expand_query_aliases`, `find_alias_collisions`, `merge_entities`, plus `resolve_entity` (now implemented) and `find_orphan_links` (now alias-aware, R-4.5d). Full signatures in [functional-architecture.md](./functional-architecture.md) §2.1 (Index Layer + Entity Resolver).

**RAG Query Layer CLI (TASK 007):** `wiki-query` is a two-subcommand `prepare`/`apply` skill (Decision-17 — no `anthropic` import; orchestrator owns synthesis via the `wiki-query-synthesis` prompt skill). `prepare "<question>" --vault V --vault-root P [--vaults|--types|--project|--limit|--no-expand-aliases|--slug|--min-hits]` emits a retrieval envelope `{vault_id, question, query_slug, question_hash, is_unchanged, retrieved_count, hits[]}`; `apply --query-slug S --question-hash HEX (--answer-stdin|--answer-file) (--citations-stdin|--citations-file) [--orchestrator-id|--force]` files `_queries/<slug>.md` + indexes it. Error codes (independent space): `INVALID_QUESTION`/`INVALID_QUERY`/`INVALID_SLUG`/`NO_CONTEXT`/`QUESTION_CHANGED`/`INVALID_QUESTION_HASH` (exit 2), `ANSWER_PARSE_ERROR`/`ANSWER_TOO_LARGE`/`CITATION_NOT_RETRIEVED`/`INVALID_CITATIONS` (exit 4) — same `{error, field?, reason}` CWE-117/209 envelope. New `IndexRepository` methods: `check_query_state` / `record_query_state` (thin `source_state` wrappers, **not** raw `repo._connect()` SQL); retrieval reuses `expand_query_aliases`+`search_pages`, write-back reuses `upsert_page`+`replace_refs(ref_type='cited')` on one connection (no manifest/`main(argv)` N+1). Reindex gains a type-aware `cites:`→`'cited'` read-side (R-6.5e). Full contract in [functional-architecture.md](./functional-architecture.md) §2.1 (RAG Query Layer).

**Verification Layer CLI (TASK 008):** `wiki-verify-multi` is a two-subcommand `prepare`/`apply` skill (Decision-17 — no `anthropic` import; orchestrator owns the four-critic audit via the `wiki-verify` prompt skill). It is **off-by-default** — `wiki-query` never calls it. `prepare <query-slug> --vault V --vault-root P [--slug S]` loads the audited query page + its cited source bodies (via `pages.file_path`, layout-agnostic) and emits a verification envelope `{vault_id, query_slug, question, answer_hash, is_unchanged, verification_slug, examined[], examined_count}`; `apply --verification-slug S --query-slug Q --answer-hash HEX (--verdict-stdin|--verdict-file) [--fail-on {…}|--orchestrator-id|--force]` files `_verifications/<slug>.md` + indexes it + writes the `verifies` backlink, and **returns a non-zero exit (6 `VERDICT_FAIL`) on a FAIL verdict without mutating the answer**. Error codes (independent space): `QUERY_NOT_FOUND`/`NO_SOURCES`/`ANSWER_CHANGED`/`INVALID_ANSWER_HASH`/`INVALID_SLUG` (exit 2), `INVALID_VERDICT`/`VERDICT_PARSE_ERROR`/`VERDICT_TOO_LARGE`/`FINDING_SOURCE_NOT_EXAMINED`/`INVALID_VERIFICATION_PAGE` (exit 4), `VERDICT_FAIL` (exit 6, a non-error verdict signal cleanly distinct from 1/2/4) — same `{error, field?, reason}` CWE-117/209 envelope. New `IndexRepository` methods: `check_verify_state` / `record_verify_state` (the `source_state` sibling of the query-state pair); write-back reuses `upsert_page`+`replace_refs(ref_type='verifies' [+ 'cited'])` on one connection. Reindex gains a `type=verification` `verifies:`→`'verifies'` read-side (R-8.5e, generalising R-6.5e). **Schema v4→v5** (the verdict-page type + `verifies` ref + `verify` event are not pre-provisioned — unlike R-6). Full contract in [functional-architecture.md](./functional-architecture.md) §2.1 (Verification Layer).

**DAL ↔ SQLite**: через stdlib `sqlite3` module. Все queries — parameterized statements. Никакого f-string concatenation.

**Adapter ↔ External Skill (transcript)**: Subprocess. Capture stdout, проверить exit code, расковырять JSON envelope.

### 5.3. Integrations with External Systems

| System | Purpose | Protocol | Error Handling |
|---|---|---|---|
| `summarizing-meetings` skill | Generate full pyramid transcript summary | Subprocess, JSON via stdout | Exit code != 0 → fail-fast с user-friendly message |
| Anthropic API (Claude) | LLM call для `wiki-light-summary` | HTTPS POST `/v1/messages` | Rate-limit → exponential backoff (3 retries); auth error → fail-fast |
| Filesystem (markdown vault) | Source-of-truth для контента | POSIX | Atomic writes (`tempfile + os.replace`); read-only on `_raw/` |
| SQLite | Index storage | Library API | WAL retry on `database is locked`; corruption → `PRAGMA integrity_check` + restore from markdown |

---

