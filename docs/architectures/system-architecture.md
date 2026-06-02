# 3. System Architecture

> Part of [docs/ARCHITECTURE.md](../ARCHITECTURE.md).


### 3.1. Architectural Style

**Layered Architecture** (5 layers):

| Layer | Responsibility | Components |
|---|---|---|
| **L1: Skill Layer** | User-facing entry points. Argument parsing, output formatting, JSON envelopes. | `wiki-init`, `wiki-search`, `wiki-lint`, etc. |
| **L2: Workflow Layer** | Multi-step orchestration, dispatch, error-handling chains. | `ingest-source` workflow |
| **L3: Source Adapter Layer** | Pluggable input normalizers. Common contract. | `wiki-source-manual / -transcript / -light` |
| **L4: Index Layer (DAL)** | Storage abstraction. Repository pattern. Single-place SQL. | `IndexRepository` + `SQLiteRepository` |
| **L5: Storage** | Persistence: filesystem + SQLite. | Markdown vault + SQLite DB |

**Justification**:
- **Simplicity** (skill-architecture-design TIER 0): Layers — простейшая модель для CLI-tool с DB.
- **No microservices**: single-user, single-machine — overkill.
- **No event-driven**: операции синхронные, сложность очередей не оправдана.
- **No frameworks**: stdlib `sqlite3` + `argparse` + `python-frontmatter` — достаточно. Никакого ORM (SQL queries напрямую через repository).
- **Pluggable adapters**: даёт extensibility под будущий email/telegram (Epic 6) без переделки L1/L2/L4.
- **Repository pattern**: позволяет swap SQLite → Postgres через config (R-04). **Test-isolation bonus**: skill unit-tests используют in-memory mock `IndexRepository` (no real SQLite файл, no FS pollution, fast tests).

### 3.2. System Components

#### Component: **wiki-init** (Skill)

- **Type**: Python CLI script + skill markdown wrapper.
- **Purpose**: Bootstrap нового vault'а. Implements UC-01.
- **Implemented Functions**: Configuration resolution, iCloud detection, SQLite creation, vault_metadata seeding, directory mkdir, CLAUDE.md template write.
- **Technologies**: Python 3.11+, `sqlite3` (stdlib), `pathlib`, `hashlib` (sha256), `pyyaml`, `jsonschema`.
- **Interfaces**:
  - **Inbound**: User via `/wiki-init [--root ...] [--language ...] [--non-interactive]`.
  - **Outbound**: filesystem (mkdir, write CLAUDE.md), SQLite (apply DDL, seed vault_metadata).
- **Dependencies**: `python-slugify`, `pyyaml`, `jsonschema`. Internal: Configuration Resolver, Index Layer (для DDL apply).

#### Component: **IndexRepository** (DAL abstract base)

- **Type**: Python abstract class (`abc.ABC`).
- **Purpose**: Generic interface для всех storage operations. Скрывает SQL/SQLite-specific код от skills.
- **Implemented Functions**: 15 methods listed в TASK §3 I-2.1.
- **Technologies**: Python 3.11+ ABC, dataclasses.
- **Interfaces**:
  - **Inbound**: Skills + Source Adapters call via `make_repo(config)` factory.
  - **Outbound**: Concrete implementations (`SQLiteRepository`, future `PostgresRepository`).
- **Dependencies**: None (это сам по себе абстрактный contract).

#### Component: **SQLiteRepository** (DAL concrete)

- **Type**: Python class implementing `IndexRepository`.
- **Purpose**: SQLite-specific implementation. WAL mode, FTS5 queries, JSON-extract для frontmatter, atomic transactions.
- **Implemented Functions**: ALL `IndexRepository` methods.
- **Technologies**: `sqlite3` (stdlib, version ≥ 3.38), `python-slugify`, `python-frontmatter`. Опц. `sqlite-vec` (.dylib/.so) для future vector layer.
- **Interfaces**:
  - **Inbound**: Through `IndexRepository` interface.
  - **Outbound**: SQLite filesystem (`<db_path>.db`).
- **Dependencies**: SQLite library (system или bundled). DDL из `sql/wiki-index.sql` (= `SCHEMA-DRAFT.sql`).

#### Component: **wiki-index-upsert** (Skill — standalone-only entry point)

- **Type**: Python CLI script + skill markdown wrapper.
- **Purpose**: Standalone skill для index upsert одной markdown-страницы которая **уже** на диске. **НЕ** вызывается изнутри Source Adapter chain — adapter сам вызывает `repo.upsert_page(...)` напрямую (см. §3.2 «Adapter <-> repository contract»: single transactional boundary, no subprocess overhead, нет race window). Это избегает дублирования и double-write semantics.
- **Когда вызывается**:
  1. Пользователь вручную: `/wiki-index-upsert --page <path>` для already-on-disk файла, который не нуждается в normalization (manual workflow альтернатива `wiki-source-manual` adapter).
  2. `wiki-lint --fix` для re-индексации orphan'ов (drift fix).
  3. Bulk migration script для tmp2/ (I-5.2 sequential calls).
- **Implemented Functions**: Read file, parse frontmatter, `repo.upsert_page(...)`, `repo.replace_refs(...)`, return JSON envelope.
- **Technologies**: Python 3.11+, `python-frontmatter`.
- **Interfaces**:
  - **Inbound**: `/wiki-index-upsert --page <path>`.
  - **Outbound**: SQLite via Index Layer.
