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

**RAG Query Layer CLI (TASK 007):** `wiki-query` is a two-subcommand `prepare`/`apply` skill (Decision-17 — no `anthropic` import; orchestrator owns synthesis via the `wiki-query-synthesis` prompt skill). `prepare "<question>" --vault V --vault-root P [--vaults|--types|--project|--limit|--no-expand-aliases|--slug|--min-hits]` emits a retrieval envelope `{vault_id, question, query_slug, question_hash, is_unchanged, retrieved_count, hits[]}`; `apply --query-slug S --question-hash HEX (--answer-stdin|--answer-file) (--citations-stdin|--citations-file) [--orchestrator-id|--force]` files `_queries/<slug>.md` + indexes it. Error codes (independent space): `INVALID_QUESTION`/`INVALID_QUERY`/`INVALID_SLUG`/`NO_CONTEXT`/`QUESTION_CHANGED`/`INVALID_QUESTION_HASH` (exit 2), `ANSWER_TOO_LARGE`/`NO_CITATIONS`/`CITATION_NOT_RETRIEVED`/`INVALID_CITATIONS` (exit 4) — same `{error, field?, reason}` CWE-117/209 envelope. New `IndexRepository` methods: `check_query_state` / `record_query_state` (thin `source_state` wrappers, **not** raw `repo._connect()` SQL); retrieval reuses `expand_query_aliases`+`search_pages`, write-back reuses `upsert_page`+`replace_refs(ref_type='cited')` on one connection (no manifest/`main(argv)` N+1). Reindex gains a type-aware `cites:`→`'cited'` read-side (R-6.5e). Full contract in [functional-architecture.md](./functional-architecture.md) §2.1 (RAG Query Layer).

**Verification Layer CLI (TASK 008):** `wiki-verify-multi` is a two-subcommand `prepare`/`apply` skill (Decision-17 — no `anthropic` import; orchestrator owns the four-critic audit via the `wiki-verify` prompt skill). It is **off-by-default** — `wiki-query` never calls it. `prepare <query-slug> --vault V --vault-root P [--slug S]` loads the audited query page + its cited source bodies (via `pages.file_path`, layout-agnostic) and emits a verification envelope `{vault_id, query_slug, question, answer_hash, is_unchanged, verification_slug, examined[], examined_count}`; `apply --verification-slug S --query-slug Q --answer-hash HEX (--verdict-stdin|--verdict-file) [--fail-on {…}|--orchestrator-id|--force]` files `_verifications/<slug>.md` + indexes it + writes the `verifies` backlink, and **returns a non-zero exit (6 `VERDICT_FAIL`) on a FAIL verdict without mutating the answer**. Error codes (independent space): `QUERY_NOT_FOUND`/`NO_SOURCES`/`ANSWER_CHANGED`/`INVALID_ANSWER_HASH`/`INVALID_SLUG` (exit 2), `INVALID_VERDICT`/`VERDICT_PARSE_ERROR`/`VERDICT_TOO_LARGE`/`FINDING_SOURCE_NOT_EXAMINED`/`INVALID_VERIFICATION_PAGE` (exit 4), and **VERDICT_FAIL at exit 6 — a non-error verdict signal that is NOT a distinct code**: `INVALID_INDEX_DB` (inherited from `build_repo_config`) also exits 6, with an error envelope, having filed nothing. Callers branch on the presence of an `error` key, never on `$? == 6`. Envelopes uphold the CWE-117/209 **no-echo** guarantee — `{error, field?, reason}` for most, `{error, integrity}` for `SKILL_INTEGRITY_DRIFT` and a `hint`-bearing variant for `INVALID_INDEX_DB`, none of which echo a value. New `IndexRepository` methods: `check_verify_state` / `record_verify_state` (the `source_state` sibling of the query-state pair); write-back reuses `upsert_page`+`replace_refs(ref_type='verifies' [+ 'cited'])` on one connection. Reindex gains a `type=verification` `verifies:`→`'verifies'` read-side (R-8.5e, generalising R-6.5e). **Schema v4→v5** (the verdict-page type + `verifies` ref + `verify` event are not pre-provisioned — unlike R-6). Full contract in [functional-architecture.md](./functional-architecture.md) §2.1 (Verification Layer).

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


### 5.4. Sync Dispatcher — `wiki-sync` (TASK 018 / R-11)

**CLI surface (deterministic core — two subcommands, as shipped):**