- **Dependencies**: Configuration Resolver, Index Layer.
- **Implements**: R-07.
- **Distinct from `wiki-source-manual` adapter**: adapter does input validation + path-traversal check + (LLM if applicable) + write markdown → then upsert. This skill assumes markdown is already valid and on-disk — only does upsert. Different responsibilities; canonically called for different scenarios.

#### Component: **wiki-index-render** (Skill)

- **Type**: Python CLI script + skill markdown wrapper.
- **Purpose**: Generate `index.md` (read-only projection) from SQLite. Implements UC-05 step 7. Auto-shards если pages > 200 → создаёт `00-Vault-Index/by-{category}.md` shards + `index.md` router.
- **Implemented Functions**: SQL query через `repo.search_pages(...)` (или `repo.list_pages(...)` если добавлен в IndexRepository v2), grouping by `wiki.index_render.group_by`, markdown rendering, atomic write через tempfile.
- **Technologies**: Python 3.11+. Reuses Index Layer.
- **Interfaces**:
  - **Inbound**: `/wiki-index-render [--scope vault|project] [--out <path>]`.
  - **Outbound**: Atomically writes `<vault>/00-Vault-Index/index.md` (overwrite). 
- **Dependencies**: Configuration Resolver, Index Layer.
- **Implements**: R-08.

#### Component: **wiki-search** (Skill)

- **Type**: Python CLI script + skill wrapper.
- **Purpose**: FTS5-backed text search. Implements UC-03.
- **Implemented Functions**: `repo.search_pages(...)` + markdown rendering + co-occurrence collection (для concept-type queries).
- **Technologies**: Python 3.11+. Reuses Index Layer.
- **Interfaces**:
  - **Inbound**: User via `/wiki-search "query" [--type ...] [--project ...] [--limit N]`.
  - **Outbound**: stdout markdown formatted output.
- **Dependencies**: Configuration Resolver, Index Layer.

#### Component: **wiki-lint** (Skill)

- **Type**: Python CLI script + skill wrapper.
- **Purpose**: Health-check корпуса через SQL. Implements UC-04.
- **Implemented Functions**: 9 чеков (orphan, missing-backlinks, stale, frontmatter, taxonomy, drift, log-gaps, duplicate-concepts strict-only, external-only-orphans). Все через SQL.
- **Technologies**: Python 3.11+, `sqlite3`. Markdown rendering для report.
- **Interfaces**:
  - **Inbound**: User via `/wiki-lint [--root ...] [--fix] [--report ...] [--strict]`.
  - **Outbound**: Markdown report file + JSON sidecar. Опц. `--fix` apply mutations.
- **Dependencies**: Configuration Resolver, Index Layer, filesystem walk (для drift).

#### Subsection: **SourceAdapter Interface** (abstract contract — R-06.1)

Все Source Adapters имплементируют этот контракт. Спрятан в `scripts/wiki_source/base.py`.

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator, Optional

@dataclass
class SourceItem:
    """Один атомарный input — manual md-file, light text-chunk, transcript path."""
    source_kind: str            # 'manual' | 'transcript' | 'light' | future 'email'/'telegram'/'web'
    source_id: str              # для manual = file path, для light = sha256(text), для transcript = transcript path
    timestamp: str              # ISO-8601, when item was fetched/seen
    sender: Optional[dict]      # {name, email, telegram_handle} — для cross-source entity resolution (future Epic 6)
    recipients: list[dict]      # same — future use
    subject: Optional[str]      # для emails/light = title; для manual/transcript = file basename
    body: str                   # raw markdown / raw text content
    metadata: dict              # source-specific fields

@dataclass
class SourceOutput:
    """Что adapter возвращает после обработки SourceItem."""
    file_path: str              # relative to vault — куда положили markdown
    interaction_id: Optional[str]  # для future Epic 6 (interactions table); None в MVP
    summary_excerpt: str        # first 200 chars of generated/indexed summary

class SourceAdapter(ABC):
    """Каждый источник имплементирует этот interface. Контракт R-06.1."""

    @property
    @abstractmethod
    def kind(self) -> str:
        """'manual' | 'transcript' | 'light' | future 'email'/'telegram'/'web'."""

    @abstractmethod
    def authenticate(self, config: dict) -> None:
        """First-run setup. manual/light/transcript: no-op. Future email: OAuth flow.
        Idempotent — повторный вызов не делает re-auth если уже OK."""

    @abstractmethod
    def fetch(self, since: Optional[str] = None) -> Iterator[SourceItem]:
        """Pull новых items. Для manual/light — single-shot (yield один SourceItem из argv).
        Для future pull-источников — pagination + dedup через source_state.
        `since` = ISO-8601; если None — adapter решает default (e.g., last 3 days)."""

    @abstractmethod
    def normalize_to_md(self, item: SourceItem, vault_paths: dict, repo: 'IndexRepository') -> SourceOutput:
        """Сгенерировать markdown с frontmatter, записать в vault, вызвать repo.upsert_page().
        Returns SourceOutput. Errors — raise SourceAdapterError(code, message)."""

    @abstractmethod
    def dedup_state_file(self, config: dict) -> Optional[str]:
        """Путь к .state.json для этого adapter'а. None для manual/light/transcript (нет state).
        Для future email/telegram — путь к persistent dedup state."""


class SourceAdapterError(Exception):
    """Унифицированная ошибка из adapter'а. Передаётся в JSON envelope."""
    def __init__(self, code: str, message: str, details: Optional[dict] = None):
        self.code = code           # 'INVALID_FRONTMATTER' | 'PATH_OUTSIDE_VAULT' | 'LLM_RATE_LIMIT' | etc.
        self.message = message
        self.details = details or {}
```

**Error envelope contract** — все adapters при failure возвращают (через workflow JSON output):

```json
{"error": "<code>", "message": "<human-readable>", "details": {<context>}}
```

with non-zero exit code. Common codes (defined в `scripts/wiki_source/base.py`):
- `INVALID_FRONTMATTER` — YAML parse error.
- `MISSING_REQUIRED_FIELD` — config-driven required field missing.
- `PATH_OUTSIDE_VAULT` — path-traversal attempt detected (R-26.2).
- `INPUT_TOO_LARGE` — wiki-source-light > 10K chars (per UC-06 §A1).
- `EMPTY_INPUT` — wiki-source-light empty text.
- `LLM_RATE_LIMIT` — Anthropic API throttling после max retries.
- `LLM_AUTH_FAILED` — invalid API key.
- `WORKFLOW_NOT_FOUND` — `/generate-detailed-meeting-summary` workflow или `claude` CLI отсутствует (TASK I-3.3 step a). Error JSON: `{missing: [...], expected_paths: [...]}`.
- `WORKFLOW_TIMEOUT` — subprocess exceeded `wiki.transcript.timeout_seconds` (default 600s). Partial output moved to `_raw/failed/` (TASK I-3.3 step c.1).
- `WORKFLOW_FAILED` — subprocess non-zero exit (TASK I-3.3 step c.1). Includes `exit_code, stderr_tail`.
- `WORKFLOW_INCOMPLETE` — output validation failed (missing SECTION marker, unrendered `{{N}}` fingerprint placeholders) (TASK I-3.3 step d).
- `UNMAPPED_TYPE` — frontmatter `type` ∉ §6.1 mapping table (TASK UC-07 A3).
- `BodyNormalizationError` — unclosed Mermaid fence detected (TASK R-07.5 anti-tail-eat).
- `CONCURRENT_INGEST_TIMEOUT` — flock contention >60s on `.summary.lock` (TASK UC-07 A8).
- `EXTERNAL_SKILL_FAILED` — generic fallback subprocess exit code != 0 (legacy; prefer `WORKFLOW_FAILED`).
- `STATE_FILE_CORRUPT` — .state.json parse error (future Epic 6).

**Adapter <-> repository contract**: adapter calls `repo.upsert_page(...)` сам (внутри `normalize_to_md`). Workflow `ingest-source` НЕ делает upsert — только dispatch + post-actions (log, lint quick-pass). Это explicit чтобы adapter решал atomicity (например, light-summary должен сначала записать markdown, потом upsert; rollback complicated).

**Transactional boundary** (resolves M-3): `repo.upsert_page` обёрнут в `BEGIN IMMEDIATE` ... `COMMIT`. Если внутри — exception, transaction rolls back, FTS5 trigger автоматически undo'ит свои writes (потому что они в той же tx). Markdown файл остаётся on-disk (already-written) — это OK: rerun ingest = idempotent (file_hash check).

#### Component: **wiki-source-manual** (Source Adapter)

- **Type**: Python class implementing `SourceAdapter`.
- **Purpose**: Index already-existing markdown файлов. Не модифицирует body, не перемещает.
- **Implemented Functions**: Path-traversal validation, frontmatter parse, refs extraction, repo.upsert.
- **Technologies**: Python 3.11+, `python-frontmatter`, `python-slugify`.
- **Interfaces**:
  - **Inbound**: `ingest-source --kind manual --source <path>` (через workflow).
  - **Outbound**: Index Layer upsert + log append.
- **Dependencies**: Index Layer, Configuration Resolver.

#### Component: **wiki-source-transcript** (Source Adapter)

- **Type**: Python class implementing `SourceAdapter` + subprocess wrapper над external workflow.
- **Purpose**: Generate educational-overlay pyramid summary from transcript via `/generate-detailed-meeting-summary` **workflow** (НЕ базовый `summarizing-meetings` skill — workflow extends его educational fields, Mermaid, SECTION-anchors, Agent Metadata).
- **Implemented Functions**: (a) Discovery (workflow file + `claude` CLI presence, escape-hatch `WIKI_GENSUMMARY_CMD` env var); (b) Idempotency short-circuit (TASK UC-07 A4 — `source_state` hash query); (c) Subprocess spawn с `timeout=600s`, `TimeoutExpired` handler с partial-file cleanup в `_raw/failed/`; (d) Output validation — `<!-- SECTION:agent-metadata -->` marker + rendered `Content Fingerprint` (NOT `{{N}}` placeholders); (e) Apply TASK R-07.4 (type-mapping `lesson-summary` → `summary`+tag, concepts slugify через `python-slugify`) and R-07.5 (Mermaid+SECTION strip regex, anti-tail-eat on unclosed fence) перед upsert; (f) Persist `source_state.source_hash`; (g) Set `trust_level='medium'` для refs.
- **Technologies**: Python 3.11+, `subprocess`, `flock` (UC-07 A8 concurrent-ingest lock), `python-slugify`. **External dependencies**: `summarizing-meetings` skill + `/generate-detailed-meeting-summary` workflow (git-submodule в `~/.claude/skills/` + `~/.claude/commands/`).
- **Interfaces**:
  - **Inbound**: `/ingest-source --kind transcript --source <transcript-path> --output <output-dir>`.
  - **Outbound**: New markdown summary in `<output-dir>/summary.md` (file frontmatter retains `type: lesson-summary`); `pages` DB row с `type='summary'` + tags `[lesson-summary, ...slugified-concepts]`; `source_state` row для idempotency.
- **Dependencies**: External workflow, Index Layer, Configuration Resolver, `wiki-source-manual` (delegated final upsert).

#### Component: **wiki-source-light** (Source Adapter — R-24)

- **Type**: Python class implementing `SourceAdapter`.
- **Purpose**: Single-call LLM summary для arbitrary md-куска. Не делает full pyramid.
- **Implemented Functions**: Input validation (≤ 10K chars), LLM call (Claude Haiku/Sonnet via Anthropic API), structured response parsing (`{tldr, tags}`), markdown file generation с frontmatter `type: summary` + tag `summary-light`.
- **Technologies**: Python 3.11+, `anthropic` SDK (или httpx + raw API), `python-frontmatter`. Использует Anthropic API key из env (`ANTHROPIC_API_KEY`).
- **Interfaces**:
  - **Inbound**: `/wiki-light-summary --text "..." | --source <path>`.
  - **Outbound**: New markdown в `Summaries/light/<date>-<slug>.md`.
- **Dependencies**: Anthropic API, Index Layer, Configuration Resolver.

#### Component: **ingest-source** (Workflow markdown)

- **Type**: Markdown workflow file в `.claude/commands/ingest-source.md`.
- **Purpose**: Dispatcher и orchestration chain.
- **Implemented Functions**: Detect kind, dispatch adapter, chain to index-upsert + log + opt lint, failure handling.
- **Technologies**: Markdown с YAML frontmatter (Claude Code workflow format).
- **Interfaces**:
  - **Inbound**: User via `/ingest-source --kind X --source Y`.
  - **Outbound**: Calls Source Adapters, ultimately mutates filesystem + SQLite.
- **Dependencies**: Source Adapters, Index Layer.

### 3.3. Components Diagram

```mermaid
graph LR
    subgraph "User Space"
        U[User]
        CC[Claude Code CLI]
    end

    subgraph "L1-2: Skills + Workflow"
        WI[wiki-init]
        WS[wiki-search]
        WL[wiki-lint]
        WLS[wiki-light-summary]
        WIS[ingest-source.md]
    end

    subgraph "L3: Source Adapters"
        SAM[wiki-source-manual]
        SAT[wiki-source-transcript]
        SLT[wiki-source-light]
    end

    subgraph "L4: DAL"
        IR[IndexRepository<br/>abstract]
        SQR[SQLiteRepository]
    end

    subgraph "L5: Storage"
        VAULT[(Markdown Vault<br/>iCloud)]
        DB[(SQLite<br/>~/Library/...<br/>NOT iCloud)]
        SUM[summarizing-meetings<br/>external git-submodule]
        API[Anthropic API]
    end

    U --> CC
    CC --> WI & WS & WL & WLS & WIS
    
    WIS -->|--kind| SAM & SAT & SLT
    WLS --> SLT
    
    SAT -->|subprocess| SUM
    SLT -->|HTTPS| API
    
    SAM & SAT & SLT -->|writes md| VAULT
    SAM & SAT & SLT -->|upsert via| IR
    
    WS --> IR
    WL --> IR
    WI --> IR
    
    IR -.config.-> SQR
    SQR -->|sqlite3 lib| DB
    
    SAM -.reads.-> VAULT