```
wiki-sync scan   <zone> [--vault <vid>] [--vault-root <path>] [--dry-run] [--db-path <p>]
wiki-sync record <vault-rel-path> --source-hash <sha256> --vault <vid> [--db-path <p>]
```

- **`scan`** walks the zone (its **own** bounded walk — *not* `iter_pages`, which is
  `.md`-only; EC-1/ID-5), classifies each file, and emits the **plan JSON** envelope
  on stdout (full schema in `functional-architecture.md` → *Sync Dispatcher → Plan
  JSON*). It is **deterministic** (no LLM, no network, no mutation) and reads the
  `wiki-sync` `source_state` partition for `is_unchanged`. A `.md` over
  `WIKI_SYNC_MD_MAX_BYTES` (8 MiB) is **skipped (`oversize-source`) before any
  read** — the one unbounded-RAM lever, bounded (vdd-multi SEC-MED); the
  convert/text hash read is chunk-streamed.
- **`record`** is the executor's post-success **commit-marker** (the only way the
  orchestrator workflow — not Python — can write the DAL): it `set_source_state`s
  the `sync` row so the next `scan` short-circuits the file as `is_unchanged`.
  Called by `workflows/wiki-sync.md` **only** after a file's pipeline *fully*
  succeeds (a partial failure records nothing → the file is re-planned). Validates
  a 64-hex `--source-hash` + a **canonical** vault-relative `path` (no
  `..`/`.`/NUL/control/backslash/absolute; `pp.as_posix()==path`); a FK-miss on an
  unregistered vault → `VAULT_NOT_REGISTERED`. *(The spec earlier named only
  `set_source_state`; `record` is its necessary orchestrator-facing CLI surface.)*
- **`--dry-run`** prints the human-readable plan (per-file action + reason + action
  counts) and writes nothing — identical classification, presentation only.
- Zone is a CLI arg (MVP); persistent multi-zone config lives in
  **`<vault>/.wiki/sync.yaml`** (`zones`, `exclude`, `tag_namespace`, `extensions`),
  validated against a new **`config/sync-config.schema.yaml`** (strict, like
  `layout-config`; a misspelled key is a load error; `exclude`×`keep` precedence
  pinned at the loader — META-4). The loader is hardened against an untrusted file:
  (0) **full-path symlink containment** — the leaf is refused if symlinked AND the
  resolved path must be inside the vault (so a symlinked *parent* `.wiki/` cannot
  redirect the read out-of-vault; vdd-multi SEC-MED); (1) a **256 KiB size-cap**
  (`stat().st_size` before read); (2) a custom **`SafeLoader` that forbids YAML
  anchors/aliases** + maps `RecursionError` (deep-nesting DoS) to a controlled
  error — note `yaml.safe_load` alone does NOT stop an anchor-bomb (it still
  expands aliases; SEC-A5/SEC-N3), so the size-cap + anchor-ban + recursion-guard
  together are the bound.

**Exit codes (consistent with the suite):** `0` ok · `2` precondition
(`scan`: zone missing / not inside the vault / vault unregistered; `record`:
`INVALID_HASH` / `INVALID_PATH` / `VAULT_NOT_REGISTERED`) · `6` config-invalid
(`.wiki/sync.yaml` schema violation / symlink / oversize / anchor / deep-nesting).
The error envelope never echoes untrusted file content (CWE-209/117).

**DAL surface (corrected — the earlier "no new DAL surface" claim was wrong, F2/ID-2/CONS-2).**
`wiki-sync` adds **two generic, zero-DDL `source_state` methods** to `IndexRepository`
/ `SQLiteRepository` (pure DML on the existing table; no schema change):
`get_source_state(vault_id, source_kind, scope, key) -> str | None` (read, used by
`scan`) and `set_source_state(vault_id, source_kind, scope, key, value) -> None`
(write, used by the executor as the post-success commit marker). These generalise the
query-specific `check_query_state`/`record_query_state` (which are keyed
`source_kind='query'` and cannot represent a raw `sync` drop). The **executor**
(`workflows/wiki-sync.md`) composes the *existing* CLIs — `wiki-import`
(the converged per-source engine, TASK 046), `wiki-index-upsert`, `wiki-extract-concepts`
— + the harness `docx`/`pdf`/`pptx`/`xlsx` convert skills + the transcript-fetcher `.vtt` cleaner. **No new `pages.type`; zero
DDL** (`user_version` 5; the new `source_kind='sync'` partition is data on the
existing `source_state` table).

---