```

### 3.4. Sequence Diagram: UC-08 Concept Extraction Flow

> The Python skill is deterministic plumbing only. LLM-driven synthesis
> happens in the calling agent's context (Claude Code / Gemini CLI /
> Cursor) between the `prepare` and `apply` subprocess calls; the
> synthesis prompt + JSON candidates contract live in operator-facing
> skill `skills/concept-extraction/SKILL.md`. Auth lives entirely in
> the calling agent.

```
Operator
  │
  ├─ /wiki-extract-concepts --vault V --source-page S
  │
  ▼
Calling Agent (Claude Opus 4.7 / Gemini / etc. — runs in OPERATOR'S LLM context)
  │  reads workflows/wiki-extract-concepts.md
  │
  ├─ STEP 1 — DETERMINISTIC RECONNAISSANCE (no LLM call)
  │   Bash: wiki-extract-concepts prepare --vault V --vault-root P --source-page S
  │   │
  │   └─▶ wiki_extract_concepts.py::prepare(args)
  │          ├─ resolve source-page path; validate_inside_vault (R-26)
  │          ├─ stat().st_size check → _MAX_SOURCE_BODY_BYTES (10 MiB) → SOURCE_TOO_LARGE
  │          ├─ read_text() → sha256(body)
  │          ├─ check_idempotency(repo, V, S, sha256) → source_state table query
  │          ├─ load_known_entities(repo, V) → entities ⨝ entity_aliases
  │          └─ emit JSON: {source_path, source_hash, is_unchanged,
  │                          known_concepts, missing_concept_files}
  │
  ├─ STEP 2 — IDEMPOTENCY GATE
  │   if is_unchanged=true → emit {action:"unchanged", manifest:null} to operator, STOP.
  │
  ├─ STEP 3 — LOAD EXTRACTION CONTRACT (calling agent's context)
  │   Skill({skill: "concept-extraction"})
  │   → loads .agent/skills/concept-extraction/SKILL.md into agent context
  │   → contract: 1≤N≤25 candidates, per-field caps (name 200/def 2000/quote 500),
  │     kebab slug regex, Lstart-Lend span, entity_type whitelist, dedup against
  │     known_concepts list, NO extra keys, source_quote substring of body
  │
  ├─ STEP 4 — READ SOURCE BODY (calling agent's tool)
  │   Read(source_path) → source body in agent's context window
  │   (NOT a double-read: prepare already returned source_path, NOT source_body —
  │    avoids 100KB-payload-via-Bash-output design smell)
  │
  ├─ STEP 5 — SYNTHESIS (calling agent's LLM context, OPERATOR'S subscription/API)
  │   Agent produces candidates JSON array per the loaded contract.
  │   THIS IS THE ONLY LLM-INVOLVED STEP. No Python code touches an LLM API.
  │   No ANTHROPIC_API_KEY. No anthropic SDK. No subagent spawn.
  │
  ├─ STEP 6 — DETERMINISTIC APPLICATION (no LLM call)
  │   Bash: echo '[{...}, {...}]' | wiki-extract-concepts apply \
  │           --vault V --vault-root P --source-page S \
  │           --source-hash <hash-from-prepare> --candidates-stdin \
  │           [--orchestrator-id "claude-opus-4-7"] [--ingest]
  │   │
  │   └─▶ wiki_extract_concepts.py::apply(args)
  │          ├─ recompute source_hash from disk
  │          │     → mismatch with --source-hash → exit 2 SOURCE_CHANGED_DURING_EXTRACTION
  │          ├─ if --candidates-file: validate_inside_vault(path); stat ≤ 1 MiB
  │          ├─ json.loads(stdin or file)
  │          ├─ _validate_candidates_schema (strict mode):
  │          │     count bound, per-field caps, kebab slug, Lstart-Lend,
  │          │     entity_type whitelist, NO extra keys, source_quote ∈ body
  │          │     → on violation → exit 4 + specific sub-envelope (no content echo)
  │          ├─ classify_candidates → (create_list, mention_list)
  │          ├─ for cand in create_list:
  │          │     ├─ write_concept_page (atomic; content-hash skip; refuse symlinks)
  │          │     │       → _concepts/<slug>.md  [Class A]
  │          │     │       → returns (Path, "created"|"updated"|"unchanged")
  │          │     └─ upsert_extracted_entity (canonicalized_by=orchestrator_id)
  │          │           → repo.upsert_entity(is_candidate=1, SQL MIN() downgrade-guard)
  │          ├─ upsert_entity_refs(repo, V, S, project, all_candidates)
  │          │     → repo.replace_refs (atomic; trust_level='medium'; parsed line spans)
  │          ├─ build_manifest → wiki-ingest v1.1-compatible JSON
  │          ├─ (if --ingest) dispatch_to_indexer:
  │          │     ├─ validate_manifest from _manifest_consumer
  │          │     ├─ index_from_manifest from _manifest_consumer (in-process)
  │          │     │     → page upserts + log_event mirror
  │          │     ↳ on failed[] non-empty → exit 5 PARTIAL_INDEX_FAILURE; source_state NOT updated
  │          ├─ update_idempotency_state (gated: success + ingest-failed[] empty)
  │          └─ emit manifest JSON (or {extraction, index} combined if --ingest)
  │
  └─ STEP 7 — operator sees manifest in their chat / shell
```

**Auth boundary**: dotted line between STEP 1 and STEP 6 = subprocess boundary (Python skill); STEP 5 happens entirely in the calling agent's process with its own LLM auth. The Python skill has zero LLM dependency and zero env-var requirements beyond the standard CLI flags.

---

### 3.5. Layout Engine (config-driven) — TASK 012 / R-X1

> **Status:** TASK 012 SHIPPED (2026-06-01). Replaces ~15 hardcoded layout
> surfaces with a YAML-config-driven engine. **Zero DDL** (`user_version` stays 5);
> new doc types route via the TYPE_MAPPING tag-route. Byte-identical for Karpathy
> vaults (the standing §D8 rebuildability invariant, now golden-snapshot-guarded).
> **dev-project `vault_root` = the project's `docs/` directory** (D-012 operator
> decision): the committed dev-vault declaration is `docs/WIKI_SCHEMA.md` and the
> `dev-project.yaml` globs are docs/-root-relative (`tasks/*.md`, `issues/*.md`, …),
> so the repo root carries no vault marker ("repo is not a vault" preserved). This
> repo is itself a live dev-vault (its `docs/issues/*.md` + auto-rendered
> `docs/KNOWN_ISSUES.md`).

#### Two config systems (deliberately separate — D-012-2)

The engine reads from **two** independent config layers that answer different
questions at different times:

| Layer | Files | Scope | Answers | Lifetime |
|---|---|---|---|---|
| **Per-vault identity/policy** (existing, unchanged) | `config_loader.py` + `config/wiki-config.schema.yaml`; `<vault>/WIKI_SCHEMA.md` (+ optional `CLAUDE.md::wiki:`, `.wiki.yaml`) | one vault | "who is this vault?" (`vault_id`, `language`, `layout` name, lint discipline) | read per skill-invocation; `deep_merge` (lists **replace**) |
| **Per-layout-class grammar** (NEW — R-X1) | `layout_config.py` + `config/layout-config.schema.yaml`; built-in `scripts/wiki_index/layouts/{karpathy,dev-project,obsidian-personal}.yaml` | one *layout class* (shared by all vaults of that kind) | "how do I parse this kind of vault?" (`paths[]` globs→type, `ref_extraction[]`, `type_mapping`, `slug_strategy`, `ignore[]`, `file_extensions`, `frontmatter_synthesis`, `auto_indexes[]`) | resolved once per reindex, cached per-vault |

They are kept separate because the per-vault `deep_merge` **replaces** lists wholesale
— wrong semantics for a layered layout grammar (a base built-in + a small operator
patch). The grammar therefore ships **once** with the tool, and `WIKI_SCHEMA.md`
merely *names* the layout.

#### Component: **LayoutConfig + loader** (`scripts/wiki_index/layout_config.py`)

- **Resolution:** `root_config["layout"]` → alias map (`flat`/`per-project` →
  `karpathy`) → built-in `layouts/<name>.yaml` (base) → optional per-vault override
  (`WIKI_SCHEMA.md` frontmatter `layout_config:` *or* conventional
  `<vault>/.wiki/layout.yaml`; explicit frontmatter wins) **deep-merged over the
  base** → validated against `layout-config.schema.yaml`.
- **Override merge policy (Q-012-f → resolved):** `paths[]` and `ref_extraction[]`
  are **replaced** if the operator supplies the key (predictable, no partial-list
  surprises); scalar fields overlay. Pinned by schema-validation tests.
- **Validation:** Draft-2020-12 (`jsonschema`, already a dep), **`additionalProperties:
  false` at the `PathEntry` level** — stricter than the per-vault schema, so a
  misspelled key is a load-time exit-6, not a silent `_unmatched_` flood.
- **`LayoutConfig`** = frozen dataclass: `paths[]`, `type_mapping`,
  `path_type_fallback`, `ref_extraction[]`, `slug_strategy`, `ignore[]`,
  `file_extensions`, `frontmatter_synthesis`, `auto_indexes[]`.
- **ReDoS guard (D-012-3, stdlib `re` only) — AS BUILT:** at config-load,
  `_redos_budget_check` runs **both** `ref_extraction[].regex` **and**
  `paths[].project_pattern` (every operator regex) against a **battery of 5
  structurally-diverse short adversarial payloads** (module constants `_REDOS_PAYLOADS`
  — a-run, digit-run, whitespace-run, alternation-cycle, two-runs+tail — so more than
  one backtracker *shape* is caught; `/vdd-multi` HIGH-2 hardened the original
  single-`"a"*N` payload that let `(.*a){50}` slip past). Budget = median of N=5 runs,
  **break-on-over** so the gate itself can't be DoS'd; over-ceiling → **exit 6** before
  any file is read. Built-ins pre-vetted. **Residual — RESOLVED in TASK 017
  (R-X1-REDOS-RT):** a pattern linear on the short payloads but catastrophic only on long
  real *file content* is NOT caught at load; the **Runtime ReDoS deadline** subsection
  below closes it with a per-file deadline at the `extract_refs`/`_derive_project`
  consumer. The gate is **kept** (defense-in-depth) and aligned to probe each pattern under
  the *same* engine it runs under (operator→`regex`, built-in→stdlib `re`).
- **Egress sanitisation (`/vdd-multi` SEC-1) — load-bearing:** the auto-index renderer
  AND `render_index` route every untrusted frontmatter field (`title`/`tldr`/`id`/
  `category`) through `_common.sanitize_markdown_text` before interpolating into
  `[[slug|title]]` / `## <category>`. Without it a crafted `title` injects a `]]`-breakout
  wikilink (graph-poisoning), a `<!-- BEGIN-CUSTOM -->` marker (hijacks preserve-custom on
  the next render), or a `<!-- GENERATED-AT: -->` line (fools the PW-Q drift hash). `slug`
  is the link *target* (slugify-derived) and is left literal.
- **Override load is path-guarded (architecture-review m3 + `/vdd-multi` MED-2):**
  `<vault>/.wiki/layout.yaml` (and a `WIKI_SCHEMA.md` `layout_config:` target) — the
  `is_symlink()` refusal is checked on the **raw** candidate (before any `resolve()`
  dereferences it), then `validate_inside_vault` + `assert_no_symlink_escape` (ancestor
  walk). An operator override is a Class-A vault file but must not escape the vault root.

#### Runtime ReDoS deadline (TASK 017 / R-X1-REDOS-RT — closes the load-gate residual)

The load-gate above is a load-time *heuristic* (short adversarial payloads, 50 ms median
ceiling); it cannot catch a pattern linear on short input but catastrophic only on a long
real file body. TASK 017 adds the sound backstop: a **per-file wall-clock deadline at the
consumer**, applied **only to operator-custom patterns**.

- **Engine selection by provenance.** Built-in `layouts/*.yaml` patterns are pre-vetted and
  stay on **stdlib `re`** (zero overhead, karpathy byte-identity preserved). Only patterns an
  operator *replaces* via a per-vault override run under the **PyPI `regex` engine** with its
  `timeout=`. Provenance is exact and free: the Q-012-f merge policy **replaces** the whole
  `paths[]` / `ref_extraction[]` list when the operator supplies that key, so
  `load_layout_config` records two booleans on the frozen `LayoutConfig`
  (`ref_extraction_operator_supplied`, `paths_operator_supplied`); `resolve_layout_config`'s
  built-in-only path leaves both `False`. **(Resolves Q-017-1.)**
- **Why `regex`, not a watchdog.** Verified on CPython 3.14.4 (standard GIL build): stdlib
  `re` holds the **GIL for the whole match**, so a `signal.alarm`/thread/subprocess watchdog
  cannot reliably interrupt a single C-level `re.search` (a worker thread froze the
  interpreter for the full ~1.37 s; `join(0.3)` did not return). `regex` checks the deadline
  **inside** its backtracking loop: on a regex-catastrophic pattern (`(a|a)*$`) over a
  **100 KB single line**, `search`/`finditer(timeout=0.5)` raised the **builtin
  `TimeoutError`** at 500 ms (+0.2 ms) — no hang — and it *releases the GIL* during matching.
  (`(a+)+$`/`(x+x+)+y` are optimised away by `regex` outright → net ReDoS reduction.)
- **Scope = per-file budget, not per-call (resolves Q-017-2).** `extract_refs` calls
  `finditer` **per line**; a naïve per-call timeout would bound each line to the ceiling →
  worst case `N_lines × ceiling`. The consumer therefore computes one
  `deadline = monotonic() + WIKI_REDOS_BUDGET_S` per file and passes the *remaining* time as
  each call's `timeout=`. Default `WIKI_REDOS_BUDGET_S = 2.0 s` (module constant in
  `layout_config.py`, env-overridable; distinct from the load-gate's 50 ms short-payload
  ceiling) — generous vs a legitimately large *linear* page, tight enough to never hang a
  reindex.
- **Degradation policy (report-and-skip; never raise, never hang).** On `TimeoutError`:
  `extract_refs` returns **empty body-refs** for that file + a WARN (deterministic — partial
  refs would be timing-dependent); the page still indexes for FTS, and any frontmatter-
  declared `cites:`/`verifies:` refs still materialise via the §D8 reindex read-side.
  `_derive_project` returns `UNMATCHED_PROJECT` + a WARN (exact parity with the existing
  pattern-miss policy). WARN/skip reasons name the **file**, never the pattern or body
  (CWE-117/209).
- **Shared guard helper.** Both consumers route through one small helper in
  `scripts/wiki_index/layout_config.py` (importable by `wiki_source/parsing.py`, preserving
  the acyclic import direction) that selects engine by the provenance flag and applies the
  shrinking-deadline `timeout=`. **Both** load-time validators — `_redos_budget_check` *and*
  `_validate_path_patterns` (the `project_pattern` compile + named-group check) — compile
  operator patterns under the **same** `regex` engine that runs them, so load-time and runtime
  share one dialect (a regex-only construct like `\p{L}` is accepted at load; a
  regex-incompatible operator pattern is rejected at load, never crashes at runtime).
  **Dialect note:** operator patterns are authored for stdlib `re`; `regex` V0 mode is
  `re`-compatible (a near-superset) — documented in the layout-config docs + schema notes.
  The eager `import regex` in `layout_config` is negligible (~6 ms cold vs the module's
  already-eager `jsonschema` ~70 ms) — a lazy import would be incoherent, so it stays eager.

#### Engine: `iter_pages(vault_root, config)` — one walk, all slug/project derivation converges

- Per `paths[]` entry, resolve `Path(vault_root).glob(entry.glob)` (native `**`).
  **First-match-wins** in declared order.
- **Walk-cost note (scoped — architecture-review M1):** for **Karpathy-shaped**
  layouts (globs anchored at named subdirs: `_sources/**/*.md`, …) this is
  structurally identical to today's per-subdir `rglob` — the root tree is never
  walked. For **multi-`**`-glob layouts** (obsidian-personal: a `*.md` root
  catch-all + three overlapping `[0-9][0-9] - */…/**/*.md` globs) `Path.glob` runs
  **once per `paths[]` entry**, so deep subtrees get re-walked once per overlapping
  glob (dedup is first-match-wins, *after* enumeration). Bounded + deterministic;
  acceptable at personal-vault scale (§8 = vertical, single-user). If a large
  personal vault ever bites, the optimisation is a single-pass `os.walk` + an
  in-memory per-entry matcher — **YAGNI-gated, not built now.** An NFR pins a
  perf-floor at the obsidian-personal fixture scale to catch a future regression.
- **Single-stat walk (TASK 017 / P-2).** The walk already stats each candidate once (via
  `path.is_file()`). `iter_pages` now derives is-file **and** `st_mtime` from a single
  `os.stat`/`DirEntry` and carries the mtime onto `DiscoveredPage.mtime`, so `reindex_delta`
  reads `disc.mtime` instead of issuing a **second** `path.stat()` per file (was
  `reindex.py:299`) — one stat/file instead of two on the no-op delta path; iteration order +
  match set unchanged (byte-identity). The same `DiscoveredPage.mtime` also feeds the P-3
  `--mtime-skip` drift fast-path (no extra stat in `check_drift`). The full single-pass
  `os.walk` rewrite stays YAGNI-deferred (Walk-cost note above).
- **PW-K `ignore[]`** evaluated before `paths[]`; **PW-M `file_extensions`** allow-list
  (default `[.md]`) skips `.base`/`.canvas`/etc. The engine **also treats
  `layout.py::SYSTEM_FILES` and every `auto_indexes[].output` as an implicit ignore
  set** (architecture-review m1) — so a `*.md` root catch-all never scoops
  `WIKI_SCHEMA.md`/`CLAUDE.md`/`index.md`/`log.md`/`README.md`, and a generated
  Class-B ledger (`docs/KNOWN_ISSUES.md`) can never be re-ingested as a Class-A page
  (closes the render→ingest feedback loop).
- **PW-J `project`** = literal, or `project_pattern` (regex) + `project_template`
  (`string.Template` `${name}` only — no shell ternaries). Error policy:
  regex-compile-fail → exit-6; glob-matches-but-pattern-misses → WARN +
  `project:"_unmatched_"`; template references missing group → exit-6.
- **Output is stably sorted by relative POSIX path** before emit — deterministic and
  independent of filesystem glob order (strictly ≥ today's order; no test asserts
  order).
- **Walk convergence (the C-4 PK-consistency invariant — architecture-review C1):**
  there are **five** physical slug/project-producing walks. `discover_pages(vault_root)`
  becomes the canonical one (keeps its signature; loads config internally, cached;
  delegates to `iter_pages`). `sqlite_repository.check_drift` **already delegates** to
  `discover_pages` (no change). The remaining three **must converge onto it**, comparing
  on `(slug, project)` — **NOT bare `f.stem`**: (1) `sqlite_repository.find_pages_missing_in_index`
  (`sqlite_repository.py:526-549` — today inlines its own `PAGE_SUBDIRS`+`Lessons/` walk
  and compares slug-**only**, a latent course-tier bug; route through `discover_pages`
  and compare on `(slug, project)`); (2) `parsing.py::derive_slug`;
  (3) `wiki_extract_concepts._derive_source_project`. If any walk computes membership via
  `f.stem` while the config path derives slug via `slug_strategy`/`project_pattern`, the
  drift/orphan surface and the reindex surface disagree → false orphans + spurious
  `wiki-lint --fix` re-upserts under a drifted slug (a direct `UNIQUE(vault_id, slug,
  project)` PK-drift hazard).

#### Byte-identity strategy (the load-bearing invariant)

`karpathy.yaml` is a **validated projection of `layout.py`** (constants NOT deleted —
scaffolding, `SYSTEM_FILES`, and the vendored `wiki_ingest.DEFAULT_SUBDIRS` drift
guard still depend on them). The invariant test
`test_karpathy_config_matches_layout_constants` ties the two. **Three slug surfaces
stay distinct**: page slug = `slug_strategy: identity` (verbatim `path.stem`); course
project = loose `slugify`; concept-tag slug = `_slugify_concept` (strict, **untouched**).
The PW-L strategies (`preserve-unicode`/`transliterate`/`ascii-only`) all call
slugify and are obsidian-personal-only. A Bead-0 golden snapshot of the current
engine's rows stays green through every bead.

#### Component: **auto_indexes render + lint guard** (PW-H / PW-Q)

- **PW-H** extends `wiki-index-render`: walk `config.auto_indexes[]`, render each
  `output` (e.g. `docs/KNOWN_ISSUES.md`) grouped/sorted from a small Python renderer.
  **Template mechanism (Q-012-e → resolved):** a dependency-free Python renderer
  driven by `group_by` / `sort_within_group`, with an optional
  `assets/<name>.md.tmpl` (`string.Template`) for the surrounding shell — no Jinja
  dependency. Preserves `BEGIN-CUSTOM` blocks; emits a `<!-- GENERATED-AT: … -->`
  header and stores the rendered-body sha256 in `<vault>/.wiki/state.json`.
  **Well-definedness of the rebuildability invariant (architecture-review M2):** the
  rendered body is a **pure deterministic function of the Class-A per-issue files'
  content** — the only volatile value is the single excluded GENERATED-AT header line
  (no `now()`/"opened N days ago"/locale-formatted dates in the body). `sort_within_group`
  carries a **stable total order with a final `id` tiebreaker** (so equal
  `(severity, opened_at)` rows never reorder across machines/clones — the cross-platform
  NFC/NFD/inode hazard). The PW-Q sha256 is computed over the **header-stripped** body.
  The `output` path is `validate_inside_vault`-checked before the atomic write
  (architecture-review m3) — an operator-set `output: ../../etc/x` is refused.
- **Render-trigger contract:** fires on `wiki-reindex --full/--delta`, on explicit
  `wiki-index-render --auto-indexes`, and at the end of any `wiki-index-upsert` batch
  that creates/deletes a page whose **tag-route type** is `known-issue` (the predicate
  keys off the tag/frontmatter marker, not a `pages.type` value — there is no
  `known-issue` enum value; zero-DDL).
- **PW-Q** `lint.py::check_auto_generated_unchanged`: re-render to a temp buffer at
  lint time, compare against the `.wiki/state.json` sha256, flag manual drift. Folded
  into `wiki-lint` (no new CLI).
- **Class-B "rebuildable markdown"** (new §D8 sub-case — see ADR-002 TASK-012
  amendment): `docs/issues/<id>-<slug>.md` are **Class A**; the rendered
  `docs/KNOWN_ISSUES.md` is **Class B** rebuilt from those files (the first Class-B
  markdown rebuilt from *markdown*, not a DB view). Rebuildability test: delete the
  ledger, `--auto-indexes`, byte-identical modulo the GENERATED-AT header.

---

